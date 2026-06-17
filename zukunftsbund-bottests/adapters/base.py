"""Schicht 2: Adapter-Vertrag.

Jeder Kanal (Telegram, HTTP, ...) implementiert dieses Protokoll. Die Engine
kennt nur diesen Vertrag — sie weiß nicht, ob dahinter MTProto oder ein
HTTP-Request steckt. Neue Kanäle = neuer Adapter, Szenarien bleiben gleich.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field

from runner.models import Step, Suite


@dataclass
class Response:
    """Antwort eines Adapters auf einen Schritt."""

    text: str = ""  # zusammengeführter Antworttext (für contains/regex)
    latency_ms: float = 0.0
    raw: dict = field(default_factory=dict)  # adapter-spezifische Rohdaten


class Adapter(abc.ABC):
    """Basisklasse für alle Treiber.

    SICHERHEIT: Adapter dürfen ausschließlich gegen Test-Targets fahren.
    Das wird in der konkreten Implementierung hart verdrahtet (siehe telegram.py),
    nicht dem Aufrufer überlassen.
    """

    name: str = "base"

    def __init__(self, suite: Suite, *, dry_run: bool = False) -> None:
        self.suite = suite
        self.dry_run = dry_run

    @abc.abstractmethod
    async def setup(self) -> None:
        """Vor dem Lauf: Verbindung aufbauen, Test-Zustand herstellen."""

    def begin_case(self, case_id: str) -> None:
        """Wird vor jedem Testfall aufgerufen. Default: no-op.

        Adapter im Dry-Run nutzen das, um ihre fallspezifischen Mock-Antworten
        zurückzusetzen — so funktionieren gezielte Re-Tests (--only) verlässlich.
        """

    @abc.abstractmethod
    async def teardown(self) -> None:
        """Nach dem Lauf: Verbindung schließen, aufräumen."""

    @abc.abstractmethod
    async def send_step(self, step: Step) -> Response:
        """Führt einen sendenden Schritt aus und gibt die Bot-Antwort zurück.

        Für nicht-sendende Schritte (expect/wait/assert_*) ist diese Methode
        nicht zuständig — die behandelt die Engine bzw. die Assertions.
        """
