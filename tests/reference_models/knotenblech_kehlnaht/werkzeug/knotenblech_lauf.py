# -*- coding: utf-8 -*-
"""Tet10-Referenz Knotenblech mit Kehlnaht (Plan-Schritt 6a, 01.10.2026).

Rechnet das gmsh-Netz von Session B (C3D10) mit dem Hauptprogramm und legt die
Rohdaten ab: Knoten, Tet10-Knoten, Verschiebungen, Reaktionen und die
geglaetteten Eckspannungen des Loesers (res.solid_knoten). Ausgewertet wird
getrennt und unabhaengig (auswertung_a.py, auswertung_b.py).

Modi
  referenz  u_x = 0 auf x = 0, u_x = eps * 200 mm auf x = 200, quer frei;
            Starrkoerper: u_y = u_z = 0 am Knoten naechst (0, 40, -5),
            u_z = 0 am Knoten naechst (0, 80, -5).
  eichung   das exakte lineare Feld u = (eps x, -nu eps (y - 40), -nu eps (z + 5))
            auf ALLEN Randknoten vorgegeben. Die Loesung ist dann genau dieses
            Feld: sigma_xx = 100 N/mm2 ueberall, alle anderen Komponenten 0,
            Reaktion an x = 200 genau 80 000 N.

Aufruf: python knotenblech_lauf.py <baum> <netz.inp> <ausgabeordner> <modus>
"""
import hashlib
import json
import os
import subprocess
import sys
import time

import numpy as np

E = 210000.0e6          # Pa
NU = 0.3
EPS = 100.0 / 210000.0  # sigma_n / E


def netz_filtern(quelle, ziel):
    """Nur *NODE, *ELEMENT TYPE=C3D10 und *NSET uebernehmen. Die CPS6-Flaechen
    der Stirnseiten wuerde der Import als ebene Scheiben rechnen."""
    behalten = False
    with open(quelle, encoding="utf-8", errors="replace") as f, \
            open(ziel, "w", encoding="utf-8") as g:
        for zeile in f:
            if zeile.startswith("*") and not zeile.startswith("**"):
                kw = zeile.upper().replace(" ", "")
                behalten = (kw.startswith("*NODE") or kw.startswith("*NSET")
                            or (kw.startswith("*ELEMENT") and "TYPE=C3D10" in kw))
            if behalten:
                g.write(zeile)


def nset_groessen(quelle):
    groessen, name = {}, None
    with open(quelle, encoding="utf-8", errors="replace") as f:
        for zeile in f:
            if zeile.startswith("*"):
                kw = zeile.upper().replace(" ", "")
                name = kw.split("NSET=")[1].split(",")[0].strip() if kw.startswith("*NSET") else None
                if name:
                    groessen[name] = 0
                continue
            if name:
                groessen[name] += len([t for t in zeile.split(",") if t.strip()])
    return groessen


