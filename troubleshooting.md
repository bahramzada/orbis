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

## Result Panel Stretched Agent Graph

- **Context/Component:** Frontend layout, workflow result UI
- **Error:** After a long workflow finished, the right result panel increased page height and stretched the left graph, causing agent cards and connection lines to drift apart.
- **Failed Attempts:** The initial flex layout let both columns match the tallest content, so long final answers resized the graph panel.
- **Solution:** Made the desktop app viewport-bounded, kept the graph panel fixed to available height, moved overflow to the right control panel, capped log/final sections, and restored normal stacked flow on mobile.

## Supabase URL Requires Real Encoded Password

- **Context/Component:** Backend database configuration, Supabase Postgres pooler
- **Error:** A connection string with `[YOUR-PASSWORD]` is only a template and must not be treated as an active database connection.
- **Failed Attempts:** No live connection was attempted with the placeholder password.
- **Solution:** `DATABASE_URL` is optional, placeholder URLs keep persistence disabled, and real Supabase URLs are converted from `postgresql://` to `postgresql+asyncpg://` internally for SQLAlchemy.

## SQLAlchemy Async Startup Required Greenlet

- **Context/Component:** Backend startup, SQLAlchemy async engine
- **Error:** FastAPI failed during startup with `ValueError: the greenlet library is required to use this function`.
- **Failed Attempts:** Restarting the backend after adding SQLAlchemy/asyncpg without `greenlet`.
- **Solution:** Added `greenlet>=3.1.1` to `backend/requirements.txt` and installed requirements into the backend virtual environment.

## Supabase TLS Require Mode With Asyncpg

- **Context/Component:** Backend startup, Supabase pooler TLS
- **Error:** FastAPI failed during startup with asyncpg SSL configuration and certificate verification errors.
- **Failed Attempts:** Passing `DATABASE_SSL=require` directly as asyncpg `ssl` config.
- **Solution:** Mapped `DATABASE_SSL=require` to a default verified SSL context for production safety and allowed `DATABASE_SSL=insecure-require` in production for Supabase poolers that need libpq-style encrypted mode without hostname verification. `DATABASE_SSL=disabled` remains blocked in production.

## Optional Database Startup Resilience

- **Context/Component:** Backend startup, Supabase/Postgres persistence
- **Error:** Startup failed when `DATABASE_SSL=disabled` was used, then failed again when the configured database host could not be resolved.
- **Failed Attempts:** Supporting only `DATABASE_SSL=disable` and letting optional DB reads run during lifespan without a fallback path.
- **Solution:** Added `DATABASE_SSL=disabled` as a local-development alias and made optional DB operations disable persistence for the current process when the database is unreachable, allowing the app to continue with in-memory defaults.

## Completed Workflow Kept Showing Spinning Log Rows

- **Context/Component:** Frontend agent activity log
- **Error:** Historical `running` log entries kept rendering with the animated spinner after the workflow had already produced results.
- **Failed Attempts:** Treating each log entry status as a permanent visual state made old start events look like active work.
- **Solution:** Track the latest log index per agent and animate only the latest `running` entry while the workflow is actively running; older `running` entries render as settled activity events.

## Alembic Script Location From Repository Root

- **Context/Component:** Backend migrations, Alembic
- **Error:** `alembic -c backend/alembic.ini heads` could not find the migration script directory when run from the repository root.
- **Failed Attempts:** Used a relative `script_location = migrations`, which resolved against the current shell directory.
- **Solution:** Set `script_location = %(here)s/migrations` and `prepend_sys_path = %(here)s` so Alembic resolves paths relative to `backend/alembic.ini`.

## Backend Startup Requires Network Access For Supabase

- **Context/Component:** FastAPI startup, Supabase Postgres pooler
- **Error:** Backend startup failed with `socket.gaierror` while resolving the Supabase pooler host inside the default sandbox.
- **Failed Attempts:** Started Uvicorn inside the default sandbox.
- **Solution:** Restarted Uvicorn with approved network access, then verified `/health` and `/metrics`.

## Coolify Database Persistence Disabled After Migration

