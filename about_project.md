# Orbis

## Project Goals

Orbis is an agentic AI workspace with one supervisor agent coordinating four worker agents.

## Architecture Overview

- Backend and frontend are separate applications.
- Backend owns configuration, OpenRouter API access, agent orchestration, and API contracts.
- Backend exposes `/health`, `/api/agents`, `/api/runs`, and `/api/runs/stream`.
- Agent graph is fixed at one supervisor and four workers: researcher, strategist, builder, reviewer.
- Supervisor creates a structured delegation plan, workers run in parallel, emits live workflow logs, and synthesizes the final output.
- Backend prompt templates are centralized in `backend/app/prompts.py` with strict planning, role-specific worker instructions, and compact final synthesis rules.
- Supabase/Postgres persistence is optional and controlled by `DATABASE_URL`.
- When database persistence is enabled, workflow runs and agent logs are stored in Postgres.
- Runtime performance controls include workflow concurrency limits, OpenRouter HTTP pooling/retry/cache settings, database pool sizing, and Prometheus-style metrics.
- Database schema management supports Alembic migrations for production deployments.
- Frontend owns agent management UI with two views:
  - Simple visual management
  - Habbo-style office management

## Tech Stack

- Backend: Python, FastAPI, Pydantic, HTTPX, SQLAlchemy, asyncpg, Alembic
- Frontend: React, TypeScript, Vite, lucide-react
- Configuration: `.env` files, no hardcoded secrets

## Project Structure

- `backend/app`: FastAPI app, settings, OpenRouter client, metrics, Supabase/Postgres persistence, logged agent orchestration, API schemas
- `backend/migrations`: Alembic migrations for workflow persistence tables and indexes
- `backend/tests`: backend test coverage
- `frontend/src`: React application, API client, types, and styling
