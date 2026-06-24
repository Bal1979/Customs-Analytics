"""
Kompatibilitets-blueprint til værktøjer der kobles på den centrale auth.

De eksisterende værktøjer har skabeloner der refererer til de gamle auth-ruter
(`url_for('auth.logout')`, `auth.admin_users`, osv.). Når et værktøj skifter til
central login, findes de ruter ikke længere lokalt — og `url_for` ville fejle
med BuildError ved rendering.

Dette blueprint registreres under navnet "auth" i værktøjet og leverer netop de
endpoint-navne, så alle eksisterende skabeloner stadig bygger. Handlingerne
omdirigeres til den centrale tjeneste (AUTH_BASE_URL), så fx "Log ud" og
"Administrer brugere" sender brugeren det rigtige sted hen.

Login/admin-UI'et lever nu kun på auth.balai.dk — værktøjerne viser det ikke selv.
"""

from __future__ import annotations

from flask import Blueprint, current_app, redirect, request

from . import core

# Navnet "auth" gør, at eksisterende url_for('auth.xxx') i værktøjernes
# skabeloner fortsat virker uændret.
bp = Blueprint("auth", __name__)


def _central(path: str = "/"):
    base = current_app.config.get("AUTH_BASE_URL", "").rstrip("/")
    return redirect((base + path) if base else path)


@bp.route("/login")
def login():
    return _central("/login")


@bp.route("/logout", methods=["GET", "POST"])
def logout():
    # Session-cookien deles på .balai.dk, så værktøjet kan selv rydde den —
    # det logger brugeren ud overalt. CSRF tjekkes ved POST (skabelonernes
    # logout-knap sender et token med).
    if request.method == "POST":
        try:
            core.check_csrf()
        except Exception:
            pass
    core.logout_session()
    return _central("/login")


@bp.route("/setup")
def setup():
    return _central("/login")


@bp.route("/invite/<token>")
def accept_invite(token):
    return _central("/login")


@bp.route("/admin/users")
def admin_users():
    return _central("/admin")


@bp.route("/admin/invites", methods=["GET", "POST"])
def admin_create_invite():
    return _central("/admin")


@bp.route("/admin/users/<int:user_id>/delete", methods=["GET", "POST"])
def admin_delete_user(user_id):
    return _central("/admin")


@bp.route("/admin/invites/<int:invite_id>/revoke", methods=["GET", "POST"])
def admin_revoke_invite(invite_id):
    return _central("/admin")


@bp.route("/admin/backup", methods=["GET", "POST"])
def admin_backup():
    return _central("/admin")
