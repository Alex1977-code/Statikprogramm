"""
Test des statischen Berichts (statik3d.report): HTML, Markdown, PDF, SVG.
Aufruf:  python -m tests.test_report      (auch mit pytest lauffaehig)
"""
import os
import re
import sys
import tempfile
import xml.etree.ElementTree as ET

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d.model import Model, Material, Section  # noqa: E402
from statik3d.profiles import make_section  # noqa: E402
from statik3d import solver, mesher  # noqa: E402
from statik3d.combinations import generate_combinations  # noqa: E402
from statik3d.examples_lib import frame_example, plate_example, solid_example  # noqa: E402
from statik3d.report import Report, write_report, print_hint  # noqa: E402
from statik3d.report import svg as sv  # noqa: E402

RESULTS = []
_SVG_RE = re.compile(r"<svg\b.*?</svg>", re.S)


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FAIL'} {name:60s} {detail}")
    return ok


def _assert_since(n0):
    failed = [r[0] for r in RESULTS[n0:] if not r[1]]
    assert not failed, "fehlgeschlagen: " + ", ".join(failed)


def _svgs_parse(html):
    blocks = _SVG_RE.findall(html)
    for blk in blocks:
        ET.fromstring(blk)          # wirft ParseError bei ungueltigem XML
    return len(blocks)


def _tmpdir():
    d = os.path.join(tempfile.gettempdir(), "statik3d_report_test")
    os.makedirs(d, exist_ok=True)
    return d


# --------------------------------------------------------------------------
def build_beam_model():
    """Einfeldtraeger IPE 300 S235 aus tests/test_ec3.py::test_design_driver."""
    m = Model("Einfeldträger IPE 300")
    m.add_material(Material.steel("S235"))
    m.add_section(make_section("IPE 300"))
    ids = mesher.line_of_beams(m, "S235", "IPE 300", (0, 0, 0), (6, 0, 0), 6)
    m.fix(ids[0], [0, 1, 2, 3])
    m.fix(ids[-1], [1, 2, 3])
    m.case().category = "G"
    for e in range(6):
        m.load_beam(e, qz=-10000.0)
    m.add_member("Traeger", list(range(6)), detail_category=71e6)
    m.add_combination("K1", {"LF1": 1.0}, "ULS")
    m.add_fatigue_load("Ermuedung", "LF1", None, 2e6)
    m.meta.update({"projekt": "Testprojekt Bericht", "bauteil": "Träger", "position": "Pos. 1",
                   "bearbeiter": "Prüfer", "auftraggeber": "Bauherr"})
    return m


def build_frame_model():
    """Rahmen aus examples_lib mit Staeben, zweitem Lastfall und automatischen Kombinationen."""
    m = frame_example()
    m.materials["S355"] = Material.steel("S355")
    m.auto_members()
    m.add_load_case("W", "W", "Wind von links")
    n = int(mesher.select_nodes(m, xmin=-1e-6, xmax=1e-6, zmin=4 - 1e-6)[0])
    m.load_node(n, Fx=8000.0)
    m.add_load_case("Q", "Q_K", "Kranlast")
    for i, e in enumerate(m.elements):
        p = m.nodes[e.nodes]
        if abs(p[0][2] - 4) < 1e-9 and abs(p[1][2] - 4) < 1e-9:
            m.load_beam(i, qz=-5000.0)
    first = next(iter(m.members))
    m.members[first].detail_category = 80e6
    m.add_fatigue_load("Kranfahrt", "Q", None, 5e5)
    generate_combinations(m)
    m.meta.update({"projekt": "Hallenrahmen", "bauteil": "Rahmen Achse 3",
                   "bearbeiter": "A. Muster", "auftraggeber": "Musterfirma GmbH"})
    return m


# --------------------------------------------------------------------------
def test_beam_report():
    n0 = len(RESULTS)
    m = build_beam_model()
    an = solver.solve_all(m, design=True, fatigue=True)
    rep = Report(m, an)
    path = os.path.join(_tmpdir(), "traeger_bericht.html")
    rep.to_html(path)
    check("Träger: HTML-Datei vorhanden", os.path.exists(path))
    size = os.path.getsize(path)
    check("Träger: Dateigröße > 20 kB", size > 20000, f"{size / 1024:.0f} kB")
    html = open(path, encoding="utf-8").read()
    for head in ("Allgemeines", "System", "Einwirkungen", "Ergebnisse",
                 "Nachweise nach DIN EN 1993-1-1", "Ermüdungsnachweis", "Zusammenfassung",
                 "Anhang"):
        check(f"Träger: Kapitel '{head}'", head in html)
    check("Träger: enthält <svg", "<svg" in html)
    check("Träger: Stabname", "Traeger" in html)
    check("Träger: 'Ausnutzung'", "Ausnutzung" in html)
    check("Träger: 'Umhüllende'", "Umhüllende" in html or "Umhuellende" in html)
    check("Träger: Metadaten", "Testprojekt Bericht" in html and "Bauherr" in html)
    check("Träger: Biegedrillknicken dokumentiert", "Biegedrillknicken" in html)
    check("Träger: Wöhlerlinie", "Wöhlerlinie" in html)
    check("Träger: Kerbfall 71", "Kerbfall 71" in html or "71 MPa" in html)
    check("Träger: Status", "Alle Nachweise erfüllt" in html or "NICHT erfüllt" in html)
    check("Träger: Umlaute korrekt", "Ausnutzung" in html and "Verschiebung" in html
          and "ä" in html and "ü" in html)
    try:
        n_svg = _svgs_parse(html)
        check("Träger: alle SVG-Blöcke XML-parsbar", n_svg > 5, f"{n_svg} SVG")
    except ET.ParseError as ex:
        check("Träger: alle SVG-Blöcke XML-parsbar", False, str(ex))
    md = rep.to_markdown()
    check("Träger: Markdown erzeugt", len(md) > 5000 and "# " in md and "|" in md)
    check("Träger: Markdown ohne HTML-Tags", "<table" not in md and "<svg" not in md)
    # Einzelergebnis ohne Analysis
    rep2 = Report(m, results=solver.solve_static(m))
    html2 = rep2.html()
    check("Träger: Report nur mit Results", len(html2) > 20000 and "Ergebnisse" in html2)
    html2b = Report(m, solver.solve_static(m)).html()      # Results im Analysis-Argument
    check("Träger: Results positional statt Analysis", "Auflagerreaktionen LF1" in html2b)
    check("Träger: ohne Nachweise -> Hinweis", "keine Nachweise" in html2.lower()
          or "keine nachweisergebnisse" in html2.lower())
    _svgs_parse(html2)
    # Kapitel einzeln
    check("Träger: chapter_html('design')", "Querschnittsnachweise" in rep.chapter_html("design"))
    _assert_since(n0)


def test_frame_report():
    n0 = len(RESULTS)
    m = build_frame_model()
    an = solver.solve_all(m, design=True, fatigue=True)
    rep = Report(m, an)
    path = os.path.join(_tmpdir(), "rahmen_bericht.html")
    rep.to_html(path)
    html = open(path, encoding="utf-8").read()
    check("Rahmen: HTML > 20 kB", os.path.getsize(path) > 20000,
          f"{os.path.getsize(path) / 1024:.0f} kB")
    for name in m.members:
        check(f"Rahmen: Stab {name} im Bericht", name in html)
    check("Rahmen: Kombinationstabelle", "Kombinationen" in html and "GZT" in html)
    check("Rahmen: Lastfall W", "Wind von links" in html)
    check("Rahmen: mehrere Umhüllende", html.count("Umhüllende") >= 3)
    check("Rahmen: Nachweistabelle", "maßgebender Nachweis" in html)
    check("Rahmen: Interaktion 6.61", "6.61" in html)
    check("Rahmen: Stabdiagramme", "Schnittgrößenverläufe" in html)
    check("Rahmen: Ermüdung Stab", "Kranfahrt" in html)
    n_svg = _svgs_parse(html)
    check("Rahmen: SVG parsbar", n_svg >= 10, f"{n_svg} SVG")
    # Optionen: alles aus ausser Nachweise
    opts = {k: False for k in Report.DEFAULTS if isinstance(Report.DEFAULTS[k], bool)}
    opts["design"] = True
    rep3 = Report(m, an, options=opts)
    html3 = rep3.html()
    check("Rahmen: Optionen reduzieren Umfang", len(html3) < len(html))
    check("Rahmen: Nachweise trotz Optionen", "Ausnutzung" in html3)
    p_md = write_report(m, an, os.path.join(_tmpdir(), "rahmen.md"), fmt="md")
    check("Rahmen: write_report md", os.path.exists(p_md) and os.path.getsize(p_md) > 5000)
    p_html = write_report(m, an, os.path.join(_tmpdir(), "rahmen2.html"), fmt="html",
                          member_diagrams=False)
    check("Rahmen: write_report html", os.path.exists(p_html))
    _assert_since(n0)


