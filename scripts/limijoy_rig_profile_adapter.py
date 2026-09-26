"""Bridge Limijoy semantic controllers onto a resolved Meshy rig profile.

The semantic arm/body controllers pre-date multiple Meshy generations and keep
their calibrated role maps as module globals.  This adapter resolves the
armature through ``limijoy_rig_profiles`` and installs the matching role maps
before a semantic controller is instantiated.  It lets Orchid prove the new
28-bone candidate without changing the behaviour-facing action API.

Once the candidate is accepted this bridge can be folded into the controllers
proper; keeping it explicit here makes the compatibility experiment small and
reversible.
"""

from __future__ import annotations

import bpy

import limijoy_arm_semantic_controls as arm_controls
import limijoy_body_semantic_controls as body_controls
from limijoy_rig_profiles import LimijoyRigProfile, resolve_rig_profile


def activate_semantic_rig_profile(
    armature: bpy.types.Object,
) -> LimijoyRigProfile:
    """Resolve *armature* and install its semantic bone-role mappings."""

    if armature.type != "ARMATURE":
        raise TypeError("armature must be a Blender ARMATURE object")

    profile = resolve_rig_profile(armature.data.bones.keys())

    arm_controls.RIGHT_ARM_BONES = dict(profile.right_arm)
    arm_controls.LEFT_ARM_BONES = dict(profile.left_arm)
    body_controls.BODY_BONES = {
        "torso": profile.body["torso"],
        "neck": profile.body["neck"],
        "head": profile.body["head"],
    }
    return profile


__all__ = ["activate_semantic_rig_profile"]
