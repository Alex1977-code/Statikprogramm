"""Anfangsvorspannung (Pressenkraft P0) mit Verankerungsschlupf (seit 14.10.2026).

Vorgabe des Anwenders vom 14.10.2026: „Bitte im Spannschritt wahlweise
„Pressenkraft + Verankerungsschlupf (mm)“ ermöglichen und getrennt
nachweisen: σ_p,max = min(0,8·f_pk; 0,9·f_p0,1k) beim Spannen,
σ_pm0 = min(0,75·f_pk; 0,85·f_p0,1k) nach dem Verankern, GZT gegen
f_pd = f_p0,1k/γ_s.“ Benennung (Anwender, gleicher Tag): „Anfangsvorspannung
(Pressenkraft P₀)“ und „Endvorspannung (bleibend nach dem Verankern)“ - die
bisherige Lastart „Vorspannkraft (Soll nach Verankerung)“.

Geprueft gegen geschlossene Loesungen (Anker k_A und Klemmteil k_K zwischen
Boden und Kopf wie tests/test_vorspannkraft.py):

* Spannschritt: das Kraeftepaar ist P0, N_spannen = P0.
* Verriegeln mit Schlupf Δs: der Anker verliert k_A·Δs gegen starre Umgebung;
  die Umgebung federt zurueck und gibt ihm den Anteil k_A/(k_A + k_K) davon
  wieder (Federverteilung): N_verankert = P0 − k_A·Δs·k_K/(k_A + k_K).
  Linear ueber die Einflussmatrix, nichtlinear ueber Spannen und Verriegeln
  mit eigenem Verankerungsschritt, mit Kontakt ebenso.
* Reihenweise: zum Schlupf kommen die elastischen Verluste wie bisher.
* Endvorspannung ohne Schlupf bleibt, wie sie war: N_spannen = F_soll, keine
  neuen Eintraege im Ergebnis, Datei bitgleich.
* Nachweis in drei Zustaenden mit den Kontrollzahlen des Anwenders
  (A = 1 256,64 mm², f_p0,1k 835, f_pk 1 030 N/mm²): 944,7 kN bleibend ->
  σ = 751,77 N/mm², nach dem Verankern 751,77/709,75 = 1,059, im GZT
  751,77/726,09 = 1,035; beim Spannen mit P0 = 944,7 kN 1,0004.
* Speichern und Laden ueber model.NEUE_FELDER.

Aufruf:  python -m tests.test_vorspannung_presse
"""
import json
import math
import os
import shutil
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")

from statik3d import plastizitaet as pl, solver                    # noqa: E402
from statik3d.model import Material, Model, NodalLoad, Section    # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:84s} {detail}")
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
A_A, A_A2, A_K = 1e-3, 2e-3, 4e-3
K_A, K_A2, K_K = E * A_A / L, E * A_A2 / L, E * A_K / L
P01, P02 = 500e3, 300e3     # Pressenkraefte [N]
DS1, DS2 = 0.5e-3, 0.25e-3  # Verankerungsschlupf [m]
P = 200e3                   # aeussere Zuglast am Kopf [N]


def _querschnitt(m, name, A):
    m.add_section(Section.circle(name, float(np.sqrt(4.0 * A / np.pi))))


def _vorspannung(m, stab, kraft, lf, gruppe=1, schlupf=None):
    """Endvorspannung (schlupf None) oder Anfangsvorspannung P0 mit Schlupf."""
    if schlupf is None:
        return m.add_vorspannung(stab, kraft, case=lf, sollkraft=True, gruppe=gruppe)
    return m.add_vorspannung(stab, kraft, case=lf, sollkraft=True, gruppe=gruppe, kraftart="presse",
                             schlupf=schlupf)


