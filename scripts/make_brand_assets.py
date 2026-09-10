"""Generate the eight brand images from FX Luminaire's own marks.

    python scripts/make_brand_assets.py

## Why these files, and why eight

A custom integration's icon comes from ``custom_components/<domain>/brand/``. Home Assistant serves
it through ``/api/brands/integration/{domain}/{image}``, and a local ``brand/`` directory takes
priority over the brands CDN. Nothing is submitted anywhere: ``home-assistant/brands`` explicitly
refuses pull requests for custom components, so a 404 from ``brands.home-assistant.io`` is normal
and means nothing.

Home Assistant asks for ``icon``, ``logo``, their ``@2x`` variants, and a ``dark_`` prefixed version
of each, choosing the ``dark_`` one on a dark theme. The ``dark_`` files are purely additive --
``dark_icon.png`` falls back to ``icon.png`` -- which is exactly the trap: relying on that fallback
puts the source's **white** lettering on a light card, where it is invisible.

## Keying, not drawing

Every pixel far enough from the artwork's own corner colour is ink; everything else becomes
transparent. The background colour is **read from a corner** rather than assumed, because the two
source files do not share one: the square mark sits on ``rgb(0, 60, 88)`` and the wordmark on
``rgb(0, 78, 114)``.

Alpha ramps across a band rather than switching at a threshold. These are JPEGs, so the letterforms
carry compression noise at their edges; a hard cut produces a jagged mark with a navy halo.

**Do not draw an approximation instead.** The real marks are right here. Reproducing them by eye is
work spent to be less accurate, and it invents a trademark rather than using one.

## One source, two polarities

FX Luminaire publish these white-on-navy only, so the light-theme variant has to be made: the ink is
recoloured, the geometry is untouched. Near-black ink for a light theme, the original white for a
dark one, both on transparency.

## Resizing: coverage, and one honest limitation

The square source is 320x320. ``icon.png`` at 256 is a downscale and is crisp. **``icon@2x.png`` at
512 is a 1.6x upscale and is measurably softer than a native asset would be** -- acceptable for
these large, simple letterforms, and stated here rather than left for someone to notice. The same
applies to ``logo@2x.png`` from a 276x75 source.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "assets"
OUT = ROOT / "custom_components" / "luxor" / "brand"

#: Ink colour for the light-theme variants. Not pure black: the mark reads as very dark navy in
#: FX Luminaire's own print use, and pure black next to Home Assistant's card text looks harsher
#: than the brand does.
LIGHT_THEME_INK = (16, 32, 44)

#: Below `KEY_LOW` from the background is fully transparent, above `KEY_HIGH` fully opaque, and the
#: band between ramps. Widened deliberately for JPEG sources -- a narrow band leaves a navy fringe.
KEY_LOW = 60
KEY_HIGH = 150


def _key(source: Path, ink: tuple[int, int, int] | None) -> Image.Image:
    """Lift the lettering off its background onto transparency.

    `ink=None` keeps the source's own colour, which is the white the marks ship with.
    """
    image = Image.open(source).convert("RGB")
    width, height = image.size
    background = image.getpixel((0, 0))

    out = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    src = image.load()
    dst = out.load()
    for y in range(height):
        for x in range(width):
            pixel = src[x, y]
            distance = sum(abs(a - b) for a, b in zip(pixel, background, strict=True))
            if distance <= KEY_LOW:
                continue
            alpha = (
                255
                if distance >= KEY_HIGH
                else round(255 * (distance - KEY_LOW) / (KEY_HIGH - KEY_LOW))
            )
            dst[x, y] = (*(ink or pixel), alpha)
    return out


def _save(image: Image.Image, name: str, height: int, square: bool) -> None:
    if square:
        size = (height, height)
    else:
        ratio = image.width / image.height
        size = (round(height * ratio), height)
    resized = image.resize(size, Image.LANCZOS)
    path = OUT / name
    resized.save(path, "PNG", optimize=True)
    upscaled = " (UPSCALED from the source -- softer than native)" if height > image.height else ""
    print(f"  {name:22s} {size[0]}x{size[1]}{upscaled}")


def main() -> int:
    if not SOURCES.exists():
        print(f"no {SOURCES}", file=sys.stderr)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)

    icon_src = SOURCES / "fx-icon-source.jpg"
    logo_src = SOURCES / "fx-logo-source.jpg"

    for source, stem, square in ((icon_src, "icon", True), (logo_src, "logo", False)):
        original = Image.open(source)
        print(
            f"{source.name}: {original.width}x{original.height}, "
            f"background {Image.open(source).convert('RGB').getpixel((0, 0))}"
        )
        light = _key(source, LIGHT_THEME_INK)
        dark = _key(source, None)
        # Home Assistant asks for 256 and 512 on icons; logos are capped at 256 high and this
        # source is 75, so its natural size is kept rather than blown up for the sake of a number.
        heights = (256, 512) if square else (original.height, original.height * 2)
        for image, prefix in ((light, ""), (dark, "dark_")):
            _save(image, f"{prefix}{stem}.png", heights[0], square)
            _save(image, f"{prefix}{stem}@2x.png", heights[1], square)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
