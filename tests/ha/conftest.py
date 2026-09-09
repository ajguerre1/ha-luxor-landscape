"""Fixtures for the Home Assistant half of the suite.

These run in CI only. Home Assistant cannot be imported on Windows (`homeassistant.runner` imports
POSIX-only `fcntl`), and the top-level conftest skips this directory wherever it is not installed.

The **same** `FakeSession` backs these tests as the offline ones. A second, divergent double is how
two descriptions of one device drift apart until neither is the device.

The config entry is built to match what the integration being replaced actually wrote: `VERSION 1`,
`unique_id: None`, and the data keys `{host, group_interval, theme_interval}`. That is not
convenience -- it is the thing under test. If setup only works against an entry this project
created, the drop-in claim is untested.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.luxor.const import (
    CONF_GROUP_INTERVAL,
    CONF_HOST,
    CONF_THEME_INTERVAL,
    DOMAIN,
)

#: A documentation-range address (RFC 5737). Not a real one -- a test that quietly reached a real
#: landscape controller would be a very bad way to find out the double was not wired in.
HOST = "192.0.2.10"

#: Exactly what the integration being replaced wrote. Any extra key here would weaken the test.
LEGACY_ENTRY_DATA = {
    CONF_HOST: HOST,
    CONF_GROUP_INTERVAL: 60,
    CONF_THEME_INTERVAL: 600,
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Home Assistant will not load a custom component in tests without this."""
    return


@pytest.fixture
def legacy_entry(hass: HomeAssistant) -> MockConfigEntry:
    """An entry shaped like the one already on the live system."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=LEGACY_ENTRY_DATA,
        options={},
        version=1,
        unique_id=None,
        title="FXLuxor Controller",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
async def setup_entry(hass: HomeAssistant, session, legacy_entry: MockConfigEntry):
    """Set the integration up against the shared double."""

    async def _setup(entry: MockConfigEntry | None = None) -> MockConfigEntry:
        target = entry or legacy_entry
        with (
            patch("custom_components.luxor.async_get_clientsession", return_value=session),
            patch(
                "custom_components.luxor.config_flow.async_get_clientsession",
                return_value=session,
            ),
        ):
            assert await hass.config_entries.async_setup(target.entry_id)
            await hass.async_block_till_done()
        return target

    return _setup
