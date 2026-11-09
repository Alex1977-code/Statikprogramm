"""Die sechs Testmodelle vom 09.11.2026 als Beispiele mit Parametern.

Mit den Vorgabewerten entstehen dieselben Modelle wie mit
``Desktop\\Statik3D\\Testmodelle\\erzeugen_testmodelle.py`` (geprueft in
tests/test_beispielbibliothek.py gegen die dort erzeugten Dateien). Alle
Masse, Querschnitte, Werkstoffe und Lasten sind Annahmen fuer ein
Beispielmodell; sie stehen in meta["annahmen"] jedes Modells.

Die Werte kommen in der Einheit der Parametertabelle (m, mm, kN, kN/m, Grad).
"""
from __future__ import annotations

import math

import numpy as np

from ..model import Model, Material, Section, DofBehaviour
from ..zahlen import zahl_text as zt
from .hilfen import (Bau, stab, kombination, lager, linienlager, wasser, kreis, mantel,
                     platten_raster, dicken)


def z1(x):
    """Wasserstand mit mindestens einer Nachkommastelle („7,0“)."""
    x = float(x)
    return f"{x:.1f}".replace(".", ",") if abs(round(x, 1) - x) < 1e-9 else zt(x)


def _fertig(m, annahmen):
    m.meta["projekt"] = "Beispielbibliothek Statik3D"
    m.meta["annahmen"] = annahmen
    m.active_case = "LF1"
    return m


