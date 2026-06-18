"""Datenmodelle für das Test-Framework.

Schicht-1-Objekte (Szenarien) werden vom Loader in diese Dataclasses geparst.
Bewusst minimal und serialisierbar gehalten — das ist der Vertrag zwischen
Loader, Engine, Adaptern und Reporter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StepKind(str, Enum):
    """Art eines Schritts in einem Testfall."""

    SEND = "send"  # Text senden
    SEND_PHOTO = "send_photo"  # einzelnes Bild senden
    SEND_ALBUM = "send_album"  # mehrere Bilder als media_group
    SEND_VOICE = "send_voice"  # Sprachnachricht senden
    EXPECT = "expect"  # Antwort prüfen (Assertion)
    WAIT = "wait"  # Pause (z. B. Album-Sammelfenster)
    ASSERT_SHEET = "assert_sheet"  # Zeile im (Test-)Sheet prüfen
    ASSERT_N8N = "assert_n8n"  # n8n-Execution-Status prüfen


@dataclass
class Step:
    """Ein einzelner Schritt eines Testfalls."""

    kind: StepKind
    payload: Any  # Text, Pfad, Liste von Pfaden, Assertion-Dict, Sekunden ...
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Case:
    """Ein Testfall: id, Beschreibung, optionaler Setup, Schrittfolge."""

    id: str
    desc: str = ""
    setup: dict[str, Any] = field(default_factory=dict)
    steps: list[Step] = field(default_factory=list)
    # Tags ordnen einen Testfall einem Feature/Bereich zu. Damit lässt sich nach
    # einer Änderung gezielt re-testen: "Feature 'album' geändert -> alle Fälle
    # mit tag 'album' fahren" (siehe runner.run --tag).
    tags: list[str] = field(default_factory=list)


@dataclass
class Target:
    """Wogegen getestet wird. Adapter-spezifisch."""

    adapter: str  # "telegram" | "http" | ...
    bot: str | None = None  # z. B. "@zkb_kontakt_bot"
    base_url: str | None = None  # für HTTP-Adapter
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Suite:
    """Eine Test-Suite: Ziel, globaler Setup, Liste von Testfällen."""

    name: str
    target: Target
    setup: dict[str, Any] = field(default_factory=dict)
    cases: list[Case] = field(default_factory=list)
    source_path: str | None = None


# --- Ergebnis-Modelle (Schicht 4: Reporting) ---


class Status(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"  # technischer Fehler, kein fachliches Fail
    SKIP = "skip"


@dataclass
class StepResult:
    kind: str
    status: Status
    detail: str = ""  # Diff / Begründung bei Fail
    latency_ms: float | None = None


@dataclass
class CaseResult:
    id: str
    desc: str
    status: Status
    steps: list[StepResult] = field(default_factory=list)
    duration_ms: float = 0.0
    error: str | None = None


@dataclass
class SuiteResult:
    suite: str
    run_id: str
    cases: list[CaseResult] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""
    # Optionaler Kosten-Platzhalter (z. B. aus LLM-as-judge Sprint 7).
    # Default 0.0 — rückwärtskompatibel, wird nur befüllt wenn Adapter Kosten meldet.
    cost: float = 0.0

    @property
    def passed(self) -> int:
        return sum(1 for c in self.cases if c.status is Status.PASS)

    @property
    def skipped(self) -> int:
        return sum(1 for c in self.cases if c.status is Status.SKIP)

    @property
    def executed(self) -> int:
        """Anzahl tatsächlich gefahrener Fälle (ohne übersprungene)."""
        return self.total - self.skipped

    @property
    def total(self) -> int:
        return len(self.cases)

    @property
    def all_green(self) -> bool:
        """Grün = kein gefahrener Fall ist FAIL/ERROR. Übersprungene zählen nicht."""
        return all(c.status in (Status.PASS, Status.SKIP) for c in self.cases)

    # --- Aggregat-Metriken (Latenz) ---

    @property
    def total_latency_ms(self) -> float:
        """Summe aller Step-Latenzen über alle Fälle."""
        return sum(
            s.latency_ms
            for c in self.cases
            for s in c.steps
            if s.latency_ms is not None
        )

    @property
    def avg_latency_ms(self) -> float | None:
        """Durchschnittliche Step-Latenz; None wenn keine Latenz-Daten vorhanden."""
        values = [
            s.latency_ms
            for c in self.cases
            for s in c.steps
            if s.latency_ms is not None
        ]
        return sum(values) / len(values) if values else None

    @property
    def max_latency_ms(self) -> float | None:
        """Maximale Step-Latenz; None wenn keine Latenz-Daten vorhanden."""
        values = [
            s.latency_ms
            for c in self.cases
            for s in c.steps
            if s.latency_ms is not None
        ]
        return max(values) if values else None

    @property
    def total_duration_ms(self) -> float:
        """Summe der Case-Laufzeiten (duration_ms) als Gesamt-Laufzeit."""
        return sum(c.duration_ms for c in self.cases)
