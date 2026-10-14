"""Globale Gleichgewichtskontrolle wirkt auf die Gueltigkeit (14.10.2026).

Entscheidung: ueber der Warnschranke (1e-4 des Umsatzes) eine WARNUNG; ab
einer klar fehlerhaften Abweichung (gleichgewicht.UNGUELTIG) ist das Ergebnis
„nicht gültig“ mit „Gleichgewicht verletzt: ΣF/ΣM …“, im selben Zustand wie
eine Last an automatisch gehaltenen Freiheitsgraden. Ein vorlaeufiges
Ergebnis (Kontakt nicht konvergiert) bleibt vorlaeufig und bekommt die Zeile.

Dazu der Fall, an dem es auffiel: Zugstab „nur Zug“ unter Druck, Last am
freien Kopf, das andere Stabende verteilt (RBE3) in einen Quader eingeleitet.
Bis dahin kam ein „gültiges“ Ergebnis heraus, in dem die Last fehlte (ΣF
bezogen 1,0): die Suche nach frei beweglichen Teilen (diagnose.teiltragwerke)
sah die Kopplung RBE3 nicht, hielt Kopf und Fuss des Stabs als ein loses Teil
fest, und die Hilfsfesselung leitete die Kopflast gegen ihre Richtung in den
Quader.

Aufruf:  python -m tests.test_gleichgewicht_gueltig
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np                                                  # noqa: E402

from statik3d import fugen, solver                                  # noqa: E402
from statik3d import gleichgewicht as gg                            # noqa: E402
from statik3d.model import NodalLoad, Stabeinleitung                # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:80s} {detail}")
    return ok


def _eintrag(rel_F, rel_M=0.0):
    g = {"x0": [0.0, 0.0, 0.0], "F_last": [0.0, 0.0, -1000.0], "M_last": [0.0] * 3,
         "F_lager": [0.0, 0.0, 1000.0 - rel_F * 2000.0], "M_lager": [0.0, 0.0, rel_M * 100.0],
         "umsatz_F": 2000.0, "umsatz_M": 100.0, "verformt": False}
    return gg.bewerten(g)


def test_schranken():
    print("\n--- Schranken: Warnung und nicht gültig ---")
    check("Werte: Warnung ab 1e-4, nicht gültig ab 1e-2 des Umsatzes",
          gg.SCHRANKE == 1e-4 and getattr(gg, "UNGUELTIG", None) == 1e-2, str(getattr(gg, "UNGUELTIG", None)))
    for rel, warn, ungueltig in ((1e-6, False, False), (5e-4, True, False), (2e-2, True, True), (1.0, True, True)):
        g = _eintrag(rel)
        info = {"gleichgewicht_global": g}
        text = solver.gueltigkeit(info)
        zeile = gg.zeile(g)
        check(f"ΣF bezogen {rel:g}: " + ("nicht gültig" if ungueltig else "Warnung" if warn else "erfüllt"),
              (not g["ok"]) == warn and bool(g.get("verletzt")) == ungueltig
              and (("Gleichgewicht verletzt" in text) == ungueltig)
              and (("NICHT GÜLTIG" in zeile) == ungueltig) and (("WARNUNG" in zeile) == (warn and not ungueltig)),
              f"„{text[:90]}“ | {zeile[:70]}")
    g = _eintrag(0.0, rel_M=0.5)
    check("ΣM bezogen 0,5 allein: ebenfalls nicht gültig, Grund nennt ΣM",
          "Gleichgewicht verletzt" in solver.gueltigkeit({"gleichgewicht_global": g})
          and "ΣM" in solver.gueltigkeit({"gleichgewicht_global": g}), solver.gueltigkeit({"gleichgewicht_global": g}))
    vorl = {"gleichgewicht_global": _eintrag(1.0),
            "vorlaeufig": {"text": "vorläufig – Kontakt nicht konvergiert in Stufe 2", "stellen": ["Stufe 2"]}}
    check("vorläufig (Kontakt nicht konvergiert): bleibt vorläufig, nicht „nicht gültig“",
          solver.gueltigkeit(vorl) == "" and solver.kontakt_vorlaeufig(vorl).startswith("vorläufig"),
          repr(solver.gueltigkeit(vorl)))
    from statik3d.gui import rechenliste as rl
    zustand, meldung = rl.zustand_und_meldung(
        dict(vorl, contact_converged=False, contact_iterations=3), "")
    check("… die Rechenliste behält „nicht konvergiert“ und nennt die Verletzung in der Meldung",
          zustand == rl.NICHT_KONVERGIERT and "Gleichgewicht verletzt" in meldung, f"{zustand} | {meldung}")
    zustand, meldung = rl.zustand_und_meldung({"gleichgewicht_global": _eintrag(1.0)}, "")
    check("… und ein konvergiertes Ergebnis wird „nicht gültig“ wie bei automatisch gehaltenen FHG",
          zustand == rl.NICHT_GUELTIG and "Gleichgewicht verletzt" in meldung, f"{zustand} | {meldung}")


def _quader_zugstab(art):
    from tests.test_stabeinleitung import lagern_frei, quader, zugstab
    m = quader(h=0.01)
    lagern_frei(m)
    fuss, kopf, e = zugstab(m)
    m.elements[e].nur = "zug"
    m.fix(kopf, [0, 1])
    m.stabeinleitung = Stabeinleitung(art)
    fugen.stabenden_koppeln(m, [])
    lc = m.add_load_case("LF1")
    lc.gravity = [0, 0, 0]
    lc.nodal_loads.append(NodalLoad(kopf, [0.0, 0.0, -10e3, 0, 0, 0]))
    return m, fuss, kopf


def test_zugstab_druck_rbe3():
    print("\n--- Zugstab „nur Zug“ unter Druck, Last am freien Kopf, Stabende über RBE3 ---")
    from statik3d.diagnose import teiltragwerke
    m, fuss, kopf = _quader_zugstab("stirn")
    teile = teiltragwerke(m)
    teil_fuss = next((set(g) for g in teile if fuss in g), set())
    vol = {int(k) for el in m.elements if el.typ in ("tet10", "tet4") for k in el.nodes}
    check("Teiltragwerke: die Kopplung RBE3 verbindet das Stabende mit dem Quader",
          len(teil_fuss & vol) > 0, f"{len(teile)} Teile, Teil des Fusses {len(teil_fuss)} Knoten")
    try:
        r = solver.solve_static(m, case="LF1")
        fehler = None
    except Exception as ex:          # noqa: BLE001
        r, fehler = None, f"{type(ex).__name__}: {str(ex)[:120]}"
    if r is None:
        check("kein gültiges Ergebnis ohne die Last: die Rechnung meldet den Mechanismus", bool(fehler), fehler)
        # die Gleichgewichtskontrolle faengt den Fall auch fuer sich: mit der
        # Teilsuche von vorher (ohne Starrkoerper) rechnet er durch und ist dann
        # „nicht gültig“
        from statik3d import diagnose
        echt = diagnose.teiltragwerke

        def ohne_starrkoerper(model):
            sk = model.starrkoerper
            model.starrkoerper = []
            try:
                return echt(model)
            finally:
                model.starrkoerper = sk
        diagnose.teiltragwerke = ohne_starrkoerper
        try:
            m2, _f, _k = _quader_zugstab("stirn")
            r2 = solver.solve_static(m2, case="LF1")
        finally:
            diagnose.teiltragwerke = echt
        g = r2.info.get("gleichgewicht_global") or {}
        check("… mit der Teilsuche von vorher: ΣF bezogen 1,0 → „nicht gültig: Gleichgewicht verletzt“",
              g.get("rel_F", 0) > 0.5 and "Gleichgewicht verletzt" in solver.gueltigkeit(r2.info),
              f"rel_F {g.get('rel_F')}, {solver.gueltigkeit(r2.info)[:60]}")
        return
    g = r.info.get("gleichgewicht_global") or {}
    R = np.asarray(r.reactions, float).reshape(-1, 6)
    print(f"       ΣR_z {R[:, 2].sum() / 1e3:+.3f} kN, ΣF bezogen {g.get('rel_F')}, "
          f"gültig „{solver.gueltigkeit(r.info)}“")
    check("kein gültiges Ergebnis ohne die Last (nicht gültig oder Abbruch)",
          bool(solver.gueltigkeit(r.info)), solver.gueltigkeit(r.info))
    check("… und keine Lagerkraft gegen die Lastrichtung im Quader (vorher ΣR_z = −10 kN)",
          R[:, 2].sum() >= -1.0, f"{R[:, 2].sum():.3f} N")


def test_gegenproben():
    print("\n--- Gegenproben ohne Meldung ---")
    m, fuss, kopf = _quader_zugstab("stirn")
    m.elements[[i for i, e in enumerate(m.elements) if e.typ == "truss"][0]].nur = ""
    r = solver.solve_static(m, case="LF1")
    g = r.info.get("gleichgewicht_global") or {}
    check("derselbe Quader, Stab trägt Druck: gültig, Gleichgewicht erfüllt",
          not solver.gueltigkeit(r.info) and g.get("ok") and not g.get("verletzt"),
          f"rel_F {g.get('rel_F', float('nan')):.1e}")
    from tests.test_kontakt_warmstart import platte, rechnen
    r, _t = rechnen(platte(strebe=True))
    g = r.info.get("gleichgewicht_global") or {}
    check("Platte mit Reibkontakt und ausfallender Strebe: gültig, Gleichgewicht erfüllt",
          not solver.gueltigkeit(r.info) and g.get("ok"), f"rel_F {g.get('rel_F', float('nan')):.1e}")


def main():
    for t in (test_schranken, test_zugstab_druck_rbe3, test_gegenproben):
        try:
            t()
        except Exception as ex:          # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{t.__name__} ohne Ausnahme", False, f"{type(ex).__name__}: {ex}")
    n_ok = sum(1 for _n, ok in RESULTS if ok)
    print(f"\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
