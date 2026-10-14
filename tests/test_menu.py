from datetime import datetime as dt

import pytest

from timelogg.menu import MAX_TOP, decode, encode, render
from timelogg.model import Entry
from timelogg.ui import parse_ask

S = "/Users/yen/Library/Mobile Documents/timelogg/plugin/timelogg.1m.py"
NOW = dt(2026, 10, 5, 10, 30)


def test_idle_menu_lists_recent_projects_first():
    e = [Entry("Old", dt(2026, 10, 1, 9), dt(2026, 10, 1, 10)),
         Entry("Rail Nexa: MaintPlan", dt(2026, 10, 5, 8), dt(2026, 10, 5, 9))]
    lines = render(e, NOW, S).split("\n")
    assert lines[:3] == ["⏱", "---", "Stemple inn på:"]
    assert lines[3] == (f'Rail Nexa: MaintPlan | bash="{S}" param1=inn param2={encode("Rail Nexa: MaintPlan")}'
                        " terminal=false refresh=true")
    assert lines[4].startswith("Old |")
    assert lines[5] == f'Nytt prosjekt… | bash="{S}" param1=inn terminal=false refresh=true'
    assert "I dag 1:00 · Uke 1:00" in lines


def test_running_menu_shows_title_and_switch_submenu():
    e = [Entry("B", dt(2026, 10, 4, 9), dt(2026, 10, 4, 10)), Entry("A", dt(2026, 10, 5, 9, 15))]
    lines = render(e, NOW, S).split("\n")
    assert lines[0] == "⏱ A 1:15"
    assert any("param1=ut " in l for l in lines) and any("param1=ut-kl" in l for l in lines)
    i = lines.index("Bytt til")
    assert lines[i + 1].startswith("--B |") and "param1=bytt" in lines[i + 1]
    assert lines[i + 2].startswith("--Nytt prosjekt… |")
    assert not any(l.startswith("--A |") for l in lines)  # ikke bytt til seg selv


def test_many_projects_go_under_more():
    e = [Entry(f"P{i}", dt(2026, 10, 1, i), dt(2026, 10, 1, i, 30)) for i in range(MAX_TOP + 2)]
    lines = render(e, NOW, S).split("\n")
    assert "Flere" in lines
    assert sum(l.startswith("--P") for l in lines) == 2


def test_pipe_in_name_cannot_break_menu():
    lines = render([Entry("A|B", NOW)], NOW, S).split("\n")
    assert lines[0] == "⏱ A¦B 0:00"


@pytest.mark.parametrize("name", ["Rail Nexa: MaintPlan", 'a"b|c', "Æøå"])
def test_encode_roundtrip(name):
    assert decode(encode(name)) == name and encode(name).isalnum()


@pytest.mark.parametrize("out, expected", [
    ("Ja\n10:00\nfalse", ("ja", "10:00")),
    ("Nei, sluttet\n 09:45 \nfalse", ("nei", "09:45")),
    ("Ja\n10:00\ntrue", (None, "")),
    (None, (None, "")),
])
def test_parse_ask(out, expected):
    assert parse_ask(out) == expected
