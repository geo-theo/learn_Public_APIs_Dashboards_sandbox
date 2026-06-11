from __future__ import annotations

from typing import Any

from montana_data_lab.clients.base import PublicApiClient
from montana_data_lab.config import settings

BASE_URL = "https://api.weather.gov"


class NwsClient(PublicApiClient):
    def __init__(self) -> None:
        super().__init__(
            timeout=settings.http_timeout_seconds,
            headers={
                "User-Agent": settings.nws_user_agent,
                "Accept": "application/geo+json",
            },
        )

    def forecast_for_point(self, latitude: float, longitude: float) -> tuple[str, list[dict]]:
        point = self.get_json(f"{BASE_URL}/points/{latitude:.4f},{longitude:.4f}")
        forecast_url = point["properties"]["forecast"]
        forecast = self.get_json(forecast_url)
        return forecast_url, forecast["properties"]["periods"]

    def active_montana_alerts(self) -> list[dict[str, Any]]:
        payload = self.get_json(f"{BASE_URL}/alerts/active", params={"area": "MT"})
        return payload.get("features", [])
