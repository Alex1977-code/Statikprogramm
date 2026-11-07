"""Starre Scheibe ueber einer Bohrung: Lochrand starr oder Kreisring verteilend (seit 16.10.2026).

Entscheidung des Anwenders vom 16.10.2026: „Mutterkraft an allen 64 Scheiben
über einen Kreisring einleiten, verteilend (RBE3, flächenanteilig), nicht
starr … Innen-Ø = Bohrung, Außen-Ø = Auflage von Mutter bzw. Scheibe … Bis
dahin Normmaße der Mutter bzw. Scheibe ansetzen und als Annahme
kennzeichnen.“ Dazu die deutliche Warnung vor plastischen Rechnungen.

Pruefkoerper: Blech 60 x 60 x 20 mm (S355) mit einer Bohrung Ø 20 mm, die
starre Scheibe aus RFEM genau ueber der Bohrung, in ihrer Mitte das Ende einer
Schraube Rund 20 (Vorspannkraft als Soll nach Verankerung), die durch die
Bohrung nach unten zu einem festen Punkt laeuft; das Blech liegt unten fest
auf. Der Kreisring hat das Normmass der Unterlegscheibe M20 nach ISO 7089
(37 mm, Annahme), also A_Ring = pi/4 (37^2 - 20^2) = 761,0 mm2.

Geprueft wird:
1. Normmasse und Kennzeichen „Annahme“; Umstellen nur auf Anweisung, mit
   Rueckgaengig; alte Einstellung (leer) = Lochrand.
2. Die Kopplung: ein RBE3 „Scheibe …“ am Stabende, die Knoten in der
   Ebene zwischen Innen- und Aussenradius, Gewichte = Ringflaeche, bei tet10
   die Seitenmitten mit; keine starre Kopplung mehr.
3. Elastisch und plastisch, tet4 und tet10: Kraftsumme und Moment
   (stabeinleitung.pruefen), mittlere Pressung im Ring ≈ F/A_Ring, die
   plastische Rechnung konvergiert mit dem Ring; mit dem Lochrand die
   netzabhaengige Spitze.
4. Die Warnung „Kraft ohne Fläche“ verschwindet mit dem Ring.
5. Mindestzahl und Rueckfall mit klarer Meldung.
6. Speichern und Laden; eine Datei ohne die Einstellung bleibt bitgleich.
7. Plastischer Start ohne Oberflaeche: deutliche Protokollzeile.

Aufruf:  python -m tests.test_scheibe_kreisring
"""
import json
import math
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import fugen, mesher, solver, spitzenstellen as sp          # noqa: E402
from statik3d import scheibeneinleitung as SCH                           # noqa: E402
from statik3d import stabeinleitung as SE                                # noqa: E402
from statik3d.model import Model, Section                                # noqa: E402

from tests.test_netzfeld import platte_mit_bohrungen                     # noqa: E402

RESULTS = []

A_, T_ = 0.06, 0.02
R_B = 0.010                       # Bohrung Ø 20
F_ = 150e3                        # Schraubenkraft [N]
D_A = 0.037                       # ISO 7089 M20
A_RING = math.pi / 4 * (D_A ** 2 - (2 * R_B) ** 2)


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:84s} {str(detail)[:200]}")
    return ok


