"""
Import von RFEM/RSTAB: native Projektdateien (.rf5/.rf6/.rs5/.rs6) und
erweiterter Tabellenexport mit Linien-/Flaechenlagern, Gelenken und
Nichtlinearitaeten.
Aufruf:  python -m tests.test_rfem
"""
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d.model import Model  # noqa: E402
from statik3d import solver, supports  # noqa: E402
from statik3d.importers import import_file, SUPPORTED  # noqa: E402
from statik3d.importers import rfem_native as RN  # noqa: E402
from statik3d.importers.rfem_tables import import_rfem_tables  # noqa: E402
from statik3d.importers.xlsx_reader import write_xlsx  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FAIL'} {name:56s} {detail}")
    return ok


def _sqlite_model(path):
    con = sqlite3.connect(path)
    con.executescript("""
    CREATE TABLE Nodes (No INTEGER, X REAL, Y REAL, Z REAL);
    INSERT INTO Nodes VALUES (1,0,0,0),(2,0,0,6),(3,15,0,6),(4,15,0,0);
    CREATE TABLE Lines (No INTEGER, "Node List" TEXT);
    INSERT INTO Lines VALUES (1,'1,2'),(2,'2,3'),(3,'3,4');
    CREATE TABLE Members (No INTEGER, Line INTEGER, "Cross-Section" TEXT, Material TEXT, Rotation REAL);
    INSERT INTO Members VALUES (1,1,'HEB 300','S355',0),(2,2,'IPE 500','S355',0),(3,3,'HEB 300','S355',0);
    CREATE TABLE "Cross-Sections" (No INTEGER, Name TEXT);
    INSERT INTO "Cross-Sections" VALUES (1,'HEB 300'),(2,'IPE 500');
    CREATE TABLE Materials (No INTEGER, Name TEXT);
    INSERT INTO Materials VALUES (1,'S355');
    CREATE TABLE "Nodal Supports" (No TEXT, Name TEXT, ux TEXT, uy TEXT, uz TEXT,
                                   phix TEXT, phiy TEXT, phiz TEXT);
    INSERT INTO "Nodal Supports" VALUES
        ('1','Fuss links','rigid','rigid','rigid, Ausfall bei Zug, Schlupf 0.002','rigid','free','rigid'),
        ('4','Fuss rechts','1.5e8','rigid','rigid, failure in tension','rigid','free','rigid');
    CREATE TABLE "Line Supports" (No INTEGER, Name TEXT, Line TEXT, uz TEXT, ux TEXT);
    INSERT INTO "Line Supports" VALUES (1,'Sohle','2','5e7, Ausfall bei Zug','rigid, Reibung mu 0.4');
    """)
    con.commit()
    con.close()


