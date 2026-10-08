"""
Prüfmatrix für quadratischen Kontakt (Paket Q3 des Bauplans Kontakt quadratisch, 08.10.2026).

Der Bauplan (PLAN-KONTAKT-QUADRATISCH-2026-10-07) lässt Kontakt, Fugen und Flächenlager an
tet10, hex20 und pent15 rechnen: die Seitenmitten jeder Kontaktseite sind an ihre Ecken
gebunden (Paket Q1). Dieses Paket bringt die Prüfmatrix (tests/pruefmatrix.py) auf diesen Stand:

* In der Matrix entfällt „gesperrt“ für Volumenelemente; es bleibt für quadratische **Schalen**
  (neuer Fall S1) und ist dort das erwartete Ergebnis.
* Die Deckel von K2 und K7 sind Flächenlager mit Bettung k/A statt Knotenfedern nach
  konsistenten Anteilen. Die Federn hatten an tri6-Ecken null und an quad8-Ecken negative
  Anteile, die supports._entry verwirft (K2 +1221 bzw. +90 N/mm², K7 hex20 Federn +29 %:
  Fehler der Matrix, nicht des Kontakts).
* Neu F1 (Block auf einem Flächenlager „starr mit Ausfall bei Zug“, außermittiger Druck, Handrechnung
  σ = N/A ± M/W), F2 (dasselbe Lager hebt unter Zug ab und trägt nichts) und K8 (Rohrbolzen in
  der Bohrung mit Übermaß, Lamé, gekrümmte Fuge; Grenzen am Entwurf geeicht).

Jede Prüfung läuft auch ohne das Geprüfte und muss dann scheitern (Gegenproben unten).

Aufruf:  python -m tests.test_pruefmatrix_q3
"""
import contextlib
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import assemble as asm, fugen              # noqa: E402
from tests import pruefmatrix as pm                      # noqa: E402

RESULTS = []

#: (Familie, Typ, Ordnung) der Stufen Mittel und Fein
QUADRATISCH = (("tet", "tet10", 2), ("hex", "hex20", 2))
STUFEN_Q = (("Mittel", 1.0), ("Fein", 0.5))
#: alle drei Stufen: (Stufe, Kantenlängenfaktor, [(Familie, Typ, Ordnung)])
STUFEN_ALLE = (("Entwurf", 1.0, (("tet", "tet4", 1), ("hex", "hex8", 1))),
               ("Mittel", 1.0, QUADRATISCH), ("Fein", 0.5, QUADRATISCH))


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FEHLER'} {name:78s} {detail}")
    return bool(ok)


@contextlib.contextmanager
def gesetzt(*patches):
    """(Objekt, Name, Wert) setzen und danach zurück - die Rücknahmeproben."""
    alt = [(o, n, getattr(o, n)) for o, n, _w in patches]
    for o, n, w in patches:
        setattr(o, n, w)
    try:
        yield
    finally:
        for o, n, w in alt:
            setattr(o, n, w)


def zelle(fall, stufe, familie, typ, ordnung, faktor):
    return pm.zelle(fall, stufe, familie, typ, ordnung, faktor)


def kurz(z):
    return "; ".join(f"{x['name']} {pm.zahl(x['wert'])}" for x in z["metriken"]) or z["befund"][:90]


