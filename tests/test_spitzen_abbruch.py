"""
Abbruch der Plastizitaet ohne die netzabhaengigen Spitzen (Plan Singularitaeten
vom 10.10.2026, Paket 3).

Entscheidung des Anwenders vom 10.10.2026: Spannungsspitzen und
Singularitaeten „sollten nicht dafür sorgen dass sich die rechenzeit
verlängert“. Der plastische Newton misst seine Konvergenz an der Aenderung der
plastischen Knotenlast F_p ueber das ganze Modell - am Drehlager sind das zu
97 bis 99 % die 16 Ankerringe, deren Spitze mit dem Netz waechst. Neu ist das
Abbruchkriterium „ingenieurmäßig“ als Vorgabe: eine Laststufe gilt als
konvergiert, wenn

* die Aenderung von F_p **ausserhalb** der auffaelligen Zonen (Paket 1,
  spitzenstellen.auffaellige_zonen) bezogen auf ||F|| unter der Toleranz liegt,
* die Kraft durch jede auffaellige Stelle sich um hoechstens 0,5 % aendert und
* die Verschiebung ausserhalb der Zonen sich hoechstens um
  plastizitaet.SPITZEN_VERSCHIEBUNG aendert.

Die Zonen rechnen weiter plastisch mit; ihre Werte stehen mit der letzten
Aenderung als „nicht auskonvergiert“ im Ergebnis. Das strenge Kriterium bleibt
waehlbar. Ohne auffaellige Stelle ist alles bitgleich zum Stand davor.

Geprueft wird an der **Ankerplatte**: eine 100 mm dicke Ringplatte mit
Bohrung (Radius 25 mm, aussen 255 mm, hex8 mit rund 10 mm Kantenlaenge am
Loch wie das Entwurfsnetz des Drehlagers), aussen fest; eine starre Scheibe
genau ueber der Bohrung koppelt nur den Lochrand (wie am Drehlager), daran
haengt ein Ankerstab Rund 40, 3 m lang, unten fest, mit einer
Temperatur-Vorspannung von 0,9 MN (wie die Anker des Drehlagers) und 0,3 MN
Zuglast am Stabende. Am Lochrand fliesst die Platte mit einer Spitze, die mit
dem Netz waechst (eps_p rund 8 %), die Pressung ueber die Scheibe liegt ueber
f_y - die Stelle ist ab dem ersten Newton-Schritt auffaellig.

Aufruf:  python -m tests.test_spitzen_abbruch
"""
import json
import os
import sys
import tempfile
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import ergebnisse, fugen, solver                                 # noqa: E402
from statik3d import plastizitaet as pl, spitzenstellen as sp                  # noqa: E402
from statik3d.model import Material, Model, Section                            # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FEHLER'} {name:78s} {detail}")
    return bool(ok)


# --------------------------------------------------------------------------
# Ankerplatte
# --------------------------------------------------------------------------
A_LOCH = 0.025                                  # Lochradius [m]
DICKE = 0.100
RHO = (0.0, 0.012, 0.030, 0.050, 0.080, 0.120, 0.170, 0.230)      # radiale Lagen ab dem Lochrand
Z = tuple(DICKE * z for z in (0.0, 0.25, 0.5, 0.7, 0.88, 1.0))
PHI = 16
E, ALPHA = 210e9, 1.2e-5
D_ANKER, L_ANKER = 0.040, 3.0


