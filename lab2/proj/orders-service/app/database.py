import os
from pathlib import Path

from sqlalchemy import URL, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


def read_db_password() -> str:
    path = Path('/run/secrets/db_password')
    try:
        value = path.read_text(encoding='utf-8').strip()
    except OSError as exc:
        raise RuntimeError(f'Required Docker secret missing: db_password ({path})') from exc
    if not value:
        raise RuntimeError('Required Docker secret is empty: db_password')
    return value


DATABASE_URL = URL.create(
    'postgresql+psycopg',
    username=os.getenv('POSTGRES_USER', 'orders'),
    password=read_db_password(),
    host='postgres',
    port=5432,
    database=os.getenv('POSTGRES_DB', 'orders'),
)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