def test_deckel_als_flaechenlager():
    print("\n--- K2 und K7: der Deckel ist ein Flächenlager mit Bettung k/A ---")
    for fall in (pm.FugeZug(), pm.Anfangsspalt()):
        for stufe, faktor in STUFEN_Q:
            for familie, typ, ordnung in QUADRATISCH:
                z = zelle(fall, stufe, familie, typ, ordnung, faktor)
                check(f"{fall.kurz} {stufe} {typ}: grün (Federn und Elemente auf 1 %, 1 N/mm²)",
                      z["ergebnis"] == "grün", f"{z['ergebnis']}: {kurz(z)}")
    # Aufbau: ein Flächenlager Deckel, seine Knoten sind nur Ecken
    for fall in (pm.FugeZug(), pm.Anfangsspalt()):
        for familie, typ, ordnung in QUADRATISCH:
            m, _meta = fall.bauen(familie, typ, ordnung, fall.h, [])
            ss = [s for s in m.surface_supports if s.name == "Deckel"]
            ecken = pm.ecken_am_netz(m)
            check(f"{fall.kurz} {typ}: genau ein Flächenlager „Deckel“ mit Federn, nur auf Eckknoten",
                  len(ss) == 1 and ss[0].nodes and all(int(n) in ecken for n in ss[0].nodes)
                  and all(ss[0].dof_behaviour(d).typ == "spring" for d in ((0, 1, 2) if fall.kurz == "K2" else (2,))),
                  f"{len(ss)} Lager, {len(ss[0].nodes) if ss else 0} Knoten")
            X = np.asarray(m.nodes, float)
            deckel = {n for n in range(m.nn) if abs(X[n, 2] - X[:, 2].max()) < 1e-9}
            check(f"{fall.kurz} {typ}: keine Knotenfedern am Deckel (nur das Flächenlager hält)",
                  not any(s.node in deckel and any(s.dof_behaviour(d).typ == "spring" for d in range(6))
                          for s in m.supports))
    # Gegenprobe: die alten Knotenfedern nach konsistenten Anteilen sind rot (wie am 07.10.2026 gemessen)
    alte = (pm, "deckel_lager",
            lambda m, seiten, k, dofs, name="Deckel": pm.federn(m, seiten, k, dofs))
    with gesetzt(alte):
        z2 = zelle(pm.FugeZug(), "Mittel", "tet", "tet10", 2, 1.0)
        z2h = zelle(pm.FugeZug(), "Mittel", "hex", "hex20", 2, 1.0)
        z7h = zelle(pm.Anfangsspalt(), "Mittel", "hex", "hex20", 2, 1.0)
    check("Gegenprobe K2 tet10 mit Knotenfedern: rot (σ_v Element +1221 N/mm²)",
          z2["ergebnis"] == "rot" and any(x["name"] == "σ_v Element" and x["wert"] > 1000 for x in z2["metriken"]),
          kurz(z2))
    check("Gegenprobe K2 hex20 mit Knotenfedern: rot (σ_v Element +90 N/mm²)",
          z2h["ergebnis"] == "rot" and any(x["name"] == "σ_v Element" and x["wert"] > 50 for x in z2h["metriken"]),
          kurz(z2h))
    check("Gegenprobe K7 hex20 mit Knotenfedern: rot (Federn +29 %)",
          z7h["ergebnis"] == "rot" and any(x["name"] == "Federn" and x["wert"] > 20 for x in z7h["metriken"]),
          kurz(z7h))


def test_f1_trapez():
    print("\n--- F1: Flächenlager mit Ausfall bei Zug, außermittiger Druck, Handrechnung N/A ± M/W ---")
    fall = pm.FlaechenlagerExzentrisch()
    # Handrechnung unabhängig vom Fall: N = 200 N/mm² · 1 m², e = L/12, W = B L²/6
    A, L, e = 1.0 * 1.0, 1.0, 1.0 / 12.0
    N = 200e6 * A
    W = 1.0 * L ** 2 / 6.0
    s_max, s_min = N / A + N * e / W, N / A - N * e / W
    check("Handrechnung: σ = N/A ± M/W = 300 und 100 N/mm² an den Rändern der Sohle",
          abs(s_max - 300e6) < 1 and abs(s_min - 100e6) < 1 and abs(fall.druck(L) - s_max) < 1
          and abs(fall.druck(0.0) - s_min) < 1, f"{s_max / 1e6:.1f} / {s_min / 1e6:.1f} N/mm²")
    for stufe, faktor, typen in STUFEN_ALLE[1:]:
        for familie, typ, ordnung in typen:
            z = zelle(fall, stufe, familie, typ, ordnung, faktor)
            check(f"F1 {stufe} {typ}: grün, σ_v, Auflager, Moment auf Rechengenauigkeit, kein Knoten offen",
                  z["ergebnis"] == "grün" and all(abs(x["wert"]) < 1e-3 for x in z["metriken"]),
                  f"{z['ergebnis']}: {kurz(z)}")
    z4 = zelle(fall, "Entwurf", "tet", "tet4", 1, 1.0)
    z8 = zelle(fall, "Entwurf", "hex", "hex8", 1, 1.0)
    check("F1 Entwurf: hex8 grün; tet4 gelb (zu steif, Diskretisierung), nicht rot",
          z8["ergebnis"] == "grün" and z4["ergebnis"] == "gelb", f"hex8 {z8['ergebnis']}, tet4 {z4['ergebnis']}")
    # die Randspannungen der Sohle direkt aus der Rechnung gelesen, nicht über die Auswertung des Falls
    for familie, typ, ordnung in QUADRATISCH:
        m, _meta = fall.bauen(familie, typ, ordnung, fall.h, [])
        res = pm.solver.solve_static(m, workers=1)
        X = np.asarray(m.nodes, float)
        zeilen = pm.knotenspannung(res, [n for n in pm.ecken_am_netz(m) if abs(X[n, 2]) < 1e-9])
        links = max(pm.sv(r) for n, S in zeilen.items() if abs(X[n, 0]) < 1e-9 for r in S) / pm.MPA
        rechts = max(pm.sv(r) for n, S in zeilen.items() if abs(X[n, 0] - 1.0) < 1e-9 for r in S) / pm.MPA
        check(f"F1 {typ}: Sohle links 100 und rechts 300 N/mm² (±1), direkt aus res.solid_knoten",
              abs(links - 100.0) < 1.0 and abs(rechts - 300.0) < 1.0, f"{links:.3f} / {rechts:.3f} N/mm²")
    # Gegenproben: ohne Bindung der Seitenmitten ist die Sohle falsch gelagert
    with gesetzt((asm, "KONTAKTSEITEN_BINDEN", False)):
        for familie, typ, ordnung in QUADRATISCH:
            z = zelle(fall, "Mittel", familie, typ, ordnung, 1.0)
            check(f"Gegenprobe F1 Mittel {typ} ohne Bindung: rot (σ_v weit daneben)",
                  z["ergebnis"] == "rot" and any(x["name"] == "σ_v" and abs(x["wert"]) > 100 for x in z["metriken"]),
                  kurz(z))


