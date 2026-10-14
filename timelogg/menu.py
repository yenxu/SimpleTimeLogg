"""Bygger SwiftBar-menyen som ren tekst – ingen I/O, så den testes som en vanlig funksjon."""
from __future__ import annotations

from datetime import datetime

from .model import Entry, fmt_hm, minutes, open_entry, projects, totals

MAX_TOP = 8  # flere prosjekter enn dette havner under «Flere», så menyen holder seg kort


def encode(project: str) -> str:
    # Hex i stedet for sitering: prosjektnavn med mellomrom, anførselstegn eller '|'
    # kan da aldri bryte SwiftBar-parseren.
    return project.encode().hex()


def decode(value: str) -> str:
    return bytes.fromhex(value).decode()


def _label(text: str) -> str:
    return text.replace("|", "¦")  # '|' skiller tekst fra parametre i SwiftBar


def _item(script: str, label: str, action: str, project: str | None = None, sub: bool = False) -> str:
    args = f'bash="{script}" param1={action}'
    if project is not None:
        args += f" param2={encode(project)}"
    return f"{'--' if sub else ''}{_label(label)} | {args} terminal=false refresh=true"


def _project_items(script: str, names: list[str], action: str, sub: bool) -> list[str]:
    pre = "--" if sub else ""
    top, rest = names[:MAX_TOP], names[MAX_TOP:]
    lines = [_item(script, p, action, p, sub) for p in top]
    if rest:
        lines.append(f"{pre}Flere")
        lines += [f"--{pre}" + _item(script, p, action, p) for p in rest]
    lines.append(_item(script, "Nytt prosjekt…", action, sub=sub))
    return lines


def render(entries: list[Entry], now: datetime, script: str) -> str:
    current = open_entry(entries)
    names = projects(entries)
    today, week = totals(entries, now)
    if current:
        lines = [
            f"⏱ {_label(current.project)} {fmt_hm(minutes(current.start, now))}",
            "---",
            f"{_label(current.project)} siden {current.start:%H:%M}",
            _item(script, "Stemple ut nå", "ut"),
            _item(script, "Stemple ut kl. …", "ut-kl"),
            "Bytt til",
            *_project_items(script, [p for p in names if p != current.project], "bytt", sub=True),
        ]
    else:
        lines = ["⏱", "---", "Stemple inn på:",
                 *_project_items(script, names, "inn", sub=False)]
    lines += [
        "---",
        f"I dag {fmt_hm(today)} · Uke {fmt_hm(week)}",
        _item(script, "Åpne timer.csv", "apne"),
        _item(script, "Importer fra Stemplingsur…", "importer"),
    ]
    return "\n".join(lines)
