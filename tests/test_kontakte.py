"""Beruehrungen zwischen Volumen und die Kontakte, die von selbst entstehen.

Wunsch vom 15.09.2026: „automatisch Kontakte anlegen, wenn zwei Volumen sich
berühren; Standard ist Druck und Zug und Schub starr", der Name traegt die
Wirkung, eine Farbe je Wirkung. Geprueft wird die Geometrie (gemeinsame
Flaeche, aufliegende Flaechen, Spalt, nur eine Kante, kleine Flaeche auf
grosser), das Anlegen und Nachfuehren, Name und Farbe.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import kontakte                                  # noqa: E402
from statik3d.model import DofBehaviour, Kontaktbedingung, Material, Model   # noqa: E402
from tests.test_fugen import Bauer, zwei_bloecke, kontaktbedingung as _fuge   # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FEHLER'} {name:64s} {detail}")
    return bool(ok)


def _wuerfel(m: Model, b: Bauer, name: str, ursprung, groesse: float = 1.0):
    """Ein Wuerfel mit **eigenen** Knoten und Linien - nichts ist mit einem
    anderen Wuerfel geteilt, die Beruehrung ist rein geometrisch."""
    E = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                  [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], float) * groesse
    basis = m.nn
    m.add_nodes(np.asarray(ursprung, float) + E)
    R0 = [b.linie(basis + i, basis + (i + 1) % 4) for i in range(4)]
    R1 = [b.linie(basis + 4 + i, basis + 4 + (i + 1) % 4) for i in range(4)]
    V = [b.linie(basis + i, basis + 4 + i) for i in range(4)]
    m.add_flaeche(f"{name}B", R0, material="S235")
    m.add_flaeche(f"{name}D", R1, material="S235")
    for i in range(4):
        m.add_flaeche(f"{name}M{i}", [R0[i], V[(i + 1) % 4], R1[i], V[i]], material="S235")
    return m.add_koerper(name, [f"{name}B", f"{name}D"] + [f"{name}M{i}" for i in range(4)],
                         material="S235")


def _zwei_wuerfel(versatz=(0.0, 0.0, 1.0), groesse_b: float = 1.0) -> Model:
    m = Model()
    m.add_material(Material.steel("S235"))
    b = Bauer(m)
    _wuerfel(m, b, "A", (0.0, 0.0, 0.0))
    _wuerfel(m, b, "B", versatz, groesse_b)
    return m


def test_gemeinsame_flaeche():
    m = zwei_bloecke("gemeinsam")
    ber = kontakte.beruehrungen(m)
    check("ein Paar über die gemeinsame Fläche, keine aufliegenden",
          len(ber) == 1 and ber[0].gemeinsam == ["Fuge"] and not ber[0].flaechen_a and not ber[0].flaechen_b
          and {ber[0].a, ber[0].b} == {"Oben", "Unten"}, str(ber))
    log = []
    erg = kontakte.kontakte_nachfuehren(m, log)
    kb = m.kontaktbedingungen.get("Oben–Unten starr")
    check("angelegt: „Oben–Unten starr“ - Verbund, automatisch, Fläche Fuge, A Oben, B Unten, eine Naht",
          erg["neu"] == ["Oben–Unten starr"] and kb is not None and kb.automatisch and kb.standard == "Verbund"
          and kb.flaechennamen == ["Fuge"] and not kb.gegenflaechen and kb.koerpernamen == ["Oben"]
          and kb.gegenkoerper == ["Unten"] and kontakte.ist_naht(kb), str((erg, sorted(m.kontaktbedingungen))))
    check("das Protokoll nennt das Paar und den Weg zur Maske",
          any("Oben berührt Unten" in z and "Maske" in z for z in log), str(log[:1]))
    erg2 = kontakte.kontakte_nachfuehren(m, [])
    check("ein zweiter Lauf legt nichts an und entfernt nichts", not erg2["neu"] and not erg2["entfernt"], str(erg2))
    del m.kontaktbedingungen["Oben–Unten starr"]
    m.kontakt_ausnahmen.append(["Oben", "Unten"])
    check("gelöscht mit Ausnahme: kommt nicht wieder", not kontakte.kontakte_nachfuehren(m, [])["neu"])
    m.kontakt_ausnahmen.clear()
    check("ohne Ausnahme kommt er wieder",
          kontakte.kontakte_nachfuehren(m, [])["neu"] == ["Oben–Unten starr"])
    d = Model.from_dict(m.to_dict())
    check("„automatisch“ und die Ausnahmen überleben Speichern und Laden",
          d.kontaktbedingungen["Oben–Unten starr"].automatisch and d.kontakt_ausnahmen == [],
          str(d.kontakt_ausnahmen))
    m.kontakt_ausnahmen.append(["Oben", "Unten"])
    check("… die Ausnahme auch", Model.from_dict(m.to_dict()).kontakt_ausnahmen == [["Oben", "Unten"]])


def test_eigene_flaechen():
    m = zwei_bloecke("eigene")
    ber = kontakte.beruehrungen(m)
    check("ein Paar über aufeinanderliegende Flächen FugeO / FugeU (gleiche Größe: A nach Namen)",
          len(ber) == 1 and not ber[0].gemeinsam and ber[0].a == "Oben" and ber[0].b == "Unten"
          and ber[0].flaechen_a == ["FugeO"] and ber[0].flaechen_b == ["FugeU"], str(ber))
    kontakte.kontakte_nachfuehren(m, [])
    kb = m.kontaktbedingungen["Oben–Unten starr"]
    check("Kontaktfläche FugeO, Gegenfläche FugeU",
          kb.flaechennamen == ["FugeO"] and kb.gegenflaechen == ["FugeU"], str((kb.flaechennamen, kb.gegenflaechen)))
    m2 = zwei_bloecke("eigene")
    _fuge(m2, "eigene")
    check("eine vorhandene Bedingung an der Fuge: nichts Neues", not kontakte.kontakte_nachfuehren(m2, [])["neu"])
    m3 = zwei_bloecke("eigene")
    m3.add_kontaktbedingung("X", koerpernamen=["Unten"], gegenkoerper=["Oben"])
    check("… auch wenn sie nur die beiden Körper nennt", not kontakte.kontakte_nachfuehren(m3, [])["neu"])


def test_spalt_kante_und_kleine_flaeche():
    m = _zwei_wuerfel((0.0, 0.0, 1.0))
    tol = kontakte.toleranz(m)
    check(f"Toleranz 1e-5 der Modellgröße: {tol * 1e6:.1f} µm (Diagonale 2,45 m)", 20e-6 < tol < 30e-6)
    ber = kontakte.beruehrungen(m)
    check("aufeinander (Spalt 0): Deckel von A auf Boden von B",
          len(ber) == 1 and ber[0].a == "A" and ber[0].flaechen_a == ["AD"] and ber[0].flaechen_b == ["BB"]
          and not ber[0].gemeinsam, str(ber))
    m = _zwei_wuerfel((0.0, 0.0, 1.0 + 0.5 * tol))
    check("Spalt halbe Toleranz: berührt", len(kontakte.beruehrungen(m)) == 1)
    m = _zwei_wuerfel((0.0, 0.0, 1.0 + 1e-3))
    check("Spalt 1 mm: keine Berührung", not kontakte.beruehrungen(m))
    m = _zwei_wuerfel((1.0, 0.0, 1.0))
    check("nur eine Kante gemeinsam (Würfel diagonal versetzt): keine Berührung", not kontakte.beruehrungen(m))
    m = _zwei_wuerfel((1.0 + 1e-3, 0.0, 0.0))
    check("nebeneinander mit 1 mm Luft: keine Berührung", not kontakte.beruehrungen(m))
    m = _zwei_wuerfel((0.3, 0.3, 1.0), groesse_b=0.4)
    ber = kontakte.beruehrungen(m)
    check("kleiner Würfel mitten auf der großen Fläche: der kleine ist Körper A, sein Boden liegt auf dem Deckel",
          len(ber) == 1 and ber[0].a == "B" and ber[0].flaechen_a == ["BB"] and ber[0].flaechen_b == ["AD"], str(ber))
    m = _zwei_wuerfel((0.5, 0.0, 1.0))
    check("halb überlappend (50 %): berührt", len(kontakte.beruehrungen(m)) == 1)
    m = _zwei_wuerfel((0.9, 0.0, 1.0))
    check("nur 10 % überlappend: keine Berührung (Grenze 25 % der Fläche)", not kontakte.beruehrungen(m))


def test_wirkung_name_farbe():
    erwartet = {"Verbund": "starr", "Ohne Trennung": "Zug/Druck", "Reibungsfrei": "nur Druck",
                "Reibungsbehaftet": "Druck, Reibung", "Rau": "Druck/Schub"}
    for std, text in erwartet.items():
        kb = Kontaktbedingung("K").standard_anwenden(std)
        check(f"{std} → „{text}“ mit eigener Farbe",
              kontakte.wirkungstext(kb) == text and kontakte.wirkungsfarbe(kb) == kontakte.WIRKUNGSFARBEN[text],
              kontakte.wirkungstext(kb))
    kb = Kontaktbedingung("K", behaviour={2: DofBehaviour("spring", 1e6), 0: DofBehaviour("free"),
                                          1: DofBehaviour("free")})
    check("eine Feder heißt „Feder“", kontakte.wirkungstext(kb) == "Feder", kontakte.wirkungstext(kb))
    kb = Kontaktbedingung("K", behaviour={2: DofBehaviour("rigid"), 0: DofBehaviour("free", mu=0.3),
                                          1: DofBehaviour("free", mu=0.3)})
    check("kein Abheben mit Reibung: „Zug/Druck, Reibung“", kontakte.wirkungstext(kb) == "Zug/Druck, Reibung",
          kontakte.wirkungstext(kb))
    check("jede Wirkung hat ihre eigene Farbe",
          len(set(kontakte.WIRKUNGSFARBEN.values())) == len(kontakte.WIRKUNGSFARBEN))
    check("nur „starr“ ist eine Naht",
          kontakte.ist_naht(Kontaktbedingung("K").standard_anwenden("Verbund"))
          and not any(kontakte.ist_naht(Kontaktbedingung("K").standard_anwenden(s))
                      for s in ("Ohne Trennung", "Reibungsfrei", "Reibungsbehaftet", "Rau")))
    m = zwei_bloecke("gemeinsam")
    kontakte.kontakte_nachfuehren(m, [])
    kb = m.kontaktbedingungen["Oben–Unten starr"]
    kb.standard_anwenden("Reibungsfrei")
    check("der Name folgt der Wirkung: „Oben–Unten nur Druck“",
          kontakte.name_fuer(m, kb, ausser=kb.name) == "Oben–Unten nur Druck", kontakte.name_fuer(m, kb, ausser=kb.name))
    m.add_kontaktbedingung("Oben–Unten nur Druck")
    check("… und bleibt eindeutig", kontakte.name_fuer(m, kb, ausser=kb.name) == "Oben–Unten nur Druck (2)",
          kontakte.name_fuer(m, kb, ausser=kb.name))


def test_verschweisst():
    """Starr an gemeinsamen Flaechen ist verschweisst: ohne Ausfuehrung, nie „zu
    steif" - am Drehlager standen sonst 22 automatische Kontakte mit ⚠, und
    ihre Ausfuehrung kostete 65 s (15.09.2026)."""
    m = zwei_bloecke("gemeinsam")
    kontakte.kontakte_nachfuehren(m, [])
    kb = m.kontaktbedingungen["Oben–Unten starr"]
    check("gemeinsame Fläche, starr: verschweißt", kontakte.ist_verschweisst(m, kb))
    check("… mit Netz und ohne Ausführung nicht „zu steif“, Zustand und Tabelle sagen verschweißt",
          not kb.ausgefuehrt and m.elements and not kb.zu_steif(m) and "verschweißt" in kb.zustand(m)
          and "verschweißt" in kb.art_der_trennung(m), f"{kb.zustand(m)} / {kb.art_der_trennung(m)}")
    kb.standard_anwenden("Reibungsfrei")
    check("nur Druck an der gemeinsamen Fläche: keine Naht, mit Netz zu steif bis zur Ausführung",
          not kontakte.ist_verschweisst(m, kb) and kb.zu_steif(m))
    m2 = zwei_bloecke("eigene")
    kontakte.kontakte_nachfuehren(m2, [])
    kb2 = m2.kontaktbedingungen["Oben–Unten starr"]
    check("eigene, aufeinanderliegende Flächen: starr, aber nicht verschweißt (braucht das Kontaktpaar)",
          kontakte.ist_naht(kb2) and not kontakte.ist_verschweisst(m2, kb2) and kb2.zu_steif(m2))


def test_veraltete_verschwinden():
    m = _zwei_wuerfel((0.0, 0.0, 1.0))
    erg = kontakte.kontakte_nachfuehren(m, [])
    check("A–B starr angelegt", erg["neu"] == ["A–B starr"], str(erg))
    oben = list(range(8, 16))
    m.nodes[oben, 2] += 0.1
    log = []
    erg = kontakte.kontakte_nachfuehren(m, log)
    check("B weggeschoben: der automatische Kontakt verschwindet (noch nicht im Netz ausgeführt)",
          erg["entfernt"] == ["A–B starr"] and not m.kontaktbedingungen and any("nicht mehr" in z for z in log),
          str((erg, log[:1])))
    m.nodes[oben, 2] -= 0.1
    kontakte.kontakte_nachfuehren(m, [])
    m.kontaktbedingungen["A–B starr"].ausgefuehrt = True
    m.nodes[oben, 2] += 0.1
    erg = kontakte.kontakte_nachfuehren(m, [])
    check("ein im Netz ausgeführter bleibt", not erg["entfernt"] and "A–B starr" in m.kontaktbedingungen, str(erg))
    m = _zwei_wuerfel((0.0, 0.0, 1.0))
    kontakte.kontakte_nachfuehren(m, [])
    m.koerper_loeschen("B")
    erg = kontakte.kontakte_nachfuehren(m, [])
    check("Körper gelöscht: der Kontakt dazu auch", erg["entfernt"] == ["A–B starr"], str(erg))


def main():
    for t in (test_gemeinsame_flaeche, test_eigene_flaechen, test_spalt_kante_und_kleine_flaeche,
              test_wirkung_name_farbe, test_verschweisst, test_veraltete_verschwinden):
        print(f"\n--- {t.__name__} ---")
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
