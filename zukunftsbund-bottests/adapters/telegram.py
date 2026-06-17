"""Telegram-Adapter über MTProto (Telethon) — der Kern des echten Testings.

Gibt sich als echter Nutzer-Account aus, schickt Fotos/Text/Voice/Alben und
sammelt die Antworten des Bots ein. Deckt damit den kompletten Pfad inkl.
Datei-Download und Dialog-Zustand ab, den ein reiner API-Aufruf umgeht.

DRY-RUN: Ohne installiertes Telethon oder gesetzte Session läuft der Adapter
im Mock-Modus — er gibt vordefinierte Antworten zurück, damit Loader, Engine,
Assertions und Reporting ohne echte Telegram-Verbindung testbar sind.

SICHERHEIT (hart verdrahtet):
  * Es wird ein separater TEST-Account verwendet (eigene API_ID/API_HASH).
  * Der Ziel-Bot muss in TELEGRAM_ALLOWED_TEST_BOTS stehen, sonst Abbruch.
  * Niemals gegen Produktions-Bots/-Daten.
"""

from __future__ import annotations

import asyncio
import os
import time

from adapters.base import Adapter, Response
from runner.models import Step, StepKind, Suite

# Antwort-Sammelfenster: so lange warten wir nach dem Senden auf Bot-Antworten.
DEFAULT_COLLECT_WINDOW_S = float(os.environ.get("TG_COLLECT_WINDOW_S", "6"))


class TelegramAdapter(Adapter):
    name = "telegram"

    def __init__(self, suite: Suite, *, dry_run: bool = False) -> None:
        super().__init__(suite, dry_run=dry_run)
        self._client = None
        self._collected: list[str] = []
        # Mock-Antworten pro Case (Dict {case_id: [...]}) oder flache Liste (Fallback).
        self._mock_by_case = suite.target.extra.get("mock_replies", {})
        self._mock_replies: list[str] = []

    def begin_case(self, case_id: str) -> None:
        if isinstance(self._mock_by_case, dict):
            self._mock_replies = list(self._mock_by_case.get(case_id, []))
        else:
            self._mock_replies = list(self._mock_by_case)

    # --- Lifecycle ---

    async def setup(self) -> None:
        self._guard_test_target()
        if self.dry_run:
            return
        await self._connect()

    async def teardown(self) -> None:
        if self._client is not None:
            await self._client.disconnect()
            self._client = None

    # --- Sicherheits-Riegel ---

    def _guard_test_target(self) -> None:
        bot = (self.suite.target.bot or "").strip()
        if not bot:
            raise ValueError("telegram-Target ohne 'bot' — Abbruch.")
        allowed = {
            b.strip()
            for b in os.environ.get("TELEGRAM_ALLOWED_TEST_BOTS", "").split(",")
            if b.strip()
        }
        if not self.dry_run and allowed and bot not in allowed:
            raise PermissionError(
                f"Ziel-Bot {bot!r} ist nicht in TELEGRAM_ALLOWED_TEST_BOTS freigegeben. "
                "Test gegen nicht freigegebene (evtl. Produktions-)Bots ist gesperrt."
            )

    # --- Verbindung (nur ohne dry_run) ---

    async def _connect(self) -> None:
        try:
            from telethon import TelegramClient  # type: ignore
            from telethon.sessions import StringSession  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "Telethon ist nicht installiert. `pip install telethon` "
                "oder im Dry-Run-Modus laufen lassen (--dry-run)."
            ) from exc

        api_id = int(os.environ["TELEGRAM_API_ID"])
        api_hash = os.environ["TELEGRAM_API_HASH"]
        session = os.environ["TELEGRAM_TEST_SESSION"]  # StringSession des Test-Accounts
        self._client = TelegramClient(StringSession(session), api_id, api_hash)
        await self._client.connect()
        if not await self._client.is_user_authorized():
            raise RuntimeError("Test-Session ist nicht autorisiert — bitte Session neu erzeugen.")

        @self._client.on(_new_message_event(self.suite.target.bot))
        async def _handler(event):  # noqa: ANN001
            self._collected.append(event.message.message or "")

    # --- Schritt ausführen ---

    async def send_step(self, step: Step) -> Response:
        start = time.perf_counter()
        self._collected = []

        if self.dry_run:
            text = self._next_mock_reply(step)
        else:
            await self._dispatch(step)
            await self._collect()
            text = "\n".join(self._collected)

        return Response(text=text, latency_ms=(time.perf_counter() - start) * 1000)

    async def _dispatch(self, step: Step) -> None:
        bot = self.suite.target.bot
        if step.kind is StepKind.SEND:
            await self._client.send_message(bot, str(step.payload))
        elif step.kind is StepKind.SEND_PHOTO:
            await self._client.send_file(bot, _fixture(step.payload, self.suite))
        elif step.kind is StepKind.SEND_ALBUM:
            files = [_fixture(p, self.suite) for p in step.payload]
            await self._client.send_file(bot, files, album=True)
        elif step.kind is StepKind.SEND_VOICE:
            await self._client.send_file(bot, _fixture(step.payload, self.suite), voice_note=True)
        else:
            raise ValueError(f"send_step kann {step.kind} nicht ausführen.")

    async def _collect(self, window_s: float = DEFAULT_COLLECT_WINDOW_S) -> None:
        """Wartet ein Sammelfenster ab, damit alle Bot-Antworten eintreffen."""
        await asyncio.sleep(window_s)

    def _next_mock_reply(self, step: Step) -> str:
        if self._mock_replies:
            return self._mock_replies.pop(0)
        return f"[mock] {step.kind.value}: {step.payload!r}"


def _new_message_event(bot: str | None):  # pragma: no cover - benötigt Telethon
    from telethon import events  # type: ignore

    return events.NewMessage(incoming=True, from_users=bot)


def _fixture(rel_path: str, suite: Suite):
    """Löst einen Fixture-Pfad relativ zum Suite-Verzeichnis auf."""
    from pathlib import Path

    if suite.source_path:
        base = Path(suite.source_path).parent
        candidate = base / rel_path
        if candidate.exists():
            return str(candidate)
    return rel_path
