# Coolify Deployment

Orbis is deployed as two separate Coolify applications: one backend API and one frontend static app.

## Backend App

- **Build Pack:** Dockerfile
- **Base Directory:** `backend`
- **Dockerfile:** `backend/Dockerfile`
- **Port:** `8000`
- **Health Check Path:** `/health`

Required environment variables:

```bash
APP_ENV=production
ORBIS_API_TOKEN=change-this-shared-token
OPENROUTER_API_KEY=change-this-openrouter-key
FRONTEND_ORIGINS=https://your-frontend-domain.example
CORS_ALLOW_CREDENTIALS=true
AUTH_SESSION_TTL_HOURS=720
AUTH_SESSION_CLEANUP_INTERVAL_SECONDS=900
AUTH_SESSION_TOUCH_INTERVAL_SECONDS=300
AUTH_RATE_LIMIT_MAX_ATTEMPTS=5
AUTH_RATE_LIMIT_WINDOW_SECONDS=900
SESSION_COOKIE_NAME=orbis_session
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_SAMESITE=lax
SESSION_COOKIE_DOMAIN=
SYSTEM_SETTINGS_CACHE_TTL_SECONDS=30
DATABASE_URL=postgresql://postgres.<project-ref>:<password>@<pooler-host>:5432/postgres
DATABASE_REQUIRED=true
DATABASE_SSL=insecure-require
DATABASE_AUTO_CREATE_TABLES=false
DATABASE_AUTO_MIGRATE=true
DATABASE_MIGRATION_LOCK_ID=739421317
DATABASE_MIGRATION_LOCK_TIMEOUT_SECONDS=30
DATABASE_MIGRATION_STATEMENT_TIMEOUT_SECONDS=240
PORT=8000
```

With `DATABASE_AUTO_MIGRATE=true`, the backend Docker entrypoint applies Alembic migrations before starting Uvicorn and then disables in-process migration for that container. This is the recommended default for simple Coolify deployments because updates bootstrap the schema without manual shell commands.

If you prefer a separate migration release step, set it to `false` and run this from the backend container shell before first production use:

```bash
alembic upgrade head
```

## Frontend App

- **Build Pack:** Dockerfile
- **Base Directory:** `frontend`
- **Dockerfile:** `frontend/Dockerfile`
- **Port:** `80`

Required environment variables:

```bash
VITE_API_BASE_URL=https://your-backend-domain.example
```

The frontend image writes `/config.js` on container start, so `VITE_API_BASE_URL` can be changed in Coolify without rebuilding the image.

Users should register/login with database-backed sessions; new accounts start as `guest`.

To create the first admin after a fresh deploy, register your account, then run this in Supabase SQL editor:

```sql
UPDATE users SET role = 'admin' WHERE email = 'you@example.com';
```

## Important Notes

- `ORBIS_API_TOKEN` is a backend bootstrap/server token. Do not expose it through the public frontend.
- Keep `CORS_ALLOW_CREDENTIALS=true` with strict `FRONTEND_ORIGINS`; Orbis browser auth uses an `HttpOnly` cookie session plus CSRF token.
- Keep `SESSION_COOKIE_SECURE=true` in production. Use `SESSION_COOKIE_SAMESITE=lax` for same-site subdomains, or `none` only when frontend/backend are on different sites and HTTPS is active.
- Keep backend **Port** set to `8000` unless you intentionally change `PORT` in the backend environment.
- `APP_ENV=production` rejects local frontend origins, disabled DB TLS, and automatic table creation.
- If Supabase is missing or unreachable, the backend refuses to start because auth, roles, settings, and run history require Postgres.
