"""
Schalenflaechen mit gemeinsamer Randlinie sind verbunden (09.11.2026).

Entscheidung des Anwenders: „flächen mit gemeinsamer randlinie sollen
verbunden sein“ und „fläche mit drei randlinien soll sich an gewünschter
netzgröße orientieren“.

Befund an den Testmodellen Stemmtor, Hubtor und Fischbauchklappe: jede
Flaeche legte auf ihren Randlinien eigene Zwischenknoten an
(mesher.mesh_flaeche, _verdichten). Zwei Flaechen hingen nur an den
Linienenden zusammen. Eine Platte von 4 m aus zwei Flaechen zwischen zwei
Linienlagern bog sich unter Eigengewicht um 398 mm statt 149,6 mm durch
(das Netz derselben Platte mit zusammengefuehrten Knoten); im Hubtor waren 1 523, im Stemmtor
1 596 Knotenpaare nicht verbunden. Eine Flaeche aus drei Randlinien wurde
ein einziges Dreieckelement - die Haut der Fischbauchklappe hing an den
dreieckigen Schotten frei (182 mm statt rund 20 mm).

Jetzt: mesher.schalen_gemeinsam_vernetzen - eine Teilung je Linie
(mesher3d.Linienteilung), Knoten je Linie nur einmal; Vierecke mit gleich
geteilten Gegenseiten abgebildet, alles andere frei in der Kantenlaenge
der Netzdichte. Einzelne Flaechen ohne Nachbarn vernetzt mesh_flaeche wie
bisher.

Aufruf:  python -m tests.test_flaechen_gemeinsam
"""
import contextlib
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_UNGESPEICHERT"] = "verwerfen"
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_flaechen_gemeinsam_"), "einstellungen.json")

import numpy as np  # noqa: E402

from statik3d import mesher, solver                                   # noqa: E402
from statik3d.model import DofBehaviour, Material, Model, ShellProp     # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK  ' if ok else 'FAIL'} {name:<78} {detail}")
    return bool(ok)


T, L, B = 0.01, 4.0, 2.0


def zwei_flaechen(m: Model = None) -> Model:
    """Platte 4 x 2 m, t = 10 mm, aus zwei Flaechen mit gemeinsamer Linie bei
    x = 2 m, an allen vier Raendern gelenkig gelagert (Navier), Eigengewicht."""
    m = m if m is not None else Model()
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("D10", T))
    for p in ((0, 0, 0), (2, 0, 0), (4, 0, 0), (4, B, 0), (2, B, 0), (0, B, 0)):
        m.add_node(*p)
    for i, (a, b) in enumerate([(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 0), (1, 4)]):
        m.add_line(f"L{i + 1}", [a, b])
    m.add_flaeche("F1", ["L1", "L7", "L5", "L6"], material="S235", dicke="D10")
    m.add_flaeche("F2", ["L2", "L3", "L4", "L7"], material="S235", dicke="D10")
    if "LF1" not in m.load_cases:
        m.add_load_case("LF1", "G")
    m.case("LF1").gravity = [0.0, 0.0, -9.81]
    ls = m.add_line_support([], name="Rand")
    ls.linien = ["L1", "L2", "L3", "L4", "L5", "L6"]
    for d in (0, 1, 2):
        ls.behaviour[d] = DofBehaviour("rigid")
    return m


def w_hand(m: Model) -> float:
    """Navier: allseits gelenkig gelagerte Rechteckplatte, Gleichlast, Mitte."""
    mat = m.materials["S235"]
    q = mat.rho * 9.81 * T
    D = mat.E * T ** 3 / (12.0 * (1.0 - mat.nu ** 2))
    w = 0.0
    for i in range(1, 80, 2):
        for j in range(1, 80, 2):
            w += (np.sin(i * np.pi / 2) * np.sin(j * np.pi / 2)
                  / (i * j * ((i / L) ** 2 + (j / B) ** 2) ** 2))
    return 16 * q / (np.pi ** 6 * D) * w


def vernetzen(m: Model) -> list:
    log = []
    with contextlib.redirect_stdout(io.StringIO()):
        mesher.modell_vernetzen(m, log, workers=1)
    return log


