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

## API

- `GET /api/agents`: agent graph
- `POST /api/runs`: complete workflow response
- `POST /api/runs/stream`: newline-delimited live logs and final workflow response
