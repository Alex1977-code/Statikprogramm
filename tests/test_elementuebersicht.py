"""
Paket E (25.09.2026): Elementwahl zum Anhaken, Rueckfrage beim Import,
Elementuebersicht mit Faerbung nach Elementtyp, Berichtskapitel „Netz und
Elemente“.

Wuensche des Anwenders: „ich möchte die zu verwendenden elemente anhaken
können und je nach kompatibilität der elemente sollen dann die
anhakmöglichkeiten ausgegraut werden … standard sollte tet10 und vq83 sein“
(23.09.) und „auswahl der zu verwendenden elemente bei berechnung war nicht
vorhanden; und nach der Berechnung sehe ich das auch nirgendwo … wie kann ich
dem prüfer beweisen dass an dieser stelle dieses element verwendet wurde“
(25.09.).

Geprueft wird ohne Fenster (statik3d.elementauswahl, Bericht, SVG) und mit
dem echten Hauptfenster offscreen (Masken, Ansicht, Import, Protokoll).

Aufruf:  python -m tests.test_elementuebersicht
"""
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_elementuebersicht_"), "einstellungen.json")

import numpy as np  # noqa: E402

from statik3d import elementauswahl as ea  # noqa: E402
from statik3d import elemente as EL  # noqa: E402
from statik3d import elementwahl as ew  # noqa: E402
from statik3d.model import Material, Model, Netzeinstellungen, Volumenkoerper  # noqa: E402
from tests import pruefkoerper as pk  # noqa: E402

RESULTS = []
#: ein Stab mit festem Lager fuer die RFEM-Pruefdateien (tests.test_rfem6.make_rf6)
_LAGER = [("Fest", (float("inf"),) * 6, (0,) * 6, None, [1])]


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FAIL'} {name:74s} {detail}")
    return ok


def _wissenschaftlich(text: str) -> bool:
    return re.search(r"\de[+-]?\d", text) is not None


# --------------------------------------------------------------------------
# Pruefmodell: fuenf Koerper mit sieben Elementtypen
# --------------------------------------------------------------------------
def _kuhn_box(m, gruppe, n, x0, h=0.1):
    """n x 1 x 1 Wuerfel (Kante h) aus Kuhn-Tetraedern."""
    ids = {}
    for k in range(2):
        for j in range(2):
            for i in range(n + 1):
                ids[(i, j, k)] = m.add_node(x0 + h * i, h * j, h * k)
    for i in range(n):
        z = [ids[(i + (x & 1), (x >> 1) & 1, (x >> 2) & 1)] for x in range(8)]
        for tet in pk.KUHN:
            kn = [z[x] for x in tet]
            if pk._tet_volumen(m.nodes[kn]) < 0:
                kn[1], kn[2] = kn[2], kn[1]
            m.add_element("tet4", kn, "S", group=gruppe)


def modell():
    """Block: 12 tet4, Stift: 6 tet10, Platte: 2 hex8, Keil: pent6 + pyr5,
    Blech: 2 shell4 - je Koerper eigene Knoten."""
    m = Model("Elementuebersicht")
    m.add_material(Material("S", E=210e9, nu=0.3, rho=7850.0, fy=355e6))
    _kuhn_box(m, "Block", 2, 0.0)
    _kuhn_box(m, "Stift", 1, 1.0)
    ew.tet4_zu_tet10(m, koerper={"Stift"})
    for i in range(2):
        x0 = 2.0 + 0.1 * i
        kn = [m.add_node(x0 + dx, dy, dz) for dz in (0, 0.1) for dx, dy in
              ((0, 0), (0.1, 0), (0.1, 0.1), (0, 0.1))]
        m.add_element("hex8", kn, "S", group="Platte")
    a = [m.add_node(*p) for p in ((3, 0, 0), (3.1, 0, 0), (3, 0.1, 0),
                                  (3, 0, 0.1), (3.1, 0, 0.1), (3, 0.1, 0.1))]
    m.add_element("pent6", a, "S", group="Keil")
    b = [m.add_node(*p) for p in ((3.5, 0, 0), (3.6, 0, 0), (3.6, 0.1, 0), (3.5, 0.1, 0),
                                  (3.55, 0.05, 0.1))]
    m.add_element("pyr5", b, "S", group="Keil")
    from statik3d.model import ShellProp
    m.add_shell_prop(ShellProp("t10", 0.01))
    for i in range(2):
        x0 = 4.0 + 0.1 * i
        kn = [m.add_node(x0, 0, 0), m.add_node(x0 + 0.1, 0, 0), m.add_node(x0 + 0.1, 0.1, 0),
              m.add_node(x0, 0.1, 0)]
        m.add_element("shell4", kn, "S", sec="t10", group="Blech")
    for name in ("Block", "Stift", "Platte", "Keil"):
        m.koerper[name] = Volumenkoerper(name, elemente=[i for i, e in enumerate(m.elements)
                                                         if e.group == name])
    return m