# ---------------------------------------------------------------------------
# Doppellenkerwippkran
# ---------------------------------------------------------------------------
def wippkran(w):
    Q, G, wind = w["hublast"] * 1e3, w["gegengewicht"] * 1e3, w["wind"] * 1e3
    L_a = w["ausleger"]
    m = Model("Doppellenkerwippkran")
    b = Bau(m)
    m.add_material(Material.steel("S355"))
    for s in (Section.from_profile("HEB 600"),
              Section.pipe("RO 2500/30", 2.500, 0.030, fabrication="welded"),
              Section.rhs("Kasten 1000x1000x20", 1.000, 1.000, 0.020, fabrication="welded"),
              Section.rhs("Kasten 1800x800x30", 1.800, 0.800, 0.030, fabrication="welded"),
              Section.rhs("Kasten 1400x1200x25", 1.400, 1.200, 0.025, fabrication="welded"),
              Section.rhs("Kasten 1000x900x20", 1.000, 0.900, 0.020, fabrication="welded"),
              Section.pipe("RO 406,4/12,5", 0.4064, 0.0125),
              Section.pipe("RO 323,9/25", 0.3239, 0.025)):
        m.add_section(s)
    ecken = [(-5, -4), (5, -4), (5, 4), (-5, 4)]
    for i, (x, y) in enumerate(ecken):
        stab(m, b, f"Portalbein {i + 1}", [(x, y, 0), (x, y, 10)], "S355", "Kasten 1000x1000x20")
        lager(m, b.node((x, y, 0)), [0, 1, 2], f"Rad {i + 1}")
    stab(m, b, "Portalriegel vorn", [(-5, -4, 10), (5, -4, 10)], "S355", "Kasten 1800x800x30")
    stab(m, b, "Portalriegel hinten", [(-5, 4, 10), (5, 4, 10)], "S355", "Kasten 1800x800x30")
    stab(m, b, "Portalriegel links", [(-5, -4, 10), (-5, 4, 10)], "S355", "Kasten 1800x800x30")
    stab(m, b, "Portalriegel rechts", [(5, -4, 10), (5, 4, 10)], "S355", "Kasten 1800x800x30")
    for i, (x, y) in enumerate(ecken):
        stab(m, b, f"Drehkranztraeger {i + 1}", [(0, 0, 10), (x, y, 10)], "S355", "Kasten 1800x800x30")
    stab(m, b, "Turm", [(0, 0, 10), (0, 0, 11), (0, 0, 16), (0, 0, 24)], "S355", "RO 2500/30")
    stab(m, b, "Auslegerkonsole", [(0, 0, 16), (1.5, 0, 16)], "S355", "Kasten 1400x1200x25", h=0.75)
    stab(m, b, "Gegengewichtstraeger", [(0, 0, 16), (-6, 0, 16)], "S355", "Kasten 1800x800x30")
    a40, a10 = math.radians(w["winkel"]), math.radians(-10)
    P = np.array([1.5, 0, 16.0])
    J1 = P + (L_a / 2) * np.array([math.cos(a40), 0, math.sin(a40)])
    A = P + L_a * np.array([math.cos(a40), 0, math.sin(a40)])
    er = np.array([math.cos(a10), 0, math.sin(a10)])
    hinten, spitze = A - 4 * er, A + 8 * er
    ausl = stab(m, b, "Ausleger", [P, J1, A], "S355", "Kasten 1400x1200x25")
    m.add_hinge("Bolzen (phi_y frei)", end=0, phiy="free")
    m.apply_hinge(ausl[0], "Bolzen (phi_y frei)", end=0)
    m.apply_hinge(ausl[-1], "Bolzen (phi_y frei)", end=1)
    stab(m, b, "Ruessel", [hinten, A, spitze], "S355", "Kasten 1000x900x20")
    stab(m, b, "Lenker", [(0, 0, 24), hinten], "S355", "RO 406,4/12,5", typ="truss")
    stab(m, b, "Wippzylinder", [(0, 0, 11), J1], "S355", "RO 323,9/25", typ="truss")
    lf1 = m.case("LF1")
    lf1.category = "G"
    lf1.bezeichnung = "Eigengewicht und Gegengewicht"
    lf1.gravity = [0.0, 0.0, -9.81]
    m.load_node(b.node((-6, 0, 16)), Fz=-G, case="LF1")
    m.add_load_case("LF2", "Q_K", f"Hublast {zt(w['hublast'] / 10)} t an der Ruesselspitze", nummer=2,
                    bezeichnung="Hublast")
    m.load_node(b.node(spitze), Fz=-Q, case="LF2")
    m.add_load_case("LF3", "W", "Wind quer (+y)", nummer=3, bezeichnung="Wind quer")
    for st in ("Ausleger", "Ruessel", "Turm", "Portalbein 1", "Portalbein 2"):
        m.add_linienlast(st, [0.0, wind, 0.0], art="stab", case="LF3")
    m.load_node(b.node(spitze), Fy=0.05 * Q, case="LF3")
    kombination(m, "LK1", {"LF1": 1.35, "LF2": 1.5}, "1,35 G + 1,5 Hublast", 1)
    kombination(m, "LK2", {"LF1": 1.35, "LF2": 1.5, "LF3": 0.9}, "1,35 G + 1,5 Hublast + 0,9 Wind", 2)
    kombination(m, "LK3", {"LF1": 1.0, "LF3": 1.5}, "1,0 G + 1,5 Wind (ohne Hublast)", 3)
    return _fertig(m, (
        f"Beispielmodell, alle Werte angenommen: Portal 10 x 8 m, Hoehe 10 m, Beine Kasten 1000 x 1000 x 20, "
        f"Portal- und Drehkranztraeger Kasten 1800 x 800 x 30; Turm RO 2500/30 bis 24 m; Ausleger "
        f"{zt(L_a)} m unter {zt(w['winkel'])} Grad, Kasten 1400 x 1200 x 25, Bolzen an beiden Enden "
        f"(phi_y frei), Wippzylinder in Auslegermitte; Ruessel Kasten 1000 x 900 x 20, 12 m (4 m hinter, "
        f"8 m vor dem Auslegerkopf) unter -10 Grad; Lenker und Wippzylinder als Fachwerkstaebe; Gegengewicht "
        f"{zt(w['gegengewicht'])} kN; Hublast {zt(w['hublast'])} kN; Wind {zt(w['wind'])} kN/m quer plus 5 % "
        f"Schraeglast. Beiwerte vereinfacht nach EN 1990, nicht nach EN 13001. Werkstoff S355 vom Anwender "
        f"zu bestaetigen."))


