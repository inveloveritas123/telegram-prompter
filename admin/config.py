"""
Zentrale Konfiguration des Admin-Panels.
Alle Pfade über Umgebungsvariablen konfigurierbar mit sicheren Defaults.
"""
import os
from pathlib import Path

# Basis-Verzeichnis des Repos (Elternverzeichnis von admin/)
_REPO_ROOT = Path(__file__).parent.parent

# Pfad-Defaults: Im Container /app/..., lokal relativ zum Repo
CONFIG_DIR = Path(os.environ.get("CONFIG_DIR", str(_REPO_ROOT / "config")))
REPORTS_DIR = Path(os.environ.get("REPORTS_DIR", str(_REPO_ROOT / "zukunftsbund-bottests" / "reports")))
STATE_DIR = Path(os.environ.get("STATE_DIR", str(_REPO_ROOT / "state")))

MCP_JSON = CONFIG_DIR / "mcp.json"
PIPELINE_YML = CONFIG_DIR / "pipeline.yml"
STATE_MD = STATE_DIR / "STATE.md"

# Bekannte Secrets (Bezeichner – nie Werte ausgeben)
SECRET_KEYS = [
    "TELEGRAM_API_ID",
    "TELEGRAM_API_HASH",
    "TELEGRAM_TEST_SESSION",
    "N8N_API_KEY",
    "N8N_BASE_URL",
    "NOTIFY_BOT_TOKEN",
    "NOTIFY_CHAT_ID",
    "GITHUB_TOKEN",
    "ADMIN_SECRET_KEY",
]