# --------------------------------------------------------------------------
# 1) Elementwahl ohne Fenster
# --------------------------------------------------------------------------
def test_zustand_vorgabe():
    """Vorgabe tet10 + VQ83: was an, was grau und mit welchem Grund."""
    z = ea.zustand(ea.VORGABE & set(ea.ANHAKBAR), sweep=False)
    check("Vorgabe: tet10 angehakt und frei", z["tet10"]["an"] and z["tet10"]["frei"])
    check("Vorgabe: tet4 grau, Grund nennt die eine Ordnung und „erst tet10 abhaken“",
          not z["tet4"]["frei"] and not z["tet4"]["an"]
          and "erst tet10 abhaken" in z["tet4"]["grund"] and "Ordnung" in z["tet4"]["grund"],
          z["tet4"]["grund"][:80])
    check("Vorgabe: tetp grau mit dem Text der Verträglichkeitstabelle (tet10–tetp: nein)",
          not z["tetp"]["frei"] and EL.VERTRAEGLICH_TEXT["nein"] in z["tetp"]["grund"],
          z["tetp"]["grund"][:80])
    check("Vorgabe: VQ83 (hex8) angehakt, grau (immer an), Grund sagt, dass der Sweep aus bleibt",
          z["hex8"]["an"] and not z["hex8"]["frei"] and "schaltet ihn nicht ein" in z["hex8"]["grund"],
          z["hex8"]["grund"][-90:])
    check("… und nennt die Verträglichkeit tet10–hex8 aus der Tabelle (Übergang)",
          EL.VERTRAEGLICH_TEXT[EL.VERTRAEGLICH[("tet10", "hex8")]] in z["hex8"]["grund"])
    check("Vorgabe: VQ203 folgt dem tet10 (abgebildete Sechsflächner), grau",
          z["hex20"]["an"] and not z["hex20"]["frei"] and "abgebildete" in z["hex20"]["grund"])
    check("Vorgabe: Schalen quadratisch an, linear aus, beide grau",
          z["schale2"]["an"] and not z["schale1"]["an"]
          and not z["schale1"]["frei"] and not z["schale2"]["frei"])
    check("Pyramiden frei anhakbar, Grund nennt die Bindung neben tet10",
          z["pyr5"]["frei"] and EL.VERTRAEGLICH_TEXT["bindung"] in z["pyr5"]["grund"])
    z4 = ea.zustand({"tet4"}, sweep=True)
    check("tet4: tet10 grau, VQ203 aus und grau, Schalen linear",
          not z4["tet10"]["frei"] and not z4["hex20"]["an"] and z4["schale1"]["an"],
          z4["hex20"]["grund"][:80])
    check("tet4: tetp bleibt grau (kein Weg im Vernetzer), ohne „passen nicht“",
          not z4["tetp"]["frei"] and EL.VERTRAEGLICH_TEXT["nein"] not in z4["tetp"]["grund"]
          and "aus_tet10" in z4["tetp"]["grund"])
    z0 = ea.zustand(set(), sweep=False)
    check("nichts gewählt: tet4 und tet10 beide frei", z0["tet4"]["frei"] and z0["tet10"]["frei"])
    alle = [d["grund"] for zz in (z, z4, z0) for d in zz.values()]
    check("kein Grund mit wissenschaftlicher Zahl", not any(_wissenschaftlich(g) for g in alle))


def test_grau_liest_die_tabelle():
    """Das Ausgrauen kommt aus elemente.VERTRAEGLICH, nicht aus einem eigenen
    Text: eine andere Tabelle gibt einen anderen Grund."""
    alt = EL.VERTRAEGLICH[("tet10", "tetp2")]
    try:
        EL.VERTRAEGLICH[("tet10", "tetp2")] = "linear"
        z = ea.zustand({"tet10"})
        check("mit „linear“ in der Tabelle steht deren Text im Grund, nicht „passen nicht“",
              EL.VERTRAEGLICH_TEXT["linear"] in z["tetp"]["grund"]
              and EL.VERTRAEGLICH_TEXT["nein"] not in z["tetp"]["grund"], z["tetp"]["grund"][:90])
    finally:
        EL.VERTRAEGLICH[("tet10", "tetp2")] = alt


