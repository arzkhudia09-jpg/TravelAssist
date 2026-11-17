# Travel Assist API

Interactive OpenAPI documentation: `/docs` (Swagger UI) and `/openapi.json`.

All `/api` endpoints require `Authorization: Bearer <access_token>` except registration and login. Timestamps are ISO 8601. Monetary values are INR. IDs are UUID strings.

## Authentication

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/auth/register` | Register (`email`, `password` of at least 10 characters, optional `username`); returns token and user |
| POST | `/api/auth/login` | Sign in |
| GET | `/api/auth/me` | Current account |

## Trips and dashboard

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/dashboard` | Upcoming/ongoing/completed trips, invitations, saved routes |
| GET, POST | `/api/trips` | List memberships / create a solo or group trip |
| GET | `/api/trips/{trip_id}` | Member-only trip details, members, shared itinerary |
| POST | `/api/trips/{trip_id}/invitations` | Invite an existing or future account by email |
| GET | `/api/invitations` | Pending invitations for the signed-in user |
| POST | `/api/invitations/{invitation_id}/accept` | Accept an invitation addressed to the signed-in account |
| PATCH | `/api/trips/{trip_id}/members/me` | Set a trip nickname |
| POST | `/api/trips/{trip_id}/itinerary` | Add a shared itinerary item |
| GET, POST, DELETE | `/api/saved-routes` | List, save, and delete the signed-in user's route searches |

## Transport and stays

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/routes/search` | Search transport with optional date, budget, and preference |
| POST | `/api/routes/recover` | Search from `current_location` to destination using remaining budget |
| POST | `/api/stays/search` | Search accommodation with optional maximum price |

Without an authorized provider, searches return HTTP 503 with `detail.code=provider_unavailable`. Only `DEMO_MODE=true` returns synthetic fixtures, marked `data_status=demo` and `is_bookable=false`.

## Expenses, chat, and location

| Method | Path | Purpose |
|---|---|---|
| POST, GET | `/api/trips/{trip_id}/expenses` | Record/list trip expenses with payer and equal or custom participant shares |
| GET | `/api/trips/{trip_id}/settlements` | Net balances and suggested transfers |
| WebSocket | `/api/trips/{trip_id}/chat` | Authenticated trip chat; provide the bearer token in the `Authorization` handshake header |
| POST | `/api/trips/{trip_id}/location/me/start` | Start an opt-in location session with a fresh UUID and expiry (1–1440 minutes) |
| PUT | `/api/trips/{trip_id}/location/me` | Update coordinates for the active sharing session |
| GET | `/api/trips/{trip_id}/locations` | Member-only, unexpired trip member locations |
| DELETE | `/api/trips/{trip_id}/location/me` | Stop the caller's sharing immediately; invalidates that update session |
| GET | `/api/trips/{trip_id}/assistant/context` | Persisted trip facts for a future assistant provider; no AI generation |

The current WebSocket broadcaster is in-process; multi-instance deployments need a shared pub/sub adapter. The Android client sends location updates about every 15 seconds while the app process is running. Location is opt-in, expires automatically, and is deleted immediately when the user stops sharing.

## Errors and provider states

Validation errors use HTTP 422. Unauthenticated requests use 401. Nonmember trip access returns 404 to avoid disclosing trip existence. Unconfigured data sources return 503; no provider failure is converted into fake live data.
