"""Temperaturlasten wirken in jeder schrittweisen Rechnung sofort voll
(Entscheidung des Anwenders vom 10.10.2026): „temperaturlast immer sofort
vorhanden berücksichtigen denn ohne vorspannung mehr verformung und dann
längere rechenzeit“.

Anlass war das Drehlager: die Ankervorspannung steht dort als Temperaturlast
im LF1 (dT -445,6 K) und wuchs bis dahin mit den Laststufen der Plastizitaet
mit - in der ersten von drei Stufen wirkte ein Drittel der Vorspannung.

Geprueft am vorgespannten Wuerfel: ein Hexaeder 1 x 1 x 1 m (S355, fliesst),
vier Ankerstaebe vom Kopf zum Boden (Temperaturlast dT -387,5 K), dazu eine
Drucklast auf den Kopf. Die Rechnung ist einachsig und hat eine geschlossene
Loesung (bilinear, Verfestigung E_t/E = 2 %); Wuerfel und Anker werden
monoton belastet, das Endergebnis haengt also nicht vom Lastweg ab.

* In Laststufe 1 (von 3) ist die Verschiebung die der vollen Temperatur und
  eines Drittels der uebrigen Last - verglichen mit zwei linearen Rechnungen
  (nur Temperatur, nur Last). Bis zum 10.10.2026 war es ein Drittel von
  beiden: Ankerkraft 51,6 statt 170,0 MN.
* Das Endergebnis trifft die geschlossene Loesung.
* Ebenso im Weg "anfangsdehnung", in einer Kombination (die Temperatur mit
  ihrem Kombinationsfaktor sofort voll), beim Halbieren einer Stufe und in der
  Theorie III. Ordnung.

Aufruf:  python -m tests.test_temperatur_sofort
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import plastizitaet as pl, solver, theorie3          # noqa: E402
from statik3d.model import Material, Model, NodalLoad, Section    # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:78s} {detail}")
    return ok


def nahe(name, ist, soll, tol, einheit=""):
    ist, soll = float(ist), float(soll)
    abw = abs(ist - soll) / (abs(soll) if abs(soll) > 1e-14 else 1.0)
    return check(name, abw <= tol, f"ist {ist:.6g} soll {soll:.6g} ({abw * 100:.3g} %) {einheit}")


E, NU, FY, ALPHA = 210e9, 0.3, 355e6, 1.2e-5
AB, LB = 0.05, 2.0          # Ankerquerschnitt je Stab [m2], Ankerlaenge [m]
DT, P = -387.5, 2.5e8       # Abkuehlung der Anker [K], Drucklast auf den Kopf [N]
ET = 0.02                   # Verfestigung E_t/E

#: Satz fuer das Protokoll - auch in der Theorie III. Ordnung
SATZ = "Temperaturlasten wirken ab der ersten Laststufe voll"


def _wuerfel(lastfaelle=("LF1",), stufen=3, verfahren="tangente"):
    """Der vorgespannte Wuerfel. ``lastfaelle``: ein Name - Temperatur und Last
    darin; zwei Namen - die Temperatur im ersten, die Last im zweiten.
    Rueckgabe (Modell, Kopfknoten, Bodenknoten der Anker)."""
    m = Model("Vorspannung")
    m.add_material(Material("S355", E=E, nu=NU, rho=7850, fy=FY))
    m.add_material(Material("Anker", E=E, nu=NU, rho=7850, alpha=ALPHA))
    m.add_section(Section.circle("D", float(np.sqrt(4 * AB / np.pi))))
    n = [m.add_node(x, y, z) for z in (0.0, 1.0) for x, y in ((0, 0), (1, 0), (1, 1), (0, 1))]
    m.add_element("hex8", n, "S355", "")
    for i in n[:4]:
        m.fix(i, [2])
    m.fix(n[0], [0, 1])
    m.fix(n[1], [1])
    m.fix(n[3], [0])
    boden = [m.add_node(x, y, -1.0) for x, y in ((0, 0), (1, 0), (1, 1), (0, 1))]
    for b, t in zip(boden, n[4:]):
        m.fix(b, "all")
        m.add_element("truss", [b, t], "Anker", "D")
    lf_t, lf_m = lastfaelle[0], lastfaelle[-1]
    for lf in dict.fromkeys(lastfaelle):
        m.add_load_case(lf).gravity = [0, 0, 0]
    for i in range(1, 5):
        m.load_temp(i, DT, case=lf_t)
    for i in n[4:]:
        m.case(lf_m).nodal_loads.append(NodalLoad(i, [0, 0, -P / 4.0, 0, 0, 0]))
    m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=ET, laststufen=stufen,
                                     iterationen=60 if verfahren == "tangente" else 400,
                                     toleranz=1e-8 if verfahren == "tangente" else 1e-7,
                                     verfahren=verfahren)
    return m, n[4:], boden


def _linear(faktoren_t: float = 1.0):
    """Zwei lineare Rechnungen ohne Fliessen: (u nur Temperatur * faktoren_t,
    u nur Last) - unabhaengig von der Stufenfolge."""
    m, _k, _b = _wuerfel(("T", "M"))
    system = solver.StaticSystem(m)
    u_t = system.solve(solver.case_loads(m, {"T": faktoren_t})[0])
    u_m = system.solve(solver.case_loads(m, {"M": 1.0})[0])
    return np.asarray(u_t, float), np.asarray(u_m, float)


def _geschlossen(faktor_t: float = 1.0):
    """Geschlossene Loesung (einachsig, bilinear): (w Kopf nach unten [m],
    Ankerkraft gesamt [N], sigma_zz Wuerfel [Pa])."""
    ks, kb = E, 4 * E * AB / LB         # Wuerfel E A/L mit A = L = 1, Anker
    d = -ALPHA * DT * LB * faktor_t     # freie Verkuerzung der Anker
    w = (P + kb * d) / (ks + kb)
    if E * w > FY:
        w = (P + kb * d - FY + ET * E * FY / E) / (ET * E + kb)
        sig = FY + ET * E * (w - FY / E)
    else:
        sig = E * w
    return w, kb * (d - w), -sig


def _mit_spur(rechnen):
    """``rechnen()`` ausfuehren und dabei jede Loesung der Fliess-Iteration
    mitschreiben: (Ergebnis, [(F_ges, u)], Schluesselwoerter an iteration)."""
    spur = {"aufrufe": [], "kw": None}
    alt = pl.iteration

    def iteration(model, F, loesen, *a, **kw):
        spur["kw"] = dict(kw)

        def mit(Fg, *x, **y):
            u = loesen(Fg, *x, **y)
            spur["aufrufe"].append((np.asarray(Fg, float).copy(), np.asarray(u, float).copy()))
            return u
        return alt(model, F, mit, *a, **kw)
    pl.iteration = iteration
    try:
        erg = rechnen()
    finally:
        pl.iteration = alt
    return erg, spur["aufrufe"], spur["kw"]


def _kopf_w(u, kopf):
    return -float(np.asarray(u, float).reshape(-1, 6)[kopf, 2].mean())


def _ankerkraft_aus_kopf(u, kopf, lam):
    """Ankerkraft gesamt aus dem Gleichgewicht am Kopf: der elastische Wuerfel
    traegt E A w/L, die Last davon lam * P - den Rest ziehen die Anker."""
    return E * _kopf_w(u, kopf) - lam * P


def _stufe1_und_ende(was, r, aufrufe, kopf, boden, faktor_t=1.0, stufen=3):
    u_t, u_m = _linear(faktor_t)
    u1 = aufrufe[0][1]
    soll = u_t + u_m / stufen
    abw = float(np.linalg.norm(u1 - soll)) / float(np.linalg.norm(soll))
    alt = (u_t + u_m) / stufen
    N1 = _ankerkraft_aus_kopf(u1, kopf, 1.0 / stufen)
    N_soll = _ankerkraft_aus_kopf(soll, kopf, 1.0 / stufen)
    N_alt = _ankerkraft_aus_kopf(alt, kopf, 1.0 / stufen)
    check(f"{was}: Stufe 1 = Temperatur voll + 1/{stufen} der Last (lineare Gegenrechnung)",
          abw <= 1e-9, f"Abweichung {abw:.2e}; Ankerkraft {N1 / 1e6:.2f} MN, soll {N_soll / 1e6:.2f}, "
          f"bis 10.10.2026 {N_alt / 1e6:.2f} MN")
    w_s, N_s, sig_s = _geschlossen(faktor_t)
    u = np.asarray(r.u, float)
    nahe(f"{was}: Ende Kopfverschiebung = geschlossene Lösung", _kopf_w(u, kopf), w_s, 1e-6, "m")
    uu = u.reshape(-1, 6)
    N_end = sum(E * AB * ((uu[t, 2] - uu[b, 2]) / LB - ALPHA * DT * faktor_t)
                for b, t in zip(boden, kopf))
    nahe(f"{was}: Ende Ankerkraft = geschlossene Lösung", N_end, N_s, 1e-6, "N")
    nahe(f"{was}: Ende σ_zz im Würfel = geschlossene Lösung", np.asarray(r.solid_res[0], float)[2],
         sig_s, 1e-6, "Pa")
    pz = r.info.get("plastizitaet") or {}
    check(f"{was}: konvergiert, der Würfel fließt", pz.get("konvergiert") and pz.get("fliessend") == 1,
          f"konvergiert {pz.get('konvergiert')}, fließend {pz.get('fliessend')}")
    log = pz.get("log") or []
    check(f"{was}: das Protokoll sagt „{SATZ} …“", any(z.startswith("Plastizität: " + SATZ) for z in log),
          str(log[:1])[:150])
    check(f"{was}: die letzte Protokollzeile bleibt die Zusammenfassung des Fließens",
          bool(log) and "Element fließt" in log[-1], str(log[-1:])[:120])


def test_newton_stufe1_und_ende():
    m, kopf, boden = _wuerfel()
    r, aufrufe, kw = _mit_spur(lambda: solver.solve_static(m))
    _stufe1_und_ende("Newton", r, aufrufe, kopf, boden)


def test_anfangsdehnung_stufe1_und_ende():
    m, kopf, boden = _wuerfel(verfahren="anfangsdehnung")
    r, aufrufe, kw = _mit_spur(lambda: solver.solve_static(m))
    _stufe1_und_ende("Anfangsdehnung", r, aufrufe, kopf, boden)


def test_kombination_mit_faktor():
    """K1 = 1,1 LF1 (Temperatur) + 1,0 LF2 (Last): die Temperatur wirkt ab
    Stufe 1 mit 1,1 - der Faktor der Kombination gilt weiter."""
    m, kopf, boden = _wuerfel(("LF1", "LF2"))
    m.add_combination("K1", {"LF1": 1.1, "LF2": 1.0}, typ="ULS")
    out, aufrufe, kw = _mit_spur(lambda: solver.solve_combinations(m, ["K1"]))
    _stufe1_und_ende("Kombination 1,1·T + 1,0·Last", out["K1"], aufrufe, kopf, boden, faktor_t=1.1)


class _DeckelEinmal:
    """Ein Kontakt, der genau einmal meldet, ein Lauf der Stufe sei am Deckel
    geendet - so halbiert der Newton die erste Stufe, in der er nicht im
    ersten Schritt fertig ist (plastizitaet._newton, Ruecksprung)."""
    gemeinsam = False

    def __init__(self):
        self.gemeldet = False

    def merken(self):
        return object()

    def deckel_seit(self, _marke):
        if self.gemeldet:
            return False
        self.gemeldet = True
        return True

    def zurueck_an(self, _marke):
        return 0


def test_halbieren_temperatur_bleibt_voll():
    """Beim Halbieren einer Stufe bleibt die Temperaturlast voll: Stufe 3 (bis
    100 %) wird in zwei halben wiederholt, die erste beginnt bei 5/6 der Last
    mit voller Temperatur."""
    m, kopf, _b = _wuerfel(("T", "M"))
    F_t = solver.case_loads(m, {"T": 1.0})[0]
    F_m = solver.case_loads(m, {"M": 1.0})[0]
    F = solver.case_loads(m, {"T": 1.0, "M": 1.0})[0]
    system = solver.StaticSystem(m)
    lasten = []

    def loesen(Fg, dK=None):
        lasten.append(np.asarray(Fg, float).copy())
        return system.solve(Fg, K_extra=dK)
    log = []
    _u, _z, _F_p, info = pl.iteration(m, F, loesen, m.plastizitaet, log=log, loesen_tangente=loesen,
                                      kontakt=_DeckelEinmal(), F_temperatur=F_t)
    check("halbiert: einmal, das Protokoll sagt es", int(info.get("halbiert") or 0) == 1
          and any("in zwei halben Stufen wiederholt" in z for z in log), f"halbiert {info.get('halbiert')}")
    # Stufenanfaenge ohne plastische Last: F_ges = F_T + lam F_M
    gefunden = []
    for Fg in lasten:
        rest = Fg - F_t
        lam = float(rest @ F_m) / float(F_m @ F_m)
        if np.linalg.norm(rest - lam * F_m) <= 1e-12 * np.linalg.norm(F):
            gefunden.append(round(lam, 9))
    check("Stufenanfänge bei 1/3, 2/3 und 5/6 der Last, jeweils mit voller Temperatur",
          {round(1 / 3, 9), round(2 / 3, 9), round(5 / 6, 9)} <= set(gefunden), str(sorted(set(gefunden))))
    w_s, _N, _s = _geschlossen()
    nahe("… und das Ende trifft die geschlossene Lösung", _kopf_w(_u, kopf), w_s, 1e-6, "m")


def test_ohne_temperatur_wie_bisher():
    """Ohne Temperaturlast steht der Satz nicht im Protokoll, und die Stufen
    rechnen mit lam * F wie bis zum 10.10.2026."""
    m, kopf, _b = _wuerfel()
    m.case("LF1").temp_loads.clear()
    r, aufrufe, kw = _mit_spur(lambda: solver.solve_static(m))
    F = solver.case_loads(m, {"LF1": 1.0})[0]
    check("ohne Temperatur: Stufe 1 rechnet mit F/3 (bitgleich)",
          np.array_equal(aufrufe[0][0], (1.0 / 3.0) * F))
    log = (r.info.get("plastizitaet") or {}).get("log") or []
    check("… und das Protokoll nennt keine Temperatur", not any("Temperatur" in z for z in log),
          str(log)[:120])


def _rahmen():
    """Kragstuetze (Stab, 3 m) unter Kopflast schraeg nach unten, dazu ein
    Zugband zum Boden (Fachwerkstab) mit Abkuehlung - fuer die Theorie III.
    Ordnung. Lastfall T nur Temperatur, M nur Last, LF1 beides."""
    m = Model("Th3")
    m.add_material(Material("S355", E=E, nu=NU, rho=7850, fy=FY, alpha=ALPHA))
    m.add_section(Section.from_profile("HEB 200"))
    m.add_section(Section.circle("D", 0.03))
    a = m.add_node(0.0, 0.0, 0.0)
    b = m.add_node(0.0, 0.0, 3.0)
    c = m.add_node(2.0, 0.0, 0.0)
    m.fix(a, "all")
    m.fix(c, "all")
    m.add_element("beam", [a, b], "S355", "HEB 200")
    m.add_element("truss", [c, b], "S355", "D")
    for lf in ("T", "M", "LF1"):
        m.add_load_case(lf).gravity = [0, 0, 0]
    for lf in ("T", "LF1"):
        m.load_temp(1, -40.0, case=lf)
    for lf in ("M", "LF1"):
        m.case(lf).nodal_loads.append(NodalLoad(b, [20e3, 5e3, -400e3, 0, 0, 0]))
    return m


def test_theorie3():
    """Theorie III. Ordnung in 5 Laststufen: die erste Iteration der ersten
    Stufe loest gegen F_T + F_M/5 (unverformt ist f_int = 0) statt (F_T +
    F_M)/5; das Ende bleibt dasselbe Gleichgewicht."""
    m = _rahmen()
    F_t = solver.case_loads(m, {"T": 1.0})[0]
    F_m = solver.case_loads(m, {"M": 1.0})[0]
    rechte = []
    alt = theorie3.splu

    class _Mit:
        def __init__(self, A):
            self._lu = alt(A)

        def solve(self, b):
            rechte.append(np.asarray(b, float).copy())
            return self._lu.solve(b)
    theorie3.splu = _Mit
    try:
        res, info = theorie3.solve_theorie3(m, {"LF1": 1.0}, "LF1", schritte=5, imperfektionen=False)
    finally:
        theorie3.splu = alt
    check("Theorie III: gerechnet", info.gerechnet, info.fehler)
    # Frei ist nur der Kopfknoten (FHG 6 bis 11). rechte[0] ist die
    # Bezugsrechnung I. Ordnung mit der vollen Last, rechte[1] die erste
    # Iteration der Stufe 1.
    fi = list(range(6, 12))
    F_ges = F_t + F_m
    check("Theorie III: die Bezugsrechnung I. Ordnung löst mit der vollen Last am Kopf",
          len(rechte[0]) == len(fi) and np.allclose(rechte[0], F_ges[fi], rtol=1e-12, atol=0.0))
    soll = (F_t + F_m / 5.0)[fi]
    bisher = (F_ges / 5.0)[fi]
    abw = float(np.linalg.norm(rechte[1] - soll)) / float(np.linalg.norm(soll))
    check("Theorie III: Stufe 1 rechnet mit voller Temperatur und 1/5 der Last",
          abw <= 1e-9, f"Abweichung {abw:.2e}, gegen (F_T + F_M)/5 (bis 10.10.2026) "
          f"{float(np.linalg.norm(rechte[1] - bisher)) / float(np.linalg.norm(bisher)):.2e}")
    check(f"Theorie III: Hinweis „{SATZ} …“", any(h.startswith(SATZ) for h in info.hinweise),
          str(info.hinweise)[:120])


def main():
    for t in (test_newton_stufe1_und_ende, test_anfangsdehnung_stufe1_und_ende,
              test_kombination_mit_faktor, test_halbieren_temperatur_bleibt_voll,
              test_ohne_temperatur_wie_bisher, test_theorie3):
        try:
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
    return 0 if not schlecht else 1


if __name__ == "__main__":
    sys.exit(main())
