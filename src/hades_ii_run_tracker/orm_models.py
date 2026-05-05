"""SQLAlchemy ORM models for tracker state."""

from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class UserRow(Base):
    __tablename__ = "users"

    position: Mapped[int] = mapped_column(Integer, nullable=False)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    access_code: Mapped[str] = mapped_column(String, nullable=False, unique=True)


class OptionRow(Base):
    __tablename__ = "options"
    __table_args__ = (UniqueConstraint("kind", "position", name="uq_options_kind_position"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    image_url: Mapped[str | None] = mapped_column(String, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String, nullable=True)


class AppSettingsRow(Base):
    """Singleton row (id == 1) for admin password and analytics defaults."""

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_password: Mapped[str] = mapped_column(String, nullable=False, default="")
    analytics_date_range_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=7
    )
    weighted_victory_fear_multiplier: Mapped[float] = mapped_column(
        Float, nullable=False, default=0, server_default="0"
    )


class RunRow(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    side: Mapped[str] = mapped_column(String, nullable=False)
    weapon: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    fear: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    boon_links: Mapped[list["RunBoonRow"]] = relationship(
        "RunBoonRow",
        back_populates="run",
        order_by="RunBoonRow.position",
        cascade="all, delete-orphan",
    )


class RunBoonRow(Base):
    __tablename__ = "run_boons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    run: Mapped["RunRow"] = relationship("RunRow", back_populates="boon_links")
