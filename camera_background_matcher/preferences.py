import bpy

from .keymaps import addon_keymaps, register_keymaps, unregister_keymaps

# Author links, shown as buttons at the top of the add-on Preferences
URL_TELEGRAM = "https://t.me/zloytux"
URL_GUMROAD = "https://zloy-pingvin.gumroad.com/"


def update_hotkey(self, context):
    """Enable/disable the hotkey from preferences without reloading the addon"""
    unregister_keymaps()
    if self.use_hotkey:
        register_keymaps()


class CAM_Preferences(bpy.types.AddonPreferences):
    # __package__ = addon package (folder) name, not the submodule's __name__ —
    # matters once split into files: must match the package's bl_idname
    bl_idname = __package__

    use_hotkey: bpy.props.BoolProperty(
        name="Enable camera switch hotkey",
        description="Ctrl + mouse wheel cycles through cameras in the list",
        default=True,
        update=update_hotkey,
    )

    def draw(self, context):
        layout = self.layout

        links = layout.row(align=True)
        links.scale_y = 1.2
        links.operator("wm.url_open", text="Telegram", icon='COMMUNITY').url = URL_TELEGRAM
        links.operator("wm.url_open", text="Gumroad", icon='URL').url = URL_GUMROAD
        layout.separator()

        row = layout.row()
        row.prop(self, "use_hotkey", icon='MOUSE_MMB' if self.use_hotkey else 'MOUSE_LMB')

        if not self.use_hotkey:
            return

        box = layout.box()
        box.label(text="Keys:", icon='KEYINGSET')

        wm = bpy.context.window_manager
        kc = wm.keyconfigs.addon
        if not kc:
            box.label(text="Keyconfig unavailable", icon='ERROR')
            return

        try:
            from rna_keymap_ui import draw_kmi
        except ImportError:
            for km, kmi in addon_keymaps:
                direction = "→ Next" if kmi.properties.direction == 1 else "← Previous"
                box.label(text=f"{direction}: {kmi.type} (ctrl={kmi.ctrl})")
            return

        for km, kmi in addon_keymaps:
            col = box.column()
            col.context_pointer_set("keymap", km)
            draw_kmi([], kc, km, kmi, col, 0)


classes = (
    CAM_Preferences,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
