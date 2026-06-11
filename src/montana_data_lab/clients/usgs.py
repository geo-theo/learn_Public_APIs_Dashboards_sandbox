from __future__ import annotations

from typing import Any

from montana_data_lab.clients.base import PublicApiClient
from montana_data_lab.config import settings

BASE_URL = "https://waterservices.usgs.gov/nwis/iv/"


class UsgsClient(PublicApiClient):
    def __init__(self) -> None:
        super().__init__(
            timeout=settings.http_timeout_seconds,
            headers={"User-Agent": settings.nws_user_agent},
        )

    def streamflow(self, site_numbers: list[str], period: str = "P2D") -> list[dict[str, Any]]:
        payload = self.get_json(
            BASE_URL,
            params={
                "format": "json",
                "sites": ",".join(site_numbers),
                "parameterCd": "00060",
                "siteStatus": "all",
                "period": period,
            },
        )
        return payload.get("value", {}).get("timeSeries", [])
