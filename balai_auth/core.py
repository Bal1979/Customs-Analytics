"""
Auth-kerne: sessions, CSRF, rate-limit-helpers, adgangs-decorators og
``init_app``. Importeres af både den centrale auth-app og af hvert værktøj.

Værktøjerne serverer IKKE selv login. En ikke-logget-ind bruger sendes til den
centrale auth-tjeneste (AUTH_BASE_URL, fx https://auth.balai.dk/login) med et
``next``-link tilbage til den side, de kom fra.
"""

from __future__ import annotations

import hmac
import logging
import os
import secrets
from datetime import timedelta
from functools import wraps
from urllib.parse import quote, urlparse

from flask import (
    abort,
    current_app,
    g,
    jsonify,
    redirect,
    request,
    session,
)
from werkzeug.security import check_password_hash, generate_password_hash

from . import config, repo
from .db import close_conn, init_db

logger = logging.getLogger(__name__)

# Forudberegnet dummy-hash til timing-sikker login (samme arbejde uanset om
# e-mailen findes). Beregnes én gang ved import.
_DUMMY_PASSWORD_HASH = generate_password_hash(
    "dummy-password-for-timing", method=config.PASSWORD_HASH_METHOD
)


# ---------------------------------------------------------------------------
# Password / tokens
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    return generate_password_hash(password, method=config.PASSWORD_HASH_METHOD)


def verify_password(stored_hash: str | None, password: str) -> bool:
    # check_password_hash køres altid (også ved ukendt bruger) for at undgå
    # timing-forskel mellem "ukendt bruger" og "forkert password".
    return check_password_hash(stored_hash or _DUMMY_PASSWORD_HASH, password)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    import hashlib
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Klient-IP (bag Railways proxy)
# ---------------------------------------------------------------------------

def client_ip() -> str:
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    return request.remote_addr or "ukendt"


# ---------------------------------------------------------------------------
# CSRF (session-baseret, dobbelt-submit)
# ---------------------------------------------------------------------------

def csrf_token() -> str:
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


def check_csrf():
    sent = request.form.get("_csrf", "") or request.headers.get("X-CSRF-Token", "")
    expected = session.get("_csrf", "")
    if not expected or not hmac.compare_digest(sent, expected):
        abort(400, "Ugyldig eller manglende CSRF-token. Genindlæs siden.")


# ---------------------------------------------------------------------------
# Validering
# ---------------------------------------------------------------------------

def validate_email(email: str) -> str | None:
    email = email.strip()
    if not (3 <= len(email) <= 255):
        return "E-mail skal være 3-255 tegn."
    # Let validering — ikke fuld RFC, men fanger oplagte fejl.
    if email.count("@") != 1 or email.startswith("@") or email.endswith("@"):
        return "Indtast en gyldig e-mailadresse."
    local, _, domain = email.partition("@")
    if "." not in domain or " " in email:
        return "Indtast en gyldig e-mailadresse."
    return None


def validate_password(password: str, password2: str) -> str | None:
    if len(password) < config.MIN_PASSWORD_LENGTH:
        return f"Password skal være mindst {config.MIN_PASSWORD_LENGTH} tegn."
    if password != password2:
        return "De to passwords er ikke ens."
    return None


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

def login_session(user_row):
    """Etabler en session for brugeren (browser-session-cookie + iat-stempel)."""
    session.clear()
    session.permanent = False  # session-cookie: udløber ved browser-luk
    session["uid"] = user_row["id"]
    session["tv"] = user_row["token_version"]
    session["iat"] = repo.now().isoformat()


def logout_session():
    session.clear()


def _session_expired() -> bool:
    from datetime import datetime
    iat = session.get("iat")
    if not iat:
        return True
    try:
        issued = datetime.fromisoformat(iat)
    except ValueError:
        return True
    age = repo.now() - issued
    return age > timedelta(hours=config.SESSION_MAX_HOURS)


def current_user():
    """
    Returner den aktuelle bruger eller None. Validerer på hver request:
    session findes, ikke udløbet (12t), bruger findes, status='active',
    og token_version matcher (så blokering/revoke virker øjeblikkeligt).
    """
    if "auth_user" in g:
        return g.auth_user
    g.auth_user = None
    uid = session.get("uid")
    if uid is None:
        return None
    if _session_expired():
        logout_session()
        return None
    user = repo.get_user_by_id(uid)
    if user is None or user["status"] != "active":
        logout_session()
        return None
    if session.get("tv") != user["token_version"]:
        logout_session()
        return None
    g.auth_user = user
    return user


# ---------------------------------------------------------------------------
# Redirect til central login
# ---------------------------------------------------------------------------

