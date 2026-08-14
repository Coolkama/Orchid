"""Semantic gaze and restrained torso follow-through for Limijoy.

The behaviour layer supplies a world-space target and an optional forward lean.
This module converts that intent into bounded head, neck, and torso quaternions;
callers never need to know the Meshy bone names or local Euler axes.

The implementation deliberately uses the same portable ingredients as the arm
controller: vectors, clamped angles, and quaternions.  Blender hosts the current
calibration, while the control model is suitable for a later Kotlin renderer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Tuple

import bpy
from mathutils import Quaternion, Vector


BODY_BONES: Dict[str, str] = {
    "torso": "Bone_015",
    "neck": "Bone_034",
    "head": "Bone_033",
}


@dataclass(frozen=True)
class LookResult:
    """Resolved semantic gaze angles and their bounded body distribution."""

    target: Tuple[float, float, float]
    yaw_degrees: float
    pitch_degrees: float
    torso_yaw_degrees: float
    torso_lean_degrees: float
    neck_yaw_degrees: float
    neck_pitch_degrees: float
    head_yaw_degrees: float
    head_pitch_degrees: float
    yaw_was_clamped: bool
    pitch_was_clamped: bool


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


class LimijoyBodySemanticControls:
    """Bounded look-at behaviour shared by reach and future personality actions."""

    MAX_YAW_DEGREES = 35.0
    MAX_PITCH_DEGREES = 22.0
    MAX_FORWARD_LEAN_DEGREES = 5.0

    def __init__(self, armature: bpy.types.Object) -> None:
        if armature.type != "ARMATURE":
            raise TypeError("armature must be a Blender ARMATURE object")

        self.armature = armature
        self.scene = bpy.context.scene
        missing = [name for name in BODY_BONES.values() if name not in armature.pose.bones]
        if missing:
            raise KeyError(f"Limijoy body-control bones missing from rig: {missing}")

        self.torso = armature.pose.bones[BODY_BONES["torso"]]
        self.neck = armature.pose.bones[BODY_BONES["neck"]]
        self.head = armature.pose.bones[BODY_BONES["head"]]
        self.controlled_bones = (self.torso, self.neck, self.head)

        for pose_bone in self.controlled_bones:
            pose_bone.rotation_mode = "QUATERNION"
            pose_bone.matrix_basis.identity()
        bpy.context.view_layer.update()

        self._rest_basis = {
            pose_bone.name: pose_bone.matrix_basis.copy()
            for pose_bone in self.controlled_bones
        }

    def _character_axis(self, axis: Iterable[float] | Vector) -> Vector:
        result = self.armature.matrix_world.to_quaternion() @ Vector(axis).normalized()
        return result.normalized()

    def _bone_point_world(self, pose_bone: bpy.types.PoseBone, amount: float) -> Vector:
        point = pose_bone.head.lerp(pose_bone.tail, amount)
        return self.armature.matrix_world @ point

    def look_origin(self) -> Vector:
        """Return a stable point within the head from which gaze is measured."""

        return self._bone_point_world(self.head, 0.58)

    def _target_angles(self, target: Vector) -> Tuple[float, float]:
        world_direction = target - self.look_origin()
        if world_direction.length_squared < 1.0e-12:
            return 0.0, 0.0

        character_rotation = self.armature.matrix_world.to_quaternion()
        local_direction = character_rotation.inverted() @ world_direction.normalized()
        horizontal = math.hypot(local_direction.x, local_direction.y)
        yaw = math.degrees(math.atan2(local_direction.x, -local_direction.y))
        pitch = math.degrees(math.atan2(local_direction.z, horizontal))
        return yaw, pitch

    def _pose_bone_world_rotation(self, pose_bone: bpy.types.PoseBone) -> Quaternion:
        result = self.armature.matrix_world.to_quaternion() @ pose_bone.matrix.to_quaternion()
        result.normalize()
        return result

    def _apply_world_delta(
        self,
        pose_bone: bpy.types.PoseBone,
        *,
        yaw_degrees: float = 0.0,
        pitch_degrees: float = 0.0,
        roll_degrees: float = 0.0,
        forward_lean_degrees: float = 0.0,
    ) -> None:
        """Apply semantic yaw/pitch/roll around character-space world axes."""

        world_up = self._character_axis((0.0, 0.0, 1.0))
        world_right = self._character_axis((1.0, 0.0, 0.0))
        world_forward = self._character_axis((0.0, -1.0, 0.0))

        yaw = Quaternion(world_up, math.radians(yaw_degrees))
        # Looking up is a negative rotation around character right; leaning
        # forward is the opposite sign around the same axis.
        pitch_and_lean = Quaternion(
            world_right,
            math.radians(forward_lean_degrees - pitch_degrees),
        )
        # Positive semantic roll tilts the top of the head toward character right.
        roll = Quaternion(world_forward, math.radians(-roll_degrees))
        delta = yaw @ pitch_and_lean @ roll

        desired_world = delta @ self._pose_bone_world_rotation(pose_bone)
        desired_world.normalize()
        armature_rotation = self.armature.matrix_world.to_quaternion()
        desired_armature = armature_rotation.inverted() @ desired_world
        desired_matrix = desired_armature.to_matrix().to_4x4()
        desired_matrix.translation = pose_bone.head.copy()
        pose_bone.matrix = desired_matrix
        bpy.context.view_layer.update()

    def _key_controlled_bones(self, frame: int) -> None:
        for pose_bone in self.controlled_bones:
            pose_bone.keyframe_insert("rotation_quaternion", frame=frame)

    def reset_pose(self, frame: Optional[int] = None) -> None:
        """Restore inherited neutral without changing any baked leg animation."""

        if frame is not None:
            self.scene.frame_set(frame)
        for pose_bone in self.controlled_bones:
            pose_bone.matrix_basis = self._rest_basis[pose_bone.name].copy()
        bpy.context.view_layer.update()
        if frame is not None:
            self._key_controlled_bones(frame)

    def look_at(
        self,
        target: Iterable[float] | Vector,
        *,
        strength: float = 1.0,
        body_follow: float = 1.0,
        forward_lean_degrees: float = 0.0,
        frame: Optional[int] = None,
    ) -> LookResult:
        """Turn Limijoy toward a world target with restrained body follow-through."""

        if not 0.0 <= strength <= 1.0:
            raise ValueError("strength must be between zero and one")
        if not 0.0 <= body_follow <= 1.0:
            raise ValueError("body_follow must be between zero and one")
        if frame is not None:
            self.scene.frame_set(frame)

        target_vector = Vector(target)
        # Measure every target from neutral rather than from an interpolated pose
        # left over at this frame.  This keeps the semantic request absolute.
        self.reset_pose()
        requested_yaw, requested_pitch = self._target_angles(target_vector)
        scaled_yaw = requested_yaw * strength
        scaled_pitch = requested_pitch * strength
        yaw = _clamp(scaled_yaw, -self.MAX_YAW_DEGREES, self.MAX_YAW_DEGREES)
        pitch = _clamp(scaled_pitch, -self.MAX_PITCH_DEGREES, self.MAX_PITCH_DEGREES)
        lean = _clamp(
            forward_lean_degrees * body_follow,
            -self.MAX_FORWARD_LEAN_DEGREES,
            self.MAX_FORWARD_LEAN_DEGREES,
        )

        torso_yaw = _clamp(yaw * 0.18 * body_follow, -6.0, 6.0)
        neck_yaw = _clamp(yaw * 0.32, -12.0, 12.0)
        head_yaw = _clamp(yaw - torso_yaw - neck_yaw, -20.0, 20.0)
        neck_pitch = _clamp(pitch * 0.30, -7.0, 7.0)
        head_pitch = _clamp(pitch - neck_pitch, -15.0, 15.0)

        # Apply from the neutral state established above so poses do not drift.
        self._apply_world_delta(
            self.torso,
            yaw_degrees=torso_yaw,
            forward_lean_degrees=lean,
        )
        self._apply_world_delta(
            self.neck,
            yaw_degrees=neck_yaw,
            pitch_degrees=neck_pitch,
        )
        self._apply_world_delta(
            self.head,
            yaw_degrees=head_yaw,
            pitch_degrees=head_pitch,
        )
        if frame is not None:
            self._key_controlled_bones(frame)

        return LookResult(
            target=tuple(target_vector),
            yaw_degrees=yaw,
            pitch_degrees=pitch,
            torso_yaw_degrees=torso_yaw,
            torso_lean_degrees=lean,
            neck_yaw_degrees=neck_yaw,
            neck_pitch_degrees=neck_pitch,
            head_yaw_degrees=head_yaw,
            head_pitch_degrees=head_pitch,
            yaw_was_clamped=not math.isclose(yaw, scaled_yaw, abs_tol=1.0e-8),
            pitch_was_clamped=not math.isclose(pitch, scaled_pitch, abs_tol=1.0e-8),
        )


__all__ = [
    "BODY_BONES",
    "LimijoyBodySemanticControls",
    "LookResult",
]
