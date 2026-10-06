import bpy
import bmesh
import math
import os
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector

from . import notes
from . import previews
from .properties import displayed

# ---------------------------------------------------------------------------
# Background import
# ---------------------------------------------------------------------------

# Formats Blender can load as images; anything else in the folder
# (Thumbs.db, desktop.ini, sidecar files...) must be skipped
IMAGE_EXTENSIONS = {
    ".bmp", ".png", ".jpg", ".jpeg", ".jp2", ".j2c", ".tga", ".cin",
    ".dpx", ".exr", ".hdr", ".sgi", ".rgb", ".bw", ".tif", ".tiff",
    ".webp", ".psd",
}


class CAM_OT_setup_backgrounds(bpy.types.Operator):
    bl_idname = "cam.setup_backgrounds"
    bl_label = "Import from Folder"
    bl_description = "Import background images from a folder and match them to cameras by name"
    bl_options = {'UNDO'}
    directory: bpy.props.StringProperty(subtype="DIR_PATH")

    ignore_suffix: bpy.props.BoolProperty(
        name="Ignore Suffixes",
        description=(
            "Ignore suffixes on both files and cameras when matching.\n"
            "Example: camera 'Camera.001' matches file 'Camera.jpg',\n"
            "and file 'Camera.001.jpg' matches camera 'Camera'"
        ),
        default=False
    )

    def execute(self, context):
        if not os.path.exists(self.directory):
            self.report({'ERROR'}, "Folder not found")
            return {"CANCELLED"}

        s = context.scene.cam_tools_settings
        files = os.listdir(self.directory)

        file_map = {}
        for f in files:
            base, ext = os.path.splitext(f)
            if ext.lower() not in IMAGE_EXTENSIONS:
                continue
            key_full  = base
            key_short = base.split('.')[0]
            path = os.path.join(self.directory, f)
            file_map.setdefault(key_full, path)
            if self.ignore_suffix:
                file_map.setdefault(key_short, path)

        # Same image names may now point at different files — drop the
        # cached square thumbnails so they get rebuilt on next draw
        previews.invalidate()

        updated = 0
        skipped = 0
        failed  = 0
        done = set()        # camera data already given its background

        # This scene's cameras only: the list is per scene, and a card of a
        # camera from another scene couldn't be made the scene camera
        for cam_obj in [o for o in context.scene.objects if o.type == 'CAMERA']:
            cam_data = cam_obj.data
            img_path = file_map.get(cam_obj.name)
            if not img_path and self.ignore_suffix:
                img_path = file_map.get(cam_obj.name.split('.')[0])
            if not img_path:
                skipped += 1
                continue

            try:
                img = bpy.data.images.load(img_path, check_existing=True)
            except RuntimeError:
                failed += 1
                continue

            if cam_data not in done:    # objects sharing data (Alt+D): once
                done.add(cam_data)
                cam_data.show_background_images = True
                cam_data.background_images.clear()
                bg = cam_data.background_images.new()
                bg.image = img
                bg.alpha = s.opacity_value

            existing = next((it for it in s.mc_items if it.camera == cam_obj), None)
            if existing:
                existing.image = img
            else:
                item = s.mc_items.add()
                item.camera = cam_obj
                item.image = img

            updated += 1

        msg = f"Updated: {updated}, skipped: {skipped}"
        if failed:
            msg += f", failed to load: {failed}"
        self.report({'WARNING' if failed else 'INFO'}, msg)
        return {"FINISHED"}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


# ---------------------------------------------------------------------------
# List management
# ---------------------------------------------------------------------------

class CAM_OT_clear_all(bpy.types.Operator):
    bl_idname = "cam.clear_all"
    bl_label = "Clear All"
    bl_description = "Remove all cameras from the list"
    bl_options = {'UNDO'}

    def execute(self, context):
        context.scene.cam_tools_settings.mc_items.clear()
        return {'FINISHED'}