def _federn(anker=(("A1", A_A, P01, 1, DS1),), plast=False, kontakt=False,
            lasten=(("V", 0.0), ("VP", P))):
    """Boden G, Kopf H; je Anker ein Fachwerkstab G-H, das Klemmteil G'-H
    (bzw. G'-B mit Spaltelement B-H). Anker (Name, A, Kraft, Gruppe, Schlupf)."""
    m = Model("Anker mit Schlupf")
    m.add_material(Material("Stahl", E=E, nu=0.3, rho=7850, alpha=1e-5))
    G = m.add_node(0.0, 0.0, 0.0)
    G2 = m.add_node(0.0, 0.0, 0.0)
    H = m.add_node(0.0, 0.0, L)
    m.fix(G, "all")
    m.fix(G2, "all")
    m.fix(H, [0, 1, 3, 4, 5])
    elem = {}
    for name, A, _F, _g, _ds in anker:
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
        for name, _A, Fs, g, ds in anker:
            _vorspannung(m, name, Fs, lf, g, ds)
        if last:
            m.case(lf).nodal_loads.append(NodalLoad(H, [0.0, 0.0, last, 0.0, 0.0, 0.0]))
    if plast:
        m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=0.02, laststufen=3, iterationen=60,
                                         toleranz=1e-10)
    return m, H, elem, eK


def _N(res, e):
    return float(res.beam_forces[int(e)]["N"][1])


def _st(res, stab):
    return ((res.info.get("vorspannung") or {}).get("staebe") or {}).get(stab, {})


# --------------------------------------------------------------------------
# 1) Ein Anker zwischen Federn
# --------------------------------------------------------------------------
def test_ein_anker():
    N_v = P01 - K_A * DS1 * K_K / (K_A + K_K)
    for art, kw in (("linear (Einflussmatrix)", {}), ("Spannen und Verriegeln", {"plast": True}),
                    ("mit Kontakt (Fuge bleibt zu)", {"kontakt": True})):
        print(f"\n--- Ein Anker, P0 = 500 kN, Δs = 0,5 mm: {art} ---")
        m, H, el, eK = _federn(**kw)
        r = solver.solve_static(m, case="V")
        st = _st(r, "A1")
        print(f"     info: { {k: st.get(k) for k in sorted(st)} }")
        weg = (r.info.get("vorspannung") or {}).get("weg")
        check(f"{art}: Weg wie erwartet",
              weg == ("einflussmatrix" if not kw else "spannen und verriegeln"), str(weg))
        nahe(f"{art}: N_spannen = P0 (Kräftepaar im Spannschritt)", st.get("N_spannen"), P01, 1e-12, "N")
        nahe(f"{art}: Schlupfverlust gegen starre Umgebung k_A·Δs = 105 kN", st.get("schlupfverlust"),
             K_A * DS1, 1e-12, "N")
        nahe(f"{art}: N_verankert = P0 − k_A·Δs·k_K/(k_A + k_K) = 416 kN (Federverteilung)",
             st.get("N_verankert"), N_v, 1e-9, "N")
        nahe(f"{art}: Ende ohne weitere Last = N_verankert", _N(r, el["A1"]), N_v, 1e-9, "N")
        nahe(f"{art}: Klemmteil drückt mit N_verankert", _N(r, eK), -N_v, 1e-9, "N")
        nahe(f"{art}: Kopf um N_verankert/k_K gesenkt", r.u[H, 2], -N_v / K_K, 1e-9, "m")
        check(f"{art}: Kraftart „presse“ und Δs im Ergebnis",
              st.get("kraftart") == "presse" and abs(float(st.get("schlupf", 0.0)) - DS1) < 1e-15,
              f"{st.get('kraftart')}, {st.get('schlupf')}")
        r2 = solver.solve_static(m, case="VP")
        nahe(f"{art}: mit Zuglast P: N = N_verankert + k_A/(k_A + k_K)·P", _N(r2, el["A1"]),
             N_v + K_A / (K_A + K_K) * P, 1e-9, "N")
        if kw:
            zs = getattr(r, "vorspannzustaende", None) or {}
            va = zs.get("verankert")
            check(f"{art}: verankerter Zustand abgelegt (Gleichgewicht nach dem Schlupf)",
                  va is not None and va.info.get("zustand") == "verankert")
            if va is not None:
                nahe(f"{art}: … in ihm N = N_verankert", _N(va, el["A1"]), N_v, 1e-9, "N")
                nahe(f"{art}: … und der Kopf um N_verankert/k_K gesenkt", va.u[H, 2], -N_v / K_K, 1e-9, "m")


