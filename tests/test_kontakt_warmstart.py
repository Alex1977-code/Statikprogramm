"""Warmstart und Pendelschutz der Kontaktlaeufe (Vorschlaege 1 bis 5, 14.10.2026).

Befund am Drehlager (V36 auf dem Flaechenlager „Starr“, mu 0,1): seit Temperatur
und Vorspannung ab der ersten Laststufe voll wirken (plastizitaet.stufenlast), ist
die Stufenlast nicht mehr proportional zur Last des elastischen Vorlaufs; die Stufe
startete trotzdem warm aus dessen Gleitzustand, und zwei Flecken pendelten in der
Gleitrichtung bis zum Deckel. Kalt gestartet pendelte nichts.

Entscheidung des Anwenders vom 14.10.2026: Vorschlaege 1 bis 5 bauen, jede
Massnahme einzeln schaltbar (Einstellung am Modell, gespeichert nur abweichend von
der Vorgabe, eingetragen in model.NEUE_FELDER) und einzeln geprueft.

Das Pruefmodell: eine Stahlplatte 1 x 1 x 0,2 m (tet10, Zellweite 0,25 m) auf einem
Flaechenlager „Starr“ (uz starr mit Ausfall bei Zug, ux/uy starr mit Reibung mu),
vier Anker Rund 40 von Knoten der Oberseite 3 m nach unten (fest), Vorspannung je
Anker 1 MN als Temperatur (wirkt in den Laststufen sofort voll), oben Schub
0,6 mu V in x und 0,2 mu V in y (V = Summe der Ankerkraefte) - der wird gestuft.
Die Platte bleibt elastisch (f_y 1e12), die Laststufen rechnen trotzdem: jede
Stufe ein Kontaktlauf. Ohne Vorschlag 1 pendelt der warme Start der Stufe 1 in den
Gleitrichtungen (gemessen 14.10.2026, kws_werk).

Aufruf:  python -m tests.test_kontakt_warmstart
"""
import contextlib
import os
import sys
import tempfile
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_warmstart_"), "einstellungen.json")

from statik3d import plastizitaet as pl, solver                # noqa: E402

RESULTS = []
E_ANKER, ALPHA = 210e9, 1.2e-5


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:78s} {detail}")
    return ok


def platte(mu=0.2, Fv=1.0e6, rx=0.6, ry=0.2, typ="tet10", h=0.25, stufen=3, fy=None,
           anker_nur_zug=False, schalter=None, strebe=False):
    """Das Pruefmodell (siehe oben). ``Fv`` je Anker (0: ohne Vorspannung, dann
    ist die Stufe proportional), ``schalter`` {Feld: Wert} an Plastizitaet.
    ``strebe``: dazu ein Zugstab Rund 40 (nur Zug) von der Mitte der Kante x = L,
    oben, 2 m waagrecht in +x zu einem festen Punkt - der Schub drueckt ihn, er
    faellt aus, und die Ausfall-Iteration braucht zwei Kontaktlaeufe je Loesung."""
    from statik3d.model import Material, Section
    from tests import pruefkoerper as pk
    from tests import pruefmatrix as pm
    L, B, H, tol = 1.0, 1.0, 0.2, 1e-9
    m = pm.leeres_modell(fy=fy)
    m.materials["S"].nu = 0.3
    m.add_material(Material("Anker", E_ANKER, 0.3, 7850.0, ALPHA))
    pm.block(m, typ, (0, 0, 0), (L, B, H), h, "P")
    sohle = pm.seiten_von(m, "P", lambda x: abs(x[2]) < tol)
    pm.flaechenlager(m, sohle, "Starr", uz=dict(typ="rigid", failure="zug"),
                     ux=dict(typ="rigid", mu=mu, mu_ref=2), uy=dict(typ="rigid", mu=mu, mu_ref=2))
    deckel = pm.seiten_von(m, "P", lambda x: abs(x[2] - H) < tol)
    X = np.asarray(m.nodes, float)
    oben = pm.knoten_von(m, "P", lambda x: abs(x[2] - H) < tol)
    m.add_section(Section.circle("Rund 40", 0.040))
    A_s = np.pi * 0.040 ** 2 / 4.0
    m.add_load_case("LF1").gravity = [0.0, 0.0, 0.0]
    for i, (x, y) in enumerate(((0.25, 0.25), (0.75, 0.25), (0.75, 0.75), (0.25, 0.75))):
        k = min(oben, key=lambda n: (X[n, 0] - x) ** 2 + (X[n, 1] - y) ** 2)
        unten = m.add_node(X[k, 0], X[k, 1], X[k, 2] - 3.0)
        m.fix(int(unten), "all")
        e = m.add_element("truss", [int(k), unten], "Anker", "Rund 40", group=f"A{i}")
        if anker_nur_zug:
            m.elements[e].nur = "zug"
        m.add_member(f"A{i}", [e])
        if Fv:
            m.load_temp(e, -Fv / (E_ANKER * A_s * ALPHA), case="LF1")
    if strebe:
        k = min(oben, key=lambda n: (X[n, 0] - L) ** 2 + (X[n, 1] - 0.5 * B) ** 2)
        fest = m.add_node(X[k, 0] + 2.0, X[k, 1], X[k, 2])
        m.fix(int(fest), "all")
        e = m.add_element("truss", [int(k), fest], "Anker", "Rund 40", group="Strebe")
        m.elements[e].nur = "zug"
        m.add_member("Strebe", [e])
    V = 4.0 * (Fv or 1.0e6)
    pk.spannung_auf_seiten(m, deckel, lambda x: np.array([rx * mu * V / (L * B), ry * mu * V / (L * B), 0.0]))
    if not Fv:
        # ohne Vorspannung drueckt eine Flaechenlast mit derselben Summe
        pk.spannung_auf_seiten(m, deckel, lambda x: np.array([0.0, 0.0, -V / (L * B)]))
    m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=0.01, laststufen=stufen, iterationen=25,
                                     toleranz=1e-3)
    if fy is None:
        m.materials["S"].fy = 1e12
    for k, v in (schalter or {}).items():
        setattr(m.plastizitaet, k, v)
    return m


