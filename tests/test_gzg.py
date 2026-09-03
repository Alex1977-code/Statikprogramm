"""
Verifikation der Verformungsnachweise (Grenzzustand der Gebrauchstauglichkeit).

Geprueft wird gegen geschlossene Loesungen der Balkenbiegung - der
Einfeldtraeger unter Gleichlast und unter Einzellast, der Kragarm - und gegen
die Regeln der Grenzwertbildung (L/x, absolut, Ueberhoehung, Punktpaar).

Aufruf:  python -m tests.test_gzg
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import solver                                    # noqa: E402
from statik3d.model import Model, Material, Section            # noqa: E402
from statik3d.gzg import (SITUATIONEN, check_verformung,       # noqa: E402
                          durchbiegung)

RESULTS = []

E = 210e9
IPE400 = dict(A=84.5e-4, Iy=23130e-8, Iz=1318e-8, It=51.1e-8, Wpl_y=1307e-6,
              Wel_y=1156e-6, typ="I", h=0.400, b=0.180, tw=0.0086, tf=0.0135,
              r=0.021, zmax=0.200, ymax=0.090)


def check(name, ok, info=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FAIL'} {name:58s} {info}")
    return ok


def close(name, got, want, tol, unit=""):
    err = abs(got - want)
    rel = err / abs(want) if want else err
    return check(name, rel <= tol,
                 f"{got:.6g}{unit} / {want:.6g}{unit}  Abw. {rel * 100:.4f} %")


def traeger(n_el: int, L: float = 8.0, gelenkig_rechts: bool = True) -> tuple:
    m = Model("Träger")
    m.add_material(Material.steel("S355"))
    m.add_section(Section("IPE 400", **IPE400))
    ids = [m.add_node(x, 0.0, 0.0) for x in np.linspace(0.0, L, n_el + 1)]
    els = [m.add_element("beam", [ids[i], ids[i + 1]], "S355", "IPE 400")
           for i in range(n_el)]
    m.fix(ids[0], [0, 1, 2, 3])
    if gelenkig_rechts:
        m.fix(ids[-1], [1, 2, 3])
    m.add_member("T", els)
    return m, ids, els


# --------------------------------------------------------------------------
def test_durchbiegung_gegen_handrechnung():
    L, q, P = 8.0, 20e3, 100e3
    I = IPE400["Iy"]

    # Gleichlast: w = 5 q L^4 / (384 E I) - auch mit nur einem Element
    for n_el in (1, 2, 4, 9):
        m, ids, els = traeger(n_el, L)
        for e in els:
            m.load_beam(e, qz=-q)
        an = solver.solve_all(m, combinations=False, envelopes=False)
        d = durchbiegung(m, an.cases[m.active_case], m.members["T"])
        w = float(np.max(np.abs(d["w_z"])))
        close(f"Einfeldträger Gleichlast, {n_el} Element(e)", w,
              5 * q * L ** 4 / (384 * E * I), 1e-4, " m")

    # Einzellast in Feldmitte: w = P L^3 / (48 E I)
    m, ids, els = traeger(2, L)
    m.load_node(ids[1], Fz=-P)
    an = solver.solve_all(m, combinations=False, envelopes=False)
    d = durchbiegung(m, an.cases[m.active_case], m.members["T"])
    close("Einfeldträger Einzellast in der Mitte",
          float(np.max(np.abs(d["w_z"]))), P * L ** 3 / (48 * E * I), 1e-9, " m")

    # Kragarm: die Sehne dreht mit - die Durchbiegung bezogen auf die Sehne
    # ist NICHT die Spitzenverschiebung. w_Sehne(max) = P L^3 / (9 sqrt(3) E I)
    m = Model("Kragarm")
    m.add_material(Material.steel("S355"))
    m.add_section(Section("IPE 400", **IPE400))
    ids = [m.add_node(x, 0, 0) for x in np.linspace(0, L, 9)]
    els = [m.add_element("beam", [ids[i], ids[i + 1]], "S355", "IPE 400")
           for i in range(8)]
    m.fix(ids[0], "all")
    m.load_node(ids[-1], Fz=-P)
    m.add_member("K", els)
    an = solver.solve_all(m, combinations=False, envelopes=False)
    res = an.cases[m.active_case]
    close("Kragarm: Spitzenverschiebung P L^3 / 3EI",
          abs(float(res.u[ids[-1], 2])), P * L ** 3 / (3 * E * I), 1e-6, " m")
    d = durchbiegung(m, res, m.members["K"])
    close("Kragarm: Durchbiegung bezogen auf die Sehne",
          float(np.max(np.abs(d["w_z"]))),
          P * L ** 3 / (9 * math.sqrt(3) * E * I), 1e-4, " m")

    # Starrkoerperanteil faellt heraus: Auflagersenkung aendert nichts
    m, ids, els = traeger(4, L)
    for e in els:
        m.load_beam(e, qz=-q)
    an1 = solver.solve_all(m, combinations=False, envelopes=False)
    w1 = float(np.max(np.abs(durchbiegung(m, an1.cases[m.active_case],
                                          m.members["T"])["w_z"])))
    m.supports = [s for s in m.supports if s.node != ids[-1]]
    m.fix(ids[-1], [1, 2, 3], values=[0.0, 0.0, -0.020])
    an2 = solver.solve_all(m, combinations=False, envelopes=False)
    w2 = float(np.max(np.abs(durchbiegung(m, an2.cases[m.active_case],
                                          m.members["T"])["w_z"])))
    close("Auflagersenkung ändert die Durchbiegung nicht", w2, w1, 1e-6, " m")


def test_grenzwerte():
    L, q = 8.0, 20e3
    I = IPE400["Iy"]
    w_soll = 5 * q * L ** 4 / (384 * E * I)

    def bau():
        m, ids, els = traeger(4, L)
        for e in els:
            m.load_beam(e, qz=-q)
        return m, ids

    # L/x gegen absolut
    m, ids = bau()
    m.add_verformungsgrenze("A", "stab", stab="T", groesse="uz", grenzart="L/x",
                            wert=300, situation="")
    m.add_verformungsgrenze("B", "stab", stab="T", groesse="uz", grenzart="absolut",
                            wert=L / 300.0, situation="")
    an = solver.solve_all(m, design=True)
    a, bb = an.gzg.checks["A"], an.gzg.checks["B"]
    close("Grenze L/300 = L/300", a.grenze, L / 300.0, 1e-12, " m")
    close("Ausnutzung gegen die Handrechnung", a.util, w_soll / (L / 300.0), 1e-3)
    check("L/x und absolut ergeben dasselbe", abs(a.util - bb.util) < 1e-9,
          f"{a.util:.4f} / {bb.util:.4f}")
    check("Status wird benannt", a.status() in ("erfüllt", "NICHT erfüllt"), a.status())

    # Ueberhoehung wird abgezogen
    m, ids = bau()
    wc = 0.010
    m.add_verformungsgrenze("C", "stab", stab="T", groesse="uz", grenzart="absolut",
                            wert=0.030, situation="", ueberhoehung=wc)
    c = solver.solve_all(m, design=True).gzg.checks["C"]
    close("Überhöhung w_c wird abgezogen", c.wert, w_soll - wc, 1e-3, " m")
    check("die Überhöhung steht im Hinweis",
          any("Überhöhung" in h for h in c.hinweise), str(c.hinweise))

    # Knoten und Punktpaar
    m, ids = bau()
    mitte = ids[2]
    m.add_verformungsgrenze("Knoten", "knoten", knoten=[mitte], groesse="uz",
                            grenzart="absolut", wert=0.050, situation="")
    m.add_verformungsgrenze("Paar", "punktpaar", knoten=[ids[0], mitte], groesse="uz",
                            grenzart="absolut", wert=0.050, situation="")
    an = solver.solve_all(m, design=True)
    res = an.cases[m.active_case] if not an.combinations else \
        list(an.combinations.values())[0]
    kn = an.gzg.checks["Knoten"]
    paar = an.gzg.checks["Paar"]
    check("Knotennachweis nimmt die Knotenverschiebung",
          abs(kn.wert - abs(float(res.u[mitte, 2]))) < 1e-9,
          f"{kn.wert * 1e3:.3f} mm")
    check("Punktpaar nimmt die Verschiebung gegeneinander",
          abs(paar.wert - abs(float(res.u[mitte, 2] - res.u[ids[0], 2]))) < 1e-9,
          f"{paar.wert * 1e3:.3f} mm")

    # Bemessungssituationen werden getrennt gehalten
    m, ids = bau()
    m.add_load_case("Q", "Q_A")
    m.load_beam(1, qz=-2 * q, case="Q")
    from statik3d.combinations import generate_combinations
    generate_combinations(m)
    for sit in ("SLS_CH", "SLS_QP"):
        m.add_verformungsgrenze(sit, "stab", stab="T", groesse="uz",
                                grenzart="L/x", wert=300, situation=sit)
    an = solver.solve_all(m, design=True)
    ch, qp = an.gzg.checks["SLS_CH"], an.gzg.checks["SLS_QP"]
    check("charakteristisch ist ungünstiger als quasi-ständig",
          ch.util > qp.util, f"{ch.util:.3f} > {qp.util:.3f}")
    check("die maßgebende Kombination ist eine GZG-Kombination",
          ch.kombination in m.combinations
          and m.combinations[ch.kombination].typ == "SLS_CH", ch.kombination)
    check("jede Kombination der Situation wird geführt",
          len(ch.je_kombination) == sum(1 for c in m.combinations.values()
                                        if c.typ == "SLS_CH"),
          f"{len(ch.je_kombination)} Kombinationen")
    beste = max(ch.je_kombination, key=lambda d: d["util"])
    check("die ungünstigste ist maßgebend",
          abs(beste["util"] - ch.util) < 1e-12
          and beste["kombination"] == ch.kombination)


def test_fehler_werden_benannt():
    m, ids, els = traeger(2)
    for e in els:
        m.load_beam(e, qz=-10e3)
    m.add_verformungsgrenze("X", "knoten", knoten=[0], groesse="uz",
                            grenzart="L/x", wert=300, situation="")
    m.add_verformungsgrenze("Y", "stab", stab="T", groesse="uz",
                            grenzart="absolut", wert=0.0, situation="")
    an = solver.solve_all(m, design=True)
    x, y = an.gzg.checks["X"], an.gzg.checks["Y"]
    check("L/x an einem Knoten wird abgewiesen",
          x.fehler and "Bezugslänge" in x.fehler, x.fehler)
    check("Grenzwert null wird abgewiesen", y.fehler, y.fehler)
    check("nicht geführte Nachweise heißen so", x.status() == "nicht geführt")

    m2, _ids, _els = traeger(2)
    m2.add_verformungsgrenze("Z", "stab", stab="T", groesse="uz",
                             situation="SLS_FR")
    an2 = solver.solve_all(m2, design=True)
    check("fehlende Bemessungssituation wird gemeldet",
          an2.gzg.checks["Z"].fehler, an2.gzg.checks["Z"].fehler)
    try:
        m2.add_verformungsgrenze("W", "stab", stab="gibtsnicht")
        check("unbekannter Stab wird abgewiesen", False)
    except KeyError as ex:
        check("unbekannter Stab wird abgewiesen", True, str(ex)[:40])
    try:
        m2.add_verformungsgrenze("W", "knoten", knoten=[])
        check("Knotennachweis ohne Knoten wird abgewiesen", False)
    except ValueError as ex:
        check("Knotennachweis ohne Knoten wird abgewiesen", True, str(ex)[:40])


def test_modell_und_bericht():
    from statik3d.report import Report
    m, ids, els = traeger(4)
    for e in els:
        m.load_beam(e, qz=-20e3)
    m.add_verformungsgrenze("Durchbiegung", "stab", stab="T", groesse="uz",
                            grenzart="L/x", wert=300, situation="",
                            beschreibung="Dachriegel nach NA")
    m2 = Model.from_dict(m.to_dict())
    check("Verformungsgrenze übersteht Speichern und Laden",
          list(m2.verformungsgrenzen) == ["Durchbiegung"]
          and m2.verformungsgrenzen["Durchbiegung"].wert == 300)
    check("und die Modellkopie (Rückgängig)",
          m.copy().verformungsgrenzen["Durchbiegung"].beschreibung == "Dachriegel nach NA")

    an = solver.solve_all(m, design=True)
    check("die Nachweise laufen mit der Berechnung", an.gzg is not None
          and "Durchbiegung" in an.gzg.checks)
    check("Zusammenfassung nennt sie", "Verformungen (GZG)" in an.summary())
    html = Report(m, an).html()
    for text in ("Verformungsnachweise (Grenzzustand der Gebrauchstauglichkeit)",
                 "bezogen auf die", "L/300", "Dachriegel nach NA",
                 "max. Ausnutzung Verformung"):
        check(f"Bericht nennt „{text}“", text in html)
    check("Situationen sind benannt",
          all(v in SITUATIONEN.values() for v in ("charakteristisch", "häufig",
                                                  "quasi-ständig")))


def main():
    print("=" * 92)
    print("STATIK3D - Verifikation Verformungsnachweise (GZG)")
    print("=" * 92)
    for t in (test_durchbiegung_gegen_handrechnung, test_grenzwerte,
              test_fehler_werden_benannt, test_modell_und_bericht):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _n, ok in RESULTS if ok)
    print("\n" + "=" * 92)
    print(f"Ergebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    sys.exit(main())
