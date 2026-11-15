"""
Behebung vom 15.11.2026, Runde k8 (Agent „bericht“), Verfahrensstand 63:
maßgebend ist der kleinste positive Verzweigungslastfaktor, nicht der erste
der Liste.

Seit Stand 62 kann ``res.buckling_factors`` (aufsteigend nach Betrag, beiderlei
Vorzeichens) vor dem ersten positiven Faktor negative enthalten - das konnte es
auch vorher schon, sobald ein gezogener Stab im Grundzustand steht. Mehrere
Stellen nahmen trotzdem den Faktor mit Index 0 als maßgebend:

* der Bericht (report/html.py, Abschnitt Verzweigungslastfaktoren): Hinweis
  und Warnung „α_cr < 10 (Theorie II. Ordnung)“ entfielen, wenn der erste
  Faktor negativ war, auch bei einem kleinsten positiven Faktor unter 10;
* die Knicklängen aus der Knickfigur (ec3.knicklaengen, Vorgabe ohne
  ``modus``): Figur 1 mit α_cr ≤ 0, jeder Stab „α_cr ≤ 0“ ohne Knicklänge;
* die Vorauswahl der Knickform in der Ergebnismaske (dieselbe Figur gilt für
  die Knicklängen nach dem Rechnen) - sie nimmt jetzt
  solver.massgebende_knickform.

Sollwerte, zwei Wege:
* Zwei Kragstützen im selben Modell, gleiches Profil, L = 5 m: A gedrückt mit
  P_cr/6, B hängend mit 2 P_cr/6 gezogen. Geschlossen (Euler, Fall 1,
  P_cr = π² E I_z / (4 L²)): Faktoren −3, 6, −12 (schwache Achse; B kehrt bei
  umgekehrter Last in den Druck). Im Programm zweiter Weg: α_cr „auto“
  (theorie2.groesstes_mu, ein anderes Verfahren) = 6. Knicklänge der Stütze A
  aus Figur 2: β_z = 2 (Euler Fall 1).
* Fachwerk mit gezogenem Untergurt (tests.test_versatz_stabteilung_k7):
  −64,38 / −64,38 / −130,78 … 7765,80 (Form 35), dort aus dichter Lösung und
  α_cr „auto“ belegt. Druckkraft der Diagonalen von Hand: 50 kN / (2 · 1,5 /
  √3,25) = 30,046 kN.

Aufruf:  python -m tests.test_knickfaktor_positiv_k8
"""
import contextlib
import io
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:96s} {str(detail)[:240]}")
    return ok


E = 210e9
IZ = 2e-5
L = 5.0
PCR = math.pi ** 2 * E * IZ / (4 * L * L)          # Euler Fall 1, schwache Achse


# --------------------------------------------------------------------------
# Modelle
# --------------------------------------------------------------------------
def _zwei_kragstuetzen(alpha_a=6.0, alpha_b=-3.0, mit_b=True):
    """A: Kragstütze nach oben, gedrückt (Faktor alpha_a); B: hängender
    Kragstab nach unten, gezogen (Faktor alpha_b < 0). Je 4 Elemente."""
    from statik3d.model import Model, Material, Section, Member
    m = Model("ZK")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=1e-2, Iy=8e-5, Iz=IZ, It=1e-5, zmax=0.1, ymax=0.05))
    a = [m.add_node(0, 0, k * L / 4) for k in range(5)]
    ea = [m.add_element("beam", [a[k], a[k + 1]], "ST", "Q") for k in range(4)]
    m.fix(a[0], "all")
    m.load_node(a[-1], Fz=-PCR / alpha_a)
    m.members["A"] = Member("A", list(ea))
    if mit_b:
        b = [m.add_node(3, 0, -k * L / 4) for k in range(5)]
        eb = [m.add_element("beam", [b[k], b[k + 1]], "ST", "Q") for k in range(4)]
        m.fix(b[0], "all")
        m.load_node(b[-1], Fz=PCR / alpha_b)       # alpha_b < 0: Last nach unten, Zug
        m.members["B"] = Member("B", list(eb))
    m.add_combination("K1", {"LF1": 1.0}, "ULS")
    m.design.theorie2 = "auto"
    return m


def _fachwerk():
    from statik3d.model import Member
    from tests.test_versatz_stabteilung_k7 import _fachwerk as fw
    m = fw()
    m.members["UG"] = Member("UG", [0])
    m.members["D1"] = Member("D1", [1])
    m.members["D2"] = Member("D2", [2])
    return m


def _knick(m, nmodes=3):
    from statik3d import solver
    with contextlib.redirect_stdout(io.StringIO()):
        return solver.solve_buckling(m, nmodes, None, case="LF1")


def _auto(m):
    from statik3d import theorie2
    with contextlib.redirect_stdout(io.StringIO()):
        return theorie2.check_theorie2(m, None, ["K1"]).kombinationen["K1"].alpha_cr


def _bericht(m, r):
    from statik3d.report.html import Report
    rep = Report(m, results=r)
    with contextlib.redirect_stdout(io.StringIO()):
        h = rep.html()
    return h, list(rep._warnings)