def rechnen(m):
    t0 = time.perf_counter()
    r = solver.solve_static(m)
    return r, time.perf_counter() - t0


def laeufe(r):
    return (r.info or {}).get("laeufe") or []


def u3(r):
    u = np.asarray(r.u, float)
    return u.reshape(-1, 6)[:, :3] if u.ndim == 1 else u[:, :3]


def max_du(r1, r2) -> float:
    return float(np.abs(u3(r1) - u3(r2)).max())


def bitgleich(r1, r2) -> bool:
    return (max_du(r1, r2) == 0.0
            and [(e.get("schritte"), e.get("grund"), e.get("warm")) for e in laeufe(r1)]
            == [(e.get("schritte"), e.get("grund"), e.get("warm")) for e in laeufe(r2)])


def kurz(r) -> str:
    return ", ".join(f"{e.get('art')}{'' if e.get('stufe') is None else ' ' + str(e.get('stufe'))}:"
                     f"{e.get('schritte')}{' warm' if e.get('warm') else ''}"
                     f"{' ' + e['grund'] if e.get('grund') else ''}" for e in laeufe(r))


# --------------------------------------------------------------------------
# Einstellungen: Vorgabe, nur abweichend gespeichert, NEUE_FELDER
# --------------------------------------------------------------------------
SCHALTER = {"kaltstart_nicht_proportional": True, "pendelschutz_winkel": True, "gleit_toleranz": 1.0e-6,
            "halbieren_lastabhaengig": False, "spannung_zuerst": True, "ausfall_warm": True}


def test_einstellungen():
    print("\n--- Einstellungen der Massnahmen ---")
    from statik3d.model import NEUE_FELDER, Model
    pz = pl.Plastizitaet()
    for k, v in SCHALTER.items():
        check(f"{k}: Vorgabe {v!r}, in NEUE_FELDER und NEU_14_10",
              getattr(pz, k, None) == v and NEUE_FELDER["plastizitaet"].get(k, object()) == v
              and pl.Plastizitaet.NEU_14_10.get(k, object()) == v,
              f"{getattr(pz, k, None)!r}")
    m = platte()
    d0 = m.to_dict()["plastizitaet"]
    check("  mit der Vorgabe nicht in der Datei", not any(k in d0 for k in SCHALTER), str(sorted(d0)))
    for k, v in SCHALTER.items():
        setattr(m.plastizitaet, k, (not v) if isinstance(v, bool) else 2.0 * v)
    d1 = m.to_dict()
    m2 = Model.from_dict(d1)
    check("  abweichend gespeichert und geladen",
          all(k in d1["plastizitaet"] for k in SCHALTER)
          and all(getattr(m2.plastizitaet, k) == getattr(m.plastizitaet, k) for k in SCHALTER),
          str({k: d1["plastizitaet"].get(k) for k in SCHALTER}))


