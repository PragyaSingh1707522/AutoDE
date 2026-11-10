"""Add users, organizations, memberships, refresh tokens, and auth audit fields.

Revision ID: 0001_authentication
Revises:
"""
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = "0001_authentication"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    if "sources" not in existing_tables:
        op.create_table("sources", sa.Column("id", sa.String(), primary_key=True), sa.Column("organization_id", sa.String(), nullable=False), sa.Column("filename", sa.String(), nullable=False), sa.Column("content_hash", sa.String(), nullable=False), sa.Column("row_count", sa.Integer(), nullable=False), sa.Column("profile_json", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
        op.create_index("ix_sources_organization_id", "sources", ["organization_id"])
    if "approval_requests" not in existing_tables:
        op.create_table("approval_requests", sa.Column("id", sa.String(), primary_key=True), sa.Column("organization_id", sa.String(), nullable=False), sa.Column("source_id", sa.String(), sa.ForeignKey("sources.id"), nullable=False), sa.Column("action", sa.String(), nullable=False), sa.Column("status", sa.String(), nullable=False), sa.Column("reason", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
        op.create_index("ix_approval_requests_organization_id", "approval_requests", ["organization_id"])
    if "audit_events" not in existing_tables:
        op.create_table("audit_events", sa.Column("id", sa.String(), primary_key=True), sa.Column("organization_id", sa.String(), nullable=True), sa.Column("actor", sa.String(), nullable=False), sa.Column("event", sa.String(), nullable=False), sa.Column("details", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
        op.create_index("ix_audit_events_organization_id", "audit_events", ["organization_id"])
    if "audit_events" in set(sa.inspect(bind).get_table_names()):
        audit_info = sa.inspect(bind).get_columns("audit_events")
        audit_columns = {column["name"] for column in audit_info}
        if "user_id" not in audit_columns:
            op.add_column("audit_events", sa.Column("user_id", sa.String(), nullable=True))
        if "ip_address" not in audit_columns:
            op.add_column("audit_events", sa.Column("ip_address", sa.String(), nullable=True))
        organization_column = next((column for column in audit_info if column["name"] == "organization_id"), None)
        if organization_column is not None and not organization_column["nullable"]:
            with op.batch_alter_table("audit_events") as batch_op:
                batch_op.alter_column("organization_id", existing_type=sa.String(), nullable=True)
    op.create_table("users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_table("organizations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table("memberships",
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("organization_id", sa.String(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role", sa.String(), nullable=False),
    )
    op.create_table("refresh_tokens",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("token_hash", sa.String(), nullable=False, unique=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", sa.String(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=True)
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_organization_id", "refresh_tokens", ["organization_id"])
    # Preserve existing tenant keys without rewriting source, approval, or audit rows.
    existing = set()
    for table in ("sources", "approval_requests", "audit_events"):
        if table in inspector.get_table_names() and "organization_id" in {column["name"] for column in inspector.get_columns(table)}:
            existing.update(row[0] for row in bind.execute(sa.text(f"SELECT DISTINCT organization_id FROM {table} WHERE organization_id IS NOT NULL")))
    now = datetime.now(timezone.utc)
    for organization_id in existing:
        bind.execute(sa.text("INSERT INTO organizations (id, name, created_at) VALUES (:id, :name, :created_at)"), {"id": organization_id, "name": f"Legacy organization {organization_id}", "created_at": now})


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_index("ix_refresh_tokens_organization_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_token_hash", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_table("memberships")
    op.drop_table("organizations")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    if "audit_events" in sa.inspect(bind).get_table_names():
        cols = {column["name"] for column in sa.inspect(bind).get_columns("audit_events")}
        if "ip_address" in cols:
            op.drop_column("audit_events", "ip_address")
        if "user_id" in cols:
            op.drop_column("audit_events", "user_id")
