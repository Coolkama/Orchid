"""Reusable semantic action paths for Limijoy.

This is the behaviour-facing layer above the calibrated Meshy rig.  New object
interactions are expressed as paths of hand targets, palm modes, elbow modes,
gaze targets, and restrained body follow-through.  That same path abstraction
can later describe picking up a stick, carrying food, moving a branch, or a play
gesture without adding another bone-specific controller.

Walking remains a baked locomotion clip by default.  The procedural arm-swing
path in this module is an optional overlay/fallback and never edits leg bones.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Sequence, Tuple

import bpy
from mathutils import Vector

from limijoy_arm_semantic_controls import (
    ELBOW_MODES,
    PALM_MODES,
    LimijoyArmSemanticControls,
    ReachResult,
)
from limijoy_body_semantic_controls import (
    LimijoyBodySemanticControls,
    LookResult,
)


SIDES: Tuple[str, ...] = ("left", "right")

WALK_POLICY = {
    "locomotion_source": "baked_walk",
    "procedural_arm_swing": "optional_overlay_or_fallback",
    "procedural_feet": "disabled_until_dynamic_grounding_is_required",
}


@dataclass(frozen=True)
class ArmIntent:
    """One arm's semantic target at an action keyframe."""

    side: str
    position: Tuple[float, float, float]
    palm_mode: str = "inward"
    elbow_mode: str = "outward"

    def __post_init__(self) -> None:
        if self.side not in SIDES:
            raise ValueError(f"side must be one of {SIDES}")
        if self.palm_mode not in PALM_MODES:
            raise ValueError(f"palm_mode must be one of {PALM_MODES}")
        if self.elbow_mode not in ELBOW_MODES:
            raise ValueError(f"elbow_mode must be one of {ELBOW_MODES}")


@dataclass(frozen=True)
class PoseIntent:
    """A complete semantic whole-body intent at one frame."""

    frame: int
    arms: Tuple[ArmIntent, ...] = ()
    look_target: Optional[Tuple[float, float, float]] = None
    gaze_strength: float = 1.0
    body_follow: float = 1.0
    forward_lean_degrees: float = 0.0

    def __post_init__(self) -> None:
        sides = [arm.side for arm in self.arms]
        if len(sides) != len(set(sides)):
            raise ValueError("A PoseIntent may contain at most one intent per arm")


@dataclass(frozen=True)
class AppliedArmResult:
    side: str
    requested_target: Tuple[float, float, float]
    applied_target: Tuple[float, float, float]
    target_was_clamped: bool
    reach: ReachResult


@dataclass(frozen=True)
class PoseApplication:
    frame: int
    arms: Tuple[AppliedArmResult, ...]
    look: Optional[LookResult]


@dataclass(frozen=True)
class SemanticClip:
    name: str
    frame_start: int
    frame_end: int
    peak_frames: Tuple[int, ...]
    applications: Tuple[PoseApplication, ...]
    notes: Tuple[str, ...] = ()


def _tuple(vector: Iterable[float] | Vector) -> Tuple[float, float, float]:
    value = Vector(vector)
    return (value.x, value.y, value.z)