# --------------------------------------------------------------------------
# Vorschlag 1: nicht proportionale erste Stufe startet beim Kontaktstatus kalt
# --------------------------------------------------------------------------
@contextlib.contextmanager
def iteration_mitschreiben(aufz: list):
    """plastizitaet.iteration umwickeln: plastischer Start (``start``) und
    Kontaktstart (kontakt.halter["start"]) beim Eintritt mitschreiben."""
    alt = pl.iteration

    def neu(*a, **kw):
        kn = kw.get("kontakt")
        aufz.append({"plast_start": kw.get("start"),
                     "kontakt_start": None if kn is None else kn.halter.get("start")})
        return alt(*a, **kw)
    pl.iteration = neu
    try:
        yield
    finally:
        pl.iteration = alt


def test_vorschlag1():
    print("\n--- Vorschlag 1: Kaltstart der ersten Stufe bei nicht proportionaler Last ---")
    check("Mass: lam F proportional (0), F_S + lam (F - F_S) nicht",
          pl.nicht_proportional(np.array([1.0, 2.0]), None, 0.5) == 0.0
          and pl.nicht_proportional(np.array([1.0, 2.0]), np.array([1.0, 0.0]), 1.0) == 0.0
          and pl.nicht_proportional(np.array([1.0, 2.0]), np.array([0.5, 1.0]), 1 / 3) < 1e-15
          and pl.nicht_proportional(np.array([1.0, 2.0]), np.array([1.0, 0.0]), 1 / 3) > 0.1,
          f"{pl.nicht_proportional(np.array([1.0, 2.0]), np.array([1.0, 0.0]), 1 / 3):.3f}")
    aus_l, an_l = [], []
    with iteration_mitschreiben(aus_l):
        r0, t0 = rechnen(platte(schalter={"kaltstart_nicht_proportional": False}))
    with iteration_mitschreiben(an_l):
        r1, t1 = rechnen(platte())
    l0, l1 = laeufe(r0), laeufe(r1)
    print(f"      aus: {kurz(r0)} ({t0:.1f} s); {solver.konvergenz_zustand(r0.info)[:60]}")
    print(f"      an:  {kurz(r1)} ({t1:.1f} s); {solver.konvergenz_zustand(r1.info)[:60]}")
    check("Schalter aus: Stufe 1 startet warm aus dem Vorlauf (Stand vor dem 14.10.2026)",
          len(l0) > 1 and l0[1].get("warm") and l0[1].get("start_von_lauf") == 1,
          f"warm {l0[1].get('warm') if len(l0) > 1 else None}, Start von Lauf "
          f"{l0[1].get('start_von_lauf') if len(l0) > 1 else None}")
    kz = r1.info.get("kontakt_kaltstart") or {}
    zeile = [z for z in (r1.info.get("plastizitaet") or {}).get("log", []) if "nicht proportional" in z]
    check("Schalter an: Stufe 1 startet beim Kontaktstatus kalt, Protokoll nennt den Rest",
          len(l1) > 1 and not l1[1].get("warm") and l1[1].get("start_von_lauf") is None
          and kz.get("anteil", 0.0) > pl.PROPORTIONAL_SCHRANKE and zeile and "kalt" in zeile[0],
          (zeile[0][:150] if zeile else "keine Zeile"))
    check("  nur der Kontaktstatus: plastischer Start unberuehrt, Kontaktstart None statt Vorlaufzustand",
          len(an_l) == 1 and len(aus_l) == 1 and an_l[0]["plast_start"] is aus_l[0]["plast_start"]
          and an_l[0]["kontakt_start"] is None and isinstance(aus_l[0]["kontakt_start"], dict),
          f"Kontaktstart aus {type(aus_l[0]['kontakt_start']).__name__ if aus_l else '-'}, "
          f"an {type(an_l[0]['kontakt_start']).__name__ if an_l else '-'}")
    check("  Stufe 1 kalt konvergiert, nicht vorläufig (warm: pendelt)",
          len(l1) > 1 and l1[1].get("konvergiert") and not r1.info.get("vorlaeufig")
          and len(l0) > 1 and not l0[1].get("konvergiert"),
          f"aus {l0[1].get('grund') if len(l0) > 1 else None!r}, an {l1[1].get('grund') if len(l1) > 1 else None!r}")
    # Proportional: ohne Vorspannung (Druck als Flaechenlast) und mit einer Laststufe
    for name, kw in (("ohne Vorspannung (F_S None)", dict(Fv=0.0, rx=0.3, ry=0.1)),
                     ("eine Laststufe (lam = 1)", dict(stufen=1))):
        a, _ta = rechnen(platte(schalter={"kaltstart_nicht_proportional": False}, **kw))
        b, _tb = rechnen(platte(**kw))
        check(f"proportional, {name}: an und aus bitgleich, Stufe 1 warm",
              bitgleich(a, b) and "kontakt_kaltstart" not in b.info
              and len(laeufe(b)) > 1 and laeufe(b)[1].get("warm"),
              f"max |du| {max_du(a, b):.1e} m; {kurz(b)}")