def blech(h: float = 0.004, ordnung: int = 2, ring: bool = False, plast: bool = False, F: float = F_,
          vernetzen: bool = True) -> Model:
    """Das Blech mit Scheibe und Schraube, vernetzt (eigene Ziellaenge ``h``,
    ``ordnung`` 1 = tet4, 2 = tet10)."""
    m, _k = platte_mit_bohrungen(a=A_, b=A_, t=T_, bohrungen=((A_ / 2, A_ / 2, R_B),), material="S355")
    sec = Section("Rund 20", math.pi * 0.02 ** 2 / 4, math.pi * 0.02 ** 4 / 64, math.pi * 0.02 ** 4 / 64,
                  math.pi * 0.02 ** 4 / 32)
    sec.typ, sec.h, sec.b, sec.r = "circle", 0.02, 0.02, 0.01
    m.add_section(sec)
    m.add_flaeche("F1", ["B1O1", "B1O2"], material="S355")
    m.flaechen["F1"].steifigkeit = "starr"
    mitte = m.add_node(A_ / 2, A_ / 2, T_)
    fuss = m.add_node(A_ / 2, A_ / 2, -0.2)
    e = m.add_element("truss", [mitte, fuss], "S355", "Rund 20", group="Schraube")
    m.add_member("S1", [e])
    m.fix(fuss, "all")
    lc = m.add_load_case("LF1")
    lc.gravity = [0.0, 0.0, 0.0]
    m.add_vorspannung("S1", F, case="LF1", sollkraft=True)
    m.active_case = "LF1"
    if ring:
        SCH.umstellen(m, ["F1"], SCH.RING)
    m.plastizitaet.an = bool(plast)
    m.netz.dichte = "eigene"
    m.netz.ziellaenge = h
    m.netz.ordnung = ordnung
    m.netz.sweep = "aus"
    if vernetzen:
        mesher.modell_vernetzen(m, [], workers=1)
        unten = [i for i in range(m.nn) if abs(m.nodes[i][2]) < 1e-9 and i != fuss]
        for i in unten:
            m.fix(i, [0, 1, 2])
    m._mitte = mitte
    return m


def ring_sk(m):
    return [sk for sk in m.starrkoerper if SE.ist_scheibenkopplung(sk)]


def deckelelemente(m, ri, ra):
    """(Element, Seitenflaeche) der Volumenelemente mit einer Seite in der
    Oberseite, deren Mittelpunkt zwischen ri und ra um die Bohrung liegt."""
    X = np.asarray(m.nodes, float)
    aus = []
    for i, e in enumerate(m.elements):
        if e.typ not in ("tet4", "tet10"):
            continue
        ecken = [int(x) for x in e.nodes[:4]]
        oben = [k for k in ecken if abs(X[k][2] - T_) < 1e-9]
        if len(oben) != 3:
            continue
        P = X[oben]
        c = P.mean(axis=0)
        r = math.hypot(c[0] - A_ / 2, c[1] - A_ / 2)
        if ri <= r <= ra:
            aus.append((i, 0.5 * float(np.linalg.norm(np.cross(P[1] - P[0], P[2] - P[0])))))
    return aus


# --------------------------------------------------------------------------
def test_normmasse():
    print("\n--- 1. Normmaße als Annahme ---")
    for d, soll, text in ((0.016, 0.030, "ISO 7089 M16"), (0.020, 0.037, "ISO 7089 M20"),
                          (0.040, 0.060, "ISO 4032 M42"), (0.018, 0.0277, "ISO 4032 M20")):
        da, q = SCH.normmass(d, 0.0)
        check(f"Stab Ø {d * 1e3:.0f} mm: Außen-Ø {soll * 1e3:.1f} mm aus {text}",
              abs(da - soll) < 1e-9 and q.startswith(text), q)
    da, q = SCH.normmass(0.040, 0.061)
    check("ein Normmaß, das nicht größer als die Bohrung ist, gilt nicht", da == 0.0 and "nicht größer" in q, q)


