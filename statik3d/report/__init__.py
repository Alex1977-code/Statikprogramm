"""
Statischer Bericht (pruefbare Dokumentation) fuer Statik3D.

    from statik3d.report import Report, write_report
    an = solver.solve_all(model, design=True, fatigue=True)
    Report(model, an).to_html("bericht.html")
    write_report(model, an, "bericht.md", fmt="md")
    write_report(model, an, "bericht.pdf", fmt="pdf")     # benoetigt reportlab

Module:
    svg.py   Zeichenhilfen (Systemdarstellung, Diagramme, Woehlerlinie)
    html.py  Report-Klasse (HTML, Markdown, Kapitelaufbau)
    pdf.py   PDF-Export ueber reportlab (optional)
"""
from __future__ import annotations

from .html import Report, Util, fmt, table  # noqa: F401
from .pdf import print_hint, to_pdf  # noqa: F401
from . import svg  # noqa: F401


def write_report(model, analysis=None, path: str = "bericht.html", fmt: str = "html",
                 results=None, **options) -> str:
    """Bericht schreiben. fmt: 'html' | 'pdf' | 'md' (Markdown). Rueckgabe: Pfad.
    Zusaetzliche Schluesselwortargumente sind Berichtsoptionen (siehe Report.DEFAULTS)."""
    rep = Report(model, analysis, results=results, options=options or None)
    f = (fmt or "html").lower().lstrip(".")
    if f in ("html", "htm"):
        return rep.to_html(path)
    if f == "pdf":
        return rep.to_pdf(path)
    if f in ("md", "markdown"):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(rep.to_markdown())
        return path
    raise ValueError(f"Berichtsformat '{fmt}' unbekannt (html | pdf | md)")


__all__ = ["Report", "write_report", "print_hint", "to_pdf", "Util", "fmt", "table", "svg"]
