"""Config flow.

`VERSION` is pinned to 1 and the data keys match what the integration this replaces wrote, so an
existing entry is **adopted** rather than migrated. That is the whole drop-in mechanism: the entry
carries the entity ids, and it survives a HACS uninstall of the files.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_COLOUR_THEME,
    CONF_GROUP_INTERVAL,
    CONF_HOST,
    CONF_THEME_INTERVAL,
    CONFIG_VERSION,
    DEFAULT_COLOUR_THEME,
    DEFAULT_GROUP_INTERVAL,
    DEFAULT_THEME_INTERVAL,
    DOMAIN,
)
from .luxor import LuxorClient, LuxorError

_LOGGER = logging.getLogger(__name__)

SCHEMA = vol.Schema({vol.Required(CONF_HOST): cv.string})


class LuxorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up a Luxor controller."""

    VERSION = CONFIG_VERSION

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST]
            client = LuxorClient(host, async_get_clientsession(self.hass))
            try:
                name = await client.controller_name()
            except LuxorError as err:
                _LOGGER.debug("Cannot reach a Luxor controller at %s: %s", host, err)
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(name)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=name,
                    data={
                        CONF_HOST: host,
                        CONF_GROUP_INTERVAL: DEFAULT_GROUP_INTERVAL,
                        CONF_THEME_INTERVAL: DEFAULT_THEME_INTERVAL,
                    },
                )
        return self.async_show_form(step_id="user", data_schema=SCHEMA, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        return LuxorOptionsFlow()


class LuxorOptionsFlow(OptionsFlow):
    """Poll intervals, and which theme colour writes target."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        data = self.config_entry.data
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_GROUP_INTERVAL,
                    default=options.get(
                        CONF_GROUP_INTERVAL, data.get(CONF_GROUP_INTERVAL, DEFAULT_GROUP_INTERVAL)
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=10, max=3600)),
                vol.Required(
                    CONF_THEME_INTERVAL,
                    default=options.get(
                        CONF_THEME_INTERVAL, data.get(CONF_THEME_INTERVAL, DEFAULT_THEME_INTERVAL)
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=30, max=7200)),
                # Every group belongs to at least two themes on a typical system, so the target
                # cannot be inferred -- "refuse when ambiguous" would refuse every group. It is a
                # setting, defaulting to the display theme, and the alarm themes are never written
                # unless named here deliberately.
                vol.Required(
                    CONF_COLOUR_THEME,
                    default=options.get(CONF_COLOUR_THEME, DEFAULT_COLOUR_THEME),
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=25)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
