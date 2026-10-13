"""
Lastfaelle beim Import und in Kombinationen (Entscheidung des Anwenders vom
13.10.2026, Zweig import/lastfaelle):

* Kategorie „nicht zugeordnet“ (NZ) statt Q, wo die Quelle die Einwirkung nicht
  eindeutig sagt; Kombinationen mit so einem Lastfall werden nicht gerechnet
  (Bedienhinweis, kein Absturz), einzelne Lastfaelle schon; alte Dateien behalten
  ihre Kategorie;
* Kennzeichen „Bemessungslastfall, bereits faktorisiert“: gamma = 1,0, kein psi,
  im Bericht, gespeichert; der Import setzt es nur bei eindeutiger Datenlage,
  der Name allein schlaegt es nur vor;
* Vorspannung: Kategorie P mit gamma_P = 1,0; eine aus RFEM umgerechnete
  Vorspannung steht als Kraft mit E und alpha da, nicht als Temperatur.

Aufruf:  python -m tests.test_lastfall_kategorie
"""
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
    tempfile.mkdtemp(prefix="statik3d_lastfall_kat_"), "einstellungen.json")

RESULTS = []
SATZ = "Vorspannung 952 kN (eingeprägte Dehnung, E = 170 000 N/mm², α = 1,0e-5 1/K)"


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:84s} {detail}")
    return ok


# --------------------------------------------------------------------------
# Hilfen
# --------------------------------------------------------------------------
def _balken(extra_faelle=()):
    """Kragarm mit drei Lastfaellen: LF1 (G), LF2 (NZ) und weitere."""
    from statik3d.model import Model, Material, Section
    m = Model("Probe")
    m.add_material(Material.steel("S355"))
    m.add_section(Section.from_profile("HEB 300"))
    n = [m.add_node(3.0 * i, 0.0, 0.0) for i in range(3)]
    for i in range(2):
        m.add_element("beam", [n[i], n[i + 1]], "S355", "HEB 300")
    m.support(n[0], "all", name="Einspannung")
    m.load_cases["LF1"].category = "G"
    m.load_node(n[-1], Fz=-5e3, case="LF1")
    m.add_load_case("LF2", "NZ", "ohne Einwirkung", activate=False)
    m.load_node(n[-1], Fz=-2e3, case="LF2")
    for name, kat in extra_faelle:
        m.add_load_case(name, kat, activate=False)
        m.load_node(n[-1], Fz=-1e3, case=name)
    return m


def _ausnahme(f, *a, **kw):
    try:
        f(*a, **kw)
    except Exception as ex:      # noqa: BLE001
        return ex
    return None


# --------------------------------------------------------------------------
# 1) Kategorie, Speichern, alte Dateien
# --------------------------------------------------------------------------
def test_kategorie_und_alte_dateien():
    from statik3d.model import ACTION_CATEGORIES, LoadCase, TempLoad, Model
    check("die Kategorie „nicht zugeordnet“ gibt es (Schluessel NZ)",
          "NZ" in ACTION_CATEGORIES and "nicht zugeordnet" in ACTION_CATEGORIES["NZ"][0],
          str(ACTION_CATEGORIES.get("NZ")))
    check("… sie steht hinter G in der Auswahl, G bleibt die Vorgabe der Maske",
          list(ACTION_CATEGORIES)[0] == "G")
    lc = LoadCase("LF1", "NZ")
    check("ein Lastfall ohne Einwirkung ist weder ständig noch veränderlich noch außergewöhnlich",
          not (lc.is_permanent or lc.is_variable or lc.is_accidental))
    check("… und seine Kombinationen sind gesperrt", lc.kombination_gesperrt and lc.kategorie_offen)
    lc.faktorisiert = True
    check("… außer er ist ein Bemessungslastfall (gamma und psi stehen dann fest)",
          not lc.kombination_gesperrt and lc.kategorie_offen)
    # alte Datei: keine Felder der neuen Fassung
    alt = {"name": "LF7", "category": "Q", "description": "alt", "nodal_loads": [], "beam_loads": [],
           "face_loads": [], "temp_loads": [{"elem": 3, "dT": -12.5, "dT_z": 0.0}], "gravity": [0, 0, 0]}
    lc = LoadCase.from_dict(alt)
    check("alte Datei: die Kategorie bleibt Q, das Kennzeichen fehlt (False)",
          lc.category == "Q" and lc.faktorisiert is False and not lc.kombination_gesperrt,
          f"{lc.category} {lc.faktorisiert}")
    t = lc.temp_loads[0]
    check("alte Datei: die Temperaturlast bleibt eine Temperaturlast (kein Merkmal)",
          t.aus_vorspannung == 0.0 and not t.ist_vorspannung and t.vorspann_text() == ""
          and "ΔT = -12.5 K" in t.bezug(None), t.bezug(None))
    d = lc.to_dict()
    check("… und gespeichert steht sie wie vorher (das Kennzeichen steht nur, wo es gesetzt ist)",
          set(d["temp_loads"][0]) == {"elem", "dT", "dT_z"} and d["category"] == "Q"
          and "faktorisiert" not in d, str(d["temp_loads"][0]))
    # neu: speichern und laden
    lc = LoadCase("LF9", "NZ")
    lc.faktorisiert = True
    lc.temp_loads.append(TempLoad(4, -445.634, 0.0, 952e3, 170e9, 1e-5))
    lc2 = LoadCase.from_dict(lc.to_dict())
    t2 = lc2.temp_loads[0]
    check("neu: Kategorie, Kennzeichen und Merkmal „aus Vorspannung“ überstehen Speichern und Laden",
          lc2.category == "NZ" and lc2.faktorisiert and t2.aus_vorspannung == 952e3
          and t2.vorspann_E == 170e9 and t2.vorspann_alpha == 1e-5, str(t2))
    m = Model("x")
    m.load_cases["LF9"] = lc
    m2 = Model.from_dict(m.to_dict())
    check("… auch durch das ganze Modell",
          m2.load_cases["LF9"].faktorisiert and m2.load_cases["LF9"].temp_loads[0].aus_vorspannung == 952e3)


