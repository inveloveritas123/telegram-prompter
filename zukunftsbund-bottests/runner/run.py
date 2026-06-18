"""CLI-Einstieg: ein Befehl, der eine Suite durchspielt und Pass/Fail sagt.

Beispiele:
    python -m runner.run --suite kontakt-bot --dry-run
    python -m runner.run --suite kontakt-bot --only T1-neuer-kontakt-foto
    python -m runner.run --all --dry-run --json
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from runner.engine import run_suite
from runner.loader import discover_suites, load_suite
from runner.reporter import console_report, telegram_summary, write_json
from adapters.n8n import N8nClient
from adapters.sheets import build_sheet_provider

ROOT = Path(__file__).resolve().parent.parent
SUITES_DIR = ROOT / "suites"
REPORTS_DIR = ROOT / "reports"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="ZUKUNFTSBUND Bot-Test-Runner")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--suite", help="Name der Suite (Verzeichnis unter suites/)")
    g.add_argument("--all", action="store_true", help="alle entdeckten Suiten fahren")
    p.add_argument("--only", action="append", default=[], help="nur diese Case-IDs (mehrfach möglich)")
    p.add_argument("--tag", action="append", default=[], help="nur Fälle mit diesem Tag (mehrfach möglich) — für gezielte Re-Tests nach einer Änderung")
    p.add_argument("--dry-run", action="store_true", help="Mock-Modus ohne echte Verbindungen")
    p.add_argument("--json", action="store_true", help="JSON-Report nach reports/ schreiben")
    p.add_argument("--notify", action="store_true", help="Zusammenfassung per Telegram an dich senden (NOTIFY_* env)")
    p.add_argument("--quiet", action="store_true", help="nur die Zusammenfassungszeile ausgeben")
    return p.parse_args(argv)


def _build_context(*, dry_run: bool) -> dict:
    """Baut den Lauf-Context aus der Umgebung.

    Sprint 2: n8n-Client (wenn N8N_BASE_URL gesetzt und nicht Dry-Run).
    Sprint 4: Sheet-Provider (wenn SHEET_TEST_ID gesetzt und nicht Dry-Run).
    Im Dry-Run sind beide None → Assertions überspringen sauber.
    """
    ctx: dict = {}

    # n8n-Provider
    import os
    if not dry_run and os.environ.get("N8N_BASE_URL"):
        ctx["n8n"] = N8nClient(dry_run=False)
    else:
        ctx["n8n"] = N8nClient(dry_run=True)  # Dry-Run-Stub: alle Calls neutral

    # Sheet-Provider (None wenn nicht konfiguriert oder Dry-Run)
    sheet = build_sheet_provider(dry_run=dry_run)
    if sheet is not None:
        ctx["sheet"] = sheet

    return ctx


async def _run_one(name: str, path: Path, args: argparse.Namespace) -> bool:
    suite = load_suite(path)
    only = set(args.only) or None
    tags = set(args.tag) or None
    context = _build_context(dry_run=args.dry_run)
    result = await run_suite(suite, dry_run=args.dry_run, only=only, tags=tags, context=context)
    if args.quiet:
        print(telegram_summary(result))
    else:
        print(console_report(result))
    if args.json:
        out = write_json(result, REPORTS_DIR)
        if not args.quiet:
            print(f"JSON: {out}")
    if args.notify:
        from runner.notify import notify_telegram

        notify_telegram(telegram_summary(result), dry_run=args.dry_run)
    return result.all_green


async def main_async(args: argparse.Namespace) -> int:
    suites = discover_suites(SUITES_DIR)
    if args.all:
        targets = suites
    else:
        if args.suite not in suites:
            print(f"Suite {args.suite!r} nicht gefunden. Verfügbar: {', '.join(suites) or '(keine)'}")
            return 2
        targets = {args.suite: suites[args.suite]}

    all_green = True
    for name, path in targets.items():
        green = await _run_one(name, path, args)
        all_green = all_green and green
    return 0 if all_green else 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