def test_auf_netz():
    """Die Wahl setzt nur Elementansatz und Pyramiden - nie den Sweep."""
    n0 = Netzeinstellungen(ziellaenge=0.05, dichte="eigene", vernetzer="gmsh")
    n = ea.auf_netz(n0, {"tet10"})
    check("tet10 → ordnung 2", n.ordnung == 2)
    # Netzeinstellungen.sweep ist seit 25.09.2026 ein Wort ("aus" | "sauber" | "immer")
    check("der Sweep bleibt aus, auch mit VQ83 in der Vorgabe", n.sweep == "aus", repr(n.sweep))
    n_s = ea.auf_netz(Netzeinstellungen(sweep="sauber"), {"tet4"})
    check("ein eingeschalteter Sweep bleibt an", n_s.sweep == "sauber" and n_s.ordnung == 1)
    check("sweep_an liest das Wort: „aus“ ist aus, „sauber“/„immer“/True an",
          not ea.sweep_an(Netzeinstellungen()) and ea.sweep_an(Netzeinstellungen(sweep="sauber"))
          and ea.sweep_an(Netzeinstellungen(sweep="immer")) and ea.sweep_an(Netzeinstellungen(sweep=True)))
    check("die übrigen Einstellungen bleiben", n.ziellaenge == 0.05 and n.vernetzer == "gmsh"
          and n.dichte == "eigene")
    check("Pyramiden an, wenn angehakt", ea.auf_netz(n0, {"tet10", "pyr5"}).pyramiden is True)
    check("… und aus, wenn nicht", ea.auf_netz(Netzeinstellungen(pyramiden=True), {"tet4"}).pyramiden
          is False)
    try:
        ea.auf_netz(n0, set())
        check("ohne Tetraeder: Fehler", False)
    except ValueError as ex:
        check("ohne Tetraeder: Fehler im Klartext", "Tetraeder" in str(ex), str(ex))
    check("wahl_aus_netz ist die Umkehrung",
          ea.wahl_aus_netz(ea.auf_netz(n0, {"tet10", "pyr5"})) == {"tet10", "pyr5"}
          and ea.wahl_aus_netz(ea.auf_netz(n0, {"tet4"})) == {"tet4"})
    from dataclasses import asdict
    check("kein neues Feld im Speicherformat", set(asdict(n)) == set(asdict(Netzeinstellungen())))
    m = Model("x")
    m.netz = n
    m2 = Model.from_dict(m.to_dict())
    check("Umlauf to_dict/from_dict behält die Wahl", ea.wahl_aus_netz(m2.netz) == {"tet10"})


