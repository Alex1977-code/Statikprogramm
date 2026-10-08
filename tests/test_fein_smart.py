"""
Smartes Fein: Flaechen und Boegen (Paket F1, 07.10.2026).

Auftrag des Anwenders vom 07.10.2026: „wir brauchen einen smarten Vernetzer,
der mit Feinheiten und Kontakten umgehen kann“ (Bauplan
PLAN-FEIN-SMART-2026-10-07.md). Entscheidungen vom 07.10.2026:

* Fein = Mittel im Feld plus Quellen im Groessenfeld (statik3d.netzfeld) an
  Kontakt-, Lager- und Lastflaechen: halbe Kantenlaenge, eine Elementlage,
  von dort Wachstum 0,35 je m. Die Halbierung ueberall entfaellt.
* Bohrungen und Kerben: „Alle an Kontakt- und Lagerflaechen vorab“ - jeder
  Bogen einer Kontakt- oder Lagerflaeche (und der Bohrungswaende und Radien,
  die an sie grenzen) bekommt 9 statt 18 Grad je Abschnitt; Boegen ohne
  Kontakt oder Lager bleiben wie bei Mittel.
* Wird das Netz zu gross, vergroebert das Paket F2 selbsttaetig ueber die
  Stufen k = 0, 1, 2, ... (elementstufe.fein_stufe); die letzte ist Mittel.

Geprueft wird ueber den echten Weg (elementstufe.beim_vernetzen und
mesher.modell_vernetzen, eigener Vernetzer, Tetraeder). Fein ist an
Kontaktmodellen noch gesperrt (elementstufe.quadratisch_gesperrt); fuer die
Netzgeometrie wird die Sperre **nur hier im Test** kurz aufgehoben, gerechnet
wird an Kontaktmodellen nichts. Gerechnet wird am Modell ohne Kontakt und
ohne Flaechenlager (Lastflaeche, Knotenlager, freie Bohrung).

Kriterien (vor dem Bau festgelegt):
  * Randkante an Kontakt-, Lager- und Lastflaechen (Median) h/2 +- 20 %,
    fern davon wie Mittel +- 10 %;
  * Segmentwinkel an der Bohrung mit Kontakt <= 9 Grad + 0,5 Grad, an der
    freien Bohrung wie Mittel;
  * Quellen auf einer Zylinderflaeche hoechstens 1 % von h neben der Flaeche;
  * Mittel und Entwurf bitgleich zum Stand f3fe832 (Netz-Hash);
  * am Modell ohne Kontakt: Fein ist an der Lastflaeche feiner und rechnet.

Aufruf:  python -m tests.test_fein_smart
"""
import hashlib
import os
import sys
import tempfile
from contextlib import contextmanager, nullcontext

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_fein_smart_"), "einstellungen.json")

import numpy as np  # noqa: E402

from statik3d.model import DofBehaviour  # noqa: E402
from tests.test_elementstufe import fuge  # noqa: E402
from tests.test_netzfeld import platte_mit_bohrungen  # noqa: E402

RESULTS = []

#: Kantenlaenge von Mittel an den Bloecken und an der Platte [m]
H_BLOCK = 0.1
H_PLATTE = 0.05

#: Netz-Hash von Mittel und Entwurf am Stand f3fe832 (vor F1), gemessen am
#: 07.10.2026 mit diesem Test (Windows, ein Arbeitsprozess). Mittel und
#: Entwurf muessen nach F1 bitgleich bleiben.
HASH_F3FE832 = {
    ("platte", "mittel"): "445a614bc6c0d902",
    ("platte", "entwurf"): "fe75528e0bf6d404",
    # Seit Q2 (08.10.2026) trennt die Fuge auch die Seitenmitten: das Mittel-Netz
    # des Kontaktmodells hat mehr Knoten (36 673, gemessen auf cc4dc5c); Q1 setzt
    # dort keine Mitte um (gleicher Hash mit Q1). Am Stand f3fe832: 832867fa2368b9b8
    ("bloecke", "mittel"): "b4c798f62895464e",
    ("bloecke", "entwurf"): "9bacd6a952210984",
}


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FAIL'} {name:84s} {str(detail)[:160]}")
    return ok


def _es():
    from statik3d import elementstufe
    return elementstufe


# --------------------------------------------------------------------------
# Pruefkoerper
# --------------------------------------------------------------------------
#: Grundriss der Bloecke: ein Fuenfeck (Quadrat 1 x 1 m mit abgeschnittener
#: Ecke). Ein Quader ginge in den abgebildeten Weg (hex20 nach Teilung) und
#: folgte dem Groessenfeld nicht; Gegenstand ist der Tetraederweg.
GRUNDRISS = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.4, 1.0), (0.0, 0.6)]


