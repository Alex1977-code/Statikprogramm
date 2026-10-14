"""Vorspannkraft (Soll nach Verankerung): Spannen, Verriegeln, Lasten.

Entscheidung des Anwenders vom 13.10.2026: „Vorspannung kraftgesteuert
eingeben. Neue Lastart „Vorspannkraft (Soll nach Verankerung)“ je Stab.
Umsetzung als eigener Spannschritt vor den übrigen Lasten: Im Spannschritt
wirkt der Stab als Kräftepaar F_soll an beiden Enden (Stabsteifigkeit
inaktiv). Danach wird der Stab in der verformten Lage mit Normalkraft F_soll
aktiviert (Verriegeln), anschließend folgen die äußeren Lasten.“ Bis dahin
kannte das Programm nur die Vorspannung als Anfangsdehnung (eps0 = -F/(EA),
im Stab, als Koerper, oder aus RFEM als Abkuehlung): der Stab traegt danach
nicht F, sondern F minus die elastische Verkuerzung der Umgebung - am
Drehlager 782 bis 833 statt 952 kN.

Geprueft mit geschlossenen Loesungen:

* Ein Anker (k_A) und ein Klemmteil (k_K) zwischen Boden und Kopf: nach dem
  Verriegeln N = F_soll, mit einer aeusseren Zuglast P am Kopf
  N = F_soll + k_A/(k_A + k_K)·P (Verspannungsschaubild). Linear ueber die
  Einflussmatrix und nichtlinear ueber Spannen und Verriegeln.
* Reihenweise zwei Anker: der erste verliert k_1 F_2/(k_K + k_1).
* Die Einflussmatrix gibt dasselbe wie Spannen und Verriegeln, wenn
  gleichzeitig gespannt wird (Wuerfel mit vier ungleichen Ankern).
* Plastisch: der Wuerfel fliesst im Spannschritt (σ = 4 F/A > f_y); nach dem
  Verriegeln N = F_soll, eine Zuglast entlastet ihn elastisch vom
  Spannzustand aus.
* Kontakt: das Klemmteil ueber ein Spaltelement - die Fuge oeffnet bei
  P = F (k_A + k_K)/k_K, danach traegt der Anker P allein.
* Speichern und Laden; alte Dateien behalten ihre Form.
* Hinweis beim RFEM-Import und Umwandlung der Temperatur-Vorspannung.

Aufruf:  python -m tests.test_vorspannkraft
"""
import json
import os
import shutil
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import plastizitaet as pl, solver                    # noqa: E402
from statik3d.model import Material, Model, NodalLoad, Section    # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:80s} {detail}")
    return ok


def nahe(name, ist, soll, tol, einheit=""):
    ist, soll = float(ist), float(soll)
    abw = abs(ist - soll) / (abs(soll) if abs(soll) > 1e-14 else 1.0)
    return check(name, abw <= tol, f"ist {ist:.9g} soll {soll:.9g} ({abw:.2e}) {einheit}")


E = 210e9
L = 1.0
A_A = 1e-3                  # Anker [m2]   -> k_A = 2,1e8 N/m
A_A2 = 2e-3                 # zweiter Anker -> k_2 = 4,2e8 N/m
A_K = 4e-3                  # Klemmteil    -> k_K = 8,4e8 N/m
K_A, K_A2, K_K = E * A_A / L, E * A_A2 / L, E * A_K / L
F1, F2 = 500e3, 300e3       # Sollkraefte [N]
P = 200e3                   # aeussere Zuglast am Kopf [N]


def _vk():
    from statik3d import vorspannkraft
    return vorspannkraft


def _querschnitt(m, name, A):
    m.add_section(Section.circle(name, float(np.sqrt(4.0 * A / np.pi))))


