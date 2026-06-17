"""
Revisionslog (audit log) — uforanderlig hændelseslog til governance.

Registrerer sikkerhedsrelevante hændelser: login (succes/fejl/lockout), logout,
valideringskørsler (hvem validerede hvilken fil hvornår), download af den fulde
revisions-eksport, og brugeradministration (invitationer, sletning, backup).

Designprincipper:
  * Append-only: der er kun INSERT — ingen UPDATE/DELETE i normal drift.
  * Egen SQLite-database på det persistente volumen (uafhængig af auth/runs).
  * Trådsikker nok til formålet: hver skrivning åbner/lukker sin egen forbindelse,
    så den også virker fra baggrundstråde (async validering) uden Flask-kontekst.
  * Robust: log() må ALDRIG vælte hovedflowet — alle fejl fanges og logges som
    en advarsel i applikationsloggen.

Opbevaringstid: revisionslogs bør typisk opbevares længe. Der er derfor INGEN
automatisk oprydning her; en evt. lovbestemt sletning håndteres bevidst og
manuelt (eller via en særskilt, dokumenteret proces).
"""

import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import List, Optional

logger = logging.getLogger(__name__)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_DB = os.path.join(_REPO_ROOT, "data", "audit.db")


def _db_path() -> str:
    """Sti til audit-databasen.

    Prioritet: AUDIT_DB_PATH; ellers samme mappe som RUNS_DB_PATH/AUTH_DB_PATH
    (det persistente volumen); ellers <repo>/data/audit.db.
    """
    explicit = os.environ.get("AUDIT_DB_PATH")
    if explicit:
        return os.path.abspath(explicit)
    base = os.environ.get("RUNS_DB_PATH") or os.environ.get("AUTH_DB_PATH")
    if base:
        return os.path.join(os.path.dirname(os.path.abspath(base)), "audit.db")
    return os.path.abspath(_DEFAULT_DB)


def _connect() -> sqlite3.Connection:
    path = _db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # timeout => busy_timeout: revisionslogning skrives fra baggrundstråde
    # samtidig med web-requests; vent på lås frem for at tabe en hændelse.
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_audit_db() -> None:
    """Opret tabellen hvis den mangler (idempotent)."""
    conn = _connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                ts      TEXT NOT NULL,
                actor   TEXT,
                event   TEXT NOT NULL,
                detail  TEXT,
                ip      TEXT,
                outcome TEXT NOT NULL DEFAULT 'ok'
            );
            CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log (ts);
            CREATE INDEX IF NOT EXISTS idx_audit_event ON audit_log (event);
            """
        )
        conn.commit()
    finally:
        conn.close()


def log(event: str, actor: Optional[str] = None, detail: str = "",
        ip: Optional[str] = None, outcome: str = "ok") -> None:
    """Skriv én hændelse. Fejler ALDRIG udadtil (fanges og logges).

    `event` er en kort prik-separeret nøgle, fx 'login.success',
    'validation.run', 'export.full_download', 'user.deleted'.
    """
    try:
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO audit_log (ts, actor, event, detail, ip, outcome) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 actor or "anonym", event, (detail or "")[:2000], ip, outcome),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 — logning må aldrig vælte hovedflowet
        logger.warning("Kunne ikke skrive audit-hændelse %r", event, exc_info=True)


def list_events(limit: int = 200, event_prefix: Optional[str] = None,
                actor: Optional[str] = None) -> List[dict]:
    """Seneste hændelser (nyeste først), evt. filtreret på event-præfiks/aktør."""
    try:
        conn = _connect()
    except Exception:  # noqa: BLE001
        return []
    try:
        where, params = [], []
        if event_prefix:
            where.append("event LIKE ?")
            params.append(event_prefix + "%")
        if actor:
            where.append("actor = ?")
            params.append(actor)
        sql = "SELECT ts, actor, event, detail, ip, outcome FROM audit_log"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(int(limit))
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    except Exception:  # noqa: BLE001
        return []
    finally:
        conn.close()


def distinct_events() -> List[str]:
    """Liste over forekommende event-typer (til filter-UI)."""
    try:
        conn = _connect()
    except Exception:  # noqa: BLE001
        return []
    try:
        rows = conn.execute(
            "SELECT DISTINCT event FROM audit_log ORDER BY event"
        ).fetchall()
        return [r["event"] for r in rows]
    except Exception:  # noqa: BLE001
        return []
    finally:
        conn.close()
