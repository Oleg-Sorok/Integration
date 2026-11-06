from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import Order
from app.schemas import FEATURE_FIELDS, OrderCreate, OrderUpdate


def create_pending(db: Session, data: OrderCreate) -> Order:
    order = Order(**data.model_dump(), status='pending', predicted_price=None, prediction_revision=0)
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def create_batch_item(db: Session, data: OrderCreate, price: float | None) -> Order:
    order = Order(**data.model_dump(), status='priced' if price is not None else 'failed', predicted_price=price)
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def list_orders(db: Session, limit: int, offset: int) -> list[Order]:
    return list(db.scalars(select(Order).order_by(Order.id).limit(limit).offset(offset)))


def get_order(db: Session, oid: int) -> Order | None:
    return db.get(Order, oid)


def update_pending(db: Session, order: Order, patch: OrderUpdate) -> tuple[Order, bool]:
    changes = patch.model_dump(exclude_unset=True)
    changed_features = any(k in FEATURE_FIELDS for k in changes)
    for key, value in changes.items():
        setattr(order, key, value)
    if changed_features:
        order.status = 'pending'
        order.predicted_price = None
        order.prediction_revision += 1
    db.commit()
    db.refresh(order)
    return order, changed_features


def delete_order(db: Session, order: Order) -> None:
    db.delete(order)
    db.commit()


def prepare_retry(db: Session, order: Order) -> tuple[Order, bool]:
    """Re-queue an existing order; never insert a duplicate row.

    A priced order is unchanged. A failed order gets a new revision. An
    existing pending task may be scheduled again after an API restart.
    Atomic compare-and-set in tasks.run_prediction makes repeated runs safe.
    """
    if order.status == 'priced':
        return order, False
    if order.status == 'failed':
        order.status = 'pending'
        order.predicted_price = None
        order.prediction_revision += 1
        db.commit()
        db.refresh(order)
    return order, True
