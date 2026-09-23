"""
Import von RFEM/RSTAB: native Projektdateien (.rf5/.rf6/.rs5/.rs6) und
erweiterter Tabellenexport mit Linien-/Flaechenlagern, Gelenken und
Nichtlinearitaeten.
Aufruf:  python -m tests.test_rfem
"""
import os
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
    """Jede Zeile der Tabelle „2.5 Lastkombinationen“ steht im Protokoll.

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
    fiel ohne Meldung weg, sobald daneben ein LF-Anteil stand. Gemessen am
    Stand 6cbc144: „1.35*LC1 + RC1“ wurde LK6 = {LF1: 1,35},
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
    check("LK8: der nicht erkannte Teil „Schnee“ wird genannt", "Schnee" in z8, z8)
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


def main():
    for t in (test_native_sqlite, test_native_zip_und_json, test_native_unbekannt,
              test_tabellen_erweitert, test_kombinationen_abgezaehlt,
              test_kombination_minus_vor_verweis, test_kombination_unerkannter_teil,
              test_kombination_ohne_nummer_name):
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