# ---------------------------------------------------------------------------
# Foerderbandbruecke
# ---------------------------------------------------------------------------
def foerderband(w):
    n, a, hh, br = int(w["felder"]), w["feld"], w["hoehe"], w["breite"]
    q_g, wind = w["foerdergut"] * 1e3, w["wind"] * 1e3
    m = Model("Foerderbandbruecke")
    b = Bau(m)
    m.add_material(Material.steel("S355"))
    for s in (Section.from_profile("HEA 200"), Section.from_profile("HEA 140"),
              Section.from_profile("HEA 180"), Section.from_profile("HEA 120"),
              Section.from_profile("HEB 300"), Section.from_profile("HEB 200"),
              Section.pipe("RO 114,3/6,3", 0.1143, 0.0063), Section.pipe("RO 76,1/5", 0.0761, 0.005)):
        m.add_section(s)
    wk = math.radians(w["neigung"])
    es = np.array([math.cos(wk), 0, math.sin(wk)])
    eh = np.array([-math.sin(wk), 0, math.cos(wk)])
    O = np.array([0.0, 0.0, 4.0])
    U = {(k, y): O + k * a * es + np.array([0, y, 0]) for k in range(n + 1) for y in (0.0, br)}
    T = {key: p + hh * eh for key, p in U.items()}
    for y, seite in ((0.0, "links"), (br, "rechts")):
        stab(m, b, f"Untergurt {seite}", [U[k, y] for k in range(n + 1)], "S355", "HEA 200")
        stab(m, b, f"Obergurt {seite}", [T[k, y] for k in range(n + 1)], "S355", "HEA 200")
        for k in range(n + 1):
            stab(m, b, f"Pfosten {seite} {k}", [U[k, y], T[k, y]], "S355", "HEA 140")
        for k in range(n):
            p, q = (U[k, y], T[k + 1, y]) if k < n // 2 else (T[k, y], U[k + 1, y])
            stab(m, b, f"Diagonale {seite} {k + 1}", [p, q], "S355", "RO 114,3/6,3", typ="truss")
    for k in range(n + 1):
        stab(m, b, f"Quertraeger {k}", [U[k, 0.0], U[k, br]], "S355", "HEA 180")
        stab(m, b, f"Querriegel oben {k}", [T[k, 0.0], T[k, br]], "S355", "HEA 120")
    for k in range(n):
        p, q = (0.0, br) if k % 2 == 0 else (br, 0.0)
        stab(m, b, f"Windverband unten {k + 1}", [U[k, p], U[k + 1, q]], "S355", "RO 76,1/5", typ="truss")
        stab(m, b, f"Windverband oben {k + 1}", [T[k, p], T[k + 1, q]], "S355", "RO 76,1/5", typ="truss")
    lager(m, b.node(U[0, 0.0]), [0, 1, 2], "Auflager unten links")
    lager(m, b.node(U[0, br]), [0, 1, 2], "Auflager unten rechts")
    xe, ze = U[n, 0.0][0], U[n, 0.0][2]
    zq = 6.0 if ze > 7.0 else ze / 2
    for y, seite in ((0.0, "links"), (br, "rechts")):
        stab(m, b, f"Stuetze {seite}", [(xe, y, 0), (xe, y, zq), (xe, y, ze)], "S355", "HEB 300")
        lager(m, b.node((xe, y, 0)), [0, 1, 2, 3, 4, 5], f"Fuss Stuetze {seite}")
    stab(m, b, "Bock-Querriegel", [(xe, 0, zq), (xe, br, zq)], "S355", "HEB 200")
    for z0, z1 in ((0.0, zq), (zq, ze)):
        stab(m, b, f"Bockverband {z0:g} a", [(xe, 0, z0), (xe, br, z1)], "S355", "RO 114,3/6,3", typ="truss")
        stab(m, b, f"Bockverband {z0:g} b", [(xe, br, z0), (xe, 0, z1)], "S355", "RO 114,3/6,3", typ="truss")
    lf1 = m.case("LF1")
    lf1.category = "G"
    lf1.bezeichnung = "Eigengewicht, Band und Tragrollen"
    lf1.gravity = [0.0, 0.0, -9.81]
    for seite in ("links", "rechts"):
        m.add_linienlast(f"Untergurt {seite}", [0.0, 0.0, -1000.0], art="stab", case="LF1")
    m.add_load_case("LF2", "Q", f"Foerdergut {zt(2 * q_g / 1e3)} kN/m", nummer=2, bezeichnung="Foerdergut")
    for seite in ("links", "rechts"):
        m.add_linienlast(f"Untergurt {seite}", [0.0, 0.0, -q_g], art="stab", case="LF2")
    m.add_load_case("LF3", "W", "Wind quer (+y)", nummer=3, bezeichnung="Wind quer")
    for st in ("Untergurt links", "Obergurt links"):
        m.add_linienlast(st, [0.0, wind, 0.0], art="stab", case="LF3")
    for st in ("Stuetze links",):
        m.add_linienlast(st, [0.0, wind * 800.0 / 1200.0, 0.0], art="stab", case="LF3")
    kombination(m, "LK1", {"LF1": 1.35, "LF2": 1.5, "LF3": 0.9}, "1,35 G + 1,5 Foerdergut + 0,9 Wind", 1)
    kombination(m, "LK2", {"LF1": 1.35, "LF2": 1.05, "LF3": 1.5}, "1,35 G + 1,05 Foerdergut + 1,5 Wind", 2)
    return _fertig(m, (
        f"Beispielmodell, alle Werte angenommen: Fachwerkbruecke {zt(n * a)} m unter {zt(w['neigung'])} Grad, "
        f"{n} Felder zu {zt(a)} m, Hoehe {zt(hh)} m, Breite {zt(br)} m; unteres Ende auf Knotenlagern, oberes "
        f"Ende auf einem Stuetzbock (HEB 300 eingespannt, biegesteif an den Untergurt angeschlossen, "
        f"Kreuzverband). Band und Tragrollen 2 x 1 kN/m, Foerdergut 2 x {zt(w['foerdergut'])} kN/m auf den "
        f"Untergurten, Wind {zt(w['wind'])} kN/m auf der Luvseite. Werkstoff S355 vom Anwender zu bestaetigen."))


