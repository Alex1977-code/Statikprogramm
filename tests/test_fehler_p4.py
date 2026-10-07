"""
Paket P4 der Fehlerliste (06.10.2026): Stellungen und Lagernamen.

F07  Eine Stellung, die ein unbenanntes Knotenlager ueber seine Nummer abschaltet,
     schaltete still auch das Linien- und das Flaechenlager mit derselben Nummer
     ab (Stellung._lager las ``lager_aus`` fuer alle drei Lagerarten).
F30  Die Stellungsmaske nannte unbenannte Knotenlager „0“, „1“, der Modellbaum
     „Lager 1“, „Lager 2“; wer „1“ anhakte und „Lager 1“ meinte, schaltete das
     zweite Lager ab.

Seither hat jede Lagerart ihren eigenen Schluessel: den Namen des Lagers, sonst den
Standardnamen aus dem Modellbaum („Lager 2“, „Linienlager 1“, „Flächenlager 1“).
Maske, Modellbaum und gespeicherte Stellung benutzen dieselben Namen. Alte Dateien
mit Nummern werden beim Laden auf Knotenlager abgebildet, das Protokoll sagt es.

Aufruf:  python -m tests.test_fehler_p4
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_p4_"), "einstellungen.json")

RESULTS = []
_FENSTER = {}


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:84s} {detail}")
    return ok


def _fuellen(m):
    """Sechs Knoten auf einer Geraden, fuenf Balken; zwei unbenannte Knotenlager (an
    Knoten 0 und 5), ein unbenanntes Linienlager und ein unbenanntes Flaechenlager -
    jede Art hat ein Lager mit der Nummer 0."""
    from statik3d.model import Material, Section
    m.add_material(Material.steel("S355"))
    m.add_section(Section.from_profile("HEB 200"))
    for x in range(6):
        m.add_node(float(x), 0.0, 0.0)
    for i in range(5):
        m.add_element("beam", [i, i + 1], "S355", "HEB 200")
    m.support(0, "all")
    m.support(5, [1, 2, 3])
    m.add_line_support([1, 2]).name = ""
    m.add_surface_support(nodes=[3, 4], areas=[1.0, 1.0]).name = ""
    return m


def _modell():
    from statik3d.model import Model
    return _fuellen(Model("P4"))


def _knoten(m) -> list:
    return [int(s.node) for s in m.supports]


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


def _fenstermodell(w):
    w.new_model()
    return _fuellen(w.model)


def _baumnamen(w) -> dict:
    """Die Beschriftung der Lager im Modellbaum, je Art."""
    from PySide6 import QtCore, QtWidgets
    out = {"lager_einzeln": [], "linienlager_einzeln": [], "flaechenlager_einzeln": []}
    it = QtWidgets.QTreeWidgetItemIterator(w.baum)
    while it.value():
        art = str(it.value().data(0, QtCore.Qt.UserRole) or "")
        if art in out:
            out[art].append(it.value().text(0))
        it += 1
    return out


def _liste(mk, feld) -> list:
    lw = (mk._felder if mk is not None else {}).get(feld)
    return [lw.item(i).text() for i in range(lw.count())] if lw is not None else None


# ---------------------------------------------------------------------------
# F07: jede Lagerart liest nur ihre eigene Liste
# ---------------------------------------------------------------------------
def test_f07_lager_aus_trifft_nur_knotenlager():
    from statik3d.bridges.positions import Stellung
    m = _modell()
    log = []
    sm = Stellung("S1", 0.0, "x", lager_aus=["Lager 1"], faelle=list(m.load_cases)).modell(m, log)
    check("F07: „Lager 1“ in „Deaktivierte Knotenlager“ schaltet das erste Knotenlager ab",
          _knoten(sm) == [5], f"Knotenlager an {_knoten(sm)}; Protokoll {log}")
    check("… das Linienlager mit derselben Nummer bleibt",
          len(sm.line_supports) == 1, f"{len(m.line_supports)} -> {len(sm.line_supports)}")
    check("… das Flächenlager ebenso",
          len(sm.surface_supports) == 1, f"{len(m.surface_supports)} -> {len(sm.surface_supports)}")

    # der Fall aus der Fehlerliste: die alte Nummer „0“ traf alle drei Arten
    log = []
    sm = Stellung("S2", 0.0, "x", lager_aus=["0"], faelle=list(m.load_cases)).modell(m, log)
    check("F07: eine nackte Nummer schaltet kein Linien- und kein Flächenlager mehr ab",
          len(sm.line_supports) == 1 and len(sm.surface_supports) == 1,
          f"Linienlager {len(m.line_supports)} -> {len(sm.line_supports)}, "
          f"Flächenlager {len(m.surface_supports)} -> {len(sm.surface_supports)}; Protokoll {log}")
    check("… und sagt, dass „0“ kein Knotenlager nennt (keine stille Wirkungslosigkeit)",
          any("„0“" in z and "kein Knotenlager" in z for z in log), str(log))


def test_f07_jede_art_hat_ihre_liste():
    from statik3d.bridges.positions import Stellung
    m = _modell()
    sm = Stellung("S1", 0.0, "x", linienlager_aus=["Linienlager 1"],
                  faelle=list(m.load_cases)).modell(m)
    check("„Deaktivierte Linienlager“ schaltet nur das Linienlager ab",
          len(sm.line_supports) == 0 and len(sm.supports) == 2 and len(sm.surface_supports) == 1,
          f"Knoten {len(sm.supports)}, Linien {len(sm.line_supports)}, Flächen {len(sm.surface_supports)}")
    sm = Stellung("S2", 0.0, "x", flaechenlager_aus=["Flächenlager 1"],
                  faelle=list(m.load_cases)).modell(m)
    check("„Deaktivierte Flächenlager“ schaltet nur das Flächenlager ab",
          len(sm.surface_supports) == 0 and len(sm.supports) == 2 and len(sm.line_supports) == 1,
          f"Knoten {len(sm.supports)}, Linien {len(sm.line_supports)}, Flächen {len(sm.surface_supports)}")
    sm = Stellung("S3", 0.0, "x", lager_aus=["Lager 2"], linienlager_aus=["Linienlager 1"],
                  flaechenlager_aus=["Flächenlager 1"], faelle=list(m.load_cases)).modell(m)
    check("alle drei Listen zugleich: genau das genannte Knotenlager bleibt weg, die anderen Arten "
          "verlieren je ihr Lager",
          _knoten(sm) == [0] and not sm.line_supports and not sm.surface_supports,
          f"Knotenlager an {_knoten(sm)}")

    # derselbe Name in zwei Arten: die Liste einer Art trifft nur ihre Art
    m = _modell()
    m.supports[0].name = "Fuß"
    m.line_supports[0].name = "Fuß"
    sm = Stellung("S4", 0.0, "x", lager_aus=["Fuß"], faelle=list(m.load_cases)).modell(m)
    check("Ein Name in „Deaktivierte Knotenlager“ trifft kein gleichnamiges Linienlager",
          _knoten(sm) == [5] and len(sm.line_supports) == 1,
          f"Knotenlager an {_knoten(sm)}, Linienlager {len(sm.line_supports)}")


def test_eintrag_ohne_lager_sagt_es():
    from statik3d.bridges.positions import Stellung
    m = _modell()
    m.line_supports[0].name = "Endlinie"
    log = []
    Stellung("S1", 0.0, "x", lager_aus=["Endlinie"], faelle=list(m.load_cases)).modell(m, log)
    check("Ein Linienlager in der Knotenlager-Liste: das Protokoll sagt, wohin es gehört",
          any("„Endlinie“" in z and "kein Knotenlager" in z and "Linienlager" in z for z in log), str(log))
    log = []
    Stellung("S2", 0.0, "x", linienlager_aus=["Lager 1"], faelle=list(m.load_cases)).modell(m, log)
    check("Ein Eintrag ohne Lager in „Deaktivierte Linienlager“ steht im Protokoll",
          any("„Lager 1“" in z and "kein Linienlager" in z for z in log), str(log))
    log = []
    Stellung("S3", 0.0, "x", lager_aus=["Lager 2"], faelle=list(m.load_cases)).modell(m, log)
    check("Ein genannter Eintrag mit Lager macht keine Warnzeile",
          not any("kein Knotenlager" in z for z in log), str(log))


# ---------------------------------------------------------------------------
# F30: Maske, Modellbaum und Stellung nennen die Lager gleich
# ---------------------------------------------------------------------------
def test_f30_maske_und_baum_nennen_die_lager_gleich():
    from statik3d.bridges.positions import Stellung
    w, app = _fenster()
    m = _fenstermodell(w)
    m.stellungen.append(Stellung("S1", 0.0, "x", faelle=list(m.load_cases)))
    w.refresh_all()
    app.processEvents()
    baum = _baumnamen(w)
    w._objektmaske("stellung", "S1")
    app.processEvents()
    mk = w.maskenrand.maske
    k, ll, fl = (_liste(mk, f) for f in ("lager_aus", "linienlager_aus", "flaechenlager_aus"))
    check("Knotenlager: die Maske nennt sie wie der Modellbaum (nicht „0“, „1“)",
          k == baum["lager_einzeln"] == ["Lager 1", "Lager 2"], f"Maske {k}, Baum {baum['lager_einzeln']}")
    check("Linienlager: Maske und Modellbaum",
          ll == baum["linienlager_einzeln"] == ["Linienlager 1"], f"Maske {ll}, Baum {baum['linienlager_einzeln']}")
    check("Flächenlager: Maske und Modellbaum",
          fl == baum["flaechenlager_einzeln"] == ["Flächenlager 1"],
          f"Maske {fl}, Baum {baum['flaechenlager_einzeln']}")
    tip = mk._felder["lager_aus"].toolTip() if "lager_aus" in mk._felder else ""
    check("Der Hinweis der Maske verspricht keine Nummern mehr", "Nummer" not in tip and "Modellbaum" in tip, tip)
    mk.abbrechen()
    app.processEvents()

    # benannt: der Name steht in Maske und Baum
    m.supports[1].name = "Fuß rechts"
    w.refresh_all()
    app.processEvents()
    w._objektmaske("stellung", "S1")
    app.processEvents()
    mk = w.maskenrand.maske
    check("Ein benanntes Knotenlager heißt in der Maske wie im Baum",
          _liste(mk, "lager_aus") == _baumnamen(w)["lager_einzeln"] == ["Lager 1", "Fuß rechts"],
          f"Maske {_liste(mk, 'lager_aus')}, Baum {_baumnamen(w)['lager_einzeln']}")
    mk.abbrechen()
    app.processEvents()


def test_f30_haken_schaltet_das_gemeinte_lager_ab():
    """Wer „Lager 1“ anhakt, schaltet das Lager ab, das der Baum „Lager 1“ nennt."""
    import numpy as np
    from PySide6 import QtCore
    from statik3d.bridges.positions import Stellung
    w, app = _fenster()
    m = _fenstermodell(w)
    m.stellungen.append(Stellung("S1", 0.0, "x", faelle=list(m.load_cases)))
    w.refresh_all()
    app.processEvents()
    w._objektmaske("stellung", "S1")
    app.processEvents()
    mk = w.maskenrand.maske
    lw = mk._felder["lager_aus"]
    for i in range(lw.count()):
        lw.item(i).setCheckState(QtCore.Qt.Checked if lw.item(i).text() == "Lager 1" else QtCore.Qt.Unchecked)
    mk.anwenden()
    app.processEvents()
    st = w.model.stellung("S1")
    check("„Übernehmen“ schreibt den Namen wie im Baum in die Stellung",
          st is not None and st.lager_aus == ["Lager 1"], str(st and st.lager_aus))
    sm = st.modell(w.model)
    check("… und die Stellung schaltet das erste Lager ab, nicht das zweite",
          _knoten(sm) == [5], f"Knotenlager an {_knoten(sm)}")
    check("… das Linienlager und das Flächenlager bleiben",
          len(sm.line_supports) == 1 and len(sm.surface_supports) == 1)
    # „Auswahl deaktivieren“ schreibt dieselben Namen
    w._objektmaske("stellung", "S1")
    app.processEvents()
    mk = w.maskenrand.maske
    mk.setzen("lager_aus", "")
    w.selection = np.array([5], dtype=int)
    w._stellung_auswahl(mk, "S1", True)
    check("„Auswahl deaktivieren“ trägt das Lager des gewählten Knotens mit seinem Namen ein",
          _liste(mk, "lager_aus") is not None and mk.werte().get("lager_aus") == ["Lager 2"],   # Mehrfachwahl als Liste (F21)
          str(mk.werte().get("lager_aus")))
    mk.abbrechen()
    app.processEvents()


# ---------------------------------------------------------------------------
# Gleichnamige Lager: ein RFEM-Lager „Fest“ an vielen Knoten ist ebenso viele Knotenlager
# ---------------------------------------------------------------------------
def _vier_lager_drei_gleich():
    m = _modell()
    m.fix(2, [1])
    m.fix(3, [1])
    for i in (1, 2, 3):
        m.supports[i].name = "Fest"
    return m


def test_gleichnamige_lager_haben_je_ihren_schluessel():
    from statik3d.bridges.positions import Stellung
    m = _vier_lager_drei_gleich()
    keys = m.lagerschluessel("lager", m.supports)
    check("Drei Knotenlager „Fest“: jedes heißt mit seinem Platz („Fest (Lager 3)“), das ohne Namen „Lager 1“",
          keys == ["Lager 1", "Fest (Lager 2)", "Fest (Lager 3)", "Fest (Lager 4)"], str(keys))
    check("… die Schlüssel sind eindeutig", len(set(keys)) == len(keys))
    sm = Stellung("S1", 0.0, "x", lager_aus=["Fest (Lager 3)"], faelle=list(m.load_cases)).modell(m)
    check("Der Schlüssel nennt genau eines davon (so schaltet der RFEM-Import „genau eines“ ab)",
          _knoten(sm) == [0, 5, 3], str(_knoten(sm)))
    sm = Stellung("S2", 0.0, "x", lager_aus=["Fest"], faelle=list(m.load_cases)).modell(m)
    check("Der gemeinsame Name nennt weiter alle drei, wie bisher", _knoten(sm) == [0], str(_knoten(sm)))
    # ein Name, der wie der Standardname eines anderen Lagers lautet
    m = _modell()
    m.supports[0].name = "Lager 2"
    keys = m.lagerschluessel("lager", m.supports)
    check("Heißt ein Lager „Lager 2“ und das zweite hat keinen Namen: die Schlüssel bleiben eindeutig",
          len(set(keys)) == 2 and keys[1] == "Lager 2", str(keys))
    # Loeschen und Umbenennen
    m = _vier_lager_drei_gleich()
    st = Stellung("S3", 0.0, "x", lager_aus=["Fest (Lager 3)", "Fest (Lager 4)"], faelle=list(m.load_cases))
    m.stellungen.append(st)
    orte = _knoten(st.modell(m))                     # bleiben: Knoten 0 und 5; weg: 2 und 3
    vorher = m.stellungsbezug()
    del m.supports[1]                                # „Fest (Lager 2)“ am Knoten 5
    m.stellungen_nachziehen(vorher)
    check("Löschen eines von drei gleichnamigen: die Einträge rücken auf und meinen dieselben Lager",
          st.lager_aus == ["Fest (Lager 2)", "Fest (Lager 3)"]
          and _knoten(st.modell(m)) == [n for n in orte if n != 5],
          f"{st.lager_aus}; {orte} -> {_knoten(st.modell(m))}")
    vorher = m.stellungsbezug()
    del m.supports[2]                                # „Fest (Lager 3)“ am Knoten 3: nur Knoten 2 heißt noch „Fest“
    m.stellungen_nachziehen(vorher)
    check("… bleibt nur ein „Fest“ übrig, heißt der Eintrag so (der Platz ist nicht mehr nötig)",
          st.lager_aus == ["Fest"], str(st.lager_aus))
    check("… und er nennt weiter dasselbe Lager am Knoten 2",
          _knoten(st.modell(m)) == [0], str(_knoten(st.modell(m))))


def test_gleichnamige_lager_in_maske_und_baum():
    from statik3d.bridges.positions import Stellung
    w, app = _fenster()
    m = _fenstermodell(w)
    m.fix(2, [1])
    m.fix(3, [1])
    for i in (1, 2, 3):
        m.supports[i].name = "Fest"
    m.stellungen.append(Stellung("S1", 0.0, "x", lager_aus=["Fest (Lager 3)"], faelle=list(m.load_cases)))
    w.refresh_all()
    app.processEvents()
    baum = _baumnamen(w)["lager_einzeln"]
    w._objektmaske("stellung", "S1")
    app.processEvents()
    mk = w.maskenrand.maske
    lw = mk._felder["lager_aus"]
    from PySide6 import QtCore
    angehakt = [lw.item(i).text() for i in range(lw.count()) if lw.item(i).checkState() == QtCore.Qt.Checked]
    check("Gleichnamige Lager: Maske und Modellbaum nennen jedes mit seinem Platz",
          _liste(mk, "lager_aus") == baum == ["Lager 1", "Fest (Lager 2)", "Fest (Lager 3)", "Fest (Lager 4)"],
          f"Maske {_liste(mk, 'lager_aus')}, Baum {baum}")
    check("… und die Maske hakt genau das genannte an", angehakt == ["Fest (Lager 3)"], str(angehakt))
    mk.abbrechen()
    app.processEvents()
    # der gemeinsame Name nennt alle drei: die Maske hakt alle an, „Übernehmen“ lässt keinen fallen
    m.stellungen.append(Stellung("S2", 0.0, "x", lager_aus=["Fest"], faelle=list(m.load_cases)))
    w.refresh_all()
    app.processEvents()
    w._objektmaske("stellung", "S2")
    app.processEvents()
    mk = w.maskenrand.maske
    lw = mk._felder["lager_aus"]
    angehakt = [lw.item(i).text() for i in range(lw.count()) if lw.item(i).checkState() == QtCore.Qt.Checked]
    check("Der gemeinsame Name „Fest“ in der Stellung: die Maske hakt alle drei Lager an",
          angehakt == ["Fest (Lager 2)", "Fest (Lager 3)", "Fest (Lager 4)"], str(angehakt))
    mk.setzen("winkel", 5.0)
    mk.anwenden()
    app.processEvents()
    st = w.model.stellung("S2")
    check("… „Übernehmen“ schreibt sie einzeln hin, und die Stellung schaltet weiter alle drei ab",
          st.lager_aus == ["Fest (Lager 2)", "Fest (Lager 3)", "Fest (Lager 4)"]
          and _knoten(st.modell(w.model)) == [0], f"{st.lager_aus}, {_knoten(st.modell(w.model))}")


# ---------------------------------------------------------------------------
# Alte Dateien: Nummern werden beim Laden auf Knotenlager abgebildet
# ---------------------------------------------------------------------------
def _alte_stellungen(m):
    from statik3d.bridges.positions import Stellung
    alle = list(m.load_cases)
    m.stellungen = [
        # „0“ traf bis zum 06.10.2026 Knotenlager 0, Linienlager 0 und Flächenlager 0;
        # „1“ das benannte Knotenlager; „Endlinie“ den Namen eines Linienlagers
        Stellung("S1", 0.0, "alt", lager_aus=["0", "1", "Endlinie"], faelle=alle),
        Stellung("S2", 0.0, "alt", linienlager_aus=["0", "1"], flaechenlager_aus=["0"], faelle=alle),
        Stellung("S3", 0.0, "alt", lager_aus=["Fuß"], lager_aktiv=["Fuß"], faelle=alle),
    ]


def _datei_mit_alten_nummern():
    m = _modell()
    m.fix(2, [1])
    m.supports[1].name = "Fuß"                       # Knotenlager 1 hat einen Namen
    m.add_line_support([3, 4], name="Endlinie")      # Linienlager 1
    _alte_stellungen(m)
    return m, json.loads(json.dumps(m.to_dict()))


def test_alte_datei_nummern_werden_knotenlager():
    from statik3d.model import Model
    m, d = _datei_mit_alten_nummern()
    m2 = Model.from_dict(json.loads(json.dumps(d)))
    s1, s2, s3 = m2.stellungen
    check("alte Datei: „0“ wird der Standardname des Knotenlagers 0 („Lager 1“)",
          s1.lager_aus[:1] == ["Lager 1"], str(s1.lager_aus))
    check("… „1“ wird der Name des benannten Knotenlagers 1", s1.lager_aus[1:2] == ["Fuß"], str(s1.lager_aus))
    check("… der Name eines Linienlagers in „Deaktivierte Knotenlager“ wandert in „Deaktivierte Linienlager“",
          "Endlinie" not in s1.lager_aus and "Endlinie" in s1.linienlager_aus,
          f"{s1.lager_aus} / {s1.linienlager_aus}")
    check("… „Deaktivierte Linienlager“ und „Deaktivierte Flächenlager“ zählen je ihre Art",
          s2.linienlager_aus == ["Linienlager 1", "Endlinie"] and s2.flaechenlager_aus == ["Flächenlager 1"],
          f"{s2.linienlager_aus} / {s2.flaechenlager_aus}")
    check("… ein Name bleibt, wie er ist (Knotenlager und „nur diese Lager aktiv“)",
          s3.lager_aus == ["Fuß"] and s3.lager_aktiv == ["Fuß"], f"{s3.lager_aus} / {s3.lager_aktiv}")
    hinweise = "\n".join(getattr(m2, "_ladehinweise", []))
    check("… das Laden sagt es, je Stellung, mit Alt und Neu",
          "Stellung S1" in hinweise and "„0“" in hinweise and "„Lager 1“" in hinweise, hinweise.replace("\n", " | "))
    check("… und nennt, dass die alte Nummer auch das Linienlager traf (jetzt nicht mehr)",
          any("S1" in z and "Linienlager" in z and "„0“" in z for z in getattr(m2, "_ladehinweise", [])),
          hinweise.replace("\n", " | "))
    check("… die Stellung S3 hat nichts umzustellen und steht nicht im Protokoll",
          "Stellung S3" not in hinweise, hinweise.replace("\n", " | "))
    # was gemeint war, rechnet wie vorher: Knotenlager 0 und 1 weg, Linienlager 0 und 1 bei S2 weg
    sm = s1.modell(m2)
    check("Die umgestellte Stellung schaltet genau die gemeinten Lager ab",
          _knoten(sm) == [2] and [x.name for x in sm.line_supports] == [""],
          f"Knotenlager an {_knoten(sm)}, Linienlager {[x.name for x in sm.line_supports]}")
    # ein zweites Laden aus dem Gespeicherten ist ein fester Punkt
    m3 = Model.from_dict(json.loads(json.dumps(m2.to_dict())))
    s1b = m3.stellungen[0]
    check("Wieder gespeichert und geladen: nichts ändert sich mehr, kein Hinweis",
          s1b.lager_aus == s1.lager_aus and s1b.linienlager_aus == s1.linienlager_aus
          and not getattr(m3, "_ladehinweise", []), f"{s1b.lager_aus}; {getattr(m3, '_ladehinweise', [])}")


def test_alte_datei_lager_heisst_wie_eine_nummer():
    """Ein Lager, das „3“ heißt, bleibt unter diesem Namen stehen - ein Name ist ein Schlüssel."""
    from statik3d.bridges.positions import Stellung
    from statik3d.model import Model
    m = _modell()
    m.fix(2, [1])
    m.fix(3, [1])                                    # es gibt ein Knotenlager mit der Nummer 3
    m.supports[0].name = "3"
    m.stellungen = [Stellung("S1", 0.0, "x", lager_aus=["3"], faelle=list(m.load_cases))]
    m2 = Model.from_dict(json.loads(json.dumps(m.to_dict())))
    check("Ein Knotenlager namens „3“: der Eintrag „3“ bleibt sein Name",
          m2.stellungen[0].lager_aus == ["3"] and not getattr(m2, "_ladehinweise", []),
          f"{m2.stellungen[0].lager_aus}; {getattr(m2, '_ladehinweise', [])}")
    sm = m2.stellungen[0].modell(m2)
    check("… und schaltet dieses Lager ab, nicht das mit der Nummer 3", _knoten(sm) == [5, 2, 3],
          str(_knoten(sm)))


def test_alte_datei_im_programm_oeffnen():
    from PySide6 import QtCore
    w, app = _fenster()
    m, d = _datei_mit_alten_nummern()
    pfad = os.path.join(tempfile.mkdtemp(prefix="statik3d_p4_alt_"), "alt.json")
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(d, f)
    n_log = len(w.log.toPlainText().splitlines())
    w.modell_laden(pfad, fragen=False)
    app.processEvents()
    neu = w.log.toPlainText().splitlines()[n_log:]
    st = w.model.stellung("S1")
    check("Öffnen: die Stellung trägt die Namen wie im Modellbaum", st is not None and st.lager_aus[:2] == ["Lager 1", "Fuß"],
          str(st and st.lager_aus))
    check("… und das Protokoll des Fensters sagt es",
          any(z.startswith("Hinweis: Stellung S1") and "„Lager 1“" in z for z in neu), " | ".join(neu[:6]))
    w._objektmaske("stellung", "S1")
    app.processEvents()
    mk = w.maskenrand.maske
    lw = mk._felder["lager_aus"]
    angehakt = [lw.item(i).text() for i in range(lw.count()) if lw.item(i).checkState() == QtCore.Qt.Checked]
    check("… die Maske der geöffneten Stellung hakt die richtigen Lager an",
          angehakt == ["Lager 1", "Fuß"], str(angehakt))
    mk.abbrechen()
    app.processEvents()


# ---------------------------------------------------------------------------
# Namen folgen dem Modell: Loeschen davor, Umbenennen
# ---------------------------------------------------------------------------
def test_nachziehen_mit_den_namen():
    from statik3d.bridges.positions import Stellung
    m = _modell()
    m.fix(2, [1])                                    # drittes Knotenlager, „Lager 3“
    st = Stellung("S1", 0.0, "x", lager_aus=["Lager 1", "Lager 3"], faelle=list(m.load_cases))
    m.stellungen.append(st)
    vorher = m.stellungsbezug()
    ort = [int(m.supports[2].node)]
    del m.supports[0]
    zeilen = m.stellungen_nachziehen(vorher)
    check("Löschen eines Knotenlagers: sein Eintrag geht, der dahinter rückt auf (Lager 3 wird Lager 2)",
          st.lager_aus == ["Lager 2"], str(st.lager_aus))
    check("… und der Eintrag meint weiter dasselbe Lager",
          [int(m.supports[1].node)] == ort and _knoten(st.modell(m)) == [5],
          f"{ort} / {_knoten(st.modell(m))}")
    check("… das Protokoll nennt beides", len(zeilen) == 2 and all("„S1“" in z for z in zeilen), str(zeilen))
    check("… ohne Änderung bleibt alles stehen, und es steht nichts im Protokoll",
          m.stellungen_nachziehen(m.stellungsbezug()) == [] and st.lager_aus == ["Lager 2"])


def test_umbenennen_fuehrt_die_stellung_mit():
    """Ein Lager ohne Namen hat seinen Standardnamen als Schlüssel; bekommt es einen Namen,
    folgt der Eintrag der Stellung - sonst wäre die Abschaltung still verloren."""
    from statik3d.bridges.positions import Stellung
    w, app = _fenster()
    m = _fenstermodell(w)
    m.stellungen.append(Stellung("S1", 0.0, "x", lager_aus=["Lager 1"], faelle=list(m.load_cases)))
    w.refresh_all()
    app.processEvents()
    i = int(w.tbl_lager.modell.zeilen[0][0])
    n_log = len(w.log.toPlainText().splitlines())
    ok = w._lager_aendern(0, 2, "Fußpunkt")
    app.processEvents()
    st = w.model.stellung("S1")
    check("Tabelle Lager: den Namen eines genannten Lagers ändern - die Stellung folgt",
          ok and i == 0 and st.lager_aus == ["Fußpunkt"], f"{ok}, {st.lager_aus}")
    check("… sie schaltet weiter dasselbe Lager ab", _knoten(st.modell(w.model)) == [5],
          str(_knoten(st.modell(w.model))))
    neu = w.log.toPlainText().splitlines()[n_log:]
    check("… und das Protokoll sagt es", any("„S1“" in z and "„Fußpunkt“" in z for z in neu), " | ".join(neu[:4]))
    # in der Maske des Lagers
    w.refresh_all()
    app.processEvents()
    w._objektmaske("lager_einzeln", "0")
    app.processEvents()
    mk = w.maskenrand.maske
    mk.setzen("name", "Fuß links")
    mk.anwenden()
    app.processEvents()
    st = w.model.stellung("S1")
    check("Maske des Lagers: einen neuen Namen übernehmen - die Stellung folgt",
          w.model.supports[0].name == "Fuß links" and st.lager_aus == ["Fuß links"],
          f"{w.model.supports[0].name!r}, {st.lager_aus}")
    # den Namen wieder streichen: der Standardname ist der Schluessel
    w.refresh_all()
    app.processEvents()
    ok = w._lager_aendern(0, 2, "")
    app.processEvents()
    check("… ohne Namen heißt das Lager wieder „Lager 1“, die Stellung folgt",
          ok and w.model.stellung("S1").lager_aus == ["Lager 1"], str(w.model.stellung("S1").lager_aus))


def test_handbuch_beschreibt_namen_und_umstellung():
    """Das Benutzerhandbuch nennt den Schluessel je Lagerart, den alten Stand und die Umstellung."""
    from tests.handbuch import absatz
    a = absatz("**Lagernamen in Stellungen (seit 06.10.2026).**")
    b = absatz("Eine alte Datei mit Nummern wird beim Öffnen und beim Importieren umgestellt")
    check("Handbuch: eigene Liste und eigener Schlüssel je Lagerart, gleiche Namen in Maske und Baum, alter Stand",
          all(x in a for x in ("Deaktivierte Linienlager", "„Lager 1“", "Fest (Lager 3)", "Bis zum 06.10.2026")),
          a[:140])
    check("Handbuch: alte Dateien werden beim Laden umgestellt, das Protokoll sagt es",
          all(x in b for x in ("„0“ wird „Lager 1“", "Protokoll", "nennt kein Knotenlager")), b[:140])


def main():
    import faulthandler
    faulthandler.dump_traceback_later(600, exit=True)
    for t in (test_f07_lager_aus_trifft_nur_knotenlager, test_f07_jede_art_hat_ihre_liste,
              test_eintrag_ohne_lager_sagt_es, test_f30_maske_und_baum_nennen_die_lager_gleich,
              test_f30_haken_schaltet_das_gemeinte_lager_ab, test_gleichnamige_lager_haben_je_ihren_schluessel,
              test_gleichnamige_lager_in_maske_und_baum, test_alte_datei_nummern_werden_knotenlager,
              test_alte_datei_lager_heisst_wie_eine_nummer, test_alte_datei_im_programm_oeffnen,
              test_nachziehen_mit_den_namen, test_umbenennen_fuehrt_die_stellung_mit,
              test_handbuch_beschreibt_namen_und_umstellung):
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
    code = 0 if n_ok == len(RESULTS) else 1
    os._exit(code)


if __name__ == "__main__":
    main()
