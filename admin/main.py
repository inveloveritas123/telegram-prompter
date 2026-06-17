"""
Admin-Web-Panel für telegram-prompter.
FastAPI + Jinja2 + HTMX — kein schweres SPA-Framework.
"""
import json
import os
from pathlib import Path

import httpx
import yaml
from fastapi import FastAPI, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from admin.config import (
    CONFIG_DIR,
    MCP_JSON,
    PIPELINE_YML,
    REPORTS_DIR,
    SECRET_KEYS,
    STATE_MD,
    STATE_DIR,
)

app = FastAPI(title="telegram-prompter Admin", version="1.0.0")

# Templates
_TPL_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TPL_DIR))

# Statische Assets
_STATIC_DIR = Path(__file__).parent / "static"
_STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

# ────────────────────────── Hilfsfunktionen ──────────────────────────


def _ensure_dirs() -> None:
    """Stellt sicher, dass alle notwendigen Verzeichnisse existieren."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def _load_mcp() -> dict:
    """Liest mcp.json oder gibt leere Struktur zurück."""
    if MCP_JSON.exists():
        try:
            return json.loads(MCP_JSON.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"mcpServers": {}}


def _save_mcp(data: dict) -> None:
    """Schreibt mcp.json atomar."""
    _ensure_dirs()
    MCP_JSON.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _load_pipeline() -> dict:
    """Liest pipeline.yml oder gibt initiale Struktur zurück."""
    if PIPELINE_YML.exists():
        try:
            data = yaml.safe_load(PIPELINE_YML.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (yaml.YAMLError, OSError):
            pass
    return {
        "goals": [],
        "schedule": {"window": "02:00-06:00", "cadence": "nightly"},
        "budget": {"max_iterations": 6, "time_minutes": 240, "cost_cap": 4.0},
        "flaky_retries": 2,
        "safety": {"staging_only": True},
    }


def _save_pipeline(data: dict) -> None:
    """Schreibt pipeline.yml."""
    _ensure_dirs()
    PIPELINE_YML.write_text(
        yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


def _load_reports() -> list[dict]:
    """
    Liest alle JSON-Reports aus REPORTS_DIR.
    Gibt leere Liste zurück wenn Verzeichnis fehlt oder leer ist.
    """
    reports: list[dict] = []
    if not REPORTS_DIR.exists():
        return reports
    for path in sorted(REPORTS_DIR.glob("*.json"), reverse=True)[:20]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            reports.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    return reports


def _load_state() -> str:
    """Liest STATE.md oder gibt Platzhalter zurück."""
    if STATE_MD.exists():
        try:
            return STATE_MD.read_text(encoding="utf-8")
        except OSError:
            pass
    return "*(Noch kein STATE.md vorhanden — Orchestrator wurde noch nicht gestartet.)*"


def _mask_secret(value: str) -> str:
    """Maskiert einen Secret-Wert für die Darstellung im Browser."""
    if not value:
        return ""
    return "•" * min(len(value), 16)


def _secret_status() -> list[dict]:
    """
    Gibt für jeden bekannten Secret-Key den Status zurück.
    Zeigt NIEMALS den Wert im Klartext.
    """
    result = []
    for key in SECRET_KEYS:
        raw = os.environ.get(key, "")
        result.append(
            {
                "key": key,
                "set": bool(raw),
                "masked": _mask_secret(raw) if raw else "",
            }
        )
    return result


# ────────────────────────── Seiten ──────────────────────────


def _tab_context(request: Request, active: str) -> dict:
    """
    Erzeugt den Template-Kontext fuer alle Seiten.
    Gibt reines Daten-Dict zurueck (ohne 'request' — wird von TemplateResponse separat uebergeben).
    """
    tab = request.query_params.get("tab", active)
    return {
        "active": tab,
        "mcp_servers": _load_mcp().get("mcpServers", {}),
        "pipeline": _load_pipeline(),
        "secrets": _secret_status(),
        "reports": _load_reports(),
        "state_text": _load_state(),
        "reports_dir": str(REPORTS_DIR),
    }


def _render(request: Request, active: str):
    """Rendert index.html mit dem aktuellen Kontext (Starlette 1.x API)."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context=_tab_context(request, active),
    )


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return _render(request, "mcp")


# ────────────────────────── MCP-Bereich ──────────────────────────


@app.get("/mcp", response_class=HTMLResponse)
async def mcp_page(request: Request):
    return _render(request, "mcp")