def test_zwei_gleichzeitig():
    print("\n--- Zwei Anker gleichzeitig mit Schlupf: Einflussmatrix = Spannen und Verriegeln ---")
    anker = (("A1", A_A, P01, 1, DS1), ("A2", A_A2, P02, 1, DS2))
    kg = K_A + K_A2 + K_K
    d = (K_A * DS1 + K_A2 * DS2) / kg          # Rueckfederung des Kopfs
    soll = {"A1": P01 - K_A * DS1 + K_A * d, "A2": P02 - K_A2 * DS2 + K_A2 * d}
    for art, kw in (("linear", {}), ("nichtlinear", {"plast": True})):
        m, H, el, eK = _federn(anker=anker, **kw)
        r = solver.solve_static(m, case="V")
        for s in ("A1", "A2"):
            nahe(f"{art}: {s} N_verankert = P0 − k·Δs + k·δ, δ = Σk_iΔs_i/Σk", _st(r, s).get("N_verankert"),
                 soll[s], 1e-9, "N")
            nahe(f"{art}: {s} Ende ohne Last", _N(r, el[s]), soll[s], 1e-9, "N")


def test_reihenweise():
    print("\n--- Reihenweise mit Schlupf: elastische Verluste kommen dazu ---")
    anker = (("A1", A_A, P01, 1, DS1), ("A2", A_A2, P02, 2, DS2))
    kg = K_A + K_A2 + K_K
    N1 = (P01 - K_A * DS1 * K_K / (K_A + K_K) - K_A * P02 / (K_A + K_K) + K_A * K_A2 * DS2 / kg)
    N2 = P02 - K_A2 * DS2 * (K_A + K_K) / kg
    for art, kw in (("linear", {}), ("nichtlinear", {"plast": True})):
        m, H, el, eK = _federn(anker=anker, **kw)
        r = solver.solve_static(m, case="V")
        nahe(f"{art}: A1 = P01 − Schlupf (verteilt) − k1·P02/(k1 + kK) + Rückfederung aus Δs2",
             _st(r, "A1").get("N_verankert"), N1, 1e-9, "N")
        nahe(f"{art}: A2 = P02 − k2·Δs2·(k1 + kK)/Σk", _st(r, "A2").get("N_verankert"), N2, 1e-9, "N")
        nahe(f"{art}: A1 am Ende", _N(r, el["A1"]), N1, 1e-9, "N")
        nahe(f"{art}: A2 am Ende", _N(r, el["A2"]), N2, 1e-9, "N")
        nahe(f"{art}: Verlust A1 = P01 − N_verankert", _st(r, "A1").get("verlust"), P01 - N1, 1e-9, "N")


def test_endvorspannung_unveraendert():
    print("\n--- Endvorspannung (bisher Soll nach Verankerung) bleibt, wie sie war ---")
    for art, kw in (("linear", {}), ("nichtlinear", {"plast": True})):
        m, H, el, eK = _federn(anker=(("A1", A_A, P01, 1, None),), **kw)
        r = solver.solve_static(m, case="V")
        st = _st(r, "A1")
        nahe(f"{art}: N_spannen = F_soll", st.get("N_spannen"), P01, 0.0, "N")
        nahe(f"{art}: N_verankert = F_soll", st.get("N_verankert"), P01, 1e-9, "N")
        check(f"{art}: keine Einträge der Anfangsvorspannung im Ergebnis",
              not any(k in st for k in ("kraftart", "schlupf", "schlupfverlust", "k_A")), str(sorted(st)))
    # Anfangsvorspannung ohne Schlupf rechnet wie die Endvorspannung mit F_soll = P0
    m0, _H, el0, _eK = _federn(anker=(("A1", A_A, P01, 1, 0.0),), plast=True)
    m1, _H, el1, _eK = _federn(anker=(("A1", A_A, P01, 1, None),), plast=True)
    r0, r1 = solver.solve_static(m0, case="VP"), solver.solve_static(m1, case="VP")
    check("Anfangsvorspannung mit Δs = 0 rechnet Zahl für Zahl wie die Endvorspannung",
          float(np.abs(np.asarray(r0.u) - np.asarray(r1.u)).max()) == 0.0
          and _N(r0, el0["A1"]) == _N(r1, el1["A1"]), f"{_N(r0, el0['A1'])} / {_N(r1, el1['A1'])}")


