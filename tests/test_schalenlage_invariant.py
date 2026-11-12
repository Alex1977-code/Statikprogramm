"""
Die Lage einzelner Schalenelemente aendert das Ergebnis nicht (12.11.2026).

Anwender: „die lage von schalenelementen sollte der user frei bestimmen
können und sie dürfte grundsätzlich nicht an der berechnung ändern“.

Aufbau jeder Pruefung: dasselbe kleine Modell wird zweimal gerechnet - einmal
wie vernetzt bzw. importiert, einmal mit einigen gespiegelten Elementen
(Knotenfolge umgekehrt, Seitenmitten mit umgeordnet; SPIEGEL). Gespiegelt wird
nach dem Vernetzen und vor dem Lastgenerator bzw. vor der Rechnung, nur ueber
die Wege des Programms (Elementknoten, Model-Methoden, Generatoren, Rechnung,
Ergebnisabfrage ohne Fenster). Lasten haengen an der Flaeche oder global; wo
eine Last am Element haengt (Nastran-Import, load_face, load_temp), wird sie
mit dem Element gespiegelt (Vorzeichen in lokal z), damit die Physik dieselbe
bleibt.

Verglichen werden physikalische Groessen: Verschiebungen und Verdrehungen,
Auflagerkraefte, ΣF der erzeugten Lasten (zwei Wege: Lastvektor der Rechnung
und Kontrollsumme des Generators), die Schnittgroessen und Spannungen im
Flaechensystem je Element und als Knotenmittel (statik3d/spannungen.py, die
Funktionen hinter der Anzeige), die Schalentabelle des Berichts und die
Spannungen des Beulnachweises. Gleich heisst: Abweichung hoechstens 1e-9 der
groessten Bezugsgroesse derselben Art.

Bei jeder Pruefung steht im Namen, ob sie die Rechnung oder die Anzeige
betrifft. Am Stand eb88ecc scheitern die Stellen, an denen die Elementnormale
die Richtung vorgibt (Befundliste der Release-Notes vom 12.11.2026, „Offen“).

Aufruf:  python -m tests.test_schalenlage_invariant
"""
import contextlib
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

RESULTS = []
TOL = 1e-9
LF = "LF1"

#: Spiegelung: umgekehrter Umlauf, die Seitenmitten folgen ihren Kanten
SPIEGEL = {"shell3": [0, 2, 1], "shell4": [0, 3, 2, 1],
           "shell6": [0, 2, 1, 5, 4, 3], "shell8": [0, 3, 2, 1, 7, 6, 5, 4]}
#: Drehung der Knotenfolge ohne Spiegelung (erste Kante wandert weiter)
ZYKLISCH = {"shell3": [1, 2, 0], "shell4": [1, 2, 3, 0],
            "shell6": [1, 2, 0, 4, 5, 3], "shell8": [1, 2, 3, 0, 5, 6, 7, 4]}
#: unsymmetrischer Zweischichter (wie tests/test_laminat_temperatur.py)
UNSYM = [{"t": 0.005, "E": 210e9, "nu": 0.3, "winkel": 0.0},
         {"t": 0.005, "E": 70e9, "nu": 0.3, "winkel": 0.0}]
#: Elementarten: (Ordnung, Form der Netzeinstellung) -> Name
NETZE = {"shell4": (1, 2), "shell8": (2, 2), "shell3": (1, 0), "shell6": (2, 0)}


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:100s} {detail}")
    return ok


@contextlib.contextmanager
def _still():
    with contextlib.redirect_stdout(io.StringIO()):
        yield


def _zahl(x: float) -> str:
    """Abweichung lesbar, ohne wissenschaftliche Schreibweise."""
    x = float(x)
    if not np.isfinite(x):
        return "unendlich"
    if x == 0.0:
        return "0"
    if x >= 1e-3:
        return f"{x:.4f}".replace(".", ",")
    stellen = int(-np.floor(np.log10(x))) + 1
    return f"{x:.{min(stellen, 18)}f}".replace(".", ",")


def _kn(F) -> str:
    return "(" + "; ".join(f"{x / 1e3:.3f}".replace(".", ",") for x in F) + ")"


def _rel(a, b) -> float:
    """Groesste Abweichung bezogen auf den groessten Betrag der Bezugsgroesse."""
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    if a.shape != b.shape:
        return float("inf")
    if a.size == 0:
        return 0.0
    ref = float(np.nanmax(np.abs(a))) if np.any(np.isfinite(a)) else 0.0
    d = np.abs(a - b)
    if np.any(np.isfinite(a) != np.isfinite(b)):
        return float("inf")
    d = float(np.nanmax(d)) if np.any(np.isfinite(d)) else 0.0
    return d / ref if ref > 0 else d


# ---------------------------------------------------------------------------
# Modelle
# ---------------------------------------------------------------------------
def _modell(name="Schale", lagen=None):
    from statik3d.model import Model, Material, ShellProp
    m = Model(name)
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("t", 0.010, lagen=[dict(x) for x in (lagen or [])]))
    return m


def _flaeche(m, name, ecken, teilung):
    """Flaeche aus vier Eckpunkten (Umlauf = Normale nach der Rechtsschraube)."""
    ids = [m.add_node(*p) for p in ecken]
    linien = []
    for j in range(4):
        ln = f"{name}_L{j}"
        m.add_line(ln, [ids[j], ids[(j + 1) % 4]])
        linien.append(ln)
    f = m.add_flaeche(name, linien, material="S235", dicke="t")
    f.teilung = list(teilung)
    return f


def _vernetzen(m, typ):
    from statik3d import mesher
    ordnung, form = NETZE[typ]
    m.netz.ordnung = ordnung
    m.netz.form = form
    with _still():
        mesher.modell_vernetzen(m, log=[], workers=1)
    typen = sorted({e.typ for e in m.elements})
    assert typen == [typ], f"Netz {typen} statt {typ}"


def _knoten(m, maske) -> list:
    return [int(i) for i in np.flatnonzero(maske)]


def _bei(m, x, y, z) -> int:
    return int(np.argmin(np.linalg.norm(m.nodes[:, :3] - np.array([x, y, z]), axis=1)))


