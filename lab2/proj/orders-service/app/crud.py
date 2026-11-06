from sqlalchemy import select
from sqlalchemy.orm import Session

from app.forecast_client import get_prediction
from app.models import Order
from app.schemas import FEATURE_FIELDS, OrderCreate, OrderUpdate


def _features(source) -> dict:
    get = source.get if isinstance(source, dict) else lambda k: getattr(source, k)
    return {k: get(k) for k in FEATURE_FIELDS}


def create_order(db: Session, data: OrderCreate) -> Order:
    payload = data.model_dump()
    order = Order(**payload, predicted_price=get_prediction(_features(payload)))
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def list_orders(db: Session, limit: int, offset: int) -> list[Order]:
    stmt = select(Order).order_by(Order.id).limit(limit).offset(offset)
    return list(db.scalars(stmt))


def get_order(db: Session, oid: int) -> Order | None:
    return db.get(Order, oid)


def update_order(db: Session, order: Order, patch: OrderUpdate) -> Order:
    changes = patch.model_dump(exclude_unset=True)
    features_changed = any(
        k in FEATURE_FIELDS and v != getattr(order, k) for k, v in changes.items()
    )
    for key, value in changes.items():
        setattr(order, key, value)

    if features_changed:
        # Re-forecast with the MERGED (old + new) property parameters.
        # If Forecast is down we store None: the old price no longer matches
        # the new parameters, and showing it would be misleading.
        order.predicted_price = get_prediction(_features(order))

    db.commit()
    db.refresh(order)
    return order


def delete_order(db: Session, order: Order) -> None:
    db.delete(order)
    db.commit()
