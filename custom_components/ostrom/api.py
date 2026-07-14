"""Ostrom API client: OAuth2 client-credentials auth + REST calls with retry/backoff.

This is the single place in the integration that talks HTTP to Ostrom. The
previous version duplicated the OAuth2 client-credentials flow in both
auth.py (async, aiohttp) and config_flow.py (sync, requests) and only the
former had 429/backoff handling - the coordinator's own data fetches had
none. Centralizing here means every call (token, /me, /spot-prices,
/contracts, /contracts/{id}/energy-consumption) gets the same retry policy.
"""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

import aiohttp

from .const import (
    API_URL_TEMPLATE,
    AUTH_URL_TEMPLATE,
    HTTP_BACKOFF_BASE,
    HTTP_BACKOFF_CAP,
    HTTP_MAX_ATTEMPTS,
)

_LOGGER = logging.getLogger(__name__)

_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)


class OstromAuthError(Exception):
    """Raised when Ostrom rejects the client_id/client_secret."""


class OstromApiError(Exception):
    """Raised when a request fails after all retries."""


class OstromNoActiveContractError(Exception):
    """Raised when the account has no active Ostrom contract."""


class OstromApiClient:
    """Thin async client for the Ostrom API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        client_id: str,
        client_secret: str,
        environment: str,
    ) -> None:
        self._session = session
        self._client_id = client_id
        self._client_secret = client_secret
        self._auth_url = AUTH_URL_TEMPLATE.format(env=environment)
        self._api_url = API_URL_TEMPLATE.format(env=environment)
        self._token: str | None = None
        self._token_lock = asyncio.Lock()

    async def async_validate_credentials(self) -> dict[str, Any]:
        """Validate credentials by obtaining a token and calling /me."""
        return await self.async_get("/me")

    async def async_get_active_contract_id(self) -> int:
        """Look up the customer's active contract id (shared by consumption fetches)."""
        response = await self.async_get("/contracts")
        contracts = response.get("data") or []
        contract = next((c for c in contracts if c.get("status") == "ACTIVE"), None)
        if contract is None:
            raise OstromNoActiveContractError("No active Ostrom contract found for this account")
        return contract["id"]

    async def async_get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET a path from the Ostrom API, retrying on 429 and transient errors."""
        url = f"{self._api_url}{path}"
        last_error: Exception | None = None
        for attempt in range(1, HTTP_MAX_ATTEMPTS + 1):
            token = await self._async_get_token()
            try:
                async with self._session.get(
                    url,
                    params=params,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=_REQUEST_TIMEOUT,
                ) as resp:
                    if resp.status == 401 and attempt < HTTP_MAX_ATTEMPTS:
                        # Token may have expired server-side; refresh and retry.
                        await self._async_get_token(force_refresh=True)
                        continue
                    if resp.status == 429:
                        delay = _retry_delay(resp.headers.get("Retry-After"), attempt)
                        _LOGGER.debug(
                            "Ostrom API rate-limited on %s, retrying in %.1fs", path, delay
                        )
                        await asyncio.sleep(delay)
                        continue
                    if resp.status >= 400:
                        detail = await resp.text()
                        raise OstromApiError(
                            f"Ostrom API request to {path} failed with HTTP {resp.status}: {detail}"
                        )
                    return await resp.json()
            except OstromApiError:
                raise
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                last_error = err
                if attempt < HTTP_MAX_ATTEMPTS:
                    await asyncio.sleep(HTTP_BACKOFF_BASE)
        raise OstromApiError(f"Ostrom API request to {path} failed: {last_error}")

    async def _async_get_token(self, *, force_refresh: bool = False) -> str:
        async with self._token_lock:
            if self._token is None or force_refresh:
                self._token = await self._fetch_token()
            return self._token

    async def _fetch_token(self) -> str:
        auth = aiohttp.BasicAuth(self._client_id, self._client_secret)
        last_error: Exception | None = None
        for attempt in range(1, HTTP_MAX_ATTEMPTS + 1):
            try:
                async with self._session.post(
                    self._auth_url,
                    auth=auth,
                    data={"grant_type": "client_credentials"},
                    timeout=_REQUEST_TIMEOUT,
                ) as resp:
                    if resp.status in (400, 401):
                        raise OstromAuthError(
                            f"Ostrom rejected the credentials (HTTP {resp.status})"
                        )
                    if resp.status == 429:
                        detail = await resp.text()
                        last_error = OstromApiError(f"rate-limited (HTTP 429): {detail}")
                        delay = _retry_delay(resp.headers.get("Retry-After"), attempt)
                        _LOGGER.debug(
                            "Ostrom token endpoint rate-limited, retrying in %.1fs", delay
                        )
                        await asyncio.sleep(delay)
                        continue
                    if resp.status >= 400:
                        detail = await resp.text()
                        raise OstromApiError(
                            f"Ostrom token endpoint returned HTTP {resp.status}: {detail}"
                        )
                    payload = await resp.json()
                    return payload["access_token"]
            except OstromAuthError:
                raise
            except OstromApiError:
                raise
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                last_error = err
                if attempt < HTTP_MAX_ATTEMPTS:
                    await asyncio.sleep(HTTP_BACKOFF_BASE)
        raise OstromApiError(f"Could not obtain an Ostrom access token: {last_error}")


def _retry_delay(retry_after: str | None, attempt: int) -> float:
    if retry_after is not None:
        try:
            return max(float(retry_after), 1.0)
        except ValueError:
            pass
    base = min(HTTP_BACKOFF_BASE * (3 ** (attempt - 1)), HTTP_BACKOFF_CAP)
    return base + random.uniform(0, base * 0.1)
