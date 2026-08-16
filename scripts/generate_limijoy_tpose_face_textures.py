"""Prepare character-sheet-derived Limijoy face overlays for the keeper review.

This revision deliberately stops drawing facial art from Pillow primitives. The
six expression studies were authored from the canonical Limijoy character sheet,
stored as compact RGBA WebP studies, and are expanded to the 512px overlay
contract expected by the Blender review pipeline.

The base64 split is only a repository transport detail for this Orchid study. If
this visual pass is accepted, the art can be promoted as normal production
assets (or decomposed into reusable eye/brow/cheek/mouth parts).
"""

from __future__ import annotations

import argparse
import base64
import binascii
import io
import json
import math
import zipfile
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
TEXTURE_SIZE = 512
STATES = ("neutral", "blink", "happy", "curious", "sad", "determined")
SOURCE_DIR = ROOT / "assets" / "face-art" / "generated-study"
SOURCE_GLOB = "limijoy-generated-faces.b64.*"


def _decode_transport_parts(parts: list[Path]) -> bytes:
    """Decode one or more independently padded base64 blocks in filename order.

    The connector transport may have split a base64 block across several files,
    and some earlier blocks are independently padded. Accumulate until padding
    marks the end of a block, decode it, then continue. This preserves the exact
    original ZIP bytes while allowing the repository-only text transport.
    """
    decoded = bytearray()
    pending = ""

    for part in parts:
        chunk = "".join(part.read_text(encoding="ascii").split())
        if not chunk:
            continue
        pending += chunk
        if "=" in chunk:
            try:
                decoded.extend(base64.b64decode(pending, validate=True))
            except binascii.Error as exc:
                raise ValueError(f"Invalid generated-face transport ending at {part.name}: {exc}") from exc
            pending = ""

    if pending:
        try:
            decoded.extend(base64.b64decode(pending, validate=True))
        except binascii.Error as exc:
            raise ValueError(f"Invalid final generated-face transport block: {exc}") from exc

    return bytes(decoded)


def load_study_archive() -> zipfile.ZipFile:
    parts = sorted(SOURCE_DIR.glob(SOURCE_GLOB))
    if not parts:
        raise FileNotFoundError(f"No generated face study parts found in {SOURCE_DIR}")
    payload = _decode_transport_parts(parts)
    return zipfile.ZipFile(io.BytesIO(payload), "r")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    overlays: dict[str, str] = {}
    previews: list[Image.Image] = []

    with load_study_archive() as archive:
        names = set(archive.namelist())
        for state in STATES:
            source_name = f"limijoy-face-{state}-overlay.webp"
            if source_name not in names:
                raise FileNotFoundError(f"Generated face study is missing {source_name}")
            with archive.open(source_name) as source:
                image = Image.open(source).convert("RGBA")
                image = image.resize((TEXTURE_SIZE, TEXTURE_SIZE), Image.Resampling.LANCZOS)

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
        "revision": "character-sheet-generated-full-face-v1",
        "texture_size": TEXTURE_SIZE,
        "states": overlays,
        "source_policy": "facial artwork derived from canonical Limijoy character sheet; no procedural primitive drawing",
        "geometry_policy": "feature-only RGBA overlays; native cream face supplies all geometry and shading",
        "test_policy": "full-face generated art first; if UV wrapping is unsatisfactory, decompose the same art into reusable eye/blink/cheek/brow/mouth parts and compose deterministically in UV space",
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
