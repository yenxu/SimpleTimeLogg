"""Hele flyten mot ekte filer, med falsk klokke og falskt UI."""
import threading
from datetime import datetime as dt
from pathlib import Path

import pytest

from timelogg import store
from timelogg.app import App, run
from timelogg.menu import encode
from timelogg.model import Entry

SCRIPT = "/Users/yen/timelogg/plugin/timelogg.1m.py"


class FakeUI:
    def __init__(self, answers=(), new_project=None, end_time=None, file=None):
        self.answers, self.new_project, self.end_time, self.file = list(answers), new_project, end_time, file
        self.notes, self.asked, self.opened = [], 0, []

    def ask_still_working(self, project, start, now, give_up):
        self.asked += 1
        return self.answers.pop(0)

    def ask_end_time(self, project, start, now):
        return self.end_time

    def ask_new_project(self):
        return self.new_project

    def choose_file(self):
        return self.file

    def open_file(self, path):
        self.opened.append(path)

    def notify(self, msg):
        self.notes.append(msg)


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def ctx(tmp_path):
    clock, ui = Clock(dt(2026, 10, 5, 9, 0)), FakeUI()
    app = App(tmp_path / "icloud" / "timer.csv", tmp_path / "state", ui, clock)
    spawned = []

    def click(*args):
        return run(list(args), app, SCRIPT, lambda: spawned.append(1))

    return app, ui, clock, click, spawned


def test_click_in_and_out(ctx):
    app, ui, clock, click, _ = ctx
    click("inn", encode("Rail Nexa: MaintPlan"))
    assert "⏱ Rail Nexa: MaintPlan 0:00" in click()
    clock.t = dt(2026, 10, 5, 9, 45)
    assert click().startswith("⏱ Rail Nexa: MaintPlan 0:45")
    click("ut")
    assert store.load(app.csv) == [Entry("Rail Nexa: MaintPlan", dt(2026, 10, 5, 9), dt(2026, 10, 5, 9, 45))]
    assert ui.notes == ["Inn: Rail Nexa: MaintPlan 09:00", "Ut: Rail Nexa: MaintPlan 09:00–09:45"]


def test_new_project_via_dialog_and_cancel(ctx):
    app, ui, clock, click, _ = ctx
    ui.new_project = None
    click("inn")
    assert store.load(app.csv) == []
    ui.new_project = "BM73"
    click("inn")
    assert store.load(app.csv) == [Entry("BM73", dt(2026, 10, 5, 9))]


def test_ut_kl_uses_dialog_time_and_cancel_keeps_open(ctx):
    app, ui, clock, click, _ = ctx
    click("inn", encode("A"))
    clock.t = dt(2026, 10, 5, 12, 0)
    ui.end_time = None
    click("ut-kl")
    assert store.load(app.csv)[0].end is None
    ui.end_time = "11:15"
    click("ut-kl")
    assert store.load(app.csv)[0].end == dt(2026, 10, 5, 11, 15)


def test_bytt_closes_and_opens_in_one_write(ctx):
    app, ui, clock, click, _ = ctx
    click("inn", encode("A"))
    clock.t = dt(2026, 10, 5, 10, 30)
    click("bytt", encode("B"))
    assert store.load(app.csv) == [Entry("A", dt(2026, 10, 5, 9), dt(2026, 10, 5, 10, 30)),
                                   Entry("B", dt(2026, 10, 5, 10, 30))]


def test_bytt_same_minute_replaces(ctx):
    app, ui, clock, click, _ = ctx
    click("inn", encode("A"))
    click("bytt", encode("B"))
    assert store.load(app.csv) == [Entry("B", dt(2026, 10, 5, 9))]


def test_errors_become_notifications(ctx):
    app, ui, clock, click, _ = ctx
    click("ut")
    click("inn", encode("A"))
    click("inn", encode("B"))
    assert ui.notes[0] == "Ingen åpen økt." and ui.notes[-1].startswith("Allerede")


def test_menu_spawns_reminder_only_when_due(ctx):
    app, ui, clock, click, spawned = ctx
    click("inn", encode("A"))
    clock.t = dt(2026, 10, 5, 9, 59)
    click()
    assert spawned == []
    clock.t = dt(2026, 10, 5, 10, 0)
    click()
    assert spawned == [1]


