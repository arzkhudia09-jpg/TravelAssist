# Travel Assist

Travel Assist is an Android (Kotlin, Jetpack Compose, Material 3) client and FastAPI service for Indian solo and group travel. The app talks only to the configured backend. It never treats a demo response as live transport, accommodation, or booking information.

## What works in this MVP

- JWT registration/login, password hashing, and authenticated API access.
- Trip creation, membership, invitations, itinerary sharing, and a trip dashboard.
- Route search/recovery and accommodation discovery provider interfaces. With no authorized provider configured, these return an explicit `provider_unavailable` error. `DEMO_MODE=true` opts into clearly marked synthetic development results.
- Trip expense records, equal/custom participant splits, balances, and greedy settlement suggestions.
- Trip-member WebSocket chat with persisted messages.
- Opt-in expiring live-location updates, member access checks, and immediate stop-sharing.
- Android login, dashboard, route search, trip creation, expense entry, trip chat, and Integrations & Add-ons Center screens.
- Admin-only integration configuration with Fernet-encrypted credentials, a fixed provider catalog, health-test status, and per-user add-on preferences.
- PostgreSQL Alembic migration and SQLite-backed automated backend tests.

This is not a ticketing or booking system. It cannot confirm inventory, fares, or availability unless an authorized live provider is configured. The integration catalog is configuration scaffolding: no live provider adapter or credential is included, so connection tests report `provider_unavailable` until one is implemented and authorized.

## Layout

- `android/` — Android Studio project.
- `backend/` — FastAPI, SQLAlchemy, provider interfaces, and Alembic migrations.
- `docker-compose.yml` — local PostgreSQL service.
- `docs/` — deployment guide and security/readiness review.
- `.github/workflows/ci.yml` — backend tests, Android compile/unit-test task, and debug APK artifact upload.
- `.env.example` — configuration template.

## Run the backend

1. Install Python 3.11+ and PostgreSQL 15+ (or use Docker Compose).
2. Copy `.env.example` to `.env`; set a unique `JWT_SECRET`, a PostgreSQL `DATABASE_URL`, and `ADMIN_EMAILS` for provider administration.
3. Generate `INTEGRATION_ENCRYPTION_KEY` with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` and keep it in secret storage. Losing or rotating this key without re-encrypting credentials makes saved credentials unreadable.
4. Start PostgreSQL: `docker compose up -d db`.
5. Create a virtual environment and install `backend/requirements.txt`.
6. From `backend/`, run `alembic upgrade head` then `uvicorn app.main:app --reload`.
7. API docs are served at `http://localhost:8000/docs`.

Alternatively, follow [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) to run the API in Docker Compose. The app does not create tables at startup by default. `AUTO_CREATE_TABLES=true` is available only as a local-development convenience. Apply Alembic migrations before starting a deployed instance.

## Run tests

From `backend/`:

```powershell
python -m pip install -r requirements.txt
python -m pytest
```

Tests use a temporary SQLite database and do not require PostgreSQL or provider credentials.

## Android

[Download the installable debug APK](downloads/TravelAssist-debug.apk).

Open `android/` in Android Studio (JDK 17 and Android SDK 35 required), then build `app` > `assembleDebug`. From PowerShell, `gradle --no-daemon assembleDebug` creates `android/app/build/outputs/apk/debug/app-debug.apk`. For an emulator, the development URL is `http://10.0.2.2:8000/`; for a physical device set `-PapiBaseUrl=http://<host-lan-ip>:8000/`. Cleartext is enabled only for debug builds.

The sign-in screen also lets you set the API server URL after installing the APK. Use the public HTTPS URL of a deployed backend, or a reachable LAN URL for local development; the backend must be running and initialized before registration or sign-in will work. The app does not bundle or host the backend.

Release builds require `releaseApiBaseUrl` or `TRAVEL_ASSIST_API_BASE_URL` to be set to HTTPS. Release signing variables are documented in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md); no signing key is included.

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

## Build and verification status

An earlier debug APK was successfully generated at `android/app/build/outputs/apk/debug/app-debug.apk` during this work. Its SHA-256 is `5883C9F16ABE0E2AB74342E7F04A4075B5F05C992AAC78C20AC4037D77AC51BC`. It predates the current Integrations & Add-ons source and is therefore not the final APK for the integrations-center phase. The initial compilation also found and fixed Kotlin package and API/UI call-site errors. Backend tests pass, and the fresh Alembic migration path was validated. Later source rebuild attempts could not complete because the host ran out of JVM native/Metaspace/commit memory; there is no attached emulator or device, so installation and launch were not verified. Rebuild on a host with at least 8 GB free RAM in an environment with fewer concurrent Java processes. See [docs/SECURITY_AUDIT.md](docs/SECURITY_AUDIT.md) for precise current limitations.

No signed release APK is included: release signing credentials are not available. No live transportation, stay, mapping, notification, or AI provider credentials/adapters are included. The app must not be presented as production-ready until those blockers and the remaining hardening actions in the security review are addressed.
