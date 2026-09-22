"""
Kopie des Modells (Model.copy): fuer Rueckgaengig, Situationen und Stellungen.

Die Kopie war ein JSON-Umweg - am Drehlager (2 Mio. Elemente) 63 s, in der
Oberflaeche vor jedem aendernden Befehl 105 s. Jetzt strukturell: Knoten als
Feld, Elemente flach mit eigenen Listen, der Rest ueber pickle. Geprueft wird,
dass die Kopie dem JSON-Umweg gleicht, unabhaengig vom Original ist und in
Sekunden statt Minuten entsteht.

Aufruf:  python -m tests.test_kopie
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from statik3d.model import Model, Material, Element  # noqa: E402
from statik3d import examples_lib  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:62s} {detail}")
    return ok


def _json_kopie(m: Model) -> Model:
    """Der fruehere Weg - der Massstab fuer die Gleichheit."""
    return Model.from_dict(json.loads(json.dumps(m.to_dict())))


def _gleich(a: Model, b: Model) -> bool:
    return json.dumps(a.to_dict(), sort_keys=True) == json.dumps(b.to_dict(), sort_keys=True)


def test_kopie_gleicht_json_umweg():
    for name in ("hall", "solid", "contact", "gate"):
        m = examples_lib.build_example(name)
        k = m.copy()
        check(f"{name}: die Kopie gleicht dem JSON-Umweg", _gleich(k, _json_kopie(m)),
              f"{len(m.elements)} Elemente, {len(m.load_cases)} Lastfaelle")
        check(f"{name}: Elemente und Knoten sind eigene Objekte",
              k.elements is not m.elements and k.nodes is not m.nodes
              and all(ke is not me and ke.nodes is not me.nodes for ke, me in zip(k.elements, m.elements)))


def test_kopie_ist_unabhaengig():
    m = examples_lib.build_example("solid")
    k = m.copy()
    k.elements[0].nodes[0] = 999
    k.elements[0].hinges.append(3)
    k.nodes[0, 0] = 123.0
    k.add_load_case("Neu", "Q")
    lc = next(iter(k.load_cases.values()))
    lc.description = "geaendert"
    check("Knoten und Elemente der Kopie aendern das Original nicht",
          m.elements[0].nodes[0] != 999 and 3 not in m.elements[0].hinges and m.nodes[0, 0] != 123.0)
    check("Lastfaelle der Kopie aendern das Original nicht",
          "Neu" not in m.load_cases
          and next(iter(m.load_cases.values())).description != "geaendert")


def test_element_kopie():
    e = Element("beam", [1, 2], "S", "IPE", hinges=[3], hinge_springs=[(4, 1e6)],
                exzentrizitaet=[[0.0, 0.1, 0.0], [0.0, 0.0, 0.0]])
    k = e.kopie()
    k.nodes[0] = 7
    k.hinges.append(5)
    k.exzentrizitaet[0][1] = 9.0
    check("Element.kopie: Listen sind eigene",
          e.nodes == [1, 2] and e.hinges == [3] and e.exzentrizitaet[0][1] == 0.1
          and k.sec == "IPE" and k.hinge_springs == [(4, 1e6)])


def test_kopie_in_sekunden():
    """300 000 Tetraeder: die Kopie in wenigen Sekunden. Am Drehlager mit
    2 Mio. Elementen: 11 s statt 63 s."""
    m = Model("gross")
    m.add_material(Material.steel("S235"))
    n = 300000
    m.add_nodes(np.random.default_rng(1).random((4 * 300, 3)))
    for i in range(n):
        b = (i % 300) * 4
        m.add_element("tet4", [b, b + 1, b + 2, b + 3], "S235")
    t = time.perf_counter()
    k = m.copy()
    dauer = time.perf_counter() - t
    check("300 000 Tetraeder kopiert", len(k.elements) == n and k.elements[5].nodes == m.elements[5].nodes)

    # Verglichen wird gegen den JSON-Umweg **im selben Lauf**, nicht gegen
    # eine feste Sekundenzahl. Bis zum 22.09.2026 stand hier `dauer < 5.0`:
    # das misst die Maschine mit. Der Lauf fiel durch, sobald nebenan
    # gerechnet wurde - und eine Pruefung, die von der Nachbarlast abhaengt,
    # fuehrt irgendwann jemanden in die Irre, der nicht weiss, dass nebenan
    # gerechnet wurde. Das Verhaeltnis ist lastunabhaengig: beide Messungen
    # leiden gleich.
    t = time.perf_counter()
    _j = Model.from_dict(m.to_dict())
    umweg = time.perf_counter() - t
    check("die Kopie geht um ein Vielfaches schneller als der JSON-Umweg",
          umweg > 2.0 * dauer,
          f"{dauer:.2f} s gegen {umweg:.2f} s, Faktor {umweg / max(dauer, 1e-9):.1f}")


def test_ganzzahlige_schluessel_ueberleben_den_umlauf():
    """Wörterbücher mit Knotennummern als Schlüssel dürfen beim Speichern
    nicht zu Zeichenketten werden.

    JSON kennt nur Zeichenketten als Schlüssel. `ContactPair.knotenflaechen`
    ist {Knotennummer: Einflussfläche}, mit **ganzzahligen** Schlüsseln gebaut
    (`fugen._passungsdaten`) und mit ganzzahligen gelesen (`contact.py`,
    Lochleibungsgrenze). Ohne Rückwandlung fand die Abfrage nach dem Öffnen
    nichts und gab 0,0 zurück - und **0,0 heißt dort „keine Grenze"**: die
    Passung trug unbegrenzt, statt bei der Grenzpressung zu fließen.

    Gemessen am 22.09.2026: 2,100 kN vor dem Umlauf, **0,000 kN danach** -
    still, ohne Meldung, in jedem gespeicherten Modell mit Passung. Dasselbe
    Muster ist beim Lagerverhalten (`behaviour`) längst behoben; hier war es
    vergessen.

    Geprüft wird die **Wirkung** (die Grenzkraft), nicht der Schlüsseltyp -
    ein Typ ist leicht zu prüfen und sagt nichts darüber, ob jemand ihn liest.
    """
    from statik3d.model import ContactPair
    m = Model("passung")
    cp = ContactPair(name="Fuge")
    cp.knotenflaechen = {12: 4.2e-6, 13: 5.1e-6}
    cp.grenzpressung = 500e6
    m.contact_pairs.append(cp)

    def grenze(modell, knoten=12):
        c = modell.contact_pairs[0]
        a = float((getattr(c, "knotenflaechen", None) or {}).get(int(knoten), 0.0) or 0.0)
        return float(getattr(c, "grenzpressung", 0.0) or 0.0) * a

    vorher = grenze(m)
    check("der Prüfkörper hat eine Lochleibungsgrenze", vorher > 0,
          f"{vorher / 1e3:.3f} kN")
    m2 = Model.from_dict(json.loads(json.dumps(m.to_dict())))
    nachher = grenze(m2)
    check("sie überlebt Speichern und Laden",
          abs(nachher - vorher) <= 1e-9 * vorher,
          f"{nachher / 1e3:.3f} kN gegen {vorher / 1e3:.3f} kN")
    check("und die Schlüssel sind wieder ganzzahlig",
          all(isinstance(k, int) for k in m2.contact_pairs[0].knotenflaechen),
          str({k: type(k).__name__ for k in m2.contact_pairs[0].knotenflaechen}))
    # Auch über Model.copy, der denselben Weg geht
    check("dasselbe über Model.copy", abs(grenze(m.copy()) - vorher) <= 1e-9 * vorher,
          f"{grenze(m.copy()) / 1e3:.3f} kN")


def main():
    for t in (test_kopie_gleicht_json_umweg, test_kopie_ist_unabhaengig, test_element_kopie,
              test_kopie_in_sekunden,
              test_ganzzahlige_schluessel_ueberleben_den_umlauf):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    failed = [n for n, ok in RESULTS if not ok]
    if failed:
        print("FEHLGESCHLAGEN:", failed)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