def _foerderband_pruefen(w):
    ze = 4.0 + w["felder"] * w["feld"] * math.sin(math.radians(w["neigung"]))
    return [] if ze >= 5.0 else [f"Oberes Ende nur {zt(ze)} m hoch: Neigung oder Länge größer wählen "
                                 "(mindestens 5 m für den Stützbock)"]


# ---------------------------------------------------------------------------
# Stemmtor, Hubtor, Fischbauchklappe
# ---------------------------------------------------------------------------
def stemmtor(w):
    S, H = w["breite"], w["hoehe"]
    d = 0.7
    ow, uw = w["ow"], w["uw"]
    m = Model("Stemmtor")
    b = Bau(m)
    m.add_material(Material.steel("S355"))
    th_ = w["haut"] / 1e3
    T = dicken(m, (th_, 0.012, 0.025, 0.020))
    th = math.atan(1 / 3)
    es = np.array([math.cos(th), -math.sin(th), 0.0])
    en = np.array([math.sin(th), math.cos(th), 0.0])

    def abb(s, n, z):
        return s * es + n * en + np.array([0, 0, z])
    riegel = [z * (H / 8.0) for z in (0.25, 1.35, 2.5, 3.7, 5.0, 6.4, 7.85)]
    haut = platten_raster(m, b, abb, S, H, d, riegel, 0.30, [S * i / 4 for i in (1, 2, 3)], 0.25, False,
                          T[th_], T[0.012], T[0.025], T[0.012], T[0.020])
    b.faces_anlegen()

    def an(s0, n0):
        return lambda X: abs((X @ es) - s0) < 1e-6 and abs((X @ en) - n0) < 1e-6
    linienlager(m, "Wendenische", b.linien_wo(an(0.0, d)), [0, 1])
    linienlager(m, "Stemmsaeule", b.linien_wo(an(S, d)), [0])
    lager(m, b.node(abb(0.0, d, 0.0)), [2], "Spurlager")
    lf1 = m.case("LF1")
    lf1.category = "G"
    lf1.bezeichnung = "Eigengewicht"
    lf1.gravity = [0.0, 0.0, -9.81]
    wasser(m, "Betrieb", haut, 2, ow, uw if uw > 0 else None, H, S, en,
           f"Wasser Betrieb OW {z1(ow)} m / UW {z1(uw)} m" if uw > 0
           else f"Wasser Betrieb OW {z1(ow)} m / UW trocken")
    wasser(m, "Revision", haut, 3, ow, None, H, S, en, f"Wasser Revision OW {z1(ow)} m / UW trocken")
    kombination(m, "LK1", {"LF1": 1.35, "LF2": 1.35}, "1,35 G + 1,35 Wasser Betrieb", 1)
    kombination(m, "LK2", {"LF1": 1.35, "LF3": 1.2}, "1,35 G + 1,2 Wasser Revision", 2)
    return _fertig(m, (
        f"Beispielmodell, alle Werte angenommen: ein Torfluegel {zt(S)} m breit, {zt(H)} m hoch, unter dem "
        f"Stemmwinkel 1:3 eingebaut; Haut {zt(w['haut'])} mm auf der Oberwasserseite, 7 Riegel 700 mm "
        f"(Steg 12 mm, Gurt 300 x 25 mm), Vertikalsteifen 250 x 12 mm, Wende- und Stemmsaeule als "
        f"Endschotte 20 mm. Lagerung geschlossenes Tor: Wendenische (x, y) an der Wendesaeule, Stemmsaeule "
        f"nur quer zur Kammer (Symmetrie), Spurlager z. Wasser OW {zt(ow)} m, UW {zt(uw)} m bzw. trocken. "
        f"Teilsicherheitsbeiwerte sinngemaess DIN 19704, vom Anwender festzulegen. Werkstoff S355 vom "
        f"Anwender zu bestaetigen."))