def test_contact_report():
    n0 = len(RESULTS)
    m = Model("Träger mit einseitigem Lager")
    m.add_material(Material("S"))
    m.add_section(Section.rectangle("R", 0.1, 0.3))
    ids = [m.add_node(i * 1.0, 0, 0) for i in range(7)]
    for i in range(6):
        m.add_element("beam", [ids[i], ids[i + 1]], "S", "R")
    A, B, C = ids[0], ids[4], ids[6]
    m.fix(A, [0, 1, 3, 5])
    m.fix(B, [1, 2, 3, 5])
    m.add_contact_support(A, (0, 0, 1))
    m.add_contact_support(C, (0, 0, 1))
    m.load_node(ids[5], Fz=-10000.0)
    r = solver.solve_static(m)
    check("Kontakt: Ergebnis hat Kontaktbedingungen", len(r.contact) == 2)
    rep = Report(m, results=r)
    html = rep.html()
    check("Kontakt: Kapitel Kontakt", "Kontaktergebnisse" in html)
    check("Kontakt: Status offen/Kontakt", "offen" in html and "Kontakt" in html)
    check("Kontakt: Tabelle einseitige Lager", "Einseitige Lager" in html)
    check("Kontakt: Penalty im Rechenverfahren", "Penalty" in html)
    # Kontaktkraefte je Kontaktpaar: Summe, Resultierende, massgebendes Ergebnis
    from statik3d import spannungen as spn
    from statik3d.report.html import fmt
    kk = spn.kontaktkraefte(m, r)
    check("Kontakt: Kraefte je Kontaktpaar (zwei einseitige Lager = zwei Gruppen)", len(kk) == 2,
          str([(k["name"], round(k["Fn"])) for k in kk]))
    check("Kontakt: Tabelle Kontaktkraefte je Kontaktpaar mit massgebendem Ergebnis",
          "Kontaktkräfte je Kontaktpaar" in html and "maßgebend" in html and "ΣF_n [kN]" in html)
    aktiv = [k for k in kk if k["aktiv"]]
    check("Kontakt: die Summe der Normalkraft des tragenden Lagers steht in der Tabelle",
          bool(aktiv) and fmt(aktiv[0]["Fn"] / 1e3, 2) in html,
          str([fmt(k["Fn"] / 1e3, 2) for k in kk]))
    check("Kontakt: Langform nennt auch die Knoten", "je Knoten (F_n" in html)
    html_kurz = Report(m, results=r, options={"umfang": "kurz"}).html()
    check("Kontakt: Kurzform nennt die Kontaktkraefte, aber nicht die Knotenliste",
          "Kontaktkräfte je Kontaktpaar" in html_kurz and "je Knoten (F_n" not in html_kurz)
    _svgs_parse(html)
    _assert_since(n0)


def test_plate_and_solid():
    n0 = len(RESULTS)
    p = plate_example()
    rp = solver.solve_static(p)
    html = Report(p, results=rp).html()
    check("Platte: Schalen als Polygone", "<polygon" in html)
    check("Platte: Knotenliste gekürzt", "gekürzt" in html)
    check("Platte: Schnittkräfte Schalen", "Schnittkräfte und Spannungen der Schalen" in html)
    check("Platte: Flächenlasten gruppiert", "Flächenlasten" in html and "384" in html)
    _svgs_parse(html)
    s = solid_example()
    rs = solver.solve_static(s)
    html = Report(s, results=rs, options={"model_tables": False}).html()
    check("Volumen: Facetten gezeichnet", html.count("<polygon") > 100)
    check("Volumen: Spannungstabelle", "Volumenelemente" in html)
    _svgs_parse(html)
    _assert_since(n0)


def test_svg_helpers():
    n0 = len(RESULTS)
    x = np.linspace(0, 6, 25)
    My = 10e3 * x * (6 - x) / 9.0 - 5e3
    svg = sv.draw_member_diagram(x, My, "My", "kNm", 600, 160, (My - 4e3, My + 4e3), "Test <&>")
    ET.fromstring(svg)
    check("SVG: Diagramm parsbar und maskiert", "&lt;&amp;&gt;" in svg and "kNm" in svg)
    svg = sv.draw_bar_chart(["S1", "S<2>"], [0.45, 1.2], 500, None, 1.0, "Ausnutzung")
    ET.fromstring(svg)
    check("SVG: Balkendiagramm rot über Grenze", "#c0392b" in svg and "S&lt;2&gt;" in svg)
    svg = sv.draw_sn_curve(71e6, [(80e6, 2e6, "LF"), (30e6, 5e7)], 1.15, title="Wöhler")
    ET.fromstring(svg)
    check("SVG: Wöhlerlinie mit Punkten", "Δσ_C" in svg and "LF" in svg)
    for kind in ("iso", "xy", "xz", "yz"):
        pr = sv.Projection(kind, 400, 300)
        pr.fit(np.array([[0, 0, 0], [6, 2, 4]]))
        P = pr.project(np.array([[0, 0, 0], [6, 2, 4]]))
        inside = np.all(P >= 0) and np.all(P[:, 0] <= 400) and np.all(P[:, 1] <= 300)
        check(f"SVG: Projektion {kind} eingepasst", inside)
    m = build_beam_model()
    r = solver.solve_static(m)
    svg = sv.draw_structure(m, "xz", 600, 300, results=r, show_nodes=True, show_numbers=True,
                            util={0: 0.3, 1: 0.9, 2: 1.2}, title="Träger")
    ET.fromstring(svg)
    check("SVG: Struktur mit Verformung/Ausnutzung", "Überhöhung" in svg and "Ausnutzung" in svg)
    check("SVG: Lasten und Lager gezeichnet", "kN/m" in svg and "<polygon" in svg)
    empty = sv.draw_structure(Model("leer"), "iso", 300, 200)
    ET.fromstring(empty)
    check("SVG: leeres Modell", "kein Modell" in empty)
    _assert_since(n0)


def test_kontaktbedingungen_im_bericht():
    """Eine nicht ausgefuehrte Kontaktfuge darf im Dokument nicht fehlen."""
    n0 = len(RESULTS)
    from statik3d.model import DofBehaviour
    m = build_beam_model()
    m.add_kontaktbedingung("Fuge 1", flaechennamen=["F1"], koerpernamen=["V1"],
                           behaviour={0: DofBehaviour("rigid"),
                                      1: DofBehaviour("rigid"),
                                      2: DofBehaviour("free", failure="zug")})
    html = Report(m, solver.solve_static(m)).html()
    check("Bericht: Kontaktbedingung genannt", "Fuge 1" in html)
    check("Bericht: Wirkung je Freiheitsgrad genannt",
          "ux=starr" in html and "Ausfall bei Zug" in html)
    check("Bericht: nicht ausgeführte Trennung wird benannt",
          "nicht ausgeführt" in html and "zu steif" in html)
    m.kontaktbedingungen["Fuge 1"].ausgefuehrt = True
    html2 = Report(m, solver.solve_static(m)).html()
    check("Bericht: ausgeführte Fuge wird nicht mehr angemahnt",
          "Kontaktbedingung(en) sind nicht ausgeführt" not in html2)
    _assert_since(n0)


def test_kontaktwarnungen_der_uebrigen_ergebnisse():
    """Im Vorgabeumfang bekommt nur eine Handvoll Ergebnisse eine eigene
    Kontakttabelle - ihre **Warnungen** dürfen deshalb nicht mit wegfallen.

    `max_contact_results` begrenzt die Einzeltabellen; die Warnung und der
    Grund der Nichtkonvergenz hingen bis zum 22.09.2026 an derselben
    Schleife. Bei 1931 Kontaktergebnissen nannte der Bericht den Grund für
    höchstens fünf (0,26 %) - 1911 standen ohne jedes Kennzeichen im
    Statikdokument. Und die Auswahl ist nicht die gefährlichste, sondern
    schlicht die erste: `je_ergebnis` folgt der Reihenfolge von
    `all_results()` ohne jede Sortierung.

    Gebündelt statt je Ergebnis: die Warnungsliste wächst um höchstens die
    Zahl der verschiedenen Protokolltexte plus eins.
    """
    n0 = len(RESULTS)
    from statik3d import examples_lib as _ex
    m = _ex.build_example("friction")
    an = solver.solve_all(m)
    # Mehrere Kontaktergebnisse: dasselbe Ergebnis unter weiteren Namen, jedes
    # mit eigenem info-Wörterbuch. Es geht um die Auswahl im Bericht, nicht um
    # die Mechanik - darum genügt die Kopie.
    import copy as _copy
    grund = next(n for n, r in an.cases.items() if getattr(r, "contact", None))
    for _k in (2, 3, 4):
        kopie = _copy.copy(an.cases[grund])
        kopie.info = dict(getattr(an.cases[grund], "info", {}) or {})
        an.cases[f"{grund} ({_k})"] = kopie
    ergebnisse = list(an.all_results().items())
    check("die Probe braucht mehrere Kontaktergebnisse",
          len(ergebnisse) >= 2 and any(getattr(r, "contact", None)
                                       for _n, r in ergebnisse),
          f"{len(ergebnisse)} Ergebnisse")
    # Das zweite und jedes weitere Ergebnis bekommt eine Warnung und gilt als
    # nicht konvergiert - genau die Ergebnisse, die keine eigene Tabelle mehr
    # bekommen, wenn nur eines gezeigt wird.
    for _i, (_name, r) in enumerate(ergebnisse):
        if _i:
            # mit Laufnummer, wie sie der Loeser seit dem 22.09.2026 anhaengt -
            # die Buendelung muss sie uebergehen, sonst zerfiele die Meldung
            r.info["contact_log"] = [f"Reibiteration am Deckel abgebrochen (Kontaktlauf {_i + 2})"]
            r.info["contact_converged"] = False
    rep = Report(m, an, options={"max_contact_results": 1})
    html = rep.html()
    warn = "\n".join(getattr(rep, "_warnings", []) or [])
    check("die Warnung der übrigen Ergebnisse steht im Bericht",
          "Reibiteration am Deckel abgebrochen" in warn, warn[:120] or "keine")
    check("verschiedene Laufnummern ergeben EINE Warnzeile",
          sum(1 for z in (getattr(rep, "_warnings", []) or [])
              if "Reibiteration am Deckel" in z) == 1,
          str([z[:60] for z in (getattr(rep, "_warnings", []) or [])
               if "Reibiteration" in z]))
    check("und die Zahl der nicht konvergierten wird genannt",
          "nicht konvergiert" in warn, warn[:160] or "keine")
    check("der Hinweis unter der Tabelle nennt sie ebenfalls",
          "davon sind nicht konvergiert" in html,
          "steht im Dokument" if "davon sind nicht" in html else "fehlt")
    _assert_since(n0)