def test_reminder_flow(ctx):
    app, ui, clock, click, spawned = ctx
    click("inn", encode("A"))
    clock.t = dt(2026, 10, 5, 10, 0)
    ui.answers = [("ja", "")]
    click("vakt")
    assert ui.asked == 1 and not app.reminder_due()
    clock.t = dt(2026, 10, 5, 10, 59)
    assert not app.reminder_due()
    clock.t = dt(2026, 10, 5, 11, 0)
    ui.answers = [(None, "")]  # ubesvart: ingenting endres, spørres igjen neste runde
    click("vakt")
    assert app.reminder_due() and store.load(app.csv)[0].end is None
    ui.answers = [("nei", "10:40")]
    click("vakt")
    assert store.load(app.csv)[0].end == dt(2026, 10, 5, 10, 40)
    assert ui.notes[-1] == "Ut: A 09:00–10:40"


def test_reminder_ignores_answer_if_changed_in_menu_meanwhile(ctx):
    app, ui, clock, click, _ = ctx
    click("inn", encode("A"))
    clock.t = dt(2026, 10, 5, 10, 0)

    class ClicksOutWhileAsking(FakeUI):
        def ask_still_working(self, *a):
            click("ut")
            return "nei", "09:30"

    app.ui = ClicksOutWhileAsking()
    click("vakt")
    assert store.load(app.csv)[0].end == dt(2026, 10, 5, 10, 0)


def test_only_one_reminder_dialog_at_a_time(ctx):
    app, ui, clock, click, _ = ctx
    click("inn", encode("A"))
    clock.t = dt(2026, 10, 5, 10, 0)
    inside, release = threading.Event(), threading.Event()

    class Blocking(FakeUI):
        def ask_still_working(self, *a):
            self.asked += 1
            inside.set()
            release.wait(5)
            return None, ""

    app.ui = Blocking()
    t = threading.Thread(target=app.vakt)
    t.start()
    inside.wait(5)
    app.vakt()  # skal gi opp straks fordi låsen er tatt
    release.set()
    t.join()
    assert app.ui.asked == 1


def test_import_via_file_dialog(ctx, tmp_path):
    app, ui, clock, click, _ = ctx
    src = tmp_path / "stemplingsur.csv"
    src.write_text("﻿Dato;Start;Slutt;Timer;Prosjekt;Kommentar;Id\r\n"
                   "2026-10-01;09:00;11:00;2,00;MaintPlan;\"notat; med semikolon\";a1\r\n"
                   "2026-10-02;08:00;;;MaintPlan;;a2\r\n", encoding="utf-8")
    ui.file = src
    click("importer")
    click("importer")
    assert ui.notes == ["Importert 1, 0 fantes fra før, 1 linjer avvist (se logg).",
                        "Importert 0, 1 fantes fra før, 1 linjer avvist (se logg)."]
    assert store.load(app.csv) == [Entry("MaintPlan", dt(2026, 10, 1, 9), dt(2026, 10, 1, 11))]
    ui.file = None
    click("importer")
    assert len(ui.notes) == 2


def test_open_creates_file_first_time(ctx):
    app, ui, clock, click, _ = ctx
    click("apne")
    assert ui.opened == [app.csv] and app.csv.read_bytes().startswith(b"\xef\xbb\xbfProsjekt;Start;Slutt")


def test_broken_csv_still_shows_icon(ctx):
    app, ui, clock, click, _ = ctx
    app.csv.parent.mkdir(parents=True, exist_ok=True)
    app.csv.write_text("noe;annet\n", encoding="utf-8")
    assert click().startswith("⏱ ⚠\n---\n")


def test_csv_roundtrip_and_format(tmp_path):
    f = tmp_path / "timer.csv"
    e = [Entry('Rail "Nexa"; MaintPlan', dt(2026, 10, 5, 9), dt(2026, 10, 5, 10)), Entry("Æøå", dt(2026, 10, 6, 8))]
    store.save(f, e)
    assert store.load(f) == e
    assert f.read_bytes().startswith(b"\xef\xbb\xbfProsjekt;Start;Slutt;Timer\r\n")
    assert not list(tmp_path.glob(".timer-*"))


def test_confirmed_state_tolerates_garbage(tmp_path):
    p = tmp_path / "s.json"
    assert store.load_confirmed(p) is None
    p.write_text("{ødelagt")
    assert store.load_confirmed(p) is None
    store.save_confirmed(p, dt(2026, 10, 5, 9))
    assert store.load_confirmed(p) == dt(2026, 10, 5, 9)