def _platte(typ, lagen=None, lager=True):
    """Kragplatte 2 x 1 m in der Ebene z = 0, Normale +z, bei x = 0 eingespannt."""
    m = _modell("Platte", lagen)
    f = _flaeche(m, "P", [(0, 0, 0), (2, 0, 0), (2, 1, 0), (0, 1, 0)], (6, 3))
    m.add_load_case(LF, "Q")
    _vernetzen(m, typ)
    if lager:
        for n in _knoten(m, np.abs(m.nodes[:, 0]) < 1e-9):
            m.fix(n, "all")
    return m, f


def spiegeln(m, elemente, perm=SPIEGEL) -> list:
    """Knotenfolge der Elemente umordnen (Rueckgabe: die Elemente)."""
    out = []
    for e in elemente:
        el = m.elements[int(e)]
        el.nodes = [el.nodes[i] for i in perm[el.typ]]
        out.append(int(e))
    return out


def einige(_m, f, rest=0) -> list:
    """Jedes dritte Element der Flaeche (mit rest = 0 auch das erste)."""
    return [int(e) for j, e in enumerate(f.elemente) if j % 3 == rest]


def rechnen(m, fall=LF):
    from statik3d import solver
    with _still():
        an = solver.solve_all(m, workers=1, combinations=False, design=False)
    return an.cases[fall]


def knotenlasten(m, fall=LF) -> np.ndarray:
    """Die Knotenkraefte (nn, 3) des Lastfalls aus dem Lastvektor der Rechnung."""
    from statik3d.assemble import load_vector
    nn = int(m.nn)
    F = np.asarray(load_vector(m, m.load_cases[fall]), float)[:6 * nn].reshape(nn, 6)
    return F[:, :3]


def summe_last(m, fall=LF) -> np.ndarray:
    """ΣF der Knotenlasten des Lastfalls aus dem Lastvektor der Rechnung."""
    return knotenlasten(m, fall).sum(axis=0)


# ---------------------------------------------------------------------------
# Vergleiche
# ---------------------------------------------------------------------------
def physik(titel, m0, r0, m1, r1, fall=LF, sf0=None, sf1=None) -> bool:
    """Rechnung: Verschiebungen, Verdrehungen, Auflagerkraefte, ΣF."""
    U0, U1 = np.asarray(r0.u, float), np.asarray(r1.u, float)
    R0, R1 = np.asarray(r0.reactions, float), np.asarray(r1.reactions, float)
    K0 = knotenlasten(m0, fall)
    F0, F1 = K0.sum(axis=0), summe_last(m1, fall)
    # ΣF bezogen auf die Summe oder - bei einer Last mit Summe null
    # (Temperatur) - auf die groesste Knotenkraft
    skala = max(float(np.linalg.norm(F0)), float(np.abs(K0).max()) if K0.size else 0.0, 1e-30)
    werte = {"u": _rel(U0[:, :3], U1[:, :3]), "φ": _rel(U0[:, 3:], U1[:, 3:]),
             "R": _rel(R0[:, :3], R1[:, :3]), "ΣF": float(np.abs(F1 - F0).max()) / skala}
    if sf0 is not None:
        werte["ΣF Generator"] = float(np.abs(np.asarray(sf1) - np.asarray(sf0)).max()) / skala
    schlecht = max(werte.values())
    detail = ", ".join(f"{k} {_zahl(v)}" for k, v in werte.items())
    detail += f"; |u|max {np.abs(U0[:, :3]).max() * 1e3:.3f} mm".replace(".", ",")
    detail += f"; ΣF {_kn(F0)} → {_kn(F1)} kN"
    if sf0 is not None:
        detail += f", Kontrollsumme des Generators {_kn(sf0)} → {_kn(sf1)} kN"
    return check(f"{titel} [Rechnung]", schlecht <= TOL, detail)


def anzeige(titel, m0, r0, m1, r1, elemente=None, bericht=False) -> bool:
    """Anzeige: n, m, σ oben/unten je Element im Flaechensystem; Knotenmittel
    (spannungen.je_knoten) fuer σ_x, σ_y, τ_xy, σ_1, σ_2, σ_v oben, unten, max;
    Vergleichsspannung je Knoten (Results.node_vm); auf Wunsch die
    Schalentabelle des Berichts."""
    from statik3d import spannungen as spn
    s0, s1 = r0.shell_stress, r1.shell_stress
    ids = sorted(s0) if elemente is None else sorted(int(e) for e in elemente)
    werte = {}
    for k, lab in (("n", "n_x n_y n_xy"), ("m", "m_x m_y m_xy"), ("sig_top", "σ oben"),
                   ("sig_bot", "σ unten")):
        A = np.array([s0[i][k] for i in ids], float)
        B = np.array([s1[i][k] for i in ids], float)
        werte[lab] = _rel(A, B)
        if k in ("n", "m"):
            for j, c in enumerate(lab.split()):
                werte[c] = _rel(A[:, j], B[:, j])
    kn = sorted({int(n) for i in ids for n in m0.elements[i].nodes})
    for seite in ("oben", "unten", "max"):
        d = 0.0
        schlimm = ""
        for g in ("sx", "sy", "txy", "s1", "s2", "sv"):
            a = spn.je_knoten(m0, r0, "flaechen", g, seite)[kn]
            b = spn.je_knoten(m1, r1, "flaechen", g, seite)[kn]
            x = _rel(a, b)
            if x > d:
                d, schlimm = x, g
        werte[f"Knotenmittel {seite}" + (f" ({schlimm})" if schlimm else "")] = d
    werte["σ_v Knoten"] = _rel(np.asarray(r0.node_vm)[kn], np.asarray(r1.node_vm)[kn])
    if bericht:
        werte["Bericht"] = 0.0 if _berichtszeilen(m0, r0) == _berichtszeilen(m1, r1) else 1.0
    schlecht = {k: v for k, v in werte.items() if v > TOL}
    detail = ("gleich" if not schlecht else "abweichend: " + ", ".join(
        f"{k} {_zahl(v)}" for k, v in schlecht.items()))
    ok = check(f"{titel} [Anzeige]", not schlecht, detail)
    return ok