def _kl(m, r, *args):
    from statik3d.ec3.knicklaengen import knicklaengen_aus_eigenform
    return knicklaengen_aus_eigenform(m, r, *args)


def _massgebend(f):
    from statik3d import solver
    fn = getattr(solver, "massgebende_knickform", None)
    return fn(f) if fn is not None else "fehlt"


# --------------------------------------------------------------------------
def test_zwei_kragstuetzen():
    m = _zwei_kragstuetzen()
    r = _knick(m)
    f = np.asarray(r.buckling_factors, float)
    soll = np.array([-3.0, 6.0, -12.0])
    a = _auto(_zwei_kragstuetzen())
    check("Zwei Kragstützen, 3 Formen: −3 / 6 / −12 wie Euler (1e-4), α_cr „auto“ = 6 (1e-4)",
          len(f) == 3 and float(np.abs(f / soll - 1).max()) < 1e-4 and abs(a / 6.0 - 1) < 1e-4,
          f"{np.round(f, 5)}, auto {a:.5f}")
    check("massgebende_knickform: Index 1 (der erste positive), nicht 0",
          _massgebend(f) == 1, repr(_massgebend(f)))
    h, w = _bericht(m, r)
    check("Bericht: Hinweis „α_cr = 6.00 < 10“ trotz negativem ersten Faktor, mit Knickform 2",
          "α_cr = 6.00 &lt; 10" in h or "α_cr = 6.00 < 10" in h,
          [z for z in w if "α_cr" in z])
    check("Bericht: Warnung „α_cr = 6.00 < 10 (Theorie II. Ordnung)“ in der Warnliste",
          any("α_cr = 6.00 < 10" in z for z in w), w)
    kl = _kl(m, r)
    ka, kb = kl.staebe.get("A"), kl.staebe.get("B")
    check("Knicklängen ohne Angabe der Figur: maßgebende Figur 2 mit α_cr = 6 (1e-4)",
          kl.modus == 1 and abs(kl.alpha_cr / 6.0 - 1) < 1e-4, f"Figur {kl.modus + 1}, α {kl.alpha_cr:.5f}")
    check("Knicklängen: Stütze A β_z = 2 (Euler Fall 1, 1e-3), Achse z, beteiligt",
          ka is not None and ka.beta_z is not None and abs(ka.beta_z / 2.0 - 1) < 1e-3
          and ka.achse == "z" and ka.beteiligt,
          f"{ka and (ka.beta_z, ka.achse, ka.beteiligung, ka.hinweis)}")
    check("Knicklängen: gezogener Stab B ohne Knicklänge („keine Druckkraft“)",
          kb is not None and not kb.N_cr and "keine Druckkraft" in kb.hinweis,
          f"{kb and kb.hinweis}")
    k0 = _kl(m, r, 0)
    check("Schutz: Figur 1 ausdrücklich gewählt bleibt Figur 1 (α_cr −3, „α_cr ≤ 0“)",
          k0.modus == 0 and k0.alpha_cr < 0 and "α_cr ≤ 0" in (k0.staebe["A"].hinweis or ""),
          f"{k0.modus} {k0.alpha_cr:.4f} {k0.staebe['A'].hinweis}")
    s = r.summary()
    check("Zusammenfassung: Zeile mit dem maßgebenden Faktor 6.000 (Form 2), ohne wissenschaftliche Schreibweise",
          any("maßgebend" in z and "6.000" in z and "Form 2" in z and "e+" not in z for z in s.splitlines()),
          [z for z in s.splitlines() if "nicklast" in z or "maßgebend" in z])


def test_fachwerk():
    m = _fachwerk()
    r = _knick(m)
    f = np.asarray(r.buckling_factors, float)
    j = len(f) - 1
    check("Fachwerk: massgebende_knickform = letzte (Form 35), Faktor 7765,80",
          _massgebend(f) == j and abs(f[j] / 7765.802747153208 - 1) < 1e-8, f"{_massgebend(f)!r} / {j}")
    kl = _kl(m, r)
    d1 = kl.staebe.get("D1")
    n_hand = 50e3 / (2 * 1.5 / math.sqrt(3.25))
    check("Fachwerk, Knicklängen ohne Figur: Figur 35, α_cr 7765,80, Diagonale D1 mit N_cr = α_cr·|N_Ed| und "
          "N_Ed = −30,046 kN (von Hand, 1e-6)",
          kl.modus == j and abs(kl.alpha_cr / 7765.802747153208 - 1) < 1e-8 and d1 is not None
          and d1.N_cr is not None and abs(d1.N_Ed / -n_hand - 1) < 1e-6
          and abs(d1.N_cr / (kl.alpha_cr * n_hand) - 1) < 1e-6,
          f"Figur {kl.modus + 1}, α {kl.alpha_cr:.3f}, D1 {d1 and (d1.N_Ed, d1.N_cr, d1.hinweis)}")
    h, w = _bericht(m, r)
    check("Fachwerk, Bericht: kein Hinweis α_cr < 10 (kleinster positiver 7765,80)",
          not any("< 10" in z for z in w) and "&lt; 10: Einfluss" not in h, w)
    s = r.summary()
    check("Fachwerk, Zusammenfassung: maßgebend 7765.803 (Form 35) - steht nicht unter den ersten zehn",
          any("maßgebend" in z and "7765.803" in z and "Form 35" in z for z in s.splitlines()),
          [z for z in s.splitlines() if "maßgebend" in z])


