# Travel Assist

Travel Assist is an Android (Kotlin, Jetpack Compose, Material 3) client and FastAPI service for Indian solo and group travel. The app talks only to the configured backend. It never treats a demo response as live transport, accommodation, or booking information.

## What works in this MVP

- JWT registration/login, password hashing, and authenticated API access.
- Trip creation, membership, invitations, itinerary sharing, and a trip dashboard.
- Route search/recovery and accommodation discovery provider interfaces. With no authorized provider configured, these return an explicit `provider_unavailable` error. `DEMO_MODE=true` opts into clearly marked synthetic development results.
- Trip expense records, equal/custom participant splits, balances, and greedy settlement suggestions.
- Trip-member WebSocket chat with persisted messages.
- Opt-in expiring live-location updates, member access checks, and immediate stop-sharing.
- Android login, dashboard, route search, trip creation, expense entry, and trip chat screens.
- PostgreSQL Alembic migration and SQLite-backed automated backend tests.

This is not a ticketing or booking system. It cannot confirm inventory, fares, or availability unless an authorized live provider is configured. The Android project has not been built into an APK in this environment; see [Build status](#build-status).

## Layout

- `android/` — Android Studio project.
- `backend/` — FastAPI, SQLAlchemy, provider interfaces, and Alembic migrations.
- `docker-compose.yml` — local PostgreSQL service.
- `.env.example` — configuration template.

## Run the backend

1. Install Python 3.11+ and PostgreSQL 15+ (or use Docker Compose).
2. Copy `.env.example` to `.env`; set a unique `JWT_SECRET` and a PostgreSQL `DATABASE_URL`.
3. Start PostgreSQL: `docker compose up -d db`.
4. Create a virtual environment and install `backend/requirements.txt`.
5. From `backend/`, run `alembic upgrade head` then `uvicorn app.main:app --reload`.
6. API docs are served at `http://localhost:8000/docs`.

The app does not create tables at startup by default. `AUTO_CREATE_TABLES=true` is available only as a local-development convenience. Apply Alembic migrations before starting a deployed instance.

## Run tests

From `backend/`:

```powershell
python -m pip install -r requirements.txt
python -m pytest
```

Tests use a temporary SQLite database and do not require PostgreSQL or provider credentials.

## Android

Open `android/` in Android Studio (JDK 17 and Android SDK 35 required), set `BuildConfig.API_BASE_URL` to a reachable backend URL, then build `app` > `assembleDebug`. For an emulator, the default development URL is `http://10.0.2.2:8000/`. For a physical device, use the development machine's LAN address and permit cleartext traffic only in a local development build; production must use HTTPS.

The Android client currently expects a backend accessible over HTTP for local development. Do not ship a cleartext configuration. No signing key is included.

## Providers and data integrity

There are no provider credentials or live integrations bundled. The provider interfaces fail closed with HTTP 503 when unavailable; they do not scrape websites or infer schedules, fares, or room availability. The optional demo adapter is synthetic and marks each result `data_status=demo` and `is_bookable=false`.

Potential authorized integrations to evaluate:

- **Rail**: seek an official IRCTC/CRIS integration or a currently authorized partner contract. IRCTC access is governed by its official [website and commercial processes](https://www.irctc.com/); no public train inventory API is assumed here.
- **Bus**: integrate an operator, aggregator, or distribution partner only under its API and data-use agreement. Contact providers such as redBus through their official business channels to confirm a supported API and current partner eligibility; a public inventory API is not assumed here.
- **Accommodation**: [Booking.com Demand API](https://developers.booking.com/demand/docs) is a partner-access option to evaluate; verify eligibility, Indian property coverage, permitted use, and current commercial terms directly. Property direct integrations are another option.
- **Maps/geocoding**: Google Maps Platform Routes API is a commercial option (see [Routes API documentation](https://developers.google.com/maps/documentation/routes)). OpenStreetMap data may be used under its attribution/licensing terms, but the public Nominatim endpoint has strict usage limits and is not an unrestricted production geocoder; see the [Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/).
- **Stays**: use a licensed accommodation distribution API or property direct integration, subject to supplier agreements; the implementation does not scrape listings.

Confirm provider coverage, rights, pricing, refresh/attribution requirements, and production limits before enabling an adapter.

## Security and privacy

- Passwords use Argon2id hashes. JWT signing requires a configured secret.
- All trip resources are scoped to trip members; chat and location enforce membership.
- Location is opt-in, expires automatically, and can be stopped by deleting the active share.
- Keep secrets in environment/secret storage, never in the Android app or source control. Add HTTPS, rate limits, email verification, key rotation, backups, and operational monitoring before production deployment.
- The MVP does not implement push notifications, payment/booking flows, or production-grade account recovery.

## Build status

Source and backend tests are the deliverables available from this workspace. The current environment has no JDK, Android SDK, or Gradle installation, so an installable APK could not be generated or verified here. Install the Android toolchain described above and build from `android/`.
