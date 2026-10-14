from datetime import datetime as dt, timedelta

import pytest

from timelogg.model import (Entry, Feil, fmt_hm, from_stemplingsur, merge_import, needs_reminder,
                            open_entry, parse_dt, projects, resolve_end, stamp_in, stamp_out,
                            totals)

T9 = dt(2026, 10, 5, 9, 0)


def test_stamp_in_and_out():
    e = stamp_in([], "MaintPlan", T9)
    assert open_entry(e) == Entry("MaintPlan", T9)
    e = stamp_out(e, dt(2026, 10, 5, 11, 30), dt(2026, 10, 5, 12, 0))
    assert e == [Entry("MaintPlan", T9, dt(2026, 10, 5, 11, 30))]
    assert open_entry(e) is None


def test_only_one_open_entry():
    with pytest.raises(Feil, match="Allerede"):
        stamp_in(stamp_in([], "A", T9), "B", T9)


def test_stamp_in_reuses_existing_spelling():
    e = stamp_out(stamp_in([], "MaintPlan", T9), T9 + timedelta(hours=1), T9 + timedelta(hours=1))
    assert open_entry(stamp_in(e, " maintplan ", T9 + timedelta(hours=2))).project == "MaintPlan"


@pytest.mark.parametrize("name", ["", "   "])
def test_stamp_in_requires_project(name):
    with pytest.raises(Feil):
        stamp_in([], name, T9)


@pytest.mark.parametrize("end, msg", [(T9, "etter start"), (T9 + timedelta(hours=5), "fram i tid")])
def test_stamp_out_validation(end, msg):
    with pytest.raises(Feil, match=msg):
        stamp_out(stamp_in([], "A", T9), end, T9 + timedelta(hours=1))


def test_stamp_out_without_open():
    with pytest.raises(Feil, match="Ingen"):
        stamp_out([], T9, T9)


def test_resolve_end_same_day_and_formats():
    now = dt(2026, 10, 5, 18, 0)
    assert resolve_end("17:15", T9, now) == dt(2026, 10, 5, 17, 15)
    assert resolve_end("7.05", dt(2026, 10, 5, 6, 0), now) == dt(2026, 10, 5, 7, 5)
    assert resolve_end("", T9, now) == now
    assert resolve_end("2026-10-05 10:00", T9, now) == dt(2026, 10, 5, 10, 0)


def test_resolve_end_after_overnight_sleep():
    # Startet 20:00, Mac sov, spørsmålet kommer neste morgen.
    start, now = dt(2026, 10, 5, 20, 0), dt(2026, 10, 6, 8, 0)
    assert resolve_end("22:30", start, now) == dt(2026, 10, 5, 22, 30)
    assert resolve_end("01:00", start, now) == dt(2026, 10, 6, 1, 0)


def test_resolve_end_rejects_future_and_garbage():
    with pytest.raises(Feil, match="fram i tid"):
        resolve_end("15:00", T9, dt(2026, 10, 5, 12, 0))
    with pytest.raises(Feil, match="HH:MM"):
        resolve_end("snart", T9, dt(2026, 10, 5, 12, 0))


def test_needs_reminder():
    e = Entry("A", T9)
    assert not needs_reminder(e, None, T9 + timedelta(minutes=59))
    assert needs_reminder(e, None, T9 + timedelta(minutes=60))
    confirmed = T9 + timedelta(minutes=70)
    assert not needs_reminder(e, confirmed, T9 + timedelta(minutes=120))
    assert needs_reminder(e, confirmed, T9 + timedelta(minutes=130))
    # Bekreftelse fra forrige økt teller ikke.
    assert needs_reminder(e, T9 - timedelta(hours=3), T9 + timedelta(minutes=60))
    assert not needs_reminder(None, None, T9)
    assert not needs_reminder(Entry("A", T9, T9 + timedelta(hours=3)), None, T9 + timedelta(hours=5))


def test_projects_most_recent_first():
    e = [Entry("A", T9), Entry("B", T9 + timedelta(days=1)), Entry("A", T9 - timedelta(days=1))]
    assert projects(e) == ["B", "A"]


def test_parse_dt_accepts_excel_reformatted():
    assert parse_dt("05.10.2026 09:00") == T9
    assert parse_dt("2026-10-05 09:00:00") == T9
    assert parse_dt("05/10/2026 09:00") == T9  # Excel på Mac med norsk region
    assert parse_dt("05/10/2026 09:00:00") == T9
    assert parse_dt("05.10.2026 09.00") == T9
    with pytest.raises(Feil):
        parse_dt("i går")


def test_from_stemplingsur():
    rows = [
        {"Dato": "2026-10-01", "Start": "09:00", "Slutt": "11:30", "Prosjekt": "MaintPlan"},
        {"Dato": "2026-10-01", "Start": "22:00", "Slutt": "01:00", "Prosjekt": "MaintPlan"},
        {"Dato": "2026-10-02", "Start": "2026-10-02 08:00", "Slutt": "2026-10-02 09:00", "Prosjekt": "X"},
        {"Dato": "2026-10-03", "Start": "08:00", "Slutt": "", "Prosjekt": "X"},
        {"Dato": "2026-10-03", "Start": "08:00", "Slutt": "09:00", "Prosjekt": ""},
        {"Dato": "feil", "Start": "08:00", "Slutt": "09:00", "Prosjekt": "X"},
    ]
    entries, notes = from_stemplingsur(rows)
    assert entries == [
        Entry("MaintPlan", dt(2026, 10, 1, 9), dt(2026, 10, 1, 11, 30)),
        Entry("MaintPlan", dt(2026, 10, 1, 22), dt(2026, 10, 2, 1)),
        Entry("X", dt(2026, 10, 2, 8), dt(2026, 10, 2, 9)),
    ]
    assert [n.split(":")[0] for n in notes] == ["linje 5", "linje 6", "linje 7"]


def test_totals_today_and_week_with_open_and_midnight():
    now = dt(2026, 10, 7, 10, 0)  # onsdag
    e = [
        Entry("A", dt(2026, 10, 4, 23, 0), dt(2026, 10, 5, 1, 0)),  # søn→man: 1 t i uka
        Entry("A", dt(2026, 10, 6, 23, 0), dt(2026, 10, 7, 0, 30)),  # 30 min i dag
        Entry("B", dt(2026, 10, 7, 9, 0)),                           # åpen: 60 min
    ]
    assert totals(e, now) == (90, 60 + 90 + 60)
    assert fmt_hm(0) == "0:00" and fmt_hm(125) == "2:05"


def test_merge_import_is_idempotent():
    a = Entry("A", T9, T9 + timedelta(hours=1))
    b = Entry("B", T9 - timedelta(days=1), T9 - timedelta(days=1, hours=-1))
    merged, added, skipped = merge_import([a], [b, Entry("a", T9, T9 + timedelta(hours=2))])
    assert (merged, added, skipped) == ([b, a], 1, 1)
    assert merge_import(merged, [a, b])[1:] == (0, 2)