# --------------------------------------------------------------------------
# 2) Rueckfrage beim Import
# --------------------------------------------------------------------------
def test_import_vorgabe():
    from statik3d.importers import rfem6_db
    from tests.test_rfem6 import make_rf6
    tmp = tempfile.mkdtemp(prefix="statik3d_ew_import_")
    f = make_rf6(os.path.join(tmp, "a.rf6"), nodes=[(0, 0, 0), (2, 0, 0)], lines=[[1, 2]],
                 members=[(1, None, None)], supports=_LAGER)
    aus = rfem6_db.mesh_info(f)
    check("mesh.xml (Prüfdatei) gibt die Form vor, keine Ordnung",
          "form" in aus and "ordnung" not in aus, str(sorted(aus)))
    abw = ea.abweichungen(aus)
    check("Abweichung nur in der Elementform (Vierecke gegen Vierecke, sonst Dreiecke)",
          [a[0] for a in abw] == ["form"], str(abw))
    text = ea.frage_text("RFEM-Datei", abw)
    check("Frage nennt Datei-Vorgabe und Statik3D-Vorgabe tet10 + VQ83",
          "Die RFEM-Datei gibt Flächen Vierecke vor" in text and "Statik3D-Vorgabe: tet10 + VQ83" in text,
          text.replace("\n", " | "))
    check("ohne Elementfelder aus der Datei: keine Frage", ea.abweichungen({"ziellaenge": 0.05}) == [])
    check("eine Datei mit „linear“ (ordnung 1) wird gefragt",
          [a[0] for a in ea.abweichungen({"ordnung": 1})] == ["ordnung"])
    netz = Netzeinstellungen(quelle="aus mesh.xml der RFEM-Datei", form=1)
    n_s, z_s = ea.nach_import(netz, aus, datei_waehlen=False, datei="RFEM-Datei")
    check("Statik3D-Vorgabe: ordnung 2, Form 2", n_s.ordnung == 2 and n_s.form == 2, z_s)
    n_d, z_d = ea.nach_import(netz, aus, datei_waehlen=True, datei="RFEM-Datei")
    check("Datei-Vorgabe: Form der Datei, Ordnung trotzdem Statik3D (die Datei gibt keine vor)",
          n_d.form == 1 and n_d.ordnung == 2 and "die Datei gibt es nicht vor" in z_d, z_d)
    check("quelle sagt, woher die Elementwahl kommt",
          "Statik3D-Vorgabe tet10 + VQ83" in n_s.quelle and "aus mesh.xml" in n_s.quelle
          and "Elementwahl der Datei" in n_d.quelle, n_s.quelle)
    check("beschreibung nennt danach quadratische Elemente",
          "quadratische Elemente" in n_s.beschreibung(), n_s.beschreibung())
    # Die echten Drehlager-Dateien (nur auf dem Rechner des Anwenders)
    wurzel = r"C:\Users\alexanderm\Desktop\Statik3D\RFEM_Modelle\Lindaunis"
    echte = [os.path.join(wurzel, x) for x in ("Drehlager_V15_4_export.rf6",)
             if os.path.exists(os.path.join(wurzel, x))]
    for p in echte:
        aus_e = rfem6_db.mesh_info(p)
        check(f"{os.path.basename(p)}: mesh.xml ohne Elementordnung, Form 2 - keine Frage",
              "ordnung" not in aus_e and aus_e.get("form") == 2 and not ea.abweichungen(aus_e),
              str(aus_e))
    log = []
    rfem6_db.read_rf6(f, log=log)
    check("Importprotokoll: die Ordnung kommt nicht aus mesh.xml",
          any("Elementordnung (linear/quadratisch) gibt mesh.xml nicht vor" in x for x in log))


# --------------------------------------------------------------------------
# 3) Uebersicht, Farben, Kantenlaenge
# --------------------------------------------------------------------------
def test_zaehlung():
    m = modell()
    z = ea.zaehlung(m)
    check("Zählung je Typ", z["typen"] == {"shell4": 2, "tet4": 12, "tet10": 6, "hex8": 2,
                                           "pent6": 1, "pyr5": 1}, str(z["typen"]))
    check("Reihenfolge des Elementverzeichnisses", list(z["typen"]) ==
          [t for t in EL.ELEMENTE if t in z["typen"]])
    check("je Körper", z["koerper"]["Keil"] == {"pent6": 1, "pyr5": 1}
          and z["koerper"]["Stift"] == {"tet10": 6}, str(z["koerper"]["Keil"]))
    zeilen = {r["typ"]: r for r in ea.zeilen(m, z)}
    check("Ansatz: linear, quadratisch", zeilen["tet4"]["ansatz"] == "linear"
          and zeilen["tet10"]["ansatz"] == "quadratisch")
    check("Ansatz tetp: p = 3 (hierarchisch)", ea.ansatz("tetp3") == "p = 3 (hierarchisch)")
    check("hex8 heißt in der Übersicht VQ83", zeilen["hex8"]["name"] == "hex8 (VQ83)")
    check("Anteil mit Komma", zeilen["tet4"]["anteil"] == "50 %"
          and zeilen["hex8"]["anteil"] == "8,3 %", zeilen["hex8"]["anteil"])
    z_ = ea.protokollzeile(m, z)
    check("Protokollzeile nennt Typen, Anzahl, Ansatz, Anteil",
          "12 tet4 (linear, 50 %)" in z_ and "6 tet10 (quadratisch, 25 %)" in z_
          and z_.startswith("Elemente dieser Rechnung (24):"), z_)
    check("Protokollzeile ohne wissenschaftliche Zahl", not _wissenschaftlich(z_))
    gross = ea.anteil_text(3, 1_812_423)
    check("kleiner Anteil ohne Exponent", not _wissenschaftlich(gross) and gross.endswith(" %"), gross)
    kmin, kmit, kmax = ea.kantenlaengen(m, [i for i, e in enumerate(m.elements) if e.group == "Block"])
    check("Kantenlänge der Kuhn-Tetraeder: h, h√3", abs(kmin - 0.1) < 1e-12
          and abs(kmax - 0.1 * np.sqrt(3)) < 1e-12, f"{kmin} … {kmax}")
    kmin, _, kmax = ea.kantenlaengen(m, [i for i, e in enumerate(m.elements) if e.group == "Platte"])
    check("Kantenlänge der hex8: 0,1 m", abs(kmin - 0.1) < 1e-12 and abs(kmax - 0.1) < 1e-12)


