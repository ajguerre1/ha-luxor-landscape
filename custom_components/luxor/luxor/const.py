"""Protocol constants for the FX Luminaire Luxor controller.

Every value here was measured against a live ZDTWO on 2026-09-09 unless marked otherwise. Where a
published source and the hardware disagree, the hardware wins and the disagreement is noted.
"""

from __future__ import annotations

from typing import Final

#: The controller speaks plain HTTP. It has no TLS listener, which is why the integration this one
#: replaces emitted two blocking-call warnings per boot building an SSL context it never used.
DEFAULT_PORT: Final = 80

#: One request at a time. A second parallel request is refused by the controller, and the
#: integration this replaces worked around it with `connection_pool_maxsize = 1`.
MAX_IN_FLIGHT: Final = 1

#: Minimum spacing between requests. The reference Homebridge implementation uses 50 ms.
MIN_REQUEST_GAP: Final = 0.05

#: Per-request timeout. Deliberately NOT the 750 ms the Homebridge plugin uses: that is too tight
#: for a 65-row GroupListGet or a 78-row ColorListGet on this controller.
DEFAULT_TIMEOUT: Final = 5.0

# --- Status codes -------------------------------------------------------------------------------
# Observed or documented. 0 and 1 are the load-bearing pair: 1 is how a method's absence is
# detected, and it is what `SetHueSat.json` returns, which is how the candidate integration's
# colour support was found to be non-functional.
STATUS_OK: Final = 0
STATUS_UNKNOWN_METHOD: Final = 1
STATUS_UNPARSEABLE: Final = 101
STATUS_INVALID_REQUEST: Final = 102
STATUS_COLOUR_OUT_OF_RANGE: Final = 151
STATUS_PRECONDITION_FAILED: Final = 201
STATUS_GROUP_NAME_IN_USE: Final = 202
STATUS_GROUP_NUMBER_IN_USE: Final = 205
STATUS_ITEM_DOES_NOT_EXIST: Final = 241
STATUS_BAD_GROUP_NUMBER: Final = 242
STATUS_THEME_INDEX_OUT_OF_RANGE: Final = 243
STATUS_BAD_THEME_INDEX: Final = 251
STATUS_THEME_CHANGES_RESTRICTED: Final = 252

STATUS_TEXT: Final[dict[int, str]] = {
    STATUS_OK: "Ok",
    STATUS_UNKNOWN_METHOD: "Unknown method",
    STATUS_UNPARSEABLE: "Unparseable request",
    STATUS_INVALID_REQUEST: "Invalid request",
    STATUS_COLOUR_OUT_OF_RANGE: "Colour value out of range",
    STATUS_PRECONDITION_FAILED: "Precondition failed",
    STATUS_GROUP_NAME_IN_USE: "Group name in use",
    STATUS_GROUP_NUMBER_IN_USE: "Group number in use",
    STATUS_ITEM_DOES_NOT_EXIST: "Item does not exist",
    STATUS_BAD_GROUP_NUMBER: "Bad group number",
    STATUS_THEME_INDEX_OUT_OF_RANGE: "Theme index out of range",
    STATUS_BAD_THEME_INDEX: "Bad theme index",
    STATUS_THEME_CHANGES_RESTRICTED: "Theme changes restricted",
}

# --- The method allowlist -----------------------------------------------------------------------
# This is the most important constant in the package, and it exists because of a real incident.
#
# On 2026-09-09 a method-existence probe posted empty JSON bodies to twelve endpoint names on the
# assumption that all would be rejected. Nine were. `IlluminateAll`, `ExtinguishAll` and
# `GroupListDelete` accept an empty body and EXECUTE, because a method with no required parameters
# has nothing to be missing -- the probe IS the command. All 65 landscape lights went to full and
# back off, and every group's colour assignment was destroyed.
#
# So the client refuses to emit anything not named here, and refuses an empty body for any method
# that declares required fields. See PARAMETERLESS_METHODS for the deliberate exceptions.

#: Reads. Safe to call at any time.
ALLOWED_READ_METHODS: Final[frozenset[str]] = frozenset(
    {
        "ControllerName",
        "GroupListGet",
        "ThemeListGet",
        "ThemeGet",
        "ColorListGet",
        "ColorWheelListGet",
    }
)

#: Writes. Each one changes the physical lighting or the controller's stored programme.
ALLOWED_WRITE_METHODS: Final[frozenset[str]] = frozenset(
    {
        "IlluminateGroup",
        "IlluminateTheme",
        "ExtinguishAll",
        "ColorListSet",
        "GroupListEdit",
        "ThemeSet",
    }
)

