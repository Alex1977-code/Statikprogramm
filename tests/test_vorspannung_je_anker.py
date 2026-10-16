"""Vorspannung je Anker: Definition, Verweise der Lastfaelle, Zuordnung, Nachweise (16.10.2026).

Freigegebener Entwurf des Anwenders (woertlich, Auszug): „Vorspannung künftig
einmal je Anker definieren (Pressenkraft, Schlupf), Lastfälle verweisen nur
darauf.“ – „Zustände 0 und ∞ plus P_max beim Spannen reichen. Sofortige
Verluste rechnet das Programm (elastische Verkürzung, Verankerungsschlupf →
P_0). Zeitabhängige Verluste sind Eingabe, wahlweise P_∞ absolut oder Verlust
ΔP_t, Anzeige beider Werte.“ – „Nachweise nach Zustand: Spannen gegen σ_p,max
mit P_max. Nach Verankern (0,85·f_p0,1k) und GZT gegen f_pd mit t = 0. […]
Ermüdung der Anker mit t = ∞.“

Geprueft:

1. Handrechnung P₀ aus P_max, Schlupf und elastischer Verkuerzung: zwei Anker
   A1, A2 (Spanngruppen 1 und 2) neben einem Klemmteil zwischen starrem Boden
   und Kopf. Gruppe 1 spannt, verriegelt mit P_max1 − k1·Δs1; Gruppe 2 spannt
   (A1 verliert k1·P_max2/(k1 + kK)), verriegelt; der Verankerungsschritt gibt
   den Schlupf von A2 frei (Rueckfederung k2·Δs2/Σk):
     P₀,1 = P1 − k1Δs1·kK/(k1+kK) − k1·P2/(k1+kK) + k1·k2·Δs2/Σk
     P₀,2 = P2 − k2Δs2·(k1+kK)/Σk
   linear und mit Plastizitaet (nichtlinearer Weg), dazu Zahl fuer Zahl wie
   dieselbe Eingabe als Anfangsvorspannung im Lastfall.
2. Zeitpunkt ∞ absolut: jeder Anker traegt genau P_∞.
3. Zeitpunkt ∞ mit ΔP_t: P_∞,i = P₀,i − ΔP_t, und P_∞,i ist bitgleich, ob der
   Lastfall ∞ allein, nach dem Lastfall 0 oder vor ihm gerechnet wird
   (Vorgabe von „main“ vom 16.10.2026).
4. Speichern und Laden; alte Dateien ohne die Felder bleiben bitgleich, die
   Rechenkennung aendert sich nur mit gesetztem Verweis.
5. Zuordnung: ΔT- und Kraft-Vorspannungen nach Wert zu Gruppen, Zuordnung
   (Wert A → 0, Wert B → ∞) stellt nur die Lastfaelle der Gruppen um.
6. Nachweise je Zustand: Spannen einmal je Definition mit P_max, nach dem
   Verankern nur t = 0, GZT mit Zustand in der Zeile, Ermuedung meldet t = 0.

Aufruf:  python -m tests.test_vorspannung_je_anker
"""
import json
import os
import shutil
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")

from statik3d import plastizitaet as pl, solver                                # noqa: E402
from statik3d import vorspannung as vsp                                        # noqa: E402
from statik3d.model import (Material, Model, NodalLoad, Section, TempLoad,    # noqa: E402
                            VorspannDefinition, LoadCase)

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:90s} {detail}")
    return ok


def nahe(name, ist, soll, tol, einheit=""):
    try:
        ist, soll = float(ist), float(soll)
    except (TypeError, ValueError):
        return check(name, False, f"ist {ist!r}")
    abw = abs(ist - soll) / (abs(soll) if abs(soll) > 1e-14 else 1.0)
    return check(name, abw <= tol, f"ist {ist:.9g} soll {soll:.9g} ({abw:.2e}) {einheit}")


E = 210e9
L = 1.0
A_1, A_2, A_K = 1e-3, 2e-3, 4e-3
K_1, K_2, K_K = E * A_1 / L, E * A_2 / L, E * A_K / L
P1, P2 = 500e3, 300e3            # Pressenkraefte P_max [N]
DS1, DS2 = 0.5e-3, 0.25e-3       # Verankerungsschlupf [m]
P = 200e3                        # aeussere Zuglast am Kopf [N]
KG = K_1 + K_2 + K_K
P0_1 = P1 - K_1 * DS1 * K_K / (K_1 + K_K) - K_1 * P2 / (K_1 + K_K) + K_1 * K_2 * DS2 / KG
P0_2 = P2 - K_2 * DS2 * (K_1 + K_K) / KG


