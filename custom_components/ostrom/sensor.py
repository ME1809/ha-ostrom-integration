"""Sensor platform for the Ostrom integration."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, MANUFACTURER
from .consumption_coordinator import OstromConsumptionCoordinator
from .coordinator import OstromSpotPriceCoordinator

_LOGGER = logging.getLogger(__name__)

PRICE_UNIT = "ct/kWh"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinators = hass.data[DOMAIN][entry.entry_id]
    price_coordinator: OstromSpotPriceCoordinator = coordinators["prices"]
    consumption_coordinator: OstromConsumptionCoordinator = coordinators["consumption"]

    async_add_entities(
        [
            OstromForecastSensor(price_coordinator, entry),
            OstromNextPriceSensor(price_coordinator, entry),
            OstromAveragePriceSensor(price_coordinator, entry),
            OstromMinPriceSensor(price_coordinator, entry),
            OstromMaxPriceSensor(price_coordinator, entry),
            OstromLowestPriceTimeSensor(price_coordinator, entry),
            OstromHighestPriceTimeSensor(price_coordinator, entry),
            OstromDailyConsumptionSensor(consumption_coordinator, entry),
            OstromWeeklyConsumptionSensor(consumption_coordinator, entry),
        ]
    )


def _price_ct(item: dict[str, Any]) -> float:
    return round(item["grossKwhPrice"], 3)


def _parse_date(item: dict[str, Any]) -> datetime:
    return dt_util.parse_datetime(item["date"])


class _OstromEntityMixin:
    """Shared device info + explicit entity_id setup for all Ostrom sensors.

    Sets entity_id explicitly: entities tied to a device otherwise get
    Home Assistant's auto-suggested id ("sensor.<device_name>_<entity_name>"),
    which would silently break the documented sensor.ostrom_energy_spotpreis
    contract (used by the apexcharts-card example) as soon as the device
    name changes (e.g. a different zip code).
    """

    _object_id: str

    def _init_ostrom_entity(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer=MANUFACTURER,
        )
        self.entity_id = generate_entity_id(
            "sensor.{}", self._object_id, hass=self.coordinator.hass
        )


class OstromBaseSensor(
    _OstromEntityMixin, CoordinatorEntity[OstromSpotPriceCoordinator], SensorEntity
):
    """Base class for price sensors: null-safe access to the price forecast."""

    def __init__(self, coordinator: OstromSpotPriceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._init_ostrom_entity(entry)

    @property
    def _prices(self) -> list[dict[str, Any]]:
        """Return the cached price list, or an empty list if none is available yet."""
        return self.coordinator.data or []

    @property
    def available(self) -> bool:
        return super().available and bool(self._prices)


class OstromConsumptionBaseSensor(
    _OstromEntityMixin, CoordinatorEntity[OstromConsumptionCoordinator], SensorEntity
):
    """Base class for consumption sensors: null-safe access to the reading window."""

    def __init__(self, coordinator: OstromConsumptionCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._init_ostrom_entity(entry)

    @property
    def _readings(self) -> list[dict[str, Any]]:
        """Return the cached reading list, or an empty list if none is available yet."""
        return self.coordinator.data or []

    @property
    def available(self) -> bool:
        return super().available and bool(self._readings)


class OstromForecastSensor(OstromBaseSensor):
    """Current spot price; the full forecast is exposed as the 'prices' attribute."""

    _attr_name = "Ostrom Energy Spotpreis"
    _attr_native_unit_of_measurement = PRICE_UNIT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _object_id = "ostrom_energy_spotpreis"

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
    _object_id = "ostrom_next_price"

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
    _object_id = "ostrom_average_price"

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
    _object_id = "ostrom_min_price"

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
    _object_id = "ostrom_max_price"

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
    _object_id = "ostrom_lowest_price_time"

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
    _object_id = "ostrom_highest_price_time"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_highest_price_time"

    @property
    def native_value(self) -> datetime | None:
        prices = self._prices
        if not prices:
            return None
        return _parse_date(max(prices, key=_price_ct))


def _reading_kwh(reading: dict[str, Any]) -> float | None:
    return reading.get("kWh")


def _reading_local_dt(reading: dict[str, Any]) -> datetime | None:
    date = reading.get("date")
    if date is None:
        return None
    parsed = dt_util.parse_datetime(date)
    return dt_util.as_local(parsed) if parsed else None


class OstromDailyConsumptionSensor(OstromConsumptionBaseSensor):
    """Today's smart-meter consumption so far - handy to cross-check against other meters."""

    _attr_name = "Ostrom Verbrauch heute"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    # device_class=energy only allows total/total_increasing, not measurement;
    # "total" also correctly allows this to reset/drop at local midnight.
    _attr_state_class = SensorStateClass.TOTAL
    _object_id = "ostrom_consumption_today"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_consumption_today"

    @property
    def native_value(self) -> float | None:
        readings = self._readings
        if not readings:
            return None
        today = dt_util.now().date()
        total = sum(
            kwh
            for r in readings
            if (kwh := _reading_kwh(r)) is not None
            and (local_dt := _reading_local_dt(r)) is not None
            and local_dt.date() == today
        )
        return round(total, 3)


class OstromWeeklyConsumptionSensor(OstromConsumptionBaseSensor):
    """Rolling 7-day smart-meter consumption - handy to cross-check against other meters."""

    _attr_name = "Ostrom Verbrauch Woche"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    # device_class=energy only allows total/total_increasing, not measurement.
    _attr_state_class = SensorStateClass.TOTAL
    _object_id = "ostrom_consumption_week"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_consumption_week"

    @property
    def native_value(self) -> float | None:
        readings = self._readings
        if not readings:
            return None
        cutoff = dt_util.now() - timedelta(days=7)
        total = sum(
            kwh
            for r in readings
            if (kwh := _reading_kwh(r)) is not None
            and (local_dt := _reading_local_dt(r)) is not None
            and local_dt >= cutoff
        )
        return round(total, 3)
