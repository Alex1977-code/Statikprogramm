"""
Die Geometriekette: aus Knoten Linien, aus Linien Flaechen, aus Flaechen
Volumenkoerper - und das Vernetzen dieser Objekte.

Geprueft wird gegen Handrechnungen: die Summe der Elementflaechen muss die
Flaeche des Randpolygons ergeben, das Volumen der Hexaeder das Volumen des
Koerpers, und die Summe der Auflagerkraefte die aufgebrachte Last.

Aufruf:  python -m tests.test_geometrie_kette
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from statik3d import mesher, solver                       # noqa: E402
from statik3d.model import (Model, Material, ShellProp,    # noqa: E402
                            Berichtseintrag)
from statik3d.elements import solid as SO                  # noqa: E402
from statik3d.gui.viewport import polygon_flaeche          # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FAIL'} {name:58s} {detail}")
    return ok


def close(name, got, want, tol, unit=""):
    err = abs(got - want)
    rel = err / abs(want) if want else err
    return check(name, err <= tol * max(1.0, abs(want)),
                 f"{got:.6g}{unit} / {want:.6g}{unit}  Abw. {rel * 100:.4f} %")


def _rechteck(lx=4.0, ly=2.0) -> Model:
    m = Model("Kette")
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("d12", 0.012))
    m.add_nodes(np.array([[0, 0, 0], [lx, 0, 0], [lx, ly, 0], [0, ly, 0.]]))
    for i, (a, b) in enumerate([(0, 1), (1, 2), (2, 3), (3, 0)]):
        m.add_line(f"L{i + 1}", [a, b])
    return m


def _quader(lx=2.0, ly=1.0, lz=1.0) -> Model:
    m = Model("Quader")
    m.add_material(Material.steel("S355"))
    m.add_nodes(np.array([[0, 0, 0], [lx, 0, 0], [lx, ly, 0], [0, ly, 0],
                          [0, 0, lz], [lx, 0, lz], [lx, ly, lz], [0, ly, lz]], float))
    kanten = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
              (0, 4), (1, 5), (2, 6), (3, 7)]
    for i, (a, b) in enumerate(kanten):
        m.add_line(f"K{i + 1}", [a, b])
    seiten = {"Boden": ["K1", "K2", "K3", "K4"], "Deckel": ["K5", "K6", "K7", "K8"],
              "S1": ["K1", "K10", "K5", "K9"], "S2": ["K2", "K11", "K6", "K10"],
              "S3": ["K3", "K12", "K7", "K11"], "S4": ["K4", "K9", "K8", "K12"]}
    for n, ls in seiten.items():
        m.add_flaeche(n, ls, material="S355")
    return m


# --------------------------------------------------------------------------
# 1) Aus Linien wird eine Flaeche
# --------------------------------------------------------------------------
def test_flaeche_aus_linien():
    m = _rechteck()
    f = m.add_flaeche("F1", ["L3", "L1", "L4", "L2"], dicke="d12",
                      material="S235", teilung=[8, 4])
    check("Flaeche angelegt", "F1" in m.flaechen)
    check("Rand schliesst trotz beliebiger Linienreihenfolge",
          sorted(f.randknoten(m)) == [0, 1, 2, 3], str(f.randknoten(m)))
    check("noch nicht vernetzt", not f.elemente and "nicht vernetzt" in f.bezug(),
          f.bezug())
    try:
        m.add_flaeche("F2", ["L1", "L3"])
        check("offener Rand wird abgewiesen", False)
    except ValueError as ex:
        check("offener Rand wird abgewiesen", "geschlossen" in str(ex), str(ex)[:50])
    try:
        m.add_flaeche("F3", ["L1", "L2", "L3", "Gibtsnicht"])
        check("unbekannte Linie wird abgewiesen", False)
    except KeyError as ex:
        check("unbekannte Linie wird abgewiesen", "Gibtsnicht" in str(ex), str(ex)[:50])

    log = []
    els = mesher.mesh_flaeche(m, f, log)
    check("32 Viereckelemente (8 x 4)", len(els) == 32, f"{len(els)}")
    check("alle Elemente sind Vierecke",
          all(m.elements[i].typ == "shell4" for i in els))
    check("Elemente tragen Dicke und Werkstoff",
          m.elements[els[0]].sec == "d12" and m.elements[els[0]].mat == "S235")
    check("Elemente sind der Flaeche zugeordnet",
          m.elements[els[0]].group == "F1", m.elements[els[0]].group)
    A = sum(polygon_flaeche(m.nodes[[int(n) for n in m.elements[i].nodes]]) for i in els)
    close("Summe der Elementflaechen", A, 8.0, 1e-12, " m^2")
    check("Knotenzahl des abgebildeten Netzes", m.nn == 9 * 5, f"{m.nn}")
    check("Protokoll nennt die Teilung", any("8 x 4" in x for x in log),
          log[0] if log else "-")

    # Randknoten liegen auf dem Rand
    rand = [n for n in range(m.nn) if abs(m.nodes[n][1]) < 1e-12]
    close("Rand y = 0 hat 9 Knoten", len(rand), 9, 0)

    # Rechnung: Kragplatte unter Flaechenlast
    for n in range(m.nn):
        if abs(m.nodes[n][0]) < 1e-12:
            m.support(n, [0, 1, 2, 3, 4, 5])
    m.load_cases["LF1"].gravity = [0.0, 0.0, 0.0]
    for i in els:
        m.load_face(i, -1000.0, case="LF1")
    r = solver.solve_static(m, case="LF1")
    close("Summe der Auflagerkraefte = q * A", float(r.reactions[:, 2].sum()),
          1000.0 * 8.0, 1e-9, " N")
    w = float(np.abs(r.u.reshape(-1, 6)[:, 2]).max())
    # Der Kragplattenstreifen liegt zwischen der Plattenloesung q L^4/(8 D) und
    # dem Balkenstreifen q L^4/(8 E I): die freien Laengsraender lassen sich
    # querkruemmen, die Platte ist also weicher als D, aber steifer als der Balken.
    E, nu, t, L, q = 210e9, 0.3, 0.012, 4.0, 1000.0
    D = E * t ** 3 / (12 * (1 - nu ** 2))
    w_platte = q * L ** 4 / (8 * D)
    w_balken = w_platte / (1 - nu ** 2)
    check("Durchbiegung liegt zwischen Platten- und Balkenstreifen",
          w_platte <= w <= w_balken * 1.02,
          f"{w * 1e3:.1f} mm in [{w_platte * 1e3:.1f}, {w_balken * 1e3:.1f}] mm")


# --------------------------------------------------------------------------
# 2) Aus Flaechen wird ein Volumenkoerper
# --------------------------------------------------------------------------
def test_koerper_aus_flaechen():
    m = _quader()
    k = m.add_koerper("V1", list(m.flaechen), material="S355", teilung=[4, 2, 2])
    check("Volumenkoerper angelegt", "V1" in m.koerper)
    check("noch nicht vernetzt", "nicht vernetzt" in k.bezug(), k.bezug())
    try:
        m.add_koerper("V2", ["Boden", "Deckel", "S1"])
        check("zu wenige Randflaechen werden abgewiesen", False)
    except ValueError as ex:
        check("zu wenige Randflaechen werden abgewiesen", "vier" in str(ex), str(ex)[:50])

    log = []
    els = mesher.mesh_koerper(m, k, log)
    check("16 Hexaeder (4 x 2 x 2)", len(els) == 16, f"{len(els)}")
    check("alle Elemente sind Hexaeder",
          all(m.elements[i].typ == "hex8" for i in els))
    V = sum(SO.solid_volume("hex8", m.nodes[[int(n) for n in m.elements[i].nodes]])
            for i in els)
    close("Summe der Elementvolumen", V, 2.0, 1e-12, " m^3")
    for i in els:
        K, Ve = SO.k_hex8(m.nodes[[int(n) for n in m.elements[i].nodes]], 210e9, 0.3)
        if Ve <= 0:
            break
    else:
        check("jedes Element hat positive Jacobi-Determinante", True)
    check("Protokoll nennt die Teilung", any("4 x 2 x 2" in x for x in log),
          log[0] if log else "-")

    # Rechnung: Zugstab aus Hexaedern, sigma = N/A
    for n in range(m.nn):
        if abs(m.nodes[n][0]) < 1e-12:
            m.support(n, [0, 1, 2])
    m.load_cases["LF1"].gravity = [0.0, 0.0, 0.0]
    rechts = [n for n in range(m.nn) if abs(m.nodes[n][0] - 2.0) < 1e-12]
    N = 300e3
    for n in rechts:
        m.load_node(n, Fx=N / len(rechts), case="LF1")
    r = solver.solve_static(m, case="LF1")
    close("Summe der Auflagerkraefte = N", -float(r.reactions[:, 0].sum()), N,
          1e-9, " N")
    u = float(m.nodes[rechts[0]][0] * N / (1.0 * 210e9))     # A = 1 m^2
    close("Verlaengerung = N L /(E A)", float(r.u.reshape(-1, 6)[rechts[0], 0]),
          u, 2e-3, " m")

    # Ein Koerper, dem eine Randflaeche fehlt, ist offen: weder abgebildet
    # noch frei vernetzbar - und das muss dastehen.
    m2 = _quader()
    k2 = m2.add_koerper("V9", ["Boden", "Deckel", "S1", "S2", "S3"])
    log2 = []
    check("unvollstaendiger Koerper nicht vernetzt",
          mesher.mesh_koerper(m2, k2, log2) == [])
    check("und der Grund steht im Protokoll",
          any("nicht dicht" in x for x in log2), log2[-1] if log2 else "-")
    # Ohne den freien Vernetzer nennt die Meldung die abgebildeten Formen
    log3 = []
    check("abgeschalteter freier Vernetzer meldet die abgebildeten Formen",
          mesher.mesh_koerper(m2, k2, log3, frei=False) == []
          and any("Sechsflächner" in x for x in log3), log3[-1] if log3 else "-")


# --------------------------------------------------------------------------
# 3) Krumme Raender: das abgebildete Netz folgt dem Rand
# --------------------------------------------------------------------------
def _viertelring(typ: str, teilung=(12, 3)) -> tuple:
    """Viertelring innen r = 1, aussen r = 2, Raender als 'arc' oder 'polyline'."""
    m = Model("Viertelring")
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("d10", 0.010))
    w = np.linspace(0.0, np.pi / 2, 3 if typ == "arc" else 9)
    innen = [m.add_node(np.cos(a), np.sin(a), 0.0) for a in w]
    aussen = [m.add_node(2 * np.cos(a), 2 * np.sin(a), 0.0) for a in w]
    m.add_line("Innen", innen, typ)
    m.add_line("Aussen", aussen, typ)
    m.add_line("Radial0", [innen[0], aussen[0]])
    m.add_line("Radial90", [innen[-1], aussen[-1]])
    f = m.add_flaeche("Ring", ["Innen", "Radial90", "Aussen", "Radial0"],
                      dicke="d10", material="S235", teilung=list(teilung))
    return m, f


def test_gekruemmter_rand():
    # ---- Bogen: das Netz folgt der wahren Kurve
    m, f = _viertelring("arc")
    log = []
    els = mesher.mesh_flaeche(m, f, log)
    check("Bogenrand wird vernetzt", len(els) == 36, f"{len(els)}")
    r = np.hypot(m.nodes[:, 0], m.nodes[:, 1])
    # Auf der Innenkante liegen die 13 Netzknoten und der urspruengliche
    # Stuetzpunkt des Bogens bei 45 Grad - alle genau auf r = 1.
    innen = r[np.abs(r - 1.0) < 0.05]
    check("die Innenkante liegt genau auf r = 1",
          len(innen) >= 13 and float(np.abs(innen - 1.0).max()) < 1e-9,
          f"{len(innen)} Knoten, groesste Abweichung "
          f"{float(np.abs(innen - 1.0).max()):.2e} m")
    aussen = r[np.abs(r - 2.0) < 0.05]
    check("die Aussenkante liegt genau auf r = 2",
          len(aussen) >= 13 and float(np.abs(aussen - 2.0).max()) < 1e-9,
          f"{len(aussen)} Knoten, groesste Abweichung "
          f"{float(np.abs(aussen - 2.0).max()):.2e} m")
    A = sum(polygon_flaeche(m.nodes[[int(x) for x in m.elements[i].nodes]]) for i in els)
    genau = np.pi / 4 * (4 - 1)
    # Auch mit exakten Randknoten bleiben die Elemente eben - die Flaeche liegt
    # darum knapp unter dem wahren Viertelring und geht mit feinerem Netz dahin.
    check("Netzflaeche knapp unter dem wahren Viertelring",
          0.995 * genau <= A <= genau, f"{A:.5f} m^2 von {genau:.5f} m^2")
    m2, f2 = _viertelring("arc", (48, 8))
    mesher.mesh_flaeche(m2, f2, [])
    A2 = sum(polygon_flaeche(m2.nodes[[int(x) for x in m2.elements[i].nodes]])
             for i in f2.elemente)
    check("feineres Netz kommt naeher an den Kreis",
          abs(A2 - genau) < abs(A - genau), f"{A2:.6f} statt {A:.6f} (soll {genau:.6f})")

    # ---- Polylinie: das Netz folgt den Sehnen, und das ist richtig so
    m3, f3 = _viertelring("polyline")
    mesher.mesh_flaeche(m3, f3, [])
    r3 = np.hypot(m3.nodes[:, 0], m3.nodes[:, 1])
    innen3 = r3[np.abs(r3 - 1.0) < 0.05]
    check("ein Polylinienrand bleibt ein Polylinienrand (Sehnen)",
          float(np.abs(innen3 - 1.0).max()) > 1e-6,
          f"groesste Abweichung {float(np.abs(innen3 - 1.0).max()):.2e} m")


# --------------------------------------------------------------------------
# 4) Berichtseintraege: Ergebnisse in den Bericht uebernehmen
# --------------------------------------------------------------------------
def test_bericht_uebernahme():
    import base64
    m = _rechteck()
    png = base64.b64encode(
        bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000"
                      "001f15c4890000000a49444154789c6360000002000100"
                      "05fe02fea7e4b2b30000000049454e44ae426082")).decode()
    m.bericht.append(Berichtseintrag("Bild 1", "combo:GZT7", "Ausnutzung EC3",
                                     "My", 30.0, png, "Ausnutzung im GZT",
                                     "maßgebend am Rahmeneck"))
    m.bericht.append(Berichtseintrag("Bild 2", "env:GZG", "|u| Verschiebung",
                                     "kein Verlauf", 20.0, png))
    e = m.bericht[0]
    check("Quelle im Klartext", e.quelle_text() == "Kombination GZT7", e.quelle_text())
    check("Bezug nennt Faerbung und Verlauf",
          e.bezug() == "Kombination GZT7 · Ausnutzung EC3 · My", e.bezug())
    check("„kein Verlauf“ steht nicht im Bezug",
          m.bericht[1].bezug() == "Umhüllende GZG · |u| Verschiebung",
          m.bericht[1].bezug())
    m2 = Model.from_dict(m.to_dict())
    check("Berichtseintraege ueberleben Speichern und Laden",
          len(m2.bericht) == 2 and m2.bericht[0].bild == png)
    check("Bemerkung bleibt erhalten",
          m2.bericht[0].bemerkung == "maßgebend am Rahmeneck")

    from statik3d.report.html import Report
    r = Report(m2, None)
    html = r.html()
    check("Bericht hat das Kapitel", "Übernommene Ergebnisbilder" in html)
    check("Bild ist eingebettet", f"data:image/png;base64,{png}" in html)
    check("Bildunterschrift steht dabei", "Ausnutzung im GZT" in html)
    check("die Einstellung steht dabei",
          "Kombination GZT7" in html and "Ausnutzung EC3" in html)
    check("Bemerkung steht dabei", "maßgebend am Rahmeneck" in html)

    ohne = Report(m2, None, options={"uebernommen": False})
    check("abschaltbar", "Übernommene Ergebnisbilder" not in ohne.html())
    leer = Report(_rechteck(), None)
    check("ohne uebernommene Bilder fehlt das Kapitel",
          "Übernommene Ergebnisbilder" not in leer.html())

    md = r.markdown() if hasattr(r, "markdown") else ""
    if md:
        check("Markdown bettet das Bild ein", "data:image/png;base64" in md)


# --------------------------------------------------------------------------
# 5) Randfaelle des Randaufbaus
# --------------------------------------------------------------------------
def test_rand_zusammensetzen():
    from statik3d.model import _rand_aus_linien
    m = _rechteck()
    check("Rand aus vier Einzellinien", len(_rand_aus_linien(m, ["L1", "L2", "L3", "L4"])) == 4)
    check("Reihenfolge egal", len(_rand_aus_linien(m, ["L3", "L1", "L4", "L2"])) == 4)
    check("Richtung egal", len(_rand_aus_linien(m, ["L1", "L4", "L3", "L2"])) == 4)
    check("leere Liste gibt leeren Rand", _rand_aus_linien(m, []) == [])
    check("unbekannte Linie gibt leeren Rand", _rand_aus_linien(m, ["Foo"]) == [])
    check("offener Zug gibt leeren Rand", _rand_aus_linien(m, ["L1", "L2"]) == [])
    m.add_node(9, 9, 9)
    m.add_line("Fern", [4, 0])
    check("Linie ohne Anschluss gibt leeren Rand",
          _rand_aus_linien(m, ["L1", "L2", "L3", "Fern"]) == [])

    # Ein Randzug aus mehreren Abschnitten
    m2 = Model()
    m2.add_material(Material.steel("S235"))
    m2.add_shell_prop(ShellProp("d10", 0.010))
    m2.add_nodes(np.array([[0, 0, 0], [1, 0, 0], [2, 0, 0], [2, 1, 0],
                           [0, 1, 0.]]))
    m2.add_line("U1", [0, 1])
    m2.add_line("U2", [1, 2])
    m2.add_line("R", [2, 3])
    m2.add_line("O", [3, 4])
    m2.add_line("Lk", [4, 0])
    ring = _rand_aus_linien(m2, ["O", "U1", "R", "Lk", "U2"])
    check("fuenf Abschnitte ergeben einen Umlauf mit fuenf Knoten",
          len(ring) == 5, str(ring))


def test_kreisflaeche_aus_zwei_boegen():
    """Bohrung, Buchse, Augenblech: ein Kreis aus zwei Halbboegen zwischen
    denselben zwei Knoten. Ueber die Knotenfolge sind das zwei Punkte und
    damit kein Polygon - erst die abgetasteten Boegen ergeben den Kreis."""
    from statik3d.gui import viewport as vp
    r = 2.0
    m = Model()
    m.add_material(Material.steel("S235"))
    m.add_nodes(np.array([[-r, 0, 0], [r, 0, 0.]]))
    m.add_line("B1", [0, 1], "arc", punkte=[(-r, 0, 0), (0, r, 0), (r, 0, 0)])
    m.add_line("B2", [1, 0], "arc", punkte=[(r, 0, 0), (0, -r, 0), (-r, 0, 0)])
    f = m.add_flaeche("Buchse", ["B1", "B2"], material="S235")

    check("ueber die Knoten schliesst der Rand nicht", f.randknoten(m) == [],
          str(f.randknoten(m)))
    P = f.randpunkte(m)
    check("ueber die Kurven schliesst er", len(P) == 32, f"{len(P)} Punkte")
    rad = np.linalg.norm(P - P.mean(axis=0), axis=1)
    close("alle Randpunkte liegen auf dem Kreis", float(rad.min()), r, 1e-12, " m")
    close("und keiner darueber hinaus", float(rad.max()), r, 1e-12, " m")
    close("Flaecheninhalt (fein abgetastet)", f.inhalt(m), np.pi * r * r,
          1e-3 * np.pi * r * r, " m^2")
    close("Anzeigepolygon liegt darunter (einbeschrieben)",
          polygon_flaeche(P), np.pi * r * r * np.sin(np.pi / 16) / (np.pi / 16),
          1e-9, " m^2")
    check("die Flaeche wird im Viewport gefunden",
          vp.flaeche_at(m, [0.0, 0.0, 0.0], m.characteristic_size()) == "Buchse")

    # Ein halber Umlauf bleibt ein halber Umlauf
    from statik3d.model import Flaeche
    g = Flaeche("Halb", ["B1"])
    check("ein einzelner Bogen schliesst nicht", len(g.randpunkte(m)) == 0,
          str(len(g.randpunkte(m))))
    close("und hat keinen Inhalt", g.inhalt(m), 0.0, 1e-12, " m^2")
    try:
        m.add_flaeche("Halb", ["B1"], material="S235")
        check("ein offener Rand wird abgewiesen", False, "keine Meldung")
    except ValueError as ex:
        check("ein offener Rand wird abgewiesen", "geschlossen" in str(ex), str(ex))


def main():
    for t in (test_flaeche_aus_linien, test_koerper_aus_flaechen,
              test_gekruemmter_rand, test_bericht_uebernahme,
              test_rand_zusammensetzen, test_kreisflaeche_aus_zwei_boegen):
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
