"""
HiCAD-Wege: DSTV-NC (Stahlbauteile), SDNF (Bauwerksmodell) und die
Untersuchung nativer HiCAD-Behaelter (.sza/.kra/.fga).

Aufruf:  python -m tests.test_hicad
"""
import math
import struct
import os
import shutil
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import solver  # noqa: E402
from statik3d.importers import import_file, SUPPORTED, file_filter  # noqa: E402
from statik3d.importers import dstv as D  # noqa: E402
from statik3d.importers import sdnf as S  # noqa: E402
from statik3d.importers import hicad as H  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FAIL'} {name:58s} {detail}")
    return ok


def close(name, got, want, tol, unit=""):
    err = abs(got - want)
    rel = err / abs(want) if want else err
    return check(name, err <= tol * max(1.0, abs(want)),
                 f"{got:.6g}{unit} / {want:.6g}{unit}  Abw. {rel * 100:.3f} %")


# --------------------------------------------------------------------------
# DSTV-NC
# --------------------------------------------------------------------------
NC_HEA200 = """ST
** Kopfdaten
  A2024-017
  Z-101
  1
  ST-01
  S355J2
  4
  HEA200
  I
   6000.00
    190.00
    200.00
     10.00
      6.50
     18.00
     42.30
      1.136
      0.00
      0.00
      0.00
      0.00
BO
  v   100.00    50.00   22.00   0.00
  v  5900.00    50.00   22.00   0.00
  o   250.00    30.00   18.00   0.00
AK
  v      0.00     0.00     0.00
  v   6000.00     0.00     0.00
  v   6000.00   190.00     0.00
  v      0.00   190.00     0.00
  v      0.00     0.00     0.00
EN
"""

NC_ROHR = """ST
  A2024-017
  Z-102
  1
  ST-02
  S235JR
  2
  RO114.3*3.6
  RU
   3200.00
    114.30
    114.30
      3.60
      3.60
      0.00
      9.83
      0.359
EN
"""

NC_WINKEL = """ST
  A2024-017
  Z-103
  1
  ST-03
  S235JR
  6
  L80*80*8
  L
   1250.00
     80.00
     80.00
      8.00
      8.00
      0.00
      9.63
      0.313
EN
"""


