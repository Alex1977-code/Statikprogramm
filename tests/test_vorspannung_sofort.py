"""Vorspannkraefte wirken in jeder schrittweisen Rechnung sofort voll, wie
die Temperaturlasten (tests/test_temperatur_sofort.py).

Der Anwender hat am 10.10.2026 entschieden: „temperaturlast immer sofort
vorhanden berücksichtigen denn ohne vorspannung mehr verformung und dann
längere rechenzeit“. Seine Begruendung ist die Vorspannung, darum gilt die
Entscheidung auch fuer eine Vorspannung, die als Vorspannkraft eingegeben ist
(model.Vorspannung): im Stab (Zugstange, Anker) und als Koerper (Schraube aus
Volumenelementen). Bis dahin wuchs eine solche Vorspannkraft mit den
Laststufen der Plastizitaet und der Theorie III. Ordnung mit.

Geprueft am vorgespannten Wuerfel aus test_temperatur_sofort, nur mit einer
Vorspannkraft in den vier Ankern statt der Abkuehlung: F_v = 48,825 MN je
Anker ist genau die Kraft von ΔT = −387,5 K bei voller Behinderung
(E A α ΔT). Die Rechnung ist einachsig, und die geschlossene bilineare
Loesung gilt unveraendert.

* Stufe 1 (von 3) ist die lineare Loesung „Vorspannung voll + 1/3 der
  Last“, gegengerechnet mit zwei unabhaengigen linearen Rechnungen (nur
  Vorspannung, nur Last); das Ende trifft die geschlossene Loesung.
* Ebenso im Weg "anfangsdehnung", in einer Kombination (die Vorspannung mit
  ihrem Faktor), beim Halbieren einer Stufe, mit Temperatur und Vorspannung
  zusammen und in der Theorie III. Ordnung (vorgespanntes Zugband).
* Vorspannung als Koerper: ein Bolzen aus einem Hexaeder auf dem fliessenden
  Wuerfel - Stufe 1 gegen dieselben zwei linearen Rechnungen.
* Ohne Temperatur und ohne Vorspannung rechnet jede Stufe bitgleich wie
  vorher.

Aufruf:  python -m tests.test_vorspannung_sofort
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import plastizitaet as pl, solver, theorie3          # noqa: E402
from statik3d.model import Material, Model, NodalLoad, Section    # noqa: E402
from statik3d.model import Volumenkoerper                          # noqa: E402

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
FV = E * AB * ALPHA * 387.5  # Vorspannkraft je Anker [N] = 48,825 MN (wie ΔT = -387,5 K)
P = 2.5e8                   # Drucklast auf den Kopf [N]
ET = 0.02                   # Verfestigung E_t/E

#: Satz fuer das Protokoll - auch in der Theorie III. Ordnung
SATZ = "Temperaturlasten und Vorspannungen wirken ab der ersten Laststufe voll"


def _einst(stufen=3, verfahren="tangente"):
    return pl.Plastizitaet(an=True, verfestigung=ET, laststufen=stufen,
                           iterationen=60 if verfahren == "tangente" else 400,
                           toleranz=1e-8 if verfahren == "tangente" else 1e-7,
                           verfahren=verfahren)


def _wuerfel(lastfaelle=("LF1",), stufen=3, verfahren="tangente", temperatur=()):
    """Der Wuerfel mit vier vorgespannten Ankern (je ein Stab „A1“ … „A4“).
    ``lastfaelle``: ein Name - Vorspannung und Last darin; zwei Namen - die
    Vorspannung im ersten, die Last im zweiten. ``temperatur``: Anker
    (1 … 4), die statt der Vorspannkraft die gleichwertige Abkuehlung tragen.
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
    anker = []
    for b, t in zip(boden, n[4:]):
        m.fix(b, "all")
        anker.append(m.add_element("truss", [b, t], "Anker", "D"))
    lf_v, lf_m = lastfaelle[0], lastfaelle[-1]
    for lf in dict.fromkeys(lastfaelle):
        m.add_load_case(lf).gravity = [0, 0, 0]
    for k, e in enumerate(anker, start=1):
        m.add_member(f"A{k}", [e])
        if k in temperatur:
            m.load_temp(e, -387.5, case=lf_v)
        else:
            m.add_vorspannung(f"A{k}", FV, case=lf_v)
    for i in n[4:]:
        m.case(lf_m).nodal_loads.append(NodalLoad(i, [0, 0, -P / 4.0, 0, 0, 0]))
    m.plastizitaet = _einst(stufen, verfahren)
    return m, n[4:], boden


