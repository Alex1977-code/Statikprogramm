"""Layer: benannte Objektgruppen fuer Sicht und Sperre (16.09.2026).

Wunsch: "Ribbon Ansicht soll eine Dropdownliste mit Layern haben, in RFEM
sind das die Objektselektionen; ein Fenster mit allen Layern, anhaken, welche
zu sehen sind, und eine Option, dass ein Layer gesperrt wird."

Geprueft wird das Modell (Anlegen, Ergaenzen, Entfernen, Inhalt mit dem, was
dazugehoert, Sperre, Speichern und Laden, Kopie, Umnummerieren beim Loeschen)
und der RFEM-6-Import der Objektselektionen an einer nachgebauten Datenbank
in beiden belegten Fassungen (Nummernliste als Text, Verweise blockweise;
Listentabelle mit Objektart, Verweise direkt).

Aufruf:  python -m tests.test_layer
"""
import os
import sqlite3
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d.model import Layer, Material, Model, Section, Volumenkoerper   # noqa: E402
from statik3d.importers import rfem6_db as R6              # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:66s} {detail}")
    return ok


def _modell() -> Model:
    """Zwei Staebe, eine Flaeche mit vier Linien, ein Koerper mit zwei Tetraedern."""
    m = Model("Layerprobe")
    mat = m.add_material(Material.steel("S235")).name
    sec = m.add_section(Section.rectangle("R", 0.1, 0.2)).name
    m.add_nodes(np.array([[0, 0, 0], [1, 0, 0], [2, 0, 0],            # 0-2 Staebe
                          [0, 1, 0], [1, 1, 0], [1, 2, 0], [0, 2, 0],  # 3-6 Flaeche
                          [3, 0, 0], [4, 0, 0], [3, 1, 0], [3, 0, 1], [4, 1, 1]], float))  # 7-11 Koerper
    e0 = m.add_element("beam", [0, 1], mat, sec)
    e1 = m.add_element("beam", [1, 2], mat, sec)
    m.add_member("S1", [e0])
    m.add_member("S2", [e1])
    for name, (a, b) in (("L1", (3, 4)), ("L2", (4, 5)), ("L3", (5, 6)), ("L4", (6, 3))):
        m.add_line(name, [a, b])
    m.add_flaeche("F1", ["L1", "L2", "L3", "L4"], material=mat)
    t0 = m.add_element("tet4", [7, 8, 9, 10], mat)
    t1 = m.add_element("tet4", [8, 9, 10, 11], mat)
    m.koerper["V1"] = Volumenkoerper("V1", ["F1"], material=mat, elemente=[t0, t1])
    return m


