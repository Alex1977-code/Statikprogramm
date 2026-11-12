"""
Gruppe 5 der Befundliste, Teil Robustheit (Befunde A21, A22, A24, C10 bis C14
der Pruefagenten, 09.11.2026).

A21 Negativer E-Modul, negative Dicke, Querdehnzahl ausserhalb (-1; 0,5]:
    FEHLER vor dem Rechnen mit Name und Wert (Staebe, Schalen, Volumen).
    Genau 0,5 ist an Volumen ein FEHLER (Division durch 1 - 2 nu), an Schalen
    und Staeben nicht - die Platte rechnet damit richtig: w(0,5)/w(0,3) =
    (1 - 0,25)/(1 - 0,09), die Plattensteifigkeit E t^3 / (12 (1 - nu^2)).
    Ueber 0,495 an Volumen eine WARNUNG „fast inkompressibel“.
C14 E = 0, t = 0, A = 0, I = 0 am Biegestab: FEHLER mit Namen. Kombination
    mit unbekanntem Lastfall: derselbe Satz in Model.check und im Loeser
    (vorher roher KeyError).
A22 Flaechenlager mit Elementliste: beim Loeschen ruecken die Nummern nach.
    Platte 2 x 1 m, 4 x 2 Elemente, rechte Haelfte gebettet: 4 x 0,25 = 1,00 m2
    vor und nach dem Loeschen eines linken Elements (vorher 0,75 m2); zweiter
    Weg ein Modell, dessen Bettung erst nach dem Loeschen ueber die Lage
    gewaehlt wird. Verliert das Lager eigene Elemente: WARNUNG „Netz
    geändert – Lager prüfen“, ohne Rest FEHLER.
A24 Last auf ein Ziel, das es nicht gibt (Flaeche, Koerper, Linie, Stab,
    Knoten, Element): FEHLER „LF1: … nennt …, die es nicht gibt“.
C10 Lager auf unbekannter Linie/Flaeche: FEHLER; vorhanden, aber nicht
    vernetzt: WARNUNG mit Namen.
C11 Tragende Flaeche ohne Dicke: FEHLER (der Vernetzer setzt weiter die
    Ersatzdicke, die Meldung nennt sie).
C12 Verformung ueber 10 % der groessten Modellabmessung: WARNUNG nach dem
    Rechnen. Zugstab 5 m: u = F L / (E A) = 0,12 L = 600 mm (Handrechnung und
    Rechnung), bei 0,08 L keine.
C13 Element- und Knotennummern in Meldungen ab 0 wie in Tabellen und
    Modellbaum.

Aufruf:  python -m tests.test_gruppe5_robustheit
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

from statik3d import mesher, solver  # noqa: E402
from statik3d import supports as sp  # noqa: E402
from statik3d.model import (BeamLoad, DofBehaviour, Linienlast, Material, Model, NodalLoad,  # noqa: E402
                            Section, ShellProp, TempLoad, Vorspannung, Zwangsverformung)

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def fehler(m, *worte):
    """Die FEHLER-Zeilen der Modellpruefung, die alle ``worte`` enthalten."""
    return [z for z in m.check() if z.startswith("FEHLER") and all(w in z for w in worte)]


def warnungen(m, *worte):
    return [z for z in m.check() if z.startswith("WARNUNG") and all(w in z for w in worte)]


def ohne_leer(s):
    """Zahlen in Meldungen tragen Tausendertrennung - fuer den Vergleich ohne."""
    return "".join(str(s).split()).replace(" ", "").replace(" ", "")


def kurz(zeilen, n=110):
    return (zeilen[0][:n] if zeilen else "(keine Meldung)")


# --------------------------------------------------------------------------
# Modelle
# --------------------------------------------------------------------------
def kragarm(E=210e9, nu=0.3, typ="beam"):
    m = Model("K")
    m.add_material(Material("S355", E=E, nu=nu, rho=0, fy=355e6, fu=490e6))
    m.add_section(Section.i_profile("HEA200", 0.190, 0.200, 0.0065, 0.010))
    ids = mesher.line_of_beams(m, "S355", "HEA200", (0, 0, 0), (5, 0, 0), n=4)
    if typ != "beam":
        for e in m.elements:
            e.typ = typ
    m.fix(ids[0], "all")
    m.load_node(ids[-1], Fz=-20000.0)
    return m, ids


def platte_netz(t=0.012, nu=0.3):
    """Platte 2 x 1 m, 8 x 4 Elemente, allseits gelenkig, 5 kN/m2."""
    m = Model("P")
    m.add_material(Material("S235", 210e9, nu, 7850, fy=235e6, fu=360e6))
    m.add_shell_prop(ShellProp("t12", t))
    ids = mesher.grid_plate(m, "S235", "t12", 2.0, 1.0, 8, 4, quad=True)
    nx, ny = ids.shape[0] - 1, ids.shape[1] - 1
    for i in range(nx + 1):
        for j in range(ny + 1):
            if i in (0, nx) or j in (0, ny):
                m.fix(int(ids[i, j]), [2])
    m.fix(int(ids[0, 0]), [0, 1])
    m.fix(int(ids[nx, 0]), [1])
    for e in range(len(m.elements)):
        m.load_face(e, -5000.0)
    return m


def hexarm(nu):
    """Kragarm 1 x 0,2 x 0,2 m aus hex8, 10 kN am Ende."""
    m = Model("H")
    m.add_material(Material("S", E=210e9, nu=nu, rho=0, fy=235e6, fu=360e6))
    ids = mesher.grid_box(m, "S", 1.0, 0.2, 0.2, 10, 2, 2, typ="hex8")
    for j in range(ids.shape[1]):
        for k in range(ids.shape[2]):
            m.fix(int(ids[0, j, k]), [0, 1, 2])
    end = ids[-1, :, :].ravel()
    for n in end:
        m.load_node(int(n), Fz=-10000.0 / len(end))
    return m


def platte_geo(dicke="t12"):
    """Platte 2 x 1 m als Geometrie (vier Linien R0 bis R3, Flaeche „P“)."""
    m = Model("G")
    m.add_material(Material("S235", 210e9, 0.3, 7850, fy=235e6, fu=360e6))
    m.add_shell_prop(ShellProp("t12", 0.012))
    m.add_nodes(np.array([[0, 0, 0], [2, 0, 0], [2, 1, 0], [0, 1, 0.]]))
    for i in range(4):
        m.add_line(f"R{i}", [i, (i + 1) % 4], "polyline")
    m.add_flaeche("P", ["R0", "R1", "R2", "R3"], material="S235", dicke=dicke)
    m.netz.dichte = "eigene"
    m.netz.ziellaenge = 0.25
    m.fix(0, [0, 1])
    m.fix(1, [1])
    return m


def linienlager(m, linie):
    ls = m.add_line_support([], name="LL", uz=DofBehaviour("rigid"))
    ls.linien = [linie]
    return ls


def wuerfel(m=None, x0=0.0, praefix=""):
    """Wuerfel 1 m als Geometrie (sechs Flaechen, ein Koerper), Netz 0,5 m."""
    if m is None:
        m = Model("W")
        m.add_material(Material("S", E=210e9, nu=0.3, rho=0.0, fy=235e6, fu=360e6))
    k0 = m.nn
    P = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                  [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1.]])
    P[:, 0] += x0
    m.add_nodes(P)
    z = [len(m.lines)]

    def linie(a, b):
        z[0] += 1
        m.add_line(f"L{z[0]}", [a, b], "polyline")
        return f"L{z[0]}"
    R = [[linie(k0 + o + i, k0 + o + (i + 1) % 4) for i in range(4)] for o in (0, 4)]
    V = [linie(k0 + i, k0 + i + 4) for i in range(4)]
    m.add_flaeche(praefix + "Boden", R[0], material="S")
    m.add_flaeche(praefix + "Deckel", R[1], material="S")
    mantel = []
    for i in range(4):
        m.add_flaeche(f"{praefix}M{i}", [R[0][i], V[(i + 1) % 4], R[1][i], V[i]], material="S")
        mantel.append(f"{praefix}M{i}")
    m.add_koerper(praefix + "V1", [praefix + "Boden", praefix + "Deckel"] + mantel, material="S")
    m.netz.dichte = "eigene"
    m.netz.ziellaenge = 0.5
    m.netz.sweep = True
    return m


def boden_lager(m, flaeche="Boden"):
    ss = m.add_surface_support(name="FL", ux=DofBehaviour("rigid"), uy=DofBehaviour("rigid"),
                               uz=DofBehaviour("rigid"))
    ss.flaechen = [flaeche]
    return ss


def vernetzen(m):
    log = []
    mesher.modell_vernetzen(m, log, workers=1)
    return log


def bettung():
    """Platte 2 x 1 m, 4 x 2 Elemente (je 0,5 x 0,5 m); Elemente und Mitten."""
    m = Model("B")
    m.add_material(Material("S235", 210e9, 0.3, 7850, fy=235e6, fu=360e6))
    m.add_shell_prop(ShellProp("t12", 0.012))
    ids = mesher.grid_plate(m, "S235", "t12", 2.0, 1.0, 4, 2, quad=True)
    m.fix(int(ids[0, 0]), [0, 1])
    m.fix(int(ids[-1, 0]), [1])
    return m


def rechts_von(m, x=1.0):
    return [i for i, e in enumerate(m.elements) if float(m.nodes[e.nodes].mean(axis=0)[0]) > x]


def betten(m, elemente):
    ss = m.add_surface_support(elements=elemente, name="Bettung", uz=DofBehaviour("spring", stiffness=1e7))
    for e in range(len(m.elements)):
        m.load_face(e, -5000.0)
    return ss


def umax(m, name="LF1"):
    an = solver.solve_all(m, workers=1, combinations=False)
    return float(np.linalg.norm(an.cases[name].u[:, :3], axis=1).max())


# --------------------------------------------------------------------------
# A21 / C14: Werkstoff, Dicke, Querschnitt
# --------------------------------------------------------------------------
def test_a21_werkstoff():
    m, _ = kragarm(E=-210e9)
    z = fehler(m, "Werkstoff „S355“", "E-Modul", "negativ")
    check("A21 Stab, E = -210 000 N/mm²: FEHLER mit Werkstoff und Wert",
          len(z) == 1 and "-210000N/mm²" in ohne_leer(z[0]), kurz(z))
    m, _ = kragarm(E=0.0)
    z = fehler(m, "Werkstoff „S355“", "E-Modul", "ist null")
    check("C14 Stab, E = 0: FEHLER mit Werkstoff", len(z) == 1, kurz(z))
    m, _ = kragarm(nu=0.7)
    z = fehler(m, "Werkstoff „S355“", "Querdehnzahl 0,7")
    check("A21 Stab, ν = 0,7: FEHLER mit Werkstoff und Wert", len(z) == 1, kurz(z))
    z = fehler(hexarm(0.6), "Werkstoff „S“", "Querdehnzahl 0,6") + fehler(hexarm(-1.2), "Werkstoff „S“", "Querdehnzahl -1,2") \
        + fehler(hexarm(-1.0), "Werkstoff „S“", "Querdehnzahl -1")
    check("A21 Volumen, ν = 0,6 / -1,2 / -1: je ein FEHLER", len(z) == 3, kurz(z))
    z = fehler(platte_netz(nu=0.6), "Werkstoff „S235“", "Querdehnzahl 0,6")
    check("A21 Schale, ν = 0,6: FEHLER", len(z) == 1, kurz(z))

    # genau 0,5: Volumen nicht rechenbar, Schale und Stab rechnen richtig
    z_vol = fehler(hexarm(0.5), "Werkstoff „S“", "Querdehnzahl 0,5", "inkompressibel")
    p03, p05 = platte_netz(nu=0.3), platte_netz(nu=0.5)
    z_schale = fehler(p05, "Querdehnzahl")
    z_stab = fehler(kragarm(nu=0.5)[0], "Querdehnzahl")
    w03 = float(np.abs(solver.solve_all(p03, workers=1, combinations=False).cases["LF1"].u[:, 2]).max())
    w05 = float(np.abs(solver.solve_all(p05, workers=1, combinations=False).cases["LF1"].u[:, 2]).max())
    soll = (1 - 0.5 ** 2) / (1 - 0.3 ** 2)          # Plattensteifigkeit E t^3 / (12 (1 - nu^2))
    check("A21 ν = 0,5: Volumen FEHLER, Schale und Stab keiner (Platte rechnet: w ~ 1 - ν²)",
          len(z_vol) == 1 and not z_schale and not z_stab and abs(w05 / w03 / soll - 1) < 0.005,
          f"w(0,5)/w(0,3) = {w05 / w03:.5f}, (1-0,25)/(1-0,09) = {soll:.5f}")
    m499, m49 = hexarm(0.499), hexarm(0.49)
    w = warnungen(m499, "Werkstoff „S“", "0,499", "fast inkompressibel")
    check("A21 Volumen, ν = 0,499: WARNUNG „fast inkompressibel“, kein FEHLER; ν = 0,49: keine",
          len(w) == 1 and not fehler(m499, "Querdehnzahl") and not warnungen(m49, "inkompressibel")
          and not fehler(m49, "Querdehnzahl"), kurz(w))


def test_a21_dicke_querschnitt():
    z = fehler(platte_netz(t=-0.012), "Dicke „t12“", "-12 mm", "negativ")
    check("A21 Schale, t = -12 mm: FEHLER mit Dicke und Wert", len(z) == 1, kurz(z))
    z = fehler(platte_netz(t=0.0), "Dicke „t12“", "0 mm", "ist null")
    check("C14 Schale, t = 0: FEHLER mit Dicke", len(z) == 1, kurz(z))
    m, _ = kragarm()
    m.sections["HEA200"].A = 0.0
    z = fehler(m, "Querschnitt „HEA200“", "Querschnittsfläche A", "ist null")
    check("C14 Stab, A = 0: FEHLER mit Querschnitt", len(z) == 1, kurz(z))
    m, _ = kragarm()
    m.sections["HEA200"].A = -0.005
    z = fehler(m, "Querschnitt „HEA200“", "Querschnittsfläche A", "-50 cm²", "negativ")
    check("A21 Stab, A = -50 cm²: FEHLER mit Querschnitt und Wert", len(z) == 1, kurz(z))
    m, _ = kragarm()
    m.sections["HEA200"].Iy = 0.0
    z = fehler(m, "Querschnitt „HEA200“", "I_y", "ist null")
    f, _ = kragarm(typ="truss")
    f.sections["HEA200"].Iy = 0.0
    check("C14 Biegestab, I_y = 0: FEHLER; Fachwerkstab mit I_y = 0: keiner (rechnet nur mit E A)",
          len(z) == 1 and not fehler(f, "Querschnitt „HEA200“"), kurz(z))
    # Gegenprobe: an den richtigen Modellen keine Zeile der Eingabepruefung -
    # zusammen mit dem Fehlerfall, damit die Pruefung den alten Stand erkennt
    sauber = [fehler(x, "Werkstoff „") + fehler(x, "Dicke „") + fehler(x, "Querschnitt „")
              + warnungen(x, "Werkstoff „") for x in (kragarm()[0], platte_netz(), hexarm(0.3))]
    check("richtige Modelle (Stab, Schale, Volumen) ohne Eingabemeldung, E < 0 an jedem mit FEHLER",
          not any(sauber) and all(len(fehler(x, "E-Modul", "negativ")) == 1
                                  for x in (_neg(kragarm()[0], "S355"), _neg(platte_netz(), "S235"),
                                            _neg(hexarm(0.3), "S"))),
          str(sauber)[:80])


def _neg(m, name):
    m.materials[name].E = -abs(m.materials[name].E)
    return m


# --------------------------------------------------------------------------
# C14: Kombination mit unbekanntem Lastfall
# --------------------------------------------------------------------------
def test_c14_kombination():
    satz = "LK1 nennt den Lastfall „GIBTSNICHT“ – den gibt es nicht."
    m, _ = kragarm()
    m.add_combination("LK1", {"LF1": 1.35, "GIBTSNICHT": 1.5})
    z = fehler(m, "GIBTSNICHT")
    check("C14 Modellprüfung: „LK1 nennt den Lastfall … – den gibt es nicht“",
          len(z) == 1 and z[0].startswith("FEHLER: " + satz), kurz(z))
    try:
        solver.solve_all(m, workers=1, combinations=True)
        art, text = "lief", ""
    except Exception as ex:                      # noqa: BLE001
        art, text = type(ex).__name__, str(ex)
    check("C14 Löser: derselbe Satz als ValueError statt rohem KeyError",
          art == "ValueError" and text.startswith(satz), f"{art}: {text[:80]}")
    m, _ = kragarm()
    m.add_combination("Wind", {"LF1": 1.0, "Schnee": 1.5})
    z = fehler(m, "Schnee")
    check("C14 freier Name: „Kombination „Wind“ nennt den Lastfall „Schnee“ …“",
          len(z) == 1 and "Kombination „Wind“ nennt den Lastfall „Schnee“ – den gibt es nicht." in z[0], kurz(z))


# --------------------------------------------------------------------------
# A22: Flaechenlager mit Elementliste beim Loeschen
# --------------------------------------------------------------------------
def test_a22_flaechenlager():
    m = bettung()
    rechts = rechts_von(m)
    ss = betten(m, rechts)
    A0 = sum(sp.tributary_areas(m, ss.elements, ss.face).values())
    m.elemente_loeschen([0])                     # ein Element der linken, nicht gebetteten Haelfte
    A1 = sum(sp.tributary_areas(m, ss.elements, ss.face).values())
    hand = 4 * 0.5 * 0.5                         # vier Elemente von 0,5 x 0,5 m
    check("A22 Löschen links: das Lager nennt weiter seine vier Elemente rechts (Nummern nachgerückt)",
          list(ss.elements) == rechts_von(m) and len(ss.elements) == 4, f"{rechts} -> {list(ss.elements)}")
    check("A22 Bettungsfläche vor und nach dem Löschen 1,00 m² (4 x 0,25 m²)",
          abs(A0 - hand) < 1e-9 and abs(A1 - hand) < 1e-9, f"vorher {A0:.4f}, nachher {A1:.4f}, Hand {hand:.4f} m²")
    # zweiter Weg: erst loeschen, dann die Bettung ueber die Lage waehlen
    r = bettung()
    r.elemente_loeschen([0])
    betten(r, rechts_von(r))
    u1, u2 = umax(m), umax(r)
    check("A22 Rechnung nach dem Löschen = Modell mit danach gewählter Bettung",
          abs(u1 - u2) < 1e-9 * u2, f"{u1 * 1e3:.4f} mm gegen {u2 * 1e3:.4f} mm")
    still = warnungen(m, "Flächenlager „Bettung“") + fehler(m, "Flächenlager „Bettung“")
    m.elemente_loeschen([ss.elements[0]])        # jetzt ein eigenes Element des Lagers
    z = warnungen(m, "Flächenlager „Bettung“", "Netz geändert – Lager prüfen", "1 Element", "3 Elementen")
    check("A22 eigenes Element gelöscht: WARNUNG „Netz geändert – Lager prüfen“ (vorher keine Meldung)",
          not still and len(z) == 1 and len(ss.elements) == 3 and not fehler(m, "Flächenlager „Bettung“"), kurz(z, 150))
    # die Meldung uebersteht Speichern und Laden; ohne Verlust steht nichts in der Datei
    d = m.to_dict()
    m2 = Model.from_dict(d)
    frisch = bettung()
    betten(frisch, rechts_von(frisch))
    d0 = frisch.to_dict()["surface_supports"][0]
    check("A22 gespeichert und geladen: die WARNUNG bleibt; ein Lager ohne Verlust schreibt kein neues Feld",
          len(warnungen(m2, "Flächenlager „Bettung“", "Netz geändert – Lager prüfen")) == 1
          and "entfallen" not in d0 and "entfallen_rest" not in d0,
          f"Felder des unberührten Lagers: {sorted(k for k in d0 if k.startswith('entf'))}")
    m.elemente_loeschen(list(ss.elements))
    z = fehler(m, "Flächenlager „Bettung“", "Netz geändert – Lager prüfen", "keinem Element")
    check("A22 alle Elemente des Lagers gelöscht: FEHLER (wirkt nirgends)", len(z) == 1 and not ss.elements, kurz(z, 150))
    ss.elements = rechts_von(m, 0.5)[:1] or [0]
    check("A22 dem Lager neue Elemente gegeben: die Meldung endet (davor stand der FEHLER)",
          len(z) == 1 and not fehler(m, "Flächenlager „Bettung“") and not warnungen(m, "Flächenlager „Bettung“"),
          f"Elemente {ss.elements}")


# --------------------------------------------------------------------------
# A24: Lasten auf Ziele, die es nicht gibt
# --------------------------------------------------------------------------
def test_a24_lastziele():
    m = platte_geo()
    for r in ("R1", "R3"):
        linienlager(m, r)
    m.add_geometrielast("P", p=5000.0, richtung=[0, 0, -1])
    vernetzen(m)
    sauber = fehler(m, "die es nicht gibt") + fehler(m, "den es nicht gibt") + fehler(m, "das es nicht gibt")
    m.add_geometrielast("GIBTSNICHT", p=5000.0, richtung=[0, 0, -1])
    z = fehler(m, "GIBTSNICHT")
    check("A24 Flächenlast auf Fläche „GIBTSNICHT“: FEHLER „LF1: … nennt die Fläche …“ (richtige Last: keiner)",
          not sauber and len(z) == 1
          and z[0].startswith("FEHLER: LF1: Eine Flächenlast nennt die Fläche „GIBTSNICHT“, die es nicht gibt"),
          kurz(z))
    m = wuerfel()
    boden_lager(m)
    m.add_geometrielast("GIBTSNICHT", art="koerper", lastart="temperatur", dT=30.0)
    vernetzen(m)
    z = fehler(m, "GIBTSNICHT")
    check("A24 Volumenlast auf Körper „GIBTSNICHT“: FEHLER",
          len(z) == 1 and z[0].startswith("FEHLER: LF1: Eine Volumenlast nennt den Körper „GIBTSNICHT“, den es nicht gibt"),
          kurz(z))

    def stab(tun, *worte):
        k, _ = kragarm()
        tun(k.case("LF1"))
        z = fehler(k, "FEHLER: LF1: ", *worte)
        return len(z) == 1, kurz(z)

    faelle = [
        ("Linienlast auf Stab „GIBTSNICHT“", lambda lc: lc.linienlasten.append(
            Linienlast(ziel="GIBTSNICHT", art="stab", q=[0, 0, -1000.0])), ("Linienlast", "Stab „GIBTSNICHT“")),
        ("Linienlast auf Linie „GIBTSNICHT“", lambda lc: lc.linienlasten.append(
            Linienlast(ziel="GIBTSNICHT", art="linie", q=[0, 0, -1000.0])), ("Linienlast", "Linie „GIBTSNICHT“")),
        ("Vorspannung an Stab „GIBTSNICHT“", lambda lc: lc.vorspannungen.append(
            Vorspannung(ziel="GIBTSNICHT", art="stab", kraft=1e5)), ("Vorspannung", "Stab „GIBTSNICHT“")),
        ("Vorspannung an Körper „GIBTSNICHT“", lambda lc: lc.vorspannungen.append(
            Vorspannung(ziel="GIBTSNICHT", art="koerper", kraft=1e5)), ("Vorspannung", "Körper „GIBTSNICHT“")),
        ("Zwangsverformung an Knoten 999", lambda lc: lc.zwangsverformungen.append(
            Zwangsverformung(node=999, dofs=[2], u=[0.01])), ("Zwangsverformung", "Knoten 999")),
        ("Zwangsverformung an Knoten -1", lambda lc: lc.zwangsverformungen.append(
            Zwangsverformung(node=-1, dofs=[2], u=[0.01])), ("Zwangsverformung", "Knoten -1")),
        ("Temperaturlast an Element 999", lambda lc: lc.temp_loads.append(
            TempLoad(elem=999, dT=50.0)), ("Temperaturlast", "Element 999")),
        ("Temperaturlast an Element -1", lambda lc: lc.temp_loads.append(
            TempLoad(elem=-1, dT=50.0)), ("Temperaturlast", "Element -1")),
        ("Knotenlast an Knoten -1", lambda lc: lc.nodal_loads.append(
            NodalLoad(node=-1, F=[0, 0, -20000.0, 0, 0, 0])), ("Knotenlast", "Knoten -1")),
        ("Stablast an Element -1", lambda lc: lc.beam_loads.append(
            BeamLoad(elem=-1, q=[0, 0, -1000.0])), ("Stablast", "Element -1")),
    ]
    for name, tun, worte in faelle:
        ok, text = stab(tun, *worte)
        check(f"A24 {name}: FEHLER „LF1: … nicht gibt“", ok, text)


# --------------------------------------------------------------------------
# C10: Lager auf unbekanntem oder nicht vernetztem Ziel
# --------------------------------------------------------------------------
def test_c10_lager():
    def platte(*lager):
        m = platte_geo()
        for ln in lager:
            if ln == "Lfrei":
                a = m.add_node(0, 3, 0)
                b = m.add_node(2, 3, 0)
                m.add_line("Lfrei", [a, b], "polyline")
            linienlager(m, ln)
        m.add_geometrielast("P", p=5000.0, richtung=[0, 0, -1])
        vernetzen(m)
        return m
    ref = platte("R1", "R3")
    sauber = fehler(ref, "Linienlager") + warnungen(ref, "Linienlager")
    m = platte("R1", "GIBTSNICHT")
    z = fehler(m, "Linienlager „LL“", "Linie „GIBTSNICHT“", "die es nicht gibt")
    check("C10 Linienlager auf unbekannter Linie: FEHLER mit Lager und Linie (Lager auf R1/R3: keine Meldung)",
          len(z) == 1 and not sauber, kurz(z))
    m = platte("R1", "Lfrei")
    z = warnungen(m, "Linienlager „LL“", "Linie „Lfrei“", "nicht vernetzt")
    check("C10 Linienlager auf loser, nicht vernetzter Linie: WARNUNG mit Namen, kein FEHLER",
          len(z) == 1 and not fehler(m, "Linienlager"), kurz(z))

    w = wuerfel()
    boden_lager(w)
    w.add_geometrielast("Deckel", p=1e6, richtung=[0, 0, -1])
    vernetzen(w)
    sauber = fehler(w, "Flächenlager") + warnungen(w, "Flächenlager")
    w = wuerfel()
    boden_lager(w, "GIBTSNICHT")
    w.add_geometrielast("Deckel", p=1e6, richtung=[0, 0, -1])
    vernetzen(w)
    z = fehler(w, "Flächenlager „FL“", "Fläche „GIBTSNICHT“", "die es nicht gibt")
    check("C10 Flächenlager auf unbekannter Fläche: FEHLER mit Lager und Fläche (Lager auf „Boden“: keine Meldung)",
          len(z) == 1 and not sauber, kurz(z))
    # eine Flaeche, die es gibt, die aber kein Netz hat: nach dem Vernetzen angelegt
    m = platte("R1", "R3")
    k0 = m.nn
    m.add_nodes(np.array([[0, 3, 0], [2, 3, 0], [2, 4, 0], [0, 4, 0.]]))
    for i in range(4):
        m.add_line(f"Q{i}", [k0 + i, k0 + (i + 1) % 4], "polyline")
    m.add_flaeche("Q", ["Q0", "Q1", "Q2", "Q3"], material="S235", dicke="t12")
    ss = m.add_surface_support(name="FL", uz=DofBehaviour("rigid"))
    ss.flaechen = ["Q"]
    z = warnungen(m, "Flächenlager „FL“", "Fläche „Q“", "nicht vernetzt")
    check("C10 Flächenlager auf vorhandener, nicht vernetzter Fläche: WARNUNG mit Namen, kein FEHLER",
          len(z) == 1 and not fehler(m, "Flächenlager"), kurz(z))


# --------------------------------------------------------------------------
# C11: Flaeche ohne Dicke
# --------------------------------------------------------------------------
def test_c11_dicke_fehlt():
    def platte(dicke):
        m = platte_geo(dicke=dicke)
        for r in ("R1", "R3"):
            linienlager(m, r)
        m.add_geometrielast("P", p=5000.0, richtung=[0, 0, -1])
        vernetzen(m)
        return m
    mit, ohne = platte("t12"), platte("")
    z = fehler(ohne, "Fläche „P“ hat keine Dicke", "Ersatzdicke „t12“")
    check("C11 Fläche ohne Dicke: FEHLER nennt Fläche und Ersatzdicke (mit Dicke: keiner)",
          len(z) == 1 and not fehler(mit, "keine Dicke"), kurz(z, 150))
    # Koerper geloescht: seine sechs Flaechen bleiben, werden tragend und
    # bekommen beim Vernetzen Schalen mit 10 mm
    m = wuerfel()
    boden_lager(m)
    wuerfel(m=m, x0=3.0, praefix="B_")
    m.add_geometrielast("Deckel", p=1e6, richtung=[0, 0, -1])
    vorher = fehler(m, "keine Dicke")
    m.koerper_loeschen("B_V1")
    vernetzen(m)
    z = fehler(m, "keine Dicke")
    schalen = sorted({e.sec for e in m.elements if e.typ.startswith("shell")})
    dicke_mm = [round(m.shells[s].dicke() * 1e3, 3) for s in schalen]
    check("C11 Körper gelöscht: ein FEHLER für die sechs verwaisten Flächen mit Ersatzdicke „t10“ (10 mm)",
          not vorher and len(z) == 1 and "6 Flächen haben keine Dicke" in z[0] and "Ersatzdicke „t10“" in z[0]
          and all(f"B_{n}" in z[0] for n in ("Boden", "Deckel", "M0", "M1", "M2", "M3"))
          and schalen == ["t10"] and dicke_mm == [10.0], f"Schalen {schalen} {dicke_mm} mm; {kurz(z, 60)}")


# --------------------------------------------------------------------------
# C12: Verformung gegen Modellgroesse
# --------------------------------------------------------------------------
def test_c12_verformung():
    def zugstab(anteil, kombination=False):
        """Stab 5 m, laengs gezogen: u = F L / (E A) = anteil * L."""
        m = Model("Z")
        m.add_material(Material("S355", E=210e9, nu=0.3, rho=0, fy=355e6, fu=490e6))
        m.add_section(Section.i_profile("HEA200", 0.190, 0.200, 0.0065, 0.010))
        ids = mesher.line_of_beams(m, "S355", "HEA200", (0, 0, 0), (5, 0, 0), n=4)
        m.fix(ids[0], "all")
        EA = 210e9 * m.sections["HEA200"].A
        F = anteil * EA
        m.load_node(ids[-1], Fx=F)
        if kombination:
            m.add_combination("LK1", {"LF1": 1.5})
        an = solver.solve_all(m, workers=1, combinations=kombination)
        return an, F * 5.0 / EA

    an12, hand12 = zugstab(0.12)
    an08, hand08 = zugstab(0.08)
    r12, r08 = an12.cases["LF1"], an08.cases["LF1"]
    u12 = float(np.linalg.norm(r12.u[:, :3], axis=1).max())
    u08 = float(np.linalg.norm(r08.u[:, :3], axis=1).max())
    check("C12 Zugstab: Rechnung = F L / (E A) (600 mm und 400 mm)",
          abs(u12 - hand12) < 1e-9 and abs(u08 - hand08) < 1e-9 and abs(hand12 - 0.6) < 1e-12
          and _hat_warnung(r12.summary()), f"{u12 * 1e3:.4f} / {u08 * 1e3:.4f} mm, Hand {hand12 * 1e3:.4f} / {hand08 * 1e3:.4f} mm")
    w = [z.strip() for z in r12.summary().splitlines() if "Einheiten und Lagerung prüfen" in z]
    check("C12 Verformung 12 % der Modellgröße: WARNUNG „Verformung 600 mm bei Modellgröße 5 m – …“; 8 %: keine",
          len(w) == 1 and w[0].startswith("WARNUNG: Verformung 600 mm bei Modellgröße 5 m – Einheiten und Lagerung prüfen")
          and not _hat_warnung(r08.summary()), kurz(w, 120))
    an, _ = zugstab(0.12, kombination=True)
    w = [z.strip() for z in an.summary().splitlines() if "Einheiten und Lagerung prüfen" in z]
    check("C12 Zusammenfassung der Rechnung: eine Zeile mit dem größten Wert (900 mm) für LF1 und LK1",
          len(w) == 1 and "Verformung 900 mm bei Modellgröße 5 m" in w[0] and "bei 2 Ergebnissen: LF1, LK1" in w[0],
          kurz(w, 130))
    check("C12 das Ergebnis bleibt gültig (WARNUNG sperrt nicht)",
          _hat_warnung(r12.summary()) and not solver.gueltigkeit(r12.info), repr(solver.gueltigkeit(r12.info))[:60])


def _hat_warnung(text):
    return any("WARNUNG" in z and "Einheiten und Lagerung prüfen" in z for z in text.splitlines())


# --------------------------------------------------------------------------
# C13: Zaehlung in Meldungen ab 0
# --------------------------------------------------------------------------
def test_c13_zaehlung():
    from statik3d import assemble, diagnose
    m = platte_netz()
    for i in (0, 5):
        e = m.elements[i]
        text = str(assemble.elementfehler(m, i, ValueError("Probe")))
        kn = ", ".join(str(int(k)) for k in e.nodes)
        check(f"C13 Meldung des Lösers zu Element {i}: „Element {i} ({e.typ} …, Knoten {kn})“ wie in der Tabelle",
              text.startswith(f"Element {i} ({e.typ}") and f", Knoten {kn}): " in text, text[:70])
    # Rechnung mit Dicke 0: der Loeser haelt am ersten Element an - das ist Element 0
    m0 = platte_netz(t=0.0)
    try:
        solver.solve_all(m0, workers=1, combinations=False)
        text = "die Rechnung lief"
    except Exception as ex:                      # noqa: BLE001
        text = str(ex)
    kn = ", ".join(str(int(k)) for k in m0.elements[0].nodes)
    check("C13 Rechnung mit t = 0: die Meldung nennt Element 0 mit seinen Knoten",
          f"Element 0 (shell4" in text and f"Knoten {kn})" in text, text[:80])
    # Modellpruefung: Sechsflaechner 2 mit einer zusammengezogenen Kante
    h = hexarm(0.3)
    kn = list(h.elements[2].nodes)
    h.elements[2].nodes = [kn[0], kn[1], kn[2], kn[2], kn[4], kn[5], kn[6], kn[7]]
    z = [x for x in diagnose.meldungen(h) if x.startswith("FEHLER") and "zusammenfallenden" in x]
    check("C13 Modellprüfung: der entartete Sechsflächner h.elements[2] heißt „Element 2 (hex8)“",
          len(z) == 1 and "Element 2 (hex8)" in z[0], kurz(z))


def main():
    for t in (test_a21_werkstoff, test_a21_dicke_querschnitt, test_c14_kombination, test_a22_flaechenlager,
              test_a24_lastziele, test_c10_lager, test_c11_dicke_fehlt, test_c12_verformung, test_c13_zaehlung):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:          # noqa: BLE001
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