def test_farben():
    """Gut unterscheidbar, auch in Graustufen verschieden hell."""
    haupt = ["beam", "hex20", "tet4", "shell8", "pent15", "tetp4", "hex8", "tetp3", "shell4",
             "pyr5", "tet10", "tetp2", "shell6", "pent6", "shell3"]
    L = {t: ea.helligkeit(ea.farbe(t)) for t in haupt}
    paare = [(a, b, abs(L[a] - L[b])) for i, a in enumerate(haupt) for b in haupt[i + 1:]]
    schlecht = [(a, b, round(d, 1)) for a, b, d in paare if d < 3.5]
    check("die 15 Haupttypen: je zwei mindestens 3,5 L* verschieden hell", not schlecht, str(schlecht))
    check("tet4 und tet10 deutlich verschieden hell (≥ 30 L*)", abs(L["tet4"] - L["tet10"]) >= 30,
          f"{L['tet4']:.1f} / {L['tet10']:.1f}")
    check("jeder Elementtyp des Verzeichnisses hat eine eigene Farbe",
          all(t in ea.FARBEN for t in EL.ELEMENTE)
          and len(set(ea.FARBEN.values())) == len(ea.FARBEN))
    m = modell()
    f = ea.faerbung(m)
    ok = all(f["typen"][int(c)] == e.typ for c, e in zip(f["codes"], m.elements))
    check("Färbung: Code je Element trifft seinen Typ", ok and len(f["codes"]) == len(m.elements))
    check("Legende: Typ und Anzahl", f["namen"][float(f["typen"].index("tet4"))] == "tet4 (12)",
          str(f["namen"]))


# --------------------------------------------------------------------------
# 4) Bericht
# --------------------------------------------------------------------------
def test_bericht():
    from statik3d.report import Report
    from statik3d.report import svg as sv
    from statik3d import ergebnisse
    m = modell()
    html = Report(m).to_html(os.path.join(tempfile.mkdtemp(prefix="statik3d_ew_ber_"), "b.html"))
    text = open(html, encoding="utf-8").read()
    check("Kapitel „Netz und Elemente“ im Bericht", "Netz und Elemente" in text)
    check("… mit Gesamtübersicht und Tabelle je Körper",
          "Elemente im Netz" in text and "Elementtyp, Ansatz, Anzahl und Netzfeinheit je Körper" in text)
    fa = ergebnisse.elementhash(m)
    check("… mit dem Netz-Fingerabdruck der Ergebnisdatei", fa in text
          and ergebnisse.kennung(m)["elemente"] == fa, fa)
    check("… und dem Satz, dass die Ergebnisse zu genau diesem Netz gehören",
          "gehören damit zu genau diesem Netz" in text)
    for t in ("tet4", "tet10", "hex8", "pent6", "pyr5", "shell4"):
        if ea.farbe(t) not in text:
            check(f"Bild: Farbe von {t} fehlt", False)
            break
    else:
        check("Bild nach Elementtyp: alle sechs Typfarben und die Legende", "Elementtyp" in text)
    seiten = sv.aussenseiten(m, [i for i, e in enumerate(m.elements) if e.typ in EL.VOLUMEN_TYPEN])
    typen = {m.elements[i].typ for i, _ in seiten}
    check("Außenseiten auch für pent6, pyr5 und tet10 (nicht nur tet4/hex8)",
          {"pent6", "pyr5", "tet10", "hex8", "tet4"} <= typen, str(sorted(typen)))
    alt_gross = sv.GROSS_AB
    try:
        sv.GROSS_AB = 5                  # wie ein grosses Netz: Umrisse je Koerper
        bild = sv.draw_elementtypen(m, "iso", 700, 450)
    finally:
        sv.GROSS_AB = alt_gross
    check("großes Netz: je Körper der Umriss in der Farbe seines häufigsten Typs",
          all(f'fill="{ea.farbe(t)}"/>' in bild for t in ("tet4", "tet10", "hex8", "pent6"))
          and "Elementtyp" in bild)
    rahmen = Model("Rahmen")
    rahmen.add_material(Material("S", E=210e9, nu=0.3, rho=0.0))
    a, b = rahmen.add_node(0, 0, 0), rahmen.add_node(1, 0, 0)
    from statik3d.model import Section
    rahmen.add_section(Section.from_profile("IPE 200"))
    rahmen.add_element("beam", [a, b], "S", sec="IPE 200")
    t2 = Report(rahmen).to_markdown()
    check("reines Stabwerk: kein Kapitel „Netz und Elemente“ (Kapitelnummern bleiben)",
          "Netz und Elemente" not in t2)
    t3 = Report(m, options={"netz": False}).to_markdown()
    check("abschaltbar über die Berichtsoption „netz“", "Netz und Elemente" not in t3)


