"""
Konfiguration for BALAI central brugerstyring.

Tool-registret er den autoritative liste over hvilke værktøjer der findes.
Et nyt tool tilføjes ved at registrere dets slug her — brugere med
``all_access`` får automatisk adgang til nye slugs uden migrering.
"""

import os

# ---------------------------------------------------------------------------
# Tool-register (slug -> visningsnavn). Skal matche subdomænerne på balai.dk.
# ---------------------------------------------------------------------------
TOOLS: dict[str, str] = {
    "saft": "SAF-T Validator",
    "vat": "VAT Analytics",
    "customs": "Customs Analytics",
    "vies": "VIES Validation",
    "vat-extract": "VAT Extract",
}


def tool_name(slug: str) -> str:
    return TOOLS.get(slug, slug)


def known_tool(slug: str) -> bool:
    return slug in TOOLS


# ---------------------------------------------------------------------------
# Politikker
# ---------------------------------------------------------------------------
INVITE_TTL_DAYS = 7
MIN_PASSWORD_LENGTH = 10

# Sessionen er en browser-session-cookie (udløber ved browser-luk). Derudover
# håndhæves en absolut øvre grænse server-side via et udstedelses-tidsstempel.
SESSION_MAX_HOURS = 12

# Rate limiting på login (fejlede forsøg inden for vinduet). Tællerne ligger i
# databasen, ikke i RAM, så de er sikre på tværs af gunicorn-workers.
LOGIN_WINDOW_MINUTES = 15
LOGIN_MAX_FAILS_PER_USER = 8
LOGIN_MAX_FAILS_PER_IP = 20
LOGIN_ATTEMPT_RETENTION_HOURS = 24
LOCKOUT_MESSAGE = "For mange loginforsøg. Prøv igen om et kvarter."

# Password-hashing: lås til pbkdf2:sha256 (portabelt på tværs af alle
# Python-bygninger; scrypt kræver OpenSSL-støtte som ikke altid findes).
PASSWORD_HASH_METHOD = "pbkdf2:sha256"


def database_url() -> str:
    """
    Returner SQLAlchemy-URL. Railway leverer typisk DATABASE_URL med skemaet
    ``postgres://`` — det normaliseres til ``postgresql+psycopg://`` som
    SQLAlchemy 2.0 + psycopg 3 forventer. Falder tilbage til en lokal
    SQLite-fil, så koden kan køre og testes uden Postgres.
    """
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        path = os.environ.get(
            "AUTH_DB_PATH",
            os.path.join(os.path.dirname(__file__), "..", "data", "auth.db"),
        )
        path = os.path.abspath(path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return f"sqlite:///{path}"
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url