# --------------------------------------------------------------------------
# 2) Speichern und Laden
# --------------------------------------------------------------------------
def test_speichern_laden():
    print("\n--- Speichern und Laden ---")
    from statik3d import model as M
    vg = (getattr(M, "NEUE_FELDER", {}) or {}).get("load_cases.vorspannungen", {})
    check("NEUE_FELDER: kraftart \"\" und schlupf 0,0 als Vorgabe",
          vg.get("kraftart", object()) == "" and vg.get("schlupf", object()) == 0.0, str(vg))
    tmp = tempfile.mkdtemp()
    try:
        m, H, el, eK = _federn(anker=(("A1", A_A, P01, 1, DS1), ("A2", A_A2, P02, 2, None)))
        p = os.path.join(tmp, "presse.json")
        m.save(p)
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        lcs = d["load_cases"].values() if isinstance(d["load_cases"], dict) else d["load_cases"]
        vs = [x for lc in lcs for x in lc.get("vorspannungen", [])]
        a1 = [x for x in vs if x["ziel"] == "A1"]
        a2 = [x for x in vs if x["ziel"] == "A2"]
        check("Datei: Anfangsvorspannung mit kraftart und schlupf",
              a1 and a1[0].get("kraftart") == "presse" and a1[0].get("schlupf") == DS1, str(a1[:1]))
        check("Datei: Endvorspannung ohne die neuen Felder",
              a2 and "kraftart" not in a2[0] and "schlupf" not in a2[0], str(a2[:1]))
        m2 = Model.load(p)
        v = {x.ziel: x for x in m2.case("V").vorspannungen}
        check("geladen: Kraftart und Schlupf wie gespeichert",
              getattr(v["A1"], "kraftart", None) == "presse" and getattr(v["A1"], "schlupf", None) == DS1
              and getattr(v["A2"], "kraftart", None) == "" and getattr(v["A2"], "schlupf", None) == 0.0)
        r1, r2 = solver.solve_static(m, case="V"), solver.solve_static(m2, case="V")
        check("… und rechnet gleich", float(np.abs(np.asarray(r1.u) - np.asarray(r2.u)).max()) == 0.0)
        # Datei mit Endvorspannung und Anfangsdehnung, gespeichert am Stand 051007d
        pa = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daten", "vorspannung_soll_051007d",
                          "anker_soll.json")
        mb = Model.load(pa)
        pb = os.path.join(tmp, "alt_neu.json")
        mb.save(pb)
        with open(pa, "rb") as f1, open(pb, "rb") as f2:
            a, b = f1.read(), f2.read()
        check("Datei vom Stand 051007d (Endvorspannung, Anfangsdehnung): Laden und Speichern bitgleich",
              a == b, f"{len(a)} / {len(b)} Byte")
        from statik3d import ergebnisse
        mc = Model.load(pa)
        k0 = ergebnisse.kennung(mc)
        for v_ in mc.case("V").vorspannungen:
            v_.kraftart, v_.schlupf = "", 0.0
        check("Kennung der Ergebnisdatei: die neuen Felder auf ihrer Vorgabe ändern sie nicht",
              ergebnisse.kennung(mc) == k0)
        mc.case("V").vorspannungen[0].kraftart = "presse"
        check("… eine Anfangsvorspannung ändert sie", ergebnisse.kennung(mc) != k0)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 3) Nachweis in drei Zustaenden: die Kontrollzahlen des Anwenders
# --------------------------------------------------------------------------
A_NENN = math.pi * 0.040 ** 2 / 4.0        # 1 256,64 mm²
L_ANKER = 3.23
E_ANKER = 170e9


