# Camera Background Matcher

*[Русская версия](README.ru.md)*

Blender 5.2.0 add-on. Solves a pain point when working with scans
(photogrammetry): dozens/hundreds of imported cameras, each needing a
background image and clip start set by hand — the addon does it in
bulk and gives you a handy camera list with previews for navigation.

## Installation

The add-on is a Blender extension. `Edit → Preferences → Add-ons → ⌄`
(top right) `→ Install from Disk…` → pick `camera_background_matcher_vX.Y.Z.zip`
— or just drag the zip into the Blender window. The panel shows up in
`View3D → N-panel → CamTools`.

If an older version was installed as a legacy add-on (before 1.4.1),
remove it first (`⌄ → Remove` on its row): both copies can't be enabled
at once.

## Importing backgrounds from a folder

After importing a model from Metashape/RealityCapture/etc., cameras
in Blender come with a bunch of problems: broken clip start, no
background images, everything has to be set up by hand one by one.

1. `CamTools → Import from Folder` → pick the folder with your scan photos.
2. The addon matches images to cameras **by name** (file name = camera name).
3. If the scanner adds suffixes to the file name or the camera name
   (e.g. RealityCapture makes it `Camera.png`, so an exact match
   fails) — enable **Ignore Suffixes** in the import dialog. Matching
   then compares the name up to the first dot, on both sides.
4. After import, every matched camera already has its background set
   up — nothing to configure by hand.
5. Re-importing from the same (or a different) folder updates
   backgrounds on already-added cameras.

## Bulk settings for all scene cameras

Two sliders at the top of the panel apply to **all** cameras in the
scene (not just the ones in the list):

- **Clip Start** — fixes the typical broken near clipping on cameras after import.
- **Opacity** — background image opacity, if the background is too harsh or barely visible.

## Building the working camera list

Scans give you cameras from every angle, but modeling usually only
needs 5–10 key ones, with the rest needed occasionally to cross-check
from a different angle.

1. Select the cameras you need in the viewport or the outliner (multi-select works).
2. `Add Selected` — adds them to the addon's list (sorted alphabetically on insert).
3. `Clear All` — clears the whole list (undoable with Ctrl+Z if needed).
4. The × on a camera card — removes just that one camera from the list.
5. `Remove Every Other` — removes every other camera from the
   **currently displayed** list (handy for quickly thinning out to, say, every second angle).

Renaming cameras in the outliner doesn't break the list — cameras are
tracked by object reference, not by name.

## Preview grid

- **1 / 2 / 3** buttons above the list — how many preview columns to show; this also controls image size.
- Search field — live filter by camera name, instant, filters as you type.
- **By Name / By Added Order** toggle — display sort order (alphabetical
  or insertion order); doesn't affect the addon's underlying list.
- Clicking the camera name at the top of the card, or the **Select
  Camera** button at the bottom, makes it the active camera and
  switches the view to Camera View.

## Quick camera switching (hotkey)

`Ctrl + mouse wheel` in the 3D Viewport cycles through cameras in the
list (respects the current sort order). Enabled by default.

- Rebind or disable: `Edit → Preferences → Add-ons → Camera Background Matcher`.
- The bottom of the CamTools panel shows a hint with the current bind
  (updates automatically if you change it).

### In edit mode the selection stays put

With a mesh in edit mode, switching cameras (hotkey or card click)
keeps the selected point on the same spot of the screen — the viewport
pans under it, like `Shift + middle mouse` in camera view. Handy for
checking one point of the model against different photos.

- The anchor is the active element (last clicked vertex), or the
  selection's centre when there is none.
- The camera itself doesn't move, so the photo match is untouched —
  only the camera frame shifts inside the viewport. `Home` re-centres it.
- Turned on and off by the **Keep Selection in Place** checkbox
  (`SCENE` section, on by default).
- **Keep Scale** (shown under it, on by default) also zooms the camera
  view, like the mouse wheel does there, so the area around the point
  keeps its size on screen when the next camera is closer or farther away.

## Hide/show camera frustums in the viewport

`Hide Camera Icons` at the bottom of the panel hides the frustum
triangles of **all** scene cameras in the viewport, if there are too
many of them visually and they're getting in the way of the model.

## Select cameras in the scene

`Select Cameras in Scene` at the bottom of the panel deselects
everything and selects only the cameras from the addon's list (in the
outliner and viewport). Handy for moving them all into a separate
collection in one go (`M` → Move to Collection) or batch-processing
them some other way.
