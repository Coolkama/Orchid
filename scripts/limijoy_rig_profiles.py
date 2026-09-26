"""Rig profiles for Limijoy Meshy generations.

Meshy can produce the same character with a different UniRig bone count and can
reuse Bone_### identifiers for completely different roles.  Limijoy behaviour
code therefore targets semantic roles and resolves the concrete generation by
both its semantic bone set and its expected joint count.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class LimijoyRigProfile:
    name: str
    bone_count: int
    body: Mapping[str, str]
    right_arm: Mapping[str, str]
    left_arm: Mapping[str, str]

    @property
    def required_bones(self) -> frozenset[str]:
        return frozenset(
            [
                *self.body.values(),
                *self.right_arm.values(),
                *self.left_arm.values(),
            ]
        )


LEGACY_GLIMMERKIN = LimijoyRigProfile(
    name="legacy-glimmerkin-35",
    bone_count=35,
    body={
        "torso": "Bone_015",
        "neck": "Bone_034",
        "head": "Bone_033",
        "head_tip": "Bone_032",
    },
    right_arm={
        "girdle": "Bone_023",
        "upper": "Bone_022",
        "elbow": "Bone_021",
        "wrist": "Bone_020",
        "hand": "Bone_019",
    },
    left_arm={
        "girdle": "Bone_031",
        "upper": "Bone_030",
        "elbow": "Bone_029",
        "wrist": "Bone_028",
        "hand": "Bone_027",
    },
)

BLANK_FACE_CANDIDATE = LimijoyRigProfile(
    name="blank-face-candidate-28",
    bone_count=28,
    body={
        "torso": "Bone_014",
        "neck": "Bone_027",
        "head": "Bone_026",
        "head_tip": "Bone_025",
    },
    right_arm={
        "girdle": "Bone_019",
        "upper": "Bone_018",
        "elbow": "Bone_017",
        "wrist": "Bone_016",
        "hand": "Bone_015",
    },
    left_arm={
        "girdle": "Bone_024",
        "upper": "Bone_023",
        "elbow": "Bone_022",
        "wrist": "Bone_021",
        "hand": "Bone_020",
    },
)

TPOSE_BLANK_FACE_CANDIDATE = LimijoyRigProfile(
    name="tpose-blank-face-candidate-45",
    bone_count=45,
    body={
        # Bone_015 is the low torso/root-follow segment. Bone_014 provides the
        # restrained chest follow used by the semantic look controller.
        "torso": "Bone_014",
        "neck": "Bone_018",
        "head": "Bone_017",
        "head_tip": "Bone_016",
    },
    # The semantic controller defines character-right as +X. On this Meshy
    # generation Bone_028->024 is the +X shoulder/arm chain and Bone_023->019
    # is the -X chain. Keep the profile aligned with semantic coordinates rather
    # than screen/viewer labels, otherwise bilateral actions cross the body.
    right_arm={
        "girdle": "Bone_028",
        "upper": "Bone_027",
        "elbow": "Bone_026",
        "wrist": "Bone_025",
        "hand": "Bone_024",
    },
    left_arm={
        "girdle": "Bone_023",
        "upper": "Bone_022",
        "elbow": "Bone_021",
        "wrist": "Bone_020",
        "hand": "Bone_019",
    },
)

PROFILES = (
    LEGACY_GLIMMERKIN,
    BLANK_FACE_CANDIDATE,
    TPOSE_BLANK_FACE_CANDIDATE,
)


def resolve_rig_profile(bone_names) -> LimijoyRigProfile:
    names = set(bone_names)
    matches = [
        profile
        for profile in PROFILES
        if len(names) == profile.bone_count
        and profile.required_bones.issubset(names)
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        return max(matches, key=lambda profile: len(profile.required_bones))

    details = ", ".join(
        (
            f"{profile.name}: expected {profile.bone_count} bones, got {len(names)}; "
            f"missing {sorted(profile.required_bones - names)}"
        )
        for profile in PROFILES
    )
    raise KeyError(f"No Limijoy rig profile matches this armature ({details})")


__all__ = [
    "BLANK_FACE_CANDIDATE",
    "LEGACY_GLIMMERKIN",
    "TPOSE_BLANK_FACE_CANDIDATE",
    "LimijoyRigProfile",
    "PROFILES",
    "resolve_rig_profile",
]
