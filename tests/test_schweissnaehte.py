"""
Schweissnaehte im Modell und Kerbfaelle nach DIN EN 1993-1-9 (Tab. 8.2-8.5):
Zuordnung der Kerbfaelle, Groesseneinfluss k_s = (25/t)^0,2, aequivalente
Ersatznaht, Uebernahme in die Staebe, Ermuedungsnachweis, Persistenz.
Aufruf:  python -m tests.test_schweissnaehte
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from statik3d.model import Model, Material, ShellProp, Flaeche  # noqa: E402
from statik3d import schweissnaehte as swn  # noqa: E402
from statik3d.schweissnaehte import Schweissnaht, kerbfall  # noqa: E402
from statik3d import mesher, solver  # noqa: E402
from statik3d.profiles import make_section  # noqa: E402
from statik3d.ec3.fatigue import sn_life  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:66s} {detail}")
    return ok


def kf(name, naht, dsC, dtC=None, detail=None):
    k = kerbfall(naht)
    ok = abs(k["dsC_wirksam"] - dsC) < 1e-9 and (dtC is None or abs(k["dtC"] - dtC) < 1e-9) \
        and (detail is None or detail in k["detail"])
    return check(name, ok, f"Δσ_C={k['dsC_wirksam']:.1f} Δτ_C={k['dtC']:.0f} {k['detail']}")


def test_kerbfaelle():
    N = Schweissnaht
    # Tabelle 8.2: Laengsnaehte
    kf("Stumpfnaht längs automatisch → 125", N("a", "Stumpfnaht", "längs", ausfuehrung="automatisch"), 125, 100, "8.2")
    kf("Kehlnaht längs automatisch → 125 (Δτ 80)", N("a", "Kehlnaht", "längs", ausfuehrung="automatisch"), 125, 80)
    kf("… mit Ansatzstellen → 112", N("a", "Kehlnaht", "längs", ausfuehrung="automatisch mit Ansatzstellen"), 112)
    kf("… von Hand → 100", N("a", "Kehlnaht", "längs"), 100, 80, "Detail 4")
    kf("unterbrochene Kehlnaht → 71", N("a", "Kehlnaht", "längs", unterbrochen=True), 71, 80, "Detail 8")
    kf("Naht mit Freischnitten → 63", N("a", "Stumpfnaht", "längs", freischnitt=True), 63, 100, "Detail 9")
    kf("einseitige Längsstumpfnaht, Wurzel geprüft → 80", N("a", "Stumpfnaht", "längs", einseitig=True, geprueft=True), 80)
    kf("einseitige Längsstumpfnaht ungeprüft → 71", N("a", "Stumpfnaht", "längs", einseitig=True), 71)
    kf("einseitig automatisch mit Gegenlage → 100", N("a", "Stumpfnaht", "längs", einseitig=True, gegenlage=True, ausfuehrung="automatisch"), 100)
    # Tabelle 8.3: Quernaehte
    kf("Querstumpfnaht bearbeitet + geprüft → 112", N("q", "Stumpfnaht", "quer", bearbeitet=True, geprueft=True), 112, 100, "8.3, Detail 1")
    kf("DHV-Naht quer geprüft → 90", N("q", "DHV-Naht", "quer", geprueft=True), 90, 100, "Detail 2/3")
    kf("Querstumpfnaht unbearbeitet ungeprüft → 80", N("q", "Stumpfnaht", "quer"), 80, 100, "Detail 5")
    kf("Querstumpfnaht mit Freischnitten → 80", N("q", "Stumpfnaht", "quer", geprueft=True, freischnitt=True), 80, 100, "Detail 4/5")
    kf("einseitig mit Badsicherung → 71", N("q", "Stumpfnaht", "quer", einseitig=True, gegenlage=True), 71, 100, "Detail 9")
    kf("einseitig, Wurzel geprüft → 71", N("q", "Stumpfnaht", "quer", einseitig=True, geprueft=True), 71, 100, "Detail 11")
    kf("einseitig ungeprüft → 36", N("q", "Stumpfnaht", "quer", einseitig=True), 36, 100, "Detail 11")
    # Tabelle 8.5: Kehlnaht quer (Kreuz-/T-Stoss)
    kf("Kehlnaht quer ℓ = 40 → 80, Δτ 80", N("k", "Kehlnaht", "quer", l_anschluss=40), 80, 80, "8.5, Detail 3")
    kf("Kehlnaht quer ℓ = 70 → 71", N("k", "Doppelkehlnaht", "quer", l_anschluss=70), 71)
    kf("Kehlnaht quer ℓ = 90 → 63", N("k", "Kehlnaht", "quer", l_anschluss=90), 63)
    kf("Kehlnaht quer ℓ = 150 → 50", N("k", "Kehlnaht", "quer", l_anschluss=150), 50)
    kf("Kehlnaht quer ℓ = 400 → 40", N("k", "Kehlnaht", "quer", l_anschluss=400), 40)
    check("Kehlnaht quer: Nahtwurzel 36 als Hinweis", kerbfall(N("k", "Kehlnaht", "quer", l_anschluss=40))["wurzel"] == 36.0)
    # Tabelle 8.4: Steifen
    kf("Quersteife ℓ ≤ 50 → 80", N("s", "Steifenanschluss", "quer", l_anschluss=40), 80, 100, "8.4, Detail 6/7")
    kf("Quersteife 50 < ℓ ≤ 80 → 71", N("s", "Steifenanschluss", "quer", l_anschluss=60), 71)
    kf("Längssteife L = 60 → 71", N("l", "Längssteife", "längs", l_anschluss=60), 71, 100, "8.4, Detail 1/2")
    kf("Längssteife L = 150 → 56", N("l", "Längssteife", "längs", l_anschluss=150), 56)
    # Tabelle 8.5: Deckblech-Ende
    kf("Deckblech-Ende t = 15 → 56", N("d", "Deckblech-Ende", "längs", t=15), 56, 80, "Detail 5")
    kf("Deckblech-Ende t = 25 → 50", N("d", "Deckblech-Ende", "längs", t=25), 50)
    kf("Deckblech-Ende t = 40 → 45", N("d", "Deckblech-Ende", "längs", t=40), 45)
    kf("Deckblech-Ende t = 60 → 40", N("d", "Deckblech-Ende", "längs", t=60), 40)
    kf("Deckblech-Ende bearbeitet t ≤ 20 → 71", N("d", "Deckblech-Ende", "längs", t=15, bearbeitet=True), 71, 80, "Detail 6")
    # Groesseneinfluss
    ks = (25.0 / 40.0) ** 0.2
    kf("Größeneinfluss quer t = 40: 112·(25/40)^0,2", N("q", "Stumpfnaht", "quer", bearbeitet=True, geprueft=True, t=40), 112 * ks)
    kf("Größeneinfluss Kreuzstoß t = 50: 80·(25/50)^0,2", N("k", "Kehlnaht", "quer", l_anschluss=40, t=50), 80 * (25 / 50) ** 0.2)
    kf("kein Größeneinfluss bei Längsnähten", N("a", "Kehlnaht", "längs", t=60), 100)
    kf("kein Größeneinfluss bis 25 mm", N("q", "Stumpfnaht", "quer", geprueft=True, t=25), 90)
    check("k_s-Funktion", abs(swn.groesseneinfluss(40) - ks) < 1e-12 and swn.groesseneinfluss(20) == 1.0)
    # Vorgabe
    k = kerbfall(N("v", "Kehlnaht", "längs", kerbfall_vorgabe=45.0, kerbfall_schub_vorgabe=60.0))
    check("Vorgabe geht vor (Δσ_C 45, Δτ_C 60)", k["dsC_wirksam"] == 45.0 and k["dtC"] == 60.0 and k["vorgabe"])
    try:
        kerbfall(N("x", "Klebung", "längs"))
        check("unbekannte Nahtart → ValueError", False)
    except ValueError as ex:
        check("unbekannte Nahtart → ValueError", "unbekannt" in str(ex))
    check("Bezugstext", "Kehlnaht, längs, a = 5 mm, äquivalent: alle Stäbe" == N("b", "Kehlnaht", "längs", a=5, aequivalent=True).bezug())


def _traeger(kerbfall_manuell=None):
    m = Model()
    m.add_material(Material.steel("S235"))
    m.add_section(make_section("IPE 300"))
    ids = mesher.line_of_beams(m, "S235", "IPE 300", (0, 0, 0), (6, 0, 0), 6)
    m.fix(ids[0], [0, 1, 2, 3])
    m.fix(ids[-1], [1, 2, 3])
    m.case().category = "G"
    for e in range(6):
        m.load_beam(e, qz=-10000.0)
    m.add_member("Traeger", list(range(3)), detail_category=kerbfall_manuell)
    m.add_member("Traeger2", list(range(3, 6)), detail_category=kerbfall_manuell)
    m.add_combination("K1", {"LF1": 1.0}, "ULS")
    m.add_fatigue_load("Ermuedung", "LF1", None, 2e6)
    return m


def test_zuordnung():
    m = _traeger()
    m.schweissnaehte["A"] = Schweissnaht("A", "Kehlnaht", "längs", staebe=["Traeger"])                     # 100 / 80
    m.schweissnaehte["B"] = Schweissnaht("B", "Kehlnaht", "quer", l_anschluss=90, staebe=["Traeger"])     # 63 / 80
    m.schweissnaehte["E"] = Schweissnaht("E", "Stumpfnaht", "quer", geprueft=True, aequivalent=True)     # 90 / 100, alle
    je = swn.kerbfaelle_je_stab(m)
    check("Traeger: ungünstigste Naht B → 63, Δτ min 80",
          abs(je["Traeger"]["dsC"] - 63e6) < 1 and abs(je["Traeger"]["dtC"] - 80e6) < 1 and je["Traeger"]["naht"] == "B",
          str(je.get("Traeger")))
    check("Traeger2: nur die äquivalente Naht → 90 (äquivalent)",
          abs(je["Traeger2"]["dsC"] - 90e6) < 1 and je["Traeger2"]["aequivalent"] and je["Traeger2"]["naht"] == "E")
    log = []
    ge = swn.kerbfaelle_uebernehmen(m, log)
    check("Übernahme schreibt beide Stäbe", sorted(ge) == ["Traeger", "Traeger2"]
          and abs(m.members["Traeger"].detail_category - 63e6) < 1 and abs(m.members["Traeger2"].detail_category_shear - 100e6) < 1
          and len(log) == 2, str(log))
    check("zweite Übernahme ändert nichts", swn.kerbfaelle_uebernehmen(m) == [])
    # aequivalente Naht mit Zuordnung gilt nur dort
    m.schweissnaehte["E"].staebe = ["Traeger2"]
    je = swn.kerbfaelle_je_stab(m)
    check("äquivalente Naht mit Zuordnung: nur Traeger2", je["Traeger2"]["naht"] == "E" and je["Traeger"]["naht"] == "B")
    # Stab ohne Naht behaelt seine Angabe
    m2 = _traeger(71e6)
    m2.schweissnaehte["A"] = Schweissnaht("A", "Stumpfnaht", "quer", bearbeitet=True, geprueft=True, staebe=["Traeger"])
    swn.kerbfaelle_uebernehmen(m2)
    check("Stab ohne Naht behält seinen Kerbfall (71), Stab mit Naht bekommt 112",
          abs(m2.members["Traeger2"].detail_category - 71e6) < 1 and abs(m2.members["Traeger"].detail_category - 112e6) < 1)
    # Flaechen / Linien
    m.schweissnaehte["F"] = Schweissnaht("F", "Kehlnaht", "quer", l_anschluss=150, flaechen=["Haut"])   # 50
    check("Kerbfall für Flächen: ungünstigste Naht an der Haut", swn.kerbfall_fuer_flaechen(m, ["Haut"]) == 50.0)
    check("… keine Naht an anderen Flächen", swn.kerbfall_fuer_flaechen(m, ["Deckel"]) is None)
    m.schweissnaehte["E"].staebe = []
    check("… äquivalente Naht ohne Zuordnung gilt auch für Flächen", swn.kerbfall_fuer_flaechen(m, ["Deckel"]) == 90.0)
    rows = swn.tabelle(m)
    check("Tabelle: Kopf + 4 Nähte, Kerbfall und Fundstelle", len(rows) == 5 and rows[2][9] == "63" and "8.5" in rows[2][12], str(rows[2]))
    z = swn.erlaeuterung(m.schweissnaehte["B"])
    check("Erläuterung nennt Kerbfall und Wurzel", any("63" in s for s in z) and any("Nahtwurzel" in s for s in z))
    # Persistenz
    m3 = Model.from_dict(json.loads(json.dumps(m.to_dict())))
    check("Nähte werden gespeichert und geladen", sorted(m3.schweissnaehte) == ["A", "B", "E", "F"]
          and m3.schweissnaehte["B"].l_anschluss == 90 and m3.schweissnaehte["E"].aequivalent)


def test_ermuedung():
    m = _traeger()
    m.schweissnaehte["N"] = Schweissnaht("N", "Stumpfnaht", "quer", geprueft=True, staebe=["Traeger", "Traeger2"])   # 90
    an = solver.solve_all(m, design=True, fatigue=True)
    fm = an.fatigue.members["Traeger"]
    check("Ermüdungsnachweis nimmt den Kerbfall aus der Naht (90)", abs(fm.category - 90e6) < 1, str(fm.category))
    ds = 45e3 / m.sections["IPE 300"].Wel_y
    check("Δσ = M/W_el", abs(fm.dsig_max - ds) / ds < 1e-2, f"{fm.dsig_max / 1e6:.1f}")
    check("D = n/N_R mit Kerbfall 90", abs(fm.D - 2e6 / sn_life(fm.dsig_max, 90e6, 1.0)) < 1e-9)
    # ohne Naht und ohne Kerbfall: kein Nachweis
    m2 = _traeger()
    an2 = solver.solve_all(m2, design=True, fatigue=True)
    check("ohne Naht und Kerbfall kein Ermüdungsnachweis", "Traeger" not in an2.fatigue.members)


def test_schwingung_kerbfall():
    from statik3d import schwingung as sw, wasserdruck as wdm
    from statik3d.wasserdruck import Wasserdruck
    m = Model("Schütz")
    m.add_material(Material("S"))
    m.add_shell_prop(ShellProp("t", 0.012))
    nx, nz, b, h = 4, 10, 3.0, 5.0
    ids = [[m.add_node(0.0, i * b / nx, k * h / nz) for k in range(nz + 1)] for i in range(nx + 1)]
    el = [m.add_element("shell4", [ids[i][k], ids[i + 1][k], ids[i + 1][k + 1], ids[i][k + 1]], "S", "t")
          for i in range(nx) for k in range(nz)]
    m.flaechen["Haut"] = Flaeche("Haut", dicke="t", material="S", elemente=el)
    for k in range(nz + 1):
        m.fix(ids[0][k], "all")
        m.fix(ids[nx][k], "all")
    wd = Wasserdruck("S", flaechen=["Haut"], h_ow=4.0, richtung=[1.0, 0, 0], unterstroemt=True, spalt=0.3, cp_dyn=0.1)
    wdm.lasten_erzeugen(m, wd)
    m.wasserdruecke["S"] = wd
    m.schweissnaehte["H"] = Schweissnaht("H", "Kehlnaht", "quer", l_anschluss=90, flaechen=["Haut"])   # 63
    erg = sw.nachweis(m, sw.Schwingungsnachweis("N", wasserdruck="S", n_moden=2, d_kante=0.2,
                                                betriebsstunden=100.0, kerbfall=None))
    check("Schwingungsnachweis: Kerbfall aus der Naht an der Haut (63)",
          erg.dyn.get("kerbfall") == 63.0 and "Schweißnähten" in erg.dyn.get("kerbfall_quelle", ""), str(erg.dyn.get("kerbfall")))
    del m.schweissnaehte["H"]
    erg = sw.nachweis(m, sw.Schwingungsnachweis("N", wasserdruck="S", n_moden=2, d_kante=0.2,
                                                betriebsstunden=100.0, kerbfall=None))
    check("… ohne Naht Vorgabe 71", erg.dyn.get("kerbfall") == 71.0)


def main():
    for f in (test_kerbfaelle, test_zuordnung, test_ermuedung, test_schwingung_kerbfall):
        print(f"\n--- {f.__name__} ---")
        try:
            f()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{f.__name__} ohne Ausnahme", False, str(ex)[:80])
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print("\n" + "=" * 60)
    print(f"Ergebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
