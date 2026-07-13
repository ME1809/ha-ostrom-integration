"""Sensor platform for the Ostrom integration."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, MANUFACTURER
from .coordinator import OstromSpotPriceCoordinator

_LOGGER = logging.getLogger(__name__)

PRICE_UNIT = "ct/kWh"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: OstromSpotPriceCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        [
            OstromForecastSensor(coordinator, entry),
            OstromNextPriceSensor(coordinator, entry),
            OstromAveragePriceSensor(coordinator, entry),
            OstromMinPriceSensor(coordinator, entry),
            OstromMaxPriceSensor(coordinator, entry),
            OstromLowestPriceTimeSensor(coordinator, entry),
            OstromHighestPriceTimeSensor(coordinator, entry),
        ]
    )


def _price_ct(item: dict[str, Any]) -> float:
    return round(item["grossKwhPrice"], 3)


def _parse_date(item: dict[str, Any]) -> datetime:
    return dt_util.parse_datetime(item["date"])


class OstromBaseSensor(CoordinatorEntity[OstromSpotPriceCoordinator], SensorEntity):
    """Base class sharing device info and null-safe access to coordinator data."""

    def __init__(self, coordinator: OstromSpotPriceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer=MANUFACTURER,
        )

    @property
    def _prices(self) -> list[dict[str, Any]]:
        """Return the cached price list, or an empty list if none is available yet."""
        return self.coordinator.data or []

    @property
    def available(self) -> bool:
        return super().available and bool(self._prices)


class OstromForecastSensor(OstromBaseSensor):
    """Current spot price; the full forecast is exposed as the 'prices' attribute."""

    _attr_name = "Ostrom Energy Spotpreis"
    _attr_native_unit_of_measurement = PRICE_UNIT
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_spot_price"

    @property
    def native_value(self) -> float | None:
        prices = self._prices
        if not prices:
            return None
        now = dt_util.utcnow()
        current = [p for p in prices if _parse_date(p) <= now]
        if not current:
            return None
        return _price_ct(max(current, key=_parse_date))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"prices": self._prices}


class OstromNextPriceSensor(OstromBaseSensor):
    _attr_name = "Ostrom Next Price"
    _attr_native_unit_of_measurement = PRICE_UNIT
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_next_price"

    @property
    def native_value(self) -> float | None:
        prices = self._prices
        if not prices:
            return None
        now = dt_util.utcnow()
        upcoming = [p for p in prices if _parse_date(p) > now]
        if not upcoming:
            return None
        return _price_ct(min(upcoming, key=_parse_date))


class OstromAveragePriceSensor(OstromBaseSensor):
    _attr_name = "Ostrom Average Price"
    _attr_native_unit_of_measurement = PRICE_UNIT
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_average_price"

    @property
    def native_value(self) -> float | None:
        prices = self._prices
        if not prices:
            return None
        return round(sum(_price_ct(p) for p in prices) / len(prices), 3)


class OstromMinPriceSensor(OstromBaseSensor):
    _attr_name = "Ostrom Min Price"
    _attr_native_unit_of_measurement = PRICE_UNIT
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_min_price"

    @property
    def native_value(self) -> float | None:
        prices = self._prices
        if not prices:
            return None
        return _price_ct(min(prices, key=_price_ct))


class OstromMaxPriceSensor(OstromBaseSensor):
    _attr_name = "Ostrom Max Price"
    _attr_native_unit_of_measurement = PRICE_UNIT
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_max_price"

    @property
    def native_value(self) -> float | None:
        prices = self._prices
        if not prices:
            return None
        return _price_ct(max(prices, key=_price_ct))


class OstromLowestPriceTimeSensor(OstromBaseSensor):
    _attr_name = "Ostrom Lowest Price Time"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_lowest_price_time"

    @property
    def native_value(self) -> datetime | None:
        prices = self._prices
        if not prices:
            return None
        return _parse_date(min(prices, key=_price_ct))


class OstromHighestPriceTimeSensor(OstromBaseSensor):
    _attr_name = "Ostrom Highest Price Time"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_highest_price_time"

    @property
    def native_value(self) -> datetime | None:
        prices = self._prices
        if not prices:
            return None
        return _parse_date(max(prices, key=_price_ct))