def _linear(faktor_v: float = 1.0, temperatur=()):
    """Zwei lineare Rechnungen ohne Fliessen: (u nur Vorspannung * faktor_v,
    u nur Last) - unabhaengig von der Stufenfolge."""
    m, _k, _b = _wuerfel(("V", "M"), temperatur=temperatur)
    system = solver.StaticSystem(m)
    u_v = system.solve(solver.case_loads(m, {"V": faktor_v})[0])
    u_m = system.solve(solver.case_loads(m, {"M": 1.0})[0])
    return np.asarray(u_v, float), np.asarray(u_m, float)


def _geschlossen(faktor_v: float = 1.0):
    """Geschlossene Loesung (einachsig, bilinear): (w Kopf nach unten [m],
    Ankerkraft gesamt [N], sigma_zz Wuerfel [Pa])."""
    ks, kb = E, 4 * E * AB / LB         # Wuerfel E A/L mit A = L = 1, Anker
    d = FV * LB / (E * AB) * faktor_v   # freie Verkuerzung der Anker
    w = (P + kb * d) / (ks + kb)
    if E * w > FY:
        w = (P + kb * d - FY + ET * E * FY / E) / (ET * E + kb)
        sig = FY + ET * E * (w - FY / E)
    else:
        sig = E * w
    return w, kb * (d - w), -sig


def _mit_spur(rechnen):
    """``rechnen()`` ausfuehren und dabei jede Loesung der Fliess-Iteration
    mitschreiben: (Ergebnis, [(F_ges, u)])."""
    spur = []
    alt = pl.iteration

    def iteration(model, F, loesen, *a, **kw):
        def mit(Fg, *x, **y):
            u = loesen(Fg, *x, **y)
            spur.append((np.asarray(Fg, float).copy(), np.asarray(u, float).copy()))
            return u
        return alt(model, F, mit, *a, **kw)
    pl.iteration = iteration
    try:
        erg = rechnen()
    finally:
        pl.iteration = alt
    return erg, spur


def _kopf_w(u, kopf):
    return -float(np.asarray(u, float).reshape(-1, 6)[kopf, 2].mean())


def _ankerkraft_aus_kopf(u, kopf, lam):
    """Ankerkraft gesamt aus dem Gleichgewicht am Kopf: der elastische Wuerfel
    traegt E A w/L, die Last davon lam * P - den Rest ziehen die Anker."""
    return E * _kopf_w(u, kopf) - lam * P


def _protokoll(was, r):
    pz = r.info.get("plastizitaet") or {}
    log = pz.get("log") or []
    check(f"{was}: das Protokoll sagt „{SATZ} …“", any(z.startswith("Plastizität: " + SATZ) for z in log),
          str(log[:1])[:150])
    return pz, log


def _stufe1_und_ende(was, r, aufrufe, kopf, boden, faktor_v=1.0, stufen=3, temperatur=()):
    u_v, u_m = _linear(faktor_v, temperatur)
    u1 = aufrufe[0][1]
    soll = u_v + u_m / stufen
    abw = float(np.linalg.norm(u1 - soll)) / float(np.linalg.norm(soll))
    alt = (u_v + u_m) / stufen
    N1 = _ankerkraft_aus_kopf(u1, kopf, 1.0 / stufen)
    N_soll = _ankerkraft_aus_kopf(soll, kopf, 1.0 / stufen)
    N_alt = _ankerkraft_aus_kopf(alt, kopf, 1.0 / stufen)
    check(f"{was}: Stufe 1 = Vorspannung voll + 1/{stufen} der Last (lineare Gegenrechnung)",
          abw <= 1e-9, f"Abweichung {abw:.2e}; Ankerkraft {N1 / 1e6:.2f} MN, soll {N_soll / 1e6:.2f}, "
          f"bis 10.10.2026 {N_alt / 1e6:.2f} MN")
    w_s, N_s, sig_s = _geschlossen(faktor_v)
    u = np.asarray(r.u, float)
    nahe(f"{was}: Ende Kopfverschiebung = geschlossene Lösung", _kopf_w(u, kopf), w_s, 1e-6, "m")
    uu = u.reshape(-1, 6)
    # Ankerkraft = E A (Dehnung - Anfangsdehnung), die Anfangsdehnung der
    # Vorspannung ist -F_v/(E A) je Anker
    N_end = sum(E * AB * (uu[t, 2] - uu[b, 2]) / LB + FV * faktor_v for b, t in zip(boden, kopf))
    nahe(f"{was}: Ende Ankerkraft = geschlossene Lösung", N_end, N_s, 1e-6, "N")
    nahe(f"{was}: Ende σ_zz im Würfel = geschlossene Lösung", np.asarray(r.solid_res[0], float)[2],
         sig_s, 1e-6, "Pa")
    pz, log = _protokoll(was, r)
    check(f"{was}: konvergiert, der Würfel fließt", pz.get("konvergiert") and pz.get("fliessend") == 1,
          f"konvergiert {pz.get('konvergiert')}, fließend {pz.get('fliessend')}")
    check(f"{was}: die letzte Protokollzeile bleibt die Zusammenfassung des Fließens",
          bool(log) and "Element fließt" in log[-1], str(log[-1:])[:120])