def _federn(anker=(("A1", A_A, F1, 1),), plast=False, kontakt=False, alt=False, lasten=(("V", 0.0),
                                                                                       ("VP", P))):
    """Boden G, Kopf H; je Anker ein Fachwerkstab G-H, das Klemmteil ein
    Fachwerkstab G'-H (bzw. G'-B mit Spaltelement B-H). ``alt``: dieselbe Kraft
    als Anfangsdehnung (bisherige Lastart). Rueckgabe (Modell, Kopf, Elemente
    der Anker, Element des Klemmteils)."""
    m = Model("Anker und Klemmteil")
    m.add_material(Material("Stahl", E=E, nu=0.3, rho=7850, alpha=1e-5))
    G = m.add_node(0.0, 0.0, 0.0)
    G2 = m.add_node(0.0, 0.0, 0.0)
    H = m.add_node(0.0, 0.0, L)
    m.fix(G, "all")
    m.fix(G2, "all")
    m.fix(H, [0, 1, 3, 4, 5])
    elem = {}
    for name, A, _F, _g in anker:
        _querschnitt(m, "Q_" + name, A)
        e = m.add_element("truss", [G, H], "Stahl", "Q_" + name)
        m.add_member(name, [e])
        elem[name] = e
    _querschnitt(m, "Q_K", A_K)
    if kontakt:
        B = m.add_node(0.0, 0.0, L)
        m.fix(B, [0, 1, 3, 4, 5])
        eK = m.add_element("truss", [G2, B], "Stahl", "Q_K")
        m.add_gap_element(B, H, direction=[0.0, 0.0, 1.0])
    else:
        eK = m.add_element("truss", [G2, H], "Stahl", "Q_K")
    for lf, last in lasten:
        m.add_load_case(lf).gravity = [0.0, 0.0, 0.0]
        for name, _A, Fs, g in anker:
            if alt:
                m.add_vorspannung(name, Fs, case=lf)
            else:
                m.add_vorspannung(name, Fs, case=lf, sollkraft=True, gruppe=g)
        if last:
            m.case(lf).nodal_loads.append(NodalLoad(H, [0.0, 0.0, last, 0.0, 0.0, 0.0]))
    if plast:
        m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=0.02, laststufen=3, iterationen=60,
                                         toleranz=1e-10)
    return m, H, elem, eK


def _N(res, e):
    """Normalkraft (Zug positiv) am Stabende - wie Tabelle und Nachweis sie lesen."""
    return float(res.beam_forces[int(e)]["N"][1])


def _rechne(m, lf):
    return solver.solve_static(m, case=lf)


# --------------------------------------------------------------------------
def test_feder_linear():
    print("\n--- Anker und Klemmteil, linear (Einflussmatrix) ---")
    m, H, el, eK = _federn()
    r = _rechne(m, "V")
    vs = r.info.get("vorspannung") or {}
    check("linear: gerechnet über die Einflussmatrix (eingeprägte Dehnung je Stab)",
          vs.get("weg") == "einflussmatrix", str(vs.get("weg")))
    nahe("nur Vorspannung: N = F_soll nach dem Verriegeln", _N(r, el["A1"]), F1, 1e-9, "N")
    nahe("… das Klemmteil drückt mit F_soll", _N(r, eK), -F1, 1e-9, "N")
    nahe("… Kopf um F_soll/k_K gesenkt", r.u[H, 2], -F1 / K_K, 1e-9, "m")
    r2 = _rechne(m, "VP")
    nahe("mit Zuglast P: N = F_soll + k_A/(k_A + k_K)·P", _N(r2, el["A1"]),
         F1 + K_A / (K_A + K_K) * P, 1e-9, "N")
    st = (r2.info.get("vorspannung") or {}).get("staebe", {}).get("A1", {})
    nahe("res.info: N_verankert = F_soll", st.get("N_verankert", 0.0), F1, 1e-9, "N")
    nahe("res.info: N_ende = Stabkraft unter allen Lasten", st.get("N_ende", 0.0),
         F1 + K_A / (K_A + K_K) * P, 1e-9, "N")
    ma, _H, ela, _eK = _federn(alt=True)
    ra = _rechne(ma, "V")
    nahe("zum Vergleich die bisherige Lastart (Anfangsdehnung): N = F·k_K/(k_K + k_A)",
         _N(ra, ela["A1"]), F1 * K_K / (K_K + K_A), 1e-9, "N")


