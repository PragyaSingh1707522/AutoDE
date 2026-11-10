import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

revision_path = Path(__file__).parents[1] / "migrations" / "versions" / "0001_authentication.py"
spec = importlib.util.spec_from_file_location("auth_migration", revision_path)
assert spec and spec.loader
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def test_migration_preserves_existing_tenant_ids_and_rows():
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE sources (id VARCHAR PRIMARY KEY, organization_id VARCHAR NOT NULL, filename VARCHAR NOT NULL, content_hash VARCHAR NOT NULL, row_count INTEGER NOT NULL, profile_json TEXT NOT NULL, created_at DATETIME NOT NULL)")
        connection.exec_driver_sql("CREATE TABLE approval_requests (id VARCHAR PRIMARY KEY, organization_id VARCHAR NOT NULL, source_id VARCHAR NOT NULL, action VARCHAR NOT NULL, status VARCHAR NOT NULL, reason TEXT NOT NULL, created_at DATETIME NOT NULL)")
        connection.exec_driver_sql("CREATE TABLE audit_events (id VARCHAR PRIMARY KEY, organization_id VARCHAR NOT NULL, actor VARCHAR NOT NULL, event VARCHAR NOT NULL, details TEXT NOT NULL, created_at DATETIME NOT NULL)")
        connection.exec_driver_sql("INSERT INTO sources VALUES ('source-1','legacy-org','old.csv','hash',1,'{}','2024-01-01')")
        connection.exec_driver_sql("INSERT INTO approval_requests VALUES ('approval-1','legacy-org','source-1','schema','pending','review','2024-01-01')")
        connection.exec_driver_sql("INSERT INTO audit_events VALUES ('audit-1','legacy-org','legacy','source.uploaded','{}','2024-01-01')")
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        org = connection.execute(sa.text("SELECT id, name FROM organizations WHERE id='legacy-org'")).one()
        source_org = connection.execute(sa.text("SELECT organization_id FROM sources WHERE id='source-1'")).scalar_one()
        approval_org = connection.execute(sa.text("SELECT organization_id FROM approval_requests WHERE id='approval-1'")).scalar_one()
        audit_org = connection.execute(sa.text("SELECT organization_id FROM audit_events WHERE id='audit-1'")).scalar_one()
        audit_columns = {column["name"] for column in sa.inspect(connection).get_columns("audit_events")}
        audit_org_column = next(column for column in sa.inspect(connection).get_columns("audit_events") if column["name"] == "organization_id")
        assert org.id == source_org == approval_org == audit_org == "legacy-org"
        assert "Legacy organization" in org.name
        assert {"user_id", "ip_address"} <= audit_columns
        assert audit_org_column["nullable"]
        connection.execute(sa.text("INSERT INTO audit_events (id, organization_id, actor, event, details, created_at) VALUES ('failed-login','unknown','unknown','auth.login.failure','{}','2024-01-01')"))
        assert connection.execute(sa.text("SELECT COUNT(*) FROM users")).scalar_one() == 0