def test_newton_stufe1_und_ende():
    m, kopf, boden = _wuerfel()
    r, aufrufe = _mit_spur(lambda: solver.solve_static(m))
    _stufe1_und_ende("Newton", r, aufrufe, kopf, boden)


def test_gleich_der_temperatur():
    """Die Vorspannkraft 48,825 MN je Anker ist die Kraft der Abkuehlung
    ΔT = −387,5 K: beide linearen Rechnungen sind dieselben."""
    u_v, _u = _linear()
    u_t, _u2 = _linear(temperatur=(1, 2, 3, 4))
    abw = float(np.linalg.norm(u_v - u_t)) / float(np.linalg.norm(u_t))
    check("Vorspannkraft E A α ΔT rechnet linear wie die Abkühlung ΔT", abw <= 1e-12, f"Abweichung {abw:.2e}")


def test_anfangsdehnung_stufe1_und_ende():
    m, kopf, boden = _wuerfel(verfahren="anfangsdehnung")
    r, aufrufe = _mit_spur(lambda: solver.solve_static(m))
    _stufe1_und_ende("Anfangsdehnung", r, aufrufe, kopf, boden)


def test_kombination_mit_faktor():
    """K1 = 1,1 LF1 (Vorspannung) + 1,0 LF2 (Last): die Vorspannung wirkt ab
    Stufe 1 mit 1,1 - der Faktor der Kombination gilt weiter."""
    m, kopf, boden = _wuerfel(("LF1", "LF2"))
    m.add_combination("K1", {"LF1": 1.1, "LF2": 1.0}, typ="ULS")
    out, aufrufe = _mit_spur(lambda: solver.solve_combinations(m, ["K1"]))
    _stufe1_und_ende("Kombination 1,1·V + 1,0·Last", out["K1"], aufrufe, kopf, boden, faktor_v=1.1)


def test_temperatur_und_vorspannung():
    """Zwei Anker mit Abkuehlung, zwei mit Vorspannkraft: beide wirken ab
    Stufe 1 voll."""
    m, kopf, boden = _wuerfel(temperatur=(1, 2))
    r, aufrufe = _mit_spur(lambda: solver.solve_static(m))
    u_v, u_m = _linear(temperatur=(1, 2))
    soll = u_v + u_m / 3.0
    abw = float(np.linalg.norm(aufrufe[0][1] - soll)) / float(np.linalg.norm(soll))
    check("Temperatur und Vorspannung: Stufe 1 = beide voll + 1/3 der Last", abw <= 1e-9,
          f"Abweichung {abw:.2e}")
    w_s, _N, _s = _geschlossen()
    nahe("… und das Ende trifft die geschlossene Lösung", _kopf_w(r.u, kopf), w_s, 1e-6, "m")
    _protokoll("Temperatur und Vorspannung", r)


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