def test_modell():
    m = _modell()
    L = m.layer_anlegen("Deckel", koerper=["V1", "V9"], staebe=["S1"], linien=["L1"], knoten=[0, 99],
                        elemente=[1, 50], quelle="rfem")
    check("Layer angelegt: nur Vorhandenes kommt hinein",
          L.koerper == ["V1"] and L.staebe == ["S1"] and L.linien == ["L1"] and L.knoten == [0]
          and L.elemente == [1] and L.quelle == "rfem" and "Deckel" in m.layer, L.bezug())
    check("bezug nennt die Arten", L.bezug() == "1 Volumen, 1 Stäbe, 1 Linien, 1 Knoten, 1 Elemente", L.bezug())
    m.layer_anlegen("Deckel", staebe=["S2", "S1"], knoten=[0, 2])
    check("gleicher Name ergaenzt ohne Doppelte", L.staebe == ["S1", "S2"] and L.knoten == [0, 2], str(L.staebe))
    m.layer_entfernen(L, staebe=["S1"], knoten=[2])
    check("layer_entfernen nimmt Objekte heraus", L.staebe == ["S2"] and L.knoten == [0], str(L.staebe))
    check("layer_von findet die Layer eines Objekts",
          m.layer_von("koerper", "V1") == ["Deckel"] and m.layer_von("staebe", "S1") == []
          and m.layer_von("knoten", 0) == ["Deckel"] and m.layer_von("knoten", "0") == ["Deckel"])
    check("enthaelt: fremde Art und Unsinn sind False",
          not L.enthaelt("lager", "x") and not L.enthaelt("knoten", "abc") and L.enthaelt("elemente", 1))
    # Inhalt mit dem, was dazugehoert
    inhalt = m.layer_inhalt("Deckel")
    check("Inhalt: Koerper bringt Flaechen, Linien, Elemente und Knoten mit",
          inhalt["koerper"] == {"V1"} and inhalt["flaechen"] == {"F1"} and inhalt["linien"] == {"L1", "L2", "L3", "L4"}
          and {2, 3} <= inhalt["elemente"] and {7, 8, 9, 10, 11, 3, 4, 5, 6} <= inhalt["knoten"],
          f"{sorted(inhalt['elemente'])} {sorted(inhalt['knoten'])}")
    check("Inhalt: Stab bringt sein Element und dessen Knoten mit",
          inhalt["staebe"] == {"S2"} and 1 in inhalt["elemente"] and {1, 2} <= inhalt["knoten"])
    # Sperre
    L2 = m.layer_anlegen("Sperre", flaechen=["F1"], knoten=[3])
    check("ohne Haken keine Sperre", m.layer_sperre("flaechen", "F1") == "" and m.layer_gesperrt()["flaechen"] == {})
    L2.gesperrt = True
    g = m.layer_gesperrt()
    check("layer_sperre nennt den gesperrten Layer",
          m.layer_sperre("flaechen", "F1") == "Sperre" and m.layer_sperre("knoten", 3) == "Sperre"
          and m.layer_sperre("koerper", "V1") == "" and g["flaechen"] == {"F1": "Sperre"} and g["knoten"] == {3: "Sperre"},
          str(g))
    # Speichern, Laden, Kopie
    L2.sichtbar = False
    d = m.to_dict()
    m2 = Model.from_dict(d)
    check("to_dict/from_dict bewahrt Layer mit Haken und Herkunft",
          set(m2.layer) == {"Deckel", "Sperre"} and m2.layer["Sperre"].gesperrt and not m2.layer["Sperre"].sichtbar
          and m2.layer["Deckel"].quelle == "rfem" and m2.layer["Deckel"].koerper == ["V1"],
          str({k: (v.sichtbar, v.gesperrt) for k, v in m2.layer.items()}))
    m3 = m.copy()
    m3.layer["Deckel"].koerper.append("V9")
    check("copy: Layer sind eine eigene Kopie", m.layer["Deckel"].koerper == ["V1"] and set(m3.layer) == set(m.layer))
    # Umnummerieren
    m4 = _modell()
    L4 = m4.layer_anlegen("Netz", elemente=[0, 1, 2, 3], knoten=[0, 5, 11])
    m4.elemente_loeschen([1])
    check("elemente_loeschen zieht die Elementnummern im Layer nach",
          L4.elemente == [0, 1, 2], str(L4.elemente))
    m5 = Model("frei")
    m5.add_nodes(np.array([[0, 0, 0], [1, 0, 0], [2, 0, 0]], float))
    L5 = m5.layer_anlegen("Punkte", knoten=[0, 1, 2])
    fehler = m5.knoten_loeschen(1)
    check("knoten_loeschen nimmt den Knoten heraus und rueckt die Nummern auf",
          fehler == "" and L5.knoten == [0, 1], f"{fehler!r} {L5.knoten}")
    check("Layer ohne Inhalt ist leer", Layer("x").leer() and not L5.leer() and Layer("x").bezug() == "leer")


