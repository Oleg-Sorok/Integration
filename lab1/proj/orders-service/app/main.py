from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app import crud
from app.database import Base, engine, get_db
from app.schemas import OrderCreate, OrderRead, OrderUpdate


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Orders API", lifespan=lifespan)


def _get_or_404(db: Session, oid: int):
    order = crud.get_order(db, oid)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    return order


@app.get("/health")
def health():
    # Deliberately independent of Forecast API (graceful degradation).
    return {"status": "ok"}


@app.post("/orders", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
def create_order(data: OrderCreate, db: Session = Depends(get_db)):
    return crud.create_order(db, data)


@app.get("/orders", response_model=list[OrderRead])
def list_orders(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return crud.list_orders(db, limit, offset)


@app.get("/orders/{oid}", response_model=OrderRead)
def get_order(oid: int, db: Session = Depends(get_db)):
    return _get_or_404(db, oid)


@app.patch("/orders/{oid}", response_model=OrderRead)
def update_order(oid: int, patch: OrderUpdate, db: Session = Depends(get_db)):
    return crud.update_order(db, _get_or_404(db, oid), patch)


@app.delete("/orders/{oid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_order(oid: int, db: Session = Depends(get_db)):
    crud.delete_order(db, _get_or_404(db, oid))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