def test_umstellen():
    print("\n--- 1b. Umstellen nur auf Anweisung, mit Rückgängig ---")
    m = blech(vernetzen=False)
    z = SCH.scheiben(m, mit_koerper=False)
    check("die Scheibe ist eine Kreisscheibe mit Stabende, Bohrung Ø 20, Vorgabe Lochrand",
          len(z) == 1 and z[0]["einleitung"] == SCH.LOCHRAND and abs(z[0]["d_bohrung"] - 0.02) < 1e-6
          and z[0]["stab"] == "S1", f"{[(x['name'], x['einleitung'], x['d_bohrung'], x['stab']) for x in z]}")
    check("Normmaß-Vorschlag 37 mm und die Pressung aus der Vorspannung F/A_Ring",
          abs(z[0]["vorschlag"] - D_A) < 1e-9 and abs(z[0]["pressung"] - F_ / A_RING) < 1e-6 * F_ / A_RING,
          f"{z[0]['vorschlag'] * 1e3:.1f} mm, {z[0]['pressung'] / 1e6:.1f} N/mm²")
    erg = SCH.alle_auf_kreisring(m)
    e = m.flaechen["F1"].einleitung
    check("alle auf Kreisring: Normmaß als Annahme, Innen-Ø aus der Geometrie (0)",
          erg["umgestellt"] == ["F1"] and e["art"] == "ring" and e["annahme"] is True
          and abs(e["d_aussen"] - D_A) < 1e-12 and e["d_innen"] == 0.0 and "ISO 7089 M20" in e["quelle"], f"{e}")
    check("… ein zweites Mal ist nichts zu tun", SCH.alle_auf_kreisring(m)["umgestellt"] == [])
    SCH.zuruecksetzen(m, erg["vorher"])
    check("Rückgängig stellt den Lochrand wieder her (leer)", m.flaechen["F1"].einleitung == {})
    erg2 = SCH.umstellen(m, ["F1"], SCH.RING, d_aussen=0.040)
    e = m.flaechen["F1"].einleitung
    check("ein eingetragenes Maß trägt kein Kennzeichen „Annahme“",
          erg2["umgestellt"] == ["F1"] and e["annahme"] is False and abs(e["d_aussen"] - 0.040) < 1e-12, f"{e}")
    erg3 = SCH.umstellen(m, ["F1"], SCH.RING, d_aussen=0.015)
    check("Außen-Ø unter der Bohrung wird abgewiesen", erg3["offen"] and m.flaechen["F1"].einleitung == e,
          f"{erg3['offen']}")


def test_kopplung():
    print("\n--- 2. Kopplung: RBE3 am Kreisring ---")
    for ordnung, typ in ((1, "tet4"), (2, "tet10")):
        m = blech(ordnung=ordnung, ring=True)
        sks = ring_sk(m)
        starr = [k for k in m.kopplungen if str(k.gruppe).startswith(fugen.STARR_GRUPPE)]
        check(f"{typ}: genau ein RBE3 „Scheibe F1“ am Stabende, keine starre Kopplung mehr",
              len(sks) == 1 and sks[0].master == m._mitte and not starr, f"{len(sks)} RBE3, {len(starr)} starr")
        if not sks:
            continue
        sk = sks[0]
        X = np.asarray(m.nodes, float)[sk.slaves]
        r = np.hypot(X[:, 0] - A_ / 2, X[:, 1] - A_ / 2)
        w = np.asarray(sk.gewichte)
        h = m.netz.ziellaenge
        check(f"{typ}: alle Knoten in der Ebene der Scheibe, zwischen Bohrung und Außenrand (± eine Seite)",
              np.all(np.abs(X[:, 2] - T_) < 1e-9) and r.min() >= R_B - 1e-9 and r.max() <= D_A / 2 + 2 * h,
              f"{len(sk.slaves)} Knoten, r {r.min() * 1e3:.2f} … {r.max() * 1e3:.2f} mm")
        check(f"{typ}: Gewichtssumme = Ringfläche (Teilzellen an den Rändern)",
              abs(w.sum() - A_RING) < 0.01 * A_RING, f"{w.sum() * 1e6:.2f} mm² gegen {A_RING * 1e6:.2f} mm²")
        tragend = int(np.sum(np.abs(w) > 1e-12 * np.abs(w).max()))
        check(f"{typ}: genug tragende Knoten (mindestens {SCH.MINDEST_KNOTEN})",
              tragend >= SCH.MINDEST_KNOTEN, f"{tragend}")
        if ordnung == 2:
            ecken = {int(x) for e in m.elements if e.typ == "tet10" for x in e.nodes[:4]}
            mitten = [s for s in sk.slaves if s not in ecken]
            check("tet10: die Seitenmitten zählen mit (konsistente Knotenflächen)",
                  len(mitten) > 0 and all(abs(w[list(sk.slaves).index(s)]) > 0 for s in mitten),
                  f"{len(mitten)} Seitenmitten von {len(sk.slaves)} Knoten")
        check(f"{typ}: der Kommentar nennt Ring, Fläche und die Annahme",
              sk.kommentar.startswith("ring 20.000/37.000") and "Annahme ISO 7089 M20" in sk.kommentar, sk.kommentar)


_ERG = {}


