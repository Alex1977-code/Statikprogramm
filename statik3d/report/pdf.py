"""
PDF-Export des statischen Berichts mit reportlab (optional).

    from statik3d.report import Report
    Report(model, analysis).to_pdf("bericht.pdf")

Ohne installiertes reportlab wird ein RuntimeError mit Installationshinweis
ausgeloest. Abbildungen (SVG) werden ueber svglib eingebettet, wenn dieses
Paket vorhanden ist; andernfalls wird an ihrer Stelle ein Hinweis gesetzt.
Alternativ kann der HTML-Bericht in jedem Browser als PDF gedruckt werden
(siehe print_hint()).
"""
from __future__ import annotations

import io

from .. import __version__

MISSING = "PDF-Export benoetigt 'pip install reportlab' (optional svglib fuer Grafiken)"


def print_hint() -> str:
    """Hinweistext zum PDF-Druck des HTML-Berichts ueber den Browser."""
    return ("Der HTML-Bericht kann in jedem Browser (Chrome, Edge, Firefox) über "
            "Drucken (Strg+P) als PDF gespeichert werden: Ziel 'Als PDF speichern', "
            "Papierformat A4, Hintergrundgrafiken aktivieren. Seitenumbrüche vor den "
            "Hauptkapiteln, wiederholte Tabellenköpfe und Ränder sind im Dokument "
            "bereits eingestellt. Für einen direkten PDF-Export mit Seitenzahlen "
            "kann optional 'pip install reportlab svglib' installiert werden.")


def _para_text(s) -> str:
    """Text fuer reportlab-Paragraphs maskieren."""
    from xml.sax.saxutils import escape
    return escape(str(s))


