from sqlalchemy import (
    String,
    Integer,
    ForeignKey,
    Text,
    JSON,
    Boolean,
    Float,
    Index,
    text,
    Table,
    Column,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(24), default="owner")
    created_at: Mapped[int] = mapped_column(Integer)


class Installation(Base):
    __tablename__ = "installation"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    timezone: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[int] = mapped_column(Integer)


class Session(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[int] = mapped_column(Integer, index=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[int] = mapped_column(Integer)


class LoginLimit(Base):
    __tablename__ = "login_limits"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer)
    window_start: Mapped[int] = mapped_column(Integer)


class Monitor(Base):
    __tablename__ = "monitors"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(16))
    config: Mapped[dict] = mapped_column(JSON)
    credentials: Mapped[str | None] = mapped_column(Text)
    interval: Mapped[int] = mapped_column(Integer)
    timeout: Mapped[float] = mapped_column(Float)
    failure_threshold: Mapped[int] = mapped_column(Integer)
    recovery_threshold: Mapped[int] = mapped_column(Integer)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    state: Mapped[str] = mapped_column(String(16), default="UNKNOWN")
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    recovery_count: Mapped[int] = mapped_column(Integer, default=0)
    next_check_at: Mapped[float] = mapped_column(Float, index=True)
    last_checked_at: Mapped[float | None] = mapped_column(Float)
    heartbeat_at: Mapped[float | None] = mapped_column(Float)
    heartbeat_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[float] = mapped_column(Float)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    group_id: Mapped[int | None] = mapped_column(
        ForeignKey("groups.id", ondelete="SET NULL")
    )
    resource_id: Mapped[int | None] = mapped_column(
        ForeignKey("resources.id", ondelete="SET NULL")
    )
    priority: Mapped[str] = mapped_column(String(16), default="normal")


class CheckResult(Base):
    __tablename__ = "check_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    monitor_id: Mapped[int] = mapped_column(
        ForeignKey("monitors.id", ondelete="CASCADE"), index=True
    )
    checked_at: Mapped[float] = mapped_column(Float, index=True)
    status: Mapped[str] = mapped_column(String(16))
    state: Mapped[str] = mapped_column(String(16))
    duration_ms: Mapped[float] = mapped_column(Float)
    message: Mapped[str] = mapped_column(String(256))


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        Index(
            "uq_incident_active",
            "monitor_id",
            unique=True,
            sqlite_where=text("ended_at IS NULL"),
            postgresql_where=text("ended_at IS NULL"),
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    monitor_id: Mapped[int] = mapped_column(
        ForeignKey("monitors.id", ondelete="CASCADE")
    )
    started_at: Mapped[float] = mapped_column(Float)
    ended_at: Mapped[float | None] = mapped_column(Float)
    cause: Mapped[str] = mapped_column(String(256))
    resolution: Mapped[str | None] = mapped_column(String(32))


class WorkerLease(Base):
    __tablename__ = "worker_lease"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[float] = mapped_column(Float)
    last_cycle_at: Mapped[float] = mapped_column(Float)


class Group(Base):
    __table_args__ = {"sqlite_autoincrement": True}
    __tablename__ = "groups"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("groups.id", ondelete="RESTRICT")
    )
    revision: Mapped[int] = mapped_column(Integer, default=1)


class Tag(Base):
    __table_args__ = {"sqlite_autoincrement": True}
    __tablename__ = "tags"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)


class Resource(Base):
    __table_args__ = {"sqlite_autoincrement": True}
    __tablename__ = "resources"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    address: Mapped[str] = mapped_column(String(253), default="")
    kind: Mapped[str] = mapped_column(String(24), default="server")
    operating_system: Mapped[str] = mapped_column(String(100), default="")
    environment: Mapped[str] = mapped_column(String(50), default="")
    group_id: Mapped[int | None] = mapped_column(
        ForeignKey("groups.id", ondelete="SET NULL")
    )
    revision: Mapped[int] = mapped_column(Integer, default=1)


monitor_tags = Table(
    "monitor_tags",
    Base.metadata,
    Column(
        "monitor_id", ForeignKey("monitors.id", ondelete="CASCADE"), primary_key=True
    ),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)
resource_tags = Table(
    "resource_tags",
    Base.metadata,
    Column(
        "resource_id", ForeignKey("resources.id", ondelete="CASCADE"), primary_key=True
    ),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class IdCounter(Base):
    __tablename__ = "id_counters"
    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    next_id: Mapped[int] = mapped_column(Integer)
