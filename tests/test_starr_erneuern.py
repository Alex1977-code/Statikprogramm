"""
Alte Kopplungen starrer Flaechen vor der Rechnung erneuern (Plan
Singularitaeten vom 10.10.2026, Paket 2, Aufgabe 0).

Paket 1 hat ``fugen.starre_flaechen_koppeln`` berichtigt: eine starre Scheibe
genau ueber einer Bohrung koppelt jetzt genau den Lochrand. Bis zum
10.10.2026 hingen mit der Toleranz max(0,5 mm; 0,1 r) auch Knoten im
Plattenkoerper an der Scheibe - am Drehlager 16 Knoten an 6 Scheiben. Ein
gespeichertes Modell traegt diese Kopplungen mit sich, und die Oberflaeche
koppelte vor der Rechnung nur dann neu, wenn es noch gar keine Kopplung
einer starren Flaeche gab (``MainWindow._vor_rechnung_vernetzen``). Es
rechnete also weiter mit der alten Kopplung.

Geprueft wird mit dem echten Hauptfenster offscreen an der Platte mit Loch
(tests.test_spitzenstellen.lochplatte):

* ein Modell mit veralteter Kopplung (ein Knoten 2 mm unter dem Lochrand
  haengt mit an der Scheibe) rechnet nach ``_vor_rechnung_vernetzen`` mit der
  richtigen Kopplung - dieselbe Verschiebung wie das frisch gekoppelte Modell;
* das Protokoll meldet die Erneuerung in einer Zeile;
* eine von Hand angelegte Kopplung einer anderen Gruppe bleibt unberuehrt;
* ein Modell mit richtiger Kopplung bleibt unveraendert (dieselben Objekte in
  derselben Reihenfolge, keine Zeile im Protokoll);
* ein Modell ganz ohne Kopplung der Scheibe (aeltere Datei) wird wie bisher
  gekoppelt.

Aufruf:  python -m tests.test_starr_erneuern
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_starr_erneuern_"), "einstellungen.json")

import numpy as np  # noqa: E402

RESULTS = []
_FENSTER = {}


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
    w.show()
    app.processEvents()
    w._fragen = lambda *a, **k: True
    w._fragen_knoepfe = lambda *a, **k: True
    w.fehler_liste = []
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w, w.fehler_liste, protokoll=True)
    _FENSTER.update(w=w, app=app)
    return w, app


def _starr(m):
    """{Gruppe: (Master, Menge der Slaves)} der Kopplungen starrer Flaechen."""
    from statik3d import fugen
    aus = {}
    for k in m.kopplungen:
        g = str(k.gruppe)
        if g.startswith(fugen.STARR_GRUPPE):
            aus.setdefault(g, (int(k.node_a), set()))[1].add(int(k.node_b))
    return aus


def _modelle():
    """(richtig gekoppelt, mit veralteter Kopplung, Knoten 2 mm unter dem
    Lochrand, Handkopplung) - beide Modelle mit derselben Handkopplung."""
    from statik3d import fugen
    from statik3d.model import Kopplung
    from tests.test_spitzenstellen import lochplatte
    unendlich = float("inf")
    eins = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    modelle = []
    for alt in (False, True):
        m, ids, mitte = lochplatte(vorspannung=1.2e6)
        # von Hand: eine weiche Kopplung zweier Knoten am Aussenrand
        hand = Kopplung(int(ids[5, -2, 0]), int(ids[6, -2, 0]), eins, [1e9, 1e9, 1e9], "Hand")
        m.kopplungen.append(hand)
        unter = int(ids[0, 0, -2])
        if alt:
            # so koppelte die Toleranz bis zum 10.10.2026: auch ein Knoten
            # 2 mm unter dem Lochrand haengt an der Scheibe
            m.kopplungen.append(Kopplung(int(mitte), unter, eins, [unendlich] * 3,
                                         fugen.STARR_GRUPPE + "Scheibe"))
        modelle.append((m, unter, hand))
    return modelle


def _protokoll(w) -> list:
    return w.log.toPlainText().splitlines()


def test_alte_kopplung_wird_erneuert():
    from statik3d import solver
    w, app = _fenster()
    (m_neu, unter, _h), (m_alt, _u, hand) = _modelle()
    soll = _starr(m_neu)
    vorher = _starr(m_alt)
    check("Vorbereitung: die veraltete Kopplung hat einen Knoten mehr",
          len(vorher["starr Scheibe"][1]) == len(soll["starr Scheibe"][1]) + 1
          and unter in vorher["starr Scheibe"][1],
          f"{len(vorher['starr Scheibe'][1])} gegen {len(soll['starr Scheibe'][1])} Knoten")
    # ohne Erneuerung rechnet das Modell anders - die Pruefung misst also etwas
    u_neu = np.asarray(solver.solve_static(m_neu).u, float)
    u_alt = np.asarray(solver.solve_static(m_alt).u, float)
    d_alt = float(np.abs(u_alt - u_neu).max())
    check("Gegenprobe: mit der alten Kopplung weicht die Verschiebung ab",
          d_alt > 1e-3 * float(np.abs(u_neu).max()),
          f"größte Abweichung {d_alt * 1e6:.3f} µm bei max |u| {np.abs(u_neu).max() * 1e3:.4f} mm")
    w._modell_setzen(m_alt)
    app.processEvents()
    n0 = len(_protokoll(w))
    ok = w._vor_rechnung_vernetzen()
    app.processEvents()
    nachher = _starr(w.model)
    check("nach _vor_rechnung_vernetzen: genau die Kopplung von heute",
          ok and nachher == soll,
          f"{ {g: len(s) for g, (_m, s) in nachher.items()} } / soll "
          f"{ {g: len(s) for g, (_m, s) in soll.items()} }")
    u = np.asarray(solver.solve_static(w.model).u, float)
    d = float(np.abs(u - u_neu).max())
    check("… und rechnet damit wie das frisch gekoppelte Modell",
          d <= 1e-9 * float(np.abs(u_neu).max()), f"größte Abweichung {d * 1e6:.6f} µm")
    neu_zeilen = _protokoll(w)[n0:]
    starr_zeilen = [z for z in neu_zeilen if "starre" in z.lower() or "Starre" in z]
    check("das Protokoll meldet die Erneuerung in einer Zeile",
          len(starr_zeilen) == 1 and "1 starre Fläche" in starr_zeilen[0]
          and "erneuert" in starr_zeilen[0],
          " | ".join(starr_zeilen))
    check("die Handkopplung der Gruppe „Hand“ ist unberührt (dasselbe Objekt)",
          sum(1 for k in w.model.kopplungen if k is hand) == 1
          and sum(1 for k in w.model.kopplungen if str(k.gruppe) == "Hand") == 1)


def test_richtige_kopplung_bleibt():
    w, app = _fenster()
    (m_neu, _unter, hand), _alt = _modelle()
    liste = list(m_neu.kopplungen)
    kommentar = m_neu.flaechen["Scheibe"].kommentar
    w._modell_setzen(m_neu)
    app.processEvents()
    n0 = len(_protokoll(w))
    w._vor_rechnung_vernetzen()
    app.processEvents()
    check("richtige Kopplung: dieselben Objekte in derselben Reihenfolge",
          len(w.model.kopplungen) == len(liste)
          and all(a is b for a, b in zip(w.model.kopplungen, liste)))
    check("… derselbe Kommentar an der Fläche und keine Zeile im Protokoll",
          w.model.flaechen["Scheibe"].kommentar == kommentar
          and not [z for z in _protokoll(w)[n0:] if "starr" in z.lower()],
          " | ".join(_protokoll(w)[n0:]))


def test_ohne_kopplung_wie_bisher():
    from statik3d import fugen
    w, app = _fenster()
    (m_neu, _unter, _hand), _alt = _modelle()
    soll = _starr(m_neu)
    m_neu.kopplungen = [k for k in m_neu.kopplungen
                        if not str(k.gruppe).startswith(fugen.STARR_GRUPPE)]
    w._modell_setzen(m_neu)
    app.processEvents()
    n0 = len(_protokoll(w))
    w._vor_rechnung_vernetzen()
    app.processEvents()
    zeilen = [z for z in _protokoll(w)[n0:] if "starre" in z.lower()]
    check("ältere Datei ganz ohne Kopplung: wird gekoppelt wie bisher",
          _starr(w.model) == soll and len(zeilen) == 1, " | ".join(zeilen))


def main():
    for t in (test_alte_kopplung_wird_erneuert, test_richtige_kopplung_bleibt, test_ohne_kopplung_wie_bisher):
        print(f"\n--- {t.__name__} ---")
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
    code = main()
    sys.stdout.flush()
    os._exit(code)
