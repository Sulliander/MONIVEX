"""Add account security without recreating users, sessions or monitoring tables."""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    for name, type_, default, nullable in [
        ("totp_secret", sa.Text(), None, True),
        ("totp_pending_secret", sa.Text(), None, True),
        ("totp_pending_expires", sa.Integer(), None, True),
        ("totp_last_step", sa.Integer(), "-1", False),
    ]:
        op.add_column(
            "users", sa.Column(name, type_, server_default=default, nullable=nullable)
        )
    op.add_column(
        "installation",
        sa.Column(
            "require_admin_totp",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # Old session cookies and CSRF hashes stay valid after the upgrade.
    for name, type_, default in [
        ("id", sa.String(64), ""),
        ("created_at", sa.Integer(), "0"),
        ("client_ip", sa.String(64), ""),
        ("user_agent", sa.String(200), ""),
    ]:
        op.add_column(
            "sessions", sa.Column(name, type_, nullable=False, server_default=default)
        )
    # Separate random public IDs, never expose cookie hashes in the session list.
    connection = op.get_bind()
    import secrets

    for row in connection.execute(
        sa.text("SELECT token_hash FROM sessions")
    ).fetchall():
        connection.execute(
            sa.text("UPDATE sessions SET id=:id WHERE token_hash=:token"),
            {"id": secrets.token_hex(16), "token": row[0]},
        )
    op.create_index("uq_session_id", "sessions", ["id"], unique=True)
    op.create_table(
        "login_challenges",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.Integer(), nullable=False, index=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "recovery_codes",
        sa.Column("code_hash", sa.String(64), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
    )


def downgrade():
    op.drop_table("recovery_codes")
    op.drop_table("login_challenges")
    op.drop_index("uq_session_id", table_name="sessions")
    for name in ["user_agent", "client_ip", "created_at", "id"]:
        op.drop_column("sessions", name)
    op.drop_column("installation", "require_admin_totp")
    for name in [
        "totp_last_step",
        "totp_pending_expires",
        "totp_pending_secret",
        "totp_secret",
    ]:
        op.drop_column("users", name)
