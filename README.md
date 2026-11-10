# AutoDE

AutoDE is a starter platform for teams who need useful, governed analytics from everyday files. The current vertical slice includes authenticated CSV/TSV upload and profiling, organization memberships and role checks, approval requests, refresh-token rotation, an audit log, and a Next.js workspace UI.

## Run it

Copy `.env.example` to `.env`. Generate a JWT secret of at least 32 characters, put it in `JWT_SECRET`, then run `docker compose up --build`. Alembic applies schema migrations before the API starts. Open http://localhost:3000, register an account, and upload a CSV. The API is at http://localhost:8000/docs.

For local API development, set the same authentication variables from `.env`, install `backend/requirements.txt`, run `alembic -c alembic.ini upgrade head`, then start `uvicorn backend.app.main:app --reload`.

### Login and authenticated API request

```sh
curl -X POST http://localhost:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"owner@example.org","password":"a-long-password"}'
```

Use the returned `access_token` as a bearer token. The refresh token is also set in an HttpOnly cookie for browser clients.

```sh
curl http://localhost:8000/auth/me \
  -H 'Authorization: Bearer YOUR_ACCESS_TOKEN'
```

To seed an owner outside self-registration, set `SEED_OWNER_EMAIL`, `SEED_OWNER_PASSWORD` (at least 10 characters), and optionally `SEED_ORG_NAME`, then run `python -m backend.seed_demo` after migrations.

## Current capabilities and limits

- Upload and profile CSV/TSV. Excel and PDF extraction, warehouse materialization, generated dbt execution, multilingual SQL analysis, and automated healing are not yet connected.
- User accounts and memberships are database-backed. Access-token identity and role are verified against the current membership on each request; organization and role headers are ignored.
- Authenticated browser requests use an in-memory access token and an HttpOnly refresh cookie. Set `COOKIE_SECURE=true` behind HTTPS and configure `ALLOWED_ORIGINS` for the frontend origin.
- The workspace includes Overview (`/`), Sources (`/sources` and `/sources/{id}`), Quality (`/quality`), and Approvals (`/approvals`). File versions are derived from upload history. Quality warnings use stored null and distinct counts; whole-row duplicate detection is marked as coming in a later phase.
- The Docker Compose starter provides the API and web UI. The agent, dbt, Dagster, Great Expectations, DuckDB/Postgres, and sandbox services are dependencies/architecture targets, not yet an end-to-end pipeline.

See [docs/architecture.md](docs/architecture.md) and [docs/design-decisions.md](docs/design-decisions.md). Run `make test`, `make lint`, and `make typecheck` for local checks.
