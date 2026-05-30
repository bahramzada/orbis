# Orbis

## Project Goals

Orbis is an agentic AI workspace with one supervisor agent coordinating four worker agents.

## Architecture Overview

- Backend and frontend are separate applications.
- Backend and frontend can be deployed as separate Coolify Dockerfile services.
- Backend owns configuration, OpenRouter API access, agent orchestration, and API contracts.
- Backend exposes `/health`, `/api/agents`, `/api/runs`, `/api/runs/stream`, plan preview, agent profile, memory, template, rerun, and evaluation endpoints.
- Agent graph is fixed at one supervisor and four workers: researcher, strategist, builder, reviewer.
- Supervisor creates a structured delegation plan, workers run in parallel, emits live workflow logs, and synthesizes the final output.
- Backend prompt templates are centralized in `backend/app/prompts.py` with strict planning, role-specific worker instructions, and compact final synthesis rules.
- Supabase/Postgres persistence is optional and controlled by `DATABASE_URL`.
- When database persistence is enabled, workflow runs and agent logs are stored in Postgres.
- Production mode requires bearer-token protection for protected API endpoints, strict non-local CORS origins, verified database TLS, and Alembic-managed schemas.
- Runtime performance controls include workflow concurrency limits, OpenRouter HTTP pooling/retry/cache settings, database pool sizing, and Prometheus-style metrics.
- Database schema management supports Alembic migrations for production deployments.
- AI capability features include Agent Studio profiles, human-in-the-loop plan review, selected project memory injection, safe internal tool-call logging, run inspector metrics, worker/final reruns, evaluation scoring, workflow templates, structured output modes, and optional second-stage reviewer collaboration.
- Frontend owns agent management UI with two views:
  - Simple visual management
  - Habbo-style office management

## Tech Stack

- Backend: Python, FastAPI, Pydantic, HTTPX, SQLAlchemy, asyncpg, Alembic
- Frontend: React, TypeScript, Vite, lucide-react
- Configuration: `.env` files, no hardcoded secrets
- Security: environment-backed tokens, sanitized public errors, bounded runtime caches, protected metrics, strict request schemas

## Project Structure

- `backend/app`: FastAPI app, settings, OpenRouter client, metrics, Supabase/Postgres persistence, prompt builders, logged agent orchestration, capability endpoints, API schemas
- `backend/Dockerfile`: Coolify-ready backend API container
- `backend/migrations`: Alembic migrations for workflow persistence tables and indexes
- `backend/tests`: backend test coverage
- `backend/requirements.lock`: pinned backend dependency set for reproducible production installs
- `frontend/src`: React application shell, API client, shared constants/types, and styling
- `frontend/src/components`: modular dashboard components for graph views, capability controls, activity logs, run summaries, and Markdown rendering
- `frontend/Dockerfile`: Coolify-ready static frontend container with runtime `/config.js`