# --------------------------------------------------------------------------
# Vorschlag 2: Pendelschutz der Gleitrichtung mit Winkeltoleranz und Pruefung
# --------------------------------------------------------------------------
def zeilen(r, *woerter):
    return [z for z in (r.info or {}).get("contact_log") or [] if all(w in z for w in woerter)]


def test_vorschlag2():
    print("\n--- Vorschlag 2: Pendelschutz der Gleitrichtung (> 90 Grad), Pruefung nach dem Festhalten ---")
    # (a) Platte ohne Vorspannung, Schub 0,6 mu V nur in x: die Gleitrichtungen pendeln
    #     bis zum Deckel; mit der Regel haften die Pendler, und der Lauf ist schnell fertig
    kw = dict(Fv=0.0, rx=0.6, ry=0.0)
    a, ta = rechnen(platte(schalter={"pendelschutz_winkel": False}, **kw))
    b, tb = rechnen(platte(**kw))
    print(f"      aus: {kurz(a)} ({ta:.1f} s, {a.info.get('contact_iterations')} Runden)")
    print(f"      an:  {kurz(b)} ({tb:.1f} s, {b.info.get('contact_iterations')} Runden)")
    fest = zeilen(b, "Pendelschutz der Gleitrichtung -", "Knoten festgehalten")
    check("aus: Vorlauf und Stufen am Deckel, vorläufig (Stand vor dem 14.10.2026)",
          laeufe(a)[0].get("grund") == "deckel" and a.info.get("vorlaeufig"),
          f"Gründe {[e.get('grund') for e in laeufe(a)]}")
    check("an: Knoten festgehalten und geprüft, Ergebnis konvergiert, weniger als ein Drittel der Runden",
          fest and solver.konvergenz_zustand(b.info) == "konvergiert"
          and b.info.get("contact_iterations", 999) * 3 < a.info.get("contact_iterations", 0),
          (fest[-1][:150] if fest else "keine Zeile"))
    # (b) Pruefung greift: warm aus dem Vorlauf (Vorschlag 1 aus) zieht das Festhalten
    #     haftende Knoten bis 13 µm zurueck, und die Haftkraft schiebt sie dorthin
    c, _tc = rechnen(platte(schalter={"kaltstart_nicht_proportional": False}))
    l1 = laeufe(c)[1] if len(laeufe(c)) > 1 else {}
    verl = zeilen(c, "wirkt die Reibkraft der Bewegung nicht entgegen", "Winkel zwischen Reibkraft und Bewegung")
    check("Pruefung: Reibkraft wirkt der Bewegung nicht entgegen -> Grund „gleitrichtung“, vorläufig mit Stufe 1",
          l1.get("grund") == "gleitrichtung" and not l1.get("konvergiert") and verl
          and "Stufe 1" in ((c.info.get("vorlaeufig") or {}).get("text") or ""),
          (verl[0][:170] if verl else f"Grund {l1.get('grund')!r}"))
    # (c) wo nichts festgehalten wird, bitgleich
    for name, bau in (("Prüfplatte mit Vorgaben", lambda s: platte(schalter=s)),
                      ("Pendelmodell (tests.test_pendeln_periode2)", None)):
        if bau is None:
            from tests import test_pendeln_periode2 as tp2

            def bau(s):
                m_ = tp2.pendelmodell(0.5e6)
                for k_, v_ in s.items():
                    setattr(m_.plastizitaet, k_, v_)
                return m_
        r0, _t0 = rechnen(bau({"pendelschutz_winkel": False}))
        r1, _t1 = rechnen(bau({}))
        check(f"nichts festgehalten, {name}: an und aus bitgleich",
              bitgleich(r0, r1) and not zeilen(r1, "Pendelschutz der Gleitrichtung -"),
              f"max |du| {max_du(r0, r1):.1e} m; {kurz(r1)}")


