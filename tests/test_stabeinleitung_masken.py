"""Stabenden verteilend einleiten: die Masken (seit 13.10.2026).

* Netzeinstellungen: Auswahl „Stabenden in Volumen“ (an 1–3 Knoten, Stirnflaeche,
  Kreisring) und die Durchmesser des Rings; „Übernehmen“ schliesst die
  Stabenden am vorhandenen Netz neu an.
* Stabmaske: je Ende, das in einem Volumen haengt, eine Auswahl (wie Modell, an
  1–3 Knoten, Stirnflaeche, Kreisring) und der Ring - ein Ende ohne Volumen
  bekommt keine Felder, die Maske eines gewoehnlichen Stabes bleibt, wie sie war.
* Ein falscher Ring ist ein Hinweis, nichts wird umgestellt.
* Vor der Rechnung: angeglichen an die Einstellung, ein zweites Mal nichts.
* Ansicht: die verteilend gekoppelten Stabenden sind gekennzeichnet.

Aufruf:  python -m tests.test_stabeinleitung_masken
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_stabeinleitung_"), "einstellungen.json")

RESULTS = []
_FENSTER = {}
FEHLER = []


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
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w, FEHLER)
    _FENSTER.update(w=w, app=app)
    return w, app


def _modell():
    """Quader 20 x 20 x 40 mm (tet10) mit einem Zugstab mittig auf der Stirnflaeche
    und einem zweiten Stab ohne Volumen daneben; angeschlossen wie bisher."""
    from statik3d import fugen
    from statik3d.model import Section
    from tests.test_stabeinleitung import quader, zugstab
    m = quader(h=0.01)
    zugstab(m)
    m.add_section(Section("Frei", 1e-4, 1e-9, 1e-9, 1e-9))
    a = m.add_node(0.1, 0.0, 0.0)
    b = m.add_node(0.2, 0.0, 0.0)
    m.add_member("S2", [m.add_element("truss", [a, b], "S235", "Frei", group="Frei")])
    fugen.stabenden_koppeln(m, [])
    return m


def _ins_fenster(w, app, m):
    w.model = m
    w._MainWindow__init_defaults()
    w.analysis = None
    w.results = None
    w.refresh_all()
    app.processEvents()


def _rbe(m):
    from statik3d import stabeinleitung as SE
    return [x for x in m.starrkoerper if SE.ist_verteilkopplung(x)]


def test_netzeinstellungen():
    from statik3d import stabeinleitung as SE
    w, app = _fenster()
    m = _modell()
    _ins_fenster(w, app, m)
    w.maske_netzeinstellungen()
    app.processEvents()
    mk = w.maskenrand.maske
    cb = mk._felder.get("stabenden")
    eintraege = [cb.itemText(i) for i in range(cb.count())] if cb is not None else []
    check("Netzeinstellungen: Auswahl „Stabenden in Volumen“ mit drei Arten, Vorgabe an 1–3 Knoten",
          eintraege == [SE.TEXTE["punkt"], SE.TEXTE["stirn"], SE.TEXTE["ring"]]
          and cb.currentText() == SE.TEXTE["punkt"], str(eintraege))
    check("… und das Feld für den Kreisring", "stabenden_ring" in mk._felder, ", ".join(list(mk._felder)[-4:]))
    cb.setCurrentText(SE.TEXTE["stirn"])
    mk.anwenden()
    app.processEvents()
    check("Stirnfläche übernommen: Modelleinstellung gesetzt, das Stabende hängt jetzt über RBE3 an der Fläche",
          w.model.stabeinleitung.art == "stirn" and len(_rbe(w.model)) == 1,
          f"{w.model.stabeinleitung} / {len(_rbe(w.model))} RBE3")
    check("… das Protokoll nennt es", "verteilt eingeleitet" in w.log.toPlainText())
    # falscher Ring: ein Hinweis, nichts umgestellt
    w.maske_netzeinstellungen()
    app.processEvents()
    mk = w.maskenrand.maske
    mk._felder["stabenden"].setCurrentText(SE.TEXTE["ring"])
    mk.setzen("stabenden_ring", "30 / 17")
    n0 = len(w.meldungen.hinweise)
    mk.anwenden()
    app.processEvents()
    check("Kreisring „30 / 17“: Hinweis, die Einstellung bleibt Stirnfläche",
          len(w.meldungen.hinweise) > n0 and w.model.stabeinleitung.art == "stirn",
          (w.meldungen.hinweise[-1] if w.meldungen.hinweise else "")[:120])
    mk = w.maskenrand.maske
    mk.setzen("stabenden_ring", "6 / 16")
    mk.anwenden()
    app.processEvents()
    st = w.model.stabeinleitung
    check("Kreisring „6 / 16“ übernommen (in mm)", st.art == "ring" and abs(st.d_innen - 0.006) < 1e-12
          and abs(st.d_aussen - 0.016) < 1e-12 and _rbe(w.model)
          and _rbe(w.model)[0].kommentar.startswith("ring 6.000/16.000"), str(st))
    w.maske_netzeinstellungen()
    app.processEvents()
    check("… und steht beim nächsten Öffnen in der Maske",
          w.maskenrand.maske._felder["stabenden_ring"].text() == "6 / 16",
          w.maskenrand.maske._felder["stabenden_ring"].text())
    w.maskenrand.maske.abbrechen()
    app.processEvents()


def test_stabmaske():
    from statik3d import stabeinleitung as SE
    w, app = _fenster()
    m = _modell()
    _ins_fenster(w, app, m)
    w._objektmaske("stab", "S2")
    app.processEvents()
    mk = w.maskenrand.maske
    check("Stab ohne Volumen: keine Felder zur Einleitung",
          not any(k.startswith(("einleitung_", "ring_")) for k in mk._felder), ", ".join(mk._felder))
    mk.abbrechen()
    w._objektmaske("stab", "S1")
    app.processEvents()
    mk = w.maskenrand.maske
    cb = mk._felder.get("einleitung_A")
    check("Stab im Volumen: Auswahl am Anfang (das Ende im Volumen), nicht am freien Ende",
          cb is not None and "einleitung_E" not in mk._felder and "ring_A" in mk._felder, ", ".join(mk._felder))
    if cb is None:
        return
    check("… Vorgabe „wie Modell (an 1–3 Knoten (wie RFEM))“",
          cb.currentText().startswith("wie Modell") and SE.TEXTE["punkt"] in cb.currentText(), cb.currentText())
    cb.setCurrentText(SE.TEXTE["stirn"])
    mk.anwenden()
    app.processEvents()
    mem = w.model.members["S1"]
    check("Stirnfläche je Stabende übernommen: gilt vor dem Modell (an 1–3 Knoten)",
          mem.einleitung == {"A": {"art": "stirn"}} and len(_rbe(w.model)) == 1
          and w.model.stabeinleitung.art == "punkt", str(mem.einleitung))
    check("… die Ansicht kennzeichnet das Stabende (Umriss der Fläche)",
          "stabeinleitungen" in w.plotter.renderer.actors, str([a for a in w.plotter.renderer.actors if "stab" in a]))
    w._objektmaske("stab", "S1")
    app.processEvents()
    mk = w.maskenrand.maske
    mk._felder["einleitung_A"].setCurrentText(next(t for t in [mk._felder["einleitung_A"].itemText(i)
                                                               for i in range(mk._felder["einleitung_A"].count())]
                                                   if t.startswith("wie Modell")))
    mk.anwenden()
    app.processEvents()
    check("„wie Modell“ zurück: wieder an 1–3 Knoten, die Kennzeichnung ist weg",
          not w.model.members["S1"].einleitung and not _rbe(w.model)
          and "stabeinleitungen" not in w.plotter.renderer.actors, str(w.model.members["S1"].einleitung))
    # vor der Rechnung: angeglichen, ein zweites Mal nichts
    from statik3d import fugen
    w.model.stabeinleitung.art = "stirn"
    check("vor der Rechnung: stabenden_erneuern gleicht an (Modell auf Stirnfläche gestellt)",
          fugen.stabenden_erneuern(w.model, []) and len(_rbe(w.model)) == 1)
    check("… ein zweites Mal ist nichts zu tun", not fugen.stabenden_erneuern(w.model, []))


def main():
    for t in (test_netzeinstellungen, test_stabmaske):
        try:
            t()
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
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