- **Context/Component:** Coolify backend, Supabase/Postgres, Alembic
- **Error:** Backend started with `Database operation failed; persistence is disabled for this process`, while `/health` showed database persistence was not active.
- **Failed Attempts:** Running `alembic upgrade head` manually after dropping Supabase tables did not make the startup failure self-explanatory in application logs; `/health` later showed `database_configured=true` and `database_status=unavailable`.
- **Solution:** Added `DATABASE_AUTO_MIGRATE` support, made it default to `true` for open-source Docker/Coolify installs, aligned Alembic with the same asyncpg TLS settings used by the app, ensured the migration runner uses the active runtime settings, made migrations idempotent for partially bootstrapped databases, added schema recovery retry, exposed `database_status` and non-secret `database_error_code` in `/health`, separated DB env configuration from active connection availability, logged sanitized operation/error details, then applied Alembic migrations to the configured Supabase database and verified persistence reports `ready`.

## Office View Mobile Agent Overlap

- **Context/Component:** Frontend Office view responsive layout
- **Error:** At 390px viewport width, the isometric office agent stations touched vertically after the first redesign pass.
- **Failed Attempts:** Initial mobile positions kept the lower worker row too close to the upper worker row.
- **Solution:** Increased the mobile graph height, hid nonessential HUD/bubble elements under 620px, and moved the mobile supervisor, worker, and lower rows into a clearer stepped layout.

## Office View Free-Floating Label Clutter

- **Context/Component:** Frontend Office view, isometric agent layout
- **Error:** Absolute-positioned labels and speech bubbles made the Office scene visually cluttered, with labels clipping or touching across desktop and mobile sizes.
- **Failed Attempts:** Scaling the scene down and moving individual labels reduced some overlap but kept the layout fragile and hard to read.
- **Solution:** Rebuilt each office agent as a compact self-contained pod where label, action chip, desk, identity card, and progress bar live inside one bounded station; then verified no overlap, text clipping, or horizontal overflow at 2048px wide and 390px mobile viewports.

## Office View Pixel Scene Was Still Too Cluttered

- **Context/Component:** Frontend Office view UX
- **Error:** The pixel/isometric scene remained visually noisy and oversized for an operational dashboard, especially on mobile and wide desktop.
- **Failed Attempts:** Compacting the pixel scene and shortening labels improved measurements but did not produce a clean enough product UI.
- **Solution:** Rolled the Office view back toward the original simple management-board concept, using a light bounded floor grid and self-contained agent cards; verified 1280x720, 2048x1325, and 390x844 with zero agent overlap, zero text clipping, no horizontal overflow, and no console errors.

## Security Scanner Tooling Needed Temporary Paths

- **Context/Component:** Audit tooling, uv, pip-audit, Bandit
- **Error:** `uv tool run` could not use the default cache/tool directories in the sandbox and later failed DNS lookup without network access.
- **Failed Attempts:** Running `uv tool run pip-audit` and `uv tool run bandit` with default paths; then retrying with only `UV_CACHE_DIR`.
- **Solution:** Ran scanners with `UV_CACHE_DIR=/private/tmp/orbis-uv-cache` and `UV_TOOL_DIR=/private/tmp/orbis-uv-tools`, then allowed network access for package download. `pip-audit` returned no known vulnerabilities and Bandit returned no findings for `backend/app`.

## Coolify Healthcheck Failed While Auto-Migration Was Running

- **Context/Component:** Backend Docker startup, Coolify healthcheck, Alembic/Supabase migrations
- **Error:** Deploy logs stopped at Alembic `Running upgrade ...` and the container healthcheck returned `ConnectionRefusedError` because Uvicorn had not opened the API port yet.
- **Failed Attempts:** Treating the issue as a manual Coolify operation left repeated deploys vulnerable to the same startup timing problem.
- **Solution:** Moved Docker auto-migration into `backend/docker-entrypoint.sh` so migrations run before Uvicorn, export `DATABASE_AUTO_MIGRATE=false` for the served process, added a 300-second Docker healthcheck start period, added Postgres advisory migration locking plus lock/statement timeouts, and fixed schema verification so required column inspection happens while the database connection is open.

## Local Validation Dependencies Missing

- **Context/Component:** Backend/frontend validation, local workspace tooling
- **Error:** `python -m pytest backend/tests/test_security_hardening.py -q` failed because global Python lacks FastAPI; `python -m ruff --version` and `python -m mypy --version` failed because those modules are not installed; `npm run build` failed because `frontend/node_modules` is absent and `tsc` is not available.
- **Failed Attempts:** Tried the system Python, the bundled Codex Python runtime, and the existing frontend `npm run build` script without installing dependencies.
- **Solution:** Used `python -m compileall backend/app backend/tests backend/migrations` for syntax verification, cleaned generated cache artifacts, and left full pytest/ruff/mypy/npm validation pending until project dependencies are installed.