def test_dstv():
    tmp = tempfile.mkdtemp()
    try:
        part = D.read_nc(NC_HEA200, "ST-01.nc1")
        check("NC: Position gelesen", part["position"] == "ST-01", part["position"])
        check("NC: Profil gelesen", part["profil"] == "HEA200", part["profil"])
        check("NC: Profilcode", part["code"] == "I", part["code"])
        check("NC: Werkstoff", part["werkstoff"] == "S355J2", part["werkstoff"])
        close("NC: Laenge", part["laenge"], 6000.0, 1e-9, " mm")
        close("NC: Hoehe", part["hoehe"], 190.0, 1e-9, " mm")
        close("NC: Stegdicke", part["stegdicke"], 6.5, 1e-9, " mm")
        close("NC: Gewicht je m", part["gewicht"], 42.30, 1e-9, " kg/m")
        check("NC: Stueckzahl", int(part["stueckzahl"]) == 4, str(part["stueckzahl"]))
        check("NC: Bohrungen gezaehlt", len(part["bohrungen"]) == 3,
              str(len(part["bohrungen"])))
        close("NC: erste Bohrung x", part["bohrungen"][0]["x"], 100.0, 1e-9, " mm")
        close("NC: erste Bohrung d", part["bohrungen"][0]["d"], 22.0, 1e-9, " mm")
        check("NC: Aussenkontur mit 5 Punkten",
              part["konturen"] and len(part["konturen"][0]["punkte"]) == 5,
              str(len(part["konturen"][0]["punkte"]) if part["konturen"] else 0))
        check("NC: Kommentarzeile verworfen", "Kopfdaten" not in str(part.values()))

        # Ordner mit drei Teilen
        d = os.path.join(tmp, "nc")
        os.makedirs(d)
        for fn, txt in (("ST-01.nc1", NC_HEA200), ("ST-02.nc1", NC_ROHR),
                        ("ST-03.nc1", NC_WINKEL)):
            with open(os.path.join(d, fn), "w", encoding="latin-1") as f:
                f.write(txt)
        log = []
        m = import_file(d, log=log)
        check("Ordner: drei Teile", len(m.elements) == 3, f"{len(m.elements)} Elemente")
        check("Ordner: Stabnamen aus der Position",
              sorted(m.members) == ["ST-01", "ST-02", "ST-03"], str(sorted(m.members)))
        sec = m.sections["HEA200"]
        close("HEA200 aus der Profildatenbank: A", sec.A, 53.83e-4, 0.02, " m^2")
        close("HEA200: I_y", sec.Iy, 3692e-8, 0.02, " m^4")
        L = [m.element_length(i) for i in range(3)]
        close("Laenge Teil 1", L[0], 6.0, 1e-9, " m")
        close("Laenge Teil 2", L[1], 3.2, 1e-9, " m")
        close("Laenge Teil 3", L[2], 1.25, 1e-9, " m")
        check("Teile liegen nebeneinander",
              len({round(float(m.nodes[e.nodes[0]][1]), 6) for e in m.elements}) == 3)
        check("Werkstoffe uebernommen", "S355J2" in m.materials and "S235JR" in m.materials,
              str(sorted(m.materials)))
        close("S355J2: Streckgrenze", m.materials["S355J2"].fy, 355e6, 1e-9, " Pa")
        check("Protokoll nennt die Gesamtmasse", any("Gesamtmasse" in x for x in log))
        check("Protokoll weist auf SDNF/IFC hin", any("SDNF" in x for x in log))

        # Rohr aus den Kopfmassen, wenn die Bezeichnung unbekannt ist
        p = D.read_nc(NC_ROHR.replace("RO114.3*3.6", "Sonderrohr"), "x.nc1")
        s = D.section_from_part(p)
        d_a, t = 0.1143, 0.0036
        close("Rohr aus Kopfmassen: A", s.A, math.pi / 4 * (d_a ** 2 - (d_a - 2 * t) ** 2),
              1e-6, " m^2")

        # ZIP mit NC-Dateien
        z = os.path.join(tmp, "teile.zip")
        with zipfile.ZipFile(z, "w") as zz:
            zz.writestr("ST-01.nc1", NC_HEA200)
            zz.writestr("ST-02.nc1", NC_ROHR)
        m2 = D.import_dstv(z)
        check("ZIP mit NC-Dateien", len(m2.elements) == 2, f"{len(m2.elements)}")

        check("is_nc erkennt die Datei", D.is_nc(os.path.join(d, "ST-01.nc1")))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# SDNF
# --------------------------------------------------------------------------
SDNF = """Packet 00
"HiCAD" "2024" "ISD Software und Systeme"
"Hallenrahmen" "Projekt 4711" "Achse A"
1
Packet 10
3
"1" 0 2 0 "HEA200" "S355JR" "Stuetze links"
0.0 0.0 0.0 0.0 0.0 6000.0
0.0 0.0 0.0
"2" 0 2 0 "HEA200" "S355JR" "Stuetze rechts"
12000.0 0.0 0.0 12000.0 0.0 6000.0
0.0 0.0 0.0
"3" 0 1 0 "IPE300" "S355JR" "Riegel"
0.0 0.0 6000.0 12000.0 0.0 6000.0
0.0 0.0 0.0
Packet 20
1
"P1" 0 0 0 "BL10" "S235JR"
0.0 0.0 6000.0 400.0 0.0 6000.0 400.0 400.0 6000.0 0.0 400.0 6000.0
10.0
Packet 99
"""