def test_feder_spannweg():
    print("\n--- Anker und Klemmteil, Spannen und Verriegeln (nichtlineare Rechnung) ---")
    m, H, el, eK = _federn(plast=True)
    r = _rechne(m, "V")
    vs = r.info.get("vorspannung") or {}
    check("nichtlinear: Spannen und Verriegeln", vs.get("weg") == "spannen und verriegeln",
          str(vs.get("weg")))
    st = (vs.get("staebe") or {}).get("A1", {})
    nahe("Spannschritt: N = F_soll (Kräftepaar)", st.get("N_spannen", 0.0), F1, 1e-12, "N")
    nahe("verankert: N = F_soll", st.get("N_verankert", 0.0), F1, 1e-9, "N")
    nahe("Ende ohne weitere Last: N = F_soll", _N(r, el["A1"]), F1, 1e-9, "N")
    nahe("… Kopf um F_soll/k_K gesenkt (Gleichgewichtslage des Spannschritts)", r.u[H, 2],
         -F1 / K_K, 1e-9, "m")
    zs = getattr(r, "vorspannzustaende", None) or {}
    sp = (zs.get("spannen") or [None])[-1]
    va = zs.get("verankert")
    check("Zustände abgelegt: „spannen“ und „verankert“ mit res.info['zustand']",
          sp is not None and va is not None and sp.info.get("zustand") == "spannen"
          and va.info.get("zustand") == "verankert",
          f"{sp and sp.info.get('zustand')}, {va and va.info.get('zustand')}")
    if sp is not None and va is not None:
        nahe("… im Spannzustand ist N = F_soll ablesbar", _N(sp, el["A1"]), F1, 1e-12, "N")
        nahe("… im verankerten Zustand N = F_soll", _N(va, el["A1"]), F1, 1e-9, "N")
        du = float(np.abs(np.asarray(va.u) - np.asarray(sp.u)).max())
        check("… Verriegeln ändert die Gleichgewichtslage nicht (u gleich)", du == 0.0, f"max |Δu| {du:.2e} m")
        dr = float(np.abs(np.asarray(r.u) - np.asarray(va.u)).max())
        check("… und die Rechnung danach bleibt ohne Last in ihr", dr <= 1e-12 * F1 / K_K,
              f"max |Δu| {dr:.2e} m")
    r2 = _rechne(m, "VP")
    nahe("mit Zuglast P: N = F_soll + k_A/(k_A + k_K)·P", _N(r2, el["A1"]),
         F1 + K_A / (K_A + K_K) * P, 1e-9, "N")


def test_reihenweise():
    print("\n--- Reihenweise: zwei Anker nacheinander ---")
    anker = (("A1", A_A, F1, 1), ("A2", A_A2, F2, 2))
    verlust = K_A * F2 / (K_K + K_A)
    for plast in (False, True):
        was = "nichtlinear" if plast else "linear"
        m, H, el, eK = _federn(anker=anker, plast=plast)
        r = _rechne(m, "V")
        vs = r.info.get("vorspannung") or {}
        check(f"{was}: reihenweise heißt Spannen und Verriegeln, Gruppe für Gruppe",
              vs.get("weg") == "spannen und verriegeln" and vs.get("reihenfolge") == [["A1"], ["A2"]],
              f"{vs.get('weg')}, {vs.get('reihenfolge')}")
        nahe(f"{was}: A1 verliert k_1 F_2/(k_K + k_1)", (vs.get("staebe") or {}).get("A1", {}).get("verlust", 0.0),
             verlust, 1e-9, "N")
        nahe(f"{was}: A1 nach dem Verankern F_1 − Verlust", _N(r, el["A1"]), F1 - verlust, 1e-9, "N")
        nahe(f"{was}: A2 (zuletzt gespannt) behält F_2", _N(r, el["A2"]), F2, 1e-9, "N")
        check(f"{was}: A2 ohne Verlust", abs((vs.get("staebe") or {}).get("A2", {}).get("verlust", 1.0)) <= 1e-9 * F2,
              str((vs.get("staebe") or {}).get("A2")))
        r2 = _rechne(m, "VP")
        kg = K_A + K_A2 + K_K
        nahe(f"{was}: mit P: A1 = F_1 − Verlust + k_1/Σk·P", _N(r2, el["A1"]), F1 - verlust + K_A / kg * P,
             1e-9, "N")
        nahe(f"{was}: mit P: A2 = F_2 + k_2/Σk·P", _N(r2, el["A2"]), F2 + K_A2 / kg * P, 1e-9, "N")
    m, H, el, eK = _federn(anker=(("A1", A_A, F1, 1), ("A2", A_A2, F2, 1)))
    r = _rechne(m, "V")
    check("gleichzeitig (eine Gruppe): beide behalten ihre Sollkraft",
          abs(_N(r, el["A1"]) - F1) <= 1e-9 * F1 and abs(_N(r, el["A2"]) - F2) <= 1e-9 * F2,
          f"{_N(r, el['A1']):.6g}, {_N(r, el['A2']):.6g} N")


