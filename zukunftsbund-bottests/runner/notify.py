"""Feedback-Kanal: Ergebnis nach dem Lauf an dich zurückmelden.

„Es muss ja gefeedbacked werden, dass man z. B. fertig ist." — genau das:
nach einem Lauf eine kurze Telegram-Nachricht (z. B. „Suite Kontakt-Bot:
16/17 grün, T9 rot"). Im Dry-Run wird nur geloggt, nichts gesendet.

Drei Feedback-Ebenen im Framework:
  1. Konsole/JSON   — der Lauf selbst (reporter.py).
  2. Telegram-Notify — diese Datei: Push an dich, wenn der Lauf fertig ist.
  3. MCP get_report — ein Agent liest das Ergebnis und fasst zusammen (Phase 3).
"""

from __future__ import annotations

import os
import urllib.parse
import urllib.request


def notify_telegram(message: str, *, dry_run: bool = False) -> bool:
    """Sendet die Zusammenfassung über die Telegram-Bot-API.

    Nutzt einen separaten Notify-Bot (NOTIFY_BOT_TOKEN) und Chat (NOTIFY_CHAT_ID).
    Gibt True bei Erfolg zurück, False wenn nicht konfiguriert.
    """
    if dry_run:
        print(f"[notify dry-run] {message}")
        return True

    token = os.environ.get("NOTIFY_BOT_TOKEN", "")
    chat_id = os.environ.get("NOTIFY_CHAT_ID", "")
    if not token or not chat_id:
        print("[notify] NOTIFY_BOT_TOKEN/NOTIFY_CHAT_ID nicht gesetzt — übersprungen.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": message}).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=15) as resp:
        return resp.status == 200