class CAM_OT_add_camera(bpy.types.Operator):
    bl_idname = "cam.add_camera"
    bl_label = "Add Selected"
    bl_description = "Add all selected cameras to the list"
    bl_options = {'UNDO'}

    def execute(self, context):
        s = context.scene.cam_tools_settings
        cam_objects = sorted(
            [o for o in context.selected_objects if o.type == 'CAMERA'],
            key=lambda o: o.name
        )

        if not cam_objects:
            notes.report(self, {'WARNING'}, "No cameras selected")
            return {'CANCELLED'}

        added = 0
        for cam_obj in cam_objects:
            if not any(it.camera == cam_obj for it in s.mc_items):
                item = s.mc_items.add()
                item.camera = cam_obj
                if cam_obj.data.background_images:
                    item.image = cam_obj.data.background_images[0].image
                added += 1

        notes.report(self, {'INFO'}, f"Cameras added: {added}")
        return {'FINISHED'}


class CAM_OT_remove_fav(bpy.types.Operator):
    bl_idname = "cam.remove_fav"
    bl_label = ""
    bl_description = "Remove this camera from the list"
    bl_options = {'UNDO'}
    index: bpy.props.IntProperty()

    def execute(self, context):
        s = context.scene.cam_tools_settings
        if self.index >= len(s.mc_items):
            return {'CANCELLED'}
        s.mc_items.remove(self.index)
        return {'FINISHED'}


class CAM_OT_remove_every_other(bpy.types.Operator):
    bl_idname = "cam.remove_every_other"
    bl_label = "Remove Every Other"
    bl_description = (
        "Remove cameras at odd positions of the displayed list (2nd, 4th, 6th...)\n"
        "Respects the current sort mode and search filter"
    )
    bl_options = {'UNDO'}

    def execute(self, context):
        s = context.scene.cam_tools_settings
        to_remove = sorted(
            [mc_idx for pos, (mc_idx, _) in enumerate(displayed(s)) if pos % 2 == 1],
            reverse=True
        )

        if not to_remove:
            notes.report(self, {'INFO'}, "No cameras at odd positions")
            return {'CANCELLED'}

        for mc_idx in to_remove:
            s.mc_items.remove(mc_idx)

        notes.report(self, {'INFO'}, f"Cameras removed: {len(to_remove)}")
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# Select / switch cameras
# ---------------------------------------------------------------------------

def _edit_anchor(context):
    """World-space point that keeps its place on screen across a camera switch.

    Mesh edit mode only: the active element (last clicked vertex, or the
    centre of the active edge / face), else the median of the selected
    vertices of every object in edit mode. None when nothing is selected."""
    if context.mode != 'EDIT_MESH':
        return None

    obj = context.edit_object
    active = bmesh.from_edit_mesh(obj.data).select_history.active
    if active is not None and active.select:
        if isinstance(active, bmesh.types.BMVert):
            co = active.co
        elif isinstance(active, bmesh.types.BMEdge):
            co = (active.verts[0].co + active.verts[1].co) / 2
        else:
            co = active.calc_center_median()
        return obj.matrix_world @ co

    total = Vector()
    count = 0
    for o in context.objects_in_mode:
        sel = [v.co for v in bmesh.from_edit_mesh(o.data).verts if v.select]
        if sel:
            total += (o.matrix_world @ (sum(sel, Vector()) / len(sel))) * len(sel)
            count += len(sel)
    return total / count if count else None


def _zoom_fac(camzoom):
    """Camera-view zoom slider value → frame scale factor; the frame's size
    on screen is proportional to it (BKE_screen_view3d_zoom_to_fac)."""
    return (math.sqrt(2) + camzoom / 50) ** 2 / 4


def _screen_scale(region, rv3d, point):
    """Screen pixels per world unit at point, measured along the view's
    right axis. For a pinhole camera that's focal length / depth exactly —
    the size of the area around the point, whatever the lens or distance."""
    right = rv3d.view_matrix.to_3x3()[0].normalized()
    step = max(-(rv3d.view_matrix @ point).z, 1e-6) * 0.01
    a = location_3d_to_region_2d(region, rv3d, point)
    b = location_3d_to_region_2d(region, rv3d, point + right * step)
    if a is None or b is None:
        return None
    return (b - a).length / step