def _modell(plast=False, definitionen=True):
    """Boden G, Kopf H; Anker A1, A2 (Fachwerkstaebe G-H) und Klemmteil K.
    Definitionen V1 (A1, Gruppe 1) und V2 (A2, Gruppe 2)."""
    m = Model("Anker je Definition")
    m.add_material(Material("Stahl", E=E, nu=0.3, rho=7850, alpha=1e-5))
    G = m.add_node(0.0, 0.0, 0.0)
    G2 = m.add_node(0.0, 0.0, 0.0)
    H = m.add_node(0.0, 0.0, L)
    m.fix(G, "all")
    m.fix(G2, "all")
    m.fix(H, [0, 1, 3, 4, 5])
    el = {}
    for name, A in (("A1", A_1), ("A2", A_2), ("K", A_K)):
        m.add_section(Section.circle("Q_" + name, float(np.sqrt(4.0 * A / np.pi))))
        el[name] = m.add_element("truss", [G2 if name == "K" else G, H], "Stahl", "Q_" + name)
        if name != "K":
            m.add_member(name, [el[name]])
    m.load_cases.pop("LF1", None)
    for lf, last in (("T0", 0.0), ("T0P", P), ("Tinf", 0.0), ("TinfP", P)):
        m.load_cases[lf] = LoadCase(lf, category="P")
        if last:
            m.case(lf).nodal_loads.append(NodalLoad(H, [0.0, 0.0, last, 0.0, 0.0, 0.0]))
        m.case(lf).vorspannzustand = {"*": "0" if lf.startswith("T0") else "inf"}
    m.active_case = "T0"
    if definitionen:
        m.vorspann_definitionen["V1"] = VorspannDefinition("V1", ["A1"], P1, DS1, 1, "absolut", 400e3)
        m.vorspann_definitionen["V2"] = VorspannDefinition("V2", ["A2"], P2, DS2, 2, "absolut", 250e3)
    if plast:
        m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=0.02, laststufen=3, iterationen=60,
                                         toleranz=1e-10)
    return m, H, el


def _N(res, e):
    return float(res.beam_forces[int(e)]["N"][1])


def _st(res, stab):
    return ((res.info.get("vorspannung") or {}).get("staebe") or {}).get(stab, {})


# --------------------------------------------------------------------------
# 1) Handrechnung P₀
# --------------------------------------------------------------------------
def test_handrechnung():
    print("\n--- Handrechnung: P₀ aus P_max, Schlupf und elastischer Verkürzung (Spannfolge 1, 2) ---")
    print(f"     k1 = {K_1 / 1e6:.0f}, k2 = {K_2 / 1e6:.0f}, kK = {K_K / 1e6:.0f} kN/mm; "
          f"P₀,1 = {P0_1 / 1e3:.4f} kN, P₀,2 = {P0_2 / 1e3:.4f} kN")
    for art, kw in (("linear", {}), ("plastisch (nichtlinearer Weg)", {"plast": True})):
        m, H, el = _modell(**kw)
        r = solver.solve_static(m, case="T0")
        nahe(f"{art}: A1 P₀ = N_verankert (Handrechnung)", _st(r, "A1").get("N_verankert"), P0_1, 1e-9, "N")
        nahe(f"{art}: A2 P₀ = N_verankert (Handrechnung)", _st(r, "A2").get("N_verankert"), P0_2, 1e-9, "N")
        nahe(f"{art}: A1 im Ergebnis ohne äußere Last", _N(r, el["A1"]), P0_1, 1e-9, "N")
        nahe(f"{art}: A2 im Ergebnis ohne äußere Last", _N(r, el["A2"]), P0_2, 1e-9, "N")
        nahe(f"{art}: N_spannen von A1 = P_max", _st(r, "A1").get("N_spannen"), P1, 0.0, "N")
        check(f"{art}: Verweise im Ergebnis", (r.info.get("vorspannung") or {}).get("verweise")
              == {"V1": ["0"], "V2": ["0"]}, str((r.info.get("vorspannung") or {}).get("verweise")))
        rP = solver.solve_static(m, case="T0P")
        nahe(f"{art}: mit Zuglast P: Kopf um (P − ΣP₀ + …) – Gleichgewicht ΣN = P",
             _N(rP, el["A1"]) + _N(rP, el["A2"]) + _N(rP, el["K"]), P, 1e-9, "N")
        # dieselbe Eingabe als Anfangsvorspannung im Lastfall: Zahl fuer Zahl gleich
        m2, _H, el2 = _modell(definitionen=False, **kw)
        m2.case("T0").vorspannzustand = {}
        m2.add_vorspannung("A1", P1, case="T0", sollkraft=True, gruppe=1, kraftart="presse", schlupf=DS1)
        m2.add_vorspannung("A2", P2, case="T0", sollkraft=True, gruppe=2, kraftart="presse", schlupf=DS2)
        r2 = solver.solve_static(m2, case="T0")
        check(f"{art}: Verweis rechnet Zahl für Zahl wie die Anfangsvorspannung im Lastfall",
              np.array_equal(np.asarray(r.u), np.asarray(r2.u)) and _N(r, el["A1"]) == _N(r2, el2["A1"]),
              f"max |Δu| {float(np.abs(np.asarray(r.u) - np.asarray(r2.u)).max()):.3g}")


