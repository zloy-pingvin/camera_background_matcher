import time

import bpy

from . import bl_info
from . import notes
from . import paint
from . import previews
from .keymaps import get_hotkey_label

# The CamTools tab is drawn by hand (gpu/blf, see paint.py) instead of with
# Blender's layout: our own look, preview cards clickable as a whole,
# photos in their own aspect ratio.
#
# How the pieces fit:
#   * CAM_PT_panel — empty HIDE_HEADER panel in the CamTools tab. Draws
#     nothing; reserves the content height so the sidebar scrolls natively.
#   * _build — lays out every widget as a dict (kind, rect, act, ...) in
#     region pixels. Shared by the panel (height), the draw handler (paint)
#     and the input operators (hit-test against the last draw's widgets).
#   * _draw — POST_PIXEL handler on the sidebar ('UI') region itself, not
#     the viewport under it: works with Region Overlap on or off, and a
#     repaint is a sidebar redraw, not a scene redraw.
#   * CAM_OT_ui_hover / CAM_OT_ui_click — keymap items (MOUSEMOVE,
#     LEFTMOUSE). Click turns modal only while a slider is dragged or a
#     field is typed into — no always-running modal operator.

TAB = "CamTools"
# Shown at the right end of the title. Read at import time only: on an
# extension install Blender deletes bl_info once __init__'s body has run
VERSION = "v" + ".".join(map(str, bl_info["version"]))

# Geometry in unscaled pixels, × ui_scale at use. Row height, gaps, radii
# and font sizes are in paint.STYLE.
MARGIN = 6.0        # region edge → background card
TAB_GAP = 2.0       # background card → category tabs
# Blender still paints its own panel outline under the empty panel, a few
# px wider and ~20 px taller than our content; the card is stretched over it
COVER_BOTTOM = 24.0
PAD = 10.0          # background card edge → widgets
TITLE_H = 22.0
SECTION_H = 16.0
SLIDER_H = 36.0     # label + value line, then the track underneath
NAME_ROW = 20.0     # camera name row, laid over the bottom of the picture
NAME_FADE = 30.0    # dark fade behind the name
CARD_PAD = 4.0
HINT_H = 18.0
NOTE_H = 20.0       # one-line message under the title (notes.py)
CHIP_W = 22.0
ODD_W = 30.0        # "−½" (remove every other) button
X_SIZE = 16.0       # card × button, at the end of the name row
CHECK_H = 20.0      # checkbox row
CHECK_BOX = 14.0
CHECK_INDENT = 20.0 # a dependent checkbox sits under its parent's label
TAB_STRIP = 26.0    # category tabs live inside the region's width
DEFAULT_ASPECT = 16 / 9
TIP_DELAY = 0.6

X_BG_HOVER = (0.85, 0.25, 0.25, 0.95)
WHITE = (1.0, 1.0, 1.0, 1.0)
NOTE_COLORS = {'INFO': None,                       # accent
               'WARNING': (0.95, 0.70, 0.20, 1.0),
               'ERROR': (0.95, 0.35, 0.35, 1.0)}

# region pointer → widgets of that region's last draw (hit-test source)
_cells = {}
# (region pointer, act) under the mouse or None, and since when
_hover = None
_hover_t = 0.0
# act whose tooltip stays hidden after a click, until the mouse leaves it
_tip_block = None
# field being typed into: {"region", "act", "text", "fresh"}, or None
_edit = None
# act of the slider / number being dragged, or None
_drag = None
_draw_handle = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _displayed(s):
    """(mc_index, item) pairs as shown: search filter + optional name sort."""
    search = s.search_filter.lower()
    items = [(i, it) for i, it in enumerate(s.mc_items)
             if it.camera and (not search or search in it.camera.name.lower())]
    if s.sort_by_name:
        items.sort(key=lambda x: x[1].camera.name)
    return items


def _grid_aspect(images):
    """One aspect for every cell — the first built thumbnail's — so rows
    line up; each photo is cover-fitted into it."""
    return next((a for a in map(previews.get_aspect, images) if a), DEFAULT_ASPECT)


def _op(idname):
    mod, name = idname.split(".")
    return getattr(getattr(bpy.ops, mod), name)


def _op_tip(idname):
    desc = _op(idname).get_rna_type().description
    return bpy.app.translations.pgettext_tip(desc) if desc else None


def _prop_tip(owner, prop):
    desc = owner.bl_rna.properties[prop].description
    return bpy.app.translations.pgettext_tip(desc) if desc else None


def _call(idname, **kw):
    # Second positional arg asks for an undo step, as a native button would
    try:
        return _op(idname)('INVOKE_DEFAULT', True, **kw)
    except RuntimeError as exc:
        # An {'ERROR'} report inside a nested bpy.ops call raises instead
        # of reaching the status bar
        msg = str(exc).strip().splitlines()[-1]
        notes.show(msg.partition(": ")[2] or msg, 'ERROR')
        return {'CANCELLED'}


def _undo(message):
    bpy.ops.ed.undo_push(message=message)


