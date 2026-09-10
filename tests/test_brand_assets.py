"""The brand images, measured rather than merely present.

A custom integration's icon comes from its own `brand/` directory; `home-assistant/brands` refuses
pull requests for custom components, so there is no upstream review and a broken icon simply ships.

The failure worth guarding is not a missing file, which is obvious. It is a **regeneration that
inverts or flattens the ink** -- the `dark_` variants exist precisely because the source marks are
white-on-navy, and white lettering on Home Assistant's light card measures 1.07:1 against it, which
is invisible. That reads as "no icon" rather than as a bug.
"""

from __future__ import annotations

from pathlib import Path

import pytest

BRAND = Path(__file__).resolve().parents[1] / "custom_components" / "luxor" / "brand"

#: Home Assistant's actual card colours, as luminance.
LIGHT_CARD = 250
DARK_CARD = 28

#: WCAG AA for large text. These are logos rather than body copy, but it is a defensible floor and
#: the real assets clear it by a wide margin -- so a failure here means something genuinely broke.
MIN_CONTRAST = 4.5

EXPECTED = {
    "icon.png": (256, 256),
    "icon@2x.png": (512, 512),
    "dark_icon.png": (256, 256),
    "dark_icon@2x.png": (512, 512),
}
WIDE = ("logo.png", "logo@2x.png", "dark_logo.png", "dark_logo@2x.png")


def _ink(name: str):
    from PIL import Image

    image = Image.open(BRAND / name).convert("RGBA")
    pixels = image.load()
    ink = [
        (r, g, b)
        for y in range(image.height)
        for x in range(image.width)
        for r, g, b, a in [pixels[x, y]]
        if a > 200
    ]
    luminance = sum(0.2126 * r + 0.7152 * g + 0.0722 * b for r, g, b in ink) / len(ink)
    return image, luminance, len(ink) / (image.width * image.height)


def _contrast(a: float, b: float) -> float:
    lo, hi = sorted(((a + 0.05) / 255, (b + 0.05) / 255))
    return hi / lo


@pytest.mark.parametrize("name", [*EXPECTED, *WIDE])
def test_every_brand_file_exists_and_is_not_empty(name):
    path = BRAND / name
    assert path.exists(), f"{name} is missing; run scripts/make_brand_assets.py"
    assert path.stat().st_size > 500, f"{name} is suspiciously small"


@pytest.mark.parametrize(("name", "size"), EXPECTED.items())
def test_icons_are_the_sizes_home_assistant_asks_for(name, size):
    from PIL import Image

    assert Image.open(BRAND / name).size == size


@pytest.mark.parametrize("name", [*EXPECTED, *WIDE])
def test_the_background_was_keyed_out(name):
    """Fully-opaque everywhere means the navy card is still baked in."""
    image, _, coverage = _ink(name)
    assert image.mode == "RGBA"
    assert 0.02 < coverage < 0.60, (
        f"{name} has {coverage:.1%} opaque pixels; the mark should be a minority of the canvas "
        "with the background transparent"
    )


@pytest.mark.parametrize(
    ("name", "card", "which"),
    [
        ("icon.png", LIGHT_CARD, "light"),
        ("logo.png", LIGHT_CARD, "light"),
        ("dark_icon.png", DARK_CARD, "dark"),
        ("dark_logo.png", DARK_CARD, "dark"),
    ],
)
def test_each_variant_is_legible_on_its_own_card(name, card, which):
    _, luminance, _ = _ink(name)
    contrast = _contrast(luminance, card)
    assert contrast >= MIN_CONTRAST, (
        f"{name} measures {contrast:.2f}:1 on the {which} card. The polarity is probably inverted."
    )


def test_the_polarities_are_actually_opposite():
    """The disarmed control for the test above.

    Legibility passing on both cards would also pass if the generator had written the *same* image
    to both names. What makes the pair meaningful is that one is dark ink and one is light.
    """
    _, light_ink, light_cov = _ink("icon.png")
    _, dark_ink, dark_cov = _ink("dark_icon.png")
    assert light_ink < 128 < dark_ink, (
        f"icon.png ink is {light_ink:.0f} and dark_icon.png is {dark_ink:.0f}; they should sit on "
        "opposite sides of mid-grey"
    )
    # Only the colour changes. Identical coverage is what proves the geometry was untouched.
    assert abs(light_cov - dark_cov) < 0.005


def test_the_white_mark_really_would_be_invisible_on_a_light_card():
    """Why `dark_` files exist at all, as a number rather than an assertion in a comment."""
    _, luminance, _ = _ink("dark_icon.png")
    assert _contrast(luminance, LIGHT_CARD) < 1.5
