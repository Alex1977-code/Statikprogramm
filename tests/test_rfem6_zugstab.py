"""RFEM-6-Zugstäbe und -Druckstäbe beim Import (14.10.2026).

Bis zum 14.10.2026 legte der RFEM-6-Import einen Zugstab (Umsetzungstabelle
MemberImplTension, in RFEM „isActiveInCompression“ = 0) als gewöhnlichen
Fachwerkstab an, der auch Druck trug; das Protokoll warnte nur („faellt in RFEM
bei Druck aus - hier traegt er auch Druck“). Am Drehlager sind das alle 64
Stäbe: S57 trug im Lastfall LF1 (Netz Mittel, 09.10.2026) −0,59 kN Druck.
Seither setzt der Import ``nur = "zug"`` (Zugstab, der in RFEM bei Druck
ausfällt) bzw. ``nur = "druck"`` (Druckstab). Ein Zugstab, der in RFEM auch
Druck trägt (isActiveInCompression = 1), bleibt ein gewöhnlicher Fachwerkstab.

Ein früher gespeichertes Modell bekommt beim Öffnen einen Hinweis mit der
Umstellung, die der Anwender auslöst (rfem6_db.zugstaebe_aus_rfem liest die
Stabtypen aus der RFEM-Datei nach); von selbst wird nichts umgestellt.

Aufruf:  python -m tests.test_rfem6_zugstab
"""
import os
import shutil
import sqlite3
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import solver                                        # noqa: E402
from statik3d.importers import rfem6_db as R6                      # noqa: E402
from statik3d.model import Model                                   # noqa: E402
from tests.test_rfem6 import INF, build_db                         # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:84s} {detail}")
    return ok