def test_schutz_ohne_negative():
    """Schutz: erster Faktor positiv - Bericht, Zusammenfassung und
    Knicklängen wie bisher."""
    m = _zwei_kragstuetzen(mit_b=False)
    r = _knick(m)
    f = np.asarray(r.buckling_factors, float)
    h, w = _bericht(m, r)
    check("Nur Stütze A: massgebende_knickform 0", _massgebend(f) == 0, repr(_massgebend(f)))
    check("Nur Stütze A: erster Faktor 6 (1e-4), Hinweis mit unverändertem Text",
          abs(f[0] / 6.0 - 1) < 1e-4
          and ("α_cr = 6.00 &lt; 10: Einfluss" in h or "α_cr = 6.00 < 10: Einfluss" in h)
          and w == ["LF1: α_cr = 6.00 < 10 (Theorie II. Ordnung)"], f"{np.round(f, 4)} {w}")
    check("Nur Stütze A: Zusammenfassung ohne Zusatzzeile „maßgebend“",
          "maßgebend" not in r.summary())
    kl = _kl(m, r)
    check("Nur Stütze A: Knicklängen aus Figur 1, β_z = 2 (1e-3)",
          kl.modus == 0 and abs(kl.staebe["A"].beta_z / 2.0 - 1) < 1e-3, f"{kl.modus} {kl.staebe['A'].beta_z}")


def test_kein_positiver():
    """Reiner Zug: kein positiver Faktor - massgebende_knickform None,
    Knicklängen aus Figur 1 mit „α_cr ≤ 0“, kein Hinweis im Bericht."""
    from tests.test_versatz_stabteilung_k7 import _knick as knick_k7
    from statik3d.model import Model, Material, Section, Member
    m = Model("Z")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=1e-2, Iy=8e-5, Iz=2e-5, It=1e-5, zmax=0.1, ymax=0.05))
    ids = [m.add_node(0, 0, -k * 1.0) for k in range(5)]
    el = [m.add_element("beam", [ids[k], ids[k + 1]], "ST", "Q") for k in range(4)]
    m.members["H"] = Member("H", el)
    m.fix(ids[0], "all")
    m.load_node(ids[-1], Fz=-100e3)
    _lam, r = knick_k7(m, 3, case="LF1")
    f = np.asarray(r.buckling_factors, float)
    kl = _kl(m, r)
    h, w = _bericht(m, r)
    check("Hängender Stab: massgebende_knickform None", _massgebend(f) is None, repr(_massgebend(f)))
    check("Hängender Stab: kein positiver Faktor, Knicklängen Figur 1 ohne Wert, kein Hinweis α_cr < 10",
          np.all(f < 0) and kl.modus == 0 and not kl.staebe["H"].N_cr
          and not any("< 10" in z for z in w), f"{_massgebend(f)!r} {kl.modus} {w}")


def test_merkmal():
    from statik3d import rechenverfahren as rv
    from statik3d import solver
    mk = rv.merkmal("knickfaktor_massgebend_positiv")
    check("Merkmal knickfaktor_massgebend_positiv: Stand 63, Fehlerkorrektur, VERFAHRENSSTAND >= 63",
          mk is not None and mk.wechsel[-1].stand == 63 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR
          and rv.VERFAHRENSSTAND >= 63, f"{mk and mk.wechsel} {rv.VERFAHRENSSTAND}")
    if mk is None:
        return
    m = _zwei_kragstuetzen()
    neg = solver.Results(name="LF1", kind="buckling", model=m)
    neg.buckling_factors = np.array([-3.0, 6.0, -12.0])
    pos = solver.Results(name="LF1", kind="buckling", model=m)
    pos.buckling_factors = np.array([6.0, -12.0, 24.0])
    nur = solver.Results(name="LF1", kind="buckling", model=m)
    nur.buckling_factors = np.array([-3.0, -12.0])
    st = solver.Results(name="LF1", kind="case", model=m)
    check("im Ergebnis: erster Faktor negativ mit positivem dahinter ja; erster positiv, nur negative, "
          "Theorie I. Ordnung nein",
          bool(mk.im_ergebnis(m, neg)) and not mk.im_ergebnis(m, pos) and not mk.im_ergebnis(m, nur)
          and not mk.im_ergebnis(m, st),
          f"{mk.im_ergebnis(m, neg)!r} / {mk.im_ergebnis(m, pos)!r} / {mk.im_ergebnis(m, nur)!r}")


def main():
    for t in (test_zwei_kragstuetzen, test_fachwerk, test_schutz_ohne_negative, test_kein_positiver,
              test_merkmal):
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
