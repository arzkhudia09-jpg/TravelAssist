# Security and readiness review

Review scope: repository source, configuration, migrations, tests, and a local Android debug build. This is an engineering review, not a penetration test or a production security certification.

## Addressed in the current implementation

- Passwords are Argon2id hashed; API access uses signed, expiring JWTs.
- Trip resources, chat, expenses, and locations enforce trip membership.
- Provider configuration endpoints use an environment allowlist for administrators; there is no public self-assigned admin role.
- Provider credentials are encrypted with Fernet before database persistence and are never included in API responses. The encryption key is supplied outside the database.
- Provider IDs are selected from a fixed catalog. No user-supplied code or arbitrary callback URL can execute.
- Locations are opt-in, time-limited, and removable; provider search fails closed if no authorized data adapter exists.
- Android release builds require an explicit HTTPS API base URL; release signing material is read from environment variables, not source.

## Remaining production blockers

- No transport, accommodation, maps, notification, or AI provider adapter and credentials are configured. The catalog is management scaffolding, not proof of a working external connection.
- No release keystore was supplied. The checked-in source cannot create a distributable signed release APK without operator-managed signing secrets.
- No physical-device or emulator install/launch test was available during this review.
- Add rate limiting, refresh/revocation strategy, account recovery, monitoring, and structured audit retention before public deployment.
- Configure HTTPS at the deployment edge, restricted production CORS origins, database backups, restore drills, and secret-manager-backed key rotation.
- The chat broadcaster uses process memory; production horizontal scaling requires shared pub/sub.
- User add-on controls currently persist preferences; Weather, currency, push notifications, and an AI response provider are not implemented.

## Verification

- Backend: `python -m pytest -q` — 11 tests passed.
- Alembic: fresh SQLite upgrade reached `0002_integrations` (head).
- Android: a debug APK was successfully assembled before the Integrations Center UI iteration. It is available at `android/app/build/outputs/apk/debug/app-debug.apk`, but its SHA-256 is `5883C9F16ABE0E2AB74342E7F04A4075B5F05C992AAC78C20AC4037D77AC51BC`; the file predates the latest integration-center source and must not be considered the final deliverable for this phase. The latest source rebuild was blocked by JVM native/Metaspace memory exhaustion while the editor's Java language servers were consuming the host's remaining commit memory.
- No external penetration test, device UI test, or live-provider test was performed.
