"""
Elementwahl je Koerper (statik3d.elementwahl, Auftrag B2 vom 22.09.2026):
tet10 dort, wo ein Nachweis gefuehrt wird und der Vorlauf Biegung oder einen
grossen Fehler zeigt; tet4 sonst.

Pruefmodell: drei getrennte Koerper aus Kuhn-Tetraedern in einem Modell -
  "Balken"   Kragarm 1,0 x 0,1 x 0,2 m unter Endquerkraft, mit Nachweis
  "Zugstab"  0,5 x 0,1 x 0,1 m unter Zug, mit Nachweis
  "Klotz"    wie der Balken, aber ohne Nachweis
Soll: Balken tet10, Zugstab und Klotz tet4; an den Nachweisstellen kostet die
Wahl hoechstens 1 N/mm2 gegenueber "ueberall tet10".

Aufruf:  python -m tests.test_elementwahl
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import elementwahl as ew                            # noqa: E402
from statik3d.elements import solid as sl                         # noqa: E402
from statik3d.model import Material, Model                        # noqa: E402
from tests import pruefkoerper as pk                              # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:74s} {detail}")
    return ok


def _box(m, gruppe, nx, ny, nz, L, B, H, x0):
    ids = {}
    for k in range(nz + 1):
        for j in range(ny + 1):
            for i in range(nx + 1):
                ids[(i, j, k)] = m.add_node(x0 + L * i / nx, B * j / ny, H * k / nz)
    els = []
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                z = [ids[(i + (x & 1), j + ((x >> 1) & 1), k + ((x >> 2) & 1))] for x in range(8)]
                for tet in pk.KUHN:
                    kn = [z[x] for x in tet]
                    if pk._tet_volumen(m.nodes[kn]) < 0:
                        kn[1], kn[2] = kn[2], kn[1]
                    els.append(m.add_element("tet4", kn, "S", group=gruppe))
    return ids, els


def modell():
    m = Model("Elementwahl")
    m.add_material(Material("S", E=210e9, nu=0.3, rho=0.0, fy=355e6))
    kr = pk.Kragarm()
    ib, eb = _box(m, "Balken", 8, 2, 4, kr.L, kr.B, kr.H, 0.0)
    iz, ez = _box(m, "Zugstab", 4, 2, 2, 0.5, 0.1, 0.1, 2.0)
    ik, ek = _box(m, "Klotz", 8, 2, 4, kr.L, kr.B, kr.H, 4.0)
    X = np.asarray(m.nodes, float)
    for n in range(m.nn):
        if abs(X[n, 0]) < 1e-9 or abs(X[n, 0] - 4.0) < 1e-9:
            m.fix(n, [0, 1, 2])
        if abs(X[n, 0] - 2.0) < 1e-9:
            m.fix(n, [0])
            if abs(X[n, 1]) < 1e-9:
                m.fix(n, [1])
            if abs(X[n, 2]) < 1e-9:
                m.fix(n, [2])
    for x_ende, F, richtung in ((kr.L, kr.F, (0, 0, -1)), (4.0 + kr.L, kr.F, (0, 0, -1)),
                                (2.5, 355e6 * 0.01, (1, 0, 0))):
        seiten = pk.randseiten(m, lambda P, xe=x_ende: bool(np.all(np.abs(P[:, 0] - xe) < 1e-9)))
        pk.schubkraft_auf_seiten(m, seiten, F, richtung)
    m.add_volumenbereich("Balken", eb)
    m.add_volumenbereich("Zugstab", ez)
    return m, ib, iz


def nachweisstellen(m, ib, iz):
    """Knoten: Balken Oberkante Mitte Breite bei L/2; Zugstab in der Mitte der Oberseite."""
    return {"Balken": ib[(4, 1, 4)], "Zugstab": iz[(2, 1, 2)]}


def knotenspannung(res, n):
    sk = res.solid_knoten
    j = np.flatnonzero(np.asarray(sk["knoten"]) == n)
    return sl.von_mises(np.asarray(sk["spannung"])[j[0]])


def test_vorschlag_und_kosten():
    m, ib, iz = modell()
    res, _t = pk.loese(m)
    v = ew.vorschlag(m, res)
    for zeile in ew.protokoll(v):
        print("     " + zeile)
    check("Balken: gebogen, mit Nachweis -> tet10", v["Balken"]["ordnung"] == 2
          and v["Balken"]["biegung"] > 0.6, f"Biegeanteil {v['Balken']['biegung']:.2f}")
    check("Zugstab: nicht gebogen, kleiner Fehler -> tet4", v["Zugstab"]["ordnung"] == 1
          and v["Zugstab"]["biegung"] < 0.05,
          f"Biegeanteil {v['Zugstab']['biegung']:.2f}, Fehler {v['Zugstab']['fehler'] * 100:.2f} %")
    check("Klotz: ohne Nachweis -> tet4, obwohl gebogen", v["Klotz"]["ordnung"] == 1
          and not v["Klotz"]["nachweis"] and v["Klotz"]["biegung"] > 0.6)
    check("das Protokoll nennt je Körper Ordnung und Grund",
          all(("tet10" in z or "tet4" in z) and " - " in z for z in ew.protokoll(v)))
    # Kosten der Wahl an den Nachweisstellen gegen "ueberall tet10"
    auto, _ = modell()[0], None
    ew.tet4_zu_tet10(auto, {k for k, w in v.items() if w["ordnung"] == 2})
    alle, _ = modell()[0], None
    ew.tet4_zu_tet10(alle, None)
    ra, _ = pk.loese(auto)
    rq, _ = pk.loese(alle)
    stellen = nachweisstellen(m, ib, iz)
    diff = {k: abs(knotenspannung(ra, n) - knotenspannung(rq, n)) / 1e6 for k, n in stellen.items()}
    check("automatische Wahl kostet an den Nachweisstellen höchstens 1 N/mm²",
          max(diff.values()) <= 1.0, ", ".join(f"{k} {d:.3f}" for k, d in diff.items()))
    fhg_auto, fhg_alle = pk.fhg(auto), pk.fhg(alle)
    check("... mit weniger Unbekannten als überall tet10", fhg_auto < fhg_alle,
          f"{fhg_auto} gegen {fhg_alle} FHG")
    # Vorgabe des Anwenders (Volumenkoerper.ordnung) gewinnt
    from statik3d.model import Volumenkoerper
    m.koerper["Zugstab"] = Volumenkoerper("Zugstab")
    m.koerper["Zugstab"].ordnung = 2
    v2 = ew.vorschlag(m, res)
    check("eine Vorgabe am Körper übersteuert den Vorschlag",
          v2["Zugstab"]["ordnung"] == 2 and "vorgegeben" in v2["Zugstab"]["grund"])


def test_ordnung_im_modell():
    """B1 (23.09.2026): Volumenkoerper.ordnung steht im Modell und im
    Speicherformat. Vorgabe None (automatisch, wie netz.ordnung bzw.
    elementwahl.vorschlag); eine aeltere Datei ohne das Feld laedt mit None;
    Model.check lehnt alles ausser None, 1 und 2 im Klartext ab."""
    from statik3d.model import Volumenkoerper
    m = modell()[0]
    for name in ("Balken", "Zugstab", "Klotz"):
        m.koerper[name] = Volumenkoerper(name)
    check("Vorgabe: keine Ordnung am Körper (automatisch)",
          all(k.ordnung is None for k in m.koerper.values()))
    m.koerper["Balken"].ordnung = 2
    m.koerper["Zugstab"].ordnung = 1
    d = m.to_dict()
    m2 = Model.from_dict(d)
    check("Umlauf to_dict/from_dict erhält die Ordnung je Körper",
          m2.koerper["Balken"].ordnung == 2 and m2.koerper["Zugstab"].ordnung == 1
          and m2.koerper["Klotz"].ordnung is None)
    for x in d.get("koerper", []):
        x.pop("ordnung", None)
    m3 = Model.from_dict(d)
    check("ältere Datei ohne das Feld lädt mit None", all(k.ordnung is None for k in m3.koerper.values()))
    falsch = []
    for wert, erlaubt in ((None, True), (1, True), (2, True), (3, False), (0, False), ("2", False),
                          (True, False), (2.0, False)):
        m.koerper["Klotz"].ordnung = wert
        meldung = [x for x in m.check() if "Elementordnung" in x and "Klotz" in x]
        if bool(meldung) == erlaubt:
            falsch.append(wert)
    check("Model.check: nur None, 1 und 2 erlaubt, sonst FEHLER im Klartext", not falsch,
          f"falsch beurteilt: {falsch}")


def main():
    print("=" * 100)
    print("STATIK3D - Elementwahl je Koerper (tet10 an den Nachweisstellen)")
    print("=" * 100)
    for t in (test_vorschlag_und_kosten, test_ordnung_im_modell):
        try:
            t()
        except Exception as ex:                  # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    ok = sum(1 for _n, o in RESULTS if o)
    print(f"\nErgebnis: {ok}/{len(RESULTS)} Pruefungen bestanden")
    return 0 if ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