def test_deckelzeilen_mit_rundenbilanz_werden_gebuendelt():
    """Seit dem Laufbuch (22.09.2026) haengt die Deckelzeile des
    Kontaktsystems eine Rundenbilanz an (``ContactSystem.runden_text``:
    " - in 40 Runden: 31 mit ..."). Ihre Zahlen sind je Lauf und Lastfall
    andere. Ohne Schnitt wuerde die Buendelung der uebrigen Ergebnisse daraus
    eine Warnzeile je gedeckeltem Lauf machen - am Drehlager bis zu 422 x 12
    statt einer. Und ein Ergebnis mit mehreren gedeckelten Laeufen traegt
    dieselbe Art mehrmals: gezaehlt werden Ergebnisse, nicht Zeilen."""
    n0 = len(RESULTS)
    import copy as _copy
    from statik3d import contact as ct
    from statik3d import examples_lib as _ex

    def deckelzeile(n_runden, n_knoten):
        # Der veraenderliche Teil im Format, das das Kontaktsystem schreibt
        cs = object.__new__(ct.ContactSystem)
        t = [0] * len(ct.RUNDEN_FELDER)
        t[0] = 2
        t[ct.RUNDEN_FELDER.index("gleiten_neu")] = n_knoten
        cs.runden = [tuple(t)] * n_runden
        return ("Kontakt: Nachpruefung der Reibung nach 40 Zustandswechseln abgebrochen"
                + cs.runden_text(n_runden))

    probe = deckelzeile(3, 7)
    check("die Probe traegt eine Rundenbilanz", " - in 3 Runden: 3 mit neuem Gleiten" in probe,
          probe)
    m = _ex.build_example("friction")
    an = solver.solve_all(m)
    grund = next(n for n, r in an.cases.items() if getattr(r, "contact", None))
    for _k in (2, 3, 4):
        kopie = _copy.copy(an.cases[grund])
        kopie.info = dict(getattr(an.cases[grund], "info", {}) or {})
        an.cases[f"{grund} ({_k})"] = kopie
    ergebnisse = list(an.all_results().items())
    uebrige = 0
    for _i, (_name, r) in enumerate(ergebnisse):
        if _i:
            # zwei gedeckelte Laeufe je Ergebnis, jeder mit eigener Bilanz
            r.info["contact_log"] = [deckelzeile(_i, 2 * _i + 1), deckelzeile(_i + 1, 3 * _i)]
            uebrige += 1
    rep = Report(m, an, options={"max_contact_results": 1})
    rep.html()
    zeilen = [z for z in (getattr(rep, "_warnings", []) or []) if "Nachpruefung der Reibung" in z]
    check("verschiedene Rundenbilanzen ergeben EINE Warnzeile", len(zeilen) == 1,
          f"{len(zeilen)} Zeilen: " + str([z[:70] for z in zeilen[:3]]))
    check("sie zaehlt Ergebnisse, nicht Zeilen",
          len(zeilen) == 1 and f"({uebrige} weitere Ergebnisse" in zeilen[0],
          zeilen[0][:90] if zeilen else "keine")
    _assert_since(n0)


def test_pdf():
    n0 = len(RESULTS)
    m = build_beam_model()
    an = solver.solve_all(m, design=True, fatigue=True)
    rep = Report(m, an)
    path = os.path.join(_tmpdir(), "traeger.pdf")
    import importlib.util
    have = importlib.util.find_spec("reportlab") is not None
    if have:
        rep.to_pdf(path)
        check("PDF: Datei erzeugt (reportlab vorhanden)",
              os.path.exists(path) and os.path.getsize(path) > 10000)
    else:
        try:
            rep.to_pdf(path)
            check("PDF: RuntimeError ohne reportlab", False)
        except RuntimeError as ex:
            check("PDF: RuntimeError ohne reportlab", "reportlab" in str(ex), str(ex))
        except Exception as ex:   # falscher Ausnahmetyp
            check("PDF: RuntimeError ohne reportlab", False, repr(ex))
    check("PDF: Druckhinweis", "Strg+P" in print_hint())
    _assert_since(n0)


def test_fortschritt():
    """Der Bericht meldet je Kapitel den Fortschritt - fuer den Balken der
    Oberflaeche; ohne Rueckruf entsteht dieselbe Datei."""
    n0 = len(RESULTS)
    m = build_beam_model()
    an = solver.solve_all(m, design=True, fatigue=True)
    schritte = []
    p1 = write_report(m, an, os.path.join(_tmpdir(), "fortschritt.html"), fmt="html",
                      fortschritt=lambda a, t: schritte.append((a, t)))
    anteile = [a for a, _t in schritte]
    check("Fortschritt: je Kapitel eine Meldung, dazu Ausgabe und Schreiben",
          len(schritte) >= 18 + 3, f"{len(schritte)} Meldungen")
    check("Fortschritt: Anteile steigen monoton von 0 bis 1",
          anteile[0] == 0.0 and anteile[-1] == 1.0
          and all(b >= a for a, b in zip(anteile, anteile[1:])),
          f"{anteile[:2]} … {anteile[-2:]}")
    texte = " | ".join(t for _a, t in schritte)
    check("Fortschritt: die Texte nennen die Kapitel mit Namen",
          all(w in texte for w in ("Kapitel 1 von", "System", "Nachweise EC3", "Ermüdung",
                                   "Zusammenfassung", "HTML", "geschrieben")), texte[:160])
    p2 = write_report(m, an, os.path.join(_tmpdir(), "fortschritt2.html"), fmt="html")
    # die Verlaufskennungen der SVGs (grad12, grad13, …) zaehlen je Prozess hoch
    ohne_grad = lambda s: re.sub(r"grad\d+", "grad", s)          # noqa: E731
    check("ohne Rueckruf dieselbe Datei",
          ohne_grad(open(p1, encoding="utf-8").read()) == ohne_grad(open(p2, encoding="utf-8").read()))
    schritte_md = []
    write_report(m, an, os.path.join(_tmpdir(), "fortschritt.md"), fmt="md",
                 fortschritt=lambda a, t: schritte_md.append((a, t)))
    check("auch Markdown meldet die Kapitel", len(schritte_md) >= 18, f"{len(schritte_md)}")
    _assert_since(n0)


