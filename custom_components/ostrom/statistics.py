"""Import Ostrom smart-meter consumption into Home Assistant long-term statistics."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .api import OstromApiClient, OstromApiError, OstromAuthError
from .const import (
    CONSUMPTION_MAX_DAYS_PER_REQUEST,
    CONSUMPTION_REQUEST_CHUNK_DELAY,
    CONSUMPTION_RESOLUTION,
    CONSUMPTION_UPDATE_INTERVAL,
    DOMAIN,
    STATISTIC_ID_CONSUMPTION,
)

_LOGGER = logging.getLogger(__name__)


def async_start_consumption_import(
    hass: HomeAssistant, entry: ConfigEntry, client: OstromApiClient
) -> CALLBACK_TYPE:
    """Kick off an immediate import and schedule periodic re-imports.

    Returns an unsub callback suitable for entry.async_on_unload.
    """

    async def _run(_now=None) -> None:
        await _async_import_once(hass, entry, client)

    hass.async_create_task(_run())
    return async_track_time_interval(hass, _run, CONSUMPTION_UPDATE_INTERVAL)


async def _async_import_once(
    hass: HomeAssistant, entry: ConfigEntry, client: OstromApiClient
) -> None:
    try:
        contracts_response = await client.async_get("/contracts")
    except (OstromAuthError, OstromApiError) as err:
        _LOGGER.warning("Could not fetch Ostrom contracts: %s", err)
        return

    contracts = contracts_response.get("data") or []
    contract = next((c for c in contracts if c.get("status") == "ACTIVE"), None)
    if contract is None:
        _LOGGER.warning(
            "No active Ostrom contract found for this account; skipping consumption import"
        )
        return

    contract_id = contract["id"]

    last_stats = await hass.async_add_executor_job(
        get_last_statistics, hass, 1, STATISTIC_ID_CONSUMPTION, True, {"sum"}
    )
    existing = last_stats.get(STATISTIC_ID_CONSUMPTION)
    if existing:
        start = dt_util.utc_from_timestamp(existing[0]["start"]) + timedelta(hours=1)
        running_sum = existing[0]["sum"] or 0.0
    else:
        start = dt_util.utcnow() - timedelta(days=CONSUMPTION_MAX_DAYS_PER_REQUEST)
        running_sum = 0.0

    end = dt_util.utcnow()
    if start >= end:
        return

    statistics: list[StatisticData] = []
    chunk_start = start
    while chunk_start < end:
        chunk_end = min(chunk_start + timedelta(days=CONSUMPTION_MAX_DAYS_PER_REQUEST), end)
        try:
            response = await client.async_get(
                f"/contracts/{contract_id}/energy-consumption",
                params={
                    "startDate": _iso(chunk_start),
                    "endDate": _iso(chunk_end),
                    "resolution": CONSUMPTION_RESOLUTION,
                },
            )
        except (OstromAuthError, OstromApiError) as err:
            _LOGGER.warning("Could not fetch Ostrom consumption data: %s", err)
            break

        for item in response.get("data") or []:
            running_sum = _accumulate(statistics, item, running_sum)

        chunk_start = chunk_end
        if chunk_start < end:
            await asyncio.sleep(CONSUMPTION_REQUEST_CHUNK_DELAY)

    if not statistics:
        return

    metadata = StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name=f"{entry.title} Consumption",
        source=DOMAIN,
        statistic_id=STATISTIC_ID_CONSUMPTION,
        unit_of_measurement="kWh",
    )
    async_add_external_statistics(hass, metadata, statistics)


def _accumulate(statistics: list[StatisticData], item: dict[str, Any], running_sum: float) -> float:
    kwh = item.get("kWh")
    date = item.get("date")
    if kwh is None or date is None:
        return running_sum
    running_sum += kwh
    statistics.append(
        StatisticData(start=dt_util.parse_datetime(date), sum=running_sum, state=kwh)
    )
    return running_sum


def _iso(value) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")