def _berichtszeilen(m, r) -> list:
    from statik3d.report.html import Report
    rep = Report(m, results=r)
    for b in rep._result_detail(LF, r):
        if isinstance(b, tuple) and len(b) > 2 and b[0] == "table" \
                and str(b[2]).startswith("Schnittkräfte und Spannungen der Schalen"):
            return [list(map(str, z)) for z in b[1]]
    return []


def _paar(bauen, aendern, vorher=None, nachher=None, perm=SPIEGEL):
    """Zwei gleiche Modelle; im zweiten die Elemente aus ``aendern(m, f)``
    gespiegelt. ``vorher(m)`` vor der Spiegelung (in beiden), ``nachher(m, g)``
    danach mit der Liste der gespiegelten Elemente (in beiden; im ersten leer);
    zuletzt verteilt Model.lasten_verteilen die Objektlasten."""
    out = []
    for mit in (False, True):
        m, f = bauen()
        if vorher is not None:
            vorher(m, f)
        g = spiegeln(m, aendern(m, f), perm) if mit else []
        if nachher is not None:
            nachher(m, f, set(g))
        # Objektlasten auf das Netz legen - wie die Oberflaeche nach dem
        # Anlegen einer Last und das Vernetzen danach (Model.lasten_verteilen)
        m.lasten_verteilen()
        out.append((m, f, g))
    return out


# ---------------------------------------------------------------------------
# 1) Anzeige bei gleicher Physik (globale Lasten)
# ---------------------------------------------------------------------------
def _globale_lasten(m, f, _g=None):
    m.add_geometrielast("P", -5e3, art="flaeche", case=LF, bezug="global", achse="z")
    m.load_node(_bei(m, 2, 1, 0), Fy=2e3, Fz=-1e3, case=LF)
    m.load_node(_bei(m, 2, 0, 0), Fx=-3e3, case=LF)


def test_anzeige_globale_last():
    """Platte mit globaler Flaechenlast und Knotenlasten (n_xy, m_xy ≠ 0):
    die Rechnung haengt nicht an der Lage; Anzeige und Bericht schon, weil das
    Flaechensystem die Elementnormale als z nimmt (solver.flaechen_bezugssystem)."""
    for typ in ("shell4", "shell8", "shell3", "shell6"):
        (m0, _f0, _), (m1, _f1, g) = _paar(lambda t=typ: _platte(t), einige, nachher=_globale_lasten)
        r0, r1 = rechnen(m0), rechnen(m1)
        titel = f"{typ}: globale Last, {len(g)} von {len(m1.elements)} Elementen gespiegelt"
        physik(titel, m0, r0, m1, r1)
        anzeige(titel, m0, r0, m1, r1, bericht=True)
    # alle Elemente der Flaeche gespiegelt
    (m0, _f0, _), (m1, f1, g) = _paar(lambda: _platte("shell4"), lambda m, f: list(f.elemente),
                                      nachher=_globale_lasten)
    r0, r1 = rechnen(m0), rechnen(m1)
    titel = f"shell4: globale Last, alle {len(g)} Elemente gespiegelt"
    physik(titel, m0, r0, m1, r1)
    anzeige(titel, m0, r0, m1, r1, bericht=True)


def test_anzeige_zyklisch():
    """Knotenfolge nur weitergedreht (keine Spiegelung): die erste Kante
    wandert. Seit dem 09.11.2026 (A20) zaehlt fuer die Anzeige das
    Flaechensystem, nicht die erste Kante."""
    for typ in ("shell4", "shell8"):
        (m0, _f0, _), (m1, _f1, g) = _paar(lambda t=typ: _platte(t), einige, nachher=_globale_lasten,
                                           perm=ZYKLISCH)
        r0, r1 = rechnen(m0), rechnen(m1)
        titel = f"{typ}: globale Last, {len(g)} Elemente zyklisch umnummeriert (nicht gespiegelt)"
        physik(titel, m0, r0, m1, r1)
        anzeige(titel, m0, r0, m1, r1, bericht=True)


def test_flaechenachsen_bild():
    """Die Achsen der Flaeche in der Ansicht (lastbezug.flaechenachsen_bild):
    an der Elementseite nahe der Mitte, also an deren Normale."""
    from statik3d.lastbezug import flaechenachsen_bild
    for typ in ("shell4", "shell8"):
        def mitte(m, f):
            M = np.array([m.nodes[m.elements[int(e)].nodes].mean(axis=0) for e in f.elemente])
            j = int(np.argmin(np.linalg.norm(M - [1.0, 0.5, 0.0], axis=1)))
            return [int(f.elemente[j])]
        (m0, f0, _), (m1, f1, g) = _paar(lambda t=typ: _platte(t), mitte)
        a0, a1 = flaechenachsen_bild(m0, f0), flaechenachsen_bild(m1, f1)
        d = max(_rel(np.asarray(x), np.asarray(y)) for x, y in zip(a0[1:], a1[1:]))
        check(f"{typ}: Flächenachsen in der Ansicht, das Element an der Mitte gespiegelt [Anzeige]",
              d <= TOL, f"z vorher ({', '.join(f'{x:+.0f}' for x in a0[3])}), "
                        f"nachher ({', '.join(f'{x:+.0f}' for x in a1[3])})")


# ---------------------------------------------------------------------------
# 2) Flaechenlasten
# ---------------------------------------------------------------------------
def _flaechenlast(**kw):
    kw = dict(kw)
    p = kw.pop("p", -5e3)

    def f(m, _f, _g):
        m.add_geometrielast("P", p, art="flaeche", case=LF, **kw)
    return f


