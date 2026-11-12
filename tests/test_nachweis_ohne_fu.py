"""
Nachweise ohne Werkstoffangabe (Nebenbefund 15, 09.11.2026). Festlegung des
Anwenders: f_u kommt aus dem Werkstoff; fehlt es, gibt es eine Meldung und
keinen Vorgabewert; ohne angegebenen Werkstoff kein Nachweis.

1. Stab als Schraube (ec3.schraubenstab): bei einem Werkstoff mit f_y ohne f_u
   nahm der Nachweis still f_ub = 1,3 f_y. Zugstab Rund 16 mit Gewinde M16
   (A_s = 157 mm²), N = 100 kN, γ_M2 = 1,25:
     f_u 800 angegeben:  F_t,Rd = 0,9 · 800 · 157 / 1,25 = 90 432 N,
                         η = 100 000 / 90 432 = 1,10580   (unverändert)
     f_y 640 ohne f_u:   bisher 1,3 · 640 = 832 N/mm², F_t,Rd = 94 049 N,
                         η = 1,06327 - jetzt kein Nachweis, Meldung
     nur Sorte S355:     f_u 510 aus der Sortentabelle, F_t,Rd = 57 650 N,
                         η = 1,73459   (unverändert; die Sorte ist eine Angabe)
     f_y 640 mit Sorte S355, ohne Wert f_u (Befund 1, 11.11.2026):
                         bisher 1,3 · 640 = 832 N/mm², η = 1,06327 - jetzt f_u 510
                         der Sorte, η = 1,73459. Das neue f_u ist richtig, das
                         Ergebnis aendert sich aber: das Merkmal schraubenstab_fu
                         der Verfahrenstabelle meldet es („möglicherweise betroffen“).
   Zweiter Weg der Soll-Zahlen: die Grenze F_t,Rd, die das Programm je
   Lastzustand ausweist, gegen die Handrechnung oben.
2. Anschlussvorschlag (joints.templates.propose, Kopfplatte, Lasche,
   Diagonale): ohne f_u bemass er mit 1,3 f_y, ganz ohne Festigkeiten mit S355
   (355/510 N/mm²) und zeigte dazu Nachweise. Jetzt die Meldung des
   Anschlussnachweises (Befund A23) und kein Vorschlag.
3. Bolzennachweis (ec3.bolzen.festigkeit): hatte den Rückfall 1,3 f_y schon
   nicht mehr - Kontrolle, dass es so bleibt.

Aufruf:  python -m tests.test_nachweis_ohne_fu
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

RESULTS = []

N_ZUG = 100e3
A_S_M16 = 157e-6


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:92s} {detail}")
    return ok


def _schraube(fy, fu, sorte=""):
    from statik3d import solver
    from statik3d.model import Material, Model, Section
    m = Model("Schraube")
    m.add_material(Material("X", 210e9, 0.3, 7850.0, 1.2e-5, fy, fu, sorte))
    sec = Section.circle("Rund 16", 0.016)
    sec.gewinde = "M16"
    m.add_section(sec)
    a, b = m.add_node(0, 0, 0), m.add_node(2.0, 0, 0)
    m.add_element("truss", [a, b], "X", sec.name)
    m.fix(a, "all")
    m.fix(b, [1, 2, 3, 4, 5])
    m.case().category = "G"
    m.load_node(b, Fx=N_ZUG)
    m.add_member("S1", [0])
    m.add_combination("K1", {"LF1": 1.0}, "ULS")
    return solver.solve_all(m, workers=1, design=True).design.members["S1"]


def test_schraubenstab():
    for text, fy, fu, sorte, fub in (("f_y 640, f_u 800 angegeben", 640e6, 800e6, "", 800e6),
                                     ("nur Sorte S355 (f_u 510 aus der Tabelle)", None, None, "S355", 510e6)):
        mc = _schraube(fy, fu, sorte)
        ftrd = 0.9 * fub * A_S_M16 / 1.25
        grenze = max((float(z["grenze"]) for z in (mc.zustaende or [])), default=0.0)
        check(f"Schraube M16, {text}: η = {N_ZUG / ftrd:.5f} wie bisher",
              mc.art == "Schraube" and not getattr(mc, "fehler", "") and abs(float(mc.util) - N_ZUG / ftrd) < 1e-9,
              f"η = {float(mc.util):.5f}, Fehler {getattr(mc, 'fehler', '')!r}")
        check(f"Schraube M16, {text}: ausgewiesene Grenze F_t,Rd = {ftrd / 1e3:.3f} kN (Handrechnung)",
              abs(grenze - ftrd) < 1e-6 * ftrd, f"F_t,Rd = {grenze / 1e3:.3f} kN")
    mc = _schraube(640e6, None)
    fehler = getattr(mc, "fehler", "") or ""
    check("Schraube M16, f_y 640 ohne f_u: kein Nachweis mit 1,3 f_y = 832 N/mm² (η wäre 1,06327)",
          bool(fehler) and not mc.governing, f"η = {float(mc.util or 0.0):.5f}, Fehler {fehler!r}")
    check("… die Meldung nennt f_u und den Werkstoff „X“ und sagt, was einzutragen ist",
          "f_u" in fehler and "X" in fehler and any("f_u (= f_ub) am Werkstoff eintragen" in w for w in mc.warnings),
          str(mc.warnings))
    mc = _schraube(None, None)
    check("Schraube M16, ohne f_y und f_u: kein Nachweis, Meldung (wie bisher)",
          bool(getattr(mc, "fehler", "")) and "f_u" in mc.fehler, repr(getattr(mc, "fehler", "")))


def test_mischfall_sorte():
    """f_y mit Stahlsorte, ohne Wert f_u (Befund 1): neu das f_u der Sorte, und die
    Verfahrenstabelle meldet das geaenderte Ergebnis."""
    from statik3d import rechenverfahren as rv
    from statik3d.model import Material, Model, Section
    mc = _schraube(640e6, None, "S355")
    ftrd = 0.9 * 510e6 * A_S_M16 / 1.25
    check(f"Schraube M16, f_y 640 mit Sorte S355 ohne Wert f_u: f_ub 510 der Sorte, η = {N_ZUG / ftrd:.5f}",
          mc.art == "Schraube" and not getattr(mc, "fehler", "") and abs(float(mc.util) - N_ZUG / ftrd) < 1e-9,
          f"η = {float(mc.util or 0.0):.5f}")
    alt = Material("X", 210e9, 0.3, 7850.0, 1.2e-5, 640e6, None, "S355").ultimate_strength(0.016)
    check("… bisher (Material.ultimate_strength) 1,3 · 640 = 832 N/mm², η = 1,06327",
          abs(alt - 832e6) < 1.0, f"{alt / 1e6:.1f} N/mm²")
    mk = rv.merkmal("schraubenstab_fu")

    def modell(fy, fu, sorte):
        m = Model("S")
        m.add_material(Material("X", 210e9, 0.3, 7850.0, 1.2e-5, fy, fu, sorte))
        sec = Section.circle("Rund 16", 0.016)
        sec.gewinde = "M16"
        m.add_section(sec)
        a, b = m.add_node(0, 0, 0), m.add_node(2.0, 0, 0)
        m.add_element("truss", [a, b], "X", sec.name)
        return m
    check("Merkmal „schraubenstab_fu“: f_y 640 mit Sorte S355, ohne Wert f_u - gemeldet (η 1,06327 → 1,73459)",
          mk.betrifft(modell(640e6, None, "S355")))
    check("… f_y 640 ohne f_u und Sorte - gemeldet (wie bisher)", mk.betrifft(modell(640e6, None, "")))
    check("… f_u 800 angegeben, nur Sorte S355 - nicht gemeldet (Ergebnis unverändert)",
          not mk.betrifft(modell(640e6, 800e6, "S355")) and not mk.betrifft(modell(None, None, "S355")))


def _traeger(fy, fu, sorte=""):
    from statik3d import mesher
    from statik3d.model import Material, Model, Section
    m = Model("A")
    m.add_material(Material("X", E=210e9, nu=0.3, rho=7850, fy=fy, fu=fu, grade=sorte))
    m.add_section(Section.i_profile("IPE300", 0.300, 0.150, 0.0071, 0.0107))
    mesher.line_of_beams(m, "X", "IPE300", (0, 0, 0), (4, 0, 0), n=4)
    return m


KRAEFTE = (("kopfplatte", dict(N=0.0, Vz=20e3, My=80e3)), ("lasche", dict(N=0.0, Vz=20e3, My=80e3)),
           ("diagonale", dict(N=200e3)))


def _vorschlag(art, kw, fy, fu, sorte=""):
    from statik3d.joints import templates
    try:
        t = templates.propose(art, _traeger(fy, fu, sorte), 0, end=0, **kw)
        return t, ""
    except ValueError as ex:
        return None, str(ex)


def test_vorschlag():
    for art, kw in KRAEFTE:
        if art == "kopfplatte":
            # Die Naehte der Kopfplatte bemisst der Vorschlag mit β_w der Stahlsorte - ohne
            # Sorte seit dem 12.11.2026 kein Vorschlag (bis dahin still S355, Pruefbericht
            # 11.11.2026, Befund 2); mit Sorte und Werten wie bisher
            t, meldung = _vorschlag(art, kw, 235e6, 360e6)
            check(f"Vorschlag {art}: f_y 235, f_u 360 ohne Sorte: kein Vorschlag, Meldung nennt Stahlsorte und „X“",
                  t is None and "Stahlsorte" in meldung and "„X“" in meldung and "kein Vorgabewert" in meldung,
                  meldung or "Vorschlag ohne Sorte")
            t, meldung = _vorschlag(art, kw, 235e6, 360e6, "S235")
        else:
            t, meldung = _vorschlag(art, kw, 235e6, 360e6)
        check(f"Vorschlag {art}: f_y 235, f_u 360 angegeben: Vorschlag mit 235/360 N/mm² wie bisher",
              t is not None and (t.fy, t.fu) == (235e6, 360e6), meldung or f"{t.fy / 1e6:.1f}/{t.fu / 1e6:.1f}")
        t, meldung = _vorschlag(art, kw, None, None, "S235")
        check(f"Vorschlag {art}: nur Sorte S235: 235/360 N/mm² aus der Sortentabelle wie bisher",
              t is not None and (t.fy, t.fu) == (235e6, 360e6), meldung or f"{t.fy / 1e6:.1f}/{t.fu / 1e6:.1f}")
        t, meldung = _vorschlag(art, kw, 235e6, None)
        check(f"Vorschlag {art}: f_y 235 ohne f_u: kein Vorschlag mit 1,3 f_y = 305,5, Meldung nennt f_u und „X“",
              t is None and "f_u" in meldung and "f_y" not in meldung and "„X“" in meldung
              and "kein Vorgabewert" in meldung,
              meldung or f"Vorschlag mit f_u {t.fu / 1e6:.1f} N/mm²")
        t, meldung = _vorschlag(art, kw, None, None)
        check(f"Vorschlag {art}: ohne f_y, f_u und Sorte: kein Vorschlag mit S355 (355/510), Meldung nennt beide",
              t is None and "f_y und f_u fehlen" in meldung and "kein Vorgabewert" in meldung,
              meldung or f"Vorschlag mit {t.fy / 1e6:.1f}/{t.fu / 1e6:.1f} N/mm²")


def test_bolzen_bleibt():
    from statik3d.ec3 import bolzen
    from statik3d.model import Material
    wert, text = bolzen.festigkeit(Material("X", 210e9, 0.3, 7850.0, 1.2e-5, 640e6, None), 0.030, "fu")
    check("Bolzen: f_y 640 ohne f_u: keine Zugfestigkeit, Meldung nennt f_u (schon bisher kein 1,3 f_y)",
          wert is None and "f_u" in text and "X" in text, f"{wert} {text!r}")
    wert, text = bolzen.festigkeit(Material("X", 210e9, 0.3, 7850.0, 1.2e-5, 640e6, 800e6), 0.030, "fu")
    check("Bolzen: f_u 800 angegeben: 800 N/mm²", wert == 800e6 and not text, f"{wert} {text!r}")


def main():
    for t in (test_schraubenstab, test_mischfall_sorte, test_vorschlag, test_bolzen_bleibt):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:          # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    sys.exit(main())