# --------------------------------------------------------------------------
# Vorschlag 3: am Deckel nur halbieren, wenn das Pendeln vom Lastanteil abhaengt
# --------------------------------------------------------------------------
def _kn(laeufe_, an=True):
    """Ein _KontaktImNewton mit erfundenem Laufbuch (nur die Entscheidung am Deckel)."""
    from types import SimpleNamespace
    pz = pl.Plastizitaet(halbieren_lastabhaengig=an)
    res = SimpleNamespace(info={"laeufe": list(laeufe_)}, model=SimpleNamespace(plastizitaet=pz))
    return solver._KontaktImNewton(None, res, None, None, [], False)


def test_vorschlag3():
    print("\n--- Vorschlag 3: am Deckel nur halbieren, wenn das Pendeln vom Lastanteil abhängt ---")
    lauf = lambda nr, a, k=False: {"nr": nr, "konvergiert": k, "grund": "" if k else "deckel",
                                   "ausschlag": a, "zyklus": True}
    kn = _kn([lauf(1, 14.7e-6)])
    j1, z1 = kn.halbieren_am_deckel({"lauf": 0}, 1 / 3)
    kn.res.info["laeufe"].append(lauf(2, 12.6e-6))
    j2, z2 = kn.halbieren_am_deckel({"lauf": 1}, 1 / 6)
    j2b, z2b = kn.halbieren_am_deckel({"lauf": 1}, 1 / 6)
    check("Kriterium: erste Halbierung misst, Ausschlag 14,7 -> 12,6 µm bei halbem Anteil: nicht lastabhängig",
          j1 and "misst die halbe Stufe" in z1 and not j2 and "nicht vom Lastanteil ab" in z2
          and "85,7" in z2 and not j2b and z2b == "",
          z2[:160])
    kn = _kn([lauf(1, 669e-6)])
    kn.halbieren_am_deckel({"lauf": 0}, 1.0)
    kn.res.info["laeufe"].append(lauf(2, 314e-6))
    j3, z3 = kn.halbieren_am_deckel({"lauf": 1}, 0.5)
    check("  Ausschlag 669 -> 314 µm bei halbem Anteil (47 %): lastabhängig, halbieren",
          j3 and "hängt vom Lastanteil ab, die Stufe wird halbiert" in z3, z3[:160])
    j4, z4 = _kn([lauf(1, 14.7e-6)], an=False).halbieren_am_deckel({"lauf": 0}, 1 / 3)
    j5, _z5 = _kn([lauf(1, 0.0, k=True)]).halbieren_am_deckel({"lauf": 0}, 1 / 3)
    check("  ausgeschaltet halbiert jeder nicht konvergierte Lauf ohne Zeile; konvergiert: nichts",
          j4 and z4 == "" and not j5, f"{j4!r} {z4!r} {j5!r}")
    # Am Modell: gequetschter Block mit einer Laststufe (tests.test_plastizitaet)
    from tests import test_plastizitaet as tpl
    m0 = tpl._gequetschter_block()
    m0.plastizitaet.laststufen = 1
    r0, t0 = rechnen(m0)
    m1 = tpl._gequetschter_block()
    m1.plastizitaet.laststufen = 1
    m1.plastizitaet.halbieren_lastabhaengig = True
    r1, t1 = rechnen(m1)
    p0, p1 = r0.info.get("plastizitaet") or {}, r1.info.get("plastizitaet") or {}
    log1 = p1.get("log") or []
    print(f"      aus: halbiert {p0.get('halbiert')}, {r0.info.get('contact_iterations')} Runden, {t0:.1f} s, "
          f"{solver.konvergenz_zustand(r0.info)[:40]}")
    print(f"      an:  halbiert {p1.get('halbiert')}, {r1.info.get('contact_iterations')} Runden, {t1:.1f} s, "
          f"{solver.konvergenz_zustand(r1.info)[:60]}")
    check("gequetschter Block, Vorgabe aus: viermal halbiert, konvergiert (wie vor dem 14.10.2026)",
          p0.get("halbiert") == 4 and solver.konvergenz_zustand(r0.info) == "konvergiert"
          and not [z for z in (p0.get("log") or []) if "Lastanteil ab" in z],
          f"halbiert {p0.get('halbiert')}")
    nicht = [z for z in log1 if "hängt nicht vom Lastanteil ab" in z]
    ja = [z for z in log1 if "hängt vom Lastanteil ab, die Stufe wird halbiert" in z]
    check("  an: Kriterium im Protokoll, nach drei Halbierungen nicht lastabhängig, Ergebnis vorläufig",
          p1.get("halbiert") == 3 and nicht and ja and r1.info.get("vorlaeufig")
          and all(e.get("ausschlag") is not None for e in laeufe(r1)),
          (nicht[0][:170] if nicht else "keine Zeile"))