def bloecke():
    """Block auf Block (Fuenfeckprismen je 1 m hoch): Kontaktbedingung an der
    Fuge (z = 1, Druck, Abheben), Flaechenlager am Boden (z = 0), Last auf
    dem Dach (z = 2). Die Seitenwaende tragen nichts."""
    from statik3d.model import Material, Model
    m = Model("Block auf Block")
    m.add_material(Material.steel("S235"))
    n = len(GRUNDRISS)
    kn = [[m.add_node(x, y, z) for x, y in GRUNDRISS] for z in (0.0, 1.0, 2.0)]
    for lage in range(3):
        for i in range(n):
            m.add_line(f"R{lage}_{i}", [kn[lage][i], kn[lage][(i + 1) % n]])
    for lage in range(2):
        for i in range(n):
            m.add_line(f"V{lage}_{i}", [kn[lage][i], kn[lage + 1][i]])
    m.add_flaeche("Boden", [f"R0_{i}" for i in range(n)], material="S235")
    m.add_flaeche("Fuge", [f"R1_{i}" for i in range(n)], material="S235")
    m.add_flaeche("Dach", [f"R2_{i}" for i in range(n)], material="S235")
    for lage, tag in ((0, "MU"), (1, "MO")):
        for i in range(n):
            j = (i + 1) % n
            m.add_flaeche(f"{tag}{i}", [f"R{lage}_{i}", f"V{lage}_{j}", f"R{lage + 1}_{i}", f"V{lage}_{i}"],
                          material="S235")
    m.add_koerper("Unten", ["Boden", "Fuge"] + [f"MU{i}" for i in range(n)], material="S235")
    m.add_koerper("Oben", ["Fuge", "Dach"] + [f"MO{i}" for i in range(n)], material="S235")
    m.netz.dichte = "eigene"
    m.netz.ziellaenge = H_BLOCK
    fuge(m)
    ss = m.add_surface_support(name="Boden fest", ux=dict(typ="rigid"), uy=dict(typ="rigid"),
                               uz=dict(typ="rigid"))
    ss.flaechen = ["Boden"]
    m.add_load_case("LF1")
    m.case("LF1").gravity = [0.0, 0.0, 0.0]
    m.add_geometrielast("Dach", 1.0e6, "flaeche", case="LF1")
    m.active_case = "LF1"
    return m


#: Bohrungen der Platte: B1 mit Kontakt (Bolzen), B2 frei
B1 = (0.3, 0.3, 0.06)
B2 = (0.75, 0.3, 0.04)


def platte_kontakt():
    """Platte 1 x 0,6 x 0,2 m mit zwei Bohrungen: die Wand von B1 ist
    Kontaktflaeche (Bolzen), B2 ist frei; Flaechenlager an M4 (x = 0), Zug
    an M2 (x = 1)."""
    m, _k = platte_mit_bohrungen(bohrungen=(B1, B2))
    m.add_kontaktbedingung("Bolzen", flaechennamen=["B1Mantel1", "B1Mantel2"])
    m.add_load_case("LF1")
    m.case("LF1").gravity = [0.0, 0.0, 0.0]
    m.add_geometrielast("M2", -100e6, "flaeche", richtung=[1.0, 0.0, 0.0], case="LF1")
    m.active_case = "LF1"
    ss = m.add_surface_support(name="Einspannung")
    ss.flaechen = ["M4"]
    for d in (0, 1, 2):
        ss.behaviour[d] = DofBehaviour("rigid")
    m.netz.dichte = "eigene"
    m.netz.ziellaenge = H_PLATTE
    return m


def platte_ohne_kontakt():
    """Dieselbe Platte mit einer freien Bohrung, Zug an M2 (x = 1); gelagert
    wird nach dem Vernetzen ueber Knotenlager an x = 0 - ohne Kontakt und
    ohne Flaechenlager, also an Fein nicht gesperrt."""
    m, _k = platte_mit_bohrungen(bohrungen=(B1,))
    m.add_load_case("LF1")
    m.case("LF1").gravity = [0.0, 0.0, 0.0]
    m.add_geometrielast("M2", -100e6, "flaeche", richtung=[1.0, 0.0, 0.0], case="LF1")
    m.active_case = "LF1"
    m.netz.dichte = "eigene"
    m.netz.ziellaenge = H_PLATTE
    return m


@contextmanager
def ohne_sperre():
    """Die Sperre quadratischer Elemente an Kontaktmodellen **nur fuer den
    Test** aufheben (wie die Messung fein_werk/vernetzen_smart.py): so laesst
    sich die Netzgeometrie von Fein an einem Kontaktmodell pruefen. Gerechnet
    wird damit nichts."""
    from statik3d import fugen
    es = _es()
    alt_q, alt_s = es.quadratisch_gesperrt, fugen.quadratische_seiten_sperren
    es.quadratisch_gesperrt = lambda model: []
    fugen.quadratische_seiten_sperren = lambda *a, **k: None
    try:
        yield
    finally:
        es.quadratisch_gesperrt, fugen.quadratische_seiten_sperren = alt_q, alt_s


def vernetzen(m, stufe: str, sperre_aus: bool = False, k: int = None) -> list:
    """Wie Netz -> Vernetzen ohne Oberflaeche, im Tetraederweg (Sweep aus);
    Rueckgabe das Protokoll. ``k``: Vergroeberungsstufe fuer F2 (None = wie
    die Oberflaeche aufruft)."""
    from statik3d import mesher
    es = _es()
    m.netz = es.setzen(m.netz, stufe)
    m.netz.sweep = "aus"                  # Gegenstand ist der Tetraederweg
    log: list = []
    with (ohne_sperre() if sperre_aus else nullcontext()):
        ctx = es.beim_vernetzen(m, log) if k is None else es.beim_vernetzen(m, log, k=k)
        with ctx:
            mesher.modell_vernetzen(m, log, workers=1)
    return log


def netz_hash(m) -> str:
    """Bitgenauer Fingerabdruck des Netzes: Knotenkoordinaten, Elementtypen
    und Knotenfolgen."""
    s = hashlib.sha256()
    s.update(np.ascontiguousarray(np.asarray(m.nodes, float)).tobytes())
    for e in m.elements:
        s.update(e.typ.encode())
        s.update(np.asarray([int(x) for x in e.nodes], np.int64).tobytes())
    return s.hexdigest()[:16]


def randkanten(m, flaechen) -> tuple:
    """Kanten der Randseiten (Ecken) auf diesen Flaechen: (Laengen, Mitten)."""
    from statik3d.elements import solid as sl
    L, Z = [], []
    for fn in flaechen:
        for ei, s in (m.flaechen[fn].randseiten or []):
            e = m.elements[int(ei)]
            ecken = [int(e.nodes[c]) for c in sl.FLAECHEN_ECKEN[e.typ][int(s)]]
            P = np.asarray(m.nodes, float)[ecken]
            for a in range(len(P)):
                b = (a + 1) % len(P)
                L.append(float(np.linalg.norm(P[a] - P[b])))
                Z.append(0.5 * (P[a] + P[b]))
    return np.asarray(L), np.asarray(Z).reshape(-1, 3)


