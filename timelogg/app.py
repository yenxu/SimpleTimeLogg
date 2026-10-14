"""Handlinger bak menyvalgene. Klokke, UI, stier og prosess-start injiseres,
så hele flyten testes uten Mac og uten SwiftBar."""
from __future__ import annotations

import fcntl
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import model, store
from .menu import decode, render
from .model import Feil

DEFAULT_CSV = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs/Timelogg/timer.csv"
# Tilstand per maskin holdes utenfor iCloud, så lås og bekreftelse ikke synkes til andre Mac-er.
DEFAULT_STATE = Path.home() / "Library/Application Support/Timelogg"
log = logging.getLogger("timelogg")


def _now() -> datetime:
    return datetime.now().replace(second=0, microsecond=0)


class App:
    def __init__(self, csv_path: Path, state_dir: Path, ui, clock: Callable[[], datetime] = _now):
        self.csv, self.ui, self.clock = csv_path, ui, clock
        self.state = state_dir / "state.json"
        self.lock = state_dir / "vakt.lock"
        state_dir.mkdir(parents=True, exist_ok=True)

    # --- handlinger (alle returnerer en melding som vises som varsel) ---

    def inn(self, project: str | None) -> str | None:
        project = project or self.ui.ask_new_project()
        if not project:
            return None
        entries = model.stamp_in(store.load(self.csv), project, self.clock())
        store.save(self.csv, entries)
        e = model.open_entry(entries)
        return f"Inn: {e.project} {e.start:%H:%M}"

    def ut(self, when: str | None = None) -> str:
        entries = store.load(self.csv)
        current = model.open_entry(entries)
        if not current:
            raise Feil("Ingen åpen økt.")
        now = self.clock()
        end = model.resolve_end(when or "", current.start, now)
        store.save(self.csv, model.stamp_out(entries, end, now))
        return f"Ut: {current.project} {current.start:%H:%M}–{end:%H:%M}"

    def ut_kl(self) -> str | None:
        current = model.open_entry(store.load(self.csv))
        if not current:
            raise Feil("Ingen åpen økt.")
        text = self.ui.ask_end_time(current.project, current.start, self.clock())
        return self.ut(text) if text is not None else None

    def bytt(self, project: str | None) -> str | None:
        project = project or self.ui.ask_new_project()
        if not project:
            return None
        # Ut og inn i samme skriving, så det aldri blir hull eller to åpne økter.
        now = self.clock()
        entries = store.load(self.csv)
        current = model.open_entry(entries)
        if current and current.start >= now:
            # Byttet i samme minutt (feilklikk): erstatt i stedet for å lage en 0-minutters økt.
            entries = [e for e in entries if e is not current]
        else:
            entries = model.stamp_out(entries, now, now)
        entries = model.stamp_in(entries, project, now)
        store.save(self.csv, entries)
        return f"Byttet til {model.open_entry(entries).project} {now:%H:%M}"

    def vakt(self) -> str | None:
        with self.lock.open("w") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return None  # en dialog står allerede oppe
            return self._vakt()

    def _vakt(self) -> str | None:
        current = model.open_entry(store.load(self.csv))
        if not self.reminder_due():
            return None
        # Dialogen gir opp etter ett intervall; ubesvart = ingen endring, neste runde spør igjen.
        answer, text = self.ui.ask_still_working(current.project, current.start, self.clock(),
                                                 model.INTERVAL)
        # Les på nytt: brukeren kan ha stemplet ut i menyen mens dialogen sto oppe.
        if model.open_entry(store.load(self.csv)) != current:
            return None
        if answer == "ja":
            store.save_confirmed(self.state, self.clock())
            log.info("vakt: bekreftet %s", current.project)
            return None
        if answer == "nei":
            return self.ut(text)
        log.info("vakt: ubesvart")
        return None

    def importer(self, path: Path | None = None) -> str | None:
        path = path or self.ui.choose_file()
        if not path:
            return None
        incoming, notes = model.from_stemplingsur(store.read_rows(path))
        merged, added, skipped = model.merge_import(store.load(self.csv), incoming)
        store.save(self.csv, merged)
        for n in notes:
            log.info("import: %s", n)
        extra = f", {len(notes)} linjer avvist (se logg)" if notes else ""
        return f"Importert {added}, {skipped} fantes fra før{extra}."

    def apne(self) -> None:
        if not self.csv.exists():
            store.save(self.csv, [])  # så Excel har noe å åpne første gang
        self.ui.open_file(self.csv)

    # --- meny ---

    def reminder_due(self) -> bool:
        current = model.open_entry(store.load(self.csv))
        return model.needs_reminder(current, store.load_confirmed(self.state), self.clock())

    def menu(self, script: str) -> str:
        return render(store.load(self.csv), self.clock(), script)


ACTIONS = {
    "inn": lambda app, arg: app.inn(arg),
    "ut": lambda app, arg: app.ut(),
    "ut-kl": lambda app, arg: app.ut_kl(),
    "bytt": lambda app, arg: app.bytt(arg),
    "vakt": lambda app, arg: app.vakt(),
    "importer": lambda app, arg: app.importer(),
    "apne": lambda app, arg: app.apne(),
}


def run(argv: list[str], app: App, script: str, spawn: Callable[[], None]) -> str:
    """Uten argumenter: tegn menyen (SwiftBar kaller dette hvert minutt).
    Med argumenter: utfør et menyvalg. Returnerer tekst som skal skrives til stdout."""
    try:
        if not argv:
            text = app.menu(script)
            if app.reminder_due():
                spawn()  # dialogen kan stå i en time; menyen må ikke vente på den
            return text
        action, arg = argv[0], (decode(argv[1]) if len(argv) > 1 else None)
        msg = ACTIONS[action](app, arg)
        if msg:
            log.info("%s: %s", action, msg)
            app.ui.notify(msg)
        return msg or ""
    except Feil as e:
        log.warning("%s: %s", argv[:1], e)
        app.ui.notify(str(e))
        # Menyen må alltid tegnes, også når CSV-en er ødelagt, ellers forsvinner ikonet.
        return f"⏱ ⚠\n---\n{str(e).replace('|', '¦')}" if not argv else str(e)


def main(argv: list[str], script: str) -> int:
    from .ui import MacUI

    csv_path = Path(os.environ.get("TIMELOGG_FIL", DEFAULT_CSV)).expanduser()
    state_dir = Path(os.environ.get("TIMELOGG_STATE", DEFAULT_STATE)).expanduser()
    app = App(csv_path, state_dir, MacUI())
    _setup_log(state_dir)

    def spawn() -> None:
        subprocess.Popen([sys.executable, script, "vakt"], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print(run(argv, app, script, spawn))
    return 0


def _setup_log(folder: Path) -> None:
    # Sporbarhet: hver endring logges, så en rar rad i CSV-en kan forklares i etterkant.
    if log.handlers:
        return
    h = logging.FileHandler(folder / "timelogg.log", encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(h)
    log.setLevel(logging.INFO)