# --------------------------------------------------------------------------
# 2) Zeitpunkt ∞ absolut
# --------------------------------------------------------------------------
def test_unendlich_absolut():
    print("\n--- Zeitpunkt ∞ absolut: jeder Anker trägt P_∞ ---")
    for art, kw in (("linear", {}), ("plastisch", {"plast": True})):
        m, H, el = _modell(**kw)
        r = solver.solve_static(m, case="Tinf")
        nahe(f"{art}: A1 = P_∞ = 400 kN", _N(r, el["A1"]), 400e3, 1e-9, "N")
        nahe(f"{art}: A2 = P_∞ = 250 kN", _N(r, el["A2"]), 250e3, 1e-9, "N")
        check(f"{art}: Verweise ∞ im Ergebnis", (r.info.get("vorspannung") or {}).get("verweise")
              == {"V1": ["inf"], "V2": ["inf"]})
        check(f"{art}: kein P0_basis ohne ΔP_t", "P0_basis" not in _st(r, "A1"))


# --------------------------------------------------------------------------
# 3) ΔP_t: unabhaengig von Reihenfolge
# --------------------------------------------------------------------------
DPT = 30e3


def _reihenfolge(m, folge):
    """Die Lastfaelle in ``folge`` an EINEM System nacheinander (wie solve_cases
    in einem Prozess); Rueckgabe {Name: Ergebnis}."""
    sys_ = solver.StaticSystem(m)
    return {n: solver._solve_loads(m, sys_, {n: 1.0}, n, "case") for n in folge}


