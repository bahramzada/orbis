<div align="center">

# Orbis

### Agent Control Room for configurable supervisor-worker AI workflows

[![Backend](https://img.shields.io/badge/backend-FastAPI-0f766e?style=for-the-badge)](#backend)
[![Frontend](https://img.shields.io/badge/frontend-React%20%2B%20Vite-1f2937?style=for-the-badge)](#frontend)
[![Database](https://img.shields.io/badge/database-Supabase%20Postgres-166534?style=for-the-badge)](#database)
[![LLM](https://img.shields.io/badge/llm-OpenRouter-b45309?style=for-the-badge)](#configuration)

Orbis turns one user task into a structured agentic workflow: a supervisor plans the work, four specialized workers execute it, and the supervisor synthesizes a final answer with logs, memory, reruns, and evaluation support.

</div>

---

## Table of Contents

- [Why Orbis](#why-orbis)
- [Core Capabilities](#core-capabilities)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Database](#database)
- [API Surface](#api-surface)
- [Validation](#validation)
- [Project Structure](#project-structure)
- [Production Notes](#production-notes)

## Why Orbis

Most AI task runners hide what happens between prompt and final answer. Orbis is built as an operational control room: you can inspect the plan, tune each agent, attach project memory, watch live logs, rerun weak steps, and compare output quality.

```mermaid
flowchart LR
    User["User Task"] --> Supervisor["Supervisor"]
    Supervisor --> Plan["Human-Reviewable Plan"]
    Plan --> Researcher["Researcher"]
    Plan --> Strategist["Strategist"]
    Plan --> Builder["Builder"]
    Plan --> Reviewer["Reviewer"]
    Researcher --> Synthesis["Final Synthesis"]
    Strategist --> Synthesis
    Builder --> Synthesis
    Reviewer --> Synthesis
    Synthesis --> Result["Readable Output"]
    Memory["Project Memory"] -. selected context .-> Supervisor
    Memory -. selected context .-> Researcher
    Runs["Run History"] -. inspector/rerun .-> Synthesis
```

## Core Capabilities

| Area | What it does |
| --- | --- |
| Agent Studio | Configure worker name, role, goal, system prompt, model, temperature, token limit, and enabled state. |
| Plan Review | Preview the supervisor delegation plan, edit worker objectives, disable agents, then run. |
| Memory Layer | Store reusable project context such as company background, brand voice, and technical constraints. |
| Live Workflow Logs | Stream agent activity, tool-call events, failures, and final results through the UI. |
| Run Inspector | View model, duration, estimated tokens, estimated cost, tool calls, plan, worker outputs, and final answer. |
| Rerun / Improve | Rerun one worker or only the final synthesis without restarting the entire workflow. |
| Evaluation Lab | Score runs with a lightweight rubric for completeness, actionability, and hallucination risk. |
| Workflow Templates | Start from presets such as market research, architecture review, startup launch, UI audit, and checklist workflows. |
| Structured Outputs | Request Markdown, JSON, checklist, table, roadmap, PRD, or test-plan style final outputs. |

## Architecture

Orbis keeps backend and frontend responsibilities clearly separated.

```mermaid
flowchart TB
    subgraph Frontend["React / Vite Frontend"]
        UI["Agent Control Room"]
        Studio["Agent Studio"]
        Inspector["Run Inspector"]
        Office["Visual + Office Views"]
    end

    subgraph Backend["FastAPI Backend"]
        API["REST + NDJSON Stream API"]
        Orchestrator["Agent Orchestrator"]
        Prompts["Prompt Builders"]
        Metrics["Prometheus Metrics"]
    end

    subgraph External["External Services"]
        OpenRouter["OpenRouter Chat API"]
        Supabase["Supabase Postgres"]
    end

    UI --> API
    Studio --> API
    Inspector --> API
    Office --> API
    API --> Orchestrator
    Orchestrator --> Prompts
    Orchestrator --> OpenRouter
    API --> Supabase
    API --> Metrics
```

## Tech Stack

| Layer | Tools |
| --- | --- |
| Backend | Python, FastAPI, Pydantic, HTTPX, SQLAlchemy, asyncpg, Alembic |
| Frontend | React, TypeScript, Vite, lucide-react |
| AI Provider | OpenRouter-compatible chat completions |
| Persistence | Supabase/Postgres with optional local disabled mode |
| Observability | Structured logs, request metrics, workflow metrics, `/metrics` endpoint |
| Configuration | `.env` files, no hardcoded secrets |

## Quick Start

### Backend

```bash
cd backend
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

The backend starts on `http://127.0.0.1:8000` by default.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

The Vite dev server usually starts on `http://127.0.0.1:5173` or the next available port.

## Configuration

Set the OpenRouter values in `backend/.env`:

```bash
OPENROUTER_API_KEY=your_openrouter_key
OPENROUTER_MODEL=openai/gpt-4.1-mini
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

Useful runtime controls:

```bash
WORKFLOW_MAX_CONCURRENCY=2
WORKFLOW_STEP_TIMEOUT_SECONDS=90
WORKFLOW_CACHE_TTL_SECONDS=0
OPENROUTER_MAX_CONNECTIONS=20
OPENROUTER_MAX_KEEPALIVE=10
OPENROUTER_RETRY_ATTEMPTS=3
LOG_LEVEL=INFO
ENABLE_METRICS=true
```

## Database

Supabase/Postgres is optional. If `DATABASE_URL` is empty or still contains `[YOUR-PASSWORD]`, persistence remains disabled and the app can still run for development.

```bash
DATABASE_URL=postgresql://postgres.<project-ref>:<password>@<pooler-host>:5432/postgres
DATABASE_SSL=require
DATABASE_POOL_SIZE=3
DATABASE_MAX_OVERFLOW=2
DATABASE_POOL_TIMEOUT_SECONDS=10
DATABASE_AUTO_CREATE_TABLES=true
```

If your database password contains reserved URL characters, URL-encode it before placing it in the connection string.

For production schema management, prefer Alembic:

```bash
cd backend
alembic upgrade head
```

Main persisted entities:

- `workflow_runs`
- `workflow_logs`
- `agent_profiles`
- `workflow_templates`
- `memory_items`
- `tool_calls`
- `run_evaluations`

## API Surface

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Service, provider, database, and model health. |
| `GET` | `/metrics` | Prometheus-style metrics. |
| `GET` | `/api/agents` | Default supervisor-worker graph. |
| `GET` / `PUT` | `/api/agent-profiles` | Agent Studio profile configuration. |
| `GET` | `/api/templates` | Workflow template presets. |
| `GET` / `POST` | `/api/memories` | Project memory list and creation. |
| `POST` | `/api/plans` | Supervisor plan preview for human review. |
| `GET` | `/api/runs` | Persisted workflow run history. |
| `GET` | `/api/runs/{run_id}` | Full run inspector detail. |
| `POST` | `/api/runs` | Run a full workflow and return the final object. |
| `POST` | `/api/runs/stream` | Stream logs, tool calls, errors, and final result as NDJSON. |
| `POST` | `/api/runs/{run_id}/rerun/worker/{worker_id}` | Rerun one worker result. |
| `POST` | `/api/runs/{run_id}/rerun/synthesis` | Rerun only the final synthesis. |
| `POST` | `/api/evaluations/compare` | Score one or more runs with a lightweight rubric. |

## Validation

Backend:

```bash
backend/.venv/bin/python -m ruff check backend/app backend/tests backend/migrations
PYTHONPATH=backend backend/.venv/bin/python -m mypy backend/app backend/tests
PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests
```

Frontend:

```bash
cd frontend
npm run lint
npm run build
```

## Project Structure

```text
.
|-- backend
|   |-- app
|   |   |-- agents.py             # supervisor-worker orchestration
|   |   |-- config.py             # environment-driven settings
|   |   |-- db.py                 # Supabase/Postgres repository
|   |   |-- main.py               # FastAPI routes and streaming
|   |   |-- metrics.py            # lightweight metrics registry
|   |   |-- openrouter_client.py  # OpenRouter HTTP client
|   |   |-- prompts.py            # centralized prompt builders
|   |   `-- schemas.py            # API and orchestration models
|   |-- migrations                # Alembic schema migrations
|   `-- tests                     # backend regression tests
|-- frontend
|   `-- src
|       |-- App.tsx               # dashboard and workflow UI
|       |-- api.ts                # typed API client
|       |-- styles.css            # dashboard styling
|       `-- types.ts              # frontend API types
|-- about_project.md
|-- progress.md
`-- troubleshooting.md
```

## Production Notes

- Keep secrets only in environment variables.
- Put the FastAPI app behind Nginx or another reverse proxy.
- Use Alembic migrations instead of relying on automatic table creation.
- Tune `WORKFLOW_MAX_CONCURRENCY` according to VPS size and OpenRouter rate limits.
- Keep `DATABASE_POOL_SIZE` small for Supabase pooler-backed deployments.
- Monitor `/metrics`, workflow duration, provider errors, and database latency.
- For larger traffic, move workflow execution into a queue-backed worker process.