def test_flaechenlasten():
    """Flaechenlasten an der Flaeche, nach der Spiegelung verteilt
    (add_geometrielast legt sie sofort auf das Netz)."""
    faelle = [
        ("ohne Bezug (senkrecht zur Fläche)", dict(p=-5e3)),
        ("lokal z", dict(p=-5e3, bezug="lokal", achse="z")),
        ("lokal y (in der Ebene)", dict(p=20e3, bezug="lokal", achse="y")),
        ("lokal x (in der Ebene, Gegenprobe)", dict(p=20e3, bezug="lokal", achse="x")),
        ("global Z (Gegenprobe)", dict(p=-5e3, bezug="global", achse="z")),
        ("global Z projiziert (Schnee, Gegenprobe)", dict(p=-5e3, richtung=[0, 0, 1], projiziert=True)),
    ]
    for typ in ("shell4", "shell8"):
        for text, kw in faelle:
            (m0, _f0, _), (m1, _f1, g) = _paar(lambda t=typ: _platte(t), einige, nachher=_flaechenlast(**kw))
            r0, r1 = rechnen(m0), rechnen(m1)
            physik(f"{typ}: Flächenlast {text}, {len(g)} Elemente gespiegelt", m0, r0, m1, r1)


def test_flaechenlast_vor_dem_vernetzen():
    """Die Last steht schon vor dem Vernetzen an der Flaeche; nach der
    Spiegelung verteilt Model.lasten_verteilen neu (wie nach jedem Vernetzen)."""
    def bauen():
        m = _modell("Platte")
        f = _flaeche(m, "P", [(0, 0, 0), (2, 0, 0), (2, 1, 0), (0, 1, 0)], (6, 3))
        m.add_load_case(LF, "Q")
        m.add_geometrielast("P", -5e3, art="flaeche", case=LF, bezug="lokal", achse="z")
        _vernetzen(m, "shell4")
        for n in _knoten(m, np.abs(m.nodes[:, 0]) < 1e-9):
            m.fix(n, "all")
        return m, f
    (m0, _f0, _), (m1, _f1, g) = _paar(bauen, einige)
    r0, r1 = rechnen(m0), rechnen(m1)
    physik(f"shell4: Flächenlast lokal z vor dem Vernetzen angelegt, danach {len(g)} Elemente gespiegelt"
           " und neu verteilt", m0, r0, m1, r1)


def test_elementlast_mit_gespiegelt():
    """Eine Elementlast in lokal z (load_face) und dT_z (load_temp) am Element:
    mit dem Element gespiegelt, also mit umgekehrtem Vorzeichen - dieselbe
    Physik. Am Stand eb88ecc gleich; die Kur muss die Lasten mitdrehen, wenn
    sie Elemente ausrichtet."""
    for typ in ("shell4", "shell8"):
        def lasten(m, f, g):
            for e in f.elemente:
                s = -1.0 if int(e) in g else 1.0
                m.load_face(int(e), s * -5e3, 0, case=LF)
                m.load_temp(int(e), 0.0, s * 30.0, case=LF)
        (m0, _f0, _), (m1, _f1, g) = _paar(lambda t=typ: _platte(t), einige, nachher=lasten)
        r0, r1 = rechnen(m0), rechnen(m1)
        physik(f"{typ}: Elementlast lokal z und ΔT_z am Element, mit {len(g)} Elementen gespiegelt",
               m0, r0, m1, r1)


# ---------------------------------------------------------------------------
# 3) Temperatur und Laminat
# ---------------------------------------------------------------------------
def test_temperatur():
    for typ in ("shell4", "shell8"):
        for text, kw in (("ΔT_z = 30 K", dict(dT_z=30.0)), ("ΔT = 30 K (Gegenprobe)", dict(dT=30.0))):
            def last(m, f, g, kw=kw):
                m.add_geometrielast("P", 0.0, art="flaeche", case=LF, lastart="temperatur", **kw)
            (m0, _f0, _), (m1, _f1, g) = _paar(lambda t=typ: _platte(t), einige, nachher=last)
            r0, r1 = rechnen(m0), rechnen(m1)
            physik(f"{typ}: Temperatur an der Fläche {text}, {len(g)} Elemente gespiegelt", m0, r0, m1, r1)


def test_laminat_unsymmetrisch():
    """Zweischichter 5 mm E 210 000 + 5 mm E 70 000 N/mm² (B ≠ 0) als Dicke
    der Flaeche: die Lagenfolge gilt zur Flaechennormalen."""
    for typ in ("shell4", "shell8"):
        for text, last in (("Flächenlast global Z", _flaechenlast(p=-5e3, bezug="global", achse="z")),
                           ("ΔT = 30 K", lambda m, f, g: m.add_geometrielast(
                               "P", 0.0, art="flaeche", case=LF, lastart="temperatur", dT=30.0)),
                           ("Zug in x am freien Rand", lambda m, f, g: [
                               m.load_node(n, Fx=1e4, case=LF)
                               for n in _knoten(m, np.abs(m.nodes[:, 0] - 2.0) < 1e-9)])):
            (m0, _f0, _), (m1, _f1, g) = _paar(lambda t=typ: _platte(t, lagen=UNSYM), einige, nachher=last)
            r0, r1 = rechnen(m0), rechnen(m1)
            physik(f"{typ}: unsymmetrisches Laminat, {text}, {len(g)} Elemente gespiegelt", m0, r0, m1, r1)


# ---------------------------------------------------------------------------
# 4) Lastgeneratoren
# ---------------------------------------------------------------------------
def _wand_yz(typ):
    """Senkrechte Haut 3 x 5 m bei x = 0 (Normale +x), an y = 0 und y = 3 eingespannt."""
    m = _modell("Haut")
    f = _flaeche(m, "Haut", [(0, 0, 0), (0, 3, 0), (0, 3, 5), (0, 0, 5)], (3, 5))
    m.add_load_case(LF, "Q")
    _vernetzen(m, typ)
    for n in _knoten(m, (np.abs(m.nodes[:, 1]) < 1e-9) | (np.abs(m.nodes[:, 1] - 3.0) < 1e-9)):
        m.fix(n, "all")
    return m, f