def _switch_camera(context, cam):
    """Make cam the scene camera and put every 3D view into camera view.

    In mesh edit mode (with pin_selection on) the selection stays on the
    same screen pixel: every view that was already in camera view gets its
    camera frame panned — view_camera_offset, the same thing Shift+MMB does
    in camera view. With pin_scale the frame is also zoomed
    (view_camera_zoom, like the mouse wheel there) so the area around the
    selection keeps its size. The camera itself doesn't move, so the photo
    match is untouched."""
    s = context.scene.cam_tools_settings
    anchor = _edit_anchor(context) if s.pin_selection else None

    pinned = []
    views = []
    for area in context.screen.areas:
        if area.type != 'VIEW_3D':
            continue
        rv3d = area.spaces[0].region_3d
        views.append((area, rv3d))
        if anchor is None or rv3d.view_perspective != 'CAMERA':
            continue
        region = next(
            (r for r in area.regions if r.type == 'WINDOW' and r.data == rv3d),
            None
        )
        if region is None:
            continue
        # Matrices are only refreshed on redraw — a fast hotkey repeat
        # would otherwise measure against the previous switch's offset
        rv3d.update()
        before = location_3d_to_region_2d(region, rv3d, anchor)
        if before is not None:
            scale = _screen_scale(region, rv3d, anchor) if s.pin_scale else None
            pinned.append((region, rv3d, before, scale))

    context.scene.camera = cam
    for area, rv3d in views:
        rv3d.view_perspective = 'CAMERA'
        area.tag_redraw()

    for region, rv3d, before, scale in pinned:
        rv3d.update()
        if scale:
            now = _screen_scale(region, rv3d, anchor)
            if now:
                # The frame's size is linear in the zoom factor; invert the
                # factor formula to get the slider value. RNA clamps it to
                # Blender's zoom range (-30..600)
                fac = _zoom_fac(rv3d.view_camera_zoom) * scale / now
                rv3d.view_camera_zoom = (2 * math.sqrt(fac) - math.sqrt(2)) * 50
                rv3d.update()
        after = location_3d_to_region_2d(region, rv3d, anchor)
        if after is None:
            continue  # behind the new camera
        # Pixels → offset units, as Blender's own camera-view pan does it
        # (ED_view3d_camera_view_pan), including its ±1 clamp
        zoom = _zoom_fac(rv3d.view_camera_zoom) * 2
        dx, dy = rv3d.view_camera_offset
        dx += (after.x - before.x) / (region.width * zoom)
        dy += (after.y - before.y) / (region.height * zoom)
        rv3d.view_camera_offset = (max(-1.0, min(1.0, dx)), max(-1.0, min(1.0, dy)))


class CAM_OT_select_preview(bpy.types.Operator):
    bl_idname = "cam.select_preview"
    bl_label = ""
    bl_description = "Set as active camera and switch to camera view"
    bl_options = {'INTERNAL'}
    index: bpy.props.IntProperty()

    def execute(self, context):
        s = context.scene.cam_tools_settings
        if self.index < len(s.mc_items):
            item = s.mc_items[self.index]
            cam = item.camera
            if cam:
                _switch_camera(context, cam)
        return {'FINISHED'}


class CAM_OT_clear_search(bpy.types.Operator):
    bl_idname = "cam.clear_search"
    bl_label = ""
    bl_description = "Clear the search field"

    def execute(self, context):
        context.scene.cam_tools_settings.search_filter = ""
        return {'FINISHED'}


class CAM_OT_cycle_camera(bpy.types.Operator):
    """Switch the active camera from the CamTools list"""
    bl_idname = "cam.cycle_camera"
    bl_label = "Cycle Camera"
    bl_options = {'INTERNAL'}

    direction: bpy.props.IntProperty(
        default=1,
        description="1 = next camera, -1 = previous camera"
    )

    @classmethod
    def poll(cls, context):
        s = context.scene.cam_tools_settings
        return any(it.camera for it in s.mc_items)

    def execute(self, context):
        s = context.scene.cam_tools_settings

        # The cameras on screen: search filter + sort, as the grid shows them
        items = [it for _, it in displayed(s)]
        if not items:
            return {'PASS_THROUGH'}

        current = context.scene.camera
        cur_idx = next(
            (i for i, it in enumerate(items) if it.camera == current),
            None
        )

        if cur_idx is None:
            next_idx = 0 if self.direction == 1 else len(items) - 1
        else:
            next_idx = (cur_idx + self.direction) % len(items)

        cam = items[next_idx].camera
        _switch_camera(context, cam)

        self.report({'INFO'}, f"Camera: {cam.name}  [{next_idx + 1}/{len(items)}]")
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# Scene display / selection
# ---------------------------------------------------------------------------

