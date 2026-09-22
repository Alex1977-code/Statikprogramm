"""
Messung (Abnahme Auftrag 4.3, plastische Grenzlast mit exaktem Sollwert):
dickwandiges Rohr a = 0,1 / b = 0,2 m unter Innendruck, ebene Dehnung,
ideal plastisch (von Mises, fy = 355 N/mm2, ohne Verfestigung).

Sollwerte nach Hill (1950), exakt fuer inkompressiblen Werkstoff (hier
nu = 0,4999), k = fy / sqrt(3), plastische Zone a <= r <= c:

    p(c)      = k (2 ln(c/a) + 1 - c^2/b^2),   Grenzlast p_L = 2 k ln(b/a)
    u_r(r)    = k c^2 / (2 G r)                (ueberall, volumentreu)
    plastisch:  sigma_r = -p + 2 k ln(r/a),  sigma_m = sigma_r + k,
                sigma_v = fy,  eps_p,eq = fy/(3G) (c^2/r^2 - 1)
    elastisch:  sigma_v = fy c^2 / r^2

Gemeldet je Typ und Netz: u_r(b) gegen Soll, sigma_v an der Aussenflaeche
(geglaettete Knotenspannung, elastisch), und am Integrationspunkt, der der
Innenflaeche am naechsten liegt: sigma_v, sigma_m und eps_p,eq gegen den
Sollwert **an seinem Radius** (misst das Element, nicht die Extrapolation).
Gerechnet wird, was das Programm ohne Verfestigung tut (Anfangsdehnungs-
Iteration), Toleranz 1e-6: bei nu = 0,4999 rauscht die Aenderung darunter
(1e-9 bis 2e-8, gemessen). Dazu je Typ, bei welchem Vielfachen von p_L die
Rechnung noch konvergiert (ein sperrendes Netz traegt ueber die Grenzlast
hinaus) - das mit dem Newton (E_t/E = 1e-300, also der Boden H_TANGENTE der
Tangente, sonst ideal plastisch): die Anfangsdehnung zieht sich bei p -> p_L
mit dem Faktor -> 1 zusammen, "nicht konvergiert" hiesse dort nichts.

Kein Test. Aufruf:  python -m tests.messung_rohr_plastisch [typ ...]
"""
from __future__ import annotations

import sys

import numpy as np

from statik3d import plastizitaet as pl
from statik3d import solver
from statik3d.elements import solid as sl
from tests import pruefkoerper as pk

FY = 355e6
NU = 0.4999


class Hill:
    def __init__(self, a=0.1, b=0.2, fy=FY, E=pk.E_ST):
        self.a, self.b, self.fy = a, b, fy
        self.k = fy / np.sqrt(3.0)
        self.G = E / 3.0                          # nu = 0,5

    def p(self, c):
        return self.k * (2 * np.log(c / self.a) + 1 - c * c / (self.b * self.b))

    def p_grenz(self):
        return 2 * self.k * np.log(self.b / self.a)

    def u_r(self, c, r):
        return self.k * c * c / (2 * self.G * r)

    def punkt(self, c, r):
        """(sigma_v, sigma_m, eps_p_eq) am Radius r."""
        if r <= c:
            sr = -self.p(c) + 2 * self.k * np.log(r / self.a)
            return self.fy, sr + self.k, self.fy / (3 * self.G) * (c * c / (r * r) - 1)
        return self.fy * c * c / (r * r), self.k * c * c / (self.b * self.b), 0.0


def modell(typ, n_t, n_r, p, laststufen=1, verfestigung=0.0, iterationen=200):
    rz = pk.Hohlzylinder(p=p)
    m = rz.modell(typ, n_t, n_r, nu=NU, fy=FY)
    m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=verfestigung, laststufen=laststufen,
                                     iterationen=iterationen, toleranz=1e-6)
    return m