def bogenluecke(m, bohrung, z: float) -> tuple:
    """Groesste Winkelluecke [Grad] zwischen den Eckknoten des Netzes auf dem
    Kreis der Bohrung in der Hoehe z - und ihre Zahl. Nur Eckknoten: die
    Seitenmitten der tet10 liegen ebenfalls auf dem Kreis."""
    cx, cy, r = bohrung
    ecken = sorted({int(x) for e in m.elements for x in e.nodes[:4]})
    X = np.asarray(m.nodes, float)[ecken]
    rho = np.hypot(X[:, 0] - cx, X[:, 1] - cy)
    auf = (np.abs(rho - r) < 1e-6 * max(r, 1.0)) & (np.abs(X[:, 2] - z) < 1e-9)
    w = np.sort(np.degrees(np.arctan2(X[auf, 1] - cy, X[auf, 0] - cx)))
    if len(w) < 2:
        return 360.0, int(auf.sum())
    luecken = np.diff(np.concatenate([w, w[:1] + 360.0]))
    return float(luecken.max()), int(auf.sum())


# --------------------------------------------------------------------------
# 1) Block auf Block: Flaechen fein, Feld wie Mittel
# --------------------------------------------------------------------------
_NETZE = {}


def _bloecke_vernetzt(stufe: str):
    if stufe not in _NETZE:
        m = bloecke()
        log = vernetzen(m, stufe, sperre_aus=True)
        _NETZE[stufe] = (m, log)
    return _NETZE[stufe]


def test_bloecke_flaechen():
    mm, _ = _bloecke_vernetzt("mittel")
    mf, log = _bloecke_vernetzt("fein")
    check("Block auf Block: Mittel und Fein vernetzt (tet10)",
          mm.elements and mf.elements and {e.typ for e in mf.elements} == {"tet10"},
          f"Mittel {len(mm.elements)}, Fein {len(mf.elements)} Elemente")
    h_f = 0.5 * H_BLOCK
    for fn, was in (("Fuge", "Kontaktfläche"), ("Boden", "Flächenlager"), ("Dach", "Lastfläche")):
        L, _ = randkanten(mf, [fn])
        Lm, _ = randkanten(mm, [fn])
        med = float(np.median(L)) if len(L) else 0.0
        check(f"{was} {fn}: Randkante (Median) h/2 ± 20 % = {h_f * 1e3:.0f} mm ± 20 %",
              len(L) and 0.8 * h_f <= med <= 1.2 * h_f,
              f"Fein {med * 1e3:.1f} mm, Mittel {float(np.median(Lm)) * 1e3:.1f} mm")
    seiten = [f"MU{i}" for i in range(len(GRUNDRISS))] + [f"MO{i}" for i in range(len(GRUNDRISS))]

    def fern(m):
        L, Z = randkanten(m, seiten)
        z = Z[:, 2]
        sel = ((z > 0.4) & (z < 0.6)) | ((z > 1.4) & (z < 1.6))
        return float(np.median(L[sel])) if sel.any() else 0.0
    lf, lm = fern(mf), fern(mm)
    check("fern der Flächen (Seitenwände, 0,4 m Abstand): Randkante wie Mittel ± 10 %",
          lm > 0 and 0.9 <= lf / lm <= 1.1, f"Fein {lf * 1e3:.1f} mm, Mittel {lm * 1e3:.1f} mm")
    zeile = next((z for z in log if str(z).startswith("Elemente Fein")), "")
    check("Protokoll nennt die verfeinerten Flächen nach Art (Kontakt, Lager, Last)",
          "3 Flächen" in zeile and "Kontakt" in zeile and "Lager" in zeile and "Last" in zeile, zeile)
    check("… und die Kantenlänge daran (50 mm statt 100 mm)", "50 mm" in zeile and "100 mm" in zeile, zeile)
    check("… und dass keine Bögen verfeinert werden", "0 Bögen" in zeile or "keine Bögen" in zeile, zeile)


# --------------------------------------------------------------------------
# 2) Platte mit Bohrung an Kontakt und freier Bohrung
# --------------------------------------------------------------------------
def test_bohrungen():
    mm = platte_kontakt()
    vernetzen(mm, "mittel", sperre_aus=True)
    mf = platte_kontakt()
    log = vernetzen(mf, "fein", sperre_aus=True)
    for z in (0.0, 0.2):
        g_f, n_f = bogenluecke(mf, B1, z)
        g_m, n_m = bogenluecke(mm, B1, z)
        check(f"Bohrung mit Kontakt (z = {z:.1f} m): Segmentwinkel ≤ 9° + 0,5°",
              g_f <= 9.5, f"Fein {g_f:.2f}° ({n_f} Knoten), Mittel {g_m:.2f}° ({n_m} Knoten)")
        g_f, n_f = bogenluecke(mf, B2, z)
        g_m, n_m = bogenluecke(mm, B2, z)
        check(f"freie Bohrung (z = {z:.1f} m): wie Mittel (gleiche Teilung)",
              n_f == n_m and abs(g_f - g_m) < 0.5, f"Fein {g_f:.2f}° ({n_f}), Mittel {g_m:.2f}° ({n_m})")
    zeile = next((z for z in log if str(z).startswith("Elemente Fein")), "")
    check("Protokoll nennt 4 Bögen mit 9°", "4 Bögen" in zeile and "9°" in zeile, zeile)
    L, _ = randkanten(mf, ["B1Mantel1", "B1Mantel2"])
    Lm, _ = randkanten(mm, ["B1Mantel1", "B1Mantel2"])
    check("Bohrungswand mit Kontakt: feiner als bei Mittel",
          len(L) and float(np.median(L)) < 0.8 * float(np.median(Lm)),
          f"Fein {float(np.median(L)) * 1e3:.1f} mm, Mittel {float(np.median(Lm)) * 1e3:.1f} mm")