# --------------------------------------------------------------------------
# 5) Mit Hauptfenster (offscreen)
# --------------------------------------------------------------------------
_FENSTER = {}
FEHLER = []


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
    # Fehlermeldungen offscreen nicht als Fenster (haelt sonst an), sondern mitschreiben
    w.error = lambda msg: FEHLER.append(str(msg))
    _FENSTER.update(w=w, app=app)
    return w, app


def _modell_ins_fenster(w, app, m):
    w.model = m
    w._MainWindow__init_defaults()
    w.analysis = None
    w.results = None
    w.refresh_all()
    app.processEvents()


def test_ribbon():
    w, _app = _fenster()
    netz = {b.text: b for b in w.ribbon.befehle if b.register == "Netz"}
    check("Ribbon Netz: „Elemente wählen…“ und „Elementübersicht…“ mit Hinweis",
          "Elemente wählen…" in netz and "Elementübersicht…" in netz
          and netz["Elemente wählen…"].hinweis and netz["Elementübersicht…"].hinweis,
          str(sorted(netz))[:120])


def test_maske_elementwahl():
    from PySide6 import QtWidgets
    w, app = _fenster()
    m = modell()
    _modell_ins_fenster(w, app, m)
    check("Modell ohne Wahl: Netzeinstellungen linear (Vorgabe des Datenmodells)", m.netz.ordnung == 1)
    w.maske_elementwahl()
    app.processEvents()
    mk = w.maskenrand.maske
    h = mk.haken
    check("Maske: je Familie eine Gruppe mit Haken",
          {g.title() for g in mk.findChildren(QtWidgets.QGroupBox)} >= {
              "Volumen – Tetraeder", "Volumen – Sechsflächner", "Schalen"})
    check("Stand aus den Netzeinstellungen: tet4 an, tet10 grau",
          h["tet4"].isChecked() and not h["tet10"].isEnabled() and h["tet4"].isEnabled())
    check("grauer Haken trägt den Grund am Zeiger", "erst tet4 abhaken" in h["tet10"].toolTip(),
          h["tet10"].toolTip()[:80])
    check("Sweep-Schalter steht daneben (aus), nicht als Haken",
          "aus" in mk.lbl_sweep.text() and "nicht ein" in mk.lbl_sweep.text())
    mk.zusatzknoepfe[f"Statik3D-Vorgabe ({ea.VORGABE_TEXT})"].click()
    app.processEvents()
    check("Knopf Statik3D-Vorgabe: tet10 an, tet4 grau, VQ83 und VQ203 an",
          h["tet10"].isChecked() and not h["tet4"].isEnabled() and h["hex8"].isChecked()
          and h["hex20"].isChecked() and not h["hex8"].isEnabled())
    check("Vorschau nennt tet10 und die abgebildeten hex20", "frei vernetzte Körper: tet10" in
          mk.lbl_vorschau.text() and "hex20 (VQ203)" in mk.lbl_vorschau.text())
    h["tet10"].setChecked(False)
    app.processEvents()
    check("tet10 abgehakt: tet4 wird frei", h["tet4"].isEnabled() and h["tet10"].isEnabled())
    FEHLER.clear()
    mk.anwenden()
    app.processEvents()
    check("ohne Tetraeder übernimmt die Maske nichts und sagt warum",
          w.model.netz.ordnung == 1 and FEHLER and "Tetraeder" in FEHLER[-1], str(FEHLER))
    h["tet10"].setChecked(True)
    h["pyr5"].setChecked(True)
    mk.anwenden()
    app.processEvents()
    check("Übernehmen: ordnung 2, Pyramiden an, Sweep bleibt aus",
          w.model.netz.ordnung == 2 and w.model.netz.pyramiden and w.model.netz.sweep == "aus")
    check("Meldung nennt die Wahl und das vorhandene Netz",
          "Elementwahl: tet10 + VQ83 + pyr5" in w.statusBar().currentMessage()
          or "Elementwahl: tet10 + VQ83 + pyr5" in w.log.toPlainText())
    w.undo()
    app.processEvents()
    check("Rückgängig nimmt die Wahl zurück", w.model.netz.ordnung == 1 and not w.model.netz.pyramiden)
    w.maskenrand.schliessen()


