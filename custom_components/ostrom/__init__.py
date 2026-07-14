"""The Ostrom integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import OstromApiClient
from .const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, CONF_ENVIRONMENT, DOMAIN
from .consumption_coordinator import OstromConsumptionCoordinator
from .coordinator import OstromSpotPriceCoordinator
from .statistics import async_start_consumption_import

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Ostrom from a config entry."""
    client = OstromApiClient(
        async_get_clientsession(hass),
        entry.data[CONF_CLIENT_ID],
        entry.data[CONF_CLIENT_SECRET],
        entry.data[CONF_ENVIRONMENT],
    )

    price_coordinator = OstromSpotPriceCoordinator(hass, entry, client)
    await price_coordinator.async_config_entry_first_refresh()

    consumption_coordinator = OstromConsumptionCoordinator(hass, entry, client)
    await consumption_coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "prices": price_coordinator,
        "consumption": consumption_coordinator,
    }

    entry.async_on_unload(async_start_consumption_import(hass, entry, client))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