def to_pdf(report, path: str) -> str:
    """Bericht als PDF schreiben (Platypus). Rueckgabe: Pfad."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT, TA_RIGHT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
                                        Spacer, Table, TableStyle)
    except ImportError as ex:
        raise RuntimeError(MISSING) from ex
    try:
        from svglib.svglib import svg2rlg
        have_svg = True
    except Exception:
        svg2rlg = None
        have_svg = False

    from .html import Util, Raw, fmt, _cell_text, _column_align

    styles = getSampleStyleSheet()
    base = ParagraphStyle("base", parent=styles["Normal"], fontName="Helvetica", fontSize=9,
                          leading=11.5)
    small = ParagraphStyle("small", parent=base, fontSize=7.5, leading=9)
    note = ParagraphStyle("note", parent=base, fontSize=8, leading=10, textColor=colors.grey)
    cap = ParagraphStyle("cap", parent=base, fontSize=8.5, leading=10.5, fontName="Helvetica-Bold",
                         spaceBefore=6, spaceAfter=2)
    h = {1: ParagraphStyle("h1", parent=base, fontName="Helvetica-Bold", fontSize=15, leading=18,
                           spaceBefore=8, spaceAfter=8, textColor=colors.HexColor("#1f3b73")),
         2: ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=12, leading=15,
                           spaceBefore=12, spaceAfter=5, textColor=colors.HexColor("#1f3b73")),
         3: ParagraphStyle("h3", parent=base, fontName="Helvetica-Bold", fontSize=10.5, leading=13,
                           spaceBefore=10, spaceAfter=4, textColor=colors.HexColor("#1f3b73")),
         4: ParagraphStyle("h4", parent=base, fontName="Helvetica-Bold", fontSize=9.5, leading=12,
                           spaceBefore=8, spaceAfter=3, textColor=colors.HexColor("#1f3b73"))}
    title_style = ParagraphStyle("title", parent=base, fontName="Helvetica-Bold", fontSize=24,
                                 leading=28, spaceAfter=10, textColor=colors.HexColor("#1f3b73"))
    right = ParagraphStyle("right", parent=base, alignment=TA_RIGHT, fontName="Courier",
                           fontSize=8, leading=10)
    right_small = ParagraphStyle("rights", parent=right, fontSize=7, leading=8.5)
    left_small = ParagraphStyle("lefts", parent=base, fontSize=7.5, leading=9, alignment=TA_LEFT)

    page_w, page_h = A4
    margin = 18 * mm
    avail_w = page_w - 2 * margin
    meta = dict(report._header_pairs()) if hasattr(report, "_header_pairs") else {}
    project = meta.get("Projekt", "")
    footer_left = f"Statik3D {__version__} – Statischer Bericht {report.model.name}" + \
        (f" – {project}" if project and project != "–" else "")

    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.grey)
        canvas.drawString(margin, 11 * mm, footer_left[:120])
        canvas.drawRightString(page_w - margin, 11 * mm, f"Seite {doc.page}")
        canvas.setStrokeColor(colors.lightgrey)
        canvas.line(margin, 14 * mm, page_w - margin, 14 * mm)
        canvas.restoreState()

    def cell_para(c, align_r, compact):
        st = (right_small if compact else right) if align_r else (left_small if compact else base)
        if isinstance(c, Util):
            col = "#1e7b34" if c.ok else "#b00020"
            return Paragraph(f'<font color="{col}"><b>{_para_text(fmt(c.value, c.digits))}</b></font>',
                             st)
        if isinstance(c, Raw):
            import re
            return Paragraph(_para_text(re.sub(r"<[^>]+>", "", str(c))), st)
        return Paragraph(_para_text(_cell_text(c)), st)

    def make_table(rows, header=True, compact=False):
        if not rows:
            return None
        al = _column_align(rows, header, None)
        ncol = len(al)
        data = []
        for i, r in enumerate(rows):
            r = list(r) + [""] * (ncol - len(r))
            if header and i == 0:
                hs = ParagraphStyle("hdr", parent=left_small if compact or ncol > 8 else base,
                                    fontName="Helvetica-Bold")
                data.append([Paragraph(_para_text(_cell_text(c)), hs) for c in r])
            else:
                data.append([cell_para(c, al[j] == "r", compact or ncol > 8)
                             for j, c in enumerate(r)])
        # Spaltenbreiten nach Textlaenge
        lens = []
        for j in range(ncol):
            mx = max(len(_cell_text(r[j])) if j < len(r) else 0 for r in rows)
            lens.append(min(max(mx, 3), 40))
        tot = float(sum(lens))
        widths = [avail_w * l / tot for l in lens]
        t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
        style = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b5b5b5")),
                 ("VALIGN", (0, 0), (-1, -1), "TOP"),
                 ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                 ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]
        if header:
            style.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8edf5")))
        t.setStyle(TableStyle(style))
        return t

    story = []
    # Titelblock
    story.append(Spacer(1, 30 * mm))
    story.append(Paragraph("Statischer Bericht", title_style))
    story.append(Paragraph(_para_text(report.model.name), h[2]))
    story.append(Spacer(1, 6 * mm))
    story.append(make_table([[k, v] for k, v in report._header_pairs()], header=False))
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(_para_text(
        "Prüffähige Dokumentation der Eingaben, Ergebnisse und Nachweise. Alle Werte in kN, "
        "kNm, mm und N/mm², sofern nicht anders angegeben."), note))
    story.append(PageBreak())
    blocks = report.blocks()
    # Inhalt
    story.append(Paragraph("Inhalt", h[1]))
    for level, number, title, _a in report._toc:
        if level <= 2:
            st = ParagraphStyle(f"toc{level}", parent=base, leftIndent=(level - 1) * 14,
                                fontName="Helvetica-Bold" if level == 1 else "Helvetica")
            story.append(Paragraph(f"{_para_text(number)}&nbsp;&nbsp;{_para_text(title)}", st))
    first = True
    skipped_figures = 0
    for blk in blocks:
        kind = blk[0]
        if kind == "h":
            _, level, number, title, _a = blk
            if level == 1:
                story.append(PageBreak())
                first = False
            story.append(Paragraph(f"{_para_text(number)}&nbsp;&nbsp;{_para_text(title)}",
                                   h.get(level, h[4])))
        elif kind == "p":
            story.append(Paragraph(_para_text(blk[1]), base))
        elif kind == "note":
            story.append(Paragraph(_para_text(blk[1]), note))
        elif kind == "list":
            for x in blk[1]:
                story.append(Paragraph("• " + _para_text(x), ParagraphStyle(
                    "li", parent=base, leftIndent=10, firstLineIndent=-8)))
        elif kind == "table":
            _, rows, caption, _al, cls = blk
            parts = []
            if caption:
                parts.append(Paragraph(_para_text(caption), cap))
            t = make_table(rows, True, cls == "compact")
            if t is not None:
                parts.append(t)
            if len(rows) <= 12:
                story.append(KeepTogether(parts))
            else:
                story.extend(parts)
            story.append(Spacer(1, 4))
        elif kind == "kv":
            _, pairs, caption = blk
            parts = []
            if caption:
                parts.append(Paragraph(_para_text(caption), cap))
            rows = [[k, v] for k, v in pairs]
            data = [[Paragraph(_para_text(k), base), cell_para(v, False, False)] for k, v in rows]
            t = Table(data, colWidths=[avail_w * 0.32, avail_w * 0.68])
            t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b5b5b5")),
                                   ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3f5f9")),
                                   ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            parts.append(t)
            story.append(KeepTogether(parts))
            story.append(Spacer(1, 4))
        elif kind == "figure":
            _, svg_text, caption = blk
            drawing = None
            if have_svg:
                try:
                    drawing = svg2rlg(io.StringIO(svg_text))
                except Exception:
                    drawing = None
            if drawing is not None:
                w = float(getattr(drawing, "width", avail_w) or avail_w)
                hgt = float(getattr(drawing, "height", w * 0.6) or w * 0.6)
                s = min(avail_w / w, (page_h - 2 * margin - 40 * mm) / hgt, 1.0)
                drawing.width, drawing.height = w * s, hgt * s
                drawing.scale(s, s)
                parts = [drawing]
                if caption:
                    parts.append(Paragraph(_para_text(caption), note))
                story.append(KeepTogether(parts))
            else:
                skipped_figures += 1
                story.append(Paragraph(_para_text(
                    f"[Abbildung: {caption} – Grafik nicht eingebettet"
                    + ("" if have_svg else ", 'pip install svglib' fuer Grafiken") + "]"), note))
            story.append(Spacer(1, 4))
        elif kind == "status":
            _, txt, ok = blk
            col = "#1e7b34" if ok else "#b00020"
            story.append(Paragraph(f'<font color="{col}"><b>{_para_text(txt)}</b></font>', base))
    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=margin, rightMargin=margin,
                            topMargin=margin, bottomMargin=margin + 4 * mm,
                            title=f"Statischer Bericht – {report.model.name}",
                            author=meta.get("Bearbeiter", ""), subject=project or "")
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return path
