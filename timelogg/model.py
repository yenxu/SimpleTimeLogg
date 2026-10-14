"""Ren domenelogikk. Ingen filer, klokke eller dialoger her, slik at reglene kan testes isolert."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, time, timedelta

INTERVAL = timedelta(minutes=60)
FMT = "%Y-%m-%d %H:%M"
# Excel skriver datoer om til maskinens regionformat når fila lagres derfra
# (f.eks. 05/10/2026 19:35); vi må tåle det. Dag først: norsk/europeisk oppsett.
_PARSE_FMTS = tuple(f"{d} {t}" for d in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y")
                    for t in ("%H:%M", "%H:%M:%S", "%H.%M"))


class Feil(ValueError):
    """Brukerfeil med melding som kan vises direkte."""


@dataclass(frozen=True)
class Entry:
    project: str
    start: datetime
    end: datetime | None = None


def parse_dt(text: str) -> datetime:
    text = text.strip()
    for fmt in _PARSE_FMTS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    raise Feil(f"Ukjent tidsformat: {text!r}")


def fmt_dt(dt: datetime) -> str:
    return dt.strftime(FMT)


def open_entry(entries: list[Entry]) -> Entry | None:
    return next((e for e in entries if e.end is None), None)


def projects(entries: list[Entry]) -> list[str]:
    """Sist brukte først, så standardvalget i velgeren blir riktig."""
    seen: dict[str, datetime] = {}
    for e in entries:
        if e.project not in seen or e.start > seen[e.project]:
            seen[e.project] = e.start
    return sorted(seen, key=seen.__getitem__, reverse=True)


def stamp_in(entries: list[Entry], project: str, now: datetime) -> list[Entry]:
    project = project.strip()
    if not project:
        raise Feil("Prosjektnavn mangler.")
    current = open_entry(entries)
    if current:
        raise Feil(f"Allerede stemplet inn på {current.project} siden {fmt_dt(current.start)}.")
    # Gjenbruk eksisterende skrivemåte så samme prosjekt ikke deles i to i rapporten.
    known = {p.casefold(): p for p in projects(entries)}
    return [*entries, Entry(known.get(project.casefold(), project), now)]


def stamp_out(entries: list[Entry], end: datetime, now: datetime) -> list[Entry]:
    current = open_entry(entries)
    if not current:
        raise Feil("Ingen åpen økt.")
    if end <= current.start:
        raise Feil(f"Slutt må være etter start ({fmt_dt(current.start)}).")
    if end > now:
        raise Feil("Slutt kan ikke være fram i tid.")
    return [replace(e, end=end) if e is current else e for e in entries]


def resolve_end(text: str, start: datetime, now: datetime) -> datetime:
    """'HH:MM' tolkes som første forekomst etter start, så en økt som har stått over natta
    (Mac-en sov) kan lukkes med gårsdagens klokkeslett uten å skrive dato."""
    text = text.strip()
    if not text:
        return now
    if len(text) > 5:
        return parse_dt(text)
    try:
        t = time.fromisoformat(text.replace(".", ":").zfill(5))
    except ValueError:
        raise Feil(f"Skriv sluttid som HH:MM, ikke {text!r}.") from None
    candidate = datetime.combine(start.date(), t)
    if candidate <= start:
        candidate += timedelta(days=1)
    if candidate > now:
        raise Feil(f"{text} er fram i tid.")
    return candidate


def needs_reminder(entry: Entry | None, confirmed: datetime | None, now: datetime,
                   interval: timedelta = INTERVAL) -> bool:
    if entry is None or entry.end is not None:
        return False
    # En bekreftelse fra en tidligere økt gjelder ikke denne.
    since = max(confirmed, entry.start) if confirmed else entry.start
    return now - since >= interval


def from_stemplingsur(rows: list[dict[str, str]]) -> tuple[list[Entry], list[str]]:
    """Leser Stemplingsur-eksport (Dato;Start;Slutt;Timer;Prosjekt;Kommentar;Id).
    Kommentar og Id droppes bevisst: det nye formatet har bare prosjekt, start og slutt."""
    out: list[Entry] = []
    notes: list[str] = []
    for n, row in enumerate(rows, start=2):  # linje 1 er overskriften
        try:
            project = (row.get("Prosjekt") or "").strip()
            if not project:
                raise Feil("prosjekt mangler")
            start = _stemplingsur_time(row.get("Dato", ""), row.get("Start", ""))
            if not (row.get("Slutt") or "").strip():
                notes.append(f"linje {n}: åpen økt hoppet over")
                continue
            end = _stemplingsur_time(row.get("Dato", ""), row["Slutt"])
            if end <= start:  # over midnatt
                end += timedelta(days=1)
            out.append(Entry(project, start, end))
        except Feil as e:
            notes.append(f"linje {n}: {e}")
    return out, notes


def _stemplingsur_time(day: str, value: str) -> datetime:
    value = value.strip()
    return parse_dt(value if len(value) > 5 else f"{day.strip()} {value}")


def minutes(a: datetime, b: datetime) -> int:
    return max(0, int((b - a).total_seconds() // 60))


def fmt_hm(mins: int) -> str:
    return f"{mins // 60}:{mins % 60:02d}"


def totals(entries: list[Entry], now: datetime) -> tuple[int, int]:
    """Minutter i dag og denne ISO-uka. Åpen økt telles fram til nå, økter over
    midnatt kuttes ved periodegrensen."""
    day = datetime.combine(now.date(), time())
    week = day - timedelta(days=now.weekday())

    def overlap(since: datetime) -> int:
        return sum(minutes(max(e.start, since), min(e.end or now, now)) for e in entries)

    return overlap(day), overlap(week)


def merge_import(existing: list[Entry], incoming: list[Entry]) -> tuple[list[Entry], int, int]:
    """Samme prosjekt + start regnes som samme økt, så importen kan kjøres flere ganger."""
    keys = {(e.project.casefold(), e.start) for e in existing}
    added = []
    for e in incoming:
        key = (e.project.casefold(), e.start)
        if key not in keys:
            keys.add(key)
            added.append(e)
    merged = sorted([*existing, *added], key=lambda e: e.start)
    return merged, len(added), len(incoming) - len(added)