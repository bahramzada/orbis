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
DATABASE_URL=postgresql://postgres.<project-ref>:<password>@<pooler-host>:5432/postgres
DATABASE_SSL=require
DATABASE_AUTO_CREATE_TABLES=false
DATABASE_AUTO_MIGRATE=true
PORT=8000
```

With `DATABASE_AUTO_MIGRATE=true`, the backend applies Alembic migrations during startup. If you prefer manual migrations, set it to `false` and run this from the backend container shell before first production use:

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
VITE_ORBIS_API_TOKEN=change-this-shared-token
```

The frontend image writes `/config.js` on container start, so `VITE_API_BASE_URL` and `VITE_ORBIS_API_TOKEN` can be changed in Coolify without rebuilding the image.

## Important Notes

- `ORBIS_API_TOKEN` and `VITE_ORBIS_API_TOKEN` must match if backend auth is enabled.
- The frontend token is visible in the browser. Treat it as a deployment gate, not real user authentication.
- Keep `CORS_ALLOW_CREDENTIALS=false` unless a future auth system requires cookies.
- `APP_ENV=production` rejects local frontend origins, disabled DB TLS, and automatic table creation.
- If Supabase is temporarily unreachable, the API starts with in-memory defaults and logs that persistence is disabled for the current process.