def rechnen(h, ordnung, ring, plast, F=F_):
    """(Modell, Ergebnis oder None, Meldungen, Abbruchtext) - ein Abbruch der
    Rechnung (singulaer, weggeflossen) ist ein Ergebnis dieser Probe."""
    schl = (h, ordnung, ring, plast, F)
    if schl not in _ERG:
        m = blech(h=h, ordnung=ordnung, ring=ring, plast=plast, F=F)
        meld = []
        try:
            r, fehler = solver.solve_static(m, progress=lambda t, *a: meld.append(str(t)), case="LF1",
                                            workers=1), ""
        except RuntimeError as ex:
            r, fehler = None, str(ex).split(" - ")[0]
        _ERG[schl] = (m, r, meld, fehler)
    return _ERG[schl]


def sigma_v_max(m, r, radius):
    """Groesste Vergleichsspannung der Knoten der Oberseite bis ``radius`` um die Bohrung."""
    X = np.asarray(m.nodes, float)
    vol = {int(x) for e in m.elements if e.typ in ("tet4", "tet10") for x in e.nodes}
    sel = [i for i in vol if abs(X[i][2] - T_) < 1e-9 and math.hypot(X[i][0] - A_ / 2, X[i][1] - A_ / 2) <= radius]
    return float(np.max(np.asarray(r.node_vm)[sel]))


def test_elastisch():
    print("\n--- 3. Elastisch: Kraftsumme, Moment, Pressung ---")
    for ordnung, typ in ((1, "tet4"), (2, "tet10")):
        m, r, _meld, _f = rechnen(0.004, ordnung, True, False)
        info = r.info.get("stabenden_kraftsumme") or {}
        check(f"{typ}: Kraftsumme und Moment der Kopplung gleich der Stabendkraft (stabeinleitung.pruefen)",
              info.get("geprueft") == 1 and not info.get("abweichend"),
              f"dF {info.get('max_dF', -1):.3g} N, dM {info.get('max_dM', -1):.3g} Nm, "
              f"Toleranz {info.get('toleranz', -1):.3g}")
        z = (info.get("je_stabende") or [{}])[0]
        Fz = -float(z.get("F_kopplung", [0, 0, 0])[2])
        check(f"{typ}: die Kopplung drückt mit F = {F_ / 1e3:.0f} kN auf den Ring",
              abs(Fz - F_) < 1e-3 * F_, f"{Fz / 1e3:.3f} kN")
        sel = deckelelemente(m, R_B, D_A / 2)
        sz = np.array([r.solid_res[i][2] for i, _a in sel])
        a = np.array([a for _i, a in sel])
        p = -float((sz * a).sum() / a.sum())
        check(f"{typ}: mittlere Pressung der obersten Elemente im Ring ≈ F/A_Ring (± 25 %)",
              abs(p - F_ / A_RING) < 0.25 * F_ / A_RING,
              f"{p / 1e6:.1f} N/mm² gegen {F_ / A_RING / 1e6:.1f} N/mm² ({len(sel)} Elemente)")


def test_netzabhaengig():
    print("\n--- 3b. Netzabhängigkeit: Lochrand wächst, Ring bleibt ---")
    werte = {}
    for ring in (False, True):
        for h in (0.004, 0.002):
            m, r, _, _f = rechnen(h, 2, ring, False)
            werte[(ring, h)] = sigma_v_max(m, r, D_A / 2 + 0.002)
    loch = werte[(False, 0.002)] / werte[(False, 0.004)]
    ringq = werte[(True, 0.002)] / werte[(True, 0.004)]
    detail = (f"Lochrand {werte[(False, 0.004)] / 1e6:.0f} → {werte[(False, 0.002)] / 1e6:.0f} N/mm², "
              f"Ring {werte[(True, 0.004)] / 1e6:.0f} → {werte[(True, 0.002)] / 1e6:.0f} N/mm²")
    check("tet10, h 4 → 2 mm: die Spitze am Lochrand wächst stärker als am Ring", loch > ringq, detail)
    check("… und der Ring bleibt unter der Lochrandspitze", werte[(True, 0.002)] < werte[(False, 0.002)], detail)


