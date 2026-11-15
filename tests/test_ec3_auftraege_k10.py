"""
EC3-Nachweis über Arbeitsprozesse nach Theorie II. Ordnung (Runde k10, Stand 69).

Befund der Gegenprüfung Gruppe B (15.11.2026): ``ec3.design._strip`` schickte
den Arbeitsprozessen die Ergebnisse ohne ``beam_th2`` und ``beam_teile``. Der
Nachweis über Arbeitsprozesse - Vorgabe ab 24 Stäben bei mehreren Arbeitern,
auch der Knopf „Nachweise EC3“ der Oberfläche - wies nach Theorie II. Ordnung
das Moment ohne den Anteil der Stabkraft an der Durchbiegung nach. IPE 300,
6 m, N = 200 kN, M = 60 kNm an beiden Enden, ein Element (Stabteilung 10):
M_Ed 60,0 statt 63,2 kNm (Handrechnung M_0/cos(kL/2) = 63,21 kNm), Ausnutzung
2,39941 statt 2,48021. Seriell war richtig.

Geprüft wird seriell gegen Arbeitsprozesse an Modellen verschiedener Art
(Stabteilung 10 und 1, zehn Elemente, Geschossrahmen mit 87 Stäben über den
Vorgabeweg), die Vollständigkeit der Kopie und das Merkmal Stand 69.

Aufruf:  python -m tests.test_ec3_auftraege_k10
"""
import contextlib
import dataclasses
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


