import time

import bpy
import gpu
import numpy as np

# Thumbnails for the hand-drawn camera grid (ui.py): GPU textures made from
# the image's own pixels, box-downscaled to THUMB px on the long side, in
# the photo's own aspect ratio.
#
# Image.preview is deliberately not used: in Blender 5.2 it is 128 px
# (soft in a 1-column grid) and it only renders when a Blender layout shows
# the icon. Building from pixels costs ~7 ms for 1080p, ~25 ms for 4K
# (pixel read + numpy box filter), so it runs on a timer under a time budget
# per tick, never in draw(). The draw handler only uploads finished pixels
# to the GPU (that needs the GPU context draw provides).

THUMB = 512
_BUDGET = 0.03      # seconds of building per timer tick

RETRY = 10.0        # seconds before a failed build is tried again

_textures = {}      # img name → (GPUTexture, aspect)
_pixels = {}        # img name → float32 (h, w, 4) built, waiting for upload
_failed = {}        # img name → time the build failed (missing file...)
_queue = []         # img names waiting to be built


def _downscale(a, f):
    """Box filter by integer factor f — rows first, then columns (~10x
    faster than reshape().mean() on a 1080p frame)."""
    h, w = a.shape[0] // f, a.shape[1] // f
    a = a[: h * f, : w * f]
    rows = a[0::f].copy()
    for d in range(1, f):
        rows += a[d::f]
    out = rows[:, 0::f].copy()
    for d in range(1, f):
        out += rows[:, d::f]
    return out * (1.0 / (f * f))


def _build(img):
    """float32 RGBA thumbnail of img (0..1), or None if it has no pixels."""
    loaded = img.has_data
    w, h = img.size          # loads the image if it isn't yet
    if w == 0 or h == 0:
        return None
    ch = img.channels
    px = np.empty(w * h * ch, dtype=np.float32)
    img.pixels.foreach_get(px)
    if not loaded:
        # Only the active camera's plate is otherwise ever decoded; don't
        # keep a full-res buffer per listed camera in Blender's image cache
        img.buffers_free()
    a = px.reshape(h, w, ch)
    if ch != 4:
        rgba = np.ones((h, w, 4), dtype=np.float32)
        rgba[..., :3] = a[..., :3] if ch >= 3 else a[..., :1]
        if ch in (2, 4):
            rgba[..., 3] = a[..., ch - 1]
        a = rgba
    f = -(-max(w, h) // THUMB)      # ceil: the long side ends up <= THUMB
    if f > 1:
        a = _downscale(a, f)
    if img.is_float:
        # Float buffers hold linear values — a rough sRGB encode so EXR/HDR
        # thumbnails don't come out dark. Byte images are already display
        # values and go to the screen as-is.
        a[..., :3] = np.clip(a[..., :3], 0.0, 1.0) ** (1 / 2.2)
    return np.ascontiguousarray(np.clip(a, 0.0, 1.0), dtype=np.float32)


def redraw_sidebars():
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == 'VIEW_3D':
                for r in area.regions:
                    if r.type == 'UI':
                        r.tag_redraw()


def _tick():
    start = time.perf_counter()
    built = False
    while _queue and time.perf_counter() - start < _BUDGET:
        name = _queue.pop(0)
        img = bpy.data.images.get(name)
        if img is None:
            continue
        try:
            px = _build(img)
        except Exception:
            px = None
        if px is None:
            _failed[name] = time.time()
        else:
            _pixels[name] = px
        built = True
    if built:
        redraw_sidebars()
    return 0.01 if _queue else None


def get_texture(img):
    """(GPUTexture, aspect) of img's thumbnail, None while it's being built
    (see is_failed). Call only from a draw callback — needs a GPU context."""
    if img is None:
        return None
    key = img.name
    entry = _textures.get(key)
    if entry is not None:
        return entry

    px = _pixels.pop(key, None)
    if px is not None:
        h, w = px.shape[:2]
        # GPUTexture only takes FLOAT buffers (Blender 5.2)
        buf = gpu.types.Buffer('FLOAT', px.size, px.ravel())
        tex = gpu.types.GPUTexture((w, h), format='RGBA16F', data=buf)
        _textures[key] = (tex, w / h)
        return _textures[key]

    failed_at = _failed.get(key)
    if failed_at is not None:
        # Try again now and then: the file may have been relinked or the
        # drive mounted since
        if time.time() - failed_at < RETRY:
            return None
        del _failed[key]
    if key not in _queue:
        _queue.append(key)
    # Timers don't survive a file load; make sure one is running whenever
    # something is queued
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=0.0)
    return None


def get_aspect(img):
    """Aspect (w / h) of an already built thumbnail, None if not built yet."""
    entry = _textures.get(img.name) if img is not None else None
    return entry[1] if entry else None


def is_failed(img):
    """True while img's last thumbnail build failed (missing file...)."""
    return img is not None and img.name in _failed


def invalidate():
    """Drop all cached thumbnails (e.g. after re-import — same image
    names may now hold different pictures)."""
    _textures.clear()
    _pixels.clear()
    _failed.clear()
    _queue.clear()


def register():
    pass


def unregister():
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    invalidate()
