"""
Runde k10d (16.11.2026), Theorie III. Ordnung: Restschranke und Konvergenz.

(a) Die Restschranke in theorie3._lastknoten war min(1e-9 * Betragssumme,
    0,001 N). Am weichen Kragarm (L = 10 m, I = 1e-6 m^4, 1 N am Ende b) mit
    -1e7 N / +1e7 N und einem Rest von 0,0009 N am Slave c eines RBE3
    „Stabende 1“ blieb der Rest unter der Schranke: Theorie III. Ordnung
    rechnete still w(b) = 1,587302 mm, Theorie I. Ordnung und Hand ergeben
    1,588730 mm. Jetzt liegt die Schranke auf Rundungsniveau (1e-13 der
    Betragssumme, hoechstens 0,001 N): der Lastfall wird abgewiesen.
(b) Am Kragarm L = 10 m, A = 1e-3 m², I = 1e-6 m⁴ meldete Theorie III.
    Ordnung bei F = 0,1 N „keine Konvergenz“ (Theorie I. Ordnung und Hand
    0,158730 mm), mit Koordinaten um 100 km schon bei 0,001 N. Ursache: die
    Laengung L - L0 als Differenz zweier Laengen aus X0 + u; deren Rundung
    gab eine Normalkraft, die nicht unter die Schranke 1e-6 der Last fiel.

Aufruf:  python -m tests.test_th3_konvergenz_k10d
"""
import contextlib
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

RESULTS = []

E = 210e9
TEXT_KP = "Theorie III. Ordnung rechnet keine"


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"[{'OK ' if ok else 'XX '}] {name}" + (f"  ({detail})" if detail else ""))
    sys.stdout.flush()


def _still(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return fn(*a, **kw)


def _rechne(m, name="LK1"):
    """(Results, Fehlertext Theorie III. Ordnung) der Kombination ``name``."""
    from statik3d import solver
    an = _still(solver.solve_all, m, workers=1, design=False)
    f = ""
    th3 = getattr(an, "theorie3", None)
    if th3 is not None and name in th3.kombinationen:
        f = th3.kombinationen[name].fehler or ""
    return an.combinations.get(name), f


# --------------------------------------------------------------------------
# (a) Restschranke am weichen Kragarm
# --------------------------------------------------------------------------
L_W, I_W = 10.0, 1e-6
FLEX_W = L_W ** 3 / (3 * E * I_W)          # m/N, 1,587302 mm je N


def weich(th, gross, rest, fb=1.0, rbe=True):
    from statik3d.model import Model, Material, Section
    from statik3d.stabeinleitung import STABENDE
    m = Model("W")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=1e-3, Iy=I_W, Iz=I_W, It=1e-7, zmax=0.05, ymax=0.05))
    m.design.imperfektionen = False
    m.netz.stabteilung = 1
    a = m.add_node(0, 0, 0)
    b = m.add_node(L_W, 0, 0)
    m.add_element("beam", [a, b], "ST", "Q")
    m.fix(a, "all")
    for n in ("LF2", "LF3", "LF4"):
        m.add_load_case(n)
    m.load_node(b, Fz=-fb, case="LF1")
    if rbe:
        c = m.add_node(L_W, -0.2, 0)
        d = m.add_node(L_W, 0.2, 0)
        e = m.add_node(L_W, 0, 0.2)
        m.add_starrkoerper(b, [c, d, e], "RBE3", name=STABENDE + "1")
        m.load_node(c, Fz=-gross, case="LF2")
        m.load_node(c, Fz=gross, case="LF3")
        if rest:
            m.load_node(c, Fz=-rest, case="LF4")
    elif rest:
        m.load_node(b, Fz=-rest, case="LF4")
    k = m.add_combination("LK1", {"LF1": 1.0, "LF2": 1.0, "LF3": 1.0, "LF4": 1.0}, "ULS")
    k.theorie = th
    return m, b


