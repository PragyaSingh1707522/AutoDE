# AutoDE architecture

## Current vertical slice

The FastAPI service accepts CSV/TSV uploads, fingerprints content, profiles columns deterministically, persists source metadata and approval requests in SQLAlchemy, and stores original upload bytes under a tenant/source path. Every source, approval, and audit query includes organization scope. The Next.js app exposes a workspace overview and approval controls.

## Target pipeline

Ingestion should enqueue an idempotent run keyed by organization, source fingerprint, and pipeline version. LangGraph nodes (profiler, schema designer, dbt generator, validator, SQL analyst, healer) exchange typed artifacts. Generated code is validated and executed only in an isolated Docker sandbox with no network, resource/time limits, and read-only input mounts. Validated tables land in DuckDB by default or Postgres by configuration. dbt tests and Great Expectations checks gate publication; Dagster schedules and records replayable runs. Risky schema changes create approval requests before apply. SQL analyst queries are read-only and tenant scoped. LLM calls go through a provider adapter and optionally emit Langfuse traces; logs use structured JSON.

## Security boundary

The API verifies signed bearer access tokens and checks the user's active membership for the token organization on every request. The frontend keeps access tokens in memory and uses an HttpOnly refresh cookie. Organization and role identity headers are not used. Production still needs upload scanning, shared rate-limit storage, secrets management, and isolation between tenant storage. Agent generated code must never be executed by the API process or mounted writable into the sandbox.
