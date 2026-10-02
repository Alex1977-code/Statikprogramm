"""
Stellungen rechnen nur zugewiesene Lastfaelle - die Oberflaeche (Plan-Schritt
7S, 02.10.2026; Zusage an den Anwender vom 24.09.2026: „nur das gerechnet wird
was auch zugewiesen wurde, einen vermerkt lastfall nicht verwendet“).

* die Stellungsmaske fuehrt die Lastfaelle zum Anhaken, „Übernehmen“ schreibt
  sie in die Stellung;
* „Alle Stellungen“ mit Stellungen ohne Lastfaelle: die Meldung sagt, warum
  nichts gerechnet wurde; Lastfaelle in keiner Stellung stehen im Protokoll;
* eine aeltere Datei (Fassung unter 8) mit leerer Zuordnung: beim Laden alle
  Lastfaelle (Entscheidung E6), das Protokoll sagt es.

Aufruf:  python -m tests.test_stellungen_zuweisung
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_stellungen_"), "einstellungen.json")

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
    w.error = lambda msg, *a, **k: (w.fehler_liste.append(str(msg)), w.log.appendPlainText("FEHLER: " + str(msg)))
    _FENSTER.update(w=w, app=app)
    return w, app


def _modell(w):
    from statik3d.model import Material, Section
    from statik3d.bridges.positions import Stellung
    w.new_model()
    m = w.model
    m.add_material(Material.steel("S355"))
    m.add_section(Section.from_profile("HEB 300"))
    n = [m.add_node(4.0 * i, 0.0, 0.0) for i in range(3)]
    for i in range(2):
        m.add_element("beam", [n[i], n[i + 1]], "S355", "HEB 300")
    m.support(n[0], "all", name="Einspannung")
    g = next(iter(m.load_cases))
    m.load_node(n[-1], Fz=-5e3, case=g)
    m.add_load_case("Wind", "W", activate=False)
    m.load_node(n[-1], Fy=2e3, case="Wind")
    m.stellungen.append(Stellung("S1", 0.0, "geschlossen"))
    return m, g


def test_maske_weist_lastfaelle_zu():
    from PySide6 import QtCore
    w, app = _fenster()
    m, g = _modell(w)
    w.refresh_all(); app.processEvents()
    w._objektmaske("stellung", "S1"); app.processEvents()
    mk = w.maskenrand.maske
    lw = (mk._felder if mk is not None else {}).get("faelle")
    namen = [lw.item(i).text() for i in range(lw.count())] if lw is not None else []
    check("Stellungsmaske: „Lastfälle dieser Stellung“ zum Anhaken, alle Lastfälle zur Wahl",
          lw is not None and namen == list(m.load_cases), str(namen))
    if lw is None:
        return
    check("… ohne Zuordnung ist nichts angehakt",
          all(lw.item(i).checkState() == QtCore.Qt.Unchecked for i in range(lw.count())))
    for i in range(lw.count()):
        lw.item(i).setCheckState(QtCore.Qt.Checked if lw.item(i).text() == g else QtCore.Qt.Unchecked)
    mk.anwenden(); app.processEvents()
    st = w.model.stellung("S1")
    check("„Übernehmen“ schreibt die angehakten Lastfälle in die Stellung", st is not None and st.faelle == [g],
          str(st and st.faelle))
    w._objektmaske("stellung", "S1"); app.processEvents()
    mk = w.maskenrand.maske
    cb = mk._felder.get("faelle_alle")
    lw = mk._felder.get("faelle")
    check("Haken „Alle Lastfälle anhaken“ unter der Liste, nicht gesetzt bei einem von zwei",
          cb is not None and not cb.isChecked(), str(list(mk._felder)))
    if cb is not None:
        cb.setChecked(True); app.processEvents()
        mk.anwenden(); app.processEvents()
        st = w.model.stellung("S1")
        check("… hakt alle an, „Übernehmen“ schreibt sie", st.faelle == list(w.model.load_cases),
              str(st.faelle))
        w._objektmaske("stellung", "S1"); app.processEvents()
        mk = w.maskenrand.maske
        cb, lw = mk._felder.get("faelle_alle"), mk._felder.get("faelle")
        check("… beim nächsten Öffnen steht er, weil alle zugewiesen sind", cb.isChecked())
        lw.item(0).setCheckState(QtCore.Qt.Unchecked); app.processEvents()
        check("… er folgt der Liste: einen Haken entfernt, steht er nicht mehr", not cb.isChecked())
        lw.item(0).setCheckState(QtCore.Qt.Checked); app.processEvents()
        check("… alle von Hand angehakt, steht er wieder", cb.isChecked())
        cb.setChecked(False); app.processEvents()
        check("… ihn entfernen löscht jeden Haken der Liste",
              all(lw.item(i).checkState() == QtCore.Qt.Unchecked for i in range(lw.count())))
        mk.abbrechen(); app.processEvents()


def test_umbenennen_fuehrt_stellung_mit():
    """Gegenpruefung 02.10.2026: Umbenennen eines Lastfalls in seiner Maske
    liess den alten Namen in der Stellung stehen, die dann scheiterte."""
    w, app = _fenster()
    m, g = _modell(w)
    m.stellung("S1").faelle = [g, "Wind"]
    w.refresh_all(); app.processEvents()
    w._objektmaske("lastfall", "Wind"); app.processEvents()
    mk = w.maskenrand.maske
    mk.setzen("name", "Sturm")
    mk.anwenden(); app.processEvents()
    st = w.model.stellung("S1")
    check("Lastfall in seiner Maske umbenannt: die Stellung führt den neuen Namen",
          "Sturm" in w.model.load_cases and st.faelle == [g, "Sturm"], str(st.faelle))


def test_alle_stellungen_ohne_zuordnung():
    w, app = _fenster()
    m, g = _modell(w)
    w.refresh_all(); app.processEvents()
    n_f = len(w.fehler_liste)
    n_log = len(w.log.toPlainText().splitlines())
    w.stellungen_rechnen(); app.processEvents()
    neu = w.log.toPlainText().splitlines()[n_log:]
    check("„Alle Stellungen“ ohne Zuordnung: die Meldung sagt, warum nichts gerechnet wurde",
          len(w.fehler_liste) == n_f + 1 and "kein" in w.fehler_liste[-1] and "zugewiesen" in w.fehler_liste[-1],
          str(w.fehler_liste[-1:]))
    check("… das Protokoll nennt die Stellung und die Lastfälle in keiner Stellung",
          any("S1" in z and "keine Lastfälle zugewiesen" in z for z in neu)
          and any("in keiner Stellung" in z and "Wind" in z for z in neu), str(neu[-4:]))
    w.model.stellung("S1").faelle = [g]
    n_log = len(w.log.toPlainText().splitlines())
    w.stellungen_rechnen(); app.processEvents()
    neu = w.log.toPlainText().splitlines()[n_log:]
    check("mit Zuordnung: gerechnet, „Wind“ steht als nicht gerechnet im Protokoll",
          w.umhuellende is not None and len(w.umhuellende.ergebnisse) == 1
          and any("in keiner Stellung" in z and "Wind" in z for z in neu), str(neu[-3:]))


def test_alte_datei_bekommt_alle_lastfaelle():
    w, app = _fenster()
    m, g = _modell(w)
    d = m.to_dict()
    d["format"] = 7
    pfad = os.path.join(tempfile.mkdtemp(prefix="statik3d_stellungen_alt_"), "alt.json")
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(d, f)
    n_log = len(w.log.toPlainText().splitlines())
    w.modell_laden(pfad, fragen=False); app.processEvents()
    st = w.model.stellung("S1")
    neu = w.log.toPlainText().splitlines()[n_log:]
    check("ältere Datei mit leerer Zuordnung: beim Laden alle Lastfälle (E6)",
          st is not None and st.faelle == list(w.model.load_cases), str(st and st.faelle))
    check("… und das Protokoll sagt es", any(z.startswith("Hinweis: Stellung S1") for z in neu), str(neu[:3]))


def main():
    import faulthandler
    faulthandler.dump_traceback_later(600, exit=True)
    for t in (test_maske_weist_lastfaelle_zu, test_umbenennen_fuehrt_stellung_mit,
              test_alle_stellungen_ohne_zuordnung, test_alte_datei_bekommt_alle_lastfaelle):
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
    sys.exit(main())