def _spannanker(P0, ds):
    """Anker Rund 40 aus Spannstahl 835/1030, beidseitig fest (starre
    Umgebung): N_verankert = P0 − k_A·Δs mit k_A = E A / L. LF_V traegt nur
    die Anfangsvorspannung, K1 = 1,0 · LF_V im GZT."""
    from statik3d.model import LoadCase
    m = Model("Spannanker")
    mat = Material("Spannstahl 835/1030", 170e9, 0.3, 7850.0, 1e-5, 835e6, 1030e6)
    mat.art = "Spannstahl"
    m.add_material(mat)
    m.add_section(Section.circle("Rund 40", 0.040))
    a = m.add_node(0, 0, 0)
    b = m.add_node(L_ANKER, 0, 0)
    m.add_element("truss", [a, b], mat.name, "Rund 40")
    m.fix(a, "all")
    m.fix(b, "all")
    m.add_member("A1", [0])
    m.load_cases["LF_V"] = LoadCase("LF_V", category="P")
    m.load_cases.pop("LF1", None)
    m.active_case = "LF_V"
    _vorspannung(m, "A1", P0, "LF_V", 1, ds)
    m.add_combination("K1", {"LF_V": 1.0}, "ULS")
    return m


def _zustand(mc, z):
    zz = [e for e in (getattr(mc, "zustaende", None) or []) if e.get("zustand") == z]
    return max(zz, key=lambda e: e["util"]) if zz else None


def test_nachweis_kontrollzahlen():
    print("\n--- Nachweis in drei Zuständen: Kontrollzahlen des Anwenders ---")
    sigma = 944.7e3 / A_NENN
    check("σ = 944,7 kN / 1 256,64 mm² = 751,77 N/mm²", abs(sigma / 1e6 - 751.77) < 0.005, f"{sigma / 1e6:.4f}")
    k_A = E_ANKER * A_NENN / L_ANKER
    for ds in (0.0, 1.0e-3):
        P0 = 944.7e3 + k_A * ds                 # bleibend 944,7 kN
        m = _spannanker(P0, ds)
        an = solver.solve_all(m, design=True)
        mc = an.design.members["A1"]
        st = _st(an.cases["LF_V"], "A1")
        print(f"     Δs {ds * 1e3:.1f} mm: P0 {P0 / 1e3:.3f} kN, k_A {k_A / 1e6:.3f} kN/mm; info {st}")
        for e in mc.zustaende:
            print(f"        {e['zustand']:20s} {e['quelle']:66s} N {e['N'] / 1e3:8.2f} kN  σ {e['sigma'] / 1e6:7.2f}"
                  f"  {e['grenzname']} {e['grenze'] / 1e6:7.2f}  η {e['util']:.4f}")
        sp, ve, gz = (_zustand(mc, z) for z in ("Spannen", "nach dem Verankern", "Lastzustand"))
        was = f"Δs = {ds * 1e3:.0f} mm"
        nahe(f"{was}: N_verankert = 944,7 kN (starre Umgebung: P0 − k_A·Δs)", st.get("N_verankert"), 944.7e3,
             1e-9, "N")
        nahe(f"{was}: Spannen P0 = {P0 / 1e3:.2f} kN gegen σ_p,max 751,5: η = {P0 / A_NENN / 751.5e6:.4f}",
             sp and sp["util"], P0 / A_NENN / 751.5e6, 1e-9)
        nahe(f"{was}: nach dem Verankern 751,77/709,75 = 1,059", ve and ve["util"], sigma / 709.75e6, 1e-9)
        nahe(f"{was}: GZT 751,77/726,09 = 1,035 (1,0354)", gz and gz["util"], sigma / (835e6 / 1.15), 1e-9)
        if ds == 0.0:
            check("Δs = 0: η beim Spannen 1,0004, nach dem Verankern 1,0592, im GZT 1,0354 (gerundet)",
                  sp and ve and gz and f"{sp['util']:.4f}" == "1.0004" and f"{ve['util']:.4f}" == "1.0592"
                  and f"{gz['util']:.4f}" == "1.0354",
                  f"{sp and sp['util']:.4f} / {ve and ve['util']:.4f} / {gz and gz['util']:.4f}")
        else:
            check("Δs = 1 mm: Spannen mit P0 = 944,7 + 66,14 = 1 010,84 kN → η 1,0704",
                  sp and f"{sp['util']:.4f}" == "1.0704" and abs(P0 / 1e3 - 1010.84) < 0.005,
                  f"{sp and sp['util']:.4f}, P0 {P0 / 1e3:.3f}")
            check("Δs = 1 mm: der Spannzustand nennt die Anfangsvorspannung P0",
                  sp and "Anfangsvorspannung" in sp["quelle"], sp and sp["quelle"])
            check("Δs = 1 mm: der verankerte Zustand nennt die Endvorspannung",
                  ve and "Endvorspannung" in ve["quelle"], ve and ve["quelle"])
    # ohne Ergebnis des Spannschritts: nach dem Verankern P0 − k_A·Δs, nicht P0
    from statik3d.ec3 import spannstahl as sp_
    m = _spannanker(1010.84e3, 1.0e-3)
    werte = sp_.eingegebene_vorspannung(m, m.members["A1"])
    bleibend = getattr(sp_, "eingegebene_endvorspannung", None)
    check("ohne Ergebnis: Endvorspannung aus der Eingabe = P0 − k_A·Δs (Hinweis „ohne Verluste der Umgebung“)",
          bleibend is not None and abs(bleibend(m, m.members["A1"])[0][1] - (1010.84e3 - k_A * 1e-3)) < 1e-6,
          f"{werte}")


