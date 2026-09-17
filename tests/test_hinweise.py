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


def test_sammellauf():
    """alle_anwenden macht die Aenderungen aller Hinweise in einem Lauf und
    sammelt, was danach zu tun bleibt - vernetzt aber nichts: der Anwender
    vernetzt selbst, und das Vernetzen fuehrt die offenen Fugen aus."""
    m, kb = _modell()
    m.importhinweise = hinweise.erzeugen(m)
    gesehen: list = []
    log: list = []
    erg = hinweise.alle_anwenden(m, log=log, fortschritt=lambda i, n, t: gesehen.append((i, n, t)))
    check("beide Hinweise angewendet, keiner offen",
          len(erg["angewendet"]) == 2 and not erg["fehler"] and not hinweise.offen(m), str(erg["angewendet"])[:90])
    check("die Fuge ist umgestellt und der Stift verkleinert",
          kb.standard == "Reibungsbehaftet" and abs(spiel.zylinder(m, "V1")["radius"] - 0.01999) < 1e-9)
    check("gesammelt: Körper V1 und Kontakt Stift, jeder einmal",
          erg["koerper"] == ["V1"] and erg["kontakte"] == ["Stift"], f"{erg['koerper']} / {erg['kontakte']}")
    check("der Fortschritt meldet jeden Hinweis mit Nummer, Anzahl und Kurztext",
          [g[:2] for g in gesehen] == [(0, 2), (1, 2)] and "μ = 0.2" in gesehen[0][2], str(gesehen)[:120])
    check("nichts wurde vernetzt: der Körper wartet auf das Netz des Anwenders",
          not (m.koerper["V1"].elemente or []) and kb.wartet_auf_netz(m))
    # Abbrechen: der erste ist angewendet, der zweite bleibt offen
    m2, _kb2 = _modell()
    m2.importhinweise = hinweise.erzeugen(m2)
    erg2 = hinweise.alle_anwenden(m2, fortschritt=lambda i, n, t: i < 1)
    check("Abbrechen nach dem ersten: einer angewendet, einer offen, als abgebrochen gemeldet",
          len(erg2["angewendet"]) == 1 and len(hinweise.offen(m2)) == 1 and erg2["abgebrochen"], str(erg2)[:100])


def test_reibung_an_ausgefuehrter_fuge():
    """Eine schon ausgefuehrte Fuge auf Reibung umstellen: ihr Kontaktpaar
    traegt den alten Reibbeiwert, und kontaktfuge_ausfuehren ruehrt eine
    ausgefuehrte Fuge nicht mehr an (Grund „schon ausgefuehrt"). Der Hinweis
    muss sie also zuruecknehmen, sonst bleibt die Umstellung wirkungslos."""
    from statik3d import fugen
    from statik3d.model import ContactPair
    m, kb = _modell()
    kb.ausgefuehrt = True
    m.contact_pairs.append(ContactPair(name="Stift", slave_nodes=[0], master_faces=[[0, 1, 2]],
                                       mu=0.0, haften=True))
    h = hinweise.erzeugen(m)
    reib = next(x for x in h if x["art"] == "reibung")
    erg = hinweise.anwenden(m, reib, [])
    check("die Fuge ist zurückgenommen: kein altes Kontaktpaar mit μ = 0, nicht mehr ausgeführt",
          erg["ok"] and not kb.ausgefuehrt and not [c for c in m.contact_pairs if c.name == "Stift"],
          f"ausgefuehrt={kb.ausgefuehrt} Paare={len(m.contact_pairs)}")
    check("… und der Text sagt, dass sie beim nächsten Vernetzen neu entsteht",
          "neu ausgeführt" in erg["text"], erg["text"][:90])
    b = fugen.kontaktfuge_ausfuehren(m, kb, [])
    check("… ohne das Zurücknehmen wäre hier Schluss gewesen („schon ausgeführt“)",
          b.get("grund") != "schon ausgeführt", str(b.get("grund"))[:60])


def main():
    for t in (test_erkennen_und_anwenden, test_sammellauf, test_reibung_an_ausgefuehrter_fuge):
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