def test_gliederung_und_rahmen():
    """Umfang kurz/mittel/lang, Rahmen (Kopf-/Fusszeile, Raender, Logo) und die
    Gliederung: Text, Ergebnistabelle und Dateien (SVG, CSV, PNG, MD) an ihrem
    Platz im Bericht (12.09.2026)."""
    import base64
    from statik3d.model import Berichtseintrag, Berichtsrahmen
    n0 = len(RESULTS)
    m = build_beam_model()
    m.meta.update({"projekt": "Halle Nord", "bauteil": "Rahmen", "position": "Pos. 7",
                   "bearbeiter": "AM"})
    an = solver.solve_all(m, design=True, fatigue=True)
    lang = Report(m, an, options={"umfang": "lang"})
    kurz = Report(m, an, options={"umfang": "kurz"})
    mittel = Report(m, an, options={"umfang": "mittel"})
    nl, nk, nm = len(lang.blocks()), len(kurz.blocks()), len(mittel.blocks())
    check("Umfang: kurz < mittel < lang (Bloecke)", nk < nm < nl, f"{nk} / {nm} / {nl}")
    hk = kurz.html()
    check("Kurzform: keine Ergebnisse je Lastfall, keine Nachweisdetails, Kurzform genannt",
          "Ergebnisse je Lastfall" not in hk and "Kurzform: die Nachweise stehen" in hk
          and "Umfang: Kurzform" in hk and kurz.design is not None,
          f"{'Ergebnisse je Lastfall' in hk} {'Kurzform: die Nachweise stehen' in hk} {kurz.design is not None}")
    check("ohne Angabe: Langform (wie bisher); mit Berichtsrahmen gilt dessen Umfang (Vorgabe kurz)",
          Report(m, an).opt("umfang") == "lang" and m.berichtsrahmen().umfang == "kurz"
          and Report(m, an).opt("umfang") == "kurz")
    hl = lang.html()
    check("Langform: Ergebnisse je Lastfall und Nachweisdetails",
          "Ergebnisse je Lastfall" in hl and "Kurzform: die Nachweise stehen" not in hl)
    # Rahmen
    r = m.berichtsrahmen()
    r.kopf = "{projekt} · {bauteil} · {position}"
    r.fuss = "{bearbeiter} · {datum}"
    r.rand_links_mm = 25.0
    r.schrift_pt = 9.5
    r.logo = base64.b64encode(_PNG_1PX).decode("ascii")
    r.inhaltsverzeichnis = False
    h = Report(m, an, options={"umfang": "kurz", "date": "12.09.2026"}).html()
    check("Rahmen: Kopfzeile mit Projekt, Bauteil, Position; Fusszeile mit Bearbeiter und Datum",
          "Halle Nord · Rahmen · Pos. 7" in h and "AM · 12.09.2026" in h and 'class="kopfzeile"' in h
          and 'class="fusszeile"' in h)
    check("Rahmen: Raender und Schrift in @page/body, Logo auf dem Titelblatt, kein Inhaltsverzeichnis",
          "margin: 18mm 16mm 20mm 25mm" in h and "font-size: 9.5pt" in h and 'class="logo"' in h
          and '<nav class="toc">' not in h)
    r.kopf = "{projekt} · {auftraggeber}"
    m.meta["auftraggeber"] = ""
    h = Report(m, an, options={"umfang": "kurz"}).html()
    check("leere Platzhalter fallen weg", ">Halle Nord</span>" in h, h[h.find('class="kopfzeile"'):][:90])
    r.titelblatt = False
    h = Report(m, an, options={"umfang": "kurz"}).html()
    check("ohne Titelblatt steht der Titel als Ueberschrift", 'class="titlepage"' not in h
          and "Statischer Bericht – " in h)
    d = Model.from_dict(m.to_dict())
    check("Rahmen wird mit dem Modell gespeichert", d.bericht_rahmen is not None
          and d.bericht_rahmen.rand_links_mm == 25.0 and d.bericht_rahmen.titelblatt is False)
    # Gliederung
    lf = list(m.load_cases)[0]
    m.bericht = [
        Berichtseintrag(name="Vorbemerkung", art="text", nach="general",
                        text="# Aufgabe\nDer Rahmen wird nachgerechnet.\n\n- Lasten nach Angabe\n- Stahl S355"),
        Berichtseintrag(name="Stabkräfte", art="tabelle", tabelle="Stabkräfte", quelle=f"case:{lf}",
                        nach="results"),
        Berichtseintrag(name="Skizze", art="datei", datei="skizze.svg", typ="svg",
                        daten=base64.b64encode(b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
                                               b'<rect width="10" height="10"/></svg>').decode("ascii")),
        Berichtseintrag(name="Messwerte", art="datei", datei="mess.csv", typ="csv",
                        daten=base64.b64encode("Stelle;Wert\nA;1,5\nB;2,5\n".encode("utf-8")).decode("ascii")),
        Berichtseintrag(name="Foto", art="datei", datei="foto.png", typ="png",
                        daten=base64.b64encode(_PNG_1PX).decode("ascii"), beschriftung="Baustelle"),
        Berichtseintrag(name="Notiz", art="datei", datei="notiz.md", typ="md",
                        daten=base64.b64encode("Erster Absatz.\n\nZweiter Absatz.".encode("utf-8")).decode("ascii")),
        Berichtseintrag(name="Gutachten", art="datei", datei="gutachten.pdf", typ="pdf", daten=""),
        Berichtseintrag(name="Auflager", art="tabelle", tabelle="Auflagerkräfte", quelle="env:GZT"),
    ]
    r.titelblatt = True
    r.inhaltsverzeichnis = True
    rep = Report(m, an, options={"umfang": "kurz"})
    h = rep.html()
    nav = h.find("</nav>")                       # das Inhaltsverzeichnis nennt alle Kapitel
    i_sys = h.find('id="k2"', nav)               # Kapitel 2 = System
    i_text = h.find("Der Rahmen wird nachgerechnet.", nav)
    check("Text nach „Allgemeines“: vor dem Kapitel System, mit Ueberschrift und Aufzaehlung",
          nav < i_text < i_sys and "<h4>Aufgabe</h4>" in h and "<li>Stahl S355</li>" in h,
          f"{nav} < {i_text} < {i_sys}")
    i_tab = h.find(f"Stabkräfte – Lastfall {lf}", nav)
    i_design = h.find("Nachweise nach DIN EN 1993-1-1", nav)
    check("Tabelle Stabkraefte nach „Ergebnisse“: vor den Nachweisen, mit Werten",
          nav < i_tab < i_design and "N1 [kN]" in h, f"{i_tab} < {i_design}")
    ende = h.find("Übernommene Ergebnisse", nav)
    i_rect = h.find('<rect width="10"', ende)
    i_csv = h.find(">2,5<", ende)
    check("Dateien ohne Platz stehen am Ende: SVG als Figur, CSV als Tabelle, PNG als Bild, MD als Absaetze",
          ende > 0 and i_rect > 0 and i_csv > 0
          and h.find("Baustelle", ende) > 0 and h.find("Zweiter Absatz.", ende) > 0,
          f"ende {ende}, rect {i_rect}, csv {i_csv}")
    check("PDF wird nicht eingebettet, sondern genannt; Auflagerkraefte brauchen ein Ergebnis",
          "gutachten.pdf: PDF-Dateien werden nicht eingebettet" in h
          and "Auflagerkräfte gibt es zu Lastfall oder Kombination" in h)
    md = rep.to_markdown()
    check("Markdown kennt die Ueberschrift des Textes", "#### Aufgabe" in md)
    # Ermuedungslast mit globaler Lastspielzahl (None): der Bericht nennt "global" statt zu reissen
    from statik3d.model import FatigueLoad
    m.fatigue_loads["Eglobal"] = FatigueLoad("Eglobal", folge=[lf, lf], wiederholungen=None)
    m.fatigue_loads["Zglobal"] = FatigueLoad("Zglobal", case_max=lf, case_min="", cycles=None)
    hg = Report(m, an, options={"umfang": "kurz"}).html()
    check("Ermuedungslasten mit globaler Lastspielzahl stehen im Bericht als „(global)“",
          "2e+06 (global)" in hg and hg.count("(global)") >= 2, str(hg.count("(global)")))
    del m.fatigue_loads["Eglobal"], m.fatigue_loads["Zglobal"]
    d = Model.from_dict(m.to_dict())
    check("Eintraege ueberleben Speichern und Laden (Art, Text, Platz)",
          len(d.bericht) == 8 and d.bericht[0].art == "text" and d.bericht[0].nach == "general"
          and d.bericht[1].tabelle == "Stabkräfte" and d.bericht[4].typ == "png")
    _assert_since(n0)


def test_grosses_netz():
    """Grosse Netze: Umrisse der Koerper statt Facetten, Lastbilder begrenzt.
    Die Grenze wird fuer die Pruefung auf 1 gesetzt (der Wuerfel hat mehr
    Elemente), gemessen wird die Zeit fuer die Systemdarstellung."""
    import time
    from statik3d.report import svg as sv2
    n0 = len(RESULTS)
    m = solid_example()
    for i in range(3):
        m.add_load_case(f"Q{i}", "Q")
        m.active_case = f"Q{i}"
        m.load_node(0, Fz=-1000.0)
    alt = sv2.GROSS_AB
    try:
        t0 = time.time()
        voll = sv2.draw_structure(m, "iso", 600, 400)
        t_voll = time.time() - t0
        sv2.GROSS_AB = 1
        t0 = time.time()
        umriss = sv2.draw_structure(m, "iso", 600, 400)
        t_umriss = time.time() - t0
        check("gross: Umriss statt Facetten - viel weniger Polygone, mindestens ein Umriss",
              umriss.count("<polygon") < voll.count("<polygon") and umriss.count("<polygon") >= 1
              and "fill-opacity" in umriss,
              f"{umriss.count('<polygon')} statt {voll.count('<polygon')} Polygone, "
              f"{t_umriss * 1e3:.0f} ms statt {t_voll * 1e3:.0f} ms")
        check("gross: der Hinweis nennt die vereinfachte Darstellung",
              "Umrisse der Volumenkörper" in sv2.figur_hinweis(m) and sv2.ist_gross(m))
        rep = Report(m, options={"umfang": "kurz"})
        h = rep.html()
        check("Kurzform: Lastbilder fuer 3 Lastfaelle, kein weiteres; Hinweis in der Unterschrift",
              h.count("Lasten des Lastfalls") == 3 and "Umrisse der Volumenkörper statt des Netzes" in h,
              f"{h.count('Lasten des Lastfalls')} Lastbilder")
        rep2 = Report(m, options={"umfang": "kurz", "max_case_figures": 1})
        h2 = rep2.html()
        check("max_case_figures 1: ein Bild und der Hinweis auf die uebrigen",
              h2.count("Lasten des Lastfalls") == 1 and "Lastbilder für die ersten 1 Lastfälle" in h2)
    finally:
        sv2.GROSS_AB = alt
    check("kleines Netz: wieder Facetten", not sv2.ist_gross(m) and sv2.figur_hinweis(m) == "")
    _assert_since(n0)


_PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da"
    "6364f8cfc0000002030101c0d3c4e70000000049454e44ae426082")


def test_nicht_gefuehrt_ist_nicht_erfuellt():
    """Das Gesamturteil darf einen übersprungenen Nachweis nicht verschlucken.

    Zwei Befunde der Durchsicht vom 22.09.2026, beide in der einen Zeile, die
    ein Prüfer als Gesamturteil liest:

    * Ein Stab ohne Streckgrenze wird übersprungen (`ec3/design.py`) und stand
      mit Ausnutzung 0,000 als **erfüllt** in Tabelle und Statikdokument. Seine
      Null berührt weder die größte Ausnutzung noch die Liste der nicht
      erfüllten - er ging lautlos als bestanden durch.
    * `self.volumen` fehlte in der Statusprüfung **und** in der Liste der
      geführten Nachweise. Ein Modell, das nur aus Volumen besteht - am
      Drehlager der Regelfall -, bekam darum entweder „Es wurden keine
      Nachweise geführt" oder „Alle Nachweise erfüllt", während der geführte
      Volumennachweis riss.

    Geprüft wird die **Zeile im Bericht**, nicht der Rückgabewert einer
    Funktion: die Zeile ist es, die jemand liest.
    """
    n0 = len(RESULTS)
    from statik3d.ec3.design import MemberCheck
    from statik3d.ec3.volumen import VolumenCheck

    mc = MemberCheck("S1", "IPE 200", "S235", 1.0)
    check("ein geführter Nachweis mit kleiner Ausnutzung ist erfüllt",
          mc.status() == "erfüllt", mc.status())
    mc.util = 1.5
    check("mit großer Ausnutzung ist er es nicht", mc.status() == "NICHT erfüllt",
          mc.status())
    mc.util, mc.fehler = 0.0, "Werkstoff X ohne Streckgrenze"
    check("ohne Streckgrenze gilt er als nicht geführt - nicht als erfüllt",
          mc.status() == "nicht geführt", mc.status())

    # Und im Bericht: ein reißender Volumennachweis darf nicht als erfüllt
    # durchgehen. Gebaut wird ein Ergebnisobjekt von Hand - ein Modell zu
    # rechnen, das den Volumennachweis reißen lässt, wäre für diese Frage
    # der Umweg.
    m = build_beam_model()
    an = solver.solve_all(m, design=True)

    class _Vol:
        def __init__(self, bereiche):
            self.bereiche = bereiche
            self.kombinationen = []
            self.settings = {}

    riss = VolumenCheck(name="Lagerblock", n_elemente=10, material="S355",
                        fy=355e6, util=1.42, kombination="GZT1", element=7)
    an.volumen = _Vol({"Lagerblock": riss})
    html = Report(m, an).html()
    check("ein reißender Volumennachweis kippt das Gesamturteil",
          "Alle Nachweise erfüllt" not in html and "NICHT erfüllt" in html,
          "Gesamturteil sagt nicht mehr erfüllt")
    check("und der Volumenbereich steht mit seiner Ausnutzung darin",
          "Lagerblock" in html, "Bereich genannt")

    # Ein nicht geführter Volumenbereich: weder erfüllt noch nicht erfüllt
    offen = VolumenCheck(name="Achse", n_elemente=5, material="S355",
                         fehler="kein Kerbfall zugewiesen")
    an.volumen = _Vol({"Achse": offen})
    html2 = Report(m, an).html()
    check("ein nicht geführter Volumenbereich wird im Gesamturteil genannt",
          "geführten" in html2 or "nicht geführt" in html2,
          "Gesamturteil nennt die Lücke")
    check("und behauptet nicht, alle Nachweise seien erfüllt",
          "Alle Nachweise erfüllt." not in html2, "keine falsche Zusage")
    return len(RESULTS) - n0