def test_uebersicht_und_faerbung():
    from statik3d.gui import elementmasken as elm
    w, app = _fenster()
    m = modell()
    _modell_ins_fenster(w, app, m)
    w.maske_elementuebersicht()
    app.processEvents()
    mk = w.maskenrand.maske
    baum = mk.baum
    zeilen = {baum.topLevelItem(i).text(0): baum.topLevelItem(i) for i in range(baum.topLevelItemCount())}
    check("Tabelle: eine Zeile je Elementtyp mit Ansatz, Anzahl, Anteil, Körper",
          set(zeilen) == {"shell4", "tet4", "tet10", "hex8 (VQ83)", "pent6", "pyr5"}
          and zeilen["tet4"].text(1) == "linear" and zeilen["tet4"].text(2) == "12"
          and zeilen["tet4"].text(3) == "50 %" and zeilen["tet4"].text(4) == "Block",
          str([zeilen["tet4"].text(k) for k in range(5)]))
    check("je Körper aufklappbar", zeilen["tet4"].childCount() == 1
          and zeilen["tet4"].child(0).text(0) == "Block")
    from statik3d import ergebnisse
    check("Netz-Fingerabdruck steht in der Maske", mk.werte()["fingerabdruck"] == ergebnisse.elementhash(m))
    baum.itemClicked.emit(zeilen["tet10"], 0)
    app.processEvents()
    tet10 = {i for i, e in enumerate(m.elements) if e.typ == "tet10"}
    check("Klick auf tet10: nur diese Elemente im Bild",
          w.versteckt["elemente"] == set(range(len(m.elements))) - tet10,
          f"{len(w.versteckt['elemente'])} ausgeblendet")
    w.alles_zeigen()
    app.processEvents()
    kind = zeilen["pent6"].child(0)
    baum.itemClicked.emit(kind, 0)
    app.processEvents()
    check("Klick auf eine Körperzeile: nur die Elemente dieses Typs in diesem Körper",
          set(range(len(m.elements))) - w.versteckt["elemente"]
          == {i for i, e in enumerate(m.elements) if e.typ == "pent6"})
    w.alles_zeigen()
    app.processEvents()
    check("vor dem Knopf ist nichts nach Typ gefärbt", not w.elementtyp_faerben)
    mk.anwenden()
    app.processEvents()
    akteur = w.plotter.actors.get("model_netz")
    arr = None
    try:
        arr = akteur.mapper.dataset.cell_data["Elementtyp"]
    except Exception:          # noqa: BLE001
        pass
    check("„Im Bild nach Elementtyp färben“: die Ansicht trägt den Typ je Zelle",
          w.elementtyp_faerben and arr is not None, str(type(akteur)))
    f = elm.faerbung_fuer_ansicht(w, m)
    check("Legende: Typ und Anzahl je Farbe", sorted(f["namen"].values())[0].endswith(")")
          and "tet4 (12)" in f["namen"].values(), str(f["namen"]))
    mk.zusatzknoepfe["Färbung aus"].click()
    app.processEvents()
    check("„Färbung aus“ nimmt sie weg", not w.elementtyp_faerben)
    w.maskenrand.schliessen()