def test_wasserdruck():
    from statik3d import wasserdruck as wdm
    faelle = [(typ, text, kw, einige) for typ in ("shell4", "shell8") for text, kw in (
        ("Näherungsformel ohne Richtung", dict(verfahren="analytisch")),
        ("Näherungsformel mit globaler Richtung (Gegenprobe)", dict(verfahren="analytisch",
                                                                    richtung=[1.0, 0.0, 0.0])))]
    # stroemungsnumerisch: die Stroemungsrichtung kommt ohne Referenzflaeche aus
    # der Summe der Elementnormalen (wasserdruck.flaechennormale)
    faelle += [("shell4", "strömungsnumerisch ohne Richtung", dict(verfahren="numerisch", gitter=20), wahl)
               for wahl in (einige, lambda m, f: list(f.elemente))]
    for typ, text, kw, wahl in faelle:
        erg = []
        for mit in (False, True):
            m, f = _wand_yz(typ)
            g = spiegeln(m, wahl(m, f)) if mit else []
            wd = wdm.Wasserdruck("WD", flaechen=["Haut"], h_ow=4.0, absenkung=False, **kw)
            with _still():
                kwerte = wdm.lasten_erzeugen(m, wd)
            erg.append((m, wd.lastfall, np.asarray(kwerte["kontrolle"]["F"], float), g))
        (m0, lf0, F0, _), (m1, lf1, F1, g) = erg
        r0, r1 = rechnen(m0, lf0), rechnen(m1, lf1)
        physik(f"{typ}: Wasserdruck {text}, {len(g)} Elemente gespiegelt", m0, r0, m1, r1, fall=lf0,
               sf0=F0, sf1=F1)


def _wand_xz(typ, name, normale_plus_y=False):
    """Freistehende Wand 10 x 2 m in der Ebene y = 0 (Normale −y, auf Wunsch
    +y), unten eingespannt."""
    m = _modell("Wand")
    ecken = [(0, 0, 0), (10, 0, 0), (10, 0, 2), (0, 0, 2)]
    f = _flaeche(m, name, ecken[::-1] if normale_plus_y else ecken, (10, 2))
    m.add_load_case(LF, "Q")
    _vernetzen(m, typ)
    for n in _knoten(m, np.abs(m.nodes[:, 2]) < 1e-9):
        m.fix(n, "all")
    return m, f


def test_wind_freie_wand_und_schild():
    from statik3d import wind as wm
    for typ in ("shell4", "shell8"):
        for rolle in ("freie_waende", "schilder"):
            erg = []
            for mit in (False, True):
                m, f = _wand_xz(typ, "W")
                g = spiegeln(m, einige(m, f)) if mit else []
                w = wm.Wind("W1", zone=2, profil="II", richtung=[0.0, 1.0, 0.0], **{rolle: ["W"]})
                with _still():
                    kw = wm.lasten_erzeugen(m, w)
                erg.append((m, w.lastfall, np.asarray(kw["kontrolle"]["F"], float), g))
            (m0, lf0, F0, _), (m1, lf1, F1, g) = erg
            r0, r1 = rechnen(m0, lf0), rechnen(m1, lf1)
            text = "freie Wand (7.4)" if rolle == "freie_waende" else "Schild (7.4.3)"
            physik(f"{typ}: Wind auf {text}, {len(g)} Elemente gespiegelt", m0, r0, m1, r1, fall=lf0,
                   sf0=F0, sf1=F1)


def test_wind_freie_wand_richtung():
    """Die Nettolast einer freien Wand bzw. eines Schildes (c_p,net, c_f)
    wirkt in Windrichtung - gleich, wie herum die Randlinien der Flaeche
    laufen. Wind +y, Wand in der Ebene y = 0 mit Flaechennormale −y bzw. +y.
    Sollwert ΣF_y > 0; Betrag von Hand: q_p(2 m) = 556 N/m² (Kat. II, Zone 2),
    mittleres c_p,net der Zonen A/B/C (je Ende 0,6 m 2,3; 3,4 m 1,4; 1,0 m 1,2)
    = 1,468, ΣF = 1,468 · 556 · 20 m² = 16,3 kN."""
    from statik3d import wind as wm
    for rolle in ("freie_waende", "schilder"):
        F = {}
        for plus in (False, True):
            m, f = _wand_xz("shell4", "W", normale_plus_y=plus)
            w = wm.Wind("W1", zone=2, profil="II", richtung=[0.0, 1.0, 0.0], **{rolle: ["W"]})
            with _still():
                kw = wm.lasten_erzeugen(m, w)
            F[plus] = (np.asarray(kw["kontrolle"]["F"], float), summe_last(m, w.lastfall))
        text = "freie Wand" if rolle == "freie_waende" else "Schild"
        for plus, (Fk, Fv) in F.items():
            check(f"shell4: Wind +y auf {text}, Flächennormale {'+y' if plus else '−y'}: Last in "
                  f"Windrichtung (ΣF_y > 0) [Rechnung, Flächenumlauf]",
                  Fk[1] > 0 and Fv[1] > 0, f"ΣF Lastvektor {_kn(Fv)} kN, Kontrollsumme {_kn(Fk)} kN")


def _halle(typ):
    """Quader 5 x 8 x 6 m aus vier Waenden und Flachdach, Normalen nach aussen,
    unten eingespannt."""
    m = _modell("Halle")
    d, b, h = 5.0, 8.0, 6.0
    flaechen = {
        "Luv": [(0, 0, 0), (0, 0, h), (0, b, h), (0, b, 0)],          # Normale −x
        "Lee": [(d, 0, 0), (d, b, 0), (d, b, h), (d, 0, h)],          # +x
        "Seite1": [(0, 0, 0), (d, 0, 0), (d, 0, h), (0, 0, h)],       # −y
        "Seite2": [(0, b, 0), (0, b, h), (d, b, h), (d, b, 0)],       # +y
        "Dach": [(0, 0, h), (d, 0, h), (d, b, h), (0, b, h)],         # +z
    }
    for name, ecken in flaechen.items():
        _flaeche(m, name, ecken, (4, 4))
    from statik3d import mesher
    with _still():
        mesher.merge_nodes(m)
    m.add_load_case(LF, "Q")
    _vernetzen(m, typ)
    for n in _knoten(m, np.abs(m.nodes[:, 2]) < 1e-9):
        m.fix(n, "all")
    return m, m.flaechen


