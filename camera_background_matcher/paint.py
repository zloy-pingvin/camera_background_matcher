import math

import blf
import bpy
import gpu
from gpu_extras.batch import batch_for_shader

# Drawing primitives and the look of the hand-drawn CamTools tab (ui.py).
# Every colour, radius and size lives in STYLE; ui.py reads them through S
# (STYLE + the theme's accent and text colours, refreshed by use()).
#
# Shapes go through an SDF shader: one oversized triangle per shape, the
# rounded box cut out of a distance field in the fragment shader. That
# gives anti-aliased edges and clean translucency — a triangle-fan rounded
# rect shows faint seams along its inner edges once it's translucent.

STYLE = {
    "text_dim": (0.60, 0.60, 0.60, 1.0),
    "text_off": (0.40, 0.40, 0.40, 1.0),
    "on_accent": (1.0, 1.0, 1.0, 1.0),        # text on an accent fill
    "bg": (0.10, 0.10, 0.13, 0.55),           # see-through card behind the tab
    "bg_border": (1.0, 1.0, 1.0, 0.14),
    "control": (0.20, 0.20, 0.20, 0.667),     # buttons / fields, 2/3 opaque
    "control_hover": (0.27, 0.27, 0.27, 0.75),
    "control_off": (0.16, 0.16, 0.16, 0.45),  # disabled button
    "border": (0.36, 0.36, 0.36, 1.0),
    "card": (1.0, 1.0, 1.0, 0.06),            # camera card, see-through
    "card_hover": (1.0, 1.0, 1.0, 0.12),
    "empty_img": (0.0, 0.0, 0.0, 0.35),
    "tip_bg": (0.06, 0.06, 0.06, 1.0),
    "tip_edge": (0.30, 0.30, 0.30, 1.0),
    "r_bg": 10.0, "r_ctl": 4.0, "r_card": 10.0, "r_img": 7.0, "r_chip": 4.0,
    "row": 26.0, "gap": 6.0, "font": 12.0, "title": 13.0, "section": 10.0,
}

# Opaque colour under the controls, for tint() blends (the card is see-through)
BASE = (0.10, 0.10, 0.11, 1.0)

S = dict(STYLE)


def use():
    """Refresh S: STYLE plus the theme's selection (accent) and text colours."""
    global S
    ui = bpy.context.preferences.themes[0].user_interface
    S = {**STYLE,
         "accent": (*ui.wcol_tool.inner_sel[:3], 1.0),
         "text": (*ui.wcol_regular.text[:3], 1.0)}
    return S


def begin():
    gpu.state.blend_set('ALPHA')


def end():
    gpu.state.blend_set('NONE')


def tint(alpha, base=BASE):
    """Accent blended over an opaque base colour, as an opaque colour."""
    a = S["accent"]
    return (base[0] + (a[0] - base[0]) * alpha,
            base[1] + (a[1] - base[1]) * alpha,
            base[2] + (a[2] - base[2]) * alpha, 1.0)


def lighten(c, k=0.15):
    return (c[0] + (1 - c[0]) * k, c[1] + (1 - c[1]) * k, c[2] + (1 - c[2]) * k, c[3])


# ---------------------------------------------------------------------------
# SDF shaders
# ---------------------------------------------------------------------------

_SDF_LIB = """
float sd_round_box(vec2 q, vec2 half_size, float r)
{
  vec2 d = abs(q) - half_size + vec2(r);
  return length(max(d, vec2(0.0))) + min(max(d.x, d.y), 0.0) - r;
}

/* Like Blender's builtin shaders: colours are display (sRGB) values,
 * converted when the target framebuffer expects linear. srgbTarget is a
 * builtin uniform Blender sets by itself on bind. */
vec4 to_framebuffer(vec4 c)
{
  if (srgbTarget) {
    vec3 v = max(c.rgb, vec3(0.0));
    c.rgb = mix(v * (1.0 / 12.92), pow((v + 0.055) * (1.0 / 1.055), vec3(2.4)),
                step(vec3(0.04045), v));
  }
  return c;
}
"""

_VERT = ("void main() { p = pos; "
         "gl_Position = ModelViewProjectionMatrix * vec4(pos, 0.0, 1.0); }")

_SHAPE_FRAG = _SDF_LIB + """
void main()
{
  vec2 hs = rect.zw * 0.5;
  float r = min(params.x, min(hs.x, hs.y));
  float d = sd_round_box(p - rect.xy - hs, hs, r);
  float a;
  if (params.y > 0.0) {             /* border of width params.y */
    a = clamp(0.5 - d, 0.0, 1.0) * clamp(d + params.y + 0.5, 0.0, 1.0);
  }
  else {
    a = clamp(0.5 - d, 0.0, 1.0);
  }
  if (params.w > 0.0) {             /* fade out upwards over params.w px */
    a *= clamp(1.0 - (p.y - rect.y) / params.w, 0.0, 1.0);
  }
  FragColor = to_framebuffer(vec4(color.rgb, color.a * a));
}
"""

