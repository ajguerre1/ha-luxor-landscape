"""Diagnostics.

Everything here is chosen to answer the questions this integration actually gets asked: which
palette slot does a group own, does the theme agree with it, and is the slot table still valid.

The host is redacted. On this hardware the group names are the plants and locations of a specific
property, so they are redacted too and replaced with their length -- which is the only thing about a
name that matters to the protocol, because the controller caps it at 19 bytes.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import LuxorConfigEntry
from .const import CONF_HOST

TO_REDACT = {CONF_HOST, "host", "unique_id"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: LuxorConfigEntry
) -> dict[str, Any]:
    data = entry.runtime_data
    groups = data.groups.data or {}
    themes = data.themes.data or {}

    return {
        "entry": {
            "version": entry.version,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "controller": {
            "name": data.controller,
            "colour_capable": data.controller.lower().startswith(("lxzdc", "lxtwo")),
            "themes_restricted": data.themes.restricted,
        },
        "counts": {
            "groups": len(groups),
            "themes": len(themes),
            "palette_entries": len(data.groups.colours),
            "slot_claims": len(data.slots),
        },
        "colour_writable": data.colour_writable,
        "groups": [
            {
                "number": group.number,
                "name_length": len(group.name.encode("utf-8")),
                "intensity": group.intensity,
                "colr": group.colr,
                "static_colour": group.has_static_colour,
                "colour_wheel": group.is_colour_wheel,
                "dmx": group.is_dmx,
                "hs": data.groups.colours.get(group.colr),
                "claimed_slot": data.slots.slot_for(group.number),
            }
            for group in sorted(groups.values(), key=lambda g: g.number)
        ],
        "themes": [
            {
                "index": theme.index,
                "name_length": len(theme.name.encode("utf-8")),
                "on": theme.on,
                "members": len(data.themes.membership.get(theme.index, [])),
                "colours_used": sorted(
                    {e.colour for e in data.themes.membership.get(theme.index, [])}
                ),
            }
            for theme in sorted(themes.values(), key=lambda t: t.index)
        ],
        # The palette by index, without the names that reference it -- enough to see whether a slot
        # this integration claimed still means what it wrote.
        "palette": dict(sorted(data.groups.colours.items())),
    }