# --------------------------------------------------------------------------
# Vorschlag 4: Ingenieurkriterium zuerst Δσ, dann Δu; Residuum am Ende jeder Stufe
# --------------------------------------------------------------------------
def test_vorschlag4():
    print("\n--- Vorschlag 4: zuerst Δσ, dann Δu; Residuum am Ende jeder Stufe ---")
    m = platte()
    w = solver._weg_aus_spannung(m)
    m_aus = platte(schalter={"spannung_zuerst": False})
    check("Wegschranke aus der Spannungsschranke: 1 N/mm² / E mal Diagonale (1,43 m) = 6,8 µm; aus: 0",
          abs(w - 1e6 * np.sqrt(1.0 + 1.0 + 0.04) / 210e9) < 1e-12 and solver._weg_aus_spannung(m_aus) == 0.0,
          f"{w * 1e6:.3f} µm")
    # (a) Stempel auf Sockel (tests.test_plastizitaet, nur Kontakt): der ganz gleitende
    #     Stempel pendelt um 0,93 µm bei 0,57 N/mm² - vorher lag die Schranke bei 0,39 µm
    from tests import test_plastizitaet as tpl

    def stempel(an):
        m_ = tpl._drehlagerartiges_modell()
        m_.plastizitaet.an = False
        m_.plastizitaet.spannung_zuerst = an
        return m_
    a, ta = rechnen(stempel(False))
    b, tb = rechnen(stempel(True))
    ing = zeilen(b, "Abschluss nach dem Ingenieurkriterium", "Schranke")
    ua = float(np.linalg.norm(u3(a), axis=1).max())
    ub = float(np.linalg.norm(u3(b), axis=1).max())
    print(f"      aus: {kurz(a)} ({ta:.1f} s), an: {kurz(b)} ({tb:.1f} s); u_max {ua * 1e3:.5f} / {ub * 1e3:.5f} mm")
    check("Stempel: an früher angenommen (Δσ zuerst, Schranke 4,69 µm), u_max auf 0,1 % gleich",
          ing and "4,69 µm" in ing[0].replace(".", ",") and laeufe(b)[0]["schritte"] < laeufe(a)[0]["schritte"]
          and abs(ub - ua) <= 1e-3 * ua and b.info.get("contact_converged"),
          (ing[0][60:230] if ing else "keine Zeile"))
    # (b) Residuum am Ende jeder Stufe, geprueft und protokolliert
    r1, _t1 = rechnen(platte())
    r0, _t0 = rechnen(platte(schalter={"spannung_zuerst": False}))
    res1 = [z for z in (r1.info.get("plastizitaet") or {}).get("log", []) if "Residuum am Ende" in z]
    res0 = [z for z in (r0.info.get("plastizitaet") or {}).get("log", []) if "Residuum am Ende" in z]
    check("Residuum am Ende jeder Stufe protokolliert (drei Stufen, unter 1e-4), aus: keine Zeile, sonst bitgleich",
          len(res1) == 3 and all("nicht konvergiert" not in z for z in res1) and not res0 and bitgleich(r0, r1)
          and solver.konvergenz_zustand(r1.info) == "konvergiert",
          (res1[0][:150] if res1 else "keine Zeile"))
    # (c) Nicht konvergierter Kontaktlauf: Residuum gemeldet, entscheidet nicht (KONTAKT_IN_KONVERGENZ aus)
    r2, _t2 = rechnen(platte(schalter={"kaltstart_nicht_proportional": False, "pendelschutz_winkel": False}))
    res2 = [z for z in (r2.info.get("plastizitaet") or {}).get("log", []) if "Residuum am Ende" in z]
    check("  Stufe mit nicht konvergiertem Kontaktlauf: gemeldet, vorläufig gekennzeichnet, nicht zusätzlich verworfen",
          res2 and "der Kontaktlauf ist nicht konvergiert, die Stufe ist vorläufig gekennzeichnet" in res2[0]
          and (r2.info.get("plastizitaet") or {}).get("konvergiert") is True and r2.info.get("vorlaeufig"),
          (res2[0][:170] if res2 else "keine Zeile"))