def test_quellen_auf_zylinder():
    """Die Abtastung einer Flaeche liegt auf der wahren, auch gekruemmten
    Flaeche (bis 07.10.2026: Gitter in der Ausgleichsebene)."""
    from statik3d import netzfeld
    m = platte_kontakt()
    cx, cy, r = B1
    h_f = 0.5 * H_PLATTE
    for fn in ("B1Mantel1", "B1Mantel2"):
        P = np.asarray(netzfeld._flaechenpunkte(m, m.flaechen[fn], h_f), float)
        rho = np.hypot(P[:, 0] - cx, P[:, 1] - cy)
        abw = float(np.abs(rho - r).max()) if len(P) else 1.0
        check(f"{fn}: alle Quellen höchstens 1 % von h neben der Zylinderfläche",
              len(P) and abw <= 0.01 * h_f, f"{len(P)} Punkte, größte Abweichung {abw * 1e3:.3f} mm "
                                            f"(Grenze {0.01 * h_f * 1e3:.2f} mm)")
        # ... und sie decken die Flaeche: jeder Punkt der wahren Flaeche hat
        # eine Quelle hoechstens im Abstand der Abtastweite
        y_seite = 1.0 if fn.endswith("1") else -1.0
        w = np.linspace(0.0, np.pi, 61)
        zz = np.linspace(0.0, 0.2, 21)
        W, Z = np.meshgrid(w, zz, indexing="ij")
        Q = np.column_stack([cx - r * np.cos(W.ravel()), cy + y_seite * r * np.sin(W.ravel()), Z.ravel()])
        from scipy.spatial import cKDTree
        d = cKDTree(P).query(Q)[0] if len(P) else np.array([1.0])
        check(f"{fn}: die Quellen decken die ganze Wand (Abstand ≤ Abtastweite)",
              float(d.max()) <= h_f * (1 + 1e-9), f"größter Abstand {float(d.max()) * 1e3:.1f} mm")


def test_feld_an_der_wand():
    """Das Feld von Fein an der Bohrungswand mit Kontakt: ueberall hoechstens
    h_F, an den Boegen h_B = r * 9 Grad."""
    from statik3d import netzfeld
    es = _es()
    m = platte_kontakt()
    m.netz = es.setzen(m.netz, "fein")
    with ohne_sperre():
        w = es.wirksam(m.netz, m)
    m.netz = w
    feld = netzfeld.aufbauen(m)
    cx, cy, r = B1
    h_f = 0.5 * H_PLATTE
    w_ = np.linspace(0.05, np.pi - 0.05, 30)
    Q = np.column_stack([cx - r * np.cos(w_), cy + r * np.sin(w_), np.full(len(w_), 0.1)])
    v = feld(Q) if feld is not None else np.full(len(Q), np.inf)
    check("Feld auf der Bohrungswand (halbe Höhe) höchstens h_F = 25 mm",
          float(np.max(v)) <= h_f * (1 + 1e-9), f"max {float(np.max(v)) * 1e3:.2f} mm")
    Qb = np.column_stack([cx - r * np.cos(w_), cy + r * np.sin(w_), np.zeros(len(w_))])
    vb = feld(Qb) if feld is not None else np.full(len(Qb), np.inf)
    h_b = r * np.radians(9.0)
    check("Feld am Bogen h_B = r · 9° (± 10 %)", float(np.max(vb)) <= 1.1 * h_b,
          f"max {float(np.max(vb)) * 1e3:.2f} mm, h_B {h_b * 1e3:.2f} mm")
    Qf = np.array([[B2[0] - B2[2], B2[1], 0.0], [B2[0] + B2[2], B2[1], 0.1]])
    vf = feld(Qf) if feld is not None else np.full(len(Qf), np.inf)
    check("an der freien Bohrung wirkt das Feld nicht (≥ Mittel 50 mm)", float(np.min(vf)) >= H_PLATTE,
          f"min {float(np.min(vf)) * 1e3:.1f} mm")
    check("die freie Bohrung bekommt keinen feineren Bogenwinkel",
          feld is not None and "B2U1" not in getattr(feld, "feine_linien", {})
          and getattr(feld, "feine_linien", {}).get("B1U1") == 9.0,
          str(sorted(getattr(feld, "feine_linien", {}) or {}))[:120] if feld is not None else "kein Feld")


# --------------------------------------------------------------------------
# 3) Mittel und Entwurf bitgleich, Texte
# --------------------------------------------------------------------------
def test_mittel_entwurf_bitgleich():
    for modell, bauen, sperre in (("platte", platte_ohne_kontakt, False), ("bloecke", bloecke, True)):
        for stufe in ("mittel", "entwurf"):
            if modell == "bloecke" and stufe == "mittel":
                m = _bloecke_vernetzt("mittel")[0]
            else:
                m = bauen()
                vernetzen(m, stufe, sperre_aus=sperre)
            h = netz_hash(m)
            soll = HASH_F3FE832[(modell, stufe)]
            check(f"{modell} {stufe}: Netz bitgleich zum Stand f3fe832",
                  soll and h == soll, f"{h} (f3fe832: {soll or '-'}), {len(m.elements)} Elemente, {m.nn} Knoten")