def test_wind_gebaeude():
    """Gebaeudehuelle mit Innendruck c_pi = 0,2: nach der Norm (je Element
    ueber die Aussenseite der Flaeche - Gegenprobe) und im numerischen
    Windkanal (c_pi wird vom abgetasteten Nettobeiwert abgezogen)."""
    from statik3d import wind as wm
    for verfahren, c_pi in (("norm", 0.2), ("windkanal", 0.0), ("windkanal", 0.2)):
        erg = []
        for mit in (False, True):
            m, fl = _halle("shell4")
            g = spiegeln(m, einige(m, fl["Luv"]) + einige(m, fl["Seite1"]) + einige(m, fl["Dach"])) if mit else []
            kw = dict(verfahren="windkanal", gitter=10, schritte=500, re=100.0) if verfahren == "windkanal" else {}
            w = wm.Wind("W1", zone=2, profil="II", richtung=[1.0, 0.0, 0.0], c_pi=c_pi,
                        flaechen=["Luv", "Lee", "Seite1", "Seite2", "Dach"], **kw)
            with _still():
                k = wm.lasten_erzeugen(m, w)
            erg.append((m, w.lastfall, np.asarray(k["kontrolle"]["F"], float), g, k.get("aus_feld")))
        (m0, lf0, F0, _, af0), (m1, lf1, F1, g, af1) = erg
        r0, r1 = rechnen(m0, lf0), rechnen(m1, lf1)
        text = ("nach der Norm (Gegenprobe)" if verfahren == "norm" else
                f"im Windkanal (aus dem Feld: {', '.join(af0)})" + (" (Gegenprobe)" if not c_pi else ""))
        physik(f"shell4: Wind auf die Gebäudehülle, c_pi = {c_pi:g} {text}, {len(g)} Elemente gespiegelt".replace(".", ","),
               m0, r0, m1, r1, fall=lf0, sf0=F0, sf1=F1)


# ---------------------------------------------------------------------------
# 5) Lager und Kontakt
# ---------------------------------------------------------------------------
def test_flaechenlager_flaechenachsen():
    """Flaechenlager in Flaechenachsen, starr mit Ausfall bei Zug; die Platte
    hebt an einer Ecke ab. Seit dem 12.11.2026 schon unabhaengig von der Lage
    (Gegenprobe; tests/test_flaechenlager_lokal_schraeg.py prueft ein Element)."""
    from statik3d.model import DofBehaviour

    def bauen():
        m, f = _platte("shell4", lager=False)
        ss = m.add_surface_support(name="B")
        ss.flaechen = ["P"]
        ss.lokal = True
        ss.behaviour[2] = DofBehaviour("rigid", failure="zug")
        m.fix(_bei(m, 0, 0, 0), [0, 1, 5])
        m.fix(_bei(m, 2, 0, 0), [1])
        return m, f

    def lasten(m, f, g):
        m.add_geometrielast("P", -5e3, art="flaeche", case=LF, bezug="global", achse="z")
        m.load_node(_bei(m, 2, 1, 0), Fz=2e3, case=LF)
    for wahl, text in ((einige, "jedes dritte, mit dem ersten"), (lambda m, f: list(f.elemente), "alle")):
        (m0, _f0, _), (m1, _f1, g) = _paar(bauen, wahl, nachher=lasten)
        r0, r1 = rechnen(m0), rechnen(m1)
        R0 = np.asarray(r0.reactions)[:, 2]
        ab = int(np.sum(np.abs(R0) < 1e-6 * np.abs(R0).max()))
        ok = physik(f"shell4: Flächenlager in Flächenachsen mit Ausfall bei Zug, {text} ({len(g)}) gespiegelt",
                    m0, r0, m1, r1)
        if ok:
            print(f"     ({ab} von {m0.nn} Knoten ohne Lagerkraft: die Platte hebt ab)")


def test_kontakt_an_schale():
    """Kontaktpaar mit Schalenelementen als Gegenseite: drei feste Knoten
    1 mm unter der Kragplatte. Die Normale einer Schale zeigt zum Knoten
    (contact.py) - Gegenprobe."""
    def kontakt(m, f, g):
        m.add_geometrielast("P", -5e3, art="flaeche", case=LF, bezug="global", achse="z")
        unten = [m.add_node(x, y, -0.001) for x, y in ((1.2, 0.5), (1.7, 0.2), (1.9, 0.8))]
        for n in unten:
            m.fix(n, "all")
        m.add_contact_pair("K", unten, master_elements=list(f.elemente), search_radius=0.1)
    for typ in ("shell4",):
        (m0, _f0, _), (m1, _f1, g) = _paar(lambda t=typ: _platte(t), einige, nachher=kontakt)
        r0, r1 = rechnen(m0), rechnen(m1)
        R = np.asarray(r0.reactions)[-3:, 2]
        physik(f"{typ}: Kontakt an der Schale (drei Knoten darunter), {len(g)} Elemente gespiegelt",
               m0, r0, m1, r1)
        print(f"     Kontaktkräfte an den drei Knoten {', '.join(f'{x / 1e3:.3f}' for x in R)} kN".replace(".", ","))


