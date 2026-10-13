"""
Spannstahl und Schrauben an Staeben (Entscheidungen des Anwenders vom
13.10.2026).

Am Drehlager sind die 16 Ankerstaebe Rund 40 aus Spannstahl (RFEM Material 3,
Werkstofftyp 15: f_p0,1k 835, f_pk 1 030 N/mm²). Bis zum 13.10.2026 wies das
Programm sie wie Baustahl nach EN 1993-1-1 nach (N_t,Rd = A f_y). Jetzt:

* Spannstahl ist die Werkstoffart Material.art aus plast/verfestigung
  (f_p0,1k in fy, f_pk in fu); der RFEM-Import setzt sie fuer Typ 15 und
  uebernimmt E_p (gerechnet wird weiter mit E). In der Werkstoffmaske ist
  die Art waehlbar (Stahl, Schraube, Spannstahl); beim Oeffnen meldet das
  Protokoll Werkstoffe wie 835/1030 ohne Art, gesetzt wird nichts.
* Rechnet die kraftgesteuerte Vorspannung (vorspannung/kraft), gehen
  N_spannen und N_verankert aus res.info["vorspannung"]["staebe"] vor.
* Stab aus Spannstahl: sigma = N / A_s gegen
  - f_pd = f_p0,1k / 1,15 (EN 1992-1-1, 3.3.6 bzw. Zulassung) in jedem
    Lastzustand (GZT-Kombination, abgelegte Laststufe),
  - sigma_p,max = min(0,8 f_pk; 0,9 f_p0,1k) beim Spannen (5.10.2.1),
  - sigma_pm0 = min(0,75 f_pk; 0,85 f_p0,1k) nach dem Verankern (5.10.3);
  beide Grenzen sind am Werkstoff ueberschreibbar. Massgebend ist der
  unguenstigste Zustand.
* A_s am Querschnitt: Eingabe aus der Zulassung, „aufgewalzter Gewindestab"
  (A_s = Nennquerschnitt ohne Meldung) oder eine Schraubengroesse M12 … M36
  (A_s nach EN ISO 898-1, wie joints.bolts.SIZES); leer -> Nennquerschnitt
  mit der Meldung „A_s aus Zulassung eintragen“.
* Stab mit Schraubengroesse (nicht Spannstahl): Zug nach EN 1993-1-8,
  Tab. 3.4 mit A_s; die Steifigkeit bleibt beim Schaft.
* Ein Stahlstab ohne diese Angaben bleibt bitgleich beim bisherigen
  Nachweis (Bezugswerte gemessen an c379601, scratchpad sps_werk).
* Beim Import ein gebuendelter Hinweis zur Schraubenguete: runde Staebe
  bis Ø 36 mm an Volumen und ihre Schraubenkoerper aus einem Werkstoff mit
  f_y unter 640 N/mm²; umgestellt wird nichts.

Aufruf:  python -m tests.test_spannstahl
Die RFEM-Datei des Drehlagers (Import 3 bis 4 s) wird geprueft, wenn sie
unter Desktop/Statik3D/RFEM_Modelle/Lindaunis liegt oder
STATIK3D_DREHLAGER_RF6 auf sie zeigt.
"""
import json
import math
import os
import shutil
import sqlite3
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_spannstahl_"), "einstellungen.json")

RESULTS = []
_FENSTER = {}

#: Nennquerschnitt Rund 40 [m^2]
A_NENN = math.pi * 0.040 ** 2 / 4.0
#: Sollvorspannkraft je Anker am Drehlager nach Angabe des Anwenders [N]
F_SOLL = 944.7e3


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:84s} {detail}")
    return ok


def nah(a, b, rel=1e-9):
    try:
        return abs(float(a) - float(b)) <= rel * max(abs(float(b)), 1e-30)
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Modelle
# ---------------------------------------------------------------------------
def spannstahl(name="Spannstahl 835/1030", **kw):
    """Werkstoff wie am Drehlager (RFEM Material 3, DB 2309). Die Merkmale
    werden gesetzt, nicht uebergeben: so laeuft die Pruefung auch am alten
    Stand und schlaegt dort fehl, statt mit TypeError abzubrechen."""
    from statik3d.model import Material
    mat = Material(name, 170e9, 0.3, 7850.0, 1e-5, 835e6, 1030e6)
    for k, v in dict(art="Spannstahl", Ep=205e9, **kw).items():
        setattr(mat, k, v)
    return mat


def zugstab(mat, N=800e3, A_s=None, gewinde=None, typ="truss", quer=0.0):
    """Ein Stab Rund 40, 3,23 m, links eingespannt, rechts in x frei, mit der
    Zugkraft N am freien Ende (Kombination K1 = 1,0 · LF1)."""
    from statik3d.model import Model, Section
    m = Model("Zug")
    m.add_material(mat)
    sec = Section.circle("Rund 40", 0.040)
    if A_s is not None:
        sec.A_s = A_s
    if gewinde is not None:
        sec.gewinde = gewinde
    m.add_section(sec)
    a = m.add_node(0, 0, 0)
    b = m.add_node(3.23, 0, 0)
    m.add_element(typ, [a, b], mat.name, "Rund 40")
    m.fix(a, "all")
    m.fix(b, [1, 3, 4, 5] if typ == "beam" else [1, 2, 3, 4, 5])
    if typ == "beam":
        m.fix(b, [2])
    m.case().category = "G"
    m.load_node(b, Fx=N)
    if quer:
        m.load_beam(0, qz=-quer)
    m.add_member("A1", [0])
    m.add_combination("K1", {"LF1": 1.0}, "ULS")
    return m


def traeger():
    """Einfeldtraeger IPE 300 S235 wie in test_ec3 (_traeger_und_stab_ohne_fy)."""
    from statik3d.model import Model, Material
    from statik3d.profiles import make_section
    from statik3d import mesher
    m = Model()
    m.add_material(Material.steel("S235"))
    m.add_section(make_section("IPE 300"))
    ids = mesher.line_of_beams(m, "S235", "IPE 300", (0, 0, 0), (6, 0, 0), 6)
    m.fix(ids[0], [0, 1, 2, 3]); m.fix(ids[-1], [1, 2, 3])
    m.case().category = "G"
    for e in range(len(m.elements)):
        m.load_beam(e, qz=-10000.0)
    m.add_member("Traeger", list(range(6)))
    m.add_combination("K1", {"LF1": 1.0}, "ULS")
    return m


def nachweis(m):
    from statik3d import solver
    an = solver.solve_all(m, design=True)
    return an, an.design