def sha256(pfad):
    h = hashlib.sha256()
    with open(pfad, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main():
    baum, netz, aus, modus = sys.argv[1:5]
    assert modus in ("referenz", "eichung"), modus
    os.makedirs(aus, exist_ok=True)
    sys.path.insert(0, baum)
    from statik3d.importers.abaqus import import_inp
    from statik3d.model import Material, Support
    from statik3d import solver

    commit = subprocess.run(["git", "-C", baum, "rev-parse", "HEAD"], capture_output=True,
                            text=True).stdout.strip()
    t0 = time.perf_counter()
    gef = os.path.join(aus, "netz_c3d10.inp")
    netz_filtern(netz, gef)
    log = []
    m = import_inp(gef, log=log, unit_scale=1e-3)
    typen = {}
    for e in m.elements:
        typen[e.typ] = typen.get(e.typ, 0) + 1
    assert set(typen) == {"tet10"}, typen
    m.add_material(Material("S_ref", E, NU))
    for e in m.elements:
        e.mat = "S_ref"
    X = np.asarray(m.nodes, float)
    T = np.array([e.nodes for e in m.elements], np.int64)
    benutzt = np.unique(T)

    s0 = np.flatnonzero(np.abs(X[:, 0]) < 1e-9)
    s200 = np.flatnonzero(np.abs(X[:, 0] - 0.2) < 1e-9)
    if modus == "referenz":
        a = int(s0[np.argmin(np.linalg.norm(X[s0] - [0.0, 0.04, -0.005], axis=1))])
        b = int(s0[np.argmin(np.linalg.norm(X[s0] - [0.0, 0.08, -0.005], axis=1))])
        for n in s0:
            if n == a:
                m.supports.append(Support(int(n), [0, 1, 2], [0.0, 0.0, 0.0]))
            elif n == b:
                m.supports.append(Support(int(n), [0, 2], [0.0, 0.0]))
            else:
                m.supports.append(Support(int(n), [0], [0.0]))
        for n in s200:
            m.supports.append(Support(int(n), [0], [EPS * 0.2]))
        starr = {"uy_uz_0": X[a].tolist(), "uz_0": X[b].tolist()}
    else:
        # Randknoten: Knoten der Seitenflaechen, die nur zu einem Tetraeder gehoeren
        seiten = {}
        flaechen = ((0, 1, 2, 4, 5, 6), (0, 1, 3, 4, 8, 7), (0, 2, 3, 6, 9, 7), (1, 2, 3, 5, 9, 8))
        for k in range(len(T)):
            for f in flaechen:
                schl = tuple(sorted(int(T[k, j]) for j in f[:3]))
                if schl in seiten:
                    seiten[schl] = None
                else:
                    seiten[schl] = [int(T[k, j]) for j in f]
        rand = sorted({n for v in seiten.values() if v for n in v})
        for n in rand:
            x, y, z = X[n]
            m.supports.append(Support(int(n), [0, 1, 2],
                                      [EPS * x, -NU * EPS * (y - 0.04), -NU * EPS * (z + 0.005)]))
        starr = {"randknoten": len(rand)}
    if not m.load_cases:
        m.add_load_case("LF1")
    t_aufbau = time.perf_counter() - t0

    t1 = time.perf_counter()
    res = solver.solve_static(m)
    t_rechnung = time.perf_counter() - t1

    np.save(os.path.join(aus, "knoten_m.npy"), X)
    np.save(os.path.join(aus, "tet10.npy"), T)
    np.save(os.path.join(aus, "u_m.npy"), np.asarray(res.u, float)[:, :3])
    np.save(os.path.join(aus, "reaktion_N.npy"), np.asarray(res.reactions, float)[:, :3])
    sk = res.solid_knoten or {}
    for schl in ("knoten", "gruppe", "spannung", "frei"):
        if schl in sk:
            np.save(os.path.join(aus, f"solid_knoten_{schl}.npy"), np.asarray(sk[schl]))
    rx200 = float(np.asarray(res.reactions, float)[s200, 0].sum())
    meta = {
        "modus": modus, "commit": commit, "netz": os.path.basename(netz), "netz_sha256": sha256(netz),
        "knoten_im_netz": int(len(X)), "knoten_benutzt": int(len(benutzt)),
        "elemente": typen, "stirn_x0": int(len(s0)), "stirn_x200": int(len(s200)),
        "nset_groessen_datei": nset_groessen(netz), "starrkoerper": starr,
        "reaktion_x_an_x200_N": rx200,
        "solid_knoten_gruppen": [list(g) for g in sk.get("gruppen", [])],
        "zeit_aufbau_s": round(t_aufbau, 1), "zeit_rechnung_s": round(t_rechnung, 1),
        "importprotokoll": [str(z) for z in log][:40],
        "info": {k: (v if isinstance(v, (int, float, str, bool)) else str(v)[:200])
                 for k, v in (getattr(res, "info", None) or {}).items()
                 if k in ("solver", "loeser", "backend", "residuum", "gestoerte_pivots", "freiheitsgrade")},
    }
    with open(os.path.join(aus, "lauf.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: meta[k] for k in ("modus", "commit", "knoten_benutzt", "elemente",
                                           "reaktion_x_an_x200_N", "zeit_rechnung_s")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
