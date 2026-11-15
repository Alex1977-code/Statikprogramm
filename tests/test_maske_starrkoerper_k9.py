"""
Behebung vom 15.11.2026, Runde k9 (vom Anwender freigegeben), Verfahrensstand 65:
Knotenlast an einem Knoten ohne Element, der nur ueber einen Starrkoerper
(RBE2/RBE3) oder eine Kette angebunden ist, bei einer Elementmaske.

Bis Stand 64 kannte situations.wirksame_knoten nur die Kopplungen und nur eine
Stufe. Sobald irgendein Element abgeschaltet war (Situation, Stab „aus“), fiel
die Last an einem solchen Knoten in assemble.load_vector still weg - ohne
Warnung: Kragarm 3 m, Lastknoten P per RBE2 am Ende, ein fremdes Element in
der Situation aus: w = 0,0000 statt 0,5357 mm. Mit der Kette (Knoten ohne
Element - Starrkoerper - Kopplung - Element) entfiel in assemble.kopplungen
dazu die Kopplung hinter dem Knoten ohne Element.

Sollwerte, je zwei Wege:
* Handformel: Kragarm L = 3 m, E I = 210 000 N/mm² · 8 000 cm⁴, Last am Ende
  F = 1 kN: w = F L³ / (3 E I) = 0,5357 mm; Theorie II. Ordnung mit
  Druckkraft N = 1 000 kN: w = F (tan kL - kL) / (N k), k = √(N / E I);
  Punktmasse 100 kg unter Eigengewicht: w = m g L³ / (3 E I).
* Gegenrechnung: dasselbe Modell ohne das abgeschaltete Element (der zweite
  Kragarm ist nicht da) und ohne Maske.

Schutz: ein Starrkoerper am ganz abgeschalteten Nebenarm bleibt unwirksam
(seine Last wirkt nicht, wie bisher); Eigenformen mit der Punktmasse an
einem solchen Knoten waren nicht betroffen (die Massenmatrix maskiert die
Punktmassen nicht) und bleiben, wie sie sind.

Aufruf:  python -m tests.test_maske_starrkoerper_k9
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


def close(name, ist, soll, rel=1e-6, einheit="mm"):
    ok = abs(ist - soll) <= rel * max(abs(soll), 1e-12)
    return check(name, ok, f"ist {ist:.6f} {einheit}, soll {soll:.6f} {einheit}")


E = 210e9
L = 3.0
I = 8e-5
F = 1e3
N = 1e6
MASSE = 100.0
G = 9.81
HAND = F * L ** 3 / (3 * E * I)                     # 0,5357 mm


def _hand_th2():
    k = math.sqrt(N / (E * I))
    return F * (math.tan(k * L) - k * L) / (N * k)


def _still(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


def modell(art, maske, mit_arm=True, teile=1, rho=0.0):
    """Kragarm a-b (x = 0..L, eingespannt in a) und Lastknoten P ohne Element.

    art: 'rbe2'  P = (L, 0, 0,5) per RBE2 an b
         'rbe3'  P = (L, 0, 0,5) Master einer RBE3 mit Slave b
         'kette' P per RBE2 an Q = (L, 0, 0), Q per Feder 1e12 N/m an b
         'kette_sk_kp' Q per RBE2 an b, P per Feder 1e12 N/m an Q
         'kette_kp_kp' Q per Kopplung an b, P per Kopplung an Q
         'mitte' P = b-Lage (L, 0, 0) per RBE2 an b (Theorie II., Eigenformen)
    maske: 'keine' | 'situation' (zweiter Kragarm in der Situation aus) |
           'aus' (zweiter Kragarm als Stab „aus“)
    mit_arm: False - Gegenrechnung, der zweite Kragarm fehlt ganz.
    Rueckgabe (Modell, b, P)."""
    from statik3d.model import Model, Material, Section, Kopplung, Situation
    m = Model("k9")
    m.add_material(Material("ST", E=E, nu=0.3, rho=rho, fy=355e6))
    m.add_section(Section("Q", A=1e-2, Iy=I, Iz=I, It=1e-5, zmax=0.1, ymax=0.1))
    m.design.imperfektionen = False
    if teile == 1:
        m.netz.stabteilung = 1
    knoten = [m.add_node(L * i / teile, 0, 0) for i in range(teile + 1)]
    for i in range(teile):
        m.add_element("beam", [knoten[i], knoten[i + 1]], "ST", "Q")
    a, b = knoten[0], knoten[-1]
    m.fix(a, "all")
    if art in ("rbe2", "rbe3"):
        p = m.add_node(L, 0, 0.5)
        m.add_starrkoerper(p, [b], art.upper(), name="A")
    elif art == "mitte":
        p = m.add_node(L, 0, 0)
        m.add_starrkoerper(p, [b], "RBE2", name="A")
    elif art == "kette":
        q = m.add_node(L, 0, 0)
        p = m.add_node(L, 0, 0.5)
        m.kopplungen.append(Kopplung(q, b, [[1, 0, 0], [0, 1, 0], [0, 0, 1]], [1e12] * 3, "Feder"))
        m.add_starrkoerper(p, [q], "RBE2", name="K")
    elif art == "kette_sk_kp":
        q = m.add_node(L, 0, 0.5)
        p = m.add_node(L, 0, 0.5)
        m.add_starrkoerper(b, [q], "RBE2", name="K")
        # federnd 1e12 N/m: starr (inf) neben dem RBE2 ist schon ohne Maske
        # numerisch singulaer (Nebenbefund 15.11.2026)
        m.kopplungen.append(Kopplung(p, q, [[1, 0, 0], [0, 1, 0], [0, 0, 1]], [1e12] * 3, "Feder"))
    elif art == "kette_kp_kp":
        q = m.add_node(L, 0, 0)
        p = m.add_node(L, 0, 0)
        m.kopplungen.append(Kopplung(q, b, [[1, 0, 0], [0, 1, 0], [0, 0, 1]], [1e12] * 3, "Feder"))
        m.kopplungen.append(Kopplung(p, q, [[1, 0, 0], [0, 1, 0], [0, 0, 1]], [1e12] * 3, "Feder"))
    else:
        raise ValueError(art)
    if mit_arm:
        c = m.add_node(0, 2, 0)
        d = m.add_node(L, 2, 0)
        e_arm = m.add_element("beam", [c, d], "ST", "Q")
        m.fix(c, "all")
        if maske == "aus":
            m.add_member("S2", [e_arm], aus=True)
    m.add_load_case("LF1", "G")
    if maske == "situation" and mit_arm:
        m.situationen["s"] = Situation("s", "", [len(m.elements) - 1])
        m.load_cases["LF1"].situation = "s"
    return m, b, p


def rechne(m):
    from statik3d import solver
    an = _still(solver.solve_all, m, workers=1, design=False)
    r = an.cases["LF1"]
    return an, np.asarray(r.u).reshape(-1, 6), np.asarray(r.reactions).reshape(-1, 6)


def _w(art, maske, mit_arm=True):
    m, b, p = modell(art, maske, mit_arm)
    m.load_node(p, Fz=-F, case="LF1")
    an, u, r = rechne(m)
    return -u[b, 2], an, r


def test_rbe2_rbe3():
    for art in ("rbe2", "rbe3"):
        gegen, _an, _r = _w(art, "keine", mit_arm=False)
        close(f"{art.upper()} ohne Maske, Gegenrechnung gleich Hand F L³/(3 E I)", gegen * 1e3, HAND * 1e3)
        for maske in ("situation", "aus"):
            w, an, r = _w(art, maske)
            close(f"{art.upper()}-Lastknoten, Maske {maske}: w(b) = F L³/(3 E I)", w * 1e3, HAND * 1e3)
            close(f"{art.upper()}-Lastknoten, Maske {maske}: w(b) gleich Gegenrechnung ohne Maske",
                  w * 1e3, gegen * 1e3, 1e-9)
            close(f"{art.upper()}-Lastknoten, Maske {maske}: Summe der Auflagerkräfte Z = F",
                  r[:, 2].sum(), F, 1e-6, "N")


def test_ketten():
    for art, text in (("kette", "Kette P–RBE2–Q–Feder–b"), ("kette_sk_kp", "Kette b–RBE2–Q–Feder–P"),
                      ("kette_kp_kp", "Kette b–Feder–Q–Feder–P")):
        gegen, _an, _r = _w(art, "keine", mit_arm=False)
        close(f"{text}, ohne Maske: Gegenrechnung gleich Hand", gegen * 1e3, HAND * 1e3, 1e-5)
        for maske in ("situation", "aus"):
            w, an, r = _w(art, maske)
            close(f"{text}, Maske {maske}: w(b) = F L³/(3 E I)", w * 1e3, HAND * 1e3, 1e-5)
            close(f"{text}, Maske {maske}: w(b) gleich Gegenrechnung ohne Maske", w * 1e3, gegen * 1e3, 1e-9)


def test_theorie2():
    from statik3d import solver
    hand = _hand_th2()
    werte = {}
    for maske, mit_arm in (("keine", False), ("situation", True), ("aus", True)):
        m, b, p = modell("mitte", maske, mit_arm, teile=8)
        m.load_node(p, Fx=-N, Fz=-F, case="LF1")
        m.load_cases["LF1"].theorie = "II"
        an = _still(solver.solve_all, m, workers=1, design=False)
        r = an.cases["LF1"]
        werte[maske] = (-np.asarray(r.u).reshape(-1, 6)[b, 2], str((r.info or {}).get("theorie", "")))
    gegen = werte["keine"][0]
    close("Theorie II. Ordnung ohne Maske: Gegenrechnung gleich Hand F (tan kL − kL)/(N k)",
          gegen * 1e3, hand * 1e3, 2e-3)
    for maske in ("situation", "aus"):
        w, th = werte[maske]
        check(f"Theorie II. Ordnung, Maske {maske}: nach Theorie II. Ordnung gerechnet",
              th.startswith("II"), th)
        close(f"Theorie II. Ordnung, RBE2-Lastknoten, Maske {maske}: w(b) = Hand", w * 1e3, hand * 1e3, 2e-3)
        close(f"Theorie II. Ordnung, RBE2-Lastknoten, Maske {maske}: w(b) gleich Gegenrechnung",
              w * 1e3, gegen * 1e3, 1e-7)


def test_knicken():
    """Knicken: Druck N am RBE2-Knoten in Stabrichtung, Kragstuetze -
    N_cr = π² E I / (2 L)²."""
    from statik3d import solver
    hand = math.pi ** 2 * E * I / (2 * L) ** 2
    werte = {}
    for maske, mit_arm in (("keine", False), ("situation", True), ("aus", True)):
        m, b, p = modell("mitte", maske, mit_arm, teile=8)
        m.load_node(p, Fx=-N, case="LF1")
        try:
            r = _still(solver.solve_buckling, m, 2, case="LF1")
            f = [float(x) for x in r.buckling_factors if float(x) > 0]
            werte[maske] = f[0] * N if f else float("nan")
        except Exception as ex:          # noqa: BLE001
            werte[maske] = float("nan")
            print(f"     Knicken, Maske {maske}: {type(ex).__name__}: {str(ex)[:120]}")
    close("Knicken ohne Maske: Gegenrechnung N_cr gleich Hand π² E I/(2L)²", werte["keine"] / 1e3, hand / 1e3,
          1e-4, "kN")
    for maske in ("situation", "aus"):
        close(f"Knicken, RBE2-Lastknoten, Maske {maske}: N_cr = Hand", werte[maske] / 1e3, hand / 1e3, 1e-4, "kN")
        close(f"Knicken, RBE2-Lastknoten, Maske {maske}: N_cr gleich Gegenrechnung", werte[maske] / 1e3,
              werte["keine"] / 1e3, 1e-7, "kN")


def test_punktmasse():
    from statik3d import solver
    hand = MASSE * G * L ** 3 / (3 * E * I)
    werte = {}
    for maske, mit_arm in (("keine", False), ("situation", True), ("aus", True)):
        m, b, p = modell("rbe2", maske, mit_arm)
        m.add_punktmasse(p, MASSE)
        m.load_cases["LF1"].gravity = [0.0, 0.0, -G]
        _an, u, _r = rechne(m)
        werte[maske] = -u[b, 2]
    close("Punktmasse am RBE2-Knoten, Eigengewicht, ohne Maske: Gegenrechnung gleich Hand m g L³/(3 E I)",
          werte["keine"] * 1e3, hand * 1e3)
    for maske in ("situation", "aus"):
        close(f"Punktmasse am RBE2-Knoten, Eigengewicht, Maske {maske}: w(b) = Hand", werte[maske] * 1e3,
              hand * 1e3)
        close(f"Punktmasse am RBE2-Knoten, Eigengewicht, Maske {maske}: gleich Gegenrechnung",
              werte[maske] * 1e3, werte["keine"] * 1e3, 1e-9)
    # Eigenformen: die Massenmatrix maskiert die Punktmassen nicht - Schutz.
    # Stab mit 1 kg (ganz masselos bricht ARPACK ab, Nebenbefund 15.11.2026);
    # Hand nach Rayleigh mit 33/140 der Stabmasse am Ende
    rho = 1.0 / (1e-2 * L)
    hand_f = math.sqrt(3 * E * I / ((MASSE + 33.0 / 140.0) * L ** 3)) / (2 * math.pi)
    fr = {}
    for maske, mit_arm in (("keine", False), ("situation", True), ("aus", True)):
        m, b, p = modell("mitte", maske, mit_arm, teile=8, rho=rho)
        m.add_punktmasse(p, MASSE)
        aktiv = m.aktive_elemente("s" if maske == "situation" else "")
        res = _still(solver.solve_modal, m, 2, workers=1, aktiv=aktiv)
        fr[maske] = float(np.asarray(res.freqs)[0])
    close("Schutz Eigenformen: Punktmasse am RBE2-Knoten ohne Maske, f₁ nach Rayleigh",
          fr["keine"], hand_f, 1e-5, "Hz")
    for maske in ("situation", "aus"):
        close(f"Schutz Eigenformen: Punktmasse am RBE2-Knoten, Maske {maske}, f₁ nach Rayleigh",
              fr[maske], hand_f, 1e-5, "Hz")
        close(f"Schutz Eigenformen: Punktmasse am RBE2-Knoten, Maske {maske}, f₁ gleich Gegenrechnung",
              fr[maske], fr["keine"], 1e-7, "Hz")


def test_lager_ohne_element():
    """Ein Lagerknoten ohne jedes Element traegt selbst: Last an Q, Q per
    Kopplung an einem gelagerten Knoten L ohne Element - die Last geht ins
    Lager (vorher entfiel die Kopplung, Q war frei und die Last weg)."""
    from statik3d.model import Kopplung
    werte = {}
    for maske, mit_arm in (("keine", False), ("situation", True)):
        m, b, p = modell("rbe2", maske, mit_arm)
        lk = m.add_node(L, -1, 0)
        q = m.add_node(L, -1, 0)
        m.fix(lk, "all")
        m.kopplungen.append(Kopplung(q, lk, [[1, 0, 0], [0, 1, 0], [0, 0, 1]], [1e12] * 3, "Feder"))
        m.load_node(q, Fz=-F, case="LF1")
        _an, u, r = rechne(m)
        werte[maske] = r[lk, 2]
    close("Lagerknoten ohne Element, ohne Maske: Auflagerkraft Z = F", werte["keine"], F, 1e-9, "N")
    close("Lagerknoten ohne Element, Maske Situation: Auflagerkraft Z = F (Hand)", werte["situation"], F, 1e-9, "N")
    close("Lagerknoten ohne Element, Maske Situation: gleich Gegenrechnung", werte["situation"], werte["keine"],
          1e-9, "N")


def test_schutz_toter_arm():
    """Starrkoerper am ganz abgeschalteten Nebenarm: bleibt unwirksam, seine
    Last wirkt nicht (wie bisher, ohne eigene Meldung)."""
    from statik3d.situationen import wirksame_knoten
    for maske in ("situation", "aus"):
        m, b, p = modell("rbe2", maske)
        m.load_node(p, Fz=-F, case="LF1")
        d = m.nn - 1                             # Ende des zweiten Kragarms
        p2 = m.add_node(L, 2, 0.5)
        m.add_starrkoerper(p2, [d], "RBE2", name="tot")
        m.load_node(p2, Fz=-5 * F, case="LF1")
        aktiv = m.aktive_elemente("s" if maske == "situation" else "")
        kn = wirksame_knoten(m, aktiv)
        check(f"Schutz toter Arm, Maske {maske}: Master und Slave des Starrkörpers bleiben unwirksam",
              not kn[p2] and not kn[d] and kn[p], f"p2 {kn[p2]}, d {kn[d]}, P {kn[p]}")
        an, u, r = rechne(m)
        close(f"Schutz toter Arm, Maske {maske}: Hauptarm w(b) = Hand", -u[b, 2] * 1e3, HAND * 1e3)
        close(f"Schutz toter Arm, Maske {maske}: Last am toten Arm wirkt nicht, Σ Z = F", r[:, 2].sum(), F,
              1e-6, "N")
        check(f"Schutz toter Arm, Maske {maske}: Knoten des toten Arms in Ruhe",
              np.allclose(u[d], 0.0) and np.allclose(u[p2], 0.0), f"{u[d][:3]} {u[p2][:3]}")
        w = [x for x in (an.info.get("warnungen") or [])]
        print(f"     (Meldungen zum toten Arm: {[x[:100] for x in w]})")


def test_merkmal():
    from statik3d import rechenverfahren as rv
    from statik3d import solver
    mk = rv.merkmal("maske_starrkoerper_last")
    check("Merkmal maske_starrkoerper_last: Stand 65, Fehlerkorrektur, VERFAHRENSSTAND >= 65",
          mk is not None and mk.wechsel[-1].stand == 65 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR
          and mk.wechsel[-1].commit == "fix/k9-rbe2" and rv.VERFAHRENSSTAND >= 65,
          f"{mk and mk.wechsel} {rv.VERFAHRENSSTAND}")
    if mk is None:
        return
    m, _b, p = modell("rbe2", "situation")
    m.load_node(p, Fz=-F, case="LF1")
    m_ohne, _b, p2 = modell("rbe2", "keine")
    m_ohne.load_node(p2, Fz=-F, case="LF1")
    m_aus, _b, p4 = modell("kette", "aus")
    m_aus.load_node(p4, Fz=-F, case="LF1")
    m_tot, b5, p5 = modell("rbe2", "situation")
    m_tot.load_node(b5, Fz=-F, case="LF1")           # Last am Element, nicht am Starrkoerper
    check("betrifft: Situation mit RBE2-Lastknoten ja, Stab „aus“ mit Kette ja, ohne Maske nein, "
          "Last am Element nein",
          mk.betrifft(m) and mk.betrifft(m_aus) and not mk.betrifft(m_ohne) and not mk.betrifft(m_tot),
          f"{mk.betrifft(m)} {mk.betrifft(m_aus)} {mk.betrifft(m_ohne)} {mk.betrifft(m_tot)}")
    an = _still(solver.solve_all, m, workers=1, design=False)
    an2 = _still(solver.solve_all, m_tot, workers=1, design=False)
    check("im Ergebnis: LF1 genannt, beim Modell mit Last am Element nichts",
          "LF1" in (mk.im_ergebnis(m, an) or "") and not mk.im_ergebnis(m_tot, an2),
          f"{mk.im_ergebnis(m, an)!r} / {mk.im_ergebnis(m_tot, an2)!r}")


def main():
    for t in (test_rbe2_rbe3, test_ketten, test_theorie2, test_knicken, test_punktmasse, test_lager_ohne_element,
              test_schutz_toter_arm, test_merkmal):
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
