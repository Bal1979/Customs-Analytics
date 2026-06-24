"""Routes: setup (første-gangs admin), login, logout, accepter invitation."""

from __future__ import annotations

import logging

from flask import (
    Blueprint,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from . import config, core, repo

logger = logging.getLogger(__name__)

bp = Blueprint("auth", __name__, template_folder="templates")


def _default_target(user):
    return url_for("admin.users") if user and user["is_admin"] else "/"


@bp.route("/setup", methods=["GET", "POST"])
def setup():
    """Første kørsel: opret den første administrator. Kun ved 0 brugere."""
    if repo.user_count() > 0:
        return redirect(url_for("auth.login"))

    error = None
    if request.method == "POST":
        core.check_csrf()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")
        error = core.validate_email(email) or core.validate_password(password, password2)
        if error is None:
            uid = repo.create_user(
                email, core.hash_password(password),
                is_admin=True, all_access=True, status="active",
            )
            user = repo.get_user_by_id(uid)
            core.login_session(user)
            repo.audit("user.created", actor=repo.normalize_email(email),
                       detail="første administrator (setup)", ip=core.client_ip())
            logger.info("Administrator oprettet via setup: %s", email)
            return redirect(url_for("admin.users"))

    return render_template("auth_setup.html", error=error)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if repo.user_count() == 0:
        return redirect(url_for("auth.setup"))

    next_url = core._safe_next(request.args.get("next", "")) or ""
    if core.current_user() is not None:
        return redirect(next_url or _default_target(core.current_user()))

    error = None
    if request.method == "POST":
        core.check_csrf()
        next_url = core._safe_next(request.form.get("next", "")) or ""
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        ip = core.client_ip()

        repo.purge_old_login_attempts()
        lockout = repo.login_lockout_reason(email, ip)
        if lockout is not None:
            repo.audit("login.lockout", actor=email, ip=ip, outcome="blocked",
                       detail=f"årsag={lockout}")
            logger.warning("Login-lockout (%s) for %r fra %s", lockout, email, ip)
            return render_template("auth_login.html",
                                   error=config.LOCKOUT_MESSAGE, next=next_url)

        user = repo.get_user_by_email(email)
        ok = core.verify_password(user["password_hash"] if user else None, password)
        blocked = user is not None and user["status"] != "active"
        success = user is not None and ok and not blocked
        repo.record_login_attempt(email, ip, success=success)

        if success:
            repo.update_last_login(user["id"])
            core.login_session(user)
            repo.audit("login.success", actor=user["email"], ip=ip)
            return redirect(next_url or _default_target(user))

        if blocked and ok:
            error = "Din adgang er blokeret. Kontakt administratoren."
            repo.audit("login.blocked", actor=email, ip=ip, outcome="blocked")
        else:
            error = "Forkert e-mail eller password."
            repo.audit("login.failure", actor=email, ip=ip, outcome="fail")
        logger.warning("Mislykket login for %r (blokeret=%s)", email, blocked)

    return render_template("auth_login.html", error=error, next=next_url)


@bp.route("/logout", methods=["POST"])
def logout():
    core.check_csrf()
    user = core.current_user()
    repo.audit("logout", actor=user["email"] if user else None, ip=core.client_ip())
    core.logout_session()
    return redirect(url_for("auth.login"))


@bp.route("/invite/<token>", methods=["GET", "POST"])
def accept_invite(token):
    invite = repo.get_valid_invite(core.hash_token(token))
    if invite is None:
        return render_template("auth_invite.html", invalid=True), 410

    error = None
    if request.method == "POST":
        core.check_csrf()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")
        error = core.validate_email(email) or core.validate_password(password, password2)
        if error is None and repo.get_user_by_email(email) is not None:
            error = "Der findes allerede en bruger med den e-mail."
        if error is None:
            uid = repo.create_user(
                email, core.hash_password(password),
                is_admin=invite["is_admin"],
                all_access=invite["all_access"],
                status="active",
            )
            if not invite["all_access"]:
                slugs = repo.get_invite_tools(invite["id"])
                repo.set_entitlements(uid, slugs, granted_by=invite["created_by"])
            repo.mark_invite_used(invite["id"], uid)
            user = repo.get_user_by_id(uid)
            core.login_session(user)
            level = "fuld adgang" if invite["all_access"] else "individuel adgang"
            repo.audit("user.created", actor=repo.normalize_email(email),
                       detail=f"via invitation ({level})", ip=core.client_ip())
            logger.info("Invitation accepteret: %s (%s)", email, level)
            return redirect(_default_target(user))

    # Vis hvilke tools invitationen giver adgang til.
    if invite["all_access"]:
        access_label = "alle værktøjer (fuld adgang)"
    else:
        slugs = repo.get_invite_tools(invite["id"])
        names = ", ".join(config.tool_name(s) for s in slugs) or "ingen værktøjer endnu"
        access_label = names
    return render_template("auth_invite.html", invalid=False,
                           note=invite["note"], access_label=access_label,
                           error=error)