def test_native_sqlite():
    d = tempfile.mkdtemp(prefix="s3d_rf6_")
    try:
        p = os.path.join(d, "halle.rf6")
        _sqlite_model(p)
        info = RN.probe(p)
        check("probe erkennt SQLite", info["kind"] == "sqlite", info["desc"])
        check("probe listet Tabellen", len(info["tables"]) == 7, str(len(info["tables"])))
        check("Bericht nennt Kennung und Tabellen",
              "Kennung" in info["report"] and "Nodal Supports" in info["report"])
        log = []
        m = import_file(p, log=log)
        check("Knoten importiert", m.nn == 4, str(m.nn))
        check("Stabelemente importiert", len(m.elements) == 3, str(len(m.elements)))
        check("Linien uebernommen", len(m.lines) == 3, str(len(m.lines)))
        check("Querschnitte aus der Datenbank",
              set(m.sections) >= {"HEB 300", "IPE 500"}, str(list(m.sections)))
        check("Knotenlager importiert", len(m.supports) == 2, str(len(m.supports)))
        b = m.supports[0].dof_behaviour(2)
        check("Ausfall bei Zug erkannt", b.failure == "zug", b.describe())
        check("Schlupf erkannt", abs(b.slip - 0.002) < 1e-12, f"{b.slip}")
        check("freier FHG erkannt", m.supports[0].dof_behaviour(4).typ == "free")
        check("Federsteifigkeit erkannt",
              abs(m.supports[1].dof_behaviour(0).stiffness - 1.5e8) < 1, "")
        check("englische Schreibweise erkannt",
              m.supports[1].dof_behaviour(2).failure == "zug")
        check("Linienlager importiert", len(m.line_supports) == 1)
        ls = m.line_supports[0]
        check("Linienlager: Feder und Ausfall",
              ls.dof_behaviour(2).typ == "spring" and ls.dof_behaviour(2).failure == "zug",
              ls.dof_behaviour(2).describe())
        check("Linienlager: Reibung", abs(ls.dof_behaviour(0).mu - 0.4) < 1e-12)
        check("Modell ist nichtlinear", m.has_contact)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_native_zip_und_json():
    d = tempfile.mkdtemp(prefix="s3d_rs6_")
    try:
        p = os.path.join(d, "rahmen.rs6")
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("nodes.csv", "No;X;Y;Z\n1;0;0;0\n2;0;0;4\n3;6;0;4\n")
            z.writestr("members.csv",
                       "No;Node A;Node B;Cross-Section;Material\n1;1;2;HEA 200;S235\n2;2;3;IPE 240;S235\n")
            z.writestr("nodal supports.csv", "No;uz;ux;uy\n1;rigid;rigid;rigid\n")
        info = RN.probe(p)
        check("probe erkennt ZIP", info["kind"] == "zip", info["desc"])
        m = import_file(p, log=[])
        check("ZIP: Knoten", m.nn == 3, str(m.nn))
        check("ZIP: Elemente", len(m.elements) == 2, str(len(m.elements)))
        check("ZIP: Querschnitte", set(m.sections) >= {"HEA 200", "IPE 240"})
        check("ZIP: Lager", len(m.supports) == 1)

        # eingebettete SQLite-Datei im ZIP
        p2 = os.path.join(d, "eingebettet.rf5")
        inner = os.path.join(d, "inner.sqlite")
        _sqlite_model(inner)
        with zipfile.ZipFile(p2, "w") as z:
            z.write(inner, "model/data.sqlite")
        m2 = import_file(p2, log=[])
        check("ZIP mit eingebetteter Datenbank", m2.nn == 4 and len(m2.elements) == 3,
              f"{m2.nn} Knoten")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_native_unbekannt():
    d = tempfile.mkdtemp(prefix="s3d_bin_")
    try:
        p = os.path.join(d, "geheim.rf5")
        with open(p, "wb") as f:
            f.write(b"\x89DLUBAL\x00" + os.urandom(4096) + b"RFEM 5.26 Projektdatei")
        info = RN.probe(p)
        check("probe erkennt unbekanntes Binaerformat", info["kind"] == "unknown", info["desc"])
        check("probe findet lesbare Zeichenketten",
              any("DLUBAL" in x for x in info.get("strings", [])))
        try:
            import_file(p)
            check("unbekannte Datei meldet Fehler", False)
        except ImportError as ex:
            txt = str(ex)
            check("Fehlermeldung nennt Kennung", "Kennung" in txt)
            check("Fehlermeldung nennt den Exportweg", "SAF" in txt and "IFC" in txt)
            check("Fehlermeldung raet nicht", "geraten" in txt)
        for ext in (".rf5", ".rf6", ".rs5", ".rs6", ".rs8", ".rs9", ".rfem", ".rstab"):
            if ext not in SUPPORTED:
                check(f"Endung {ext} gefuehrt", False)
                break
        else:
            check("alle nativen Endungen gefuehrt", True)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_tabellen_erweitert():
    d = tempfile.mkdtemp(prefix="s3d_tab_")
    try:
        def w(n, t):
            with open(os.path.join(d, n), "w", encoding="utf-8") as f:
                f.write(t)
        w("1.1 Knoten.csv", "Knoten Nr.;X [m];Y [m];Z [m]\n1;0;0;0\n2;0;0;4\n3;6;0;4\n4;6;0;0\n")
        w("1.2 Linien.csv", "Linie Nr.;Knoten Nr.\n1;1,2\n2;2,3\n3;3,4\n")
        w("1.7 Staebe.csv",
          "Stab Nr.;Linie Nr.;Querschnitt;Material\n1;1;HEB 200;S235\n2;2;IPE 240;S235\n3;3;HEB 200;S235\n")
        w("1.8 Knotenlager.csv",
          "Lager Nr.;Knoten Nr.;ux;uy;uz;phix;phiy;phiz\n"
          "1;1;starr;starr;starr, Ausfall bei Zug, Schlupf 0.003;starr;frei;starr\n"
          "2;4;starr;starr;starr, Ausfall bei Zug, Reibung mu 0.35;starr;frei;starr\n")
        w("1.9 Linienlager.csv",
          "Nr.;Linie Nr.;uz [kN/m];ux\n1;2;50000, Ausfall bei Zug;starr, Reibung mu 0.4\n")
        w("1.13 Stabendgelenke.csv", "Nr.;ux;uy;uz;phix;phiy;phiz\n1;-;-;-;-;frei;1500\n")
        log = []
        m = import_rfem_tables(d, Model("Tab"), log)
        check("Tabellen: Knoten und Staebe", m.nn == 4 and len(m.elements) == 3)
        check("Tabellen: Knotenlager mit Schlupf",
              abs(m.supports[0].dof_behaviour(2).slip - 0.003) < 1e-12,
              m.supports[0].dof_behaviour(2).describe())
        b0 = m.supports[1].dof_behaviour(0)
        check("Tabellen: Reibung auf die Querrichtungen gelegt",
              abs(b0.mu - 0.35) < 1e-12 and b0.mu_ref == 2, f"mu={b0.mu} ref={b0.mu_ref}")
        check("Tabellen: Linienlager", len(m.line_supports) == 1
              and m.line_supports[0].dof_behaviour(2).failure == "zug")
        check("Tabellen: Gelenkdefinition", len(m.hinges) == 1
              and "phiy" in list(m.hinges.values())[0].describe())
        h = list(m.hinges.values())[0]
        check("Tabellen: Federgelenk phiz", h.typ[5] == "spring" and h.stiffness[5] > 0,
              h.describe())
        check("Zusammenfassung nennt Linienlager", "Linienlager" in supports.summary(m))
        for e in range(len(m.elements)):
            m.load_beam(e, qz=-10e3)
        r = solver.solve_static(m)
        check("importiertes Modell rechnet", r.u is not None and r.contact,
              f"{len(r.contact)} Kontaktbedingungen")
        check("Gleichgewicht", abs(r.reactions[:, 2].sum() - 10e3 * 14) < 1.0,
              f"{r.reactions[:, 2].sum():.1f} N")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_kombinationen_abgezaehlt():
    """Jede Zeile der Tabelle „2.5 Lastkombinationen“ hat einen gezählten Ausgang.

    In dieser Tabelle haben eine eigene Protokollzeile nur die nicht
    übernommenen Zeilen LK2 und LK3 (je eine WARNUNG) und die aufgelöste LK4;
    LK1 und LK5 stehen nur in der Schlusszeile „3 von 5 Lastkombinationen“
    (gemessen an den Ständen 0ad95bb und aa22f5d). Das ist keine Regel für
    jede Zeile aus eigenen Lastfall-Anteilen: eine Zeile ohne Nummer oder mit
    Ausweichnamen bekommt auch dann eine eigene Zeile, z. B. bei
    ['1;GZT;1.35*LF1', ';GZT;1.5*LF2', '1;GZT;LF2'] „Kombination LK2
    (Tabellenzeile 2 ohne Nummer): 1.5*LF2“ und „Kombination LK1_2
    (Tabellennummer 1; LK1 gab es schon): 1*LF2“ (gemessen am Stand aa22f5d).

    Bis zum 22.09.2026 verwarf die Schleife eine Zeile ohne LF-Faktor
    (``if not factors: continue``) **vor** der Warnung über nicht aufgelöste
    Verweise (Befund SV10). Gemessen an den ersten vier Zeilen unten:
    Protokoll „2 Lastkombinationen“, Modell LK1 und LK4, eine Warnung nur für
    LK4 - LK2 und LK3 verschwanden ohne eine Zeile. Dazu wurde eine Zeile,
    deren Nummer als Text „CO5“ dasteht und deren Formel nicht mit einer Zahl
    beginnt, als Blocktitel gelesen und ebenfalls wortlos verworfen.
    """
    d = tempfile.mkdtemp(prefix="s3d_ko_")
    try:
        def w(n, t):
            with open(os.path.join(d, n), "w", encoding="utf-8") as f:
                f.write(t)
        w("1.1 Knoten.csv", "Knoten Nr.;X [m];Y [m];Z [m]\n1;0;0;0\n2;2;0;0\n")
        w("2.1 Lastfaelle.csv", "Lastfall Nr.;Bezeichnung\n1;Eigengewicht\n2;Nutzlast\n")
        w("2.5 Lastkombinationen.csv",
          "Lastkombination Nr.;Bemessungssituation;Belastung\n"
          "1;GZT;1.35*LF1 + 1.5*LF2\n"
          "2;GZT;CO1 + CO3\n"
          "3;GZT;1.0*EK1\n"
          "4;GZT;LF1 + CO1\n"
          "CO5;;LF1 + LF2\n")
        log = []
        m = import_rfem_tables(d, Model("Ko"), log)
        txt = "\n".join(log)
        ko = [z for z in log if "ombination" in z]
        for nr in (2, 3):
            check(f"die Zeile LK{nr} steht im Protokoll",
                  any(f"LK{nr}" in z for z in ko), str(ko))
        check("die Verweise der verworfenen Zeilen werden genannt",
              "CO3" in txt and "EK1" in txt, str(ko))
        check("die Schlusszeile nennt Übernommene von allen Zeilen",
              "3 von 5 Lastkombinationen" in txt,
              next((z for z in log if z.strip().endswith("Lastkombinationen")), "keine Zeile"))
        # Der Verweis auf eine schon gelesene Kombination wird aufgeloest:
        # LF1 + CO1 = LF1 + 1,35 LF1 + 1,5 LF2
        lk4 = m.combinations.get("LK4")
        f4 = dict(lk4.factors) if lk4 is not None else {}
        check("LF1 + CO1 wird zu 2,35 LF1 + 1,5 LF2 aufgelöst",
              abs(f4.get("LF1", 0.0) - 2.35) < 1e-12 and abs(f4.get("LF2", 0.0) - 1.5) < 1e-12,
              str(f4))
        check("die Zeile „CO5“ wird nicht als Blocktitel verworfen",
              "LK5" in m.combinations, str(sorted(m.combinations)))
        check("LK2 und LK3 sind nicht still im Modell",
              "LK2" not in m.combinations and "LK3" not in m.combinations,
              str(sorted(m.combinations)))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_kombination_minus_vor_verweis():
    """Ein Minus ohne Zahl zieht ab, auch vor einem Verweis auf eine Kombination.

    Der Ausdruck in ``_formel_zerlegen`` fing das Vorzeichen nur zusammen mit
    einer Ziffer. „LF2 - CO1“ ging darum als LF2 + CO1 ein; seit Verweise
    aufgeloest werden (Befund SV10), ergab das mit CO1 = 1,35·LF1 still
    LK2 = LF2 + 1,35·LF1 statt LF2 - 1,35·LF1, nur mit einer Infozeile
    (Gegenpruefung vom 23.09.2026). Vorher war LK2 = LF2 mit einer Warnung.
    Dieselbe Ursache: „LF1 - LF2“ ergab LF1 + LF2. Die Zeile mit
    ausgeschriebenem Faktor „1.0*LF2 - 1.0*CO1“ rechnete schon richtig und
    ist die Gegenprobe. Ob RFEM ein Minus ohne Zahl schreibt, ist an keiner
    echten Datei gemessen.
    """
    d = tempfile.mkdtemp(prefix="s3d_km_")
    try:
        def w(n, t):
            with open(os.path.join(d, n), "w", encoding="utf-8") as f:
                f.write(t)
        w("1.1 Knoten.csv", "Knoten Nr.;X [m];Y [m];Z [m]\n1;0;0;0\n2;2;0;0\n")
        w("2.1 Lastfaelle.csv", "Lastfall Nr.;Bezeichnung\n1;Eigengewicht\n2;Nutzlast\n")
        w("2.5 Lastkombinationen.csv",
          "Lastkombination Nr.;Bemessungssituation;Belastung\n"
          "1;GZT;1.35*LF1\n"
          "2;GZT;LF2 - CO1\n"
          "3;GZT;1.0*LF2 - 1.0*CO1\n"
          "4;GZT;LF1 - LF2\n")
        log = []
        m = import_rfem_tables(d, Model("Km"), log)

        def faktoren(name):
            k = m.combinations.get(name)
            return dict(k.factors) if k is not None else {}

        def gleich(ist, soll):
            return set(ist) == set(soll) and all(abs(ist[k] - v) < 1e-12
                                                 for k, v in soll.items())

        check("„LF2 - CO1“ ergibt LF2 - 1,35·LF1",
              gleich(faktoren("LK2"), {"LF2": 1.0, "LF1": -1.35}), str(faktoren("LK2")))
        check("„1.0*LF2 - 1.0*CO1“ ergibt dasselbe (Gegenprobe)",
              gleich(faktoren("LK3"), {"LF2": 1.0, "LF1": -1.35}), str(faktoren("LK3")))
        check("„LF1 - LF2“ ergibt LF1 - LF2",
              gleich(faktoren("LK4"), {"LF1": 1.0, "LF2": -1.0}), str(faktoren("LK4")))
        z2 = next((z for z in log if "LK2" in z), "keine Zeile")
        check("das Protokoll nennt das Ergebnis der Aufloesung samt Vorzeichen",
              "1*LF2 - 1.35*LF1" in z2, z2)
        check("alle vier Zeilen angelegt", "4 von 4 Lastkombinationen" in "\n".join(log),
              next((z for z in log if z.strip().endswith("Lastkombinationen")),
                   "keine Zeile"))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _kombinationstabelle(prefix, zeilen, lastfaelle=3):
    """Kleine Tabellenmappe mit „2.5 Lastkombinationen“ -> (Modell, Protokoll)."""
    d = tempfile.mkdtemp(prefix=prefix)
    try:
        def w(n, t):
            with open(os.path.join(d, n), "w", encoding="utf-8") as f:
                f.write(t)
        w("1.1 Knoten.csv", "Knoten Nr.;X [m];Y [m];Z [m]\n1;0;0;0\n2;2;0;0\n")
        w("2.1 Lastfaelle.csv", "Lastfall Nr.;Bezeichnung\n"
          + "".join(f"{i};LF {i}\n" for i in range(1, lastfaelle + 1)))
        w("2.5 Lastkombinationen.csv",
          "Lastkombination Nr.;Bemessungssituation;Belastung\n" + "\n".join(zeilen) + "\n")
        log = []
        m = import_rfem_tables(d, Model("Kt"), log)
        return m, log
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _gleich(ist, soll):
    return set(ist) == set(soll) and all(abs(ist[k] - v) < 1e-12 for k, v in soll.items())