def _datei(tmp, aktiv_druck=(0, 1), druckstab=True, spalte=True, parallel=False):
    """model.db mit Zugstäben (MemberImplTension, isActiveInCompression aus
    ``aktiv_druck``), einem Druckstab (MemberImplCompression) und einem
    Balken. ``spalte=False``: eine Datei ohne die Spalte isActiveInCompression
    (wie die Prüfdateien bis heute). ``parallel``: ein Zugstab und ein Balken
    zwischen denselben zwei Knoten, Knoten 1 fest, Knoten 2 in x frei."""
    db = os.path.join(tmp, "model.db")
    if parallel:
        build_db(db, nodes=[(0, 0, 0), (1, 0, 0)], lines=[[1, 2], [1, 2]],
                 members=[(1, None, None, "MemberImplTension"), (2, None, None, "MemberImplBeam")],
                 supports=[("Fest", (INF,) * 6, (0,) * 6, None, [1]),
                           ("Gleit", (0.0, INF, INF, INF, INF, INF), (0,) * 6, None, [2])])
        aktiv_druck, druckstab = (0,), False
    else:
        n = len(aktiv_druck) + (1 if druckstab else 0) + 1
        knoten = [(float(i % 2), float(i // 2), 0.0) for i in range(2 * n)]
        linien = [[2 * i + 1, 2 * i + 2] for i in range(n)]
        mem = [(i + 1, None, None, "MemberImplTension") for i in range(len(aktiv_druck) + (1 if druckstab else 0))]
        mem.append((n, None, None, "MemberImplBeam"))
        build_db(db, nodes=knoten, lines=linien, members=mem,
                 supports=[("Fest", (INF,) * 6, (0,) * 6, None, list(range(1, 2 * n + 1)))])
    con = sqlite3.connect(db)
    try:
        if spalte:
            con.execute("ALTER TABLE MemberImplTension ADD COLUMN isActiveInCompression boolean")
            for i, a in enumerate(aktiv_druck, 1):
                con.execute("UPDATE MemberImplTension SET isActiveInCompression=? WHERE id=?", (int(a), i))
        if druckstab:
            i = len(aktiv_druck) + 1
            spalten = [r[1] for r in con.execute("PRAGMA table_info(MemberImplTension)")]
            con.execute("CREATE TABLE MemberImplCompression AS SELECT * FROM MemberImplTension WHERE 0")
            con.execute(f"INSERT INTO MemberImplCompression SELECT {', '.join(spalten)} "
                        f"FROM MemberImplTension WHERE id=?", (i,))
            con.execute("DELETE FROM MemberImplTension WHERE id=?", (i,))
            con.execute("UPDATE Member SET impl_table='MemberImplCompression' WHERE id=?", (i,))
        con.commit()
    finally:
        con.close()
    rf6 = os.path.join(tmp, "zugstab.rf6")
    with zipfile.ZipFile(rf6, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(db, "model.db")
        z.writestr("format.txt", "RFEM\n6.11.0004\nRFEM6\n6.12.0010\n1773229130\n")
    os.remove(db)
    return rf6


def _nur(m, stab):
    return [m.elements[i].nur for i in m.members[stab].elements]


def test_import_setzt_nur():
    print("\n--- Import: Zugstab nur Zug, Druckstab nur Druck ---")
    tmp = tempfile.mkdtemp()
    try:
        log = []
        m = R6.read_rf6(_datei(tmp), log=log)
        check("Zugstab (isActiveInCompression 0): nur Zug", _nur(m, "S1") == ["zug"], _nur(m, "S1"))
        check("Zugstab, der in RFEM auch Druck trägt (isActiveInCompression 1): Zug und Druck",
              _nur(m, "S2") == [""], _nur(m, "S2"))
        check("Druckstab: nur Druck", _nur(m, "S3") == ["druck"], _nur(m, "S3"))
        check("Balken bleibt Balken ohne Ausfall", _nur(m, "S4") == [""]
              and m.elements[m.members["S4"].elements[0]].typ == "beam")
        check("das Protokoll nennt den Zugstab mit „nur Zug“",
              any("Zugstab trägt nur Zug" in z and "S1" in z for z in log),
              next((z for z in log if "nur Zug" in z), "-"))
        check("… und den Druckstab mit „nur Druck“",
              any("Druckstab trägt nur Druck" in z and "S3" in z for z in log),
              next((z for z in log if "nur Druck" in z), "-"))
        check("das Protokoll nennt den Zugstab, der auch Druck trägt",
              any("auch Druck" in z and "S2" in z for z in log), next((z for z in log if "auch Druck" in z), "-"))
        check("keine Warnung „trägt hier auch Druck“ mehr",
              not any("hier traegt er auch Druck" in z for z in log))
        check("das Modell weiß, dass der Import die Stabtypen kennt (kein Hinweis beim Öffnen)",
              bool(m.meta.get("rfem_zugstaebe")) and not any(h.get("art") == "zugstab" for h in m.importhinweise),
              str(m.meta.get("rfem_zugstaebe")))
        m2 = R6.read_rf6(_datei(tempfile.mkdtemp(dir=tmp), spalte=False, druckstab=False, aktiv_druck=(0,)),
                         log=[])
        check("Datei ohne Spalte isActiveInCompression: Zugstab nur Zug (Vorgabe in RFEM)",
              _nur(m2, "S1") == ["zug"], _nur(m2, "S1"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_zugstab_faellt_aus():
    print("\n--- Rechnung: der importierte Zugstab fällt unter Druck aus ---")
    tmp = tempfile.mkdtemp()
    try:
        m = R6.read_rf6(_datei(tmp, parallel=True), log=[])
        z = m.members["S1"].elements[0]
        b = m.members["S2"].elements[0]
        lc = m.add_load_case("D")
        lc.gravity = [0, 0, 0]
        m.load_node(1, Fx=-10e3, case="D")
        r = solver.solve_static(m, case="D")
        check("der Zugstab fällt aus", list(r.info.get("ausfall") or []) == [z], str(r.info.get("ausfall")))
        N_z = float(r.beam_forces[z]["N"][1])
        N_b = float(r.beam_forces[b]["N"][1])
        check("er trägt nichts, der Balken trägt die 10 kN", abs(N_z) < 1e-9 and abs(N_b + 10e3) < 1e-6,
              f"N_Zugstab {N_z:.3g} N, N_Balken {N_b:.6g} N")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_gespeichertes_modell():
    print("\n--- Gespeichertes Modell von vor dem 14.10.2026: Hinweis und Umstellung auf Anweisung ---")
    tmp = tempfile.mkdtemp()
    try:
        rf6 = _datei(tmp)
        m = R6.read_rf6(rf6, log=[])
        # so legte der Import es bis zum 14.10.2026 an
        for e in m.elements:
            e.nur = ""
        m.meta.pop("rfem_zugstaebe", None)
        m.meta["quelle"] = rf6
        pfad = os.path.join(tmp, "alt.json")
        m.save(pfad)
        alt = Model.load(pfad)
        h = [x for x in alt.importhinweise if x.get("art") == "zugstab"]
        check("beim Öffnen: ein Hinweis zu den Zugstäben", len(h) == 1 and not h[0].get("erledigt"),
              h[0].get("text", "") if h else "kein Hinweis")
        check("… mit der Umstellung als Vorschlag und der RFEM-Datei",
              h and "zugstaebe_aus_rfem" in str(h[0].get("vorschlag", "")) and h[0].get("datei") == rf6,
              str(h[0].get("vorschlag", ""))[:120] if h else "")
        check("… und im Protokoll des Öffnens", any("Zugst" in z for z in alt._ladehinweise),
              next((z for z in alt._ladehinweise if "Zugst" in z), "-"))
        check("von selbst wird nichts umgestellt", all(e.nur == "" for e in alt.elements))
        log = []
        aus = R6.zugstaebe_aus_rfem(alt, log=log)
        check("Umstellung: Zugstab nur Zug, Druckstab nur Druck, der Rest bleibt",
              _nur(alt, "S1") == ["zug"] and _nur(alt, "S2") == [""] and _nur(alt, "S3") == ["druck"]
              and _nur(alt, "S4") == [""], f"{aus}")
        check("Umstellung: sie nennt die Stäbe", aus.get("zug") == ["S1"] and aus.get("druck") == ["S3"]
              and aus.get("auch_druck") == ["S2"], f"{aus}")
        check("Umstellung: der Hinweis ist erledigt",
              all(x.get("erledigt") for x in alt.importhinweise if x.get("art") == "zugstab"))
        alt.save(pfad)
        wieder = Model.load(pfad)
        check("nach dem Speichern: kein neuer Hinweis, die Einstellung bleibt",
              not any(x.get("art") == "zugstab" and not x.get("erledigt") for x in wieder.importhinweise)
              and _nur(wieder, "S1") == ["zug"])
        # fehlt die RFEM-Datei, sagt es die Umstellung und aendert nichts
        alt2 = Model.load(os.path.join(tmp, "alt.json"))
        for e in alt2.elements:
            e.nur = ""
        try:
            R6.zugstaebe_aus_rfem(alt2, pfad=os.path.join(tmp, "fehlt.rf6"))
            check("fehlende RFEM-Datei: Fehler mit Grund", False, "kein Fehler")
        except FileNotFoundError as ex:
            check("fehlende RFEM-Datei: Fehler mit Grund, nichts umgestellt",
                  "fehlt.rf6" in str(ex) and all(e.nur == "" for e in alt2.elements), str(ex)[:100])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_ohne_rfem_kein_hinweis():
    print("\n--- Ein Modell, das nicht aus RFEM 6 kommt, bekommt keinen Hinweis ---")
    tmp = tempfile.mkdtemp()
    try:
        from statik3d.model import Material, Section
        m = Model("eigen")
        m.add_material(Material("S", E=210e9, nu=0.3, rho=7850))
        m.add_section(Section.circle("D", 0.02))
        a, b = m.add_node(0, 0, 0), m.add_node(1, 0, 0)
        m.add_member("S1", [m.add_element("truss", [a, b], "S", "D")])
        pfad = os.path.join(tmp, "eigen.json")
        m.save(pfad)
        neu = Model.load(pfad)
        check("kein Zugstab-Hinweis", not any(x.get("art") == "zugstab" for x in neu.importhinweise)
              and not any("Zugst" in z for z in neu._ladehinweise))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    for t in (test_import_setzt_nur, test_zugstab_faellt_aus, test_gespeichertes_modell,
              test_ohne_rfem_kein_hinweis):
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {type(ex).__name__}: {ex})", False))
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
