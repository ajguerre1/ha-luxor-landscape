"""Two coordinators and one shared client.

Groups and themes poll at different rates because they change at different rates, and the intervals
match what the integration this replaces used -- 60 s and 600 s -- so the swap changes nothing
observable about polling.

Both coordinators share **one** `LuxorClient`, and therefore one lock. That is deliberate: Home
Assistant's `PARALLEL_UPDATES` semaphore is per platform, so it does not serialise `light` against
`scene`. Only the client's own lock does, and this controller refuses a second concurrent request.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import REQUEST_REFRESH_DELAY
from .luxor import Colour, Group, LuxorClient, LuxorError, Theme, ThemeGroup

_LOGGER = logging.getLogger(__name__)


class LuxorGroupCoordinator(DataUpdateCoordinator[dict[int, Group]]):
    """The light groups, and the palette needed to report their colour.

    The palette is fetched here rather than per light because it is one request for all 65 entities
    and it changes only when this integration changes it.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: LuxorClient, interval: int):
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name="luxor_groups",
            update_interval=timedelta(seconds=interval),
            request_refresh_debouncer=Debouncer(
                hass, _LOGGER, cooldown=REQUEST_REFRESH_DELAY, immediate=True
            ),
        )
        self.client = client
        self.colours: dict[int, tuple[float, float]] = {}

    async def _async_update_data(self) -> dict[int, Group]:
        try:
            groups = await self.client.group_list()
            self.colours = {colour.index: colour.hs for colour in await self.client.colour_list()}
        except LuxorError as err:
            raise UpdateFailed(str(err)) from err
        return {group.number: group for group in groups}


class LuxorThemeCoordinator(DataUpdateCoordinator[dict[int, Theme]]):
    """The themes, and their per-group membership.

    Membership is fetched because it is where colour lives, and because a colour write needs to
    know whether the group it is about to paint is even in the target theme.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: LuxorClient, interval: int):
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name="luxor_themes",
            update_interval=timedelta(seconds=interval),
            request_refresh_debouncer=Debouncer(
                hass, _LOGGER, cooldown=REQUEST_REFRESH_DELAY, immediate=True
            ),
        )
        self.client = client
        self.membership: dict[int, list[ThemeGroup]] = {}
        self.restricted = False

    async def _async_update_data(self) -> dict[int, Theme]:
        try:
            themes = await self.client.theme_list()
            membership: dict[int, list[ThemeGroup]] = {}
            for theme in themes:
                membership[theme.index] = await self.client.theme_groups(theme.index)
        except LuxorError as err:
            raise UpdateFailed(str(err)) from err
        self.membership = membership
        return {theme.index: theme for theme in themes}


async def async_fetch_palette(client: LuxorClient) -> list[Colour]:
    """The palette as objects, for slot allocation rather than for display."""
    return await client.colour_list()