def _blech_auf_block(wahl):
    """Block 1 x 1 x 0,2 m (hex8, unten eingespannt), darauf ein Blech 10 mm als
    eigene Flaeche ueber denselben Randlinien (Normale +z, vom Block weg).
    Nach dem Vernetzen werden die Elemente aus ``wahl`` gespiegelt, dann
    legt der Befehl „Kontaktfugen ausführen“ (fugen.kontaktfugen_ausfuehren)
    die Fuge an: in der Ebene starr, senkrecht Ausfall bei Zug. Last: 50 kN/m²
    nach unten auf das Blech, 8 kN nach oben an einer Ecke."""
    from statik3d.model import DofBehaviour
    from statik3d import fugen
    m = _modell("Fuge")
    P = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                  [0, 0, .2], [1, 0, .2], [1, 1, .2], [0, 1, .2]], float)
    m.add_nodes(P)
    z = [0]

    def L(a, c):
        z[0] += 1
        m.add_line(f"L{z[0]}", [a, c])
        return f"L{z[0]}"
    R = [[L(o + i, o + (i + 1) % 4) for i in range(4)] for o in (0, 4)]
    V = [L(i, i + 4) for i in range(4)]
    m.add_flaeche("Boden", R[0], material="S235")
    m.add_flaeche("Oben", R[1], material="S235")
    mantel = [m.add_flaeche(f"M{i}", [R[0][i], V[(i + 1) % 4], R[1][i], V[i]], material="S235").name
              for i in range(4)]
    m.add_koerper("Block", ["Boden", "Oben"] + mantel, material="S235")
    f = m.add_flaeche("Blech", R[1], material="S235", dicke="t")
    m.add_load_case(LF, "Q")
    m.netz.ziellaenge, m.netz.dichte = 0.25, "eigene"
    from statik3d import mesher
    with _still():
        mesher.modell_vernetzen(m, [], workers=1)
    for n in _knoten(m, np.abs(m.nodes[:, 2]) < 1e-9):
        m.fix(n, "all")
    g = spiegeln(m, wahl(m, f)) if wahl is not None else []
    kb = {0: DofBehaviour("rigid"), 1: DofBehaviour("rigid"), 2: DofBehaviour("rigid", failure="zug")}
    m.add_kontaktbedingung("K", flaechennamen=["Blech"], gegenkoerper=["Block"], behaviour=kb)
    log = []
    with _still():
        fugen.kontaktfugen_ausfuehren(m, log)
    m.add_geometrielast("Blech", -50e3, art="flaeche", case=LF, bezug="global", achse="z")
    blech = {int(k) for e in f.elemente for k in m.elements[int(e)].nodes}
    ecke = min(blech, key=lambda k: float(np.linalg.norm(m.nodes[k] - [1.0, 1.0, 0.2])))
    m.load_node(ecke, Fz=8e3, case=LF)
    m.lasten_verteilen()
    zeile = next((z for z in log if "Kontaktbedingung K" in z), "")
    return m, f, g, zeile


def _fugenprotokoll(zeile: str) -> tuple:
    """(liegt auf, Auszug) aus der Protokollzeile der Fuge: „100 % aufliegend“
    und kein durchdringender Knoten."""
    import re
    a = re.search(r"Spalt (\d+) % aufliegend", zeile)
    d = re.search(r"(\d+) durchdringend, tiefste ([\d.,]+) mm", zeile)
    auszug = (f"{a.group(1)} % aufliegend" if a else "Anteil aufliegend fehlt") +         (f", {d.group(1)} durchdringend bis {d.group(2).replace('.', ',')} mm" if d else "")
    return bool(a and a.group(1) == "100" and not d), auszug


def test_fuge_an_schale():
    """Kontaktfuge zwischen Blech (Schale) und Block, nach der Spiegelung
    ausgefuehrt. Bezug: alle Blechelemente gespiegelt, Normale zum Block -
    das Protokoll der Fuge meldet 100 % aufliegend. Verglichen werden „wie
    vernetzt“ (Normale vom Block weg) und „jedes dritte gespiegelt“: Protokoll
    der Fuge (Sollwert 100 % aufliegend, kein Knoten durchdringend) und
    Rechnung gegen den Bezug."""
    m0, _f0, g0, z0 = _blech_auf_block(lambda m, f: list(f.elemente))
    r0 = rechnen(m0)
    ok0, a0 = _fugenprotokoll(z0)
    check(f"shell4: Fuge Blech auf Block, alle {len(g0)} Blechelemente zum Block gespiegelt: Fuge liegt auf "
          "[Rechnung]", ok0, a0)
    for text, wahl in (("wie vernetzt (Normale vom Block weg)", None), ("jedes dritte Element gespiegelt", einige)):
        m1, _f1, g, z1 = _blech_auf_block(wahl)
        r1 = rechnen(m1)
        ok1, a1 = _fugenprotokoll(z1)
        check(f"shell4: Fuge Blech auf Block, {text}: Fuge liegt auf [Rechnung]", ok1, a1)
        physik(f"shell4: Fuge Blech auf Block, {text}, gegen „alle zum Block gespiegelt“", m0, r0, m1, r1)


# ---------------------------------------------------------------------------
# 6) Netz ohne Flaeche: Nastran-Import
# ---------------------------------------------------------------------------
def _bdf(gespiegelt: set, p: float = -5e3) -> str:
    """Zwei Platten als CQUAD4 ohne Flaeche: A (2 x 1 m, 6 x 3, bei x = 0
    eingespannt, Normale +z) und B (daneben, 1 x 1 m, 2 x 2, ganz gespiegelt
    in der zweiten Datei). PLOAD2 mit dem Vorzeichen des Elements."""
    z = ["BEGIN BULK", "MAT1,1,2.1+11,,0.3,7850.0", "PSHELL,1,1,0.01"]
    gid = {}

    def grid(x, y):
        k = (round(x, 9), round(y, 9))
        if k not in gid:
            gid[k] = len(gid) + 1
            z.append(f"GRID,{gid[k]},,{x:.6f},{y:.6f},0.0")
        return gid[k]
    eid = 0
    spc = []
    for x0, nx, ny, lx, ly in ((0.0, 6, 3, 2.0, 1.0), (3.0, 2, 2, 1.0, 1.0)):
        for i in range(nx):
            for j in range(ny):
                eid += 1
                a = grid(x0 + lx * i / nx, ly * j / ny)
                b = grid(x0 + lx * (i + 1) / nx, ly * j / ny)
                c = grid(x0 + lx * (i + 1) / nx, ly * (j + 1) / ny)
                d = grid(x0 + lx * i / nx, ly * (j + 1) / ny)
                k = [a, d, c, b] if eid in gespiegelt else [a, b, c, d]
                z.append(f"CQUAD4,{eid},1,{k[0]},{k[1]},{k[2]},{k[3]}")
                z.append(f"PLOAD2,1,{-p if eid in gespiegelt else p},{eid}")
        for j in range(ny + 1):
            spc.append(grid(x0, ly * j / ny))
    z.append("SPC1,1,123456," + ",".join(str(s) for s in spc))
    z.append(f"FORCE,1,{grid(2.0, 1.0)},0,1.0,0.0,2000.0,-1000.0")
    z.append(f"FORCE,1,{grid(2.0, 0.0)},0,1.0,-3000.0,0.0,0.0")
    z.append("ENDDATA")
    return "\n".join(z) + "\n"


