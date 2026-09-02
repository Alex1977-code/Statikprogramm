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


def test_pdf():
    n0 = len(RESULTS)
    m = build_beam_model()
    an = solver.solve_all(m, design=True, fatigue=True)
    rep = Report(m, an)
    path = os.path.join(_tmpdir(), "traeger.pdf")
    try:
        import reportlab  # noqa: F401
        have = True
    except ImportError:
        have = False
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


def main():
    print("=" * 96)
    print("STATIK3D - Test statischer Bericht (HTML / Markdown / PDF / SVG)")
    print("=" * 96)
    tests = [test_beam_report, test_frame_report, test_contact_report, test_plate_and_solid,
             test_svg_helpers, test_pdf]
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
