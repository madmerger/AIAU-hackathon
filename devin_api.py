"""Thin client for the Devin enterprise REST API (v3)."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class DevinApiError(RuntimeError):
    pass


class DevinEnterpriseClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 60) -> None:
        if not api_key:
            raise DevinApiError("DEVIN_ENTERPRISE_API_KEY is not set")
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = self._base_url + path
        if params:
            url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {self._api_key}"})
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=self._timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as error:
                body = error.read().decode("utf-8", "replace")[:300]
                if error.code in (429, 500, 502, 503, 504):
                    last_error = DevinApiError(f"{error.code} on {path}: {body}")
                    time.sleep(2 * (attempt + 1))
                    continue
                raise DevinApiError(f"{error.code} on {path}: {body}") from error
            except (urllib.error.URLError, TimeoutError) as error:
                last_error = error
                time.sleep(2 * (attempt + 1))
        raise DevinApiError(f"GET {path} failed: {last_error}")

    def _paginate(self, path: str, params: dict[str, Any], page_size: int = 200) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            page = self._get(path, {**params, "limit": page_size, "first": page_size, "after": cursor})
            items.extend(page.get("items", []))
            if not page.get("has_next_page"):
                return items
            cursor = page.get("end_cursor")
            if cursor is None:
                return items

    def list_organizations(self) -> list[dict[str, Any]]:
        return self._paginate("/v3/enterprise/organizations", {})

    def list_org_users(self, org_id: str) -> list[dict[str, Any]]:
        return self._paginate(f"/v3/enterprise/organizations/{org_id}/members/users", {})

    def list_sessions(self) -> list[dict[str, Any]]:
        return self._paginate("/v3/enterprise/sessions", {})

    def usage_metrics(self, time_after: int, time_before: int) -> dict[str, Any]:
        return self._get(
            "/v3/enterprise/metrics/usage",
            {"time_after": time_after, "time_before": time_before},
        )

    def daily_consumption(self) -> dict[str, Any]:
        return self._get("/v3/enterprise/consumption/daily")

    def daily_org_consumption(self, org_id: str) -> dict[str, Any]:
        return self._get(f"/v3/enterprise/consumption/daily/organizations/{org_id}")