def test_bezeichnung_je_lastfall():
    print("\n--- Bezeichnung je Lastfall: RFEM-Vorspannung (ΔT) neben der Anfangsvorspannung ---")
    from statik3d.model import LoadCase, TempLoad
    from statik3d.ec3 import spannstahl as sp_
    m = _spannanker(1010.84e3, 1.0e-3)
    m.load_cases["LF398"] = LoadCase("LF398", category="P")
    mat = m.materials["Spannstahl 835/1030"]
    m.load_cases["LF398"].temp_loads.append(TempLoad(0, -952e3 / (mat.E * A_NENN * mat.alpha)))
    an = solver.solve_all(m, design=True)
    zst = an.design.members["A1"].zustaende
    sp = {e["quelle"].split(":")[0]: e["quelle"] for e in zst if e["zustand"] == "Spannen"
          and "eingegebene" in e["quelle"]}
    print(f"     {sp}")
    check("LF_V: eingegebene Anfangsvorspannung P₀", "Anfangsvorspannung P₀" in sp.get("LF_V", ""), sp.get("LF_V"))
    check("LF398 (ΔT, Kategorie P): eingegebene Vorspannung als eingeprägte Dehnung",
          "Vorspannung als eingeprägte Dehnung" in sp.get("LF398", ""), sp.get("LF398"))
    check("eingabe_art je Lastfall", sp_.eingabe_art(m, m.members["A1"], "LF398")
          == "Vorspannung als eingeprägte Dehnung" and sp_.eingabe_art(m, m.members["A1"], "LF_V")
          == "Anfangsvorspannung P₀")


def test_bericht_je_anker():
    print("\n--- Bericht: je Anker eine Zeile mit drei Zuständen ---")
    from statik3d.report import Report
    k_A = E_ANKER * A_NENN / L_ANKER
    m = _spannanker(944.7e3 + k_A * 1e-3, 1e-3)
    an = solver.solve_all(m, design=True)
    html = Report(m, an).html()
    i = html.find("Spannstahl je Anker")
    teil = html[i:i + 6000] if i >= 0 else ""
    print(f"     Ausschnitt: {teil[:1500]!r}")
    check("Bericht: Tabelle „Spannstahl je Anker“", i >= 0)
    for t in ("Anfangsvorspannung P₀", "Endvorspannung", "Lastzustand", "1010.84", "944.70", "1.0704",
              "1.0592", "1.0354", "Δs = 1.00 mm"):
        check(f"… nennt „{t}“", t in teil)
    check("Lastangaben: Anfangsvorspannung (Pressenkraft P₀) mit Δs",
          "Anfangsvorspannung (Pressenkraft P₀)" in html and "Δs" in html)


def main():
    for t in (test_ein_anker, test_zwei_gleichzeitig, test_reihenweise, test_endvorspannung_unveraendert,
              test_speichern_laden, test_nachweis_kontrollzahlen, test_bezeichnung_je_lastfall,
              test_bericht_je_anker):
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