def _safe_next(target: str) -> str | None:
    """Tillad kun relative stier eller absolutte balai.dk-URL'er."""
    if not target:
        return None
    if target.startswith("/") and not target.startswith("//"):
        return target
    parsed = urlparse(target)
    host = (parsed.hostname or "").lower()
    if parsed.scheme in ("http", "https") and (
        host == "balai.dk" or host.endswith(".balai.dk")
    ):
        return target
    return None


def _login_redirect():
    next_url = request.url  # absolut, så central auth kan sende tilbage
    base = current_app.config.get("AUTH_BASE_URL", "").rstrip("/")
    if base:
        return redirect(f"{base}/login?next={quote(next_url, safe='')}")
    # Lokal/centralt: auth-blueprintet findes i samme app.
    return redirect(f"/login?next={quote(next_url, safe='')}")


def _wants_json() -> bool:
    return request.accept_mimetypes.best == "application/json" or request.is_json


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            if _wants_json():
                return jsonify({"error": "Login krævet."}), 401
            return _login_redirect()
        return view(*args, **kwargs)
    return wrapped


def _enforce_tool(view, args, kwargs, slug):
    user = current_user()
    if user is None:
        if _wants_json():
            return jsonify({"error": "Login krævet."}), 401
        return _login_redirect()
    if slug and not repo.user_has_tool(user, slug):
        if _wants_json():
            return jsonify({"error": "Ingen adgang til dette værktøj."}), 403
        abort(403, "Du har ikke adgang til dette værktøj.")
    return view(*args, **kwargs)


def require_tool(view):
    """
    Beskyt en rute med adgangstjek for værktøjets eget slug
    (app.config['BALAI_TOOL_SLUG'], sat i init_app).
    """
    @wraps(view)
    def wrapped(*args, **kwargs):
        slug = current_app.config.get("BALAI_TOOL_SLUG")
        return _enforce_tool(view, args, kwargs, slug)
    return wrapped


def require_tool_slug(slug):
    """Som require_tool, men med eksplicit slug (uafhængigt af app-config)."""
    def deco(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            return _enforce_tool(view, args, kwargs, slug)
        return wrapped
    return deco


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if user is None:
            return _login_redirect()
        if not user["is_admin"]:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


# ---------------------------------------------------------------------------
# init_app
# ---------------------------------------------------------------------------

def init_app(app, *, tool_slug=None, mount_auth_routes=False, mount_admin=False,
             mount_compat_redirects=False):
    """
    Kobl brugerstyring på en Flask-app.

    - tool_slug:              værktøjets slug (sætter adgangstjek for require_tool).
    - mount_auth_routes:      registrér setup/login/logout/invite (kun auth-appen).
    - mount_admin:            registrér adminpanelet (kun auth-appen).
    - mount_compat_redirects: registrér "auth"-blueprint med omdirigeringer til
                              den centrale tjeneste (kun værktøjer — så gamle
                              skabeloner med url_for('auth.xxx') stadig virker).
    """
    secret = os.environ.get("SECRET_KEY")
    if not secret:
        secret = secrets.token_hex(32)
        logger.warning(
            "SECRET_KEY er ikke sat — bruger tilfældig nøgle. Alle sessions "
            "invalideres ved genstart, og SSO på tværs af tools virker IKKE. "
            "Sæt en delt SECRET_KEY i produktion."
        )
    app.secret_key = secret

    # Browser-session-cookie + absolut 12t-grænse håndhæves i current_user().
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    cookie_domain = os.environ.get("SESSION_COOKIE_DOMAIN")  # fx ".balai.dk"
    if cookie_domain:
        app.config["SESSION_COOKIE_DOMAIN"] = cookie_domain
    if os.environ.get("FLASK_ENV") == "production":
        app.config["SESSION_COOKIE_SECURE"] = True

    if tool_slug:
        app.config["BALAI_TOOL_SLUG"] = tool_slug
    auth_base = os.environ.get("AUTH_BASE_URL")
    if auth_base:
        app.config["AUTH_BASE_URL"] = auth_base

    init_db()
    app.teardown_appcontext(close_conn)
    app.jinja_env.globals["csrf_token"] = csrf_token
    app.jinja_env.globals["current_user"] = current_user
    app.jinja_env.globals["tool_name"] = config.tool_name
    app.jinja_env.globals["INVITE_TTL_DAYS"] = config.INVITE_TTL_DAYS

    if mount_auth_routes:
        from .auth_routes import bp as auth_bp
        app.register_blueprint(auth_bp)
    if mount_admin:
        from .admin_routes import bp as admin_bp
        app.register_blueprint(admin_bp)
    if mount_compat_redirects:
        from .compat import bp as compat_bp
        app.register_blueprint(compat_bp)