def test_f2_hebt_ab():
    print("\n--- F2: Flächenlager mit Ausfall bei Zug trägt keinen Zug ---")
    fall = pm.FlaechenlagerAbheben()
    for stufe, faktor, typen in STUFEN_ALLE:
        for familie, typ, ordnung in typen:
            z = zelle(fall, stufe, familie, typ, ordnung, faktor)
            check(f"F2 {stufe} {typ}: grün (Sohle 0, alle Knoten offen, Block spannungsfrei, Federn = F)",
                  z["ergebnis"] == "grün", f"{z['ergebnis']}: {kurz(z)}")
    with gesetzt((fall.__class__, "ausfall", "")):
        z = zelle(fall, "Mittel", "hex", "hex20", 2, 1.0)
    check("Gegenprobe F2 ohne Ausfall bei Zug: rot (die Sohle hält den Block, Sohle ≠ 0)",
          z["ergebnis"] == "rot" and any(x["name"] == "Sohle" and abs(x["wert"]) > 10 for x in z["metriken"]),
          kurz(z))
    with gesetzt((asm, "KONTAKTSEITEN_BINDEN", False)):
        z = zelle(fall, "Mittel", "tet", "tet10", 2, 1.0)
    check("Gegenprobe F2 Mittel tet10 ohne Bindung: rot (σ_v Element weit daneben)",
          z["ergebnis"] == "rot" and any(x["name"] == "σ_v Element" and abs(x["wert"]) > 100 for x in z["metriken"]),
          kurz(z))


def test_k8_bolzen():
    print("\n--- K8: Rohrbolzen in Bohrung mit Übermaß (Lamé), gekrümmte Fuge ---")
    fall = pm.BolzenInBohrung()
    k = fall.lame()
    # Lamé-Handrechnung: Pressung aus σ_v(Nabe, Bohrung) = 355 N/mm², Gleichgewicht der Übermaße
    check("Lamé: Pressung p so, dass σ_v der Nabe an der Bohrung 355 N/mm² erreicht",
          abs(k["p"] * k["sv_nabe_a"] / pm.MPA - 355.0) < 1e-6, f"p {k['p'] / pm.MPA:.2f} N/mm²")
    check("Lamé: Übermaß am Durchmesser = 2 (u_Nabe − u_Bolzen) p (radial die Hälfte)",
          abs(k["dD"] - 2.0 * k["p"] * (k["u_nabe"] - k["u_bolzen"])) < 1e-15
          and k["u_nabe"] > 0 > k["u_bolzen"], f"{k['dD'] * 1e6:.1f} µm")
    erwartet = {("Entwurf", "tet4"): "gelb", ("Entwurf", "hex8"): "grün"}
    for stufe, familie, typ, ordnung, faktor in (("Entwurf", "tet", "tet4", 1, 1.0), ("Entwurf", "hex", "hex8", 1, 1.0),
                                                 ("Mittel", "tet", "tet10", 2, 1.0), ("Mittel", "hex", "hex20", 2, 1.0),
                                                 ("Fein", "tet", "tet10", 2, 0.5), ("Fein", "hex", "hex20", 2, 0.5)):
        z = zelle(fall, stufe, familie, typ, ordnung, faktor)
        soll = erwartet.get((stufe, typ), "grün")
        check(f"K8 {stufe} {typ}: {soll} (Grenzen am Entwurf geeicht, Mittel und Fein halten sie)",
              z["ergebnis"] == soll and z["kontakt_konv"] is True and not z["pivots"],
              f"{z['ergebnis']}: {kurz(z)}")
    # die Fuge wird als zylindrisch erkannt (Übermaß am Durchmesser halbiert)
    for familie, typ, ordnung in QUADRATISCH:
        m, meta = fall.bauen(familie, typ, ordnung, fall.h, [])
        res = pm.solver.solve_static(m, workers=1)
        log = " ".join(res.info.get("contact_log", []))
        check(f"K8 {typ}: Fuge zylindrisch erkannt, radial wirkt die Hälfte des Übermaßes",
              "zylindrisch" in log and f"radial wirken {0.5 * k['dD'] * 1e6:.4g}" in log,
              [z for z in res.info.get("contact_log", []) if "Übermaß" in z][0][:110])
        weit = pm.pruefe_sehne(m, meta["slave"])
        check(f"K8 {typ}: die Seitenmitten der Fuge liegen nach der Rechnung auf der Sehne (Q1)",
              weit < 1e-9, f"{weit * 1e3:.6f} mm neben der Sehne")
    # Gegenprobe: ohne Bindung ist die Fuge mit den Seitenmitten als Kontaktknoten weit daneben
    with gesetzt((asm, "KONTAKTSEITEN_BINDEN", False)):
        for familie, typ, ordnung in QUADRATISCH:
            z = zelle(fall, "Mittel", familie, typ, ordnung, 1.0)
            check(f"Gegenprobe K8 Mittel {typ} ohne Bindung: nicht grün (Nabe an der Bohrung weit daneben)",
                  z["ergebnis"] != "grün" and any(x["name"] == "σ_v Nabe(a)" and abs(x["wert"]) > 100
                                                  for x in z["metriken"]), kurz(z))


