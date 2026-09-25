"""
Messung: was der Uebergang hex8 -> Pyramide -> Tetraeder nahe der
Nachweisstelle kostet (dritter Auftrag der Statik3D-Sitzung, 24.09.2026,
Aufgabe 4).

Kragarm wie in V5 (tests/pruefkoerper.Kragarm: 1,0 x 0,1 x 0,2 m, Soll 355
N/mm2 an (L/2, B/2, H)), als Geometrie fuer den Vernetzer in **zwei Koerpern**
mit der Fuge bei x = L/2 - genau an der Nachweisstelle:

    A  x in [0, L/2]   Quader, abgebildetes hex8-Gitter
    B  x in [L/2, L]   Deckel geteilt, hintere Ecke um 20 mm angehoben,
                       damit ihn kein Sweep und kein abgebildeter Pfad nimmt

Drei Netze derselben Kantenlaenge:
    hex8       das strukturierte hex8-Netz des Pruefkoerpers (pk.Kragarm.modell)
    uebergang  A hex8 (abgebildet), B frei mit Pyramiden an der Fuge
    tet4       beide frei (B abgebildet? nein - A wird dafuer wie B verwunden)

Gemessen wird der Fehler an der Nachweisstelle (Mittel der Elementfelder,
pk.punktspannung) und die Unbekannten. Kein Test. Aufruf:

    python -m tests.messung_uebergang_pyramiden [--h mm] [--json datei]
"""
from __future__ import annotations

import contextlib
import io
import json
import sys

import numpy as np

from statik3d import mesher, solver
from statik3d.model import Model, Material
from tests import pruefkoerper as pk


def geometrie(m: Model, kr, dz: float = 0.02, a_frei: bool = False, h_teilung: float = 0.025):
    """A: Quader mit sechs Flaechen - der abgebildete Quaderpfad, ein
    regelmaessiges hex8-Gitter (der Sweep pflastert die Grundflaeche aus
    gepaarten Dreiecken und kommt an einem Rechteck auf 43 Grad Winkelfehler).
    B: Deckel bei x = 3L/4 geteilt, die hintere Ecke um dz angehoben - weder
    abgebildet noch sweepbar (Kappen nicht deckungsgleich): der freie
    Vernetzer, an der Fuge mit Pyramiden."""
    L, B, H = kr.L, kr.B, kr.H
    P = [(0, 0, 0), (L / 2, 0, 0), (L, 0, 0), (L, B, 0), (L / 2, B, 0), (0, B, 0),
         (0, 0, H), (L / 2, 0, H), (L, 0, H), (L, B, H + dz), (L / 2, B, H), (0, B, H),
         (L / 4, 0, 0), (L / 4, B, 0), (3 * L / 4, 0, H), (3 * L / 4, B, H)]
    # A mit geteiltem Boden (a_frei): sieben Flaechen, also nicht abgebildet -
    # und mit sweep "aus" frei vernetzt (die reine Tetraeder-Vergleichsrechnung).
    # Die Teilungspunkte 12 und 13 gibt es nur dann: ein Knoten ohne Linie
    # waere in der Abnahme ein "Knoten ohne Element".
    n = ([m.add_node(*p) for p in P[:12]]
         + ([m.add_node(*p) for p in P[12:14]] if a_frei else [None, None])
         + [m.add_node(*p) for p in P[14:]])
    kanten: dict = {}

    def linie(a, b):
        key = (min(a, b), max(a, b))
        if key not in kanten:
            kanten[key] = f"L{len(kanten)}"
            m.add_line(kanten[key], [n[a], n[b]])
        return kanten[key]

    def flaeche(name, q):
        m.add_flaeche(name, [linie(q[i], q[(i + 1) % len(q)]) for i in range(len(q))], material="S")
        return name
    if a_frei:
        fa = [flaeche("A_Boden1", (0, 12, 13, 5)), flaeche("A_Boden2", (12, 1, 4, 13)),
              flaeche("A_Deckel", (6, 7, 10, 11)), flaeche("A_Einsp", (0, 5, 11, 6)),
              flaeche("Fuge", (1, 4, 10, 7)), flaeche("A_Vorn", (0, 12, 1, 7, 6)), flaeche("A_Hinten", (5, 13, 4, 10, 11))]
    else:
        fa = [flaeche("A_Boden", (0, 1, 4, 5)), flaeche("A_Deckel", (6, 7, 10, 11)), flaeche("A_Einsp", (0, 5, 11, 6)),
              flaeche("Fuge", (1, 4, 10, 7)), flaeche("A_Vorn", (0, 1, 7, 6)), flaeche("A_Hinten", (5, 4, 10, 11))]
    fb = [flaeche("B_Boden", (1, 2, 3, 4)), flaeche("B_Deckel1", (7, 14, 15, 10)), flaeche("B_Deckel2", (14, 8, 9, 15)),
          flaeche("B_Stirn", (2, 3, 9, 8)), "Fuge", flaeche("B_Vorn", (1, 2, 8, 14, 7)),
          flaeche("B_Hinten", (4, 3, 9, 15, 10))]
    kA = m.add_koerper("A", fa, material="S")
    kB = m.add_koerper("B", fb, material="S")
    if not a_frei:
        # der abgebildete Quader nimmt seine Teilung vom Koerper (Vorgabe 4 x 4 x 4)
        kA.teilung = [int(round(L / 2 / h_teilung)), int(round(B / h_teilung)), int(round(H / h_teilung))]
    return kA, kB