#: Kraft fuer die plastische Probe: 300 kN, im Ring 394 N/mm² = 1,11 f_y (S355) -
#: dort fliesst es unter dem Ring ein wenig, am Lochrand (300 kN auf 62,8 mm
#: Umfang) weit
F_PLAST = 300e3


def test_plastisch():
    print("\n--- 3c. Plastisch: Ring konvergiert, Lochrand fließt weg ---")
    for ordnung, typ in ((1, "tet4"), (2, "tet10")):
        _m, r, meld, fehler = rechnen(0.004, ordnung, True, True, F_PLAST)
        pz = (r.info.get("plastizitaet") or {}) if r is not None else {}
        info = (r.info.get("stabenden_kraftsumme") or {}) if r is not None else {}
        check(f"{typ}, Kreisring, 300 kN (1,11 f_y im Ring): konvergiert, Kraftsumme stimmt",
              not fehler and pz.get("konvergiert") is True and info.get("geprueft") == 1
              and not info.get("abweichend"),
              fehler or f"konvergiert {pz.get('konvergiert')}, eps_p max {pz.get('eps_p_max')}, "
                        f"fließend {pz.get('fliessend')}, dF {info.get('max_dF', -1):.3g} N")
        check(f"{typ}, Kreisring: keine deutliche Warnung vor dem Start",
              not any("BITTE LESEN" in z for z in meld), "")
        _m2, r2, meld2, fehler2 = rechnen(0.004, ordnung, False, True, F_PLAST)
        pz2 = (r2.info.get("plastizitaet") or {}) if r2 is not None else {}
        weg = bool(fehler2) or pz2.get("konvergiert") is not True
        check(f"{typ}, Lochrand: weggeflossen (Abbruch, nicht konvergiert) oder eps_p weit über dem Ring",
              weg or float(pz2.get("eps_p_max") or 0) > 3 * float(pz.get("eps_p_max") or 0),
              fehler2 or f"konvergiert {pz2.get('konvergiert')}, eps_p max {pz2.get('eps_p_max')} "
                         f"(Ring {pz.get('eps_p_max')})")
        check(f"{typ}, Lochrand: vor dem Start eine deutliche Protokollzeile",
              any("WARNUNG – BITTE LESEN" in z and "Lochrand" in z for z in meld2),
              next((z for z in meld2 if "BITTE LESEN" in z), "")[:160])
    _m3, _r3, meld3, _f3 = rechnen(0.004, 1, False, False)
    check("elastisch, Lochrand: keine deutliche Zeile (bleibt bei Warnung und Zone)",
          not any("BITTE LESEN" in z for z in meld3), "")


def test_warnung():
    print("\n--- 4. Warnung „Kraft ohne Fläche“ ---")
    m = blech(ring=False)
    st = [s for s in sp.kandidaten(m, zonen=False) if s["quelle"] == sp.STARRE_SCHEIBE]
    check("Lochrand: die Scheibe ist eine Stelle „Kraft ohne Fläche“ (Lochrand)",
          len(st) == 1 and st[0]["lochrand"], f"{[(s['art'], s['n_knoten'], s.get('lochrand')) for s in st]}")
    SCH.alle_auf_kreisring(m)
    log = []
    erg = fugen.starre_kopplungen_erneuern(m, log)
    st = [s for s in sp.kandidaten(m, zonen=False) if s["quelle"] == sp.STARRE_SCHEIBE]
    check("nach dem Umstellen: neu gekoppelt, keine Stelle mehr (die Kraft geht über eine Fläche)",
          erg["geaendert"] and not st and len(ring_sk(m)) == 1, f"{[(s['art'], s['n_knoten']) for s in st]}")
    check("… das Protokoll nennt den Kreisring, die Annahme und die Pressung",
          any("über einen Kreisring" in z for z in log) and any("Annahme ISO 7089 M20" in z and "N/mm²" in z
                                                                 for z in log), " | ".join(log)[:300])
    log2 = []
    check("… ein zweites Erneuern ändert nichts", not fugen.starre_kopplungen_erneuern(m, log2)["geaendert"]
          and not log2, " | ".join(log2))
    m.flaechen["F1"].einleitung = {}
    log3 = []
    fugen.starre_kopplungen_erneuern(m, log3)
    check("zurück auf Lochrand: wieder starr gekoppelt, das Protokoll sagt es",
          not ring_sk(m) and any(str(k.gruppe) == "starr F1" for k in m.kopplungen)
          and any("wieder starr am Lochrand" in z for z in log3), " | ".join(log3)[:200])


