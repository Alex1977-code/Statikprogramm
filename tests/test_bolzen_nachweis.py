"""Bolzennachweis nach EN 1993-1-8, 3.13 (Tab. 3.10) fuer Passstifte (06.11.2026).

Vorgaben des Anwenders: Abscheren F_v,Rd = 0,6 A f_up / gamma_M2 mit f_up = f_u des
am Koerper angegebenen Werkstoffs; Lochleibung und Biegung mit f_yp; Biegung mit
Wechselwirkung nach Tab. 3.10, das Moment aus dem Netz (kenntlich gemacht). Nur
nachgewiesen, wenn der Anwender den Koerper als Bolzen festgelegt und Durchmesser
und Werkstoff angegeben hat - sonst „Nachweis nicht geführt“ mit Grund, kein
Vorgabewert, nichts aus Namen oder Form.

1. Handprobe an den Formeln (A = 491 mm², F = 133,2 kN): f_up 490 gibt eta 1,15,
   f_up 510 gibt 1,11; Biegung, Lochleibung und Wechselwirkung von Hand.
2. Kleines Kontaktmodell: Querkraft aus den Kontaktkraeften = Auflagerreaktion
   der einen Seite (unabhaengiger Weg); Momente beider Seiten heben sich auf.
3. Keine Festlegung, kein Werkstoff, kein Durchmesser, kein f_u: nicht gefuehrt.
4. Speichern/Laden: ohne Festlegung bleibt die Datei bitgleich; mit Festlegung
   rund; die Festlegung aendert die Kennung der Ergebnisse nicht.
5. Festlegen/Entfernen (die Funktionen hinter „Als Bolzen nachweisen…“).

Aufruf:  python -m tests.test_bolzen_nachweis
"""
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import ergebnisse, mesher, solver                       # noqa: E402
from statik3d.ec3 import bolzen as B                                  # noqa: E402
from statik3d.model import Material, Model, Volumenkoerper           # noqa: E402

RESULTS = []
A_MM2 = math.pi * 25.0 ** 2 / 4.0
MM = 1e-3


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:84s} {str(detail)[:170]}")
    return ok


class Res:
    def __init__(self, contact):
        self.contact = contact


class Analyse:
    def __init__(self, res):
        self.cases = {"LF1": res}


