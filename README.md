# Timelogg

Stemple inn og ut fra menylinjen på Mac. Timene lagres i én CSV-fil som åpnes i Excel.

```
SwiftBar (hvert minutt) ──► plugin/timelogg.1m.py ──► meny: ⏱ MaintPlan 1:23
        klikk i menyen ──► samme skript med handling (inn/ut/bytt/…)
        ≥ 60 min siden start/«Ja» ──► dialog «Jobber du fortsatt med …?» (gir opp etter 60 min)
                                   ▼
        iCloud Drive/Timelogg/timer.csv   Prosjekt;Start;Slutt  (tom Slutt = åpen)
```

| Modul | Ansvar |
|---|---|
| `model.py` | regler og summer, ingen I/O |
| `menu.py` | menyen som tekst |
| `store.py` | CSV (atomisk, Excel-vennlig) og siste bekreftelse |
| `ui.py` | macOS-dialoger og varsler |
| `app.py` | handlingene bak menyvalgene, logg i `~/Library/Application Support/Timelogg` |

## Oppsett (én gang)

1. Installer [SwiftBar](https://github.com/swiftbar/SwiftBar/releases).
2. Pakk ut `timelogg.zip`, for eksempel til `~/timelogg`.
3. Åpne SwiftBar og velg `~/timelogg/plugin` som plugin-mappe.
4. Importer gamle timer: menyen → «Importer fra Stemplingsur…».

Krever `/usr/bin/python3` (følger med Xcode Command Line Tools).

Test: `python3 -m pytest`