# --------------------------------------------------------------------------
# Wuerfel mit vier Ankern (wie tests/test_vorspannung_sofort.py)
# --------------------------------------------------------------------------
NU, FY, ET = 0.3, 355e6, 0.02
AB, LB = 0.05, 2.0          # Ankerquerschnitt [m2], Ankerlaenge [m]


def _wuerfel(kraefte=(100e6,) * 4, flaechen=(AB,) * 4, plast=True, P_kopf=0.0):
    m = Model("Würfel mit Ankern")
    m.add_material(Material("S355", E=E, nu=NU, rho=7850, fy=FY))
    m.add_material(Material("Anker", E=E, nu=NU, rho=7850, alpha=1e-5))
    n = [m.add_node(x, y, z) for z in (0.0, 1.0) for x, y in ((0, 0), (1, 0), (1, 1), (0, 1))]
    m.add_element("hex8", n, "S355", "")
    for i in n[:4]:
        m.fix(i, [2])
    m.fix(n[0], [0, 1])
    m.fix(n[1], [1])
    m.fix(n[3], [0])
    boden = [m.add_node(x, y, -1.0) for x, y in ((0, 0), (1, 0), (1, 1), (0, 1))]
    anker = []
    for k, (b, t, A) in enumerate(zip(boden, n[4:], flaechen), start=1):
        m.fix(b, "all")
        _querschnitt(m, f"D{k}", A)
        anker.append(m.add_element("truss", [b, t], "Anker", f"D{k}"))
        m.add_member(f"A{k}", [anker[-1]])
    for lf in ("V", "VP"):
        m.add_load_case(lf).gravity = [0, 0, 0]
        for k, F in enumerate(kraefte, start=1):
            m.add_vorspannung(f"A{k}", F, case=lf, sollkraft=True)
    for i, f in zip(n[4:], (1.0, 0.7, 1.3, 1.0)):
        m.case("VP").nodal_loads.append(NodalLoad(i, [0, 0, P_kopf * f / 4.0, 0, 0, 0]))
    if plast:
        m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=ET, laststufen=3, iterationen=60,
                                         toleranz=1e-10)
    return m, n[4:], anker