def box_knoten(m, x0, x1, y0, y1, z0, z1):
    return [m.add_node(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]


def kuenstlich(F=133.2e3):
    """Stift Ø 25 (als Quader 25 x 70 x 25 mm, y = Achse), Deckel A und Gegenstueck B
    als Koerper; die Kraft F wirkt von A bei y = 20 mm in +x, von B bei y = 50 mm
    in -x auf den Stift (Kontakteintraege mit je einem Stiftknoten als Master)."""
    m = Model("Bolzen")
    m.add_material(Material.steel("S355"))
    m.add_material(Material("Stift490", fy=355e6, fu=490e6))
    m.add_material(Material("OhneFu", fy=355e6))
    m.add_material(Material("OhneFy"))
    e0 = len(m.elements)
    pin = mesher.grid_box(m, "S355", 25 * MM, 70 * MM, 25 * MM, 2, 7, 2, origin=(-12.5 * MM, 0.0, -12.5 * MM))
    m.koerper["Stift"] = Volumenkoerper("Stift", material="S355", elemente=list(range(e0, len(m.elements))))
    ka = box_knoten(m, 12.5 * MM, 40 * MM, 0.0, 35 * MM, -20 * MM, 20 * MM)
    kb = box_knoten(m, -40 * MM, -12.5 * MM, 35 * MM, 70 * MM, -20 * MM, 20 * MM)
    for name, kn in (("A", ka), ("B", kb)):
        e = m.add_element("hex8", kn, "S355")
        m.koerper[name] = Volumenkoerper(name, material="S355", elemente=[e])
    # Kraftpunkte im Stift auf der Achsmitte der Seitenflaechen: y = 20 mm (+x) bzw. y = 50 mm (-x)
    p_a = int(pin[-1, 2, 1])
    p_b = int(pin[0, 5, 1])
    contact = [
        {"kind": "node", "label": "A:1", "node": ka[0], "master": ([p_a], [1.0]), "F_vek": [-F, 0.0, 0.0]},
        {"kind": "node", "label": "B:1", "node": kb[0], "master": ([p_b], [1.0]), "F_vek": [F, 0.0, 0.0]},
    ]
    return m, Res(contact)


def lastfall(m, res, stoff="Stift490"):
    return B.bolzen_lastfall(m, res, "Stift", {"d": 0.025, "werkstoff": stoff}, m.materials[stoff], m.design)


def test_handprobe():
    print("\n--- 1. Handprobe an den Formeln (A = 491 mm², F = 133,2 kN) ---")
    F = 133.2e3
    for stoff, fup, soll in (("Stift490", 490.0, 1.15), ("S355", 510.0, 1.11)):
        m, res = kuenstlich(F)
        w = lastfall(m, res, stoff)
        check(f"f_up {fup:g}: kein Fehler", not w["fehler"], w.get("fehler", ""))
        if w["fehler"]:
            continue
        Fv = 0.6 * A_MM2 * fup / 1.25 / 1e3
        check(f"f_up {fup:g}: F_v,Rd = {Fv:.1f} kN, V = 133,2 kN, eta_v = {soll:.2f}",
              abs(w["F_vRd"] / 1e3 - Fv) < 0.1 and abs(w["V"] / 1e3 - 133.2) < 0.01
              and abs(w["eta_v"] - soll) < 0.005, f"{w['F_vRd'] / 1e3:.2f} kN, V {w['V'] / 1e3:.2f}, eta {w['eta_v']:.3f}")
    m, res = kuenstlich(F)
    w = lastfall(m, res)
    MRd = 1.5 * math.pi * 25.0 ** 3 / 32.0 * 355.0 / 1e3             # Nm
    M = F * 0.015                                                     # Hebel 15 mm zur Fuge bei y = 35 mm
    check("Biegung: M_Rd = 1,5 W_el f_yp = 816,9 Nm, M_Ed = F 15 mm = 1998 Nm",
          abs(w["M_Rd"] - MRd) < 0.5 and abs(w["M"] - M) < 0.5, f"{w['M_Rd']:.1f} / {w['M']:.1f} Nm")
    eta_ww = (M / MRd) ** 2 + (133.2 / (0.6 * A_MM2 * 490 / 1.25 / 1e3)) ** 2
    check("Wechselwirkung (M/M_Rd)² + (V/F_v,Rd)² = 7,31", abs(w["eta_ww"] - eta_ww) < 0.01, f"{w['eta_ww']:.3f}")
    Fb = 1.5 * 35.0 * 25.0 * 355.0 / 1e3
    check("Lochleibung je Partner: F_b,Rd = 1,5 t d f_y = 465,9 kN (t = 35 mm), eta 0,286",
          len(w["partner"]) == 2 and all(abs(p["F_bRd"] / 1e3 - Fb) < 0.5 and abs(p["eta_b"] - 133.2 / Fb) < 0.002
                                         for p in w["partner"]), [(p["name"], round(p["t"] * 1e3, 1)) for p in w["partner"]])
    check("Quader statt Rundstahl: Hinweis zum gemessenen Durchmesser",
          any("gemessener Durchmesser" in h for h in w["hinweise"]), w["hinweise"])
    # Lochleibung mit dem kleineren f_y: Partner A mit f_y 275 (Quader 27,5 mm dick: Stufe bis 40 mm)
    m2, res2 = kuenstlich(F)
    m2.add_material(Material("Platte275", fy=275e6, fu=430e6))
    m2.koerper["A"].material = "Platte275"
    w2 = lastfall(m2, res2)
    pa = [p for p in w2["partner"] if p["name"] == "A"][0]
    check("Lochleibung: f_y = min(f_yp 355, f_y des Partners 275) = 275", abs(pa["fy"] - 275e6) < 1.0, pa.get("fy"))


def test_nicht_gefuehrt():
    print("\n--- 3. Keine Angabe: Nachweis nicht geführt, mit Grund ---")
    m, res = kuenstlich()
    an = Analyse(res)
    check("Koerper ohne Festlegung: kein Bolzennachweis, auch nicht nach dem Namen „Stift“",
          B.check_bolzen(m, an) == {}, "")
    m.koerper["Stift"].bolzen = {"d": 0.025}
    c = B.check_bolzen(m, an)["Stift"]
    check("ohne Werkstoff: nicht geführt, Grund genannt", c.fehler.startswith("Werkstoff nicht angegeben")
          and "Nachweis nicht geführt" in c.zeile(), c.zeile())
    m.koerper["Stift"].bolzen = {"werkstoff": "Stift490"}
    c = B.check_bolzen(m, an)["Stift"]
    check("ohne Durchmesser: nicht geführt", "Durchmesser" in c.fehler, c.fehler)
    m.koerper["Stift"].bolzen = {"d": 0.025, "werkstoff": "OhneFu"}
    c = B.check_bolzen(m, an)["Stift"]
    check("Werkstoff ohne f_u: nicht geführt (keine Ersatzregel 1,3 f_y)", "f_u fehlt" in c.fehler, c.fehler)
    m.koerper["Stift"].bolzen = {"d": 0.025, "werkstoff": "OhneFy"}
    c = B.check_bolzen(m, an)["Stift"]
    check("Werkstoff ohne f_y: nicht geführt", "f_y fehlt" in c.fehler, c.fehler)
    m.koerper["Stift"].bolzen = {"d": 0.025, "werkstoff": "Stift490"}
    c = B.check_bolzen(m, an)["Stift"]
    check("mit beiden Angaben: geführt, Ausgabezeile nennt Werte und „netzabhängig“",
          not c.fehler and "netzabhängig" in c.zeile() and c.lastfall == "LF1", c.zeile())
    check("Hinweise der Ausgabe tragen den Netzvermerk", B.NETZABHAENGIG in c.hinweise, "")
    c = B.check_bolzen(m, Analyse(Res([])))["Stift"]
    check("Lastfall ohne Kontaktergebnis: nicht geführt mit Grund", c.fehler and "Kontakt" in c.fehler, c.fehler)


def fe_modell(spalt: float = 0.05e-3):
    """Stift (Quader 25 x 70 x 25 mm, y = Achse) zwischen vier Blocken: A1 (+x) und A2 (-x)
    fuer y 0..35, B1 (+x) und B2 (-x) fuer y 35..70; A1 wird mit F gegen den Stift gedrueckt,
    A2 und B1 stehen mit Spalt, B2 liegt dicht; die Aussenflaechen von A2, B1, B2 sind fest."""
    m = Model("Stift im Kontakt")
    m.add_material(Material.steel("S355"))
    m.add_material(Material("Stift490", fy=355e6, fu=490e6))
    n_el0 = len(m.elements)
    pin = mesher.grid_box(m, "S355", 25 * MM, 70 * MM, 25 * MM, 2, 4, 2, origin=(-12.5 * MM, 0.0, -12.5 * MM))
    e_pin = list(range(n_el0, len(m.elements)))
    teile = {}
    for name, x0, y0 in (("A1", 12.5 * MM, 0.0), ("A2", -32.5 * MM - spalt, 0.0),
                         ("B1", 12.5 * MM + spalt, 35 * MM), ("B2", -32.5 * MM, 35 * MM)):
        e0 = len(m.elements)
        n = mesher.grid_box(m, "S355", 20 * MM, 35 * MM, 40 * MM, 2, 2, 2, origin=(x0, y0, -20 * MM))
        teile[name] = (n, list(range(e0, len(m.elements))))
    m.koerper["Stift"] = Volumenkoerper("Stift", material="Stift490", elemente=e_pin)
    m.koerper["A"] = Volumenkoerper("A", material="S355", elemente=teile["A1"][1] + teile["A2"][1])
    m.koerper["B"] = Volumenkoerper("B", material="S355", elemente=teile["B1"][1] + teile["B2"][1])
    X = np.asarray(m.nodes, float)
    for nm, ix, nur_a in (("A1", -1, True), ("A2", 0, True), ("B1", -1, False), ("B2", 0, False)):
        sl = [int(n) for n in pin[ix, :, :].ravel()
              if (X[int(n), 1] < 35 * MM - 1e-9 if nur_a else X[int(n), 1] > 35 * MM + 1e-9)]
        m.add_contact_pair(nm, sl, teile[nm][1], mu=0.0)
    for nm in ("A2", "B1", "B2"):
        n = teile[nm][0]
        aussen = n[-1, :, :] if nm == "B1" else n[0, :, :]
        for k in aussen.ravel():
            m.fix(int(k), "all")
    for k in teile["A1"][0].ravel():
        m.fix(int(k), [1, 2])                     # A1 nur in x frei (die Last schiebt es gegen den Stift)
    # Starrkoerperbewegungen des Stifts (reibungsfreier Kontakt haelt nur in x)
    for idx in ((0, 0, 1), (-1, 0, 1), (0, -1, 1)):
        m.fix(int(pin[idx]), [2])
    m.fix(int(pin[0, 0, 1]), [1])
    lasten = [int(k) for k in teile["A1"][0][-1, :, :].ravel()]
    lc = m.add_load_case("LF1")
    lc.gravity = [0.0, 0.0, 0.0]
    for k in lasten:
        m.load_node(k, Fx=-10e3 / len(lasten), case="LF1")
    m.active_case = "LF1"
    return m, teile, 10e3


def test_gleichgewicht():
    print("\n--- 2. Kleines Kontaktmodell: Querkraft aus den Kontaktkräften = Gleichgewicht ---")
    m, teile, F = fe_modell()
    res = solver.solve_static(m)
    check("Kontakt konvergiert", res.info.get("contact_converged"), res.info.get("contact_iterations"))
    R = np.asarray(res.reactions, float)
    festB = [int(k) for k in teile["B1"][0][-1, :, :].ravel()] + [int(k) for k in teile["B2"][0][0, :, :].ravel()]
    festA = [int(k) for k in teile["A2"][0][0, :, :].ravel()]
    sumRA = R[festA].sum(axis=0)
    sumRB = R[festB].sum(axis=0)
    w = lastfall(m, res)
    check("Bolzenrechnung ohne Fehler", not w["fehler"], w.get("fehler", ""))
    if w["fehler"]:
        return
    V_B = abs(sumRB[0])
    check("Querkraft in der Fuge = Auflagerreaktion der B-Seite (Gleichgewicht, 1 %)",
          abs(w["V"] - V_B) < 0.01 * V_B, f"V {w['V']:.1f} N, ΣR_B {V_B:.1f} N")
    check("… und gleich F minus Reaktion der A-Seite", abs(w["V"] - abs(F - sumRA[0])) < 0.01 * V_B,
          f"F {F:.0f}, ΣR_A {sumRA[0]:.1f}")
    check("Gleichgewicht der Kontaktkräfte am Bolzen (Rest < 1 % von V)",
          w["gleichgewicht_rest"] < 0.01 * w["V"], f"{w['gleichgewicht_rest']:.2f} N")
    f = w["fugen"][0]
    a = np.asarray(w["achse"])
    teile_k = B.kraefte_am_bolzen(m, res, "Stift")
    X = np.asarray(m.nodes, float)
    kn = sorted({int(x) for e in m.koerper["Stift"].elemente for x in m.elements[int(e)].nodes})
    c0 = X[kn].mean(axis=0)
    s0 = min(float((X[k] - c0) @ a) for k in kn)
    xf = c0 + a * (f["s"] + s0)
    mom_u = sum((np.cross(x - xf, F_) for p in teile_k.values() for x, F_ in p if (x - c0) @ a <= f["s"] + s0), np.zeros(3))
    mom_o = sum((np.cross(x - xf, F_) for p in teile_k.values() for x, F_ in p if (x - c0) @ a > f["s"] + s0), np.zeros(3))
    rest = np.linalg.norm(mom_u + mom_o)
    check("Moment unterhalb + oberhalb der Fuge = 0 (Momentengleichgewicht des Bolzens)",
          rest < 0.02 * max(np.linalg.norm(mom_u), 1e-9), f"{np.linalg.norm(mom_u):.3f} Nm, Rest {rest:.4f}")
    check("Moment M_Ed ist ungleich null (Bolzen wird auf Biegung beansprucht)", f["M"] > 1e-3, f"{f['M']:.3f} Nm")


def test_speichern_laden():
    print("\n--- 4. Alte Dateien und Ergebniskennung ---")
    m, _res = kuenstlich()
    d0 = m.to_dict()
    check("ohne Festlegung steht „bolzen“ nicht in der Datei", all("bolzen" not in k for k in d0["koerper"]), "")
    s0 = json.dumps(d0, sort_keys=True)
    k0 = ergebnisse.rechenkennung(m)
    B.bolzen_festlegen(m, ["Stift"], 0.025, "Stift490")
    d1 = m.to_dict()
    soll = {"d": 0.025, "werkstoff": "Stift490"}
    check("mit Festlegung steht sie in der Datei und lädt rund",
          [k for k in d1["koerper"] if k["name"] == "Stift"][0].get("bolzen") == soll
          and Model.from_dict(json.loads(json.dumps(d1))).koerper["Stift"].bolzen == soll, "")
    check("die Festlegung ändert die Kennung der Ergebnisse nicht (sie wird nur nachgewiesen)",
          ergebnisse.rechenkennung(m) == k0, "")
    B.bolzen_entfernen(m, ["Stift"])
    check("Entfernen stellt die Datei bitgleich wieder her", json.dumps(m.to_dict(), sort_keys=True) == s0, "")
    m2 = Model.from_dict(json.loads(s0))
    check("Datei ohne das Feld lädt, kein Körper ist als Bolzen festgelegt",
          all(not k.bolzen for k in m2.koerper.values()), "")


def test_festlegen():
    print("\n--- 5. Festlegen und Entfernen ---")
    m, _r = kuenstlich()
    z = B.bolzen_festlegen(m, ["Stift"], 0.025, "Stift490")
    check("festlegen: Eintrag und Protokollzeile", m.koerper["Stift"].bolzen["d"] == 0.025 and "Stift" in z[0], z)
    for args, text in ((("Stift", 0.0, "Stift490"), "Durchmesser"), (("Stift", 0.025, "gibtsnicht"), "Werkstoff"),
                       (("keiner", 0.025, "Stift490"), "Volumen")):
        try:
            B.bolzen_festlegen(m, [args[0]], args[1], args[2])
            check(f"Abweisung ({text})", False, "kein Fehler")
        except ValueError as ex:
            check(f"Abweisung ({text}) mit Grund", text in str(ex), str(ex))
    check("entfernen: eine aufgehoben, danach leer", B.bolzen_entfernen(m, ["Stift"]) == 1
          and not m.koerper["Stift"].bolzen, "")


def main():
    for t in (test_handprobe, test_nicht_gefuehrt, test_gleichgewicht, test_speichern_laden, test_festlegen):
        try:
            t()
        except Exception as ex:                      # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{t.__name__} ohne Ausnahme", False, f"{type(ex).__name__}: {ex}")
    n_ok = sum(1 for _n, ok in RESULTS if ok)
    print(f"\n{n_ok}/{len(RESULTS)} Prüfungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