def lauf(typ, n_t, n_r, c=0.15, verfestigung=0.0):
    h = Hill()
    m = modell(typ, n_t, n_r, h.p(c), verfestigung=verfestigung)
    res = solver.solve_static(m)
    inf = res.info["plastizitaet"]
    ok = f"{inf.get('verfahren')} {inf.get('iterationen')} Schr. " + ("konv." if inf.get("konvergiert") else "NICHT konv.")
    u = pk.verschiebungen(res, m)
    X = np.asarray(m.nodes, float)
    r = np.hypot(X[:, 0], X[:, 1])
    ecken = {int(n) for e in m.elements for n in e.nodes[:len(sl.ECKEN_NATUERLICH[e.typ])]}
    aussen = [n for n in range(m.nn) if abs(r[n] - h.b) < 1e-9 and n in ecken]
    ur = np.mean([(u[n, 0] * X[n, 0] + u[n, 1] * X[n, 1]) / r[n] for n in aussen])
    sk = res.solid_knoten
    pos = {int(k): j for j, k in enumerate(np.asarray(sk["knoten"]))}
    S = np.asarray(sk["spannung"])
    sv_b = np.mean([sl.von_mises(S[pos[n]]) for n in aussen])
    # Zustand an den Integrationspunkten: eine Laststufe, also die Rueckfuehrung
    # aus dem Anfangszustand bei der Endverschiebung (wie der Loeser rechnete)
    uu = np.asarray(res.u, float).ravel()
    el = pl._solid_elemente(m, None)
    _F, zst, _i = pl.schritt(m, uu, pl.Zustand(), m.plastizitaet, el)
    beste = None
    for i, (xi, sig) in pl.punktspannungen(m, uu, zst).items():
        e = m.elements[int(i)]
        Xe = X[e.nodes]
        for q in range(len(xi)):
            xp = sl.N_dN(e.typ, *xi[q])[0] @ Xe
            rp = float(np.hypot(xp[0], xp[1]))
            if beste is None or rp < beste[0]:
                beste = (rp, sig[q], float(np.asarray(zst.eps_p_eq[int(i)])[q]))
    rp, s, ep = beste
    sv_s, sm_s, ep_s = h.punkt(c, rp)
    return {"fhg": pk.fhg(m), "ok": ok, "u": ur / h.u_r(c, h.b),
            "sv_b": (sv_b - h.punkt(c, h.b)[0]) / 1e6,
            "r": rp, "sv": (sl.von_mises(s) - sv_s) / 1e6,
            "sm": (np.mean(s[:3]) - sm_s) / 1e6, "ep": ep / ep_s - 1}


def traegt(typ, n_t, n_r, faktor):
    h = Hill()
    m = modell(typ, n_t, n_r, faktor * h.p_grenz(), laststufen=4, verfestigung=1e-300,
               iterationen=40)
    res = solver.solve_static(m)
    return bool(res.info["plastizitaet"].get("konvergiert", False))


def main(argv=None):
    typen = list(sys.argv[1:] if argv is None else argv) or ["hex8", "tet10", "tet4"]
    h = Hill()
    print(f"Rohr a 0,1 / b 0,2 m, ebene Dehnung, fy 355, nu {NU}, ideal plastisch; "
          f"c/a = 1,5 bei p = {h.p(0.15) / 1e6:.2f} N/mm2, p_L = {h.p_grenz() / 1e6:.2f} N/mm2")
    netze = {"hex8": ((8, 4), (16, 8), (32, 16)), "tet10": ((8, 4), (16, 8)),
             "tet4": ((8, 4), (16, 8))}
    for typ in typen:
        for n_t, n_r in netze.get(typ, ((8, 4),)):
            try:
                z = lauf(typ, n_t, n_r)
                print(f"{typ:6s} {n_t:2d} x {n_r:2d} ({z['fhg']:5d} FHG) {z['ok']}: "
                      f"u_r(b) {z['u']:.4f}, sv(b) {z['sv_b']:+.2f} | Punkt r = {z['r']:.4f}: "
                      f"sv {z['sv']:+.2f}, sm {z['sm']:+.2f} N/mm2, ep {z['ep'] * 100:+.1f} %",
                      flush=True)
            except Exception as ex:                    # noqa: BLE001
                print(f"{typ:6s} {n_t:2d} x {n_r:2d}: {type(ex).__name__}: {ex}", flush=True)
        n_t, n_r = netze.get(typ, ((8, 4),))[0]
        z = [f"{f:.3f}: {'ja' if traegt(typ, n_t, n_r, f) else 'nein'}"
             for f in (0.97, 0.995, 1.005, 1.03)]
        print(f"{typ:6s} {n_t:2d} x {n_r:2d}: traegt p/p_L " + ", ".join(z), flush=True)


if __name__ == "__main__":
    main()
