# Deployment and release guide

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