def _stau_pruefen(w):
    f = []
    if w["ow"] > w["hoehe"]:
        f.append("Oberwasser über der Torhöhe")
    if w["uw"] >= w["ow"]:
        f.append("Unterwasser muss unter dem Oberwasser liegen")
    return f


def hubtor(w):
    S, H, d = w["stuetzweite"], w["hoehe"], 1.0
    ow, uw = w["ow"], w["uw"]
    m = Model("Hubtor")
    b = Bau(m)
    m.add_material(Material.steel("S355"))
    th_ = w["haut"] / 1e3
    T = dicken(m, (th_, 0.015, 0.030, 0.025, 0.012))

    def abb(s, n, z):
        return np.array([s, n, z])
    riegel = [z * (H / 5.0) for z in (0.4, 1.7, 3.1, 4.6)]
    ns = max(1, round(S / 2.0))
    schotte = [S * i / ns for i in range(1, ns)]
    haut = platten_raster(m, b, abb, S, H, d, riegel, 0.40, schotte, 0.0, True,
                          T[th_], T[0.015], T[0.030], T[0.012], T[0.025])
    b.faces_anlegen()
    linienlager(m, "Rollenbahn links", b.linien_wo(lambda X: abs(X[0]) < 1e-6 and abs(X[1] - d) < 1e-6), [1])
    linienlager(m, "Rollenbahn rechts", b.linien_wo(lambda X: abs(X[0] - S) < 1e-6 and abs(X[1] - d) < 1e-6), [1])
    lager(m, b.node((0.0, d, H)), [2], "Hubseil links")
    lager(m, b.node((S, d, H)), [2], "Hubseil rechts")
    lager(m, b.node((0.0, 0.0, H)), [0], "Seitenfuehrung")
    lf1 = m.case("LF1")
    lf1.category = "G"
    lf1.bezeichnung = "Eigengewicht"
    lf1.gravity = [0.0, 0.0, -9.81]
    wasser(m, "Stau", haut, 2, ow, uw if uw > 0 else None, H, S, (0, 1, 0),
           f"Wasser OW {z1(ow)} m / UW {z1(uw)} m" if uw > 0
           else f"Wasser OW {z1(ow)} m / UW trocken")
    kombination(m, "LK1", {"LF1": 1.35, "LF2": 1.35}, "1,35 G + 1,35 Wasser", 1)
    return _fertig(m, (
        f"Beispielmodell, alle Werte angenommen: Stuetzweite {zt(S)} m, Hoehe {zt(H)} m, Haut "
        f"{zt(w['haut'])} mm auf der Oberwasserseite (y < 0), 4 Riegel 1,0 m (Steg 15 mm, Gurt 400 x 30 mm), "
        f"Querschotte etwa alle 2 m (12 mm), Endschotte 25 mm. Lagerung: Rollenbahnen an beiden Enden (y) an "
        f"der Unterwasserkante, Hubseile an den oberen Ecken (z), Seitenfuehrung (x). Wasser OW {zt(ow)} m, "
        f"UW {zt(uw)} m. Teilsicherheitsbeiwerte sinngemaess DIN 19704, vom Anwender festzulegen. Werkstoff "
        f"S355 vom Anwender zu bestaetigen."))