def test_a_restschranke():
    from statik3d import rechenverfahren as rv
    from statik3d.theorie3 import kopplung_sperre
    mk = rv.merkmal("theorie3_stabende_anschluss")
    for gross, rest in ((1e7, 0.0009), (1e5, 0.0009), (1e9, 0.0005)):
        hand = (1.0 + rest) * FLEX_W
        m, b = weich("I", gross, rest)
        r1, _f = _rechne(m)
        w1 = -np.asarray(r1.u).reshape(-1, 6)[b, 2]
        check(f"(a) ±{gross:.0f} N, Rest {rest} N: Theorie I. Ordnung w(b) = Hand",
              abs(w1 - hand) <= 1e-6 * hand, f"{w1 * 1e3:.6f} mm, Hand {hand * 1e3:.6f} mm")
        m, b = weich("III", gross, rest)
        wg = _rechne(weich("III", gross, rest, rbe=False)[0])
        wg = -np.asarray(wg[0].u).reshape(-1, 6)[b, 2]
        check("… gleichwertiges Modell (Rest direkt an b) nach Theorie III. Ordnung = Hand",
              abs(wg - hand) <= 1e-5 * hand, f"{wg * 1e3:.6f} mm")
        t = kopplung_sperre(m, None, factors={"LF1": 1.0, "LF2": 1.0, "LF3": 1.0, "LF4": 1.0})
        check("… kopplung_sperre sieht den Rest (stille Abweichung waere "
              f"{rest * FLEX_W * 1e3:.4f} mm)", TEXT_KP in t, t[:80])
        r3, f3 = _rechne(m)
        check("… Theorie III. Ordnung weist ab statt still ohne Rest zu rechnen",
              TEXT_KP in f3, f"{f3[:80]!r}")
        check("… Merkmal theorie3_stabende_anschluss betrifft",
              mk.betrifft(weich("III", gross, rest)[0]) is True)
    # Gegenprobe: genau aufgehoben wird gerechnet
    m, b = weich("III", 1e7, 0.0)
    r3, f3 = _rechne(m)
    w3 = -np.asarray(r3.u).reshape(-1, 6)[b, 2] if r3 is not None else float("nan")
    check("(a) Gegenprobe ±1e7 N ohne Rest: gerechnet, w(b) = Hand",
          not f3 and abs(w3 - FLEX_W) <= 1e-5 * FLEX_W, f"{f3[:60]!r} {w3 * 1e3:.6f} mm")


# --------------------------------------------------------------------------
# (b) kleine Lasten
# --------------------------------------------------------------------------
def kragarm(F, th, versatz=0.0, L=L_W, A=1e-3, I=I_W, teil=1):
    from statik3d.model import Model, Material, Section
    m = Model("K")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=A, Iy=I, Iz=I, It=1e-7, zmax=0.05, ymax=0.05))
    m.design.imperfektionen = False
    m.netz.stabteilung = teil
    a = m.add_node(versatz, versatz, versatz)
    b = m.add_node(versatz + L, versatz, versatz)
    m.add_element("beam", [a, b], "ST", "Q")
    m.fix(a, "all")
    m.load_node(b, Fz=-F)
    k = m.add_combination("LK1", {"LF1": 1.0}, "ULS")
    k.theorie = th
    return m, b


def test_b_kleine_last():
    for F, off in ((0.1, 0.0), (1.0, 0.0), (0.001, 1e5), (0.1, 1e5)):
        hand = F * FLEX_W
        m, b = kragarm(F, "I", off)
        r1, _f = _rechne(m)
        w1 = -np.asarray(r1.u).reshape(-1, 6)[b, 2]
        m, b = kragarm(F, "III", off)
        r3, f3 = _rechne(m)
        w3 = -np.asarray(r3.u).reshape(-1, 6)[b, 2]
        th = str((r3.info or {}).get("theorie", ""))
        check(f"(b) F = {F} N, Koordinaten um {off:.0f} m: Theorie III. Ordnung konvergiert",
              not f3 and th.startswith("III"), f"{f3!r} {th}")
        check("… w(b) = Hand = Theorie I. Ordnung (auf 0,000001 mm)",
              abs(w3 - hand) <= 1e-9 and abs(w1 - hand) <= 1e-9,
              f"Th III {w3 * 1e3:.6f}, Th I {w1 * 1e3:.6f}, Hand {hand * 1e3:.6f} mm")


TESTS = [test_a_restschranke, test_b_kleine_last]


def main():
    for t in TESTS:
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