def _fmt(v):
    return f"{v:.3f}" if abs(v) < 1 else f"{v:.2f}"


def _visible(region):
    return (region is not None and region.type == 'UI'
            # dragged shut, the sidebar still reports its tab but is ~26 px
            and region.width >= 60
            and getattr(region, "active_panel_category", "") == TAB)


def _hit(region, mx, my):
    """Topmost enabled widget with an action under (mx, my), or None.
    Later widgets are painted on top, so they're tested first."""
    for w in reversed(_cells.get(region.as_pointer(), ())):
        if w.get("act") is None or not w.get("enabled", True):
            continue
        x, y, ww, hh = w["rect"]
        if x <= mx <= x + ww and y <= my <= y + hh:
            return w
    return None


def _redraw():
    previews.redraw_sidebars()


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

class _Layout:
    """Top-down cursor over a column: row(h) gives the bottom of the next
    row of height h (unscaled) and moves below it."""

    def __init__(self, y, sc, left, inner):
        self.y, self.sc, self.left, self.inner = y, sc, left, inner
        self.widgets = []

    def row(self, h, after):
        bottom = self.y - h * self.sc
        self.y = bottom - after * self.sc
        return bottom

    def add(self, kind, rect, **kw):
        kw["kind"] = kind
        kw["rect"] = rect
        self.widgets.append(kw)
        return kw

    def bottom(self):
        return min(w["rect"][1] for w in self.widgets if w.get("rect"))