def test_kombination_unerkannter_teil():
    """Ein nicht erkannter Teil der Formel legt die Kombination nicht halb an.

    Gegenpruefung vom 23.09.2026 zu Befund SV10: Der Ausdruck in
    ``_formel_zerlegen`` griff nur LF/LC/CO/LK/EK heraus, der Rest der Formel
    fiel ohne Meldung weg, sobald daneben ein LF-Anteil stand (oder ein
    aufgeloester Verweis, siehe test_kombination_rest_neben_verweis). Gemessen
    am Stand 6cbc144: „1.35*LC1 + RC1“ wurde LK6 = {LF1: 1,35},
    „1.35*LF1 + 1.5*LF2 + 0.9*RC2“ wurde {LF1: 1,35, LF2: 1,5},
    „1.35*LF1 + 1.5*Schnee“ wurde {LF1: 1,35} - zu keiner der Zeilen eine
    Protokollzeile. RC ist das englische Kuerzel der Ergebniskombination (wie
    CO zu LK); ob RFEM RC oder EK in eine Lastkombinationsformel schreibt, ist
    an keiner echten Datei gemessen. Die Klammer „1.35*(LF1 + LF2)“ ergab
    LF1 = LF2 = 1,0 aus demselben Grund („1.35*(“ fiel weg).
    """
    m, log = _kombinationstabelle("s3d_kt_", [
        "1;GZT;1.35*LF1 + 1.5*LF2",
        "2;GZT;1.35 LF1 + 1.5 LF2",
        "3;GZT;1,35*LF1 + 1,50*LF2 + 0,9*LF3",
        "4;GZT;1.35*LF1 + -1.0*LF2",
        "6;GZT;1.35*LC1 + RC1",
        "7;GZT;1.35*LF1 + 1.5*LF2 + 0.9*RC2",
        "8;GZT;1.35*LF1 + 1.5*Schnee",
        "9;GZT;1.35*(LF1 + LF2)",
    ])
    ko = [z for z in log if "ombination" in z]
    for nr in (6, 7, 8, 9):
        check(f"LK{nr} mit nicht erkanntem Teil nicht halb angelegt",
              f"LK{nr}" not in m.combinations,
              str(dict(m.combinations[f"LK{nr}"].factors)) if f"LK{nr}" in m.combinations
              else "nicht angelegt")
        z = next((z for z in ko if f"LK{nr} " in z or f"LK{nr}:" in z), "keine Zeile")
        check(f"LK{nr} steht als Warnung im Protokoll", z.startswith("WARNUNG"), z)
    z6 = next((z for z in ko if "LK6" in z), "")
    check("LK6: RC1 wird als Ergebniskombination genannt",
          "RC1" in z6 and "Ergebniskombination" in z6, z6)
    z8 = next((z for z in ko if "LK8" in z), "")
    # Den Rest selbst pruefen, nicht nur „Schnee“: die Warnung zitiert die
    # Formel „1.35*LF1 + 1.5*Schnee“, „Schnee“ stuende also auch ohne den
    # Rest darin. Gegenpruefung vom 23.09.2026: mit ``pass`` statt
    # ``gruende.append(f"nicht erkannter Teil {rest}")`` bestand die alte
    # Pruefung „"Schnee" in z8“ weiter (test_rfem 70/70).
    check("LK8: der nicht erkannte Teil „+ 1.5*Schnee“ wird genannt",
          "nicht erkannter Teil ['+ 1.5*Schnee']" in z8, z8)
    # Gegenprobe: Schreibweisen ohne Rest bleiben, wie sie waren.
    check("„1.35 LF1 + 1.5 LF2“ ohne Stern bleibt",
          _gleich(dict(m.combinations["LK2"].factors) if "LK2" in m.combinations else {},
                  {"LF1": 1.35, "LF2": 1.5}))
    check("Dezimalkomma bleibt",
          _gleich(dict(m.combinations["LK3"].factors) if "LK3" in m.combinations else {},
                  {"LF1": 1.35, "LF2": 1.5, "LF3": 0.9}))
    check("„+ -1.0*LF2“ bleibt -1,0",
          _gleich(dict(m.combinations["LK4"].factors) if "LK4" in m.combinations else {},
                  {"LF1": 1.35, "LF2": -1.0}))
    check("Schlusszeile „4 von 8 Lastkombinationen“",
          "4 von 8 Lastkombinationen" in "\n".join(log),
          next((z for z in log if z.strip().endswith("Lastkombinationen")), "keine Zeile"))


def test_kombination_verweis_auf_rest():
    """Ein Verweis auf eine Zeile mit nicht erkanntem Teil bleibt offen.

    Gegenpruefung vom 23.09.2026 zu Befund SV10: Die Zeile mit Rest selbst
    wurde gewarnt und nicht angelegt, der Rest ging aber nicht mit in die
    Aufloesung der Verweise. Ein Verweis auf sie wurde darum mit ihren halb
    gelesenen Faktoren aufgeloest. Gemessen am Stand 0ad95bb:
    ['1: 1.35*LF1 + 1.5*Schnee', '2: CO1 + LF2'] ergab LK2 = LF2 + 1,35·LF1
    mit nur einer Infozeile und „1 von 2“; ['1: 1.35*(LF1 + LF2)',
    '2: LF3 + CO1'] ergab LK2 = LF1 + LF2 + LF3 (richtig waeren 1,35/1,35/1,0);
    die Kette ['1: 1.35*LF1 + x', '2: CO1', '3: 2*CO2 + LF2'] legte
    LK2 = 1,35·LF1 und LK3 = 2,7·LF1 + LF2 an. Alle Formeln selbst gebaut; ob
    RFEM so etwas schreibt, ist an keiner echten Datei gemessen.
    """
    m, log = _kombinationstabelle("s3d_kr_", ["1;GZT;1.35*LF1 + 1.5*Schnee",
                                              "2;GZT;CO1 + LF2"], lastfaelle=2)
    ko = [z for z in log if "ombination" in z]
    for nr in (1, 2):
        z = next((z for z in ko if f"LK{nr} " in z or f"LK{nr}:" in z), "keine Zeile")
        check(f"(1) LK{nr} steht als Warnung im Protokoll", z.startswith("WARNUNG"), z)
    check("(1) LK2 nicht mit dem halb gelesenen CO1 angelegt", "LK2" not in m.combinations,
          str(dict(m.combinations["LK2"].factors)) if "LK2" in m.combinations
          else "nicht angelegt")
    check("(1) Schlusszeile „0 von 2 Lastkombinationen“",
          "0 von 2 Lastkombinationen" in "\n".join(log),
          next((z for z in log if z.strip().endswith("Lastkombinationen")), "keine Zeile"))

    m, log = _kombinationstabelle("s3d_kr_", ["1;GZT;1.35*(LF1 + LF2)",
                                              "2;GZT;LF3 + CO1"], lastfaelle=3)
    check("(2) die Klammer kommt nicht ueber den Verweis an", "LK2" not in m.combinations,
          str(dict(m.combinations["LK2"].factors)) if "LK2" in m.combinations
          else "nicht angelegt")
    check("(2) Schlusszeile „0 von 2 Lastkombinationen“",
          "0 von 2 Lastkombinationen" in "\n".join(log),
          next((z for z in log if z.strip().endswith("Lastkombinationen")), "keine Zeile"))

    m, log = _kombinationstabelle("s3d_kr_", ["1;GZT;1.35*LF1 + x", "2;GZT;CO1",
                                              "3;GZT;2*CO2 + LF2"], lastfaelle=2)
    ko = [z for z in log if "ombination" in z]
    for nr in (2, 3):
        check(f"(3) Kette: LK{nr} nicht angelegt", f"LK{nr}" not in m.combinations,
              str(dict(m.combinations[f"LK{nr}"].factors)) if f"LK{nr}" in m.combinations
              else "nicht angelegt")
        z = next((z for z in ko if f"LK{nr} " in z or f"LK{nr}:" in z), "keine Zeile")
        check(f"(3) Kette: LK{nr} steht als Warnung im Protokoll", z.startswith("WARNUNG"), z)
    check("(3) Schlusszeile „0 von 3 Lastkombinationen“",
          "0 von 3 Lastkombinationen" in "\n".join(log),
          next((z for z in log if z.strip().endswith("Lastkombinationen")), "keine Zeile"))

    # Gegenprobe: dieselbe Kette ohne Rest wird weiter aufgeloest.
    m, log = _kombinationstabelle("s3d_kr_", ["1;GZT;1.35*LF1", "2;GZT;CO1",
                                              "3;GZT;2*CO2 + LF2"], lastfaelle=2)
    lk3 = dict(m.combinations["LK3"].factors) if "LK3" in m.combinations else {}
    check("Gegenprobe: Kette ohne Rest ergibt LK3 = 2,7·LF1 + LF2",
          _gleich(lk3, {"LF1": 2.7, "LF2": 1.0}), str(lk3))
    check("Gegenprobe: „3 von 3 Lastkombinationen“",
          "3 von 3 Lastkombinationen" in "\n".join(log),
          next((z for z in log if z.strip().endswith("Lastkombinationen")), "keine Zeile"))