class LimijoySemanticActions:
    """Compose calibrated arms and bounded body controls into named actions."""

    def __init__(
        self,
        armature: bpy.types.Object,
        *,
        control_size: float = 0.05,
    ) -> None:
        self.armature = armature
        self.scene = bpy.context.scene
        self.body = LimijoyBodySemanticControls(armature)
        self.arms: Dict[str, LimijoyArmSemanticControls] = {
            side: LimijoyArmSemanticControls(
                armature,
                side=side,
                control_size=control_size,
            )
            for side in SIDES
        }
        self.reference_shoulders = {
            side: controller.rest_shoulder.copy()
            for side, controller in self.arms.items()
        }
        self.reference_hands = {
            side: controller.rest_hand_target.copy()
            for side, controller in self.arms.items()
        }
        self.reference_chain_length = sum(
            controller.chain_length for controller in self.arms.values()
        ) / len(self.arms)
        self.clips: list[SemanticClip] = []

    def character_direction(self, direction: Iterable[float] | Vector) -> Vector:
        result = self.armature.matrix_world.to_quaternion() @ Vector(direction).normalized()
        return result.normalized()

    @property
    def right(self) -> Vector:
        return self.character_direction((1.0, 0.0, 0.0))

    @property
    def forward(self) -> Vector:
        return self.character_direction((0.0, -1.0, 0.0))

    @property
    def up(self) -> Vector:
        return self.character_direction((0.0, 0.0, 1.0))

    def shoulder_centre(self) -> Vector:
        return self.reference_shoulders["left"].lerp(
            self.reference_shoulders["right"],
            0.5,
        )

    def choose_side(self, target: Iterable[float] | Vector) -> str:
        """Choose the nearer side without exposing a rig or coordinate sign."""

        offset = Vector(target) - self.shoulder_centre()
        return "right" if offset.dot(self.right) >= 0.0 else "left"

    def neutral(self, frame: int) -> None:
        """Key a neutral semantic boundary while leaving leg animation untouched."""

        self.scene.frame_set(frame)
        self.body.reset_pose(frame=frame)
        for controller in self.arms.values():
            controller.release(frame=frame)

    def apply_pose(self, intent: PoseIntent) -> PoseApplication:
        """Resolve and key one general semantic pose intent."""

        self.scene.frame_set(intent.frame)
        look_result = None
        if intent.look_target is None:
            self.body.reset_pose(frame=intent.frame)
        else:
            look_result = self.body.look_at(
                intent.look_target,
                strength=intent.gaze_strength,
                body_follow=intent.body_follow,
                forward_lean_degrees=intent.forward_lean_degrees,
                frame=intent.frame,
            )

        intents_by_side = {arm.side: arm for arm in intent.arms}
        arm_results = []
        for side, controller in self.arms.items():
            arm_intent = intents_by_side.get(side)
            if arm_intent is None:
                controller.release(frame=intent.frame)
                continue

            requested = Vector(arm_intent.position)
            applied = controller.clamp_target(requested)
            reach = controller.reach_to(
                applied,
                palm_mode=arm_intent.palm_mode,
                elbow_mode=arm_intent.elbow_mode,
                frame=intent.frame,
            )
            arm_results.append(
                AppliedArmResult(
                    side=side,
                    requested_target=_tuple(requested),
                    applied_target=_tuple(applied),
                    target_was_clamped=(requested - applied).length > 1.0e-8,
                    reach=reach,
                )
            )

        return PoseApplication(
            frame=intent.frame,
            arms=tuple(arm_results),
            look=look_result,
        )

    def animate_path(
        self,
        name: str,
        poses: Sequence[PoseIntent],
        *,
        neutral_start: Optional[int] = None,
        neutral_end: Optional[int] = None,
        peak_frames: Sequence[int] = (),
        notes: Sequence[str] = (),
    ) -> SemanticClip:
        """Key a reusable semantic path—the extension point for future actions."""

        if not poses:
            raise ValueError("poses must contain at least one PoseIntent")
        ordered = tuple(sorted(poses, key=lambda pose: pose.frame))
        if len({pose.frame for pose in ordered}) != len(ordered):
            raise ValueError("poses must use unique frame numbers")

        if neutral_start is not None:
            self.neutral(neutral_start)
        applications = tuple(self.apply_pose(pose) for pose in ordered)
        if neutral_end is not None:
            self.neutral(neutral_end)

        frame_start = min(
            [pose.frame for pose in ordered]
            + ([] if neutral_start is None else [neutral_start])
        )
        frame_end = max(
            [pose.frame for pose in ordered]
            + ([] if neutral_end is None else [neutral_end])
        )
        clip = SemanticClip(
            name=name,
            frame_start=frame_start,
            frame_end=frame_end,
            peak_frames=tuple(peak_frames),
            applications=applications,
            notes=tuple(notes),
        )
        self.clips.append(clip)
        return clip

    def reach_for(
        self,
        target: Iterable[float] | Vector,
        *,
        side: str = "auto",
        start_frame: int = 1,
        palm_mode: str = "inward",
        elbow_mode: str = "outward",
    ) -> SemanticClip:
        """Reach with gaze, a small torso turn, and a restrained forward lean."""

        target_vector = Vector(target)
        resolved_side = self.choose_side(target_vector) if side == "auto" else side
        if resolved_side not in SIDES:
            raise ValueError(f"side must be 'auto' or one of {SIDES}")
        rest = self.reference_hands[resolved_side]
        poses = (
            PoseIntent(
                frame=start_frame + 8,
                arms=(
                    ArmIntent(
                        resolved_side,
                        _tuple(rest.lerp(target_vector, 0.25)),
                        palm_mode,
                        elbow_mode,
                    ),
                ),
                look_target=_tuple(target_vector),
                gaze_strength=0.16,
                body_follow=0.25,
                forward_lean_degrees=0.5,
            ),
            PoseIntent(
                frame=start_frame + 24,
                arms=(ArmIntent(resolved_side, _tuple(target_vector), palm_mode, elbow_mode),),
                look_target=_tuple(target_vector),
                gaze_strength=0.27,
                body_follow=0.55,
                forward_lean_degrees=1.4,
            ),
            PoseIntent(
                frame=start_frame + 34,
                arms=(ArmIntent(resolved_side, _tuple(target_vector), palm_mode, elbow_mode),),
                look_target=_tuple(target_vector),
                gaze_strength=0.32,
                body_follow=0.65,
                forward_lean_degrees=1.6,
            ),
        )
        return self.animate_path(
            f"reach_for_{resolved_side}",
            poses,
            neutral_start=start_frame,
            neutral_end=start_frame + 48,
            peak_frames=(start_frame + 34,),
            notes=("Dynamic target action; solve at runtime rather than baking a fixed endpoint.",),
        )

    def point(
        self,
        target: Iterable[float] | Vector,
        *,
        side: str = "auto",
        start_frame: int = 1,
    ) -> SemanticClip:
        """Indicate a target with the whole arm (the current rig has no finger bones)."""

        target_vector = Vector(target)
        resolved_side = self.choose_side(target_vector) if side == "auto" else side
        if resolved_side not in SIDES:
            raise ValueError(f"side must be 'auto' or one of {SIDES}")
        rest = self.reference_hands[resolved_side]
        poses = (
            PoseIntent(
                frame=start_frame + 8,
                arms=(
                    ArmIntent(
                        resolved_side,
                        _tuple(rest.lerp(target_vector, 0.38)),
                        "down",
                        "outward",
                    ),
                ),
                look_target=_tuple(target_vector),
                gaze_strength=0.16,
                body_follow=0.25,
            ),
            PoseIntent(
                frame=start_frame + 20,
                arms=(ArmIntent(resolved_side, _tuple(target_vector), "down", "outward"),),
                look_target=_tuple(target_vector),
                gaze_strength=0.30,
                body_follow=0.60,
                forward_lean_degrees=0.8,
            ),
            PoseIntent(
                frame=start_frame + 29,
                arms=(ArmIntent(resolved_side, _tuple(target_vector), "down", "outward"),),
                look_target=_tuple(target_vector),
                gaze_strength=0.30,
                body_follow=0.60,
                forward_lean_degrees=0.8,
            ),
        )
        return self.animate_path(
            f"point_{resolved_side}",
            poses,
            neutral_start=start_frame,
            neutral_end=start_frame + 40,
            peak_frames=(start_frame + 29,),
            notes=("Whole-arm point until a future asset supplies articulated fingers.",),
        )

    def wave(self, *, side: str = "right", start_frame: int = 1) -> SemanticClip:
        """Raise one open palm and wave from target-space arcs near the head."""

        if side not in SIDES:
            raise ValueError(f"side must be one of {SIDES}")
        controller = self.arms[side]
        sign = controller.side_sign
        length = controller.chain_length
        shoulder = self.reference_shoulders[side]

        def wave_target(outward: float, height: float) -> Vector:
            return (
                shoulder
                + self.right * (sign * length * outward)
                + self.forward * (length * 0.30)
                + self.up * (length * height)
            )

        targets = (
            (start_frame + 10, wave_target(0.32, 0.46), 0.25),
            (start_frame + 20, wave_target(0.20, 0.56), 0.35),
            (start_frame + 29, wave_target(0.40, 0.48), 0.35),
            (start_frame + 38, wave_target(0.20, 0.56), 0.35),
            (start_frame + 47, wave_target(0.40, 0.48), 0.35),
        )
        poses = tuple(
            PoseIntent(
                frame=frame,
                arms=(ArmIntent(side, _tuple(position), "forward", "outward"),),
                look_target=_tuple(position),
                gaze_strength=gaze,
                body_follow=0.20,
            )
            for frame, position, gaze in targets
        )
        return self.animate_path(
            f"wave_{side}",
            poses,
            neutral_start=start_frame,
            neutral_end=start_frame + 58,
            peak_frames=(start_frame + 29, start_frame + 47),
            notes=("Fixed greeting candidate; may be baked after visual approval.",),
        )

    def carry(
        self,
        centre: Optional[Iterable[float] | Vector] = None,
        *,
        start_frame: int = 1,
    ) -> SemanticClip:
        """Cup both hands beneath a shared object-space carry point."""

        length = self.reference_chain_length
        carry_centre = Vector(centre) if centre is not None else (
            self.shoulder_centre()
            + self.forward * (length * 0.62)
            - self.up * (length * 0.42)
        )
        separation = self.right * (length * 0.17)
        targets = {
            "left": carry_centre - separation,
            "right": carry_centre + separation,
        }

        def bilateral(amount: float) -> Tuple[ArmIntent, ...]:
            return tuple(
                ArmIntent(
                    side,
                    _tuple(self.reference_hands[side].lerp(targets[side], amount)),
                    "up",
                    "outward",
                )
                for side in SIDES
            )

        poses = (
            PoseIntent(
                frame=start_frame + 9,
                arms=bilateral(0.45),
                look_target=_tuple(carry_centre),
                gaze_strength=0.16,
                body_follow=0.20,
            ),
            PoseIntent(
                frame=start_frame + 22,
                arms=bilateral(1.0),
                look_target=_tuple(carry_centre),
                gaze_strength=0.24,
                body_follow=0.35,
                forward_lean_degrees=1.0,
            ),
            PoseIntent(
                frame=start_frame + 32,
                arms=bilateral(1.0),
                look_target=_tuple(carry_centre),
                gaze_strength=0.24,
                body_follow=0.35,
                forward_lean_degrees=1.0,
            ),
        )
        return self.animate_path(
            "carry",
            poses,
            neutral_start=start_frame,
            neutral_end=start_frame + 44,
            peak_frames=(start_frame + 32,),
            notes=("Shared object-space centre can later follow a held prop.",),
        )

    def push(
        self,
        centre: Optional[Iterable[float] | Vector] = None,
        *,
        start_frame: int = 1,
    ) -> SemanticClip:
        """Plant both forward-facing palms, then extend with modest body weight."""

        length = self.reference_chain_length
        push_centre = Vector(centre) if centre is not None else (
            self.shoulder_centre()
            + self.forward * (length * 0.82)
            - self.up * (length * 0.05)
        )
        tuck_centre = (
            self.shoulder_centre()
            + self.forward * (length * 0.43)
            - self.up * (length * 0.08)
        )
        separation = self.right * (length * 0.21)

        def bilateral(centre_point: Vector) -> Tuple[ArmIntent, ...]:
            return (
                ArmIntent("left", _tuple(centre_point - separation), "forward", "outward"),
                ArmIntent("right", _tuple(centre_point + separation), "forward", "outward"),
            )

        poses = (
            PoseIntent(
                frame=start_frame + 10,
                arms=bilateral(tuck_centre),
                look_target=_tuple(push_centre),
                gaze_strength=0.18,
                body_follow=0.45,
                forward_lean_degrees=0.8,
            ),
            PoseIntent(
                frame=start_frame + 24,
                arms=bilateral(push_centre),
                look_target=_tuple(push_centre),
                gaze_strength=0.28,
                body_follow=0.65,
                forward_lean_degrees=2.5,
            ),
            PoseIntent(
                frame=start_frame + 34,
                arms=bilateral(push_centre),
                look_target=_tuple(push_centre),
                gaze_strength=0.28,
                body_follow=0.65,
                forward_lean_degrees=2.5,
            ),
        )
        return self.animate_path(
            "push",
            poses,
            neutral_start=start_frame,
            neutral_end=start_frame + 46,
            peak_frames=(start_frame + 34,),
            notes=("Bilateral palm action; no foot or baked-walk tracks are replaced.",),
        )

    def walking_arm_swing(
        self,
        *,
        start_frame: int = 1,
        amplitude: float = 0.14,
        release_at_end: bool = False,
    ) -> SemanticClip:
        """Build one optional, loopable arm-only overlay for the baked walk."""

        if not 0.0 <= amplitude <= 0.25:
            raise ValueError("amplitude must be between zero and 0.25")
        length = self.reference_chain_length

        def swing_intents(phase: float) -> Tuple[ArmIntent, ...]:
            return tuple(
                ArmIntent(
                    side,
                    _tuple(
                        self.reference_shoulders[side].lerp(
                            self.reference_hands[side],
                            0.90,
                        )
                        + self.forward
                        * (length * amplitude * phase * (1.0 if side == "left" else -1.0))
                        + self.up * (length * 0.015)
                    ),
                    "inward",
                    "outward",
                )
                for side in SIDES
            )

        phases = ((0, 1.0), (6, 0.0), (12, -1.0), (18, 0.0), (24, 1.0))
        poses = tuple(
            PoseIntent(frame=start_frame + offset, arms=swing_intents(phase))
            for offset, phase in phases
        )
        return self.animate_path(
            "walking_arm_swing_optional_overlay",
            poses,
            neutral_end=start_frame + 28 if release_at_end else None,
            peak_frames=(start_frame, start_frame + 12, start_frame + 24),
            notes=(
                "Baked walk remains authoritative.",
                "This loop touches arms only and is opt-in for blending or fallback use.",
            ),
        )

    def set_smooth_interpolation(self) -> None:
        """Use smooth curves for authored previews while leaving action intent unchanged."""

        animated_objects = [self.armature]
        for controller in self.arms.values():
            animated_objects.extend(
                (controller.hand_target, controller.elbow_pole, controller.palm_target)
            )
        for obj in animated_objects:
            action = obj.animation_data.action if obj.animation_data else None
            if action is None:
                continue
            for curve in action.fcurves:
                for point in curve.keyframe_points:
                    point.interpolation = "BEZIER"


__all__ = [
    "ArmIntent",
    "AppliedArmResult",
    "LimijoySemanticActions",
    "PoseApplication",
    "PoseIntent",
    "SemanticClip",
    "SIDES",
    "WALK_POLICY",
]