def test_einfluss_gleich_spannweg():
    print("\n--- Einflussmatrix = Spannen und Verriegeln (gleichzeitig, linear) ---")
    vk = _vk()
    kraefte = (40e6, 70e6, 55e6, 90e6)
    flaechen = (0.03, 0.05, 0.08, 0.04)
    ergebnisse = {}
    alt = vk.LINEAR_WEG
    try:
        for weg in ("einflussmatrix", "spannen und verriegeln"):
            vk.LINEAR_WEG = weg
            m, kopf, anker = _wuerfel(kraefte, flaechen, plast=False, P_kopf=60e6)
            ergebnisse[weg] = (_rechne(m, "V"), _rechne(m, "VP"), anker)
    finally:
        vk.LINEAR_WEG = alt
    (rv_e, rp_e, anker), (rv_s, rp_s, _a) = ergebnisse["einflussmatrix"], ergebnisse["spannen und verriegeln"]
    check("beide Wege gerechnet, wie gewählt",
          rv_e.info["vorspannung"]["weg"] == "einflussmatrix"
          and rv_s.info["vorspannung"]["weg"] == "spannen und verriegeln",
          f"{rv_e.info['vorspannung']['weg']} / {rv_s.info['vorspannung']['weg']}")
    for was, a, b in (("nur Vorspannung", rv_e, rv_s), ("mit Last", rp_e, rp_s)):
        du = float(np.abs(np.asarray(a.u) - np.asarray(b.u)).max())
        um = float(np.abs(np.asarray(b.u)).max())
        check(f"{was}: Verschiebungen gleich", du <= 1e-9 * um, f"max |Δu| {du:.2e} von {um:.3e} m")
        dN = max(abs(_N(a, e) - _N(b, e)) for e in anker)
        check(f"{was}: Ankerkräfte gleich", dN <= 1e-9 * max(kraefte), f"max |ΔN| {dN:.2e} N")
        ds = float(np.abs(np.asarray(a.solid_res[0]) - np.asarray(b.solid_res[0])).max())
        check(f"{was}: Spannung im Würfel gleich", ds <= 1e-9 * max(kraefte), f"max |Δσ| {ds:.2e} Pa")
    dN = max(abs(_N(rv_e, e) - F) for e, F in zip(anker, kraefte))
    check("nur Vorspannung: jeder Anker trägt seine Sollkraft", dN <= 1e-9 * max(kraefte),
          f"max |N − F_soll| {dN:.2e} N")


def test_plastisch():
    print("\n--- Plastisch: der Würfel fließt im Spannschritt ---")
    F = 100e6
    Pz = 100e6
    m, kopf, anker = _wuerfel((F,) * 4, plast=True, P_kopf=0.0)
    for i in kopf:
        m.case("VP").nodal_loads.append(NodalLoad(i, [0, 0, Pz / 4.0, 0, 0, 0]))
    r = _rechne(m, "V")
    zs = getattr(r, "vorspannzustaende", None) or {}
    sp = (zs.get("spannen") or [None])[-1]
    Et = ET * E
    eps = FY / E + (4 * F - FY) / Et
    if sp is not None:
        pz = sp.info.get("plastizitaet") or {}
        check("Spannschritt: der Würfel fließt (σ = 4F/A = 400 N/mm² > f_y), konvergiert",
              pz.get("konvergiert") and pz.get("fliessend") == 1, str({k: pz.get(k) for k in ("konvergiert", "fliessend")}))
        nahe("Spannschritt: σ_zz = −4F/A", np.asarray(sp.solid_res[0])[2], -4 * F, 1e-8, "Pa")
        nahe("Spannschritt: Kopf um (f_y/E + (σ − f_y)/E_t)·L gesenkt", np.asarray(sp.u)[kopf, 2].mean(),
             -eps, 1e-8, "m")
    else:
        check("Spannschritt abgelegt", False)
    vs = r.info.get("vorspannung") or {}
    for k, e in enumerate(anker, start=1):
        nahe(f"A{k}: nach dem Verriegeln N = F_soll", (vs.get("staebe") or {}).get(f"A{k}", {}).get("N_verankert", 0.0),
             F, 1e-9, "N")
    nahe("ohne weitere Last bleibt N = F_soll", _N(r, anker[0]), F, 1e-9, "N")
    r2 = _rechne(m, "VP")
    k1 = E * AB / LB
    dw = Pz / (E * 1.0 / 1.0 + 4 * k1)          # der Wuerfel entlastet elastisch
    nahe("Zuglast: der Würfel entlastet elastisch vom Spannzustand aus, N = F + k_1·Δw",
         _N(r2, anker[0]), F + k1 * dw, 1e-7, "N")
    nahe("… σ_zz = −4F/A + E·Δw", np.asarray(r2.solid_res[0])[2], -4 * F + E * dw, 1e-7, "Pa")
    pz = r2.info.get("plastizitaet") or {}
    nahe("… ε_p bleibt die des Spannschritts", pz.get("eps_p_max", 0.0),
         (4 * F - FY) / (E * ET / (1 - ET)), 1e-7)


