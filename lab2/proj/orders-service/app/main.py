from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import crud, models  # register both model tables before create_all
from app.database import Base, engine, get_db
from app.schemas import OrderCreate, OrderRead, OrderUpdate, TokenOut, UserCreate, UserOut
from app.security import get_current_user, hash_password, make_token, unauthorized, verify_password


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title='Orders API', lifespan=lifespan)


def _get_or_404(db: Session, oid: int):
    order = crud.get_order(db, oid)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'Order not found')
    return order


@app.get('/health')
def health():
    return {'status': 'ok'}


@app.post('/auth/register', response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, db: Session = Depends(get_db)):
    user = models.User(username=data.username, hashed_password=hash_password(data.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, 'Username already taken') from None
    db.refresh(user)
    return user


@app.post('/auth/login', response_model=TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.scalar(select(models.User).where(models.User.username == form.username))
    if user is None or not user.is_active or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, 'Incorrect username or password', headers={'WWW-Authenticate': 'Bearer'})
    return TokenOut(access_token=make_token(user.username))


@app.get('/auth/me', response_model=UserOut)
def me(user: models.User = Depends(get_current_user)):
    return user


@app.post('/orders', response_model=OrderRead, status_code=status.HTTP_201_CREATED)
def create_order(data: OrderCreate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return crud.create_order(db, data)


@app.get('/orders', response_model=list[OrderRead])
def list_orders(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return crud.list_orders(db, limit, offset)


@app.get('/orders/{oid}', response_model=OrderRead)
def get_order(oid: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return _get_or_404(db, oid)


@app.patch('/orders/{oid}', response_model=OrderRead)
def update_order(oid: int, patch: OrderUpdate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return crud.update_order(db, _get_or_404(db, oid), patch)


@app.delete('/orders/{oid}', status_code=status.HTTP_204_NO_CONTENT)
def delete_order(oid: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    crud.delete_order(db, _get_or_404(db, oid))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
