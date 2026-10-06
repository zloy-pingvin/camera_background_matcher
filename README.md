# Camera Background Matcher

*[Русская версия](README.ru.md)*

Add-on for Blender 4.2 and newer (tested on 4.2, 4.5, 5.0, 5.2). Solves a
pain point when working with scans (photogrammetry): dozens or hundreds of
imported cameras, each needing a background photo and a clip start set by
hand. The add-on does it in bulk and gives you a camera list with photo
previews to navigate the angles you actually model from.

## Installation

The add-on is a Blender extension. `Edit → Preferences → Add-ons → ⌄`
(top right) `→ Install from Disk…` → pick `camera_background_matcher_vX.Y.Z.zip`
— or just drag the zip into the Blender window. The panel shows up in
`View3D → N-panel → CamTools`; its title shows the installed version.

If an older version was installed as a legacy add-on (before 1.4.1),
remove it first (`⌄ → Remove` on its row): both copies can't be enabled
at once.

## Importing backgrounds from a folder

After importing a model from Metashape / RealityCapture / etc., the
cameras come with a broken clip start and no background images, and
everything has to be set up by hand, one camera at a time.

1. `BACKGROUNDS → Import from Folder` → pick the folder with the scan photos.
2. Photos are matched to cameras **by name** (file name = camera name).
3. If the scanner adds suffixes to the file or camera names (e.g.
   RealityCapture names it `Camera.png`, so an exact match fails),
   enable **Ignore Suffixes** in the import dialog: names are then
   compared up to the first dot, on both sides.
4. Every matched camera gets its background set up and is added to the
   camera list.
5. Importing again (from the same or another folder) updates the
   backgrounds of cameras already in the list.

## Settings for all scene cameras

Under `BACKGROUNDS`, applied to **all** cameras, not just the listed
ones. The two values go together: changing either one sets both on
every camera.

- **Clip Start** — fixes the near clipping that's typically broken after
  import. Drag sideways to change it (`Shift` for fine steps), or click
  to type a value.
- **Opacity** — background photo opacity, when the photo is too harsh or
  barely visible.

## The camera list

Scans give you cameras from every angle, but modeling usually needs 5–10
key ones, plus a few others now and then to cross-check from another side.

1. Select the cameras in the viewport or the outliner (multi-select works).
2. `Add Selected` — adds them to the list, sorted by name.
3. `−½` — removes every other camera of the list **as displayed** (with
   the current sort and search), to thin out the angles quickly.
4. `Clear All` — empties the list.
5. The **×** at the end of a card's name (shows on hover) removes that
   one camera from the list.

Every list action can be undone with `Ctrl+Z`. The cameras themselves
stay in the scene — only the list changes. Renaming a camera in the
outliner doesn't break the list: cameras are tracked by object, not by
name.

## Preview grid

- **Search** — filters by camera name as you type. `Enter` confirms,
  `Esc` restores the previous text, the × clears it. The section header
  shows how many cameras match.
- **By Added Order / By Name** — display order only; the list itself
  keeps the order cameras were added in.
- **1 / 2 / 3** — number of columns, which is also the preview size.
- Each card shows the camera's photo (the grid takes its proportions
  from the photos), with the camera name over its bottom edge. **Click anywhere on a card** to make
  that camera active and switch the view to Camera View. The active
  camera's card is framed in the accent colour.

## Switching cameras with the hotkey

`Ctrl + mouse wheel` in the 3D Viewport goes to the next / previous
camera **of the grid as shown**: with a search typed in, only through
the cameras it found, in the current sort order. Enabled by default.

- The bottom of the panel shows the current keys. When the hotkey is
  off it says so, with an **Enable** link to the add-on preferences.
- Rebind or disable it in `Edit → Preferences → Add-ons → Camera
  Background Matcher` (or in `Preferences → Keymap`) — the rebind is
  saved with your preferences.

### In edit mode the selection stays put

With a mesh in edit mode, switching cameras (hotkey or card click) keeps
the selected point on the same spot of the screen — the view pans under
it, like `Shift + middle mouse` in camera view. Handy for checking one
point of the model against different photos.

- The anchor is the active element (last clicked vertex), or the
  selection's centre when there is none.
- The camera itself doesn't move, so the photo match is untouched — only
  the camera frame shifts inside the viewport. `Home` re-centres it.
- **Keep Selection in Place** (`SCENE` section, on by default) turns it
  on and off.
- **Keep Scale** (under it, on by default) also zooms the camera view,
  like the mouse wheel does there, so the area around the point keeps
  its size on screen when the next camera is closer or farther away.

## Scene tools

- **Hide Camera Icons** — hides the frustum triangles of **all** scene
  cameras in the viewport when there are too many of them in the way of
  the model. The cameras keep working, backgrounds included. The button
  then reads **Show Camera Icons** and brings back the original sizes.
- **Select Cameras in Scene** — deselects everything and selects only
  the cameras of the list (viewport and outliner), e.g. to move them all
  to a collection in one go (`M` → Move to Collection).

## Preferences

`Edit → Preferences → Add-ons → Camera Background Matcher`: links to
Telegram and the Gumroad shop, the hotkey switch and the key editor.

With Blender's interface language set to Russian (and
`Translation → Tooltips` on), the add-on's tooltips are in Russian; the
labels stay in English.

## Links

- Shop: [zloy-pingvin.gumroad.com](https://zloy-pingvin.gumroad.com/)
- Telegram: [t.me/zloytux](https://t.me/zloytux)

## License

GPL-3.0-or-later — see [LICENSE](LICENSE).
