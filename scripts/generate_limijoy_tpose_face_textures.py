"""Generate revised Limijoy feature overlays for the 45-bone T-pose keeper model.

This is deliberately isolated from the earlier face texture generator until the
new proportions are visually approved. The native cream face remains supplied
by the Meshy model; these PNGs contain transparent eyes/brows/cheeks/mouth only.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

TEXTURE_SIZE = 512
SUPERSAMPLE = 4
STATES = ("neutral", "blink", "happy", "curious", "sad", "determined")
PALETTE = {
    "cheek": (208, 219, 145),
    "mouth": (182, 116, 104),
    "eyes": (58, 48, 34),
    "highlight": (252, 249, 229),
    "sprout": (73, 99, 41),
}


def rgba(colour: tuple[int, int, int], alpha: int = 255) -> tuple[int, int, int, int]:
    return (*colour, alpha)


def scaled_point(point: tuple[float, float]) -> tuple[int, int]:
    return tuple(round(value * SUPERSAMPLE) for value in point)


def scaled_box(box: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    return tuple(round(value * SUPERSAMPLE) for value in box)


def quadratic_points(start, control, end, samples: int = 28):
    result = []
    for index in range(samples + 1):
        amount = index / samples
        inverse = 1.0 - amount
        result.append(
            scaled_point(
                (
                    inverse * inverse * start[0]
                    + 2.0 * inverse * amount * control[0]
                    + amount * amount * end[0],
                    inverse * inverse * start[1]
                    + 2.0 * inverse * amount * control[1]
                    + amount * amount * end[1],
                )
            )
        )
    return result


def draw_curve(draw, start, control, end, *, colour, width: float) -> None:
    draw.line(
        quadratic_points(start, control, end),
        fill=colour,
        width=round(width * SUPERSAMPLE),
        joint="curve",
    )


def colour(name: str):
    return rgba(PALETTE[name])


def draw_cheeks(draw) -> None:
    for box in ((88, 292, 137, 319), (375, 292, 424, 319)):
        draw.ellipse(scaled_box(box), fill=colour("cheek"))


def draw_open_eye(draw, centre_x: float, *, pupil_shift: float = 0.0) -> None:
    """Narrow eye art so the wider physical face renders a vertical oval."""
    eye = colour("eyes")
    lower_rgb = tuple(min(255, channel + 22) for channel in PALETTE["eyes"])
    draw.ellipse(scaled_box((centre_x - 26, 169, centre_x + 26, 281)), fill=eye)
    draw.ellipse(
        scaled_box((centre_x - 19 + pupil_shift, 177, centre_x + 19 + pupil_shift, 275)),
        fill=rgba(lower_rgb),
    )
    draw.ellipse(
        scaled_box((centre_x - 15 + pupil_shift, 181, centre_x + 17 + pupil_shift, 264)),
        fill=eye,
    )
    draw.ellipse(
        scaled_box((centre_x - 11 + pupil_shift, 190, centre_x + 1 + pupil_shift, 212)),
        fill=colour("highlight"),
    )
    draw.ellipse(
        scaled_box((centre_x + 7 + pupil_shift, 225, centre_x + 13 + pupil_shift, 235)),
        fill=colour("highlight"),
    )


def draw_closed_eye(draw, centre_x: float) -> None:
    draw_curve(
        draw,
        (centre_x - 28, 232),
        (centre_x, 258),
        (centre_x + 28, 232),
        colour=colour("eyes"),
        width=11,
    )


def draw_brow(draw, centre_x: float, *, inner_y: float, outer_y: float) -> None:
    if centre_x < TEXTURE_SIZE / 2:
        start, end = (centre_x - 30, outer_y), (centre_x + 27, inner_y)
    else:
        start, end = (centre_x - 27, inner_y), (centre_x + 30, outer_y)
    control = ((start[0] + end[0]) * 0.5, min(start[1], end[1]) - 8)
    draw_curve(draw, start, control, end, colour=colour("sprout"), width=9)


def draw_neutral_mouth(draw, *, offset_x: float = 0.0) -> None:
    draw_curve(
        draw,
        (225 + offset_x, 366),
        (256 + offset_x, 390),
        (287 + offset_x, 366),
        colour=colour("eyes"),
        width=10,
    )


def draw_open_smile(draw) -> None:
    draw.ellipse(scaled_box((214, 349, 298, 423)), fill=colour("eyes"))
    draw.ellipse(scaled_box((227, 381, 285, 418)), fill=colour("mouth"))
    draw.rectangle(scaled_box((227, 349, 285, 365)), fill=colour("highlight"))


def draw_o_mouth(draw) -> None:
    draw.ellipse(scaled_box((236, 357, 276, 408)), fill=colour("eyes"))
    draw.ellipse(scaled_box((245, 368, 267, 399)), fill=colour("mouth"))


def draw_frown(draw) -> None:
    draw_curve(
        draw,
        (225, 391),
        (256, 363),
        (287, 391),
        colour=colour("eyes"),
        width=10,
    )


def render_overlay(state: str) -> Image.Image:
    size = TEXTURE_SIZE * SUPERSAMPLE
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw_cheeks(draw)

    if state in {"blink", "happy"}:
        draw_closed_eye(draw, 158)
        draw_closed_eye(draw, 354)
    else:
        shift = 4 if state == "curious" else 0
        draw_open_eye(draw, 158, pupil_shift=shift)
        draw_open_eye(draw, 354, pupil_shift=shift)

    if state == "curious":
        draw_brow(draw, 158, inner_y=150, outer_y=169)
        draw_brow(draw, 354, inner_y=139, outer_y=165)
        draw_o_mouth(draw)
    elif state == "sad":
        draw_brow(draw, 158, inner_y=171, outer_y=145)
        draw_brow(draw, 354, inner_y=171, outer_y=145)
        draw_frown(draw)
    elif state == "determined":
        draw_brow(draw, 158, inner_y=168, outer_y=137)
        draw_brow(draw, 354, inner_y=168, outer_y=137)
        draw_neutral_mouth(draw, offset_x=5)
    elif state == "happy":
        draw_brow(draw, 158, inner_y=154, outer_y=159)
        draw_brow(draw, 354, inner_y=154, outer_y=159)
        draw_open_smile(draw)
    else:
        draw_brow(draw, 158, inner_y=153, outer_y=159)
        draw_brow(draw, 354, inner_y=153, outer_y=159)
        draw_neutral_mouth(draw)

    return image.resize((TEXTURE_SIZE, TEXTURE_SIZE), Image.Resampling.LANCZOS)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    overlays = {}
    previews = []
    for state in STATES:
        image = render_overlay(state)
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
        "revision": "tpose-keeper-face-v2",
        "texture_size": TEXTURE_SIZE,
        "states": overlays,
        "eye_policy": "narrow 52x112 texture oval to counter native face width and render vertically oval",
        "mouth_policy": "all mouth artwork lowered approximately 30 texture pixels from first blank-face prototype",
        "geometry_policy": "feature-only RGBA overlays; native cream face supplies all geometry/shading",
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