def ankerplatte(F_v=0.9e6, P=0.3e6, stufen=3, abbruch=None):
    """Ringplatte mit starrer Scheibe ueber der Bohrung und Ankerstab. ``F_v``:
    Vorspannung des Ankers als Temperaturlast (bei voller Behinderung), ``P``:
    Zuglast nach unten am Stabende. Rueckgabe (Modell, Knotennummern
    [phi, rho, z], Stabende, Ankerelement)."""
    from statik3d.elements import solid as _sl
    m = Model("Ankerplatte")
    m.add_material(Material.steel("S355"))
    m.add_material(Material("Anker", E, 0.3, 7850.0, ALPHA))
    ids = np.zeros((PHI, len(RHO), len(Z)), int)
    for i in range(PHI):
        ph = 2.0 * np.pi * i / PHI
        for j, dr in enumerate(RHO):
            for k, z in enumerate(Z):
                ids[i, j, k] = m.add_node((A_LOCH + dr) * np.cos(ph), (A_LOCH + dr) * np.sin(ph), z)
    for i in range(PHI):
        i2 = (i + 1) % PHI
        for j in range(len(RHO) - 1):
            for k in range(len(Z) - 1):
                kn = [int(x) for x in (ids[i, j, k], ids[i, j + 1, k], ids[i2, j + 1, k], ids[i2, j, k],
                                       ids[i, j, k + 1], ids[i, j + 1, k + 1], ids[i2, j + 1, k + 1],
                                       ids[i2, j, k + 1])]
                if _sl.jacobi_volumen("hex8", m.nodes[kn])["V"] < 0:
                    kn = kn[4:] + kn[:4]
                m.add_element("hex8", kn, "S355")
    k = len(Z) - 1
    p, q = int(ids[0, 0, k]), int(ids[PHI // 2, 0, k])
    a, t = A_LOCH, DICKE
    m.add_line("S1", [p, q], "arc", punkte=[(a, 0, t), (0, a, t), (-a, 0, t)])
    m.add_line("S2", [q, p], "arc", punkte=[(-a, 0, t), (0, -a, t), (a, 0, t)])
    m.add_flaeche("Scheibe", ["S1", "S2"], material="S355")
    m.flaechen["Scheibe"].steifigkeit = "starr"
    mitte = m.add_node(0.0, 0.0, t)
    unten = m.add_node(0.0, 0.0, t - L_ANKER)
    m.add_section(Section.circle("Rund 40", D_ANKER))
    e = m.add_element("truss", [mitte, unten], "Anker", "Rund 40", group="Anker")
    m.add_member("Anker", [e])
    fugen.starre_flaechen_koppeln(m, [])
    for n in ids[:, -1, :].ravel():
        m.fix(int(n), [0, 1, 2])
    m.fix(int(unten), "all")
    m.add_load_case("LF1").gravity = [0.0, 0.0, 0.0]
    A_s = np.pi * D_ANKER ** 2 / 4.0
    m.load_temp(e, -F_v / (E * A_s * ALPHA), case="LF1")
    if P:
        m.load_node(int(mitte), Fz=-P, case="LF1")
    m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=0.01, laststufen=stufen, iterationen=25,
                                     toleranz=1e-3)
    if abbruch is not None:
        m.plastizitaet.abbruch = abbruch
    return m, ids, mitte, e


def ankerkraft(m, r, e):
    return abs(float(solver.beam_end_forces(m, e, r.beam_end[e])["N"][1]))


def sv_je_element(r):
    return {int(i): float(sp.vergleichsspannung(v)[0]) for i, v in r.solid_res.items()}


def rechnen(m):
    t0 = time.perf_counter()
    r = solver.solve_static(m)
    return r, time.perf_counter() - t0


# --------------------------------------------------------------------------
# 1) Einstellung
# --------------------------------------------------------------------------
def test_einstellung():
    """„Abbruch der Plastizität“: ingenieurmäßig (Vorgabe) oder streng - am
    Modell gespeichert und geladen; alte Dateien bekommen die Vorgabe."""
    check("zwei Wege, die Vorgabe zuerst: ingenieurmäßig, streng",
          tuple(getattr(pl, "ABBRUCH_WEGE", ())) == ("ingenieurmaessig", "streng"),
          f"{getattr(pl, 'ABBRUCH_WEGE', None)}")
    check("ein neues Modell rechnet ingenieurmäßig",
          getattr(Model().plastizitaet, "abbruch", None) == "ingenieurmaessig",
          f"{getattr(Model().plastizitaet, 'abbruch', None)!r}")
    m, _ids, _mitte, _e = ankerplatte(abbruch="streng")
    with tempfile.TemporaryDirectory() as tmp:
        pfad = os.path.join(tmp, "ankerplatte.json")
        m.save(pfad)
        m2 = Model.load(pfad)
        with open(pfad, encoding="utf-8") as f:
            roh = json.load(f)
    check("Speichern und Laden: „streng“ kommt zurück",
          getattr(m2.plastizitaet, "abbruch", None) == "streng"
          and roh.get("plastizitaet", {}).get("abbruch") == "streng",
          f"{getattr(m2.plastizitaet, 'abbruch', None)!r}, in der Datei {roh.get('plastizitaet', {}).get('abbruch')!r}")
    d = m.to_dict()
    d["plastizitaet"].pop("abbruch", None)
    alt = Model.from_dict(json.loads(json.dumps(d)))
    check("eine Datei von vor dem 13.10.2026 (ohne den Schlüssel) rechnet ingenieurmäßig",
          getattr(alt.plastizitaet, "abbruch", None) == "ingenieurmaessig",
          f"{getattr(alt.plastizitaet, 'abbruch', None)!r}")


# --------------------------------------------------------------------------
# 2) Streng gegen ingenieurmaessig an der Ankerplatte
# --------------------------------------------------------------------------
def _paar():
    m_s, _ids, _mitte, e = ankerplatte(abbruch="streng")
    r_s, t_s = rechnen(m_s)
    m_i, _ids, _mitte, _e = ankerplatte(abbruch="ingenieurmaessig")
    r_i, t_i = rechnen(m_i)
    return (m_s, r_s, t_s), (m_i, r_i, t_i), e


def test_streng_gegen_ingenieurmaessig(paar):
    (m_s, r_s, t_s), (m_i, r_i, t_i), e = paar
    pz_s, pz_i = r_s.info["plastizitaet"], r_i.info["plastizitaet"]
    st_s = (r_s.info.get("spitzenstellen") or {}).get("stellen") or []
    check("die Scheibe über der Bohrung ist auffällig (Pressung über die Hülle ≥ f_y)",
          len(st_s) == 1 and st_s[0]["auffaellig"],
          f"{[(x['quelle'], x['art'], x['gruende'], round(x.get('pressung_fy') or 0, 3)) for x in st_s]}")
    check("beide konvergiert", pz_s.get("konvergiert") and pz_i.get("konvergiert"),
          f"streng {pz_s.get('konvergiert')}, ingenieurmäßig {pz_i.get('konvergiert')}")
    n_s, n_i = pz_s.get("iterationen"), pz_i.get("iterationen")
    check("ingenieurmäßig braucht weniger Newton-Schritte", n_i < n_s,
          f"streng {n_s} Schritte ({t_s:.1f} s), ingenieurmäßig {n_i} Schritte ({t_i:.1f} s)")
    zone = set(int(i) for i in sp.zonen_elemente(r_s).tolist())
    check("… mit derselben Zone in beiden Rechnungen",
          zone and zone == set(int(i) for i in sp.zonen_elemente(r_i).tolist()), f"{len(zone)} Elemente")
    sv_s, sv_i = sv_je_element(r_s), sv_je_element(r_i)
    aussen = [i for i in sv_s if i not in zone]
    abw = max(abs(sv_s[i] - sv_i[i]) for i in aussen)
    wo = max(aussen, key=lambda i: abs(sv_s[i] - sv_i[i]))
    check("außerhalb der Zone weicht σ_v um höchstens 1 N/mm² ab", abw <= 1e6,
          f"größte Abweichung {abw / 1e6:.4f} N/mm² (Element {wo}: {sv_s[wo] / 1e6:.2f} / {sv_i[wo] / 1e6:.2f}), "
          f"σ_v max außerhalb {max(sv_s[i] for i in aussen) / 1e6:.1f} N/mm²")
    N_s, N_i = ankerkraft(m_s, r_s, e), ankerkraft(m_i, r_i, e)
    check("die Ankerkraft weicht um höchstens 0,5 % ab", abs(N_i - N_s) <= 5e-3 * N_s,
          f"streng {N_s / 1e3:.2f} kN, ingenieurmäßig {N_i / 1e3:.2f} kN ({(N_i - N_s) / N_s * 100:+.3f} %)")
    u_s = np.asarray(r_s.u, float).reshape(-1, 6)[:, :3]
    u_i = np.asarray(r_i.u, float).reshape(-1, 6)[:, :3]
    st = st_s[0]
    innen = {int(k) for i in zone for k in m_s.elements[i].nodes} | {int(k) for k in st["knoten"]} | {int(st["master"])}
    aussen_kn = np.array([k for k in range(m_s.nn) if k not in innen])
    ua = float(np.linalg.norm(u_s[aussen_kn], axis=1).max())
    dua = float(np.linalg.norm(u_s[aussen_kn] - u_i[aussen_kn], axis=1).max())
    check("außerhalb der Zone weicht u um höchstens 1 % ab", dua <= 1e-2 * ua,
          f"max |Δu| {dua * 1e6:.2f} µm bei u max {ua * 1e3:.4f} mm außerhalb ({dua / ua * 100:.3f} %); "
          f"u_max gesamt (am Ring) streng {np.linalg.norm(u_s, axis=1).max() * 1e3:.4f} mm, ingenieurmäßig "
          f"{np.linalg.norm(u_i, axis=1).max() * 1e3:.4f} mm")
    # der Satz im Benutzerhandbuch nennt diese Messung (tests/handbuch.py)
    from tests.handbuch import absatz
    satz = absatz("An der Ankerplatte der Tests")
    check("das Benutzerhandbuch nennt die gemessenen Schritte und Abweichungen",
          f"{n_i} statt {n_s} Newton-Schritte" in satz and f"{abw / 1e6:.2f} N/mm²".replace(".", ",") in satz
          and f"{abs(N_i - N_s) / N_s * 100:.2f} %".replace(".", ",") in satz
          and f"{dua / ua * 100:.2f} %".replace(".", ",") in satz, satz[:160])
    ep_s = max((r_s.info.get("plastisch") or {0: 0.0}).values())
    ep_i = max((r_i.info.get("plastisch") or {0: 0.0}).values())
    print(f"       ε_p max streng {ep_s * 100:.3f} %, ingenieurmäßig {ep_i * 100:.3f} % (in der Zone, nicht auskonvergiert)")


def test_kennzeichnung_im_ergebnis(paar):
    (m_s, r_s, _t), (m_i, r_i, _t2), _e = paar
    st_i = (r_i.info.get("spitzenstellen") or {}).get("stellen") or []
    st_s = (r_s.info.get("spitzenstellen") or {}).get("stellen") or []
    na = st_i[0].get("nicht_auskonvergiert") if st_i else None
    check("ingenieurmäßig: die Stelle trägt „nicht auskonvergiert“ mit der letzten Änderung",
          isinstance(na, dict) and all(k in na for k in ("kraft_aenderung", "sv_aenderung", "eps_p_aenderung",
                                                         "fp_aenderung_zone", "stufe", "schritt")),
          f"{na}")
    check("streng: kein Vermerk (die Zone ist auskonvergiert)",
          st_s and not st_s[0].get("nicht_auskonvergiert"), f"{st_s[0].get('nicht_auskonvergiert') if st_s else None}")
    sp_i = (r_i.info.get("plastizitaet") or {}).get("spitzen") or {}
    check("res.info['plastizitaet']['spitzen'] nennt Kriterium und ausgenommene Stellen",
          sp_i.get("abbruch") == "ingenieurmaessig" and sp_i.get("ausgenommen") == [st_i[0]["nr"]],
          f"{ {k: v for k, v in sp_i.items() if k != 'verlauf'} }")
    log_i = (r_i.info.get("plastizitaet") or {}).get("log") or []
    log_s = (r_s.info.get("plastizitaet") or {}).get("log") or []
    zl_i = [z for z in log_i if "Zonen" in z and "Newton-Schritt" in z]
    zl_s = [z for z in log_s if "Zonen" in z and "Newton-Schritt" in z]
    check("Protokoll: je Newton-Schritt eine Zeile mit der Änderung in und außerhalb der Zonen und der Kraft",
          len(zl_i) == r_i.info["plastizitaet"]["iterationen"] and len(zl_s) == r_s.info["plastizitaet"]["iterationen"]
          and all("außerhalb" in z and "in den Zonen" in z and "kN" in z for z in zl_i + zl_s),
          f"{len(zl_i)} / {len(zl_s)} Zeilen; {zl_i[-1] if zl_i else ''}")
    check("… und eine Zeile, die die ausgenommenen Stellen als nicht auskonvergiert nennt",
          any("nicht auskonvergiert" in z and "ausgenommen" in z for z in log_i)
          and not any("ausgenommen" in z for z in log_s), "")
    with tempfile.TemporaryDirectory() as tmp:
        pfad = os.path.join(tmp, "ankerplatte.ergebnisse")
        an = solver.Analysis(m_i) if hasattr(solver, "Analysis") else None
        if an is None:
            check("Ergebnisdatei (Analysis fehlt)", False)
            return
        an.cases["LF1"] = r_i
        ergebnisse.schreiben(pfad, m_i, an)
        an2 = ergebnisse.lesen(pfad, m_i)
    b = ((an2.cases["LF1"].info.get("spitzenstellen") or {}).get("stellen") or [{}])[0]
    check("Speichern und Laden der Ergebnisdatei: der Vermerk kommt gleich zurück",
          b.get("nicht_auskonvergiert") == na, f"{b.get('nicht_auskonvergiert')}")


# --------------------------------------------------------------------------
# 3) Bitgleich ohne auffaellige Stelle
# --------------------------------------------------------------------------
def _drei_laeufe(bauen):
    """(ohne Beobachtung wie vor dem 13.10.2026, streng, ingenieurmaessig)."""
    echt = solver._spitzen_im_newton
    aus = []
    try:
        solver._spitzen_im_newton = lambda *a, **k: None
        m = bauen()
        aus.append(solver.solve_static(m))
    finally:
        solver._spitzen_im_newton = echt
    for weg in ("streng", "ingenieurmaessig"):
        m = bauen()
        m.plastizitaet.abbruch = weg
        aus.append(solver.solve_static(m))
    return aus


def _gleich(a, b):
    pa, pb = a.info["plastizitaet"], b.info["plastizitaet"]
    return (np.array_equal(np.asarray(a.u), np.asarray(b.u))
            and a.info.get("plastisch") == b.info.get("plastisch")
            and pa.get("iterationen") == pb.get("iterationen")
            and pa.get("faktorisierungen") == pb.get("faktorisierungen")
            and pa.get("halbiert") == pb.get("halbiert"))


def test_bitgleich_ohne_auffaellige_stelle():
    from tests.test_plastizitaet import _gequetschter_block
    alt, streng, ing = _drei_laeufe(_gequetschter_block)
    check("gequetschter Block (keine Stelle): streng und ingenieurmäßig bitgleich zum Stand ohne Beobachtung",
          _gleich(alt, streng) and _gleich(alt, ing),
          f"{alt.info['plastizitaet'].get('iterationen')} Newton-Schritte, "
          f"ε_p max {max(alt.info['plastisch'].values()) * 100:.2f} %")
    check("… ohne Zonenzeile im Protokoll",
          not any("Zonen" in z for z in ing.info["plastizitaet"].get("log") or []), "")

    def leicht():
        return ankerplatte(F_v=0.45e6, P=0.15e6)[0]
    alt, streng, ing = _drei_laeufe(leicht)
    st = (ing.info.get("spitzenstellen") or {}).get("stellen") or []
    check("Ankerplatte mit kleiner Ankerkraft: die Stelle fließt, ist aber nicht auffällig",
          len(st) == 1 and not st[0]["auffaellig"] and ing.info.get("plastisch"),
          f"{[(x['gruende'], round(x.get('pressung_fy') or 0, 3), round(x.get('sv_fy') or 0, 3)) for x in st]}, "
          f"{len(ing.info.get('plastisch') or {})} Elemente fließen")
    check("… streng und ingenieurmäßig bitgleich zum Stand ohne Beobachtung",
          _gleich(alt, streng) and _gleich(alt, ing),
          f"{alt.info['plastizitaet'].get('iterationen')} Newton-Schritte")


# --------------------------------------------------------------------------
# 4) Einmal auffaellig, bleibt auffaellig
# --------------------------------------------------------------------------
def test_einmal_auffaellig_bleibt_auffaellig():
    """Innerhalb eines Lastfalls bleibt eine Stelle, die einmal auffaellig war,
    ausgenommen - auch wenn ihre Kraft danach unter die Grenze faellt. Sonst
    pendelte das Kriterium zwischen zwei Massen."""
    m, _ids, mitte, e = ankerplatte()
    stellen = sp.kandidaten(m)
    F, feq, _q, temp = solver.case_loads(m, {"LF1": 1.0})
    system = solver.StaticSystem(m)
    u1 = np.asarray(system.solve(F), float)
    w = solver._SpitzenImNewton(m, stellen, streng=False, faktoren={"LF1": 1.0}, feq=feq, feq_sofort={},
                                temp=temp)
    z0 = pl.Zustand()
    nF = float(np.linalg.norm(F))
    a = w.messen(u1, np.zeros(m.ndof), np.zeros(m.ndof), z0, {}, nF, 1.0)
    check("elastisch unter voller Last: die Scheibe ist auffällig (Pressung)",
          w.auffaellig == {stellen[0]["nr"]} and a["zonen"] == 1, f"{w.auffaellig}, {a.get('zeile')}")
    # Anker entspannt: das Stabende so weit nach unten, dass der Stab keine
    # Kraft mehr hat, und ohne die Zuglast (Lastfaktor 0)
    u2 = u1.copy()
    A_s = np.pi * D_ANKER ** 2 / 4.0
    N1 = ankerkraft_aus_u(m, e, u1, feq, temp)
    u2[6 * mitte + 2] -= N1 * L_ANKER / (E * A_s)
    b = w.messen(u2, np.zeros(m.ndof), np.zeros(m.ndof), z0, {}, nF, 0.0)
    erg = sp.bewerten(m, stellen, sp.kraefte(m, stellen, None, u=u2, faktoren={"LF1": 0.0}, feq=feq, temp=temp),
                      {}, {})
    jetzt = [x["nr"] for x in erg["stellen"] if x["auffaellig"]]
    N2 = ankerkraft_aus_u(m, e, u2, feq, temp)
    check("danach ohne Kraft: für sich nicht mehr auffällig, bleibt aber ausgenommen",
          not jetzt and w.auffaellig == {stellen[0]["nr"]} and b["zonen"] == 1 and N2 < 1e-6 * N1,
          f"Ankerkraft vorher {N1 / 1e3:.1f} kN, nachher {N2:.3g} N; jetzt auffällig {jetzt}, "
          f"ausgenommen {w.auffaellig}")


def ankerkraft_aus_u(m, e, u, feq, temp):
    """Stabkraft aus u wie im Loeser (die Temperatur-Vorspannung steht in feq)."""
    fl = [w for i, art, w in solver._post_chunk(m, [e], {"u": np.asarray(u, float), "feq": feq, "temp": temp})
          if art == "beam"][0]
    return abs(float(solver.beam_end_forces(m, e, fl)["N"][1]))


# --------------------------------------------------------------------------
# 4b) Nie strenger als streng
# --------------------------------------------------------------------------
def test_streng_genuegt_immer():
    """Was streng konvergiert, ist auch ingenieurmaessig konvergiert: die
    Bedingungen fuer Kraft und Verschiebung duerfen keine Stufe verlaengern.
    Am Drehlager (Entwurf) aenderte der Kontakt die Verschiebung ausserhalb
    der Zonen um 6,6 % in einem Schritt, in dem F_p ueberall unter der
    Toleranz lag (13.10.2026)."""
    class Zonen:
        ingenieur = True

        def __init__(self, erfuellt):
            self.erfuellt = erfuellt

        def messen(self, *a, **k):
            return {"zonen": 16, "aussen": 5e-4, "erfuellt": self.erfuellt, "zeile": None}
    mass, ok, _m = pl._zonen_mass(Zonen(False), 8e-4, 1e-3, None, None, None, None, None, 1.0, 1.0, "1/1", 1)
    check("streng erfüllt (8e-4 ≤ 1e-3), Kraft oder Verschiebung nicht: konvergiert", ok and mass == 5e-4,
          f"{ok}, Maß {mass}")
    mass, ok, _m = pl._zonen_mass(Zonen(False), 2e-3, 1e-3, None, None, None, None, None, 1.0, 1.0, "1/1", 1)
    check("streng nicht erfüllt, außerhalb unter der Toleranz, Kraft oder Verschiebung nicht: weiter", not ok,
          f"{ok}")
    mass, ok, _m = pl._zonen_mass(Zonen(True), 2e-3, 1e-3, None, None, None, None, None, 1.0, 1.0, "1/1", 1)
    check("streng nicht erfüllt, alle drei Bedingungen erfüllt: konvergiert", ok, f"{ok}")


# --------------------------------------------------------------------------
# 5) Protokoll: Werkstoffe ohne Streckgrenze einmal je Lastfall
# --------------------------------------------------------------------------
def test_protokollzeile_einmal():
    """Am Koerper-Bolzen (tests.test_vorspannung_sofort) stand „Werkstoffe ohne
    Streckgrenze bleiben elastisch“ bis zum 13.10.2026 in 11 von 13 Zeilen -
    einmal je Newton-Schritt."""
    from tests.test_vorspannung_sofort import _bolzen_auf_wuerfel
    m, _fuge = _bolzen_auf_wuerfel()
    r = solver.solve_static(m)
    log = (r.info.get("plastizitaet") or {}).get("log") or []
    n = sum(1 for z in log if "ohne Streckgrenze" in z)
    check("„Werkstoffe ohne Streckgrenze bleiben elastisch“ steht einmal je Lastfall",
          n == 1 and r.info["plastizitaet"].get("iterationen", 0) > 1,
          f"{n} von {len(log)} Zeilen, {r.info['plastizitaet'].get('iterationen')} Newton-Schritte")


# --------------------------------------------------------------------------
# 6) Unbekannter Wert
# --------------------------------------------------------------------------
def test_unbekannter_wert():
    m, _ids, _mitte, _e = ankerplatte(abbruch="Streng ")
    r = solver.solve_static(m)
    log = (r.info.get("plastizitaet") or {}).get("log") or []
    check("ein unbekannter Wert rechnet ingenieurmäßig (Vorgabe) und steht im Protokoll",
          any("Abbruch" in z and "unbekannt" in z for z in log)
          and ((r.info["plastizitaet"].get("spitzen") or {}).get("abbruch") == "ingenieurmaessig"),
          " | ".join(z for z in log if "Abbruch" in z))


# --------------------------------------------------------------------------
# 7) Maske Berechnung (offscreen)
# --------------------------------------------------------------------------
def test_maske():
    """Die Auswahl „Abbruch“ in der Maske Berechnung zeigt die Einstellung des
    Modells und schreibt sie zurueck; ein neues Modell steht auf ingenieurmäßig."""
    from PySide6 import QtWidgets
    from statik3d.gui.main import MainWindow
    from tests.meldungen import abfangen
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = MainWindow()
    w.show()
    app.processEvents()
    w._fragen_knoepfe = lambda *a, **k: True
    w.fehler_liste = []
    w.meldungen = abfangen(w, w.fehler_liste, protokoll=True)
    cb = getattr(w, "cb_plast_abbruch", None)
    if not check("Maske Berechnung: Auswahl „Abbruch“ vorhanden", cb is not None):
        return
    texte = {cb.itemData(i): cb.itemText(i) for i in range(cb.count())}
    check("zwei Einträge, die Vorgabe zuerst", list(texte) == ["ingenieurmaessig", "streng"]
          and texte["ingenieurmaessig"] == "ingenieurmäßig (Vorgabe)", str(texte))
    check("der Tooltip nennt die ausgenommenen Spitzen und „nicht auskonvergiert“",
          "netzabhängige Spitzen ausgenommen" in cb.toolTip() and "nicht auskonvergiert" in cb.toolTip())
    w.new_model()
    app.processEvents()
    check("ein neues Modell steht auf „ingenieurmäßig“",
          cb.currentData() == "ingenieurmaessig" and w.model.plastizitaet.abbruch == "ingenieurmaessig",
          f"{cb.currentData()} / {w.model.plastizitaet.abbruch}")
    m, _ids, _mitte, _e = ankerplatte(abbruch="streng")
    w._modell_setzen(m)
    app.processEvents()
    check("ein Modell mit „streng“ zeigt „streng“", cb.currentData() == "streng", f"{cb.currentData()}")
    cb.setCurrentIndex(cb.findData("ingenieurmaessig"))
    w._plast_uebernehmen()
    app.processEvents()
    check("… umgestellt und übernommen: das Modell rechnet ingenieurmäßig und ist ungespeichert",
          w.model.plastizitaet.abbruch == "ingenieurmaessig" and w.ungespeichert(),
          f"{w.model.plastizitaet.abbruch}, ungespeichert {w.ungespeichert()!r}")
    check("keine Fehlermeldung", not w.fehler_liste, str(w.fehler_liste[:3]))


def main():
    paar = None
    for t in (test_einstellung, test_maske, test_protokollzeile_einmal, test_einmal_auffaellig_bleibt_auffaellig,
              test_streng_genuegt_immer,
              "paar", test_streng_gegen_ingenieurmaessig, test_kennzeichnung_im_ergebnis,
              test_bitgleich_ohne_auffaellige_stelle, test_unbekannter_wert):
        if t == "paar":
            try:
                paar = _paar()
            except Exception as ex:      # noqa: BLE001
                import traceback
                traceback.print_exc()
                RESULTS.append((f"Ankerplatte rechnen (Ausnahme: {ex})", False))
            continue
        print(f"\n--- {t.__name__} ---")
        try:
            if t in (test_streng_gegen_ingenieurmaessig, test_kennzeichnung_im_ergebnis):
                if paar is None:
                    RESULTS.append((t.__name__ + " (ohne Rechnung)", False))
                    continue
                t(paar)
            else:
                t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    sys.stdout.flush()
    return 0 if not schlecht else 1


if __name__ == "__main__":
    # ein Fenster ist offen (test_maske): ohne Rueckfrage beenden
    os._exit(main())
