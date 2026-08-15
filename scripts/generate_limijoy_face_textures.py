"""Generate the first Limijoy textured-face expression set.

The palette and expression language come from the canonical Limijoy character
and turnaround sheets.  The output is deliberately small and deterministic so
Android can later animate only the face material instead of replacing the full
body texture.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw


TEXTURE_SIZE = 512
SUPERSAMPLE = 4

# Canonical sheet swatches sampled from limijoy-turnaround-sheet.png.  The face
# base is nudged slightly warmer so it matches the cream seen under the model's
# existing lighting rather than reading as a grey-white mask.
PALETTE = {
    "lime": (192, 202, 122),
    "leaf": (140, 168, 87),
    "sprout": (73, 99, 41),
    "face": (238, 231, 174),
    "cheek": (208, 219, 145),
    "mouth": (182, 116, 104),
    "eyes": (58, 48, 34),
    "highlight": (252, 249, 229),
}

STATES = ("neutral", "blink", "happy", "curious", "sad", "determined")


def scaled_point(point: tuple[float, float]) -> tuple[int, int]:
    return tuple(round(value * SUPERSAMPLE) for value in point)


def scaled_box(box: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    return tuple(round(value * SUPERSAMPLE) for value in box)


def quadratic_points(
    start: tuple[float, float],
    control: tuple[float, float],
    end: tuple[float, float],
    samples: int = 28,
) -> list[tuple[int, int]]:
    result = []
    for index in range(samples + 1):
        amount = index / samples
        inverse = 1.0 - amount
        x = inverse * inverse * start[0] + 2.0 * inverse * amount * control[0] + amount * amount * end[0]
        y = inverse * inverse * start[1] + 2.0 * inverse * amount * control[1] + amount * amount * end[1]
        result.append(scaled_point((x, y)))
    return result


def draw_curve(
    draw: ImageDraw.ImageDraw,
    start: tuple[float, float],
    control: tuple[float, float],
    end: tuple[float, float],
    *,
    colour: tuple[int, int, int],
    width: float,
) -> None:
    draw.line(
        quadratic_points(start, control, end),
        fill=colour,
        width=round(width * SUPERSAMPLE),
        joint="curve",
    )


def face_background() -> Image.Image:
    size = TEXTURE_SIZE * SUPERSAMPLE
    image = Image.new("RGB", (size, size), PALETTE["face"])
    pixels = image.load()
    base = PALETTE["face"]
    # A restrained centre lift keeps the sheet's soft painted quality while the
    # model material and scene lighting remain responsible for actual shading.
    for y in range(size):
        normal_y = (y / (size - 1) - 0.46) / 0.72
        for x in range(size):
            normal_x = (x / (size - 1) - 0.5) / 0.78
            radius = normal_x * normal_x + normal_y * normal_y
            lift = max(0.0, 1.0 - radius) * 5.0
            pixels[x, y] = tuple(min(255, round(channel + lift)) for channel in base)
    return image


def draw_cheeks(draw: ImageDraw.ImageDraw) -> None:
    for box in ((82, 286, 137, 317), (375, 286, 430, 317)):
        draw.ellipse(scaled_box(box), fill=PALETTE["cheek"])


def draw_open_eye(draw: ImageDraw.ImageDraw, centre_x: float, *, pupil_shift: float = 0.0) -> None:
    outer = (centre_x - 39, 169, centre_x + 39, 281)
    inner = (centre_x - 30 + pupil_shift, 177, centre_x + 30 + pupil_shift, 275)
    draw.ellipse(scaled_box(outer), fill=PALETTE["eyes"])
    lower_colour = tuple(min(255, channel + 22) for channel in PALETTE["eyes"])
    draw.ellipse(scaled_box(inner), fill=lower_colour)
    draw.ellipse(scaled_box((centre_x - 23 + pupil_shift, 181, centre_x + 26 + pupil_shift, 264)), fill=PALETTE["eyes"])
    draw.ellipse(scaled_box((centre_x - 16 + pupil_shift, 190, centre_x + 1 + pupil_shift, 212)), fill=PALETTE["highlight"])
    draw.ellipse(scaled_box((centre_x + 10 + pupil_shift, 225, centre_x + 18 + pupil_shift, 235)), fill=PALETTE["highlight"])


def draw_closed_eye(draw: ImageDraw.ImageDraw, centre_x: float) -> None:
    draw_curve(
        draw,
        (centre_x - 37, 231),
        (centre_x, 264),
        (centre_x + 37, 231),
        colour=PALETTE["eyes"],
        width=13,
    )


def draw_brow(
    draw: ImageDraw.ImageDraw,
    centre_x: float,
    *,
    inner_y: float,
    outer_y: float,
) -> None:
    if centre_x < TEXTURE_SIZE / 2:
        start, end = (centre_x - 34, outer_y), (centre_x + 31, inner_y)
    else:
        start, end = (centre_x - 31, inner_y), (centre_x + 34, outer_y)
    control = ((start[0] + end[0]) * 0.5, min(start[1], end[1]) - 9)
    draw_curve(draw, start, control, end, colour=PALETTE["sprout"], width=10)


def draw_neutral_mouth(draw: ImageDraw.ImageDraw, *, offset_x: float = 0.0) -> None:
    draw_curve(
        draw,
        (224 + offset_x, 336),
        (256 + offset_x, 360),
        (288 + offset_x, 336),
        colour=PALETTE["eyes"],
        width=10,
    )


def draw_open_smile(draw: ImageDraw.ImageDraw) -> None:
    draw.ellipse(scaled_box((211, 319, 301, 393)), fill=PALETTE["eyes"])
    draw.ellipse(scaled_box((225, 351, 287, 388)), fill=PALETTE["mouth"])
    draw.rectangle(scaled_box((225, 319, 287, 335)), fill=PALETTE["highlight"])


def draw_o_mouth(draw: ImageDraw.ImageDraw) -> None:
    draw.ellipse(scaled_box((234, 327, 278, 378)), fill=PALETTE["eyes"])
    draw.ellipse(scaled_box((244, 338, 268, 369)), fill=PALETTE["mouth"])


def draw_frown(draw: ImageDraw.ImageDraw) -> None:
    draw_curve(
        draw,
        (224, 361),
        (256, 333),
        (288, 361),
        colour=PALETTE["eyes"],
        width=10,
    )


def render_state(state: str, background: Image.Image | None = None) -> Image.Image:
    image = background.copy() if background is not None else face_background()
    draw = ImageDraw.Draw(image)
    draw_cheeks(draw)

    if state in {"blink", "happy"}:
        draw_closed_eye(draw, 158)
        draw_closed_eye(draw, 354)
    else:
        shift = 5 if state == "curious" else 0
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
    arguments = parser.parse_args()
    arguments.output.mkdir(parents=True, exist_ok=True)

    textures = {}
    rendered = []
    background = face_background()
    for state in STATES:
        image = render_state(state, background)
        path = arguments.output / f"limijoy-face-{state}.png"
        image.save(path, optimize=True)
        textures[state] = path.name
        rendered.append(image)

    columns = 3
    rows = math.ceil(len(rendered) / columns)
    atlas = Image.new("RGB", (TEXTURE_SIZE * columns, TEXTURE_SIZE * rows), PALETTE["face"])
    for index, image in enumerate(rendered):
        atlas.paste(image, ((index % columns) * TEXTURE_SIZE, (index // columns) * TEXTURE_SIZE))
    atlas_path = arguments.output / "limijoy-face-atlas.png"
    atlas.save(atlas_path, optimize=True)

    manifest = {
        "source": "Canonical Limijoy character and turnaround sheets",
        "texture_size": TEXTURE_SIZE,
        "states": textures,
        "atlas": {
            "file": atlas_path.name,
            "columns": columns,
            "rows": rows,
            "order": list(STATES),
        },
        "palette": {name: "#" + "".join(f"{channel:02x}" for channel in colour) for name, colour in PALETTE.items()},
    }
    (arguments.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Generated {len(STATES)} Limijoy face states in {arguments.output}")


if __name__ == "__main__":
    main()
