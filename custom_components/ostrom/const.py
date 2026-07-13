"""Constants for the Ostrom integration."""
from __future__ import annotations

from datetime import timedelta

DOMAIN = "ostrom"

CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"
CONF_ZIP_CODE = "zip_code"
CONF_ENVIRONMENT = "environment"

ENV_SANDBOX = "sandbox"
ENV_PRODUCTION = "production"
ENVIRONMENTS = [ENV_SANDBOX, ENV_PRODUCTION]

AUTH_URL_TEMPLATE = "https://auth.{env}.ostrom-api.io/oauth2/token"
API_URL_TEMPLATE = "https://{env}.ostrom-api.io"

SPOT_PRICE_UPDATE_INTERVAL = timedelta(minutes=30)
CONSUMPTION_UPDATE_INTERVAL = timedelta(hours=6)

# The /spot-prices endpoint only supports HOUR resolution
# (Ostrom OpenAPI spec 2023-11-01) - not user-configurable.
SPOT_PRICE_RESOLUTION = "HOUR"

# /contracts/{id}/energy-consumption supports HOUR/DAY/MONTH; we want the
# smart-meter's precise hourly readings for HA's Energy dashboard.
CONSUMPTION_RESOLUTION = "HOUR"
CONSUMPTION_MAX_DAYS_PER_REQUEST = 30
CONSUMPTION_REQUEST_CHUNK_DELAY = 3  # seconds between chunk requests (rate-limit friendly)
STATISTIC_ID_CONSUMPTION = f"{DOMAIN}:{DOMAIN}_hourly_consumption_energy"

# Retry/backoff shared by every HTTP call the integration makes.
HTTP_MAX_ATTEMPTS = 4
HTTP_BACKOFF_BASE = 5  # seconds
HTTP_BACKOFF_CAP = 120  # seconds

MANUFACTURER = "Ostrom"
