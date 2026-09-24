"""
Messung V5 (zweiter Auftrag der Statik3D-Sitzung, 23.09.2026): adaptive
Verfeinerung bis 1 N/mm2 mit dem **freien Vernetzer** - am Kragarm und an der
Lame-Hohlkugel (beide mit exakter Loesung, tests/pruefkoerper.py), fuer tet4,
tet10 und das Element mit Ordnung p (tetp2 ueberall, tetp4 in einer Lage an
der gekruemmten Innenflaeche).

Die Schleife ist die von statik3d.adaptiv, nur mit dem Abbruch an der
Nachweisstelle statt am geschaetzten Gesamtfehler:

    vernetzen (mesher.modell_vernetzen, Groessenfeld aus netz.feldpunkte)
    -> Lager und Lasten auf das neue Netz
    -> rechnen (solver.solve_all, ein Lastfall)
    -> Fehler an der Nachweisstelle gegen die exakte Loesung
    -> wenn > 1 N/mm2: netzfehler.indikator, neue_kantenlaengen,
       koerper_kantenlaengen, feldpunkte -> naechster Durchgang

Gemeldet je Durchgang: Elemente, Knoten, Unbekannte (3 je Knoten; beim tetp
dazu die Zusatzfreiheitsgrade je Kante und Seite), Fehler, Zeiten.

Kragarm 1,0 x 0,1 x 0,2 m: Nachweisstelle (L/2, B/2, H), Soll 355 N/mm2
(Saint-Venant); Fehler = Mittel der Elementfelder am Punkt minus Soll.
Hohlkugel a = 0,1, b = 0,2 m (Achtel, Symmetrie): Soll sigma_v(a) = 355 N/mm2;
Fehler = groesste Abweichung der geglaetteten Knotenspannung an den Eckknoten
der Innenflaeche (wie tests/messung_hohlkugel.py), daneben das Mittel.

Kein Test (steht nicht in run_all). Aufruf:

    python -m tests.messung_adaptiv_v5 [kragarm|hohlkugel] [tet4 tet10 tetp2 tetp4innen ...]
                                       [--runden N] [--h0 mm] [--ziel N/mm2] [--json datei]
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import time

import numpy as np

from statik3d import mesher, netzfehler
from statik3d.elements import solid as sl
from statik3d.model import Model, Material
from tests import pruefkoerper as pk

TYPEN = ("tet4", "tet10", "tetp2", "tetp4innen")


# --------------------------------------------------------------------------
# Geometrie fuer den freien Vernetzer
# --------------------------------------------------------------------------
def kragarm_geometrie(m: Model, kr) -> object:
    """Quader [0,L] x [0,B] x [0,H] als Volumenkoerper. Der Deckel ist bei
    x = L/2 in zwei Flaechen geteilt: so ist der Koerper kein Sechsflaechner
    mehr und geht an den **freien** Vernetzer (mesher.abgebildet), und die
    Nachweisstelle (L/2, B/2, H) liegt auf einer Huelllinie."""
    L, B, H = kr.L, kr.B, kr.H
    P = [(0, 0, 0), (L, 0, 0), (L, B, 0), (0, B, 0), (0, 0, H), (L, 0, H), (L, B, H), (0, B, H),
         (0.5 * L, 0, H), (0.5 * L, B, H)]
    n = [m.add_node(*p) for p in P]
    kanten: dict = {}

    def linie(a, b):
        key = (min(a, b), max(a, b))
        if key not in kanten:
            kanten[key] = f"L{len(kanten)}"
            m.add_line(kanten[key], [n[a], n[b]])
        return kanten[key]
    fl = []
    for nm, q in (("Boden", (0, 1, 2, 3)), ("Deckel1", (4, 8, 9, 7)), ("Deckel2", (8, 5, 6, 9)),
                  ("Einspannung", (0, 3, 7, 4)), ("Stirn", (1, 2, 6, 5)),
                  ("Vorn", (0, 1, 5, 8, 4)), ("Hinten", (3, 2, 6, 9, 7))):
        m.add_flaeche(nm, [linie(q[i], q[(i + 1) % len(q)]) for i in range(len(q))], material="S")
        fl.append(nm)
    return m.add_koerper("K", fl, material="S")


def hohlkugel_geometrie(m: Model, hk) -> object:
    """Achtel der Hohlkugel a <= r <= b: zwei Kugelflaechen aus je drei
    Grosskreisboegen, drei ebene Viertelringe in den Symmetrieebenen."""
    a, b = hk.a, hk.b
    s2 = 1 / np.sqrt(2)
    ia = [m.add_node(a, 0, 0), m.add_node(0, a, 0), m.add_node(0, 0, a)]
    ib = [m.add_node(b, 0, 0), m.add_node(0, b, 0), m.add_node(0, 0, b)]

    def bogen(nm, kn, r, ij):
        P = {0: (r, 0, 0), 1: (0, r, 0), 2: (0, 0, r)}
        mitte = {(0, 1): (r * s2, r * s2, 0), (1, 2): (0, r * s2, r * s2), (0, 2): (r * s2, 0, r * s2)}
        i, j = ij
        m.add_line(nm, [kn[i], kn[j]], "arc", punkte=[P[i], mitte[(min(i, j), max(i, j))], P[j]])
    for tag, kn, r in (("I", ia, a), ("A", ib, b)):
        bogen(f"{tag}xy", kn, r, (0, 1))
        bogen(f"{tag}yz", kn, r, (1, 2))
        bogen(f"{tag}zx", kn, r, (2, 0))
    m.add_line("Rx", [ia[0], ib[0]])
    m.add_line("Ry", [ia[1], ib[1]])
    m.add_line("Rz", [ia[2], ib[2]])
    m.add_flaeche("innen", ["Ixy", "Iyz", "Izx"], material="S")
    m.add_flaeche("aussen", ["Axy", "Ayz", "Azx"], material="S")
    m.add_flaeche("Ez", ["Ixy", "Ry", "Axy", "Rx"], material="S")
    m.add_flaeche("Ex", ["Iyz", "Rz", "Ayz", "Ry"], material="S")
    m.add_flaeche("Ey", ["Izx", "Rx", "Azx", "Rz"], material="S")
    return m.add_koerper("K", ["innen", "aussen", "Ez", "Ex", "Ey"], material="S")


# --------------------------------------------------------------------------
# Lager, Lasten, Elementtyp je Durchgang
# --------------------------------------------------------------------------
def _tetp_umstellen(m: Model, typ: str, radien: tuple = ()) -> None:
    """Das **tet10**-Netz des Vernetzers (Ordnung 2: Seitenmitten auf der
    wahren Flaeche, Jacobi-Determinante geprueft, wo noetig oertlich feiner)
    in tetp umstellen: die Ecken bleiben, die Seitenmittenknoten (vom Einbau
    hinten angehaengt) fallen weg, gekruemmte Kanten gehen als
    ``tetp_kantenmitten`` mit. tetp2 ueberall bzw. tetp4 in den Elementen mit
    einer Ecke auf dem ersten Halbmesser in ``radien`` (die Innenflaeche),
    sonst tetp2 - wie tests/messung_tetp_hohlkugel.py."""
    from statik3d.elements import tetp as tp
    X = np.asarray(m.nodes, float)
    ecken = [[int(x) for x in e.nodes[:4]] for e in m.elements]
    n_ecken = max(max(kn) for kn in ecken) + 1
    km: dict = {}
    for e, kn in zip(m.elements, ecken):
        if len(e.nodes) >= 10:
            for (a, b), mid in zip(tp.TET10_KANTEN, [int(x) for x in e.nodes[4:10]]):
                if mid < n_ecken:
                    continue
                gerade = 0.5 * (X[kn[a]] + X[kn[b]])
                if np.linalg.norm(X[mid] - gerade) > 1e-12:
                    km[(min(kn[a], kn[b]), max(kn[a], kn[b]))] = X[mid].copy()
    r = np.linalg.norm(X, axis=1)
    innen = np.abs(r - radien[0]) < 1e-9 if radien else np.zeros(len(X), bool)
    for e, kn in zip(m.elements, ecken):
        e.nodes = list(kn)
        if typ == "tetp4innen":
            e.typ = "tetp4" if innen[kn].any() else "tetp2"
        else:
            e.typ = typ
    if len(X) > n_ecken:
        m.nodes = X[:n_ecken].copy()
    m._tetp_version = getattr(m, "_tetp_version", 0) + 1
    m.tetp_kantenmitten = km


def _tetp_gerade_lassen(m: Model, meldung: str) -> int:
    """Nennt der Loeser ein umgeklapptes tetp-Element, bleiben seine
    gekruemmten Kanten gerade (wie der tet10-Einbau es an gemeinsamen
    Flaechen tut); Rueckgabe: Zahl der gerade gelassenen Kanten."""
    import re
    from statik3d.elements import tetp as tp
    nr = re.search(r"Element (\d+)", meldung)
    if nr is None:
        return 0
    e = m.elements[int(nr.group(1))]
    kn = [int(x) for x in e.nodes[:4]]
    weg = 0
    for a, b in tp.TET10_KANTEN:
        key = (min(kn[a], kn[b]), max(kn[a], kn[b]))
        if key in m.tetp_kantenmitten:
            del m.tetp_kantenmitten[key]
            weg += 1
    m._tetp_version = getattr(m, "_tetp_version", 0) + 1
    return weg


def _fhg(m: Model) -> int:
    """Unbekannte: drei je Knoten; beim tetp dazu die Zusatzfreiheitsgrade
    je Kante ((p-1) x 3) und je Seite ((p-1)(p-2)/2 x 3) - hergeleitet aus der
    Knoten-, Kanten- und Seitenzahl des Netzes."""
    from statik3d.elements import tetp as tp
    n = 3 * m.nn
    kanten: dict = {}
    seiten: dict = {}
    for e in m.elements:
        p = tp.TYPEN.get(e.typ)
        if not p:
            continue
        kn = [int(x) for x in e.nodes[:4]]
        for a, b in tp.KANTEN:
            key = (min(kn[a], kn[b]), max(kn[a], kn[b]))
            kanten[key] = max(kanten.get(key, 0), p)
        for f in tp.FLAECHEN:
            key = tuple(sorted(kn[i] for i in f))
            seiten[key] = max(seiten.get(key, 0), p)
    n += 3 * sum(p - 1 for p in kanten.values())
    n += 3 * sum((p - 1) * (p - 2) // 2 for p in seiten.values())
    return int(n)


def _loesen(m: Model):
    """Ein Lastfall, **seriell** (workers=1): die parallele Nachbereitung des
    Loesers fuehrte die geglaettete Knotenspannung nicht fuer alle Knoten
    (res.solid_knoten) und brach bei tetp mit "max() iterable argument is
    empty" ab (gemessen 24.09.2026)."""
    from statik3d import solver
    try:
        r = solver.solve_all(m, workers=1)
    except TypeError:
        r = solver.solve_all(m)
    return next(iter(r.cases.values()))


