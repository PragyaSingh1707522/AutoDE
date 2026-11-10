# Design decisions

- **Start with a runnable CSV/TSV slice.** Excel/PDF parsing introduces format-specific dependencies and ambiguous extraction behavior. The UI/API state the supported formats explicitly; add spreadsheet and PDF adapters behind a common ingestion contract.
- **Use SQLite for the local metadata store.** It keeps the first run simple. SQLAlchemy allows Postgres via `DATABASE_URL`; production deployments should use Postgres and Alembic migrations rather than startup `create_all`.
- **Keep profiling deterministic before adding LLMs.** Basic type/null/distinct summaries are reproducible and auditable. An LLM should propose transformations, never silently apply destructive changes.
- **Require owner approval for changed same-name sources.** A changed file may imply a schema change. This simple fingerprint trigger favors safety; later use explicit schema diffs and configurable risk tiers.
- **Authentication uses signed bearer access tokens with database-backed rotating refresh tokens.** Membership is reloaded for each request, so a role change invalidates older access tokens immediately.
- **Generated code sandboxing is a deployment gate.** No generated SQL, Python, or dbt project is run in this starter. The target design uses a no-network constrained container before enabling execution.

## Authentication

Access tokens expire after 15 minutes and include a user subject, organization, role, expiry/issued timestamps, and unique token ID. Refresh tokens expire after 7 days, are stored only as SHA-256 hashes, and rotate on every refresh; the consumed token is revoked in the same transaction. Browser access tokens remain in memory. Refresh tokens use an HttpOnly, SameSite=Lax cookie so JavaScript cannot read them; API clients may also send a refresh token in the request body. Set `COOKIE_SECURE=true` when serving over HTTPS.

We chose signed bearer tokens over server-side sessions to keep authenticated API calls stateless while retaining server-side refresh revocation and membership checks. We rejected trusted organization/role headers because callers could spoof their tenant or privileges. Registration and login share per-IP and per-normalized-email in-process limits; multi-worker production deployments should move these counters to shared storage such as Redis.
