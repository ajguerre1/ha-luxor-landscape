"""The Luxor protocol layer, free of Home Assistant imports.

Kept separate so it can be tested on a machine where Home Assistant cannot be imported at all, and
so that contributing this integration to Home Assistant core -- which requires protocol code to
live in a published library -- would be a move rather than a rewrite.
"""

from .client import LuxorClient
from .colour import ColourWrite, ColourWriteError, resolve_hs, set_group_colour
from .const import (
    ALLOWED_METHODS,
    ALLOWED_READ_METHODS,
    ALLOWED_WRITE_METHODS,
    COLOUR_NONE,
    COLOUR_WHEEL_MAX,
    COLOUR_WHEEL_MIN,
    DEFAULT_PORT,
    DEFAULT_TIMEOUT,
    DENIED_METHODS,
    DMX_SENTINEL,
    INTENSITY_MAX,
    INTENSITY_MIN,
    MAX_GROUP_NAME_BYTES,
    MIN_REQUEST_GAP,
    PALETTE_MAX,
    PALETTE_MIN,
    PARAMETERLESS_METHODS,
    REQUIRED_FIELDS,
    STATUS_OK,
    STATUS_TEXT,
    STATUS_UNKNOWN_METHOD,
    is_static_colour,
)
from .errors import (
    ColourRangeError,
    EmptyBodyError,
    GroupNameError,
    IntensityRangeError,
    LuxorConnectionError,
    LuxorError,
    LuxorStatusError,
    MethodNotAllowedError,
)
from .model import Colour, Group, Theme, ThemeGroup, normalise_hue
from .slots import SlotAllocationError, SlotClaim, SlotProblem, SlotTable, revalidate

__all__ = [
    "ALLOWED_METHODS",
    "ALLOWED_READ_METHODS",
    "ALLOWED_WRITE_METHODS",
    "COLOUR_NONE",
    "COLOUR_WHEEL_MAX",
    "COLOUR_WHEEL_MIN",
    "DEFAULT_PORT",
    "DEFAULT_TIMEOUT",
    "DENIED_METHODS",
    "DMX_SENTINEL",
    "INTENSITY_MAX",
    "INTENSITY_MIN",
    "MAX_GROUP_NAME_BYTES",
    "MIN_REQUEST_GAP",
    "PALETTE_MAX",
    "PALETTE_MIN",
    "PARAMETERLESS_METHODS",
    "REQUIRED_FIELDS",
    "STATUS_OK",
    "STATUS_TEXT",
    "STATUS_UNKNOWN_METHOD",
    "Colour",
    "ColourRangeError",
    "ColourWrite",
    "ColourWriteError",
    "EmptyBodyError",
    "Group",
    "GroupNameError",
    "IntensityRangeError",
    "LuxorClient",
    "LuxorConnectionError",
    "LuxorError",
    "LuxorStatusError",
    "MethodNotAllowedError",
    "SlotAllocationError",
    "SlotClaim",
    "SlotProblem",
    "SlotTable",
    "Theme",
    "ThemeGroup",
    "is_static_colour",
    "normalise_hue",
    "resolve_hs",
    "revalidate",
    "set_group_colour",
]