def test_zwei_flaechen_tragen_wie_eine_platte():
    m = zwei_flaechen()
    vernetzen(m)
    check("zwei Flaechen mit gemeinsamer Linie: keine doppelten Knoten",
          mesher.doppelte_knoten(m) == 0, f"{mesher.doppelte_knoten(m)}")
    r = solver.solve_all(m, workers=1, combinations=False).cases["LF1"]
    w = float(np.abs(r.u[:, 2]).max())
    wh = w_hand(m)
    # Ohne den Umbau knickt die Platte an der gemeinsamen Linie wie ein Gelenk
    check("Durchbiegung in der Mitte wie Navier (Abweichung unter 2 %)",
          abs(w - wh) / wh < 0.02, f"{w * 1e3:.2f} mm, Navier {wh * 1e3:.2f} mm")
    x = m.nodes[:, 0]
    auf = np.where(np.abs(x - 2.0) < 1e-9)[0]
    benutzt = {int(k) for e in m.elements for k in e.nodes}
    auf = [int(i) for i in auf if int(i) in benutzt]
    F1 = {int(k) for e in m.flaechen["F1"].elemente for k in m.elements[e].nodes}
    F2 = {int(k) for e in m.flaechen["F2"].elemente for k in m.elements[e].nodes}
    check("jeder Netzknoten auf der gemeinsamen Linie gehoert beiden Flaechen",
          auf and all(i in F1 and i in F2 for i in auf), f"{len(auf)} Knoten")


def test_einzelne_flaeche_bleibt_wie_bisher():
    """Eine Flaeche ohne Nachbarn: dasselbe abgebildete Netz wie vor dem Umbau."""
    m = Model()
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("D10", T))
    for p in ((0, 0, 0), (4, 0, 0), (4, 2, 0), (0, 2, 0)):
        m.add_node(*p)
    for j in range(4):
        m.add_line(f"L{j + 1}", [j, (j + 1) % 4])
    f = m.add_flaeche("F1", ["L1", "L2", "L3", "L4"], material="S235", dicke="D10")
    check("einzelne Flaeche gehoert nicht zur gemeinsamen Vernetzung",
          not mesher.gemeinsame_schalen(m, [f]))
    log = vernetzen(m)
    from statik3d import netzdichte as nd
    nu, nv = nd.teilung_flaeche(m, m.netz, f)
    check("einzelne Flaeche: abgebildetes Netz nu x nv aus der Netzdichte wie bisher",
          len(f.elemente) == nu * nv and all(m.elements[e].typ == "shell4" for e in f.elemente),
          f"{len(f.elemente)} Elemente, Teilung {nu} x {nv}")
    check("einzelne Flaeche: keine Meldung der gemeinsamen Vernetzung",
          not any("zusammenhängend" in z for z in log))


def dreieck_neben_viereck() -> Model:
    """Dreiecksflaeche (Seiten 2 m) neben einem Quadrat 2 x 2 m, gemeinsame Linie."""
    m = Model()
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("D10", T))
    for p in ((0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0), (3.0, 1.0, 0)):
        m.add_node(*p)
    for i, (a, b) in enumerate([(0, 1), (1, 2), (2, 3), (3, 0), (1, 4), (4, 2)]):
        m.add_line(f"L{i + 1}", [a, b])
    m.add_flaeche("Q", ["L1", "L2", "L3", "L4"], material="S235", dicke="D10")
    m.add_flaeche("D", ["L2", "L5", "L6"], material="S235", dicke="D10")
    m.add_load_case("LF1", "G")
    m.case("LF1").gravity = [0.0, 0.0, 0.0]
    m.add_geometrielast("D", 1000.0, "flaeche", case="LF1")
    ls = m.add_line_support([], name="Rand")
    ls.linien = ["L4"]
    for d in range(6):                    # eingespannt: Kragplatte
        ls.behaviour[d] = DofBehaviour("rigid")
    return m


