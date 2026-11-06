"""Infrastructure links without recreating monitors or losing cascading history."""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "id_counters",
        sa.Column("name", sa.String(32), primary_key=True),
        sa.Column("next_id", sa.Integer(), nullable=False),
    )
    op.execute(
        "INSERT INTO id_counters (name, next_id) SELECT 'monitor', COALESCE(MAX(id), 0) + 1 FROM monitors"
    )
    op.create_table(
        "groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column(
            "parent_id", sa.Integer(), sa.ForeignKey("groups.id", ondelete="RESTRICT")
        ),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sqlite_autoincrement=True,
    )
    op.create_index(
        "uq_group_name_parent",
        "groups",
        [sa.func.coalesce(sa.column("parent_id"), 0), sa.func.lower(sa.column("name"))],
        unique=True,
    )
    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(50), nullable=False, unique=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sqlite_autoincrement=True,
    )
    op.create_table(
        "resources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("address", sa.String(253), nullable=False, server_default=""),
        sa.Column("kind", sa.String(24), nullable=False, server_default="server"),
        sa.Column(
            "operating_system", sa.String(100), nullable=False, server_default=""
        ),
        sa.Column("environment", sa.String(50), nullable=False, server_default=""),
        sa.Column(
            "group_id", sa.Integer(), sa.ForeignKey("groups.id", ondelete="SET NULL")
        ),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sqlite_autoincrement=True,
    )
    # SQLite ADD COLUMN supports inline nullable REFERENCES. Alembic batch recreation
    # would DROP monitors with foreign_keys=ON and cascade existing result history.
    if op.get_bind().dialect.name == "sqlite":
        op.execute(
            "ALTER TABLE monitors ADD COLUMN group_id INTEGER REFERENCES groups(id) ON DELETE SET NULL"
        )
        op.execute(
            "ALTER TABLE monitors ADD COLUMN resource_id INTEGER REFERENCES resources(id) ON DELETE SET NULL"
        )
    else:
        op.add_column(
            "monitors",
            sa.Column(
                "group_id",
                sa.Integer(),
                sa.ForeignKey("groups.id", ondelete="SET NULL"),
            ),
        )
        op.add_column(
            "monitors",
            sa.Column(
                "resource_id",
                sa.Integer(),
                sa.ForeignKey("resources.id", ondelete="SET NULL"),
            ),
        )
    op.add_column(
        "monitors",
        sa.Column("priority", sa.String(16), nullable=False, server_default="normal"),
    )
    op.add_column("incidents", sa.Column("resolution", sa.String(32)))
    for name, model, key in [
        ("monitor_tags", "monitors", "monitor_id"),
        ("resource_tags", "resources", "resource_id"),
    ]:
        op.create_table(
            name,
            sa.Column(
                key,
                sa.Integer(),
                sa.ForeignKey(model + ".id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column(
                "tag_id",
                sa.Integer(),
                sa.ForeignKey("tags.id", ondelete="CASCADE"),
                primary_key=True,
            ),
        )


def downgrade():
    op.drop_table("resource_tags")
    op.drop_table("monitor_tags")
    op.drop_column("incidents", "resolution")
    for name in ["priority", "resource_id", "group_id"]:
        op.drop_column("monitors", name)
    op.drop_table("resources")
    op.drop_table("tags")
    op.drop_table("groups")
    op.drop_table("id_counters")