def lager_lasten(m: Model, kr):
    m.supports.clear()
    lc = m.case()
    lc.nodal_loads.clear()
    lc.face_loads.clear()
    tol = 1e-9 * kr.L
    pk.einspannen(m, lambda X: bool(np.all(np.abs(X[:, 0]) < tol)))
    seiten = pk.randseiten(m, lambda X: bool(np.all(np.abs(X[:, 0] - kr.L) < tol)))
    pk.schubkraft_auf_seiten(m, seiten, kr.F, (0.0, 0.0, -1.0))


def lauf(art: str, h: float, kr) -> dict:
    log = []
    if art == "hex8":
        nx, ny, nz = (round(kr.L / h), max(1, round(kr.B / h)), max(1, round(kr.H / h)))
        m, _ids = kr.modell("hex8", nx, ny, nz)
    else:
        m = Model(f"uebergang_{art}")
        m.add_material(Material("S", E=pk.E_ST, nu=pk.NU_ST, rho=0.0))
        kA, kB = geometrie(m, kr, a_frei=(art == "tet4"), h_teilung=h)
        m.netz.sweep = {"uebergang": "sauber", "tet4": "aus"}[art]
        m.netz.pyramiden = art == "uebergang"
        m.netz.ziellaenge = h
        m.netz.dichte = "eigene"
        with contextlib.redirect_stdout(io.StringIO()):
            mesher.modell_vernetzen(m, log, workers=1)
        lager_lasten(m, kr)
    r = solver.solve_all(m, workers=1)
    res = next(iter(r.cases.values()))
    ps = pk.punktspannung(m, res, kr.punkt())
    typen: dict = {}
    for e in m.elements:
        typen[e.typ] = typen.get(e.typ, 0) + 1
    # dazu je ein Element weit in den hex8-Teil (x = L/2 - h) und in den
    # Tetraederteil (x = L/2 + h), Soll dort nach Saint-Venant
    daneben = {}
    for tag, dx in (("hex_seite", -h), ("tet_seite", +h)):
        punkt = kr.punkt() + np.array([dx, 0.0, 0.0])
        soll = kr.F * (kr.L - punkt[0]) * (0.5 * kr.H) / kr.I / 1e6
        try:
            q = pk.punktspannung(m, res, punkt)
            daneben[tag] = float(q["sv_mittel"] / 1e6 - soll)
        except Exception as ex:                 # noqa: BLE001
            daneben[tag] = str(ex)[:60]
    aus = {"art": art, "h_mm": h * 1e3, "typen": typen, "knoten": int(m.nn), "unbekannte": 3 * int(m.nn),
           "fehler": float(ps["sv_mittel"] / 1e6 - kr.sigma_soll() / 1e6),
           "spanne": [float(ps["sv_min"] / 1e6 - 355.0), float(ps["sv_max"] / 1e6 - 355.0)],
           "daneben": daneben,
           "protokoll": [z.strip()[:120] for z in log if "gesweept" in z or "Pyramiden" in z or "nicht gesweept" in z][:6]}
    print(f"  {art:9s} h = {h * 1e3:.0f} mm: {typen}, {aus['unbekannte']} Unbekannte, Fehler {aus['fehler']:+.2f} N/mm2 "
          f"(Spanne {aus['spanne'][0]:+.1f} … {aus['spanne'][1]:+.1f}); ein Element daneben: {daneben}", flush=True)
    for z in aus["protokoll"]:
        print("      ", z, flush=True)
    return aus


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    h, ausgabe = 0.025, ""
    if "--h" in argv:
        i = argv.index("--h")
        h = float(argv[i + 1]) * 1e-3
        del argv[i:i + 2]
    if "--json" in argv:
        i = argv.index("--json")
        ausgabe = argv[i + 1]
        del argv[i:i + 2]
    kr = pk.Kragarm()
    alles = [lauf(art, h, kr) for art in ("hex8", "uebergang", "tet4")]
    if ausgabe:
        json.dump(alles, open(ausgabe, "w", encoding="utf-8"), indent=1)
    return alles


if __name__ == "__main__":
    main()