def test_verlust_reihenfolge():
    print("\n--- Zeitpunkt ∞ mit ΔP_t: P_∞,i = P₀,i − ΔP_t, unabhängig von der Reihenfolge ---")
    for art, kw in (("linear", {}), ("plastisch", {"plast": True})):
        m, H, el = _modell(**kw)
        m.vorspann_definitionen["V1"].endwert = "verlust"
        m.vorspann_definitionen["V1"].dP_t = DPT
        laeufe = {"∞ allein": _reihenfolge(m, ["Tinf"]),
                  "0 dann ∞": _reihenfolge(m, ["T0", "Tinf"]),
                  "∞ dann 0": _reihenfolge(m, ["Tinf", "T0"])}
        werte = {k: (_st(v["Tinf"], "A1").get("P_inf"), _st(v["Tinf"], "A1").get("P0_basis"))
                 for k, v in laeufe.items()}
        print(f"     {art}: {werte}")
        a = werte["∞ allein"]
        check(f"{art}: P_∞,1 und P₀,1 bitgleich in allen drei Reihenfolgen",
              a[0] is not None and all(w == a for w in werte.values()), str(werte))
        nahe(f"{art}: P₀,1 = Handrechnung", a[1], P0_1, 1e-9, "N")
        nahe(f"{art}: P_∞,1 = P₀,1 − ΔP_t", a[0], P0_1 - DPT, 1e-9, "N")
        for k, v in laeufe.items():
            nahe(f"{art}, {k}: A1 trägt P_∞,1", _N(v["Tinf"], el["A1"]), P0_1 - DPT, 1e-9, "N")
            nahe(f"{art}, {k}: A2 trägt P_∞ = 250 kN (absolut)", _N(v["Tinf"], el["A2"]), 250e3, 1e-9, "N")
        n_inf = [_N(v["Tinf"], el["A1"]) for v in laeufe.values()]
        check(f"{art}: Ankerkraft im Lastfall ∞ in allen Reihenfolgen gleich (≤ 1e-9 relativ)",
              max(n_inf) - min(n_inf) <= 1e-9 * abs(n_inf[0]), str(n_inf))
        n0 = [_N(v["T0"], el["A1"]) for k, v in laeufe.items() if "T0" in v]
        check(f"{art}: Lastfall 0 vor und nach ∞ bitgleich", len(set(n0)) == 1, str(n0))
    # derselbe Weg ueber solve_cases (Pool, wie die Oberflaeche rechnet)
    m, H, el = _modell()
    m.vorspann_definitionen["V1"].endwert = "verlust"
    m.vorspann_definitionen["V1"].dP_t = DPT
    allein = solver.solve_cases(m, ["Tinf"])["Tinf"]
    beide = solver.solve_cases(m, ["T0", "Tinf"])["Tinf"]
    check("solve_cases: P_∞,1 allein und mit dem Lastfall 0 bitgleich",
          _st(allein, "A1").get("P_inf") == _st(beide, "A1").get("P_inf") is not None,
          f"{_st(allein, 'A1').get('P_inf')} / {_st(beide, 'A1').get('P_inf')}")
    # Anzeige beider Werte
    a = vsp.anzeige(m, m.vorspann_definitionen["V1"], {"T0": solver.solve_static(m, case="T0")})
    check("Anzeige: P₀ aus dem Ergebnis T0", "aus dem Ergebnis T0" in a["text_P0"], a["text_P0"])
    check("Anzeige: ΔP_t eingegeben und P_∞ = P₀ − ΔP_t gezeigt",
          "ΔP_t = 30 kN (Eingabe)" in a["text_dP_t"] and "P_∞ = P₀ − ΔP_t" in a["text_P_inf"],
          f"{a['text_dP_t']} | {a['text_P_inf']}")
    a2 = vsp.anzeige(m, m.vorspann_definitionen["V2"])
    check("Anzeige ohne Ergebnis: P₀ geschätzt (starre Umgebung), P_∞ absolut und ΔP_t = P₀ − P_∞",
          a2["P0_geschaetzt"] and "P_∞ = 250 kN (Eingabe, absolut)" == a2["text_P_inf"]
          and "ΔP_t = P₀ − P_∞" in a2["text_dP_t"], f"{a2['text_P0']} | {a2['text_dP_t']}")
    nahe("geschätztes P₀,2 = P_max − k2·Δs2", a2["P0"]["A2"], P2 - K_2 * DS2, 1e-12, "N")


