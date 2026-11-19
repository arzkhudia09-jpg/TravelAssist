# Deployment and release guide

## Architecture

The FastAPI backend uses synchronous SQLAlchemy and the `psycopg` PostgreSQL driver. Neon supplies the production database:

- `DATABASE_URL` — Neon pooled connection string used by application sessions.
- `DATABASE_URL_DIRECT` — direct Neon connection string used by Alembic migrations.

Local development and tests may use SQLite only by setting an explicit SQLite URL or passing a test URL to `create_app`. Production is PostgreSQL-only and fails startup when `DATABASE_URL` or `ENVIRONMENT=production` is invalid. The Docker image does not create or migrate SQLite files.

## Neon setup

1. Create or select a Neon project and a database branch for development/testing.
2. Copy the pooled connection string into `DATABASE_URL`.
3. Copy the direct connection string into `DATABASE_URL_DIRECT`.
4. Confirm both strings use `postgresql+psycopg://` (or `postgresql://`) and include `sslmode=require`.
5. Create a least-privilege migration role if migrations are run separately from runtime, or use separate migration/runtime credentials.
6. Never put Neon credentials in source control or the Android APK.

The SQLAlchemy engine uses `pool_pre_ping`, a 300-second recycle, bounded pooling, a 15-second pool wait, and a 10-second connection timeout. It validates PostgreSQL connections with `pool_pre_ping` after Neon compute suspension. Neon transaction pooling is intended for normal application traffic; migrations use the direct endpoint.

## Migration commands

Create an explicit backup/checkpoint before the first or every destructive migration. Run migrations once from a controlled release step, never concurrently in application replicas:

```powershell
cd backend
$env:DATABASE_URL_DIRECT="postgresql+psycopg://...direct...?...sslmode=require"
$env:DATABASE_URL="postgresql+psycopg://...pooled...?...sslmode=require"
$env:ENVIRONMENT="production"
alembic upgrade head
alembic current
```

To generate a future migration:

```powershell
alembic revision --autogenerate -m "describe_schema_change"
alembic upgrade head
```

Review every generated migration before applying it. Existing migrations are preserved and Alembic version tracking makes upgrades repeatable.

## Render deployment

The repository includes `render.yaml` for an infrastructure-as-code web service:

- Runtime: Docker
- Dockerfile: `backend/Dockerfile`
- Docker build context: repository root
- Health check: `/health`
- Pre-deploy command: `alembic upgrade head`
- Container port: Render's `PORT` value
- Bind address: `0.0.0.0`

Create the service from `render.yaml`, then set every `sync: false` secret in the Render Dashboard:

```text
DATABASE_URL
DATABASE_URL_DIRECT
CORS_ORIGINS
ADMIN_EMAILS
INTEGRATION_ENCRYPTION_KEY
```

Set `ENVIRONMENT=production`, `AUTO_CREATE_TABLES=false`, `DEMO_MODE=false`, and `ACCESS_TOKEN_MINUTES=60`. Render pre-deploy migrations run once as a release step. Do not start migrations in the application container command or add them to the Docker startup command.

After deployment:

1. Open `https://<render-service>.onrender.com/health`.
2. Open `https://<render-service>.onrender.com/ready`.
3. Verify `alembic current` against the direct Neon endpoint.
4. Configure the Android release URL with `TRAVEL_ASSIST_API_BASE_URL=https://<render-service>.onrender.com/`.
5. Build the release APK and verify sign-in, trips, and WSS chat.

## Local backend with Docker Compose

1. Copy `.env.example` to `.env`.
2. Set `JWT_SECRET` to a unique random value of at least 32 characters.
3. Generate an integration encryption key with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` and set `INTEGRATION_ENCRYPTION_KEY`.
4. Set `ADMIN_EMAILS` to comma-separated trusted operator accounts.
5. Run `docker compose up -d db`.
6. Apply migrations with `docker compose run --rm api alembic upgrade head`.
7. Start the API with `docker compose up -d api`.
8. Verify `http://localhost:8000/health` and browse `/docs`.

Do not use the example secrets in a deployed environment. Back up PostgreSQL and test restoration before upgrades. Take a backup before applying migrations; deploy migrations as a separate one-shot step and roll back using a tested database restore plan, not an automatic downgrade.

## Android debug APK

Use JDK 17, Android SDK Platform 35, and Gradle 8.9. From `android/`:

```powershell
gradle --no-daemon assembleDebug
```

For an emulator, the debug base URL defaults to `http://10.0.2.2:8000/`. For a device, pass a reachable development URL using `-PapiBaseUrl=http://<host-lan-ip>:8000/`.

## Release APK

Set a production HTTPS base URL in `TRAVEL_ASSIST_API_BASE_URL` (or Gradle property `releaseApiBaseUrl`). For signed output, configure these environment variables from a secure CI secret store:

- `ANDROID_KEYSTORE_PATH`
- `ANDROID_KEYSTORE_PASSWORD`
- `ANDROID_KEY_ALIAS`
- `ANDROID_KEY_PASSWORD`

Then run `gradle --no-daemon assembleRelease`. The keystore must be provisioned and backed up by the release owner. Never commit it or put its password in Gradle files. Without all signing variables, Gradle does not sign the release artifact.

## Production deployment checklist

- Terminate TLS at a trusted reverse proxy/load balancer; expose only HTTPS publicly.
- Configure production `DATABASE_URL`, `JWT_SECRET`, `INTEGRATION_ENCRYPTION_KEY`, and exact `CORS_ORIGINS` using a managed secret store.
- Use a separately managed PostgreSQL instance, least-privilege DB role, automated encrypted backups, retention, and restore drills.
- Apply Alembic migrations during a controlled release before routing traffic to the new API.
- Add rate limiting, request/error monitoring, log redaction, alerting, and a shared WebSocket pub/sub backend before horizontal scaling.
- Configure only providers with a current contract and authorized API access; test their terms, coverage, limits, and attribution requirements.
