from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_name: Mapped[str] = mapped_column(String(120))
    gr_liv_area: Mapped[float]
    total_bsmt_sf: Mapped[float]
    garage_area: Mapped[float]
    year_built: Mapped[int]
    overall_qual: Mapped[int]
    ms_zoning: Mapped[str] = mapped_column(String(10))
    predicted_price: Mapped[float | None] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default='pending', server_default='pending')
    # Increment on each feature edit to prevent outdated background tasks overwriting new results.
    prediction_revision: Mapped[int] = mapped_column(nullable=False, default=0, server_default='0')
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class User(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False, server_default='true')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
