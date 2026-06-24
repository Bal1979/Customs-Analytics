"""
Data-lag (SQLAlchemy Core).

Samme kode kører på SQLite (lokal udvikling/test) og PostgreSQL (Railway,
produktion). Vi bruger Core-expression-language frem for rå SQL, så
dialekt-forskelle (autoincrement, RETURNING, boolean-literaler) håndteres af
SQLAlchemy.

Forbindelser er request-scoped: én forbindelse pr. Flask-request, gemt på
``g`` og lukket i teardown. Uden for en request-kontekst (fx migrering, CLI)
bruges ``engine.begin()`` direkte.
"""

from __future__ import annotations

import threading

from flask import g
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
)

from . import config

metadata = MetaData()

# BigInteger som autoincrement-primærnøgle: på SQLite skal den rendere som
# INTEGER for at virke som rowid-alias. with_variant klarer det.
_PK = BigInteger().with_variant(Integer, "sqlite")


users = Table(
    "users",
    metadata,
    Column("id", _PK, primary_key=True, autoincrement=True),
    Column("email", String(255), nullable=False, unique=True),
    Column("password_hash", Text, nullable=False),
    # 'active' | 'blocked'
    Column("status", String(16), nullable=False, default="active"),
    Column("all_access", Boolean, nullable=False, default=False),
    Column("is_admin", Boolean, nullable=False, default=False),
    # Hæves for at invalidere alle eksisterende sessions for brugeren.
    Column("token_version", Integer, nullable=False, default=0),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("last_login_at", DateTime(timezone=True)),
)

entitlements = Table(
    "entitlements",
    metadata,
    Column("user_id", _PK, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("tool_slug", String(64), nullable=False),
    Column("granted_by", _PK, ForeignKey("users.id", ondelete="SET NULL")),
    Column("granted_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("user_id", "tool_slug", name="uq_entitlement"),
)

invites = Table(
    "invites",
    metadata,
    Column("id", _PK, primary_key=True, autoincrement=True),
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("all_access", Boolean, nullable=False, default=False),
    Column("is_admin", Boolean, nullable=False, default=False),
    Column("note", Text),
    Column("created_by", _PK, ForeignKey("users.id", ondelete="SET NULL")),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("used_at", DateTime(timezone=True)),
    Column("used_by", _PK, ForeignKey("users.id", ondelete="SET NULL")),
)

# Forudvalgte tools til en niveau-2-invitation (portabelt alternativ til et
# Postgres-array — virker også på SQLite).
invite_tools = Table(
    "invite_tools",
    metadata,
    Column("invite_id", _PK, ForeignKey("invites.id", ondelete="CASCADE"), nullable=False),
    Column("tool_slug", String(64), nullable=False),
    UniqueConstraint("invite_id", "tool_slug", name="uq_invite_tool"),
)

login_attempts = Table(
    "login_attempts",
    metadata,
    Column("id", _PK, primary_key=True, autoincrement=True),
    Column("email", String(255), nullable=False),
    Column("ip", String(64), nullable=False),
    Column("attempted_at", DateTime(timezone=True), nullable=False),
    Column("success", Integer, nullable=False, default=0),
)

audit_log = Table(
    "audit_log",
    metadata,
    Column("id", _PK, primary_key=True, autoincrement=True),
    Column("ts", DateTime(timezone=True), nullable=False),
    Column("actor", String(255)),
    Column("action", String(64), nullable=False),
    Column("tool_slug", String(64)),
    Column("detail", Text),
    Column("ip", String(64)),
    Column("outcome", String(32)),
)


# ---------------------------------------------------------------------------
# Engine (singleton pr. proces)
# ---------------------------------------------------------------------------
_engine = None
_engine_lock = threading.Lock()


def get_engine():
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                url = config.database_url()
                kwargs = {"pool_pre_ping": True, "future": True}
                if url.startswith("sqlite"):
                    # Tillad brug på tværs af tråde (gunicorn gthread).
                    kwargs["connect_args"] = {"check_same_thread": False}
                else:
                    # Beskedne pool-grænser pr. worker, så mange workers ikke
                    # udtømmer Postgres-forbindelser.
                    kwargs.update(pool_size=5, max_overflow=5, pool_recycle=1800)
                _engine = create_engine(url, **kwargs)
    return _engine


def init_db():
    """Opret tabeller hvis de mangler (fungerer som let migration)."""
    metadata.create_all(get_engine())


def conn():
    """Request-scoped forbindelse (auto-commit ved teardown hvis ingen fejl)."""
    if "auth_conn" not in g:
        g.auth_conn = get_engine().connect()
    return g.auth_conn


def commit():
    if "auth_conn" in g:
        g.auth_conn.commit()


def close_conn(exc=None):
    c = g.pop("auth_conn", None)
    if c is not None:
        try:
            if exc is None:
                c.commit()
            else:
                c.rollback()
        finally:
            c.close()