# --------------------------------------------------------------------------
# 4) Speichern und Laden, alte Dateien
# --------------------------------------------------------------------------
def test_speichern_laden():
    print("\n--- Speichern und Laden, alte Dateien bitgleich ---")
    from statik3d import ergebnisse as erg
    from statik3d.model import NEUE_FELDER
    check("NEUE_FELDER: vorspannzustand {} am Lastfall, vorspann_definitionen [] am Modell",
          NEUE_FELDER["load_cases"].get("vorspannzustand", 0) == {}
          and NEUE_FELDER[""].get("vorspann_definitionen", 0) == [])
    tmp = tempfile.mkdtemp()
    try:
        m, H, el = _modell()
        m.vorspann_definitionen["V1"].endwert = "verlust"
        m.vorspann_definitionen["V1"].dP_t = DPT
        p = os.path.join(tmp, "je_anker.json")
        m.save(p)
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        check("Datei: vorspann_definitionen mit V1, V2", [x["name"] for x in d.get("vorspann_definitionen", [])]
              == ["V1", "V2"])
        lcs = d["load_cases"].values() if isinstance(d["load_cases"], dict) else d["load_cases"]
        check("Datei: vorspannzustand an T0 und Tinf",
              {lc["name"]: lc.get("vorspannzustand") for lc in lcs}.get("Tinf") == {"*": "inf"})
        m2 = Model.load(p)
        check("geladen: Definitionen gleich", m2.vorspann_definitionen == m.vorspann_definitionen)
        check("geladen: Verweise gleich", {n: lc.vorspannzustand for n, lc in m2.load_cases.items()}
              == {n: lc.vorspannzustand for n, lc in m.load_cases.items()})
        r1, r2 = solver.solve_static(m, case="Tinf"), solver.solve_static(m2, case="Tinf")
        check("… und rechnet bitgleich", np.array_equal(np.asarray(r1.u), np.asarray(r2.u)))
        # alte Dateien: ohne Felder bitgleich gespeichert
        for rel in (("vorspannung_soll_051007d", "anker_soll.json"),):
            pa = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daten", *rel)
            if not os.path.exists(pa):
                check(f"alte Datei {rel[-1]} vorhanden", False, pa)
                continue
            mb = Model.load(pa)
            pb = os.path.join(tmp, "alt.json")
            mb.save(pb)
            with open(pa, encoding="utf-8") as f1, open(pb, encoding="utf-8") as f2:
                a, b = json.load(f1), json.load(f2)
            check(f"alte Datei {rel[-1]}: ohne vorspann_definitionen und vorspannzustand gespeichert",
                  "vorspann_definitionen" not in b and not any("vorspannzustand" in lc for lc in (
                      b["load_cases"].values() if isinstance(b["load_cases"], dict) else b["load_cases"])))
            check(f"alte Datei {rel[-1]}: Lastfälle gleich wie in der Datei", a["load_cases"] == b["load_cases"])
        # Rechenkennung: ohne Verweis gleich, mit Verweis die Definition darin
        m3, _H, _el = _modell()
        for lc in m3.load_cases.values():
            lc.vorspannzustand = {}
        k_def = erg.rechenkennung(m3)
        m3.vorspann_definitionen.clear()
        k_leer = erg.rechenkennung(m3)
        # wie ein Stand ohne die Felder
        del m3.vorspann_definitionen
        for lc in m3.load_cases.values():
            del lc.vorspannzustand
        k_alt = erg.rechenkennung(m3)
        check("Rechenkennung: leere Felder wie ein Stand ohne sie", k_leer == k_alt)
        check("Rechenkennung: Definitionen ohne Verweis rechnen nirgends mit", k_def == k_alt)
        m4, _H, _el = _modell()
        k1 = erg.rechenkennung(m4)[1]
        m4.vorspann_definitionen["V1"].P_inf = 401e3
        k2 = erg.rechenkennung(m4)[1]
        check("Rechenkennung: P_∞ geändert → Lasten jedes verweisenden Lastfalls geändert",
              all(k1[n][1] != k2[n][1] for n in ("Tinf", "T0")) and all(k1[n][0] == k2[n][0] for n in k1))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 5) Zuordnung
# --------------------------------------------------------------------------
def _alt_modell():
    """Wie eine aus RFEM uebernommene Datei: ΔT 952 kN (LF398 P und Q-Faelle),
    ΔT 805 kN (LF399 P, FAT-Faelle), Endvorspannung 944,7 kN in LF1."""
    m, H, el = _modell(definitionen=False)
    for lc in list(m.load_cases):
        m.load_cases.pop(lc)
    mat = m.materials["Stahl"]

    def dT(N, A):
        return -N / (mat.E * A * mat.alpha)
    faelle = {"LF398": ("P", 952e3), "LF2": ("Q", 952e3), "LF3": ("Q", 952e3),
              "LF399": ("P", 805e3), "LF401": ("FAT", 805e3), "LF13": ("Q", 805e3)}
    for lf, (kat, N) in faelle.items():
        lc = LoadCase(lf, category=kat)
        m.load_cases[lf] = lc
        for s, A in (("A1", A_1), ("A2", A_2)):
            lc.temp_loads.append(TempLoad(el[s], dT(N, A)))
        if lf != "LF398" and lf != "LF399":
            lc.nodal_loads.append(NodalLoad(H, [0.0, 0.0, 1e3, 0.0, 0.0, 0.0]))
    # eine echte Temperaturlast am Klemmteil bleibt, wie sie ist
    m.load_cases["LF2"].temp_loads.append(TempLoad(el["K"], 20.0))
    m.load_cases["LF1"] = LoadCase("LF1", category="Q")
    for s in ("A1", "A2"):
        m.add_vorspannung(s, 944.7e3, case="LF1", sollkraft=True)
    m.active_case = "LF1"
    return m, H, el


