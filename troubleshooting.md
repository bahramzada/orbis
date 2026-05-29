# Troubleshooting

## Sandbox Dependency Install Network Failure

- **Context/Component:** Backend pip install, frontend npm install
- **Error:** Sandbox install attempts could not resolve package hosts or stalled without output.
- **Failed Attempts:** Ran dependency installation inside the default sandbox.
- **Solution:** Re-ran the same `pip install` and `npm install` commands with approved network access, then ran validation locally.

## Localhost CORS Origin Mismatch

- **Context/Component:** FastAPI CORS, Vite frontend
- **Error:** Browser run request failed because frontend was served from `http://127.0.0.1:5173` while backend allowed only `http://localhost:5173`.
- **Failed Attempts:** Initial browser run test returned no API error state because the preflight request was rejected.
- **Solution:** Added `FRONTEND_ORIGINS` with comma-separated origin support and allowed both `localhost` and `127.0.0.1`.

## Long Workflow Had No Visible Progress

- **Context/Component:** Agent workflow UI, OpenRouter orchestration
- **Error:** A run could spend more than a minute across supervisor planning, four worker calls, and final synthesis while the frontend only showed a spinner.
- **Failed Attempts:** The initial `POST /api/runs` response returned only after the full workflow, so partial agent status was not visible.
- **Solution:** Added `POST /api/runs/stream` with newline-delimited log/result events and updated the frontend to render live agent logs, worker outputs, and final answer.
