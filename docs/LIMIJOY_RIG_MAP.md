# Limijoy rig map — arms and hands

This document records the empirically measured arm/hand rig controls for the current Meshy-generated Limijoy GLB. It exists so animation code does not have to rediscover bone behaviour by trial and error.

The map was produced with isolated cardinal tests: each bone was rotated alone by +90° and +180° around local X, Y and Z, with all other arm rotations reset to zero, then rendered from true front and true side in wireframe with the armature visible. The diagnostic also recorded pose-bone head/tail positions and descendant positions numerically.

## Coordinate convention

For the imported Blender model used by the diagnostics:

- world +X = Limijoy's right
- world -Y = Limijoy's forward
- world +Z = up

Important: animation rotations below are **bone-local Euler rotations**, not world rotations. Their visible effect depends on the bone's rest orientation and inherited parent transforms.

## Arm hierarchy

Right arm descendant chain discovered automatically from `Bone_023`:

`Bone_023 -> Bone_022 -> Bone_021 -> Bone_020 -> Bone_019 -> Bone_018 -> Bone_017 -> Bone_016`

Mirrored left chain previously identified:

`Bone_031 -> Bone_030 -> Bone_029 -> Bone_028 -> Bone_027 -> Bone_026 -> Bone_025 -> Bone_024`

No additional branches exist below `Bone_023`. In particular, the current Meshy rig has **no separately articulated finger bones** on this arm. The visible hand/finger shape is driven by the distal linear chain and skin weights rather than individual digit joints.

## Practical functional map

| Right | Left mirror | Practical role | Visible influence |
|---|---|---|---|
| `Bone_023` | `Bone_031` | shoulder/girdle/root orientation | very strong; reorients entire arm chain |
| `Bone_022` | `Bone_030` | main upper-arm / shoulder articulation | very strong |
| `Bone_021` | `Bone_029` | elbow / forearm articulation | strong |
| `Bone_020` | `Bone_028` | distal forearm / wrist shaping | moderate-small |
| `Bone_019` | `Bone_027` | wrist/hand shaping | small but visible |
| `Bone_018` | `Bone_026` | distal hand helper | very small |
| `Bone_017` | `Bone_025` | terminal helper | no meaningful visible deformation in cardinal tests |
| `Bone_016` | `Bone_024` | terminal/end helper | no meaningful visible deformation in cardinal tests |

The important consequence is that routine animation should normally be authored with `023/022/021`, optionally `020/019` for hand attitude, and should not depend on `017/016` for visible finger articulation.

## Bone_023 — shoulder/girdle root

Neutral direction approximately:

`(+0.979, 0.000, -0.203)`

So the bone is almost horizontal, pointing outward to Limijoy's right with a small downward component. It is **not** the 45°-down upper-arm pose that the rendered arm silhouette can suggest.

Measured cardinal directions:

| Rotation | Resulting direction | Interpretation |
|---|---|---|
| neutral | `( +0.979,  0.000, -0.203 )` | outward, slightly down |
| X +90 | `( +0.198, +0.203, +0.959 )` | mostly upward; also small depth/right component |
| X +180 | `( -0.979,  0.000, +0.203 )` | reversed across body |
| Y +90/+180 | effectively unchanged centreline | axial twist/roll of inherited frame |
| Z +90 | `( -0.041, +0.979, -0.198 )` | strong depth/horizontal swing |
| Z +180 | `( -0.979,  0.000, +0.203 )` | reversed across body |

Practical rule: `Bone_023` is a **girdle/frame control**, not the primary reach/elevation joint. Large rotations here rotate the coordinate frame inherited by the rest of the arm and can make compound poses difficult to reason about. Keep it modest unless deliberately repositioning the whole shoulder plane.

## Bone_022 — main upper arm

Neutral direction approximately:

`(-0.904, -0.231, -0.359)`

This explains the apparent downward/outward rest attitude of the visible arm: much of that orientation is introduced here, not by `Bone_023`.

Measured cardinal directions:

| Rotation | Resulting direction | Practical effect |
|---|---|---|
| neutral | `(-0.904, -0.231, -0.359)` | diagonal outward/down, with forward component |
| X +90 | `(+0.498, +0.735, +0.460)` | very large plane change; raises/repositions upper arm |
| X +180 | `(-0.678, 0.000, +0.735)` | inverted/upward orientation |
| Y +90/+180 | `(+0.678, 0.000, -0.735)` centreline result | predominantly long-axis/attitude roll; use cautiously |
| Z +90 | `(-0.540, +0.678, -0.498)` | strong secondary swing plane |
| Z +180 | `(-0.678, 0.000, +0.735)` | inverted/upward orientation |

Visual tests confirm this is the major limb-positioning bone. Earlier small-angle tests were misleading because several local rotations contain mixtures of world forward/up/side motion. Do not label a local axis simply as global 'forward' or 'up'. Use calibrated poses or target-based solving.

## Bone_021 — elbow / forearm

Neutral direction approximately:

`(-0.719, -0.005, +0.695)`

Cardinal directions:

| Rotation | Resulting direction | Practical effect |
|---|---|---|
| X +90 | `(+0.527, +0.734, +0.430)` | large elbow bend in one plane |
| X +180 | `(-0.677, +0.056, +0.734)` | folded/inverted endpoint |
| Y +90/+180 | `(+0.677, -0.056, -0.734)` centreline result | forearm/hand attitude roll; significant palm-orientation influence |
| Z +90 | `(-0.514, +0.677, -0.527)` | elbow bend in the secondary plane |
| Z +180 | `(-0.677, +0.056, +0.734)` | folded/inverted endpoint |

This is the main elbow/forearm control. Previous reach experiments established that large negative-X values can over-flex the arm and curl the hand back toward the torso; around the tested reach configuration, +10° X produced a straighter/further-forward distal chain than 0° or -10°.

## Bone_020 — distal forearm / wrist shaping

Neutral direction approximately:

`(-0.624, -0.096, +0.776)`

It produces visible but comparatively local changes. Its cardinal rotations move the distal chain without substantially repositioning the upper arm. Useful for finishing wrist/hand attitude after the reach has been established with `022/021`.

Cardinal directions:

- X +90: `(+0.462, +0.832, +0.308)`
- X +180: `(-0.555, 0.000, +0.832)`
- Y +90/+180: `(+0.555, 0.000, -0.832)`
- Z +90: `(-0.692, +0.555, -0.462)`
- Z +180: `(-0.555, 0.000, +0.832)`

## Bone_019 — wrist/hand helper

Neutral direction approximately:

`(-0.572, +0.051, +0.819)`

This gives a small but visible hand-region deformation and is suitable for subtle palm/hand finishing rather than gross arm placement.

Cardinal directions:

- X +90: `(+0.480, +0.800, +0.360)`
- X +180: `(-0.600, 0.000, +0.800)`
- Y +90/+180: `(+0.600, 0.000, -0.800)`
- Z +90: `(-0.640, +0.600, -0.480)`
- Z +180: `(-0.600, 0.000, +0.800)`

## Bone_018 — distal hand helper

Neutral direction approximately:

`(-0.574, -0.099, +0.813)`

The rig moves mathematically when this bone rotates, but visible skin deformation is very small in the diagnostic renders. Treat it as a fine correction/helper rather than a primary control.

Cardinal directions:

- X +90: `(+0.441, +0.857, +0.265)`
- X +180: `(-0.514, 0.000, +0.857)`
- Y +90/+180: `(+0.514, 0.000, -0.857)`
- Z +90: `(-0.735, +0.514, -0.441)`
- Z +180: `(-0.514, 0.000, +0.857)`

## Bone_017 and Bone_016 — terminal helpers

These form the final linear end of the chain. They have valid transforms, but the wireframe deformation comparison shows no meaningful visible skin movement from isolated cardinal rotations.

`Bone_017` neutral direction approximately `( +0.129, -0.196, +0.972 )`.

`Bone_016` neutral direction approximately `( 0.000, -0.447, +0.894 )`.

Both exhibit the same broad cardinal end directions:

- X +90 -> approximately `(0, +0.894, +0.447)`
- Y +90/+180 -> approximately `(0, +0.447, -0.894)`
- Z +90 -> approximately `(-1, 0, 0)`

Because these bones do not visibly articulate individual fingers, they should not be treated as finger joints.

## Animation guidance

1. **Pose from proximal to distal.** Establish the shoulder plane with `023`, gross upper-arm direction with `022`, then elbow/forearm with `021`; finish with `020/019` only as needed.
2. **Avoid large compound guesses.** A local Euler axis is not a global semantic axis. Large simultaneous values on `023` and `022` can rotate the inherited frame and create unintuitive arcs into the torso/head.
3. **Use cardinal calibration first.** For any new semantic control, establish neutral/90/180 behaviour in front and side views before interpolating fine angles.
4. **Use palm roll deliberately.** `021` Y is useful for changing hand attitude/palm presentation, but it should be added after gross reach direction is established.
5. **Do not expect finger animation from this model.** There are no separate finger branches. If independent finger gestures are required later, the asset must be re-rigged/augmented or replaced with a rig that includes digit bones.
6. **Mirror by structure, not blindly by sign.** The left chain mirrors the right numerically by bone role, but signs should be verified for any authored pose because mirrored local coordinate frames can differ.

## Current lesson for the reach problem

The main reason reaching took too long was treating small local-Euler changes as though they mapped directly to semantic world directions. The diagnostics show that the rest axes are already rotated and parent transforms alter descendant coordinate frames. Future animation work should therefore build a small library of calibrated semantic poses/controls (arm-down, horizontal-forward, overhead, palm-in, palm-forward, etc.) from these measured bones rather than repeatedly deriving them from raw Euler intuition.

Diagnostic source: GitHub Actions `Limijoy arm diagnostic` run #22, generated from commit `39bc1cee`.