def test_texte():
    es = _es()
    check("Elemente Fein: wie Mittel, feiner an Kontakt, Lagern, Lasten und Bögen – keine halbe Kantenlänge",
          all(x in es.ELEMENTE["fein"] for x in ("wie Mittel", "Kontakt", "Lager", "Last", "Bögen"))
          and "halbe" not in es.ELEMENTE["fein"], es.ELEMENTE["fein"])
    m = bloecke()
    t = es.kantenlaenge_text(es.setzen(m.netz, "fein"), m)
    check("Maske (wirksame Kantenlänge) nennt bei Fein, was verfeinert wird",
          "Kontakt" in t and "Lager" in t and "Last" in t and "50 mm" in t and "100 mm" in t, t)
    m2 = platte_kontakt()
    t2 = es.kantenlaenge_text(es.setzen(m2.netz, "fein"), m2)
    check("… an der Platte mit Bohrungen auch die Bögen mit 9°", "4 Bögen" in t2 and "9°" in t2, t2)
    m3 = platte_ohne_kontakt()
    m3.load_cases.clear()
    t3 = es.kantenlaenge_text(es.setzen(m3.netz, "fein"), m3)
    check("… ohne Kontakt, Lager und Last: Fein wie Mittel, gesagt", "wie Mittel" in t3, t3)


# --------------------------------------------------------------------------
# 4) Ohne Kontakt: Fein ist an der Lastflaeche feiner und rechnet
# --------------------------------------------------------------------------
def test_rechnen_ohne_kontakt():
    from statik3d import solver
    es = _es()
    zahlen = {}
    for stufe in ("mittel", "fein"):
        m = platte_ohne_kontakt()
        check(f"{stufe}: Modell ohne Kontakt ist nicht gesperrt", es.frei(m, stufe))
        vernetzen(m, stufe)
        L, _ = randkanten(m, ["M2"])
        X = np.asarray(m.nodes, float)
        benutzt = np.zeros(m.nn, bool)
        benutzt[[int(x) for e in m.elements for x in e.nodes]] = True
        lager = np.flatnonzero(benutzt & (np.abs(X[:, 0]) < 1e-9))
        for i in lager:
            m.fix(int(i), [0, 1, 2])
        m.lasten_verteilen()
        try:
            r = solver.solve_static(m, case="LF1")
            Rx = float(r.reactions[lager, 0].sum())
            u = float(np.abs(np.asarray(r.u)[:, 0]).max())
            ok, txt = True, f"Rx = {Rx / 1e6:.4f} MN, max |ux| = {u * 1e3:.4f} mm"
        except Exception as ex:      # noqa: BLE001
            Rx, ok, txt = 0.0, False, f"{type(ex).__name__}: {ex}"
        zahlen[stufe] = (float(np.median(L)), len(m.elements), m.nn, Rx)
        F = 100e6 * 0.6 * 0.2
        check(f"{stufe}: gerechnet, das Lager trägt den Zug (12 MN)", ok and abs(abs(Rx) - F) < 1e-6 * F, txt)
    (lm, em, nm, _), (lf, ef, nf, _) = zahlen["mittel"], zahlen["fein"]
    check("Fein ist an der Lastfläche feiner: Randkante h/2 ± 20 % statt h",
          0.8 * 0.5 * H_PLATTE <= lf <= 1.2 * 0.5 * H_PLATTE and lf < 0.8 * lm,
          f"Fein {lf * 1e3:.1f} mm ({ef} Elemente, {nf} Knoten), Mittel {lm * 1e3:.1f} mm ({em}, {nm})")


# --------------------------------------------------------------------------
# 5) Schnittstelle fuer F2: Vergroeberungsstufen
# --------------------------------------------------------------------------
def test_vergroeberung_f2():
    es = _es()
    soll = [(9.0, 0.5), (12.0, 0.5), (18.0, 0.5), (18.0, 1.0 / 1.5), (18.0, 1.0)]
    ist = [(es.fein_stufe(k).bogenwinkel, es.fein_stufe(k).flaechenfaktor) for k in range(len(soll))]
    check("fein_stufe(k): 9° → 12° → 18°, dann h/2 → h/1,5 → h",
          all(abs(a - c) < 1e-12 and abs(b - d) < 1e-12 for (a, b), (c, d) in zip(ist, soll)), str(ist))
    check("… die letzte Stufe ist Mittel, darüber bleibt es dabei",
          es.fein_stufe(len(soll) - 1).letzte and es.fein_stufe(len(soll) - 1).ist_mittel
          and es.fein_stufe(len(soll) + 3) == es.fein_stufe(len(soll) - 1)
          and not es.fein_stufe(0).letzte and es.FEIN_STUFEN_ANZAHL == len(soll))
    m = platte_kontakt()
    f = es.setzen(m.netz, "fein")
    with ohne_sperre():
        w1 = es.wirksam(f, m, k=1)
        w4 = es.wirksam(f, m, k=4)
    boegen = [v for v in w1.verfeinerungen if v.get("art") == "fein_bogen"]
    check("Stufe 1: die Bögen mit 12°", boegen and all(v.get("winkel") == 12.0 for v in boegen),
          str(boegen[:1]))
    check("Stufe 4 (Mittel): keine Quellen von Fein",
          not [v for v in w4.verfeinerungen if str(v.get("art", "")).startswith("fein_")])
    # Mit der letzten Stufe vernetzt: dasselbe Netz wie Mittel
    m1 = platte_ohne_kontakt()
    vernetzen(m1, "mittel")
    m2 = platte_ohne_kontakt()
    log = vernetzen(m2, "fein", k=es.FEIN_STUFEN_ANZAHL - 1)
    check("Fein in der letzten Stufe vernetzt bitgleich wie Mittel", netz_hash(m1) == netz_hash(m2),
          f"{netz_hash(m1)} / {netz_hash(m2)}")
    check("… und das Protokoll sagt die Stufe", any("Stufe 4" in str(z) for z in log),
          next((str(z) for z in log if str(z).startswith("Elemente Fein")), ""))


