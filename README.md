# Orchid

Experimental graphics and animation sandbox.

Used for testing procedural modelling, rendering, rigging and animation workflows with Blender and related open-source tools.

Work in this repository is experimental and subject to change.

## Headless Blender pipeline

The first milestone proved a fully headless Blender workflow on GitHub Actions:

1. GitHub Actions installs Blender on a Linux runner.
2. Blender runs without a graphical interface.
3. A Python script builds a small test scene from scratch.
4. The workflow renders a PNG and exports a GLB file.
5. Both files are uploaded as a short-lived workflow artifact.

No local Blender installation is required to run these tests.

## Model inspection

The next milestone added inspection of externally generated, textured and rigged GLB characters. The generic inspection workflow:

1. Imports a repository GLB into headless Blender.
2. Measures mesh, material, texture, armature and animation metadata.
3. Records the full bone hierarchy and mesh-to-armature links.
4. Automatically frames and renders front, 3/4, left, right and back views.
5. Saves an inspection `.blend` and JSON report.
6. Uploads the inspection pack as a GitHub Actions artifact.

The current public test creature is Glimmerkin. Its source model belongs at `assets/models/glimmerkin.glb`; see `assets/models/README.md`.

Run the **Inspect model** workflow manually and provide the repository path to any GLB you want to inspect. This keeps the tooling generic while allowing unusual non-humanoid rigs to be compared consistently.

## Glimmerkin rig diagnostics

The rig is being validated from visible deformation rather than relying on generated bone names or humanoid assumptions. The leg diagnostic uses `scripts/limijoy_leg_diagnostic.py` with `assets/models/glimmerkin.glb` and produces controlled stills in `output/limijoy-leg-diagnostic/`.

The associated workflow is `.github/workflows/limijoy-leg-diagnostic.yml`. It installs Blender and its required runtime dependencies, including `python3-numpy`, and uploads the short-lived `limijoy-leg-diagnostic` artifact.

The validated leg correspondence is:

| Function | Leg 1 | Leg 2 |
| --- | --- | --- |
| Hip / leg root | `Bone_006` | `Bone_011` |
| Upper leg / thigh | `Bone_005` | `Bone_010` |
| Knee / lower leg | `Bone_004` | `Bone_009` |
| Ankle / foot | `Bone_003` | `Bone_008` |
| Terminal foot / toe | `Bone_002` | `Bone_007` |

The working rotation convention observed across the investigated rig is X for forward/back pitch, Y for left/right yaw and Z for side-to-side roll.

## Validated locomotion baseline

A complete in-place walking foundation has now been visually validated. The current implementation is `scripts/limijoy_first_step.py`, rendered by `.github/workflows/limijoy-first-step.yml`.

The baseline includes:

- alternating hip and thigh motion;
- knee flexion during swing;
- phase-dependent ankle and toe roll;
- heel contact, flat-foot stance, heel rise and toe-off;
- extra stance keys to keep the load-bearing foot visually grounded rather than hovering during the flat phase;
- a small vertical body movement;
- subtle alternating torso weight shift and yaw using `Bone_014` and `Bone_015`;
- subtle counter-roll through `Bone_034` to keep the head visually stable.

The grounded walk produced by commit `4c6928faeaf1e61be34ccc780e21ab5a78234272` is the validated locomotion baseline and should be preserved when experimenting with later movement layers.

### Animation layering direction

Locomotion is intentionally separate from upper-body behaviour. Arm swing is not baked into the baseline walk because the arms may instead be carrying, reaching, pointing, waving or interacting with an object. Once the arm rig has been mapped, natural arm swing can be provided as the default behaviour when the arms are otherwise unoccupied.

Likewise, head and neck attention can be layered independently over locomotion so that the creature can look at the mouse, screen content or other targets while continuing to move.

The intended movement stack is therefore:

1. **Locomotion base** — legs, feet, stance contact, body rise and weight transfer.
2. **Upper-body behaviour** — optional arm swing, carrying, reaching and gestures.
3. **Attention and expression** — independent head/neck looking and later facial behaviour.

This separation is important for the eventual interactive character, where locomotion and actions need to combine rather than exist only as fixed monolithic animation clips.