@app.post("/mcp/add")
async def mcp_add(
    name: str = Form(...),
    url: str = Form(...),
    api_key: str = Form(""),
):
    """Fügt einen neuen MCP-Server hinzu und schreibt config/mcp.json."""
    if not name.strip() or not url.strip():
        raise HTTPException(status_code=422, detail="Name und URL sind Pflichtfelder.")
    data = _load_mcp()
    headers: dict[str, str] = {}
    if api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"
    data["mcpServers"][name.strip()] = {
        "type": "http",
        "url": url.strip(),
        "headers": headers,
    }
    _save_mcp(data)
    return RedirectResponse(url="/?tab=mcp", status_code=303)


@app.post("/mcp/remove")
async def mcp_remove(name: str = Form(...)):
    """Entfernt einen MCP-Server aus der Konfiguration."""
    data = _load_mcp()
    data["mcpServers"].pop(name, None)
    _save_mcp(data)
    return RedirectResponse(url="/?tab=mcp", status_code=303)


@app.post("/mcp/test")
async def mcp_test(name: str = Form(...)):
    """
    Testet die HTTP-Verbindung zu einem registrierten MCP-Server.
    Gibt JSON-Status zurück (für HTMX).
    """
    data = _load_mcp()
    server = data.get("mcpServers", {}).get(name)
    if not server:
        return JSONResponse({"ok": False, "detail": "Server nicht gefunden."})
    url = server.get("url", "")
    headers = server.get("headers", {})
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers=headers)
        ok = resp.status_code < 500
        return JSONResponse(
            {"ok": ok, "status": resp.status_code, "detail": resp.reason_phrase}
        )
    except Exception as exc:
        return JSONResponse({"ok": False, "detail": str(exc)})


@app.get("/api/mcp")
async def api_mcp():
    """JSON-API: aktuelle MCP-Konfiguration."""
    return _load_mcp()


# ────────────────────────── Ziele & Zeitplan ──────────────────────────


@app.get("/pipeline", response_class=HTMLResponse)
async def pipeline_page(request: Request):
    return _render(request, "goals")


@app.post("/pipeline/save")
async def pipeline_save(
    window: str = Form("02:00-06:00"),
    cadence: str = Form("nightly"),
    max_iterations: int = Form(6),
    time_minutes: int = Form(240),
    cost_cap: float = Form(4.0),
    flaky_retries: int = Form(2),
    goals_json: str = Form("[]"),
):
    """Speichert Zeitplan + Budget in pipeline.yml."""
    try:
        goals = json.loads(goals_json)
    except json.JSONDecodeError:
        goals = []
    data = {
        "goals": goals,
        "schedule": {"window": window, "cadence": cadence},
        "budget": {
            "max_iterations": max_iterations,
            "time_minutes": time_minutes,
            "cost_cap": cost_cap,
        },
        "flaky_retries": flaky_retries,
        "safety": {"staging_only": True},
    }
    _save_pipeline(data)
    return RedirectResponse(url="/?tab=goals", status_code=303)


@app.post("/pipeline/goal/add")
async def goal_add(
    goal_id: str = Form(...),
    suite: str = Form(...),
    acceptance: str = Form(...),
    tags: str = Form(""),
):
    """Fügt ein Ziel zur pipeline.yml hinzu."""
    data = _load_pipeline()
    if "goals" not in data:
        data["goals"] = []
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    data["goals"].append(
        {"id": goal_id.strip(), "suite": suite.strip(), "acceptance": acceptance.strip(), "tags": tag_list}
    )
    _save_pipeline(data)
    return RedirectResponse(url="/?tab=goals", status_code=303)


@app.post("/pipeline/goal/remove")
async def goal_remove(goal_id: str = Form(...)):
    """Entfernt ein Ziel aus pipeline.yml."""
    data = _load_pipeline()
    data["goals"] = [g for g in data.get("goals", []) if g.get("id") != goal_id]
    _save_pipeline(data)
    return RedirectResponse(url="/?tab=goals", status_code=303)


@app.get("/api/pipeline")
async def api_pipeline():
    """JSON-API: aktuelle pipeline.yml."""
    return _load_pipeline()


# ────────────────────────── Secrets ──────────────────────────


@app.get("/secrets", response_class=HTMLResponse)
async def secrets_page(request: Request):
    return _render(request, "secrets")


@app.get("/api/secrets/status")
async def api_secrets_status():
    """
    JSON-API: zeigt welche Secrets gesetzt sind — NIEMALS den Wert im Klartext.
    """
    return _secret_status()


# ────────────────────────── Status ──────────────────────────


@app.get("/status", response_class=HTMLResponse)
async def status_page(request: Request):
    return _render(request, "status")


@app.get("/api/status")
async def api_status():
    """JSON-API: letzte Läufe + STATE."""
    return {"reports": _load_reports(), "state": _load_state()}
