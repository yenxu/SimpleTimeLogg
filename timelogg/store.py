"""CSV-fila er eneste kilde til sannhet; tilstandsfila holder bare siste bekreftelse."""
from __future__ import annotations

import csv
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from .model import Entry, Feil, fmt_dt, parse_dt

HEADER = ["Prosjekt", "Start", "Slutt", "Timer"]
# utf-8-sig: uten BOM viser Excel æøå feil. Semikolon: norsk Excel bruker komma som desimaltegn.
ENC, DELIM = "utf-8-sig", ";"


def load(path: Path) -> list[Entry]:
    if not path.exists():
        return []
    with path.open(encoding=ENC, newline="") as f:
        rows = list(csv.reader(f, delimiter=DELIM))
    if not rows:
        return []
    if [h.strip() for h in rows[0][:3]] != HEADER[:3]:
        # Ikke gjett på en ukjent fil – da risikerer vi å skrive over brukerens data.
        raise Feil(f"{path.name}: forventet overskrift {';'.join(HEADER)}")
    entries = []
    for n, row in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in row):
            continue
        row += [""] * (3 - len(row))
        try:
            end = parse_dt(row[2]) if row[2].strip() else None
            entries.append(Entry(row[0].strip(), parse_dt(row[1]), end))
        except Feil as e:
            raise Feil(f"{path.name} linje {n}: {e}") from None
    return entries


def save(path: Path, entries: list[Entry]) -> None:
    rows = [HEADER] + [[e.project, fmt_dt(e.start),
                        fmt_dt(e.end) if e.end else "", _timer(e)]
                       for e in sorted(entries, key=lambda e: e.start)]
    _atomic_write(path, rows)


def _timer(e: Entry) -> str:
    # Avledet felt: komma som desimaltegn så norsk Excel kan summere kolonnen direkte.
    if e.end is None:
        return ""
    return f"{(e.end - e.start).total_seconds() / 3600:.2f}".replace(".", ",")


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding=ENC, newline="") as f:
        return list(csv.DictReader(f, delimiter=DELIM))


def load_confirmed(path: Path) -> datetime | None:
    try:
        return parse_dt(json.loads(path.read_text())["confirmed"])
    except (OSError, ValueError, KeyError, TypeError):
        return None  # mangler eller er ødelagt: regn fra start, det er alltid trygt


def save_confirmed(path: Path, when: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"confirmed": fmt_dt(when)}))


def _atomic_write(path: Path, rows: list[list[str]]) -> None:
    # Skriv til temp + rename: iCloud eller Excel skal aldri se en halvskrevet fil.
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".timer-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=ENC, newline="") as f:
            csv.writer(f, delimiter=DELIM, lineterminator="\r\n").writerows(rows)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