# --------------------------------------------------------------------------
# 2) Sperre der Kombinationen
# --------------------------------------------------------------------------
def test_sperre():
    from statik3d import solver
    from statik3d.model import Combination, KombinationGesperrt
    m = _balken()
    m.combinations["K1"] = Combination("K1", {"LF1": 1.35, "LF2": 1.5}, "ULS")
    m.combinations["K2"] = Combination("K2", {"LF1": 1.0}, "SLS_CH")
    m.combinations["EK1"] = Combination("EK1", {}, "ULS", alternativen=[{"LF1": 1.0}, {"LF2": 1.0}])
    check("gesperrt sind genau die Kombinationen mit dem Lastfall ohne Einwirkung",
          m.gesperrte_kombinationen() == {"K1": ["LF2"], "EK1": ["LF2"]}, str(m.gesperrte_kombinationen()))
    text = m.sperrhinweis()
    check("der Hinweis nennt den Lastfall, die Kombinationen und den Weg zur Zuordnung",
          "LF2" in text and "K1" in text and "EK1" in text and "Modellbaum" in text
          and "Einwirkung" in text and "Bemessungslastfall" in text and "Nur aktiver Lastfall" in text,
          text.splitlines()[0])
    ex = _ausnahme(solver.solve_combination, m, m.combinations["K1"])
    check("eine gesperrte Kombination rechnet nicht: KombinationGesperrt, kein Absturz",
          isinstance(ex, KombinationGesperrt) and isinstance(ex, ValueError) and "LF2" in str(ex), repr(ex)[:80])
    check("… die Ausnahme trägt Kombination und Lastfall",
          getattr(ex, "kombinationen", None) == {"K1": ["LF2"]} and getattr(ex, "lastfaelle", None) == ["LF2"])
    check("eine Kombination ohne ihn rechnet", _ausnahme(solver.solve_combination, m, m.combinations["K2"]) is None)
    ex = _ausnahme(solver.umhuellende_der_kombination, m, m.combinations["EK1"], {})
    check("auch die Alternative einer Ergebniskombination ist gesperrt", isinstance(ex, KombinationGesperrt),
          repr(ex)[:80])
    ex = _ausnahme(solver.solve_all, m)
    check("‚Alle Lastfälle + Kombinationen‘ startet nicht, mit demselben Hinweis (vor dem ersten Lastfall)",
          isinstance(ex, KombinationGesperrt) and ex.kombinationen == m.gesperrte_kombinationen(), repr(ex)[:80])
    an = solver.solve_all(m, combinations=False)
    check("ohne Kombinationen rechnen alle Lastfälle", set(an.cases) == {"LF1", "LF2"}, str(sorted(an.cases)))
    r = solver.solve_static(m, case="LF2")
    check("ein einzelner Lastfall ohne Einwirkung bleibt rechenbar", r is not None and abs(r.u).max() > 0)
    msgs = m.check()
    check("die Modellprüfung meldet es als Warnung, nicht als Fehler",
          any(z.startswith("WARNUNG") and "LF2" in z and "gesperrt" in z for z in msgs)
          and not any(z.startswith("FEHLER") for z in msgs), str([z[:60] for z in msgs]))
    # zugeordnet -> frei
    m.load_cases["LF2"].category = "Q"
    check("mit zugeordneter Einwirkung ist nichts mehr gesperrt", m.gesperrte_kombinationen() == {}
          and m.sperrhinweis() == "")
    an = solver.solve_all(m)
    check("… und ‚Alle Lastfälle + Kombinationen‘ rechnet", {"K1", "K2"} <= set(an.combinations)
          and "EK1" in an.envelopes or "EK1" in str(an.envelopes), str(sorted(an.combinations)))
    # Bemessungslastfall
    m.load_cases["LF2"].category = "NZ"
    m.load_cases["LF2"].faktorisiert = True
    check("ein Bemessungslastfall ohne Einwirkung hält keine Kombination auf",
          m.gesperrte_kombinationen() == {})
    check("… die Rechnung läuft", _ausnahme(solver.solve_all, m) is None)


def test_kommandozeile_hinweis_statt_absturz():
    import contextlib
    import io
    from statik3d import cli
    from statik3d.model import Combination
    m = _balken()
    m.combinations["K1"] = Combination("K1", {"LF1": 1.35, "LF2": 1.5}, "ULS")
    pfad = os.path.join(tempfile.mkdtemp(prefix="statik3d_lfkat_cli_"), "m.json")
    m.save(pfad)
    err, out = io.StringIO(), io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
        rc = cli.main([pfad])
    check("Kommandozeile: gesperrte Kombination -> Hinweis auf stderr und Rueckgabe 2, kein Absturz",
          rc == 2 and "Kombinationen gesperrt" in err.getvalue() and "LF2" in err.getvalue(),
          f"rc {rc}, {err.getvalue()[:80]!r}")


