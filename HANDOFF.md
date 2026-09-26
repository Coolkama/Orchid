# Limijoy / Orchid handoff

**Updated:** 2026-08-17  
**Active branch:** `glimmerkin-inspection-pipeline`  
**Current branch baseline before this documentation pass:** `830a97efcc56c0370aa0ee8d711e926a4880c958`

## Role of this repository

Orchid is the staging and validation sandbox for Limijoy model, rig, facial projection and animation work. Visual or rig changes should be proven here before they are promoted to the Android runtime.

## Approved keeper

The current approved keeper is the blank-face, 45-bone rig:

- source model: `assets/models/glimmerkin-tpose-blank-face-candidate.glb`;
- rig profile: `tpose-blank-face-candidate-45`;
- runtime export pipeline: `scripts/build_limijoy_runtime_assets.py`;
- runtime validation workflow: `.github/workflows/limijoy-runtime-assets.yml`;
- validated runtime-asset commit: `830a97efcc56c0370aa0ee8d711e926a4880c958`.

The exported runtime GLB has been re-imported and visually checked after export. The skinned face shell remains attached through head turns and the rig remains 45 bones.

## Approved face system

The face is texture driven, using the authored character-sheet overlays rather than procedural drawing:

- `neutral`
- `blink`
- `happy`
- `curious`
- `sad`
- `determined`

Source art lives in `assets/Ace-art/character-sheet/`.

The approved face projection includes:

- aspect-ratio-preserving UV projection;
- final visible face width approximately 81.225% of the first aspect-corrected projection;
- lowered face placement approved on-device;
- two-ring UV support around the cream face patch to prevent mouth clipping;
- a thin skinned face shell for portable runtime use.

This visual result has been approved and promoted into Limijoy. Do not redesign or regenerate the face unless a later device test identifies a specific problem.

## Rig mapping used by Limijoy

Key semantic bones for the 45-bone keeper:

- torso: `Bone_014`
- neck: `Bone_018`
- head: `Bone_017`
- right arm chain: girdle `Bone_028`, upper `Bone_027`, elbow `Bone_026`, wrist `Bone_025`, hand `Bone_024`
- left arm chain: girdle `Bone_023`, upper `Bone_022`, elbow `Bone_021`, wrist `Bone_020`, hand `Bone_019`

The visible hand has two child branches. The main finger direction is **not** the thumb-side branch:

- right main finger chain reference: `Bone_044`
- left main finger chain reference: `Bone_036`
- `Bone_040` / `Bone_032` are thumb-side branches and must not define hand-forward.

This distinction materially improved Carry and Wave in the Android runtime.

## Current animation status

### Approved / good enough to continue

- relaxed neutral arm pose;
- look/head-turn behaviour;
- authored face expressions and blink;
- Carry: palm-up pose now reads correctly after main-finger calibration;
- Wave: substantially improved and no longer shows the previous squashed/twisted hand deformation.

### Known issue deliberately parked

Push still has one visible continuity problem: near the top/contact pose, Limijoy's **left arm/hand can fall back or jump to a different arm position for a frame**. Several continuity/IK attempts reduced other artefacts but did not eliminate this exact fault.

Do not spend more time tuning Push in isolation. Revisit it when there is an actual prop/object to push so contact position, palm direction and elbow route can be judged against a real target.

## Locomotion note

Orchid contains an older validated in-place locomotion baseline in `scripts/limijoy_first_step.py` (historical baseline commit `4c6928faeaf1e61be34ccc780e21ab5a78234272`). Treat it as useful motion/reference work only.

It has **not yet been revalidated as the final walking solution for the new 45-bone keeper and current Limijoy runtime**.

## Next work

1. Create and validate a **sleeping body pose** for the 45-bone keeper. It should be a genuine body position, not just closed eyes plus reduced bobbing.
2. Add walking/locomotion to the current keeper, using the older grounded gait as reference where helpful.
3. Make walking particularly convincing in **mini mode**, where Limijoy should be able to move around the screen rather than remain fixed in place.
4. Keep locomotion separable from upper-body actions so walking can coexist with looking, waving, carrying and later object interaction.
5. Return to the parked Push arm fault once a pushable prop exists.

## Promotion rule

Orchid remains the proving ground. Once a body/animation change is visually accepted here, promote only the required runtime asset/code behaviour to `Coolkama/Limijoy` on `glimmerkin-runtime-rendering`.
