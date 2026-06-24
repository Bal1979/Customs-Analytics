"""
Kompatibilitets-shim for central BALAI-brugerstyring.

Dette værktøj brugte tidligere et selvstændigt auth-modul. Det delegerer nu til
den fælles balai_auth-pakke, så login deles på tværs af *.balai.dk og adgang
styres centralt på auth.balai.dk.

app.py og skabeloner er UÆNDREDE: de importerer fortsat dette modul som auth
og bruger de samme navne (init_app, login_required, admin_required, current_user,
_check_csrf, _client_ip).
"""

import balai_auth
from balai_auth import core

# Værktøjets slug i det centrale tool-register (balai_auth/config.py).
TOOL_SLUG = "customs"


def init_app(app):
    """Kobl appen på central auth + adgangstjek for netop dette værktøj."""
    balai_auth.init_app(app, tool_slug=TOOL_SLUG, mount_compat_redirects=True)


# --- Decorators (uændrede navne) ---------------------------------------------
# login_required kræver nu BÅDE login og adgang til netop dette værktøj.
login_required = balai_auth.require_tool
admin_required = balai_auth.admin_required

# --- Hjælpefunktioner brugt af app.py og skabeloner --------------------------
current_user = core.current_user
csrf_token = core.csrf_token
check_csrf = core.check_csrf
_check_csrf = core.check_csrf
client_ip = core.client_ip
_client_ip = core.client_ip