def test_kontakt():
    print("\n--- Kontakt: Klemmteil über ein Spaltelement ---")
    P_auf = F1 * (K_A + K_K) / K_K
    m, H, el, eK = _federn(kontakt=True, lasten=(("V", 0.0), ("VP", P), ("VQ", 1.6 * P_auf)))
    r = _rechne(m, "V")
    check("mit Kontakt: Spannen und Verriegeln",
          (r.info.get("vorspannung") or {}).get("weg") == "spannen und verriegeln",
          str((r.info.get("vorspannung") or {}).get("weg")))
    nahe("nur Vorspannung: N = F_soll", _N(r, el["A1"]), F1, 1e-9, "N")
    nahe("… das Klemmteil drückt mit F_soll", _N(r, eK), -F1, 1e-9, "N")
    r2 = _rechne(m, "VP")
    nahe("Fuge geschlossen: N = F_soll + k_A/(k_A + k_K)·P", _N(r2, el["A1"]),
         F1 + K_A / (K_A + K_K) * P, 1e-9, "N")
    r3 = _rechne(m, "VQ")
    nahe(f"P = 1,6 × {P_auf / 1e3:.0f} kN: die Fuge ist offen, der Anker trägt P allein",
         _N(r3, el["A1"]), 1.6 * P_auf, 1e-9, "N")