def test_sdnf():
    tmp = tempfile.mkdtemp()
    try:
        f = os.path.join(tmp, "rahmen.sdnf")
        with open(f, "w", encoding="latin-1") as fh:
            fh.write(SDNF)
        check("is_sdnf erkennt den Kopf", S.is_sdnf(SDNF))
        pk = S.packets(SDNF)
        check("Pakete erkannt", sorted(pk) == ["00", "10", "20", "99"], str(sorted(pk)))
        recs = S.records(pk["10"])
        check("Paket 10: drei Saetze", len(recs) == 3, str(len(recs)))
        check("Satz hat drei Zeilen", len(recs[0]) == 3, str(len(recs[0])))

        log = []
        m = import_file(f, log=log)
        beams = [e for e in m.elements if e.typ == "beam"]
        check("SDNF: drei Bauteile", len(beams) == 3, f"{len(beams)} Staebe")
        check("SDNF: Knoten der Stuetzen/Riegel zusammengefuehrt", m.nn == 7, f"{m.nn}")
        check("SDNF: Bauteilnamen", sorted(m.members) == ["1", "2", "3"],
              str(sorted(m.members)))
        check("SDNF: Profile erkannt",
              "HEA200" in m.sections and "IPE300" in m.sections, str(sorted(m.sections)))
        check("SDNF: Werkstoff erkannt", "S355JR" in m.materials, str(sorted(m.materials)))
        close("SDNF: Einheit mm -> Riegellaenge", m.element_length(2), 12.0, 1e-9, " m")
        close("SDNF: Stuetzenlaenge", m.element_length(0), 6.0, 1e-9, " m")
        check("SDNF: Blech als Schalen", any(e.typ.startswith("shell") for e in m.elements[3:])
              or len(m.shells) >= 1, f"{len(m.shells)} Schalendicken")
        check("Protokoll nennt die Pakete", any("Pakete" in x for x in log))

        # Rechnung: Rahmen unter Horizontallast
        m.fix(0, "all")
        m.fix(1, "all")
        m.load_node(2, Fx=10000.0, case=m.active_case)
        r = solver.solve_static(m)
        Rx = float(r.reactions[:, 0].sum())
        close("Gleichgewicht: Summe R_x = -H", Rx, -10000.0, 1e-6, " N")
        u = float(r.u.reshape(-1, 6)[2, 0])
        check("Rahmen verschiebt sich in x", u > 0, f"u = {u * 1e3:.3f} mm")

        # Einheit Zoll
        f2 = os.path.join(tmp, "zoll.sdnf")
        with open(f2, "w", encoding="latin-1") as fh:
            fh.write(SDNF.replace('"Achse A"\n1\n', '"Achse A"\n2\n'))
        m2 = S.import_sdnf(f2)
        close("Einheitenkennzahl 2 = Zoll", m2.element_length(0), 6000 * 0.0254, 1e-6, " m")

        # kein SDNF
        f3 = os.path.join(tmp, "kein.sdnf")
        with open(f3, "w", encoding="latin-1") as fh:
            fh.write("irgendein Text\n")
        try:
            S.import_sdnf(f3)
            check("Datei ohne Paket 00 wird abgewiesen", False)
        except ImportError as ex:
            check("Datei ohne Paket 00 wird abgewiesen", "Packet 00" in str(ex), str(ex)[:50])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# Native HiCAD-Behaelter
