"""Prepare character-sheet-derived Limijoy face overlays for the keeper review.

The six expression textures are authored image assets derived from the canonical
Limijoy character sheet. This script performs no procedural facial drawing: it
loads the committed RGBA PNG overlays, normalises them to the 512 px review
contract, applies the approved horizontal proportion adjustment, and emits the
manifest/atlas expected by the Blender review pipeline.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
TEXTURE_SIZE = 512
STATES = ("neutral", "blink", "happy", "curious", "sad", "determined")
SOURCE_DIR = ROOT / "assets" / "Ace-art" / "character-sheet"
ART_HORIZONTAL_SCALE = 0.95


def narrow_overlay(image: Image.Image) -> Image.Image:
    """Narrow authored facial features by 5% without changing their height."""
    target_width = max(1, int(round(TEXTURE_SIZE * ART_HORIZONTAL_SCALE)))
    narrowed = image.resize((target_width, TEXTURE_SIZE), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (TEXTURE_SIZE, TEXTURE_SIZE), (0, 0, 0, 0))
    x = (TEXTURE_SIZE - target_width) // 2
    canvas.alpha_composite(narrowed, (x, 0))
    return canvas


def load_overlay(state: str) -> Image.Image:
    source = SOURCE_DIR / f"limijoy-face-{state}-overlay.png"
    if not source.exists():
        raise FileNotFoundError(f"Character-sheet face overlay is missing: {source}")

    image = Image.open(source).convert("RGBA")
    if image.size != (TEXTURE_SIZE, TEXTURE_SIZE):
        image = image.resize((TEXTURE_SIZE, TEXTURE_SIZE), Image.Resampling.LANCZOS)
    return narrow_overlay(image)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    overlays: dict[str, str] = {}
    previews: list[Image.Image] = []

    for state in STATES:
        image = load_overlay(state)
        path = args.output / f"limijoy-face-{state}-overlay.png"
        image.save(path, optimize=True)
        overlays[state] = path.name

        preview = Image.new("RGBA", (TEXTURE_SIZE, TEXTURE_SIZE), (238, 231, 174, 255))
        preview.alpha_composite(image)
        previews.append(preview.convert("RGB"))

    columns = 3
    rows = math.ceil(len(previews) / columns)
    atlas = Image.new("RGB", (TEXTURE_SIZE * columns, TEXTURE_SIZE * rows), (238, 231, 174))
    for index, image in enumerate(previews):
        atlas.paste(image, ((index % columns) * TEXTURE_SIZE, (index // columns) * TEXTURE_SIZE))
    atlas.save(args.output / "revised-face-art-atlas.png", optimize=True)

    manifest = {
        "revision": "character-sheet-authored-full-face-v1",
        "texture_size": TEXTURE_SIZE,
        "art_horizontal_scale": ART_HORIZONTAL_SCALE,
        "effective_face_width_scale_with_uv": 0.855 * ART_HORIZONTAL_SCALE,
        "states": overlays,
        "source_dir": str(SOURCE_DIR.relative_to(ROOT)),
        "source_policy": "facial artwork derived from canonical Limijoy character sheet; no procedural primitive drawing",
        "geometry_policy": "feature-only RGBA overlays; native cream face supplies all geometry and shading",
        "test_policy": "full-face authored art first; if UV wrapping is unsatisfactory, decompose the same art into reusable eye/blink/cheek/brow/mouth parts and compose deterministically in UV space",
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