def test_generator_weigert_sich():
    from statik3d.combinations import generate_combinations
    from statik3d.model import Combination, KombinationGesperrt
    m = _balken()
    m.combinations["Hand"] = Combination("Hand", {"LF1": 1.0}, "USER")
    ex = _ausnahme(generate_combinations, m)
    check("der Generator weigert sich bei einem Lastfall ohne Einwirkung (statt ihn still wegzulassen)",
          isinstance(ex, KombinationGesperrt) and "LF2" in str(ex) and "Modellbaum" in str(ex), repr(ex)[:90])
    check("… und lässt die vorhandenen Kombinationen stehen", list(m.combinations) == ["Hand"])
    m.load_cases["LF2"].category = "Q"
    cs = generate_combinations(m)
    check("mit Einwirkung erzeugt er wie gewohnt", len(cs) > 0 and any("LF2" in c.factors for c in cs))


# --------------------------------------------------------------------------
# 3) Bemessungslastfall und gamma_P
# --------------------------------------------------------------------------
def test_bemessungslastfall_im_generator():
    from statik3d.combinations import generate_combinations, _gamma
    from statik3d.model import Model
    m = _balken(extra_faelle=[("LF3", "Q")])
    m.load_cases["LF2"].faktorisiert = True            # NZ + Bemessungslastfall
    ds = m.design
    check("gamma eines Bemessungslastfalls ist 1,0 (günstig und ungünstig)",
          _gamma(m.load_cases["LF2"], ds, False) == 1.0 and _gamma(m.load_cases["LF2"], ds, True) == 1.0)
    # auch mit einer Einwirkung gilt 1,0, nicht gamma_Q
    m.load_cases["LF3"].faktorisiert = True
    check("… auch wenn der Lastfall eine Einwirkung hat (Q würde 1,5 geben)",
          _gamma(m.load_cases["LF3"], ds, False) == 1.0)
    m.load_cases["LF3"].faktorisiert = False
    cs = generate_combinations(m)
    mit = [c for c in cs if "LF2" in c.factors]
    check("der Generator bildet für ihn eine eigene GZT-Kombination mit 1,0",
          len(mit) == 1 and mit[0].factors == {"LF2": 1.0} and mit[0].typ == "ULS", str([c.factors for c in mit]))
    check("… beschrieben als Bemessungslastfall",
          "Bemessungslastfall" in mit[0].description and "faktorisiert" in mit[0].description, mit[0].description)
    check("… er wird nicht mit anderen Lastfällen überlagert und nicht in GZG-Kombinationen genommen",
          all(len(c.factors) == 1 for c in mit) and all(c.typ == "ULS" for c in mit))
    check("die übrigen Lastfälle werden unverändert kombiniert (1,35·G + 1,5·Q)",
          any(c.factors == {"LF1": 1.35, "LF3": 1.5} for c in cs), str([c.factors for c in cs][:6]))


def test_vorspannung_gamma_p():
    from statik3d.combinations import generate_combinations
    from statik3d.model import Model
    m = _balken(extra_faelle=[("LF3", "P"), ("LF4", "Q")])
    m.load_cases["LF2"].category = "G"
    cs = generate_combinations(m, sls=False, accidental=False)
    gzt = [c for c in cs if c.typ == "ULS"]
    g_ungue = [c for c in gzt if "LF4" in c.factors and c.factors.get("LF1") == 1.35]
    check("Vorspannung P geht mit gamma_P = 1,0 ein, G mit 1,35, Q mit 1,5 (ungünstig)",
          g_ungue and all(c.factors.get("LF3") == 1.0 and c.factors.get("LF2") == 1.35 for c in g_ungue)
          and any(c.factors.get("LF4") == 1.5 for c in g_ungue), str([c.factors for c in g_ungue][:2]))
    g_guen = [c for c in gzt if "LF4" in c.factors and c.factors.get("LF1") == 1.0]
    check("… auch in der günstigen Variante 1,0 (nicht gamma_G,inf nur zufällig)",
          g_guen and all(c.factors.get("LF3") == 1.0 for c in g_guen), str([c.factors for c in g_guen][:2]))
    check("gamma_P steht in den Einstellungen und ist 1,0", m.design.gamma_P == 1.0)
    m.design.gamma_P = 1.2
    cs = generate_combinations(m, sls=False, accidental=False)
    check("… und ist einstellbar", any(c.factors.get("LF3") == 1.2 for c in cs if c.typ == "ULS"))
    # eigenes gamma am Lastfall geht vor
    m.load_cases["LF3"].gamma_sup = 1.1
    cs = generate_combinations(m, sls=False, accidental=False)
    check("ein eigenes gamma am Lastfall geht vor", any(c.factors.get("LF3") == 1.1 for c in cs if c.typ == "ULS"))


def test_gemischter_lastfall_mit_vorspannung():
    """Wie ein Lastfall mit Vorspannung UND anderen Lasten kombiniert wird: als
    Ganzes, mit dem gamma seiner Einwirkung (belegt, nicht angenommen)."""
    from statik3d.combinations import generate_combinations
    from statik3d.model import TempLoad
    m = _balken(extra_faelle=[("LF3", "Q")])
    m.load_cases["LF2"].category = "G"
    m.load_cases["LF3"].temp_loads.append(TempLoad(0, -100.0, 0.0, 500e3, 210e9, 1.2e-5))
    cs = generate_combinations(m, sls=False, accidental=False)
    q = [c for c in cs if c.typ == "ULS" and c.leading == "LF3"]
    check("gemischter Lastfall (Q-Last + Vorspannung): die Kombination gibt ihm als Ganzem gamma_Q = 1,5",
          q and all(c.factors["LF3"] == 1.5 for c in q), str([c.factors for c in q][:2]))
    check("… die Vorspannung darin bekommt also nicht gamma_P = 1,0 – deshalb meldet der Import es",
          m.design.gamma_P == 1.0 and q[0].factors["LF3"] != m.design.gamma_P)
    m.load_cases["LF3"].faktorisiert = True
    cs = generate_combinations(m, sls=False, accidental=False)
    own = [c for c in cs if c.factors == {"LF3": 1.0}]
    check("als Bemessungslastfall gekennzeichnet gilt für alles darin 1,0", len(own) == 1)