def test_zuordnung():
    print("\n--- Zuordnung: Gruppen nach Wert, 952 → 0, 805 → ∞, LF1 bleibt ---")
    m, H, el = _alt_modell()
    vorher_lf1 = json.dumps(m.load_cases["LF1"].to_dict(), sort_keys=True)
    gr = vsp.gruppen_finden(m, linear_rechnen=True)
    for g in gr:
        print(f"     {vsp.gruppe_text(g)}: X {vsp.x_text(g)}")
    by = {(g["art"], round(g["N0"])): g for g in gr}
    g952, g805, g944 = by.get((vsp.ART_DT, 952000)), by.get((vsp.ART_DT, 805000)), by.get((vsp.ART_ENDE, 944700))
    check("drei Gruppen: 952 kN ΔT (3 LF), 805 kN ΔT (3 LF), 944,7 kN Endvorspannung (LF1)",
          len(gr) == 3 and g952 and len(g952["faelle"]) == 3 and g805 and len(g805["faelle"]) == 3
          and g944 and g944["faelle"] == ["LF1"], str([(g["art"], g["N0"], len(g["faelle"])) for g in gr]))
    check("Kategorien je Gruppe gezählt", g805 and g805["kategorien"] == {"P": 1, "FAT": 1, "Q": 1},
          str(g805 and g805["kategorien"]))
    # X: linear gerechnet, gleich der Kraft im Ergebnis des Lastfalls nur mit der Vorspannung
    r398 = solver.solve_static(m, case="LF398")
    x_res = [_N(r398, el[s]) for s in ("A1", "A2")]
    check("X 952 kN: linear = Ergebnis LF398 (je Anker, min/max)",
          g952 and g952["X"] and abs(g952["X"][0] - min(x_res)) < 1e-6 * 952e3
          and abs(g952["X"][1] - max(x_res)) < 1e-6 * 952e3, f"{g952 and g952['X']} / {x_res}")
    gr2 = vsp.gruppen_finden(m, {"LF398": r398})
    g2 = next(g for g in gr2 if round(g["N0"]) == 952000)
    check("X aus dem Ergebnis LF398 ohne lineare Rechnung", "LF398" in g2["X_herkunft"], g2["X_herkunft"])
    check("Vorschlag 0: P_max = Wert der Gruppe; ∞: P_∞ absolut = Wert",
          vsp.vorschlag(g952, "0")["P_max"] == 952e3 and vsp.vorschlag(g805, "inf") ==
          {"endwert": "absolut", "P_inf": 805e3, "dP_t": 0.0})
    # ohne Zuordnung bleibt alles
    vor = json.dumps(m.to_dict(netz=False), sort_keys=True, default=str)
    vsp.zuordnen(m, [{"gruppe": g, "zustand": ""} for g in gr])
    check("ohne Zuordnung: Modell unverändert", json.dumps(m.to_dict(netz=False), sort_keys=True, default=str) == vor)
    # Fehler vor jeder Aenderung
    try:
        vsp.zuordnen(m, [{"gruppe": g952, "zustand": "0", "definition": "V1", "P_max": 0.0}])
        check("P_max 0 im Zeitpunkt 0 abgewiesen", False)
    except ValueError as ex:
        check("P_max 0 im Zeitpunkt 0 abgewiesen, nichts geändert",
              json.dumps(m.to_dict(netz=False), sort_keys=True, default=str) == vor, str(ex))
    erg_ = vsp.zuordnen(m, [
        {"gruppe": g952, "zustand": "0", "definition": "V1", **vsp.vorschlag(g952, "0")},
        {"gruppe": g805, "zustand": "inf", "definition": "V1", **vsp.vorschlag(g805, "inf")},
        {"gruppe": g944, "zustand": ""}])
    print(f"     {erg_}")
    d = m.vorspann_definitionen.get("V1")
    check("Definition V1: A1, A2; P_max 952; P_∞ 805 absolut; Vermerk RFEM",
          d and d.staebe == ["A1", "A2"] and d.P_max == 952e3 and d.P_inf == 805e3 and d.endwert == "absolut"
          and d.herkunft == vsp.VERMERK_RFEM, str(d))
    zst = {n: lc.vorspannzustand for n, lc in m.load_cases.items()}
    check("6 Lastfälle verweisen (3 × 0, 3 × ∞), LF1 nicht",
          erg_["faelle"] == 6 and sum(1 for z in zst.values() if z == {"V1": "0"}) == 3
          and sum(1 for z in zst.values() if z == {"V1": "inf"}) == 3 and zst["LF1"] == {}, str(zst))
    check("LF1 unverändert", json.dumps(m.load_cases["LF1"].to_dict(), sort_keys=True) == vorher_lf1)
    check("ΔT-Vorspannungen entfernt, echte Temperatur am Klemmteil bleibt, Knotenlasten bleiben",
          [t.elem for t in m.load_cases["LF2"].temp_loads] == [el["K"]]
          and not m.load_cases["LF398"].temp_loads and len(m.load_cases["LF2"].nodal_loads) == 1)
    r = solver.solve_static(m, case="LF398")
    nahe("LF398 nach der Zuordnung: Anker tragen P₀ = P_max (gleichzeitig, ohne Schlupf)",
         _N(r, el["A1"]), 952e3, 1e-9, "N")
    r = solver.solve_static(m, case="LF399")
    nahe("LF399 nach der Zuordnung: Anker tragen P_∞ = 805 kN", _N(r, el["A2"]), 805e3, 1e-9, "N")
    check("Zustand je Lastfall zum Lesen", vsp.zustand_lastfall_text(m, m.load_cases["LF401"])
          == "Zeitpunkt ∞ (V1)" and vsp.zustand_lastfall_text(m, m.load_cases["LF1"]) == "keine")
    check("Modellprüfung ohne Befund", vsp.pruefen(m) == [], str(vsp.pruefen(m)))


