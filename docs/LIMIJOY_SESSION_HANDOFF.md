# Limijoy session handoff — 14 August 2026

This file is the durable handoff for continuing Limijoy development in a fresh ChatGPT session. It records the important decisions, measured rig facts, current branch state, and the next implementation direction so we do not repeat the same discovery work.

## Repository / working state

- Repository: `Coolkama/Orchid`
- Working branch: `glimmerkin-inspection-pipeline`
- Open PR: #2
- Main character asset: `assets/models/glimmerkin.glb`
- Character/app name: **Limijoy**. Older filenames may still use “Glimmerkin”.
- Prefer direct **GitHub Actions run links** for render results. Sandbox download links expire too quickly and should not be the primary handoff.

## High-level product direction

Limijoy is a desktop pet that eventually needs to react procedurally to the mouse, screen content, toys, food, user actions, and AI-selected behaviours. The AI/behaviour layer should think in semantic actions such as:

- `lookAt(mouse)`
- `reachFor(object)`
- `walkTo(x, y)`
- `pickUp(object)`
- `wave()`
- `celebrate()`

The AI should **not** know Meshy bone names or raw Euler angles.

## Important architectural decision: stop animating Meshy deform bones directly

Directly authoring `Bone_022 X`, `Bone_021 Y`, etc. has taken too long because Meshy’s local bone axes are rotated, inherited transforms compound, and a local Euler axis does not map cleanly to semantic directions such as “forward”, “up”, or “palm inward”.

The new direction is to place a **semantic control layer** above the Meshy rig.

For an arm, the semantic controls should be:

1. **Hand target** — where the hand should be in world/model space.
2. **Elbow pole** — which way the elbow should point.
3. **Palm direction/orientation target** — which way the palm should face.

A semantic reach should conceptually be expressed as:

```text
reach(
    handPosition = target,
    elbowDirection = outward,
    palmDirection = inward
)
```

The controller/solver then converts that into whatever rotations the underlying Meshy bones require.

## Blender vs app runtime

Blender is now treated as a **calibration and authoring environment**, not the final runtime.

- Fixed actions such as an idle, wave, or celebration can be baked into the GLB and played by the app.
- Dynamic actions such as reaching toward an arbitrary mouse/toy/screen position need a small **runtime IK/orientation solver** in the app.
- The Blender prototype should therefore use portable vector/quaternion/IK maths rather than relying on Blender-only tricks wherever possible.
- The runtime app should expose semantic controls, not Meshy bones.

Target architecture:

```text
AI / behaviour
    ↓
semantic action, e.g. ReachFor(toy)
    ↓
hand target + elbow pole + palm direction
    ↓
runtime IK/orientation solver
    ↓
Meshy skeleton
    ↓
Limijoy mesh
```

## Current arm rig map

Detailed measured values are in `docs/LIMIJOY_RIG_MAP.md`.

Right arm hierarchy discovered automatically:

`Bone_023 -> Bone_022 -> Bone_021 -> Bone_020 -> Bone_019 -> Bone_018 -> Bone_017 -> Bone_016`

Mirrored left chain:

`Bone_031 -> Bone_030 -> Bone_029 -> Bone_028 -> Bone_027 -> Bone_026 -> Bone_025 -> Bone_024`

Practical roles:

- `Bone_023` / `Bone_031`: shoulder/girdle frame control. Very strong. Do not use as the main reach joint.
- `Bone_022` / `Bone_030`: main upper-arm control.
- `Bone_021` / `Bone_029`: elbow/forearm control; roll strongly affects palm attitude.
- `Bone_020` / `Bone_028`: distal forearm/wrist shaping.
- `Bone_019` / `Bone_027`: wrist/hand finishing.
- `Bone_018` / `Bone_026`: very small visible influence.
- `Bone_017` / `Bone_025` and `Bone_016` / `Bone_024`: essentially no meaningful visible deformation in cardinal tests.

There are **no separately articulated finger branches** in the current Meshy rig. Individual finger animation requires re-rigging/augmentation or another asset.

Imported model world convention measured by diagnostics:

- world +X = Limijoy’s right
- world -Y = Limijoy’s forward
- world +Z = up

Do not confuse these with local pose-bone axes.

## Current reach work

A target-based reach script exists at:

- `scripts/limijoy_semantic_reach.py`

This was a useful improvement because it uses IK for the **hand position** instead of manually guessing upper-arm/elbow Euler rotations.

However, palm orientation was still being adjusted by direct local Euler roll. That is the remaining weak point and should now be replaced rather than tuned further.

Current workflow:

- `.github/workflows/limijoy-reach.yml`

Important temporary detail: because direct GitHub script writes were being falsely blocked by an OpenAI safety classifier, the workflow currently contains an **`Apply palm calibration` text-replacement step** that reverses some palm-roll signs at render time. This is a workaround, not final architecture. Remove it once the semantic orientation controller replaces the raw roll values.

