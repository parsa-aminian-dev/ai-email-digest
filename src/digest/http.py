from __future__ import annotations

import time
from typing import Any

import httpx


def request_json(
    client: httpx.Client, method: str, url: str, *, attempts: int = 3, **kwargs: Any
) -> dict[str, Any]:
    """Retry transient read/API failures; never expose remote response bodies in logs."""
    for attempt in range(attempts):
        try:
            response = client.request(method, url, **kwargs)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Expected JSON object")
            return data
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as error:
            retryable = not isinstance(
                error, httpx.HTTPStatusError
            ) or error.response.status_code in {429, 500, 502, 503, 504}
            if not retryable or attempt == attempts - 1:
                raise
            time.sleep(0.25 * (2**attempt))
    raise RuntimeError("Request exhausted")