ALLOWED_METHODS: Final[frozenset[str]] = ALLOWED_READ_METHODS | ALLOWED_WRITE_METHODS

#: The methods that legitimately take no parameters.
#:
#: "Never send an empty body" would be the obvious rule and it is the wrong one -- it would block
#: GroupListGet, which is the integration's main read. The real rule is narrower and stricter: an
#: empty body is permitted ONLY for a method named here, and every other method must supply every
#: required field before anything is sent. That is what makes an accidental command impossible,
#: because the accident was never "an empty body" as such -- it was an empty body reaching a method
#: whose parameters were all optional.
PARAMETERLESS_METHODS: Final[frozenset[str]] = frozenset(
    {
        "ControllerName",
        "GroupListGet",
        "ThemeListGet",
        "ColorListGet",
        "ColorWheelListGet",
        "ExtinguishAll",
    }
)

#: Required fields, validated client-side before a request is built. The controller treats a
#: missing field as a default rather than an error on at least three methods, so waiting for its
#: opinion is not a validation strategy.
REQUIRED_FIELDS: Final[dict[str, frozenset[str]]] = {
    "ThemeGet": frozenset({"ThemeIndex"}),
    "ThemeSet": frozenset({"ThemeIndex", "Groups"}),
    "ColorListSet": frozenset({"C", "Hue", "Sat"}),
    "GroupListEdit": frozenset({"Name", "GroupNumber", "Color"}),
    "IlluminateGroup": frozenset({"GroupNumber", "Intensity"}),
    "IlluminateTheme": frozenset({"ThemeIndex", "OnOff"}),
}

#: Named so the refusal can say *why*, rather than "unknown method". A denied method is a
#: deliberate exclusion, not a gap, and the message should not invite someone to add it.
DENIED_METHODS: Final[dict[str, str]] = {
    "IlluminateAll": (
        "sets every group to Colr 0 at Inten 75, destroying the colour assignment of all groups. "
        "Measured in isolation on 2026-09-09. There is no sanctioned all-on; the manual states the "
        "physical control is off-only. Use ExtinguishAll for all-off."
    ),
    "GroupListDelete": (
        "deletes a light group. This integration controls lighting; it does not administer "
        "the controller."
    ),
    "GroupListAdd": "creates a light group. Administration, not control.",
    "GroupListClear": "erases every light group. Administration, not control.",
    "GroupListReorder": "renumbers groups, which invalidates every stored palette-slot claim.",
    "GroupListRename": (
        "renames a group. GroupListEdit already carries a name and is guarded; a second rename "
        "path is not needed."
    ),
    "ThemeListAdd": "creates a theme. Administration, not control.",
    "ThemeListDelete": "deletes a theme. Administration, not control.",
    "ThemeListClear": "erases every theme, including the nightly display and both alarm themes.",
    "ThemeListRename": (
        "renames a theme. Scene unique_ids derive from theme names, so renaming would orphan "
        "entities."
    ),
    "ThemeListReorder": "renumbers themes, which invalidates every stored theme index.",
    "ThemeClear": "empties a theme's group membership.",
    "FlashLights": "a commissioning aid. Nothing in Home Assistant should trigger it.",
}

# --- Ranges -------------------------------------------------------------------------------------
INTENSITY_MIN: Final = 0
INTENSITY_MAX: Final = 100

#: The controller reports hue up to 360 while the documented device range is 0-359 and Home
#: Assistant expects a half-open [0, 360). Normalise on read or the entity flaps between the value
#: written and the value read back.
HUE_MIN: Final = 0
HUE_MAX: Final = 360
SATURATION_MIN: Final = 0
SATURATION_MAX: Final = 100

#: Group names are a unique key on the controller and are capped in BYTES, not characters, so a
#: multi-byte character can be truncated mid-sequence.
MAX_GROUP_NAME_BYTES: Final = 19

#: Palette slots. 1-250 are colours; 0 means the group is configured as non-colour fixtures, which
#: is NOT the same as "no colour chosen".
COLOUR_NONE: Final = 0
PALETTE_MIN: Final = 1
PALETTE_MAX: Final = 250

#: 251-260 are animated colour wheels and 65535 means the group is under DMX control. Neither is a
#: static colour. No group on the reference controller uses either, and all ten wheel slots are
#: empty, so this is a guard rather than a feature.
COLOUR_WHEEL_MIN: Final = 251
COLOUR_WHEEL_MAX: Final = 260
DMX_SENTINEL: Final = 65535


def is_static_colour(colr: int) -> bool:
    """Whether `colr` is a palette index that resolves to one hue and saturation."""
    return PALETTE_MIN <= colr <= PALETTE_MAX
