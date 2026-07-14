"""Import Ostrom smart-meter consumption into Home Assistant long-term statistics."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .api import (
    OstromApiClient,
    OstromApiError,
    OstromAuthError,
    OstromNoActiveContractError,
)
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
        contract_id = await client.async_get_active_contract_id()
    except OstromNoActiveContractError:
        _LOGGER.warning(
            "No active Ostrom contract found for this account; skipping consumption import"
        )
        return
    except (OstromAuthError, OstromApiError) as err:
        _LOGGER.warning("Could not fetch Ostrom contracts: %s", err)
        return

    last_stats = await hass.async_add_executor_job(
        get_last_statistics, hass, 1, STATISTIC_ID_CONSUMPTION, True, {"sum"}
    )
    existing = last_stats.get(STATISTIC_ID_CONSUMPTION)
    fresh_lookback = dt_util.utcnow() - timedelta(days=CONSUMPTION_MAX_DAYS_PER_REQUEST)
    if existing:
        start = dt_util.utc_from_timestamp(existing[0]["start"]) + timedelta(hours=1)
        running_sum = existing[0]["sum"] or 0.0
        # Defensive: get_last_statistics() should hand back a sane recent
        # timestamp. If it ever doesn't (e.g. a units mismatch), this branch
        # would otherwise short-circuit forever below without logging
        # anything - self-heal by falling back to a fresh lookback instead.
        if start > dt_util.utcnow() + timedelta(days=1):
            _LOGGER.warning(
                "Ostrom consumption continuation point %s is implausible "
                "(last recorded start=%s); falling back to a %s-day lookback",
                start,
                existing[0]["start"],
                CONSUMPTION_MAX_DAYS_PER_REQUEST,
            )
            start = fresh_lookback
            running_sum = 0.0
    else:
        start = fresh_lookback
        running_sum = 0.0

    end = dt_util.utcnow()
    _LOGGER.debug(
        "Ostrom consumption import: fetching %s to %s (existing=%s)",
        start,
        end,
        bool(existing),
    )
    if start >= end:
        _LOGGER.debug("Ostrom consumption import: nothing to do (start >= end)")
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
        _LOGGER.debug(
            "Ostrom consumption import: Ostrom returned no new readings for %s to %s "
            "(smart-meter data is typically published with a reporting delay)",
            start,
            end,
        )
        return

    _LOGGER.debug("Ostrom consumption import: adding %d new hourly readings", len(statistics))

    metadata = StatisticMetaData(
        has_mean=False,
        mean_type=StatisticMeanType.NONE,
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
    # Ostrom's docs specify this exact format, milliseconds included
    # (e.g. "2023-11-01T00:00:00.000Z") - omitting them causes a 400.
    return value.strftime("%Y-%m-%dT%H:%M:%S.000Z")