def test_schalen_bleiben_gesperrt():
    print("\n--- S1: quadratische Schalen an Flächenlager bleiben gesperrt ---")
    fall = pm.SchaleAnFlaechenlager()
    z = zelle(fall, "Entwurf", "hex", "hex8", 1, 1.0)
    check("S1 Entwurf (shell4): rechnet, Auflagerkraft = q A", z["ergebnis"] == "grün", f"{z['ergebnis']}: {kurz(z)}")
    for stufe, faktor in STUFEN_Q:
        z = zelle(fall, stufe, "hex", "hex20", 2, faktor)
        check(f"S1 {stufe} (shell8): gesperrt - das erwartete Ergebnis, mit Grund an Schalen",
              z["ergebnis"] == "gesperrt" and "Schalen" in z["befund"], z["befund"][:100])
    with gesetzt((fugen, "quadratische_knoten", lambda model: {})):
        z = zelle(fall, "Mittel", "hex", "hex20", 2, 1.0)
    check("Gegenprobe S1 ohne Sperre: rot „Sperre fehlt“ (die Rechnung lief an der Schale durch)",
          z["ergebnis"] == "rot" and "Sperre fehlt" in z["befund"], z["befund"][:100])


def test_matrix_ohne_gesperrt_fuer_volumen():
    print("\n--- Prüfmatrix Mittel: keine gesperrte Zelle mehr bei Volumenelementen ---")
    faelle = [f for f in pm.FAELLE if f.rechenart in ("Kontakt", "Kontakt + Plastizität") and f.kurz != "S1"]
    check("die Kontaktfälle der Matrix: K1 bis K8, F1, F2, KP1, KP2",
          [f.kurz for f in faelle] == ["K1", "K2", "K3", "K4", "K5", "K6", "K7", "F1", "F2", "K8", "KP1", "KP2"],
          " ".join(f.kurz for f in faelle))
    gesperrt, nicht_gruen = [], []
    for fall in faelle:
        for familie, typ, ordnung in QUADRATISCH:
            z = zelle(fall, "Mittel", familie, typ, ordnung, 1.0)
            if z["ergebnis"] == "gesperrt":
                gesperrt.append(f"{fall.kurz} {typ}")
            elif z["ergebnis"] != "grün":
                nicht_gruen.append(f"{fall.kurz} {typ} {z['ergebnis']}")
    check("keine Zelle der Stufe Mittel ist gesperrt (tet10, hex20)", not gesperrt, ", ".join(gesperrt))
    check("alle 24 Kontaktzellen der Stufe Mittel sind grün", not nicht_gruen, ", ".join(nicht_gruen))


def main() -> int:
    for t in (test_deckel_als_flaechenlager, test_f1_trapez, test_f2_hebt_ab, test_k8_bolzen,
              test_schalen_bleiben_gesperrt, test_matrix_ohne_gesperrt_fuer_volumen):
        try:
            t()
        except Exception as ex:             # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{t.__name__} läuft ohne Ausnahme", False, str(ex)[:120])
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print("\n" + "=" * 60)
    print(f"Ergebnis: {n_ok}/{len(RESULTS)} Prüfungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
