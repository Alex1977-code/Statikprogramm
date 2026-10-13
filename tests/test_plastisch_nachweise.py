"""
Volumennachweis und Ermuedung bei plastischer Rechnung (Entscheidung des
Anwenders vom 13.10.2026).

Wortlaut: „Sofort: Volumennachweis und Ermüdung in plastischen Rechnungen als
„nicht bewertet“ statt Zahlenwert. … Ermüdung bei plastischer Rechnung „nicht
anwendbar – erfordert elastische Ermüdungslastfälle“.“

Bis zum 13.10.2026 lasen beide in einer plastischen Rechnung Spannungen, die
dort keine Nachweisgroesse sind: der Volumennachweis die geglaettete
Eckspannung (am Drehlager ausserhalb der Zonen bis 1 596 N/mm2), die
Ermuedung dieselbe bzw. den Elementwert (bis 14 599 N/mm2), und eine
Schwingbreite aus plastischen Zustaenden ist keine Ermuedungsgroesse.

Geprueft an der Platte mit Loch (0,4 MN, harter Ring, sonst S355), plastisch
und elastisch: Status, Tabelle, Ampel, Zusammenfassung, Ergebnisbaum und
Bericht; die Ermuedung auch ueber eine Kombination und eine Ueberlagerung, in
der ein plastisches Ergebnis steckt. Elastisch bleibt alles, wie es war.

Aufruf:  python -m tests.test_plastisch_nachweise
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_plastisch_nachweise_"), "einstellungen.json")

import numpy as np  # noqa: E402

from statik3d import solver, plastizitaet as pl  # noqa: E402
from statik3d.model import Material, Volumenkoerper  # noqa: E402

RESULTS = []
_FENSTER = {}
NB = "nicht bewertet – plastische Rechnung"
NA = "nicht anwendbar – erfordert elastische Ermüdungslastfälle"


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FEHLER'} {name:78s} {detail}")
    return bool(ok)


def _fenster():
    if "w" in _FENSTER:
        return _FENSTER["w"], _FENSTER["app"]
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
    _FENSTER.update(w=w, app=app)
    return w, app


def _platte(plastisch: bool):
    """Platte mit Loch (0,4 MN), harter Ring bis 12,5 mm um das Loch, sonst
    S355; Koerper „Platte“ mit Kerbfall 71, Volumenbereich B1, GZT1 = LF1,
    Ermuedungslasten auf LF1 und auf GZT1."""
    from tests.test_spitzenstellen import lochplatte
    from tests.test_fugen import _RING_A
    m, _ids, _mitte = lochplatte(vorspannung=0.4e6)
    m.add_material(Material("Hart", 210e9, 0.3, 7850, fy=3000e6))
    hexa = []
    for i, e in enumerate(m.elements):
        if e.typ == "hex8":
            hexa.append(i)
            e.group = "Platte"
            rho = np.linalg.norm(np.asarray(m.nodes[e.nodes], float)[:, :2], axis=1).max()
            if rho <= _RING_A + 0.0125:
                e.mat = "Hart"
    m.koerper["Platte"] = Volumenkoerper("Platte", [], material="S355", elemente=list(hexa), kerbfall=71e6)
    m.add_volumenbereich("B1", hexa)
    m.add_combination("GZT1", {"LF1": 1.0}, "ULS")
    m.add_fatigue_load("FAT1", "LF1", cycles=1e4)
    m.add_fatigue_load("FAT2", "GZT1", cycles=1e3)
    if plastisch:
        m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=0.01, laststufen=2, iterationen=40,
                                         toleranz=1e-4)
    an = solver.solve_all(m, design=True, fatigue=True)
    return m, an


def test_plastisch(platte):
    from statik3d.gui import tabellen as tab
    from statik3d.report import Report
    m, an = platte
    r = an.cases["LF1"]
    check("Vorbereitung: plastisch gerechnet, ein Teil fließt",
          bool(r.info.get("plastizitaet")) and bool(r.info.get("plastisch")),
          f"{len(r.info.get('plastisch') or {})} Elemente fließen")
    c = an.volumen.bereiche["B1"]
    check("Volumennachweis: Status „nicht bewertet – plastische Rechnung“, kein Zahlenwert",
          c.status() == NB and c.util == 0.0 and not c.werte and not c.je_kombination, f"{c.status()!r}")
    zeile = [z for z in an.volumen.table() if z[0] == "B1"][0]
    check("… Tabelle: keine Spannung, keine Ausnutzung, der Status",
          zeile[4] == "–" and zeile[7] == "–" and zeile[-1] == NB, str(zeile))
    check("… Ampel: ohne Farbe (offen, nicht überschritten)", tab.ampelstufe(c.status()) == "")
    s = an.volumen.summary()
    check("… Zusammenfassung", s.startswith(f"Volumen: {NB}") and "B1" in s and "Ausnutzung" not in s, s)
    # Ermuedung
    f = an.fatigue
    fv = f.volumen.get("Platte")
    fm = f.members.get("Anker") if f.members else None
    check("Ermüdung: Volumen und Stab „nicht anwendbar – erfordert elastische Ermüdungslastfälle“",
          fv is not None and fv.status() == "nicht anwendbar" and fv.util == 0.0
          and (fm is None or fm.status() == "nicht anwendbar"),
          f"{getattr(fv, 'status', lambda: None)()} / {getattr(fm, 'status', lambda: None)() if fm else '–'}")
    check("… Zusammenfassung und Tabelle", NA in f.summary()
          and all(NA in str(z[-1]) for z in f.table()[1:]) and "D = " not in f.summary(),
          f.summary()[:160])
    # Oberflaeche: Tabelle, Ampel, Protokollzusatz, Ergebnisbaum
    w, app = _fenster()
    w._modell_setzen(m)
    w._solve_done("all", an)
    app.processEvents()
    w.refresh_volumen()
    vz = [list(z) for z in w.tbl_vol.modell.zeilen]
    check("Oberfläche: Volumentabelle ohne Ausnutzung, Status „nicht bewertet“",
          vz and vz[0][-1] == NB and vz[0][8] in ("", None), str(vz[:1]))
    check("… Ermüdung: Urteil und Protokollzusatz „nicht anwendbar“",
          w._ermuedung_zusatz(f) == " - nicht anwendbar" and w._ermuedung_urteil(fv) == "nicht anwendbar"
          and not [n for _t, n in w._nachweise_nicht_erfuellt() if n.startswith(("Ermüdung", "Volumen"))],
          f"{w._ermuedung_zusatz(f)!r} {w._nachweise_nicht_erfuellt()}")
    nachweise = dict((e[2], e[1]) for e in w._ergebnisliste().get("Nachweise", []))
    check("… Ergebnisbaum: Volumen und Ermüdung ohne Zahlenwert",
          "nicht bewertet" in nachweise.get("nachweis:volumen", "")
          and "nicht anwendbar" in nachweise.get("nachweis:fatigue", ""), str(nachweise))
    html = Report(m, an).html()
    teil_v = html[html.find("Spannungsnachweise der Volumenbereiche"):]
    teil_f = html[html.find("Ermüdungsnachweis nach DIN EN 1993-1-9"):]
    check("Bericht: Volumen „nicht bewertet – plastische Rechnung“, Ermüdung „nicht anwendbar“",
          NB in teil_v and NA in teil_f and "Schädigung D an der maßgebenden Stelle" not in teil_f)
    i0 = html.find("Wesentliche Ergebnisse")
    check("… die Zusammenfassung nennt beide, ohne „Alle Nachweise erfüllt“",
          "nicht bewertet" in html[i0:] and "nicht anwendbar" in html[i0:]
          and "Alle Nachweise erfüllt" not in html[i0:])
    # Stabnachweis bleibt
    d = an.design.members.get("Anker") if an.design is not None else None
    check("Stabnachweis (EN 1993-1-1/-1-8) des Ankers liefert weiter einen Wert",
          d is not None and float(d.util) > 0.0, f"{getattr(d, 'util', None)}")


def test_ueberlagerung(platte):
    """Eine Ueberlagerung, in der ein plastisches Ergebnis steckt, gilt als
    plastisch - auch ohne eigenen Eintrag „plastizitaet“."""
    from statik3d.ec3.volumen import ist_plastisch
    m, an = platte
    r = an.cases["LF1"]
    u = solver.Results.combine(m, [(r, 1.0)], "Ü1", "combination")
    check("Überlagerung eines plastischen Lastfalls gilt als plastisch",
          not (u.info or {}).get("plastizitaet") and ist_plastisch(u, an.all_results()))


def test_elastisch(platte_el):
    from statik3d.ec3 import volumen as vol
    m, an = platte_el
    r = an.combinations["GZT1"]
    c = an.volumen.bereiche["B1"]
    hexa = [i for i, e in enumerate(m.elements) if e.typ == "hex8"]
    werte = {e: vol.vergleichsspannung(s) for e, s, _p in vol._elementspannungen(m, r, hexa)}
    fy = {e: m.materials[m.elements[e].mat].yield_strength(c.werte.get("dicke", 0.0)) for e in hexa}
    eta = max(werte[e] / (fy[e] / m.design.gamma_M0) for e in hexa if fy[e] == c.fy)
    check("elastisch: Volumennachweis wie bisher mit Zahlenwert",
          c.status() in ("erfüllt", "NICHT erfüllt") and c.util > 0.0 and c.werte, f"η {c.util:.4f}, {c.status()}")
    fv = an.fatigue.volumen.get("Platte")
    check("… Ermüdung wie bisher mit Schädigung",
          fv is not None and fv.status() in ("erfüllt", "NICHT erfüllt") and fv.D > 0.0, f"D {getattr(fv, 'D', None)}")
    check("… und nichts sagt „nicht bewertet“ oder „nicht anwendbar“",
          "nicht bewertet" not in an.volumen.summary() and "nicht anwendbar" not in an.fatigue.summary())
    _ = eta


def main():
    platten = {}
    for k, plast in (("pl", True), ("el", False)):
        try:
            platten[k] = _platte(plast)
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((f"Platte rechnen {k} (Ausnahme: {ex})", False))
    for t, k in ((test_plastisch, "pl"), (test_ueberlagerung, "pl"), (test_elastisch, "el")):
        print(f"\n--- {t.__name__} ---")
        try:
            if k not in platten:
                RESULTS.append((t.__name__ + " (ohne Rechnung)", False))
            else:
                t(platten[k])
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
