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
        # Ostrom only ever publishes prices through the end of "today" (before
        # ~14:00 local) or "tomorrow" (after ~14:00 local). Requesting a fixed
        # now+48h window can reach into a third calendar day and gets rejected
        # with HTTP 400 - ask for today+tomorrow in local time instead, and
        # simply use whatever the API has actually published within that.
        today_start = dt_util.now().replace(hour=0, minute=0, second=0, microsecond=0)
        start = dt_util.as_utc(today_start)
        end = dt_util.as_utc(today_start + timedelta(days=2))
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