def test_pressung_hinweis():
    print("\n--- 4b. Pressung über 3 f_y: „Auflage prüfen (Zeichnungsmaß)“ ---")
    m = blech(F=900e3)
    SCH.alle_auf_kreisring(m)
    log = []
    fugen.starre_kopplungen_erneuern(m, log)
    z = SCH.scheiben(m)[0]
    check("die Zeile der Scheibe trägt Pressung, f_y und den Hinweis",
          z["fy"] == 355e6 and z["verhaeltnis"] > 3 and z["hinweis"] == SCH.AUFLAGE_PRUEFEN,
          f"{SCH.pressung_text(z)}, {z['hinweis']}")
    check("… und das Protokoll eine WARNUNG mit dem Hinweis",
          any(w.startswith("WARNUNG") and SCH.AUFLAGE_PRUEFEN in w for w in log), " | ".join(log)[-250:])


def test_mindestzahl_rueckfall():
    print("\n--- 5. Mindestzahl und Rückfall ---")
    m = blech(ring=True, vernetzen=False)
    alt = SCH.MINDEST_KNOTEN
    SCH.MINDEST_KNOTEN = 10 ** 6
    try:
        log = []
        mesher.modell_vernetzen(m, log, workers=1)
    finally:
        SCH.MINDEST_KNOTEN = alt
    check("unter der Mindestzahl: WARNUNG mit Knotenzahl, der Ring bleibt",
          any("nur" in z and "tragende Knoten im Ring" in z for z in log) and len(ring_sk(m)) == 1,
          next((z for z in log if "tragende Knoten" in z), ""))
    # ohne Stab in der Mitte gibt es keinen Bezugsknoten
    m = blech(ring=True)
    m.elements = [e for e in m.elements if e.typ != "truss"]
    m.members = {}
    log = []
    b = fugen.starre_flaechen_koppeln(m, log)
    check("ohne Stabende in der Mitte: Rückfall auf den Lochrand mit WARNUNG",
          b["rueckfall"] and not ring_sk(m) and any("bleibt am Lochrand starr" in z for z in log),
          " | ".join(z for z in log if "Kreisring" in z))


def test_speichern_laden():
    print("\n--- 6. Speichern und Laden ---")
    d = tempfile.mkdtemp()
    m = blech(vernetzen=False)
    p0 = os.path.join(d, "ohne.json")
    m.save(p0)
    roh = json.load(open(p0, encoding="utf-8"))
    check("ohne Einstellung steht der Schlüssel nicht in der Datei",
          all("einleitung" not in f for f in roh["flaechen"]), "")
    m2 = Model.load(p0)
    p1 = os.path.join(d, "ohne2.json")
    m2.save(p1)
    check("… und die Datei bleibt beim Speichern bitgleich", open(p0, "rb").read() == open(p1, "rb").read())
    SCH.alle_auf_kreisring(m)
    p2 = os.path.join(d, "ring.json")
    m.save(p2)
    m3 = Model.load(p2)
    check("die Einstellung kommt mit Maß, Annahme und Quelle zurück",
          m3.flaechen["F1"].einleitung == m.flaechen["F1"].einleitung, f"{m3.flaechen['F1'].einleitung}")
    m4 = blech(ring=True)
    p3 = os.path.join(d, "netz.json")
    m4.save(p3)
    m5 = Model.load(p3)
    log = []
    check("mit Netz: nach dem Laden stimmt der Bestand, nichts wird neu gekoppelt",
          not fugen.starre_kopplungen_erneuern(m5, log)["geaendert"] and len(ring_sk(m5)) == 1, " | ".join(log))


def main():
    for t in (test_normmasse, test_umstellen, test_kopplung, test_warnung, test_pressung_hinweis,
              test_mindestzahl_rueckfall, test_speichern_laden, test_elastisch, test_netzabhaengig,
              test_plastisch):
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
