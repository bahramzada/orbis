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

To enable Supabase/Postgres persistence, set `DATABASE_URL` in `backend/.env`:

```bash
DATABASE_URL=postgresql://postgres.<project-ref>:<password>@<pooler-host>:5432/postgres
DATABASE_SSL=require
```

If the database password contains reserved URL characters, URL-encode it before placing it in the connection string.

## API

- `GET /api/agents`: agent graph
- `GET /api/runs`: persisted workflow run history
- `POST /api/runs`: complete workflow response
- `POST /api/runs/stream`: newline-delimited live logs and final workflow response