# ---------------------------------------------------------------------------
# 1) Spannstahlstab mit bekanntem N: eta mit und ohne A_s
# ---------------------------------------------------------------------------
def test_eta_mit_und_ohne_As():
    N = 800e3
    fpd = 835e6 / 1.15
    # ohne A_s: Nennquerschnitt, Meldung
    an, d = nachweis(zugstab(spannstahl(), N=N))
    mc = d.members["A1"]
    soll = N / A_NENN / fpd
    print(f"     ohne A_s: util {float(mc.util)!r}, soll {soll!r}; massgebend {mc.governing.get('name')!r}")
    print(f"     Text: {mc.governing.get('text')!r}")
    check("ohne A_s: eta = N/(A_nenn) / (f_p0,1k/1,15) = 0,8768", nah(mc.util, soll), f"{float(mc.util):.6f}")
    name = str(mc.governing.get("name", ""))
    check("ohne A_s: massgebend nennt EN 1992-1-1, 3.3.6 bzw. Zulassung",
          "EN 1992-1-1" in name and "3.3.6" in name and "Zulassung" in name, name)
    check("ohne A_s: Vermerk „Nennquerschnitt“ im massgebenden Nachweis", "Nennquerschnitt" in name, name)
    check("ohne A_s: Meldung „A_s aus Zulassung eintragen“ am Stab",
          any("A_s aus Zulassung eintragen" in w for w in mc.warnings), str(mc.warnings))
    check("ohne A_s: Zusammenfassung meldet „A_s aus Zulassung eintragen“",
          "A_s aus Zulassung eintragen" in d.summary(), d.summary().replace("\n", " | "))
    zeile = d.table()[1]
    print(f"     Tabelle: {zeile}")
    check("Tabelle: Klasse „–“ statt Querschnittsklasse, Status erfüllt",
          zeile[4] == "–" and zeile[-1] == "erfüllt", str(zeile))
    # mit A_s aus der Zulassung
    an, d = nachweis(zugstab(spannstahl(), N=N, A_s=1150e-6))
    mc = d.members["A1"]
    soll = N / 1150e-6 / fpd
    print(f"     mit A_s 1150 mm²: util {float(mc.util)!r}, soll {soll!r}")
    check("mit A_s = 1150 mm²: eta = 0,9581", nah(mc.util, soll), f"{float(mc.util):.6f}")
    name = str(mc.governing.get("name", ""))
    check("mit A_s: Vermerk „A_s aus Eingabe“, keine Meldung",
          "A_s aus Eingabe" in name and not any("A_s aus Zulassung eintragen" in w for w in mc.warnings), name)
    # aufgewalzter Gewindestab: Nennquerschnitt ohne Meldung
    an, d = nachweis(zugstab(spannstahl(), N=N, gewinde="aufgewalzt"))
    mc = d.members["A1"]
    name = str(mc.governing.get("name", ""))
    check("aufgewalzter Gewindestab: eta mit Nennquerschnitt, Vermerk, keine Meldung",
          nah(mc.util, N / A_NENN / fpd) and "aufgewalzt" in name
          and not any("A_s aus Zulassung eintragen" in w for w in mc.warnings)
          and "A_s aus Zulassung eintragen" not in d.summary(), name)
    # Momente: als Balken mit Querlast - Biegung im Gewinde wird genannt, nicht nachgewiesen
    an, d = nachweis(zugstab(spannstahl(), N=N, typ="beam", quer=1000.0))
    mc = d.members["A1"]
    print(f"     Balken mit Querlast: {mc.warnings}")
    check("Momente im Spannstahlstab werden genannt („Biegung im Gewinde … nicht nachgewiesen“)",
          any("Biegung im Gewinde" in w and "M_y" in w for w in mc.warnings), str(mc.warnings))


# ---------------------------------------------------------------------------
# 2) Stahlstab bitgleich beim heutigen Nachweis
# ---------------------------------------------------------------------------
#: gemessen an c379601 (scratchpad sps_werk/ref_stahl.py, ref_stahl_basis.out)
BEZUG = {
    "Rund 40 S355, 300 kN": (0.6724856750361775, "N_t (6.2.3)", "N_Ed/N_t,Rd = 300.0/446.1 kN",
                             ['A1', 'Rund 40', 'S355', '3.23', '1', '0.672', 'N_t (6.2.3)', 'K1', '0.00',
                              'erfüllt']),
    "Rund 40 S355, 800 kN": (1.7932951334298068, "N_t (6.2.3)", "N_Ed/N_t,Rd = 800.0/446.1 kN",
                             ['A1', 'Rund 40', 'S355', '3.23', '1', '1.793', 'N_t (6.2.3)', 'K1', '0.00',
                              'NICHT erfüllt']),
    "IPE 300 S235": (0.6333413625603722, "Biegedrillknicken (6.3.2)",
                     "M_Ed/M_b,Rd = 45.0/71.1 kNm; M_cr = 102.4 kNm (C1 = 1.14, L_LT = 6.00 m), "
                     "lambda_LT = 1.201, Linie a, chi_LT = 0.529",
                     ['Traeger', 'IPE 300', 'S235', '6.00', '1', '0.633', 'Biegedrillknicken (6.3.2)', 'K1',
                      '0.00', 'erfüllt']),
}
ZUSAMMENFASSUNG = {
    "IPE 300 S235": "Nachweise EC3: 1 Stab, 1 Kombination, max. Ausnutzung 0.633 (Traeger: "
                    "Biegedrillknicken (6.3.2), K1, x = 0.00 m) - alle erfüllt",
}


def test_stahlstab_bitgleich():
    from statik3d.model import Material
    faelle = [("Rund 40 S355, 300 kN", zugstab(Material.steel("S355"), N=300e3)),
              ("Rund 40 S355, 300 kN", zugstab(Material.steel("S355"), N=300e3, A_s=1150e-6)),
              ("Rund 40 S355, 800 kN", zugstab(Material.steel("S355"), N=800e3, A_s=1150e-6,
                                               gewinde="aufgewalzt")),
              ("IPE 300 S235", traeger())]
    for i, (titel, m) in enumerate(faelle):
        an, d = nachweis(m)
        mc = next(iter(d.members.values()))
        util, gname, gtext, zeile = BEZUG[titel]
        zusatz = ["", " (A_s gesetzt)", " (A_s und „aufgewalzt“ gesetzt)", ""][i]
        check(f"Stahl bitgleich: {titel}{zusatz}: Ausnutzung {util!r}",
              float(mc.util) == util, repr(float(mc.util)))
        check(f"Stahl bitgleich: {titel}{zusatz}: massgebender Nachweis und Text",
              mc.governing.get("name") == gname and mc.governing.get("text") == gtext,
              f"{mc.governing.get('name')!r}")
        check(f"Stahl bitgleich: {titel}{zusatz}: Tabellenzeile", d.table()[1] == zeile, str(d.table()[1]))
        if titel in ZUSAMMENFASSUNG:
            check(f"Stahl bitgleich: {titel}: Zusammenfassung", d.summary() == ZUSAMMENFASSUNG[titel],
                  d.summary())


