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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
