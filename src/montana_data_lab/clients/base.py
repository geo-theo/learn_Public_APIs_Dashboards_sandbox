from __future__ import annotations

import time
from typing import Any

import httpx


class PublicApiClient:
    def __init__(self, *, timeout: float, headers: dict[str, str] | None = None) -> None:
        self.client = httpx.Client(timeout=timeout, headers=headers, follow_redirects=True)

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        attempts: int = 3,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                response = self.client.get(url, params=params)
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt < attempts - 1:
                    time.sleep(0.5 * (2**attempt))
        raise RuntimeError(f"API request failed after {attempts} attempts: {url}") from last_error

    def close(self) -> None:
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        self.close()
