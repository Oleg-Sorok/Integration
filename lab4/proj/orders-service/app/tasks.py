"""RQ worker function, isolated from API process; DB revision makes retries idempotent."""
import logging
import time
from datetime import datetime, timezone
import httpx
from sqlalchemy import update
from app.database import SessionLocal
from app.forecast_client import FORECAST_TIMEOUT, FORECAST_URL
from app.models import Order
from app.schemas import FEATURE_FIELDS

logging.basicConfig(level=logging.INFO)
log=logging.getLogger('orders.worker')

def run_prediction(order_id:int, revision:int):
    with SessionLocal() as db:
        order=db.get(Order, order_id)
        if order is None or order.prediction_revision != revision or order.status != 'pending':
            log.info('skip stale/deleted order_id=%s rev=%s',order_id,revision)
            return
        features={k:getattr(order,k) for k in FEATURE_FIELDS}
    price=None
    model_version=None
    final_status='failed'
    for attempt in range(1,3):
        try:
            with httpx.Client(timeout=FORECAST_TIMEOUT) as client:
                r=client.post(f'{FORECAST_URL}/predict',json=features)
                r.raise_for_status()
                content=r.json()
                price=float(content['predicted_price'])
                model_version=str(content['model_version'])
                final_status='priced'
                break
        except (httpx.HTTPError,KeyError,TypeError,ValueError) as exc:
            log.warning('order_id=%s attempt=%s forecast failure=%s', order_id,attempt,type(exc).__name__)
            if attempt<2: time.sleep(.4)
    with SessionLocal.begin() as db:
        update_result=db.execute(update(Order)
          .where(Order.id==order_id,Order.prediction_revision==revision,Order.status=='pending')
          .values(status=final_status,predicted_price=price,model_version=model_version))
    log.info('order_id=%s rev=%s result=%s version=%s updated=%s at=%s',
             order_id,revision,final_status,model_version,update_result.rowcount,datetime.now(timezone.utc).isoformat())