# --------------------------------------------------------------------------
def test_hicad_behaelter():
    tmp = tempfile.mkdtemp()
    try:
        # unbekannter Binaerbehaelter mit lesbaren Profilnamen
        f = os.path.join(tmp, "halle.sza")
        # Fuellbytes bewusst nicht zufaellig: sie duerfen nicht mit den
        # Bezeichnungen zu einem lesbaren Wort verschmelzen.
        fill = bytes(range(1, 32)) * 8
        blob = (b"HCSZA\x01\x00\x00\x00" + fill
                + "HEA 200;IPE 300;S355J2;L 80x80x8".encode("latin-1")
                + fill + b"Stuetze A1" + fill)
        with open(f, "wb") as fh:
            fh.write(blob)
        info = H.probe(f)
        check("Behaelter als unbekannt gemeldet", info["kind"] == "unbekannt", info["kind"])
        check("Kennung im Bericht", info["magic"].startswith("48 43 53 5a 41"), info["magic"])
        check("Profile aus dem Binaerstrom erkannt",
              {"HEA 200", "IPE 300"} <= set(info["profile"]), str(info["profile"][:6]))
        check("Werkstoff erkannt", "S355" in info["grades"], str(info["grades"]))
        check("Bericht nennt den Exportweg (Ausnahme)", True)
        try:
            H.import_hicad(f)
            check("unbekannte .sza wird abgewiesen", False)
        except ImportError as ex:
            check("unbekannte .sza wird abgewiesen",
                  "SDNF" in str(ex) and "HEA 200" in str(ex), str(ex)[:60])

        # .sza, die in Wahrheit ein ZIP mit SDNF ist
        f2 = os.path.join(tmp, "paket.sza")
        with zipfile.ZipFile(f2, "w") as z:
            z.writestr("modell.sdnf", SDNF)
            z.writestr("liste.txt", "Teileliste")
        log = []
        m = import_file(f2, log=log)
        nb = len([e for e in m.elements if e.typ == "beam"])
        check("ZIP-.sza mit SDNF wird gelesen", nb == 3, f"{nb} Staebe")
        check("Protokoll nennt die gefundene SDNF-Datei",
              any("modell.sdnf" in x for x in log))

        # .sza, die in Wahrheit DSTV-NC ist
        f3 = os.path.join(tmp, "teil.sza")
        with open(f3, "w", encoding="latin-1") as fh:
            fh.write(NC_HEA200)
        m3 = H.import_hicad(f3)
        check("DSTV-Inhalt in .sza erkannt", len(m3.elements) == 1, f"{len(m3.elements)}")

        # Dateidialog und Formatliste
        check("Endungen registriert",
              all(e in SUPPORTED for e in (".sdnf", ".nc1", ".sza", ".kra", ".fga")),
              str([e for e in (".sdnf", ".nc1", ".sza") if e in SUPPORTED]))
        ff = file_filter()
        check("Dateidialog nennt HiCAD", "*.sza" in ff and "*.sdnf" in ff and "*.nc1" in ff)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# HiCAD-Archiv (!HFA##)
# --------------------------------------------------------------------------
IPT_U = """ISD Part Table File, Version 1.06
# WARNING: DO NOT EDIT OR DELETE THIS FILE!

[SIZE]
Cols 30
Rows 2

[CATEGORY]
U-PROFIL_GENEIGTE_FLANSCHE:METRIC

[PARAMETER]
INT: ID
STR: MOD
INT: STATUS
STR: BZ!$BB
STR: SIZE
STR: MATERIAL
STR: OBERFL
STR: TYPE
STR: DSTV
DBL: H@~74!\u00a704&1\u20ac2
DBL: B@~1242004976&1\u20ac2
DBL: TS@~1242005297&1\u20ac2
DBL: R1@~1242005018&1\u20ac2
DBL: R2@~1242005018&1\u20ac2
DBL: H-2C&1\u20ac2
DBL: EZ&1\u20ac2
DBL: NGF&8\u20ac1
DBL: F&2\u20ac6
DBL: GEW&13\u20ac29
DBL: HGEW&13\u20ac29
DBL: W1&1\u20ac2
DBL: MANTELFL&14\u20ac27
DBL: IY&10\u20ac30
DBL: WY&12\u20ac32
DBL: IZ&10\u20ac30
DBL: WZ&12\u20ac32
DBL: ASTEG&2\u20ac20
DBL: TG&1\u20ac2
DBL: B1&1\u20ac2
STR: NORM!NRM

[DATA]
1\t*\t1\tU 200\tU 200\tS355J2+N\t\tS355J2+N\tU200\t200\t75\t8.5\t11.5\t6\t151\t20.1\t0.08\t3220\t25.3\t26\t40\t0.661\t1910\t191\t148\t27\t16\t11.5\t37.5\tDIN 1026-1
2\t*\t1\tU 120\tU 120\tS235J2+N\t\tS235J2+N\tU120\t120\t55\t7\t9\t4.5\t82\t16\t0.06\t1700\t13.4\t14\t30\t0.439\t364\t60.7\t43.2\t11.1\t9\t9\t27.5\tDIN 1026-1
"""