def _still(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


N_DRUCK = 200e3
M_END = 60e3
L_IPE = 6.0


def ipe(teilung=None, n_el=1):
    """Einfeldträger IPE 300, S235, 6 m, gabelgelagert, N = 200 kN Druck und
    M = 60 kNm gleichbleibend, Vorverformungen an, K1 nach Theorie II."""
    from statik3d.model import Model, Material
    from statik3d.profiles import make_section
    from statik3d import mesher
    m = Model("IPE")
    m.add_material(Material.steel("S235"))
    m.add_section(make_section("IPE 300"))
    ids = mesher.line_of_beams(m, "S235", "IPE 300", (0, 0, 0), (L_IPE, 0, 0), n_el)
    m.fix(ids[0], [0, 1, 2, 3])
    m.fix(ids[-1], [1, 2, 3])
    m.load_node(ids[-1], Fx=-N_DRUCK)
    m.load_node(ids[0], My=M_END)
    m.load_node(ids[-1], My=-M_END)
    mem = m.add_member("T1", list(range(n_el)))
    mem.lt_check = True
    mem.design = True
    m.design.imperfektionen = True
    if teilung is not None:
        m.netz.stabteilung = teilung
    m.add_combination("K1", {m.active_case: 1.0}, "ULS", theorie="II")
    return m


def geschoss(th2="ein"):
    """Räumlicher Geschossrahmen, 3 x 2 Felder, 3 Geschosse: 48 Stützen HEB 200
    und 39 Riegel IPE 300 (87 Stäbe), G, Q und Wind in x, Kombinationen nach
    EN 1990, Vorverformungen an."""
    from statik3d.model import Model, Material, Section
    from statik3d import mesher
    from statik3d.combinations import generate_combinations
    m = Model("Geschoss")
    m.add_material(Material.steel("S355"))
    m.add_section(Section.from_profile("HEB 200"))
    m.add_section(Section.from_profile("IPE 300"))
    m.case().category = "G"
    a, b, h, nx, ny, ng = 5.0, 4.0, 3.5, 3, 2, 3
    staebe, riegel = [], []

    def stab(p, q, sec, nel):
        e0 = len(m.elements)
        mesher.line_of_beams(m, "S355", sec, p, q, nel)
        staebe.append(list(range(e0, len(m.elements))))
        return staebe[-1]
    for g in range(ng):
        for i in range(nx + 1):
            for j in range(ny + 1):
                stab((i * a, j * b, g * h), (i * a, j * b, (g + 1) * h), "HEB 200", 2)
        for i in range(nx):
            for j in range(ny + 1):
                riegel.append(stab((i * a, j * b, (g + 1) * h), ((i + 1) * a, j * b, (g + 1) * h), "IPE 300", 2))
        for i in range(nx + 1):
            for j in range(ny):
                riegel.append(stab((i * a, j * b, (g + 1) * h), (i * a, (j + 1) * b, (g + 1) * h), "IPE 300", 1))
    mesher.merge_nodes(m)
    for k, els in enumerate(staebe):
        m.add_member(f"S{k + 1}", els)
    for n in mesher.select_nodes(m, zmin=-1e-6, zmax=1e-6):
        m.fix(int(n), "all")
    for els in riegel:
        for e in els:
            m.load_beam(e, qz=-12e3)
    m.add_load_case("LF2", "Q", "Nutzlast", nummer=2)
    for els in riegel:
        for e in els:
            m.load_beam(e, qz=-8e3)
    m.add_load_case("LF3", "W", "Wind x", nummer=3)
    for n in range(m.nn):
        if abs(m.nodes[n][0]) < 1e-9 and m.nodes[n][2] > 1e-6:
            m.load_node(n, Fx=15e3)
    m.active_case = "LF1"
    generate_combinations(m)
    m.design.theorie2 = th2
    m.design.imperfektionen = True
    return m


def _abweichung(a, b) -> tuple:
    """(Zahl der Werte, groesste relative Abweichung, Textunterschiede) ueber
    Ausnutzung, massgebenden Nachweis, Extremwerte und die Stabilitaets- und
    Querschnittsnachweise jedes Stabes."""
    n, gr, txt = 0, 0.0, []

    def zahl(x, y):
        nonlocal n, gr
        x, y = float(x), float(y)
        n += 1
        if x != y:
            gr = max(gr, abs(x - y) / max(abs(x), abs(y), 1e-300))
    if set(a.members) != set(b.members):
        txt.append("andere Staebe")
    for k, ma in a.members.items():
        mb = b.members.get(k)
        if mb is None:
            continue
        zahl(ma.util, mb.util)
        if ma.governing.get("name") != mb.governing.get("name") or ma.governing.get("combo") != mb.governing.get("combo"):
            txt.append(f"{k}: massgebend {ma.governing.get('name')}/{ma.governing.get('combo')} gegen "
                       f"{mb.governing.get('name')}/{mb.governing.get('combo')}")
        for e in ma.extremes:
            zahl(ma.extremes[e], mb.extremes.get(e, float("nan")))
        if len(ma.stability) != len(mb.stability) or len(ma.section_checks) != len(mb.section_checks):
            txt.append(f"{k}: Zahl der Nachweise verschieden")
            continue
        for sa, sb in zip(ma.stability, mb.stability):
            for f in ("N_Ed", "My_Ed", "Mz_Ed", "util"):
                if f in sa:
                    zahl(sa[f], sb.get(f, float("nan")))
        for sa, sb in zip(ma.section_checks, mb.section_checks):
            for f in ("util", "x", "N", "Vy", "Vz", "Mt", "My", "Mz"):
                zahl(sa[f], sb.get(f, float("nan")))
    return n, gr, txt


def test_ipe_ein_element():
    from statik3d import solver
    from statik3d.ec3.design import check_members
    for teilung, n_el, tag in ((None, 1, "ein Element, Stabteilung Vorgabe 10"),
                               (1, 1, "ein Element, Stabteilung 1"),
                               (None, 10, "zehn Elemente")):
        m = ipe(teilung, n_el)
        an = _still(solver.solve_all, m, workers=1, design=False)
        a = _still(check_members, m, an, use_jobs=False)
        b = _still(check_members, m, an, use_jobs=True, workers=2)
        sa, sb = a.members["T1"].stability[0], b.members["T1"].stability[0]
        n, gr, txt = _abweichung(a, b)
        check(f"IPE 300 Th II, {tag}: Arbeitsprozesse bitgleich mit seriell ({n} Werte)",
              gr == 0.0 and not txt,
              f"util seriell {a.util_max:.6f}, Auftraege {b.util_max:.6f}; My_Ed {sa['My_Ed'] / 1e3:.4f} / "
              f"{sb['My_Ed'] / 1e3:.4f} kNm; groesste Abw. {gr:.3g} {txt[:2]}")
        # Handrechnung: gleichbleibendes Moment am Druckstab, M_max = M_0 / cos(k L/2)
        sec = m.sections["IPE 300"]
        k = math.sqrt(N_DRUCK / (m.materials["S235"].E * sec.Iy))
        hand = M_END / math.cos(k * L_IPE / 2.0)
        check(f"IPE 300 Th II, {tag}: My_Ed ueber Arbeitsprozesse = M_0/cos(kL/2) = {hand / 1e3:.2f} kNm (0,1 %)",
              abs(sb["My_Ed"] - hand) <= 1e-3 * hand, f"ist {sb['My_Ed'] / 1e3:.4f} kNm")


def test_geschoss_vorgabeweg():
    """87 Staebe nach Theorie II mit Vorverformungen: der Vorgabeweg (mehrere
    Arbeiter, ab 24 Staeben von selbst ueber Auftraege) gleich wie seriell."""
    from statik3d import solver, parallel
    from statik3d.ec3.design import check_members
    m = geschoss()
    an = _still(solver.solve_all, m, workers=1, design=False)
    alt = parallel.settings().workers
    parallel.configure(workers=2)
    try:
        b = _still(check_members, m, an)
    finally:
        parallel.configure(workers=alt)
    a = _still(check_members, m, an, use_jobs=False)
    teile = any(getattr(r, "beam_teile", None) for r in an.combinations.values())
    n, gr, txt = _abweichung(a, b)
    check(f"Geschossrahmen {len(a.members)} Staebe, Th II, Stabteilung: Ergebnis mit beam_teile",
          len(a.members) == 87 and teile, f"{len(a.members)} Staebe, beam_teile {teile}")
    check(f"Geschossrahmen: Vorgabeweg (Arbeitsprozesse) bitgleich mit seriell ({n} Werte)",
          gr == 0.0 and not txt and n > 1000,
          f"util_max seriell {a.util_max:.6f}, Vorgabeweg {b.util_max:.6f}; groesste Abw. {gr:.3g} {txt[:2]}")


def test_kopie_vollstaendig():
    """_strip kopiert jedes Feld von solver.Results ausser den benannten
    grossen Feldern, die der Stabnachweis nicht liest - ein neues Feld geht
    von selbst mit."""
    from statik3d.solver import Results
    from statik3d.ec3 import design as d
    weg = getattr(d, "STRIP_OHNE", None)
    check("ec3.design.STRIP_OHNE nennt die nicht versandten Felder", weg is not None, repr(weg))
    if weg is None:
        weg = set()
    gelesen = {"beam_end", "beam_q", "beam_th2", "beam_teile", "info", "name", "kind"}
    check("… und keines, das der Stabnachweis liest (member_forces, Spannstahl)",
          not (gelesen & set(weg)), sorted(gelesen & set(weg)))
    r = Results()
    marken = {}
    for f in dataclasses.fields(Results):
        marke = {"marke": f.name}
        marken[f.name] = marke
        object.__setattr__(r, f.name, marke)
    r.info = {"theorie": "II. Ordnung"}
    rr = d._strip(r)
    fehlt = [f.name for f in dataclasses.fields(Results)
             if f.name not in weg and f.name != "info" and getattr(rr, f.name) is not marken[f.name]]
    check("_strip: jedes andere Feld geht unveraendert mit (Vorher fehlten beam_th2, beam_teile u. a.)",
          not fehlt, fehlt)
    check("_strip: info als Kopie, Modell nicht", rr.info == r.info and rr.info is not r.info and rr.model is None,
          f"{rr.info} {type(rr.model)}")


def test_merkmal():
    from statik3d import rechenverfahren as rv
    from statik3d import solver
    mk = rv.merkmal("ec3_auftraege_th2")
    check("Merkmal ec3_auftraege_th2: Stand 69, Fehlerkorrektur, fix/k10-ec3, VERFAHRENSSTAND >= 69",
          mk is not None and mk.wechsel[-1].stand == 69 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR
          and mk.wechsel[-1].commit == "fix/k10-ec3" and mk.wechsel[-1].datum == "15.11.2026"
          and rv.VERFAHRENSSTAND >= 69,
          f"{mk and mk.wechsel} {rv.VERFAHRENSSTAND}")
    if mk is None:
        return
    m = geschoss("ein")
    m_lin = geschoss("aus")
    m_ipe = ipe()
    check("Merkmal: Geschossrahmen 87 Staebe nach Th II betroffen, linear und IPE (1 Stab) nicht",
          mk.betrifft(m) and not mk.betrifft(m_lin) and not mk.betrifft(m_ipe),
          f"{mk.betrifft(m)} {mk.betrifft(m_lin)} {mk.betrifft(m_ipe)}")
    from statik3d.ec3.design import check_members
    an = _still(solver.solve_all, m, workers=1, design=False)
    ohne = mk.im_ergebnis(m, an)
    an.design = _still(check_members, m, an, use_jobs=False)
    im = mk.im_ergebnis(m, an) or ""
    check("Merkmal im Ergebnis: mit Nachweis die Kombinationen nach Th II genannt, ohne Nachweis leer",
          "LK" in im and not ohne, repr(im)[:200])


def main():
    for t in (test_ipe_ein_element, test_geschoss_vorgabeweg, test_kopie_vollstaendig, test_merkmal):
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