# --------------------------------------------------------------------------
# 6) Anschluss an F2 (08.10.2026): Fein vergroebert selbsttaetig ueber die
#    Stufen, wenn das Netz die Grenze in Unbekannten ueberschreitet
# --------------------------------------------------------------------------
#: Zahlen der Referenzen ohne Grenze, je Lauf einmal gemessen
_GRENZE = {}


class _Laeufe:
    """Haelt fest, wie jeder Lauf einer Stufe (mesher._koerper_lauf) begann -
    Elemente, Knoten, Elemente der Koerper und der Text ``quelle`` der
    Netzeinstellungen, mit denen er lief - und was er zurueckgab."""

    def __init__(self):
        from statik3d import mesher
        self.mesher = mesher
        self.echt = getattr(mesher, "_koerper_lauf", None)
        self.zu_beginn = []
        self.ergebnisse = []

    def __enter__(self):
        if self.echt is not None:
            def lauf(model, koerper, *a, **k):
                self.zu_beginn.append((len(model.elements), int(model.nn),
                                       sum(len(x.elemente or []) for x in koerper),
                                       str(getattr(model.netz, "quelle", "") or "")))
                aus = self.echt(model, koerper, *a, **k)
                self.ergebnisse.append(dict(aus))
                return aus
            self.mesher._koerper_lauf = lauf
        return self

    def __exit__(self, *a):
        if self.echt is not None:
            self.mesher._koerper_lauf = self.echt


def _zahl(n) -> str:
    from statik3d.zahlen import zahl_text
    return zahl_text(int(n))


def _referenz(bauen, stufe: str, k: int = None, sperre_aus: bool = False) -> tuple:
    """(Netz-Hash, Unbekannte) ohne Grenze - Fein in der Stufe k ueber den
    Weg von F1 (elementstufe.beim_vernetzen mit k)."""
    schluessel = (bauen.__name__, stufe, k)
    if schluessel not in _GRENZE:
        m = bauen()
        m.netz.hoechstens_unbekannte = 0
        vernetzen(m, stufe, sperre_aus=sperre_aus, k=k)
        _GRENZE[schluessel] = (netz_hash(m), 3 * m.nn)
    return _GRENZE[schluessel]


def vernetzen_mit_grenze(m, grenze: int, sperre_aus: bool = False) -> tuple:
    """Fein mit der Grenze ``grenze`` wie ``statik3d --vernetzen`` (cli.py):
    beim_vernetzen und die Stufen von Fein (elementstufe.fein_stufen) an
    mesher.modell_vernetzen. Rueckgabe (Ergebnis, Protokoll, Laeufe)."""
    from statik3d import mesher
    es = _es()
    m.netz = es.setzen(m.netz, "fein")
    m.netz.sweep = "aus"                  # wie die Referenzen: Tetraederweg
    m.netz.hoechstens_unbekannte = int(grenze)
    log: list = []
    with (ohne_sperre() if sperre_aus else nullcontext()):
        with _Laeufe() as lf:
            with es.beim_vernetzen(m, log) as w:
                # Ohne den Anschluss (Stand vor dem 08.10.2026) gibt es keine
                # Stufen: dann wird ueber der Grenze nur gewarnt
                stufen = es.fein_stufen(m, w) if hasattr(es, "fein_stufen") else None
                erg = mesher.modell_vernetzen(m, log, workers=1, stufen=stufen)
    return erg, [str(z) for z in log], lf


def _ohne_fein_quellen(netz) -> bool:
    return not [v for v in (getattr(netz, "verfeinerungen", None) or [])
                if str((v or {}).get("art", "")).startswith("fein_")]


