"""macOS-dialoger via osascript. Tekst sendes som argv, ikke flettet inn i skriptet,
så prosjektnavn med anførselstegn ikke kan bryte AppleScript."""
from __future__ import annotations

import subprocess
from datetime import datetime, timedelta
from pathlib import Path

TITLE = "Timelogg"

# 'activate' først: dialoger fra en bakgrunnsprosess havner ellers bak vinduet du jobber i.
_ASK = """on run argv
  try
    activate
  end try
  set r to display dialog (item 1 of argv) default answer (item 2 of argv) ¬
    buttons {"Nei, sluttet", "Ja"} default button "Ja" with title "%s" ¬
    giving up after ((item 3 of argv) as integer)
  return (button returned of r) & linefeed & (text returned of r) & linefeed & ((gave up of r) as text)
end run""" % TITLE

_INPUT = """on run argv
  try
    activate
  end try
  set r to display dialog (item 1 of argv) default answer (item 2 of argv) ¬
    buttons {"Avbryt", (item 3 of argv)} default button 2 cancel button 1 with title "%s"
  return text returned of r
end run""" % TITLE

_CHOOSE_FILE = """on run argv
  try
    activate
  end try
  return POSIX path of (choose file with prompt (item 1 of argv))
end run"""

_NOTIFY = 'on run argv\n display notification (item 1 of argv) with title "%s"\nend run' % TITLE


def _osa(script: str, *args: str) -> str | None:
    p = subprocess.run(["osascript", "-e", script, *args], capture_output=True, text=True)
    return p.stdout.rstrip("\n") if p.returncode == 0 else None  # != 0: brukeren avbrøt


def parse_ask(output: str | None) -> tuple[str | None, str]:
    if output is None:
        return None, ""
    button, text, gave_up = (output.split("\n") + ["", ""])[:3]
    if gave_up.strip() == "true":
        return None, ""
    return ("ja" if button == "Ja" else "nei"), text.strip()


class MacUI:
    def ask_still_working(self, project: str, start: datetime, now: datetime,
                          give_up: timedelta) -> tuple[str | None, str]:
        msg = (f"Jobber du fortsatt med {project}?\n\nStartet {start:%d.%m %H:%M}.\n"
               "Har du sluttet: skriv sluttid (HH:MM) og trykk «Nei, sluttet».")
        return parse_ask(_osa(_ASK, msg, f"{now:%H:%M}", str(int(give_up.total_seconds()))))

    def ask_end_time(self, project: str, start: datetime, now: datetime) -> str | None:
        return _osa(_INPUT, f"Stemple ut fra {project} (startet {start:%d.%m %H:%M}).\n"
                    "Sluttid (HH:MM):", f"{now:%H:%M}", "Stemple ut")

    def ask_new_project(self) -> str | None:
        return _osa(_INPUT, "Navn på nytt prosjekt:", "", "Stemple inn")

    def choose_file(self) -> Path | None:
        path = _osa(_CHOOSE_FILE, "Velg CSV-eksport fra Stemplingsur")
        return Path(path) if path else None

    def open_file(self, path: Path) -> None:
        subprocess.run(["open", str(path)])

    def notify(self, message: str) -> None:
        _osa(_NOTIFY, message)
