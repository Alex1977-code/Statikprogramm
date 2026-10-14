"""
Rand der netzabhaengigen Zonen: unstetige Faerbung (14.10.2026).

Auftrag nach dem Bild V21 in normaler Skala vom 13.10.2026: ein grosser Teil
der Platte ausserhalb der Schraffur war magenta („> Skalenmax“), weil die
Randknoten der Zone - Knoten, an denen Zonen- und Aussenelemente haengen -
ueber beide gemittelt wurden. An V21 lagen 131 von 226 Randknoten ueber dem
Groesstwert ausserhalb (207,1 N/mm2, bis 484,8), und 318 Aussenelemente
(29,5 % des Volumens ausserhalb) zogen die Farbe von dort herein.

Jetzt: die Faerbung der Randknoten nimmt nur die Aussenelemente, die
Zonenelemente bekommen fuer ihre Darstellung eigene Knotenwerte - an der
Zonengrenze ist die Faerbung unstetig. Skala, Max/Min-Marke, Kennwerte und
Uebersicht nehmen ausserhalb dieselben Werte (Randknoten mit dem Mittel der
Aussenelemente). Die Knotenregel der Nachweise kennt das Mittel nur ueber
alle Elemente eines Koerpers (solid_knoten): dort zaehlen die Randknoten zur
Zone, wie es die Ermuedung schon tat; der Volumennachweis las bis zum
14.10.2026 an Aussenelementen die gemischte Ecke.

Geprueft an der Platte mit Loch (elastisch, tests.test_spitzen_zeigen._platte)
gegen eine eigene Mittelung aus den Elementwerten.

Aufruf:  python -m tests.test_zonenrand
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_zonenrand_"), "einstellungen.json")

import numpy as np  # noqa: E402

from statik3d import spannungen as spn, spitzenstellen as sp, spitzenanzeige as sa  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FEHLER'} {name:78s} {detail}")
    return bool(ok)


def _eigene(m, r, zone: set):
    """Eigene Mittelung (elastisch): je Volumenelement sein Wert sigma_v
    (solid_res) an allen seinen Knoten, getrennt nach Zone und aussen; dazu die
    Staebe (sig_max) fuer die Vergleichsspannung der Uebersicht."""
    nn = m.nn
    sa_, ca_, sz_, cz_ = np.zeros(nn), np.zeros(nn), np.zeros(nn), np.zeros(nn)
    for i, S in r.solid_res.items():
        v = float(spn.volumen_werte(np.asarray(S, float).reshape(1, 6), "sv")[0])
        kn = np.asarray(m.elements[i].nodes, int)
        if int(i) in zone:
            np.add.at(sz_, kn, v)
            np.add.at(cz_, kn, 1.0)
        else:
            np.add.at(sa_, kn, v)
            np.add.at(ca_, kn, 1.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        aussen = np.where(ca_ > 0, sa_ / np.maximum(ca_, 1), np.nan)
        zone_w = np.where(cz_ > 0, sz_ / np.maximum(cz_, 1), np.nan)
    # Vergleichsspannung aussen: dazu die Staebe
    sv, cv = sa_.copy(), ca_.copy()
    for i, d in (r.beam_forces or {}).items():
        kn = np.asarray(m.elements[i].nodes, int)
        np.add.at(sv, kn, float(d["sig_max"]))
        np.add.at(cv, kn, 1.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        vm_aussen = np.where(cv > 0, sv / np.maximum(cv, 1), np.nan)
    return aussen * spn.MPA, zone_w * spn.MPA, vm_aussen, ca_ > 0, cz_ > 0


def test_getrennt(fall):
    m, _hexa, an = fall
    r = an.cases["LF1"]
    zone = set(int(e) for e in sp.zonen_elemente(r))
    aussen, zone_w, _vm, an_aussen, an_zone = _eigene(m, r, zone)
    g = sa.getrennt(m, r, "volumen", "sv")
    rand = an_aussen & an_zone
    check("getrennt: Knotenwerte aussen nur aus Aussenelementen, Zone nur aus Zonenelementen",
          g is not None and np.allclose(g["aussen"], aussen, equal_nan=True, rtol=1e-12, atol=1e-9)
          and np.allclose(g["zone"], zone_w, equal_nan=True, rtol=1e-12, atol=1e-9),
          f"{len(zone)} Zonenelemente")
    sprung = rand & (np.abs(np.nan_to_num(zone_w) - np.nan_to_num(aussen)) > 1.0)
    check("… an der Zonengrenze springt der Wert (Randknoten mit beiden Seiten)",
          int(rand.sum()) > 0 and int(sprung.sum()) > 0 and np.array_equal(g["nur_zone"], an_zone & ~an_aussen),
          f"{int(rand.sum())} Randknoten, {int(sprung.sum())} mit Sprung > 1 N/mm²")


def _fenster():
    from PySide6 import QtWidgets
    from statik3d.gui.main import MainWindow
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = MainWindow()
    w.resize(1400, 900)
    w.show()
    app.processEvents()
    w._fragen = lambda *a, **k: True
    w._fragen_knoepfe = lambda *a, **k: True
    w.fehler_liste = []
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w, w.fehler_liste, protokoll=True)
    return w, app


def test_ansicht(fall):
    m, _hexa, an = fall
    w, app = _fenster()
    w._modell_setzen(m)
    w._solve_done("all", an)
    app.processEvents()
    for k in range(w.cb_result.count()):
        d = w.cb_result.itemData(k)
        if d and d[0] == "case" and d[1] == "LF1":
            w.cb_result.setCurrentIndex(k)
    w.cb_field.setCurrentIndex(w.cb_field.findText(spn.feldname("volumen", "sv")))
    app.processEvents()
    w.redraw()
    app.processEvents()
    r = w.current_result()
    zone = set(int(e) for e in sp.zonen_elemente(r))
    aussen, zone_w, _vm, an_aussen, _an_zone = _eigene(m, r, zone)
    akt = w.plotter.actors.get("result_netz")
    ds = akt.mapper.dataset if akt is not None else None
    name = ds.active_scalars_name if ds is not None else None
    werte = np.asarray(ds.point_data[name], float) if name else None
    kn = np.asarray(ds.point_data["vtkOriginalPointIds"], int) if ds is not None else None
    elem = np.asarray(ds.cell_data["elem"], int) if ds is not None else None
    clim = akt.mapper.scalar_range if akt is not None else (0, 0)
    max_aussen = float(np.nanmax(aussen))
    # Punkte der Aussenzellen und der Zonenzellen
    pz = np.zeros(ds.n_points, bool) if ds is not None else None
    pa = np.zeros(ds.n_points, bool) if ds is not None else None
    if ds is not None:
        for c in range(ds.n_cells):
            ids = ds.get_cell(c).point_ids
            (pz if int(elem[c]) in zone else pa)[ids] = True
    check("Skala: Größtwert = größter Knotenwert der Aussenelemente (Randknoten aus den Aussenelementen)",
          akt is not None and abs(clim[1] - max_aussen) <= 1e-9 * max_aussen, f"{clim} / {max_aussen:.3f}")
    check("Abnahme: an den Punkten der Aussenzellen nichts über dem Größtwert außerhalb (kein „> Skalenmax“)",
          werte is not None and float(np.nanmax(werte[pa])) <= max_aussen * (1 + 1e-12)
          and np.allclose(werte[pa], aussen[kn[pa]], equal_nan=True),
          f"max {np.nanmax(werte[pa]) if werte is not None else None:.3f}")
    check("… Zonenzellen mit eigenen Knotenwerten (unstetig an der Grenze, Punkte doppelt)",
          werte is not None and pz.any() and np.allclose(werte[pz], zone_w[kn[pz]], equal_nan=True)
          and len(set(kn[pz].tolist()) & set(kn[pa].tolist())) > 0,
          f"{int(pz.sum())} Zonenpunkte, gemeinsame Knoten {len(set(kn[pz].tolist()) & set(kn[pa].tolist()))}")
    marken = dict(getattr(w, "_extremmarken", []) or [])
    kw = getattr(w, "_kennwerte_zeilen", []) or []
    check("Max-Marke und Kennwerte: dasselbe Maximum außerhalb",
          marken.get("marke_max", "").startswith("max " + spn.dezimal(max_aussen))
          and any(f"max {spn.dezimal(max_aussen)}" in z for z in kw), f"{marken} | {kw[:3]}")
    w.close()


def test_uebersicht(fall):
    m, _hexa, an = fall
    r = an.cases["LF1"]
    r._cache.pop("spitzen_uebersicht", None)
    zone = set(int(e) for e in sp.zonen_elemente(r))
    _a, _z, vm_aussen, _ka, _kz = _eigene(m, r, zone)
    u = sa.uebersicht(m, r)
    k = int(np.nanargmax(vm_aussen))
    check("Übersicht: größte Vergleichsspannung außerhalb mit Randknoten aus den Aussenelementen",
          u is not None and u["sv"] is not None and abs(u["sv"][0] - vm_aussen[k]) <= 1e-9 * vm_aussen[k]
          and u["sv"][1] == k, f"{u['sv'] if u else None} / {vm_aussen[k]:.1f} Knoten {k}")


def test_nachweise(fall):
    from statik3d.ec3 import volumen as vol
    m, hexa, an = fall
    r = an.combinations["GZT1"]
    zone = set(int(e) for e in sp.zonen_elemente(r))
    zk = np.zeros(m.nn, bool)
    for e in zone:
        zk[np.asarray(m.elements[e].nodes, int)] = True
    sk = r.solid_knoten
    ng = max(1, len(sk["gruppen"]))
    pos = {int(a) * ng + int(b): j for j, (a, b) in enumerate(zip(sk["knoten"], sk["gruppe"]))}
    grp = {g: j for j, g in enumerate(sk["gruppen"])}
    S = np.asarray(sk["spannung"], float)
    best = (-1.0, -1, -1)
    from statik3d.elements import solid as sl
    for i in hexa:
        if i in zone:
            continue
        e = m.elements[i]
        g = grp[(str(e.group), str(e.mat))]
        nk = len(sl.ECKEN_NATUERLICH[e.typ])
        js = [pos[int(n) * ng + g] for n in e.nodes[:nk] if not zk[int(n)]]
        if js:
            j = max(js, key=lambda jj: vol.vergleichsspannung(S[jj]))
            v, kn = vol.vergleichsspannung(S[j]), int(sk["knoten"][j])
        else:
            v, kn = vol.vergleichsspannung(r.solid_res[i]), -1
        if v > best[0]:
            best = (v, i, kn)
    c = an.volumen.bereiche["B1"]
    fyd = c.fy / m.design.gamma_M0
    punkt = str(c.werte.get("punkt", ""))
    knoten = int(punkt.split()[1]) - 1 if punkt.startswith("Knoten") else -1
    check("Volumennachweis: Ecken auf Randknoten der Zone zählen zur Zone (wie in der Ermüdung)",
          abs(c.util - best[0] / fyd) <= 1e-9 * c.util and (knoten < 0 or not zk[knoten])
          and c.element == best[1], f"η {c.util:.4f} / eigen {best[0] / fyd:.4f}, {punkt}")
    fv = an.fatigue.volumen.get("Platte")
    check("Ermüdung: der maßgebende Ort liegt außerhalb der Zonenknoten (unverändert)",
          fv is not None and (getattr(fv, "knoten", -1) < 0 or not zk[int(fv.knoten)]),
          f"Knoten {getattr(fv, 'knoten', None)}")


def main():
    from tests import test_spitzen_zeigen as tz
    try:
        fall = tz._platte()
    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        RESULTS.append((f"Platte rechnen (Ausnahme: {ex})", False))
        fall = None
    for t in (test_getrennt, test_ansicht, test_uebersicht, test_nachweise):
        print(f"\n--- {t.__name__} ---")
        try:
            if fall is None:
                RESULTS.append((t.__name__ + " (ohne Rechnung)", False))
            else:
                t(fall)
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
    code = main()
    sys.stdout.flush()
    os._exit(code)
