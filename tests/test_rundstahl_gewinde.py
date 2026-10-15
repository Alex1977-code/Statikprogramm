"""Gewinde am Rundstahl, vom Anwender einstellbar (Auftrag vom 15.10.2026).

Wortlaut des Anwenders: „bei rundstahl soll die option mit gewinde einstellbar
sein also M16 etc. beim import als rundstahl 16 übernehmen aus rfem. der user
soll das allein einstellen wenn er möchte“.

* Querschnittsmaske eines Rundstahls (Section.typ „circle“): Auswahl
  „Gewinde“ ohne / aufgewalzt / M12 … M36 und das Feld A_s. Bei einem anderen
  Querschnitt (Rechteck, I-Profil …) gibt es beides nicht.
* Mit gewähltem Gewinde gilt Section.gewinde, A_s steht in der Tabelle nach
  EN ISO 898-1 (M16 157 mm², M20 245 mm²); das Feld A_s zeigt ihn. Der Stab wird
  als Schraube auf Zug nach EN 1993-1-8 nachgewiesen (ist_schraube), die Güte
  kommt aus dem Werkstoff. Ohne Gewinde bleibt alles wie vorher.
* Passt der Nenndurchmesser des Gewindes nicht zum Stabdurchmesser (M20 an Rund
  16), gibt es nur einen Hinweis (Protokoll, Statuszeile, Bericht des
  Nachweises), keine Sperre: gewählt bleibt, was der Anwender eingestellt hat.
* Der Import aus RFEM bleibt, wie er war: „Rund“ kommt als Rundstahl ohne
  Gewinde, ohne Hinweis dazu.
* Gespeichert wird das Feld nur, wenn es gesetzt ist (model.NEUE_FELDER).

Aufruf:  python -m tests.test_rundstahl_gewinde
"""
import json
import math
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_gewinde_"), "einstellungen.json")

RESULTS = []
_FENSTER = {}


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:84s} {detail}")
    return ok


def nah(a, b, rel=1e-9):
    try:
        return abs(float(a) - float(b)) <= rel * max(abs(float(b)), 1e-30)
    except (TypeError, ValueError):
        return False


def _modell(d=0.016, gewinde=None, N=100e3, fu=800e6):
    """Zugstab Rund d, 2 m, links fest, rechts Zugkraft N; Werkstoff wie eine
    Schraube 8.8 (f_y 640, f_u 800 N/mm²) - die Güte kommt aus dem Werkstoff."""
    from statik3d.model import Material, Model, Section
    m = Model("Rundstahl")
    m.add_material(Material("Güte 8.8", 210e9, 0.3, 7850.0, 1.2e-5, 640e6, fu))
    sec = Section.circle(f"Rund {d * 1e3:g}", d)
    if gewinde:
        sec.gewinde = gewinde
    m.add_section(sec)
    a, b = m.add_node(0, 0, 0), m.add_node(2.0, 0, 0)
    m.add_element("truss", [a, b], "Güte 8.8", sec.name)
    m.fix(a, "all")
    m.fix(b, [1, 2, 3, 4, 5])
    m.case().category = "G"
    m.load_node(b, Fx=N)
    m.add_member("S1", [0])
    m.add_combination("K1", {"LF1": 1.0}, "ULS")
    return m, sec.name


# ---------------------------------------------------------------------------
def test_passt():
    from statik3d.ec3 import spannstahl as sp
    from statik3d.model import Section
    print("\n--- Gewinde und Stabdurchmesser: spannstahl.gewinde_hinweis ---")
    r16, r40 = Section.circle("Rund 16", 0.016), Section.circle("Rund 40", 0.040)
    check("ohne Gewinde: kein Hinweis", sp.gewinde_hinweis(r16) == "")
    r16.gewinde = "M16"
    check("M16 an Rund 16: passt, kein Hinweis", sp.gewinde_hinweis(r16) == "")
    r16.gewinde = "M20"
    t = sp.gewinde_hinweis(r16)
    print(f"     {t}")
    check("M20 an Rund 16: Hinweis mit Gewinde, Durchmesser und Stabname",
          "M20" in t and "16 mm" in t and "Rund 16" in t and "passt nicht" in t, t[:120])
    check("… sagt, dass nichts gesperrt ist", "gerechnet wird mit" in t, t[-120:])
    r16.gewinde = "M12"
    check("M12 an Rund 16: ebenfalls Hinweis (kleiner als der Schaft)", sp.gewinde_hinweis(r16) != "")
    r40.gewinde = "M36"
    check("M36 an Rund 40: Hinweis", "M36" in sp.gewinde_hinweis(r40))
    r40.gewinde = "aufgewalzt"
    check("aufgewalzter Gewindestab: kein Hinweis (Nennquerschnitt)", sp.gewinde_hinweis(r40) == "")
    rect = Section.rectangle("R 100x200", 0.1, 0.2)
    rect.gewinde = "M16"
    check("kein Rundstahl: kein Hinweis (Durchmesser unbekannt)", sp.gewinde_hinweis(rect) == "")
    # Rundung: Rund 16,2 gilt als 16 mm
    s = Section.circle("Rund 16,2", 0.0162)
    s.gewinde = "M16"
    check("Rund 16,2 mit M16 passt (auf ganze mm gerundet)", sp.gewinde_hinweis(s) == "")


