"""
Brugerstyring for Customs Analytics.

- Brugere gemmes i SQLite (data/auth.db) med hashede passwords (werkzeug/pbkdf2).
- Login via session-cookie (kraever SECRET_KEY i produktion).
- Admin kan oprette invitationslinks; modtageren vaelger selv brugernavn/password.
- Invitationstokens gemmes kun som SHA-256-hash og er engangs + tidsbegraensede.

BEMAERK (deploy): SQLite-filen ligger paa det persistente Railway-volume
(AUTH_DB_PATH=/data/auth.db). Volumet overlever genstarts og deploys, saa
brugere og logins bevares. Med 1 gunicorn-worker er SQLite rigeligt; skal
appen en dag skaleres til flere worker-PROCESSER, boer databasen flyttes til
Postgres (in-memory jobstate i app.py kraever ogsaa 1 worker — se Procfile).
"""

import hashlib
import hmac
import logging
import os
import secrets
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from customs import audit_log

logger = logging.getLogger(__name__)

bp = Blueprint("auth", __name__)

INVITE_TTL_DAYS = 7
MIN_PASSWORD_LENGTH = 10
SESSION_LIFETIME_HOURS = 12

# Password-hashing: laas metoden til pbkdf2:sha256. Werkzeugs default er
# scrypt, men scrypt kraever at OpenSSL er kompileret med scrypt-stoette —
# det er IKKE altid tilfaeldet (fx visse macOS-Python-bygninger fejler med
# "module 'hashlib' has no attribute 'scrypt'"). pbkdf2:sha256 er portabelt
# paa tvaers af alle Python-bygninger og lige saa anbefalet. check_password_hash
# laeser metoden fra hver gemt hash, saa eksisterende scrypt-hashes (oprettet
# i produktion) verificeres stadig korrekt dér hvor scrypt er tilgaengeligt.
PASSWORD_HASH_METHOD = "pbkdf2:sha256"

# Forudberegnet dummy-hash til timing-sikker login (samme arbejde uanset om
# brugernavnet findes). Beregnes én gang ved import — ikke pr. login-request.
_DUMMY_PASSWORD_HASH = generate_password_hash(
    "dummy-password-for-timing", method=PASSWORD_HASH_METHOD
)

# Rate limiting paa /login. Taellerne ligger i SQLite (tabellen
# login_attempts) og IKKE i RAM. Appen koerer 1 worker-proces med flere
# traade (se Procfile); SQLite-taelleren er traadsikker og overlever desuden
# genstart, hvor en in-memory-taeller ville nulstilles. Graenserne gaelder
# FEJLEDE forsoeg inden for vinduet.
LOGIN_WINDOW_MINUTES = 15
LOGIN_MAX_FAILS_PER_USER = 8
LOGIN_MAX_FAILS_PER_IP = 20
LOGIN_ATTEMPT_RETENTION_HOURS = 24
LOCKOUT_MESSAGE = "For mange loginforsøg. Prøv igen om et kvarter."

_DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "data", "auth.db")


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def _db_path():
    return os.environ.get("AUTH_DB_PATH", _DEFAULT_DB_PATH)


