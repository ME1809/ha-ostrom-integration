"""DataUpdateCoordinator for Ostrom spot prices."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import OstromApiClient, OstromApiError, OstromAuthError
from .const import (
    CONF_ZIP_CODE,
    DOMAIN,
    SPOT_PRICE_RESOLUTION,
    SPOT_PRICE_UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class OstromSpotPriceCoordinator(DataUpdateCoordinator[list[dict[str, Any]]]):
    """Fetch and cache Ostrom spot prices."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: OstromApiClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=SPOT_PRICE_UPDATE_INTERVAL,
        )
        self._client = client
        self._zip_code = entry.data[CONF_ZIP_CODE]

    async def _async_update_data(self) -> list[dict[str, Any]]:
        start = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
        # Ostrom publishes next-day prices from ~14:00; ask for a wide-enough
        # window and simply use whatever the API has actually published.
        end = start + timedelta(hours=48)
        try:
            response = await self._client.async_get(
                "/spot-prices",
                params={
                    "startDate": _iso(start),
                    "endDate": _iso(end),
                    "resolution": SPOT_PRICE_RESOLUTION,
                    # zip is technically optional, but omitting it makes Ostrom
                    # return base price/gridFees/tax/levies as zero - always pass it.
                    "zip": self._zip_code,
                },
            )
        except OstromAuthError as err:
            raise UpdateFailed(f"Ostrom authentication failed: {err}") from err
        except OstromApiError as err:
            raise UpdateFailed(f"Error fetching Ostrom spot prices: {err}") from err

        data = response.get("data") or []
        if not data:
            raise UpdateFailed("Ostrom returned no spot price data")
        return data


def _iso(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")
