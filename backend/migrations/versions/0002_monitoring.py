"""Monitoring, results, incident invariant and durable scheduler lease."""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "monitors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("credentials", sa.Text()),
        sa.Column("interval", sa.Integer(), nullable=False),
        sa.Column("timeout", sa.Float(), nullable=False),
        sa.Column("failure_threshold", sa.Integer(), nullable=False),
        sa.Column("recovery_threshold", sa.Integer(), nullable=False),
        sa.Column("paused", sa.Boolean(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("recovery_count", sa.Integer(), nullable=False),
        sa.Column("next_check_at", sa.Float(), nullable=False),
        sa.Column("last_checked_at", sa.Float()),
        sa.Column("heartbeat_at", sa.Float()),
        sa.Column("heartbeat_hash", sa.String(64)),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
    )
    op.create_index("ix_monitors_next_check_at", "monitors", ["next_check_at"])
    op.create_table(
        "check_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "monitor_id",
            sa.Integer(),
            sa.ForeignKey("monitors.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("checked_at", sa.Float(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.Column("message", sa.String(256), nullable=False),
    )
    op.create_index("ix_check_results_monitor_id", "check_results", ["monitor_id"])
    op.create_index("ix_check_results_checked_at", "check_results", ["checked_at"])
    op.create_table(
        "incidents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "monitor_id",
            sa.Integer(),
            sa.ForeignKey("monitors.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("started_at", sa.Float(), nullable=False),
        sa.Column("ended_at", sa.Float()),
        sa.Column("cause", sa.String(256), nullable=False),
    )
    op.create_index(
        "uq_incident_active",
        "incidents",
        ["monitor_id"],
        unique=True,
        sqlite_where=sa.text("ended_at IS NULL"),
        postgresql_where=sa.text("ended_at IS NULL"),
    )
    op.create_table(
        "worker_lease",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.Float(), nullable=False),
        sa.Column("last_cycle_at", sa.Float(), nullable=False),
    )


def downgrade():
    for name in ["worker_lease", "incidents", "check_results", "monitors"]:
        op.drop_table(name)
