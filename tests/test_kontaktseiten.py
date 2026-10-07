"""
Kontaktseiten an quadratischen Volumen binden (Paket Q1, 08.10.2026).

Bauplan PLAN-KONTAKT-QUADRATISCH-2026-10-07, Entscheidung des Anwenders:
die Seitenmitten jeder Kontaktseite eines tet10, hex20 oder pent15 werden
exakt an ihre Kantenecken gebunden (u_m = (u_a + u_b)/2, dieselbe Bindung B5
wie am Uebergang tet4/tet10, assemble.mittelknoten_bindungen). Kontakt,
Mortar, Reibung, Fugen und Flaechenlager rechnen auf den Ecken weiter;
quadratische Schalen an Kontakt oder Flaechenlager bleiben gesperrt.

Geprueft wird hier:

* welche Mitten gebunden werden (Flaechenlager, Kontaktpaar; ferne
  Master-Seiten nicht) und dass der Schalter fuer die Ruecknahmeprobe sie
  abschaltet;
* dass gebundene Mitten neben der Sehne auf die Kantenmitte kommen, mit
  Protokollzeile;
* dass eine Mitte, die selbst ein Lager traegt oder ueber eine getrennte
  Fuge beiden Seiten gemeinsam blieb, laut abbricht statt still falsch zu
  rechnen - und dass starre Lager an Mitte und Ecken erlaubt bleiben;
* dass quadratische Schalen weiter sperren (Rechnung und Elementstufe);
* die Kontaktfaelle K3 und K6 der Pruefmatrix in Mittel (tet10, hex20):
  gruen, ohne Bindung rot (gemessen 07.10.2026 +904 bzw. +350 N/mm2).

Aufruf:  python -m tests.test_kontaktseiten
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import assemble as asm, fugen, solver          # noqa: E402
from statik3d.model import DofBehaviour, Material, Model, ShellProp   # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FEHLER'} {name:70s} {detail}")
    return bool(ok)


def _wuerfel(ordnung=2):
    from tests.test_fugen import _wuerfel as w
    return w(0.5, ordnung=ordnung)


def _knoten_z(m, z):
    im = np.zeros(m.nn, bool)
    im[[int(x) for e in m.elements for x in e.nodes]] = True
    return [int(i) for i in np.flatnonzero(im & (np.abs(m.nodes[:, 2] - z) < 1e-9))]


def _mitten(m):
    """Alle Kantenmitten der tet10 im Modell."""
    return {int(n) for e in m.elements if e.typ == "tet10" for n in e.nodes[4:]}


def _flaechenlager(m, name="Starr"):
    ss = m.add_surface_support(name=name, ux=dict(typ="rigid"), uy=dict(typ="rigid"), uz=dict(typ="rigid"))
    ss.flaechen = ["Boden"]
    return ss


def _druck(m, p=1.0e6):
    lc = m.add_load_case("LF1")
    lc.gravity = [0, 0, 0]
    m.add_geometrielast("Deckel", p, "flaeche", case="LF1")
    m.lasten_verteilen()
    return solver.solve_static(m, case="LF1", workers=1)


def _ohne_bindung(f):
    alt = asm.KONTAKTSEITEN_BINDEN
    asm.KONTAKTSEITEN_BINDEN = False
    try:
        return f()
    finally:
        asm.KONTAKTSEITEN_BINDEN = alt


# --------------------------------------------------------------------------
def test_welche_mitten():
    """Am tet10-Wuerfel mit starrem Flaechenlager am Boden: gebunden sind
    genau die Mitten der Bodenseiten, je an die Ecken ihrer Kante."""
    m = _wuerfel()
    check("ohne Lager und Kontakt: an reinem tet10 nichts gebunden", asm.mittelknoten_bindungen(m) == [])
    _flaechenlager(m)
    bind = asm.mittelknoten_bindungen(m)
    boden = set(_knoten_z(m, 0.0))
    soll = boden & _mitten(m)
    gebunden = {mm for mm, _a, _b in bind}
    check("Flächenlager am Boden: gebunden sind genau die Seitenmitten am Boden",
          gebunden == soll and len(soll) > 0, f"{len(gebunden)} gebunden, {len(soll)} Bodenmitten")
    X = m.nodes
    ok = all(a in boden and b in boden and np.allclose(X[mm], 0.5 * (X[a] + X[b])) for mm, a, b in bind)
    check("… je an die beiden Ecken ihrer Kante (Mitte = Kantenmitte)", ok)
    check("Rücknahmeprobe: mit KONTAKTSEITEN_BINDEN = False nichts gebunden",
          _ohne_bindung(lambda: asm.mittelknoten_bindungen(m)) == [])


def test_master_nur_nah():
    """Ein Kontaktpaar mit ganzen Master-Elementen bindet nur die Master-Seiten
    in Reichweite der Slave-Knoten - nicht die ganze Oberflaeche des Koerpers."""
    from tests.test_fugen import zwei_bloecke, _flaechenknoten
    m = zwei_bloecke("eigene", ordnung=2)
    unten = sorted(i for i, e in enumerate(m.elements) if str(e.group) == "Unten")
    in_unten = {int(n) for i in unten for n in m.elements[i].nodes}
    slave = [n for n in _flaechenknoten(m, 1.0) if n not in in_unten]
    m.add_contact_pair("Paar", slave, master_elements=unten)
    gebunden = {mm for mm, _a, _b in asm.mittelknoten_bindungen(m)}
    fuge = {n for n in gebunden if abs(m.nodes[n, 2] - 1.0) < 1e-9}
    boden = {n for n in gebunden if abs(m.nodes[n, 2]) < 1e-9}
    check("Kontaktpaar: die Mitten der Fugenseiten beider Blöcke sind gebunden",
          len(fuge) > 0 and fuge >= ({n for n in slave if n in _mitten(m)}), f"{len(fuge)} an z = 1")
    check("… die Bodenseiten des Master-Blocks (1 m entfernt) nicht", not boden, f"{len(boden)} am Boden")


def test_auf_die_sehne():
    """Eine gebundene Mitte neben der Sehne kommt auf die Kantenmitte; die
    Zeile im Protokoll nennt Zahl und groessten Abstand. Ein zweiter Aufruf
    aendert nichts."""
    m = _wuerfel()
    _flaechenlager(m)
    mm, a, b = asm.mittelknoten_bindungen(m)[0]
    m.nodes[mm] = 0.5 * (m.nodes[a] + m.nodes[b]) + np.array([0.0, 0.0, -1.0e-3])
    log = []
    n, versetzt, gross = asm.mittelknoten_auf_sehne(m, log)
    check("eine Mitte 1 mm neben der Sehne: versetzt, Abstand 1 mm",
          versetzt == 1 and abs(gross - 1e-3) < 1e-12 and n > 1, f"{n} gebunden, {versetzt} versetzt, {gross}")
    check("… und liegt jetzt auf der Kantenmitte", np.allclose(m.nodes[mm], 0.5 * (m.nodes[a] + m.nodes[b])))
    text = " ".join(str(x) for x in log)
    check("… das Protokoll nennt gebundene, versetzte Mitten und den Abstand",
          f"{n} gebunden" in text and "1 davon auf die Kantenmitte gesetzt" in text and "1,000 mm" in text.replace(".", ","),
          text[:160])
    check("zweiter Aufruf: nichts mehr zu versetzen", asm.mittelknoten_auf_sehne(m)[1] == 0)
    # Vor der Rechnung geschieht es ohnehin (assemble.stiffness)
    m.nodes[mm] = m.nodes[mm] + np.array([0.0, 0.0, 2.0e-3])
    r = _druck(m)
    check("Rechnung: die Mitte steht danach auf der Sehne, Setzung endlich",
          np.allclose(m.nodes[mm], 0.5 * (m.nodes[a] + m.nodes[b])) and np.isfinite(r.u).all())


def test_belegte_mitte():
    """Eine Mitte, die selbst eine Feder traegt, wuerde ihre Feder verlieren:
    laut abbrechen, mit Namen. Starr an Mitte und beiden Ecken (alle
    Bodenknoten fest) ist dagegen dasselbe wie gebunden - erlaubt."""
    m = _wuerfel()
    _flaechenlager(m)
    mm, _a, _b = asm.mittelknoten_bindungen(m)[0]
    m.fix(mm, [2], stiffness=[1.0e9])
    m._mittelknoten = None
    try:
        _druck(m)
        text = ""
    except fugen.QuadratischeSeiten as ex:
        text = str(ex)
    check("Feder an einer gebundenen Mitte: die Rechnung bricht laut ab",
          "Knotenlager" in text and f"Knoten {mm}" in text and "Entwurf" in text, text[:160])
    m2 = _wuerfel()
    _flaechenlager(m2)
    for i in _knoten_z(m2, 0.0):
        m2.fix(i, [0, 1, 2])
    try:
        r = _druck(m2)
        ok, text = np.isfinite(r.u).all(), ""
    except fugen.QuadratischeSeiten as ex:
        ok, text = False, str(ex)
    check("starre Knotenlager an Mitte und Ecken zusätzlich zum Flächenlager: erlaubt", ok, text[:120])


def test_gemeinsame_mitte_ueber_fuge():
    """Bleiben die Mitten einer getrennten Fuge beiden Seiten gemeinsam, waere
    eine Mitte an zwei Eckpaare zu binden: die Rechnung bricht laut ab und
    nennt die Fuge. Seit Q2 trennt die Fuge die Mitten mit; nachgestellt wird
    der Stand davor, indem die getrennten Mitten danach wieder
    zusammengelegt werden (die geloeste Seite benutzt die alten)."""
    from tests.test_fugen import zwei_bloecke, kontaktbedingung, rechnen
    m = zwei_bloecke("gemeinsam", ordnung=2)
    kb = kontaktbedingung(m, "gemeinsam")
    b = fugen.kontaktfuge_ausfuehren(m, kb, [])
    mitten = {int(n) for e in m.elements if e.typ == "tet10" for n in e.nodes[4:]}
    zurueck = {int(n): int(k) for k, n in m.getrennte_knoten.get("Fuge", []) if int(k) in mitten}
    for e in m.elements:
        e.nodes = [zurueck.get(int(x), int(x)) for x in e.nodes]
    check("Q2 hat Ecken und Mitten getrennt; die Mitten sind für die Probe wieder gemeinsam",
          b.get("mitten", 0) > 0 and len(zurueck) == b.get("mitten"), f"{b.get('mitten')} Mitten, {len(zurueck)} zurück")
    try:
        rechnen(m, -1.0e6, federn=1.0e11)
        text = ""
    except fugen.QuadratischeSeiten as ex:
        text = str(ex)
    check("gemeinsame Mitten über einer getrennten Fuge: laut abbrechen, mit der Fuge im Text",
          "zwei Seiten mit verschiedenen Ecken" in text and "(Fuge)" in text, text[:200])


def test_schalen_gesperrt():
    """Quadratische Schalen an Kontakt oder Flaechenlager sperren weiter - in
    der Rechnung (fugen.QuadratischeSeiten) und in der Elementstufe."""
    from statik3d import elementstufe as es
    m = Model("Schale")
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("t", 0.01))
    P = [(0, 0), (1, 0), (1, 1), (0, 1), (0.5, 0), (1, 0.5), (0.5, 1), (0, 0.5)]
    ids = [int(m.add_node(x, y, 0.0)) for x, y in P]
    m.add_element("shell8", ids, "S235", "t")
    try:
        fugen.quadratische_seiten_sperren(m, ids[:4], "Flächenlager Platte")
        text = ""
    except fugen.QuadratischeSeiten as ex:
        text = str(ex)
    check("Flächenlager an shell8: die Rechnung bricht laut ab, mit Namen und Abhilfe",
          "Flächenlager Platte" in text and "shell8" in text and "Entwurf" in text, text[:160])
    # Elementstufe: eine Flaeche mit Dicke (Schale) traegt ein Flaechenlager
    from tests.test_elementstufe import _Bauer
    g = Model("Platte")
    g.add_material(Material.steel("S235"))
    g.add_shell_prop(ShellProp("t", 0.01))
    g.add_nodes(np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0.]]))
    b = _Bauer(g)
    R = [b.linie(i, (i + 1) % 4) for i in range(4)]
    g.add_flaeche("Platte", R, material="S235", dicke="t")
    ss = g.add_surface_support(name="Bettung", uz=dict(typ="spring", stiffness=1e8))
    ss.flaechen = ["Platte"]
    gr = es.quadratisch_gesperrt(g)
    check("Elementstufe: Flächenlager an einer Schale sperrt Mittel und Fein, mit Namen",
          gr == ["Flächenlager Bettung (an Schalen)"] and not es.frei(g, "mittel") and es.frei(g, "entwurf"),
          str(gr))


def test_pruefmatrix_k3_k6():
    """K3 (Presspassung, Kontaktpaar mit Uebermass) und K6 (ungleiche Netze,
    Mortar) der Pruefmatrix in Mittel: gruen mit tet10 und hex20; ohne
    Bindung rot (Bauplan Anhang A: +904 / +671 bzw. +350 / +314 N/mm2)."""
    from tests import pruefmatrix as pm
    for fall in (pm.UebermassFuge(), pm.UngleicheNetze()):
        for familie, typ in (("tet", "tet10"), ("hex", "hex20")):
            z = pm.zelle(fall, "Mittel", familie, typ, 2, 1.0)
            check(f"{fall.kurz} Mittel {typ}: grün", z["ergebnis"] == "grün", pm.zeile(z)[:170])
            z0 = _ohne_bindung(lambda: pm.zelle(fall, "Mittel", familie, typ, 2, 1.0))
            sv = next((x["wert"] for x in z0["metriken"] if x["name"] == "σ_v"), 0.0)
            check(f"{fall.kurz} Mittel {typ} ohne Bindung: rot, σ_v über 100 N/mm² daneben",
                  z0["ergebnis"] == "rot" and abs(sv) > 100.0, pm.zeile(z0)[:170])


def main():
    import faulthandler
    faulthandler.dump_traceback_later(1200, exit=True)
    for t in (test_welche_mitten, test_master_nur_nah, test_auf_die_sehne, test_belegte_mitte,
              test_gemeinsame_mitte_ueber_fuge, test_schalen_gesperrt, test_pruefmatrix_k3_k6):
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