def test_nachweis():
    from statik3d import solver
    print("\n--- Nachweis: mit Gewinde als Schraube, ohne Gewinde wie vorher ---")
    FtRd = 0.9 * 800e6 * 157e-6 / 1.25
    m, _n = _modell(0.016, "M16")
    an = solver.solve_all(m, design=True)
    mc = an.design.members["S1"]
    check("M16: Art Schraube, η = N / F_t,Rd mit A_s = 157 mm², f_ub aus dem Werkstoff",
          mc.art == "Schraube" and nah(mc.util, 100e3 / FtRd), f"{mc.art!r} {float(mc.util):.5f} soll {100e3 / FtRd:.5f}")
    check("M16: kein Hinweis zum Durchmesser", not [w for w in mc.warnings if "passt nicht" in w])
    m20, _n = _modell(0.016, "M20")
    mc20 = solver.solve_all(m20, design=True).design.members["S1"]
    Ft20 = 0.9 * 800e6 * 245e-6 / 1.25
    check("M20 an Rund 16: gerechnet wird mit A_s = 245 mm² (keine Sperre)", nah(mc20.util, 100e3 / Ft20),
          f"{float(mc20.util):.5f} soll {100e3 / Ft20:.5f}")
    check("M20 an Rund 16: der Nachweis trägt den Hinweis", any("passt nicht" in w and "M20" in w for w in mc20.warnings),
          str(mc20.warnings[:1]))
    # Güte aus dem Werkstoff: andere f_u, andere Ausnutzung
    m10, _n = _modell(0.016, "M16", fu=1000e6)
    mc10 = solver.solve_all(m10, design=True).design.members["S1"]
    check("Güte kommt aus dem Werkstoff (f_u 1 000: η kleiner)", mc10.util < mc.util and
          nah(mc10.util, 100e3 / (0.9 * 1000e6 * 157e-6 / 1.25)))
    m0, _n = _modell(0.016, None)
    mc0 = solver.solve_all(m0, design=True).design.members["S1"]
    check("ohne Gewinde: Nachweis wie bisher (keine Schraube, keine Art)", getattr(mc0, "art", "") == "")
    from statik3d.report import Report
    html = Report(m20, solver.solve_all(m20, design=True)).html()
    check("Bericht: der Hinweis zum Durchmesser steht beim Stab", "passt nicht zum Stabdurchmesser" in html)