def fischbauchklappe(w):
    L, H = w["stuetzweite"], w["hoehe"]
    ow, uw = w["ow"], w["uw"]
    nseg = int(w["felder"])
    t_rand, t_mitte = w["tiefe_rand"], w["tiefe_mitte"]
    m = Model("Fischbauchklappe")
    b = Bau(m)
    m.add_material(Material.steel("S355"))
    th_ = w["haut"] / 1e3
    T = dicken(m, (th_, 0.012, 0.025))
    neig = math.radians(w["neigung"])
    eu = np.array([0.0, math.cos(neig), math.sin(neig)])
    en = np.array([0.0, math.sin(neig), -math.cos(neig)])
    a = H / math.sin(neig)
    xs = [L * i / nseg for i in range(nseg + 1)]

    def tiefe(x):
        return t_rand + (t_mitte - t_rand) * (1.0 - (2.0 * x / L - 1.0) ** 2)
    A = [np.array([x, 0.0, 0.0]) for x in xs]
    B = [p + a * eu for p in A]
    C1 = [p + 0.25 * a * eu + tiefe(p[0]) * en for p in A]
    C2 = [p + 0.75 * a * eu + tiefe(p[0]) * en for p in A]
    haut = []
    for i in range(nseg):
        nm = f"Haut {i + 1}"
        b.face(nm, [A[i], A[i + 1], B[i + 1], B[i]], "S355", T[th_])
        haut.append(nm)
        b.face(f"Bauch unten {i + 1}", [A[i], A[i + 1], C1[i + 1], C1[i]], "S355", T[0.012])
        b.face(f"Bauch Boden {i + 1}", [C1[i], C1[i + 1], C2[i + 1], C2[i]], "S355", T[0.012])
        b.face(f"Bauch oben {i + 1}", [C2[i], C2[i + 1], B[i + 1], B[i]], "S355", T[0.012])
    for i in range(nseg + 1):
        b.face(f"{'Endschott' if i in (0, nseg) else 'Schott'} {i}", [A[i], C1[i], C2[i], B[i]], "S355",
               T[0.025] if i in (0, nseg) else T[0.012])
    b.faces_anlegen()
    for nm, f in m.flaechen.items():
        if nm.startswith("Bauch"):
            f.typ = "regelflaeche"     # leicht verwunden (Bauchtiefe aendert sich je Feld)
    linienlager(m, "Drehachse", b.linien_wo(lambda X: abs(X[1]) < 1e-6 and abs(X[2]) < 1e-6), [0, 1, 2])
    lager(m, b.node(C1[0]), [1], "Zylinder links")
    lager(m, b.node(C1[-1]), [1], "Zylinder rechts")
    lf1 = m.case("LF1")
    lf1.category = "G"
    lf1.bezeichnung = "Eigengewicht"
    lf1.gravity = [0.0, 0.0, -9.81]
    wasser(m, "Stau", haut, 2, ow, uw if uw > 0 else None, H, L, en,
           f"Wasser OW {z1(ow)} m / UW {z1(uw)} m" if uw > 0
           else f"Wasser OW {z1(ow)} m / UW trocken")
    m.add_load_case("LF3", "Q", f"Eisdruck {zt(w['eis'])} kN/m an der Oberkante (+y)", nummer=3,
                    bezeichnung="Eis")
    for ln in b.linien_wo(lambda X: abs(X[2] - H) < 1e-6):
        m.add_linienlast(ln, [0.0, w["eis"] * 1e3, 0.0], art="linie", case="LF3")
    kombination(m, "LK1", {"LF1": 1.35, "LF2": 1.35}, "1,35 G + 1,35 Wasser", 1)
    kombination(m, "LK2", {"LF1": 1.35, "LF2": 1.35, "LF3": 1.5}, "1,35 G + 1,35 Wasser + 1,5 Eis", 2)
    return _fertig(m, (
        f"Beispielmodell, alle Werte angenommen: Stuetzweite {zt(L)} m, Stauhoehe {zt(H)} m, Klappe unter "
        f"{zt(w['neigung'])} Grad; Haut {zt(w['haut'])} mm, Fischbauch als geschlossenes Trapez (Bauchboden "
        f"zwischen 1/4 und 3/4 der Hautlaenge), Bauchtiefe {zt(t_rand)} m an den Enden bis {zt(t_mitte)} m in "
        f"der Mitte (Parabel), {nseg} Felder, Schotte 12 mm, Endschotte 25 mm. Lagerung: Drehachse am Fuss "
        f"(x, y, z), Zylinder an beiden Endschotten an der unteren Bauchkante (y). Wasser OW {zt(ow)} m, UW "
        f"{zt(uw)} m; Eisdruck {zt(w['eis'])} kN/m. Teilsicherheitsbeiwerte sinngemaess DIN 19704, vom "
        f"Anwender festzulegen. Werkstoff S355 vom Anwender zu bestaetigen."))