def kragarm_lager_lasten(m: Model, kr) -> None:
    m.supports.clear()
    lc = m.case()
    lc.nodal_loads.clear()
    lc.face_loads.clear()
    tol = 1e-9 * kr.L
    pk.einspannen(m, lambda X: bool(np.all(np.abs(X[:, 0]) < tol)))
    seiten = pk.randseiten(m, lambda X: bool(np.all(np.abs(X[:, 0] - kr.L) < tol)))
    pk.schubkraft_auf_seiten(m, seiten, kr.F, (0.0, 0.0, -1.0))


def hohlkugel_lager_lasten(m: Model, hk) -> None:
    m.supports.clear()
    lc = m.case()
    lc.nodal_loads.clear()
    lc.face_loads.clear()
    X = np.asarray(m.nodes, float)
    tol = 1e-9 * hk.b
    for n in range(m.nn):
        dofs = [d for d in range(3) if abs(X[n, d]) < tol]
        if dofs:
            m.fix(n, dofs)
    for e, s in m.flaechen["innen"].randseiten:
        m.load_face(int(e), hk.p, int(s))


# --------------------------------------------------------------------------
# Fehler an der Nachweisstelle
# --------------------------------------------------------------------------
def kragarm_fehler(m: Model, res, kr) -> dict:
    """tet4/tet10: Mittel der Elementfelder am Punkt (pk.punktspannung). tetp:
    die Elementfelder kennt pruefkoerper nicht - die geglaettete
    Knotenspannung (res.solid_knoten) am naechsten Knoten der Deckflaeche;
    die Nachweisstelle liegt auf der Huelllinie x = L/2, dort steht bei
    gerader Teilung der Breite ein Knoten."""
    if any(e.typ.startswith("tetp") for e in m.elements):
        sk = res.solid_knoten
        kn = np.asarray(sk["knoten"], int)
        X = np.asarray(m.nodes, float)[kn]
        d = np.linalg.norm(X - kr.punkt(), axis=1)
        j = int(np.argmin(d))
        sv = float(sl.von_mises(np.asarray(sk["spannung"])[j])) / 1e6
        return {"fehler": sv - kr.sigma_soll() / 1e6, "fehler_max": abs(sv - kr.sigma_soll() / 1e6),
                "sv": sv, "abstand_knoten": float(d[j])}
    ps = pk.punktspannung(m, res, kr.punkt())
    return {"fehler": float(ps["sv_mittel"] / 1e6 - kr.sigma_soll() / 1e6),
            "fehler_max": float(max(abs(ps["sv_min"] / 1e6 - 355.0), abs(ps["sv_max"] / 1e6 - 355.0))),
            "sv": float(ps["sv_mittel"] / 1e6)}


