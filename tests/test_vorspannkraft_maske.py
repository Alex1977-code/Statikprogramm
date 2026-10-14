"""Vorspannkraft (Soll nach Verankerung) in der Oberflaeche (offscreen).

Seit dem 13.10.2026 hat die Maske „Vorspannung“ eine Lastart: die
Anfangsdehnung wie bisher, die Vorspannkraft (Soll nach Verankerung) mit
ihrer Gruppe beim Spannen und die Umwandlung einer Temperatur-Vorspannung
(RFEM-Import) in die Sollkraft. Geprueft: Eingabe in der Maske, Bearbeiten
in der Lastmaske (Kraft und Gruppe), Anzeige in der Lasttabelle (F_soll, beim
ΔT die Kraft mit E und α der Umrechnung), Umwandeln.

Aufruf:  python -m tests.test_vorspannkraft_maske
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_vorspannkraft_"), "einstellungen.json")

RESULTS = []
_FENSTER = {}


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


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
    w.fehler_liste = []
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w, w.fehler_liste, protokoll=True)
    _FENSTER.update(w=w, app=app)
    return w, app


def _modell(w):
    """Zwei Anker (Fachwerkstaebe) zwischen Boden und Kopfplatte, Kopfplatte
    auf einem Klemmstab; A2 traegt die RFEM-Form der Vorspannung (dT)."""
    from statik3d.model import Material, Section
    w.new_model()
    m = w.model
    # Spannstahl ist die Werkstoffart (Material.art); der Name allein macht es
    # seit der Zusammenfuehrung (14.10.2026) nicht mehr
    m.add_material(Material("Spannstahl St 835/1030", E=205e9, nu=0.3, rho=7850, alpha=1e-5,
                            fy=835e6, fu=1030e6, art="Spannstahl"))
    m.add_section(Section.circle("Rund 40", 0.04))
    g1, g2, g3 = (m.add_node(0.0, 0.0, 0.0), m.add_node(0.1, 0.0, 0.0), m.add_node(0.2, 0.0, 0.0))
    h = m.add_node(0.1, 0.0, 1.0)
    for g in (g1, g2, g3):
        m.fix(g, "all")
    m.fix(h, [0, 1, 3, 4, 5])
    a1 = m.add_element("truss", [g1, h], "Spannstahl St 835/1030", "Rund 40")
    a2 = m.add_element("truss", [g3, h], "Spannstahl St 835/1030", "Rund 40")
    m.add_element("truss", [g2, h], "Spannstahl St 835/1030", "Rund 40")
    m.add_member("A1", [a1])
    m.add_member("A2", [a2])
    fall = m.active_case
    m.case(fall).gravity = [0.0, 0.0, 0.0]
    sec = m.sections["Rund 40"]
    m.load_temp(a2, -952e3 / (205e9 * sec.A * 1e-5), case=fall)
    return m, fall


def test_maske_und_anzeige():
    w, app = _fenster()
    m, fall = _modell(w)
    w.refresh_all()
    app.processEvents()
    w.sel_staebe = ["A1"]
    w.maske_vorspannung()
    app.processEvents()
    mk = w.maskenrand.maske
    felder = list(getattr(mk, "_felder", {}) or {})
    check("Maske Vorspannung: Lastart und Gruppe beim Spannen",
          "art" in felder and "gruppe" in felder, str(felder))
    check("… mit dem Hinweis auf die Temperatur-Vorspannung im Modell", "hinweise" in felder, str(felder))
    mk.setzen("art", w.VORSPANN_ARTEN[1])
    mk.setzen("F", 944.7)
    mk.setzen("gruppe", 2)
    mk.anwenden()
    app.processEvents()
    vs = m.case(fall).vorspannungen
    check("Sollkraft aufgebracht: A1 trägt F_soll = 944,7 kN, Gruppe 2",
          len(vs) == 1 and vs[0].ziel == "A1" and vs[0].sollkraft and vs[0].gruppe == 2
          and abs(vs[0].kraft - 944.7e3) < 1e-6, str([(v.ziel, v.kraft, v.sollkraft, v.gruppe) for v in vs]))
    w.refresh_all()
    app.processEvents()
    zeilen = [list(map(str, r)) for r in w.tbl_last.modell.zeilen]
    z_soll = [r for r in zeilen if "Vorspannkraft (Soll)" in r]
    check("Lasttabelle: Vorspannkraft (Soll) mit F_soll und Gruppe",
          z_soll and "F_soll = 944,7 kN, Gruppe 2" in z_soll[0], str(z_soll[:1]))
    z_dt = [r for r in zeilen if "Temperatur" in r]
    check("Lasttabelle: ΔT mit „aus Vorspannung 952 kN, E = 205 000 N/mm², α = 1,0e-5 1/K“",
          z_dt and "aus Vorspannung 952 kN, E = 205 000 N/mm², α = 1,0e-5 1/K" in z_dt[0], str(z_dt[:1]))
    # Lastmaske der Sollkraft: Kraft und Gruppe aendern
    w._lastmaske(fall, "vorspannungen", 0)
    app.processEvents()
    mk = w.maskenrand.maske
    check("Lastmaske: Titel nennt die Sollkraft, Feld Gruppe",
          "Soll nach Verankerung" in str(getattr(mk, "titel", "")) and "gruppe" in (mk._felder or {}),
          str(getattr(mk, "titel", "")))
    mk.setzen("F", 900.0)
    mk.setzen("gruppe", 1)
    mk.anwenden()
    app.processEvents()
    v = m.case(fall).vorspannungen[0]
    check("… übernommen: 900 kN, Gruppe 1", abs(v.kraft - 900e3) < 1e-6 and v.gruppe == 1 and v.sollkraft,
          f"{v.kraft}, {v.gruppe}")
    # Umwandeln: ohne Auswahl alle Staebe mit Temperatur-Vorspannung
    w.sel_staebe = []
    w.maske_vorspannung()
    app.processEvents()
    mk = w.maskenrand.maske
    mk.setzen("art", w.VORSPANN_ARTEN[2])
    mk.setzen("F", 0.0)
    mk.anwenden()
    app.processEvents()
    vs = {v.ziel: v for v in m.case(fall).vorspannungen}
    erwartet = 0.9 * 835e6 * m.sections["Rund 40"].A
    check("Umwandeln: A2 trägt die Sollkraft, der Vorschlag 0,9·f_p0,1k·A bei Spannstahl",
          "A2" in vs and vs["A2"].sollkraft and abs(vs["A2"].kraft - erwartet) < 1e-3,
          f"{vs.get('A2') and vs['A2'].kraft:.6g} N, erwartet {erwartet:.6g} N")
    check("… und die ΔT-Last ist weg", not m.case(fall).temp_loads, str(m.case(fall).temp_loads))
    # gerechnet: die Sollkraefte stehen am Ende in den Staeben
    from statik3d import solver
    r = solver.solve_static(m, case=fall)
    N = {s: float(r.beam_forces[m.members[s].elements[0]]["N"][1]) for s in ("A1", "A2")}
    check("gerechnet: A1 900 kN, A2 0,9·f_p0,1k·A",
          abs(N["A1"] - 900e3) < 1e-3 and abs(N["A2"] - erwartet) < 1e-3, str(N))


def main():
    import faulthandler
    faulthandler.dump_traceback_later(600, exit=True)
    for t in (test_maske_und_anzeige,):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    sys.stdout.flush()
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    rc = main()
    os._exit(rc)
