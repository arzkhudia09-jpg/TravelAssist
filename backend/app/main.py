import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .assistant import build_trip_context
from .db import Base, make_session_factory
from .models import ChatMessage, Expense, ExpenseSplit, Invitation, ItineraryItem, LocationShare, SavedRoute, Trip, TripMember, User, utcnow
from .providers import ProviderUnavailable, rank_routes, search_stays, search_transport
from .schemas import (
    Credentials, ExpenseCreate, InviteCreate, ItineraryItemCreate, LocationUpdate, NicknameUpdate,
    LocationSharingStart, RouteSearch, SavedRouteCreate, StaySearch, TokenOut, TripCreate, UserOut,
)
from .security import decode_token, hash_password, issue_token, verify_password


def create_app(database_url: str | None = None, auto_create_tables: bool | None = None) -> FastAPI:
    engine, session_factory = make_session_factory(database_url or settings.database_url)
    should_create_tables = database_url is not None or settings.auto_create_tables
    if auto_create_tables is not None:
        should_create_tables = auto_create_tables

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if should_create_tables:
            Base.metadata.create_all(bind=engine)
        yield

    app = FastAPI(title="Travel Assist API", version="0.1.0", lifespan=lifespan)
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.chat_connections = {}
    import asyncio
    app.state.chat_lock = asyncio.Lock()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    def current_user(token: str, db: Session) -> User:
        try:
            user_id = decode_token(token)
        except (jwt.InvalidTokenError, ValueError):
            raise HTTPException(status_code=401, detail="Invalid or expired access token")
        user = db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=401, detail="Account no longer exists")
        return user

    def authenticated(authorization: str | None, db: Session) -> User:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Bearer token required")
        return current_user(authorization[7:], db)

    def member_or_404(db: Session, trip_id: str, user_id: str) -> TripMember:
        member = db.scalar(select(TripMember).where(
            TripMember.trip_id == trip_id, TripMember.user_id == user_id
        ))
        if not member:
            raise HTTPException(status_code=404, detail="Trip not found")
        return member

    def aware_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/api/auth/register", response_model=TokenOut, status_code=201)
    def register(payload: Credentials, db: Session = Depends(get_db)):
        if db.scalar(select(User).where(User.email == payload.email.lower())):
            raise HTTPException(status_code=409, detail="Email is already registered")
        username = payload.username or payload.email.split("@", 1)[0][:40]
        if db.scalar(select(User).where(User.username == username)):
            raise HTTPException(status_code=409, detail="Username is already taken")
        user = User(email=payload.email.lower(), username=username, password_hash=hash_password(payload.password))
        db.add(user)
        db.commit()
        db.refresh(user)
        return {"access_token": issue_token(user.id), "user": user}

    @app.post("/api/auth/login", response_model=TokenOut)
    def login(payload: Credentials, db: Session = Depends(get_db)):
        user = db.scalar(select(User).where(User.email == payload.email.lower()))
        if not user or not verify_password(payload.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        return {"access_token": issue_token(user.id), "user": user}

    @app.get("/api/auth/me", response_model=UserOut)
    def me(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
        return authenticated(authorization, db)

    @app.get("/api/dashboard")
    def dashboard(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
        user = authenticated(authorization, db)
        trips = db.scalars(select(Trip).join(TripMember).where(TripMember.user_id == user.id).order_by(Trip.created_at.desc())).all()
        now = utcnow()
        categorized = {"upcoming": [], "ongoing": [], "completed": []}
        for trip in trips:
            item = {"id": trip.id, "name": trip.name, "destination": trip.destination, "starts_at": trip.starts_at}
            if not trip.starts_at or aware_utc(trip.starts_at) > now:
                categorized["upcoming"].append(item)
            elif aware_utc(trip.starts_at).date() == now.date():
                categorized["ongoing"].append(item)
            else:
                categorized["completed"].append(item)
        invitations = db.scalars(select(Invitation).where(
            Invitation.email == user.email, Invitation.status == "pending"
        )).all()
        saved = db.scalars(select(SavedRoute).where(SavedRoute.user_id == user.id)).all()
        return {**categorized, "saved_routes": [
            {"id": route.id, "source": route.source, "destination": route.destination}
            for route in saved
        ], "invitations": [
            {"id": invite.id, "trip_id": invite.trip_id, "email": invite.email}
            for invite in invitations
        ]}

    @app.get("/api/saved-routes")
    def list_saved_routes(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
        user = authenticated(authorization, db)
        routes = db.scalars(select(SavedRoute).where(SavedRoute.user_id == user.id).order_by(SavedRoute.created_at.desc())).all()
        return [{"id": route.id, "source": route.source, "destination": route.destination,
                 "result": json.loads(route.result_json), "created_at": route.created_at} for route in routes]

    @app.post("/api/saved-routes", status_code=201)
    def save_route(payload: SavedRouteCreate, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
        user = authenticated(authorization, db)
        route = SavedRoute(user_id=user.id, source=payload.source.strip(), destination=payload.destination.strip(),
                           result_json=json.dumps(payload.result))
        db.add(route)
        db.commit()
        db.refresh(route)
        return {"id": route.id, "source": route.source, "destination": route.destination}

    @app.delete("/api/saved-routes/{route_id}", status_code=204)
    def delete_saved_route(route_id: str, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
        user = authenticated(authorization, db)
        route = db.scalar(select(SavedRoute).where(SavedRoute.id == route_id, SavedRoute.user_id == user.id))
        if not route:
            raise HTTPException(status_code=404, detail="Saved route not found")
        db.delete(route)
        db.commit()

    @app.get("/api/trips")
    def list_trips(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
        user = authenticated(authorization, db)
        trips = db.scalars(select(Trip).join(TripMember).where(TripMember.user_id == user.id).order_by(Trip.created_at.desc())).all()
        return [{"id": t.id, "name": t.name, "destination": t.destination, "starts_at": t.starts_at} for t in trips]

    @app.post("/api/trips", status_code=201)
    def create_trip(payload: TripCreate, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
        user = authenticated(authorization, db)
        trip = Trip(name=payload.name.strip(), destination=payload.destination.strip(), starts_at=payload.starts_at, owner_id=user.id)
        db.add(trip)
        db.flush()
        db.add(TripMember(trip_id=trip.id, user_id=user.id, nickname=user.username, role="owner"))
        db.commit()
        db.refresh(trip)
        return {"id": trip.id, "name": trip.name, "destination": trip.destination, "starts_at": trip.starts_at}

    @app.get("/api/trips/{trip_id}")
    def get_trip(trip_id: str, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
        user = authenticated(authorization, db)
        member_or_404(db, trip_id, user.id)
        trip = db.get(Trip, trip_id)
        members = db.scalars(select(TripMember).where(TripMember.trip_id == trip_id)).all()
        return {
            "id": trip.id, "name": trip.name, "destination": trip.destination,
            "starts_at": trip.starts_at,
            "members": [{"user_id": m.user_id, "nickname": m.nickname, "role": m.role} for m in members],
            "itinerary": [
                {"id": item.id, "title": item.title, "details": item.details, "scheduled_at": item.scheduled_at}
                for item in db.scalars(select(ItineraryItem).where(ItineraryItem.trip_id == trip_id).order_by(ItineraryItem.scheduled_at)).all()
            ],
        }

    @app.get("/api/trips/{trip_id}/assistant/context")
    def assistant_context(trip_id: str, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
        user = authenticated(authorization, db)
        member_or_404(db, trip_id, user.id)
        return build_trip_context(db, db.get(Trip, trip_id))

    @app.post("/api/trips/{trip_id}/itinerary", status_code=201)
    def add_itinerary_item(trip_id: str, payload: ItineraryItemCreate, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
        user = authenticated(authorization, db)
        member_or_404(db, trip_id, user.id)
        item = ItineraryItem(trip_id=trip_id, title=payload.title.strip(), details=payload.details.strip(),
                             scheduled_at=payload.scheduled_at, created_by=user.id)
        db.add(item)
        db.commit()
        db.refresh(item)
        return {"id": item.id, "title": item.title, "details": item.details, "scheduled_at": item.scheduled_at}

    @app.post("/api/trips/{trip_id}/invitations", status_code=201)
    def invite(trip_id: str, payload: InviteCreate, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
        user = authenticated(authorization, db)
        member = member_or_404(db, trip_id, user.id)
        trip = db.get(Trip, trip_id)
        email = payload.email.lower()
        if db.scalar(select(TripMember).join(User).where(TripMember.trip_id == trip_id, User.email == email)):
            raise HTTPException(status_code=409, detail="User is already a trip member")
        invitation = Invitation(trip_id=trip_id, email=email, invited_by=user.id)
        db.add(invitation)
        db.commit()
        db.refresh(invitation)
        return {"id": invitation.id, "trip_id": trip.id, "email": email, "status": invitation.status}

    @app.post("/api/invitations/{invitation_id}/accept")
    def accept_invitation(invitation_id: str, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
        user = authenticated(authorization, db)
        invitation = db.get(Invitation, invitation_id)
        if not invitation or invitation.email != user.email or invitation.status != "pending":
            raise HTTPException(status_code=404, detail="Invitation not found")
        invitation.status = "accepted"
        db.add(TripMember(trip_id=invitation.trip_id, user_id=user.id, nickname=user.username))
        db.commit()
        return {"status": "accepted", "trip_id": invitation.trip_id}

    @app.get("/api/invitations")
    def list_invitations(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
        user = authenticated(authorization, db)
        invitations = db.scalars(select(Invitation).where(
            Invitation.email == user.email, Invitation.status == "pending"
        )).all()
        return [{"id": invite.id, "trip_id": invite.trip_id, "email": invite.email,
                 "trip_name": db.get(Trip, invite.trip_id).name} for invite in invitations]

    @app.patch("/api/trips/{trip_id}/members/me")
    def update_nickname(trip_id: str, payload: NicknameUpdate, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
        user = authenticated(authorization, db)
        membership = member_or_404(db, trip_id, user.id)
        membership.nickname = payload.nickname.strip()
        db.commit()
        return {"nickname": membership.nickname}

    @app.post("/api/trips/{trip_id}/expenses", status_code=201)
    def create_expense(trip_id: str, payload: ExpenseCreate, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
        user = authenticated(authorization, db)
        member_or_404(db, trip_id, user.id)
        members = {m.user_id for m in db.scalars(select(TripMember).where(TripMember.trip_id == trip_id)).all()}
        payer = payload.payer_id or user.id
        participants = set(payload.participants)
        if payer not in members or not participants or not participants <= members:
            raise HTTPException(status_code=422, detail="Payer and participants must be trip members")
        shares = payload.shares or {uid: round(payload.amount / len(participants), 2) for uid in participants}
        if payload.shares is None:
            last = sorted(participants)[-1]
            shares[last] = round(payload.amount - sum((v for k, v in shares.items() if k != last), Decimal("0")), 2)
        expense = Expense(
            trip_id=trip_id, payer_id=payer, amount=payload.amount,
            description=payload.description.strip(), category=payload.category,
            occurred_at=payload.occurred_at or utcnow(),
        )
        db.add(expense)
        db.flush()
        db.add_all([ExpenseSplit(expense_id=expense.id, user_id=uid, amount=value) for uid, value in shares.items()])
        db.commit()
        db.refresh(expense)
        return {"id": expense.id, "trip_id": trip_id, "payer_id": payer, "amount": expense.amount,
                "description": expense.description, "category": expense.category,
                "participants": sorted(shares), "shares": {uid: value for uid, value in shares.items()}}

    @app.get("/api/trips/{trip_id}/expenses")
    def list_expenses(trip_id: str, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
        user = authenticated(authorization, db)
        member_or_404(db, trip_id, user.id)
        rows = db.scalars(select(Expense).where(Expense.trip_id == trip_id).order_by(Expense.occurred_at.desc())).all()
        return [{"id": e.id, "payer_id": e.payer_id, "amount": e.amount, "description": e.description,
                 "category": e.category, "occurred_at": e.occurred_at,
                 "participants": [split.user_id for split in e.splits],
                 "shares": {split.user_id: split.amount for split in e.splits}} for e in rows]

    @app.get("/api/trips/{trip_id}/settlements")
    def settlements(trip_id: str, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
        user = authenticated(authorization, db)
        member_or_404(db, trip_id, user.id)
        member_ids = [m.user_id for m in db.scalars(select(TripMember).where(TripMember.trip_id == trip_id)).all()]
        net = {uid: Decimal("0") for uid in member_ids}
        for expense in db.scalars(select(Expense).where(Expense.trip_id == trip_id)).all():
            net[expense.payer_id] += Decimal(str(expense.amount))
            for split in expense.splits:
                net[split.user_id] -= Decimal(str(split.amount))
        debtors = [[uid, -value] for uid, value in net.items() if value < Decimal("-0.005")]
        creditors = [[uid, value] for uid, value in net.items() if value > Decimal("0.005")]
        transfers = []
        i = j = 0
        while i < len(debtors) and j < len(creditors):
            amount = min(debtors[i][1], creditors[j][1]).quantize(Decimal("0.01"))
            transfers.append({"from_user_id": debtors[i][0], "to_user_id": creditors[j][0], "amount": amount})
            debtors[i][1] = (debtors[i][1] - amount).quantize(Decimal("0.01"))
            creditors[j][1] = (creditors[j][1] - amount).quantize(Decimal("0.01"))
            if debtors[i][1] < Decimal("0.005"):
                i += 1
            if creditors[j][1] < Decimal("0.005"):
                j += 1
        return {"balances": net, "suggested_transfers": transfers}

    @app.post("/api/routes/search")
    def route_search(payload: RouteSearch, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
        authenticated(authorization, db)
        try:
            result = search_transport(payload.source, payload.destination, payload.departure_date.isoformat() if payload.departure_date else None)
            return rank_routes(result, payload.budget, payload.preference)
        except ProviderUnavailable as error:
            raise HTTPException(status_code=503, detail={"code": "provider_unavailable", "message": str(error)})

    @app.post("/api/routes/recover")
    def route_recovery(payload: RouteSearch, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
        authenticated(authorization, db)
        if not payload.current_location:
            raise HTTPException(status_code=422, detail="current_location is required for route recovery")
        try:
            result = search_transport(payload.current_location, payload.destination, None)
            result = rank_routes(result, payload.remaining_budget, payload.preference)
            result["recovery_context"] = {
                "from": payload.current_location, "destination": payload.destination,
                "remaining_budget": payload.remaining_budget, "data_status": result["data_status"],
            }
            return result
        except ProviderUnavailable as error:
            raise HTTPException(status_code=503, detail={"code": "provider_unavailable", "message": str(error)})

    @app.post("/api/stays/search")
    def stay_search(payload: StaySearch, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
        authenticated(authorization, db)
        try:
            return search_stays(payload.destination, payload.max_price)
        except ProviderUnavailable as error:
            raise HTTPException(status_code=503, detail={"code": "provider_unavailable", "message": str(error)})

    @app.post("/api/trips/{trip_id}/location/me/start")
    def start_location(trip_id: str, payload: LocationSharingStart, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
        user = authenticated(authorization, db)
        member_or_404(db, trip_id, user.id)
        session_id = str(payload.session_id)
        share = db.scalar(select(LocationShare).where(LocationShare.trip_id == trip_id, LocationShare.user_id == user.id))
        if share and share.session_id == session_id and not share.is_sharing:
            raise HTTPException(status_code=409, detail="A stopped location session cannot be restarted")
        if not share:
            share = LocationShare(trip_id=trip_id, user_id=user.id, session_id=session_id,
                                  is_sharing=True, latitude=None, longitude=None,
                                  expires_at=utcnow() + timedelta(minutes=payload.duration_minutes))
            db.add(share)
        else:
            share.session_id = session_id
            share.is_sharing = True
            share.latitude = None
            share.longitude = None
            share.expires_at = utcnow() + timedelta(minutes=payload.duration_minutes)
        db.commit()
        return {"sharing": True, "expires_at": share.expires_at}

    @app.put("/api/trips/{trip_id}/location/me")
    def update_location(trip_id: str, payload: LocationUpdate, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
        user = authenticated(authorization, db)
        member_or_404(db, trip_id, user.id)
        share = db.scalar(select(LocationShare).where(LocationShare.trip_id == trip_id, LocationShare.user_id == user.id))
        if not share or not share.is_sharing or share.session_id != str(payload.session_id):
            raise HTTPException(status_code=409, detail="Location sharing session is no longer active")
        share.latitude, share.longitude = payload.latitude, payload.longitude
        share.expires_at = utcnow() + timedelta(minutes=payload.duration_minutes)
        db.commit()
        return {"sharing": True, "expires_at": share.expires_at}

    @app.get("/api/trips/{trip_id}/locations")
    def get_locations(trip_id: str, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
        user = authenticated(authorization, db)
        member_or_404(db, trip_id, user.id)
        now = utcnow()
        shares = db.scalars(select(LocationShare).where(LocationShare.trip_id == trip_id)).all()
        return [{"user_id": s.user_id, "latitude": s.latitude, "longitude": s.longitude,
                 "updated_at": s.updated_at, "expires_at": s.expires_at} for s in shares
                if s.is_sharing and s.latitude is not None and s.longitude is not None and aware_utc(s.expires_at) > now]

    @app.delete("/api/trips/{trip_id}/location/me", status_code=204)
    def stop_location(trip_id: str, session_id: str | None = None, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
        user = authenticated(authorization, db)
        member_or_404(db, trip_id, user.id)
        share = db.scalar(select(LocationShare).where(LocationShare.trip_id == trip_id, LocationShare.user_id == user.id))
        if share and session_id and share.session_id != session_id:
            return
        if not share:
            if session_id:
                share = LocationShare(trip_id=trip_id, user_id=user.id, session_id=session_id,
                                      is_sharing=False, latitude=None, longitude=None, expires_at=utcnow())
                db.add(share)
        else:
            share.is_sharing = False
            share.latitude = None
            share.longitude = None
            share.expires_at = utcnow()
        if share:
            db.commit()

    @app.websocket("/api/trips/{trip_id}/chat")
    async def trip_chat(websocket: WebSocket, trip_id: str, authorization: str | None = Header(default=None)):
        db = session_factory()
        try:
            if not authorization or not authorization.startswith("Bearer "):
                raise HTTPException(status_code=401, detail="Bearer token required")
            token = authorization[7:]
            user = current_user(token, db)
            member_or_404(db, trip_id, user.id)
        except (HTTPException, jwt.InvalidTokenError):
            await websocket.close(code=1008, reason="Authentication or trip membership required")
            db.close()
            return
        await websocket.accept()
        async with app.state.chat_lock:
            app.state.chat_connections.setdefault(trip_id, set()).add(websocket)
        try:
            history = db.scalars(select(ChatMessage).where(ChatMessage.trip_id == trip_id)
                                 .order_by(ChatMessage.created_at.desc()).limit(50)).all()
            for msg in reversed(history):
                await websocket.send_json({"id": msg.id, "sender_id": msg.sender_id, "message": msg.message, "created_at": msg.created_at.isoformat()})
            while True:
                message = (await websocket.receive_text()).strip()
                if not message or len(message) > 2000:
                    await websocket.send_json({"error": "Message must contain 1–2000 characters"})
                    continue
                saved = ChatMessage(trip_id=trip_id, sender_id=user.id, message=message)
                db.add(saved)
                db.commit()
                db.refresh(saved)
                event = {"id": saved.id, "sender_id": saved.sender_id,
                         "message": saved.message, "created_at": saved.created_at.isoformat()}
                async with app.state.chat_lock:
                    connections = list(app.state.chat_connections.get(trip_id, set()))
                for connection in connections:
                    try:
                        await connection.send_json(event)
                    except (RuntimeError, WebSocketDisconnect):
                        async with app.state.chat_lock:
                            app.state.chat_connections.get(trip_id, set()).discard(connection)
        except WebSocketDisconnect:
            pass
        finally:
            async with app.state.chat_lock:
                app.state.chat_connections.get(trip_id, set()).discard(websocket)
            db.close()

    return app


app = create_app()
