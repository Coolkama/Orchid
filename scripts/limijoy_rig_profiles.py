"""Rig profiles for Limijoy Meshy generations.

Meshy can produce the same character with a slightly different UniRig bone
count.  Limijoy behaviour code should target semantic roles instead of hard
coding one generation's Bone_### identifiers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class LimijoyRigProfile:
    name: str
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

PROFILES = (LEGACY_GLIMMERKIN, BLANK_FACE_CANDIDATE)


def resolve_rig_profile(bone_names) -> LimijoyRigProfile:
    names = set(bone_names)
    matches = [
        profile
        for profile in PROFILES
        if profile.required_bones.issubset(names)
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        # Prefer the most specific profile if a future generation happens to
        # contain a superset of another generation's semantic controls.
        return max(matches, key=lambda profile: len(profile.required_bones))

    details = ", ".join(
        f"{profile.name}: missing {sorted(profile.required_bones - names)}"
        for profile in PROFILES
    )
    raise KeyError(f"No Limijoy rig profile matches this armature ({details})")


__all__ = [
    "BLANK_FACE_CANDIDATE",
    "LEGACY_GLIMMERKIN",
    "LimijoyRigProfile",
    "PROFILES",
    "resolve_rig_profile",
]
