"""Adminpanel: brugere, adgang (fuld/individuel), blokering, invitationer."""

from __future__ import annotations

import logging

from flask import (
    Blueprint,
    abort,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from . import config, core, repo

logger = logging.getLogger(__name__)

bp = Blueprint("admin", __name__, url_prefix="/admin", template_folder="templates")


@bp.before_request
@core.admin_required
def _guard():
    # Alle ruter i blueprintet kræver admin. (core.admin_required kører her.)
    pass


@bp.route("", methods=["GET"])
@bp.route("/", methods=["GET"])
def users():
    user_rows = repo.list_users()
    ent_map = repo.all_entitlements()
    view = []
    for u in user_rows:
        if u["all_access"]:
            access = "Fuld adgang"
        else:
            slugs = sorted(ent_map.get(u["id"], set()))
            access = ", ".join(config.tool_name(s) for s in slugs) or "Ingen værktøjer"
        view.append({"u": u, "access": access,
                     "tools": ent_map.get(u["id"], set())})
    new_invite_link = session.pop("new_invite_link", None)
    return render_template(
        "admin.html",
        users=view,
        tools=config.TOOLS,
        invites=repo.list_invites(),
        audit=repo.list_audit(50),
        new_invite_link=new_invite_link,
        me=core.current_user(),
    )


@bp.route("/invites", methods=["POST"])
def create_invite():
    core.check_csrf()
    level = request.form.get("level", "individual")
    all_access = level == "all"
    is_admin = request.form.get("is_admin") == "on"
    note = request.form.get("note", "").strip()[:200]
    slugs = request.form.getlist("tools") if not all_access else []

    token = core.new_token()
    repo.create_invite(
        core.hash_token(token),
        all_access=all_access, is_admin=is_admin, note=note,
        created_by=core.current_user()["id"], tool_slugs=slugs,
    )
    session["new_invite_link"] = url_for("auth.accept_invite", token=token,
                                         _external=True)
    repo.audit("user.invite_created", actor=core.current_user()["email"],
               detail=f"niveau={'fuld' if all_access else 'individuel'}; "
                      f"tools={','.join(slugs)}; admin={is_admin}",
               ip=core.client_ip())
    return redirect(url_for("admin.users"))


@bp.route("/invites/<int:invite_id>/revoke", methods=["POST"])
def revoke_invite(invite_id):
    core.check_csrf()
    repo.revoke_invite(invite_id)
    repo.audit("user.invite_revoked", actor=core.current_user()["email"],
               detail=f"invite_id={invite_id}", ip=core.client_ip())
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/access", methods=["POST"])
def set_access(user_id):
    core.check_csrf()
    target = repo.get_user_by_id(user_id)
    if target is None:
        abort(404)
    level = request.form.get("level", "individual")
    if level == "all":
        repo.set_all_access(user_id, True)
        repo.set_entitlements(user_id, [], granted_by=core.current_user()["id"])
        detail = "fuld adgang"
    else:
        repo.set_all_access(user_id, False)
        slugs = request.form.getlist("tools")
        repo.set_entitlements(user_id, slugs, granted_by=core.current_user()["id"])
        detail = f"individuel: {','.join(slugs) or 'ingen'}"
    repo.audit("user.access_changed", actor=core.current_user()["email"],
               detail=f"{target['email']} -> {detail}", ip=core.client_ip())
    logger.info("Adgang ændret for %s -> %s", target["email"], detail)
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/block", methods=["POST"])
def block_user(user_id):
    core.check_csrf()
    me = core.current_user()
    target = repo.get_user_by_id(user_id)
    if target is None:
        abort(404)
    if user_id == me["id"]:
        abort(400, "Du kan ikke blokere din egen konto.")
    repo.set_status(user_id, "blocked")
    repo.bump_token_version(user_id)  # invalidér alle aktive sessions straks
    repo.audit("user.blocked", actor=me["email"], detail=target["email"],
               ip=core.client_ip())
    logger.info("Bruger blokeret: %s (af %s)", target["email"], me["email"])
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/unblock", methods=["POST"])
def unblock_user(user_id):
    core.check_csrf()
    target = repo.get_user_by_id(user_id)
    if target is None:
        abort(404)
    repo.set_status(user_id, "active")
    repo.audit("user.unblocked", actor=core.current_user()["email"],
               detail=target["email"], ip=core.client_ip())
    logger.info("Bruger genåbnet: %s", target["email"])
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/delete", methods=["POST"])
def delete_user(user_id):
    core.check_csrf()
    me = core.current_user()
    if user_id == me["id"]:
        abort(400, "Du kan ikke slette din egen konto.")
    target = repo.get_user_by_id(user_id)
    if target is None:
        abort(404)
    if target["is_admin"] and repo.count_admins() <= 1:
        abort(400, "Kan ikke slette den sidste administrator.")
    repo.delete_user(user_id)
    repo.audit("user.deleted", actor=me["email"],
               detail=f"slettet={target['email']}", ip=core.client_ip())
    logger.info("Bruger slettet: %s (af %s)", target["email"], me["email"])
    return redirect(url_for("admin.users"))