def test_grenze_stufen():
    """Platte ohne Kontakt (Lastflaeche M2, freie Bohrung; gelagert wuerde
    ueber Knotenlager, also nichts gesperrt) mit Fein und Grenze:

    a) knapp unter dem Fein-Netz: gröber ueber die Stufen, jede Stufe mit
       ihrem Text im Protokoll, Ergebnis unter der Grenze und bitgleich mit
       Fein in dieser Stufe; die Stufen 1 und 2 vergroebern nur Boegen an
       Kontakt- und Lagerflaechen - an diesem Modell gibt es keine, sie
       ergaeben dasselbe Netz wie Stufe 0 und werden uebersprungen;
    b) ueber dem Netz: bitgleich Fein ohne Grenze;
    c) unter Mittel: endet in der letzten Stufe, bitgleich Mittel, WARNUNG.
    """
    es = _es()
    h_f, u_f = _referenz(platte_ohne_kontakt, "fein")
    h_m, u_m = _referenz(platte_ohne_kontakt, "mittel")
    check("Voraussetzung: Fein ist feiner als Mittel (Lastfläche h/2)", u_f > u_m,
          f"Fein {_zahl(u_f)}, Mittel {_zahl(u_m)} Unbekannte")

    # a) Grenze knapp unter dem Fein-Netz
    m = platte_ohne_kontakt()
    erg, log, lf = vernetzen_mit_grenze(m, u_f - 3)
    k, u = int(erg.get("stufe", 0) or 0), 3 * m.nn
    check(f"a) Grenze {_zahl(u_f - 3)} (3 unter Fein): gröber vernetzt, Ergebnis unter der Grenze",
          k >= 1 and u <= u_f - 3, f"Stufe {k}, {_zahl(u)} Unbekannte")
    h_k = _referenz(platte_ohne_kontakt, "fein", k=k)[0] if k else ""
    check("… bitgleich mit Fein in dieser Stufe ohne Grenze (Weg von F1)", k and netz_hash(m) == h_k,
          f"{netz_hash(m)} / {h_k}")
    check("… Stufen 1 und 2 (nur Bögen) übersprungen: zwei Läufe, Stufe 0 und Stufe 3",
          k == 3 and len(lf.ergebnisse) == 2, f"Stufe {k}, {len(lf.ergebnisse)} Läufe: "
                                               f"{[z[3] or '(Stufe 0)' for z in lf.zu_beginn]}")
    zeilen = [z for z in log if "Netzgrenze" in z]
    check("… Protokoll: Stufe 0 angehalten, mit Grund und Zahl",
          any("Stufe 0" in z and "angehalten" in z and "über der Grenze" in z and _zahl(u_f - 3) in z
              for z in zeilen), zeilen[0] if zeilen else "keine Zeile „Netzgrenze“")
    check("… Protokoll nennt die nächste Stufe mit ihrem Text: „Fein Stufe 3: Bögen 18°, Flächen h/1,5“",
          any("Stufe 3 (Fein Stufe 3: Bögen 18°, Flächen h/1,5)" in z for z in zeilen),
          zeilen[0][-170:] if zeilen else "")
    check("… und dass die Stufen 1 und 2 dasselbe Netz ergäben und übersprungen werden",
          any("Stufen 1 und 2" in z and "übersprungen" in z for z in zeilen), zeilen[0][-170:] if zeilen else "")
    check("… Schlusszeile: vernetzt mit Stufe 3, Zahl unter der Grenze",
          any("vernetzt mit Stufe 3 (Fein Stufe 3" in z and _zahl(u) in z and "unter der Grenze" in z
              for z in zeilen), zeilen[-1] if zeilen else "")
    check("… keine WARNUNG", not [z for z in log if z.startswith("WARNUNG") and "Unbekannte" in z])
    if len(lf.zu_beginn) >= 2:
        check("… kein halbes Netz zu Beginn der Stufe 3 (Elemente, Knoten wie vor Stufe 0)",
              lf.zu_beginn[1][:3] == lf.zu_beginn[0][:3] and lf.zu_beginn[1][2] == 0,
              f"vor 0: {lf.zu_beginn[0][:3]}, vor 3: {lf.zu_beginn[1][:3]}")
        check("… Stufe 3 lief mit ihren Einstellungen (quelle der Netzeinstellungen)",
              lf.zu_beginn[1][3].startswith("Fein Stufe 3"), lf.zu_beginn[1][3])
    check("… danach stehen die gespeicherten Netzeinstellungen da (Fein, ohne Quellen, quelle leer)",
          es.stufe(m.netz) == "fein" and _ohne_fein_quellen(m.netz) and not m.netz.quelle,
          f"{es.stufe(m.netz)}, quelle {m.netz.quelle!r}")

    # b) Grenze auf dem Netz (nicht ueberschritten)
    m = platte_ohne_kontakt()
    erg, log, lf = vernetzen_mit_grenze(m, u_f)
    check("b) Grenze = Fein-Netz: bitgleich Fein ohne Grenze, Stufe 0, ein Lauf",
          netz_hash(m) == h_f and erg.get("stufe", 0) == 0 and len(lf.ergebnisse) == 1,
          f"{netz_hash(m)} / {h_f}, Stufe {erg.get('stufe')}, {len(lf.ergebnisse)} Läufe")
    check("… keine Zeile „Netzgrenze“, keine Warnung",
          not [z for z in log if "Netzgrenze" in z or (z.startswith("WARNUNG") and "Unbekannte" in z)])

    # c) Grenze unter Mittel: endet in der letzten Stufe (Mittel)
    m = platte_ohne_kontakt()
    erg, log, lf = vernetzen_mit_grenze(m, u_m - 3)
    check(f"c) Grenze {_zahl(u_m - 3)} unter Mittel: endet in der letzten Stufe 4, bitgleich Mittel",
          erg.get("stufe") == es.FEIN_STUFEN_ANZAHL - 1 and netz_hash(m) == h_m,
          f"Stufe {erg.get('stufe')}, {netz_hash(m)} / {h_m}, {_zahl(3 * m.nn)} Unbekannte")
    warn = [z for z in log if z.startswith("WARNUNG") and "Unbekannte" in z]
    check("… mit WARNUNG: Zahl, Grenze und die gröbste Stufe (Fein Stufe 4, wie Mittel)",
          any(_zahl(3 * m.nn) in z and _zahl(u_m - 3) in z and "Fein Stufe 4" in z for z in warn),
          warn[0] if warn else "keine WARNUNG")
    check("… drei Läufe: Stufe 0, 3 und 4", [z[3][:12] for z in lf.zu_beginn]
          == ["", "Fein Stufe 3", "Fein Stufe 4"], [z[3] or "(Stufe 0)" for z in lf.zu_beginn])


def test_grenze_boegen():
    """Platte mit Kontakt an der Bohrung B1 und Flaechenlager (Sperre nur im
    Test aufgehoben, nur vernetzt): die Boegen sind an Fein 9 Grad, Stufe 1
    vergroebert sie auf 12 Grad - mit der Grenze knapp unter Fein endet es
    dort."""
    h1, u1 = _referenz(platte_kontakt, "fein", k=1, sperre_aus=True)
    _h0, u0 = _referenz(platte_kontakt, "fein", sperre_aus=True)
    check("Voraussetzung: Stufe 1 (Bögen 12°) ist gröber als Stufe 0 (9°)", u1 < u0 - 3,
          f"Stufe 0 {_zahl(u0)}, Stufe 1 {_zahl(u1)} Unbekannte")
    m = platte_kontakt()
    erg, log, lf = vernetzen_mit_grenze(m, u0 - 3, sperre_aus=True)
    check("Grenze knapp unter Fein: Stufe 1, bitgleich mit Fein in Stufe 1 ohne Grenze",
          erg.get("stufe") == 1 and netz_hash(m) == h1 and 3 * m.nn <= u0 - 3,
          f"Stufe {erg.get('stufe')}, {netz_hash(m)} / {h1}, {_zahl(3 * m.nn)} Unbekannte")
    zeilen = [z for z in log if "Netzgrenze" in z]
    check("… Protokoll: „Stufe 1 (Fein Stufe 1: Bögen 12°, Flächen h/2)“, nichts übersprungen",
          any("Stufe 1 (Fein Stufe 1: Bögen 12°, Flächen h/2)" in z for z in zeilen)
          and not any("übersprungen" in z for z in zeilen), zeilen[0][-150:] if zeilen else "keine Zeile")