# ---------------------------------------------------------------------------
# RFEM 6: Objektselektionen
# ---------------------------------------------------------------------------
def _db(schema: str) -> str:
    """Eine Modelldatenbank mit den Tabellen der Objektselektionen.

    schema "gepackt": ObjectListConditionValue.objects_packed, Verweise
    blockweise hinter dem Bereich der conditions_id (wie am Drehlager);
    "liste": ObjectListConditionValue_model_object_indices, Verweise direkt.
    """
    pfad = os.path.join(tempfile.mkdtemp(prefix="statik3d_layer_"), "model.db")
    con = sqlite3.connect(pfad)
    c = con.cursor()
    for tabelle in ("Line", "Surface", "Solid", "ObjectSelection"):
        c.execute(f"CREATE TABLE {tabelle} (id INTEGER, userID INTEGER, impl_id INTEGER, impl_table TEXT)")
    for tabelle in ("LineImplPolyline", "SurfaceImplPlane", "SolidImplStandard"):
        c.execute(f"CREATE TABLE {tabelle} (id INTEGER)")
    for i, uid in enumerate((10, 11, 12), 1):
        c.execute("INSERT INTO Line VALUES (?, ?, ?, 'LineImplPolyline')", (i, uid, i))
        c.execute("INSERT INTO LineImplPolyline VALUES (?)", (i,))
    for i, uid in enumerate((5, 6), 1):
        c.execute("INSERT INTO Surface VALUES (?, ?, ?, 'SurfaceImplPlane')", (i, uid, i))
        c.execute("INSERT INTO SurfaceImplPlane VALUES (?)", (i,))
    for i, uid in enumerate((30, 34, 35), 1):
        c.execute("INSERT INTO Solid VALUES (?, ?, ?, 'SolidImplStandard')", (i, uid, i))
        c.execute("INSERT INTO SolidImplStandard VALUES (?)", (i,))
    c.execute("CREATE TABLE ObjectSelectionImpl (id INTEGER, isNameEnabled INTEGER, name TEXT)")
    c.execute("CREATE TABLE ObjectSelectionImpl_objectSelectors_keys (id INTEGER, container_order INTEGER, value TEXT)")
    c.execute("CREATE TABLE ObjectSelectionImpl_objectSelectors_values "
              "(id INTEGER, container_order INTEGER, conditions_id INTEGER, typeActive INTEGER)")
    c.execute("CREATE TABLE ObjectSelectionImpl_TypeSelector_Conditions (id INTEGER, version INTEGER)")
    c.execute("CREATE TABLE ObjectSelectionImpl_TypeSelector_Conditions_conditions "
              "(id INTEGER, container_order INTEGER, condition INTEGER, operator INTEGER, value_id INTEGER, "
              "value_table TEXT, hasLeftParenthesis INTEGER, hasRightParenthesis INTEGER)")
    typen = ["Node", "Line", "Member", "Member_Representant", "Surface", "Opening", "Solid", "Nodal_Support"]
    # drei Selektionen: "Bolzen" (Solid 30), "Deckel" (Surface 5, Line 10-11, Node 1, Lager), ohne Namen (Solid 34-35)
    sel = [(1, 4, 1, "Bolzen"), (2, 5, 1, "Deckel"), (3, 6, 0, "")]
    n_typ = len(typen)
    for sid, uid, benannt, name in sel:
        c.execute("INSERT INTO ObjectSelection VALUES (?, ?, ?, 'ObjectSelectionImpl')", (sid, uid, sid))
        c.execute("INSERT INTO ObjectSelectionImpl VALUES (?, ?, ?)", (sid, benannt, name))
        for k, typ in enumerate(typen):
            cid = (sid - 1) * n_typ + k + 1
            c.execute("INSERT INTO ObjectSelectionImpl_objectSelectors_keys VALUES (?, ?, ?)", (sid, k, typ))
            c.execute("INSERT INTO ObjectSelectionImpl_objectSelectors_values VALUES (?, ?, ?, 0)", (sid, k, cid))
    n_werte = len(sel) * n_typ
    if schema == "gepackt":
        # Bedingungen in einem zweiten Block dahinter (Blockgroesse n_typ + 2)
        block = n_typ + 2
        for i in range(1, n_werte + len(sel) * block + 1):
            c.execute("INSERT INTO ObjectSelectionImpl_TypeSelector_Conditions VALUES (?, 4)", (i,))
        c.execute("CREATE TABLE ObjectListConditionValue (id INTEGER, version INTEGER, attributeStringId TEXT, objects_packed TEXT)")
        werte = [(1, "id", "30"), (2, "id", "5"), (3, "id", "10-11,99"), (4, "id", "1"),
                 (5, "support_on_object", "7"), (6, "id", "34-35")]
        for w in werte:
            c.execute("INSERT INTO ObjectListConditionValue VALUES (?, 0, ?, ?)", w)

        def bed(sid, typ, value_id, order=0):
            cid = n_werte + 1 + (sid - 1) * block + typen.index(typ)
            c.execute("INSERT INTO ObjectSelectionImpl_TypeSelector_Conditions_conditions VALUES (?, ?, 0, 0, ?, 'ObjectListConditionValue', 0, 0)",
                      (cid, order, value_id))
        bed(1, "Solid", 1)
        bed(2, "Surface", 2)
        bed(2, "Line", 3)
        bed(2, "Node", 4)
        bed(2, "Nodal_Support", 5)
        bed(3, "Solid", 6)
    else:
        for i in range(1, n_werte + 1):
            c.execute("INSERT INTO ObjectSelectionImpl_TypeSelector_Conditions VALUES (?, 4)", (i,))
        c.execute("CREATE TABLE ObjectListConditionValue (id INTEGER, version INTEGER, attributeStringId TEXT)")
        c.execute("CREATE TABLE ObjectListConditionValue_model_object_indices "
                  "(id INTEGER, container_order INTEGER, objectType TEXT, userId INTEGER)")
        werte = {1: ("id", [("Solid", 30)]), 2: ("id", [("Surface", 5)]),
                 3: ("id", [("Line", 10), ("Line", 11), ("Line", 99)]), 4: ("id", [("Node", 1)]),
                 5: ("support_on_object", [("Nodal_Support", 7)]), 6: ("id", [("Solid", 34), ("Solid", 35)])}
        for vid, (attr, liste) in werte.items():
            c.execute("INSERT INTO ObjectListConditionValue VALUES (?, 0, ?)", (vid, attr))
            for k, (typ, uid) in enumerate(liste):
                c.execute("INSERT INTO ObjectListConditionValue_model_object_indices VALUES (?, ?, ?, ?)", (vid, k, typ, uid))

        def bed(sid, typ, value_id, order=0):
            cid = (sid - 1) * n_typ + typen.index(typ) + 1
            c.execute("INSERT INTO ObjectSelectionImpl_TypeSelector_Conditions_conditions VALUES (?, ?, 0, 0, ?, 'ObjectListConditionValue', 0, 0)",
                      (cid, order, value_id))
        bed(1, "Solid", 1)
        bed(2, "Surface", 2)
        bed(2, "Line", 3)
        bed(2, "Node", 4)
        bed(2, "Nodal_Support", 5)
        bed(3, "Solid", 6)
    con.commit()
    con.close()
    return pfad