def test_kombination_rest_neben_verweis():
    """Ein nicht erkannter Teil neben einem aufgeloesten Verweis legt nicht halb an.

    Befund B024 vom 23.09.2026: Schnittstellen.md und der Docstring von
    _formel_zerlegen sagten, der Text sei vorher nur neben einem LF-Anteil
    weggefallen. Gemessen am Stand 6cbc144 fiel er auch neben einem
    aufgeloesten Verweis weg: ['1;GZT;1.35*LF1', '2;GZT;CO1 + Schnee'] ergab
    LK2 = {LF1: 1,35} mit der Infozeile „Verweise ['CO1'] ... aufgeloest:
    1.35*LF1“ und „2 von 2“, „Schnee“ stand in keiner Zeile;
    '2;GZT;2*CO1 x' ergab LK2 = {LF1: 2,7}. Keine Pruefung deckte den Fall:
    mit ``if offen or (rest and _f0)`` statt ``if offen or rest`` bestand
    test_rfem 96/96 (Stand ec6448c). Formeln selbst gebaut; ob RFEM so etwas
    schreibt, ist an keiner echten Datei gemessen.
    """
    for rest, zeile in ((["+ Schnee"], "2;GZT;CO1 + Schnee"), (["x"], "2;GZT;2*CO1 x")):
        m, log = _kombinationstabelle("s3d_krv_", ["1;GZT;1.35*LF1", zeile], lastfaelle=1)
        formel = zeile.split(";")[2]
        check(f"„{formel}“: LK2 nicht mit dem aufgeloesten CO1 angelegt",
              "LK2" not in m.combinations,
              str(dict(m.combinations["LK2"].factors)) if "LK2" in m.combinations
              else "nicht angelegt")
        z = next((z for z in log if "LK2 " in z or "LK2:" in z), "keine Zeile")
        check(f"„{formel}“: Warnung nennt den nicht erkannten Teil {rest}",
              z.startswith("WARNUNG") and f"nicht erkannter Teil {rest}" in z, z)
        check(f"„{formel}“: keine Infozeile „aufgeloest“ zu LK2",
              not any("LK2" in x and "aufgeloest" in x for x in log))
        check(f"„{formel}“: LK1 bleibt 1,35·LF1",
              _gleich(dict(m.combinations["LK1"].factors) if "LK1" in m.combinations else {},
                      {"LF1": 1.35}))
        check(f"„{formel}“: „1 von 2 Lastkombinationen“",
              "1 von 2 Lastkombinationen" in "\n".join(log),
              next((z for z in log if z.strip().endswith("Lastkombinationen")), "keine Zeile"))


def test_kombination_vorsatz_zusatz():
    """Vorsatz, Zusatz oder Komma in der Formel: gewarnt und nicht angelegt.

    Befund B092 vom 23.09.2026: Gemessen am Stand 6cbc144 wurden
    „GZT-1: 1.35*LF1“ als {LF1: 1,35}, „LF1/p + 1.5*LF2“ als
    {LF1: 1, LF2: 1,5}, „1.35*LF1 + 1.5*LF2 [GZT]“ und „1.35*LF1, 1.5*LF2“
    als {LF1: 1,35, LF2: 1,5} angelegt, je „1 von 1“ ohne weitere Zeile. Am
    Stand ec6448c wird jede gewarnt und nicht angelegt (nicht erkannter Teil
    in _formel_zerlegen), das deckte aber keine Pruefung: mit „,“ in der
    Zeichenklasse von ``luecke`` (Komma verbindet wie „+“) bestand test_rfem
    96/96. Ob RFEM solche Zusaetze schreibt, ist nicht gemessen - es liegt
    kein echter Tabellenexport mit Kombinationen vor; darum haelt die
    Pruefung nur die Warnung fest, der Parser liest sie nicht.
    """
    faelle = [("GZT-1: 1.35*LF1", "GZT-1:"), ("LF1/p + 1.5*LF2", "/p"),
              ("1.35*LF1 + 1.5*LF2 [GZT]", "[GZT]"), ("1.35*LF1, 1.5*LF2", ",")]
    m, log = _kombinationstabelle(
        "s3d_kvz_", [f"{i};GZT;{f}" for i, (f, _r) in enumerate(faelle, 1)]
        + ["5;GZT;1.35*LF1 + 1.5*LF2"], lastfaelle=2)
    for i, (formel, rest) in enumerate(faelle, 1):
        check(f"„{formel}“ nicht angelegt", f"LK{i}" not in m.combinations,
              str(dict(m.combinations[f"LK{i}"].factors)) if f"LK{i}" in m.combinations
              else "nicht angelegt")
        z = next((z for z in log if f"LK{i} " in z or f"LK{i}:" in z), "keine Zeile")
        check(f"„{formel}“: Warnung nennt den nicht erkannten Teil ['{rest}']",
              z.startswith("WARNUNG") and f"nicht erkannter Teil ['{rest}']" in z, z)
    # Gegenprobe: dieselbe Tabelle legt eine Formel ohne Zusatz an.
    check("Gegenprobe: „1.35*LF1 + 1.5*LF2“ angelegt",
          _gleich(dict(m.combinations["LK5"].factors) if "LK5" in m.combinations else {},
                  {"LF1": 1.35, "LF2": 1.5}))
    check("„1 von 5 Lastkombinationen“", "1 von 5 Lastkombinationen" in "\n".join(log),
          next((z for z in log if z.strip().endswith("Lastkombinationen")), "keine Zeile"))


