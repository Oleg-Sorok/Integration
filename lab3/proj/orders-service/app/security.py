"""Authentication with Docker-mounted secrets; no environment fallback."""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User


def read_secret(name: str) -> str:
    path = Path('/run/secrets') / name
    try:
        value = path.read_text(encoding='utf-8').strip()
    except OSError as exc:
        raise RuntimeError(f'Required Docker secret missing: {name} ({path})') from exc
    if not value:
        raise RuntimeError(f'Required Docker secret is empty: {name}')
    return value


JWT_KEY = read_secret('jwt_secret_key')
JWT_ALGORITHM = 'HS256'
TOKEN_MINUTES = int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES', '30'))
if TOKEN_MINUTES < 1:
    raise RuntimeError('ACCESS_TOKEN_EXPIRE_MINUTES must be >= 1')

password_hash = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl='auth/login')


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)


def make_token(username: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({'sub': username, 'iat': now, 'exp': now + timedelta(minutes=TOKEN_MINUTES)}, JWT_KEY, algorithm=JWT_ALGORITHM)


def unauthorized() -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Could not validate credentials', headers={'WWW-Authenticate': 'Bearer'})


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    try:
        payload = jwt.decode(token, JWT_KEY, algorithms=[JWT_ALGORITHM])
        username = payload.get('sub')
        if not isinstance(username, str) or not username:
            raise unauthorized()
        if not isinstance(payload.get('iat'), int) or not isinstance(payload.get('exp'), int):
            raise unauthorized()
    except jwt.InvalidTokenError:
        raise unauthorized() from None
    user = db.scalar(select(User).where(User.username == username))
    if user is None or not user.is_active:
        raise unauthorized()
    return user
