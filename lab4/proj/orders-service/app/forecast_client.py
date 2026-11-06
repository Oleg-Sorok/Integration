"""HTTP client for Forecast API. NEVER raises: returns None when forecast is unavailable."""
import logging
import os

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

log = logging.getLogger("orders.forecast")

FORECAST_URL = os.getenv("FORECAST_URL", "http://forecast-api:8001").rstrip("/")
FORECAST_TIMEOUT = float(os.getenv("FORECAST_TIMEOUT", "3.0"))


# Retry only network-level problems (connect error, timeout), max 3 attempts.
# 4xx/5xx answers are not retried. Worst case ~= 3 * timeout + 0.4 s (only when Forecast hangs; connection refused fails instantly).
@retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(0.2),
    retry=retry_if_exception_type(httpx.TransportError),
    reraise=True,
)
def _predict(features: dict) -> float:
    with httpx.Client(timeout=FORECAST_TIMEOUT) as client:
        resp = client.post(f"{FORECAST_URL}/predict", json=features)
        resp.raise_for_status()
        return float(resp.json()["predicted_price"])


def get_prediction(features: dict) -> float | None:
    try:
        return _predict(features)
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        log.warning("Forecast unavailable, continuing without prediction: %r", exc)
        return None