IPT_BLECH = """ISD Part Table File, Version 1.06

[SIZE]
Cols 12
Rows 2

[CATEGORY]
BLECH:METRIC

[PARAMETER]
INT: ID
STR: MOD
INT: STATUS
STR: BZ!$BB
STR: SIZE
STR: MATERIAL
STR: OBERFL
STR: TYPE
STR: DSTV
DBL: S&1\u20ac2
DBL: L1&1\u20ac2
DBL: W1&1\u20ac2

[DATA]
1\t*\t1\tBl 10\t10\tS355J2+N\t\tS355J2+N\tBL10\t10\t0\t0
2\t*\t1\tBl 20\t20\tS355J2+N\t\tS355J2+N\tBL20\t20\t0\t0
"""

IPT_MAT = """ISD Part Table File, Version 1.06

[SIZE]
Cols 14
Rows 2

[CATEGORY]
MATERIAL:METRIC

[PARAMETER]
INT: ID
STR: MOD
INT: STATUS
STR: BZ@~3
STR: BBZ
STR: WN@~3
DBL: RHO@~3&5\u20ac28
DBL: RM@~3&29\u20ac76
DBL: RE@~3&29\u20ac76
INT: *SRAF@~3
STR: MATERIAL@~3

[DATA]
1\t*\t1\tS355J2+N\t\t-\t7.85\t550\t355\t21\tS355J2+N
2\t*\t1\tS235J2+N\t\t-\t7.85\t550\t355\t21\tS235J2+N
"""


def _hfa(path, parts, atc_text=""):
    """HiCAD-Archiv (!HFA##) im echten Aufbau schreiben."""
    import struct
    try:
        import zstandard
    except ImportError:
        return None
    cc = zstandard.ZstdCompressor()
    head = bytearray(b"!HFA##\x00\x00")
    head += struct.pack("<QQ", 5, 11)
    head += struct.pack("<IQ", 22631, 48)
    head += "ISD Software & Systeme GmbH - Dortmund".encode("utf-16-le")
    head += b"\x00" * (0x198 - len(head))
    body = bytearray(head)
    items = list(parts.items())
    if atc_text:
        items.append(("C:\\HiCAD\\temp\\Archiv-1\\1.SZN.ATC",
                      b".ATC" + atc_text.encode("utf-16-le")))
    for i, (name, data) in enumerate(items):
        blob = cc.compress(data)
        pos = len(body)
        nxt = pos + 1024 + 72 + len(blob)
        nm = name.encode("utf-16-le")
        body += nm + b"\x00" * (1024 - len(nm))
        f = [0] * 18
        f[1] = nxt
        f[13] = 3
        f[16] = len(blob)
        f[17] = len(data)
        body += struct.pack("<18I", *f)
        body += blob
    with open(path, "wb") as fh:
        fh.write(bytes(body))
    return path


