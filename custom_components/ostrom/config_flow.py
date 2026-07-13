"""Config flow for the Ostrom integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig

from .api import OstromApiClient, OstromApiError, OstromAuthError
from .const import (
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_ENVIRONMENT,
    CONF_ZIP_CODE,
    DOMAIN,
    ENV_PRODUCTION,
    ENVIRONMENTS,
)

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CLIENT_ID): str,
        vol.Required(CONF_CLIENT_SECRET): str,
        vol.Required(CONF_ZIP_CODE): str,
        vol.Required(CONF_ENVIRONMENT, default=ENV_PRODUCTION): SelectSelector(
            SelectSelectorConfig(options=ENVIRONMENTS)
        ),
    }
)


async def _async_validate(hass, user_input: dict[str, Any]) -> str | None:
    """Try to authenticate; return an error key, or None on success."""
    client = OstromApiClient(
        async_get_clientsession(hass),
        user_input[CONF_CLIENT_ID],
        user_input[CONF_CLIENT_SECRET],
        user_input[CONF_ENVIRONMENT],
    )
    try:
        await client.async_validate_credentials()
    except OstromAuthError:
        return "invalid_auth"
    except OstromApiError:
        return "cannot_connect"
    return None


class OstromConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Ostrom."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(
                f"{user_input[CONF_CLIENT_ID]}_{user_input[CONF_ZIP_CODE]}"
            )
            self._abort_if_unique_id_configured()

            error = await _async_validate(self.hass, user_input)
            if error:
                errors["base"] = error
            else:
                return self.async_create_entry(
                    title=f"Ostrom Energy ({user_input[CONF_ZIP_CODE]})",
                    data=user_input,
                )

        return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OstromOptionsFlowHandler:
        return OstromOptionsFlowHandler()


class OstromOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Ostrom options: re-enter credentials/zip/environment post-setup."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            error = await _async_validate(self.hass, user_input)
            if error:
                errors["base"] = error
            else:
                self.hass.config_entries.async_update_entry(self.config_entry, data=user_input)
                return self.async_create_entry(title="", data={})

        current = self.config_entry.data
        schema = vol.Schema(
            {
                vol.Required(CONF_CLIENT_ID, default=current[CONF_CLIENT_ID]): str,
                vol.Required(CONF_CLIENT_SECRET, default=current[CONF_CLIENT_SECRET]): str,
                vol.Required(CONF_ZIP_CODE, default=current[CONF_ZIP_CODE]): str,
                vol.Required(
                    CONF_ENVIRONMENT, default=current[CONF_ENVIRONMENT]
                ): SelectSelector(SelectSelectorConfig(options=ENVIRONMENTS)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