def test_kombination_verweis_grund():
    """Die Warnung zu einem offenen CO/LK-Verweis nennt den Grund dieses Verweises.

    Je Verweis einer von drei Gruenden: die Tabelle fuehrt die Nummer nicht;
    Kreis; oder die verwiesene Zeile wird selbst nicht angelegt, mit dem Namen
    ihrer Warnung. Geprueft an Tabellen, die CO1 vollstaendig fuehren, CO1
    aber nicht anlegen (nicht erkannter Teil, kein Lastfall), an einer Kette,
    an zwei Kreisen (einer mit einer Zeile, die nur hineinverweist), am
    Verweis auf sich selbst und an einer fehlenden Nummer neben EK
    (Gegenpruefung vom 23.09.2026 zu Befund SV10). Alle Formeln selbst gebaut;
    ob RFEM so etwas schreibt, ist an keiner echten Datei gemessen.
    """
    alt = "fuehrt diese Kombination nicht oder nicht vollstaendig"
    alle = []

    def tabelle(zeilen, lastfaelle):
        m, log = _kombinationstabelle("s3d_kg_", zeilen, lastfaelle=lastfaelle)
        alle.extend(log)
        return m, log

    def warnung(log, nr):
        return next((z for z in log if z.startswith("WARNUNG")
                     and (f"LK{nr} " in z or f"LK{nr}:" in z)), "keine Zeile")

    # (1) die verwiesene Zeile hat einen nicht erkannten Teil
    m, log = tabelle(["1;GZT;1.35*LF1 + 1.5*Schnee", "2;GZT;CO1 + LF2"], 2)
    z = warnung(log, 2)
    check("(1) CO1: wird selbst nicht angelegt, siehe LK1",
          "(CO1: wird selbst nicht angelegt, siehe Warnung zu LK1)" in z, z)
    check("(1) die Warnung zu LK1, auf die verwiesen wird, gibt es",
          warnung(log, 1) != "keine Zeile", warnung(log, 1))

    # (2) die verwiesene Zeile hat keinen erkennbaren Lastfall
    m, log = tabelle(["1;GZT;Schnee", "2;GZT;CO1 + LF2"], 2)
    z = warnung(log, 2)
    check("(2) Formel ohne Lastfall: CO1 wird selbst nicht angelegt",
          "(CO1: wird selbst nicht angelegt, siehe Warnung zu LK1)" in z, z)

    # (3) Kette mit eigenem LF in der Mitte: LK2 ist offen, LK3 verweist auf LK2
    m, log = tabelle(["1;GZT;1.35*LF1 + x", "2;GZT;CO1 + LF2", "3;GZT;CO2 + LF3"], 3)
    z = warnung(log, 3)
    check("(3) Kette: CO2 wird selbst nicht angelegt, siehe LK2",
          "(CO2: wird selbst nicht angelegt, siehe Warnung zu LK2)" in z, z)
    check("(3) Kette: LK3 nicht ohne den offenen Anteil von LK2 angelegt",
          "LK3" not in m.combinations,
          str(dict(m.combinations["LK3"].factors)) if "LK3" in m.combinations
          else "nicht angelegt")
    # Der ganze Weg der Kette, wie ihn Schnittstellen.md beschreibt: jede
    # Warnung verweist auf die Zeile davor (LK3 -> LK2 -> LK1), den
    # eigentlichen Grund nennt erst die Warnung zur ersten Zeile. Befund B023
    # vom 23.09.2026: das Handbuch nannte nur den Fall mit einem Schritt.
    z2 = warnung(log, 2)
    check("(3) Kette: LK2 verweist auf LK1",
          "(CO1: wird selbst nicht angelegt, siehe Warnung zu LK1)" in z2, z2)
    z1 = warnung(log, 1)
    check("(3) Kette: erst die Warnung zu LK1 nennt den Grund",
          "nicht erkannter Teil ['+ x']" in z1, z1)
    z = next((warnung(log, nr) for nr in (2, 3) if "nicht erkannter Teil" in warnung(log, nr)),
             "")
    check("(3) Kette: LK2 und LK3 nennen den Grund nicht selbst", not z, z)

    # (4) Kreis ueber zwei Zeilen
    m, log = tabelle(["1;GZT;LF1 + CO2", "2;GZT;LF2 + CO1"], 2)
    for nr, ref in ((1, "CO2"), (2, "CO1")):
        z = warnung(log, nr)
        check(f"(4) Kreis: LK{nr} nennt {ref} als Kreis",
              f"({ref}: Kreis, führt über Verweise auf diese Kombination zurück)" in z, z)

    # (5) Kreis zwischen 2 und 3; Zeile 1 verweist nur hinein und liegt nicht darin
    m, log = tabelle(["1;GZT;LF1 + CO2", "2;GZT;LF2 + CO3", "3;GZT;LF3 + CO2"], 3)
    z = warnung(log, 1)
    check("(5) LK1 liegt nicht im Kreis: CO2 wird selbst nicht angelegt",
          "(CO2: wird selbst nicht angelegt, siehe Warnung zu LK2)" in z, z)
    for nr, ref in ((2, "CO3"), (3, "CO2")):
        z = warnung(log, nr)
        check(f"(5) LK{nr} nennt {ref} als Kreis", f"({ref}: Kreis, führt über" in z, z)

    # (6) Verweis auf sich selbst; (7) EK, Verweis auf eine Zeile mit Rest und eine
    # Nummer, die die Tabelle nicht fuehrt, in einer Formel
    m, log = tabelle(["1;GZT;LF1 + CO1", "2;GZT;LF2 + x", "3;GZT;LF3 + CO2 + EK1 + CO9"], 3)
    z = warnung(log, 1)
    check("(6) CO1 in LK1: Kreis auf sich selbst",
          "(CO1: Kreis, verweist auf diese Kombination selbst)" in z, z)
    z = warnung(log, 3)
    check("(7) je Verweis ein Grund: EK, CO2 nicht angelegt, CO9 fehlt",
          "(EK/RC ist eine Ergebniskombination (Umhüllende), als Summand nicht "
          "darstellbar; CO2: wird selbst nicht angelegt, siehe Warnung zu LK2; "
          "CO9: die Tabelle führt keine Nummer 9)" in z, z)
    check("(1)-(7) der alte Sammelgrund steht in keiner Zeile",
          not any(alt in x for x in alle), next((x for x in alle if alt in x), ""))

    # (8) eine aufgeloeste Kombination, damit auch die Infozeile geprueft wird.
    # Befund B090: der Rahmen der Warnung stand in ASCII („nicht aufloesbar -
    # nicht uebernommen“, „Umhuellende“), die Gruende darin mit Umlauten
    # („führt“, „über“) - eine Meldung in zwei Schreibweisen (Stand ec6448c).
    tabelle(["1;GZT;1.35*LF1", "2;GZT;LF2 + CO1"], 2)
    ascii_formen = ("uebernommen", "aufloesbar", "Umhuellende", "vollstaendig",
                    "aufgeloest", "fuehrt", "ueber", "zurueck")
    gemischt = [x for x in alle if x.startswith(("Kombination", "WARNUNG: Kombination"))
                and any(a in x for a in ascii_formen)]
    check("(1)-(8) keine Kombinationsmeldung in ASCII-Umschrift", not gemischt,
          gemischt[0] if gemischt else "")
    check("(8) die Infozeile schreibt „aufgelöst“",
          any(x.startswith("Kombination LK2") and "aufgelöst: 1*LF2 + 1.35*LF1" in x
              for x in alle), next((x for x in alle if x.startswith("Kombination LK2")),
                                   "keine Zeile"))


def test_kombination_ohne_nummer_name():
    """Eine Zeile ohne Nummer belegt keinen Namen, den die Tabelle vergibt.

    Gegenpruefung vom 23.09.2026 zu Befund SV10: Die Zeile ohne Nummer hiess
    LK{Zahl der bisher angelegten + 1}, das Protokoll nennt aber die
    Tabellennummer. Gemessen am Stand 6cbc144: bei
    ['1;GZT;1.35*LF1', ';GZT;1.5*LF2', '2;GZT;1.0*EK1'] warnte das Protokoll
    „LK2 ... nicht uebernommen“, im Modell stand LK2 = {LF2: 1,5}. Bei
    [';GZT;1.5*LF2', '1;GZT;1.35*LF1 + CO2', '2;GZT;LF2'] meldete es
    „LK1: ... aufgeloest: 1.35*LF1 + 1*LF2“, LK1 war aber {LF2: 1,5} und die
    aufgeloeste Kombination hiess LK1_2.

    C und D: eine doppelte Tabellennummer bekommt einen Ausweichnamen, und
    die Protokollzeile nennt ihn samt Grund, mit Verweis (Aufloesezeile) und
    ohne (elif-Zweig); seit B086/B088 heisst der Grund „Zeile n in <Blatt>;
    die Tabelle führt die Nummer 2 mehrfach; LK2 gab es schon“ statt
    „Tabellennummer 2; LK2 gab es schon“. Bis zum 23.09.2026 hielt das keine
    Pruefung (Befund B089): am Stand ec6448c bestand diese Suite 96/96 auch
    mit ``{herkunft}`` aus der Aufloesezeile gestrichen, dann hiess die Zeile
    nur „Kombination LK2_2: Verweise ['CO1'] ...“. Ebenso 96/96 ohne den Grund „LK2 gab es
    schon“ und mit einem elif-Zweig nur fuer Zeilen ohne Nummer (dann bekam
    LK2_2 = LF3 gar keine Zeile).
    """
    m, log = _kombinationstabelle("s3d_kn_", ["1;GZT;1.35*LF1", ";GZT;1.5*LF2",
                                              "2;GZT;1.0*EK1"], lastfaelle=2)
    check("A: die gewarnte LK2 steht nicht im Modell", "LK2" not in m.combinations,
          str({k: dict(c.factors) for k, c in m.combinations.items()}))
    frei = [k for k, c in m.combinations.items() if _gleich(dict(c.factors), {"LF2": 1.5})]
    z = next((z for z in log if frei and frei[0] in z and "ohne Nummer" in z), "keine Zeile")
    check("A: die Zeile ohne Nummer nennt ihren Namen im Modell", z != "keine Zeile",
          f"{frei} / {z}")

    m, log = _kombinationstabelle("s3d_kn_", [";GZT;1.5*LF2", "1;GZT;1.35*LF1 + CO2",
                                              "2;GZT;LF2"], lastfaelle=2)
    lk1 = dict(m.combinations["LK1"].factors) if "LK1" in m.combinations else {}
    check("B: LK1 ist die aufgeloeste Tabellenzeile 1",
          _gleich(lk1, {"LF1": 1.35, "LF2": 1.0}), str(lk1))
    check("B: kein Ausweichname LK1_2", "LK1_2" not in m.combinations,
          str(sorted(m.combinations)))
    frei = [k for k, c in m.combinations.items() if _gleich(dict(c.factors), {"LF2": 1.5})]
    z = next((z for z in log if frei and frei[0] in z and "ohne Nummer" in z), "keine Zeile")
    check("B: die Zeile ohne Nummer nennt ihren Namen im Modell", z != "keine Zeile",
          f"{frei} / {z}")
    check("B: alle drei Zeilen angelegt", "3 von 3 Lastkombinationen" in "\n".join(log))

    # C: doppelte Nummer 2, die zweite Zeile mit Verweis -> Aufloesezeile.
    # Seit B086/B088 nennt die Zeile statt „Tabellennummer 2“ ihre Zeile im
    # Blatt und die mehrfach gefuehrte Nummer (Kopfzeile + drei Zeilen: die
    # zweite Zeile 2 ist Zeile 4 der Datei).
    doppelt = "Zeile 4 in „2.5 Lastkombinationen“; die Tabelle führt die Nummer 2 mehrfach"
    m, log = _kombinationstabelle("s3d_kn_", ["1;GZT;LF1", "2;GZT;LF2", "2;GZT;LF3 + CO1"],
                                  lastfaelle=3)
    fk = {k: dict(c.factors) for k, c in m.combinations.items()}
    check("C: LK2 ist die erste Zeile 2, LK2_2 die aufgeloeste zweite",
          _gleich(fk.get("LK2", {}), {"LF2": 1.0})
          and _gleich(fk.get("LK2_2", {}), {"LF3": 1.0, "LF1": 1.0}), str(fk))
    z = next((z for z in log if "Verweise ['CO1']" in z), "keine Zeile")
    check("C: die Aufloesezeile nennt den Ausweichnamen samt Grund",
          z.startswith(f"Kombination LK2_2 ({doppelt}; LK2 gab es schon): "
                       "Verweise ['CO1']") and z.endswith(": 1*LF3 + 1*LF1"), z)

    # D: dieselbe Doppelung ohne Verweis -> eigene Zeile nur wegen des Ausweichnamens
    m, log = _kombinationstabelle("s3d_kn_", ["1;GZT;LF1", "2;GZT;LF2", "2;GZT;LF3"],
                                  lastfaelle=3)
    fk = {k: dict(c.factors) for k, c in m.combinations.items()}
    check("D: LK2_2 ist die zweite Zeile 2", _gleich(fk.get("LK2_2", {}), {"LF3": 1.0}),
          str(fk))
    z = next((z for z in log if "LK2_2" in z), "keine Zeile")
    check("D: die Zeile ohne Verweis nennt den Ausweichnamen samt Grund",
          z == f"Kombination LK2_2 ({doppelt}; LK2 gab es schon): 1*LF3", z)


