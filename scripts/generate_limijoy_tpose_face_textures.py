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
    "outline": (45, 31, 21),
    "eye_outer": (52, 36, 25),
    "eye_mid": (95, 67, 39),
    "eye_inner": (39, 29, 23),
    "highlight": (255, 252, 243),
    "cheek": (190, 207, 111),
    "mouth": (211, 126, 111),
    "mouth_dark": (72, 39, 28),
    "brow_shadow": (53, 82, 27),
    "brow": (85, 121, 44),
    "brow_highlight": (119, 150, 64),
}


def rgba(colour: tuple[int, int, int], alpha: int = 255) -> tuple[int, int, int, int]:
    return (*colour, alpha)


def scaled_point(point: tuple[float, float]) -> tuple[int, int]:
    return tuple(round(value * SUPERSAMPLE) for value in point)


def scaled_box(box: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    return tuple(round(value * SUPERSAMPLE) for value in box)


def quadratic_points(start, control, end, samples: int = 36):
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


def draw_curve(draw, start, control, end, *, colour, width: float, round_caps: bool = True) -> None:
    points = quadratic_points(start, control, end)
    pixel_width = round(width * SUPERSAMPLE)
    draw.line(points, fill=colour, width=pixel_width, joint="curve")
    if round_caps:
        radius = pixel_width // 2
        for point in (points[0], points[-1]):
            draw.ellipse(
                (point[0] - radius, point[1] - radius, point[0] + radius, point[1] + radius),
                fill=colour,
            )


def draw_cheeks(draw) -> None:
    # Character-sheet placement: cheeks sit below the eye sockets, not beside
    # the pupils. They are intentionally a little farther outward as well.
    for box in ((77, 330, 137, 362), (375, 330, 435, 362)):
        draw.ellipse(scaled_box(box), fill=rgba(PALETTE["cheek"], 235))


def draw_open_eye(draw, centre_x: float, *, pupil_shift: float = 0.0) -> None:
    """Large glossy vertical oval matching the character-sheet eye emphasis."""
    outer = (centre_x - 34, 164, centre_x + 34, 286)
    mid = (centre_x - 29, 170, centre_x + 29, 281)
    inner = (
        centre_x - 20 + pupil_shift,
        183,
        centre_x + 20 + pupil_shift,
        273,
    )
    draw.ellipse(scaled_box(outer), fill=rgba(PALETTE["outline"]))
    draw.ellipse(scaled_box(mid), fill=rgba(PALETTE["eye_mid"]))
    draw.ellipse(scaled_box(inner), fill=rgba(PALETTE["eye_inner"]))
    draw.ellipse(
        scaled_box(
            (
                centre_x - 18 + pupil_shift,
                188,
                centre_x - 1 + pupil_shift,
                216,
            )
        ),
        fill=rgba(PALETTE["highlight"]),
    )
    draw.ellipse(
        scaled_box(
            (
                centre_x + 10 + pupil_shift,
                226,
                centre_x + 18 + pupil_shift,
                238,
            )
        ),
        fill=rgba(PALETTE["highlight"]),
    )


def draw_closed_eye(draw, centre_x: float) -> None:
    draw_curve(
        draw,
        (centre_x - 31, 244),
        (centre_x, 266),
        (centre_x + 31, 244),
        colour=rgba(PALETTE["outline"]),
        width=8,
    )


def draw_brow(draw, centre_x: float, *, inner_y: float, outer_y: float) -> None:
    """Soft curved brow with rounded ends and a subtle highlight, not a flat bar."""
    if centre_x < TEXTURE_SIZE / 2:
        start, end = (centre_x - 31, outer_y), (centre_x + 28, inner_y)
    else:
        start, end = (centre_x - 28, inner_y), (centre_x + 31, outer_y)
    control = ((start[0] + end[0]) * 0.5, min(start[1], end[1]) - 11)

    draw_curve(
        draw,
        start,
        control,
        end,
        colour=rgba(PALETTE["brow_shadow"]),
        width=13,
    )
    highlight_start = (start[0], start[1] - 1.5)
    highlight_control = (control[0], control[1] - 1.5)
    highlight_end = (end[0], end[1] - 1.5)
    draw_curve(
        draw,
        highlight_start,
        highlight_control,
        highlight_end,
        colour=rgba(PALETTE["brow"]),
        width=9,
    )
    # A narrow lighter crest keeps the mark visually soft on the shaded model.
    draw_curve(
        draw,
        (highlight_start[0] + 2, highlight_start[1] - 0.5),
        (highlight_control[0], highlight_control[1] - 0.5),
        (highlight_end[0] - 2, highlight_end[1] - 0.5),
        colour=rgba(PALETTE["brow_highlight"], 170),
        width=3,
    )


def draw_neutral_mouth(draw, *, offset_x: float = 0.0) -> None:
    draw_curve(
        draw,
        (224 + offset_x, 367),
        (256 + offset_x, 392),
        (288 + offset_x, 367),
        colour=rgba(PALETTE["outline"]),
        width=9,
    )


def draw_open_smile(draw) -> None:
    """Curved open smile from the character-sheet reference; no tooth rectangle."""
    upper = quadratic_points((216, 367), (256, 383), (296, 367), samples=30)
    lower = quadratic_points((296, 367), (256, 427), (216, 367), samples=36)
    mouth_points = upper + lower
    draw.polygon(mouth_points, fill=rgba(PALETTE["mouth_dark"]))

    # The tongue follows the lower bowl of the smile and remains entirely within
    # the mouth silhouette, avoiding the previous rectangular white artefact.
    draw.ellipse(
        scaled_box((231, 394, 281, 421)),
        fill=rgba(PALETTE["mouth"]),
    )
    # Reassert the curved lower edge so the tongue cannot flatten the silhouette.
    draw_curve(
        draw,
        (220, 369),
        (256, 426),
        (292, 369),
        colour=rgba(PALETTE["outline"]),
        width=5,
    )


def draw_o_mouth(draw) -> None:
    draw.ellipse(scaled_box((238, 362, 274, 406)), fill=rgba(PALETTE["outline"]))
    draw.ellipse(scaled_box((247, 371, 265, 397)), fill=rgba(PALETTE["mouth"]))


def draw_frown(draw) -> None:
    draw_curve(
        draw,
        (224, 399),
        (256, 367),
        (288, 399),
        colour=rgba(PALETTE["outline"]),
        width=9,
    )


def draw_straight_mouth(draw) -> None:
    start = scaled_point((228, 382))
    end = scaled_point((284, 382))
    width = round(9 * SUPERSAMPLE)
    draw.line((start, end), fill=rgba(PALETTE["outline"]), width=width)
    radius = width // 2
    for point in (start, end):
        draw.ellipse(
            (point[0] - radius, point[1] - radius, point[0] + radius, point[1] + radius),
            fill=rgba(PALETTE["outline"]),
        )


def render_overlay(state: str) -> Image.Image:
    size = TEXTURE_SIZE * SUPERSAMPLE
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw_cheeks(draw)

    if state == "blink":
        draw_closed_eye(draw, 158)
        draw_closed_eye(draw, 354)
    else:
        shift = 4 if state == "curious" else 0
        draw_open_eye(draw, 158, pupil_shift=shift)
        draw_open_eye(draw, 354, pupil_shift=shift)

    if state == "curious":
        draw_brow(draw, 158, inner_y=153, outer_y=171)
        draw_brow(draw, 354, inner_y=143, outer_y=167)
        draw_o_mouth(draw)
    elif state == "sad":
        draw_brow(draw, 158, inner_y=174, outer_y=145)
        draw_brow(draw, 354, inner_y=174, outer_y=145)
        draw_frown(draw)
    elif state == "determined":
        draw_brow(draw, 158, inner_y=171, outer_y=139)
        draw_brow(draw, 354, inner_y=171, outer_y=139)
        draw_straight_mouth(draw)
    elif state == "happy":
        # Happy remains open-eyed; Blink alone owns the closed-eye state.
        draw_brow(draw, 158, inner_y=151, outer_y=158)
        draw_brow(draw, 354, inner_y=151, outer_y=158)
        draw_open_smile(draw)
    else:
        draw_brow(draw, 158, inner_y=155, outer_y=161)
        draw_brow(draw, 354, inner_y=155, outer_y=161)
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
        "revision": "tpose-keeper-face-v3-character-sheet",
        "texture_size": TEXTURE_SIZE,
        "states": overlays,
        "eye_policy": "68x122 dark glossy vertical oval with stronger highlights",
        "cheek_policy": "rounded cheek spots moved below eye sockets and slightly outward",
        "brow_policy": "rounded curved multi-tone brow strokes; no squared flat bars",
        "mouth_policy": "mouths retain lowered placement; Happy uses a curved open bowl with no white tooth rectangle",
        "expression_policy": "Blink alone closes the eyes; Happy stays open-eyed; Determined uses a straight mouth",
        "geometry_policy": "feature-only RGBA overlays; native cream face supplies all geometry/shading",
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