def _kv_status(html: str, titel: str):
    """Die Zeile „Status“ des Schlüssel-Wert-Blocks mit der Überschrift *titel*
    im erzeugten HTML - oder None, wenn es den Block oder die Zeile nicht gibt."""
    blk = re.search(r'<div class="caption">' + re.escape(titel)
                    + r'</div><table class="kv"><tbody>(.*?)</tbody>', html, re.S)
    if not blk:
        return None
    zeile = re.search(r"<tr><th>Status</th><td>(.*?)</td></tr>", blk.group(1), re.S)
    return re.sub(r"<[^>]+>", "", zeile.group(1)) if zeile else None


def test_ermuedung_nicht_gefuehrt_im_bericht():
    """Befunde FE2, FE5, FE13, SV5 (22.09.2026): der Ermüdungseintrag, dessen
    Nachweis nicht oder nicht vollständig geführt wurde, im Bericht.

    Gemessen vor der Kur: ein Volumen, dessen einzige Ermüdungslast ihren
    Mindestzustand verliert, stand mit „Status: Nachweis erfüllt“, D 0.000
    und „Element -1 von 40“ im Bericht; beim Stab ebenso. Verlor von zwei
    Lasten eine ihren Mindestzustand (oder-EK), lautete das Gesamturteil
    „Alle Nachweise erfüllt.“ - der Hinweis stand nur darunter, und der
    Anhang schrieb „Die Modellprüfung ergab keine Beanstandungen“.

    Geprüft wird die **Zeile im Bericht**, wie im Test darüber.
    """
    n0 = len(RESULTS)
    import html as _html_text
    from tests.test_ermuedung_verlauf import _zugstab_volumen, _stab_oben_unten, _oder_ek

    # (1) Volumen: die einzige Last verliert ihren Mindestzustand
    m = _zugstab_volumen(1000e3, -400e3)
    m.add_fatigue_load("Zwei", "LF1", "FEHLT", 1e5)
    an = solver.solve_all(m, design=False, fatigue=True)
    html = Report(m, an).html()
    st = _kv_status(html, "Ermüdung Volumen V1")
    check("Ermüdung Volumen ohne Mindestzustand: Status „nicht geführt“",
          st is not None and "nicht geführt" in st and "erfüllt" not in st, repr(st))
    check("die Übersicht zeigt kein „Element -1“", "Element -1" not in html,
          "Element -1 gefunden" if "Element -1" in html else "")

    # (2) Stab: die einzige Last verliert ihren Mindestzustand
    ms = _stab_oben_unten()
    ms.add_fatigue_load("EL", "OBEN", "FEHLT", cycles=1e6)
    an = solver.solve_all(ms, fatigue=True)
    html = Report(ms, an).html()
    st = _kv_status(html, "Ermüdung Stab M1")
    check("Ermüdung Stab ohne Mindestzustand: Status „nicht geführt“",
          st is not None and "nicht geführt" in st and "erfüllt" not in st, repr(st))

    # (3) Zwei Lasten, eine mit oder-EK als Mindestzustand
    m = _zugstab_volumen(1000e3, -400e3)
    m.add_fatigue_load("Gut", "LF1", "LF2", 1e5)
    _oder_ek(m)
    m.add_fatigue_load("Schlecht", "LF1", "EK_oder", 1e5)
    an = solver.solve_all(m, design=False, fatigue=True)
    html = Report(m, an).html()
    check("Gesamturteil sagt nicht „Alle Nachweise erfüllt.“",
          "Alle Nachweise erfüllt." not in html, "")
    check("sondern nennt den Ermüdungsnachweis nicht vollständig geführt",
          "nicht vollständig geführt" in html, "")
    st = _kv_status(html, "Ermüdung Volumen V1")
    check("der Eintrag selbst heißt „unvollständig“ und nennt die Last",
          st is not None and "unvollständig" in st and "Schlecht" in st, repr(st))
    check("die Modellprüfung im Bericht meldet die oder-EK",
          "Die Modellprüfung ergab keine Beanstandungen" not in html
          and re.search(r"FEHLER: Ermüdungslast 'Schlecht'[^<]*EK_oder",
                        _html_text.unescape(html)) is not None, "")

    # (4) Dasselbe am Stab - der ursprünglichen Fehlerstelle des Befunds FE5.
    # (3) hielt nur den Volumenkörper: das Gesamturteil ohne den Stabteil
    # („if teil_e“ → „if False“) und der Stabzweig mit der alten bloßen
    # Warnung blieben bei 120/120 (Mangel 1 der Gegenprüfung, 23.09.2026,
    # Mutationen M10 und M11). Gegenprobe zuerst: „Gut“ allein ist erfüllt,
    # sonst sagte das Gesamturteil hier nichts über die fehlende Last.
    ms = _stab_oben_unten()
    ms.add_fatigue_load("Gut", "OBEN", "UNTEN", cycles=5e4)
    html = Report(ms, solver.solve_all(ms, fatigue=True)).html()
    check("Stab, Gegenprobe: „Gut“ allein → „Alle Nachweise erfüllt.“",
          "Alle Nachweise erfüllt." in html
          and _kv_status(html, "Ermüdung Stab M1") == "Nachweis erfüllt",
          repr(_kv_status(html, "Ermüdung Stab M1")))
    ek = ms.add_combination("EK_oder", {}, "FAT")
    ek.alternativen = [{"OBEN": 1.0}, {"UNTEN": 1.0}]
    ms.add_fatigue_load("Schlecht", "OBEN", "EK_oder", cycles=5e4)
    html = Report(ms, solver.solve_all(ms, fatigue=True)).html()
    check("Stab, eine von zwei Lasten fällt aus: nicht „Alle Nachweise erfüllt.“, "
          "sondern „nicht vollständig geführt“",
          "Alle Nachweise erfüllt." not in html
          and "nicht vollständig geführt wurden: 1 Stab (Ermüdung)" in html, "")
    st = _kv_status(html, "Ermüdung Stab M1")
    check("der Stabeintrag heißt „unvollständig“ und nennt die Last",
          st is not None and "unvollständig" in st and "Schlecht" in st, repr(st))
    _assert_since(n0)
    return len(RESULTS) - n0


def _hinweisliste(html: str) -> list:
    """Die Punkte der Liste "Offene Hinweise und Warnungen" der Zusammenfassung."""
    i = html.find("Offene Hinweise und Warnungen:")
    if i < 0:
        return []
    j = html.find("<ul>", i)
    k = html.find("</ul>", j)
    if j < 0 or k < 0:
        return []
    return re.findall(r"<li>(.*?)</li>", html[j:k], re.S)


def test_stab_ohne_streckgrenze_in_den_hinweisen():
    """Ein nicht geführter Stab gehört in jedem Umfang in die Hinweise.

    Der Grund (Werkstoff ohne Streckgrenze) lag nur in ``mc.warnings``, und
    die kamen allein über ``_member_design_blocks`` in die Hinweisliste.
    Dieser Block läuft im Umfang „kurz" - der Vorgabe des Berichtsrahmens -
    gar nicht, in „mittel" nur für die 20 am höchsten ausgenutzten Stäbe; ein
    Stab mit Ausnutzung 0,000 fällt dort zuerst heraus. Gemessen 22.09.2026
    im Umfang „kurz": 'ohne Streckgrenze' 0-mal im Bericht, die Statuszeile
    verweist auf „die Hinweise unten", und direkt darunter steht „Es liegen
    keine offenen Hinweise oder Warnungen vor."

    Derselbe Widerspruch auf einem zweiten Weg: die Berichtsoption „Nachweise
    EC3" (ReportDialog, ``design=False``). Das Nachweiskapitel kehrt dann früh
    zurück, die Zusammenfassung liest ``self.design`` aber weiter und nennt
    den Stab in der Statuszeile. Gemessen 23.09.2026 an 97df705 mit
    ``{"umfang": "kurz", "design": False}`` und ebenso „lang": Statuszeile
    „… nicht geführt wurden: 1 Stäbe (EC3) (siehe die Hinweise unten).",
    darunter „Es liegen keine offenen Hinweise oder Warnungen vor."
    """
    n0 = len(RESULTS)
    m = build_beam_model()
    m.add_material(Material("Frei", 210e9, 0.3, 7850.0))       # fy = None
    ids = mesher.line_of_beams(m, "Frei", "IPE 300", (0, 2, 0), (6, 2, 0), 6)
    m.fix(ids[0], [0, 1, 2, 3])
    m.fix(ids[-1], [1, 2, 3])
    els = [i for i, e in enumerate(m.elements) if e.mat == "Frei"]
    for e in els:
        m.load_beam(e, qz=-10000.0)
    m.add_member("Ohne_fy", els)
    an = solver.solve_all(m, design=True)
    for opts in ({"umfang": "kurz"}, {"umfang": "lang"},
                 {"umfang": "kurz", "design": False}, {"umfang": "lang", "design": False}):
        umfang = opts["umfang"] + (", Nachweise EC3 aus" if "design" in opts else "")
        html = Report(m, an, options=opts).html()
        hin = _hinweisliste(html)
        treffer = [h for h in hin if "Ohne_fy" in h and "ohne Streckgrenze" in h]
        check(f"Umfang {umfang}: die Hinweise nennen den Stab ohne Streckgrenze",
              len(treffer) == 1, f"{len(treffer)} Treffer in {len(hin)} Hinweisen")
        check(f"Umfang {umfang}: … und sagen, was zu tun ist",
              bool(treffer) and "Nachweis nicht geführt" in treffer[0]
              and "am Werkstoff" in treffer[0], treffer[0] if treffer else "–")
        check(f"Umfang {umfang}: nicht 'keine offenen Hinweise'",
              "keine offenen Hinweise" not in html, "")
        if "design" in opts:
            check(f"Umfang {umfang}: das Nachweiskapitel ist wirklich aus",
                  "Die Ausgabe der Nachweise ist deaktiviert." in html, "")

    # Umfang "mittel" mit mehr als 20 Staeben: die Details werden nach
    # Ausnutzung auf 20 gekuerzt, der Stab ohne f_y (0,000) steht am Ende
    y = 4.0
    for i in range(20):
        ids = mesher.line_of_beams(m, "S235", "IPE 300", (0, y, 0), (6, y, 0), 2)
        m.fix(ids[0], [0, 1, 2, 3])
        m.fix(ids[-1], [1, 2, 3])
        neu = [len(m.elements) - 2, len(m.elements) - 1]
        for e in neu:
            m.load_beam(e, qz=-10000.0)
        m.add_member(f"Zusatz{i + 1}", neu)
        y += 2.0
    an2 = solver.solve_all(m, design=True)
    html = Report(m, an2, options={"umfang": "mittel"}).html()
    check("Umfang mittel: 22 Stäbe, die Details sind gekürzt",
          len(an2.design.members) == 22 and "am höchsten ausgenutzten" in html,
          f"{len(an2.design.members)} Stäbe")
    hin = _hinweisliste(html)
    check("Umfang mittel, gekürzt: die Hinweise nennen den Stab ohne Streckgrenze",
          any("Ohne_fy" in h and "ohne Streckgrenze" in h for h in hin),
          f"{len(hin)} Hinweise")
    _assert_since(n0)


