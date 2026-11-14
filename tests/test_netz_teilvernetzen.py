"""
Befunde B9 und B10 der Befundliste vom 14.11.2026, zur Behebung freigegeben
am 14.11.2026.

B9: Eine einzelne Schalenflaeche neu vernetzen trennte sie still von der
schon vernetzten Nachbarflaeche: der Vernetzer teilte nur die gewaehlten
Flaechen gemeinsam (gui.main._vernetzen_netz, mesher.modell_vernetzen mit
``flaechen=[...]``), die gemeinsame Linie bekam neue Knoten, der Nachbar
behielt die alten. Platte 4 x 2 m aus F1/F2 (gemeinsame Linie L7 bei
x = 2), gelenkig an x = 0 und x = 4, Eigengewicht: alles vernetzt
w_max 149,59 mm, danach nur F2 neu vernetzt 397,70 mm, 2 von 12 Knoten auf
x = 2 gemeinsam, ohne Meldung. Jetzt nimmt der Vernetzer die schon
vernetzten Nachbarflaechen mit (Protokollzeile), und vor der Rechnung meldet
die Eingabepruefung ein Schalennetz, das an einer gemeinsamen Linie
getrennt ist.

B10: Eine gerade Linie gegen eine Polylinie mit Zwischenknoten auf derselben
Strecke blieb unverbunden (F1 mit L7 = [1, 4], F2 mit L7p = [1, 6, 4]):
407,02 statt 149,99 mm (dieselbe Strecke mit Einzellinien La/Lb). Jetzt
sind die Abschnitte der Polylinie im Netz Linien wie jede andere.

Zwei Wege fuer die Zahlen: dieselbe Platte mit gemeinsamer Linie bzw. mit
Einzellinien, ganz vernetzt (Referenz), gegen die Platte nach dem
Teilvernetzen bzw. mit Polylinie.

Aufruf:  python -m tests.test_netz_teilvernetzen
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
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_netz_teilvernetzen_"), "einstellungen.json")

import numpy as np  # noqa: E402

from statik3d import diagnose, mesher, solver                           # noqa: E402
from statik3d import rechenverfahren as rv                              # noqa: E402
from statik3d.model import DofBehaviour, Material, Model, ShellProp     # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK  ' if ok else 'FAIL'} {name:<96} {detail}")
    return bool(ok)


def still(f, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return f(*a, **kw)


def platte(art: str = "gemeinsam", dritte: bool = False, fern: bool = False) -> Model:
    """Platte 4 x 2 m aus F1 (x 0..2) und F2 (x 2..4), t = 10 mm, gelenkig an
    x = 0 und x = 4, Eigengewicht (wie ag_pruef_8/b5_ueberlappend.py).
    ``art`` an x = 2: "gemeinsam" (L7 beiden), "doppelt" (F2 eigene L7d),
    "polylinie" (F1 L7 = [1, 4], F2 L7p = [1, 6, 4]), "einzeln" (F1 L7, F2
    La/Lb), "einzeln_polylinie" (F1 La/Lb, F2 L7p). ``dritte``: F3 (x 4..6)
    an L3 dazu, gelenkig an x = 6 statt 4. ``fern``: eine eigene Platte F9
    weit daneben, ohne gemeinsame Linie."""
    m = Model()
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("D10", 0.01))
    for p in [(0, 0, 0), (2, 0, 0), (4, 0, 0), (4, 2, 0), (2, 2, 0), (0, 2, 0), (2, 1, 0)]:
        m.add_node(*p)
    for i, (a, b) in enumerate([(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 0)]):
        m.add_line(f"L{i + 1}", [a, b])
    if art == "gemeinsam":
        m.add_line("L7", [1, 4]); r1 = ["L7"]; r2 = ["L7"]
    elif art == "doppelt":
        m.add_line("L7", [1, 4]); m.add_line("L7d", [4, 1]); r1 = ["L7"]; r2 = ["L7d"]
    elif art == "polylinie":
        m.add_line("L7", [1, 4]); m.add_line("L7p", [1, 6, 4]); r1 = ["L7"]; r2 = ["L7p"]
    elif art == "einzeln":
        m.add_line("L7", [1, 4]); m.add_line("La", [1, 6]); m.add_line("Lb", [6, 4]); r1 = ["L7"]
        r2 = ["La", "Lb"]
    elif art == "einzeln_polylinie":
        m.add_line("La", [1, 6]); m.add_line("Lb", [6, 4]); m.add_line("L7p", [4, 6, 1])
        r1 = ["La", "Lb"]; r2 = ["L7p"]
    else:
        raise ValueError(art)
    m.add_flaeche("F1", ["L1"] + r1 + ["L5", "L6"], material="S235", dicke="D10")
    m.add_flaeche("F2", ["L2", "L3", "L4"] + r2, material="S235", dicke="D10")
    lager = ["L6", "L3"]
    if dritte:
        n6 = m.add_node(6, 0, 0); n7 = m.add_node(6, 2, 0)
        m.add_line("L8", [2, n6]); m.add_line("L9", [n6, n7]); m.add_line("L10", [n7, 3])
        m.add_flaeche("F3", ["L8", "L9", "L10", "L3"], material="S235", dicke="D10")
        lager = ["L6", "L9"]
    if fern:
        k = [m.add_node(x, y, 0) for x, y in [(20, 0), (21, 0), (21, 1), (20, 1)]]
        for i in range(4):
            m.add_line(f"P{i}", [k[i], k[(i + 1) % 4]])
        m.add_flaeche("F9", ["P0", "P1", "P2", "P3"], material="S235", dicke="D10")
        ls9 = m.add_line_support([], name="LP")
        ls9.linien = ["P0", "P1", "P2", "P3"]
        for d in (0, 1, 2):
            ls9.behaviour[d] = DofBehaviour("rigid")
    m.add_load_case("LF1", "G")
    m.case("LF1").gravity = [0, 0, -9.81]
    ls = m.add_line_support([], name="LL")
    ls.linien = lager
    for d in (0, 1, 2):
        ls.behaviour[d] = DofBehaviour("rigid")
    return m


def w_max(m) -> float:
    r = still(solver.solve_all, m, workers=1, combinations=False).cases["LF1"]
    dran = sorted({int(k) for e in m.elements for k in e.nodes})
    return float(np.abs(np.asarray(r.u)[dran, 2]).max())


def auf_x(m, f, x=2.0) -> set:
    X = np.asarray(m.nodes)
    return {int(k) for e in m.flaechen[f].elemente for k in m.elements[int(e)].nodes
            if abs(X[int(k)][0] - x) < 1e-9}


def gemeinsam_x(m, a="F1", b="F2", x=2.0) -> tuple:
    ka, kb = auf_x(m, a, x), auf_x(m, b, x)
    return len(ka), len(kb), len(ka & kb)


def gui_vernetzen(m, flaechen, koerper=None) -> list:
    """Der Weg der Oberflaeche (MainWindow._vernetzen mit _netz_loeschen), das
    Fenster als Attrappe - wie tests.test_netz_altbefunde.gui_vernetzen."""
    import importlib
    import time
    from unittest import mock
    G = importlib.import_module("statik3d.gui.main")
    s = mock.MagicMock()
    s.model = m
    s._fortschritt_t0 = time.time()
    s._netz_loeschen = G.MainWindow._netz_loeschen.__get__(s)
    s._vernetzen_netz = G.MainWindow._vernetzen_netz.__get__(s)
    with mock.patch.object(G, "QtWidgets"):
        still(G.MainWindow._vernetzen, s, flaechen, koerper or [])
    return [str(c.args[0]) for c in s.log.appendPlainText.call_args_list if c.args]


def mitvernetzt_zeile(log) -> list:
    return [z for z in log if "mitvernetzt" in z]


def getrennt_vernetzen(m) -> None:
    """Jede Flaeche fuer sich (mesh_flaeche): getrennte Netzknoten an der
    gemeinsamen Linie wie nach dem Teilvernetzen vor der Behebung."""
    from statik3d import netzdichte as nd
    nd.anwenden(m, m.netz, list(m.flaechen.values()), [], [])
    with contextlib.redirect_stdout(io.StringIO()):
        for f in m.flaechen.values():
            mesher.mesh_flaeche(m, f, [])


# ---------------------------------------------------------------------------
# B9: eine Flaeche einzeln neu vernetzen
# ---------------------------------------------------------------------------
def test_b9_teilvernetzen(weg):
    ref = platte("gemeinsam")
    still(mesher.modell_vernetzen, ref, [], workers=1)
    w_ref = w_max(ref)
    for art in ("gemeinsam", "doppelt"):
        m = platte(art)
        still(mesher.modell_vernetzen, m, [], workers=1)
        if weg == "Oberfläche":
            log = gui_vernetzen(m, [m.flaechen["F2"]])
        else:
            log = []
            still(mesher.modell_vernetzen, m, log, workers=1, flaechen=[m.flaechen["F2"]], koerper=[])
        n1, n2, gem = gemeinsam_x(m)
        w = w_max(m)
        check(f"**B9, {weg}, {art}: nur F2 neu vernetzt – F1 wird mitvernetzt, alle Knoten auf x = 2 gemeinsam, "
              "w_max wie ganz vernetzt (zwei Wege)**",
              n1 == n2 == gem and gem > 2 and abs(w - w_ref) <= 1e-6 * w_ref,
              f"F1 {n1}, F2 {n2}, gemeinsam {gem}; w_max {w * 1e3:.2f} mm, ganz vernetzt {w_ref * 1e3:.2f} mm")
        z = mitvernetzt_zeile(log)
        check(f"… {weg}, {art}: das Protokoll nennt die mitvernetzte Fläche F1 und die Linie",
              len(z) == 1 and "F1" in z[0] and ("L7" in z[0]), z[0][:160] if z else "keine Zeile")
        check(f"… {weg}, {art}: danach keine unverbundene Schalenlinie",
              not mesher.unverbundene_schalenlinien(m), str(mesher.unverbundene_schalenlinien(m)))


def test_b9_ohne_netz():
    """Weg „Nur das Objekt ohne Netz“: F1 hat ein Netz, F2 noch keins."""
    m = platte("gemeinsam")
    still(mesher.modell_vernetzen, m, [], workers=1, flaechen=[m.flaechen["F1"]], koerper=[])
    n_f1 = len(m.flaechen["F1"].elemente)
    log = gui_vernetzen(m, [m.flaechen["F2"]])
    n1, n2, gem = gemeinsam_x(m)
    check("**B9, nur das Objekt ohne Netz (F2): F1 mit Netz wird mitvernetzt, die Netze sind verbunden**",
          n_f1 > 0 and n1 == n2 == gem and gem > 2 and mitvernetzt_zeile(log),
          f"F1 {n1}, F2 {n2}, gemeinsam {gem}; {mitvernetzt_zeile(log)[:1]}")


def test_b9_kette_und_fern():
    """F1|F2|F3 in Reihe und eine ferne Platte F9: nur F1 neu vernetzen nimmt F2
    und - weil F2 neue Knoten auf L3 bekommt - auch F3 mit; F9 bleibt, wie sie ist."""
    ref = platte("gemeinsam", dritte=True, fern=True)
    still(mesher.modell_vernetzen, ref, [], workers=1)
    w_ref = w_max(ref)
    m = platte("gemeinsam", dritte=True, fern=True)
    still(mesher.modell_vernetzen, m, [], workers=1)
    X = np.asarray(m.nodes)
    f9_vor = sorted(tuple(np.round(X[k], 9)) for e in m.flaechen["F9"].elemente for k in m.elements[int(e)].nodes)
    log = []
    still(mesher.modell_vernetzen, m, log, workers=1, flaechen=[m.flaechen["F1"]], koerper=[])
    X = np.asarray(m.nodes)
    f9_nach = sorted(tuple(np.round(X[k], 9)) for e in m.flaechen["F9"].elemente for k in m.elements[int(e)].nodes)
    a = gemeinsam_x(m, "F1", "F2", 2.0)
    b = gemeinsam_x(m, "F2", "F3", 4.0)
    w = w_max(m)
    z = mitvernetzt_zeile(log)
    check("**B9, Reihe F1|F2|F3: F1 neu vernetzt – F2 und F3 mitvernetzt, beide Linien verbunden, w_max wie "
          "ganz vernetzt**",
          a[0] == a[1] == a[2] > 2 and b[0] == b[1] == b[2] > 2 and abs(w - w_ref) <= 1e-6 * w_ref
          and z and "F2" in z[0] and "F3" in z[0] and "F9" not in z[0],
          f"x = 2 {a}, x = 4 {b}; w_max {w * 1e3:.2f} mm, ganz {w_ref * 1e3:.2f} mm; {z[:1]}")
    check("… die ferne Platte F9 ohne gemeinsame Linie behält ihr Netz (dieselben Knoten)",
          f9_vor == f9_nach and len(f9_vor) > 0, f"{len(f9_vor)} Elementknoten")


def test_b9_vor_der_rechnung():
    """Ein getrenntes Netz an der gemeinsamen Linie (wie nach dem Teilvernetzen
    vor der Behebung) meldet sich vor der Rechnung."""
    m = platte("gemeinsam")
    getrennt_vernetzen(m)
    n1, n2, gem = gemeinsam_x(m)
    check("Nachstellung: F1 und F2 an L7 getrennt vernetzt (nur die Linienenden gemeinsam)",
          gem == 2 and n1 > 2 and n2 > 2, f"F1 {n1}, F2 {n2}, gemeinsam {gem}")
    bef = [b for b in diagnose.eingabepruefung(m) if "nicht verbunden" in b.text]
    check("**B9: die Eingabeprüfung vor der Rechnung meldet das getrennte Schalennetz (WARNUNG, Linie und "
          "Flächen)**",
          len(bef) == 1 and bef[0].stufe == "WARNUNG" and "L7" in bef[0].text and "F1/F2" in bef[0].text
          and "neu vernetzen" in bef[0].text,
          bef[0].text[:200] if bef else "keine Meldung")
    msgs = still(m.check)
    check("… und steht in Model.check (Meldungen vor der Rechnung)",
          any("WARNUNG" in z and "nicht verbunden" in z and "L7" in z for z in msgs),
          str([z[:80] for z in msgs if "verbunden" in z]))
    mk = rv.merkmal("schalennetz_getrennt")
    check("Verfahrenstabelle: Merkmal „schalennetz_getrennt“, Stand 50, Korrektur am Modell, betrifft das "
          "getrennte Netz",
          mk is not None and any(w.stand == 50 and w.art == rv.FEHLERKORREKTUR for w in mk.wechsel)
          and mk.import_korrektur and "neu erzeugen" in mk.vorschlag and bool(mk.betrifft(m))
          and rv.VERFAHRENSSTAND >= 50,
          f"{mk.name if mk else 'fehlt'}")
    g = platte("gemeinsam")
    still(mesher.modell_vernetzen, g, [], workers=1)
    check("… nicht nach dem Neuvernetzen, nicht ohne Netz, keine Meldung am verbundenen Netz",
          mk is not None and not mk.betrifft(g) and not mk.betrifft(platte("gemeinsam"))
          and not [b for b in diagnose.eingabepruefung(g) if "nicht verbunden" in b.text])
    d = platte("doppelt")
    getrennt_vernetzen(d)
    check("… eine getrennte Doppellinie bleibt beim Merkmal „doppelte_randlinien“ (nicht doppelt gezählt), die "
          "Eingabeprüfung meldet sie",
          mk is not None and not mk.betrifft(d) and rv.merkmal("doppelte_randlinien").betrifft(d)
          and [b for b in diagnose.eingabepruefung(d) if "nicht verbunden" in b.text])


# ---------------------------------------------------------------------------
# B10: gerade Linie gegen Polylinie auf derselben Strecke
# ---------------------------------------------------------------------------
def test_b10_polylinie():
    ref = platte("einzeln")
    still(mesher.modell_vernetzen, ref, [], workers=1)
    w_ref = w_max(ref)
    for art in ("polylinie", "einzeln_polylinie"):
        m = platte(art)
        log = []
        still(mesher.modell_vernetzen, m, log, workers=1)
        n1, n2, gem = gemeinsam_x(m)
        w = w_max(m)
        check(f"**B10, {art}: Abschnitte der Polylinie im Netz verbunden – alle Knoten auf x = 2 gemeinsam, "
              "w_max wie mit Einzellinien (zwei Wege)**",
              n1 == n2 == gem and gem > 2 and abs(w - w_ref) <= 1e-6 * w_ref,
              f"F1 {n1}, F2 {n2}, gemeinsam {gem}; w_max {w * 1e3:.2f} mm, Einzellinien {w_ref * 1e3:.2f} mm")
        z = [x for x in log if "L7p" in x and "Abschnitt" in x]
        check(f"… {art}: das Protokoll nennt die Polylinie L7p und ihre Abschnitte",
              len(z) >= 1, z[0][:160] if z else str([x[:80] for x in log if "L7" in x][:3]))
        check(f"… {art}: danach keine unverbundene Schalenlinie", not mesher.unverbundene_schalenlinien(m),
              str(mesher.unverbundene_schalenlinien(m)))


def test_b10_altes_netz():
    """Netz der Polylinie von vor der Behebung (getrennt) wird erkannt."""
    m = platte("polylinie")
    getrennt_vernetzen(m)
    n1, n2, gem = gemeinsam_x(m)
    lose = mesher.unverbundene_schalenlinien(m)
    mk = rv.merkmal("schalennetz_getrennt")
    bef = [b for b in diagnose.eingabepruefung(m) if "nicht verbunden" in b.text]
    check("**B10: getrenntes Netz an Linie/Polylinie wird erkannt (unverbundene_schalenlinien, Merkmal, "
          "Eingabeprüfung)**",
          gem < n1 and lose and mk is not None and mk.betrifft(m) and len(bef) == 1 and "L7p" in bef[0].text,
          f"gemeinsam {gem} von {n1}; {lose}; {bef[0].text[:120] if bef else 'keine Meldung'}")


def test_polylinie_doppelt_unveraendert():
    """Zwei gleiche Polylinien (Doppellinie, Befund 39) und eine gemeinsame
    Polylinie bleiben, wie sie sind: eine Linie im Netz, kein Abschnitt."""
    from statik3d.model import Model as _M  # noqa: F401
    for art, r1, r2 in (("doppelt", "L7p", "L7q"), ("gemeinsam", "L7p", "L7p")):
        m = platte("gemeinsam")
        m.add_line("L7p", [1, 6, 4]); m.add_line("L7q", [4, 6, 1])
        m.flaechen["F1"].linien = ["L1", r1, "L5", "L6"]
        m.flaechen["F2"].linien = ["L2", "L3", "L4", r2]
        log = []
        still(mesher.modell_vernetzen, m, log, workers=1)
        n1, n2, gem = gemeinsam_x(m)
        check(f"Polylinie {art} (wie bisher): verbunden, ohne Abschnitte im Protokoll",
              n1 == n2 == gem > 2 and not [x for x in log if "Abschnitt" in x],
              f"F1 {n1}, F2 {n2}, gemeinsam {gem}")


def main():
    for t in (lambda: test_b9_teilvernetzen("Befehl"), lambda: test_b9_teilvernetzen("Oberfläche"),
              test_b9_ohne_netz, test_b9_kette_und_fern, test_b9_vor_der_rechnung,
              test_b10_polylinie, test_b10_altes_netz, test_polylinie_doppelt_unveraendert):
        try:
            t()
        except Exception as ex:                    # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{getattr(t, '__name__', 'test')} ohne Ausnahme", False, f"{type(ex).__name__}: {ex}")
    n_ok = sum(1 for _n, ok in RESULTS if ok)
    print(f"\n{n_ok}/{len(RESULTS)} Prüfungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