def test_halbieren_vorspannung_bleibt_voll():
    """Beim Halbieren einer Stufe bleibt die Vorspannung voll: die
    Stufenanfaenge liegen bei 1/3, 2/3 und 5/6 der Last, jeweils mit voller
    Vorspannung (F_sofort aus solver.case_sofort)."""
    m, kopf, _b = _wuerfel(("V", "M"))
    F_v = solver.case_loads(m, {"V": 1.0})[0]
    F_m = solver.case_loads(m, {"M": 1.0})[0]
    F = solver.case_loads(m, {"V": 1.0, "M": 1.0})[0]
    F_s = solver.case_sofort(m, {"V": 1.0, "M": 1.0})
    check("case_sofort: der Anteil der Vorspannung am Lastvektor",
          F_s is not None and np.allclose(F_s, F_v, rtol=0.0, atol=1e-9 * np.abs(F_v).max()))
    system = solver.StaticSystem(m)
    lasten = []

    def loesen(Fg, dK=None):
        lasten.append(np.asarray(Fg, float).copy())
        return system.solve(Fg, K_extra=dK)
    log = []
    _u, _z, _F_p, info = pl.iteration(m, F, loesen, m.plastizitaet, log=log, loesen_tangente=loesen,
                                      kontakt=_DeckelEinmal(), F_sofort=F_s)
    check("halbiert: einmal, das Protokoll sagt es", int(info.get("halbiert") or 0) == 1
          and any("in zwei halben Stufen wiederholt" in z for z in log), f"halbiert {info.get('halbiert')}")
    gefunden = []
    for Fg in lasten:
        rest = Fg - F_v
        lam = float(rest @ F_m) / float(F_m @ F_m)
        if np.linalg.norm(rest - lam * F_m) <= 1e-12 * np.linalg.norm(F):
            gefunden.append(round(lam, 9))
    check("Stufenanfänge bei 1/3, 2/3 und 5/6 der Last, jeweils mit voller Vorspannung",
          {round(1 / 3, 9), round(2 / 3, 9), round(5 / 6, 9)} <= set(gefunden), str(sorted(set(gefunden))))
    w_s, _N, _s = _geschlossen()
    nahe("… und das Ende trifft die geschlossene Lösung", _kopf_w(_u, kopf), w_s, 1e-6, "m")


def _bolzen_auf_wuerfel(lastfaelle=("LF1",)):
    """Vorspannung als Koerper: der fliessende Wuerfel (S355, z 0 … 1) und
    darueber ein Bolzen aus einem Hexaeder (z 1 … 2, ohne Streckgrenze, als
    Volumenkoerper „Bolzen“ mit Vorspannkraft 1,5 f_y A), oben in z gehalten.
    Der Bolzen zieht die Fuge bei z = 1 nach oben, die Last 0,9 f_y A zieht
    mit; der Wuerfel traegt zusammen 1,2 f_y A und fliesst. In Stufe 1 traegt
    er jetzt 0,9 f_y A (Vorspannung voll + 1/3 der Last), bis zum 10.10.2026
    waren es 0,4 f_y A."""
    m = Model("Bolzen")
    m.add_material(Material("S355", E=E, nu=NU, rho=7850, fy=FY))
    m.add_material(Material("Bolzen", E=E, nu=NU, rho=7850))
    n = [m.add_node(x, y, z) for z in (0.0, 1.0, 2.0) for x, y in ((0, 0), (1, 0), (1, 1), (0, 1))]
    m.add_element("hex8", n[0:8], "S355", "")
    b = m.add_element("hex8", n[4:12], "Bolzen", "")
    m.koerper["Bolzen"] = Volumenkoerper("Bolzen", flaechen=[], material="Bolzen", elemente=[b])
    for i in n[:4] + n[8:]:
        m.fix(i, [2])
    m.fix(n[0], [0, 1])
    m.fix(n[1], [1])
    m.fix(n[3], [0])
    lf_v, lf_m = lastfaelle[0], lastfaelle[-1]
    for lf in dict.fromkeys(lastfaelle):
        m.add_load_case(lf).gravity = [0, 0, 0]
    m.add_vorspannung("Bolzen", 1.5 * FY, achse=[0, 0, 1], case=lf_v)
    for i in n[4:8]:
        m.case(lf_m).nodal_loads.append(NodalLoad(i, [0, 0, 0.9 * FY / 4.0, 0, 0, 0]))
    m.plastizitaet = _einst()
    return m, n[4:8]