def test_dreiecksflaeche_folgt_der_netzgroesse():
    m = dreieck_neben_viereck()
    log = vernetzen(m)
    D = m.flaechen["D"]
    h = 2.0 / 16                          # Netzdichte mittel: 16 Elemente ueber die Objektgroesse
    kanten = []
    for e in D.elemente:
        X = m.nodes[m.elements[e].nodes[:3]]
        kanten += [float(np.linalg.norm(X[i] - X[(i + 1) % 3])) for i in range(3)]
    # Ohne den Umbau: ein einziges Element mit Kanten von 2 m
    check("Dreiecksflaeche: viele Elemente statt eines", len(D.elemente) > 50, f"{len(D.elemente)} Elemente")
    check("Dreiecksflaeche: groesste Kante hoechstens 2 h der Netzgroesse",
          max(kanten) <= 2.0 * h, f"{max(kanten) * 1e3:.0f} mm, h etwa {h * 1e3:.0f} mm")
    check("Dreiecksflaeche neben Viereck: keine doppelten Knoten", mesher.doppelte_knoten(m) == 0)
    check("Protokoll nennt die freie Vernetzung mit h", any("frei vernetzt, h =" in z for z in log))
    # Richtung: die Flaechenlast ohne Richtung wirkt senkrecht - fuer alle Dreiecke
    # gleich gedreht, also Summe = p A in z (A = 1 m2), nicht weniger
    r = solver.solve_all(m, workers=1, combinations=False).cases["LF1"]
    Rz = float(r.reactions[:, 2].sum())
    check("Flaechenlast auf der Dreiecksflaeche: |Summe Lager z| = p A = 1000 N (alle Dreiecke gleich gedreht)",
          abs(abs(Rz) - 1000.0) < 1.0, f"{Rz:.1f} N")


def test_einzelne_flaeche_mit_oeffnung():
    """Befund A18 der Pruefagenten (09.11.2026): eine Scheibe 2 x 2 m mit
    Kreisloch d = 0,2 m ohne Nachbarn wurde ueber den Aussenrand abgebildet
    vernetzt - das Loch war gefuellt (Netzflaeche 4,0000 m2)."""
    m = Model()
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("D10", T))
    for p in ((0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0)):
        m.add_node(*p)
    for j in range(4):
        m.add_line(f"L{j + 1}", [j, (j + 1) % 4])
    r, c = 0.1, (1.0, 1.0)
    a = m.add_node(c[0] + r, c[1], 0)
    b = m.add_node(c[0] - r, c[1], 0)
    m.add_line("K1", [a, b], "arc", punkte=[(c[0] + r, c[1], 0), (c[0], c[1] + r, 0), (c[0] - r, c[1], 0)])
    m.add_line("K2", [b, a], "arc", punkte=[(c[0] - r, c[1], 0), (c[0], c[1] - r, 0), (c[0] + r, c[1], 0)])
    f = m.add_flaeche("P", ["L1", "L2", "L3", "L4"], material="S235", dicke="D10")
    f.oeffnungen = [["K1", "K2"]]
    check("Flaeche mit Oeffnung gehoert zur gemeinsamen (freien) Vernetzung",
          [g.name for g in mesher.gemeinsame_schalen(m, [f])] == ["P"])
    vernetzen(m)
    A, im_loch = 0.0, 0
    for e in f.elemente:
        el = m.elements[e]
        X = m.nodes[el.nodes[:4] if el.typ in ("shell4", "shell8") else el.nodes[:3]]
        A += sum(0.5 * float(np.linalg.norm(np.cross(X[k] - X[0], X[k + 1] - X[0])))
                 for k in range(1, len(X) - 1))
        s = X.mean(axis=0)
        if np.hypot(s[0] - c[0], s[1] - c[1]) < r * 0.95:
            im_loch += 1
    soll = 4.0 - np.pi * r * r
    # Ohne den Umbau: 4,0000 m2 und Elemente im Loch
    check("Netzflaeche = Aussenflaeche minus Loch (auf 0,5 %)", abs(A - soll) / soll < 0.005,
          f"{A:.4f} m2, Soll {soll:.4f} m2")
    check("kein Element liegt im Loch", im_loch == 0, f"{im_loch}")