# --------------------------------------------------------------------------
# Vorschlag 5: Warmstart der Kontaktlaeufe in der Ausfall-Iteration
# --------------------------------------------------------------------------
@contextlib.contextmanager
def kontaktlaeufe_mitschreiben(aufz: list, unkonvergiert=()):
    """solver.solve_with_contact umwickeln (nur die aeusseren Aufrufe): Start, Runden
    und zurueckgegebener Zustand je Lauf. ``unkonvergiert``: Nummern (ab 0) der
    Laeufe, deren Zustand als nicht konvergiert zurueckgemeldet wird."""
    alt = solver.solve_with_contact
    tiefe = [0]

    def neu(*a, **kw):
        tiefe[0] += 1
        try:
            erg = alt(*a, **kw)
        finally:
            tiefe[0] -= 1
        if tiefe[0] == 0:
            z = erg[4].get("contact_state")
            if len(aufz) in unkonvergiert and isinstance(z, dict):
                z = dict(z, konvergiert=False)
                erg[4]["contact_state"] = z
            aufz.append({"start": kw.get("start"), "fortsetzung": kw.get("fortsetzung"),
                         "runden": int(erg[4].get("contact_iterations", 0) or 0), "zustand": z})
        return erg
    solver.solve_with_contact = neu
    try:
        yield
    finally:
        solver.solve_with_contact = alt