def _statuszeilen(html: str) -> list:
    """(Klasse, Text) jeder Statuszeile des Berichts."""
    return re.findall(r'<div class="status (ok|nok)">(.*?)</div>', html, re.S)


def _kennwert(html: str, schluessel: str):
    """Wert einer Zeile im Block "Wesentliche Ergebnisse" (None, wenn sie fehlt)."""
    t = re.search(r"<tr><th>" + re.escape(schluessel) + r"</th><td>(.*?)</td></tr>", html, re.S)
    return re.sub(r"<[^>]+>", "", t.group(1)) if t else None


def test_kein_stab_gefuehrt_keine_ausnutzung():
    """Ist kein einziger Stab geführt, gibt es keine größte Ausnutzung.

    Die Zusammenfassung bildete die größte Ausnutzung über **alle** Stäbe,
    auch über die nicht geführten. Gemessen 23.09.2026 an 97df705 (und
    genauso an 54b6f9a) mit einem einzigen Riegel aus einem Werkstoff ohne
    f_y, Umfang „kurz": „max. Ausnutzung Nachweise EC3 | 0.000", „maßgebend
    | Stab Riegel_ohne_fy: , Kombination , x = 0.00 m" und die Statuszeile
    „Alle **geführten** Nachweise erfüllt – nicht geführt wurden: 1 Stäbe
    (EC3)" (Wortlaut jenes Stands; die Sternchen standen wörtlich im Bericht),
    obwohl kein Nachweis geführt war. ``DesignResults.summary()``
    nennt in diesem Fall schon keine Ausnutzung mehr, der Bericht tat es.
    """
    n0 = len(RESULTS)
    m = Model("nur ohne fy")
    m.add_material(Material("Frei", 210e9, 0.3, 7850.0))       # fy = None
    m.add_section(make_section("IPE 300"))
    ids = mesher.line_of_beams(m, "Frei", "IPE 300", (0, 0, 0), (6, 0, 0), 6)
    m.fix(ids[0], [0, 1, 2, 3])
    m.fix(ids[-1], [1, 2, 3])
    m.case().category = "G"
    for e in range(6):
        m.load_beam(e, qz=-10000.0)
    m.add_member("Ohne_fy", list(range(6)))
    m.add_combination("K1", {"LF1": 1.0}, "ULS")
    an = solver.solve_all(m, design=True)
    check("Aufbau: der einzige Stab ist nicht geführt",
          list(an.design.members) == ["Ohne_fy"] and bool(an.design.members["Ohne_fy"].fehler)
          and an.fatigue is None and an.volumen is None, "")
    for umfang in ("kurz", "lang"):
        html = Report(m, an, options={"umfang": umfang}).html()
        wert = _kennwert(html, "max. Ausnutzung Nachweise EC3")
        check(f"nur nicht geführt, {umfang}: keine 'max. Ausnutzung Nachweise EC3'",
              wert is None, f"steht da: {wert}")
        mg = _kennwert(html, "maßgebend")
        check(f"nur nicht geführt, {umfang}: kein 'maßgebend' ohne Nachweis",
              mg is None, f"steht da: {mg}")
        st = _statuszeilen(html)
        check(f"nur nicht geführt, {umfang}: Statuszeile nok, nicht 'geführten … erfüllt'",
              len(st) == 1 and st[0][0] == "nok" and "erfüllt" not in st[0][1]
              and "nicht geführt wurden: 1 Stab (EC3)" in st[0][1], str(st))
        check(f"nur nicht geführt, {umfang}: der Stab steht in den Hinweisen",
              any("Ohne_fy" in h and "ohne Streckgrenze" in h for h in _hinweisliste(html)), "")

    # Gegenprobe: ein geführter Stab daneben - dann gibt es die Ausnutzung,
    # und sie stammt von ihm, nicht vom nicht geführten
    m2 = build_beam_model()
    m2.add_material(Material("Frei", 210e9, 0.3, 7850.0))
    ids = mesher.line_of_beams(m2, "Frei", "IPE 300", (0, 2, 0), (6, 2, 0), 6)
    m2.fix(ids[0], [0, 1, 2, 3])
    m2.fix(ids[-1], [1, 2, 3])
    els = [i for i, e in enumerate(m2.elements) if e.mat == "Frei"]
    for e in els:
        m2.load_beam(e, qz=-10000.0)
    m2.add_member("Ohne_fy", els)
    an2 = solver.solve_all(m2, design=True)
    html = Report(m2, an2, options={"umfang": "kurz"}).html()
    u_tr = an2.design.members["Traeger"].util
    wert = _kennwert(html, "max. Ausnutzung Nachweise EC3")
    check("Gegenprobe mit geführtem Träger: Ausnutzung des Trägers",
          wert is not None and abs(float(wert) - u_tr) < 1e-3, f"{wert} / {u_tr:.3f}")
    mg = _kennwert(html, "maßgebend") or ""
    check("Gegenprobe: maßgebend ist der Träger", mg.startswith("Stab Traeger:"), mg)
    st = _statuszeilen(html)
    check("Gegenprobe: 'Alle geführten … erfüllt – nicht geführt wurden'",
          len(st) == 1 and st[0][0] == "nok" and "geführten" in st[0][1]
          and "nicht geführt wurden: 1 Stab (EC3)" in st[0][1], str(st))
    _assert_since(n0)


def _alle_nachweise_reissen():
    """Einfeldträger, an dem jede Nachweisart reißt - für die Frage, ob der
    Hinweis „… NICHT erfüllt für“ auch bei ausgeschaltetem Kapitel dasteht.

    EC3, Ermüdung und Verformung werden gerechnet (q = 150 kN/m, eine
    Durchbiegungsgrenze von 0,1 mm gegen eine charakteristische
    GZG-Kombination). Beulen, Anschlüsse und Volumen hängen
    als Ergebnisobjekte von Hand daran: ein Modell zu rechnen, an dem sie
    reißen, wäre für diese Frage der Umweg - gelesen wird im Bericht nur die
    Ausnutzung (wie in test_nicht_gefuehrt_ist_nicht_erfuellt).
    """
    from statik3d.ec3.beulen import BeulCheck, BeulResults
    from statik3d.joints.anschluss import AnschlussCheck, AnschlussResults
    from statik3d.ec3.volumen import VolumenCheck, VolumenResults
    m = build_beam_model()
    for e in range(6):
        m.load_beam(e, qz=-140000.0)            # zusammen mit den 10 kN/m: 150 kN/m
    m.add_combination("S1", {"LF1": 1.0}, "SLS_CH")
    m.add_verformungsgrenze("Durchbiegung", "stab", stab="Traeger", groesse="uz",
                            grenzart="absolut", wert=1e-4, situation="")
    an = solver.solve_all(m, design=True, fatigue=True)
    an.beulen = BeulResults(felder={"Blech": BeulCheck(name="Blech", a=1.0, b=0.5,
                                                       t=0.01, fy=235e6, util=1.3,
                                                       kombination="K1")},
                            kombinationen=["K1"])
    an.joints = AnschlussResults(joints={"Stoss": AnschlussCheck(
        name="Stoss", elem=0, ort="Anfang", util=1.2, kombination="K1",
        massgebend="Abscheren")}, combinations=["K1"])
    an.volumen = VolumenResults(bereiche={"Lagerblock": VolumenCheck(
        name="Lagerblock", n_elemente=10, material="S355", fy=355e6, util=1.42,
        kombination="K1", element=7)}, kombinationen=["K1"])
    return m, an