def test_din19704_generator_sperre():
    """Der Generator nach DIN 19704 liesse einen Lastfall ohne Einwirkung genauso
    still weg (er steht in keiner Einwirkungsart des Regelwerks)."""
    from statik3d.bridges.din19704 import Regelwerk
    from statik3d.model import KombinationGesperrt
    m = _balken()
    rw = Regelwerk()
    ex = _ausnahme(rw.kombinationen, m)
    check("DIN 19704: der Generator weigert sich bei einem Lastfall ohne Einwirkung",
          isinstance(ex, KombinationGesperrt) and "LF2" in str(ex), repr(ex)[:90])
    check("… und legt nichts an", not m.combinations)
    m.load_cases["LF2"].faktorisiert = True
    log = []
    namen = rw.kombinationen(m, log=log)
    check("als Bemessungslastfall ist er kein Hindernis, wird aber nicht mit gamma ein zweites Mal kombiniert",
          not any("LF2" in m.combinations[n].factors for n in namen)
          and any("Bemessungslastfälle" in z and "LF2" in z for z in log), str(log))


def test_lastart_titel():
    from statik3d.model import TempLoad
    m = _balken()
    lc = m.load_cases["LF1"]
    lc.temp_loads.append(TempLoad(0, 20.0))
    check("Lastart Temperatur: ohne Vorspannung heisst sie Temperaturlasten",
          lc.lastart_titel("temperatur") == "Temperaturlasten", lc.lastart_titel("temperatur"))
    lc.temp_loads.clear()
    lc.temp_loads.append(TempLoad(0, -445.6, 0.0, 952e3, 170e9, 1e-5))
    check("… sind alle aus einer Vorspannung, heisst sie Vorspannung (eingeprägte Dehnung) – im Baum und in der Maske",
          lc.lastart_titel("temperatur") == "Vorspannung (eingeprägte Dehnung)", lc.lastart_titel("temperatur"))
    lc.temp_loads.append(TempLoad(1, 20.0))
    check("… gemischt bleibt es bei Temperaturlasten", lc.lastart_titel("temperatur") == "Temperaturlasten")
    check("andere Lastarten behalten ihren Titel", lc.lastart_titel("knoten") == "Knotenlasten")


# --------------------------------------------------------------------------
# 4) Vorspannung als Kraft: Text, Tabelle, Bericht
# --------------------------------------------------------------------------
def test_vorspannung_als_kraft_text():
    from statik3d.model import TempLoad
    t = TempLoad(13, -445.634, 0.0, 952e3, 170e9, 1e-5)
    check("der Satz: Kraft, eingeprägte Dehnung, E und alpha", t.vorspann_text() == SATZ, t.vorspann_text())
    check("in der Ansicht mit Dezimalpunkt", t.vorspann_text(punkt=True).endswith("α = 1.0e-5 1/K)"),
          t.vorspann_text(punkt=True))
    check("die Bezeichnung der Last nennt die Kraft, nicht ΔT",
          t.bezug(None) == "Element 13: " + SATZ and "ΔT" not in t.bezug(None), t.bezug(None))
    check("eine gewöhnliche Temperaturlast bleibt, wie sie war",
          TempLoad(2, 20.0).vorspann_text() == "" and "ΔT = +20.0 K" in TempLoad(2, 20.0).bezug(None))
    t2 = TempLoad(1, -376.823, 0.0, 805e3, 170e9, 1e-5)
    check("805 kN", "Vorspannung 805 kN (" in t2.vorspann_text())
    check("ohne E und alpha (alte Merkmale) steht nur, was bekannt ist",
          TempLoad(1, -1.0, 0.0, 100e3).vorspann_text() == "Vorspannung 100 kN (eingeprägte Dehnung)",
          TempLoad(1, -1.0, 0.0, 100e3).vorspann_text())


def test_bericht():
    from statik3d import solver
    from statik3d.model import TempLoad
    from statik3d.report import html as rh
    m = _balken(extra_faelle=[("LF3", "P")])
    m.load_cases["LF1"].faktorisiert = True
    m.load_cases["LF1"].category = "NZ"
    m.load_cases["LF3"].temp_loads.append(TempLoad(0, -445.634, 0.0, 952e3, 170e9, 1e-5))
    m.load_cases["LF3"].temp_loads.append(TempLoad(1, -445.634, 0.0, 952e3, 170e9, 1e-5))
    m.load_cases["LF2"].category = "NZ"
    an = solver.solve_all(m, combinations=False)
    rep = rh.Report(m, an)
    kap = rep.chapter_actions()
    text = " ".join(str(b) for b in kap)
    check("Bericht: die Vorspannung steht als Kraft mit E und alpha",
          SATZ in text, "kein Satz" if SATZ not in text else "")
    check("… nicht als Temperaturlast ΔT",
          "Temperaturlasten Lastfall LF3" not in text and "ΔT [K]" not in text.split("Vorspannung Lastfall LF3")[-1][:400])
    check("Bericht: das Kennzeichen Bemessungslastfall steht bei LF1",
          "Bemessungslastfall, bereits faktorisiert" in text)
    tab = next(b for b in kap if b[0] == "table" and "Einwirkungskategorien" in str(b[2]))
    zeilen = {r[0]: r for r in tab[1][1:]}
    check("… mit gamma 1,00 und ohne psi", zeilen["LF1"][4:7] == ["–", "–", "–"] and zeilen["LF1"][7] == "1.00"
          or zeilen["LF1"][7] in ("1,00", "1.00"), str(zeilen["LF1"]))
    check("Bericht: ein Lastfall ohne Einwirkung zeigt – bei gamma und psi (kein erfundener Wert)",
          zeilen["LF2"][4:9] == ["–", "–", "–", "–", "–"] and zeilen["LF2"][1] == "NZ", str(zeilen["LF2"]))
    check("Bericht: die Vorspannung P steht mit gamma_P = 1,00",
          zeilen["LF3"][7] in ("1,00", "1.00") and zeilen["LF3"][8] in ("1,00", "1.00"), str(zeilen["LF3"]))
    from statik3d.report import svg as sv
    m.load_cases["LF3"].category = "P"
    s = sv.draw_structure(m, "iso", 600, 400, show_supports=True, show_loads=True, case=m.load_cases["LF3"])
    check("Lastbild: „2 Vorspannungen (952 kN …)“ statt Temperaturlasten",
          "2 Vorspannungen (952 kN" in s and "Temperaturlasten" not in s)