def _build(context, region):
    """Every widget of the tab in region pixels, laid out top-down.
    Returns (widgets, content height). A widget is a dict: kind, rect
    (x, y, w, h — y is the bottom edge), optional act (hit-test key and
    what a click does), tip, enabled, plus per-kind fields."""
    S = paint.use()
    s = context.scene.cam_tools_settings
    sc = context.preferences.system.ui_scale
    row, gap = S["row"], S["gap"]

    # View y = 0 is the top of the panel list; view_to_region adds the scroll
    top = region.view2d.view_to_region(0, 0, clip=False)[1]
    # The category tabs sit on the region's outer edge: right normally,
    # left when the sidebar is flipped to the viewport's left side
    strip = (TAB_STRIP + TAB_GAP) * sc
    bg_x = strip if region.alignment == 'LEFT' else MARGIN * sc
    bg_w = region.width - strip - MARGIN * sc
    L = _Layout(top - (MARGIN + PAD) * sc, sc, bg_x + PAD * sc,
                max(bg_w - 2 * PAD * sc, 1.0))
    left, inner = L.left, L.inner
    bg = L.add('bg', None)

    def section(label, right=None):
        b = L.row(SECTION_H, 2)
        L.add('section', (left, b, inner, SECTION_H * sc), text=label, right=right)

    def button(rect, label, idname, **kw):
        L.add('button', rect, text=label, act=('op', idname), tip=_op_tip(idname),
              enabled=_op(idname).poll(), **kw)

    def check(prop, indent=0.0, after=2):
        b = L.row(CHECK_H, after)
        x = left + indent * sc
        L.add('check', (x, b, left + inner - x, CHECK_H * sc),
              text=s.bl_rna.properties[prop].name, on=getattr(s, prop),
              act=('toggle', prop), tip=_prop_tip(s, prop))

    b = L.row(TITLE_H, 4)
    L.add('title', (left, b, inner, TITLE_H * sc), text="Camera Tools", right=VERSION)
    note = notes.current()
    if note is not None:
        b = L.row(NOTE_H, 4)
        L.add('note', (left, b, inner, NOTE_H * sc), text=note[0], level=note[1])

    # --- Backgrounds
    section("BACKGROUNDS")
    b = L.row(row, gap)
    L.add('number', (left, b, inner, row * sc), text="Clip Start",
          prop='clip_start_value', act=('number', 'clip_start_value'),
          tip=_prop_tip(s, 'clip_start_value'))
    b = L.row(SLIDER_H, gap)
    p = s.bl_rna.properties['opacity_value']
    L.add('slider', (left, b, inner, SLIDER_H * sc), text="Opacity",
          prop='opacity_value', lo=p.hard_min, hi=p.hard_max,
          act=('slider', 'opacity_value'), tip=_prop_tip(s, 'opacity_value'))
    b = L.row(row + 4, 12)
    button((left, b, inner, (row + 4) * sc), "Import from Folder",
           "cam.setup_backgrounds", primary=True)

    # --- Cameras
    items = _displayed(s)
    count = (f"{len(items)} / {len(s.mc_items)}" if s.search_filter
             else str(len(s.mc_items)))
    section("CAMERAS", count)
    b = L.row(row, gap)
    odd_w = ODD_W * sc
    half = (inner - 2 * gap * sc - odd_w) * 0.5
    button((left, b, half, row * sc), "Add Selected", "cam.add_camera")
    button((left + half + gap * sc, b, odd_w, row * sc), "−½", "cam.remove_every_other")
    button((left + half + 2 * gap * sc + odd_w, b, half, row * sc), "Clear All",
           "cam.clear_all")

    b = L.row(row, gap)
    L.add('search', (left, b, inner, row * sc), act=('search',),
          tip=_prop_tip(s, 'search_filter'))
    if s.search_filter:
        L.add('clear', (left + inner - row * sc, b, row * sc, row * sc),
              act=('clear_search',), tip=_op_tip('cam.clear_search'))

    h = (row - 4) * sc
    b = L.row(row - 4, 10)
    chip_w, chip_gap = CHIP_W * sc, 2 * sc
    chips_x = left + inner - 3 * chip_w - 2 * chip_gap
    sort_w = chips_x - gap * sc - left
    L.add('button', (left, b, sort_w, h),
          text="By Name" if s.sort_by_name else "By Added Order",
          act=('sort',), on=s.sort_by_name, tip=_prop_tip(s, 'sort_by_name'))
    cols = int(s.ui_columns)
    for n in (1, 2, 3):
        L.add('chip', (chips_x + (n - 1) * (chip_w + chip_gap), b, chip_w, h),
              text=str(n), on=n == cols, act=('cols', n),
              tip=_prop_tip(s, 'ui_columns'))

    if items:
        # Cards: the picture fills the card (minus a thin frame), the name
        # and the × sit on its bottom edge over a dark fade
        camera = context.scene.camera
        aspect = _grid_aspect([it.image for _, it in items])
        card_w = max((inner - gap * sc * (cols - 1)) / cols, 1.0)
        img_h = (card_w - 2 * CARD_PAD * sc) / aspect
        card_h = img_h + 2 * CARD_PAD * sc
        side = X_SIZE * sc
        x_tip = _op_tip('cam.remove_fav')
        grid_top = L.y
        for n, (index, it) in enumerate(items):
            r, c = divmod(n, cols)
            x = left + c * (card_w + gap * sc)
            cb = grid_top - r * (card_h + gap * sc) - card_h
            ix, iy, iw = x + CARD_PAD * sc, cb + CARD_PAD * sc, card_w - 2 * CARD_PAD * sc
            L.add('card', (x, cb, card_w, card_h), act=('card', index),
                  x_act=('remove', index), name=it.camera.name, image=it.image,
                  active=it.camera == camera, img_rect=(ix, iy, iw, img_h))
            L.add('card_x', (ix + iw - 4 * sc - side,
                             iy + 2 * sc + (NAME_ROW * sc - side) * 0.5, side, side),
                  act=('remove', index), card_act=('card', index), tip=x_tip)
        rows = -(-len(items) // cols)
        L.y = grid_top - rows * (card_h + gap * sc) - 6 * sc
    else:
        if s.search_filter:
            lines = ("No cameras found", f'Query: "{s.search_filter}"')
        else:
            lines = ("Camera list is empty", "Import from Folder or Add Selected")
        b = L.row(18, 0)
        L.add('text', (left, b, inner, 18 * sc), text=lines[0], size=12)
        b = L.row(16, 12)
        L.add('text', (left, b, inner, 16 * sc), text=lines[1], size=11, dim=True)

    # --- Scene
    section("SCENE")
    check('pin_selection', after=2 if s.pin_selection else 6)
    if s.pin_selection:
        check('pin_scale', indent=CHECK_INDENT, after=6)
    hidden = s.cameras_display_hidden
    b = L.row(row, gap)
    button((left, b, inner, row * sc),
           "Show Camera Icons" if hidden else "Hide Camera Icons",
           "cam.toggle_camera_display", on=hidden)
    b = L.row(row, 10)
    button((left, b, inner, row * sc), "Select Cameras in Scene", "cam.select_in_outliner")

    enabled, label_next, label_prev = get_hotkey_label(__package__)
    if enabled and (label_next or label_prev):
        for label, keys in (("Next camera", label_next),
                            ("Previous camera", label_prev)):
            b = L.row(HINT_H, 0)
            L.add('pair', (left, b, inner, HINT_H * sc), text=label, right=keys)
    else:
        b = L.row(HINT_H, 0)
        L.add('pair', (left, b, inner, HINT_H * sc), text="Hotkey disabled",
              right="Enable", act=('prefs',), link=True)

    bg_top = top - MARGIN * sc
    bg_bottom = L.bottom() - PAD * sc
    cover = COVER_BOTTOM * sc
    bg["rect"] = (bg_x, bg_bottom - cover, bg_w, bg_top - bg_bottom + cover)
    return L.widgets, top - bg_bottom + MARGIN * sc


# ---------------------------------------------------------------------------
# Painting (colours and sizes from paint.S)
# ---------------------------------------------------------------------------

def _control(x, y, w, h, r, sc, hot=False, enabled=True):
    """Background of a button / field: a 2/3-opaque fill with a border."""
    S = paint.S
    fill = S["control_hover"] if hot else (S["control"] if enabled else S["control_off"])
    paint.rect(x, y, w, h, r, fill)
    paint.frame(x, y, w, h, r, max(1.0, sc), S["border"])


def _toggled(x, y, w, h, r, sc, hot):
    """An 'on' toggle / chip: accent-tinted fill with an accent border."""
    paint.rect(x, y, w, h, r, paint.tint(0.5 if hot else 0.32))
    paint.frame(x, y, w, h, r, max(1.0, sc), paint.S["accent"])


def _paint_edit(e, x, y, w, h, sc, size):
    """Text being typed + caret; shows the tail when it doesn't fit. A
    fresh field (the first key replaces it) gets a selection highlight."""
    S = paint.S
    shown = e["text"]
    while shown and paint.width(shown, size) > w - 4 * sc:
        shown = shown[1:]
    tw = paint.width(shown, size)
    tx = x + w - tw - 3 * sc if e["act"][0] == 'number' else x
    if e["fresh"] and shown:
        paint.rect(tx - 2 * sc, y + 5 * sc, tw + 4 * sc, h - 10 * sc, 2 * sc,
                   paint.tint(0.45))
    paint.text_in(shown, tx, y, tw + 1, h, size, S["text"])
    paint.rect(tx + tw + 1 * sc, y + 6 * sc, max(1.0, sc), h - 12 * sc, 0, S["text"])


def _paint(w, ctx):
    S = paint.S
    k = w["kind"]
    x, y, ww, hh = w["rect"]
    act = w.get("act")
    enabled = w.get("enabled", True)
    hov = act is not None and enabled and act == ctx["hover"]
    editing = ctx["edit"] is not None and act == ctx["edit"]["act"]
    sc, s = ctx["sc"], ctx["s"]
    size = S["font"] * sc
    r_ctl = S["r_ctl"] * sc
    acc, txt = S["accent"], S["text"]

    if k == 'bg':
        paint.rect(x, y, ww, hh, S["r_bg"] * sc, S["bg"])
        paint.frame(x, y, ww, hh, S["r_bg"] * sc, max(1.0, sc), S["bg_border"])

    elif k == 'title':
        paint.text_in(w["text"], x, y, ww, hh, S["title"] * sc, txt, bold=True)
        paint.text_in(w["right"], x, y, ww, hh, 11 * sc, S["text_dim"], align='RIGHT')

    elif k == 'section':
        paint.text_in(w["text"], x, y, ww, hh, S["section"] * sc, S["text_dim"])
        if w.get("right"):
            paint.text_in(w["right"], x, y, ww, hh, S["section"] * sc, S["text_dim"],
                          align='RIGHT')

    elif k == 'button':
        col = txt
        if not enabled:
            _control(x, y, ww, hh, r_ctl, sc, enabled=False)
            col = S["text_off"]
        elif w.get("primary"):
            # Same fill as the other buttons, outlined in the accent
            paint.rect(x, y, ww, hh, r_ctl,
                       paint.tint(0.18) if hov else S["control"])
            paint.frame(x, y, ww, hh, r_ctl, 1.5 * sc, acc)
            col = acc
        elif w.get("on"):
            _toggled(x, y, ww, hh, r_ctl, sc, hov)
        else:
            _control(x, y, ww, hh, r_ctl, sc, hot=hov)
        paint.text_in(paint.fit(w["text"], ww - 8 * sc, size), x, y, ww, hh, size, col,
                      align='CENTER')

    elif k == 'number':
        _control(x, y, ww, hh, r_ctl, sc, hot=hov or editing)
        pad = 8 * sc
        paint.text_in(w["text"], x + pad, y, ww - 2 * pad, hh, size, S["text_dim"])
        if editing:
            _paint_edit(ctx["edit"], x + pad, y, ww - 2 * pad, hh, sc, size)
            paint.frame(x, y, ww, hh, r_ctl, max(1.0, sc), acc)
        else:
            paint.text_in(_fmt(getattr(s, w["prop"])), x + pad, y, ww - 2 * pad, hh,
                          size, txt, align='RIGHT')

    elif k == 'slider':
        # Label + value on top, a thin track with a knob underneath
        v = getattr(s, w["prop"])
        frac = min(max((v - w["lo"]) / max(w["hi"] - w["lo"], 1e-9), 0.0), 1.0)
        hot = hov or act == _drag
        ty = y + 7 * sc
        paint.rect(x, ty - 1.5 * sc, ww, 3 * sc, 1.5 * sc, S["control_hover"])
        paint.rect(x, ty - 1.5 * sc, ww * frac, 3 * sc, 1.5 * sc, acc)
        kr = (7 if hot else 6) * sc
        kx = min(max(x + ww * frac, x + kr), x + ww - kr)
        paint.rect(kx - kr, ty - kr, 2 * kr, 2 * kr, kr, acc)
        ly, lh = y + 14 * sc, hh - 14 * sc
        paint.text_in(w["text"], x, ly, ww, lh, size, txt)
        paint.text_in(_fmt(v), x, ly, ww, lh, size, txt, align='RIGHT')

    elif k == 'search':
        _control(x, y, ww, hh, r_ctl, sc, hot=hov or editing)
        paint.magnifier(x + hh * 0.5, y + hh * 0.5, 12 * sc, S["text_dim"])
        text = s.search_filter
        tx = x + hh
        tw = ww - hh - (hh if text else 6 * sc)
        if editing:
            _paint_edit(ctx["edit"], tx, y, tw, hh, sc, size)
            paint.frame(x, y, ww, hh, r_ctl, max(1.0, sc), acc)
        elif text:
            paint.text_in(paint.fit(text, tw, size), tx, y, tw, hh, size, txt)
        else:
            paint.text_in("Search", tx, y, tw, hh, size, S["text_dim"])

    elif k == 'clear':
        paint.text_in("×", x, y, ww, hh, 15 * sc, txt if hov else S["text_dim"],
                      align='CENTER')

    elif k == 'chip':
        r = S["r_chip"] * sc
        if w["on"]:
            _toggled(x, y, ww, hh, r, sc, hov)
            col = acc
        else:
            _control(x, y, ww, hh, r, sc, hot=hov)
            col = txt if hov else S["text_dim"]
        paint.text_in(w["text"], x, y, ww, hh, size - 1 * sc, col, align='CENTER')

    elif k == 'check':
        # Box + label; the whole row is the click target
        bs = CHECK_BOX * sc
        by = y + (hh - bs) * 0.5
        r = 3 * sc
        if w["on"]:
            paint.rect(x, by, bs, bs, r, paint.lighten(acc, 0.15) if hov else acc)
            paint.tick(x, by, bs, S["on_accent"])
        else:
            _control(x, by, bs, bs, r, sc, hot=hov)
        tx = x + bs + 6 * sc
        paint.text_in(paint.fit(w["text"], x + ww - tx, size), tx, y, x + ww - tx, hh,
                      size, txt)

    elif k == 'card':
        _paint_card(w, ctx, x, y, ww, hh)

    elif k == 'card_x':
        if ctx["hover"] in (w["card_act"], act):
            if hov:
                paint.rect(x, y, ww, hh, 4 * sc, X_BG_HOVER)
            paint.text_in("×", x, y, ww, hh, 13 * sc, WHITE, align='CENTER')

    elif k == 'note':
        col = NOTE_COLORS.get(w["level"]) or acc
        paint.rect(x, y, ww, hh, r_ctl, S["control"])
        paint.text_in(paint.fit(w["text"], ww - 12 * sc, 11 * sc), x + 6 * sc, y, ww, hh,
                      11 * sc, col)

    elif k == 'text':
        tsize = w.get("size", 12) * sc
        paint.text_in(paint.fit(w["text"], ww, tsize), x, y, ww, hh, tsize,
                      S["text_dim"] if w.get("dim") else txt)

    elif k == 'pair':
        paint.text_in(w["text"], x, y, ww, hh, 11 * sc, S["text_dim"])
        col = (paint.lighten(acc, 0.3) if hov else acc) if w.get("link") else txt
        paint.text_in(w["right"], x, y, ww, hh, 11 * sc, col, align='RIGHT')


def _paint_card(w, ctx, x, y, ww, hh):
    S = paint.S
    sc = ctx["sc"]
    hovered = ctx["hover"] in (w["act"], w["x_act"])
    active = w["active"]
    r = S["r_card"] * sc
    acc = S["accent"]

    if active:
        # Accent plate 1 px larger than the see-through card: it fills
        # everything around the picture
        ring = 1 * sc
        paint.rect(x - ring, y - ring, ww + 2 * ring, hh + 2 * ring, r + ring,
                   paint.lighten(acc, 0.1) if hovered else acc)
    paint.rect(x, y, ww, hh, r, S["card_hover"] if hovered else S["card"])

    ix, iy, iw, ih = w["img_rect"]
    r_img = S["r_img"] * sc
    entry = previews.get_texture(w["image"]) if w["image"] else None
    if entry is not None:
        paint.image(entry[0], entry[1], ix, iy, iw, ih, r_img)
    else:
        paint.rect(ix, iy, iw, ih, r_img, S["empty_img"])
        if w["image"] is None:
            label = "No Image"
        elif previews.is_failed(w["image"]):
            label = "Missing"
        else:
            label = "…"
        paint.text_in(label, ix, iy, iw, ih, 11 * sc, S["text_dim"], align='CENTER')

    # Name over the picture's bottom edge; room left for the × at its end
    size = S["font"] * sc
    paint.fade_rect(ix, iy, iw, ih, r_img, (0.0, 0.0, 0.0, 0.78),
                    min(ih, NAME_FADE * sc))
    nx = ix + 6 * sc
    nw = iw - 12 * sc - (X_SIZE + 4) * sc
    paint.text_in(paint.fit(w["name"], nw, size), nx, iy + 2 * sc, nw, NAME_ROW * sc,
                  size, WHITE, bold=active)


def _paint_tip(widgets, ctx):
    hover = ctx["hover"]
    if (hover is None or _drag is not None or _edit is not None
            or hover == _tip_block or time.time() - _hover_t < TIP_DELAY):
        return
    w = next((w for w in widgets if w.get("act") == hover), None)
    tip = w.get("tip") if w else None
    if not tip:
        return
    S = paint.S
    sc = ctx["sc"]
    txt = (0.95, 0.95, 0.95, 1.0)
    size, pad, line_h = 11 * sc, 7 * sc, 15 * sc
    bg = widgets[0]["rect"]
    lines = paint.wrap(tip, bg[2] - 2 * pad, size)
    bw = min(max(paint.width(l, size) for l in lines) + 2 * pad, bg[2])
    bh = (len(lines) - 1) * line_h + size + 2 * pad
    x, y, ww, hh = w["rect"]
    bx = min(max(x, bg[0]), bg[0] + bg[2] - bw)
    by = y - 4 * sc - bh
    if by < 2 * sc:
        by = y + hh + 4 * sc
    paint.rect(bx, by, bw, bh, 5 * sc, S["tip_bg"])
    paint.frame(bx, by, bw, bh, 5 * sc, max(1.0, sc), S["tip_edge"])
    for i, line in enumerate(lines):
        paint.text(line, bx + pad, by + bh - pad - size * 0.8 - i * line_h, size, txt)


def _draw():
    context = bpy.context
    region = context.region
    if region is None:
        return
    key = region.as_pointer()
    if not _visible(region):
        _cells.pop(key, None)
        return

    # Regions come and go (areas closed, files loaded); an ARegion can be
    # reallocated at an old pointer, so drop entries for regions that no
    # longer exist before the input operators trust them
    live = {r.as_pointer()
            for win in context.window_manager.windows
            for a in win.screen.areas if a.type == 'VIEW_3D'
            for r in a.regions if r.type == 'UI'}
    for k in list(_cells):
        if k not in live:
            _cells.pop(k)

    # The sidebar can be zoomed (Ctrl+MMB / Ctrl+Numpad±); the spacer panel
    # would follow the zoom and our painting wouldn't. Snap it back instead.
    v2d = region.view2d
    zoom = (v2d.view_to_region(0, 0, clip=False)[1]
            - v2d.view_to_region(0, -100, clip=False)[1]) / 100.0
    if abs(zoom - 1.0) > 0.02 and not bpy.app.timers.is_registered(_unzoom):
        bpy.app.timers.register(_unzoom)

    widgets, _ = _build(context, region)
    _cells[key] = widgets
    ctx = {
        "sc": context.preferences.system.ui_scale,
        "s": context.scene.cam_tools_settings,
        "hover": _hover[1] if _hover is not None and _hover[0] == key else None,
        "edit": _edit if _edit is not None and _edit["region"] == key else None,
    }
    paint.begin()
    height = region.height
    for w in widgets:
        # Only what's scrolled into view gets painted — and only visible
        # cards ask previews for a thumbnail, so a long list is decoded
        # lazily as it scrolls
        y, h = w["rect"][1], w["rect"][3]
        if y > height or y + h < 0:
            continue
        _paint(w, ctx)
    _paint_tip(widgets, ctx)
    paint.end()


def _unzoom():
    """Reset the zoom of every sidebar showing our tab."""
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type != 'VIEW_3D':
                continue
            for region in area.regions:
                if region.type == 'UI' and region.active_panel_category == TAB:
                    with bpy.context.temp_override(window=win, area=area, region=region):
                        bpy.ops.view2d.reset()
    return None


@bpy.app.handlers.persistent
def _on_load(*_):
    # Everything keyed by pointers or image names belongs to the old file
    global _hover, _edit, _drag, _tip_block
    _cells.clear()
    _hover = _edit = _drag = _tip_block = None
    notes.clear()
    previews.invalidate()


# ---------------------------------------------------------------------------
# Panel + input operators
# ---------------------------------------------------------------------------

class CAM_PT_panel(bpy.types.Panel):
    bl_label = "Camera Tools"
    bl_idname = "CAM_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = TAB
    bl_options = {'HIDE_HEADER'}

    def draw(self, context):
        # Nothing visible: an empty label as tall as the hand-drawn content,
        # so the region scrolls natively. _draw paints everything over it.
        _, height = _build(context, context.region)
        system = context.preferences.system
        unit = round(18 * system.ui_scale) + 2 * system.pixel_size
        col = self.layout.column()
        col.scale_y = max(height / unit, 1.0)
        col.label(text="")


def _tip_timer():
    """Repaint once the hover has rested TIP_DELAY, so the tooltip shows."""
    if _hover is None:
        return None
    left = TIP_DELAY - (time.time() - _hover_t)
    if left > 0:
        return left + 0.01
    _redraw()
    return None


class CAM_OT_ui_hover(bpy.types.Operator):
    """Track the widget under the mouse in the CamTools tab"""
    bl_idname = "cam.ui_hover"
    bl_label = "CamTools Hover"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        # Runs on every mouse move anywhere — keep it to a dict lookup
        region = context.region
        return _hover is not None or (region is not None
                                      and region.as_pointer() in _cells)

    def invoke(self, context, event):
        global _hover, _hover_t, _tip_block
        region = context.region
        hover = None
        if region is not None and region.as_pointer() in _cells:
            w = _hit(region, event.mouse_x - region.x, event.mouse_y - region.y)
            if w is not None:
                hover = (region.as_pointer(), w["act"])
        if hover != _hover:
            _hover = hover
            _hover_t = time.time()
            if hover is None or hover[1] != _tip_block:
                _tip_block = None
            _redraw()
            if hover is not None and not bpy.app.timers.is_registered(_tip_timer):
                bpy.app.timers.register(_tip_timer, first_interval=TIP_DELAY + 0.01)
        return {'PASS_THROUGH'}


class CAM_OT_ui_click(bpy.types.Operator):
    """Click in the CamTools tab: press a button, drag a slider, type into a field or pick a camera"""
    bl_idname = "cam.ui_click"
    bl_label = "CamTools Click"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        region = context.region
        return region is not None and region.as_pointer() in _cells

    @staticmethod
    def _mouse(context, event):
        region = context.region
        return event.mouse_x - region.x, event.mouse_y - region.y

    def invoke(self, context, event):
        global _tip_block
        w = _hit(context.region, *self._mouse(context, event))
        if w is None:
            return {'PASS_THROUGH'}
        act = w["act"]
        kind = act[0]
        _tip_block = act
        s = context.scene.cam_tools_settings

        if kind in {'slider', 'number', 'search'}:
            return self._start(context, event, w)
        if kind == 'op':
            _call(act[1])
        elif kind == 'card':
            _call('cam.select_preview', index=act[1])
        elif kind == 'remove':
            _call('cam.remove_fav', index=act[1])
        elif kind == 'cols':
            s.ui_columns = str(act[1])
            _undo("Columns")
        elif kind == 'sort':
            s.sort_by_name = not s.sort_by_name
            _undo("Sort by Name")
        elif kind == 'toggle':
            setattr(s, act[1], not getattr(s, act[1]))
            _undo(s.bl_rna.properties[act[1]].name)
        elif kind == 'clear_search':
            _call('cam.clear_search')
        elif kind == 'prefs':
            bpy.ops.screen.userpref_show('INVOKE_DEFAULT')
        _redraw()
        return {'FINISHED'}

    # --- modal: slider drag, number drag-or-type, text typing -------------

    def _start(self, context, event, w):
        global _drag, _edit
        s = context.scene.cam_tools_settings
        self._w = w
        self._mode = w["act"][0]
        if self._mode == 'slider':
            self._old = getattr(s, w["prop"])
            _drag = w["act"]
            self._slide(context, self._mouse(context, event)[0])
        elif self._mode == 'number':
            self._old = getattr(s, w["prop"])
            self._x0 = self._mouse(context, event)[0]
            self._moved = False
        else:
            self._mode = 'type'
            self._old = s.search_filter
            _edit = {"region": context.region.as_pointer(), "act": w["act"],
                     "text": s.search_filter, "fresh": False}
        context.window_manager.modal_handler_add(self)
        _redraw()
        return {'RUNNING_MODAL'}

    def _slide(self, context, mx):
        w = self._w
        x, _, ww, _ = w["rect"]
        frac = min(max((mx - x) / max(ww, 1.0), 0.0), 1.0)
        setattr(context.scene.cam_tools_settings, w["prop"],
                w["lo"] + frac * (w["hi"] - w["lo"]))

    def _finish(self, context, undo=None, cancelled=False):
        global _drag, _edit
        _drag = None
        _edit = None
        if undo:
            bpy.ops.ed.undo_push(message=undo)
        _redraw()
        return {'CANCELLED'} if cancelled else {'FINISHED'}

    def cancel(self, context):
        # Blender ends modals on its own too (file load, window close)
        global _drag, _edit
        _drag = None
        _edit = None

    def modal(self, context, event):
        global _drag, _edit
        if self._mode == 'type':
            return self._type(context, event)

        s = context.scene.cam_tools_settings
        prop = self._w["prop"]
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            setattr(s, prop, self._old)
            return self._finish(context, cancelled=True)

        mx = self._mouse(context, event)[0]
        if self._mode == 'slider':
            if event.type == 'MOUSEMOVE':
                self._slide(context, mx)
                _redraw()
            elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                return self._finish(context, undo=self._w["text"])
            return {'RUNNING_MODAL'}

        # number: drag sideways to change, click without dragging to type
        sc = context.preferences.system.ui_scale
        if event.type == 'MOUSEMOVE':
            dx = (mx - self._x0) / sc
            if not self._moved and abs(dx) > 3:
                self._moved = True
                _drag = self._w["act"]
            if self._moved:
                step = 0.001 if event.shift else 0.01
                setattr(s, prop, self._old + dx * step)   # RNA clamps to min
                _redraw()
        elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            if self._moved:
                return self._finish(context, undo=self._w["text"])
            self._mode = 'type'
            text = _fmt(getattr(s, prop))
            _edit = {"region": context.region.as_pointer(), "act": self._w["act"],
                     "text": text, "seed": text, "fresh": True}
            _redraw()
        return {'RUNNING_MODAL'}

    def _type(self, context, event):
        e = _edit
        s = context.scene.cam_tools_settings
        number = e["act"][0] == 'number'

        # Timers (animation playback, region fades) and the mouse keep
        # going while a field is open; only the keyboard is ours
        if event.type.startswith('TIMER') or event.type in {
                'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE', 'WHEELUPMOUSE',
                'WHEELDOWNMOUSE', 'MIDDLEMOUSE', 'TRACKPADPAN', 'TRACKPADZOOM',
                'WINDOW_DEACTIVATE'}:
            return {'PASS_THROUGH'}
        if event.value != 'PRESS':
            return {'RUNNING_MODAL'}

        if event.type == 'LEFTMOUSE':
            w = _hit(context.region, *self._mouse(context, event))
            if w is not None and w["act"] == e["act"]:
                return {'RUNNING_MODAL'}          # click inside the field
            # Click elsewhere keeps the text and still does its own thing
            return self._finish(context, undo=self._close(context)) | {'PASS_THROUGH'}
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            if not number:
                s.search_filter = self._old
            return self._finish(context, cancelled=True)
        if event.type in {'RET', 'NUMPAD_ENTER', 'TAB'}:
            return self._finish(context, undo=self._close(context))

        text = e["text"]
        if event.type == 'BACK_SPACE':
            if e["fresh"]:
                text = ""
            elif event.ctrl:
                t = text.rstrip()
                text = t[:t.rfind(" ") + 1]
            else:
                text = text[:-1]
        elif event.ctrl and event.type == 'A':
            e["fresh"] = True
            _redraw()
            return {'RUNNING_MODAL'}
        elif event.ctrl and event.type == 'V':
            paste = context.window_manager.clipboard.splitlines()
            text = ("" if e["fresh"] else text) + (paste[0] if paste else "")
        elif (event.unicode and event.unicode.isprintable()
              and not (event.ctrl or event.alt or event.oskey)):
            ch = event.unicode
            if number and not (ch.isdigit() or ch in ".,-"):
                return {'RUNNING_MODAL'}
            text = ch if e["fresh"] else text + ch
        else:
            return {'RUNNING_MODAL'}               # swallow other shortcuts

        e["text"] = text
        e["fresh"] = False
        if not number:
            s.search_filter = text                 # live filtering
        _redraw()
        return {'RUNNING_MODAL'}

    def _close(self, context):
        """Commit the typed text; the undo label if anything changed."""
        e = _edit
        s = context.scene.cam_tools_settings
        if e["act"][0] != 'number':
            return "Search" if s.search_filter != self._old else None
        # Opening the field and clicking away must not round the value to
        # the 2–3 decimals shown, nor push an undo step
        if e["fresh"] or e["text"] == e["seed"]:
            return None
        try:
            value = float(e["text"].replace(",", "."))
        except ValueError:
            return None                            # not a number: keep the old value
        setattr(s, self._w["prop"], value)
        return self._w["text"]


classes = (
    CAM_PT_panel,
    CAM_OT_ui_hover,
    CAM_OT_ui_click,
)

# Not in keymaps.addon_keymaps: that list is the user-facing hotkey the
# preferences draw as editable. These are plumbing, always on.
_keymaps = []


def register():
    global _draw_handle
    for cls in classes:
        bpy.utils.register_class(cls)
    _draw_handle = bpy.types.SpaceView3D.draw_handler_add(
        _draw, (), 'UI', 'POST_PIXEL')
    bpy.app.handlers.load_post.append(_on_load)

    kc = bpy.context.window_manager.keyconfigs.addon
    if kc is None:
        return  # background mode
    # Hover in the window-level keymap: it also sees the mouse leaving the
    # sidebar for another editor, which clears the highlight
    km = kc.keymaps.new(name="Window", space_type='EMPTY')
    _keymaps.append((km, km.keymap_items.new(
        CAM_OT_ui_hover.bl_idname, 'MOUSEMOVE', 'ANY')))
    # "3D View Generic" is active in the sidebar region too
    km = kc.keymaps.new(name="3D View Generic", space_type='VIEW_3D')
    _keymaps.append((km, km.keymap_items.new(
        CAM_OT_ui_click.bl_idname, 'LEFTMOUSE', 'PRESS')))


def unregister():
    global _draw_handle, _hover, _edit, _drag, _tip_block
    for km, kmi in _keymaps:
        km.keymap_items.remove(kmi)
    _keymaps.clear()
    if _draw_handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handle, 'UI')
        _draw_handle = None
    for fn in (_tip_timer, _unzoom):
        if bpy.app.timers.is_registered(fn):
            bpy.app.timers.unregister(fn)
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)
    _cells.clear()
    _hover = _edit = _drag = _tip_block = None
    paint.release()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