# --------------------------------------------------------------------------
def test_speichern_laden():
    print("\n--- Speichern und Laden ---")
    tmp = tempfile.mkdtemp()
    try:
        m, H, el, eK = _federn(anker=(("A1", A_A, F1, 1), ("A2", A_A2, F2, 2)))
        p = os.path.join(tmp, "soll.json")
        m.save(p)
        m2 = Model.load(p)
        v = m2.case("V").vorspannungen
        check("Sollkraft und Gruppe überleben Speichern und Laden",
              [(x.ziel, x.art, x.kraft, x.sollkraft, x.gruppe) for x in v]
              == [("A1", "stab", F1, True, 1), ("A2", "stab", F2, True, 2)],
              str([(x.ziel, x.kraft, getattr(x, "sollkraft", None), getattr(x, "gruppe", None)) for x in v]))
        r1, r2 = _rechne(m, "V"), _rechne(m2, "V")
        check("… und rechnen gleich", float(np.abs(np.asarray(r1.u) - np.asarray(r2.u)).max()) == 0.0)
        # Gespeichert am Stand 192317a (vor der Sollkraft): ein Anker mit
        # Vorspannkraft als Anfangsdehnung und der RFEM-Form dT = -445,634 K
        pa = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daten",
                          "vorspannung_alt_192317a", "anker_dT_und_Fv.json")
        with open(pa, encoding="utf-8") as f:
            d = json.load(f)
        lcs = d["load_cases"].values() if isinstance(d.get("load_cases"), dict) else d["load_cases"]
        vs = [x for lc in lcs for x in lc.get("vorspannungen", [])]
        mb = Model.load(pa)
        vb = mb.case("V").vorspannungen
        check("alte Datei: Anfangsdehnung bleibt Anfangsdehnung, ΔT bleibt ΔT",
              vs and len(vb) == 1 and not vb[0].sollkraft and len(mb.case("V").temp_loads) == 1,
              f"{[(x.ziel, x.kraft, x.sollkraft) for x in vb]}, ΔT {len(mb.case('V').temp_loads)}")
        pb = os.path.join(tmp, "alt_neu.json")
        mb.save(pb)
        with open(pa, "rb") as f1, open(pb, "rb") as f2:
            a, b = f1.read(), f2.read()
        check("alte Datei mit ΔT-Vorspannung: Laden und Speichern bitgleich", a == b,
              f"{len(a)} / {len(b)} Byte")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_import_hinweis_und_umwandlung():
    print("\n--- RFEM-Import: Hinweis und Umwandlung ---")
    from tests.test_rfem6 import INF, make_rf6
    from statik3d.importers import rfem6_db as R6
    vk = _vk()
    tmp = tempfile.mkdtemp()
    try:
        f = make_rf6(os.path.join(tmp, "anker.rf6"),
                     nodes=[(0, 0, 0), (4, 0, 0), (8, 0, 0), (12, 0, 0)],
                     lines=[[1, 2], [2, 3], [3, 4]],
                     members=[(1, None, None, "MemberImplTension"), (2, None, None, "MemberImplTension"),
                              (3, None, None, "MemberImplTension")],
                     supports=[("Fest", (INF,) * 6, (0,) * 6, None, [1, 4])],
                     load_cases=[("Vorspannung", 1, 0.0)],
                     prestress=[(1, [1], 120e3)])
        log = []
        m = R6.read_rf6(f, log=log)
        lf = next(iter(m.load_cases))
        zeilen = [z.strip() for z in log if "Anfangsvorspannung" in z]
        # Zugstaebe wie die Anker am Drehlager (RFEM MemberImplTension). Stab 1
        # zieht gegen die Staebe 2 und 3 in Reihe (gleiches E A): N = N_0/3
        soll = "Anfangsvorspannung 120 kN ergibt nach elastischer Verkürzung 40 kN – in Sollkraft umwandeln?"
        check("Importprotokoll: der Hinweis mit X (linear, Einflussmatrix)",
              any(soll in z for z in zeilen), str(zeilen[:2]))
        h = [x for x in (m.importhinweise or []) if x.get("art") == "vorspannung"]
        check("… und als Importhinweis am Modell, mit den Stäben",
              len(h) == 1 and soll in h[0].get("text", "") and h[0].get("objekte"),
              str(h)[:200])
        tl = m.case(lf).temp_loads
        mat = m.materials[m.elements[tl[0].elem].mat] if tl else None
        text = tl[0].bezug(m) if tl else ""
        # seit der Zusammenfuehrung (14.10.2026) in der Form des Imports
        # (TempLoad.vorspann_text); bis dahin „aus Vorspannung 120 kN, E = …“
        check("ΔT-Last zeigt die Kraft mit E und α der Umrechnung",
              mat is not None and "Vorspannung 120 kN (eingeprägte Dehnung, E = 210 000 N/mm², "
              "α = 1,2e-5 1/K)" in text, text)
        n = vk.in_sollkraft_umwandeln(m)
        v = m.case(lf).vorspannungen
        check("Umwandlung: ΔT weg, Lastart Sollkraft mit dem RFEM-Wert (kein Spannstahl)",
              n == 1 and not m.case(lf).temp_loads and len(v) == 1 and v[0].sollkraft
              and abs(v[0].kraft - 120e3) < 1e-6,
              f"{n} umgewandelt, ΔT {len(m.case(lf).temp_loads)}, {[(x.ziel, x.kraft, x.sollkraft) for x in v]}")
        r = solver.solve_static(m, case=lf)
        stab = v[0].ziel if v else ""
        e = m.members[stab].elements[0] if stab in m.members else 0
        nahe("… danach trägt der Stab die Sollkraft", _N(r, e), 120e3, 1e-9, "N")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_hinweis_nach_rechnung():
    print("\n--- Hinweis mit Kontakt: X folgt nach der ersten Rechnung ---")
    vk = _vk()
    m, H, el, eK = _federn(kontakt=True, lasten=(("V", 0.0), ("VP", P)))
    for lf in ("V", "VP"):                     # die RFEM-Form: dT statt Sollkraft
        m.case(lf).vorspannungen = []
        m.load_temp(el["A1"], -F1 / (E * A_A * 1e-5), case=lf)
    h = vk.import_hinweise(m)
    check("mit Kontakt: X beim Import nicht gerechnet, der Hinweis sagt warum",
          len(h) == 1 and h[0]["X"] is None and "folgt nach der ersten Rechnung" in h[0]["text"]
          and "Kontakt" in h[0]["text"], h[0]["text"] if h else "kein Hinweis")
    an = solver.solve_all(m, combinations=False)
    h = [x for x in m.importhinweise if x.get("art") == "vorspannung"]
    soll = vk.hinweis_text(F1, F1 * K_K / (K_K + K_A))
    check("nach der Rechnung: X aus dem Lastfall nur mit Vorspannung (V), nicht aus VP",
          h and h[0]["X"] is not None and h[0]["text"].startswith(soll) and h[0].get("X_aus") == ["V"],
          h[0]["text"] if h else "")
    nahe("… X = F·k_K/(k_K + k_A) (Fuge geschlossen)", (h[0]["X"] or [0])[0] if h else 0.0,
         F1 * K_K / (K_K + K_A), 1e-9, "N")


