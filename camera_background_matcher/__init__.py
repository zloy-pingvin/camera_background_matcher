# Used by a legacy install (scripts/addons); an extension install reads
# blender_manifest.toml instead — keep the version in both. The values must
# be literals: the Add-ons list ast.literal_eval's this dict without
# importing the module.
bl_info = {
    "name": "Camera Background Matcher",
    "author": "zloy_pingvin",
    "version": (1, 4, 1),
    "blender": (5, 2, 0),
    "location": "View3D > UI > CamTools",
    "description": "Match cameras with backgrounds and manage cameras",
    "doc_url": "https://github.com/zloy-pingvin/camera_background_matcher",
    "category": "Camera",
}

import importlib

from . import keymaps
from . import previews
from . import notes
from . import paint
from . import properties
from . import preferences
from . import operators
from . import ui
from . import translations

# Python caches submodules in sys.modules, so re-running __init__ alone
# (addon disable/enable, "Reload Addons" in the VS Code extension) would
# keep stale code. Force-reload them every time, dependencies first
# (keymaps, previews, notes, paint — the others import names from them).
for _m in (keymaps, previews, notes, paint, properties, preferences, operators,
           ui, translations):
    importlib.reload(_m)

import bpy

modules = (previews, properties, preferences, operators, ui)


def register():
    for m in modules:
        m.register()
    translations.register()

    prefs = bpy.context.preferences.addons.get(__package__)
    use_hotkey = prefs.preferences.use_hotkey if prefs else True
    if use_hotkey:
        keymaps.register_keymaps()


def unregister():
    keymaps.unregister_keymaps()
    translations.unregister()
    for m in reversed(modules):
        m.unregister()


if __name__ == "__main__":
    register()