def _import(gespiegelt: set):
    from statik3d.importers import import_file
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "platten.bdf")
        with open(p, "w") as fh:
            fh.write(_bdf(gespiegelt))
        with _still():
            m = import_file(p, log=[])
    return m


def test_nastran_import():
    """Nastran-Netz ohne Flaeche: in A jedes dritte Element ab dem zweiten
    gespiegelt, B ganz. PLOAD2 wirkt in Nastran nach der Elementnormalen und
    ist darum mit dem Element gespiegelt (gleiche Physik). Die Anzeige wird
    nur an A verglichen: B hat ohne Flaeche keine Seite, die „oben“ heisst."""
    gesp = {e for e in range(1, 19) if (e - 1) % 3 == 1} | set(range(19, 23))
    m0, m1 = _import(set()), _import(gesp)
    fall = next(n for n in m0.load_cases if n.startswith("SID"))
    r0, r1 = rechnen(m0, fall), rechnen(m1, fall)
    titel = f"Nastran-Import ohne Fläche: {len(gesp)} von {len(m1.elements)} CQUAD4 gespiegelt, PLOAD2 mitgespiegelt"
    physik(titel, m0, r0, m1, r1, fall=fall)
    m0.load_cases[LF] = m0.load_cases[fall]
    m1.load_cases[LF] = m1.load_cases[fall]
    anzeige(titel + " (Platte A)", m0, r0, m1, r1, elemente=range(18))
    # ΔT_z je Element und ein unsymmetrisches Laminat: mit dem Element gespiegelt
    from statik3d.model import ShellProp
    erg = []
    for g, m in ((set(), _import(set())), (gesp, _import(gesp))):
        m.shells["PID 1"].lagen = [dict(x) for x in UNSYM]
        m.add_shell_prop(ShellProp("PID 1 umgekehrt", 0.010, lagen=[dict(x) for x in reversed(UNSYM)]))
        fall = next(n for n in m.load_cases if n.startswith("SID"))
        for i, el in enumerate(m.elements):
            umgekehrt = (i + 1) in g
            if umgekehrt:
                el.sec = "PID 1 umgekehrt"
            m.load_temp(i, 0.0, (-30.0 if umgekehrt else 30.0), case=fall)
        erg.append((m, rechnen(m, fall), fall))
    (m0, r0, fall), (m1, r1, _) = erg
    physik("Nastran-Import: dazu ΔT_z = 30 K je Element und unsymmetrisches Laminat, beides mit dem "
           "Element gespiegelt", m0, r0, m1, r1, fall=fall)


# ---------------------------------------------------------------------------
# 7) Beulnachweis
# ---------------------------------------------------------------------------
def _beulplatte(typ):
    """Blechfeld 2 x 1 m, 10 mm, Rand x = 0 in x gehalten, alle Knoten in z;
    am Rand x = 2 Druck 300 kN und Schub 100 kN."""
    m, f = _platte(typ, lager=False)
    for n in range(m.nn):
        m.fix(n, [2])
    for n in _knoten(m, np.abs(m.nodes[:, 0]) < 1e-9):
        m.fix(n, [0, 1])
    rand = _knoten(m, np.abs(m.nodes[:, 0] - 2.0) < 1e-9)
    for n in rand:
        m.load_node(n, Fx=-3e5 / len(rand), Fy=1e5 / len(rand), case=LF)
    m.add_beulfeld("B1", list(f.elemente))
    return m, f


def test_beulen():
    from statik3d.ec3 import beulen
    for perm, art in ((SPIEGEL, "gespiegelt"), (ZYKLISCH, "zyklisch umnummeriert (nicht gespiegelt)")):
        for typ in ("shell4", "shell8"):
            (m0, _f0, _), (m1, _f1, g) = _paar(lambda t=typ: _beulplatte(t), einige, perm=perm)
            r0, r1 = rechnen(m0), rechnen(m1)
            physik(f"{typ}: Beulfeld unter Druck und Schub, {len(g)} Elemente {art}", m0, r0, m1, r1)
            b0 = beulen.check_beulfeld(m0, m0.beulfelder["B1"], r0)
            b1 = beulen.check_beulfeld(m1, m1.beulfelder["B1"], r1)
            s0, s1 = b0.get("spannungen", {}), b1.get("spannungen", {})
            schl = [k for k in ("sigma_u_max", "sigma_u_min", "sigma_v_max", "sigma_v_min", "tau")]
            d = max((_rel([s0.get(k, np.nan)], [s1.get(k, np.nan)]) for k in schl), default=float("inf"))
            d_eta = _rel([b0.get("eta_interaktion", np.nan)], [b1.get("eta_interaktion", np.nan)])
            check(f"{typ}: Beulnachweis (beulen.feldspannungen), {len(g)} Elemente {art} [Anzeige]",
                  max(d, d_eta) <= TOL,
                  f"σ_u max {s0.get('sigma_u_max', 0) / 1e6:.2f} → {s1.get('sigma_u_max', 0) / 1e6:.2f}, "
                  f"σ_v max {s0.get('sigma_v_max', 0) / 1e6:.2f} → {s1.get('sigma_v_max', 0) / 1e6:.2f}, "
                  f"τ {s0.get('tau', 0) / 1e6:.2f} → {s1.get('tau', 0) / 1e6:.2f} N/mm², "
                  f"η {b0.get('eta_interaktion', 0):.4f} → {b1.get('eta_interaktion', 0):.4f}".replace(".", ","))


def main():
    for t in (test_anzeige_globale_last, test_anzeige_zyklisch, test_flaechenachsen_bild,
              test_flaechenlasten, test_flaechenlast_vor_dem_vernetzen, test_elementlast_mit_gespiegelt,
              test_temperatur, test_laminat_unsymmetrisch, test_wasserdruck,
              test_wind_freie_wand_und_schild, test_wind_freie_wand_richtung, test_wind_gebaeude, test_flaechenlager_flaechenachsen,
              test_kontakt_an_schale, test_fuge_an_schale, test_nastran_import, test_beulen):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:          # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
        sys.stdout.flush()
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    sys.stdout.flush()
    return 0 if not schlecht else 1


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
