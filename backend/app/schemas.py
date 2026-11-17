from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    username: str | None = Field(default=None, min_length=2, max_length=40, pattern=r"^[A-Za-z0-9_.-]+$")


class UserOut(BaseModel):
    id: str
    email: EmailStr
    username: str
    model_config = ConfigDict(from_attributes=True)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class TripCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    destination: str = Field(default="", max_length=160)
    starts_at: datetime | None = None


class InviteCreate(BaseModel):
    email: EmailStr


class NicknameUpdate(BaseModel):
    nickname: str = Field(min_length=1, max_length=40)


class ItineraryItemCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    details: str = Field(default="", max_length=2000)
    scheduled_at: datetime | None = None


class ExpenseCreate(BaseModel):
    payer_id: str | None = None
    amount: Decimal = Field(gt=0, le=10_000_000, max_digits=12, decimal_places=2)
    description: str = Field(min_length=1, max_length=200)
    category: str = Field(default="other", max_length=32)
    occurred_at: datetime | None = None
    participants: list[str] = Field(min_length=1)
    shares: dict[str, Decimal] | None = None

    @model_validator(mode="after")
    def valid_shares(self):
        if self.shares is not None and set(self.shares) != set(self.participants):
            raise ValueError("custom shares must cover exactly the listed participants")
        if self.shares is not None and any(value < 0 for value in self.shares.values()):
            raise ValueError("shares cannot be negative")
        if self.shares is not None and any(value.as_tuple().exponent < -2 for value in self.shares.values()):
            raise ValueError("custom shares must use at most two decimal places")
        if self.shares is not None and abs(sum(self.shares.values(), Decimal("0")) - self.amount) > Decimal("0.01"):
            raise ValueError("custom shares must add up to the expense amount")
        return self


class RouteSearch(BaseModel):
    source: str = Field(min_length=2, max_length=160)
    destination: str = Field(min_length=2, max_length=160)
    departure_date: datetime | None = None
    budget: float | None = Field(default=None, gt=0)
    preference: str = Field(default="balanced", pattern="^(cheapest|fastest|balanced)$")
    current_location: str | None = Field(default=None, max_length=160)
    remaining_budget: float | None = Field(default=None, gt=0)


class SavedRouteCreate(BaseModel):
    source: str = Field(min_length=2, max_length=160)
    destination: str = Field(min_length=2, max_length=160)
    result: dict[str, Any]

    @field_validator("result")
    @classmethod
    def limit_result_size(cls, value):
        import json
        if len(json.dumps(value)) > 100_000:
            raise ValueError("saved route result is too large")
        return value


class StaySearch(BaseModel):
    destination: str = Field(min_length=2, max_length=160)
    max_price: float | None = Field(default=None, gt=0)


class LocationUpdate(BaseModel):
    session_id: UUID
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    duration_minutes: int = Field(default=60, ge=1, le=1440)


class LocationSharingStart(BaseModel):
    session_id: UUID
    duration_minutes: int = Field(default=60, ge=1, le=1440)