# --------------------------------------------------------------------------
# 6) Nachweise je Zustand
# --------------------------------------------------------------------------
def _spannanker_modell():
    """Wie _modell, aber die Anker aus Spannstahl 835/1030 mit Nachweis; GZT-
    Kombinationen LK0 (T0P) und LKinf (TinfP), Ermuedung FAT1 im Zeitpunkt 0."""
    from statik3d.model import FatigueLoad
    m, H, el = _modell()
    mat = Material("Spannstahl 835/1030", 170e9, 0.3, 7850.0, 1e-5, 835e6, 1030e6)
    mat.art = "Spannstahl"
    m.add_material(mat)
    for s in ("A1", "A2"):
        m.elements[el[s]].mat = mat.name
        m.members[s].design = True
    m.add_combination("LK0", {"T0P": 1.0}, "ULS")
    m.add_combination("LKinf", {"TinfP": 1.0}, "ULS")
    m.fatigue_loads["FAT1"] = FatigueLoad("FAT1", "T0P", "T0", cycles=1e6)
    return m, H, el


def test_nachweise_je_zustand():
    print("\n--- Nachweise je Zustand ---")
    from statik3d.ec3 import spannstahl as sp_
    from statik3d.ec3.fatigue import vorspannzustand_text
    m, H, el = _spannanker_modell()
    an = solver.solve_all(m, design=True)
    mc = an.design.members["A1"]
    for e in mc.zustaende:
        print(f"        {e['zustand']:20s} {e['quelle'][:90]:90s} N {e['N'] / 1e3:8.2f} kN η {e['util']:.4f}")
    sp = [e for e in mc.zustaende if e["zustand"] == sp_.ZUSTAND_SPANNEN]
    check("Spannen: genau ein Eintrag, aus der Definition V1 mit P_max",
          len(sp) == 1 and sp[0]["combo"] == "V1" and sp[0]["N"] == P1, str([(e["quelle"], e["N"]) for e in sp]))
    ve = [e for e in mc.zustaende if e["zustand"] == sp_.ZUSTAND_VERANKERT]
    check("nach dem Verankern: nur Ergebnisse im Zeitpunkt 0 (T0, T0P), keines aus ∞",
          ve and all(e["combo"] in ("T0", "T0P") for e in ve) and all("t = 0" in e["quelle"] for e in ve),
          str([e["combo"] for e in ve]))
    if ve:
        nahe("nach dem Verankern: N = N_verankert aus T0", max(abs(e["N"]) for e in ve),
             _st(an.cases["T0"], "A1").get("N_verankert"), 1e-12, "N")
    gz = [e for e in mc.zustaende if e["zustand"] == sp_.ZUSTAND_LAST]
    check("GZT: beide Kombinationen, je mit Zustand in der Zeile",
          any("LK0 (Vorspannung t = 0)" == e["quelle"] for e in gz)
          and any("LKinf (Vorspannung t = ∞)" == e["quelle"] for e in gz), str([e["quelle"] for e in gz]))
    check("GZT: die Kombination heißt im Eintrag wie im Modell", {e["combo"] for e in gz} == {"LK0", "LKinf"})
    check("Eingabe am Stab nennt die Definition", "Vorspannung V1: P_max = 500.00 kN" in sp_.eingabe_text(
        m, m.members["A1"]), sp_.eingabe_text(m, m.members["A1"]))
    t = vorspannzustand_text(m)
    check("Ermüdung: Zustand t = 0 erkannt und Hinweis „mit t = ∞ zu führen“",
          "t = 0" in t and "mit t = ∞ zu führen" in t, t)
    m.fatigue_loads["FAT1"].case_max, m.fatigue_loads["FAT1"].case_min = "TinfP", "Tinf"
    check("Ermüdung im Zeitpunkt ∞: ohne Hinweis", vorspannzustand_text(m)
          == "Vorspannung der Anker in den Ermüdungszuständen: t = ∞", vorspannzustand_text(m))
    zeilen = vsp.ergebnis_zeilen(m, an.cases)
    print("     " + "\n     ".join(zeilen))
    check("Ergebniszeile je Definition mit P_max, P₀, P_∞, ΔP_t",
          zeilen and all(k in zeilen[0] for k in ("P_max = 500 kN", "P₀ = ", "P_∞ = 400 kN", "ΔP_t = P₀ − P_∞")))
    check("Zustand je Nachweis: Klaffen/Gleiten/Passstifte t = ∞, als noch nicht im Programm",
          "Klaffen der Fuge mit t = ∞ (Nachweis noch nicht im Programm)" in zeilen[-1], zeilen[-1])
    check("Nachweise EC3: Zusammenfassung nennt die Definitionen", "Vorspannung V1" in an.design.summary())
    zs = an.summary()
    check("Zusammenfassung der Rechnung: Zeitpunkte je Definition",
          "Vorspannung je Anker V1: Zeitpunkt 0 in 3, Zeitpunkt ∞ in 3 Ergebnissen gerechnet" in zs,
          [z for z in zs.splitlines() if "je Anker" in z])
    # ohne Ergebnis im Zeitpunkt 0: P₀ gegen starre Umgebung
    m2, _H, _el = _spannanker_modell()
    for n in ("T0", "T0P"):
        m2.load_cases.pop(n)
    m2.combinations.pop("LK0")
    m2.fatigue_loads.clear()
    an2 = solver.solve_all(m2, design=True)
    ve2 = [e for e in an2.design.members["A1"].zustaende if e["zustand"] == sp_.ZUSTAND_VERANKERT]
    check("ohne Lastfall im Zeitpunkt 0: nach dem Verankern P_max − k_A·Δs mit Vermerk",
          len(ve2) == 1 and "starre Umgebung" in ve2[0]["quelle"], str([e["quelle"] for e in ve2]))
    if ve2:
        k_A = 170e9 * A_1 / L
        nahe("… N = P_max − k_A·Δs", ve2[0]["N"], P1 - k_A * DS1, 1e-12, "N")


