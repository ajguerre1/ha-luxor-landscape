"""One light entity per Luxor group.

Brightness behaviour is deliberately identical to the integration this replaces, because a swap
that also changed how a dimmer responds would be two changes wearing one coat. Colour is the new
part, and it is written into the theme rather than onto the group -- see `luxor/colour.py`.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import voluptuous as vol
from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_HS_COLOR, ColorMode, LightEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_platform
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import LuxorConfigEntry
from .const import (
    CONF_COLOUR_THEME,
    DEFAULT_COLOUR_THEME,
    MANUFACTURER,
    light_device_identifier,
    light_unique_id,
)
from .luxor import Group, LuxorError, ThemeGroup, resolve_hs, set_group_colour

#: Answers two questions at once, which is why it is one service and not two.
#:
#: Q2 -- which theme does a colour write target? Per entry by default; this takes an optional
#: `theme_index`, so a single light can be pointed at a different theme without a per-entity
#: setting that most people would never touch.
#:
#: Q3 -- brightness turned out to be transient in exactly the way colour was: theme 0 stores
#: `Intensity: 100` for all 65 groups, so activating it overwrites whatever Home Assistant set.
#: Measured, not assumed. Making every brightness change durable was rejected: a slider drag would
#: rewrite the whole 65-group theme on every step. So brightness stays transient by default and
#: becomes durable only when asked for, which is what this service is.
SERVICE_SAVE_TO_THEME = "save_to_theme"
ATTR_THEME_INDEX = "theme_index"

_LOGGER = logging.getLogger(__name__)

#: The controller refuses a second concurrent request. This is per platform, so it does not
#: serialise `light` against `scene` -- only the client's own lock does that -- but it keeps Home
#: Assistant from starting 65 coroutines that all immediately block.
PARALLEL_UPDATES = 1


def intensity_to_brightness(intensity: int) -> int:
    return round(255 * intensity / 100)


def brightness_to_intensity(brightness: int) -> int:
    """Map Home Assistant's 0-255 onto the controller's 0-100, without turning a light off.

    Clamped to at least 1 when turning on. The integration this replaces rounds `brightness=1` to
    intensity 0, so the dimmest possible request switches the light off instead.
    """
    return max(1, round(100 * brightness / 255))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LuxorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    data = entry.runtime_data
    known: dict[int, LuxorLight] = {}

    @callback
    def _sync() -> None:
        """Add and remove entities as the controller's group list changes.

        A new group appears without a reload, which the integration this replaces cannot do.
        """
        new = [
            known.setdefault(number, LuxorLight(data, entry, number))
            for number in data.groups.data
            if number not in known
        ]
        if new:
            async_add_entities(new)

    _sync()
    entry.async_on_unload(data.groups.async_add_listener(_sync))

    entity_platform.async_get_current_platform().async_register_entity_service(
        SERVICE_SAVE_TO_THEME,
        {vol.Optional(ATTR_THEME_INDEX): vol.All(vol.Coerce(int), vol.Range(min=0, max=25))},
        "async_save_to_theme",
    )


class LuxorLight(LightEntity):
    """A Luxor light group."""

    _attr_has_entity_name = False
    _attr_should_poll = False

    def __init__(self, data, entry: LuxorConfigEntry, group_number: int) -> None:
        self._data = data
        self._entry = entry
        self._group_number = group_number

        # Controller-scoped from version 2. The previous scheme, `LUXOR_LIGHT_{n}`, was adopted
        # verbatim through the swap so nothing moved, then converted in place by `migrate.py` --
        # which preserves the entity_id, and therefore the `light.landscape_lights` group
        # membership that holds these ids as plain strings.
        self._attr_unique_id = light_unique_id(data.controller, group_number)

        colour_capable = data.controller.lower().startswith(("lxzdc", "lxtwo"))
        mode = ColorMode.HS if colour_capable else ColorMode.BRIGHTNESS
        self._attr_color_mode = mode
        self._attr_supported_color_modes = {mode}

    # --- identity ------------------------------------------------------------------------------

    @property
    def _group(self) -> Group | None:
        return self._data.groups.data.get(self._group_number)

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={light_device_identifier(self._data.controller, self._group_number)},
            manufacturer=MANUFACTURER,
            name=self.name,
            # `via_device_id`, not `via_device`. The latter is gone from DeviceInfo in 2026.9 and
            # emits a deprecation dated 2027.8.0 -- which is the defect this integration replaced
            # the old one partly to fix, and which it reproduced until the live cutover showed it.
            via_device_id=self._data.controller_device_id,
        )

    @property
    def name(self) -> str | None:
        group = self._group
        return group.name if group else None

    @property
    def available(self) -> bool:
        return self._data.groups.last_update_success and self._group is not None

    # --- state ---------------------------------------------------------------------------------

    @property
    def is_on(self) -> bool:
        group = self._group
        return bool(group and group.is_on)

    @property
    def brightness(self) -> int | None:
        group = self._group
        return intensity_to_brightness(group.intensity) if group else None

    @property
    def hs_color(self) -> tuple[float, float] | None:
        """The colour the controller has, not the colour we last asked for.

        When a theme repaints a group this changes to match. That is what makes the design's
        no-op visible: if it is working, the nightly theme changes nothing here.
        """
        group = self._group
        if group is None or self._attr_color_mode is not ColorMode.HS:
            return None
        return resolve_hs(group, self._data.groups.colours)

    # --- commands ------------------------------------------------------------------------------

    async def async_turn_on(self, **kwargs: Any) -> None:
        if ATTR_HS_COLOR in kwargs:
            await self._async_set_colour(*kwargs[ATTR_HS_COLOR])

        if ATTR_BRIGHTNESS in kwargs:
            intensity = brightness_to_intensity(kwargs[ATTR_BRIGHTNESS])
        elif self.is_on:
            # Colour-only change on a lit group: leave the brightness where it is rather than
            # jumping it to full.
            intensity = self._group.intensity if self._group else 100
        else:
            intensity = 100

        await self._call(self._data.client.illuminate_group(self._group_number, intensity))

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._call(self._data.client.illuminate_group(self._group_number, 0))

    async def _async_set_colour(self, hue: float, saturation: float) -> None:
        if not self._data.colour_writable:
            raise HomeAssistantError(
                "Luxor colour writing is disabled because a palette-slot claim no longer matches "
                "the controller. See the repair issue for details."
            )
        theme = self._entry.options.get(CONF_COLOUR_THEME, DEFAULT_COLOUR_THEME)
        now: datetime = dt_util.utcnow()
        try:
            await set_group_colour(
                self._data.client,
                self._data.slots,
                group_number=self._group_number,
                hue=round(hue),
                saturation=round(saturation),
                theme_index=theme,
                now=now.isoformat(),
            )
        except LuxorError as err:
            raise HomeAssistantError(f"could not set the colour of {self.name}: {err}") from err
        await self._data.async_persist_slots()

    async def async_save_to_theme(self, theme_index: int | None = None) -> None:
        """Write this group's CURRENT brightness and colour into a theme, so they persist.

        Both are otherwise transient: a theme stores its own per-group intensity and colour and
        re-applies both on activation, which on this system happens every evening. Colour set
        through `light.turn_on` is written to the theme already; brightness is not, deliberately.

        Reads the group fresh rather than trusting the coordinator's cache, because the value being
        made permanent should be the one the controller actually has.
        """
        theme = (
            theme_index
            if theme_index is not None
            else self._entry.options.get(CONF_COLOUR_THEME, DEFAULT_COLOUR_THEME)
        )
        try:
            group = next(
                (g for g in await self._data.client.group_list() if g.number == self._group_number),
                None,
            )
            if group is None:
                raise HomeAssistantError(f"group {self._group_number} is not on the controller")

            entries = await self._data.client.theme_groups(theme)
            if not any(e.number == self._group_number for e in entries):
                raise HomeAssistantError(
                    f"{self.name} is not a member of theme {theme}, so saving to it would never "
                    "be applied"
                )
            updated = [
                ThemeGroup(number=e.number, intensity=group.intensity, colour=group.colr)
                if e.number == self._group_number
                else e
                for e in entries
            ]
            await self._data.client.set_theme_groups(theme, updated)
        except LuxorError as err:
            raise HomeAssistantError(f"could not save {self.name} to theme {theme}: {err}") from err

        _LOGGER.info(
            "Saved %s to theme %d at intensity %d, colour %d",
            self.name,
            theme,
            group.intensity,
            group.colr,
        )
        await self._data.themes.async_request_refresh()

    async def _call(self, coro) -> None:
        try:
            await coro
        except LuxorError as err:
            raise HomeAssistantError(f"{self.name}: {err}") from err
        await self._data.groups.async_request_refresh()

    # --- coordinator wiring --------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._data.groups.async_add_listener(self.async_write_ha_state))
