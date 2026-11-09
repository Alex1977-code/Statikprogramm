"""
Scheitert das Speichern, bleibt die alte Datei unversehrt (Befund B1, 09.11.2026).

Befund der Pruefagenten: Model.save oeffnete die Zieldatei sofort zum
Schreiben und schrieb sie Schluessel fuer Schluessel. Brach json.dump
mittendrin ab - im Versuch ein np.float32 in einer Knotenlast -, blieb eine
halbe Datei zurueck (72 506 -> 53 095 Bytes, JSONDecodeError). Dasselbe
droht bei voller Platte oder getrenntem Netzlaufwerk, und die Ergebnisdatei
wurde genauso geschrieben.

Jetzt: model.sicher_schreiben - Zwischendatei, danach os.replace; numpy-Zahlen
werden beim Speichern in Python-Zahlen gewandelt.

Aufruf:  python -m tests.test_speichern_sicher
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from statik3d import ergebnisse, mesher, solver                        # noqa: E402
from statik3d.model import Material, Model, Section                    # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK  ' if ok else 'FAIL'} {name:<78} {detail}")
    return bool(ok)


def kragarm() -> Model:
    m = Model("Kragarm")
    m.add_material(Material.steel("S235"))
    m.add_section(Section.from_profile("IPE 200"))
    ids = mesher.line_of_beams(m, "S235", "IPE 200", (0, 0, 0), (3, 0, 0), 3)
    m.fix(int(ids[0]), "all")
    m.load_node(int(ids[-1]), Fz=-1000.0)
    return m


def test_abbruch_laesst_alte_datei_stehen():
    ordner = tempfile.mkdtemp(prefix="s3d_speichern_")
    pfad = os.path.join(ordner, "modell.json")
    m = kragarm()
    m.save(pfad)
    alt = open(pfad, "rb").read()
    m.meta["kaputt"] = object()            # nicht speicherbar: json.dump bricht ab
    try:
        m.save(pfad)
        check("ein nicht speicherbarer Wert laesst das Speichern scheitern", False)
    except TypeError:
        check("ein nicht speicherbarer Wert laesst das Speichern scheitern", True)
    neu = open(pfad, "rb").read()
    # Ohne den Umbau: die Datei ist kuerzer und nicht mehr lesbar
    check("nach dem Abbruch ist die alte Datei Byte fuer Byte unveraendert", neu == alt,
          f"{len(alt)} -> {len(neu)} Bytes")
    try:
        Model.load(pfad)
        lesbar = True
    except Exception:                       # noqa: BLE001
        lesbar = False
    check("die alte Datei laesst sich weiter oeffnen", lesbar)
    rest = [x for x in os.listdir(ordner) if x != "modell.json"]
    check("keine Zwischendatei bleibt liegen", not rest, str(rest))


def test_numpy_zahlen_speichern():
    ordner = tempfile.mkdtemp(prefix="s3d_speichern_")
    pfad = os.path.join(ordner, "modell.json")
    m = kragarm()
    m.load_node(1, Fz=np.float32(-500.0))
    m.save(pfad)
    m2 = Model.load(pfad)
    werte = [float(nl.F[2]) for nl in m2.case().nodal_loads]
    check("eine Knotenlast mit np.float32 wird gespeichert und gelesen", -500.0 in werte, str(werte))


def test_ergebnisdatei_bleibt_bei_abbruch():
    from statik3d.model import sicher_schreiben
    ordner = tempfile.mkdtemp(prefix="s3d_speichern_")
    pfad = os.path.join(ordner, "modell.erg")
    with open(pfad, "wb") as f:
        f.write(b"alte Ergebnisdatei")

    def kaputt(fh):
        fh.write(b"halb")
        raise OSError("Platte voll")
    try:
        sicher_schreiben(pfad, kaputt, text=False)
    except OSError:
        pass
    check("sicher_schreiben: alte Datei bleibt bei Abbruch", open(pfad, "rb").read() == b"alte Ergebnisdatei")
    check("sicher_schreiben: keine Zwischendatei bleibt liegen", os.listdir(ordner) == ["modell.erg"],
          str(os.listdir(ordner)))
    # Die Ergebnisdatei selbst geht ueber sicher_schreiben
    m = kragarm()
    an = solver.solve_all(m, workers=1, combinations=False)
    groesse = ergebnisse.schreiben(os.path.join(ordner, "kragarm.erg"), m, an)
    check("Ergebnisdatei wird geschrieben (ueber die Zwischendatei)",
          groesse and os.path.exists(os.path.join(ordner, "kragarm.erg"))
          and not [x for x in os.listdir(ordner) if x.endswith(".schreiben")], str(groesse))


def main():
    for t in (test_abbruch_laesst_alte_datei_stehen, test_numpy_zahlen_speichern,
              test_ergebnisdatei_bleibt_bei_abbruch):
        try:
            t()
        except Exception as ex:               # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((f"{t.__name__} (Ausnahme: {ex})", False))
    nok = sum(1 for _n, ok in RESULTS if ok)
    print("=" * 92)
    print(f"Ergebnis: {nok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    sys.exit(main())