def test_nach_der_rechnung():
    """Protokollzeile nach der Rechnung; Faerbung blendet ein gezeigtes
    Ergebnis aus, ohne es zu verwerfen."""
    from statik3d import solver
    w, app = _fenster()
    w.load_example("solid")
    app.processEvents()
    an = solver.solve_all(w.model)
    w._solve_done("all", an)
    app.processEvents()
    log = w.log.toPlainText()
    check("nach der Rechnung nennt das Protokoll die Elementtypen",
          "Elemente dieser Rechnung (960): 960 hex8 (VQ83) (linear, 100 %)" in log,
          next((z for z in log.splitlines() if z.startswith("Elemente dieser")), "-"))
    check("Ergebnisse sichtbar", w.act_ergebnisse.isChecked() and w.current_result() is not None)
    w.maske_elementuebersicht()
    app.processEvents()
    w.maskenrand.maske.anwenden()
    app.processEvents()
    check("Färben nach Typ blendet die Ergebnisse aus, verwirft sie aber nicht",
          not w.act_ergebnisse.isChecked() and w.analysis is an and w.elementtyp_faerben)
    w.maske_netzguete()
    app.processEvents()
    w.maskenrand.maske.angewendet.emit(w.maskenrand.maske.werte())
    app.processEvents()
    check("Netzqualität anzeigen schaltet die Typfärbung ab (eine Färbung zur Zeit)",
          not w.elementtyp_faerben and w.netzguete_feld is not None)
    w.maskenrand.schliessen()
    w.load_example("frame")
    app.processEvents()
    check("neues Modell: Typfärbung aus", not w.elementtyp_faerben)


def test_import_im_fenster():
    from PySide6 import QtWidgets
    from statik3d.gui import dialogs as dg
    from statik3d.gui import elementmasken as elm
    from tests.test_rfem6 import make_rf6
    w, app = _fenster()
    tmp = tempfile.mkdtemp(prefix="statik3d_ew_imp_")
    f = make_rf6(os.path.join(tmp, "b.rf6"), nodes=[(0, 0, 0), (2, 0, 0)], lines=[[1, 2]],
                 members=[(1, None, None)], supports=_LAGER)
    fragen = []
    antwort = {"v": False}

    def fragen_knoepfe(titel, text, ja="Ja", nein="Abbrechen", **k):
        fragen.append((titel, text, ja, nein, k.get("vorgabe")))
        return antwort["v"]
    alt_fk = w._fragen_knoepfe
    alt_open = QtWidgets.QFileDialog.getOpenFileName
    alt_exec = dg.ImportDialog.exec
    w._fragen_knoepfe = fragen_knoepfe
    QtWidgets.QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (f, ""))
    dg.ImportDialog.exec = lambda self: 1
    try:
        w.import_file()
        app.processEvents()
        check("Import RFEM-Datei: eine Rückfrage mit Datei-Vorgabe / Statik3D-Vorgabe",
              len(fragen) == 1 and fragen[0][2] == "Datei-Vorgabe" and fragen[0][3] == "Statik3D-Vorgabe"
              and "tet10 + VQ83" in fragen[0][1], str(fragen)[:160])
        check("Enter und Esc nehmen die Statik3D-Vorgabe", fragen and fragen[0][4] == "nein")
        check("Antwort Statik3D-Vorgabe: ordnung 2, Form 2",
              w.model.netz.ordnung == 2 and w.model.netz.form == 2, w.model.netz.beschreibung())
        check("Protokollzeile nennt die Wahl", "Elementwahl nach dem Import:" in w.log.toPlainText())
        antwort["v"] = True
        fragen.clear()
        w.import_file()
        app.processEvents()
        check("Antwort Datei-Vorgabe: Form der Datei (Vierecke), Ordnung Statik3D",
              w.model.netz.form == 1 and w.model.netz.ordnung == 2)
        f2 = make_rf6(os.path.join(tmp, "c.rf6"), mesh_xml="", nodes=[(0, 0, 0), (2, 0, 0)],
                      lines=[[1, 2]], members=[(1, None, None)], supports=_LAGER)
        QtWidgets.QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (f2, ""))
        fragen.clear()
        w.import_file()
        app.processEvents()
        check("ohne mesh.xml: keine Frage, Statik3D-Vorgabe", not fragen and w.model.netz.ordnung == 2)
        m = modell()
        m.netz.ordnung = 1
        p = os.path.join(tmp, "eigen.json")
        m.save(p)
        zeile = elm.elementwahl_nach_import(w, m, p)
        check("Statik3D-Datei (.json) behält ihre Wahl", zeile == "" and m.netz.ordnung == 1)
    finally:
        w._fragen_knoepfe = alt_fk
        QtWidgets.QFileDialog.getOpenFileName = alt_open
        dg.ImportDialog.exec = alt_exec


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    for t in (test_zustand_vorgabe, test_grau_liest_die_tabelle, test_auf_netz, test_import_vorgabe,
              test_zaehlung, test_farben, test_bericht, test_ribbon, test_maske_elementwahl,
              test_uebersicht_und_faerbung, test_nach_der_rechnung, test_import_im_fenster):
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
