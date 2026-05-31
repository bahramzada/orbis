# Orbis

## Project Goals

Orbis is an agentic AI workspace with one supervisor agent coordinating four worker agents.

## Architecture Overview

- Backend and frontend are separate applications.
- Backend and frontend can be deployed as separate Coolify Dockerfile services.
- Backend owns configuration, OpenRouter API access, agent orchestration, and API contracts.
- Backend exposes `/health` with database status/error-code diagnostics, plus `/api/agents`, `/api/runs`, `/api/runs/stream`, plan preview, agent profile, memory, template, rerun, and evaluation endpoints.
- Backend provides database-backed register/login sessions with `HttpOnly` cookie auth, CSRF protection for browser mutations, role-based access for `guest`, `vip`, and `admin`, and admin controls for user roles plus system/registration availability.
- Agent graph is fixed at one supervisor and four workers: researcher, strategist, builder, reviewer.
- Supervisor creates a structured delegation plan, workers run in parallel, emits live workflow logs, and synthesizes the final output.
- Backend prompt templates are centralized in `backend/app/prompts.py` with strict planning, role-specific worker instructions, and compact final synthesis rules.
- Supabase/Postgres persistence is required and controlled by `DATABASE_URL`.
- Users, sessions, system settings, workflow runs, and agent logs are stored in Postgres.
- Production mode requires a backend bootstrap bearer token for server clients, secure cookie settings, strict non-local CORS origins with credentials, encrypted database TLS, and Alembic-managed schemas.
- Runtime performance controls include workflow concurrency limits, OpenRouter HTTP pooling/retry/cache settings, database pool sizing, and Prometheus-style metrics.
- Authentication hot paths use throttled expired-session cleanup, throttled session touch writes, and a short system-settings cache to reduce routine database roundtrips without weakening cookie/CSRF controls.
- Database schema management uses Alembic migrations; Docker/Coolify containers run migrations in the backend entrypoint before Uvicorn starts, with Postgres advisory locking and bounded migration timeouts.
- AI capability features include Agent Studio profiles, human-in-the-loop plan review, selected project memory injection, safe internal tool-call logging, run inspector metrics, worker/final reruns, evaluation scoring, workflow templates, structured output modes, and optional second-stage reviewer collaboration.
- Frontend owns agent management UI with two views:
  - Simple visual management
  - Habbo-style office management
- Frontend blocks the workspace behind login/register and exposes admin controls through a separate `/admin` console for admin users.

## Tech Stack

- Backend: Python, FastAPI, Pydantic, HTTPX, SQLAlchemy, asyncpg, Alembic, Argon2id password hashing
- Frontend: React, TypeScript, Vite, lucide-react
- Configuration: `.env` files, no hardcoded secrets
- Security: `HttpOnly` cookie sessions, CSRF tokens, Argon2id password hashing with PBKDF2 upgrade, role-based admin controls, environment-backed bootstrap tokens, sanitized public errors, bounded runtime caches, protected metrics, strict request schemas, CSP/security headers

## Project Structure

- `backend/app`: FastAPI app, settings, auth/session helpers, OpenRouter client, metrics, Supabase/Postgres persistence, migration runner, prompt builders, logged agent orchestration, capability endpoints, API schemas
- `backend/Dockerfile`: Coolify-ready backend API container with migration entrypoint and bounded healthcheck startup window
- `backend/docker-entrypoint.sh`: production container bootstrap that runs Alembic migrations before serving API traffic
- `backend/migrations`: Alembic migrations for workflow persistence tables and indexes
- `backend/tests`: backend test coverage
- `backend/requirements.lock`: pinned backend dependency set for reproducible production installs
- `frontend/src`: React application shell, API client, shared constants/types, and styling
- `frontend/src/components`: modular dashboard components for graph views, capability controls, activity logs, run summaries, and Markdown rendering
- `frontend/Dockerfile`: Coolify-ready static frontend container with runtime `/config.js`
