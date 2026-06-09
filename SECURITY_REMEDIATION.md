# Orbis Security Remediation

## Scope

This document records the targeted hardening work for the public-internet threat model: authentication, sessions, CSRF, password hashing, input validation, headers, error disclosure, database migration safety, and scanner validation.

## Critical / High Findings

### Browser Session Token Exposure

- **Severity:** High
- **Before:** Browser auth used a bearer session token stored in `localStorage`.
- **Risk:** XSS or malicious browser extensions could steal long-lived session tokens.
- **After:** Browser auth uses an `HttpOnly` `orbis_session` cookie. The frontend stores only an in-memory CSRF token.
- **Changed files:** `backend/app/main.py`, `backend/app/db.py`, `backend/app/security.py`, `frontend/src/api.ts`, `frontend/src/App.tsx`
- **Proof:** Security tests assert cookie flags, cookie-backed `/me`, and no frontend `localStorage` token usage.

### Missing CSRF Protection For Cookie Auth

- **Severity:** High
- **Before:** Token auth did not need CSRF, but switching to cookies requires request forgery protection.
- **Risk:** A malicious site could trigger authenticated state-changing requests.
- **After:** Every mutating browser request requires `X-CSRF-Token`; server bootstrap bearer calls remain CSRF-exempt.
- **Changed files:** `backend/app/main.py`, `backend/app/db.py`, `frontend/src/api.ts`
- **Proof:** Security tests reject missing/invalid CSRF and accept valid CSRF.

### Password Hashing Modernization

- **Severity:** High
- **Before:** Passwords used PBKDF2-HMAC-SHA256.
- **Risk:** PBKDF2 is still acceptable when tuned, but Argon2id is stronger against GPU cracking.
- **After:** New passwords use Argon2id through `argon2-cffi`; legacy PBKDF2 hashes verify and rehash on successful login.
- **Changed files:** `backend/app/security.py`, `backend/requirements.txt`, `backend/requirements.lock`
- **Proof:** Security tests cover PBKDF2 login and Argon2id upgrade.

## Medium Findings

### Login/Register Abuse Controls

- **Severity:** Medium
- **Before:** Repeated login/register failures were not locally throttled.
- **Risk:** Credential stuffing and user-enumeration pressure.
- **After:** IP+email keyed rate limiting, generic login failure messages, bounded limiter state, and Postgres-backed counters in production.
- **Changed files:** `backend/app/main.py`, `backend/app/config.py`

### Admin Access-Control Footguns

- **Severity:** Medium
- **Before:** Admins could disable/downgrade the last active admin.
- **Risk:** Permanent admin lockout through the UI or API.
- **After:** The API blocks last-admin downgrade/disable and self-disable actions.
- **Changed files:** `backend/app/main.py`

### Error Disclosure And Headers

- **Severity:** Medium
- **Before:** API responses and frontend Nginx lacked a complete security-header layer.
- **Risk:** Browser hardening gaps and accidental internal error exposure.
- **After:** Backend has generic exception handling plus security headers; frontend Nginx sends CSP, frame denial, nosniff, referrer, and permissions headers.
- **Changed files:** `backend/app/main.py`, `frontend/nginx.conf`, `frontend/docker-entrypoint.d/40-orbis-config.sh`

### Schema Drift Detection

- **Severity:** Medium
- **Before:** Startup schema verification checked table presence, not security-critical session columns.
- **Risk:** Old databases could start with incomplete auth session schema.
- **After:** Startup verification checks required session columns and migrations add them idempotently.
- **Changed files:** `backend/app/db.py`, `backend/migrations/versions/20260531_0004_secure_sessions.py`

## Low / Quality Findings

### Input Validation Tightening

- **Severity:** Low
- **Before:** Email validation used a simple regex-like string constraint.
- **After:** Auth payloads use `EmailStr`, normalized lowercase emails, bounded strings, UUID path params for admin user IDs, and role literals.
- **Changed files:** `backend/app/schemas.py`, `backend/app/main.py`

### Production Configuration Guardrails

- **Severity:** Low
- **Before:** Production mode did not enforce secure cookie settings.
- **After:** Production requires `DATABASE_REQUIRED=true`, encrypted DB SSL, strict origins, `CORS_ALLOW_CREDENTIALS=true`, and `SESSION_COOKIE_SECURE=true`.
- **Changed files:** `backend/app/config.py`, `backend/.env.example`, `backend/.env.coolify.example`, `README.md`, `COOLIFY_DEPLOYMENT.md`

## Validation Commands

The implementation passed these checks on 2026-05-31.

```bash
backend/.venv/bin/python -m ruff check backend/app backend/tests backend/migrations
PYTHONPATH=backend backend/.venv/bin/python -m mypy backend/app backend/tests
PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests
cd frontend && npm run lint
cd frontend && npm run build
npm audit --audit-level=low
uv tool run pip-audit -r backend/requirements.lock
uv tool run bandit -r backend/app
uv tool run detect-secrets scan --all-files --exclude-files '(^backend/.venv/|^frontend/node_modules/|^\.mypy_cache/|^\.pytest_cache/|^\.ruff_cache/|^backend/.env$|^frontend/.env$)'
```

Local `.env`, virtualenv, package caches, and `node_modules` are excluded from the secret scan because they are local runtime artifacts rather than source files. If a real `.env` was ever committed or shared, rotate those secrets immediately.

## 2026-06-09 STRIDE Remediation Addendum

### Bearer Token Admin Bypass Removal

- **Severity:** Critical
- **Before:** `ORBIS_API_TOKEN` could authorize browser-facing user/admin API paths.
- **Risk:** Exposure of the shared token allowed broad data access and admin mutation.
- **After:** Browser and admin endpoints require cookie sessions; `ORBIS_API_TOKEN` is scoped to explicit service diagnostics such as `/api/service/health` and every service-token use is audited.
- **Changed files:** `backend/app/main.py`, `backend/app/schemas.py`, `backend/tests/test_security_hardening.py`, `README.md`, `COOLIFY_DEPLOYMENT.md`

### Per-User Data Isolation

- **Severity:** High
- **Before:** workflow runs, memories, and agent profile edits were global.
- **Risk:** one authenticated user could read or mutate another user's operational data.
- **After:** new writes are bound to `owner_user_id`; user-facing run, memory, rerun, evaluation, and profile endpoints filter by current user; legacy ownerless run/memory data is visible only through admin endpoints.
- **Changed files:** `backend/app/main.py`, `backend/app/db.py`, `backend/app/schemas.py`, `frontend/src/types.ts`, `backend/migrations/versions/20260609_0005_stride_remediation.py`

### Audit Events And Postgres Rate Limits

- **Severity:** High
- **Before:** security-relevant events and rate-limit counters were process-local or not persisted.
- **Risk:** multi-instance production deployments could miss abuse patterns and lose audit trails on restart.
- **After:** `security_audit_events` stores sanitized auth/admin/service/workflow events, and `rate_limit_counters` backs auth plus workflow hourly/daily quotas in Postgres.
- **Changed files:** `backend/app/config.py`, `backend/app/db.py`, `backend/app/main.py`, `backend/.env.example`, `backend/.env.coolify.example`

### Health Disclosure Reduction

- **Severity:** Medium
- **Before:** public `/health` exposed provider/database/model diagnostics.
- **Risk:** unauthenticated users could fingerprint deployment state.
- **After:** `/health` returns only `{ "status": "ok" }`; detailed diagnostics moved to `/api/admin/health` and service-token `/api/service/health`.
- **Changed files:** `backend/app/main.py`, `backend/app/schemas.py`, `frontend/src/api.ts`, `frontend/src/types.ts`