def _import(schema: str):
    m = Model("rfem")
    mat = m.add_material(Material.steel("S235")).name
    m.add_nodes(np.zeros((4, 3)))
    for n, ln in (("L10", [0, 1]), ("L11", [1, 2]), ("L12", [2, 0])):
        m.add_line(n, ln)
    m.add_flaeche("F5", ["L10", "L11", "L12"], material=mat)
    m.add_flaeche("F6", ["L10", "L11", "L12"], material=mat)
    for n in ("V30", "V34", "V35"):
        m.koerper[n] = Volumenkoerper(n, ["F5"], material=mat)
    db = R6.Db(R6.connect(_db(schema)))
    log: list = []
    n = R6._object_selections(db, m, log, node_user={1: 0, 2: 1},
                              line_name={1: "L10", 2: "L11", 3: "L12"}, member_user={},
                              surf_name={1: "F5", 2: "F6"}, solid_name={1: "V30", 2: "V34", 3: "V35"})
    return m, n, log


def test_import():
    check("nummern_entpacken liest Bereiche und Einzelne",
          R6.nummern_entpacken("288-290,293, 5;7-7") == [288, 289, 290, 293, 5, 7]
          and R6.nummern_entpacken("") == [] and R6.nummern_entpacken(None) == [])
    for schema in ("gepackt", "liste"):
        m, n, log = _import(schema)
        L = m.layer
        check(f"[{schema}] drei Layer aus drei Objektselektionen", n == 3 and set(L) == {"Bolzen", "Deckel", "Objektselektion 6"},
              f"{n} {sorted(L)}")
        check(f"[{schema}] Bolzen = Volumen 30", L.get("Bolzen") is not None and L["Bolzen"].koerper == ["V30"]
              and L["Bolzen"].quelle == "rfem", str(L.get("Bolzen")))
        d = L.get("Deckel")
        check(f"[{schema}] Deckel: Flaeche 5, Linien 10-11 (99 fehlt), Knoten 1 -> Index 0; Lagerbedingung uebergangen",
              d is not None and d.flaechen == ["F5"] and d.linien == ["L10", "L11"] and d.knoten == [0] and not d.koerper,
              str(d))
        check(f"[{schema}] ohne Namen heisst nach der Nummer; Volumen 34-35",
              L.get("Objektselektion 6") is not None and L["Objektselektion 6"].koerper == ["V34", "V35"])
        check(f"[{schema}] Protokoll nennt Layer und Uebergangenes",
              any("Layer Bolzen" in z for z in log) and any("support_on_object" in z for z in log)
              and (schema != "gepackt" or any("blockweise" in z for z in log)), " | ".join(log)[:200])
    # ohne die Tabellen passiert nichts
    m = Model("leer")
    pfad = os.path.join(tempfile.mkdtemp(prefix="statik3d_layer0_"), "model.db")
    sqlite3.connect(pfad).close()
    db = R6.Db(R6.connect(pfad))
    check("ohne Objektselektionen bleibt das Modell ohne Layer",
          R6._object_selections(db, m, [], {}, {}, {}, {}, {}) == 0 and not m.layer)


def main():
    for t in (test_modell, test_import):
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
    sys.exit(main())