# ---------------------------------------------------------------------------
# 3) Import RFEM Werkstofftyp 15 setzt Spannstahl
# ---------------------------------------------------------------------------
def _rf6_spannstahl(pfad, typ=15):
    """RFEM-6-Datei mit einem Stab Rund 40 aus einem Werkstoff wie Material 3
    am Drehlager: Typ 15, E 170 000 (Datenbank), E_p 205 000 (eingegeben),
    f_p0,1k 835, f_p0,2k 835, f_pk 1 030 N/mm², ohne f_y/f_u."""
    from tests.test_rfem6 import build_db, INF
    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "model.db")
    build_db(db, nodes=[(0, 0, 0), (3.23, 0, 0)], lines=[[1, 2]],
             members=[(1, None, None, "MemberImplTension")],
             supports=[("Fest", (INF,) * 6, (0,) * 6, None, [1]),
                       ("Gleit", (0.0, INF, INF, INF, INF, INF), (0,) * 6, None, [2])])
    con = sqlite3.connect(db)
    con.execute("UPDATE MaterialImpl SET materialType=? WHERE id=1", (typ,))
    con.execute("UPDATE MaterialPropertyDouble SET valueSI=170e9 WHERE propertyKey='E'")
    con.execute("UPDATE MaterialPropertyDouble SET valueSI=1e-5 WHERE propertyKey='alpha'")
    # die Kennwerte am Parameterquerschnitt fuehrt RFEM mit (am Drehlager E 170 000)
    con.execute("UPDATE SectionMaterialCharacteristics SET modulusOfElasticity=170e9, "
                "compressiveStrength=835e6, tensileStrength=1030e6 WHERE id=1")
    # f_y/f_u (Dickenbereiche, Reihenfolge 6 und 7) gibt es beim Spannstahl nicht
    con.execute("DELETE FROM MaterialProperties_propertiesMap_keys WHERE id=1 AND container_order IN (6,7)")
    con.execute("DELETE FROM MaterialProperties_propertiesMap_values WHERE id=1 AND container_order IN (6,7)")
    for j, (k, v) in enumerate([("E_p", 205e9), ("f_p01k", 835e6), ("f_p02k", 835e6),
                                ("f_pk", 1030e6), ("epsilon_uk_prestressing", 0.045)]):
        rid = 100 + j
        con.execute("INSERT INTO MaterialPropertyDouble VALUES (?,1,?,?)", (rid, k, v))
        con.execute("INSERT INTO MaterialProperties_propertiesMap_keys VALUES (1,?,?)", (20 + j, k))
        con.execute("INSERT INTO MaterialProperties_propertiesMap_values VALUES (1,?,?,'MaterialPropertyDouble')",
                    (20 + j, rid))
    con.commit()
    con.close()
    with zipfile.ZipFile(pfad, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(db, "model.db")
        z.writestr("format.txt", "RFEM\n6.11.0004\nRFEM6\n6.12.0010\n1773229130\n")
        z.writestr("general_data.xml", "<?xml version='1.0'?><property key='generalData'/>")
    shutil.rmtree(tmp, ignore_errors=True)
    return pfad


def test_import_typ15():
    from statik3d.importers import rfem6_db as R6
    tmp = tempfile.mkdtemp()
    try:
        log = []
        m = R6.read_rf6(_rf6_spannstahl(os.path.join(tmp, "anker.rf6")), log=log)
        mat = list(m.materials.values())[0]
        print(f"     Werkstoff {mat.name!r}: art {getattr(mat, 'art', None)!r}, fy {mat.fy}, fu {mat.fu}, "
              f"E {mat.E}, Ep {getattr(mat, 'Ep', None)}")
        check("Import Typ 15: Werkstoffart Spannstahl", getattr(mat, "art", "") == "Spannstahl")
        check("Import Typ 15: f_p0,1k = 835 in f_y, f_pk = 1 030 in f_u, E_p = 205 000 N/mm² übernommen",
              mat.fy == 835e6 and mat.fu == 1030e6 and getattr(mat, "Ep", None) == 205e9)
        check("Import Typ 15: gerechnet wird weiter mit E = 170 000 (unverändert), f_y = f_p0,1k",
              mat.E == 170e9 and mat.fy == 835e6 and mat.fu == 1030e6, f"E {mat.E}")
        zeile = [z for z in log if "Spannstahl" in z and "E_p" in z]
        print(f"     Protokoll: {zeile}")
        check("Import Typ 15: das Protokoll nennt Spannstahl, f_p0,1k und E_p",
              bool(zeile) and "f_p0,1k" in zeile[0] and "E_p" in zeile[0], str(zeile[:1]))
        # Regel aus plast/verfestigung: auch ohne Typ 15 ist ein Werkstoff mit
        # f_p0,1k und ohne f_y Spannstahl
        m2 = R6.read_rf6(_rf6_spannstahl(os.path.join(tmp, "stahl.rf6"), typ=10), log=[])
        mat2 = list(m2.materials.values())[0]
        check("Werkstofftyp 10 mit f_p0,1k und ohne f_y: ebenfalls Spannstahl (Regel aus plast/verfestigung)",
              getattr(mat2, "art", "") == "Spannstahl", repr(getattr(mat2, "art", None)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    # der Baustahl der Grundprobe von test_rfem6 bleibt ohne Art
    from tests.test_rfem6 import make_rf6, INF
    tmp = tempfile.mkdtemp()
    try:
        f = make_rf6(os.path.join(tmp, "traeger.rf6"), nodes=[(0, 0, 0), (2, 0, 0)], lines=[[1, 2]],
                     members=[(1, None, None)],
                     supports=[("Fest", (INF,) * 6, (0,) * 6, None, [1])])
        mat = list(R6.read_rf6(f, log=[]).materials.values())[0]
        check("Gegenprobe: S355 (Typ 10) bleibt Baustahl (art leer)",
              hasattr(mat, "art") and mat.art == "" and getattr(mat, "Ep", 1) is None, repr(getattr(mat, "art", None)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# 4) Speichern und Laden: A_s, Gewinde, Werkstoffart und Spannungsgrenzen
# ---------------------------------------------------------------------------
def test_speichern_laden():
    from statik3d.model import Model
    m = zugstab(spannstahl(sigma_pmax=780e6), N=1.0, A_s=1150e-6)
    sec = m.sections["Rund 40"]
    pfad = os.path.join(tempfile.mkdtemp(), "anker.json")
    m.save(pfad)
    with open(pfad, encoding="utf-8") as f:
        d = json.load(f)
    s = d["sections"]["Rund 40"]
    w = d["materials"]["Spannstahl 835/1030"]
    print(f"     Datei: A_s {s.get('A_s')}, gewinde {s.get('gewinde')!r}; art {w.get('art')!r}, "
          f"Ep {w.get('Ep')}, "
          f"sigma_pmax {w.get('sigma_pmax')}, sigma_pm0 {w.get('sigma_pm0')}")
    check("Speichern: A_s steht in der Datei (SI, m²)", s.get("A_s") == 1150e-6, str(s.get("A_s")))
    m2 = Model.load(pfad)
    check("Laden: A_s = 1150 mm² wieder da", getattr(m2.sections["Rund 40"], "A_s", None) == 1150e-6)
    mat2 = m2.materials["Spannstahl 835/1030"]
    check("Laden: Werkstoffart, f_p0,1k/f_pk in f_y/f_u, E_p und σ_p,max-Eingabe wieder da",
          getattr(mat2, "art", "") == "Spannstahl" and mat2.fy == 835e6
          and mat2.fu == 1030e6 and getattr(mat2, "Ep", None) == 205e9
          and getattr(mat2, "sigma_pmax", None) == 780e6 and getattr(mat2, "sigma_pm0", 1) is None)
    sec.gewinde = "M20"
    m.save(pfad)
    check("Speichern/Laden: Schraubengröße M20 am Querschnitt",
          getattr(Model.load(pfad).sections["Rund 40"], "gewinde", "") == "M20")
    # alte Datei: die Felder fehlen - sie bleiben leer
    for k in ("A_s", "gewinde"):
        d["sections"]["Rund 40"].pop(k, None)
    for k in ("art", "verfestigung", "Ep", "sigma_pmax", "sigma_pm0"):
        d["materials"]["Spannstahl 835/1030"].pop(k, None)
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(d, f)
    m3 = Model.load(pfad)
    s3, w3 = m3.sections["Rund 40"], m3.materials["Spannstahl 835/1030"]
    check("alte Datei: A_s leer (None), Gewinde leer",
          hasattr(s3, "A_s") and s3.A_s is None and getattr(s3, "gewinde", None) == "")
    check("alte Datei: Werkstoffart leer (Baustahl), Kennwerte und Grenzen leer",
          hasattr(w3, "art") and w3.art == "" and w3.Ep is None
          and w3.sigma_pmax is None and w3.sigma_pm0 is None)


# ---------------------------------------------------------------------------
# 4b) Kennung der Ergebnisdatei: die neuen Felder auf ihrer Vorgabe aendern sie nicht
# ---------------------------------------------------------------------------
#: ergebnisse.rechenkennung an c379601 (scratchpad sps_werk/kennung_ref.py, kennung_basis.out)
KENNUNG_BASIS = {
    "traeger": {"werkstoffe": "97e837654cd6f9f4e88de4c8a60b5cee", "querschnitte": "d4474a556de133c7aa23bd0adfef15b9"},
    "zugstab": {"werkstoffe": "864f56aff04787152736363e83f2fe76", "querschnitte": "d7f7c34650e7f1bda4fbc14c71a958e5"},
}


def _kennungsmodell_zug():
    """Wie kennung_ref.zugstab: Werkstoff ohne Art, Rund 40, eine Kraft."""
    from statik3d.model import Model, Material, Section
    m = Model("Zug")
    m.add_material(Material("Spannstahl 835/1030", 170e9, 0.3, 7850.0, 1e-5, 835e6, 1030e6))
    m.add_section(Section.circle("Rund 40", 0.040))
    a = m.add_node(0, 0, 0)
    b = m.add_node(3.23, 0, 0)
    m.add_element("truss", [a, b], "Spannstahl 835/1030", "Rund 40")
    m.fix(a, "all")
    m.load_node(b, Fx=800e3)
    m.add_member("A1", [0])
    return m


def test_kennung_unveraendert():
    """Bis zur Nachbesserung (13.10.2026) machten die neuen Felder jede
    gespeicherte Ergebnisdatei ungueltig: am Drehlager-Lauf vom 09.10.2026
    „Die Ergebnisdatei passt nicht zum Modell: seit der Rechnung geändert:
    Werkstoffe, Querschnitte und Dicken“."""
    from statik3d import ergebnisse
    for name, m in (("traeger", traeger()), ("zugstab", _kennungsmodell_zug())):
        g, _e = ergebnisse.rechenkennung(m)
        for gruppe in ("werkstoffe", "querschnitte"):
            check(f"Kennung {name}/{gruppe} wie an c379601 (neue Felder auf Vorgabe zählen nicht)",
                  g[gruppe] == KENNUNG_BASIS[name][gruppe], g[gruppe])
    m = _kennungsmodell_zug()
    g0, _e = ergebnisse.rechenkennung(m)
    m.materials["Spannstahl 835/1030"].art = "Spannstahl"
    g1, _e = ergebnisse.rechenkennung(m)
    m.sections["Rund 40"].A_s = 1150e-6
    g2, _e = ergebnisse.rechenkennung(m)
    check("gesetzt zählen sie: Werkstoffart ändert die Gruppe Werkstoffe, A_s die Gruppe Querschnitte",
          g1["werkstoffe"] != g0["werkstoffe"] and g2["querschnitte"] != g1["querschnitte"])


# ---------------------------------------------------------------------------
# 5) Spannungsgrenzen beim Spannen und nach dem Verankern
# ---------------------------------------------------------------------------
def test_spannungsgrenzen():
    try:
        from statik3d.ec3 import spannstahl as sp
    except ImportError as ex:
        check("Modul ec3.spannstahl", False, str(ex))
        return
    mat = spannstahl()
    pmax, herk1 = sp.sigma_p_max(mat)
    pm0, herk2 = sp.sigma_pm0(mat)
    print(f"     σ_p,max {pmax / 1e6} ({herk1}), σ_pm0 {pm0 / 1e6} ({herk2})")
    check("σ_p,max = min(0,8·1030; 0,9·835) = 751,5 N/mm² (EN 1992-1-1, 5.10.2.1)", nah(pmax, 751.5e6))
    check("σ_pm0 = min(0,75·1030; 0,85·835) = 709,75 N/mm² (EN 1992-1-1, 5.10.3)", nah(pm0, 709.75e6))
    mat2 = spannstahl(sigma_pmax=780e6, sigma_pm0=700e6)
    p2, h2 = sp.sigma_p_max(mat2)
    q2, g2 = sp.sigma_pm0(mat2)
    check("Eingabe am Werkstoff überschreibt beide Grenzen (Zulassung)",
          p2 == 780e6 and q2 == 700e6 and "Eingabe" in h2 and "Eingabe" in g2, f"{h2} / {g2}")


# ---------------------------------------------------------------------------
# 6) Zustaende: Spannen, nach dem Verankern, Lastzustand
# ---------------------------------------------------------------------------
def anker(F_v=F_SOLL, als_temperatur=False, dT_last=20.0):
    """Anker Rund 40, beidseitig fest: die Vorspannung F_v bleibt voll im
    Stab (N = F_v). LF_V traegt nur die Vorspannung (Kategorie P), LF_T
    erwaermt den Stab um dT_last (der Anker verliert E A alpha dT), K1 = LF_V
    + LF_T im GZT."""
    from statik3d.model import Model, Section, Vorspannung, TempLoad
    m = Model("Anker")
    mat = spannstahl()
    m.add_material(mat)
    m.add_section(Section.circle("Rund 40", 0.040))
    a = m.add_node(0, 0, 0)
    b = m.add_node(3.23, 0, 0)
    m.add_element("truss", [a, b], mat.name, "Rund 40")
    m.fix(a, "all")
    m.fix(b, "all")
    m.add_member("A1", [0])
    lv = m.add_load_case("LF_V", category="P") if hasattr(m, "add_load_case") else None
    if lv is None:
        from statik3d.model import LoadCase
        m.load_cases["LF_V"] = LoadCase("LF_V", category="P")
        lv = m.load_cases["LF_V"]
    if als_temperatur:
        dT = -F_v / (mat.E * A_NENN * mat.alpha)
        lv.temp_loads.append(TempLoad(0, dT))
    else:
        lv.vorspannungen.append(Vorspannung(ziel="A1", art="stab", kraft=F_v))
    from statik3d.model import LoadCase
    m.load_cases["LF_T"] = LoadCase("LF_T", category="T")
    m.load_cases["LF_T"].temp_loads.append(TempLoad(0, dT_last))
    m.load_cases.pop("LF1", None)
    m.active_case = "LF_V"
    m.add_combination("K1", {"LF_V": 1.0, "LF_T": 1.0}, "ULS")
    return m


def test_zustaende():
    for als_t in (False, True):
        quelle = "Temperaturlast (RFEM-Import)" if als_t else "Vorspannung"
        m = anker(als_temperatur=als_t)
        an, d = nachweis(m)
        mc = d.members["A1"]
        N_v = float(an.cases["LF_V"].member_forces(m.members["A1"], 3)["N"].max())
        print(f"     [{quelle}] N(LF_V) = {N_v / 1e3:.3f} kN; util {float(mc.util):.5f}; "
              f"massgebend {mc.governing.get('name')!r} / {mc.governing.get('combo')!r}")
        zst = getattr(mc, "zustaende", None) or []
        for z in zst:
            print(f"        {z.get('zustand')!s:22s} {z.get('quelle')!s:46s} N {z.get('N', 0) / 1e3:8.1f} kN  "
                  f"σ {z.get('sigma', 0) / 1e6:7.2f}  Grenze {z.get('grenzname')} {z.get('grenze', 0) / 1e6:7.2f}"
                  f"  η {z.get('util', 0):.4f}")
        sigma = F_SOLL / A_NENN
        check(f"[{quelle}] reiner Vorspannlastfall: N = F_v = 944,7 kN (beidseitig fest)",
              nah(N_v, F_SOLL, 1e-6), f"{N_v / 1e3:.3f} kN")
        sp = [z for z in zst if z.get("zustand") == "Spannen"]
        ve = [z for z in zst if z.get("zustand") == "nach dem Verankern"]
        gz = [z for z in zst if z.get("zustand") == "Lastzustand"]
        check(f"[{quelle}] Spannen: σ = 751,8 N/mm² gegen σ_p,max 751,5 → η = 1,0004",
              bool(sp) and nah(sp[0]["sigma"], sigma, 1e-6) and nah(sp[0]["util"], sigma / 751.5e6, 1e-6),
              f"{sp[0]['util']:.5f}" if sp else "fehlt")
        check(f"[{quelle}] nach dem Verankern: Ergebnis LF_V gegen σ_pm0 709,75 → η = 1,059",
              bool(ve) and nah(ve[0]["util"], sigma / 709.75e6, 1e-5) and "LF_V" in str(ve[0].get("quelle")),
              f"{ve[0]['util']:.5f} ({ve[0].get('quelle')})" if ve else "fehlt")
        N_k1 = F_SOLL - 170e9 * A_NENN * 1e-5 * 20.0
        check(f"[{quelle}] Lastzustand K1 gegen f_pd: N = 944,7 − EAαΔT = 902,0 kN, η = 0,9886",
              bool(gz) and nah(gz[0]["util"], N_k1 / A_NENN / (835e6 / 1.15), 1e-5),
              f"{gz[0]['util']:.5f}" if gz else "fehlt")
        check(f"[{quelle}] massgebend ist der ungünstigste Zustand: nach dem Verankern (σ_pm0)",
              nah(mc.util, sigma / 709.75e6, 1e-5) and "σ_pm0" in str(mc.governing.get("name"))
              and mc.status() == "NICHT erfüllt", f"{float(mc.util):.5f}")
    # Schnittstelle fuer den kuenftigen Spannschritt: res.info["zustand"]
    from statik3d import solver
    from statik3d.ec3.design import check_members
    m = anker()
    an = solver.solve_all(m, design=False)
    # verteilt (Auftraege ueber die Paketdatei): dieselben Zustaende
    d_seq = check_members(m, an, use_jobs=False)
    d_par = check_members(m, an, use_jobs=True, workers=2)
    a, b = d_seq.members["A1"], d_par.members["A1"]
    check("verteilt wie nacheinander: Ausnutzung und Zustände gleich (Vorspannzustände im Paket)",
          float(a.util) == float(b.util) and [z["quelle"] for z in a.zustaende] == [z["quelle"] for z in b.zustaende],
          f"{float(a.util):.5f} / {float(b.util):.5f}, {len(b.zustaende)} Zustände")
    import copy
    r = copy.copy(an.cases["LF_V"])
    r.info = dict(r.info, zustand="spannen")
    r.name = "Spannschritt 1"
    an.cases["Spannschritt 1"] = r
    d = check_members(m, an, use_jobs=False)
    zst = getattr(d.members["A1"], "zustaende", None) or []
    sp = [z for z in zst if z.get("zustand") == "Spannen" and "Spannschritt 1" in str(z.get("quelle"))]
    check("Schnittstelle: ein Ergebnis mit info['zustand'] = 'spannen' wird gegen σ_p,max geprüft",
          bool(sp) and nah(sp[0]["grenze"], 751.5e6), str([z.get("quelle") for z in zst]))
    # Laststufen der Plastizitaet: abgelegt -> jede Stufe; sonst Endzustand mit Vermerk
    an = solver.solve_all(m, design=False)
    k1 = an.combinations["K1"]
    k1.info = dict(k1.info, plastizitaet={"an": True})
    d = check_members(m, an, use_jobs=False)
    mc = d.members["A1"]
    check("Plastizität ohne abgelegte Laststufen: Endzustand mit Vermerk",
          any("Laststufen" in w and "Endzustand" in w for w in mc.warnings), str(mc.warnings))
    stufe = copy.copy(an.cases["LF_V"])
    stufe.info = dict(stufe.info, lam=0.5)
    k1.info = dict(k1.info, laststufen=[stufe])
    d = check_members(m, an, use_jobs=False)
    zst = getattr(d.members["A1"], "zustaende", None) or []
    st = [z for z in zst if "Laststufe" in str(z.get("quelle"))]
    check("abgelegte Laststufe wird gegen f_pd geprüft (Stufe 1, λ = 0,5)",
          bool(st) and nah(st[0]["grenze"], 835e6 / 1.15) and "0.5" in str(st[0].get("quelle")),
          str([z.get("quelle") for z in zst]))


def test_ladehinweis():
    """Beim Oeffnen: ein Werkstoff wie 835/1030 ohne Art wird gemeldet,
    gesetzt wird nichts (Drehlager vor dem 13.10.2026 importiert)."""
    from statik3d.model import Model, Material
    m = Model("Laden")
    m.add_material(Material("Material 3 (DB 2309)", 170e9, 0.3, 7850.0, 1e-5, 835e6, 1030e6))
    m.add_material(Material("Spannstahl gesetzt", 170e9, 0.3, 7850.0, 1e-5, 835e6, 1030e6, art="Spannstahl"))
    m.add_material(Material("Schraube 10.9", 210e9, 0.3, 7850.0, 1.2e-5, 900e6, 1000e6))
    m.add_material(Material.steel("S355"))
    pfad = os.path.join(tempfile.mkdtemp(), "laden.json")
    m.save(pfad)
    m2 = Model.load(pfad)
    z = [s for s in getattr(m2, "_ladehinweise", []) if "Spannstahl" in s]
    print(f"     Ladehinweise: {z}")
    check("Oeffnen: „Material 3 (DB 2309)“ 835/1030 ohne Art wird gemeldet, die anderen nicht",
          len(z) == 1 and "Material 3 (DB 2309)" in z[0] and "gesetzt wurde nichts" in z[0], str(z))
    check("Oeffnen: die Art bleibt leer (nichts automatisch gesetzt)", m2.materials["Material 3 (DB 2309)"].art == "")


def test_vorspannkraft_schnittstelle():
    """vorspannung/kraft legt je Stab N_spannen und N_verankert in
    res.info["vorspannung"]["staebe"] ab - sie gehen vor die eingegebene Kraft
    und vor das Ergebnis des Lastfalls."""
    from statik3d import solver
    from statik3d.ec3.design import check_members
    m = anker()
    an = solver.solve_all(m, design=False)
    an.cases["LF_V"].info = dict(an.cases["LF_V"].info, vorspannung={
        "weg": "spannen", "staebe": {"A1": {"F_soll": F_SOLL, "gruppe": 1, "N_spannen": F_SOLL,
                                            "N_verankert": 900e3, "verlust": F_SOLL - 900e3, "N_ende": 880e3}}})
    d = check_members(m, an, use_jobs=False)
    zst = d.members["A1"].zustaende
    for z in zst:
        print(f"        {z['zustand']:20s} {z['quelle']:55s} N {z['N'] / 1e3:7.1f} kN  η {z['util']:.4f}")
    sp_ = [z for z in zst if z["zustand"] == "Spannen" and "N_spannen" in z["quelle"]]
    ve = [z for z in zst if z["zustand"] == "nach dem Verankern"]
    check("N_spannen = 944,7 kN gegen σ_p,max: η = 1,0004",
          bool(sp_) and nah(sp_[0]["util"], F_SOLL / A_NENN / 751.5e6, 1e-6), str([z["quelle"] for z in zst]))
    check("nach dem Verankern nur aus N_verankert = 900 kN: η = 900/1 256,6/709,75 = 1,0091",
          len(ve) == 1 and "N_verankert" in ve[0]["quelle"] and nah(ve[0]["util"], 900e3 / A_NENN / 709.75e6, 1e-6),
          str([z["quelle"] for z in ve]))


# ---------------------------------------------------------------------------
# 7) Schraube M20: Zug nach EN 1993-1-8 mit A_s, Steifigkeit am Schaft
# ---------------------------------------------------------------------------
def test_schraube_m20():
    from statik3d.model import Material
    acht = Material("Schraube 8.8", 210e9, 0.3, 7850.0, 1.2e-5, 640e6, 800e6)
    N = 100e3
    an, d = nachweis(zugstab(acht, N=N, gewinde="M20"))
    mc = d.members["A1"]
    FtRd = 0.9 * 800e6 * 245e-6 / 1.25
    print(f"     M20 8.8: util {float(mc.util)!r}, soll {N / FtRd!r}; {mc.governing.get('name')!r}; "
          f"{mc.governing.get('text')!r}")
    check("M20, f_ub 800: η = N / (0,9 f_ub A_s / γ_M2) = 100 / 141,12 = 0,7086 (EN 1993-1-8, Tab. 3.4)",
          nah(mc.util, N / FtRd), f"{float(mc.util):.5f}")
    name = str(mc.governing.get("name", ""))
    check("M20: massgebender Nachweis nennt EN 1993-1-8 und A_s = 245 mm²",
          "1993-1-8" in name and "245" in str(mc.governing.get("text")), name)
    an0, _d0 = nachweis(zugstab(acht, N=N))
    u = float(an.cases["LF1"].u[1][0])
    u0 = float(an0.cases["LF1"].u[1][0])
    check("M20: die Steifigkeit bleibt beim Schaft (u_x gleich wie ohne Schraubengröße)",
          u == u0, f"{u * 1e3:.6f} mm / {u0 * 1e3:.6f} mm")
    try:
        from statik3d.ec3 import spannstahl as sp
        from statik3d.model import Section
        s = Section.circle("Rund 16", 0.016)
        s.gewinde = "M16"
        A, vermerk, meldung = sp.spannungsquerschnitt(s)
        check("Schraubengröße M16: A_s = 157 mm² (EN ISO 898-1), ohne Meldung",
              nah(A, 157e-6) and not meldung and "M16" in vermerk, vermerk)
    except ImportError as ex:
        check("Schraubengröße M16: A_s = 157 mm²", False, str(ex))


# ---------------------------------------------------------------------------
# 8) Bericht: Zustaende, Normstellen und Vermerk A_s
# ---------------------------------------------------------------------------
def test_bericht():
    from statik3d.report import Report
    m = anker()
    an, d = nachweis(m)
    html = Report(m, an).html()
    for teil in ("EN 1992-1-1", "3.3.6", "5.10.2.1", "5.10.3", "σ_p,max", "σ_pm0", "f_pd",
                 "Spannen", "nach dem Verankern", "Lastzustand", "Nennquerschnitt", "A_s aus Zulassung eintragen"):
        check(f"Bericht nennt „{teil}“", teil in html)
    check("Bericht: Kapitelhinweis „Stäbe aus Spannstahl … nicht nach EN 1993-1-1“",
          "aus Spannstahl" in html and "nicht nach EN 1993-1-1" in html)


# ---------------------------------------------------------------------------
# 9) Masken: Werkstoffart, Spannungsgrenzen, A_s mit Einheit, Gewinde
# ---------------------------------------------------------------------------
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


def _maskeninhalt(w, app, art, name):
    """(Feldnamen, leer erlaubte Felder, Hinweise, Beschriftungen, Auswahllisten, werte())
    der Objektmaske rechts."""
    from PySide6 import QtWidgets
    w._objektmaske(art, name)
    app.processEvents()
    mk = w.maskenrand.maske
    if mk is None:
        return set(), set(), {}, [], {}, {}
    wahl = {k: [v.itemText(i) for i in range(v.count())] for k, v in mk._felder.items()
            if isinstance(v, QtWidgets.QComboBox)}
    texte = [l.text() for l in mk.findChildren(QtWidgets.QLabel)]
    return set(mk._felder), set(mk._leer_erlaubt), dict(mk._hinweise), texte, wahl, mk.werte()


def test_masken():
    w, app = _fenster()
    w.model = zugstab(spannstahl(), N=800e3)
    w.refresh_all()
    app.processEvents()
    namen, leer, hinweise, texte, wahl, werte = _maskeninhalt(w, app, "querschnitt", "Rund 40")
    print(f"     Querschnittsmaske: {sorted(namen)}")
    check("Querschnittsmaske: Feld A_s mit Einheit mm², leer zulässig (leer = Nennquerschnitt)",
          "A_s" in namen and "A_s" in leer and any("A_s" in t and "[mm²]" in t for t in texte)
          and werte.get("A_s") == "", str([t for t in texte if "A_s" in t]))
    g = wahl.get("gewinde") or []
    check("Querschnittsmaske: Auswahl „aufgewalzter Gewindestab“ und Schraubengrößen M12 … M36",
          any("aufgewalzt" in x for x in g) and "M12" in g and "M36" in g and "M16" in g, str(g))
    # Uebernehmen: A_s 1150 mm²
    w._eigenschaften_uebernehmen("querschnitt", "Rund 40", {"name": "Rund 40", "A_s": "1150"})
    s = w.model.sections["Rund 40"]
    check("Übernehmen: A_s = 1150 mm² am Querschnitt (SI 1,15e-3 m²), A unverändert",
          nah(getattr(s, "A_s", 0), 1150e-6) and nah(s.A, A_NENN), f"A_s {getattr(s, 'A_s', None)}")
    w._eigenschaften_uebernehmen("querschnitt", "Rund 40", {"name": "Rund 40", "A_s": "", "gewinde": "M20"})
    s = w.model.sections["Rund 40"]
    check("Übernehmen: Schraubengröße M20 setzt A_s = 245 mm², A bleibt Schaft",
          getattr(s, "gewinde", "") == "M20" and nah(getattr(s, "A_s", 0), 245e-6) and nah(s.A, A_NENN),
          f"A_s {getattr(s, 'A_s', None)}")
    aufgew = next((x for x in g if "aufgewalzt" in x), "aufgewalzter Gewindestab (A_s = Nennquerschnitt)")
    w._eigenschaften_uebernehmen("querschnitt", "Rund 40", {"name": "Rund 40", "A_s": "", "gewinde": aufgew})
    s = w.model.sections["Rund 40"]
    check("Übernehmen: aufgewalzter Gewindestab - A_s leer, Merkmal gesetzt",
          getattr(s, "gewinde", "") == "aufgewalzt" and getattr(s, "A_s", 1) is None)
    # Werkstoffmaske
    namen, leer, hinweise, texte, wahl, werte = _maskeninhalt(w, app, "werkstoff", "Spannstahl 835/1030")
    print(f"     Werkstoffmaske: {sorted(namen)}")
    check("Werkstoffmaske: Werkstoffart wählbar (Stahl, Schraube, Spannstahl), σ_p,max und σ_pm0",
          all(k in namen for k in ("art", "sigma_pmax", "sigma_pm0"))
          and (wahl.get("art") or []) == ["Stahl", "Schraube", "Spannstahl"]
          and werte.get("art") == "Spannstahl", str(wahl.get("art")))
    check("Werkstoffmaske: f_y heißt beim Spannstahl f_p0,1k, f_u heißt f_pk (plast/verfestigung)",
          any("f_p0,1k [N/mm²]" in t for t in texte) and any("f_pk [N/mm²]" in t for t in texte))
    check("Werkstoffmaske: σ_p,max leer = Vorgabe nach Formel (Hinweis nennt 751,5)",
          werte.get("sigma_pmax") == "" and "sigma_pmax" in leer and "751" in hinweise.get("sigma_pmax", ""),
          hinweise.get("sigma_pmax", ""))
    w._eigenschaften_uebernehmen("werkstoff", "Spannstahl 835/1030", {
        "name": "Spannstahl 835/1030", "E": "170", "nu": "0.3", "rho": "7850", "alpha": "10",
        "fy": "835", "fu": "1030", "grade": "", "art": "Spannstahl",
        "sigma_pmax": "780", "sigma_pm0": ""})
    mt = w.model.materials["Spannstahl 835/1030"]
    check("Übernehmen Werkstoff: Art, σ_p,max-Eingabe; E_p aus dem Import bleibt",
          getattr(mt, "art", "") == "Spannstahl" and getattr(mt, "sigma_pmax", None) == 780e6
          and getattr(mt, "sigma_pm0", 1) is None and mt.fu == 1030e6
          and getattr(mt, "Ep", None) == 205e9, f"{getattr(mt, 'art', None)!r}")
    # die Maske ohne die neuen Felder (Attrappen in test_fehler_p10) aendert die Art nicht
    w._eigenschaften_uebernehmen("werkstoff", "Spannstahl 835/1030", {
        "name": "Spannstahl 835/1030", "E": "170", "nu": "0.3", "rho": "7850", "alpha": "10",
        "fy": "835", "fu": "1030", "grade": ""})
    mt = w.model.materials["Spannstahl 835/1030"]
    check("Übernehmen ohne die neuen Felder: Art und Kennwerte bleiben",
          getattr(mt, "art", "") == "Spannstahl" and getattr(mt, "Ep", None) == 205e9
          and getattr(mt, "sigma_pmax", None) == 780e6)
    # Art umstellen: die gespeicherte Drehlager-Datei traegt keine Art
    for wahl_text, art in (("Stahl", ""), ("Schraube", "Schraube"), ("Spannstahl", "Spannstahl")):
        w._eigenschaften_uebernehmen("werkstoff", "Spannstahl 835/1030", {
            "name": "Spannstahl 835/1030", "E": "170", "nu": "0.3", "rho": "7850", "alpha": "10",
            "fy": "835", "fu": "1030", "grade": "", "art": wahl_text})
        check(f"Werkstoffart „{wahl_text}“ wählen setzt Material.art = {art!r}",
              w.model.materials["Spannstahl 835/1030"].art == art)


# ---------------------------------------------------------------------------
# 10) Hinweis zur Schraubenguete beim Import
# ---------------------------------------------------------------------------
def _quader(m, name, x0, y0, z0, a, b, c, material):
    """Quader aus sechs Vierecken (Kanten parallel zu den Achsen)."""
    E = [(0, 0), (a, 0), (a, b), (0, b)]
    ku = [m.add_node(x0 + x, y0 + y, z0) for x, y in E]
    ko = [m.add_node(x0 + x, y0 + y, z0 + c) for x, y in E]
    for i in range(4):
        j = (i + 1) % 4
        m.add_line(f"{name}U{i}", [ku[i], ku[j]])
        m.add_line(f"{name}O{i}", [ko[i], ko[j]])
        m.add_line(f"{name}V{i}", [ku[i], ko[i]])
    m.add_flaeche(f"{name}_Boden", [f"{name}U{i}" for i in range(4)], material=material)
    m.add_flaeche(f"{name}_Deckel", [f"{name}O{i}" for i in range(4)], material=material)
    seiten = []
    for i in range(4):
        j = (i + 1) % 4
        nm = f"{name}_S{i}"
        m.add_flaeche(nm, [f"{name}U{i}", f"{name}V{j}", f"{name}O{i}", f"{name}V{i}"], material=material)
        seiten.append(nm)
    m.add_koerper(name, [f"{name}_Boden", f"{name}_Deckel"] + seiten, material=material)
    return m.flaechen[f"{name}_Deckel"]


def schraubenmodell(stab_fy=355e6, koerper_fy=355e6, d_stab=0.016, platte=False):
    """Zwei Schrauben wie am Drehlager: je ein Schraubenkoerper 16 x 16 x 26 mm
    und ein Zugstab Rund d_stab von der Mitte seiner Deckflaeche (integrierter
    Knoten) 35 mm nach oben; dazu ein Passstift (Quader ohne Stab) und eine
    Platte 100 x 100 x 20 mm aus S355. ``platte``: der Stab der zweiten
    Schraube haengt statt am Schraubenkoerper an der Platte."""
    from statik3d.model import Model, Material, Section
    m = Model("Schrauben")
    m.add_material(Material("Nullmaterial", 210e9, 0.3, 7850.0, 1.2e-5, stab_fy, 490e6))
    m.add_material(Material("Koerper", 210e9, 0.3, 7850.0, 1.2e-5, koerper_fy, 490e6))
    # gleicher Werkstoff an Stab und Koerper wie am Drehlager, sonst ein eigener
    kw = "Nullmaterial" if koerper_fy == stab_fy else "Koerper"
    m.add_material(Material.steel("S355"))
    m.add_section(Section.circle(f"Rund {d_stab * 1e3:g}", d_stab))
    for i in range(2):
        x0 = 0.1 * i
        deckel = _quader(m, f"V{37 + i}", x0, 0.0, 0.0, 0.016, 0.016, 0.026, kw)
        oben = m.add_node(x0 + 0.008, 0.008, 0.026)
        deckel.integrierte_knoten.append(oben)
        spitze = m.add_node(x0 + 0.008, 0.008, 0.061)
        m.add_element("truss", [oben, spitze], "Nullmaterial", f"Rund {d_stab * 1e3:g}")
        m.add_member(f"S{17 + i}", [len(m.elements) - 1])
    _quader(m, "V61", 0.3, 0.0, 0.0, 0.025, 0.025, 0.067, "Koerper")          # Passstift, kein Stab
    p = _quader(m, "V1", 0.5, 0.0, 0.0, 0.1, 0.1, 0.02, "S355")              # Platte
    if platte:
        n = m.add_node(0.55, 0.05, 0.02)
        p.integrierte_knoten.append(n)
        n2 = m.add_node(0.55, 0.05, 0.06)
        m.add_element("truss", [n, n2], "Nullmaterial", f"Rund {d_stab * 1e3:g}")
        m.add_member("S99", [len(m.elements) - 1])
    return m


def test_schraubenhinweis():
    try:
        from statik3d.importers.schraubenhinweis import schraubenhinweis
    except ImportError as ex:
        check("Modul importers.schraubenhinweis", False, str(ex))
        return
    m = schraubenmodell()
    text = schraubenhinweis(m, stabarten={"S17": "Zugstab", "S18": "Zugstab"})
    print(f"     Hinweis: {text!r}")
    check("zwei Schrauben aus Nullmaterial: ein gebündelter Hinweis „2 Zugstäbe (Rund 16) und 2 Schraubenkörper …“",
          bool(text) and "2 Zugstäbe (Rund 16) und 2 Schraubenkörper aus „Nullmaterial“ (f_y 355 N/mm²)" in text
          and "8.8 (f_yb 640" in text and "10.9 (f_yb 900" in text and "umgestellt wurde nichts" in text, str(text))
    check("Hinweis nennt Stäbe und Volumen beim Namen, nicht den Passstift V61 und nicht die Platte V1",
          bool(text) and "S17" in text and "V37" in text and "V38" in text and "V61" not in text
          and "V1," not in text and "V1)" not in text, str(text))
    check("umgestellt wird nichts: Werkstoffe und Zuordnung unverändert",
          m.materials["Nullmaterial"].fy == 355e6 and m.koerper["V37"].material == "Nullmaterial"
          and m.elements[0].mat == "Nullmaterial")
    # keine Fehlalarme
    check("8.8 (f_y 640) an Stab und Körper: kein Hinweis",
          not schraubenhinweis(schraubenmodell(stab_fy=640e6, koerper_fy=640e6)))
    t = schraubenhinweis(schraubenmodell(stab_fy=640e6))
    check("nur die Körper unter 640: Hinweis nennt nur die Schraubenkörper",
          bool(t) and "Schraubenkörper" in t and "Stäbe" not in t.split(":")[1].split("Falls")[0], str(t))
    check("Stab Rund 40 (über Ø 36): kein Hinweis zum Stab, kein Schraubenkörper",
          not schraubenhinweis(schraubenmodell(d_stab=0.040)))
    t = schraubenhinweis(schraubenmodell(platte=True))
    check("Stab an einer Platte 100 mm: die Platte ist kein Schraubenkörper (nur der Stab zählt)",
          bool(t) and "V1 " not in t and "3 Stäbe" in t and "2 Schraubenkörper" in t, str(t))
    # Beispiele des Programms und die Modelle des Anwenders ohne Fehlalarm
    from statik3d.examples_lib import EXAMPLES
    for name, f in EXAMPLES.items():
        mm = f()
        check(f"Beispiel „{name}“: kein Hinweis", not schraubenhinweis(mm))
    from statik3d.model import Model
    for pfad in (os.path.join(os.path.expanduser("~"), "Desktop", "Statik3D", n)
                 for n in ("Kopfplatte_HEA_200.json", "cbg.json", "modellimport_rf6.json")):
        if os.path.exists(pfad):
            check(f"Modell {os.path.basename(pfad)}: kein Hinweis", not schraubenhinweis(Model.load(pfad)))
    rf6 = os.environ.get("STATIK3D_DREHLAGER_RF6") or os.path.join(
        os.path.expanduser("~"), "Desktop", "Statik3D", "RFEM_Modelle", "Lindaunis", "Drehlager_V15_4_export.rf6")
    if os.path.exists(rf6):
        from statik3d.importers import rfem6_db as R6
        log = []
        dm = R6.read_rf6(rf6, log=log)
        z = [s for s in log if "Schraubengüte" in s]
        print(f"     Drehlager: {z}")
        check("Drehlager: 48 Zugstäbe (Rund 16/20) und 48 Schraubenkörper aus „Nullmaterial“ (f_y 355)",
              len(z) == 1 and "48 Zugstäbe (Rund 16/20)" in z[0] and "48 Schraubenkörper" in z[0]
              and "„Nullmaterial“ (f_y 355" in z[0], str(z))
        check("Drehlager: Ankerstäbe Rund 40 und Passstifte V61 … nicht genannt",
              bool(z) and "Rund 40" not in z[0] and "V61" not in z[0], str(z))
        check("Drehlager: Namen gebündelt (S17–S64; V37–V60, V65–V70, V80–V91, V96–V101)",
              bool(z) and "Stäbe S17–S64; Volumen V37–V60, V65–V70, V80–V91, V96–V101." in z[0], str(z))
        mat = dm.materials.get("Material 3 (DB 2309)")
        check("Drehlager: Material 3 (DB 2309) als Spannstahl, f_p0,1k 835, f_pk 1 030, E 170 000, E_p 205 000",
              mat is not None and getattr(mat, "art", "") == "Spannstahl" and mat.fy == 835e6
              and mat.fu == 1030e6 and mat.E == 170e9 and mat.Ep == 205e9)


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    for t in (test_eta_mit_und_ohne_As, test_stahlstab_bitgleich, test_import_typ15, test_speichern_laden, test_kennung_unveraendert,
              test_spannungsgrenzen, test_zustaende, test_ladehinweis, test_vorspannkraft_schnittstelle,
              test_schraube_m20, test_bericht, test_masken,
              test_schraubenhinweis):
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
    sys.stdout.flush()
    os._exit(rc)