def test_kombination_abhilfe():
    """Die Abhilfe, die Warnung und Handbuch zu einer nicht uebernommenen Kombination nennen, geht.

    Am Stand ec6448c endete die Warnung fuer jeden Grund mit „Bitte in RFEM
    nachsehen und die Kombination von Hand anlegen.“, und das Handbuch sagte
    „legen Sie sie dann in der Kombinationsmaske von Hand an“. Fuer einen
    Verweis auf eine Ergebniskombination geht das nicht: der Dialog
    (dialogs.CombinationDialog) uebernimmt Alternativen nur aus einer
    bestehenden Kombination, die Maske (gui/main.py, Art „kombination“) baut
    Combination ohne alternativen; kein anderer Weg der Oberflaeche legt
    welche an. Es bleibt, je Alternative eine eigene Kombination anzulegen.
    Nennt der nicht erkannte Teil einen Lastfall, den der Import nicht
    angelegt hat („Schnee“), bietet der Dialog nur die Felder LF1 und LF2 an
    (offscreen gemessen am 23.09.2026), und die Maske weist „Schnee: 1,5“ ab -
    dass er erst angelegt werden muss, sagte das Handbuch nicht. Die Klammer
    der nicht aufloesbaren Verweise nannte nur EK/RC und „eine Kombination,
    die selbst nicht angelegt wird“; Kreis und fehlende Nummer fehlten
    (Nebenbefunde der Fehlerrunden 22./23.09.2026, am Stand ec6448c
    nachgeprueft).
    """
    from tests import handbuch
    hb = handbuch.absatz("**Das Importprotokoll zählt ab")
    abhilfe = handbuch.absatz("**Eine nicht übernommene Kombination von Hand anlegen.**")

    def warnung(log, nr):
        return next((z for z in log if z.startswith("WARNUNG")
                     and (f"LK{nr} " in z or f"LK{nr}:" in z)), "keine Zeile")

    # (1) Verweis auf eine Ergebniskombination: eine Umhuellende, keine
    # Summe - als eine Kombination nicht anlegbar
    m, log = _kombinationstabelle("s3d_ka_", ["1;GZT;1.35*LF1 + EK1", "2;GZT;LF2 + RC1"],
                                  lastfaelle=2)
    for nr, ref in ((1, "EK1"), (2, "RC1")):
        z = warnung(log, nr)
        check(f"(1) {ref}: Warnung nennt je Alternative eine eigene Kombination",
              "je Alternative eine eigene Kombination" in z
              and "die Kombination von Hand anlegen" not in z, z)
    check("(1) keine der beiden Zeilen angelegt", not m.combinations, str(sorted(m.combinations)))
    check("(1) Handbuch: keine Umhüllende in der Maske, je Alternative eine Kombination",
          "keine Umhüllende" in abhilfe and "je Alternative eine eigene Kombination" in abhilfe
          and "legen Sie sie dann in der Kombinationsmaske von Hand an" not in hb,
          abhilfe[:200] or "Absatz fehlt")

    # (2) nicht erkannter Teil, der einen Lastfall nennt, den es nicht gibt
    m, log = _kombinationstabelle("s3d_ka_", ["1;GZT;1.35*LF1 + 1.5*Schnee", "2;GZT;CO1 + LF2"],
                                  lastfaelle=2)
    z = warnung(log, 1)
    check("(2) Gegenprobe: ohne EK/RC bleibt „die Kombination von Hand anlegen“",
          "die Kombination von Hand anlegen" in z and "je Alternative" not in z, z)
    check("(2) „Schnee“ steht im nicht erkannten Teil und ist kein Lastfall des Modells",
          "nicht erkannter Teil ['+ 1.5*Schnee']" in z and sorted(m.load_cases) == ["LF1", "LF2"],
          f"{sorted(m.load_cases)} / {z}")
    check("(2) Handbuch: diesen Lastfall zuerst anlegen",
          "„Schnee“" in abhilfe and "samt seinen Lasten zuerst an" in abhilfe,
          abhilfe[:200] or "Absatz fehlt")

    # (3) Jeder Grund, den der Import nennt (EK/RC und je CO/LK-Verweis der
    # aus _kombinationen_aufloesen), steht in der Klammer des Handbuchs.
    faelle = (
        (["1;GZT;LF1 + EK1"], "EK/RC ist eine Ergebniskombination",
         "Verweis auf eine Ergebniskombination"),
        (["1;GZT;LF1 + CO7"], "CO7: die Tabelle führt keine Nummer 7",
         "auf eine Nummer, die die Tabelle nicht führt"),
        (["1;GZT;1.35*LF1 + x", "2;GZT;CO1 + LF2"], "CO1: wird selbst nicht angelegt",
         "auf eine Kombination, die selbst nicht angelegt wird"),
        (["1;GZT;LF1 + CO2", "2;GZT;LF2 + CO1"],
         "CO2: Kreis, führt über Verweise auf diese Kombination zurück", "ein Kreis von Verweisen"),
        (["1;GZT;LF1 + CO1"], "CO1: Kreis, verweist auf diese Kombination selbst",
         "der Verweis einer Kombination auf sich selbst"),
    )
    for zeilen, grund, satz in faelle:
        m, log = _kombinationstabelle("s3d_ka_", zeilen, lastfaelle=2)
        txt = "\n".join(z for z in log if z.startswith("WARNUNG"))
        check(f"(3) gemessen „{grund[:34]}…“ steht im Handbuch",
              grund in txt and satz in hb,
              f"im Protokoll {grund in txt}, im Handbuch „{satz}“ {satz in hb}")


def _schlusszeile(log):
    return next((z for z in log if z.strip().endswith("Lastkombinationen")), "keine Zeile")


