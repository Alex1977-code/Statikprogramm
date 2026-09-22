"""
InfoCAD/InfoGraph: die Textausgabe von ``/ExportTxt`` lesen.

Geprueft wird nicht, ob eine InfoCAD-Datei „irgendwie ankommt", sondern
genau die vier Eigenheiten, an denen dieses Format einen Leser scheitern
laesst - jede an einer Datei, die sie enthaelt:

* **Der Exitcode taugt nicht.** InfoCAD endet immer mit 13. Ob die Ausgabe
  vollstaendig ist, steht allein in ihr: jeder Block muss mit ``END <NAME>``
  schliessen, und ``N=`` im Kopf muss zur Zahl der Datenzeilen passen. Eine
  abgebrochene Datei muss der Leser als abgebrochen melden - nicht als
  kleineres Modell.
* **Unbekannte Tabellen ueberspringt InfoCAD still.** Der Leser tut das
  Gegenteil: er benennt jede Tabelle, die er gefunden und nicht verwertet
  hat. Sonst haelt ein Anwender ein Modell ohne Lager fuer vollstaendig.
* **Derselbe Typcode bedeutet in zwei Tabellen Verschiedenes**: in ELEMENTE
  ist 2 der Stab, in QUERSW die Schale. Wer den Code aus der falschen Tabelle
  nimmt, filtert lautlos das Gegenteil - und bekommt eine gefuellte,
  plausible Liste. Die Probe enthaelt beides zugleich.
* **Dezimalkomma, Tabulator, wechselnde Kodierung** (UTF-16, UTF-8, cp1252).

Dazu der gepackte Layercode (``Layer<<16 | FarbID<<8 | 1``), aus dem die
Elementgruppe wird, und die Lage der Z-Achse.

Die Formatangaben stammen aus der Uebergabe eines InfoCAD-Projekts vom
21.09.2026; die Bloecke dieser Pruefung sind danach gebaut.
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d.importers import import_file                      # noqa: E402
from statik3d.importers.infocad_txt import (bloecke_lesen,       # noqa: E402
                                            import_infocad_txt)

RESULTS = []
HIER = os.path.dirname(os.path.abspath(__file__))


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FEHLER'} {name:58s} {detail}")
    return bool(ok)


def close(name, got, want, tol, unit=""):
    ok = abs(float(got) - float(want)) <= tol
    abw = abs(got - want) / abs(want) * 100 if want else 0.0
    return check(name, ok, f"{got:.6g}{unit} / {want:.6g}{unit}  Abw. {abw:.4f} %")


# --------------------------------------------------------------------------
# Baukasten: Bloecke genau in der Schreibweise des Formats
# --------------------------------------------------------------------------
def block(name, zeilen, kopf=None, n=None, zeit="04.09.26 18:07"):
    """Ein BEGIN/END-Block. ``kopf`` fehlt oft und ist dann nur '?'."""
    n = len(zeilen) if n is None else n
    aus = [f"BEGIN {name} N={n} TIME={zeit}"]
    aus.append("\t".join(kopf or ["?"] * 4))
    aus.extend("\t".join(str(x) for x in z) for z in zeilen)
    aus.append(f"END {name}")
    return "\n".join(aus)


def probemodell(z_faktor=1.0):
    """Vier Knoten, ein Viereck, ein Dreieck und ein Stab - und zu jedem
    Element die Angaben, die die Tabelle ELEMENTE fuehrt.

    Der Layercode ist gepackt: Layer 21, rot (FarbID 3) -> 21*65536 + 3*256
    + 1 = 1377025; Layer 10, schwarz (1) -> 655617.
    """
    knoten = [[1, "0", "0", "0"], [2, "2,5", "0", "0"],
              [3, "2,5", "1,5", f"{0.4 * z_faktor:.1f}".replace(".", ",")],
              [4, "0", "1,5", "0"], [5, "1,0", "3,0", "0"]]
    # Nr Typ K1 K2 K3 K4 - - Mat QS - - Layercode
    elemente = [
        [1, 11, 1, 2, 3, 4, 0, 0, 1, 1, 0, 0, 1377025],   # Viereckschale
        [2, 8, 4, 3, 5, 0, 0, 0, 1, 1, 0, 0, 655617],     # Dreieckschale
        [3, 2, 1, 5, 0, 0, 0, 0, 1, 2, 0, 0, 655617],     # Stab
    ]
    # Nr Typ E G nu alpha_t gamma   (E in N/mm^2, Wichte in kN/m^3)
    mat = [[1, 1, "210000", "81000", "0,3", "1,2e-5", "78,5"]]
    # Nr Typ Wert ...  - Typ 2 ist hier die SCHALE, Dicke in Metern
    quersw = [[1, 2, "0,012", 0, 0], [2, 1, "0,0", 0, 0]]
    return knoten, elemente, mat, quersw


def schreibe(name, text, kodierung="utf-8"):
    pfad = os.path.join(HIER, name)
    io.open(pfad, "w", encoding=kodierung, newline="\r\n").write(text)
    return pfad


def volle_datei(z_faktor=1.0, extra=""):
    kn, el, mat, qs = probemodell(z_faktor)
    teile = [block("KNOTEN", kn), block("ELEMENTE", el),
             block("MAT", mat, n=len(mat)), block("QUERSW", qs)]
    if extra:
        teile.append(extra)
    return "\n".join(teile) + "\n"


# --------------------------------------------------------------------------
def test_bloecke_und_vollstaendigkeit():
    """BEGIN/END, N= und die abgebrochene Datei.

    Der Exitcode von InfoCAD ist immer 13 - die Vollstaendigkeit steht allein
    in der Datei. Ein Leser, der eine abgebrochene Ausgabe als kleineres
    Modell nimmt, liefert stillschweigend zu wenig.
    """
    pfad = schreibe("_infocad_voll.txt", volle_datei())
    log = []
    b = bloecke_lesen(pfad, log)
    check("die vier Bloecke werden gefunden",
          sorted(b) == ["ELEMENTE", "KNOTEN", "MAT", "QUERSW"], str(sorted(b)))
    check("N= aus dem Blockkopf wird gelesen", b["KNOTEN"].n_soll == 5,
          f"N={b['KNOTEN'].n_soll}, gelesen {b['KNOTEN'].n_ist}")
    check("TIME= aus dem Blockkopf wird gelesen",
          b["KNOTEN"].zeit == "04.09.26 18:07", b["KNOTEN"].zeit)
    check("die Kopfzeile zaehlt nicht als Datenzeile", b["KNOTEN"].n_ist == 5)
    check("alle Bloecke gelten als vollstaendig",
          all(x.vollstaendig() for x in b.values()))
    check("und nichts wird beanstandet",
          not any("N=" in z or "END" in z for z in log if z.startswith("WARN")),
          str([z for z in log if z.startswith("WARN")])[:70])

    # abgebrochen: das END fehlt, weil InfoCAD mitten im Schreiben endete
    roh = volle_datei()
    ab = roh[:roh.index("END ELEMENTE")]
    p2 = schreibe("_infocad_ab.txt", ab)
    log2 = []
    b2 = bloecke_lesen(p2, log2)
    check("die abgebrochene Tabelle gilt nicht als vollstaendig",
          not b2["ELEMENTE"].vollstaendig(),
          f"abgeschlossen={b2['ELEMENTE'].abgeschlossen}, "
          f"{b2['ELEMENTE'].n_ist} von {b2['ELEMENTE'].n_soll}")
    check("und der Abbruch wird gemeldet",
          any("endet mitten im Block" in z for z in log2),
          str([z for z in log2 if z.startswith("WARN")])[:80])

    # zu wenige Zeilen: N= sagt mehr, als dasteht
    kn, el, mat, qs = probemodell()
    p3 = schreibe("_infocad_kurz.txt",
                  block("KNOTEN", kn, n=99) + "\n" + block("ELEMENTE", el) + "\n")
    log3 = []
    b3 = bloecke_lesen(p3, log3)
    check("eine zu kurze Tabelle wird an N= erkannt",
          not b3["KNOTEN"].vollstaendig() and b3["KNOTEN"].n_ist == 5,
          f"{b3['KNOTEN'].n_ist} von {b3['KNOTEN'].n_soll}")
    check("und die Meldung nennt beide Zahlen",
          any("N=99" in z and "5 Zeilen" in z for z in log3),
          str([z for z in log3 if "N=" in z])[:80])


def test_modell_kommt_an():
    """Knoten, Elemente, Werkstoff und Dicke - mit Dezimalkomma."""
    pfad = schreibe("_infocad_voll.txt", volle_datei())
    log = []
    m = import_infocad_txt(pfad, log=log)
    check("fünf Knoten", m.nn == 5, f"{m.nn}")
    close("das Dezimalkomma wird gelesen", m.nodes[1][0], 2.5, 1e-12, " m")
    check("drei Elemente", len(m.elements) == 3,
          str([e.typ for e in m.elements]))
    check("Viereck, Dreieck und Stab in dieser Reihenfolge",
          [e.typ for e in m.elements] == ["shell4", "shell3", "beam"],
          str([e.typ for e in m.elements]))
    check("das Dreieck bekommt drei Knoten, nicht vier",
          len(m.elements[1].nodes) == 3, str(m.elements[1].nodes))
    check("der Stab bekommt zwei", len(m.elements[2].nodes) == 2,
          str(m.elements[2].nodes))
    mat = m.materials[m.elements[0].mat]
    close("E-Modul aus N/mm² gedeutet", mat.E, 210e9, 1e3, " Pa")
    check("und die Deutung steht im Protokoll",
          any("als N/mm²" in z for z in log),
          str([z for z in log if "N/mm" in z])[:70])
    close("Querdehnzahl", mat.nu, 0.3, 1e-12)
    close("Dichte aus der Wichte in kN/m³", mat.rho, 78.5e3 / 9.81, 1.0, " kg/m³")
    t = m.shells[m.elements[0].sec].t
    close("die Schalendicke steht in Metern", t, 0.012, 1e-12, " m")


def test_typcode_kommt_aus_der_richtigen_tabelle():
    """In ELEMENTE ist 2 der Stab, in QUERSW die Schale.

    Das ist der teuerste Lesefehler dieses Formats, weil er nicht auffaellt:
    beide Deutungen liefern eine gefuellte, plausible Liste. Die Probe
    enthaelt darum beides zugleich - ein Element mit Typ 2 (ein Stab) und
    einen Querschnitt mit Typ 2 (eine Schale von 12 mm).
    """
    pfad = schreibe("_infocad_voll.txt", volle_datei())
    m = import_infocad_txt(pfad, log=[])
    stab = [e for e in m.elements if e.typ == "beam"]
    check("Typ 2 in ELEMENTE ist genau ein Stab", len(stab) == 1,
          f"{len(stab)} Stab/Staebe")
    check("und nicht zwei Schalen", len([e for e in m.elements
                                         if e.typ.startswith("shell")]) == 2)
    check("Typ 2 in QUERSW ist die Schale mit 12 mm",
          any(abs(s.t - 0.012) < 1e-12 for s in m.shells.values()),
          str({k: v.t for k, v in m.shells.items()}))
    check("der Querschnitt mit Typ 1 wird nicht als Dicke genommen",
          not any(abs(s.t) < 1e-9 for s in m.shells.values()),
          str({k: v.t for k, v in m.shells.items()}))


def test_layercode_wird_ausgepackt():
    """Spalte 13 ist gepackt: ``Layer<<16 | FarbID<<8 | 1``.

    Der Layer ist in InfoCAD die Auswertungseinheit; in Statik3D wird er die
    Elementgruppe. 1377025 = 21*65536 + 3*256 + 1 (Layer 21, rot),
    655617 = 10*65536 + 1*256 + 1 (Layer 10, schwarz).
    """
    pfad = schreibe("_infocad_voll.txt", volle_datei())
    m = import_infocad_txt(pfad, log=[])
    gruppen = [e.group for e in m.elements]
    check("die Probe ist scharf: die Rohwerte sind nicht die Layernummern",
          1377025 != 21 and 655617 != 10)
    check("Layer 21 wird ausgepackt", gruppen[0] == "Layer 21", gruppen[0])
    check("Layer 10 auch", gruppen[1] == "Layer 10" == gruppen[2], str(gruppen))


def test_unbekannte_tabelle_wird_benannt():
    """InfoCAD ueberspringt unbekannte Tabellen still - der Leser nicht.

    Ein Anwender, dem die Lager fehlen, muss es erfahren. Steht FESTH in der
    Ausgabe, sagt der Leser, dass er sie nicht liest; fehlt sie ganz, sagt er
    das auch.
    """
    fremd = block("FESTH", [[1, 1, 1, 1, 1, 1, 1], [4, 1, 1, 1, 0, 0, 0]])
    pfad = schreibe("_infocad_fremd.txt", volle_datei(extra=fremd))
    log = []
    import_infocad_txt(pfad, log=log)
    check("die fremde Tabelle wird benannt",
          any("FESTH" in z and "nicht gelesen" in z for z in log),
          str([z for z in log if "FESTH" in z])[:90])
    check("und die Zeilenzahl steht dabei",
          any("FESTH" in z and "2 Zeilen" in z for z in log))
    check("der Anwender erfährt, dass die Lager fehlen",
          any("Lager" in z and "anzulegen" in z for z in log),
          str([z for z in log if "Lager" in z])[:90])

    # ganz ohne FESTH muss es genauso deutlich sein
    log2 = []
    import_infocad_txt(schreibe("_infocad_voll.txt", volle_datei()), log=log2)
    check("auch ohne FESTH wird auf die fehlenden Lager hingewiesen",
          any("Lager und Lasten" in z for z in log2),
          str([z for z in log2 if "Lager" in z])[:90])

    # eine Ergebnistabelle ist kein Versehen, sondern Absicht
    reak = block("REAK.GZT", [[1, "0,1", "0,2", "0,0", "0", "0", "0"]])
    log3 = []
    import_infocad_txt(schreibe("_infocad_reak.txt", volle_datei(extra=reak)),
                       log=log3)
    check("eine Ergebnistabelle wird als solche benannt",
          any("REAK.GZT" in z and "Ergebnistabelle" in z for z in log3),
          str([z for z in log3 if "REAK" in z])[:90])
    check("und nicht als Fehler gemeldet",
          not any(z.startswith("WARN") and "REAK" in z for z in log3))


def test_kodierungen_und_erkennung():
    """UTF-16, UTF-8 und cp1252 - und die Erkennung am Inhalt."""
    for kod in ("utf-8", "utf-16", "cp1252"):
        pfad = schreibe(f"_infocad_{kod}.txt", volle_datei(), kodierung=kod)
        m = import_infocad_txt(pfad, log=[])
        check(f"{kod} wird gelesen", m.nn == 5 and len(m.elements) == 3,
              f"{m.nn} Knoten, {len(m.elements)} Elemente")

    # ueber import_file: die Endung .txt allein sagt nichts
    m2 = import_file(os.path.join(HIER, "_infocad_utf-8.txt"), log=[])
    check("import_file erkennt die Ausgabe am BEGIN", m2.nn == 5, f"{m2.nn} Knoten")
    p_fremd = schreibe("_infocad_nichts.txt", "Das ist eine Notiz.\nZweite Zeile.\n")
    try:
        import_file(p_fremd, log=[])
        check("eine fremde .txt wird abgewiesen", False, "sie wurde gelesen")
    except ImportError as ex:
        check("eine fremde .txt wird abgewiesen mit Begründung",
              "BEGIN" in str(ex), str(ex)[:80])


def test_z_achse_bleibt_rechtshaendig():
    """InfoCAD-Modelle stehen oft mit Z nach unten.

    Gedreht wird darum um 180 Grad um die X-Achse (y → −y, z → −z) und nicht
    z allein gespiegelt: eine Spiegelung waere linkshaendig und kehrte jede
    Flaechennormale um - ein Fehler, den keine Kraeftebilanz sieht.
    """
    pfad = schreibe("_infocad_voll.txt", volle_datei())
    ohne = import_infocad_txt(pfad, log=[])
    mit = import_infocad_txt(pfad, log=[], z_nach_unten=True)
    close("ohne Angabe bleibt z, wie es dasteht", ohne.nodes[2][2], 0.4, 1e-12, " m")
    close("mit Angabe kehrt sich z um", mit.nodes[2][2], -0.4, 1e-12, " m")
    close("und y ebenfalls", mit.nodes[2][1], -1.5, 1e-12, " m")
    close("x bleibt", mit.nodes[2][0], 2.5, 1e-12, " m")
    import numpy as np
    # Drei Knoten, deren Normale in **allen drei** Komponenten von null
    # verschieden ist - sonst unterscheidet die Probe Drehung und Spiegelung
    # gar nicht: bei n_x = 0 sehen beide gleich aus.
    a = np.asarray(ohne.nodes)[[0, 2, 4]]
    b = np.asarray(mit.nodes)[[0, 2, 4]]
    va = np.cross(a[1] - a[0], a[2] - a[0])
    vb = np.cross(b[1] - b[0], b[2] - b[0])
    check("die Probe ist scharf: die Normale hat drei Komponenten",
          all(abs(x) > 1e-9 for x in va), f"{np.round(va, 4)}")
    # Drehung R = diag(1,-1,-1), det = +1: die Normale dreht mit,
    #     n -> R n = (n_x, -n_y, -n_z).
    # Spiegelung M = diag(1,1,-1), det = -1: sie kippt zusaetzlich um,
    #     n -> -M n = (-n_x, -n_y, n_z)  -  das waere linkshaendig.
    gedreht = np.array([va[0], -va[1], -va[2]])
    gespiegelt = np.array([-va[0], -va[1], va[2]])
    check("die Normale dreht mit (rechtshändig)",
          float(np.abs(vb - gedreht).max()) < 1e-12,
          f"{np.round(va, 4)} → {np.round(vb, 4)}")
    check("und kippt nicht um, wie es eine Spiegelung täte",
          float(np.abs(vb - gespiegelt).max()) > 1e-6,
          f"eine Spiegelung gäbe {np.round(gespiegelt, 4)}")
    close("die Länge bleibt", float(np.linalg.norm(vb)),
          float(np.linalg.norm(va)), 1e-12)


def test_leere_und_falsche_dateien():
    """Was nicht gelesen werden kann, wird benannt und nicht erfunden."""
    p = schreibe("_infocad_leer.txt", "BEGIN ZEUG N=0 TIME=x\n?\nEND ZEUG\n")
    try:
        import_infocad_txt(p, log=[])
        check("eine Ausgabe ohne KNOTEN wird abgewiesen", False, "sie lief durch")
    except ImportError as ex:
        check("eine Ausgabe ohne KNOTEN wird abgewiesen",
              "KNOTEN" in str(ex), str(ex)[:90])
    p2 = schreibe("_infocad_nichts2.txt", "nur Text\n")
    try:
        import_infocad_txt(p2, log=[])
        check("eine Datei ohne Block wird abgewiesen", False, "sie lief durch")
    except ImportError as ex:
        check("eine Datei ohne Block wird abgewiesen",
              "BEGIN/END" in str(ex), str(ex)[:90])


def aufraeumen():
    for n in os.listdir(HIER):
        if n.startswith("_infocad_") and n.endswith(".txt"):
            try:
                os.remove(os.path.join(HIER, n))
            except OSError:
                pass


def main():
    for t in (test_bloecke_und_vollstaendigkeit, test_modell_kommt_an,
              test_typcode_kommt_aus_der_richtigen_tabelle,
              test_layercode_wird_ausgepackt,
              test_unbekannte_tabelle_wird_benannt,
              test_kodierungen_und_erkennung,
              test_z_achse_bleibt_rechtshaendig,
              test_leere_und_falsche_dateien):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:                                  # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{t.__name__} laeuft durch", False, str(ex)[:80])
    aufraeumen()
    ok = sum(1 for _n, o in RESULTS if o)
    print("\n" + "=" * 92)
    print(f"Ergebnis: {ok}/{len(RESULTS)} Pruefungen bestanden")
    if ok != len(RESULTS):
        print("FEHLGESCHLAGEN:", [n for n, o in RESULTS if not o])
    return 0 if ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