def test_nicht_erfuellt_auch_bei_ausgeschaltetem_kapitel():
    """Der Hinweis „… NICHT erfüllt für“ steht in den Hinweisen, auch wenn die
    Berichtsoption des Nachweiskapitels ausgeschaltet ist.

    Er entstand im Nachweiskapitel, und das kehrt bei ausgeschalteter Option
    früh zurück; die Zusammenfassung liest die Ergebnisse aber unabhängig von
    der Option und schrieb „Nachweise NICHT erfüllt – siehe die
    Nachweiskapitel.“ Gemessen 23.09.2026 an ec6448c: IPE 300 mit Ausnutzung
    9,5 und „Nachweise EC3“ aus - Hinweisliste leer, darunter „Es liegen
    keine offenen Hinweise oder Warnungen vor.“, und das Kapitel, auf das die
    Statuszeile verweist, sagt nur „Die Ausgabe der Nachweise ist
    deaktiviert.“ Ebenso gemessen mit „Ermüdung“ aus (Kragarm, D = 12185);
    Volumen, Beulen, Anschlüsse und Verformung folgten demselben Muster
    (gelesen).
    """
    n0 = len(RESULTS)
    m, an = _alle_nachweise_reissen()
    faelle = (("design", "Nachweise NICHT erfüllt für:", "Traeger",
               "Die Ausgabe der Nachweise ist deaktiviert."),
              ("fatigue", "Ermüdungsnachweis NICHT erfüllt für:", "Traeger",
               "Die Ausgabe des Ermüdungsnachweises ist deaktiviert."),
              ("gzg", "Verformungsnachweis NICHT erfüllt für:", "Durchbiegung",
               "Die Ausgabe der Verformungsnachweise ist deaktiviert."),
              ("beulen", "Beulnachweis NICHT erfüllt für:", "Blech",
               "Die Ausgabe der Beulnachweise ist deaktiviert."),
              ("joints", "Anschlussnachweis NICHT erfüllt für:", "Stoss",
               "Die Ausgabe der Anschlussnachweise ist deaktiviert."),
              ("volumen", "Volumennachweis NICHT erfüllt für:", "Lagerblock", None))
    check("Aufbau: jede Nachweisart reißt",
          an.design.members["Traeger"].util > 1.0
          and an.fatigue.members["Traeger"].util > 1.0
          and an.gzg.checks["Durchbiegung"].util > 1.0,
          f"EC3 {an.design.members['Traeger'].util:.2f}, "
          f"Ermüdung {an.fatigue.members['Traeger'].util:.0f}, "
          f"GZG {an.gzg.checks['Durchbiegung'].util:.1f}")

    # Gegenprobe: alle Kapitel an - jeder Hinweis genau einmal, die
    # Statuszeile verweist auf die Nachweiskapitel
    html = Report(m, an, options={"umfang": "kurz"}).html()
    hin = _hinweisliste(html)
    for _key, kopf, name, _aus in faelle:
        treffer = [h for h in hin if h.startswith(kopf)]
        check(f"alle Kapitel an: „{kopf} {name}“ genau einmal",
              len(treffer) == 1 and name in treffer[0], str(treffer))
    st = _statuszeilen(html)
    check("alle Kapitel an: Statuszeile verweist auf die Nachweiskapitel",
          st == [("nok", "Nachweise NICHT erfüllt – siehe die Nachweiskapitel.")], str(st))

    for key, kopf, name, aus in faelle:
        html = Report(m, an, options={"umfang": "kurz", key: False}).html()
        if aus is not None:
            check(f"{key} aus: das Kapitel ist wirklich aus", aus in html, "")
        else:
            check(f"{key} aus: das Kapitel ist wirklich aus",
                  "Spannungsnachweise der Volumenbereiche" not in html, "")
        hin = _hinweisliste(html)
        treffer = [h for h in hin if h.startswith(kopf)]
        check(f"{key} aus: die Hinweise nennen „{kopf} {name}“",
              len(treffer) == 1 and name in treffer[0], f"{len(hin)} Hinweise: {treffer}")
        check(f"{key} aus: nicht 'keine offenen Hinweise'",
              "keine offenen Hinweise" not in html, "")
        st = _statuszeilen(html)
        check(f"{key} aus: Statuszeile verweist auf die Hinweise, nicht auf das Kapitel",
              st == [("nok", "Nachweise NICHT erfüllt – siehe die Hinweise unten.")], str(st))
    _assert_since(n0)


def test_ermuedung_nur_nicht_gefuehrt_ist_kein_nachweis():
    """Ist jeder Ermüdungseintrag (Stab oder Volumen) bzw. jeder
    Volumenbereich nicht geführt, ist **kein** Nachweis geführt.

    ``gefuehrt`` in chapter_summary war wahr, sobald ``f.members``,
    ``f.volumen`` oder ``vo.bereiche`` nicht leer waren - auch wenn jeder
    Eintrag ``fehler`` trug. Gemessen 23.09.2026 an ec6448c mit der einzigen
    Ermüdungslast auf dem nicht gerechneten Höchstzustand „FEHLT“: am Kragarm
    „Alle **geführten** Nachweise erfüllt – nicht geführt wurden: 1 Stäbe
    (Ermüdung) …“, am Zugstab-Volumen dieselbe Zeile mit „1 Volumenkörper
    (Ermüdung)“, obwohl in beiden Fällen kein Nachweis geführt war.
    """
    n0 = len(RESULTS)
    from statik3d.model import FatigueLoad
    from statik3d.ec3.volumen import VolumenCheck, VolumenResults
    from tests.test_ermuedung_verlauf import _kragarm, _zugstab_volumen
    for titel, m, teil in (("Stab", _kragarm(), "(Ermüdung)"),
                           ("Volumen", _zugstab_volumen(1000e3, -400e3),
                            "Volumenkörper (Ermüdung)")):
        m.fatigue_loads.clear()
        m.fatigue_loads["N"] = FatigueLoad("N", case_max="FEHLT", case_min="LF2", cycles=1e5)
        an = solver.solve_all(m, design=False, fatigue=True)
        eintraege = list(an.fatigue.members.values()) + list(an.fatigue.volumen.values())
        check(f"Ermüdung {titel}: Aufbau, ein Eintrag, nicht geführt",
              len(eintraege) == 1 and bool(eintraege[0].fehler)
              and an.design is None and an.volumen is None and an.gzg is None,
              str([e.fehler for e in eintraege]))
        html = Report(m, an).html()
        st = _statuszeilen(html)
        check(f"Ermüdung {titel}: Statuszeile 'Kein Nachweis geführt – …'",
              len(st) == 1 and st[0][0] == "nok"
              and st[0][1].startswith("Kein Nachweis geführt – nicht geführt wurden: ")
              and teil in st[0][1], str(st))
        check(f"Ermüdung {titel}: und keine 'max. Schädigung Ermüdung'",
              _kennwert(html, "max. Schädigung Ermüdung") is None, "")

    # Volumenbereiche: nur nicht geführte bzw. nur berichtete (singuläre)
    m = build_beam_model()
    an = solver.solve_all(m)                    # ohne Nachweise
    an.volumen = VolumenResults(bereiche={"Achse": VolumenCheck(
        name="Achse", n_elemente=5, material="S355", fehler="erzwungen")})
    st = _statuszeilen(Report(m, an).html())
    check("nur ein nicht geführter Volumenbereich: 'Kein Nachweis geführt – …'",
          len(st) == 1 and st[0][0] == "nok"
          and st[0][1].startswith("Kein Nachweis geführt – nicht geführt wurden: "), str(st))
    an.volumen = VolumenResults(bereiche={"Ecke": VolumenCheck(
        name="Ecke", n_elemente=5, material="S355", fy=355e6, util=0.5, singular=True)})
    st = _statuszeilen(Report(m, an).html())
    check("nur ein singulärer (nur berichteter) Bereich: nicht 'Alle Nachweise erfüllt.'",
          len(st) == 1 and st[0][1].startswith("Es wurden keine Nachweise geführt"), str(st))
    # Gegenprobe: ein geführter Bereich daneben zählt
    an.volumen = VolumenResults(bereiche={
        "Achse": VolumenCheck(name="Achse", n_elemente=5, material="S355", fehler="erzwungen"),
        "Block": VolumenCheck(name="Block", n_elemente=5, material="S355", fy=355e6,
                              util=0.5, kombination="K1", element=1)})
    st = _statuszeilen(Report(m, an).html())
    check("Gegenprobe mit geführtem Bereich: 'Alle geführten Nachweise erfüllt – …'",
          len(st) == 1 and st[0][1].startswith("Alle geführten Nachweise erfüllt – "), str(st))
    _assert_since(n0)


def test_gesamturteil_einzahl_und_mehrzahl():
    """„1 Stab“, „2 Stäbe“ - das Gesamturteil schrieb bei einem Eintrag
    „1 Stäbe (EC3)“ und „1 Stäbe (Ermüdung)“ (gemessen 23.09.2026 an
    ec6448c)."""
    n0 = len(RESULTS)
    from statik3d.ec3.volumen import VolumenCheck, VolumenResults
    m = build_beam_model()
    m.add_material(Material("Frei", 210e9, 0.3, 7850.0))       # fy = None
    for k, y in enumerate((2.0, 4.0)):
        ids = mesher.line_of_beams(m, "Frei", "IPE 300", (0, y, 0), (6, y, 0), 2)
        m.fix(ids[0], [0, 1, 2, 3])
        m.fix(ids[-1], [1, 2, 3])
        neu = [len(m.elements) - 2, len(m.elements) - 1]
        for e in neu:
            m.load_beam(e, qz=-10000.0)
        m.add_member(f"Ohne_fy{k + 1}", neu)
    an = solver.solve_all(m, design=True)
    st = _statuszeilen(Report(m, an, options={"umfang": "kurz"}).html())
    check("zwei Stäbe ohne f_y: '2 Stäbe (EC3)'",
          len(st) == 1 and "nicht geführt wurden: 2 Stäbe (EC3)" in st[0][1], str(st))
    m2 = build_beam_model()
    an2 = solver.solve_all(m2)
    for n, soll in ((1, "1 Volumenbereich (siehe"), (2, "2 Volumenbereiche (siehe")):
        an2.volumen = VolumenResults(bereiche={
            f"B{i}": VolumenCheck(name=f"B{i}", n_elemente=5, material="S355",
                                  fehler="erzwungen") for i in range(n)})
        st = _statuszeilen(Report(m2, an2).html())
        check(f"{n} nicht geführte Volumenbereiche: '{soll}'",
              len(st) == 1 and soll in st[0][1], str(st))
    _assert_since(n0)