def get_db():
    if "auth_db" not in g:
        path = _db_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # timeout => busy_timeout: vent på lås i stedet for straks at fejle med
        # 'database is locked' (flere tråde + baggrundsjob deler db'en).
        conn = sqlite3.connect(path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")  # samtidige læsninger u. blokering
        g.auth_db = conn
    return g.auth_db


def close_db(_exc=None):
    conn = g.pop("auth_db", None)
    if conn is not None:
        conn.close()


def init_db():
    path = _db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                role          TEXT NOT NULL CHECK (role IN ('admin', 'user')),
                created_at    TEXT NOT NULL,
                last_login_at TEXT
            );

            CREATE TABLE IF NOT EXISTS invites (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                token_hash TEXT NOT NULL UNIQUE,
                role       TEXT NOT NULL CHECK (role IN ('admin', 'user')),
                note       TEXT,
                created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                used_at    TEXT,
                used_by    INTEGER REFERENCES users(id) ON DELETE SET NULL
            );

            -- Rate limiting paa login (se LOGIN_*-konstanterne).
            -- CREATE TABLE IF NOT EXISTS fungerer som migration: eksisterende
            -- databaser faar tabellen automatisk ved naeste opstart.
            CREATE TABLE IF NOT EXISTS login_attempts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                username     TEXT NOT NULL COLLATE NOCASE,
                ip           TEXT NOT NULL,
                attempted_at TEXT NOT NULL,
                success      INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_login_attempts_user
                ON login_attempts (username, attempted_at);
            CREATE INDEX IF NOT EXISTS idx_login_attempts_ip
                ON login_attempts (ip, attempted_at);
            """
        )
        conn.commit()
    finally:
        conn.close()


def _now():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(value):
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def user_count():
    return get_db().execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]


def _hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Rate limiting paa login (multi-worker-sikkert via SQLite)
# ---------------------------------------------------------------------------

def _client_ip():
    """
    Klientens IP-adresse bag Railways proxy.

    ANTAGELSE: Railway terminerer TLS i sin edge-proxy og saetter
    X-Forwarded-For, hvor FOERSTE element er den oprindelige klient-IP
    (Railway kontrollerer headeren ved indgangen, saa den kan ikke
    spoofes udefra). Fallback til request.remote_addr ved lokal koersel
    og i tests, hvor der ikke er nogen proxy.
    """
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    return request.remote_addr or "ukendt"


def _purge_old_login_attempts(db):
    """Lazy oprydning: slet forsoeg aeldre end 24 timer (kaldes ved login)."""
    cutoff = _iso(_now() - timedelta(hours=LOGIN_ATTEMPT_RETENTION_HOURS))
    db.execute("DELETE FROM login_attempts WHERE attempted_at < ?", (cutoff,))


def _login_lockout_reason(db, username, ip):
    """
    Returner "brugernavn"/"ip" hvis (username) hhv. (ip) har for mange
    FEJLEDE forsoeg inden for de seneste LOGIN_WINDOW_MINUTES — ellers None.
    username-sammenligningen er case-insensitiv (kolonnen er COLLATE NOCASE,
    samme som users.username).
    """
    cutoff = _iso(_now() - timedelta(minutes=LOGIN_WINDOW_MINUTES))
    user_fails = db.execute(
        "SELECT COUNT(*) AS n FROM login_attempts "
        "WHERE username = ? AND success = 0 AND attempted_at >= ?",
        (username, cutoff),
    ).fetchone()["n"]
    if user_fails >= LOGIN_MAX_FAILS_PER_USER:
        return "brugernavn"
    ip_fails = db.execute(
        "SELECT COUNT(*) AS n FROM login_attempts "
        "WHERE ip = ? AND success = 0 AND attempted_at >= ?",
        (ip, cutoff),
    ).fetchone()["n"]
    if ip_fails >= LOGIN_MAX_FAILS_PER_IP:
        return "ip"
    return None


def _record_login_attempt(db, username, ip, success):
    """
    Registrér et loginforsoeg. Ved succes nulstilles brugerens fejltaeller
    (raekkerne slettes), saa en legitim bruger ikke arver gamle fejl.
    Kalderen committer.
    """
    db.execute(
        "INSERT INTO login_attempts (username, ip, attempted_at, success) "
        "VALUES (?, ?, ?, ?)",
        (username, ip, _iso(_now()), 1 if success else 0),
    )
    if success:
        db.execute(
            "DELETE FROM login_attempts WHERE username = ? AND success = 0",
            (username,),
        )


# ---------------------------------------------------------------------------
# CSRF (let, session-baseret)
# ---------------------------------------------------------------------------

def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


def _check_csrf():
    """
    Verificér CSRF-token mod session['_csrf'].

    Accepterer token fra enten form-feltet "_csrf" (klassiske <form>-POST)
    ELLER headeren "X-CSRF-Token" (fetch/XHR fra upload-JS'en, som sender rå
    chunk-bytes som body og derfor ikke kan lægge tokenet i form-data).
    Sammenligningen er konstant-tid (hmac.compare_digest).
    """
    sent = request.form.get("_csrf", "") or request.headers.get("X-CSRF-Token", "")
    expected = session.get("_csrf", "")
    if not expected or not hmac.compare_digest(sent, expected):
        abort(400, "Ugyldig eller manglende CSRF-token. Genindlaes siden.")


# ---------------------------------------------------------------------------
# Decorators & hooks
# ---------------------------------------------------------------------------

def current_user():
    uid = session.get("user_id")
    if uid is None:
        return None
    if "auth_user" not in g:
        g.auth_user = get_db().execute(
            "SELECT * FROM users WHERE id = ?", (uid,)
        ).fetchone()
    return g.auth_user


def _wants_json():
    return (
        request.path.startswith(("/upload", "/status/", "/result/", "/stop/"))
        or request.accept_mimetypes.best == "application/json"
    )


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if user_count() == 0:
            return redirect(url_for("auth.setup"))
        if current_user() is None:
            if _wants_json():
                return jsonify({"error": "Login kraevet. Genindlaes siden og log ind."}), 401
            return redirect(url_for("auth.login", next=request.path))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = current_user()
        if user is None:
            return redirect(url_for("auth.login", next=request.path))
        if user["role"] != "admin":
            abort(403)
        return f(*args, **kwargs)
    return decorated


def init_app(app):
    """Kobl auth-modulet paa Flask-appen."""
    secret = os.environ.get("SECRET_KEY")
    if not secret:
        secret = secrets.token_hex(32)
        logger.warning(
            "SECRET_KEY er ikke sat — bruger tilfaeldig noegle. "
            "Alle sessions invalideres ved genstart. Saet SECRET_KEY i produktion."
        )
    app.secret_key = secret
    app.permanent_session_lifetime = timedelta(hours=SESSION_LIFETIME_HOURS)
    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")
    # Secure-cookie som standard (Railway/produktion er altid HTTPS). Kan slaas
    # fra til lokal HTTP-udvikling/tests med SESSION_COOKIE_SECURE=0.
    app.config["SESSION_COOKIE_SECURE"] = (
        os.environ.get("SESSION_COOKIE_SECURE", "1").strip().lower()
        not in ("0", "false", "no", ""))

    # Diagnostik: afslør om brugerdatabasen rent faktisk ligger på et persistent
    # volume. Asks-for-admin-hver-deploy skyldes næsten altid at AUTH_DB_PATH ikke
    # er sat, ELLER at intet volume er mountet på mappen (så /data findes som
    # almindelig container-mappe og forsvinder ved deploy).
    _db = _db_path()
    _db_dir = os.path.dirname(_db) or "."
    _is_mount = os.path.ismount(_db_dir)
    logger.info(
        "Auth-DB diagnostik: path=%s | AUTH_DB_PATH sat=%s | mappe-er-volume(mountpoint)=%s | db-fil-findes=%s",
        _db, "AUTH_DB_PATH" in os.environ, _is_mount, os.path.exists(_db),
    )
    if not os.environ.get("AUTH_DB_PATH") or not _is_mount:
        logger.warning(
            "Auth-DB persisteres IKKE: %s. Sæt AUTH_DB_PATH=/data/auth.db og "
            "mount et Railway-volume på /data (samme service), ellers nulstilles "
            "brugere ved hver deploy.",
            "AUTH_DB_PATH mangler" if not os.environ.get("AUTH_DB_PATH")
            else f"{_db_dir} er ikke et mountet volume",
        )

    init_db()
    app.teardown_appcontext(close_db)
    app.register_blueprint(bp)
    app.jinja_env.globals["csrf_token"] = csrf_token
    app.jinja_env.globals["current_user"] = current_user


# ---------------------------------------------------------------------------
# Validering af input
# ---------------------------------------------------------------------------

def _validate_username(username):
    if not (3 <= len(username) <= 64):
        return "Brugernavn skal vaere 3-64 tegn."
    if not all(c.isalnum() or c in "._-@" for c in username):
        return "Brugernavn maa kun indeholde bogstaver, tal og . _ - @"
    return None


def _validate_password(password, password2):
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password skal vaere mindst {MIN_PASSWORD_LENGTH} tegn."
    if password != password2:
        return "De to passwords er ikke ens."
    return None


# ---------------------------------------------------------------------------
# Routes: setup / login / logout
# ---------------------------------------------------------------------------

@bp.route("/setup", methods=["GET", "POST"])
def setup():
    """Foerste kørsel: opret administrator. Kun tilgaengelig naar der er 0 brugere."""
    if user_count() > 0:
        return redirect(url_for("auth.login"))

    error = None
    if request.method == "POST":
        _check_csrf()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")
        error = _validate_username(username) or _validate_password(password, password2)
        if error is None:
            db = get_db()
            db.execute(
                "INSERT INTO users (username, password_hash, role, created_at) "
                "VALUES (?, ?, 'admin', ?)",
                (username, generate_password_hash(password, method=PASSWORD_HASH_METHOD), _iso(_now())),
            )
            db.commit()
            row = db.execute(
                "SELECT id FROM users WHERE username = ?", (username,)
            ).fetchone()
            session.clear()
            session.permanent = True
            session["user_id"] = row["id"]
            logger.info("Administrator oprettet: %s", username)
            return redirect(url_for("index"))

    return render_template("auth_setup.html", error=error)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if user_count() == 0:
        return redirect(url_for("auth.setup"))
    if current_user() is not None:
        return redirect(url_for("index"))

    error = None
    if request.method == "POST":
        _check_csrf()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        db = get_db()
        ip = _client_ip()

        # Rate limiting FOER verifikation. Lockout-forsoeg registreres ikke
        # selv, saa vinduet udloeber af sig selv efter et kvarter.
        _purge_old_login_attempts(db)
        lockout = _login_lockout_reason(db, username, ip)
        if lockout is not None:
            db.commit()  # persistér oprydningen
            logger.warning(
                "Login-lockout (%s) for brugernavn=%r fra ip=%s",
                lockout, username, ip,
            )
            audit_log.log("login.lockout", actor=username, ip=ip, outcome="blocked")
            error = LOCKOUT_MESSAGE
            return render_template(
                "auth_login.html", error=error, next=request.args.get("next", "")
            )

        row = db.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        # check_password_hash koeres altid (ogsaa ved ukendt bruger) for at
        # undgaa timing-forskel mellem "ukendt bruger" og "forkert password".
        # Dummy-hashen er forudberegnet ved import (se _DUMMY_PASSWORD_HASH).
        ok = check_password_hash(row["password_hash"] if row else _DUMMY_PASSWORD_HASH, password)
        _record_login_attempt(db, username, ip, success=(row is not None and ok))
        if row is not None and ok:
            session.clear()
            session.permanent = True
            session["user_id"] = row["id"]
            db.execute(
                "UPDATE users SET last_login_at = ? WHERE id = ?",
                (_iso(_now()), row["id"]),
            )
            db.commit()
            audit_log.log("login.success", actor=username, ip=ip)
            target = request.form.get("next") or url_for("index")
            # Kun interne redirects
            if not target.startswith("/") or target.startswith("//"):
                target = url_for("index")
            return redirect(target)
        db.commit()  # persistér det fejlede forsoeg + oprydning
        error = "Forkert brugernavn eller password."
        audit_log.log("login.failure", actor=username, ip=ip, outcome="fail")
        logger.warning("Mislykket login for brugernavn: %r", username)

    return render_template(
        "auth_login.html", error=error, next=request.args.get("next", "")
    )


@bp.route("/logout", methods=["POST"])
def logout():
    _check_csrf()
    u = current_user()
    audit_log.log("logout", actor=u["username"] if u else None, ip=_client_ip())
    session.clear()
    return redirect(url_for("auth.login"))


# ---------------------------------------------------------------------------
# Routes: admin — brugere og invitationer
# ---------------------------------------------------------------------------

@bp.route("/admin/users", methods=["GET"])
@admin_required
def admin_users():
    db = get_db()
    users = db.execute(
        "SELECT id, username, role, created_at, last_login_at FROM users ORDER BY created_at"
    ).fetchall()
    invites = db.execute(
        "SELECT i.id, i.role, i.note, i.created_at, i.expires_at, i.used_at, "
        "       u.username AS used_by_name "
        "FROM invites i LEFT JOIN users u ON u.id = i.used_by "
        "ORDER BY i.created_at DESC LIMIT 50"
    ).fetchall()
    now = _iso(_now())
    new_invite_link = session.pop("new_invite_link", None)
    return render_template(
        "auth_admin.html",
        users=users,
        invites=invites,
        now=now,
        new_invite_link=new_invite_link,
    )


@bp.route("/admin/invites", methods=["POST"])
@admin_required
def admin_create_invite():
    _check_csrf()
    role = request.form.get("role", "user")
    if role not in ("admin", "user"):
        role = "user"
    note = request.form.get("note", "").strip()[:200]

    token = secrets.token_urlsafe(32)
    db = get_db()
    db.execute(
        "INSERT INTO invites (token_hash, role, note, created_by, created_at, expires_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            _hash_token(token),
            role,
            note,
            current_user()["id"],
            _iso(_now()),
            _iso(_now() + timedelta(days=INVITE_TTL_DAYS)),
        ),
    )
    db.commit()
    # Linket vises een gang til admin — kun hash gemmes i databasen.
    session["new_invite_link"] = url_for("auth.accept_invite", token=token, _external=True)
    audit_log.log("user.invite_created", actor=current_user()["username"],
                  detail=f"rolle={role}; note={note}", ip=_client_ip())
    logger.info("Invitation oprettet (rolle=%s, note=%r)", role, note)
    return redirect(url_for("auth.admin_users"))


@bp.route("/admin/invites/<int:invite_id>/revoke", methods=["POST"])
@admin_required
def admin_revoke_invite(invite_id):
    _check_csrf()
    db = get_db()
    db.execute("DELETE FROM invites WHERE id = ? AND used_at IS NULL", (invite_id,))
    db.commit()
    audit_log.log("user.invite_revoked", actor=current_user()["username"],
                  detail=f"invite_id={invite_id}", ip=_client_ip())
    return redirect(url_for("auth.admin_users"))


@bp.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@admin_required
def admin_delete_user(user_id):
    _check_csrf()
    me = current_user()
    if user_id == me["id"]:
        abort(400, "Du kan ikke slette din egen konto.")
    db = get_db()
    target = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if target is None:
        abort(404)
    if target["role"] == "admin":
        admins = db.execute(
            "SELECT COUNT(*) AS n FROM users WHERE role = 'admin'"
        ).fetchone()["n"]
        if admins <= 1:
            abort(400, "Kan ikke slette den sidste administrator.")
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()
    audit_log.log("user.deleted", actor=me["username"],
                  detail=f"slettet={target['username']} (rolle={target['role']})",
                  ip=_client_ip())
    logger.info("Bruger slettet: %s (af %s)", target["username"], me["username"])
    return redirect(url_for("auth.admin_users"))


@bp.route("/admin/backup", methods=["POST"])
@admin_required
def admin_backup():
    """
    Download en konsistent sikkerhedskopi af brugerdatabasen.

    Bruger sqlite3's backup-API (src.backup(dst)) til en temp-fil i stedet
    for at laese db-filen raat fra disk — filen kan vaere midt i en
    skrivning fra en anden worker, og backup-API'et tager de noedvendige
    laase og giver et konsistent oejebliksbillede.

    BEMAERK: Kopien indeholder password-hashes — den skal opbevares sikkert.
    """
    _check_csrf()
    fd, tmp_path = tempfile.mkstemp(prefix="auth-backup-", suffix=".db")
    os.close(fd)
    try:
        dst = sqlite3.connect(tmp_path)
        try:
            get_db().backup(dst)
        finally:
            dst.close()
        with open(tmp_path, "rb") as fh:
            payload = fh.read()
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    filename = "balai-brugere-%s.db" % _now().strftime("%Y%m%d-%H%M")
    audit_log.log("admin.backup_downloaded", actor=current_user()["username"],
                  detail=f"{len(payload)} bytes", ip=_client_ip())
    logger.info(
        "Sikkerhedskopi af brugerdatabasen downloadet af %s (%d bytes)",
        current_user()["username"], len(payload),
    )
    return Response(
        payload,
        mimetype="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


# ---------------------------------------------------------------------------
# Routes: accepter invitation
# ---------------------------------------------------------------------------

def _load_valid_invite(token):
    row = get_db().execute(
        "SELECT * FROM invites WHERE token_hash = ?", (_hash_token(token),)
    ).fetchone()
    if row is None or row["used_at"] is not None:
        return None
    if _parse_iso(row["expires_at"]) < _now():
        return None
    return row


@bp.route("/invite/<token>", methods=["GET", "POST"])
def accept_invite(token):
    invite = _load_valid_invite(token)
    if invite is None:
        return render_template("auth_invite.html", invalid=True), 410

    error = None
    if request.method == "POST":
        _check_csrf()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")
        error = _validate_username(username) or _validate_password(password, password2)
        db = get_db()
        if error is None:
            exists = db.execute(
                "SELECT 1 FROM users WHERE username = ?", (username,)
            ).fetchone()
            if exists:
                error = "Brugernavnet er optaget. Vaelg et andet."
        if error is None:
            db.execute(
                "INSERT INTO users (username, password_hash, role, created_at) "
                "VALUES (?, ?, ?, ?)",
                (username, generate_password_hash(password, method=PASSWORD_HASH_METHOD), invite["role"], _iso(_now())),
            )
            row = db.execute(
                "SELECT id FROM users WHERE username = ?", (username,)
            ).fetchone()
            db.execute(
                "UPDATE invites SET used_at = ?, used_by = ? WHERE id = ?",
                (_iso(_now()), row["id"], invite["id"]),
            )
            db.commit()
            session.clear()
            session.permanent = True
            session["user_id"] = row["id"]
            audit_log.log("user.created", actor=username,
                          detail=f"rolle={invite['role']} (via invitation)",
                          ip=_client_ip())
            logger.info("Invitation accepteret: %s (rolle=%s)", username, invite["role"])
            return redirect(url_for("index"))

    return render_template(
        "auth_invite.html", invalid=False, note=invite["note"], error=error
    )
