"""Generate character-sheet-proportioned Limijoy face overlays for the keeper model.

The native cream face remains supplied by the Meshy model.  These PNGs contain
transparent facial features only.  This revision deliberately increases the
feature scale and shifts the complete face lower on the cream patch after the
previous render remained too small and chin-heavy compared with the canonical
character sheet.
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
    "outline": (42, 28, 18),
    "eye_outer": (49, 32, 20),
    "eye_mid": (102, 70, 37),
    "eye_inner": (31, 23, 18),
    "highlight": (255, 253, 247),
    "cheek": (188, 207, 105),
    "mouth": (221, 132, 116),
    "mouth_dark": (68, 34, 24),
    "brow_shadow": (48, 76, 24),
    "brow": (83, 120, 41),
    "brow_highlight": (119, 153, 64),
}

# The previous on-model render was substantially smaller than the reference.
# These values are intentionally a strong correction rather than another tiny
# incremental nudge.
LEFT_EYE_X = 154
RIGHT_EYE_X = 358
EYE_CENTRE_Y = 255
EYE_WIDTH = 94
EYE_HEIGHT = 172
CHEEK_CENTRE_Y = 378
MOUTH_Y = 420


def rgba(colour: tuple[int, int, int], alpha: int = 255) -> tuple[int, int, int, int]:
    return (*colour, alpha)


def scaled_point(point: tuple[float, float]) -> tuple[int, int]:
    return tuple(round(value * SUPERSAMPLE) for value in point)


def scaled_box(box: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    return tuple(round(value * SUPERSAMPLE) for value in box)


def quadratic_points(start, control, end, samples: int = 40):
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
    # Below the eye sockets, slightly outward, as in the reference sheet.
    width = 70
    height = 40
    for centre_x in (104, 408):
        draw.ellipse(
            scaled_box(
                (
                    centre_x - width / 2,
                    CHEEK_CENTRE_Y - height / 2,
                    centre_x + width / 2,
                    CHEEK_CENTRE_Y + height / 2,
                )
            ),
            fill=rgba(PALETTE["cheek"], 240),
        )


def draw_open_eye(draw, centre_x: float, *, pupil_shift: float = 0.0) -> None:
    """Large glossy vertical oval matching the character sheet's dominant eyes."""
    half_w = EYE_WIDTH / 2
    half_h = EYE_HEIGHT / 2
    outer = (
        centre_x - half_w,
        EYE_CENTRE_Y - half_h,
        centre_x + half_w,
        EYE_CENTRE_Y + half_h,
    )
    draw.ellipse(scaled_box(outer), fill=rgba(PALETTE["outline"]))

    margin_x = 7
    margin_y = 8
    draw.ellipse(
        scaled_box(
            (
                outer[0] + margin_x,
                outer[1] + margin_y,
                outer[2] - margin_x,
                outer[3] - margin_y,
            )
        ),
        fill=rgba(PALETTE["eye_mid"]),
    )

    inner_half_w = 30
    inner_half_h = 61
    draw.ellipse(
        scaled_box(
            (
                centre_x - inner_half_w + pupil_shift,
                EYE_CENTRE_Y - inner_half_h + 8,
                centre_x + inner_half_w + pupil_shift,
                EYE_CENTRE_Y + inner_half_h + 8,
            )
        ),
        fill=rgba(PALETTE["eye_inner"]),
    )

    # Two strong reference-style highlights.
    draw.ellipse(
        scaled_box(
            (
                centre_x - 29 + pupil_shift,
                EYE_CENTRE_Y - 52,
                centre_x - 4 + pupil_shift,
                EYE_CENTRE_Y - 17,
            )
        ),
        fill=rgba(PALETTE["highlight"]),
    )
    draw.ellipse(
        scaled_box(
            (
                centre_x + 15 + pupil_shift,
                EYE_CENTRE_Y + 12,
                centre_x + 26 + pupil_shift,
                EYE_CENTRE_Y + 27,
            )
        ),
        fill=rgba(PALETTE["highlight"]),
    )


def draw_closed_eye(draw, centre_x: float) -> None:
    # The eye socket still occupies the same location when blinking.
    draw_curve(
        draw,
        (centre_x - 45, EYE_CENTRE_Y + 3),
        (centre_x, EYE_CENTRE_Y + 40),
        (centre_x + 45, EYE_CENTRE_Y + 3),
        colour=rgba(PALETTE["outline"]),
        width=9,
    )


def draw_brow(draw, centre_x: float, *, inner_y: float, outer_y: float) -> None:
    """Rounded, arched, subtly shaded brow rather than a flat squared stroke."""
    if centre_x < TEXTURE_SIZE / 2:
        start, end = (centre_x - 39, outer_y), (centre_x + 35, inner_y)
    else:
        start, end = (centre_x - 35, inner_y), (centre_x + 39, outer_y)
    control = ((start[0] + end[0]) * 0.5, min(start[1], end[1]) - 15)

    draw_curve(
        draw,
        start,
        control,
        end,
        colour=rgba(PALETTE["brow_shadow"]),
        width=16,
    )
    draw_curve(
        draw,
        (start[0], start[1] - 2),
        (control[0], control[1] - 2),
        (end[0], end[1] - 2),
        colour=rgba(PALETTE["brow"]),
        width=11,
    )
    draw_curve(
        draw,
        (start[0] + 4, start[1] - 4),
        (control[0], control[1] - 4),
        (end[0] - 4, end[1] - 4),
        colour=rgba(PALETTE["brow_highlight"], 175),
        width=3,
    )