def test_vorschlag5():
    print("\n--- Vorschlag 5: Warmstart in der Ausfall-Iteration, vom letzten konvergierten Zustand ---")
    # (a) Platte mit einer Strebe "nur Zug", die der Schub drueckt: je Loesung zwei Laeufe
    l0, l1 = [], []
    with kontaktlaeufe_mitschreiben(l0):
        a, ta = rechnen(platte(strebe=True, schalter={"ausfall_warm": False}))
    with kontaktlaeufe_mitschreiben(l1):
        b, tb = rechnen(platte(strebe=True))
    n0, n1 = sum(x["runden"] for x in l0), sum(x["runden"] for x in l1)
    print(f"      aus: {len(l0)} Kontaktläufe, {n0} Runden, {ta:.1f} s; an: {len(l1)} Läufe, {n1} Runden, {tb:.1f} s")
    check("aus: jeder Kontaktlauf der Ausfall-Iteration kalt (Stand vor dem 14.10.2026)",
          l0 and all(x["start"] is None for x in l0) and len(l0) == 2 * len(laeufe(a)),
          f"{len(l0)} Läufe, {len(laeufe(a))} Lösungen")
    zweite = l1[1::2]
    check("an: der zweite Lauf jeder Lösung startet beim Zustand des ersten, fortgesetzt",
          len(l1) == len(l0) and all(z["start"] is v["zustand"] and z["fortsetzung"]
                                     for v, z in zip(l1[0::2], zweite)),
          f"{len(l1)} Läufe")
    check("  weniger als 60 % der Runden, dasselbe Ergebnis (|Δu| < 1e-9 m), konvergiert",
          n1 < 0.6 * n0 and max_du(a, b) < 1e-9 and solver.konvergenz_zustand(b.info) == "konvergiert"
          and solver.konvergenz_zustand(a.info) == "konvergiert",
          f"{n1} statt {n0} Runden, max |Δu| {max_du(a, b):.1e} m")
    # (b) Vom letzten konvergierten Zustand: meldet der erste Lauf "nicht konvergiert",
    #     beginnt der zweite beim angebotenen Start, nicht bei diesem Zustand
    m = platte(strebe=True)
    system = solver.StaticSystem(m)
    F = solver.case_loads(m, {"LF1": 1.0})[0]
    n0a = solver._anfang_ausfall(m, {"LF1": 1.0}, None, None)
    vor = []
    with kontaktlaeufe_mitschreiben(vor):
        solver.solve_with_ausfall(m, system, F, n0=n0a)
    start = vor[-1]["zustand"]
    mit = []
    with kontaktlaeufe_mitschreiben(mit, unkonvergiert=(0,)):
        solver.solve_with_ausfall(m, system, F, n0=n0a, start=start, fortsetzung=True)
    check("  vom letzten konvergierten: nach einem nicht konvergierten Lauf wieder der angebotene Start",
          len(mit) == 2 and mit[0]["start"] is start and mit[1]["start"] is start
          and mit[0]["zustand"].get("konvergiert") is False,
          f"Start 2. Lauf ist der angebotene: {len(mit) == 2 and mit[1]['start'] is start}")
    # (c) eps_p aus verworfenen Iterationen wird nicht aufsummiert: mit Fliessen dieselben
    #     Rueckfuehrungen und dasselbe eps_p, obwohl jede Loesung zwei Kontaktlaeufe hat
    #     (auf 1e-5: die Kontaktlaeufe enden am Residuum 1e-6 der Kontaktkraft, nicht bitgleich)
    zaehler = {"n": 0}
    alt_s = pl.schritt

    def schritt(*a_, **kw_):
        zaehler["n"] += 1
        return alt_s(*a_, **kw_)
    erg = {}
    pl.schritt = schritt
    try:
        for an in (False, True):
            zaehler["n"] = 0
            lz = []
            with kontaktlaeufe_mitschreiben(lz):
                r, _t = rechnen(platte(strebe=True, fy=30e6, schalter={"ausfall_warm": an}))
            pz = r.info.get("plastizitaet") or {}
            erg[an] = (r, zaehler["n"], float(pz.get("eps_p_max") or 0.0), int(pz.get("iterationen") or 0),
                       sum(x["runden"] for x in lz), len(lz))
    finally:
        pl.schritt = alt_s
    (ra, sa, ea, na, ka, la), (rb, sb, eb, nb, kb, lb) = erg[False], erg[True]
    print(f"      Fließen aus: {sa} Rückführungen, ε_p {ea * 100:.5f} %, {na} Newton, {ka} Runden in {la} Läufen; "
          f"an: {sb}, {eb * 100:.5f} %, {nb}, {kb} Runden in {lb} Läufen")
    check("  mit Fließen: Rückführungen und Newton-Schritte gleich, ε_p auf 1e-5 gleich, weniger Runden",
          sa == sb and na == nb and ea > 0 and abs(eb - ea) <= 1e-5 * ea and kb < ka and la == lb == 2 * len(laeufe(ra)),
          f"{sb} Rückführungen bei {lb} Kontaktläufen, Δε_p {abs(eb - ea):.1e}")


def main() -> int:
    for t in (test_einstellungen, test_vorschlag1, test_vorschlag2, test_vorschlag3, test_vorschlag4,
              test_vorschlag5):
        try:
            t()
        except Exception as ex:             # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{t.__name__} laeuft ohne Ausnahme", False, str(ex)[:120])
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print("\n" + "=" * 60)
    print(f"Ergebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
