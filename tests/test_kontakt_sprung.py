"""Koerper springen in der Kontaktiteration (17.10.2026, kontakt/pendeln-rt).

Anlass: Mittel-Z mit mu 0,2 auf addd95a. In Laststufe 1/3, Newton-Schritt 5, sprangen
im Kontaktlauf einzelne Ankerplatten als starre Koerper (V4 um 180 mm, V7 um 101 mm,
Verformungsanteil um 1e-7 %), nachdem sie zwei Stufen lang anlagen. Die Zerlegung
scheiterte nicht - der Loeser loeste das fast singulaere System, und die vorhandene
Halte-Hilfe (solver._freie_teile_halten) griff nur bei einer RuntimeError.

Nachgestellt (Pruefkoerper unten): Platte mit Bohrung auf einer Reibfuge (mu 0,2) unter
300 kN Ankerkraft, dazu ein Stab "nur Zug" mit Temperaturdehnung, der die Platte im
ersten Schritt der Ausfall-Iteration hochdrueckt - am Ende liegt sie auf 4 Knoten. Der
naechste Lauf startet warm von diesem Zustand, der Stab ist ausgefallen: die 4 Knoten
halten die Platte rechnerisch, aber kaum, und die Loesung springt um 220 m.

Geprueft wird (Auftrag des Anwenders):
1. Kontaktstart "geschlossen" als Einstellung der Fuge (Kontaktbedingung.start_geschlossen,
   im Kontaktpaar mitgefuehrt; NEUE_FELDER): der Lauf beginnt geschlossen mit dem echten
   Spalt und darf abheben, wenn Zug entsteht.
2a. Eine Runde oeffnet nicht alle Bedingungen eines Koerpers, wenn er dadurch frei wird
   (nur die staerker gezogene Haelfte); der Endzustand bleibt streng - muss der Koerper
   wirklich abheben, endet der Lauf nicht konvergiert.
2b/2c. Springt ein Koerper in einer Runde um mehr als eine Elementgroesse bei praktisch
   null Verformung, wird die Runde verworfen und gedaempft wiederholt; das Protokoll
   sagt "Koerper ... in dieser Runde nicht gehalten". Die Kraft der Stabilisierung steht
   im Protokoll, ueber 0,1 % der Last mit Warnung.

Aufruf:  python -m tests.test_kontakt_sprung
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np                                                  # noqa: E402

from statik3d import contact, mesher, solver                        # noqa: E402
from statik3d.model import (Material, Model, Section, TempLoad,     # noqa: E402
                            Volumenkoerper)

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:86s} {str(detail)[:200]}")
    return ok


def platte(n=8, F=300e3, mu=0.2, a=0.12, t=0.02, loch=2, dT=480.0, A_stab=1e-3, start_zu=None,
           Fz_auf=0.0, spalt=0.0):
    """Platte mit Bohrung auf einem Unterlegblech (Koerper "Platte" und "Blech"), Reibfuge
    mu, Ankerkraft F auf dem Ring um die Bohrung; ``dT``: Stab "nur Zug" durch die
    Bohrung, der sich dehnt und die Platte im ersten Ausfallschritt hochdrueckt;
    ``Fz_auf``: zusaetzlich eine Kraft nach oben an den Ecken der Platte; ``spalt``: die
    Platte liegt um so viel hoeher (echter Spalt)."""
    m = Model("Platte springt")
    m.add_material(Material("S355", E=210e9, nu=0.3, rho=0.0))
    s = mesher.grid_box(m, "S355", a, a, t, n, n, 2, typ="tet4")
    lo, hi = (n - loch) // 2, (n + loch) // 2
    h = a / n

    def im_loch(e):
        c = np.asarray(m.nodes, float)[list(e.nodes)].mean(axis=0)
        return lo * h < c[0] < hi * h and lo * h < c[1] < hi * h
    m.elements[:] = [e for e in m.elements if not im_loch(e)]
    n_sockel = len(m.elements)
    for k in s[:, :, 0].ravel():
        m.fix(int(k), "all")
    p = mesher.grid_box(m, "S355", a, a, t, n, n, 2, origin=(0.0, 0.0, t + spalt), typ="tet4")
    m.elements[:] = m.elements[:n_sockel] + [e for e in m.elements[n_sockel:] if not im_loch(e)]
    n_platte = len(m.elements)
    m.koerper["Blech"] = Volumenkoerper("Blech", elemente=list(range(n_sockel)))
    m.koerper["Platte"] = Volumenkoerper("Platte", elemente=list(range(n_sockel, n_platte)))
    benutzt = {int(k) for e in m.elements for k in e.nodes}
    unten = [int(k) for k in p[:, :, 0].ravel() if int(k) in benutzt]
    m.add_contact_pair("Platte/Unterlegblech", unten, list(range(n_sockel)), mu=mu,
                       search_radius=max(0.01, 4 * spalt))
    if start_zu is not None:
        m.contact_pairs[-1].start_geschlossen = bool(start_zu)
    X = np.asarray(m.nodes, float)
    oben = [int(k) for k in p[:, :, -1].ravel() if int(k) in benutzt]
    ring = [k for k in oben if (lo - 1) * h - 1e-9 <= X[k, 0] <= (hi + 1) * h + 1e-9
            and (lo - 1) * h - 1e-9 <= X[k, 1] <= (hi + 1) * h + 1e-9]
    lc = m.add_load_case("LF1")
    lc.gravity = [0, 0, 0]
    for k in ring:
        m.load_node(k, Fz=-F / len(ring))
    if Fz_auf:
        ecken = [k for k in oben if (X[k, 0] < 1e-9 or X[k, 0] > a - 1e-9)
                 and (X[k, 1] < 1e-9 or X[k, 1] > a - 1e-9)]
        for k in ecken:
            m.load_node(k, Fz=Fz_auf / len(ecken))
    if dT:
        A = min(ring, key=lambda k: float(np.hypot(X[k, 0] - lo * h, X[k, 1] - lo * h)))
        P = m.add_node(X[A, 0], X[A, 1], -0.3)
        m.fix(P, "all")
        m.add_section(Section("Stab", A_stab, 1e-8, 1e-8, 2e-8))
        i = m.add_element("truss", [A, P], "S355", "Stab", nur="zug")
        lc.temp_loads.append(TempLoad(elem=int(i), dT=float(dT)))
    m.active_case = "LF1"
    m.plastizitaet.an = False
    return m


def _platte_knoten(m):
    return sorted({int(k) for i in m.koerper["Platte"].elemente for k in m.elements[i].nodes})


def rechnen(m):
    """Loesen; je Runde die groesste Verschiebungsaenderung der Platte und die Zahl ihrer
    aktiven Bedingungen vor und nach der Aktualisierung."""
    kn = _platte_knoten(m)
    runden = []
    alt = contact.ContactSystem.update
    vor = {"u": None}

    def update(self, u, lam=None):
        U = np.asarray(u, float)[:m.nn * 6].reshape(-1, 6)[:, :3]
        d = 0.0 if vor["u"] is None else float(np.abs(U[kn] - vor["u"][kn]).max())
        a0 = sum(1 for c in self.cons if c.active)
        erg = alt(self, u, lam)
        runden.append((d, a0, sum(1 for c in self.cons if c.active)))
        vor["u"] = U.copy()
        return erg
    alt_swc = solver.solve_with_contact

    def swc(*a, **kw):
        vor["u"] = None
        return alt_swc(*a, **kw)
    contact.ContactSystem.update = update
    solver.solve_with_contact = swc
    meld = []
    try:
        r = solver.solve_static(m, workers=1, progress=lambda t_, *a: meld.append(str(t_)))
    finally:
        contact.ContactSystem.update = alt
        solver.solve_with_contact = alt_swc
    log = [str(z) for z in r.info.get("contact_log") or []] + meld
    return r, runden, log


def test_kontaktstart_geschlossen():
    print("\n--- 1. Kontaktstart „geschlossen“: Einstellung der Fuge ---")
    from statik3d import model as md
    from statik3d.model import ContactPair, Kontaktbedingung
    check("Felder mit Vorgabe aus (Kontaktbedingung und Kontaktpaar), in NEUE_FELDER",
          Kontaktbedingung().start_geschlossen is False and ContactPair("x").start_geschlossen is False
          and md.NEUE_FELDER.get("kontaktbedingungen", {}).get("start_geschlossen") is False
          and md.NEUE_FELDER.get("contact_pairs", {}).get("start_geschlossen") is False)
    m = platte(dT=0.0)
    d = m.to_dict()
    check("eine Datei ohne die Einstellung bleibt ohne das Feld (Vorgabe nicht gespeichert)",
          all("start_geschlossen" not in c for c in d.get("contact_pairs", [])))
    m.contact_pairs[0].start_geschlossen = True
    m2 = Model.from_dict(m.to_dict())
    check("gesetzt: gespeichert und gelesen", m2.contact_pairs[0].start_geschlossen is True)
    # echter Spalt 0,05 mm, die Ankerkraft drueckt die Platte auf die Fuge
    erg = {}
    for zu in (False, True):
        r, runden, _log = rechnen(platte(dT=0.0, spalt=5e-5, start_zu=zu))
        erg[zu] = (r, runden)
    (r0, rd0), (r1, rd1) = erg[False], erg[True]
    du = float(np.abs(np.asarray(r1.u) - np.asarray(r0.u)).max())
    check("mit Spalt 0,05 mm und Andruck: der Lauf beginnt geschlossen (alle 80 aktiv), "
          "Ergebnis wie offen gestartet",
          rd1 and rd1[0][1] == 80 and rd0[0][1] < 80 and r1.info.get("contact_converged") is True
          and du <= 1e-9, f"Runde 1 aktiv {rd0[0][1]} / {rd1[0][1]}, max |Δu| {du:.1e} m")
    akt = sum(1 for c in r1.contact if c["status"] != "offen")
    check("… wo Zug entsteht, hebt die Fuge ab: am Ende nicht mehr alle geschlossen",
          0 < akt < 80, f"am Ende aktiv {akt} von 80")
    try:
        from statik3d.gui import main as gm
        src = open(gm.__file__, encoding="utf-8").read()
        check("Maske: Feld „Kontaktstart“ mit Klartext-Hinweis",
              "start_geschlossen" in src and "planmäßig anliegen" in src)
    except Exception as ex:                          # noqa: BLE001
        check("Maske: Feld „Kontaktstart“ mit Klartext-Hinweis", False, str(ex)[:120])


def test_sprung():
    print("\n--- 2c. Platte springt im warm gestarteten Lauf (Stab fällt aus) ---")
    alt = (solver.SPRUNG_PRUEFEN, solver.VORAB_HALTEN, contact.OEFFNEN_BEGRENZEN)
    try:
        solver.SPRUNG_PRUEFEN = solver.VORAB_HALTEN = contact.OEFFNEN_BEGRENZEN = False
        r0, rd0, _l0 = rechnen(platte())
    finally:
        solver.SPRUNG_PRUEFEN, solver.VORAB_HALTEN, contact.OEFFNEN_BEGRENZEN = alt
    h = 0.12 / 8
    check("Rücknahme: eine Runde, in der die Platte um mehr als 1 m springt",
          max(d for d, _a, _b in rd0) > 1.0, f"größter Sprung {max(d for d, _a, _b in rd0):.3g} m")
    r, rd, log = rechnen(platte())
    d_max = max(d for d, _a, _b in rd)
    check("mit Sprungprüfung: keine angenommene Runde mit Sprung über eine Elementgröße (15 mm)",
          d_max < h, f"größte Änderung {d_max * 1e3:.4g} mm")
    check("… das Protokoll sagt „Körper Platte in dieser Runde nicht gehalten“",
          any("Platte" in z and "nicht gehalten" in z for z in log),
          next((z for z in log if "nicht gehalten" in z), "")[:200])
    du = float(np.abs(np.asarray(r.u) - np.asarray(r0.u)).max())
    check("… konvergiert, Ergebnis wie ohne Sprung (u bis 1e-6 relativ), Stab ausgefallen",
          r.info.get("contact_converged") is True and len(r.info.get("ausfall") or []) == 1
          and du <= 1e-6 * float(np.abs(np.asarray(r0.u)).max()),
          f"max |Δu| {du:.2e} m, ausgefallen {r.info.get('ausfall')}")
    stab = [z for z in log if "stabilisierung" in z.lower() and "trägt am Ende" in z]
    warn = [z for z in stab if "WARNUNG" in z]
    check("… die Kraft der Stabilisierung steht im Protokoll, unter 0,1 % der Last keine Warnung",
          stab and not warn, (stab or ["keine Zeile"])[-1][:200])


def test_abheben():
    print("\n--- 2a. Platte, die abheben muss: keine Runde öffnet alles, kein Sprung, ehrlich nicht konvergiert ---")
    r, rd, log = rechnen(platte(dT=0.0, F=10e3, Fz_auf=60e3, start_zu=True))
    nie_alle = all(b > 0 for _d, a, b in rd if a > 0)
    check("keine Runde öffnet alle Bedingungen der Platte (sie wäre frei)",
          nie_alle and any("wäre in dieser Runde nicht gehalten" in z for z in log),
          " ".join(f"{a}->{b}" for _d, a, b in rd[:12]))
    d_max = max(d for d, _a, _b in rd)
    check("… kein Sprung über eine Elementgröße", d_max < 0.015, f"{d_max * 1e3:.4g} mm")
    check("… der Lauf endet nicht konvergiert und sagt, dass die Platte nicht gehalten ist",
          r.info.get("contact_converged") is False
          and any("Platte" in z and ("nicht gehalten" in z or "abheben" in z) for z in log),
          next((z for z in log if "Platte" in z and ("nicht gehalten" in z or "abheben" in z)), "")[:200])


def test_stabilisierung_warnt():
    print("\n--- 2b. Die Stabilisierung warnt, wenn sie am Ende mehr als 0,1 % der Last trägt ---")
    check("Schranke 0,1 % und Anteil 1e-6 der Kontaktsteifigkeit",
          solver.STABIL_WARNUNG == 1e-3 and contact.STABIL_ANTEIL == 1e-6)


def main():
    test_kontaktstart_geschlossen()
    test_sprung()
    test_abheben()
    test_stabilisierung_warnt()
    n_f = sum(1 for _n, ok in RESULTS if not ok)
    print(f"\n{len(RESULTS) - n_f} von {len(RESULTS)} Prüfungen bestanden")
    return 1 if n_f else 0


if __name__ == "__main__":
    sys.exit(main())