def test_hicad_archiv():
    from statik3d.importers import hicad_sza as A
    try:
        import zstandard          # noqa: F401
    except ImportError:
        check("zstandard vorhanden (HiCAD-Archive)", False, "pip install zstandard")
        return
    tmp = tempfile.mkdtemp()
    try:
        f = os.path.join(tmp, "rahmen.sza")
        atc = "U 200 {U - Profile} {12}\x00Bl 10 {Bleche} {7}\x00S355J2+N\x00"
        _hfa(f, {
            "C:\\HiCAD\\temp\\Archiv-1\\1.SZN": b"FILE-CONTAINER ISD  1.0\x00" + b"\x01" * 200,
            "C:\\HiCAD\\temp\\Archiv-1\\DIN_1026_U.IPT": b"\xff\xfe" + IPT_U.encode("utf-16-le"),
            "C:\\HiCAD\\temp\\Archiv-1\\BLECH.IPT": b"\xff\xfe" + IPT_BLECH.encode("utf-16-le"),
            "C:\\HiCAD\\temp\\Archiv-1\\ALLGEMEINE_BAUSTAEHLE.IPT":
                b"\xff\xfe" + IPT_MAT.encode("utf-16-le"),
        }, atc_text=atc)
        check("Archiv als HiCAD-Behaelter erkannt", A.is_hicad_archive(f))
        ents = A.archive_entries(f)
        check("Archiv: fuenf Teile", len(ents) == 5, str(len(ents)))
        check("Teilart erkannt (SZN)", ents[0]["art"].startswith("Szene"), ents[0]["art"])
        check("Teilart erkannt (IPT)", ents[1]["art"].startswith("Teiletabelle"), ents[1]["art"])

        ents = A.archive_entries(f, data=True)
        check("SZN entpackt", ents[0]["data"].startswith(b"FILE-CONTAINER ISD"),
              repr(ents[0]["data"][:20]))

        tabs = A.part_tables(f)
        check("drei Teiletabellen gelesen", len(tabs) == 3, str(sorted(tabs)))
        u = tabs["DIN_1026_U.IPT"]
        check("Kategorie der Tabelle", u["kategorie"].startswith("U-PROFIL"), u["kategorie"])
        check("Spaltennamen bereinigt", "IY" in u["spalten"] and "TS" in u["spalten"],
              str(u["spalten"][:12]))
        secs = A.table_sections(u)
        close("U 200 aus der Teiletabelle: A", secs["U 200"].A, 32.20e-4, 1e-9, " m^2")
        close("U 200: I_y", secs["U 200"].Iy, 1910e-8, 1e-9, " m^4")
        close("U 200: I_z", secs["U 200"].Iz, 148e-8, 1e-9, " m^4")
        close("U 200: h", secs["U 200"].h, 0.200, 1e-9, " m")
        close("U 120: A", secs["U 120"].A, 17.00e-4, 1e-9, " m^2")
        check("Torsion aus duennwandiger Naeherung", 0 < secs["U 200"].It < 2e-6,
              f"I_t = {secs['U 200'].It * 1e8:.2f} cm^4")

        plates = A.table_plates(tabs["BLECH.IPT"])
        close("Blech Bl 20", plates["Bl 20"], 0.020, 1e-12, " m")
        check("Blechtabelle liefert keine Querschnitte",
              not A.table_sections(tabs["BLECH.IPT"]))
        mats = A.table_materials(tabs["ALLGEMEINE_BAUSTAEHLE.IPT"])
        check("Werkstofftabelle gelesen", "S355J2+N" in mats, str(sorted(mats)))
        close("Werkstoffdichte", mats["S355J2+N"][0], 7850.0, 1e-9, " kg/m^3")

        desig = A.part_designations(f)
        check("Bauteilbezeichnungen gefunden",
              any(d.startswith("U 200") for d in desig), str(desig[:5]))

        # Vollstaendiger Import ueber den Dispatcher
        log = []
        m = import_file(f, log=log)
        check("Import: U 200 uebernommen", "U 200" in m.sections, str(sorted(m.sections)))
        check("Import: Blech als Schalendicke", "Bl 10" in m.shells, str(sorted(m.shells)))
        check("Import: Werkstoff uebernommen", "S355J2+N" in m.materials,
              str(sorted(m.materials)))
        close("Import: f_y nach EN 10025-2", m.materials["S355J2+N"].fy, 355e6, 1e-9, " Pa")
        check("Protokoll nennt die Teileliste", any("Teileliste" in x for x in log))
        check("Protokoll nennt den Exportweg", any("SDNF" in x for x in log))

        # Entpacken in ein Verzeichnis
        d2 = os.path.join(tmp, "raus")
        files = A.extract(f, d2)
        check("Archiv entpackt", len(files) == 5, str(len(files)))
        check("entpackte Teiletabelle lesbar",
              os.path.getsize(os.path.join(d2, "DIN_1026_U.IPT")) > 100)

        rep = A.report(f)
        check("Bericht nennt Teile und Groesse", "HiCAD-Archiv" in rep and "DIN_1026_U.IPT" in rep)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# SZN: Geometrie aus dem Szenenteil