def test_norm_grenze():
    print("\n--- σ_pm0 nach EN 1992-1-1, 5.10.3(2): min(0,75·f_pk; 0,85·f_p0,1k) ---")
    from statik3d.ec3 import spannstahl as sp_
    mat = Material("St 835/1030", 170e9, 0.3, 7850.0, 1e-5, 835e6, 1030e6)
    g, her = sp_.sigma_pm0(mat)
    nahe("Drehlager 835/1030: σ_pm0 = 0,85·835 = 709,75 N/mm² (0,75·1030 = 772,5)", g, 709.75e6, 1e-12)
    mat2 = Material("Y1860", 195e9, 0.3, 7850.0, 1e-5, 1600e6, 1860e6)
    g2, _h = sp_.sigma_pm0(mat2)
    nahe("Litze 1600/1860: σ_pm0 = min(1395; 1360) = 1360 N/mm² (0,85·f_p0,1k)", g2, 1360e6, 1e-12)
    mat3 = Material("St 1080/1230", 205e9, 0.3, 7850.0, 1e-5, 1080e6, 1230e6)
    g3, _h = sp_.sigma_pm0(mat3)
    nahe("St 1080/1230: σ_pm0 = min(922,5; 918) = 918 N/mm²", g3, 918e6, 1e-12)
    mat4 = Material("fiktiv 900/1000", 205e9, 0.3, 7850.0, 1e-5, 900e6, 1000e6)
    g4, _h = sp_.sigma_pm0(mat4)
    nahe("f_pk/f_p0,1k < 1,133: 0,75·f_pk maßgebend (750 statt 765)", g4, 750e6, 1e-12)


def main():
    for t in (test_handrechnung, test_unendlich_absolut, test_verlust_reihenfolge, test_speichern_laden,
              test_zuordnung, test_nachweise_je_zustand, test_norm_grenze):
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {type(ex).__name__}: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    sys.exit(main())