# --------------------------------------------------------------------------
# 5) RFEM-Import mit nachgebauter Datenbank
# --------------------------------------------------------------------------
def _rf6(pfad, aktionen=(), **kw):
    """Wie tests.test_rfem6.make_rf6, mit Aktionen des Kombinationsassistenten:
    aktionen = [(Name, Kennzahl, [Lastfall-ids])]."""
    from tests import test_rfem6 as T
    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "model.db")
    T.build_db(db, **kw)
    if aktionen:
        con = sqlite3.connect(db)
        con.executescript("""
            CREATE TABLE Action (id INTEGER PRIMARY KEY, version INTEGER, userID INTEGER,
                                 impl_id bigint, impl_table TEXT);
            CREATE TABLE ActionImpl (id INTEGER PRIMARY KEY, version INTEGER, name TEXT,
                                     parent_id bigint, actionCategoryId INTEGER);
            CREATE TABLE ActionImpl_items (id INTEGER, container_order INTEGER,
                                           actingGroupNumber INTEGER, loadCase_id bigint,
                                           loadCase_table TEXT);""")
        for i, (name, kz, lfs) in enumerate(aktionen, 1):
            con.execute("INSERT INTO Action VALUES (?,1,?,?,'ActionImpl')", (i, i, i))
            con.execute("INSERT INTO ActionImpl VALUES (?,1,?,?,?)", (i, name, i, kz))
            for j, lf in enumerate(lfs):
                con.execute("INSERT INTO ActionImpl_items VALUES (?,?,0,?,'LoadCase')", (i, j, lf))
        con.commit()
        con.close()
    with zipfile.ZipFile(pfad, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(db, "model.db")
        z.writestr("format.txt", "RFEM\n6.11.0004\nRFEM6\n6.12.0010\n1773229130\n")
        z.writestr("general_data.xml", "<?xml version='1.0'?><property key='generalData'/>")
    shutil.rmtree(tmp, ignore_errors=True)
    return pfad


def _drehlager_klein(tmp, **extra):
    """Ein Zugstab mit zehn Lastfaellen, alle mit der Kennzahl 11 wie am
    Drehlager - bis auf zwei mit eigener Kennzahl."""
    from tests import test_rfem6 as T
    INF = T.INF
    namen = [
        ("Staendige Last Aufbau", 11, 0.0),                              # 1: nur der Name sagt G
        ("Verkehrslage Fall 1", 11, 0.0),                                # 2: Q nach dem Namen
        ("Bemessungslast im GZT - Fall 1", 11, 0.0),                     # 3: GZT-Alternative 1,0
        ("char.Last - Fall 1", 11, 0.0),                                 # 4: GZG-Alternative 1,0
        ("Vorspannung der Anker", 11, 0.0),                              # 5: nur Vorspannlast
        ("Ermuedungslast Zug 1", 11, 0.0),                               # 6: nur FAT-Kombination
        ("Wind in +X", 61, 0.0),                                         # 7: Kennzahl W
        ("Nutzlast", 32, 0.0),                                           # 8: Kennzahl Q_A
        ("Bemessungslast nur im Namen", 11, 0.0),                        # 9: in keiner Kombination
        ("Bemessungslast char. vorsicht", 11, 0.0),                      # 10: GZT 1,0, aber „char.“
        ("Eigengewicht", 11, 1.0),                                       # 11: nur Eigengewicht
    ]
    return T.make_rf6(
        os.path.join(tmp, "klein.rf6"),
        nodes=[(0, 0, 0), (2, 0, 0)], lines=[[1, 2]], members=[(1, None, None)],
        supports=[("Fest", (INF,) * 6, (0,) * 6, None, [1])],
        load_cases=namen,
        nodal_loads=[(i, [2], (0.0, 0.0, -1e3 * i), (0.0, 0.0, 0.0)) for i in (1, 2, 3, 4, 6, 7, 8, 9, 10)],
        prestress=[(5, [1], 120e3)],
        bemessungssituationen=[("GZT", "GZT - staendig", 7007), ("GZG", "GZG char", 6193),
                               ("FAT", "GZT (FAT) - Ermuedung", 7505)],
        combinations=[("EK Bemessung", 0, {3: 1.0, 10: 1.0}, 1, [0, 2]),
                      ("EK char", 1, {4: 1.0}, 2, [2]),
                      ("EK Ermuedung", 0, {6: 1.0}, 3, [2])], **extra)


def test_import_kategorien():
    from statik3d.importers import rfem6_db as R6
    from statik3d import solver
    from statik3d.model import KombinationGesperrt
    tmp = tempfile.mkdtemp()
    try:
        log = []
        m = R6.read_rf6(_drehlager_klein(tmp), log=log)
        txt = "\n".join(log)
        kat = {n: lc.category for n, lc in m.load_cases.items()}
        check("Kennzahl 11 sagt nichts: „Staendige Last“ und Verkehr bleiben nicht zugeordnet (nicht Q, nicht G)",
              kat["LF1"] == "NZ" and kat["LF2"] == "NZ", str(kat))
        check("nur Eigengewicht -> G (aus dem Inhalt: Eigengewicht ist nach DIN EN 1990 staendig)",
              kat["LF11"] == "G", kat["LF11"])
        check("auch der Name setzt keine Einwirkung (er schlägt sie nur vor)",
              kat["LF1"] == "NZ" and "Vorschlag nach dem Namen (nicht gesetzt): G für LF1" in txt,
              next((z for z in log if "Vorschlag nach dem Namen" in z), "keine Zeile"))
        check("eine eigene Kennzahl gilt: 61 -> W, 32 -> Q_A (Aufzählung der Dlubal-API)",
              kat["LF7"] == "W" and kat["LF8"] == "Q_A", f"{kat['LF7']} {kat['LF8']}")
        check("nur in Ermüdungskombinationen -> FAT (aus der Struktur, nicht aus dem Namen)",
              kat["LF6"] == "FAT", kat["LF6"])
        check("nur Vorspannlasten -> P", kat["LF5"] == "P", kat["LF5"])
        check("der Rest: nicht zugeordnet", kat["LF4"] == "NZ" and kat["LF9"] == "NZ", f"{kat['LF4']} {kat['LF9']}")
        check("das Protokoll nennt die Lastfälle ohne Einwirkung und den Weg zur Zuordnung",
              any(z.startswith("WARNUNG") and "ohne zugeordnete Einwirkung" in z and "LF4" in z
                  and "Modellbaum" in z for z in log),
              next((z[:100] for z in log if "ohne zugeordnete" in z), "keine Zeile"))
        check("das Protokoll sagt zur Kennzahl 11: Vorgabe jedes neuen Lastfalls",
              any("Kennzahl 11" in z and "Vorgabe" in z for z in log))
        check("keine Annahme „11 -> Q“ mehr", "11 -> Q" not in txt and "angenommen" not in txt)
        # Kennzeichen
        fak = {n: lc.faktorisiert for n, lc in m.load_cases.items()}
        check("Bemessungslastfall: LF3 steht nur in der GZT-Kombination, allein, mit 1,0 -> gesetzt",
              fak["LF3"], str(fak))
        check("… LF4 (GZG), LF6 (FAT), LF9 (keine Kombination) nicht",
              not fak["LF4"] and not fak["LF6"] and not fak["LF9"])
        check("… LF10 steht mit 1,0 in der GZT-Kombination, heißt aber „char.“: nicht gesetzt, gemeldet",
              not fak["LF10"] and any("LF10" in z and "charakteristisch" in z for z in log),
              next((z[:100] for z in log if "charakteristisch" in z), "keine Zeile"))
        check("… LF9 heißt Bemessungslast, die Datei sagt es nicht: nur ein Vorschlag, nichts gesetzt",
              any("Vorschlag" in z and "Bemessungslastfall" in z and "LF9" in z for z in log))
        check("das Protokoll nennt das Kennzeichen und seinen Grund",
              any("als Bemessungslastfall" in z and "LF3" in z and "Faktor 1,0" in z for z in log),
              next((z[:100] for z in log if "als Bemessungslastfall" in z), "keine Zeile"))
        # Sperre am importierten Modell
        gesperrt = m.gesperrte_kombinationen()
        check("Kombinationen: die mit LF4 (nicht zugeordnet) und LF10 sind gesperrt, die Bemessung mit LF3 allein nicht",
              "EK char" in gesperrt and gesperrt["EK char"] == ["LF4"], str(gesperrt))
        ex = _ausnahme(solver.solve_all, m)
        check("‚Alle Lastfälle + Kombinationen‘: Hinweis mit den Namen, kein Absturz",
              isinstance(ex, KombinationGesperrt) and "LF4" in str(ex), repr(ex)[:80])
        r = solver.solve_static(m, case="LF4")
        check("der Lastfall LF4 selbst rechnet", r is not None and abs(r.u).max() > 0)
        for n, c in list(m.combinations.items()):
            if n in gesperrt:
                m.combinations.pop(n)
        check("ohne die gesperrten Kombinationen rechnet alles, auch die Bemessungs-EK mit dem Kennzeichen",
              _ausnahme(solver.solve_all, m) is None)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_import_aktion_gilt():
    from statik3d.importers import rfem6_db as R6
    tmp = tempfile.mkdtemp()
    try:
        f = _rf6(os.path.join(tmp, "aktion.rf6"),
                 aktionen=[("Ständig", 11, [1]), ("Nutzlast A", 32, [2]), ("Wind", 61, [3, 4])],
                 nodes=[(0, 0, 0), (2, 0, 0)], lines=[], members=[], supports=[],
                 load_cases=[("Staendige Last", 11, 0.0), ("Nutzlast", 11, 0.0),
                             ("Wind +X", 11, 0.0), ("Wind -X", 61, 0.0), ("Ohne Aktion", 11, 0.0)])
        log = []
        m = R6.read_rf6(f, log=log)
        kat = {n: lc.category for n, lc in m.load_cases.items()}
        check("Aktion des Kombinationsassistenten mit anderer Kennzahl: dort hat der Aufsteller gewählt "
              "(LF2 -> Q_A, LF3 und LF4 -> W), obwohl die 11 des Lastfalls nichts sagt",
              kat["LF2"] == "Q_A" and kat["LF3"] == "W" and kat["LF4"] == "W", str(kat))
        check("eine Aktion mit der Vorgabe 11 sagt auch nichts (so beginnt jede neue Aktion): LF1 bleibt offen",
              kat["LF1"] == "NZ", str(kat))
        check("… ein Lastfall in keiner Aktion mit der Kennzahl 11 bleibt nicht zugeordnet",
              kat["LF5"] == "NZ", str(kat))
        check("das Protokoll sagt, woher die Einwirkung kommt",
              any("aus einer Aktion" in z for z in log), next((z for z in log if "Aktion" in z), "keine Zeile"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_import_widerspruch():
    from statik3d.importers import rfem6_db as R6
    tmp = tempfile.mkdtemp()
    try:
        f = _rf6(os.path.join(tmp, "wider.rf6"), aktionen=[("Wind", 61, [1])],
                 nodes=[(0, 0, 0), (2, 0, 0)], lines=[], members=[], supports=[],
                 load_cases=[("Eigengewicht", 32, 1.0)])
        log = []
        m = R6.read_rf6(f, log=log)
        check("nennt die Aktion eine andere Einwirkung als der Lastfall selbst: nicht raten",
              m.load_cases["LF1"].category == "NZ" and any("verschiedene Einwirkungen" in z for z in log),
              m.load_cases["LF1"].category)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_import_vorspannung_als_kraft():
    from statik3d.importers import rfem6_db as R6
    tmp = tempfile.mkdtemp()
    try:
        log = []
        m = R6.read_rf6(_drehlager_klein(tmp), log=log)
        lf5 = m.load_cases["LF5"]
        t = lf5.temp_loads[0]
        e = m.elements[t.elem]
        mat = m.materials[e.mat]
        check("die umgerechnete Vorspannung trägt das Merkmal: Kraft, E und alpha der Umrechnung",
              t.aus_vorspannung == 120e3 and abs(t.vorspann_E - mat.E) < 1e-3
              and abs(t.vorspann_alpha - mat.alpha) < 1e-18, str(t))
        check("angezeigt als Kraft mit E und alpha, nicht als ΔT",
              t.bezug(m).startswith("Element 0: Vorspannung 120 kN (eingeprägte Dehnung, E = ")
              and "ΔT" not in t.bezug(m), t.bezug(m))
        check("gerechnet wird weiter mit dT = -N0/(E·A·alpha)",
              abs(t.dT + 120e3 / (mat.E * m.sections[e.sec].A * mat.alpha)) < 1e-9, f"{t.dT:.4f}")
        check("das Protokoll nennt das verwendete E und alpha (bis zur kraftgesteuerten Vorspannung)",
              any("Angezeigt wird die Vorspannung als Kraft" in z and "E = " in z and "α = " in z
                  and "N/mm²" in z for z in log), next((z for z in log if "Angezeigt wird" in z), "keine Zeile"))
        check("der reine Vorspannungslastfall hat Einwirkung P, gamma_P = 1,0",
              lf5.category == "P" and m.design.gamma_P == 1.0)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_import_gemischter_lastfall_wird_gemeldet():
    from statik3d.importers import rfem6_db as R6
    from tests import test_rfem6 as T
    tmp = tempfile.mkdtemp()
    try:
        f = T.make_rf6(
            os.path.join(tmp, "gemischt.rf6"),
            nodes=[(0, 0, 0), (2, 0, 0)], lines=[[1, 2]], members=[(1, None, None)],
            supports=[("Fest", (T.INF,) * 6, (0,) * 6, None, [1])],
            load_cases=[("Nutzlast samt Vorspannung", 32, 0.0)],
            nodal_loads=[(1, [2], (0.0, 0.0, -1e3), (0.0, 0.0, 0.0))],
            prestress=[(1, [1], 120e3)])
        log = []
        m = R6.read_rf6(f, log=log)
        check("Vorspannung und Last in einem Lastfall (Q_A): der Import meldet, dass die Vorspannung dort "
              "das gamma der Einwirkung bekäme",
              any(z.startswith("WARNUNG") and "Vorspannung mit anderen Lasten" in z and "γ_P = 1,0" in z
                  and "LF1" in z and "1 Lastfall mischt" in z for z in log),
              next((z[:90] for z in log if "mischen" in z or "mischt" in z), "keine Zeile"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_alte_datei_bleibt():
    """Eine Datei von vor dem 13.10.2026 wird beim Laden nicht verändert."""
    import json
    from statik3d.model import Model
    m = _balken(extra_faelle=[("LF3", "Q")])
    d = m.to_dict()
    for lc in d["load_cases"].values() if isinstance(d["load_cases"], dict) else d["load_cases"]:
        lc.pop("faktorisiert", None)           # so sah die Datei vorher aus
    m2 = Model.from_dict(json.loads(json.dumps(d)))
    check("alte Datei: alle Kategorien unverändert",
          {n: lc.category for n, lc in m2.load_cases.items()} == {n: lc.category for n, lc in m.load_cases.items()})
    check("alte Datei: kein Lastfall ist Bemessungslastfall, nichts wird gesperrt außer dem, was NZ war",
          not any(lc.faktorisiert for lc in m2.load_cases.values()))
    d1 = json.dumps(m2.to_dict(), sort_keys=True)
    d2 = json.dumps(Model.from_dict(json.loads(d1)).to_dict(), sort_keys=True)
    check("erneutes Speichern und Laden ändert nichts mehr", d1 == d2)


# --------------------------------------------------------------------------
# 6) Oberflaeche
# --------------------------------------------------------------------------
_FENSTER = {}


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


def test_oberflaeche():
    from statik3d.model import Combination, TempLoad
    w, app = _fenster()
    w.new_model()
    m = _balken()
    w.model = m
    m.combinations["K1"] = Combination("K1", {"LF1": 1.35, "LF2": 1.5}, "ULS")
    m.load_cases["LF1"].temp_loads.append(TempLoad(0, -445.634, 0.0, 952e3, 170e9, 1e-5))
    w.refresh_all(); app.processEvents()

    # Maske des Lastfalls
    w._objektmaske("lastfall", "LF2"); app.processEvents()
    mk = w.maskenrand.maske
    felder = getattr(mk, "_felder", {})
    kat = felder.get("kategorie")
    texte = [kat.itemText(i) for i in range(kat.count())] if kat is not None and hasattr(kat, "itemText") else []
    check("Lastfallmaske: „nicht zugeordnet“ steht zur Wahl und ist gewählt",
          any(t.startswith("NZ: nicht zugeordnet") for t in texte)
          and kat.currentText().startswith("NZ"), kat.currentText() if kat is not None else "keine Auswahl")
    hk = felder.get("faktorisiert")
    check("… der Haken „Bemessungslastfall, bereits faktorisiert“ ist da, nicht gesetzt",
          hk is not None and not hk.isChecked(), str(list(felder)))
    hk.setChecked(True); app.processEvents()
    mk.anwenden(); app.processEvents()
    check("… „Übernehmen“ speichert das Kennzeichen im Lastfall", w.model.load_cases["LF2"].faktorisiert)
    w._objektmaske("lastfall", "LF2"); app.processEvents()
    check("… und die Maske zeigt es beim nächsten Öffnen",
          w.maskenrand.maske._felder["faktorisiert"].isChecked())
    w.maskenrand.maske.abbrechen(); app.processEvents()
    w.model.load_cases["LF2"].faktorisiert = False

    # Tabellen
    w.refresh_all(); app.processEvents()
    zeilen = [w.tbl_lastfall.modell.zeilen[i] for i in range(len(w.tbl_lastfall.modell.zeilen))]
    z2 = next(z for z in zeilen if z[0] == "LF2")
    check("Tabelle der Lastfälle: Einwirkung im Klartext „nicht zugeordnet“", z2[2] == "nicht zugeordnet", str(z2[:3]))
    w.cb_lastfilter.setCurrentText("LF1"); w._lasten_fuellen(); app.processEvents()
    lz = [w.tbl_last.modell.zeilen[i] for i in range(len(w.tbl_last.modell.zeilen))]
    vz = [z for z in lz if z[2] == "Vorspannung"]
    check("Lasttabelle: die Vorspannung steht als Vorspannung mit Kraft, E und alpha",
          len(vz) == 1 and vz[0][4] == "F_v = 952 kN" and "E = 170 000 N/mm²" in vz[0][5]
          and "α = 1,0e-5 1/K" in vz[0][5], str(vz))
    check("… nicht als „Temperatur“ mit ΔT", not any(z[2] == "Temperatur" for z in lz))
    # Text der gewaehlten Last und Lastmaske
    check("der Text der gewählten Last ist der Satz",
          w._lasttext("temperatur", m.load_cases["LF1"].temp_loads[0]) == "E0: " + SATZ,
          w._lasttext("temperatur", m.load_cases["LF1"].temp_loads[0]))
    w._lastmaske("LF1", "temp_loads", 0); app.processEvents()
    mk = w.maskenrand.maske
    fe = getattr(mk, "_felder", {})
    check("Maske der einzelnen Last: Vorspannkraft in kN, Umrechnung, Rechenwert ΔT nur als Info",
          "F" in fe and "dT" not in fe and "umrechnung" in fe, str(list(fe)))
    # Ansicht: Beschriftung
    from statik3d.gui import viewport as vp
    class _Plotter:
        def __getattr__(self, n):
            return lambda *a, **k: None
    merker = []
    try:
        einheiten = vp.add_loads(_Plotter(), m, m.load_cases["LF1"], 10.0, beschriften=True, merker=merker)
        check("Ansicht: die Vorspannung zählt als Kraft (Einheit kN), nicht als Temperatur",
              "kN" in einheiten and not any("K" == e for e in einheiten), str(einheiten))
    except Exception as ex:      # noqa: BLE001
        check("Ansicht: add_loads mit Vorspannung", False, repr(ex)[:90])

    # Rechnen: Hinweis statt Rechnung
    w.fehler_liste.clear()
    w.cb_analysis.setCurrentIndex(0)
    w.do_solve(); app.processEvents()
    log = w.log.toPlainText()
    check("‚Rechnen‘ mit gesperrter Kombination: ein Bedienhinweis, kein Fehlerfenster",
          w.meldungen.hinweis_mit("Kombinationen gesperrt", "LF2", "Modellbaum")
          and not w.meldungen.fehler, str(w.meldungen.alle)[:200])
    check("… es läuft keine Rechnung (kein Ergebnis)", w.analysis is None)
    w.cb_analysis.setCurrentIndex(0)


def main():
    tests = (test_kategorie_und_alte_dateien, test_sperre, test_kommandozeile_hinweis_statt_absturz,
             test_generator_weigert_sich,
             test_bemessungslastfall_im_generator, test_vorspannung_gamma_p,
             test_gemischter_lastfall_mit_vorspannung, test_din19704_generator_sperre, test_lastart_titel,
             test_vorspannung_als_kraft_text, test_bericht,
             test_import_kategorien, test_import_aktion_gilt, test_import_widerspruch,
             test_import_vorspannung_als_kraft, test_import_gemischter_lastfall_wird_gemeldet,
             test_alte_datei_bleibt, test_oberflaeche)
    for t in tests:
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
    if "w" in _FENSTER:
        sys.stdout.flush()
        os._exit(0 if not failed else 1)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