def test_statuszeile_ohne_sternchen():
    """Die Statuszeile „Alle geführten Nachweise erfüllt – …“ trug Sternchen
    („Alle **geführten** …“). HTML maskiert sie, sie standen wörtlich im
    Bericht; Markdown setzt die Statuszeile selbst fett, daraus wurde
    verschachteltes Fett „> **Alle **geführten** … unten).**“ (gemessen
    23.09.2026 an ec6448c, Einfeldträger mit einem Stab ohne f_y)."""
    n0 = len(RESULTS)
    m = build_beam_model()
    m.add_material(Material("Frei", 210e9, 0.3, 7850.0))
    ids = mesher.line_of_beams(m, "Frei", "IPE 300", (0, 2, 0), (6, 2, 0), 6)
    m.fix(ids[0], [0, 1, 2, 3])
    m.fix(ids[-1], [1, 2, 3])
    els = [i for i, e in enumerate(m.elements) if e.mat == "Frei"]
    for e in els:
        m.load_beam(e, qz=-10000.0)
    m.add_member("Ohne_fy", els)
    rep = Report(m, solver.solve_all(m, design=True), options={"umfang": "kurz"})
    st = _statuszeilen(rep.html())
    check("HTML: Statuszeile 'Alle geführten Nachweise erfüllt – …' ohne '**'",
          len(st) == 1 and st[0][1].startswith("Alle geführten Nachweise erfüllt – ")
          and "*" not in st[0][1], str(st))
    md = [z for z in rep.to_markdown().splitlines() if z.startswith("> ")]
    check("Markdown: eine Statuszeile mit genau einem Fettpaar",
          len(md) == 1 and md[0].startswith("> **Alle geführten Nachweise erfüllt – ")
          and md[0].endswith("**") and md[0].count("**") == 2, str(md))
    _assert_since(n0)


def test_keine_sternchen_im_berichtstext():
    """Absätze und Listenpunkte gehen durch esc() - Markdown-Sternchen darin
    stehen wörtlich im HTML und im PDF. Gemessen 23.09.2026 an ec6448c:
    „Die Schädigung wird **am Ort** aufsummiert“ (Ermüdung, Grundlagen) und
    „w bezogen auf die **Sehne**“ (Verformung, Grundlagen)."""
    n0 = len(RESULTS)
    m = build_beam_model()
    m.add_verformungsgrenze("Durchbiegung", "stab", stab="Traeger", groesse="uz",
                            grenzart="L/x", wert=300, situation="")
    html = Report(m, solver.solve_all(m, design=True, fatigue=True)).html()
    ohne_svg = _SVG_RE.sub("", html)
    texte = re.findall(r"<(?:li|p)>(.*?)</(?:li|p)>", ohne_svg, re.S)
    texte += [t for _k, t in _statuszeilen(ohne_svg)]
    mit = [t[:70] for t in texte if "**" in t]
    check("Aufbau: Ermüdung und Verformung stehen im Bericht",
          "Die Schädigung wird am Ort aufsummiert" in html.replace("**", "")
          and "bezogen auf die" in html, "")
    check("kein Absatz, Listenpunkt oder Statustext mit '**'", not mit, str(mit))
    _assert_since(n0)


def _ergebniszeile(html: str, name: str):
    """Zellen der Zeile *name* der Tabelle „Rechenzeiten je Ergebnis“."""
    i = html.find("Rechenzeiten je Ergebnis")
    if i < 0:
        return None
    k = html.find("</table>", i)
    for z in re.findall(r"<tr>(.*?)</tr>", html[i:k], re.S):
        zellen = [re.sub(r"<[^>]+>", "", c) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", z, re.S)]
        if zellen and zellen[0] == name:
            return zellen
    return None


def test_loeserspalte_nennt_ausweichen():
    """Die Spalte „Löser“ der Tabelle „Rechenzeiten je Ergebnis“ zeigte nur
    ``info["solver"]``, den Löser der letzten Faktorisierung. Scheitert
    PARDISO nur in einem Teil der Faktorisierungen, steht dort wieder
    „pardiso“ (solver.ausweich_info, 23.09.2026). Gemessen an ec6448c mit so
    gesetztem ``info``: Zeile „LF1 | Lastfall | … | pardiso | –“, während
    Anhang und Hinweise das Ausweichen auf SuperLU nannten."""
    n0 = len(RESULTS)
    m = build_beam_model()
    an = solver.solve_all(m)
    res = an.cases["LF1"]
    vorher = _ergebniszeile(Report(m, an).html(), "LF1")
    check("ohne Ausweichen: Spalte 'Löser' ist der Löser selbst",
          vorher is not None and vorher[3] == str(res.info.get("solver"))
          and "ausgewichen" not in vorher[3], str(vorher))
    res.info["solver"] = "pardiso"
    res.info["ausweichen"] = [("PARDISO: erzwungen für die Prüfung", "superlu")]
    html = Report(m, an).html()
    zeile = _ergebniszeile(html, "LF1")
    check("teilweise ausgewichen: 'pardiso – ausgewichen auf SuperLU …'",
          zeile is not None and zeile[3].startswith("pardiso – ausgewichen auf SuperLU"),
          str(zeile))
    # Nur hier von Hand: K1 wurde vor dem Setzen überlagert und trägt darum
    # keinen Ausweich-Eintrag. In einer echten Rechnung trägt sie den ihrer
    # Lastfälle - das prüft test_loeserspalte_ausweichen_echte_rechnung.
    k1 = _ergebniszeile(html, "K1")
    check("Überlagerung ohne Ausweich-Eintrag: Spalte 'Löser' bleibt '–'",
          k1 is not None and k1[3] == "–", str(k1))
    # ganz ausgewichen: der Löser heißt schon so - kein „auf SuperLU“ doppelt
    res.info["solver"] = "superlu"
    zeile = _ergebniszeile(Report(m, an).html(), "LF1")
    check("ganz ausgewichen: 'superlu – ausgewichen'",
          zeile is not None and zeile[3] == "superlu – ausgewichen", str(zeile))
    _assert_since(n0)


def test_loeserspalte_ausweichen_echte_rechnung():
    """Spalte „Löser“ an einer echten Rechnung, in der PARDISO beim
    Faktorisieren scheitert (Aufbau wie
    test_loeser.test_ausweichgrund_erreicht_ergebnis_bericht_und_modalanalyse).
    Eine überlagerte Kombination hat kein eigenes ``info["solver"]``, trägt
    aber das Ausweichen ihrer Lastfälle (Results.combine). Gemessen
    24.09.2026 an 0b7d95b: Spalte der K1 „– – ausgewichen auf SuperLU
    (direkt, einkernig)“, LF1 und LF2 „superlu – ausgewichen“."""
    n0 = len(RESULTS)
    import pypardiso
    from statik3d import parallel
    from statik3d.solver import ausweich_paare
    from tests.test_loeser import _k2_modell
    alt_backend = parallel.settings().solver_backend
    parallel.configure(solver_backend="auto")
    echt = pypardiso.PyPardisoSolver.factorize

    def wirft(self, A):
        raise RuntimeError("Probe: PARDISO verweigert")

    pypardiso.PyPardisoSolver.factorize = wirft
    try:
        m = _k2_modell()
        an = solver.solve_all(m)
    finally:
        pypardiso.PyPardisoSolver.factorize = echt
        parallel.configure(solver_backend=alt_backend)
    k1 = an.all_results()["K1"]
    check("Aufbau: K1 ist eine Überlagerung ohne eigenen Löser und trägt das Ausweichen",
          k1.info.get("superposition") and not k1.info.get("solver")
          and ausweich_paare(k1.info), str({k: k1.info.get(k) for k in
                                           ("superposition", "solver", "ausweichen")}))
    html = Report(m, an).html()
    for n in ("LF1", "LF2"):
        z = _ergebniszeile(html, n)
        check(f"{n}: Spalte 'Löser' 'superlu – ausgewichen'",
              z is not None and z[3] == "superlu – ausgewichen", str(z))
    z = _ergebniszeile(html, "K1")
    check("K1: 'ausgewichen auf SuperLU …' ohne vorangestellten Strich",
          z is not None and z[3].startswith("ausgewichen auf SuperLU") and "–" not in z[3],
          str(z))
    _assert_since(n0)


def main():
    print("=" * 96)
    print("STATIK3D - Test statischer Bericht (HTML / Markdown / PDF / SVG)")
    print("=" * 96)
    tests = [test_kontaktwarnungen_der_uebrigen_ergebnisse,
             test_deckelzeilen_mit_rundenbilanz_werden_gebuendelt,
             test_beam_report, test_frame_report, test_contact_report, test_plate_and_solid,
             test_svg_helpers, test_kontaktbedingungen_im_bericht, test_pdf, test_fortschritt,
             test_gliederung_und_rahmen, test_grosses_netz,
             test_nicht_gefuehrt_ist_nicht_erfuellt,
             test_ermuedung_nicht_gefuehrt_im_bericht,
             test_stab_ohne_streckgrenze_in_den_hinweisen,
             test_kein_stab_gefuehrt_keine_ausnutzung,
             test_nicht_erfuellt_auch_bei_ausgeschaltetem_kapitel,
             test_ermuedung_nur_nicht_gefuehrt_ist_kein_nachweis,
             test_gesamturteil_einzahl_und_mehrzahl,
             test_statuszeile_ohne_sternchen,
             test_keine_sternchen_im_berichtstext,
             test_loeserspalte_nennt_ausweichen,
             test_loeserspalte_ausweichen_echte_rechnung]
    for t in tests:
        try:
            t()
        except AssertionError:
            pass                       # Einzelchecks bereits protokolliert
        except Exception as ex:        # Absturz eines Tests als FAIL ausweisen
            import traceback
            traceback.print_exc()
            check(f"{t.__name__}: Ausnahme", False, repr(ex))
    nok = sum(1 for r in RESULTS if r[1])
    print("=" * 96)
    print(f"Ergebnis: {nok}/{len(RESULTS)} Tests bestanden")
    return 0 if nok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
