"""Background prediction with a fresh DB session and HTTP client per task.

BackgroundTasks runs only within the API process; tasks are NOT durable across crashes.
"""
import logging
from datetime import datetime, timezone
import httpx
from sqlalchemy import update

from app.database import SessionLocal
from app.forecast_client import FORECAST_TIMEOUT, FORECAST_URL
from app.models import Order
from app.schemas import FEATURE_FIELDS

log = logging.getLogger('orders.background')


def run_prediction(order_id: int, revision: int) -> None:
    # Read the CURRENT record so an older queued payload is never blindly applied.
    with SessionLocal() as db:
        order = db.get(Order, order_id)
        if order is None or order.prediction_revision != revision or order.status != 'pending':
            log.info('order_id=%s revision=%s skipped/deleted time=%s', order_id, revision, datetime.now(timezone.utc).isoformat())
            return
        features = {field: getattr(order, field) for field in FEATURE_FIELDS}

    price = None
    final_status = 'failed'
    try:
        with httpx.Client(timeout=FORECAST_TIMEOUT) as client:
            response = client.post(f'{FORECAST_URL}/predict', json=features)
            response.raise_for_status()
            price = float(response.json()['predicted_price'])
            final_status = 'priced'
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        log.warning('order_id=%s prediction failure: %s', order_id, type(exc).__name__)

    # Atomic compare-and-set protects against PATCH or DELETE during prediction.
    with SessionLocal.begin() as db:
        result = db.execute(
            update(Order)
            .where(Order.id == order_id, Order.prediction_revision == revision, Order.status == 'pending')
            .values(status=final_status, predicted_price=price)
        )
        log.info('order_id=%s revision=%s result=%s updated=%s time=%s',
                 order_id, revision, final_status, result.rowcount, datetime.now(timezone.utc).isoformat())