def test_vorspannung_als_koerper():
    m, fuge = _bolzen_auf_wuerfel()
    r, aufrufe = _mit_spur(lambda: solver.solve_static(m))
    mv, _f = _bolzen_auf_wuerfel(("V", "M"))
    system = solver.StaticSystem(mv)
    u_v = np.asarray(system.solve(solver.case_loads(mv, {"V": 1.0})[0]), float)
    u_m = np.asarray(system.solve(solver.case_loads(mv, {"M": 1.0})[0]), float)
    soll = u_v + u_m / 3.0
    alt = (u_v + u_m) / 3.0
    u1 = aufrufe[0][1]
    abw = float(np.linalg.norm(u1 - soll)) / float(np.linalg.norm(soll))

    def w(u):
        return float(np.asarray(u, float).reshape(-1, 6)[fuge, 2].mean())
    check("Körper: Stufe 1 = Vorspannung voll + 1/3 der Last (lineare Gegenrechnung)", abw <= 1e-9,
          f"Abweichung {abw:.2e}; Fuge {w(u1) * 1e3:.4f} mm, soll {w(soll) * 1e3:.4f}, "
          f"bis 10.10.2026 {w(alt) * 1e3:.4f} mm")
    pz, _log = _protokoll("Körper", r)
    check("Körper: konvergiert, der Würfel fließt", pz.get("konvergiert") and pz.get("fliessend") == 1,
          f"konvergiert {pz.get('konvergiert')}, fließend {pz.get('fliessend')}")
    Rz = float(np.asarray(r.reactions, float)[:, 2].sum())
    nahe("Körper: Gleichgewicht ΣR_z = −Last (die Vorspannung ist innere Kraft)", Rz, -0.9 * FY, 1e-9, "N")


def test_ohne_temperatur_und_vorspannung_wie_bisher():
    """Ohne Temperatur und Vorspannung steht der Satz nicht im Protokoll, und
    die Stufen rechnen mit lam * F wie bis zum 10.10.2026."""
    m, kopf, _b = _wuerfel()
    m.case("LF1").vorspannungen.clear()
    check("case_sofort ohne Temperatur und Vorspannung: None",
          solver.case_sofort(m, {"LF1": 1.0}) is None)
    r, aufrufe = _mit_spur(lambda: solver.solve_static(m))
    F = solver.case_loads(m, {"LF1": 1.0})[0]
    check("ohne Temperatur und Vorspannung: Stufe 1 rechnet mit F/3 (bitgleich)",
          np.array_equal(aufrufe[0][0], (1.0 / 3.0) * F))
    log = (r.info.get("plastizitaet") or {}).get("log") or []
    check("… und das Protokoll nennt weder Temperatur noch Vorspannung",
          not any("Temperatur" in z or "Vorspann" in z for z in log), str(log)[:120])


def _rahmen():
    """Kragstuetze (Stab, 3 m) unter Kopflast schraeg nach unten, dazu ein
    vorgespanntes Zugband zum Boden (Fachwerkstab, Stab „Band“, 70 kN) - fuer
    die Theorie III. Ordnung. Lastfall V nur Vorspannung, M nur Last, LF1
    beides."""
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
    band = m.add_element("truss", [c, b], "S355", "D")
    m.add_member("Band", [band])
    for lf in ("V", "M", "LF1"):
        m.add_load_case(lf).gravity = [0, 0, 0]
    for lf in ("V", "LF1"):
        m.add_vorspannung("Band", 70e3, case=lf)
    for lf in ("M", "LF1"):
        m.case(lf).nodal_loads.append(NodalLoad(b, [20e3, 5e3, -400e3, 0, 0, 0]))
    return m


def test_theorie3():
    """Theorie III. Ordnung in 5 Laststufen: die erste Iteration der ersten
    Stufe loest gegen F_V + F_M/5 (unverformt ist f_int = 0) statt (F_V +
    F_M)/5."""
    m = _rahmen()
    F_v = solver.case_loads(m, {"V": 1.0})[0]
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
    fi = list(range(6, 12))
    F_ges = F_v + F_m
    soll = (F_v + F_m / 5.0)[fi]
    bisher = (F_ges / 5.0)[fi]
    abw = float(np.linalg.norm(rechte[1] - soll)) / float(np.linalg.norm(soll))
    check("Theorie III: Stufe 1 rechnet mit voller Vorspannung und 1/5 der Last",
          abw <= 1e-9, f"Abweichung {abw:.2e}, gegen (F_V + F_M)/5 (bis 10.10.2026) "
          f"{float(np.linalg.norm(rechte[1] - bisher)) / float(np.linalg.norm(bisher)):.2e}")
    check(f"Theorie III: Hinweis „{SATZ} …“", any(h.startswith(SATZ) for h in info.hinweise),
          str(info.hinweise)[:120])


def main():
    for t in (test_newton_stufe1_und_ende, test_gleich_der_temperatur, test_anfangsdehnung_stufe1_und_ende,
              test_kombination_mit_faktor, test_temperatur_und_vorspannung,
              test_halbieren_vorspannung_bleibt_voll, test_vorspannung_als_koerper,
              test_ohne_temperatur_und_vorspannung_wie_bisher, test_theorie3):
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
