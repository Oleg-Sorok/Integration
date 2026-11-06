import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import crud, models
from app.database import Base, engine, get_db
from app.migrations import migrate_orders
from app.schemas import OrderCreate, OrderRead, OrderUpdate, TokenOut, UserCreate, UserOut, FEATURE_FIELDS
from app.security import get_current_user, hash_password, make_token, verify_password
from app.queue import enqueue_prediction
from app.forecast_client import FORECAST_URL, FORECAST_TIMEOUT
from redis.exceptions import RedisError

logger = logging.getLogger('orders.api')
BATCH_MAX_ITEMS = int(os.getenv('BATCH_MAX_ITEMS', '50'))
if BATCH_MAX_ITEMS < 1:
    raise RuntimeError('BATCH_MAX_ITEMS must be positive')


@asynccontextmanager
async def lifespan(application: FastAPI):
    Base.metadata.create_all(bind=engine)
    migrate_orders()
    application.state.forecast_client = httpx.AsyncClient(timeout=FORECAST_TIMEOUT)
    try:
        yield
    finally:
        await application.state.forecast_client.aclose()


app = FastAPI(title='Orders API — Lab 4 (MLflow + RQ)', lifespan=lifespan)


def _get_or_404(db: Session, oid: int):
    order = crud.get_order(db, oid)
    if order is None:
        raise HTTPException(404, 'Order not found')
    return order


@app.get('/health')
def health():
    return {'status': 'ok'}


@app.post('/auth/register', response_model=UserOut, status_code=201)
def register(data: UserCreate, db: Session = Depends(get_db)):
    user = models.User(username=data.username, hashed_password=hash_password(data.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Username already taken') from None
    db.refresh(user)
    return user


@app.post('/auth/login', response_model=TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.scalar(select(models.User).where(models.User.username == form.username))
    if user is None or not user.is_active or not verify_password(form.password, user.hashed_password):
        raise HTTPException(401, 'Incorrect username or password', headers={'WWW-Authenticate': 'Bearer'})
    return TokenOut(access_token=make_token(user.username))


@app.get('/auth/me', response_model=UserOut)
def me(user: models.User = Depends(get_current_user)):
    return user


@app.post('/orders/batch')
async def batch_orders(data: list[OrderCreate], request: Request,
                       db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    if len(data) > BATCH_MAX_ITEMS or len(data) == 0:
        raise HTTPException(422, f'Expected 1..{BATCH_MAX_ITEMS} orders')

    async def forecast_one(item: OrderCreate):
        features = item.model_dump(include=set(FEATURE_FIELDS))
        try:
            response = await request.app.state.forecast_client.post(f'{FORECAST_URL}/predict', json=features)
            response.raise_for_status()
            body=response.json()
            return (float(body['predicted_price']), str(body['model_version']))
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning('batch prediction failed: %s at %s', type(exc).__name__, datetime.now(timezone.utc).isoformat())
            return (None, None)

    # Concurrent network I/O, but independent persistence of every valid order.
    prices = await asyncio.gather(*(forecast_one(item) for item in data))
    results = []
    for index, (item, result) in enumerate(zip(data, prices)):
        price, version = result
        try:
            order = crud.create_batch_item(db, item, price, version)
            entry = {'index': index, 'order_id': order.id, 'status': order.status,
                     'predicted_price': price, 'model_version': version}
            if price is None:
                entry['error'] = 'ForecastUnavailable'
            results.append(entry)
        except Exception:
            db.rollback()
            logger.exception('batch DB persist failure index=%s', index)
            results.append({'index': index, 'order_id': None, 'status': 'failed', 'error': 'PersistenceError'})
    return {'total': len(data), 'results': results}


@app.post('/orders', response_model=OrderRead, status_code=202)
def create_order(data: OrderCreate, response: Response,
                 db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    order = crud.create_pending(db, data)
    response.headers['Location'] = f'/orders/{order.id}'
    try:
        enqueue_prediction(order.id, order.prediction_revision)
    except RedisError as exc:
        logger.error('order_id=%s queued failed: %s', order.id,exc)
        raise HTTPException(503, f'Order {order.id} saved; queue unavailable; retry later') from exc
    return order


@app.get('/orders', response_model=list[OrderRead])
def list_orders(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return crud.list_orders(db, limit, offset)


@app.get('/orders/{oid}', response_model=OrderRead)
def get_order(oid: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return _get_or_404(db, oid)


@app.patch('/orders/{oid}', response_model=OrderRead)
def update_order(oid: int, patch: OrderUpdate,
                 db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    order, repricing = crud.update_pending(db, _get_or_404(db, oid), patch)
    if repricing:
        enqueue_prediction(order.id, order.prediction_revision)
    return order


@app.post('/orders/{oid}/retry', response_model=OrderRead, status_code=202)
def retry_order(oid: int, response: Response,
                db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Retry an existing pending/failed prediction; never add an order."""
    order, should_enqueue = crud.prepare_retry(db, _get_or_404(db, oid))
    response.headers['Location'] = f'/orders/{order.id}'
    if should_enqueue:
        enqueue_prediction(order.id, order.prediction_revision)
    else:
        response.status_code = 200
    return order


@app.delete('/orders/{oid}', status_code=204)
def delete_order(oid: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    crud.delete_order(db, _get_or_404(db, oid))
    return Response(status_code=204)