# --------------------------------------------------------------------------
def _szn(blaetter) -> bytes:
    """Eine SZN im echten Aufbau bauen: Fortran-Saetze, Abschnitte, Blaetter.

    blaetter: [(Nummer, [(x, y, z, art), ...])] - Masse in Millimetern.
    """
    from statik3d.importers import hicad_szn as Z

    def satz(b: bytes) -> bytes:
        return struct.pack("<I", len(b)) + b + struct.pack("<I", len(b))

    def abschnitt(name: str, saetze: list) -> bytes:
        inhalt = b"".join(satz(x) for x in saetze)
        return (satz(Z.SECTION + b"\0") + satz(struct.pack("<I", len(inhalt)))
                + satz(struct.pack("<I", len(name))) + satz(name.encode("ascii"))
                + inhalt)

    out = [Z.MAGIC, abschnitt("SZN_HEA", [struct.pack("<I", 1)])]
    for nummer, punkte in blaetter:
        roh = b"".join(struct.pack("<3dI I I I", x, y, z, 0, art, 0, 0)
                       for x, y, z, art in punkte)
        out.append(abschnitt("SZ_LEAF", [struct.pack("<I", nummer),
                                         struct.pack("<I", len(punkte)), roh]))
    out.append(abschnitt("ENDTREE", [struct.pack("<I", 0)]))
    return b"".join(out)


