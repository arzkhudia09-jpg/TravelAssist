from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def new_id() -> str:
    return str(uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Trip(Base):
    __tablename__ = "trips"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    destination: Mapped[str] = mapped_column(String(160), default="")
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    members: Mapped[list["TripMember"]] = relationship(back_populates="trip", cascade="all, delete-orphan")


class TripMember(Base):
    __tablename__ = "trip_members"
    __table_args__ = (UniqueConstraint("trip_id", "user_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    nickname: Mapped[str] = mapped_column(String(40))
    role: Mapped[str] = mapped_column(String(16), default="member")
    trip: Mapped[Trip] = relationship(back_populates="members")


class ItineraryItem(Base):
    __tablename__ = "itinerary_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    details: Mapped[str] = mapped_column(Text, default="")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))


class SavedRoute(Base):
    __tablename__ = "saved_routes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(160))
    destination: Mapped[str] = mapped_column(String(160))
    result_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Invitation(Base):
    __tablename__ = "invitations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(254), index=True)
    invited_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    sender_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    message: Mapped[str] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LocationShare(Base):
    __tablename__ = "location_shares"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    session_id: Mapped[str] = mapped_column(String(36))
    is_sharing: Mapped[bool] = mapped_column(Boolean, default=False)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Expense(Base):
    __tablename__ = "expenses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    payer_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    description: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(32))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    splits: Mapped[list["ExpenseSplit"]] = relationship(back_populates="expense", cascade="all, delete-orphan")


class ExpenseSplit(Base):
    __tablename__ = "expense_splits"
    __table_args__ = (UniqueConstraint("expense_id", "user_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    expense_id: Mapped[str] = mapped_column(ForeignKey("expenses.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    expense: Mapped[Expense] = relationship(back_populates="splits")


class IntegrationConfig(Base):
    __tablename__ = "integration_configs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider_id: Mapped[str] = mapped_column(String(64), index=True)
    display_name: Mapped[str] = mapped_column(String(100))
    credentials_ciphertext: Mapped[str] = mapped_column(Text)
    options_json: Mapped[str] = mapped_column(Text, default="{}")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), default="configuration_required")
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class UserAddon(Base):
    __tablename__ = "user_addons"
    __table_args__ = (UniqueConstraint("user_id", "addon_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    addon_id: Mapped[str] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class IntegrationAudit(Base):
    __tablename__ = "integration_audit"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    integration_id: Mapped[str] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(32))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
