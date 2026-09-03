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


def main():
    for t in (test_native_sqlite, test_native_zip_und_json, test_native_unbekannt,
              test_tabellen_erweitert):
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
