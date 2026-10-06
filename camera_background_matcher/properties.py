import bpy


def update_params(self, context):
    s = context.scene.cam_tools_settings
    for cam in bpy.data.cameras:
        cam.clip_start = s.clip_start_value
        for bg in cam.background_images:
            bg.alpha = s.opacity_value


def displayed(s):
    """(mc_index, item) pairs as the tab shows them: search filter, then the
    optional name sort. Everything acting on "what's on screen" (the grid,
    remove every other, the cycle hotkey) goes through this."""
    search = s.search_filter.lower()
    items = [(i, it) for i, it in enumerate(s.mc_items)
             if it.camera and (not search or search in it.camera.name.lower())]
    if s.sort_by_name:
        items.sort(key=lambda x: x[1].camera.name)
    return items


def update_search(self, context):
    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()


class MCItem(bpy.types.PropertyGroup):
    # PointerProperty, not a string — survives camera rename in the outliner.
    camera: bpy.props.PointerProperty(
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'CAMERA'
    )
    image: bpy.props.PointerProperty(type=bpy.types.Image)


class CamToolsSettings(bpy.types.PropertyGroup):
    clip_start_value: bpy.props.FloatProperty(
        name="Clip Start",
        description="Clip start distance applied to all scene cameras",
        default=1.0, min=0.001, update=update_params
    )
    opacity_value: bpy.props.FloatProperty(
        name="Opacity",
        description="Background image opacity applied to all scene cameras",
        default=0.5, min=0.0, max=1.0, update=update_params
    )
    preview_scale: bpy.props.FloatProperty(
        name="Preview Scale",
        description="Preview thumbnail size",
        default=4.0, min=1.0, max=10.0
    )
    ui_columns: bpy.props.EnumProperty(
        name="Cols",
        description="Number of columns in the camera preview grid",
        items=[("1", "1", ""), ("2", "2", ""), ("3", "3", "")],
        default="2"
    )
    search_filter: bpy.props.StringProperty(
        name="Search",
        description="Filter cameras by name",
        default="",
        update=update_search,
        options={'TEXTEDIT_UPDATE'}
    )
    sort_by_name: bpy.props.BoolProperty(
        name="By Name",
        description="Sort the displayed list by camera name (A→Z).\nOff — order in which cameras were added by the user",
        default=False,
    )
    pin_selection: bpy.props.BoolProperty(
        name="Keep Selection in Place",
        description=(
            "In mesh edit mode, switching cameras pans the camera view so the active vertex "
            "(or the selection centre) stays on the same spot of the screen.\n"
            "The camera itself doesn't move"
        ),
        default=True,
    )
    pin_scale: bpy.props.BoolProperty(
        name="Keep Scale",
        description=(
            "Also zoom the camera view so the area around the selection keeps its size "
            "on screen when the next camera is closer or farther away"
        ),
        default=True,
    )
    # The original sizes live on the camera data itself while hidden
    # (operators.SIZE_KEY), not here
    cameras_display_hidden: bpy.props.BoolProperty(
        name="Camera icons hidden",
        default=False,
        options={'HIDDEN'}
    )
    mc_items: bpy.props.CollectionProperty(type=MCItem)


classes = (
    MCItem,
    CamToolsSettings,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.cam_tools_settings = bpy.props.PointerProperty(type=CamToolsSettings)


def unregister():
    del bpy.types.Scene.cam_tools_settings
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