def test_kombination_plus_nur_verbindet():
    """Ein „+“ verbindet nur zwei Anteile; am Ende, am Anfang oder doppelt ist es ein Rest.

    Befund B085: ``luecke`` in ``_formel_zerlegen`` verwarf jedes Stueck, das
    nach Entfernen von Leerraum und „+“ leer war. Gemessen am Stand ec6448c:
    „1.35*LF1 + 1.5*LF2 +“ und „1.35*LF1 ++ 1.5*LF2“ wurden beide ohne
    Meldung 1,35·LF1 + 1,5·LF2 („2 von 2 Lastkombinationen“), „+ 1.35*LF1“
    wurde 1,35·LF1. Ein „-“ am Ende wurde schon als Rest gewarnt. Ein „+“ am
    Ende kann auf eine abgeschnittene Formel deuten; ob RFEM je eine
    schreibt, ist an keiner echten Datei gemessen.
    """
    m, log = _kombinationstabelle("s3d_kp_", ["1;GZT;1.35*LF1 + 1.5*LF2 +",
                                              "2;GZT;1.35*LF1 ++ 1.5*LF2",
                                              "3;GZT;+ 1.35*LF1"], lastfaelle=2)
    for nr, teil in ((1, "['+']"), (2, "['++']"), (3, "['+']")):
        check(f"LK{nr} mit überzähligem „+“ nicht angelegt", f"LK{nr}" not in m.combinations,
              str(dict(m.combinations[f"LK{nr}"].factors)) if f"LK{nr}" in m.combinations
              else "nicht angelegt")
        z = next((z for z in log if z.startswith("WARNUNG") and f"LK{nr} " in z),
                 "keine Zeile")
        check(f"LK{nr} gewarnt, Rest {teil} genannt", f"nicht erkannter Teil {teil}" in z, z)
    check("Schlusszeile „0 von 3 Lastkombinationen“",
          "0 von 3 Lastkombinationen" in "\n".join(log), _schlusszeile(log))

    # Gegenprobe: ein „+“ zwischen zwei Anteilen (auch ohne Leerzeichen und vor
    # einem negativen Faktor) und ein Minus am Anfang bleiben, wie sie waren.
    m, log = _kombinationstabelle("s3d_kp_", ["1;GZT;1.35*LF1 + 1.5*LF2",
                                              "2;GZT;1.35*LF1+1.5*LF2",
                                              "3;GZT;1.35*LF1 + -1.0*LF2",
                                              "4;GZT;-LF1 + LF2"], lastfaelle=2)
    for nr, soll in ((1, {"LF1": 1.35, "LF2": 1.5}), (2, {"LF1": 1.35, "LF2": 1.5}),
                     (3, {"LF1": 1.35, "LF2": -1.0}), (4, {"LF1": -1.0, "LF2": 1.0})):
        ist = dict(m.combinations[f"LK{nr}"].factors) if f"LK{nr}" in m.combinations else {}
        check(f"Gegenprobe: LK{nr} = {soll}", _gleich(ist, soll), str(ist))
    check("Gegenprobe: „4 von 4 Lastkombinationen“",
          "4 von 4 Lastkombinationen" in "\n".join(log), _schlusszeile(log))

    # Stichprobe statt Einzelfall: zufaellige gueltige Formeln (1-5 Anteile,
    # mit/ohne Faktor, Stern, Leerzeichen, negativ als „- LF“ oder „+ -LF“)
    # bleiben ohne Rest und richtig; dieselbe Formel mit einem „+“ mehr am
    # Anfang, am Ende oder neben einem vorhandenen „+“ hat einen Rest.
    # Gemessen am 23.09.2026 mit genau dieser Stichprobe: am Stand ec6448c
    # alle 500 gueltigen richtig, aber alle 500 mit „+“ zu viel ohne Rest;
    # mit der Regel 500/500 und 0 still.
    import random
    from statik3d.importers.rfem_tables import _formel_zerlegen
    rnd = random.Random(20260923)
    leer = ["", " ", "  "]
    falsch_gut, still = [], []
    for _ in range(500):
        k = rnd.randint(1, 5)
        soll, teile = {}, []
        for j in range(k):
            f = rnd.choice([None, 1.0, 1.35, 1.5, 0.9, 2.0])
            neg = rnd.random() < 0.3
            lf = rnd.randint(1, 9)
            soll[f"LF{lf}"] = soll.get(f"LF{lf}", 0.0) + (f or 1.0) * (-1 if neg else 1)
            zahl = "" if f is None else f"{f:g}" + rnd.choice(["*", " * ", " "])
            if j == 0:
                vor = ("-" + rnd.choice(leer)) if neg else ""
            elif neg:
                vor = rnd.choice(leer) + rnd.choice(["-" + rnd.choice(leer),
                                                     "+" + rnd.choice(leer) + "-"])
            else:
                vor = rnd.choice(leer) + "+" + rnd.choice(leer)
            teile.append(vor + zahl + rnd.choice(["LF", "LC", "lf"]) + str(lf))
        formel = "".join(teile)
        fac, ver, rest = _formel_zerlegen(formel)
        if rest or ver or not _gleich(fac, soll):
            falsch_gut.append((formel, fac, rest))
        mit_plus = [j for j in range(1, k) if "+" in teile[j]]
        wo = rnd.choice(["anfang", "ende"] + (["zwischen"] if mit_plus else []))
        if wo == "anfang":
            schlecht = "+" + rnd.choice(leer) + formel
        elif wo == "ende":
            schlecht = formel + rnd.choice(leer) + "+"
        else:
            j = rnd.choice(mit_plus)
            schlecht = "".join(teile[:j]) + rnd.choice(leer) + "+" + "".join(teile[j:])
        if not _formel_zerlegen(schlecht)[2]:
            still.append(schlecht)
    check("Stichprobe: 500 gültige Formeln ohne Rest und richtig", not falsch_gut,
          str(falsch_gut[:2]))
    check("Stichprobe: 500 Formeln mit einem „+“ zu viel haben einen Rest", not still,
          f"{len(still)} still, z. B. {still[:2]}")


def _ungeklaert(m, log):
    """Warnungen zu einem Namen, der zugleich ohne eigene Protokollzeile im Modell steht.

    Steht ein gewarnter Name (etwa LK2) auch im Modell, muss die Warnung ihre
    Zeile im Blatt nennen und die angelegte Kombination eine eigene Zeile
    haben - sonst liest der Anwender „LK2 nicht übernommen“ und findet LK2.
    """
    aus = []
    for z in log:
        mm = re.match(r"WARNUNG: Kombination (LK\d+)\b", z)
        if mm and mm.group(1) in m.combinations:
            name = mm.group(1)
            eigene = [x for x in log if x.startswith(f"Kombination {name} (")]
            if not eigene or "Zeile" not in z:
                aus.append(z)
    return aus


def test_kombination_doppelte_nummer():
    """Eine doppelt gefuehrte Tabellennummer loest keinen Verweis still auf.

    Befund B086: ``nach_nummer.setdefault`` in ``_kombinationen_aufloesen``
    liess einen Verweis immer auf die erste Zeile mit dieser Nummer zeigen,
    und die gewarnte und die angelegte Zeile trugen denselben Namen.
    Gemessen am Stand ec6448c:
    (a) ['2;GZT;LF1', '2;GZT;LF2 + CO2', ';GZT;LF1'] legte LK2_2 = LF2 + LF1
        an - der Verweis der Zeile auf ihre eigene Nummer ging still auf die
        andere Zeile, als Kreis galt er nicht;
    (b) ['2;GZT;LF1', '2;GZT;EK1'] legte LK2 = LF1 an und warnte
        „Kombination LK2 („EK1“) ... nicht uebernommen“;
    (c) ['1;GZT;1.35*LF1 + x', '1;GZT;LF2', '2;GZT;CO1'] warnte zu LK1, im
        Modell stand LK1 = LF2 ohne eigene Zeile, und LK2 meldete „CO1: wird
        selbst nicht angelegt, siehe Warnung zu LK1“.
    Ob RFEM doppelte Nummern schreibt, ist an keiner echten Datei gemessen.
    """
    grund2 = "CO2: die Tabelle führt die Nummer 2 mehrfach"
    # (a)
    m, log = _kombinationstabelle("s3d_kd_", ["2;GZT;LF1", "2;GZT;LF2 + CO2", ";GZT;LF1"])
    check("(a) kein still aufgeloestes LK2_2", "LK2_2" not in m.combinations,
          str({k: dict(c.factors) for k, c in m.combinations.items()}))
    z = next((z for z in log if z.startswith("WARNUNG") and "LF2 + CO2" in z), "keine Zeile")
    check("(a) die Zeile mit CO2 wird mit Grund gewarnt", grund2 in z, z)
    check("(a) ihre Warnung nennt die Zeile 3 des Blatts",
          "Zeile 3 in „2.5 Lastkombinationen“" in z, z)
    lk2 = dict(m.combinations["LK2"].factors) if "LK2" in m.combinations else {}
    check("(a) LK2 ist die Zeile 2 = LF1", _gleich(lk2, {"LF1": 1.0}), str(lk2))
    z = next((z for z in log if z.startswith("Kombination LK2 (")), "keine Zeile")
    check("(a) die angelegte LK2 hat eine eigene Zeile mit ihrer Zeile im Blatt",
          "Zeile 2 in „2.5 Lastkombinationen“" in z, z)
    check("(a) kein gewarnter Name unkommentiert im Modell", not _ungeklaert(m, log),
          str(_ungeklaert(m, log)))
    check("(a) Schlusszeile „2 von 3 Lastkombinationen“",
          "2 von 3 Lastkombinationen" in "\n".join(log), _schlusszeile(log))

    # (b)
    m, log = _kombinationstabelle("s3d_kd_", ["2;GZT;LF1", "2;GZT;EK1"])
    z = next((z for z in log if z.startswith("WARNUNG") and "EK1" in z), "keine Zeile")
    check("(b) die Warnung zu „EK1“ nennt die Zeile 3 des Blatts",
          "Zeile 3 in „2.5 Lastkombinationen“" in z, z)
    z = next((z for z in log if z.startswith("Kombination LK2 (")), "keine Zeile")
    check("(b) die angelegte LK2 = LF1 nennt die Zeile 2 des Blatts",
          "Zeile 2 in „2.5 Lastkombinationen“" in z and "1*LF1" in z, z)
    check("(b) kein gewarnter Name unkommentiert im Modell", not _ungeklaert(m, log),
          str(_ungeklaert(m, log)))

    # (c)
    m, log = _kombinationstabelle("s3d_kd_", ["1;GZT;1.35*LF1 + x", "1;GZT;LF2",
                                              "2;GZT;CO1"])
    lk1 = dict(m.combinations["LK1"].factors) if "LK1" in m.combinations else {}
    check("(c) LK1 = LF2 aus Zeile 3", _gleich(lk1, {"LF2": 1.0}), str(lk1))
    z = next((z for z in log if z.startswith("Kombination LK1 (")), "keine Zeile")
    check("(c) die angelegte LK1 hat eine eigene Zeile (Zeile 3)",
          "Zeile 3 in „2.5 Lastkombinationen“" in z, z)
    z = next((z for z in log if z.startswith("WARNUNG") and "1.35*LF1 + x" in z),
             "keine Zeile")
    check("(c) die Warnung zu „1.35*LF1 + x“ nennt die Zeile 2",
          "Zeile 2 in „2.5 Lastkombinationen“" in z, z)
    z = next((z for z in log if z.startswith("WARNUNG: Kombination LK2 ")), "keine Zeile")
    check("(c) LK2: CO1 zeigt auf eine mehrfach geführte Nummer",
          "CO1: die Tabelle führt die Nummer 1 mehrfach" in z
          and "wird selbst nicht angelegt" not in z, z)
    check("(c) kein gewarnter Name unkommentiert im Modell", not _ungeklaert(m, log),
          str(_ungeklaert(m, log)))

    # (d) beide Zeilen mit derselben Nummer werden angelegt: jede mit eigener Zeile
    m, log = _kombinationstabelle("s3d_kd_", ["2;GZT;LF1", "2;GZT;LF2"])
    z2 = next((z for z in log if z.startswith("Kombination LK2 (")), "keine Zeile")
    z22 = next((z for z in log if z.startswith("Kombination LK2_2 (")), "keine Zeile")
    check("(d) LK2 nennt Zeile 2, LK2_2 nennt Zeile 3",
          "Zeile 2 in „2.5 Lastkombinationen“" in z2
          and "Zeile 3 in „2.5 Lastkombinationen“" in z22, f"{z2} / {z22}")