_FENSTER = {}
FEHLER = []


def _fenster():
    if "w" in _FENSTER:
        return _FENSTER["w"], _FENSTER["app"]
    from PySide6 import QtWidgets
    from statik3d.gui.main import MainWindow
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = MainWindow()
    w.show()
    app.processEvents()
    w._fragen_knoepfe = lambda *a, **k: True
    w._netzaenderung_bestaetigen = lambda *a, **k: True
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w, FEHLER)
    _FENSTER.update(w=w, app=app)
    return w, app


def test_grenze_fenster():
    """Netz -> Vernetzen im Hauptfenster (gui.main._vernetzen): Fein ueber der
    Grenze wird gröber vernetzt, ohne Warnung als Meldung."""
    es = _es()
    w, app = _fenster()
    m = platte_ohne_kontakt()
    m.netz = es.setzen(m.netz, "fein")
    m.netz.sweep = "aus"
    m.netz.hoechstens_unbekannte = 0
    w.model = m
    w._MainWindow__init_defaults()
    w.analysis = None
    w.results = None
    w.refresh_all()
    app.processEvents()
    gewarnt = []
    alt = w.warnung
    w.warnung = lambda msg: gewarnt.append(str(msg))
    try:
        w.geometrie_vernetzen()
        app.processEvents()
        u_g = 3 * w.model.nn
        w.model.netz.hoechstens_unbekannte = u_g - 3
        w.log.clear()
        w.geometrie_vernetzen()
        app.processEvents()
    finally:
        w.warnung = alt
    text = w.log.toPlainText()
    u = 3 * w.model.nn
    check("Fenster: Fein mit Grenze 3 unter dem eigenen Netz wird gröber vernetzt (Stufe 3), unter der Grenze",
          u <= u_g - 3 and "vernetzt mit Stufe 3 (Fein Stufe 3" in text,
          [z for z in text.splitlines() if "Netzgrenze" in z][-1:] or f"{_zahl(u)} von {_zahl(u_g)}")
    check("… keine Warnung als Meldung", not gewarnt, gewarnt[:1])
    check("… die Netzeinstellungen des Modells bleiben Fein mit der Grenze",
          es.stufe(w.model.netz) == "fein" and w.model.netz.hoechstens_unbekannte == u_g - 3
          and _ohne_fein_quellen(w.model.netz))


def test_grenze_cli():
    """``statik3d modell.json --vernetzen`` (cli.py): dieselbe Vergroeberung
    ohne Oberflaeche. Gerechnet wird danach nicht (der Loeser ist hier
    ersetzt) - gespeichert wird das Netz vorher mit --speichern."""
    import contextlib
    import io
    from statik3d import cli, solver
    from statik3d.model import Model
    es = _es()
    _h_f, u_f = _referenz(platte_ohne_kontakt, "fein")
    m = platte_ohne_kontakt()
    m.netz = es.setzen(m.netz, "fein")
    m.netz.sweep = "aus"
    m.netz.hoechstens_unbekannte = u_f - 3
    ordner = tempfile.mkdtemp(prefix="statik3d_fein_cli_")
    ein, aus = os.path.join(ordner, "platte.json"), os.path.join(ordner, "vernetzt.json")
    m.save(ein)

    class _Halt(Exception):
        pass

    def halt(*a, **k):
        raise _Halt()
    alt = solver.solve_all
    solver.solve_all = halt
    puffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(puffer):
            try:
                cli.main([ein, "--vernetzen", "--speichern", aus, "--kerne", "1"])
            except _Halt:
                pass
    finally:
        solver.solve_all = alt
    text = puffer.getvalue()
    m2 = Model.load(aus) if os.path.exists(aus) else None
    u = 3 * m2.nn if m2 is not None else 0
    check("cli --vernetzen: Fein über der Grenze gröber vernetzt (Stufe 3), gespeichertes Netz unter der Grenze",
          m2 is not None and 0 < u <= u_f - 3 and "vernetzt mit Stufe 3 (Fein Stufe 3" in text,
          [z.strip() for z in text.splitlines() if "Netzgrenze" in z][-1:] or f"{_zahl(u)} Unbekannte")


def main():
    import faulthandler
    faulthandler.dump_traceback_later(1800, exit=True)
    gruppen = (test_quellen_auf_zylinder, test_feld_an_der_wand, test_texte, test_bloecke_flaechen,
               test_bohrungen, test_mittel_entwurf_bitgleich, test_rechnen_ohne_kontakt,
               test_vergroeberung_f2, test_grenze_stufen, test_grenze_boegen, test_grenze_fenster,
               test_grenze_cli)
    # Aufruf mit Namensteilen (python -m tests.test_fein_smart grenze) laesst nur diese laufen
    auswahl = [a for a in sys.argv[1:] if not a.startswith("-")]
    for t in gruppen:
        if auswahl and not any(a in t.__name__ for a in auswahl):
            continue
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
    # Das Hauptfenster (test_grenze_fenster) ohne Rueckfrage beenden
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