_IMAGE_FRAG = _SDF_LIB + """
void main()
{
  vec2 hs = rect.zw * 0.5;
  float r = min(params.x, min(hs.x, hs.y));
  float d = sd_round_box(p - rect.xy - hs, hs, r);
  vec2 t = clamp((p - rect.xy) / rect.zw, 0.0, 1.0);
  vec4 c = texture(image, mix(uv.xy, uv.zw, t));
  FragColor = to_framebuffer(vec4(c.rgb, c.a * clamp(0.5 - d, 0.0, 1.0)));
}
"""

# Segment from rect.xy to rect.zw, half-width params.x, round caps
_SEGMENT_FRAG = _SDF_LIB + """
void main()
{
  vec2 pa = p - rect.xy;
  vec2 ba = rect.zw - rect.xy;
  float h = clamp(dot(pa, ba) / max(dot(ba, ba), 1e-6), 0.0, 1.0);
  float d = length(pa - ba * h) - params.x;
  FragColor = to_framebuffer(vec4(color.rgb, color.a * clamp(0.5 - d, 0.0, 1.0)));
}
"""

_FRAGS = {'shape': _SHAPE_FRAG, 'image': _IMAGE_FRAG, 'segment': _SEGMENT_FRAG}

_shaders = {}


def _sdf_shader(kind):
    sh = _shaders.get(kind)
    if sh is not None:
        return sh
    iface = gpu.types.GPUStageInterfaceInfo(f"cam_{kind}_iface")
    iface.smooth('VEC2', "p")
    info = gpu.types.GPUShaderCreateInfo()
    info.push_constant('MAT4', "ModelViewProjectionMatrix")
    info.push_constant('VEC4', "rect")
    info.push_constant('VEC4', "params")
    if kind == 'image':
        info.push_constant('VEC4', "uv")
        info.sampler(0, 'FLOAT_2D', "image")
    else:
        info.push_constant('VEC4', "color")
    # Builtin uniform: Blender sets it on bind (linear vs sRGB framebuffer)
    info.push_constant('BOOL', "srgbTarget")
    info.vertex_in(0, 'VEC2', "pos")
    info.vertex_out(iface)
    info.fragment_out(0, 'VEC4', "FragColor")
    info.vertex_source(_VERT)
    info.fragment_source(_FRAGS[kind])
    sh = gpu.shader.create_from_info(info)
    _shaders[kind] = sh
    return sh


def _cover(x, y, w, h, m=2.0):
    """One triangle covering the rect grown by m — no inner edges, so no
    seams even for translucent colours."""
    x0, y0, ww, hh = x - m, y - m, w + 2 * m, h + 2 * m
    return ((x0, y0), (x0 + 2 * ww, y0), (x0, y0 + 2 * hh))


def _sdf(x, y, w, h, color, r=0.0, border=0.0, fade=0.0):
    if w <= 0 or h <= 0 or color[3] <= 0:
        return
    sh = _sdf_shader('shape')
    sh.bind()
    sh.uniform_float("rect", (x, y, w, h))
    sh.uniform_float("color", color)
    sh.uniform_float("params", (r, border, 0.0, fade))
    batch_for_shader(sh, 'TRIS', {"pos": _cover(x, y, w, h)}).draw(sh)


def release():
    """Drop the shaders (addon unregister)."""
    _shaders.clear()


# ---------------------------------------------------------------------------
# Shapes
# ---------------------------------------------------------------------------

def rect(x, y, w, h, r, color):
    """Filled rounded rectangle; (x, y) is the bottom-left corner."""
    _sdf(x, y, w, h, color, r)


def frame(x, y, w, h, r, t, color):
    """Rounded-rect border of thickness t, inside left untouched."""
    _sdf(x, y, w, h, color, r, border=t)


def fade_rect(x, y, w, h, r, color, fade_h):
    """Rounded rect fading out upwards over fade_h px (name backdrop)."""
    _sdf(x, y, w, h, color, r, fade=fade_h)


def image(tex, aspect, x, y, w, h, r):
    """Texture cover-fitted into the rect (centre-cropped, never
    letterboxed), with rounded corners."""
    u0, u1, v0, v1 = 0.0, 1.0, 0.0, 1.0
    cell = w / h
    if aspect > cell:
        span = cell / aspect
        u0, u1 = 0.5 - span * 0.5, 0.5 + span * 0.5
    else:
        span = aspect / cell
        v0, v1 = 0.5 - span * 0.5, 0.5 + span * 0.5
    sh = _sdf_shader('image')
    sh.bind()
    sh.uniform_float("rect", (x, y, w, h))
    sh.uniform_float("uv", (u0, v0, u1, v1))
    sh.uniform_float("params", (r, 0.0, 0.0, 0.0))
    sh.uniform_sampler("image", tex)
    batch_for_shader(sh, 'TRIS', {"pos": _cover(x, y, w, h)}).draw(sh)


