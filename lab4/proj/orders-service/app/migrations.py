"""Idempotent migration; preserves existing order rows and users."""
from sqlalchemy import text
from app.database import engine


def migrate_orders() -> None:
    with engine.begin() as conn:
        existed = conn.scalar(text("""SELECT count(*) FROM information_schema.columns
            WHERE table_name='orders' AND column_name='status'""")) > 0
        conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS status VARCHAR(16) NOT NULL DEFAULT 'pending'"))
        conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS prediction_revision INTEGER NOT NULL DEFAULT 0"))
        conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS model_version VARCHAR(32)"))
        if not existed:
            conn.execute(text("""UPDATE orders SET status = CASE
                WHEN predicted_price IS NULL THEN 'failed' ELSE 'priced' END"""))
