import bpy

# Registered keymaps storage — cleared on unregister, read in preferences.py
# (bind editor) and ui.py (hint text)
addon_keymaps = []

KEYMAP = '3D View'


def user_item(kmi):
    """(keymap, item) of the user keyconfig's copy of our addon item kmi.

    Blender merges addon items into keyconfigs.user; rebinds made there
    are what it saves (as diffs) and what's actually active. Editing the
    addon item itself is never saved, so the bind editor and the hint both
    work on this copy. item is None until the merge has run."""
    kc = bpy.context.window_manager.keyconfigs.user
    km = kc.keymaps.get(KEYMAP) if kc else None
    if km is None:
        return None, None
    for item in km.keymap_items:
        if (item.idname == kmi.idname
                and item.properties.direction == kmi.properties.direction):
            return km, item
    return km, None


def register_keymaps():
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if not kc:
        return

    km = kc.keymaps.new(name=KEYMAP, space_type='VIEW_3D')

    kmi_next = km.keymap_items.new(
        "cam.cycle_camera", type='WHEELUPMOUSE', value='PRESS', ctrl=True
    )
    kmi_next.properties.direction = 1
    addon_keymaps.append((km, kmi_next))

    kmi_prev = km.keymap_items.new(
        "cam.cycle_camera", type='WHEELDOWNMOUSE', value='PRESS', ctrl=True
    )
    kmi_prev.properties.direction = -1
    addon_keymaps.append((km, kmi_prev))


def unregister_keymaps():
    for km, kmi in addon_keymaps:
        try:
            km.keymap_items.remove(kmi)
        except RuntimeError:
            pass
    addon_keymaps.clear()


def get_hotkey_label(addon_module_name):
    """Return (enabled, label_next, label_prev) of the live binds — the
    user keyconfig's copies, so a rebind in Preferences → Keymap shows."""
    prefs = bpy.context.preferences.addons.get(addon_module_name)
    if not prefs or not prefs.preferences.use_hotkey:
        return False, "", ""

    if not addon_keymaps:
        return True, "?", "?"

    def kmi_to_str(kmi):
        parts = []
        if kmi.ctrl:  parts.append("Ctrl")
        if kmi.shift: parts.append("Shift")
        if kmi.alt:   parts.append("Alt")
        aliases = {
            'WHEELUPMOUSE':   '↑ Scroll',
            'WHEELDOWNMOUSE': '↓ Scroll',
            'WHEELINMOUSE':   '↑ Scroll',
            'WHEELOUTMOUSE':  '↓ Scroll',
        }
        parts.append(aliases.get(kmi.type, kmi.type))
        return " + ".join(parts)

    label_next = ""
    label_prev = ""
    for _, addon_kmi in addon_keymaps:
        kmi = user_item(addon_kmi)[1] or addon_kmi
        if not kmi.active:
            continue
        if kmi.properties.direction == 1:
            label_next = kmi_to_str(kmi)
        else:
            label_prev = kmi_to_str(kmi)

    return True, label_next, label_prev
