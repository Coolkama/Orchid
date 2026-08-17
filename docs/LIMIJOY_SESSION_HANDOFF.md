# Limijoy session handoff — 14 August 2026

This file is the durable handoff for continuing Limijoy development in a fresh ChatGPT session. It records the important decisions, measured rig facts, current branch state, and the next implementation direction so we do not repeat the same discovery work.

## Repository / working state

- Repository: `Coolkama/Orchid`
- Working branch: `glimmerkin-inspection-pipeline`
- Open PR: #2
- Latest verified movement commit: `0b4c8d2` — shoulder-relative semantic action targets
- Latest handoff commit before the Android integration checkpoint: `27c65d2`
- Main character asset: `assets/models/glimmerkin.glb`
- Character/app name: **Limijoy**. Older filenames may still use “Glimmerkin”.
- Prefer direct **GitHub Actions run links** for render results. Sandbox download links expire too quickly and should not be the primary handoff.

## High-level product direction

Limijoy is a persistent Android digital pet that eventually needs to react procedurally to touch, screen content, toys, food, user actions, and AI-selected behaviours. Full-screen and mini-pet modes should share one running pet state. Ordinary behaviours must remain local/offline: **pet first, AI second**.

The local behaviour layer and optional AI should both think in semantic actions such as:

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
local pet behaviour / optional AI
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

A reusable semantic controller and target-based reach script now exist at:

- `scripts/limijoy_arm_semantic_controls.py`
- `scripts/limijoy_semantic_reach.py`
- `scripts/limijoy_palm_orientation_sheet.py`

The controller uses IK for the **hand position**, a pole target for the **elbow direction**, and an orthonormal vector frame/quaternion for the **palm direction**. Palm orientation is no longer adjusted with Meshy Euler values.

For the right wrist control, the neutral calibration measured:

- hand-forward reference: local `(0, 1, 0)`
- palm-normal reference: local `(-0.8320505, 0, -0.5546999)`

The palm-normal value is derived once from the neutral inward-facing hand and the actual wrist frame rather than being used as a guessed Euler sign.

Current workflow:

- `.github/workflows/limijoy-reach.yml`
- `.github/workflows/limijoy-palm-orientation-sheet.yml`

The temporary **`Apply palm calibration` text-replacement step has been removed**. The reach workflow now calls the semantic controller directly and contains no render-time sign replacement.

Latest tested reach Action:

- `Limijoy reach` run #31
- https://github.com/Coolkama/Orchid/actions/runs/31781898730

User feedback on the reach sequence:

- The reach trajectory itself became much better with IK.
- A normal horizontal reach should have the **palm facing inward**, not palm up.
- The first attempted palm correction turned the hand in the wrong direction.
- The next test reversed the same amount.
- Rather than continue sign/angle guessing, we decided to replace palm-angle tuning with a real orientation target.

## Completed task — semantic arm controller

Do **not** return to manually tuning palm Euler values.

The reusable controller now provides:

- world-space hand target
- outward, neutral, and inward elbow-pole modes
- world-space palm/orientation target
- `reach_to(position, palm_mode="inward", elbow_mode="outward")`
- `reset_pose()` helper

Supported palm modes:

- inward
- outward
- up
- down
- forward
- backward

The controller constructs local and desired world orthonormal frames, then maps between them with a quaternion. This makes the semantic directions independent of arbitrary Meshy Euler signs and also permits forward/backward palms, which cannot be produced by forearm roll alone.

## Completed diagnostic — one run, many answers

The new calibration workflow rendered all six palm orientations:

- inward
- outward
- up
- down
- forward
- backward

It combined them with all three elbow-pole variants:

- outward
- neutral
- inward

Each of the 18 poses was rendered from front, side, and three-quarter views, producing 54 stills and three contact sheets in one run.

Latest verified orientation-sheet Action:

- `Limijoy palm orientation sheet` run #5
- https://github.com/Coolkama/Orchid/actions/runs/31781898717

Measured results:

- maximum hand-target error across the 18 still poses: `< 4.7e-6` model units
- maximum palm angular error: `0°` at report precision
- maximum hand-target error across the animated reach keys: `< 2.4e-5` model units
- no quaternion flip was visible through the animated reach

The standard horizontal reach now uses **palm inward + elbow outward**.

## Completed phase — bilateral and whole-body semantic actions

The user visually accepted the right-arm controller, then commits `8deefd5`, `a21cd27`, and `0b4c8d2` completed the planned movement foundation.

New reusable modules:

- `scripts/limijoy_body_semantic_controls.py`
- `scripts/limijoy_semantic_actions.py`
- `scripts/limijoy_left_arm_parity.py`
- `scripts/limijoy_semantic_action_showcase.py`

New validation workflows:

- `.github/workflows/limijoy-left-arm-parity.yml`
- `.github/workflows/limijoy-semantic-actions.yml`

### Left-arm parity

The controller is now rendered and measured bilaterally across all six palm modes and all three elbow modes. The left wrist neutral calibration is:

- hand-forward reference: local `(0, 1, 0)`
- palm-normal reference: local `(0.8000007, 0, -0.5999991)`

Verified bilateral Action:

- `Limijoy left-arm parity` run #3
- https://github.com/Coolkama/Orchid/actions/runs/31781898747

Measured across the 18 bilateral poses:

- maximum hand-target error: `< 7.5e-6` model units
- maximum mirrored hand-displacement difference: `< 1.9e-6` model units
- maximum mirrored palm-direction difference: `< 0.000022°`

### Whole-body coordinator

`LimijoyBodySemanticControls.look_at(target)` uses bounded world/character-space quaternions internally, distributed across torso, neck, and head. The behaviour API does not expose the Meshy controls.

Conservative hard bounds:

- total yaw: `±35°`
- total pitch: `±22°`
- forward lean: `±5°`

Individual actions use smaller strengths so gaze and torso motion remain secondary to the hand action. The final reach/point reel kept resolved pitch within about `13.5°`.

The arm solver now reads the **live shoulder position** after body movement, rotates semantic directions through the armature world frame, clamps unreachable requests to a safe reach envelope, and can key a clean IK release back to inherited neutral.

### Reusable semantic action layer

`LimijoySemanticActions` now provides:

- `reach_for(target, side="auto")`
- `point(target, side="auto")`
- `wave(side)`
- `carry(centre)`
- `push(centre)`
- `walking_arm_swing()`

`ArmIntent`, `PoseIntent`, and `animate_path()` are the general extension point. Picking up a stick, carrying food, moving branches, or play behaviours should add new target/orientation paths rather than another controller rewrite.

Because the rig has no articulated fingers, `point` is intentionally a whole-arm indication. A future finger-rigged asset can refine the endpoint without changing the behaviour API.

Final semantic-action reel:

- `Limijoy semantic actions` run #3
- https://github.com/Coolkama/Orchid/actions/runs/31781898771

Measured across every authored action key:

- maximum hand-target error: `< 2.7e-5` model units
- maximum palm angular error: `0°` at report precision
- right reach and left point required no reach-envelope clamping
- no baked-walk source or leg control was edited

The action data remains authored at 24 fps. CI samples the review reel at 12 fps to reduce render time without changing controller timing.

### Walk policy

The substantially complete baked walk remains authoritative. Procedural walking arm swing is an **optional arm-only overlay/fallback**. Procedural feet remain disabled until dynamic terrain or precise grounding requires them.

Leaves and other secondary parts should use spring/secondary-motion controls rather than IK. Facial expressions and blinking should use semantic face states rather than the skeletal arm controller.

## Android runtime integration checkpoint

Product integration is now active in `Coolkama/Limijoy` on branch
`glimmerkin-runtime-rendering` (draft PR #14).

Completed in the Android app:

1. `glimmerkin.glb` renders through SceneView in both the full activity and the draggable mini overlay;
2. both modes consume one shared `PetRuntime` state and presentation;
3. on-device framing and transparency passed for both modes;
4. the mini character overlapping the activity is intentional user placement, not a layout defect;
5. the first live skeletal slice ports Orchid's bounded gaze distribution to torso `Bone_015`, neck `Bone_034`, and head `Bone_033` for `PetMotionIntent.LookAround`;
6. full and mini renderers use the same frame clock so the semantic gaze remains in phase;
7. Android Build #98 passed unit tests and APK packaging at commit `10e48cf`:
   https://github.com/Coolkama/Limijoy/actions/runs/31791231075

The gaze unit suite verifies Orchid's exact yaw/pitch/body-follow limits and curiosity-energy scaling. The next immediate gate is on-device visual acceptance of build #98 while the debug summary reads `Behaviour: Observe` and `Motion: LookAround`.

After that device gate, continue the runtime port in increasing complexity:

1. semantic wave using the bilateral arm controls;
2. live reach/point using two-bone IK, elbow pole, palm-frame quaternion, live shoulder position, and reach-envelope clamping;
3. remaining play/carry/push and whole-body coordination;
4. semantic face states/blinking and spring motion for leaves;
5. deepen the local personality/state-to-intent layer before adding any optional AI behaviour selection.

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
- Face work now belongs to the upcoming personality phase, after the model is visibly running in the app.

## Key diagnostic/action references

- Full arm cardinal diagnostic run #22:
  https://github.com/Coolkama/Orchid/actions/runs/31693545602
- Shoulder-only cardinal diagnostic run #21:
  https://github.com/Coolkama/Orchid/actions/runs/31680543823
- Latest target-based/reversed-palm reach run #25:
  https://github.com/Coolkama/Orchid/actions/runs/31728651128
- Semantic palm orientation sheet run #1:
  https://github.com/Coolkama/Orchid/actions/runs/31775846079
- Semantic inward-palm reach run #27:
  https://github.com/Coolkama/Orchid/actions/runs/31775846065
- Final bilateral parity run #3:
  https://github.com/Coolkama/Orchid/actions/runs/31781898747
- Final semantic-action reel run #3:
  https://github.com/Coolkama/Orchid/actions/runs/31781898771

Important commits from this phase:

- `39bc1cee` — automatic all-descendant arm cardinal diagnostics
- `234f45f2` — created `docs/LIMIJOY_RIG_MAP.md`
- `485169d3` — new target-based semantic reach script
- `e1c0da66` — reach workflow switched to target-based script
- `4a5c08d6` — attempted palm direction correction
- `1fc3e5cc` — workflow workaround to reverse palm-roll signs at render time
- `10de5ff7` — reusable hand/elbow/palm semantic controller and one-run orientation sheet
- `8deefd5` — bilateral calibration, bounded gaze/body controls, and reusable action paths
- `a21cd27` — restrained gaze/carry presentation and faster CI review sampling
- `0b4c8d2` — shoulder-relative reach/point targets

## Working method going forward

- Prefer systematic calibration over repeated guesses.
- Prefer semantic/world-space controls over raw local Euler controls.
- Use GitHub Actions artifacts for visual verification.
- When a render completes, provide the direct GitHub Actions run URL.
- Do not claim a render is ready until workflow status is checked.
- Avoid rebuilding knowledge that is already recorded in `docs/LIMIJOY_RIG_MAP.md` and this handoff.
- Bilateral parity, head/torso coordination, and the initial semantic action catalogue are verified in Orchid. Full/mini in-app rendering and the first personality-driven gaze slice are implemented; the next success criterion is on-device visual acceptance of `LookAround`, followed by the bilateral arm runtime port.
