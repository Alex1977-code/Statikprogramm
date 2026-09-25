"""
Messung: die Grenze fuer den Winkelfehler eines hex8 (dritter Auftrag der
Statik3D-Sitzung, 24.09.2026, Aufgabe 4).

Kragarm wie in V5 (tests/pruefkoerper.Kragarm, 1,0 x 0,1 x 0,2 m, Soll 355
N/mm2 an (L/2, B/2, H)). Zuerst die Feinheit, mit der das **regelmaessige**
hex8-Netz 1 N/mm2 erreicht; dann dasselbe Netz mit **Parallelogramm**- und
mit **Trapezverzerrung** von 0 / 5 / 10 / 15 / 20 / 30 Grad in der x-z-Ebene:

    Parallelogramm  x' = x + (-1)^k (h/2) tan(theta)          k = Knotenlage, h = Elementhoehe
    Trapez          x' = x + (-1)^k (-1)^i (h/2) tan(theta)   dazu das Vorzeichen der Spalte i

Beide Muster geben jedem Element den Eckwinkel 90 +- theta (Zickzack ueber
die Lagen, Vorzeichenwechsel je Spalte macht aus dem Parallelogramm das
Trapez); die Verschiebung bleibt unter der halben Elementhoehe, nichts klappt
um, und die Nachweisstelle bleibt an ihrer Stelle. Die Endspalten x = 0 und
x = L bleiben stehen (Einspannung und Last wie im regelmaessigen Netz). Der
Winkelfehler nach sweep.winkelfehler ist bei beiden gleich theta. Gemessen wird
der Fehler am Knoten der Nachweisstelle gegen Saint-Venant an seiner
(kaum verschobenen) Lage.
Vorschlag fuer sweep.WINKELFEHLER_GRENZE: der groesste Winkel, bei dem der
Fehler bei beiden Verzerrungen unter 1 N/mm2 bleibt.

Kein Test. Aufruf:  python -m tests.messung_winkelfehler [--json datei]
"""
from __future__ import annotations

import json
import sys

import numpy as np

from statik3d import solver, sweep
from tests import pruefkoerper as pk

NETZE = [(8, 2, 4), (16, 4, 8), (32, 8, 16), (48, 12, 24)]
WINKEL = (0.0, 2.5, 5.0, 7.5, 10.0, 15.0, 20.0, 30.0)


def _fehler(m, res, kr, punkt):
    ps = pk.punktspannung(m, res, punkt)
    x = float(punkt[0])
    soll = kr.F * (kr.L - x) * (0.5 * kr.H) / kr.I / 1e6
    return float(ps["sv_mittel"] / 1e6 - soll), soll


def _loesen(m):
    r = solver.solve_all(m, workers=1)
    return next(iter(r.cases.values()))


def regelmaessig(kr):
    for nx, ny, nz in NETZE:
        m, _ids = kr.modell("hex8", nx, ny, nz)
        res = _loesen(m)
        f, _soll = _fehler(m, res, kr, kr.punkt())
        print(f"  regelmaessig {nx}x{ny}x{nz}: {len(m.elements)} hex8, {pk.fhg(m)} FHG, Fehler {f:+.2f} N/mm2", flush=True)
        if abs(f) <= 1.0:
            return (nx, ny, nz), f
    return NETZE[-1], f