# ---------------------------------------------------------------------------
# Spurlager (Volumen)
# ---------------------------------------------------------------------------
def spurlager(w):
    m = Model("Spurlager")
    m.add_material(Material.steel("S355"))
    mat = "S355"
    R1, h1 = 0.30, 0.10
    rz, hz = w["zapfen"] / 2e3, 0.25
    ri, ra = rz + w["spiel"] / 1e3, 0.20
    zu, zo = 0.15, 0.33
    N, Hk = w["torgewicht"] * 1e3, w["horizontal"] * 1e3
    k0 = kreis(m, "SP_K0_", R1, 0.0)
    k1 = kreis(m, "SP_K1_", R1, h1)
    z1 = kreis(m, "ZA_K1_", rz, h1)
    z2 = kreis(m, "ZA_K2_", rz, hz)
    m.add_flaeche("Spurplatte Boden", k0[2], material=mat)
    sp_m = mantel(m, "Spurplatte Mantel", k0, k1, mat)
    f = m.add_flaeche("Spurplatte oben", k1[2], material=mat)
    f.oeffnungen = [list(z1[2])]
    za_m = mantel(m, "Zapfen Mantel", z1, z2, mat)
    m.add_flaeche("Zapfen Kopf", z2[2], material=mat)
    m.add_koerper("Spurplatte", ["Spurplatte Boden", *sp_m, "Spurplatte oben", *za_m, "Zapfen Kopf"],
                  material=mat)
    p0a = kreis(m, "PF_A0_", ra, zu)
    p1a = kreis(m, "PF_A1_", ra, zo)
    p0i = kreis(m, "PF_I0_", ri, zu)
    p1i = kreis(m, "PF_I1_", ri, hz)
    f = m.add_flaeche("Pfanne unten", p0a[2], material=mat)
    f.oeffnungen = [list(p0i[2])]
    pa_m = mantel(m, "Pfanne Mantel aussen", p0a, p1a, mat)
    pi_m = mantel(m, "Pfanne Bohrung", p0i, p1i, mat)
    m.add_flaeche("Pfanne Bohrungsgrund", p1i[2], material=mat)
    m.add_flaeche("Pfanne Deckel", p1a[2], material=mat)
    m.add_koerper("Spurpfanne", ["Pfanne unten", *pa_m, *pi_m, "Pfanne Bohrungsgrund", "Pfanne Deckel"],
                  material=mat)
    kb = m.add_kontaktbedingung("Pfanne auf Zapfen", koerpernamen=["Spurpfanne"], gegenkoerper=["Spurplatte"],
                                flaechennamen=[*pi_m, "Pfanne Bohrungsgrund"],
                                gegenflaechen=[*za_m, "Zapfen Kopf"],
                                suchweite=0.01, start_geschlossen=True)
    kb.standard_anwenden("Reibungsbehaftet", mu=w["mu"])
    ss = m.add_surface_support(name="Spurplatte im Beton")
    ss.flaechen = ["Spurplatte Boden"]
    for dd in (0, 1, 2):
        ss.behaviour[dd] = DofBehaviour("rigid")
    lager(m, p1a[0], [1], "Verdrehsicherung Pfanne")
    A = math.pi * ra ** 2
    lf1 = m.case("LF1")
    lf1.category = "G"
    lf1.bezeichnung = f"Torgewicht {zt(w['torgewicht'])} kN"
    lf1.gravity = [0.0, 0.0, -9.81]
    m.add_geometrielast("Pfanne Deckel", N / A, "flaeche", case="LF1")
    m.add_load_case("LF2", "G", f"Betrieb: Torgewicht {zt(w['torgewicht'])} kN und Horizontalkraft "
                    f"{zt(w['horizontal'])} kN in +x", nummer=2, bezeichnung="Betrieb")
    m.case("LF2").gravity = [0.0, 0.0, -9.81]
    m.add_geometrielast("Pfanne Deckel", N / A, "flaeche", case="LF2")
    m.add_geometrielast("Pfanne Deckel", Hk / A, "flaeche", richtung=[1.0, 0.0, 0.0], case="LF2")
    kombination(m, "LK1", {"LF2": 1.35}, "1,35 Betrieb", 1)
    return _fertig(m, (
        f"Beispielmodell, alle Werte angenommen: Spurplatte D 600 x 100 mm mit Zapfen D {zt(w['zapfen'])} mm "
        f"bis 250 mm Hoehe (ein Stueck); Spurpfanne aussen D 400 mm, 180 mm hoch, Bohrung D "
        f"{zt(2 * ri * 1e3)} mm ({zt(w['spiel'])} mm Spiel am Radius) und 100 mm tief, 50 mm Luft unter der "
        f"Pfanne. Kontakt Pfanne auf Zapfen reibungsbehaftet mu = {zt(w['mu'])}, Start geschlossen, Suchweite "
        f"10 mm. Lagerung: Spurplatte unten fest, Pfanne an einem Punkt gegen Verdrehen um z (y). Torgewicht "
        f"{zt(w['torgewicht'])} kN und Horizontalkraft {zt(w['horizontal'])} kN als Flaechenlast auf dem "
        f"Pfannendeckel. Flacher Zapfenkopf statt Kugelkalotte. Werkstoff S355 vom Anwender festzulegen "
        f"(Pfanne in der Regel Bronze oder Stahlguss)."))