def test_altes_netz_beim_oeffnen_erkannt():
    """Punkt 10 (Anwender, 09.11.2026: „10 ja“): ein Schalennetz von vor dem
    09.11.2026 - jede Flaeche fuer sich vernetzt - wird beim Oeffnen erkannt
    und zum Neuvernetzen aufgefordert; ein neu vernetztes Modell nicht."""
    ordner = tempfile.mkdtemp(prefix="s3d_netz_alt_")
    # altes Netz: jede Flaeche einzeln mit mesh_flaeche, wie bis zum 09.11.2026
    m = zwei_flaechen()
    from statik3d import netzdichte as nd
    nd.anwenden(m, m.netz, list(m.flaechen.values()), [], [])
    with contextlib.redirect_stdout(io.StringIO()):
        for f in m.flaechen.values():
            mesher.mesh_flaeche(m, f, [])
    lose = mesher.unverbundene_schalenlinien(m)
    check("altes Netz: die gemeinsame Linie L7 ist unverbunden", [x[0] for x in lose] == ["L7"], str(lose))
    p = os.path.join(ordner, "alt.json")
    m.save(p)
    m2 = Model.load(p)
    zeilen = [z for z in m2._ladehinweise if "Schalennetz nicht verbunden" in z]
    check("beim Oeffnen: Hinweis „Schalennetz nicht verbunden … neu vernetzen“",
          len(zeilen) == 1 and "neu vernetzen" in zeilen[0] and "F1/F2" in zeilen[0],
          zeilen[0][:90] if zeilen else "kein Hinweis")
    check("der Hinweis steht als offener Importhinweis im Modell",
          any(h.get("art") == "schalennetz" and not h.get("erledigt") for h in m2.importhinweise))
    # neu vernetzt: kein Hinweis, der gespeicherte gilt beim naechsten Oeffnen als erledigt
    vernetzen(m2)
    check("neu vernetzt: keine unverbundene Linie", not mesher.unverbundene_schalenlinien(m2))
    p2 = os.path.join(ordner, "neu.json")
    m2.save(p2)
    m3 = Model.load(p2)
    check("neu vernetzt und geoeffnet: kein Hinweis, der alte ist erledigt",
          not [z for z in m3._ladehinweise if "Schalennetz" in z]
          and all(h.get("erledigt") for h in m3.importhinweise if h.get("art") == "schalennetz"))


def test_oberflaeche_vernetzt_genauso():
    """Die Oberflaeche hat eine eigene Vernetzungsschleife (MainWindow._vernetzen)."""
    from PySide6 import QtWidgets
    from statik3d.gui.main import MainWindow
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = MainWindow()
    w._fragen_knoepfe = lambda *a, **k: True
    w._bestaetigen = lambda *a, **k: True
    w.new_model()
    m = zwei_flaechen(w.model)
    with contextlib.redirect_stdout(io.StringIO()):
        w._vernetzen(list(m.flaechen.values()), [])
    app.processEvents()
    check("Oberflaeche: zwei Flaechen ohne doppelte Knoten", mesher.doppelte_knoten(m) == 0,
          f"{mesher.doppelte_knoten(m)}")
    r = solver.solve_all(m, workers=1, combinations=False).cases["LF1"]
    w_ = float(np.abs(r.u[:, 2]).max())
    wh = w_hand(m)
    check("Oberflaeche: Durchbiegung wie Navier (unter 2 %)", abs(w_ - wh) / wh < 0.02,
          f"{w_ * 1e3:.2f} mm, Navier {wh * 1e3:.2f} mm")
    w.close()


def main():
    for t in (test_zwei_flaechen_tragen_wie_eine_platte,
              test_einzelne_flaeche_bleibt_wie_bisher,
              test_dreiecksflaeche_folgt_der_netzgroesse,
              test_einzelne_flaeche_mit_oeffnung,
              test_altes_netz_beim_oeffnen_erkannt,
              test_oberflaeche_vernetzt_genauso):
        try:
            t()
        except Exception as ex:               # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((f"{t.__name__} (Ausnahme: {ex})", False))
    nok = sum(1 for _n, ok in RESULTS if ok)
    print("=" * 92)
    print(f"Ergebnis: {nok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    sys.exit(main())
