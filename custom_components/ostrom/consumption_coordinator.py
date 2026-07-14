"""DataUpdateCoordinator for a rolling window of Ostrom smart-meter consumption.

Separate from statistics.py: that module incrementally imports the full
history into Home Assistant's long-term statistics store (not directly
queryable from a sensor). This coordinator instead keeps the last ~week of
hourly readings in memory so the visible "today"/"this week" sensors can be
computed cheaply on every coordinator update.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import OstromApiClient, OstromApiError, OstromAuthError, OstromNoActiveContractError
from .const import (
    CONSUMPTION_RESOLUTION,
    CONSUMPTION_ROLLING_WINDOW_DAYS,
    CONSUMPTION_UPDATE_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class OstromConsumptionCoordinator(DataUpdateCoordinator[list[dict[str, Any]]]):
    """Fetch a rolling window of hourly smart-meter consumption readings."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: OstromApiClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_consumption",
            update_interval=CONSUMPTION_UPDATE_INTERVAL,
        )
        self._client = client
        self._contract_id: int | None = None

    async def _async_update_data(self) -> list[dict[str, Any]]:
        try:
            if self._contract_id is None:
                self._contract_id = await self._client.async_get_active_contract_id()

            end = dt_util.utcnow()
            start = end - timedelta(days=CONSUMPTION_ROLLING_WINDOW_DAYS)
            response = await self._client.async_get(
                f"/contracts/{self._contract_id}/energy-consumption",
                params={
                    "startDate": _iso(start),
                    "endDate": _iso(end),
                    "resolution": CONSUMPTION_RESOLUTION,
                },
            )
        except OstromNoActiveContractError as err:
            raise UpdateFailed(str(err)) from err
        except OstromAuthError as err:
            raise UpdateFailed(f"Ostrom authentication failed: {err}") from err
        except OstromApiError as err:
            raise UpdateFailed(f"Error fetching Ostrom consumption: {err}") from err

        return response.get("data") or []


def _iso(value) -> str:
    # Ostrom's docs specify this exact format, milliseconds included
    # (e.g. "2023-11-01T00:00:00.000Z") - omitting them causes a 400.
    return value.strftime("%Y-%m-%dT%H:%M:%S.000Z")
