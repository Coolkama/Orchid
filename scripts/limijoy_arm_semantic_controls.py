"""World-space semantic controls for Limijoy's Meshy arm rig.

The public API deliberately avoids Meshy bone names and Euler angles.  A caller
provides a hand position, an elbow mode, and a palm mode; this module converts
those semantic values into the current rig's IK target, pole target, and wrist
quaternion.

Blender is the calibration host for now, but the maths is intentionally limited
to vectors, projections, orthonormal bases, and quaternions so the same control
model can later be ported to Limijoy's runtime renderer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Tuple

import bpy
from mathutils import Matrix, Quaternion, Vector


PALM_MODES: Tuple[str, ...] = (
    "inward",
    "outward",
    "up",
    "down",
    "forward",
    "backward",
)

ELBOW_MODES: Tuple[str, ...] = (
    "outward",
    "neutral",
    "inward",
)


RIGHT_ARM_BONES: Dict[str, str] = {
    "girdle": "Bone_023",
    "upper": "Bone_022",
    "elbow": "Bone_021",
    "wrist": "Bone_020",
    "hand": "Bone_019",
}

LEFT_ARM_BONES: Dict[str, str] = {
    "girdle": "Bone_031",
    "upper": "Bone_030",
    "elbow": "Bone_029",
    "wrist": "Bone_028",
    "hand": "Bone_027",
}


@dataclass(frozen=True)
class ReachResult:
    """Measured result of one semantic reach operation."""

    palm_mode: str
    elbow_mode: str
    target: Tuple[float, float, float]
    achieved_hand_anchor: Tuple[float, float, float]
    palm_direction: Tuple[float, float, float]
    hand_forward: Tuple[float, float, float]
    target_error: float
    palm_error_degrees: float


def _normalised(value: Iterable[float] | Vector, label: str) -> Vector:
    vector = Vector(value)
    if vector.length_squared < 1.0e-12:
        raise ValueError(f"{label} must not be a zero-length vector")
    return vector.normalized()


def _project_onto_plane(value: Vector, plane_normal: Vector) -> Vector:
    return value - plane_normal * value.dot(plane_normal)


def _first_valid_projection(
    candidates: Iterable[Vector],
    plane_normal: Vector,
    label: str,
) -> Vector:
    for candidate in candidates:
        projected = _project_onto_plane(candidate, plane_normal)
        if projected.length_squared >= 1.0e-10:
            return projected.normalized()
    raise ValueError(f"Could not find a usable {label} perpendicular to {plane_normal}")


def _basis_matrix(axis_x: Vector, axis_y: Vector) -> Matrix:
    """Return a right-handed basis whose first two columns are the given axes."""

    x_axis = _normalised(axis_x, "basis X axis")
    y_axis = _normalised(_project_onto_plane(axis_y, x_axis), "basis Y axis")
    z_axis = _normalised(x_axis.cross(y_axis), "basis Z axis")
    return Matrix((x_axis, y_axis, z_axis)).transposed()


def orientation_quaternion(
    local_palm: Vector,
    local_forward: Vector,
    world_palm: Vector,
    world_forward: Vector,
) -> Quaternion:
    """Map a local palm/forward frame onto a world palm/forward frame.

    This is the portable core of the palm controller.  It does not use a Meshy
    Euler sign or a Blender constraint; it constructs two orthonormal frames and
    returns the quaternion that rotates one frame onto the other.
    """

    local_basis = _basis_matrix(local_palm, local_forward)
    world_basis = _basis_matrix(world_palm, world_forward)
    quaternion = (world_basis @ local_basis.transposed()).to_quaternion()
    quaternion.normalize()
    return quaternion


class LimijoyArmSemanticControls:
    """IK hand placement plus quaternion palm orientation for one Limijoy arm."""

    def __init__(
        self,
        armature: bpy.types.Object,
        *,
        side: str = "right",
        control_size: float = 0.05,
    ) -> None:
        if armature.type != "ARMATURE":
            raise TypeError("armature must be a Blender ARMATURE object")
        if side not in {"right", "left"}:
            raise ValueError("side must be 'right' or 'left'")

        self.armature = armature
        self.scene = bpy.context.scene
        self.side = side
        self.side_sign = 1.0 if side == "right" else -1.0
        self.bones = RIGHT_ARM_BONES if side == "right" else LEFT_ARM_BONES

        missing = [name for name in self.bones.values() if name not in armature.pose.bones]
        if missing:
            raise KeyError(f"Limijoy {side} arm bones missing from rig: {missing}")

        self.girdle = armature.pose.bones[self.bones["girdle"]]
        self.upper = armature.pose.bones[self.bones["upper"]]
        self.elbow = armature.pose.bones[self.bones["elbow"]]
        self.wrist = armature.pose.bones[self.bones["wrist"]]
        self.hand = armature.pose.bones[self.bones["hand"]]

        for pose_bone in (self.girdle, self.upper, self.elbow, self.wrist, self.hand):
            pose_bone.rotation_mode = "QUATERNION"
            pose_bone.matrix_basis.identity()

        bpy.context.view_layer.update()

        self._rest_basis = {
            pose_bone.name: pose_bone.matrix_basis.copy()
            for pose_bone in (self.girdle, self.upper, self.elbow, self.wrist, self.hand)
        }
        self.rest_hand_target = self._bone_tail_world(self.elbow)
        self.rest_shoulder = self._bone_head_world(self.upper)
        self.chain_length = (
            self._bone_length_world(self.upper) + self._bone_length_world(self.elbow)
        )

        prefix = f"Limijoy_{side.capitalize()}"
        self.hand_target = self._new_empty(
            f"{prefix}_HandTarget",
            self.rest_hand_target,
            control_size,
            "SPHERE",
        )
        self.elbow_pole = self._new_empty(
            f"{prefix}_ElbowPole",
            self.rest_shoulder,
            control_size,
            "PLAIN_AXES",
        )
        self.palm_target = self._new_empty(
            f"{prefix}_PalmTarget",
            self.rest_hand_target,
            control_size * 1.35,
            "ARROWS",
        )
        self.palm_target.rotation_mode = "QUATERNION"

        old_constraint = self.elbow.constraints.get("SemanticReachIK")
        if old_constraint is not None:
            self.elbow.constraints.remove(old_constraint)
        self.ik = self.elbow.constraints.new("IK")
        self.ik.name = "SemanticReachIK"
        self.ik.target = self.hand_target
        self.ik.pole_target = self.elbow_pole
        self.ik.chain_count = 2
        self.ik.use_tail = True
        self.ik.iterations = 64
        self.ik.influence = 0.0

        # Bone-local +Y follows the Bone_020 -> Bone_019 chain and is therefore
        # the portable hand/finger-forward reference axis.
        self.hand_forward_local = Vector((0.0, 1.0, 0.0))

        # The neutral character pose is authored with each palm facing the body.
        # Convert that semantic inward direction into this particular wrist's
        # neutral local frame once.  The projection removes any component along
        # the hand-forward axis, leaving a stable palm-normal reference without
        # baking a Meshy Euler sign into the controller.
        wrist_world_rotation = self._pose_bone_world_rotation(self.wrist)
        inward_world = Vector((-self.side_sign, 0.0, 0.0))
        inward_local = wrist_world_rotation.inverted() @ inward_world
        self.palm_normal_local = _first_valid_projection(
            (inward_local, Vector((1.0, 0.0, 0.0)), Vector((0.0, 0.0, 1.0))),
            self.hand_forward_local,
            "neutral palm reference",
        )

        self.reset_pose()

    def _new_empty(
        self,
        name: str,
        location: Vector,
        size: float,
        display_type: str,
    ) -> bpy.types.Object:
        existing = bpy.data.objects.get(name)
        if existing is not None:
            bpy.data.objects.remove(existing, do_unlink=True)
        bpy.ops.object.empty_add(type=display_type, location=location)
        empty = bpy.context.object
        empty.name = name
        empty.empty_display_size = size
        return empty

    def _pose_bone_world_rotation(self, pose_bone: bpy.types.PoseBone) -> Quaternion:
        armature_rotation = self.armature.matrix_world.to_quaternion()
        result = armature_rotation @ pose_bone.matrix.to_quaternion()
        result.normalize()
        return result

    def _bone_head_world(self, pose_bone: bpy.types.PoseBone) -> Vector:
        return self.armature.matrix_world @ pose_bone.head

    def _bone_tail_world(self, pose_bone: bpy.types.PoseBone) -> Vector:
        return self.armature.matrix_world @ pose_bone.tail

    def _bone_length_world(self, pose_bone: bpy.types.PoseBone) -> float:
        return (self._bone_tail_world(pose_bone) - self._bone_head_world(pose_bone)).length

    def palm_direction_for_mode(self, mode: str) -> Vector:
        if mode not in PALM_MODES:
            raise ValueError(f"Unsupported palm mode {mode!r}; expected one of {PALM_MODES}")
        return {
            "inward": Vector((-self.side_sign, 0.0, 0.0)),
            "outward": Vector((self.side_sign, 0.0, 0.0)),
            "up": Vector((0.0, 0.0, 1.0)),
            "down": Vector((0.0, 0.0, -1.0)),
            "forward": Vector((0.0, -1.0, 0.0)),
            "backward": Vector((0.0, 1.0, 0.0)),
        }[mode]

    def elbow_direction_for_mode(self, mode: str) -> Vector:
        if mode not in ELBOW_MODES:
            raise ValueError(f"Unsupported elbow mode {mode!r}; expected one of {ELBOW_MODES}")
        return {
            "outward": Vector((self.side_sign, 0.0, 0.0)),
            "neutral": Vector((0.0, 0.0, -1.0)),
            "inward": Vector((-self.side_sign, 0.0, 0.0)),
        }[mode]

    def _pole_position(self, hand_position: Vector, elbow_mode: str) -> Vector:
        reach_axis = _normalised(hand_position - self.rest_shoulder, "reach direction")
        requested = self.elbow_direction_for_mode(elbow_mode)
        pole_direction = _first_valid_projection(
            (
                requested,
                Vector((0.0, 0.0, -1.0)),
                Vector((self.side_sign, 0.0, 0.0)),
                Vector((0.0, 1.0, 0.0)),
            ),
            reach_axis,
            "elbow pole direction",
        )
        midpoint = self.rest_shoulder.lerp(hand_position, 0.45)
        return midpoint + pole_direction * self.chain_length * 0.8

    def _desired_hand_forward(self, palm_direction: Vector, hand_position: Vector) -> Vector:
        current_rotation = self._pose_bone_world_rotation(self.wrist)
        current_forward = current_rotation @ self.hand_forward_local
        reach_direction = hand_position - self.rest_shoulder

        # Preserve the current/reach-aligned hand direction where possible.
        # When the palm points along the reach axis (forward/backward), use world
        # up as the natural "stop gesture" fallback so the frame is never singular.
        return _first_valid_projection(
            (
                current_forward,
                reach_direction,
                Vector((0.0, 0.0, 1.0)),
                Vector((-self.side_sign, 0.0, 0.0)),
                Vector((0.0, 1.0, 0.0)),
            ),
            palm_direction,
            "hand-forward direction",
        )

    def _apply_palm_orientation(
        self,
        palm_direction: Vector,
        hand_position: Vector,
    ) -> Tuple[Vector, Vector, float]:
        desired_palm = _normalised(palm_direction, "palm direction")
        desired_forward = self._desired_hand_forward(desired_palm, hand_position)
        desired_world_rotation = orientation_quaternion(
            self.palm_normal_local,
            self.hand_forward_local,
            desired_palm,
            desired_forward,
        )

        armature_world_rotation = self.armature.matrix_world.to_quaternion()
        desired_armature_rotation = armature_world_rotation.inverted() @ desired_world_rotation
        desired_matrix = desired_armature_rotation.to_matrix().to_4x4()
        desired_matrix.translation = self.wrist.head.copy()
        self.wrist.matrix = desired_matrix
        bpy.context.view_layer.update()

        self.palm_target.location = self._bone_head_world(self.wrist)
        self.palm_target.rotation_quaternion = desired_world_rotation

        actual_rotation = self._pose_bone_world_rotation(self.wrist)
        actual_palm = (actual_rotation @ self.palm_normal_local).normalized()
        actual_forward = (actual_rotation @ self.hand_forward_local).normalized()
        dot = max(-1.0, min(1.0, actual_palm.dot(desired_palm)))
        error_degrees = math.degrees(math.acos(dot))
        return actual_palm, actual_forward, error_degrees

    def reset_pose(self) -> None:
        """Restore the controlled arm to its imported neutral pose."""

        self.ik.influence = 0.0
        for pose_bone in (self.girdle, self.upper, self.elbow, self.wrist, self.hand):
            pose_bone.matrix_basis = self._rest_basis[pose_bone.name].copy()
        self.hand_target.location = self.rest_hand_target
        self.elbow_pole.location = self.rest_shoulder
        self.palm_target.location = self.rest_hand_target
        self.palm_target.rotation_quaternion = Quaternion()
        bpy.context.view_layer.update()

    def reach_to(
        self,
        position: Iterable[float] | Vector,
        *,
        palm_mode: str = "inward",
        elbow_mode: str = "outward",
        frame: Optional[int] = None,
    ) -> ReachResult:
        """Place the hand anchor and orient the palm using semantic world modes."""

        if palm_mode not in PALM_MODES:
            raise ValueError(f"Unsupported palm mode {palm_mode!r}; expected one of {PALM_MODES}")
        if elbow_mode not in ELBOW_MODES:
            raise ValueError(f"Unsupported elbow mode {elbow_mode!r}; expected one of {ELBOW_MODES}")
        if frame is not None:
            self.scene.frame_set(frame)

        hand_position = Vector(position)
        self.wrist.matrix_basis = self._rest_basis[self.wrist.name].copy()
        self.hand.matrix_basis = self._rest_basis[self.hand.name].copy()
        self.hand_target.location = hand_position
        self.elbow_pole.location = self._pole_position(hand_position, elbow_mode)
        self.ik.influence = 1.0
        bpy.context.view_layer.update()

        actual_palm, actual_forward, palm_error = self._apply_palm_orientation(
            self.palm_direction_for_mode(palm_mode),
            hand_position,
        )

        if frame is not None:
            self.hand_target.keyframe_insert("location", frame=frame)
            self.elbow_pole.keyframe_insert("location", frame=frame)
            self.wrist.keyframe_insert("rotation_quaternion", frame=frame)
            self.palm_target.keyframe_insert("location", frame=frame)
            self.palm_target.keyframe_insert("rotation_quaternion", frame=frame)
            self.ik.keyframe_insert("influence", frame=frame)

        achieved = self._bone_head_world(self.wrist)
        return ReachResult(
            palm_mode=palm_mode,
            elbow_mode=elbow_mode,
            target=tuple(hand_position),
            achieved_hand_anchor=tuple(achieved),
            palm_direction=tuple(actual_palm),
            hand_forward=tuple(actual_forward),
            target_error=(achieved - hand_position).length,
            palm_error_degrees=palm_error,
        )


__all__ = [
    "ELBOW_MODES",
    "PALM_MODES",
    "LimijoyArmSemanticControls",
    "ReachResult",
    "orientation_quaternion",
]
