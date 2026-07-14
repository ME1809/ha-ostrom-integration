# Ostrom Integration for Home Assistant

Home Assistant custom integration for [Ostrom](https://www.ostrom.de) dynamic
electricity prices. Polls the official Ostrom API for hourly spot prices and
exposes them as sensors, and imports your smart-meter's exact energy
consumption into Home Assistant's long-term statistics for the Energy
dashboard.

This is a rewrite of
[oliverwehrens/homeassistant_ostrom_integration](https://github.com/oliverwehrens/homeassistant_ostrom_integration)
(MIT licensed), rebuilt against the official
[Ostrom OpenAPI spec (2023-11-01)](https://production.ostrom-api.io/ostrom-open-api-2023-11-01.json)
to fix several issues found in the original during review — see
[What changed](#what-changed-vs-the-original) below.

## Features

- Hourly dynamic spot prices via `GET /spot-prices` (7 sensors, see below)
- Exact smart-meter consumption via `GET /contracts/{id}/energy-consumption`,
  imported as Home Assistant external statistics for the Energy dashboard
- OAuth2 client-credentials authentication with automatic 429 rate-limit
  backoff on every API call, not just login
- Config flow (UI setup, no YAML) with an options flow for updating
  credentials later
- Sandbox and production environment support

## Sensors

| Entity | Description |
| --- | --- |
| `sensor.ostrom_energy_spotpreis` | Current price (ct/kWh); full forecast in the `prices` attribute |
| `sensor.ostrom_next_price` | Next hour's price |
| `sensor.ostrom_average_price` | Average price across the available forecast window |
| `sensor.ostrom_min_price` / `sensor.ostrom_max_price` | Lowest / highest price in the forecast window |
| `sensor.ostrom_lowest_price_time` / `sensor.ostrom_highest_price_time` | Timestamp of the lowest / highest price |
| `sensor.ostrom_consumption_today` | Smart-meter consumption so far today (kWh) |
| `sensor.ostrom_consumption_week` | Rolling 7-day smart-meter consumption (kWh) |

## Installation

### HACS (recommended)

1. HACS → Integrations → ⋮ → Custom repositories
2. Add `https://github.com/ME1809/ha-ostrom-integration` as an "Integration"
3. Install "Ostrom", then restart Home Assistant

### Manual

Copy `custom_components/ostrom` into your Home Assistant `config/custom_components`
directory and restart.

## Setup

1. Create a Client ID / Client Secret at the
   [Ostrom Developer Portal](https://developer.ostrom-api.io/)
2. Settings → Devices & Services → Add Integration → "Ostrom"
3. Enter Client ID, Client Secret, your zip code, and choose the environment
   (`production` for real data, `sandbox` for testing)

The zip code is required: Ostrom's `/spot-prices` endpoint only returns your
actual base price, grid fees, tax and levies when a zip code is supplied —
without it those components come back as zero.

## Displaying prices with apexcharts-card

Install [apexcharts-card](https://github.com/RomRider/apexcharts-card) via
HACS, then use `sensor.ostrom_energy_spotpreis`'s `prices` attribute to draw a
color-banded forecast chart:

```yaml
type: custom:apexcharts-card
header:
  show: true
  title: Ostrom Strompreis
graph_span: 48h
series:
  - entity: sensor.ostrom_energy_spotpreis
    attribute: prices
    data_generator: |
      return entity.attributes.prices.map((item) => {
        return [new Date(item.date).getTime(), item.grossKwhPrice];
      });
    type: column
    color_threshold:
      - value: 0
        color: "#16a765"
      - value: 15
        color: "#fad165"
      - value: 25
        color: "#ffad47"
      - value: 35
        color: "#fb4c2f"
```

## What changed vs. the original

Code review of the forked project turned up a few issues, addressed here:

- **Duplicate OAuth logic**: the original implemented the client-credentials
  flow twice — once async in `auth.py` (aiohttp), once sync in
  `config_flow.py` (`requests`, run in an executor). This rewrite has a
  single `api.py` client used everywhere.
- **No rate-limit recovery on data fetches**: only the original's token
  fetch retried on HTTP 429. Spot-price and consumption requests did not.
  Every request now shares the same retry/backoff (`api.py`).
- **Non-idiomatic setup**: `async_setup` called
  `hass.states.async_set("ostrom.status", "running")`, manually creating a
  raw state outside the entity model. Removed — config-entry setup no longer
  needs `async_setup` at all.
- **Missing null-checks**: sensors could raise if `coordinator.data` was
  empty (e.g. right after startup, or after a failed refresh). Sensors now
  guard against empty data and report `unavailable` instead of crashing.
  Cross-references and null-checks were likewise added to consumption import.
  (`kWh`/`date` fields checked before use.)
- **Silent failure with no active contract**: consumption import now logs a
  warning and skips cleanly instead of failing silently.
- **Hardcoded constants**: `MAX_DAYS_PER_REQUEST` and the inter-request delay
  are now named constants in `const.py` instead of magic numbers buried in
  `sensor.py`.
- **Unnecessary dependency**: dropped the `requests` library requirement —
  everything now goes through `aiohttp`, which Home Assistant already bundles.

## API reference

Endpoints used, straight from the Ostrom OpenAPI spec:

- `POST /oauth2/token` — OAuth2 client-credentials grant
- `GET /me` — used to validate credentials
- `GET /contracts` — find the active contract
- `GET /contracts/{contractId}/energy-consumption` — hourly smart-meter kWh
- `GET /spot-prices` — hourly dynamic prices (HOUR resolution only)

Not used by this integration (require a PARTNER-role API client, which a
personal Ostrom customer does not have): `/users/link`, `/users/{id}/orders`,
`/products`, `/webhooks`.

## License

MIT — see [LICENSE](LICENSE). Originally based on
[oliverwehrens/homeassistant_ostrom_integration](https://github.com/oliverwehrens/homeassistant_ostrom_integration).
