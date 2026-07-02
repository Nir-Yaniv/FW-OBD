"""HTTPS/REST connection to FortiOS (/api/v2) for HTTPS-only sites (issue #27).

Mirrors the SSHHandler contract (connect / disconnect / typed errors) so the
scan pipeline can treat both transports uniformly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)


@dataclass
class RESTCredentials:
    host: str
    api_key: str
    port: int = 443
    verify_tls: bool = True


class RESTConnectionError(Exception):
    """Device unreachable or the REST API refused us."""


class RESTAuthError(RESTConnectionError):
    pass


class FortiGateRESTClient:
    """Thin wrapper over the FortiOS REST API (/api/v2/) using API-key auth."""

    def __init__(self, credentials: RESTCredentials, timeout: float = 15.0) -> None:
        self._creds = credentials
        self._timeout = timeout
        self._session: Optional[requests.Session] = None
        self._base = f"https://{credentials.host}:{credentials.port}/api/v2"

    # ------------------------------------------------------------------
    # Connection lifecycle (mirrors SSHHandler)
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Open a session and validate reachability + auth with one status call.

        Raises RESTConnectionError variants on failure — a failure HERE means
        the device was never reached (same contract as SSHHandler.connect).
        """
        session = requests.Session()
        session.headers["Authorization"] = f"Bearer {self._creds.api_key}"
        session.verify = self._creds.verify_tls
        if not self._creds.verify_tls:
            # Self-signed opt-in: silence only the warning this session causes.
            import urllib3

            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            logger.warning("TLS verification DISABLED for %s (self-signed opt-in)", self._creds.host)

        self._session = session
        logger.info("Connecting to https://%s:%s via REST", self._creds.host, self._creds.port)
        self.get_monitor("system/status")
        logger.info("REST API session established with %s", self._creds.host)

    def disconnect(self) -> None:
        if self._session:
            self._session.close()
            self._session = None
            logger.info("REST session closed for %s", self._creds.host)

    @property
    def is_connected(self) -> bool:
        return self._session is not None

    # ------------------------------------------------------------------
    # Requests
    # ------------------------------------------------------------------

    def get_monitor(self, path: str, params: Optional[dict] = None) -> Any:
        """GET /api/v2/monitor/<path> and return the 'results' payload."""
        return self._get_json(f"monitor/{path}", params)

    def get_cmdb(self, path: str, params: Optional[dict] = None) -> Any:
        """GET /api/v2/cmdb/<path> and return the 'results' payload."""
        return self._get_json(f"cmdb/{path}", params)

    def get_text(self, path: str, params: Optional[dict] = None, read_timeout: float = 120.0) -> str:
        """GET an endpoint that returns raw text (e.g. config backup)."""
        resp = self._request(path, params, read_timeout=read_timeout)
        return resp.text

    # ------------------------------------------------------------------

    def _get_json(self, path: str, params: Optional[dict]) -> Any:
        resp = self._request(path, params, read_timeout=self._timeout)
        try:
            body = resp.json()
        except ValueError as exc:
            raise RESTConnectionError(f"Non-JSON response from '{path}'") from exc
        # FortiOS envelope: {"results": ..., "status": "success", ...}.
        # serial/version/build live on the envelope (not in results) on most
        # FortiOS builds — fold them in so readers see one flat dict.
        if isinstance(body, dict) and "results" in body:
            results = body["results"]
            if isinstance(results, dict):
                for key in ("serial", "version", "build"):
                    if key in body and key not in results:
                        results[key] = body[key]
            return results
        return body

    def _request(self, path: str, params: Optional[dict], read_timeout: float) -> requests.Response:
        if self._session is None:
            raise RESTConnectionError("Not connected — call connect() first")
        url = f"{self._base}/{path}"
        try:
            resp = self._session.get(url, params=params, timeout=(self._timeout, read_timeout))
        except requests.exceptions.SSLError as exc:
            raise RESTConnectionError(
                f"TLS error connecting to {self._creds.host}: {exc}. "
                "If the device uses a self-signed certificate, enable the insecure "
                "self-signed option in the connect dialog."
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise RESTConnectionError(f"HTTPS connection to {self._creds.host} failed: {exc}") from exc
        if resp.status_code in (401, 403):
            raise RESTAuthError(
                f"REST API auth failed for {self._creds.host} (HTTP {resp.status_code}) — check the API key"
            )
        if resp.status_code >= 400:
            raise RESTConnectionError(f"REST API error on '{path}': HTTP {resp.status_code}")
        return resp