def test_kombination_zeilennummer():
    """Die Meldung nennt die Zeile im Blatt bzw. in der CSV-Datei, Kopf- und Leerzeilen mitgezaehlt.

    Befund B088: die Zahl in „Tabellenzeile k“ zaehlte nur die nicht leeren
    Datenzeilen, weil ``Table.data`` Leerzeilen ueberspringt. Gemessen am
    Stand ec6448c mit ['1;GZT;1.35*LF1', ';;', ';;', ';GZT;1.5*LF2',
    ';GZT;Schnee'] (Kopfzeile = Zeile 1 der Datei): „Kombination LK2
    (Tabellenzeile 2 ohne Nummer): 1.5*LF2“ fuer Zeile 5 der Datei und
    „Kombination in Tabellenzeile 3 ohne Nummer: Formel „Schnee“ …“ fuer
    Zeile 6. Geprueft an CSV und an xlsx (dort mit einer Leerzeile ueber der
    Kopfzeile, damit die Zahl der Zeilennummer am Blattrand entspricht).
    """
    m, log = _kombinationstabelle("s3d_kz_", ["1;GZT;1.35*LF1", ";;", ";;",
                                              ";GZT;1.5*LF2", ";GZT;Schnee"], lastfaelle=2)
    z = next((z for z in log if z.startswith("Kombination LK2 (")), "keine Zeile")
    check("CSV: „1.5*LF2“ steht in Zeile 5 der Datei",
          "Zeile 5 in „2.5 Lastkombinationen“" in z, z)
    z = next((z for z in log if z.startswith("WARNUNG") and "Schnee" in z), "keine Zeile")
    check("CSV: „Schnee“ steht in Zeile 6 der Datei",
          "Zeile 6 in „2.5 Lastkombinationen“" in z, z)

    d = tempfile.mkdtemp(prefix="s3d_kz_")
    try:
        p = os.path.join(d, "kombi.xlsx")
        write_xlsx(p, {
            "1.1 Knoten": [["Knoten Nr.", "X [m]", "Y [m]", "Z [m]"], [1, 0, 0, 0], [2, 2, 0, 0]],
            "2.1 Lastfaelle": [["Lastfall Nr.", "Bezeichnung"], [1, "LF 1"], [2, "LF 2"]],
            "2.5 Lastkombinationen": [
                [],                                                   # Blattzeile 1
                ["Lastkombination Nr.", "Bemessungssituation", "Belastung"],   # 2
                [1, "GZT", "1.35*LF1"],                               # 3
                [],                                                   # 4
                [None, "GZT", "1.5*LF2"],                             # 5
                [None, "GZT", "Schnee"],                              # 6
            ]})
        log = []
        import_rfem_tables(p, Model("Kz"), log)
        z = next((z for z in log if z.startswith("Kombination LK2 (")), "keine Zeile")
        check("xlsx: „1.5*LF2“ steht in Blattzeile 5",
              "Zeile 5 in „2.5 Lastkombinationen“" in z, z)
        z = next((z for z in log if z.startswith("WARNUNG") and "Schnee" in z), "keine Zeile")
        check("xlsx: „Schnee“ steht in Blattzeile 6",
              "Zeile 6 in „2.5 Lastkombinationen“" in z, z)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_kombination_eigene_zeile():
    """Welche Zeile der Tabelle eine eigene Protokollzeile bekommt, wie Schnittstellen.md sie aufzaehlt.

    Schnittstellen.md, „Lastkombinationen aus der Tabelle zählen sich ab“:
    eine eigene Zeile bekommt jede nicht übernommene, jede aufgelöste, jede
    ohne Nummer, jede mit einer Nummer, die die Tabelle mehrfach führt, und
    jede mit Ausweichnamen; eine Zeile nur aus eigenen Lastfall-Anteilen
    unter ihrer nur einmal geführten Tabellennummer steht nur in der
    Schlusszeile. Gegenpruefung vom 24.09.2026: seit der Kur zu B086
    (e9aecb7) bekommt auch eine angelegte Zeile mit mehrfach gefuehrter
    Nummer ohne Verweis und ohne Ausweichnamen eine eigene Zeile
    (['2;GZT;LF1', '2;GZT;LF2'] -> „Kombination LK2 (Zeile 2 in
    „2.5 Lastkombinationen“; die Tabelle führt die Nummer 2 mehrfach):
    1*LF1“; am Stand ec6448c stand zu ihr keine Zeile), das Handbuch zaehlte
    sie aber nicht auf und nannte sie unter „steht nur in dieser Zählung“.
    Geprueft werden beide Haelften des Satzes.
    """
    d = tempfile.mkdtemp(prefix="s3d_ke_")
    try:
        def w(n, t):
            with open(os.path.join(d, n), "w", encoding="utf-8") as f:
                f.write(t)
        w("1.1 Knoten.csv", "Knoten Nr.;X [m];Y [m];Z [m]\n1;0;0;0\n2;2;0;0\n")
        w("2.1 Lastfaelle.csv", "Lastfall Nr.;Bezeichnung\n1;LF 1\n2;LF 2\n3;LF 3\n")
        w("2.5 Lastkombinationen.csv",
          "Lastkombination Nr.;Bemessungssituation;Belastung\n"
          "1;GZT;1.35*LF1\n"      # Zeile 2: eindeutige Nummer, nur eigene Anteile
          "2;GZT;LF1 + CO1\n"     # Zeile 3: aufgeloest
          ";GZT;1.5*LF2\n"        # Zeile 4: ohne Nummer -> LK7
          "3;GZT;LF1\n"           # Zeile 5: Nummer 3 mehrfach, unter LK3 angelegt
          "3;GZT;LF2\n"           # Zeile 6: Nummer 3 mehrfach, Ausweichname LK3_2
          "4;GZT;1.0*EK1\n"       # Zeile 7: nicht uebernommen
          "5;GZT;LF3\n"           # Zeile 8: LK5 gab es im Modell schon -> LK5_2
          "6;GZT;0.9*LF3\n")      # Zeile 9: eindeutige Nummer, nur eigene Anteile
        m = Model("Ke")
        m.add_combination("LK5", {"LF1": 1.0}, "ULS", "vorher")
        log = []
        m = import_rfem_tables(d, m, log)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    eigene = {}
    for z in log:
        mm = re.match(r"Kombination (LK\d+(?:_\d+)?)[ :]", z)
        if mm:
            eigene.setdefault(mm.group(1), []).append(z)
    angelegt = sorted(k for k in m.combinations if k != "LK5")
    check("sieben Zeilen angelegt", angelegt == ["LK1", "LK2", "LK3", "LK3_2", "LK5_2",
                                                "LK6", "LK7"], str(angelegt))
    for name, grund in (("LK2", "aufgelöst"), ("LK7", "ohne Nummer"),
                        ("LK3", "mehrfach"), ("LK3_2", "mehrfach"),
                        ("LK5_2", "gab es schon")):
        z = eigene.get(name, [])
        check(f"{name} hat genau eine eigene Zeile mit Ergebnis („{grund}“)",
              len(z) == 1 and grund in z[0] and "*LF" in z[0], str(z))
    for name in ("LK1", "LK6"):
        check(f"{name} (eindeutige Nummer, nur eigene Anteile) steht nur in der Zählung",
              name not in eigene, str(eigene.get(name)))
    z = next((z for z in log if z.startswith("WARNUNG: Kombination LK4 ")), "keine Zeile")
    check("LK4 wird mit Grund gewarnt", "Umhüllende" in z, z)
    check("Schlusszeile „7 von 8 Lastkombinationen“",
          "7 von 8 Lastkombinationen" in "\n".join(log), _schlusszeile(log))


def main():
    for t in (test_native_sqlite, test_native_zip_und_json, test_native_unbekannt,
              test_tabellen_erweitert, test_kombinationen_abgezaehlt,
              test_kombination_minus_vor_verweis, test_kombination_unerkannter_teil,
              test_kombination_verweis_auf_rest, test_kombination_rest_neben_verweis,
              test_kombination_vorsatz_zusatz, test_kombination_verweis_grund,
              test_kombination_ohne_nummer_name, test_kombination_abhilfe,
              test_kombination_plus_nur_verbindet, test_kombination_doppelte_nummer,
              test_kombination_zeilennummer, test_kombination_eigene_zeile):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    failed = [n for n, ok in RESULTS if not ok]
    if failed:
        print("FEHLGESCHLAGEN:", failed)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
