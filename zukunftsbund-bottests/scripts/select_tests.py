"""scripts/select_tests.py — Change-Detection: Git-Diff → passende Test-Tags

Liest `git diff --name-only <base>..HEAD`, mappt die geänderten Pfade über
`feature_map.yaml` auf Test-Tags und gibt die passenden `--tag`-Argumente für
den Runner aus.

Kernlogik: reine Funktion `pfade_zu_tags(pfade, regeln)` — vollständig ohne git
testbar (Diff-Liste injizierbar). Nur `main()` ruft git auf.

Beispiele:
    python scripts/select_tests.py                   # Diff gegen HEAD~1
    python scripts/select_tests.py --base main       # Diff gegen main
    python scripts/select_tests.py --base HEAD~3     # letzte 3 Commits
    python scripts/select_tests.py --dry-run         # zeigt Pfade + Tags, kein Commit
"""

from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
from pathlib import Path
from typing import Sequence

try:
    import yaml
except ImportError:  # pragma: no cover
    print("FEHLER: PyYAML nicht installiert. `pip install PyYAML`", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
FEATURE_MAP = ROOT / "feature_map.yaml"


# ---------------------------------------------------------------------------
# Kernlogik — reine Funktion, ohne git, vollständig testbar
# ---------------------------------------------------------------------------

def lade_regeln(map_pfad: Path = FEATURE_MAP) -> list[dict]:
    """Liest feature_map.yaml und gibt die Regeln zurück."""
    with map_pfad.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data.get("rules", [])


def pfade_zu_tags(pfade: Sequence[str], regeln: list[dict]) -> set[str]:
    """Mappt eine Liste geänderter Pfade (relativ zum Repo-Root) auf Tags.

    Reine Funktion: kein git, kein I/O — ideal für Unit-Tests.

    Args:
        pfade:   Liste von Pfadstrings aus `git diff --name-only`.
        regeln:  Geparste Regeln aus feature_map.yaml (Liste von Dicts mit
                 Schlüsseln 'globs' und 'tags').

    Returns:
        Menge aller passenden Tags (kann leer sein).
    """
    gefundene_tags: set[str] = set()
    for pfad in pfade:
        for regel in regeln:
            globs: list[str] = regel.get("globs", [])
            tags: list[str] = regel.get("tags", [])
            for glob in globs:
                # fnmatch prüft den Pfad-String direkt (kein ** — absichtlich,
                # da git diff immer vollständige relative Pfade ausgibt).
                if fnmatch.fnmatch(pfad, glob):
                    gefundene_tags.update(tags)
                    break  # erste passende Glob dieser Regel reicht
    return gefundene_tags


def tags_zu_args(tags: set[str]) -> list[str]:
    """Wandelt eine Tag-Menge in --tag-Argumente für runner.run um.

    Gibt eine leere Liste zurück, wenn keine Tags gefunden wurden
    (Caller kann dann --all verwenden).
    """
    return [f"--tag {tag}" for tag in sorted(tags)]


# ---------------------------------------------------------------------------
# Git-Aufruf-Schale
# ---------------------------------------------------------------------------

def git_diff_pfade(basis: str = "HEAD~1", cwd: Path | None = None) -> list[str]:
    """Ruft `git diff --name-only <basis>..HEAD` auf und gibt die Pfade zurück.

    Robust gegen:
    - kein git-Repo: gibt leere Liste zurück + Warnung
    - leerer Diff (keine Änderungen): gibt leere Liste zurück
    - git nicht im PATH: gibt leere Liste zurück + Warnung
    """
    arbeitsverzeichnis = cwd or ROOT
    try:
        ergebnis = subprocess.run(
            ["git", "diff", "--name-only", f"{basis}..HEAD"],
            cwd=arbeitsverzeichnis,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        print("WARNUNG: git nicht gefunden. Keine Tags ausgewählt.", file=sys.stderr)
        return []
    except subprocess.TimeoutExpired:
        print("WARNUNG: git diff Timeout. Keine Tags ausgewählt.", file=sys.stderr)
        return []

    if ergebnis.returncode != 0:
        # Kein git-Repo, ungültige Revision o.ä.
        stderr_kurz = ergebnis.stderr.strip()[:200]
        print(f"WARNUNG: git diff fehlgeschlagen ({stderr_kurz}). Keine Tags ausgewählt.", file=sys.stderr)
        return []

    pfade = [zeile.strip() for zeile in ergebnis.stdout.splitlines() if zeile.strip()]
    return pfade


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Change-Detection: Git-Diff → passende --tag-Argumente für runner.run.\n\n"
            "Gibt auf stdout die --tag-Argumente aus, die nach einer Änderung\n"
            "re-getestet werden sollten. Leer = keine Änderungen erkannt."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--base",
        default="HEAD~1",
        help="Basis-Revision für den Diff (default: HEAD~1). Beispiel: main, HEAD~3.",
    )
    p.add_argument(
        "--map",
        default=str(FEATURE_MAP),
        help=f"Pfad zur feature_map.yaml (default: {FEATURE_MAP})",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Zeigt geänderte Pfade und gefundene Tags, aber gibt keine --tag-Args aus.",
    )
    p.add_argument(
        "--pfade",
        nargs="*",
        help="Pfade direkt übergeben statt git-Diff zu lesen (für Tests/CI).",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    # Regeln laden
    map_pfad = Path(args.map)
    if not map_pfad.exists():
        print(f"FEHLER: feature_map.yaml nicht gefunden: {map_pfad}", file=sys.stderr)
        return 2

    regeln = lade_regeln(map_pfad)

    # Pfade bestimmen: entweder direkt übergeben oder via git diff
    if args.pfade is not None:
        pfade = list(args.pfade)
    else:
        pfade = git_diff_pfade(basis=args.base)

    if args.dry_run:
        print(f"Basis: {args.base}")
        print(f"Geänderte Pfade ({len(pfade)}):")
        for p in pfade:
            print(f"  {p}")

    if not pfade:
        if args.dry_run:
            print("Keine Änderungen erkannt — keine Tags ausgewählt.")
        return 0

    tags = pfade_zu_tags(pfade, regeln)

    if args.dry_run:
        print(f"Erkannte Tags: {sorted(tags) if tags else '(keine)'}")
        if tags:
            print("Runner-Argumente:")
            print("  " + " ".join(tags_zu_args(tags)))
        return 0

    # Normalausgabe: --tag-Argumente für runner.run
    if tags:
        print(" ".join(tags_zu_args(tags)))
    # Keine Tags → leere Ausgabe (Caller kann --all verwenden)
    return 0


if __name__ == "__main__":
    sys.exit(main())
