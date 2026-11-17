from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Expense, ItineraryItem, Trip, TripMember


def build_trip_context(db: Session, trip: Trip) -> dict:
    """Return only persisted trip facts for a future, explicitly configured AI provider."""
    members = db.scalars(select(TripMember).where(TripMember.trip_id == trip.id)).all()
    itinerary = db.scalars(select(ItineraryItem).where(ItineraryItem.trip_id == trip.id)).all()
    expenses = db.scalars(select(Expense).where(Expense.trip_id == trip.id)).all()
    return {
        "trip": {"id": trip.id, "name": trip.name, "destination": trip.destination, "starts_at": trip.starts_at},
        "members": [{"user_id": member.user_id, "nickname": member.nickname} for member in members],
        "itinerary": [{"title": item.title, "details": item.details, "scheduled_at": item.scheduled_at} for item in itinerary],
        "expenses": [{"amount_inr": expense.amount, "description": expense.description, "category": expense.category}
                     for expense in expenses],
        "data_status": "actual_application_data",
        "ai_provider": "not_configured",
    }