def _rahmen_th():
    """Kragstuetze (HEB 200, 3 m) mit vorgespanntem Zugband zum Boden (wie
    tests/test_vorspannung_sofort._rahmen), hier mit Sollkraft 70 kN; V nur
    Vorspannung, LF1 mit Kopflast."""
    m = Model("Th2/Th3")
    m.add_material(Material("S355", E=E, nu=NU, rho=7850, fy=FY, alpha=1.2e-5))
    m.add_section(Section.from_profile("HEB 200"))
    m.add_section(Section.circle("D", 0.03))
    a = m.add_node(0.0, 0.0, 0.0)
    b = m.add_node(0.0, 0.0, 3.0)
    c = m.add_node(2.0, 0.0, 0.0)
    m.fix(a, "all")
    m.fix(c, "all")
    m.add_element("beam", [a, b], "S355", "HEB 200")
    band = m.add_element("truss", [c, b], "S355", "D")
    m.add_member("Band", [band])
    for lf in ("V", "LF1"):
        m.add_load_case(lf).gravity = [0, 0, 0]
        m.add_vorspannung("Band", 70e3, case=lf, sollkraft=True)
    m.case("LF1").nodal_loads.append(NodalLoad(b, [20e3, 5e3, -400e3, 0, 0, 0]))
    return m, band


def test_theorie():
    print("\n--- Theorie II. und III. Ordnung: bleibt nach Theorie I. Ordnung, gekennzeichnet ---")
    for th in ("II", "III"):
        m, band = _rahmen_th()
        m.case("V").theorie = th
        an = solver.solve_all(m, combinations=False)
        r = an.cases["V"]
        check(f"Theorie {th} verlangt: das Ergebnis bleibt nach Theorie I. Ordnung und sagt es",
              r.info.get("theorie") == "I" and r.info.get("theorie_gewuenscht") == th
              and "Vorspannkraft (Soll nach Verankerung)" in str(r.info.get("theorie_fehler", "")),
              f"{r.info.get('theorie')}, {r.info.get('theorie_gewuenscht')}: {str(r.info.get('theorie_fehler'))[:90]}")
        nahe(f"Theorie {th} verlangt: N = F_soll nach Theorie I. Ordnung", _N(r, band), 70e3, 1e-9, "N")
        mo, bo = _rahmen_th()
        for lc in mo.load_cases.values():
            for v in lc.vorspannungen:
                v.sollkraft = False
        mo.case("V").theorie = th
        ro = solver.solve_all(mo, combinations=False).cases["V"]
        check(f"Theorie {th} mit Anfangsdehnung: wird wie bisher gerechnet",
              ro.info.get("theorie_gewuenscht") is None and "theorie_fehler" not in ro.info,
              f"{ro.info.get('theorie')}")


def test_ohne_sollkraft_unveraendert():
    print("\n--- Ohne Sollkraft rechnet alles wie bisher ---")
    ma, _H, ela, _eK = _federn(alt=True)
    r = _rechne(ma, "VP")
    check("ohne Sollkraft kein Eintrag „vorspannung“", "vorspannung" not in r.info)
    nahe("Anfangsdehnung unverändert: N = (F k_K + k_A P)/(k_A + k_K)", _N(r, ela["A1"]),
         (F1 * K_K + K_A * P) / (K_A + K_K), 1e-9, "N")


def main():
    for t in (test_feder_linear, test_feder_spannweg, test_reihenweise, test_einfluss_gleich_spannweg,
              test_plastisch, test_kontakt, test_speichern_laden, test_import_hinweis_und_umwandlung,
              test_hinweis_nach_rechnung, test_theorie, test_ohne_sollkraft_unveraendert):
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
