"""SQLAlchemy async engine, session factory, models and table creation."""
import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from config import DATABASE_URL


class Base(DeclarativeBase):
    pass


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    date: Mapped["Date"] = mapped_column(Date, nullable=False)
    hour: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    tg_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tg_username: Mapped[str | None] = mapped_column(String, nullable=True)
    tg_name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped["DateTime"] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    cancelled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    reminded: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))

    __table_args__ = (
        CheckConstraint("hour >= 7 AND hour <= 21", name="ck_bookings_hour"),
        UniqueConstraint("date", "hour", name="uq_bookings_date_hour"),
    )


# Engine + session factory.
engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    """Create tables if they do not exist."""
    async with engine.begin() as conn:
        # gen_random_uuid() lives in pgcrypto on older Postgres; ensure available.
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)
        # Add the reminder flag to pre-existing tables (create_all won't alter).
        await conn.execute(
            text(
                "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS "
                "reminded boolean NOT NULL DEFAULT false"
            )
        )


async def get_session() -> AsyncSession:
    """FastAPI dependency yielding an async session."""
    async with SessionLocal() as session:
        yield session
