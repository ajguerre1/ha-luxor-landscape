"""One light entity per Luxor group.

Brightness behaviour is deliberately identical to the integration this replaces, because a swap
that also changed how a dimmer responds would be two changes wearing one coat. Colour is the new
part, and it is written into the theme rather than onto the group -- see `luxor/colour.py`.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_HS_COLOR, ColorMode, LightEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import LuxorConfigEntry
from .const import (
    CONF_COLOUR_THEME,
    DEFAULT_COLOUR_THEME,
    DEVICE_LIGHT_NAMESPACE,
    DOMAIN,
    MANUFACTURER,
)
from .luxor import Group, LuxorError, resolve_hs, set_group_colour

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


class LuxorLight(LightEntity):
    """A Luxor light group."""

    _attr_has_entity_name = False
    _attr_should_poll = False

    def __init__(self, data, entry: LuxorConfigEntry, group_number: int) -> None:
        self._data = data
        self._entry = entry
        self._group_number = group_number

        # Reproduced exactly. Change this and 65 entities are orphaned and recreated with a `_2`
        # suffix, which would also silently drop them out of the Landscape Lights group helper.
        self._attr_unique_id = f"LUXOR_LIGHT_{group_number}"

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
            # `luxor_light` is not the integration domain and the id is an int. Both are off-spec
            # and both are reproduced, because that is what keeps the existing 65 devices.
            identifiers={(DEVICE_LIGHT_NAMESPACE, self._group_number)},
            manufacturer=MANUFACTURER,
            name=self.name,
            via_device=(DOMAIN, self._data.controller),
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

    async def _call(self, coro) -> None:
        try:
            await coro
        except LuxorError as err:
            raise HomeAssistantError(f"{self.name}: {err}") from err
        await self._data.groups.async_request_refresh()

    # --- coordinator wiring --------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._data.groups.async_add_listener(self.async_write_ha_state))
