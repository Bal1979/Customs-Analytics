"""
Repository: al databaseadgang samlet ét sted (SQLAlchemy Core).

Datetime-sammenligninger (login-vindue, invitations-udløb) udføres i SQL frem
for i Python, så naive/aware-forskelle mellem SQLite og Postgres ikke giver
problemer.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, insert, select, update

from . import config
from .db import (
    audit_log,
    commit,
    conn,
    entitlements,
    invite_tools,
    invites,
    login_attempts,
    users,
)


def now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def normalize_email(email: str) -> str:
    return email.strip().lower()


def user_count() -> int:
    return conn().execute(select(func.count()).select_from(users)).scalar_one()


def count_admins() -> int:
    return conn().execute(
        select(func.count()).select_from(users).where(users.c.is_admin.is_(True))
    ).scalar_one()


def get_user_by_id(uid):
    return conn().execute(select(users).where(users.c.id == uid)).mappings().first()


def get_user_by_email(email):
    return conn().execute(
        select(users).where(users.c.email == normalize_email(email))
    ).mappings().first()


def create_user(email, password_hash, *, is_admin=False, all_access=False,
                status="active") -> int:
    result = conn().execute(
        insert(users).values(
            email=normalize_email(email),
            password_hash=password_hash,
            status=status,
            all_access=all_access,
            is_admin=is_admin,
            token_version=0,
            created_at=now(),
        )
    )
    commit()
    return result.inserted_primary_key[0]


def set_status(uid, status):
    conn().execute(update(users).where(users.c.id == uid).values(status=status))
    commit()


def bump_token_version(uid):
    conn().execute(
        update(users).where(users.c.id == uid)
        .values(token_version=users.c.token_version + 1)
    )
    commit()


def set_all_access(uid, value: bool):
    conn().execute(update(users).where(users.c.id == uid).values(all_access=value))
    commit()


def update_last_login(uid):
    conn().execute(update(users).where(users.c.id == uid).values(last_login_at=now()))
    commit()


def delete_user(uid):
    conn().execute(delete(users).where(users.c.id == uid))
    commit()


def list_users():
    return conn().execute(
        select(users).order_by(users.c.created_at)
    ).mappings().all()


# ---------------------------------------------------------------------------
# Entitlements
# ---------------------------------------------------------------------------

def get_entitlements(uid) -> set[str]:
    rows = conn().execute(
        select(entitlements.c.tool_slug).where(entitlements.c.user_id == uid)
    ).scalars().all()
    return set(rows)


def set_entitlements(uid, slugs, granted_by):
    """Erstat brugerens individuelle tool-adgang med præcis ``slugs``."""
    valid = [s for s in slugs if config.known_tool(s)]
    c = conn()
    c.execute(delete(entitlements).where(entitlements.c.user_id == uid))
    for slug in valid:
        c.execute(insert(entitlements).values(
            user_id=uid, tool_slug=slug, granted_by=granted_by, granted_at=now(),
        ))
    commit()


def all_entitlements() -> dict:
    """uid -> set(tool_slug) for alle brugere (til adminoverblik)."""
    out: dict = {}
    for row in conn().execute(
        select(entitlements.c.user_id, entitlements.c.tool_slug)
    ).all():
        out.setdefault(row[0], set()).add(row[1])
    return out


def user_has_tool(user_row, slug) -> bool:
    """Adgangsreglen: aktiv bruger med all_access ELLER entitlement til slug."""
    if user_row is None or user_row["status"] != "active":
        return False
    if user_row["all_access"]:
        return True
    found = conn().execute(
        select(func.count()).select_from(entitlements).where(
            entitlements.c.user_id == user_row["id"],
            entitlements.c.tool_slug == slug,
        )
    ).scalar_one()
    return found > 0


# ---------------------------------------------------------------------------
# Invites
# ---------------------------------------------------------------------------

def create_invite(token_hash, *, all_access, is_admin, note, created_by,
                  tool_slugs) -> int:
    expires = now() + timedelta(days=config.INVITE_TTL_DAYS)
    result = conn().execute(insert(invites).values(
        token_hash=token_hash,
        all_access=all_access,
        is_admin=is_admin,
        note=note,
        created_by=created_by,
        created_at=now(),
        expires_at=expires,
    ))
    invite_id = result.inserted_primary_key[0]
    if not all_access:
        for slug in tool_slugs:
            if config.known_tool(slug):
                conn().execute(insert(invite_tools).values(
                    invite_id=invite_id, tool_slug=slug,
                ))
    commit()
    return invite_id


def get_valid_invite(token_hash):
    """Returner invitationen hvis den er ubrugt og ikke udløbet, ellers None."""
    return conn().execute(
        select(invites).where(
            invites.c.token_hash == token_hash,
            invites.c.used_at.is_(None),
            invites.c.expires_at > now(),
        )
    ).mappings().first()


def get_invite_tools(invite_id) -> list[str]:
    return list(conn().execute(
        select(invite_tools.c.tool_slug).where(invite_tools.c.invite_id == invite_id)
    ).scalars().all())


def mark_invite_used(invite_id, user_id):
    conn().execute(update(invites).where(invites.c.id == invite_id).values(
        used_at=now(), used_by=user_id,
    ))
    commit()


def revoke_invite(invite_id):
    conn().execute(delete(invites).where(
        invites.c.id == invite_id, invites.c.used_at.is_(None),
    ))
    commit()


def list_invites(limit=50):
    return conn().execute(
        select(invites).order_by(invites.c.created_at.desc()).limit(limit)
    ).mappings().all()


# ---------------------------------------------------------------------------
# Login-rate-limiting
# ---------------------------------------------------------------------------

def purge_old_login_attempts():
    cutoff = now() - timedelta(hours=config.LOGIN_ATTEMPT_RETENTION_HOURS)
    conn().execute(delete(login_attempts).where(login_attempts.c.attempted_at < cutoff))
    commit()


def login_lockout_reason(email, ip):
    cutoff = now() - timedelta(minutes=config.LOGIN_WINDOW_MINUTES)
    email = normalize_email(email)
    user_fails = conn().execute(
        select(func.count()).select_from(login_attempts).where(
            login_attempts.c.email == email,
            login_attempts.c.success == 0,
            login_attempts.c.attempted_at >= cutoff,
        )
    ).scalar_one()
    if user_fails >= config.LOGIN_MAX_FAILS_PER_USER:
        return "e-mail"
    ip_fails = conn().execute(
        select(func.count()).select_from(login_attempts).where(
            login_attempts.c.ip == ip,
            login_attempts.c.success == 0,
            login_attempts.c.attempted_at >= cutoff,
        )
    ).scalar_one()
    if ip_fails >= config.LOGIN_MAX_FAILS_PER_IP:
        return "ip"
    return None


def record_login_attempt(email, ip, success: bool):
    email = normalize_email(email)
    conn().execute(insert(login_attempts).values(
        email=email, ip=ip, attempted_at=now(), success=1 if success else 0,
    ))
    if success:
        conn().execute(delete(login_attempts).where(
            login_attempts.c.email == email, login_attempts.c.success == 0,
        ))
    commit()


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

def audit(action, *, actor=None, tool_slug=None, detail=None, ip=None, outcome=None):
    conn().execute(insert(audit_log).values(
        ts=now(), actor=actor, action=action, tool_slug=tool_slug,
        detail=detail, ip=ip, outcome=outcome,
    ))
    commit()


def list_audit(limit=100):
    return conn().execute(
        select(audit_log).order_by(audit_log.c.ts.desc()).limit(limit)
    ).mappings().all()