def verzerrt(kr, netz, art, theta):
    nx, ny, nz = netz
    m, _ids = kr.modell("hex8", nx, ny, nz)
    X = np.asarray(m.nodes, float).copy()
    t = np.tan(np.radians(theta))
    h_el = kr.H / nz
    dx = np.round(X[:, 0] / (kr.L / nx)).astype(int)          # Knotenspalte
    lage = np.round(X[:, 2] / h_el).astype(int)               # Knotenlage
    innen = (X[:, 0] > 1e-9) & (X[:, 0] < kr.L - 1e-9)
    schub = np.where(lage % 2 == 0, 1.0, -1.0) * 0.5 * h_el * t
    if art == "trapez":
        schub = schub * np.where(dx % 2 == 0, 1.0, -1.0)
    X[innen, 0] += schub[innen]
    m.nodes = X
    # Winkelfehler des Elements an der Nachweisstelle
    wf, tf = 0.0, 0.0
    for e in m.elements:
        P = X[e.nodes]
        if np.all(np.abs(P.mean(axis=0) - np.array([kr.L / 2, kr.B / 2, kr.H])) < np.array([kr.L / nx, kr.B / ny, kr.H / nz])):
            wf = max(wf, sweep.winkelfehler(P, "hex8"))
            tf = max(tf, sweep.trapezfehler(P, "hex8"))
    verzerrt.trapez = tf
    try:
        res = _loesen(m)
    except ValueError as ex:                 # umgeklapptes Element
        return float("nan"), float("nan"), wf, kr.punkt(), str(ex)[:80]
    # der Knoten der Nachweisstelle nach der Verzerrung
    alt = kr.punkt()
    j = int(np.argmin(np.linalg.norm(np.asarray(kr.modell("hex8", nx, ny, nz)[0].nodes, float) - alt, axis=1)))
    punkt = X[j]
    f, soll = _fehler(m, res, kr, punkt)
    return f, soll, wf, punkt, ""


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ausgabe = ""
    if "--json" in argv:
        i = argv.index("--json")
        ausgabe = argv[i + 1]
        del argv[i:i + 2]
    kr = pk.Kragarm()
    print("Regelmaessiges hex8-Netz: Feinheit fuer 1 N/mm2", flush=True)
    netz, f0 = regelmaessig(kr)
    print(f"  gewaehlt: {netz}, Fehler {f0:+.2f} N/mm2", flush=True)
    # Gemessen wird am gewaehlten Netz und am naechstfeineren: der Fehler des
    # regelmaessigen Netzes (0,77 N/mm2 bei 8 x 2 x 4) zehrt sonst den ganzen
    # Spielraum auf, und die Grenze hinge an der Feinheit statt an der Form.
    netze = [netz] + [n for n in NETZE if n > netz][:1]
    tab = []
    for nz_ in netze:
        f_null = {}
        for art in ("parallelogramm", "trapez"):
            for theta in WINKEL:
                f, soll, wf, punkt, meldung = verzerrt(kr, nz_, art, theta)
                if theta == 0.0:
                    f_null[art] = f
                tab.append({"netz": list(nz_), "art": art, "theta": theta, "winkelfehler": wf,
                            "trapezfehler": getattr(verzerrt, "trapez", 0.0), "fehler": f,
                            "zuwachs": f - f_null[art], "soll": soll, "punkt": [float(v) for v in punkt],
                            "meldung": meldung})
                print(f"  {nz_} {art:15s} {theta:4.1f} Grad: Winkelfehler {wf:5.1f}, Trapezfehler "
                      f"{getattr(verzerrt, 'trapez', 0.0):5.1f}, Fehler {f:+7.2f} N/mm2, "
                      f"Zuwachs gegen 0 Grad {f - f_null[art]:+7.2f} (Soll {soll:.1f} an x = {punkt[0] * 1e3:.1f} mm)"
                      + (f" {meldung}" if meldung else ""), flush=True)
    grenze, grenze_zuwachs = {}, {}
    for art in ("parallelogramm", "trapez"):
        def bis(schluessel):
            # der groesste Winkel, bis zu dem **alle** kleineren die Schranke halten
            reihe = sorted((z["theta"], abs(z[schluessel])) for z in tab if z["art"] == art and z["netz"] == list(netz))
            aus_ = None
            for th, wert in reihe:
                if not (wert <= 1.0):
                    break
                aus_ = th
            return aus_
        grenze[art] = bis("fehler")
        grenze_zuwachs[art] = bis("zuwachs")
    def kleinstes(g):
        w = [v for v in g.values() if v is not None]
        return min(w) if w else None
    print(f"Groesster Winkel mit Fehler <= 1 N/mm2 (woertlich, am Netz {netz}): {grenze} -> {kleinstes(grenze)}", flush=True)
    print(f"Groesster Winkel mit Zuwachs <= 1 N/mm2 gegen das regelmaessige Netz: {grenze_zuwachs} -> {kleinstes(grenze_zuwachs)}", flush=True)
    if ausgabe:
        json.dump({"netz": netz, "netze": netze, "fehler_regelmaessig": f0, "tabelle": tab, "grenze": grenze,
                   "grenze_zuwachs": grenze_zuwachs, "vorschlag_woertlich": kleinstes(grenze),
                   "vorschlag_zuwachs": kleinstes(grenze_zuwachs)}, open(ausgabe, "w", encoding="utf-8"), indent=1)


if __name__ == "__main__":
    main()
