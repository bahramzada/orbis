# Orbis

Agentic AI workspace with one supervisor agent and four worker agents.

## Backend

```bash
cd backend
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

## Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

## Environment

Set `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` in `backend/.env`.

Performance-related defaults can also be tuned in `backend/.env`:

```bash
WORKFLOW_MAX_CONCURRENCY=2
WORKFLOW_STEP_TIMEOUT_SECONDS=90
OPENROUTER_MAX_CONNECTIONS=20
OPENROUTER_MAX_KEEPALIVE=10
OPENROUTER_RETRY_ATTEMPTS=3
WORKFLOW_CACHE_TTL_SECONDS=0
```

To enable Supabase/Postgres persistence, set `DATABASE_URL` in `backend/.env`:

```bash
DATABASE_URL=postgresql://postgres.<project-ref>:<password>@<pooler-host>:5432/postgres
DATABASE_SSL=require
DATABASE_POOL_SIZE=3
DATABASE_MAX_OVERFLOW=2
DATABASE_POOL_TIMEOUT_SECONDS=10
```

If the database password contains reserved URL characters, URL-encode it before placing it in the connection string.

For production schema management, use Alembic migrations from the repository root:

```bash
cd backend
alembic upgrade head
```

## API

- `GET /api/agents`: agent graph
- `GET/PUT /api/agent-profiles`: Agent Studio profile configuration
- `GET /api/templates`: workflow template presets
- `GET/POST /api/memories`: project memory list and creation
- `POST /api/plans`: supervisor plan preview for human review
- `GET /api/runs`: persisted workflow run history
- `GET /api/runs/{run_id}`: full run inspector detail
- `POST /api/runs`: complete workflow response
- `POST /api/runs/stream`: newline-delimited live logs, tool calls, and final workflow response
- `POST /api/runs/{run_id}/rerun/worker/{worker_id}`: rerun one worker
- `POST /api/runs/{run_id}/rerun/synthesis`: rerun final synthesis
- `POST /api/evaluations/compare`: heuristic output evaluation scoring
- `GET /metrics`: Prometheus-style process metrics