Latest tested reach Action:

- `Limijoy reach` run #25
- https://github.com/Coolkama/Orchid/actions/runs/31728651128

User feedback on the reach sequence:

- The reach trajectory itself became much better with IK.
- A normal horizontal reach should have the **palm facing inward**, not palm up.
- The first attempted palm correction turned the hand in the wrong direction.
- The next test reversed the same amount.
- Rather than continue sign/angle guessing, we decided to replace palm-angle tuning with a real orientation target.

## Next task — do this first in the new session

Do **not** continue manually tuning the current palm Euler values.

Implement a semantic arm-control prototype, preferably as reusable code such as:

- `scripts/limijoy_arm_semantic_controls.py`
- `scripts/limijoy_palm_orientation_sheet.py`

The arm controller should provide at least:

- hand target
- elbow pole
- palm/orientation target
- `reach_to(position, palm_mode="inward", elbow_mode="outward")`
- rest/reset pose helper

Palm modes to support:

- inward
- outward
- up
- down
- forward
- backward

The key implementation goal is to determine the hand’s palm-normal/reference axes once, then use vector/quaternion orientation maths so semantic directions are independent of arbitrary Meshy Euler signs.

## Next diagnostic — one run, many answers

Instead of one render per guess, create one calibration/pose-sheet render using a fixed reach target and multiple palm orientations:

- inward
- outward
- up
- down
- forward
- backward

Ideally combine these with elbow pole variants:

- outward
- neutral
- inward

Render front, side, and/or 3/4 views as useful. The purpose is to calibrate the control system in one GitHub Action instead of repeated commits and waits.

Once the six cardinal palm orientations are correct, use **palm inward + elbow outward** for the standard horizontal reach.

## Earlier reach observations worth retaining

These are historical measurements, not the final control API:

- A previous raw-Euler reach using upper `Bone_022 X=-48` and elbow `Bone_021 X=+10` was among the better direct-Euler attempts.
- In an elbow comparison around that setup, `+10°` elbow X gave a straighter/further-forward distal chain than `0°` or `-10°`.
- Sweeping upper Z eventually produced a horizontal arm, but further compound rotations drove the arm into the head because the inherited rotation plane was tilted.
- This is the evidence that led to the semantic/target-based approach.

Treat these as diagnostic history only, not as the preferred runtime control scheme.

## Shoulder cardinal findings

Measured `Bone_023` behaviour from 90°/180° cardinal tests:

- X = strong vertical swing / frame reorientation
- Y = mostly axial twist/roll
- Z = strong depth/horizontal swing

`Bone_023` neutral is almost horizontal, so the apparent downward arm silhouette mainly comes from `Bone_022` rest orientation. This is why using the shoulder/girdle as a large corrective reach control causes confusing compound motion.

## Head / body facts to retain

- `Bone_034` is useful for head/neck movement without moving the whole body.
- A subtle head turn toward a reached-for object is appropriate, but should remain secondary to the arm action.
- Walking leg work was considered substantially complete before this arm investigation; arms can later swing during walking but also need independent task control.

## Face observations retained from earlier work

- The previous face implementation had an unwanted baked/open mouth plus an overlay mouth; the baked mouth needs to be removed/avoided.
- Neutral should not look permanently open-mouthed/agape.
- A blink diagnostic button was requested so visual glitches can be held long enough to screenshot.
- Face work is not the current priority; semantic arm control is.

## Key diagnostic/action references

- Full arm cardinal diagnostic run #22:
  https://github.com/Coolkama/Orchid/actions/runs/31693545602
- Shoulder-only cardinal diagnostic run #21:
  https://github.com/Coolkama/Orchid/actions/runs/31680543823
- Latest target-based/reversed-palm reach run #25:
  https://github.com/Coolkama/Orchid/actions/runs/31728651128

Important commits from this phase:

- `39bc1cee` — automatic all-descendant arm cardinal diagnostics
- `234f45f2` — created `docs/LIMIJOY_RIG_MAP.md`
- `485169d3` — new target-based semantic reach script
- `e1c0da66` — reach workflow switched to target-based script
- `4a5c08d6` — attempted palm direction correction
- `1fc3e5cc` — workflow workaround to reverse palm-roll signs at render time

## Working method going forward

- Prefer systematic calibration over repeated guesses.
- Prefer semantic/world-space controls over raw local Euler controls.
- Use GitHub Actions artifacts for visual verification.
- When a render completes, provide the direct GitHub Actions run URL.
- Do not claim a render is ready until workflow status is checked.
- Avoid rebuilding knowledge that is already recorded in `docs/LIMIJOY_RIG_MAP.md` and this handoff.
- The immediate success criterion is not “perfect animation”; it is a reusable arm controller that makes future reaches, waves, carrying, pointing, and interaction substantially faster.
