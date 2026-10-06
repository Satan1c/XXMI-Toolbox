# XXMI Toolbox

Game-independent mesh and vertex group tools shared by the XXMI modding add-ons.
It has no sidebar tab of its own: a **Toolbox** panel appears inside the tab of every supported host add-on that
is enabled.

| Host add-on | Tab        |
|-------------|------------|
| XXMI Tools  | XXMI Tools |
| WWMI Tools  | WWMI Tools |
| EFMI Tools  | EFMI Tools |

The vertex group tools are also added to the vertex group specials menu (Object Data properties, and Weight Paint
sidebar) and to **Ctrl+G** in Edit Mode.

## Tools

**Vertex Groups** — all work on every selected mesh.

- **Merge**: joins groups addressing the same ID (`7`, `7.1`, `7.head.001`) or differing only by Blender's `.001`
  suffix. Modes: same ID, into active, list, range. A labelled name (`0.head`) is kept over a bare ID (`0`).
- **Fill Gaps**: adds missing IDs so the list runs `0..N`, and prefixes name-only groups with their position (`hair` at
  position 2 becomes `2.hair`). IDs above 1023 are refused.
- **Remove Unused** / **Remove All**.

**Mesh**

- Separate by Material (parts named after their material), Clean UV Names (`TEXCOORD.xy`, `TEXCOORD1.xy`, …), Reset
  Vertex Colors, Convert Vertex Colors to Float (keeps stored values).
- Apply Modifiers with Shape Keys.
- Merged-object sculpt: Create Merged Object, then Apply Sculpt or Apply Sculpt + Shape Keys (also moves every shape key
  by the sculpted offset). Also applies merged objects made by WWMI/EFMI Tools.

**Model Swap** — add meshes to the **Source** list (where the format comes from) and the **Target** list (where it is
applied) with **Add Selected**. Meshes must be aligned in world space. Every target is processed in one click; several
source meshes are used together as one.

- **UV Names**: target UV maps renamed in order to the first source's names, extra ones removed.
- **Colors**: color attributes overwritten from the sources with their names, domain and type; extra ones removed.
- **VGs**: for weighted targets, **Keep Weights** renames each target group after the source group it overlaps most
  (judged by the source weights on the nearest source surface, across all sources and all targets together, so every
  piece gets the same name for the same bone); **Copy Weights** replaces their weights with the source ones. Unweighted
  targets always get the source weights. Then: remove unused → merge → limit to 4 influences and normalize (DX11) →
  remove unused → fill gaps → sort.
- **Remap Vertex Groups** runs only the remap step.
- **Copy Custom Properties** replaces the custom properties of every target with those of the source. Needs exactly one
  source mesh, since properties belong to one specific piece.

**Armature** — makes dumped meshes poseable with the game's own armature, whatever they are named or however the
character is split.

- **Attach to Game Armature**: select the game model (its armature or a mesh it deforms, e.g. from an FBX extract) and
  the dumped meshes, in the same place and scale. The game model is mirrored if it was imported with the other
  handedness. Each dumped mesh's IDs are matched to the game bones whose weights look most like theirs. Meshes that
  number their bones the same way (all of a merged character, or the pieces of one component) share a hidden ID
  armature: its bones are named `0`, `1`, … and copy the game bone each ID matched. Pose the game armature and every
  piece follows; vertex groups keep their plain IDs, so exporting and the vertex group tools are unaffected. Run it
  again with new pieces selected to attach them too: they join the ID armature they agree with, which grows any IDs it
  lacks.
- **Clean Up Game Model**: once every piece is attached, deletes what came with the game model that nothing uses: its
  meshes, whatever hangs under its armature (weapons, props), bones no ID armature follows (their parents are kept,
  since a bone's pose depends on them) and the collections this leaves empty. New pieces can't be attached afterwards,
  since matching needs the game meshes; Undo brings them back.

## Install

Download from [Releases](https://github.com/Satan1c/XXMI-Toolbox/releases):

- Blender 4.2+: `xxmi_toolbox-<version>.zip`, via Edit > Preferences > Get Extensions > Install from Disk (or drag it
  into Blender).
- Blender 3.6: `xxmi_toolbox-<version>-legacy.zip`, via Edit > Preferences > Add-ons > Install. The legacy copy does
  nothing on 4.2+.

## Updating

The **Updater** section of the Toolbox panel, and the add-on preferences, check GitHub for a new release (at start-up,
at most once per interval, or with the button) and install it; restart Blender afterwards. A new release also shows a
notice at the top of the Toolbox panel. On Blender 4.2+ this needs **Allow Online Access** (Preferences > System).

## Layout

| Path             | Contents                                                                                                     |
|------------------|--------------------------------------------------------------------------------------------------------------|
| `vertex_groups/` | IDs and naming (`ids.py`), merge / fill / remove (`cleanup.py`), weights, remap by overlap                   |
| `mesh/`          | UV names, vertex colors, separate by material, modifiers with shape keys, merged-object sculpt               |
| `model_swap/`    | Model Swap, custom properties copy, source / target lists                                                    |
| `armature/`      | Matching dumped IDs to ripped bones and the ID armatures (`attach.py`), ripped model clean-up (`cleanup.py`) |
| `updater/`       | GitHub release check, download and install                                                                   |
| `common/`        | Shared helpers, the per-mesh operator base, data transfer                                                    |
| `panels.py`      | The Toolbox panel and its sections in the host add-ons' tabs                                                 |
| `settings.py`    | Scene settings, one group per feature folder (its `settings.py`)                                             |
| `preferences.py` | Add-on preferences                                                                                           |

## Credits

Built from the toolboxes of:

- [XXMI Tools](https://github.com/leotorrez/XXMITools) by [LeoTorreZ](https://github.com/leotorrez)
- [QuickImportXXMI](https://github.com/Seris0/QuickImportXXMI) by [Gustav0](https://github.com/Seris0) and
  [LeoTorreZ](https://github.com/leotorrez)
- [WWMI Tools](https://github.com/SpectrumQT/WWMI-TOOLS) and [EFMI Tools](https://github.com/SpectrumQT/EFMI-Tools)
  by [SpectrumQT](https://github.com/SpectrumQT)

With scripts by:

- SilentNightSound
- Ave
- Przemysław Bągard

The armature tools replace [ArmatureXXMI](https://github.com/Seris0/Gustav0/tree/main/Addons/ArmatureXXMI) by
[Gustav0](https://github.com/Seris0), with matching logic by Comilarex.

Licensed under GPL-3.0-or-later.
