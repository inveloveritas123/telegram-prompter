#!/usr/bin/env python3
"""Erzeugt interaktiv eine Telethon StringSession für den Test-Account.

WICHTIG: Dieses Skript läuft EINMALIG interaktiv auf deinem Rechner.
Es fragt nach der Telefonnummer des Test-Accounts und generiert einen
sicheren StringSession-String, den du dann in .env als TELEGRAM_TEST_SESSION
speicherst. Nach diesem Setup brauchst du diesen Prozess nicht zu wiederholen —
der Adapter verbindet sich automatisch mit der gespeicherten Session.

Voraussetzungen:
  - TELEGRAM_API_ID und TELEGRAM_API_HASH müssen in der Umgebung gesetzt sein
    (üblicherweise aus .env).
  - Der Test-Account muss bereits existieren (z. B. per WhatsApp-Verifikation).
  - Dieses Skript muss auf deinem Rechner (nicht im CI/CD) laufen.

Warnung: Der StringSession ist vertraulich wie ein Passwort. Niemals in Git
oder öffentliche Repos committen.
"""

import asyncio
import os
import sys


async def main() -> None:
    """Interaktive StringSession-Erzeugung."""
    try:
        from telethon import TelegramClient  # type: ignore
        from telethon.sessions import StringSession  # type: ignore
    except ImportError:
        print("Fehler: Telethon ist nicht installiert.", file=sys.stderr)
        print("Installiere es mit: pip install telethon", file=sys.stderr)
        sys.exit(1)

    # Umgebungsvariablen auslesen
    api_id_str = os.environ.get("TELEGRAM_API_ID", "").strip()
    api_hash = os.environ.get("TELEGRAM_API_HASH", "").strip()

    if not api_id_str or not api_hash:
        print(
            "Fehler: TELEGRAM_API_ID und/oder TELEGRAM_API_HASH nicht gesetzt.",
            file=sys.stderr,
        )
        print(
            "Bitte in .env eintragen oder exportieren (z. B. export TELEGRAM_API_ID=123456).",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        api_id = int(api_id_str)
    except ValueError:
        print(f"Fehler: TELEGRAM_API_ID '{api_id_str}' ist keine gültige Nummer.", file=sys.stderr)
        sys.exit(1)

    print()
    print("=" * 70)
    print("Telethon StringSession-Generator für Test-Account")
    print("=" * 70)
    print()
    print("Dieser Prozess verbindet sich einmalig mit deinem Test-Account")
    print("und erzeugt einen verschlüsselten Session-String.")
    print()
    print("WICHTIG:")
    print("  • Der Test-Account muss bereits existieren und funktionsfähig sein.")
    print("  • Du wirst nach der Telefonnummer und dem Verifizierungs-Code gefragt.")
    print("  • Der resultierende String ist vertraulich (wie ein Passwort).")
    print("  • Speichere ihn nur in .env (niemals in Git).")
    print()

    phone = input("Gib die Telefonnummer des Test-Accounts ein (mit +): ").strip()
    if not phone:
        print("Abbruch: Telefonnummer erforderlich.", file=sys.stderr)
        sys.exit(1)

    print()
    print("Verbinde mich mit Telegram…")
    print()

    # Neue leere Session starten (wird bei der Authentifizierung gefüllt).
    session = StringSession("")
    client = TelegramClient(session, api_id, api_hash)

    try:
        await client.connect()
        print("Mit Telegram verbunden. Sende Verifizierungs-Code…")
        await client.send_code_request(phone)
        print()

        code = input("Gib den Verifizierungs-Code ein (den du per SMS/Telegram erhältst): ").strip()
        if not code:
            print("Abbruch: Code erforderlich.", file=sys.stderr)
            sys.exit(1)

        print()
        print("Verifiziere…")
        await client.sign_in(phone, code)
        print()

        # StringSession auslesen und ausgeben.
        session_string = session.save()

        print("=" * 70)
        print("ERFOLG!")
        print("=" * 70)
        print()
        print("Deine neue StringSession (kopiere diese Zeile komplett):")
        print()
        print(session_string)
        print()
        print("Speichere sie in .env unter TELEGRAM_TEST_SESSION:")
        print("  TELEGRAM_TEST_SESSION=<füge hier die String ein>")
        print()
        print("Hinweis: Diese Session bleibt gültig. Du brauchst diesen")
        print("Prozess nicht zu wiederholen.")
        print()

    except Exception as exc:  # pylint: disable=broad-except
        print()
        print(f"Fehler während der Verifizierung: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