def test_speichern_laden():
    from statik3d.model import Model
    print("\n--- Speichern und Laden: nur wenn gesetzt (model.NEUE_FELDER) ---")
    tmp = tempfile.mkdtemp()
    try:
        m, name = _modell(0.016, None)
        p0 = os.path.join(tmp, "ohne.json")
        m.save(p0)
        with open(p0, encoding="utf-8") as f:
            s0 = json.load(f)["sections"][name]
        check("ohne Gewinde: weder gewinde noch A_s in der Datei", "gewinde" not in s0 and "A_s" not in s0,
              str([k for k in s0 if k in ("gewinde", "A_s")]))
        m1, name = _modell(0.016, "M16")
        p1 = os.path.join(tmp, "mit.json")
        m1.save(p1)
        with open(p1, encoding="utf-8") as f:
            s1 = json.load(f)["sections"][name]
        check("mit Gewinde: gewinde = M16 steht in der Datei", s1.get("gewinde") == "M16", str(s1.get("gewinde")))
        m2 = Model.load(p1)
        check("Laden: Gewinde M16 wieder da", m2.sections[name].gewinde == "M16")
        check("Laden einer Datei ohne das Feld: Gewinde leer",
              Model.load(p0).sections[name].gewinde == "" and Model.load(p0).sections[name].A_s is None)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_import():
    from statik3d.importers import rfem6_db as R6
    from tests.test_rfem6 import make_rf6, INF
    print("\n--- Import aus RFEM: Rundstahl bleibt ohne Gewinde, ohne zusätzlichen Hinweis ---")
    tmp = tempfile.mkdtemp()
    try:
        f = make_rf6(os.path.join(tmp, "rund.rf6"), nodes=[(0, 0, 0), (2, 0, 0)], lines=[[1, 2]],
                     members=[(1, None, None)], supports=[("Fest", (INF,) * 6, (0,) * 6, None, [1])])
        log = []
        m = R6.read_rf6(f, log=log)
        sec = list(m.sections.values())[0]
        check("Rundstahl übernommen (Section.typ circle), Gewinde leer, A_s leer",
              sec.typ == "circle" and sec.gewinde == "" and sec.A_s is None, f"{sec.name}: {sec.typ}, {sec.gewinde!r}")
        zeilen = [z for z in log if "Gewinde" in z or "Schraubengröße" in z]
        check("das Importprotokoll sagt nichts zum Gewinde", not zeilen, str(zeilen[:1]))
        check("kein Importhinweis zum Gewinde", not [h for h in getattr(m, "importhinweise", [])
                                                    if "ewinde" in str(h.get("text", "")) or h.get("art") == "gewinde"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
def _fenster():
    if "w" in _FENSTER:
        return _FENSTER["w"], _FENSTER["app"]
    from PySide6 import QtWidgets
    from statik3d.gui.main import MainWindow
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = MainWindow()
    w.show()
    app.processEvents()
    w._fragen_knoepfe = lambda *a, **k: True
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w, protokoll=True)
    _FENSTER.update(w=w, app=app)
    return w, app


def _maske(w, app, name):
    from PySide6 import QtWidgets
    w._objektmaske("querschnitt", name)
    app.processEvents()
    mk = w.maskenrand.maske
    wahl = {k: [v.itemText(i) for i in range(v.count())] for k, v in mk._felder.items()
            if isinstance(v, QtWidgets.QComboBox)}
    return set(mk._felder), wahl, mk.werte()


def test_maske():
    from statik3d.model import Section
    print("\n--- Querschnittsmaske: Gewinde nur beim Rundstahl, Hinweis ohne Sperre ---")
    w, app = _fenster()
    m, name = _modell(0.016, None)
    m.add_section(Section.rectangle("R 100x200", 0.1, 0.2))
    w.model = m
    w.refresh_all()
    app.processEvents()
    namen, wahl, werte = _maske(w, app, name)
    g = wahl.get("gewinde") or []
    check("Rund 16: Felder Gewinde und A_s da", "gewinde" in namen and "A_s" in namen, str(sorted(namen))[:80])
    check("… Auswahl ohne (–) / aufgewalzt / M12 … M36 (M16, M20, M24, M27, M30)",
          g[:1] == ["–"] and any("aufgewalzt" in x for x in g) and all(x in g for x in ("M12", "M16", "M20", "M24", "M27",
                                                                                      "M30", "M36")), str(g))
    check("… eingestellt ist „–“ (ohne Gewinde)", werte.get("gewinde") == "–", str(werte.get("gewinde")))
    namen2, _wahl2, _werte2 = _maske(w, app, "R 100x200")
    check("Rechteckquerschnitt: weder Gewinde noch A_s", "gewinde" not in namen2 and "A_s" not in namen2,
          str(sorted(namen2))[:80])
    # M16 wählen: A_s aus der Tabelle, kein Hinweis
    w.log.clear()
    w.meldungen.eintraege.clear() if hasattr(w.meldungen, "eintraege") else None
    w._eigenschaften_uebernehmen("querschnitt", name, {"name": name, "gewinde": "M16"})
    s = w.model.sections[name]
    check("M16 gewählt: Section.gewinde = M16, A_s = 157 mm², Fläche A unverändert (Schaft)",
          s.gewinde == "M16" and nah(s.A_s, 157e-6) and nah(s.A, math.pi * 0.016 ** 2 / 4), f"{s.gewinde} {s.A_s}")
    _n, _w, werte = _maske(w, app, name)
    check("das Feld A_s zeigt 157 mm²", str(werte.get("A_s", "")).replace(",", ".").startswith("157"), str(werte.get("A_s")))
    check("M16 an Rund 16: kein Hinweis im Protokoll", "passt nicht zum Stabdurchmesser" not in w.log.toPlainText())
    # M20 an Rund 16: Hinweis, keine Sperre
    w._eigenschaften_uebernehmen("querschnitt", name, {"name": name, "gewinde": "M20"})
    s = w.model.sections[name]
    log = w.log.toPlainText()
    check("M20 an Rund 16: gesetzt wird trotzdem (A_s = 245 mm²)", s.gewinde == "M20" and nah(s.A_s, 245e-6))
    check("… im Protokoll steht der Hinweis „M20 … passt nicht zum Stabdurchmesser 16 mm“",
          "HINWEIS:" in log and "M20" in log and "passt nicht zum Stabdurchmesser" in log, log[-200:])
    check("… die Übernahme zählt nicht als abgewiesen (kein Hinweis über hinweis())",
          not w.meldungen.hinweis_mit("passt nicht") and not w.meldungen.fehler)
    check("… die Statuszeile nennt ihn", "passt nicht" in w.statusBar().currentMessage(), w.statusBar().currentMessage()[:100])
    # zurück auf ohne
    w._eigenschaften_uebernehmen("querschnitt", name, {"name": name, "gewinde": "–"})
    s = w.model.sections[name]
    check("zurück auf „–“: Gewinde leer, A_s leer", s.gewinde == "" and s.A_s is None, f"{s.gewinde!r} {s.A_s}")


def main():
    for t in (test_passt, test_nachweis, test_speichern_laden, test_import, test_maske):
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {type(ex).__name__}: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    sys.stdout.flush()
    return 0 if not schlecht else 1


if __name__ == "__main__":
    rc = main()
    os._exit(rc)