def draw_neutral_mouth(draw) -> None:
    draw_curve(
        draw,
        (211, MOUTH_Y - 8),
        (256, MOUTH_Y + 28),
        (301, MOUTH_Y - 8),
        colour=rgba(PALETTE["outline"]),
        width=10,
    )


def draw_open_smile(draw) -> None:
    """Large curved happy bowl with tongue fully clipped inside the silhouette."""
    top_y = MOUTH_Y - 9
    upper = quadratic_points((204, top_y), (256, top_y + 22), (308, top_y), samples=36)
    lower = quadratic_points((308, top_y), (256, MOUTH_Y + 61), (204, top_y), samples=46)
    mouth_points = upper + lower
    draw.polygon(mouth_points, fill=rgba(PALETTE["mouth_dark"]))

    # Keep the tongue well inside the dark bowl; no teeth/white rectangle.
    draw.ellipse(
        scaled_box((226, MOUTH_Y + 22, 286, MOUTH_Y + 52)),
        fill=rgba(PALETTE["mouth"]),
    )

    # Reinforce the curved outline without flattening the mouth.
    draw_curve(
        draw,
        (207, top_y + 1),
        (256, MOUTH_Y + 61),
        (305, top_y + 1),
        colour=rgba(PALETTE["outline"]),
        width=5,
    )


def draw_o_mouth(draw) -> None:
    draw.ellipse(
        scaled_box((232, MOUTH_Y - 12, 280, MOUTH_Y + 42)),
        fill=rgba(PALETTE["outline"]),
    )
    draw.ellipse(
        scaled_box((243, MOUTH_Y, 269, MOUTH_Y + 31)),
        fill=rgba(PALETTE["mouth"]),
    )


def draw_frown(draw) -> None:
    draw_curve(
        draw,
        (211, MOUTH_Y + 24),
        (256, MOUTH_Y - 14),
        (301, MOUTH_Y + 24),
        colour=rgba(PALETTE["outline"]),
        width=10,
    )


def draw_straight_mouth(draw) -> None:
    start = scaled_point((218, MOUTH_Y + 10))
    end = scaled_point((294, MOUTH_Y + 10))
    width = round(10 * SUPERSAMPLE)
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
        draw_closed_eye(draw, LEFT_EYE_X)
        draw_closed_eye(draw, RIGHT_EYE_X)
    else:
        shift = 5 if state == "curious" else 0
        draw_open_eye(draw, LEFT_EYE_X, pupil_shift=shift)
        draw_open_eye(draw, RIGHT_EYE_X, pupil_shift=shift)

    # Brows follow the enlarged/lowered eyes. Their state-specific slopes retain
    # the existing emotional language while sitting closer to the eye sockets.
    if state == "curious":
        draw_brow(draw, LEFT_EYE_X, inner_y=178, outer_y=205)
        draw_brow(draw, RIGHT_EYE_X, inner_y=165, outer_y=198)
        draw_o_mouth(draw)
    elif state == "sad":
        draw_brow(draw, LEFT_EYE_X, inner_y=210, outer_y=174)
        draw_brow(draw, RIGHT_EYE_X, inner_y=210, outer_y=174)
        draw_frown(draw)
    elif state == "determined":
        draw_brow(draw, LEFT_EYE_X, inner_y=208, outer_y=168)
        draw_brow(draw, RIGHT_EYE_X, inner_y=208, outer_y=168)
        draw_straight_mouth(draw)
    elif state == "happy":
        draw_brow(draw, LEFT_EYE_X, inner_y=181, outer_y=191)
        draw_brow(draw, RIGHT_EYE_X, inner_y=181, outer_y=191)
        draw_open_smile(draw)
    else:
        draw_brow(draw, LEFT_EYE_X, inner_y=188, outer_y=196)
        draw_brow(draw, RIGHT_EYE_X, inner_y=188, outer_y=196)
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
        "revision": "tpose-keeper-face-v4-large-low",
        "texture_size": TEXTURE_SIZE,
        "states": overlays,
        "layout_policy": "substantially enlarged feature set shifted lower to match canonical sheet and reduce chin-heavy appearance",
        "eye_policy": f"{EYE_WIDTH}x{EYE_HEIGHT} dark glossy vertical ovals centred lower on the native face",
        "cheek_policy": "70x40 rounded cheek spots below the enlarged eye sockets and slightly outward",
        "brow_policy": "wider rounded curved multi-tone brows tracking the enlarged/lowered eyes",
        "mouth_policy": "larger mouths centred near y=420; Happy is a curved open bowl with tongue fully inside and no white rectangle",
        "expression_policy": "Blink alone closes the eyes; Happy remains open-eyed; Determined uses a firm straight mouth",
        "geometry_policy": "feature-only RGBA overlays; native cream face supplies all geometry/shading",
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
