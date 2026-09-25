"""„Sechsflächner sweepen“ ist keine Option der Oberfläche mehr (25.09.2026).

Am Drehlager hatte der Anwender den Sweep eingeschaltet – „er war als option
da und für mich als user nicht erkennbar dass das ein problem ist“. Es
entstanden 926 hex8 mit fast entarteter Ecke und 242 flache Keile (gemessen von
der Element-Sitzung), LF1 konvergierte nicht mehr. Statt Warnungen und
Grenzwerten („keep it simple“) gibt es die Falle nicht mehr: die Maske bietet
den Haken nicht an, Übernehmen schaltet ihn aus, eine ältere Datei mit „an“
lädt mit „aus“, und das Vernetzen schaltet ein noch gesetztes „an“ aus und
sagt es im Protokoll. Der Vernetzer selbst kann weiter sweepen (Prüfungen der
Vernetzer-Sitzung setzen model.netz.sweep direkt).

Seit 25.09.2026 ist das Feld ein Wort ("aus" | "sauber" | "immer", dritte
Lieferung der Vernetzer-Sitzung). „An“ heißt hier True oder „immer“: beide
laden als „aus“, Übernehmen und Vernetzen machen daraus „aus“. „Sauber“
bleibt überall stehen – es sweept nur Körper, die die Probe bestehen, und
wird künftig von der Stufe gesetzt.
"""
from __future__ import annotations

import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK  ' if ok else 'FAIL'} {name:70s} {detail}")


def test_laden_schaltet_aus():
    from statik3d.model import Model
    m = Model("x")
    m.netz.sweep = True
    d = m.to_dict()
    check("Datei mit „sweep an“ gespeichert", bool(d["netz"].get("sweep")), str(d["netz"].get("sweep")))
    m2 = Model.from_dict(d)
    check("… lädt mit „sweep aus“", m2.netz.sweep == "aus", str(m2.netz.sweep))
    # Das Wort (25.09.2026): „immer“ ist der alte Sweep und laedt als „aus“,
    # „sauber“ bleibt
    for wert, soll in (("immer", "aus"), ("sauber", "sauber")):
        d["netz"]["sweep"] = wert
        m3 = Model.from_dict(d)
        check(f"Datei mit „{wert}“ lädt mit „{soll}“", m3.netz.sweep == soll, str(m3.netz.sweep))


def _vernetzen_leer(w):
    """Das Vernetzen am leeren Modell; Rueckgabe Protokoll und Meldungen."""
    meldungen = []
    alt = w.info
    w.info = lambda t, *a, **k: meldungen.append(str(t))
    vorher = len(w.log.toPlainText())
    try:
        w._vernetzen([], [])
    except Exception as ex:             # noqa: BLE001 - leeres Modell darf melden
        meldungen.append(f"Ausnahme: {ex}")
    finally:
        w.info = alt
    return w.log.toPlainText()[vorher:] + "\n" + "\n".join(meldungen)


def test_maske_ohne_haken():
    from PySide6 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from statik3d.gui import main as G
    from statik3d.model import Model
    w = G.MainWindow()
    try:
        w.model = Model("x")
        w.model.netz.sweep = True           # als kaeme es aus einer alten Sitzung
        w.maske_netzeinstellungen()
        app.processEvents()
        mk = w.maskenrand.maske
        felder = list(getattr(mk, "_felder", {}) or {})
        check("Netzeinstellungen: kein Haken „Sechsflächner sweepen“", "sweep" not in felder,
              ", ".join(felder))
        n = w._netz_aus_maske(mk.werte())
        check("Übernehmen der Netzeinstellungen schaltet den Sweep aus", n.sweep == "aus", str(n.sweep))
        for wert, soll in (("immer", "aus"), ("sauber", "sauber"), ("aus", "aus")):
            w.model.netz.sweep = wert
            n = w._netz_aus_maske(mk.werte())
            check(f"  Übernehmen: „{wert}“ → „{soll}“", n.sweep == soll, str(n.sweep))
        # Vernetzen: ein noch gesetztes „an“ wird ausgeschaltet und gemeldet
        w.model.netz.sweep = True
        protokoll = _vernetzen_leer(w)
        check("Vernetzen schaltet ein gesetztes „an“ aus", w.model.netz.sweep == "aus", str(w.model.netz.sweep))
        check("… und sagt es im Protokoll", "Sechsflächner-Sweep ausgeschaltet" in protokoll,
              protokoll[-300:].replace("\n", " | "))
        w.model.netz.sweep = "immer"
        protokoll = _vernetzen_leer(w)
        check("Vernetzen schaltet „immer“ aus und sagt es",
              w.model.netz.sweep == "aus" and "Sechsflächner-Sweep ausgeschaltet" in protokoll,
              str(w.model.netz.sweep))
        # Seit das Feld ein Wort ist, waere getattr(netz, "sweep") auch fuer
        # „aus“ wahr - dann meldete jedes Vernetzen den Sweep
        for wert in ("sauber", "aus"):
            w.model.netz.sweep = wert
            protokoll = _vernetzen_leer(w)
            check(f"Vernetzen lässt „{wert}“ stehen und meldet nichts",
                  w.model.netz.sweep == wert and "Sechsflächner-Sweep ausgeschaltet" not in protokoll,
                  f"{w.model.netz.sweep}: " + protokoll[-200:].replace("\n", " | "))
    finally:
        w.close()
        w.deleteLater()


def test_vernetzer_kann_weiter():
    """Der Sweep selbst bleibt (Vernetzer-Datei): programmatisch gesetzt wirkt er."""
    from statik3d import mesher
    import tests.test_sweep as TS
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        m, k = TS.platte_mit_stufe() if hasattr(TS, "platte_mit_stufe") else (None, None)
        if m is None:
            check("Prüfkörper aus test_sweep vorhanden", False)
            return
        m.netz.sweep = True
        mesher.modell_vernetzen(m, [], workers=1)
    typen = {m.elements[int(i)].typ for i in k.elemente}
    check("programmatisch gesetzt sweept der Vernetzer weiter (hex8 im Netz)", "hex8" in typen, str(sorted(typen)))


def main():
    for t in (test_laden_schaltet_aus, test_maske_ohne_haken, test_vernetzer_kann_weiter):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:             # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