def hohlkugel_fehler(m: Model, res, hk) -> dict:
    sk = res.solid_knoten
    pos = {int(k): j for j, k in enumerate(np.asarray(sk["knoten"]))}
    S = np.asarray(sk["spannung"])
    X = np.asarray(m.nodes, float)
    r = np.linalg.norm(X, axis=1)
    ecken = {int(n) for e in m.elements for n in e.nodes[:4]}
    auf_a = [n for n in ecken if abs(r[n] - hk.a) < 1e-9 * hk.b]
    innen = [n for n in auf_a if n in pos]
    if not innen:
        return {"fehler": float("nan"), "fehler_max": float("nan"), "sv": float("nan"),
                "innenknoten": 0, "auf_a": len(auf_a), "in_solid_knoten": len(pos)}
    f = np.array([sl.von_mises(S[pos[n]]) for n in innen]) / 1e6 - hk.sigma / 1e6
    return {"fehler": float(f.mean()), "fehler_max": float(np.abs(f).max()), "sv": float(f.mean() + hk.sigma / 1e6),
            "innenknoten": len(innen), "auf_a": len(auf_a)}


# --------------------------------------------------------------------------
# Die Schleife
# --------------------------------------------------------------------------
def lauf(koerper: str, typ: str, runden: int = 6, h0: float = 0.0, ziel: float = 1.0,
         log: list = None) -> list:
    log = [] if log is None else log
    m = Model(f"{koerper}_{typ}")
    m.add_material(Material("S", E=pk.E_ST, nu=pk.NU_ST, rho=0.0))
    if koerper == "kragarm":
        kr = pk.Kragarm()
        k = kragarm_geometrie(m, kr)
        h = h0 or 0.05
        radien = ()
    else:
        kr = pk.Hohlkugel()
        k = hohlkugel_geometrie(m, kr)
        h = h0 or 0.03
        radien = (kr.a, kr.b)
    m.netz.sweep = False
    m.netz.dichte = "eigene"
    m.netz.ziellaenge = h
    m.netz.nachvernetzen = True
    if typ == "tet10" or typ.startswith("tetp"):
        k.ordnung = 2                       # tetp entsteht aus dem geprueften tet10-Netz
    verlauf = []
    for runde in range(runden + 1):
        t0 = time.time()
        # Lager und Lasten des alten Netzes weg, **bevor** neu vernetzt wird:
        # der Vernetzer behielte sonst die belasteten Knoten ohne Element
        m.supports.clear()
        lc = m.case()
        lc.nodal_loads.clear()
        lc.face_loads.clear()
        with contextlib.redirect_stdout(io.StringIO()):
            mesher.modell_vernetzen(m, log, workers=1)
        if typ.startswith("tetp"):
            _tetp_umstellen(m, typ, radien)
        if koerper == "kragarm":
            kragarm_lager_lasten(m, kr)
        else:
            hohlkugel_lager_lasten(m, kr)
        t_netz = time.time() - t0
        t0 = time.time()
        gerade = 0
        for _versuch in range(6):
            try:
                res = _loesen(m)
                break
            except ValueError as ex:
                if "Ordnung p" not in str(ex) or not typ.startswith("tetp"):
                    raise
                n = _tetp_gerade_lassen(m, str(ex))
                if not n:
                    raise
                gerade += n
                print(f"  {typ}: {str(ex)[:90]} ... - {n} Kante(n) gerade gelassen", flush=True)
        t_rechnen = time.time() - t0
        f = kragarm_fehler(m, res, kr) if koerper == "kragarm" else hohlkugel_fehler(m, res, kr)
        schritt = {"runde": runde, "typ": typ, "elemente": len(m.elements), "knoten": int(m.nn),
                   "gerade_gelassen": gerade,
                   "unbekannte": _fhg(m), "h_koerper": float(m.netz.koerper_h.get("K", m.netz.ziellaenge))
                   if getattr(m.netz, "koerper_h", None) else float(m.netz.ziellaenge),
                   "feldpunkte": len(getattr(m.netz, "feldpunkte", None) or []),
                   "t_netz": t_netz, "t_rechnen": t_rechnen, **f}
        verlauf.append(schritt)
        print(f"  {koerper} {typ:9s} Durchgang {runde + 1}: {schritt['elemente']:7d} Elemente, "
              f"{schritt['knoten']:7d} Knoten, {schritt['unbekannte']:8d} Unbekannte, "
              f"Fehler {f['fehler']:+7.2f} N/mm2 (groesster {f['fehler_max']:6.2f}), "
              f"Netz {t_netz:5.1f} s, Rechnung {t_rechnen:5.1f} s", flush=True)
        if abs(f["fehler"]) <= ziel or runde >= runden:
            break
        ind = netzfehler.indikator(m, [res])
        if not ind["N"]:
            print("  kein Indikator (keine Tetraeder erkannt) - Ende", flush=True)
            break
        kal = netzfehler.kalibrierung_fuer(m, ind)
        h_neu = netzfehler.neue_kantenlaengen(ind, netzfehler.ZIEL, kalibrierung=kal)
        koerper_h = netzfehler.koerper_kantenlaengen(m, ind, h_neu)
        m.netz.koerper_h = dict(getattr(m.netz, "koerper_h", None) or {})
        m.netz.koerper_h.update(koerper_h)
        m.netz.feldpunkte = netzfehler.feldpunkte(m, ind, h_neu, m.netz.koerper_h)
        if koerper_h:
            m.netz.ziellaenge = float(min(koerper_h.values()))
    return verlauf


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    runden, h0, ziel, ausgabe = 6, 0.0, 1.0, ""
    for flag in ("--runden", "--h0", "--ziel", "--json"):
        if flag in argv:
            i = argv.index(flag)
            wert = argv[i + 1]
            del argv[i:i + 2]
            if flag == "--runden":
                runden = int(wert)
            elif flag == "--h0":
                h0 = float(wert) * 1e-3
            elif flag == "--ziel":
                ziel = float(wert)
            else:
                ausgabe = wert
    koerper = [a for a in argv if a in ("kragarm", "hohlkugel")] or ["kragarm", "hohlkugel"]
    typen = [a for a in argv if a in TYPEN] or list(TYPEN)
    alles = {}
    for kn in koerper:
        for typ in typen:
            print(f"== {kn}, {typ}, Ziel {ziel} N/mm2, hoechstens {runden} Verfeinerungen", flush=True)
            try:
                alles[f"{kn}/{typ}"] = lauf(kn, typ, runden=runden, h0=h0, ziel=ziel)
            except Exception as ex:                     # noqa: BLE001
                import traceback
                traceback.print_exc()
                print(f"  {kn} {typ}: {type(ex).__name__}: {str(ex)[:160]}", flush=True)
                alles[f"{kn}/{typ}"] = {"fehler": f"{type(ex).__name__}: {str(ex)[:200]}"}
    if ausgabe:
        with open(ausgabe, "w", encoding="utf-8") as f:
            json.dump(alles, f, indent=1)
    return alles


if __name__ == "__main__":
    main()
