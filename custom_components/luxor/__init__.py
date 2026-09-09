"""FX Luminaire Luxor landscape lighting."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_GROUP_INTERVAL,
    CONF_HOST,
    CONF_THEME_INTERVAL,
    DEFAULT_GROUP_INTERVAL,
    DEFAULT_THEME_INTERVAL,
    DOMAIN,
    MANUFACTURER,
    PLATFORMS,
)
from .coordinator import LuxorGroupCoordinator, LuxorThemeCoordinator
from .data import LuxorData
from .luxor import LuxorClient, LuxorError
from .store import SlotStore

_LOGGER = logging.getLogger(__name__)

type LuxorConfigEntry = ConfigEntry[LuxorData]


async def async_setup_entry(hass: HomeAssistant, entry: LuxorConfigEntry) -> bool:
    """Adopt the entry and bring the controller up."""
    host = entry.data[CONF_HOST]
    client = LuxorClient(host, async_get_clientsession(hass))

    try:
        controller = await client.controller_name()
    except LuxorError as err:
        # Not `return False`. A controller that is briefly unreachable at boot -- which this one
        # was four times in one recent day -- must retry rather than leave the entry failed until
        # somebody notices.
        raise ConfigEntryNotReady(f"cannot reach the Luxor controller at {host}: {err}") from err

    groups = LuxorGroupCoordinator(
        hass, entry, client, entry.data.get(CONF_GROUP_INTERVAL, DEFAULT_GROUP_INTERVAL)
    )
    themes = LuxorThemeCoordinator(
        hass, entry, client, entry.data.get(CONF_THEME_INTERVAL, DEFAULT_THEME_INTERVAL)
    )
    await groups.async_config_entry_first_refresh()
    await themes.async_config_entry_first_refresh()

    store = SlotStore(hass, entry.entry_id)
    data = LuxorData(
        client=client,
        controller=controller,
        groups=groups,
        themes=themes,
        slots=await store.async_load(),
        store=store,
    )
    entry.runtime_data = data
    data.revalidate_slots(hass)

    hub = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, controller)},
        manufacturer=MANUFACTURER,
        name=controller,
    )
    # The lights hang off this device, and they must reference it by registry id. Created before
    # the platforms are forwarded so the id exists by the time an entity asks for it.
    data.controller_device_id = hub.id

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LuxorConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: LuxorConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
