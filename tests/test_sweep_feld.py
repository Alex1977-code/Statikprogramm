"""Netzeinstellungen.sweep ist ein Wort: "aus" | "sauber" | "immer" (25.09.2026).

Die dritte Lieferung der Vernetzer-Sitzung liest das Feld nur noch ueber
sweep.betriebsart(model) und kennt drei Betriebsarten. Das Modell fuehrt es
darum als Wort, Vorgabe "aus". Aeltere Dateien fuehren True/False; beim
Laden werden beide zu "aus" - der Anwender hat den Sweep-Haken nie bewusst
gewollt (so hat es der Zweig ui/pS-2509 fuer den Haken festgelegt), und
betriebsart laese True als "immer". Ein unbekanntes Wort wird beim Laden
ebenfalls "aus" (betriebsart laese es als "immer").

Aufruf: python -m tests.test_sweep_feld
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK  ' if ok else 'FAIL'} {name:70s} {detail}")


def _geladen(wert):
    """Modell mit netz.sweep = wert speichern und wieder laden."""
    from statik3d.model import Model
    m = Model("x")
    d = m.to_dict()
    d["netz"]["sweep"] = wert
    return Model.from_dict(d)


def test_vorgabe_ist_ein_wort():
    from statik3d.model import Netzeinstellungen, Model
    from statik3d import sweep
    n = Netzeinstellungen()
    check("Vorgabe von Netzeinstellungen.sweep ist das Wort „aus“",
          isinstance(n.sweep, str) and n.sweep == "aus", repr(n.sweep))
    check("… und der Vernetzer liest „aus“", sweep.betriebsart(Model("x")) == "aus",
          sweep.betriebsart(Model("x")))
    d = Model("x").to_dict()
    check("gespeichert wird das Wort", d["netz"].get("sweep") == "aus", repr(d["netz"].get("sweep")))


def test_alte_datei_mit_haken():
    from statik3d import sweep
    an, aus = _geladen(True), _geladen(False)
    check("alte Datei mit sweep = true lädt mit „aus“", an.netz.sweep == "aus", repr(an.netz.sweep))
    check("… und der Vernetzer sweept nicht (betriebsart „aus“, nicht „immer“)",
          sweep.betriebsart(an) == "aus", sweep.betriebsart(an))
    check("alte Datei mit sweep = false lädt mit „aus“", aus.netz.sweep == "aus", repr(aus.netz.sweep))


def test_woerter_beim_laden():
    from statik3d import sweep
    s = _geladen("sauber")
    check("„sauber“ bleibt beim Laden „sauber“", s.netz.sweep == "sauber" and sweep.betriebsart(s) == "sauber",
          repr(s.netz.sweep))
    s2 = _geladen(" Sauber ")
    check("… auch mit Großbuchstaben und Leerzeichen", s2.netz.sweep == "sauber", repr(s2.netz.sweep))
    u = _geladen("hexaeder")
    check("ein unbekanntes Wort lädt als „aus“ (betriebsart läse es als „immer“)",
          u.netz.sweep == "aus" and sweep.betriebsart(u) == "aus", repr(u.netz.sweep))
    ohne = _geladen("aus")
    del_d = ohne.to_dict()
    del del_d["netz"]["sweep"]
    from statik3d.model import Model
    m = Model.from_dict(del_d)
    check("Datei ohne das Feld lädt mit „aus“", m.netz.sweep == "aus", repr(m.netz.sweep))


def main():
    for t in (test_vorgabe_ist_ein_wort, test_alte_datei_mit_haken, test_woerter_beim_laden):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:             # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