HIDDEN_SIZE = 0.001
# Original display_size, stored on the camera data while the icons are
# hidden; the leading underscore keeps it out of the Custom Properties panel
SIZE_KEY = "_cbm_display_size"


class CAM_OT_toggle_camera_display(bpy.types.Operator):
    """Hide / show the frustums of all scene cameras in the viewport"""
    bl_idname = "cam.toggle_camera_display"
    bl_label = "Toggle Camera Icons"
    bl_description = (
        "Hides the frustum triangles of ALL scene cameras in the viewport (display_size → 0.001).\n"
        "Cameras remain fully functional, background images are preserved.\n"
        "Pressing again restores the original sizes"
    )

    @classmethod
    def poll(cls, context):
        return any(o.type == 'CAMERA' for o in context.scene.objects)

    def execute(self, context):
        s = context.scene.cam_tools_settings
        cam_objects = [o for o in context.scene.objects if o.type == 'CAMERA']
        # display_size belongs to the camera data, which objects can share
        # (Alt+D): one saved size per data block, kept on the block itself —
        # so renaming a camera while hidden doesn't lose it either
        datas = {o.data for o in cam_objects}

        if not s.cameras_display_hidden:
            for d in datas:
                if SIZE_KEY not in d:
                    d[SIZE_KEY] = d.display_size
                d.display_size = HIDDEN_SIZE
            s.cameras_display_hidden = True
            notes.report(self, {'INFO'}, f"Icons hidden for {len(cam_objects)} scene cameras")
        else:
            # Only what was shrunk comes back; a camera added while hidden
            # keeps its own size
            for d in datas:
                if SIZE_KEY in d:
                    d.display_size = d[SIZE_KEY]
                    del d[SIZE_KEY]
            s.cameras_display_hidden = False
            notes.report(self, {'INFO'}, "Camera icons restored")

        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

        return {'FINISHED'}


class CAM_OT_select_in_outliner(bpy.types.Operator):
    """Select all cameras from the preview list in the outliner and viewport"""
    bl_idname = "cam.select_in_outliner"
    bl_label = "Select Cameras in Outliner"
    bl_description = (
        "Deselects all objects and selects only the cameras from the list.\n"
        "After that you can move them between collections (M) or run other operations"
    )
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        s = context.scene.cam_tools_settings
        return any(it.camera for it in s.mc_items)

    def execute(self, context):
        s = context.scene.cam_tools_settings

        cam_objects = [it.camera for it in s.mc_items if it.camera]
        if not cam_objects:
            notes.report(self, {'WARNING'}, "No cameras in the list")
            return {'CANCELLED'}

        # The view layer's objects, not the scene's: an object in an excluded
        # collection raises on select_set / becoming active
        for obj in context.view_layer.objects:
            obj.select_set(False)

        visible = [cam for cam in cam_objects if cam.visible_get()]
        for cam in visible:
            cam.select_set(True)
        selected = len(visible)
        skipped = len(cam_objects) - selected

        if visible:
            context.view_layer.objects.active = visible[0]

        for area in context.screen.areas:
            if area.type in {'OUTLINER', 'VIEW_3D'}:
                area.tag_redraw()

        msg = f"Cameras selected: {selected}"
        if skipped:
            msg += f"  (hidden skipped: {skipped})"
        notes.report(self, {'INFO'}, msg)
        return {'FINISHED'}


classes = (
    CAM_OT_setup_backgrounds,
    CAM_OT_clear_all,
    CAM_OT_add_camera,
    CAM_OT_remove_fav,
    CAM_OT_remove_every_other,
    CAM_OT_select_preview,
    CAM_OT_clear_search,
    CAM_OT_cycle_camera,
    CAM_OT_toggle_camera_display,
    CAM_OT_select_in_outliner,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
