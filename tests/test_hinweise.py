"""Importhinweise (17.09.2026): haftende Fuge an einem Zylinder -> Vorschlag
Reibung; Zylinder ohne Spiel in seiner Bohrung -> Vorschlag Spiel geben.
Vorschlaege aendern nichts von selbst; anwenden() setzt sie um, die Liste
reist mit dem Modell.

Aufruf:  python -m tests.test_hinweise
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import hinweise, spiel                          # noqa: E402
from statik3d.model import Model                              # noqa: E402
from tests.test_spiel import _stift_und_platte                # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:78s} {detail}")
    return ok


def _modell():
    m, k = _stift_und_platte()
    kb = m.add_kontaktbedingung("Stift").standard_anwenden("Rau")      # haftet, hebt ab (RFEM Typ 4)
    kb.koerpernamen, kb.gegenkoerper = ["V1"], ["Platte"]
    kb.flaechennamen = ["V1_M1", "V1_M2"]
    return m, kb


def test_erkennen_und_anwenden():
    m, kb = _modell()
    h = hinweise.erzeugen(m)
    arten = sorted(x["art"] for x in h)
    check("zwei Hinweise: haftende Fuge am Zylinder (Reibung) und Nullspiel (Spiel)", arten == ["reibung", "spiel"], str(arten))
    reib = next(x for x in h if x["art"] == "reibung")
    sp_ = next(x for x in h if x["art"] == "spiel")
    check("Reibung: nennt Fuge und Zylinder, Vorschlag Reibungsbehaftet μ = 0,2",
          "Stift" in reib["text"] and ["kontaktbedingung", "Stift"] in reib["objekte"] and ["geokoerper_einzeln", "V1"] in reib["objekte"]
          and reib["vorschlag"]["mu"] == 0.2, reib["text"][:100])
    check("Spiel: nennt Zylinder und Bohrung (Platte), Vorschlag 0,02 mm",
          sp_["vorschlag"]["spiel"] == "V1" and ["geokoerper_einzeln", "Platte"] in sp_["objekte"] and sp_["vorschlag"]["mm"] == 0.02,
          sp_["text"][:100])
    check("nichts wird von selbst geändert: die Fuge haftet noch, der Stift hat r = 20 mm",
          kb.standard == "Rau" and abs(spiel.zylinder(m, "V1")["radius"] - 0.02) < 1e-12)
    m.importhinweise = h
    check("offen: beide", len(hinweise.offen(m)) == 2)
    log = []
    e1 = hinweise.anwenden(m, reib, log)
    check("Reibung angewendet: Fuge Reibungsbehaftet mit μ = 0,2, Hinweis erledigt, Kontakt neu auszuführen",
          e1["ok"] and kb.standard == "Reibungsbehaftet" and abs(kb.reibbeiwert() - 0.2) < 1e-12 and reib["erledigt"] == "angewendet"
          and e1["kontakte"] == ["Stift"], str(e1))
    e2 = hinweise.anwenden(m, sp_, log)
    check("Spiel angewendet: der Stift hat r = 19,99 mm, der Körper ist neu zu vernetzen, seine Fuge auszuführen",
          e2["ok"] and abs(spiel.zylinder(m, "V1")["radius"] - 0.01999) < 1e-9 and e2["koerper"] == ["V1"] and "Stift" in e2["kontakte"],
          str(e2))
    check("offen: keiner mehr; Kurzzeilen fuer den Baum", not hinweise.offen(m) and "μ = 0.2" in hinweise.kurz(reib) and "Spiel 0.02 mm" in hinweise.kurz(sp_),
          f"{hinweise.kurz(reib)} / {hinweise.kurz(sp_)}")
    # verwerfen
    m2, _kb2 = _modell()
    h2 = hinweise.erzeugen(m2)
    hinweise.verwerfen(h2[0])
    m2.importhinweise = h2
    check("verworfen zählt nicht als offen", len(hinweise.offen(m2)) == 1 and h2[0]["erledigt"] == "verworfen")
    # speichern und laden
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "h.json")
        m2.save(p)
        m3 = Model.load(p)
        check("die Hinweise reisen mit dem Modell (Speichern und Laden)",
              len(getattr(m3, "importhinweise", [])) == 2 and m3.importhinweise[0]["erledigt"] == "verworfen"
              and m3.importhinweise[1]["art"] == "spiel", str(len(getattr(m3, "importhinweise", []))))
    # ohne Zylinder: keine Hinweise
    from tests.test_fugen import zwei_bloecke
    m4 = zwei_bloecke("eigene", 0.5, 0.15)
    check("zwei Blöcke ohne Zylinder: keine Hinweise", hinweise.erzeugen(m4) == [])


def main():
    for t in (test_erkennen_und_anwenden,):
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    sys.exit(main())
