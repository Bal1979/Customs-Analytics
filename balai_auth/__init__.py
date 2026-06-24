"""BALAI central brugerstyring — delt auth-pakke.

Offentligt API (brugt af hvert værktøj):

    import balai_auth
    balai_auth.init_app(app, tool_slug="saft")
    requires_tool = balai_auth.require_tool

    @app.route("/")
    @requires_tool
    def index(): ...
"""

from . import config
from .core import (
    admin_required,
    check_csrf,
    client_ip,
    csrf_token,
    current_user,
    init_app,
    login_required,
    require_tool,
    require_tool_slug,
)

__all__ = [
    "init_app",
    "require_tool",
    "require_tool_slug",
    "login_required",
    "admin_required",
    "current_user",
    "csrf_token",
    "check_csrf",
    "client_ip",
    "config",
]