def line(x0, y0, x1, y1, t, color):
    """Anti-aliased segment of thickness t with round caps."""
    sh = _sdf_shader('segment')
    sh.bind()
    sh.uniform_float("rect", (x0, y0, x1, y1))
    sh.uniform_float("color", color)
    sh.uniform_float("params", (t * 0.5, 0.0, 0.0, 0.0))
    bx, by = min(x0, x1) - t * 0.5, min(y0, y1) - t * 0.5
    pos = _cover(bx, by, abs(x1 - x0) + t, abs(y1 - y0) + t)
    batch_for_shader(sh, 'TRIS', {"pos": pos}).draw(sh)


def tick(x, y, size, color):
    """Check mark inside the size × size box at (x, y). The round caps
    close the joint; an opaque colour keeps the overlap from showing."""
    t = max(1.5, size * 0.14)
    bx, by = x + size * 0.42, y + size * 0.30
    line(x + size * 0.25, y + size * 0.52, bx, by, t, color)
    line(bx, by, x + size * 0.76, y + size * 0.70, t, color)


def magnifier(cx, cy, size, color):
    """Search glyph: a ring and a handle, centred on (cx, cy). Opaque, so
    plain triangles are fine here."""
    r_out = size * 0.32
    r_in = r_out - max(1.2, size * 0.1)
    ox, oy = cx - size * 0.08, cy + size * 0.08
    tris = []
    steps = 20
    for i in range(steps):
        a0 = 2 * math.pi * i / steps
        a1 = 2 * math.pi * (i + 1) / steps
        p0o = (ox + math.cos(a0) * r_out, oy + math.sin(a0) * r_out)
        p1o = (ox + math.cos(a1) * r_out, oy + math.sin(a1) * r_out)
        p0i = (ox + math.cos(a0) * r_in, oy + math.sin(a0) * r_in)
        p1i = (ox + math.cos(a1) * r_in, oy + math.sin(a1) * r_in)
        tris.extend((p0o, p1o, p0i, p0i, p1o, p1i))
    d = math.sqrt(0.5)
    t = max(1.4, size * 0.12) * 0.5
    ax, ay = ox + d * r_out, oy - d * r_out
    bx, by = cx + size * 0.42, cy - size * 0.42
    nx, ny = d * t, d * t
    tris.extend(((ax - nx, ay - ny), (bx - nx, by - ny), (ax + nx, ay + ny),
                 (ax + nx, ay + ny), (bx - nx, by - ny), (bx + nx, by + ny)))
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    shader.bind()
    shader.uniform_float("color", color)
    batch_for_shader(shader, 'TRIS', {"pos": tris}).draw(shader)


# ---------------------------------------------------------------------------
# Text (blf, the default UI font)
# ---------------------------------------------------------------------------

def width(s, size):
    blf.size(0, size)
    return blf.dimensions(0, s)[0]


def text(s, x, y, size, color, bold=False):
    """Draw s with its baseline at y."""
    blf.size(0, size)
    blf.color(0, *color)
    blf.position(0, x, y, 0)
    blf.draw(0, s)
    if bold:
        # blf has one weight; the same glyphs half a pixel right read as bold
        blf.position(0, x + 0.6, y, 0)
        blf.draw(0, s)
    # blf.draw leaves blending off: every translucent shape drawn after it
    # would come out opaque (whole cover triangles, solid × backdrops)
    gpu.state.blend_set('ALPHA')


def text_in(s, x, y, w, h, size, color, align='LEFT', bold=False):
    """Text vertically centred in a rect, aligned LEFT / CENTER / RIGHT."""
    tw = width(s, size)
    if align == 'CENTER':
        x = x + (w - tw) * 0.5
    elif align == 'RIGHT':
        x = x + w - tw
    text(s, x, y + (h - size * 0.72) * 0.5, size, color, bold)
    return tw


def fit(s, max_w, size):
    """s cut with an ellipsis to fit max_w."""
    if width(s, size) <= max_w:
        return s
    while s and width(s + "…", size) > max_w:
        s = s[:-1]
    return s + "…"


def wrap(s, max_w, size):
    """Lines of s word-wrapped to max_w (keeps explicit newlines)."""
    lines = []
    for para in s.split("\n"):
        line = ""
        for word in para.split(" "):
            probe = word if not line else line + " " + word
            if line and width(probe, size) > max_w:
                lines.append(line)
                line = word
            else:
                line = probe
        lines.append(line)
    return lines