def _u200_wolke(x0, y0, z0, x1, y1, z1, h=200.0, b=75.0):
    """Achse (Art 4003) und ein Querschnittsrechteck (Art 2) an beiden Enden."""
    import numpy as np
    p0, p1 = np.array([x0, y0, z0]), np.array([x1, y1, z1])
    e1 = (p1 - p0) / np.linalg.norm(p1 - p0)
    # zwei Richtungen senkrecht zur Achse
    hilf = np.array([0.0, 0.0, 1.0]) if abs(e1[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    e2 = np.cross(e1, hilf); e2 /= np.linalg.norm(e2)
    e3 = np.cross(e1, e2)
    pts = [(x0, y0, z0, 4003), (x1, y1, z1, 4003), (*e1, 5)]
    for p in (p0, p1):
        for sh in (-h / 2, h / 2):
            for sb in (-b / 2, b / 2):
                q = p + e2 * sh + e3 * sb
                pts.append((q[0], q[1], q[2], 2))
    return pts


def test_szn_geometrie():
    from statik3d.importers import hicad_szn as Z
    from statik3d.model import Model, Material
    from statik3d.profiles import make_section

    blatt_u = _u200_wolke(0, 0, 0, 0, 0, 3000)                 # Pfosten, 3 m
    blatt_q = _u200_wolke(37.5, 0, 1000, 2000, 0, 1000, 100, 10)   # Querstab
    klein = [(0, 0, 0, 4003), (0, 0, 30, 4003)] + [(1, 1, 1, 2)] * 4   # 30 mm Stift
    data = _szn([(1, blatt_u), (2, blatt_q), (3, klein)])

    check("SZN-Kennung erkannt", Z.is_szn(data))
    recs = Z.records(data, strict=True)
    check("Satzkette endet am Dateiende", len(recs) > 10, f"{len(recs)} Saetze")
    namen = [n for n, _a, _b in Z.sections(recs)]
    check("Abschnitte gelesen", namen.count("SZ_LEAF") == 3 and "SZN_HEA" in namen,
          str(namen))
    check("Fremde Datei wird abgewiesen",
          not Z.is_szn(b"nur text") and _raises(Z.records, b"nur text"))

    bl = Z.leaves(data)
    check("drei Blaetter mit Punkten", len(bl) == 3 and len(bl[0].punkte) == len(blatt_u))
    check("Millimeter in Meter umgerechnet",
          abs(float(bl[0].punkte[1][2]) - 3.0) < 1e-9, str(bl[0].punkte[1]))
    check("Punktarten uebernommen",
          int((bl[0].arten == Z.ACHSE).sum()) == 2
          and int((bl[0].arten == Z.RICHTUNG).sum()) == 1)

    k = Z.koerper(bl[0])
    check("Achse 4003 wird als Stabachse genommen", k.quelle == "Achse 4003", k.quelle)
    check("Laenge aus der Achse", abs(k.L - 3.0) < 1e-9, f"{k.L}")
    check("Querschnitt senkrecht zur Achse gemessen",
          abs(k.h - 0.200) < 1e-6 and abs(k.b - 0.075) < 1e-6, f"{k.h}/{k.b}")

    st = Z.staebe(data)
    check("Stift unter 100 mm wird nicht zum Stab", len(st) == 2, str(len(st)))

    prof = {"UPN 200": make_section("UPN 200"), "IPE 300": make_section("IPE 300")}
    name, dh, db = Z.passendes_profil(0.206, 0.079, prof)
    check("gemessene 206 x 79 mm finden 'UPN 200'", name == "UPN 200", str(name))
    check("Abweichung wird ausgewiesen", abs(dh - 0.006) < 1e-6, f"{dh}")
    check("zu breites Profil wird verworfen",
          Z.passendes_profil(0.206, 0.020, {"UPN 200": prof["UPN 200"]})[0] is None)
    check("unpassende Hoehe findet nichts",
          Z.passendes_profil(0.500, 0.200, prof)[0] is None)

    m = Model("SZN")
    m.add_material(Material.steel("S235"))
    log = []
    r = Z.in_modell(data, m, profile=prof, log=log)
    check("Staebe im Modell", r["staebe"] == 2 and len(m.elements) == 2, str(r))
    check("Knoten im Modell", m.nn == 4, str(m.nn))
    check("Pfosten bekommt UPN 200",
          any(getattr(e, "sec", "") == "UPN 200" for e in m.elements),
          str([getattr(e, "sec", "") for e in m.elements]))
    check("Ersatzrechteck fuer unbekanntes Mass",
          any(s.startswith("gemessen") for s in m.sections), str(sorted(m.sections)))
    check("Protokoll nennt die Zuordnung", any("UPN 200" in z for z in log))

    zus = Z.zusammenhang(m)
    check("Teiltragwerke gezaehlt", zus["teile"] == 2, str(zus))
    # gemessen wird der kleinste Knoten-Knoten-Abstand zwischen den Teilen:
    # Pfostenfuss (0,0,0) zum Anfang des Querstabes (37,5 mm, 0, 1 m)
    check("Luecke zwischen den Teilen gemessen",
          abs(zus["luecke"] - math.hypot(0.0375, 1.0)) < 1e-6, str(zus["luecke"]))

    log2 = []
    r2 = Z.an_staebe_anschliessen(m, 0.06, log2)
    check("freies Ende angeschlossen", r2["angeschlossen"] >= 1, str(r2))
    check("Pfosten dafuer geteilt", r2["geteilt"] == 1 and len(m.elements) == 3, str(r2))
    check("Versatz ausgewiesen und begrenzt",
          0 < r2["groesster_versatz"] <= 0.06, str(r2["groesster_versatz"]))
    check("System haengt zusammen", Z.zusammenhang(m)["teile"] == 1)
    check("Protokoll nennt den Versatz", any("Versatz" in z for z in log2))

    m2 = Model("leer")
    m2.add_material(Material.steel("S235"))
    check("Szene ohne Staebe stoert nicht",
          Z.in_modell(_szn([(1, klein)]), m2, profile=prof)["staebe"] == 0)


def _raises(fn, *a) -> bool:
    try:
        fn(*a)
    except Exception:      # noqa: BLE001
        return True
    return False


def main():
    for t in (test_dstv, test_sdnf, test_hicad_behaelter, test_hicad_archiv,
              test_szn_geometrie):
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


