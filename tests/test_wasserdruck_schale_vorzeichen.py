"""
Wasserdruck an Schalen: Seite des Wassers aus Eingabe und Geometrie
(Befund vom 11.11.2026, Kur 12.11.2026, statik3d/wasserdruck.py).

Nachstellung am Stand eb88ecc: Wand 2 m breit, 3 m hoch in der Ebene y = 0,
Oberwasser 2,5 m, als Schalenflaeche. Die Maske sagt „senkrecht zur Fläche,
gegen die Normale (in den Körper)“ (seite +1); an der Schale wirkte die Last
aber MIT der Elementnormale (ΣF −61,3 kN bei Normale −y), die Eintraege der
Maske waren vertauscht. Strömungsnumerisch ebenso: Oberwasser an der Oberseite
(+Normale) drueckte die Wand zum Oberwasser hin. Am Volumen und mit globaler
Lastrichtung war es richtig. Zweiter Befund: der Zwischenspeicher des
Druckfelds erkannte eine gedrehte Wand bei gleicher Knotenzahl nicht
(ΣF −61,22 kN aus dem Speicher gegen +61,22 kN frisch).

Sollwert (Handrechnung): F = ½ ρ g h² b = ½ · 1000 · 9,81 · 2,5² · 2 =
61 312,5 N, Richtung vom Wasser weg. Zweiter Weg: die Wand an allen Raendern
gelenkig gelagert gerechnet, Summe der Lagerkraefte und Durchbiegung.

Aufruf:  python -m tests.test_wasserdruck_schale_vorzeichen
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

RESULTS = []
RHO, G = 1000.0, 9.81
H_OW, B = 2.5, 2.0
F_HAND = 0.5 * RHO * G * H_OW ** 2 * B          # 61 312,5 N
#: Umlauf A: Normale −y; Umlauf B: Normale +y
ECKEN_A = [[0, 0, 0], [2, 0, 0], [2, 0, 3], [0, 0, 3]]
ECKEN_B = [[0, 0, 0], [0, 0, 3], [2, 0, 3], [2, 0, 0]]


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:96s} {detail}")
    return ok


def _modell():
    from statik3d.model import Model, Material, ShellProp
    m = Model("Wand")
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("t10", 0.010))
    return m


def _wand(ecken, ordnung=1):
    from statik3d import mesher
    m = _modell()
    base = m.nn
    m.add_nodes(np.asarray(ecken, float))
    lin = []
    for i in range(4):
        m.add_line(f"L{i}", [base + i, base + (i + 1) % 4])
        lin.append(f"L{i}")
    f = m.add_flaeche("W", lin, material="S235", dicke="t10")
    f.teilung = [8, 8]
    m.netz.ordnung = ordnung
    m.netz.ziellaenge = 3.0 / 8
    mesher.modell_vernetzen(m, log=[], workers=1)
    return m


def _summe(m, fall):
    from statik3d import solver
    F = np.asarray(solver.case_loads(m, {fall: 1.0}, None)[0], float).reshape(-1, 6)
    return F[:, :3].sum(axis=0)


def _last(m, **kw):
    from statik3d.wasserdruck import Wasserdruck, lasten_erzeugen
    wd = Wasserdruck("W1", flaechen=["W"], h_ow=H_OW, **kw)
    k = lasten_erzeugen(m, wd)
    return wd, k, _summe(m, wd.lastfall)


def _umdrehen_jedes_zweite(m):
    """Knotenreihenfolge jedes zweiten Schalenelements umkehren (Normale dreht)."""
    n = alle = 0
    for i, e in enumerate(m.elements):
        if e.typ == "shell4":
            alle += 1
            if i % 2 == 0:
                e.nodes = [e.nodes[0], e.nodes[3], e.nodes[2], e.nodes[1]]
                n += 1
    return n, alle


def _soll(name, S, richtung, F=F_HAND, tol=0.005):
    """ΣF zeigt in ``richtung`` (Einheitsvektor) mit dem Betrag F."""
    d = np.asarray(richtung, float)
    ok = abs(float(S @ d) - F) <= tol * F and float(np.linalg.norm(S - (S @ d) * d)) <= tol * F
    return check(name, ok, f"ΣF = ({S[0] / 1e3:.3f}; {S[1] / 1e3:.3f}; {S[2] / 1e3:.3f}) kN, "
                           f"Soll {F / 1e3:.3f} kN in ({d[0]:+.0f}; {d[1]:+.0f}; {d[2]:+.0f})")


# ---------------------------------------------------------------------------
def test_analytisch_seite():
    """seite +1 = gegen die Flächennormale, seite −1 = mit ihr."""
    for nm, ecken, n in (("A", ECKEN_A, (0, -1, 0)), ("B", ECKEN_B, (0, 1, 0))):
        n = np.asarray(n, float)
        _wd, _k, S = _last(_wand(ecken), verfahren="analytisch", seite=1, absenkung=False)
        _soll(f"Umlauf {nm} (Normale {n[1]:+.0f}y), analytisch, seite +1: Last gegen die Normale", S, -n)
        _wd, k, S = _last(_wand(ecken), verfahren="analytisch", seite=-1, absenkung=False)
        _soll(f"Umlauf {nm}, analytisch, seite −1: Last mit der Normale", S, n)
        Kf = np.asarray(k["kontrolle"]["F"], float)
        check(f"Umlauf {nm}, seite −1: Kontrollsumme des Generierers = ΣF des Lastfalls",
              float(np.linalg.norm(Kf - S)) <= 1e-6 * F_HAND)


def test_analytisch_quadratisch():
    _wd, _k, S = _last(_wand(ECKEN_A, ordnung=2), verfahren="analytisch", seite=1, absenkung=False)
    _soll("Umlauf A quadratisch (shell8), analytisch, seite +1: gegen die Normale", S, (0, 1, 0))


def test_elementreihenfolge():
    """Die Seite des Wassers haengt nicht an der Knotenreihenfolge des Elements."""
    m = _wand(ECKEN_A)
    wd, _k, S0 = _last(m, verfahren="analytisch", seite=1, absenkung=False)
    n, alle = _umdrehen_jedes_zweite(m)
    m.lasten_verteilen()
    S1 = _summe(m, wd.lastfall)
    _soll(f"analytisch: {n} von {alle} Elementen umgedreht, ΣF unverändert gegen die Flächennormale", S1, (0, 1, 0))
    check("… und bitgleich zur Summe vor dem Umdrehen (auf 1e-9)",
          float(np.linalg.norm(S1 - S0)) <= 1e-9 * F_HAND)
    m = _wand(ECKEN_A)
    _umdrehen_jedes_zweite(m)
    _wd, _k, S = _last(m, verfahren="numerisch", ow_flaeche="W", ow_seite="Oberseite")
    _soll("numerisch: jedes zweite Element umgedreht, Oberwasser an der Oberseite: vom Wasser weg",
          S, (0, 1, 0), tol=0.01)


def test_alte_last_ohne_flaechennormale():
    """Eine Last aus einer Datei ohne gespeicherte Flaechennormale rechnet mit
    der Elementnormale als Bezug - an einer gleichsinnig vernetzten Flaeche richtig."""
    m = _wand(ECKEN_A)
    wd, _k, _S = _last(m, verfahren="analytisch", seite=1, absenkung=False)
    for lc in m.load_cases.values():
        for gl in lc.geometrielasten:
            if gl.verlauf.get("art") == "wasser":
                gl.verlauf.pop("normale_flaeche", None)
    m.lasten_verteilen()
    _soll("Last ohne gespeicherte Flächennormale: seite +1 gegen die Normale", _summe(m, wd.lastfall), (0, 1, 0))


def test_numerisch_seite():
    """Oberwasser an der Oberseite (+Normale): die Last zeigt vom Oberwasser weg (−Normale)."""
    for nm, ecken, n in (("A", ECKEN_A, (0, -1, 0)), ("B", ECKEN_B, (0, 1, 0))):
        n = np.asarray(n, float)
        _wd, k, S = _last(_wand(ecken), verfahren="numerisch", ow_flaeche="W", ow_seite="Oberseite")
        _soll(f"Umlauf {nm}, numerisch, Oberwasser an der Oberseite: Last gegen die Normale", S, -n, tol=0.01)
        check(f"Umlauf {nm}, numerisch: |ΣF| = Resultierende des Druckfelds (0,5 %)",
              abs(float(np.linalg.norm(S)) - abs(float(k["F"]))) <= 0.005 * abs(float(k["F"])),
              f"|ΣF| {np.linalg.norm(S) / 1e3:.3f} kN, Feld {k['F'] / 1e3:.3f} kN")
        _wd, _k, S = _last(_wand(ecken), verfahren="numerisch", ow_flaeche="W", ow_seite="Unterseite")
        _soll(f"Umlauf {nm}, numerisch, Oberwasser an der Unterseite: Last mit der Normale", S, n, tol=0.01)


def test_dynamisch():
    """Druckschwankung (analytisch, ueberstroemt) wirkt wie die statische Last vom Wasser weg."""
    m = _wand(ECKEN_A)
    wd, k, S = _last(m, verfahren="analytisch", seite=1, absenkung=False, ueberstroemt=True,
                     cp_dyn=0.1, z_ok=2.0)
    Sd = _summe(m, wd.lastfall_dyn)
    check("dynamischer Lastfall angelegt", bool(wd.lastfall_dyn) and k["dp_dyn"] > 0,
          f"Δp = {k['dp_dyn']:.1f} Pa")
    check("Druckschwankung an der Schale gegen die Normale (+y), wie die statische Last",
          Sd[1] > 0 and S[1] > 0, f"ΣF_dyn,y = {Sd[1] / 1e3:.3f} kN, ΣF_y = {S[1] / 1e3:.3f} kN")


def test_global_und_volumen_unveraendert():
    _wd, _k, S = _last(_wand(ECKEN_A), verfahren="analytisch", richtung=[0, 1, 0], absenkung=False)
    _soll("globale Richtung +y an Umlauf A: unverändert in +y", S, (0, 1, 0))
    _wd, _k, S = _last(_wand(ECKEN_B), verfahren="analytisch", richtung=[0, 1, 0], absenkung=False)
    _soll("globale Richtung +y an Umlauf B: unverändert in +y", S, (0, 1, 0))
    # Volumen: Quader 2 × 0,1 × 3 m, benetzt die Seite y = 0 (Aussennormale −y)
    from statik3d import mesher
    from statik3d.wasserdruck import Wasserdruck, lasten_erzeugen
    m = _modell()
    P = np.array([[0, 0, 0], [2, 0, 0], [2, .1, 0], [0, .1, 0], [0, 0, 3], [2, 0, 3], [2, .1, 3], [0, .1, 3]], float)
    m.add_nodes(P)
    z = iter(range(1, 100))

    def li(a, b):
        nm = f"K{next(z)}"
        m.add_line(nm, [a, b])
        return nm
    R = [[li(o + i, o + (i + 1) % 4) for i in range(4)] for o in (0, 4)]
    V = [li(i, i + 4) for i in range(4)]
    m.add_flaeche("Boden", R[0], material="S235")
    m.add_flaeche("Dach", R[1], material="S235")
    for i in range(4):
        m.add_flaeche(f"M{i}", [R[0][i], V[(i + 1) % 4], R[1][i], V[i]], material="S235")
    k = m.add_koerper("K", ["Boden", "Dach", "M0", "M1", "M2", "M3"], material="S235")
    m.netz.ziellaenge = 0.375
    k.teilung = [8, 1, 8]
    mesher.modell_vernetzen(m, log=[], workers=1)
    wd = Wasserdruck("W1", flaechen=["M0"], h_ow=H_OW, verfahren="analytisch", seite=1, absenkung=False)
    lasten_erzeugen(m, wd)
    _soll("Volumen, seite +1: in den Körper (+y), unverändert", _summe(m, wd.lastfall), (0, 1, 0), tol=0.01)


def test_zweiter_weg_lagerkraefte():
    """Weg 2: Wand an allen Raendern gelenkig, rechnen; ΣR = −ΣF, Durchbiegung vom Wasser weg."""
    from statik3d import solver
    for nm, ecken in (("A", ECKEN_A), ("B", ECKEN_B)):
        m = _wand(ecken)
        X = m.nodes[:, :3]
        for i, x in enumerate(X):
            if min(abs(x[0]), abs(x[0] - 2), abs(x[2]), abs(x[2] - 3)) < 1e-9:
                m.fix(int(i), [0, 1, 2])
        # Oberwasser auf der Seite −y: Umlauf A seite +1 (Normale −y), Umlauf B seite −1
        wd, _k, _S = _last(m, verfahren="analytisch", seite=1 if nm == "A" else -1, absenkung=False)
        res = solver.solve_all(m, workers=1, combinations=False)
        r = res.cases[wd.lastfall]
        R = np.asarray(r.reactions, float)[:, :3].sum(axis=0)
        U = np.asarray(r.u)
        mitte = int(np.argmin(np.linalg.norm(X - np.array([1.0, 0.0, 1.5]), axis=1)))
        _soll(f"Umlauf {nm}, Oberwasser bei −y: Lagerkräfte ΣR gegen die Last (−y)", R, (0, -1, 0))
        check(f"Umlauf {nm}: Durchbiegung in Wandmitte vom Wasser weg (u_y > 0)", U[mitte, 1] > 0,
              f"u_y = {U[mitte, 1] * 1000:+.3f} mm")


def test_zwischenspeicher_geometrie():
    """Gleiche Knoten-, Element- und Flaechenzahl, gedrehte Wand: kein altes Druckfeld."""
    m = _wand(ECKEN_A)
    _wd, _k, S0 = _last(m, verfahren="numerisch", ow_flaeche="W", ow_seite="Oberseite")
    m.nodes[:, 0] = 2.0 - m.nodes[:, 0]          # um die z-Achse um 180° drehen: Normale +y
    _wd, _k, S1 = _last(m, verfahren="numerisch", ow_flaeche="W", ow_seite="Oberseite")
    from statik3d import wasserdruck as wdm
    wdm._FELD_CACHE.clear()
    wdm._FELDER.clear()
    _wd, _k, S2 = _last(m, verfahren="numerisch", ow_flaeche="W", ow_seite="Oberseite")
    check("nach dem Drehen: Druckfeld aus dem Speicher = frisch gerechnet",
          float(np.linalg.norm(S1 - S2)) <= 1e-6 * F_HAND,
          f"Speicher ΣF_y {S1[1] / 1e3:.3f} kN, frisch {S2[1] / 1e3:.3f} kN")
    _soll("gedrehte Wand (Normale +y), Oberwasser an der Oberseite: Last in −y", S1, (0, -1, 0), tol=0.01)
    check("vor dem Drehen in +y", S0[1] > 0, f"ΣF_y {S0[1] / 1e3:.3f} kN")


def test_verfahrenstabelle():
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("wasserdruck_schale_seite")
    check("Verfahrenstabelle: Wasserdruck an Schalen (Stand 32) als Fehlerkorrektur",
          mk is not None and mk.wechsel[-1].stand == 32 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR
          and rv.VERFAHRENSSTAND >= 32, f"Stand {rv.VERFAHRENSSTAND}")
    if mk is None:
        return
    m1 = _wand(ECKEN_A)
    _last(m1, verfahren="analytisch", seite=1)
    m2 = _wand(ECKEN_A)
    _last(m2, verfahren="analytisch", richtung=[0, 1, 0])
    m3 = _wand(ECKEN_A)
    check("… betroffen: Schale ohne globale Richtung ja, mit globaler Richtung nein, ohne Wasserdruck nein",
          mk.betrifft(m1) and not mk.betrifft(m2) and not mk.betrifft(m3))
    # numerisch mit globaler Richtung: betroffen nur, wenn die Elemente der
    # Oberwasser-Referenzflaeche gegen ihren Randumlauf zeigen. Seit dem
    # 12.11.2026 (statik3d.schalenlage) richten Vernetzer und Generator die
    # Elemente zur Flaeche aus; den Zustand einer alten Datei stellt darum
    # erst das Spiegeln nach dem Erzeugen her (so lag er im gespeicherten
    # Modell, solange niemand neu gerechnet hat)
    m4 = _wand(ECKEN_A)
    _last(m4, verfahren="numerisch", richtung=[0, 1, 0], ow_flaeche="W", ow_seite="Oberseite")
    for e in m4.elements:
        if e.typ == "shell4":
            e.nodes = [e.nodes[0], e.nodes[3], e.nodes[2], e.nodes[1]]
    m5 = _wand(ECKEN_A)
    _last(m5, verfahren="numerisch", richtung=[0, 1, 0], ow_flaeche="W", ow_seite="Oberseite")
    check("… numerisch mit globaler Richtung: Referenzfläche gegen ihren Umlauf vernetzt ja, sonst nein",
          mk.betrifft(m4) and not mk.betrifft(m5))


def main():
    for t in (test_analytisch_seite, test_analytisch_quadratisch, test_elementreihenfolge,
              test_alte_last_ohne_flaechennormale, test_numerisch_seite, test_dynamisch,
              test_global_und_volumen_unveraendert, test_zweiter_weg_lagerkraefte,
              test_zwischenspeicher_geometrie, test_verfahrenstabelle):
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
