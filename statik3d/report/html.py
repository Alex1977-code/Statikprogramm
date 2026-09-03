"""
Statischer Bericht (pruefbare Dokumentation) als HTML und Markdown.

Der Bericht wird zunaechst als Liste von Bloecken aufgebaut (Ueberschriften,
Absaetze, Tabellen, Abbildungen, Listen, Statuszeilen) und anschliessend in
HTML (druckfaehig, A4) oder Markdown gerendert; der PDF-Export (report.pdf)
verwendet dieselben Bloecke. Jedes Kapitel ist eine eigene Methode
(chapter_general, chapter_system, ...), die eine Blockliste liefert;
chapter_html(name) liefert das HTML eines einzelnen Kapitels.

Bloecke:
    ("h", level, nummer, titel, anker)
    ("p", text)                      Absatz (reiner Text)
    ("table", rows, caption, align, cls)
    ("kv", [(schluessel, wert), ...], caption)
    ("figure", svg, caption)
    ("list", [text, ...])
    ("status", text, ok)             hervorgehobene Statuszeile
    ("note", text)                   Hinweis (klein, kursiv)

Zellinhalte: Zeichenketten, Zahlen (werden mit fmt formatiert), Util
(Ausnutzungsgrad, im HTML farbig) oder Raw (fertiges HTML).
"""
from __future__ import annotations

import math

import datetime
import html as _html
import re

import numpy as np

from .. import __version__
from ..model import ACTION_CATEGORIES, DOF_NAMES
from ..combinations import combination_table
from . import svg as sv

# --------------------------------------------------------------------------
NORMS = [
    ("DIN EN 1990", "Grundlagen der Tragwerksplanung – Kombinationsregeln, Teilsicherheits- "
                    "und Kombinationsbeiwerte (mit Nationalem Anhang)"),
    ("DIN EN 1991", "Einwirkungen auf Tragwerke – Einwirkungskategorien und ψ-Beiwerte"),
    ("DIN EN 1993-1-1", "Stahlbau, allgemeine Bemessungsregeln – Querschnittsklassifizierung, "
                        "Querschnittsnachweise (6.2), Stabilitätsnachweise (6.3, Anhang B)"),
    ("DIN EN 1993-1-5", "Plattenförmige Bauteile – wirksame Querschnitte der Klasse 4, "
                        "Hinweis auf Schubbeulen"),
    ("DIN EN 1993-1-9", "Ermüdung – Nennspannungskonzept, Wöhlerlinien, Schadensakkumulation "
                        "nach Palmgren-Miner"),
    ("DIN 1080", "Begriffe, Formelzeichen und Einheiten im Bauingenieurwesen – "
                 "Vorzeichenkonvention der Schnittgrößen"),
]

ELEMENT_TYPES = {
    "beam": "Balken 3D (12 FHG, Timoshenko-Schub)",
    "truss": "Fachwerkstab (nur Normalkraft)",
    "shell3": "Schale, Dreieck (CST + DKT)",
    "shell4": "Schale, Viereck (in 2 Dreiecke zerlegt)",
    "tet4": "Tetraeder, linear",
    "tet10": "Tetraeder, quadratisch",
    "hex8": "Hexaeder mit inkompatiblen Moden",
}

COMBO_TYPES = {"ULS": "GZT (STR/GEO)", "EQU": "GZT (EQU)", "ACC": "außergewöhnlich",
               "SLS_CH": "GZG charakteristisch", "SLS_FR": "GZG häufig",
               "SLS_QP": "GZG quasi-ständig", "USER": "benutzerdefiniert"}

ENVELOPE_NAMES = {"ULS": "Grenzzustand der Tragfähigkeit (GZT)",
                  "SLS_CH": "Gebrauchstauglichkeit, charakteristisch",
                  "SLS_FR": "Gebrauchstauglichkeit, häufig",
                  "SLS_QP": "Gebrauchstauglichkeit, quasi-ständig",
                  "CASES": "Lastfälle"}

KIND_NAMES = {"Querschnitt": "Querschnittsnachweis", "Stabilitaet": "Stabilitätsnachweis",
              "section": "Querschnittsnachweis"}

FORCE_UNITS = {"N": "kN", "Vy": "kN", "Vz": "kN", "Mt": "kNm", "My": "kNm", "Mz": "kNm"}

_NUM_RE = re.compile(r"^[-+−]?(\d+([.,]\d+)?|[.,]\d+)([eE][-+]?\d+)?\s*%?$|^[–-]$|^-?∞$")


# ==========================================================================
# Helfer
# ==========================================================================
def esc(s) -> str:
    return _html.escape(str(s), quote=True)


def fmt(value, digits: int = 2) -> str:
    """Zahl als Zeichenkette (Punkt als Dezimaltrenner, ohne Tausendertrenner)."""
    if value is None:
        return "–"
    if isinstance(value, str):
        return value
    if isinstance(value, (bool, np.bool_)):
        return "ja" if value else "nein"
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not np.isfinite(v):
        return "∞" if v > 0 else ("-∞" if v < 0 else "–")
    s = f"{v:.{int(digits)}f}"
    if s.startswith("-") and float(s) == 0.0:
        s = s[1:]
    return s


class Util:
    """Ausnutzungsgrad als Tabellenzelle (im HTML gruen/rot hervorgehoben)."""

    def __init__(self, value, digits: int = 3, limit: float = 1.0):
        self.value = float(value) if value is not None else None
        self.digits = digits
        self.limit = limit

    @property
    def ok(self) -> bool:
        return self.value is None or self.value <= self.limit

    def __str__(self):
        return fmt(self.value, self.digits)


class Raw(str):
    """Fertiges HTML fuer eine Zelle (im Markdown unveraendert uebernommen)."""


def _cell_text(c) -> str:
    if isinstance(c, (Util, Raw)):
        return str(c)
    if isinstance(c, str):
        return c
    return fmt(c)


def _is_num(c) -> bool:
    if isinstance(c, Util) or isinstance(c, (int, float, np.integer, np.floating)):
        return True
    if isinstance(c, Raw):
        return False
    s = _cell_text(c).strip()
    return bool(s) and bool(_NUM_RE.match(s))


def _column_align(rows, header: bool, align):
    ncol = max(len(r) for r in rows)
    out = []
    body = rows[1:] if header and len(rows) > 1 else rows
    for j in range(ncol):
        if align and j < len(align) and align[j]:
            out.append(align[j])
            continue
        cells = [r[j] for r in body if j < len(r) and _cell_text(r[j]).strip() not in ("", "–")]
        out.append("r" if cells and all(_is_num(c) for c in cells) else "l")
    return out


def table(rows, header: bool = True, align=None, cls: str = "") -> str:
    """HTML-Tabelle. align: Liste je Spalte ('l', 'r', 'c'); ohne Angabe werden
    numerische Spalten rechtsbuendig (monospace) gesetzt."""
    if not rows:
        return ""
    al = _column_align(rows, header, align)
    cmap = {"r": "num", "c": "ctr", "l": ""}

    def cell(c, tag, j):
        klass = cmap.get(al[j], "")
        if isinstance(c, Util):
            inner = (f'<span class="util {"ok" if c.ok else "nok"}">'
                     f'{esc(fmt(c.value, c.digits))}</span>')
        elif isinstance(c, Raw):
            inner = str(c)
        else:
            inner = esc(_cell_text(c))
        attr = f' class="{klass}"' if klass else ""
        return f"<{tag}{attr}>{inner}</{tag}>"

    out = [f'<table class="{esc(cls)}">' if cls else "<table>"]
    body = rows
    if header:
        out.append("<thead><tr>" + "".join(cell(c, "th", j) for j, c in enumerate(rows[0]))
                   + "</tr></thead>")
        body = rows[1:]
    out.append("<tbody>")
    for r in body:
        out.append("<tr>" + "".join(cell(c, "td", j) for j, c in enumerate(r)) + "</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def _md_table(rows, header: bool = True) -> str:
    if not rows:
        return ""
    ncol = max(len(r) for r in rows)

    def cell(c):
        return _cell_text(c).replace("|", "\\|").replace("\n", " ")

    al = _column_align(rows, header, None)
    lines = []
    head = rows[0] if header else [""] * ncol
    lines.append("| " + " | ".join(cell(c) for c in head) + " |")
    lines.append("|" + "|".join("---:" if al[j] == "r" else "---" for j in range(ncol)) + "|")
    for r in (rows[1:] if header else rows):
        lines.append("| " + " | ".join(cell(c) for c in r) + " |")
    return "\n".join(lines)


def _ranges(ids) -> str:
    return sv._ranges(ids)


def _steifigkeit_text(g) -> str:
    """S_j,ini in MNm/rad - unendlich und null lesbar geschrieben."""
    if g is None:
        return "–"
    v = float(getattr(g, "S_j_ini", 0.0) or 0.0)
    if not math.isfinite(v):
        return "∞ (starr)"
    if v <= 0:
        return "0 (gelenkig)"
    return f"{v / 1e6:.1f}"


def _pretty(s: str) -> str:
    """ASCII-Formelzeichen der Kernmodule fuer die Anzeige."""
    return (str(s).replace("Delta-sigma", "Δσ").replace("Delta-tau", "Δτ")
            .replace("lambda_LT", "λ̄_LT").replace("chi_LT", "χ_LT"))


def _dof_text(dofs) -> str:
    return " ".join(DOF_NAMES[d] for d in sorted(set(int(d) for d in dofs)) if 0 <= d < 6)


def _ids_text(ids, limit: int = 12) -> str:
    ids = sorted(set(int(i) for i in ids))
    if len(ids) <= limit:
        return _ranges(ids)
    return f"{_ranges(ids[:limit])} … ({len(ids)} Stück)"


# ==========================================================================
# Bericht
# ==========================================================================
class Report:
    """Statischer Bericht fuer ein Modell mit Ergebnissen.

    Report(model, analysis)                  Analysis aus solver.solve_all(...)
    Report(model, results=solver.solve_static(model))   einzelnes Ergebnis
    options: dict mit Schaltern (siehe DEFAULTS), alle standardmaessig True.
    """

    DEFAULTS = {
        "model_tables": True, "materials": True, "sections": True, "supports": True,
        "load_cases": True, "combinations": True, "figures": True, "results_cases": True,
        "results_combinations": True, "envelopes": True, "member_diagrams": True,
        "design": True, "fatigue": True, "joints": True, "gzg": True, "beulen": True, "contact": True,
        "modal": True, "buckling": True,
        # Grenzen fuer grosse Modelle
        "max_rows": 200, "max_detail_cases": 20, "max_detail_combinations": 12,
        "max_member_diagrams": 40, "figure_width": 760, "figure_height": 480,
        "date": None,
    }
    LIST_LIMIT = 200          # Knoten-/Elementlisten oberhalb: gekuerzt

    def __init__(self, model, analysis=None, results=None, options: dict = None):
        self.model = model
        # Ein Results-Objekt an Stelle der Analysis (z.B. CLI/GUI ohne solve_all) zulassen
        if analysis is not None and not hasattr(analysis, "cases") and hasattr(analysis, "beam_end"):
            if results is None:
                results = analysis
            analysis = None
        self.analysis = analysis
        self.results = results
        self.options = dict(self.DEFAULTS)
        if options:
            self.options.update(options)
        self.cases: dict = {}
        self.combos: dict = {}
        self.envelopes: dict = {}
        self.design = None
        self.fatigue = None
        self.joints = None
        self.gzg = None
        self.beulen = None
        self.lasteinleitung = None
        self.info: dict = {}
        if analysis is not None:
            self.cases = dict(getattr(analysis, "cases", {}) or {})
            self.combos = dict(getattr(analysis, "combinations", {}) or {})
            self.envelopes = dict(getattr(analysis, "envelopes", {}) or {})
            self.design = getattr(analysis, "design", None)
            self.fatigue = getattr(analysis, "fatigue", None)
            self.joints = getattr(analysis, "joints", None)
            self.gzg = getattr(analysis, "gzg", None)
            self.beulen = getattr(analysis, "beulen", None)
            self.lasteinleitung = getattr(analysis, "lasteinleitung", None)
            self.info = dict(getattr(analysis, "info", {}) or {})
        if results is not None:
            name = results.name or "Ergebnis"
            if name in self.cases or name in self.combos:
                name = name + " (Einzelergebnis)"
            if getattr(results, "kind", "case") == "combination":
                self.combos[name] = results
            else:
                self.cases[name] = results
            if analysis is None:
                self.info = dict(getattr(results, "info", {}) or {})
        self._blocks = None
        self._toc = []
        self._num = [0, 0, 0]
        self._appendix = False
        self._warnings: list = []

    # ---------------------------------------------------------------- Hilfen
    def opt(self, key):
        return self.options.get(key, self.DEFAULTS.get(key))

    def _h(self, level: int, title: str, appendix: bool = False):
        if appendix:
            self._appendix = True
        if level == 1:
            if not self._appendix:
                self._num[0] += 1
            self._num[1] = self._num[2] = 0
        elif level == 2:
            self._num[1] += 1
            self._num[2] = 0
        else:
            self._num[2] += 1
        first = "A" if self._appendix else str(self._num[0])
        parts = [first] + [str(x) for x in self._num[1:level]]
        number = ".".join(parts)
        anchor = "k" + number.replace(".", "-")
        self._toc.append((level, number, title, anchor))
        return ("h", level, number, title, anchor)

    def all_results(self) -> list:
        return list(self.cases.items()) + list(self.combos.items())

    def _truncate(self, rows, limit: int = None):
        """Tabelle kuerzen; Rueckgabe (rows, hinweis oder None)."""
        limit = limit or self.opt("max_rows")
        if len(rows) - 1 <= limit:
            return rows, None
        n = len(rows) - 1
        keep = max(limit // 2, 20)
        return rows[:keep + 1], f"Tabelle gekürzt: {keep} von {n} Zeilen dargestellt."

    def _views(self) -> list:
        lo, hi = self.model.bbox()
        d = hi - lo
        tol = 1e-6 * max(float(d.max()), 1.0)
        planar = [k for k, v in enumerate(d) if v <= tol]
        if len(planar) >= 2:                      # linienfoermiges Modell
            return ["yz"] if 0 in planar and 1 not in planar else ["xz"]
        if planar == [1]:
            return ["xz"]
        if planar == [2]:
            return ["xy"]
        if planar == [0]:
            return ["yz"]
        return ["iso", "xz", "xy"]

    def _governing_result(self):
        """(Name, Results) mit der groessten Verschiebung (bevorzugt GZT-Kombination)."""
        pools = []
        uls = [(n, r) for n, r in self.combos.items()
               if n in self.model.combinations and self.model.combinations[n].is_uls]
        if uls:
            pools.append(uls)
        if self.combos:
            pools.append(list(self.combos.items()))
        if self.cases:
            pools.append(list(self.cases.items()))
        for pool in pools:
            best = None
            for n, r in pool:
                if getattr(r, "u", None) is None or r.u.size == 0:
                    continue
                um = float(np.nanmax(np.linalg.norm(r.u[:, :3], axis=1)))
                if best is None or um > best[0]:
                    best = (um, n, r)
            if best is not None:
                return best[1], best[2]
        return None, None

    def _support_nodes(self) -> list:
        m = self.model
        s = set(sup.node for sup in m.supports) | set(c.node for c in m.contact_supports)
        return sorted(n for n in s if 0 <= n < m.nn)

    def _stations(self, res, n: int = None):
        try:
            return res.stations(n)
        except Exception:
            return {}

    def _figure(self, svg_text: str, caption: str):
        return ("figure", svg_text, caption)

    # ---------------------------------------------------------------- Aufbau
    def blocks(self) -> list:
        if self._blocks is None:
            self._toc = []
            self._num = [0, 0, 0]
            self._appendix = False
            self._warnings = []
            b = []
            for ch in (self.chapter_general, self.chapter_system, self.chapter_actions,
                       self.chapter_results, self.chapter_design, self.chapter_beulen,
                       self.chapter_fatigue,
                       self.chapter_joints, self.chapter_gzg, self.chapter_summary,
                       self.chapter_appendix):
                b.extend(ch())
            self._blocks = b
        return self._blocks

    # ============================================================ Kapitel 1
    def chapter_general(self) -> list:
        m = self.model
        b = [self._h(1, "Allgemeines")]
        b.append(self._h(2, "Programm und Grundlagen"))
        b.append(("p", f"Die Berechnung wurde mit dem Programm Statik3D, Version {__version__}, "
                       "durchgeführt (Finite-Elemente-Programm für Stab-, Flächen- und "
                       "Volumentragwerke des Stahlbaus). Der vorliegende Bericht dokumentiert "
                       "System, Einwirkungen, Ergebnisse und Nachweise in prüffähiger Form."))
        b.append(("table", [["Norm", "Inhalt / Anwendung"]] + [[n, t] for n, t in NORMS],
                  "Zugrunde gelegte Normen", None, ""))
        b.append(self._h(2, "Einheiten"))
        b.append(("table", [
            ["Größe", "Rechenwert (intern)", "Angabe im Bericht"],
            ["Länge, Koordinaten", "m", "m"],
            ["Verschiebung", "m", "mm"],
            ["Verdrehung", "rad", "mrad"],
            ["Kraft", "N", "kN"],
            ["Moment", "Nm", "kNm"],
            ["Streckenlast", "N/m", "kN/m"],
            ["Flächenlast", "Pa (N/m²)", "kN/m²"],
            ["Spannung, Festigkeit, E-Modul", "Pa", "N/mm² (MPa)"],
            ["Querschnittswerte", "m², m³, m⁴, m⁶", "cm², cm³, cm⁴, cm⁶"],
            ["Dichte", "kg/m³", "kg/m³"],
            ["Temperatur", "K", "K"],
        ], "Einheiten", None, ""))
        b.append(self._h(2, "Vorzeichenkonvention"))
        b.append(("list", [
            "Globales Koordinatensystem x, y, z rechtshändig; z zeigt in der Regel nach oben. "
            "Verschiebungen und Lasten sind positiv in Richtung der positiven Achsen.",
            "Schnittgrößen der Stäbe nach DIN 1080: am positiven Schnittufer wirken positive "
            "Schnittgrößen in Richtung der positiven lokalen Achsen. Normalkraft N > 0 ist Zug; "
            "My > 0 erzeugt Zug auf der +z-Seite des Querschnitts.",
            "Lokale Stabachsen: x von Anfangs- zu Endknoten, y und z Hauptachsen "
            "(y = starke Achse, Steg in lokaler z-Richtung bei I-Profilen); die Bezugsrichtung "
            "ist die globale z-Achse (bei lotrechten Stäben die globale x-Achse), zusätzlich "
            "der Rollwinkel des Elements.",
            "Auflagerreaktionen sind Kräfte vom Lager auf das Tragwerk, positiv in Richtung "
            "der globalen Achsen.",
            "Schnittgrößenverläufe: positive Werte sind nach oben aufgetragen.",
        ]))
        b.append(self._h(2, "Rechenverfahren"))
        counts = {}
        for e in m.elements:
            counts[e.typ] = counts.get(e.typ, 0) + 1
        items = [
            "Lineare Finite-Elemente-Berechnung (Theorie I. Ordnung, linear-elastisches "
            "Werkstoffverhalten, kleine Verformungen). Die Lastfälle werden mit einer "
            "Faktorisierung der Gesamtsteifigkeitsmatrix gelöst; Kombinationen entstehen durch "
            "lineare Überlagerung (Superposition) der Lastfallergebnisse."]
        if counts:
            items.append("Elementtypen im Modell: " + "; ".join(
                f"{ELEMENT_TYPES.get(t, t)} ({n} Stück)" for t, n in counts.items()) + ".")
        if self.info.get("solver"):
            items.append(f"Gleichungslöser: {self.info['solver']} (direkt, sparse).")
        if m.has_contact:
            items.append(
                "Kontakt (einseitige Lager, Spaltelemente, Knoten-Flächen-Kontakt) wird mit dem "
                "Penalty-Verfahren und Aktiv-Mengen-Iteration berechnet; Kombinationen mit "
                "Kontakt werden nichtlinear (ohne Superposition) gelöst. Reibung nach Coulomb "
                "(Haften/Gleiten) für monoton aufgebrachte Lasten.")
        ds = m.design
        items.append(
            f"Kombinationsbildung nach DIN EN 1990 mit Gleichung {ds.combination_rule} "
            f"(γ_G,sup = {ds.gamma_G_sup:g}, γ_G,inf = {ds.gamma_G_inf:g}, γ_Q = {ds.gamma_Q:g}"
            + (f", ξ = {ds.xi:g}" if ds.combination_rule == "6.10ab" else "")
            + "); ψ-Beiwerte nach DIN EN 1990/NA Tabelle A.1.1 je Einwirkungskategorie. "
              "Gebrauchstauglichkeit: charakteristisch (6.14b), häufig (6.15b), "
              "quasi-ständig (6.16b). Umhüllende: Extremwerte aller Kombinationen je "
              "Bemessungssituation mit Angabe der maßgebenden Kombination.")
        items.append(
            "Stabnachweise nach DIN EN 1993-1-1: Querschnittsklassifizierung (Tabelle 5.2), "
            "Querschnittsnachweise nach 6.2 (N, V, M, Interaktion, Torsion, Vergleichsspannung) "
            f"an {ds.stations} Nachweisstellen je Element, Stabilitätsnachweise nach 6.3 "
            "(Biegeknicken, Drillknicken, Biegedrillknicken mit M_cr nach NCCI SN003, "
            f"Interaktion nach Anhang {ds.interaction_method}); "
            f"γ_M0 = {ds.gamma_M0:g}, γ_M1 = {ds.gamma_M1:g}, γ_M2 = {ds.gamma_M2:g}.")
        if m.joints:
            items.append(
                f"Anschlussnachweise nach DIN EN 1993-1-8 für {len(m.joints)} Anschlüsse "
                "(Schrauben 3.6/3.7/3.9, äquivalenter T-Stummel 6.2.4, Schweißnähte 4.5.3, "
                "Blockversagen 3.10.2) sowie deren Ermüdung nach DIN EN 1993-1-9, "
                f"Tab. 8.1 und 8.5; γ_M2 = {ds.gamma_M2:g}.")
        if m.verformungsgrenzen:
            items.append(
                f"Verformungsnachweise im Grenzzustand der Gebrauchstauglichkeit für "
                f"{len(m.verformungsgrenzen)} festgelegte Grenzwerte (DIN EN 1990, 6.5.3; "
                "Durchbiegung bezogen auf die Sehne, Knotenverschiebungen, "
                "Verschiebungen von Punktpaaren).")
        items.append(
            "Ermüdungsnachweis nach DIN EN 1993-1-9 (Nennspannungskonzept, Kerbfallklassen, "
            "Wöhlerlinien mit m = 3/5 bzw. m = 5 für Schub, Schadensakkumulation "
            f"D = Σ n_i/N_Ri ≤ 1; γ_Ff = {ds.gamma_Ff:g}, γ_Mf nach Tabelle 3.1).")
        b.append(("list", items))
        b.append(self._h(2, "Gültigkeitsbereich und Hinweise"))
        b.append(("list", [
            "Die Berechnung ist linear: keine Plastizität, keine Theorie II./III. Ordnung, "
            "kein Schalenbeulen. Verzweigungslasten (lineares Knicken) gelten für "
            "Stabtragwerke; Imperfektionen sind über die Knicklinien der Nachweise erfasst.",
            "Stabilitätsnachweise setzen die angegebenen Knicklängen, seitlichen Halterungen "
            "und Randbedingungsbeiwerte voraus; diese sind vom Anwender zu verantworten.",
            "Schubbeulen der Stegbleche wird nach DIN EN 1993-1-5, Abschnitt 5 "
            "nachgewiesen (V_b,Rd ohne Flanschanteil, Interaktion M–V nach 7.1); "
            "Blechfelder werden – soweit im Modell als Beulfeld festgelegt – nach "
            "Abschnitt 10 geführt. Schalenbeulen nach EN 1993-1-6 und Längssteifen "
            "sind nicht enthalten.",
            "Anschlüsse, Schweißnähte und Schrauben nach DIN EN 1993-1-8 werden für die im "
            "Modell angelegten Anschlüsse in Kapitel 7 nachgewiesen; nicht angelegte "
            "Anschlüsse sind gesondert nachzuweisen.",
            "Ermüdung: Nennspannungen an den Querschnittsrändern aus N, My, Mz; "
            "Schub aus V/A_v; Reihenfolgeeffekte werden nicht berücksichtigt.",
            "Alle Ergebnisse sind vom Aufsteller auf Plausibilität zu prüfen "
            "(Gleichgewicht der Auflagerkräfte, Größenordnung der Verformungen).",
        ]))
        return b

    # ============================================================ Kapitel 2
    def chapter_system(self) -> list:
        m = self.model
        b = [self._h(1, "System")]
        # ---- Geometrie
        b.append(self._h(2, "Geometrie"))
        lo, hi = m.bbox()
        counts = {}
        for e in m.elements:
            counts[e.typ] = counts.get(e.typ, 0) + 1
        kv = [("Modell", m.name), ("Knoten", str(m.nn)),
              ("Elemente", f"{len(m.elements)}" + (" (" + ", ".join(
                  f"{n} {t}" for t, n in counts.items()) + ")" if counts else "")),
              ("Abmessungen x / y / z [m]",
               f"{fmt(hi[0] - lo[0], 3)} / {fmt(hi[1] - lo[1], 3)} / {fmt(hi[2] - lo[2], 3)}"),
              ("Koordinatenbereich",
               f"x: {fmt(lo[0], 3)} … {fmt(hi[0], 3)}, y: {fmt(lo[1], 3)} … {fmt(hi[1], 3)}, "
               f"z: {fmt(lo[2], 3)} … {fmt(hi[2], 3)} m"),
              ("Freiheitsgrade", f"{m.ndof} (6 je Knoten)"),
              ("Stäbe (Nachweise)", str(len(m.members)))]
        b.append(("kv", kv, "Modellkennwerte"))
        if self.opt("model_tables"):
            rows = [["Knoten", "x [m]", "y [m]", "z [m]"]]
            nmax = m.nn
            if m.nn > self.LIST_LIMIT:
                nmax = 40
            for k in range(nmax):
                rows.append([str(k), fmt(m.nodes[k, 0], 3), fmt(m.nodes[k, 1], 3),
                             fmt(m.nodes[k, 2], 3)])
            b.append(("table", rows, "Knotenkoordinaten", None, "compact"))
            if m.nn > self.LIST_LIMIT:
                b.append(("note", f"Die Knotenliste ist wegen der Modellgröße ({m.nn} Knoten) "
                                  f"auf die ersten {nmax} Knoten gekürzt; die vollständigen "
                                  "Koordinaten sind in der Modelldatei enthalten."))
            rows = [["Element", "Typ", "Knoten", "Material", "Querschnitt / Dicke", "L [m]"]]
            emax = len(m.elements)
            if emax > self.LIST_LIMIT:
                emax = 40
            for i in range(emax):
                e = m.elements[i]
                L = fmt(m.element_length(i), 3) if e.typ in ("beam", "truss") else ""
                rows.append([str(i), e.typ, " ".join(str(n) for n in e.nodes), e.mat,
                             e.sec or "", L])
            b.append(("table", rows, "Elemente", None, "compact"))
            if len(m.elements) > self.LIST_LIMIT:
                b.append(("note", f"Die Elementliste ist wegen der Modellgröße "
                                  f"({len(m.elements)} Elemente) auf die ersten {emax} "
                                  "Elemente gekürzt."))
        if m.members:
            rows = [["Stab", "Elemente", "L [m]", "Querschnitt", "Material", "β_y", "β_z",
                     "L_cr,y [m]", "L_cr,z [m]", "L_LT [m]", "k_z", "k_w", "Lastangriff",
                     "BDK", "Kerbfall [MPa]"]]
            for name, mem in m.members.items():
                if not mem.elements:
                    continue
                e0 = m.elements[mem.elements[0]]
                L = m.member_length(mem)
                rows.append([name, _ids_text(mem.elements), fmt(L, 3), e0.sec or "", e0.mat,
                             fmt(mem.beta_y, 2), fmt(mem.beta_z, 2),
                             fmt(mem.Lcr_y if mem.Lcr_y else mem.beta_y * L, 2),
                             fmt(mem.Lcr_z if mem.Lcr_z else mem.beta_z * L, 2),
                             fmt(mem.L_LT if mem.L_LT else L, 2), fmt(mem.k_z, 2),
                             fmt(mem.k_w, 2),
                             {"top": "Obergurt", "bottom": "Untergurt"}.get(
                                 mem.load_position, "Schubmittelpunkt"),
                             "ja" if mem.lt_check else "nein",
                             fmt(mem.detail_category / 1e6, 0) if mem.detail_category else "–"])
            rows, note = self._truncate(rows)
            b.append(("table", rows, "Stäbe für die Nachweise (Knicklängen, "
                                     "Biegedrillknicken, Kerbfall)", None, "compact"))
            if note:
                b.append(("note", note))
        # ---- Materialien
        if self.opt("materials"):
            b.append(self._h(2, "Materialien"))
            rows = [["Material", "Stahlsorte", "E [N/mm²]", "ν", "G [N/mm²]", "ρ [kg/m³]",
                     "α_T [1/K]", "f_y [N/mm²]", "f_u [N/mm²]"]]
            for mat in m.materials.values():
                rows.append([mat.name, mat.grade or "–", fmt(mat.E / 1e6, 0), fmt(mat.nu, 2),
                             fmt(mat.G / 1e6, 0), fmt(mat.rho, 0), f"{mat.alpha:.2e}",
                             fmt(mat.fy / 1e6, 0) if mat.fy else "–",
                             fmt(mat.fu / 1e6, 0) if mat.fu else "–"])
            b.append(("table", rows, "Materialkennwerte", None, ""))
            if any(mat.grade for mat in m.materials.values()):
                b.append(("note", "Streckgrenzen für Erzeugnisdicken t ≤ 40 mm nach EN 10025-2; "
                                  "für t > 40 mm werden die abgeminderten Werte nach "
                                  "DIN EN 1993-1-1 Tabelle 3.1 verwendet."))
        # ---- Querschnitte
        if self.opt("sections"):
            b.append(self._h(2, "Querschnitte"))
            if m.sections:
                rows = [["Querschnitt", "Typ", "h [mm]", "b [mm]", "t_w [mm]", "t_f [mm]",
                         "r [mm]", "A [cm²]", "A_vy [cm²]", "A_vz [cm²]", "I_y [cm⁴]",
                         "I_z [cm⁴]", "I_t [cm⁴]", "I_w [cm⁶]", "W_el,y [cm³]", "W_el,z [cm³]",
                         "W_pl,y [cm³]", "W_pl,z [cm³]", "Herstellung"]]
                for s in m.sections.values():
                    rows.append([s.name, s.typ, fmt(s.h * 1e3, 1), fmt(s.b * 1e3, 1),
                                 fmt(s.tw * 1e3, 1), fmt(s.tf * 1e3, 1), fmt(s.r * 1e3, 1),
                                 fmt(s.A * 1e4, 2), fmt(s.Asy * 1e4, 2), fmt(s.Asz * 1e4, 2),
                                 fmt(s.Iy * 1e8, 1), fmt(s.Iz * 1e8, 1), fmt(s.It * 1e8, 2),
                                 fmt(s.Iw * 1e12, 1), fmt(s.Wel_y * 1e6, 1), fmt(s.Wel_z * 1e6, 1),
                                 fmt(s.Wpl_y * 1e6, 1), fmt(s.Wpl_z * 1e6, 1),
                                 {"rolled": "gewalzt", "welded": "geschweißt",
                                  "cold_formed": "kaltgeformt"}.get(s.fabrication, s.fabrication)])
                b.append(("table", rows, "Querschnittswerte (Bruttoquerschnitt)", None,
                          "compact"))
                b.append(("list", [f"{s.name}: {s.describe()}" for s in m.sections.values()]))
            if m.shells:
                rows = [["Schalenquerschnitt", "t [mm]"]]
                for sp in m.shells.values():
                    rows.append([sp.name, fmt(sp.t * 1e3, 1)])
                b.append(("table", rows, "Schalendicken", None, ""))
            if not m.sections and not m.shells:
                b.append(("p", "Keine Stab- oder Schalenquerschnitte (reines Volumenmodell)."))
        # ---- Lagerung
        if self.opt("supports"):
            b.append(self._h(2, "Lagerung"))
            rows = [["Knoten", "x [m]", "y [m]", "z [m]", "gehaltene FHG", "Vorgabe",
                     "Feder [kN/m, kNm/rad]"]]
            for s in m.supports:
                if not (0 <= s.node < m.nn):
                    continue
                p = m.nodes[s.node]
                vals = ""
                if s.values is not None and any(v for v in s.values):
                    vals = ", ".join(f"{DOF_NAMES[d]} = {v * 1e3:.2f} mm" if d < 3 else
                                     f"{DOF_NAMES[d]} = {v * 1e3:.3f} mrad"
                                     for d, v in zip(s.dofs, s.values) if v)
                stiff = ""
                if s.stiffness is not None and any(k for k in s.stiffness):
                    stiff = ", ".join(f"{DOF_NAMES[d]}: {fmt(k / 1e3, 1)}"
                                      for d, k in zip(s.dofs, s.stiffness) if k)
                rows.append([str(s.node), fmt(p[0], 3), fmt(p[1], 3), fmt(p[2], 3),
                             _dof_text(s.dofs), vals or "–", stiff or "starr"])
            rows, note = self._truncate(rows)
            if len(rows) > 1:
                b.append(("table", rows, "Lagerbedingungen", None, "compact"))
                if note:
                    b.append(("note", note))
            else:
                b.append(("p", "Keine starren Lager definiert."))
            if m.contact_supports:
                rows = [["Knoten", "Richtung", "Spalt [mm]", "Steifigkeit [kN/m]", "μ", "Gruppe"]]
                for c in m.contact_supports:
                    rows.append([str(c.node),
                                 "(" + ", ".join(f"{v:g}" for v in c.direction) + ")",
                                 fmt(c.gap * 1e3, 2),
                                 fmt(c.stiffness / 1e3, 1) if c.stiffness > 0 else "automatisch",
                                 fmt(c.mu, 2), c.group])
                b.append(("table", rows, "Einseitige Lager (nur Druck)", None, ""))
            if m.gap_elements:
                rows = [["Knoten a", "Knoten b", "Richtung", "Spalt [mm]", "Steifigkeit [kN/m]",
                         "μ"]]
                for g in m.gap_elements:
                    rows.append([str(g.node_a), str(g.node_b),
                                 "(" + ", ".join(f"{v:g}" for v in g.direction) + ")"
                                 if g.direction is not None else "aus Geometrie",
                                 fmt(g.gap * 1e3, 2),
                                 fmt(g.stiffness / 1e3, 1) if g.stiffness > 0 else "automatisch",
                                 fmt(g.mu, 2)])
                b.append(("table", rows, "Spaltelemente (Knoten-Knoten-Kontakt)", None, ""))
            if m.contact_pairs:
                rows = [["Kontaktpaar", "Slave-Knoten", "Master-Elemente", "Master-Facetten",
                         "Spalt [mm]", "Steifigkeit [kN/m]", "μ"]]
                for cp in m.contact_pairs:
                    rows.append([cp.name, _ids_text(cp.slave_nodes),
                                 _ids_text(cp.master_elements) if cp.master_elements else "–",
                                 str(len(cp.master_faces)), fmt(cp.gap * 1e3, 2),
                                 fmt(cp.stiffness / 1e3, 1) if cp.stiffness > 0 else "automatisch",
                                 fmt(cp.mu, 2)])
                b.append(("table", rows, "Knoten-Flächen-Kontaktpaare", None, ""))
        # ---- Figuren
        if self.opt("figures") and m.nn:
            b.append(self._h(2, "Systemdarstellung"))
            W, H = self.opt("figure_width"), self.opt("figure_height")
            small = m.nn <= 400
            for k, view in enumerate(self._views()):
                svg_text = sv.draw_structure(
                    m, view, W, H, show_supports=True, show_loads=False, show_nodes=small,
                    show_numbers=small and k == 0,
                    title=f"System – {sv.Projection.LABELS[view]}")
                b.append(self._figure(svg_text, f"Statisches System, {sv.Projection.LABELS[view]}"
                                      + (" (mit Knoten- und Elementnummern)"
                                         if small and k == 0 else "")))
        return b

    # ============================================================ Kapitel 3
    def _load_tables(self, lc) -> list:
        b = []
        # Knotenlasten (gleiche Lastvektoren zusammenfassen)
        if lc.nodal_loads:
            groups = {}
            for l in lc.nodal_loads:
                key = tuple(round(float(v), 6) for v in l.F)
                groups.setdefault(key, []).append(l.node)
            rows = [["Knoten", "Anzahl", "F_x [kN]", "F_y [kN]", "F_z [kN]", "M_x [kNm]",
                     "M_y [kNm]", "M_z [kNm]"]]
            for key, nodes in groups.items():
                rows.append([_ids_text(nodes), str(len(nodes))]
                            + [fmt(v / 1e3, 3) for v in key])
            rows, note = self._truncate(rows)
            b.append(("table", rows, f"Knotenlasten Lastfall {lc.name}", None, ""))
            if note:
                b.append(("note", note))
        if lc.beam_loads:
            groups = {}
            for l in lc.beam_loads:
                q2 = l.q2 if l.q2 is not None else l.q
                key = (tuple(round(float(v), 6) for v in l.q),
                       tuple(round(float(v), 6) for v in q2), l.system)
                groups.setdefault(key, []).append(l.elem)
            rows = [["Elemente", "Anzahl", "System", "q_x [kN/m]", "q_y [kN/m]", "q_z [kN/m]",
                     "q_x,Ende", "q_y,Ende", "q_z,Ende"]]
            for (q1, q2, system), elems in groups.items():
                rows.append([_ids_text(elems), str(len(elems)),
                             "global" if system == "global" else "lokal"]
                            + [fmt(v / 1e3, 3) for v in q1]
                            + ([fmt(v / 1e3, 3) for v in q2] if q2 != q1 else ["=", "=", "="]))
            rows, note = self._truncate(rows)
            b.append(("table", rows, f"Streckenlasten Lastfall {lc.name} "
                                     "(Werte am Elementanfang / -ende)", None, ""))
            if note:
                b.append(("note", note))
        if lc.face_loads:
            groups = {}
            for l in lc.face_loads:
                key = (round(float(l.p), 6), int(l.face),
                       tuple(round(float(v), 6) for v in l.direction)
                       if l.direction is not None else None)
                groups.setdefault(key, []).append(l.elem)
            rows = [["Elemente", "Anzahl", "p [kN/m²]", "Fläche", "Richtung"]]
            for (p, face, d), elems in groups.items():
                rows.append([_ids_text(elems), str(len(elems)), fmt(p / 1e3, 3), str(face),
                             "normal" if d is None else "(" + ", ".join(f"{v:g}" for v in d) + ")"])
            rows, note = self._truncate(rows)
            b.append(("table", rows, f"Flächenlasten Lastfall {lc.name}", None, ""))
            if note:
                b.append(("note", note))
        if lc.temp_loads:
            groups = {}
            for l in lc.temp_loads:
                key = (round(float(l.dT), 4), round(float(l.dT_z), 4))
                groups.setdefault(key, []).append(l.elem)
            rows = [["Elemente", "Anzahl", "ΔT [K]", "ΔT_z (oben − unten) [K]"]]
            for (dT, dTz), elems in groups.items():
                rows.append([_ids_text(elems), str(len(elems)), fmt(dT, 2), fmt(dTz, 2)])
            rows, note = self._truncate(rows)
            b.append(("table", rows, f"Temperaturlasten Lastfall {lc.name}", None, ""))
            if note:
                b.append(("note", note))
        g = np.asarray(lc.gravity, dtype=float)
        if np.any(g):
            b.append(("p", f"Eigengewicht aus den Elementmassen mit g = ({g[0]:.2f}, {g[1]:.2f}, "
                           f"{g[2]:.2f}) m/s²."))
        if lc.n_loads == 0:
            b.append(("p", "Dieser Lastfall enthält keine Lasten."))
        return b

    def chapter_actions(self) -> list:
        m = self.model
        b = [self._h(1, "Einwirkungen")]
        b.append(self._h(2, "Lastfälle"))
        rows = [["Lastfall", "Kategorie", "Einwirkung", "Beschreibung", "ψ_0", "ψ_1", "ψ_2",
                 "γ_sup", "γ_inf", "Gruppe", "Lasten"]]
        ds = m.design
        for lc in m.load_cases.values():
            psi = lc.psi_factors
            cat = ACTION_CATEGORIES.get(lc.category, ("–", psi))[0]
            if lc.is_permanent:
                gs = lc.gamma_sup if lc.gamma_sup is not None else ds.gamma_G_sup
                gi = lc.gamma_inf if lc.gamma_inf is not None else ds.gamma_G_inf
            elif lc.is_variable:
                gs = lc.gamma_sup if lc.gamma_sup is not None else ds.gamma_Q
                gi = ds.gamma_Q_fav
            else:
                gs, gi = 1.0, 1.0
            rows.append([lc.name, lc.category, cat, lc.description or "–", fmt(psi[0], 2),
                         fmt(psi[1], 2), fmt(psi[2], 2), fmt(gs, 2), fmt(gi, 2),
                         lc.exclusive_group or "–", str(lc.n_loads)])
        b.append(("table", rows, "Lastfälle und Einwirkungskategorien (DIN EN 1990/NA)",
                  None, ""))
        if self.opt("load_cases"):
            W, H = self.opt("figure_width"), int(self.opt("figure_height") * 0.85)
            views = self._views()
            for lc in m.load_cases.values():
                b.append(self._h(3, f"Lastfall {lc.name}" + (f" – {lc.description}"
                                                            if lc.description else "")))
                b.extend(self._load_tables(lc))
                if self.opt("figures") and lc.n_loads > 0 and m.nn:
                    view = views[0] if len(views) == 1 else "iso"
                    svg_text = sv.draw_structure(m, view, W, H, show_supports=True,
                                                 show_loads=True, case=lc,
                                                 title=f"Lastfall {lc.name}")
                    b.append(self._figure(svg_text, f"Lasten des Lastfalls {lc.name}"))
        b.append(self._h(2, "Kombinationen"))
        if m.combinations:
            rows = combination_table(m)
            head = list(rows[0])
            head[1] = "Typ"
            body = []
            for r in rows[1:]:
                r = list(r)
                r[1] = COMBO_TYPES.get(r[1], r[1])
                body.append(r)
            rows = [head] + body
            rows, note = self._truncate(rows)
            b.append(("table", rows, "Lastfallkombinationen (Faktoren je Lastfall)", None,
                      "compact"))
            if note:
                b.append(("note", note))
            b.append(("note", f"Kombinationsregel: Gleichung {ds.combination_rule} nach "
                              "DIN EN 1990; GZT = Grenzzustand der Tragfähigkeit (STR/GEO), "
                              "GZG = Gebrauchstauglichkeit."))
        else:
            b.append(("p", "Es sind keine Lastfallkombinationen definiert; die Ergebnisse "
                           "werden je Lastfall ausgewiesen."))
        if m.fatigue_loads:
            b.append(self._h(2, "Ermüdungslasten"))
            rows = [["Ermüdungslast", "Oberlast (Lastfall)", "Unterlast (Lastfall)",
                     "Lastspiele n", "Faktor"]]
            for f in m.fatigue_loads.values():
                rows.append([f.name, f.case_max, f.case_min or "Nullzustand", f"{f.cycles:.3g}",
                             fmt(f.factor, 2)])
            b.append(("table", rows, "Ermüdungsbeanspruchungen (Lastwechsel zwischen zwei "
                                     "Lastfällen)", None, ""))
        return b

    # ============================================================ Kapitel 4
    def _overview_row(self, name, res) -> list:
        kind = getattr(res, "kind", "case")
        typ = res.info.get("typ", "") if isinstance(res.info, dict) else ""
        art = {"case": "Lastfall", "combination": "Kombination", "modal": "Modalanalyse",
               "buckling": "Knicken"}.get(kind, kind)
        if typ:
            art += f" ({COMBO_TYPES.get(typ, typ)})"
        umax, node = "–", "–"
        if getattr(res, "u", None) is not None and res.u.size:
            um = np.linalg.norm(res.u[:, :3], axis=1)
            i = int(np.nanargmax(um))
            umax, node = fmt(um[i] * 1e3, 3), str(i)
        R = ["–"] * 3
        if getattr(res, "reactions", None) is not None and res.reactions.size:
            Rs = res.reactions[:, :3].sum(axis=0)
            R = [fmt(v / 1e3, 2) for v in Rs]
        vm = "–"
        try:
            nv = res.node_vm
            if nv is not None and np.any(np.isfinite(nv)):
                vm = fmt(np.nanmax(nv) / 1e6, 1)
        except Exception:
            pass
        ct = "–"
        if res.contact:
            n_act = sum(1 for c in res.contact if c.get("status") != "offen")
            ct = f"{n_act}/{len(res.contact)} aktiv"
            if res.info.get("contact_converged") is False:
                ct += " (nicht konvergiert)"
        return [name, art, umax, node] + R + [vm, ct]

    def _result_detail(self, name, res) -> list:
        b = []
        kv = []
        if getattr(res, "u", None) is not None and res.u.size:
            um = np.linalg.norm(res.u[:, :3], axis=1)
            i = int(np.nanargmax(um))
            kv.append(("max. Verschiebung |u|",
                       f"{fmt(um[i] * 1e3, 3)} mm am Knoten {i} "
                       f"(u_x = {fmt(res.u[i, 0] * 1e3, 3)}, u_y = {fmt(res.u[i, 1] * 1e3, 3)}, "
                       f"u_z = {fmt(res.u[i, 2] * 1e3, 3)} mm)"))
            rm = np.linalg.norm(res.u[:, 3:], axis=1)
            j = int(np.nanargmax(rm))
            if rm[j] > 0:
                kv.append(("max. Verdrehung", f"{fmt(rm[j] * 1e3, 3)} mrad am Knoten {j}"))
        try:
            nv = res.node_vm
            if nv is not None and np.any(np.isfinite(nv)):
                k = int(np.nanargmax(nv))
                kv.append(("max. Vergleichsspannung (Knotenmittel)",
                           f"{fmt(nv[k] / 1e6, 1)} N/mm² am Knoten {k}"))
        except Exception:
            pass
        if res.info.get("factors"):
            kv.append(("Lastfaktoren", " + ".join(f"{f:g}·{k}" for k, f in
                                                  res.info["factors"].items() if f)))
        if res.info.get("superposition"):
            kv.append(("Ermittlung", "lineare Überlagerung der Lastfallergebnisse"))
        elif res.info.get("contact_iterations") is not None:
            kv.append(("Kontakt-Iterationen", f"{res.info['contact_iterations']}"
                       + ("" if res.info.get("contact_converged", True)
                          else " – NICHT konvergiert")))
        b.append(("kv", kv, f"Kennwerte {name}"))
        # Auflagerreaktionen
        if getattr(res, "reactions", None) is not None and res.reactions.size:
            nodes = self._support_nodes()
            rows = [["Knoten", "F_x [kN]", "F_y [kN]", "F_z [kN]", "M_x [kNm]", "M_y [kNm]",
                     "M_z [kNm]"]]
            for n in nodes:
                r = res.reactions[n]
                rows.append([str(n)] + [fmt(v / 1e3, 2) for v in r])
            rows, note = self._truncate(rows)
            Rs = res.reactions.sum(axis=0)
            rows.append(["Summe"] + [fmt(v / 1e3, 2) for v in Rs])
            b.append(("table", rows, f"Auflagerreaktionen {name}", None, "compact"))
            if note:
                b.append(("note", note + " Die Summenzeile enthält alle Lagerknoten."))
        # Schnittgroessen Staebe
        st = self._stations(res)
        if st:
            rows = [["Schnittgröße", "min", "Element", "x [m]", "max", "Element", "x [m]"]]
            for k in ("N", "Vy", "Vz", "Mt", "My", "Mz"):
                mn = (np.inf, None, 0.0)
                mx = (-np.inf, None, 0.0)
                for i, d in st.items():
                    arr = d[k]
                    j1, j2 = int(np.argmin(arr)), int(np.argmax(arr))
                    if arr[j1] < mn[0]:
                        mn = (float(arr[j1]), i, float(d["x"][j1]))
                    if arr[j2] > mx[0]:
                        mx = (float(arr[j2]), i, float(d["x"][j2]))
                unit = FORCE_UNITS[k]
                rows.append([f"{k} [{unit}]", fmt(mn[0] / 1e3, 2), str(mn[1]), fmt(mn[2], 2),
                             fmt(mx[0] / 1e3, 2), str(mx[1]), fmt(mx[2], 2)])
            b.append(("table", rows, f"Extremwerte der Stabschnittgrößen {name} "
                                     "(x ab Elementanfang)", None, ""))
        # Schalen
        try:
            ss = res.shell_stress
        except Exception:
            ss = {}
        if ss:
            rows = [["Größe", "max |Wert|", "Element"]]
            labels = [("n_x [kN/m]", "n", 0), ("n_y [kN/m]", "n", 1), ("n_xy [kN/m]", "n", 2),
                      ("m_x [kNm/m]", "m", 0), ("m_y [kNm/m]", "m", 1), ("m_xy [kNm/m]", "m", 2)]
            for lab, key, idx in labels:
                best = max(ss.items(), key=lambda kv_: abs(kv_[1][key][idx]))
                rows.append([lab, fmt(best[1][key][idx] / 1e3, 3), str(best[0])])
            best = max(ss.items(), key=lambda kv_: kv_[1]["vM"])
            rows.append(["σ_v [N/mm²]", fmt(best[1]["vM"] / 1e6, 1), str(best[0])])
            b.append(("table", rows, f"Schnittkräfte und Spannungen der Schalen {name}", None, ""))
        try:
            so = res.solid_stress
        except Exception:
            so = {}
        if so:
            best = max(so.items(), key=lambda kv_: kv_[1]["vM"])
            p1 = max(so.items(), key=lambda kv_: float(np.max(kv_[1]["principal"])))
            p3 = min(so.items(), key=lambda kv_: float(np.min(kv_[1]["principal"])))
            rows = [["Größe", "Wert [N/mm²]", "Element"],
                    ["max. Vergleichsspannung σ_v", fmt(best[1]["vM"] / 1e6, 1), str(best[0])],
                    ["max. Hauptspannung σ_1", fmt(float(np.max(p1[1]["principal"])) / 1e6, 1),
                     str(p1[0])],
                    ["min. Hauptspannung σ_3", fmt(float(np.min(p3[1]["principal"])) / 1e6, 1),
                     str(p3[0])]]
            b.append(("table", rows, f"Spannungen der Volumenelemente {name}", None, ""))
        return b

    def _member_envelope(self, env, member):
        """Umhuellende entlang eines Stabes: x, {k: (min, max, komb_min, komb_max)}."""
        xs = []
        data = {k: ([], [], [], []) for k in ("N", "Vy", "Vz", "Mt", "My", "Mz")}
        x0 = 0.0
        for i in member.elements:
            d = env.beam.get(i)
            if d is None:
                continue
            xs.append(np.asarray(d["x"]) + x0)
            x0 += float(d["x"][-1])
            for k in data:
                mn, mx, imn, imx = d[k]
                data[k][0].append(mn)
                data[k][1].append(mx)
                data[k][2].append(imn)
                data[k][3].append(imx)
        if not xs:
            return None, None
        x = np.concatenate(xs)
        out = {}
        for k, (mn, mx, imn, imx) in data.items():
            out[k] = (np.concatenate(mn), np.concatenate(mx), np.concatenate(imn),
                      np.concatenate(imx))
        return x, out

    def chapter_results(self) -> list:
        m = self.model
        b = [self._h(1, "Ergebnisse")]
        allres = self.all_results()
        if not allres:
            b.append(("p", "Es liegen keine Berechnungsergebnisse vor."))
            return b
        # ---- Uebersicht
        b.append(self._h(2, "Übersicht"))
        rows = [["Ergebnis", "Art", "max |u| [mm]", "Knoten", "ΣF_x [kN]", "ΣF_y [kN]",
                 "ΣF_z [kN]", "max σ_v [N/mm²]", "Kontakt"]]
        for name, res in allres:
            rows.append(self._overview_row(name, res))
        rows, note = self._truncate(rows)
        b.append(("table", rows, "Übersicht aller Ergebnisse (Summe der Auflagerkräfte = "
                                 "Reaktionen vom Lager auf das Tragwerk)", None, "compact"))
        if note:
            b.append(("note", note))
        gname, gres = self._governing_result()
        if self.opt("figures") and gres is not None and m.nn:
            views = self._views()
            view = views[0] if len(views) == 1 else "iso"
            W, H = self.opt("figure_width"), self.opt("figure_height")
            svg_text = sv.draw_structure(m, view, W, H, results=gres, field="umag",
                                         show_supports=True, show_loads=False,
                                         title=f"Verformung – {gname}")
            b.append(self._figure(svg_text, f"Verformte Lage für {gname} (Ausgangslage "
                                            "gestrichelt, Farbe: Verschiebungsbetrag)"))
        # ---- Lastfaelle
        if self.opt("results_cases") and self.cases:
            b.append(self._h(2, "Ergebnisse je Lastfall"))
            items = list(self.cases.items())
            lim = self.opt("max_detail_cases")
            for name, res in items[:lim]:
                b.append(self._h(3, f"Lastfall {name}"))
                b.extend(self._result_detail(name, res))
            if len(items) > lim:
                b.append(("note", f"Für die übrigen {len(items) - lim} Lastfälle siehe "
                                  "Übersicht und Umhüllende."))
        # ---- Kombinationen
        if self.opt("results_combinations") and self.combos:
            b.append(self._h(2, "Ergebnisse je Kombination"))
            items = list(self.combos.items())
            lim = self.opt("max_detail_combinations")
            for name, res in items[:lim]:
                c = m.combinations.get(name)
                sub = f"Kombination {name}"
                if c is not None:
                    sub += f" ({COMBO_TYPES.get(c.typ, c.typ)}): {c.formula()}"
                b.append(self._h(3, sub))
                b.extend(self._result_detail(name, res))
            if len(items) > lim:
                b.append(("note", f"Für die übrigen {len(items) - lim} Kombinationen siehe "
                                  "Übersicht und Umhüllende (maßgebende Kombinationen sind "
                                  "dort ausgewiesen)."))
        # ---- Umhuellende
        if self.opt("envelopes") and self.envelopes:
            b.append(self._h(2, "Umhüllende"))
            for key, env in self.envelopes.items():
                b.append(self._h(3, f"Umhüllende {ENVELOPE_NAMES.get(key, key)}"))
                b.append(("p", f"Extremwerte aus {len(env.names)} Ergebnissen: "
                               + ", ".join(env.names[:30])
                               + (" …" if len(env.names) > 30 else "") + "."))
                b.extend(self._envelope_tables(env))
        # ---- Stabdiagramme
        if self.opt("member_diagrams") and m.members:
            b.extend(self._member_diagram_blocks())
        # ---- Kontakt
        if self.opt("contact"):
            ct = [(n, r) for n, r in allres if r.contact]
            if ct:
                b.append(self._h(2, "Kontakt"))
                from .. import contact as ctm
                for name, res in ct:
                    b.append(self._h(3, f"Kontaktergebnisse {name}"))
                    b.append(("p", ctm.summary(res.contact) + "."))
                    rows = [["Knoten", "Art", "Bezeichnung", "Status", "F_n [kN]", "F_t [kN]",
                             "Spalt [mm]"]]
                    kinds = {"support": "einseitiges Lager", "gap": "Spaltelement",
                             "surface": "Knoten-Fläche"}
                    for c in res.contact:
                        rows.append([str(c.get("node", "")), kinds.get(c.get("kind"), c.get("kind")),
                                     c.get("label", ""), c.get("status", ""),
                                     fmt(c.get("Fn", 0.0) / 1e3, 3), fmt(c.get("Ft", 0.0) / 1e3, 3),
                                     fmt(c.get("gap", 0.0) * 1e3, 3)])
                    rows, note = self._truncate(rows)
                    b.append(("table", rows, f"Kontaktbedingungen {name} (F_n = Normalkraft, "
                                             "F_t = Reibkraft, Spalt < 0 = Durchdringung)",
                              None, "compact"))
                    if note:
                        b.append(("note", note))
                    log = [s for s in res.info.get("contact_log", []) if "zugeordnet" not in s]
                    if log:
                        b.append(("list", log))
                        self._warnings.extend(f"Kontakt {name}: {s}" for s in log)
                    if res.info.get("contact_converged") is False:
                        self._warnings.append(f"Kontakt {name}: Iteration nicht konvergiert")
        # ---- Modal
        if self.opt("modal"):
            modal = [(n, r) for n, r in allres if getattr(r, "freqs", None) is not None]
            for name, res in modal:
                b.append(self._h(2, f"Eigenfrequenzen ({name})"))
                rows = [["Nr.", "f [Hz]", "ω [rad/s]", "T [s]"]]
                for k, f in enumerate(res.freqs):
                    rows.append([str(k + 1), fmt(f, 3), fmt(2 * np.pi * f, 2),
                                 fmt(1.0 / f, 3) if f > 0 else "∞"])
                b.append(("table", rows, "Eigenfrequenzen (ungedämpft, konsistente Massen)",
                          None, ""))
        # ---- Knicken
        if self.opt("buckling"):
            buck = [(n, r) for n, r in allres if getattr(r, "buckling_factors", None) is not None]
            for name, res in buck:
                b.append(self._h(2, f"Verzweigungslastfaktoren ({name})"))
                rows = [["Nr.", "α_cr"]]
                for k, f in enumerate(res.buckling_factors):
                    rows.append([str(k + 1), fmt(f, 3)])
                b.append(("table", rows, "Knicklastfaktoren α_cr = F_cr / F_Ed (lineares "
                                         "Verzweigungsproblem)", None, ""))
                a1 = float(res.buckling_factors[0]) if len(res.buckling_factors) else np.inf
                if 0 < a1 < 10:
                    b.append(("note", f"α_cr = {a1:.2f} < 10: Einfluss der Verformungen auf das "
                                      "Gleichgewicht (Theorie II. Ordnung) nach DIN EN 1993-1-1, "
                                      "5.2.1 zu berücksichtigen."))
                    self._warnings.append(f"{name}: α_cr = {a1:.2f} < 10 (Theorie II. Ordnung)")
        return b

    def _envelope_tables(self, env) -> list:
        m = self.model
        b = []
        names = env.names
        # Verschiebungen
        if env.u_max.size and env.u_max.shape[0] == m.nn:
            rows = [["Größe", "min", "Knoten", "Kombination", "max", "Knoten", "Kombination"]]
            for d in range(6):
                f = 1e3
                unit = "mm" if d < 3 else "mrad"
                i1 = int(np.argmin(env.u_min[:, d]))
                i2 = int(np.argmax(env.u_max[:, d]))
                c1 = names[int(env.u_min_src[i1, d])] if hasattr(env, "u_min_src") else ""
                c2 = names[int(env.u_max_src[i2, d])] if hasattr(env, "u_max_src") else ""
                rows.append([f"{DOF_NAMES[d]} [{unit}]", fmt(env.u_min[i1, d] * f, 3), str(i1), c1,
                             fmt(env.u_max[i2, d] * f, 3), str(i2), c2])
            b.append(("table", rows, "Extremwerte der Verschiebungen und Verdrehungen", None, ""))
        # Auflagerreaktionen
        nodes = self._support_nodes()
        if nodes and env.r_max.size:
            rows = [["Knoten", "Komponente", "min [kN, kNm]", "Kombination", "max [kN, kNm]",
                     "Kombination"]]
            for n in nodes:
                for d in range(6):
                    lo, hi = env.r_min[n, d], env.r_max[n, d]
                    if abs(lo) < 1e-9 and abs(hi) < 1e-9:
                        continue
                    c1 = names[int(env.r_min_src[n, d])] if hasattr(env, "r_min_src") else ""
                    c2 = names[int(env.r_max_src[n, d])] if hasattr(env, "r_max_src") else ""
                    comp = ["F_x", "F_y", "F_z", "M_x", "M_y", "M_z"][d]
                    rows.append([str(n), comp, fmt(lo / 1e3, 2), c1, fmt(hi / 1e3, 2), c2])
            rows, note = self._truncate(rows)
            if len(rows) > 1:
                b.append(("table", rows, "Extremwerte der Auflagerreaktionen", None, "compact"))
                if note:
                    b.append(("note", note))
        # Schnittgroessen
        if env.beam:
            rows = [["Stab / Element", "Schnittgröße", "min", "x [m]", "Kombination", "max",
                     "x [m]", "Kombination"]]
            if m.members:
                for mname, mem in m.members.items():
                    x, data = self._member_envelope(env, mem)
                    if x is None:
                        continue
                    for k in ("N", "Vy", "Vz", "Mt", "My", "Mz"):
                        mn, mx, imn, imx = data[k]
                        if np.all(np.abs(mn) < 1e-9) and np.all(np.abs(mx) < 1e-9):
                            continue
                        j1, j2 = int(np.argmin(mn)), int(np.argmax(mx))
                        rows.append([mname, f"{k} [{FORCE_UNITS[k]}]", fmt(mn[j1] / 1e3, 2),
                                     fmt(x[j1], 2), names[int(imn[j1])], fmt(mx[j2] / 1e3, 2),
                                     fmt(x[j2], 2), names[int(imx[j2])]])
                cap = "Extremwerte der Stabschnittgrößen je Stab (x ab Stabanfang)"
            else:
                for i, d in env.beam.items():
                    for k in ("N", "Vy", "Vz", "Mt", "My", "Mz"):
                        mn, mx, imn, imx = d[k]
                        if np.all(np.abs(mn) < 1e-9) and np.all(np.abs(mx) < 1e-9):
                            continue
                        j1, j2 = int(np.argmin(mn)), int(np.argmax(mx))
                        rows.append([f"Element {i}", f"{k} [{FORCE_UNITS[k]}]",
                                     fmt(mn[j1] / 1e3, 2), fmt(d["x"][j1], 2),
                                     names[int(imn[j1])], fmt(mx[j2] / 1e3, 2),
                                     fmt(d["x"][j2], 2), names[int(imx[j2])]])
                cap = "Extremwerte der Stabschnittgrößen je Element (x ab Elementanfang)"
            rows, note = self._truncate(rows)
            if len(rows) > 1:
                b.append(("table", rows, cap, None, "compact"))
                if note:
                    b.append(("note", note))
            # elastische Ausnutzung
            util = getattr(env, "util", {}) or {}
            vals = [(i, u) for i, u in util.items() if u is not None]
            if vals:
                i, u = max(vals, key=lambda t: t[1])
                b.append(("p", f"Größte elastische Randspannungsausnutzung σ/f_y = {u:.3f} "
                               f"(Element {i}, aus N, M_y, M_z ohne Teilsicherheitsbeiwert; "
                               "maßgebend sind die Nachweise nach Kapitel 5)."))
        vm = getattr(env, "node_vm_max", None)
        if vm is not None and np.any(vm):
            k = int(np.nanargmax(vm))
            b.append(("p", f"Maximale Vergleichsspannung (Knotenmittel) {vm[k] / 1e6:.1f} N/mm² "
                           f"am Knoten {k}."))
        return b

    def _member_diagram_blocks(self) -> list:
        m = self.model
        b = []
        env = self.envelopes.get("ULS") or (next(iter(self.envelopes.values()))
                                            if self.envelopes else None)
        gname, gres = self._governing_result()
        if env is None and gres is None:
            return b
        b.append(self._h(2, "Schnittgrößenverläufe der Stäbe"))
        if env is not None:
            b.append(("p", f"Dargestellt sind die Umhüllende (min/max, grau) aus "
                           f"{ENVELOPE_NAMES.get(next(k for k, v in self.envelopes.items() if v is env), '')}"
                           " und der Verlauf der jeweils maßgebenden Kombination (blau/rot)."))
        else:
            b.append(("p", f"Dargestellt sind die Verläufe für {gname}."))
        W = self.opt("figure_width")
        lim = self.opt("max_member_diagrams")
        allres = dict(self.all_results())
        for k, (mname, mem) in enumerate(m.members.items()):
            if k >= lim:
                b.append(("note", f"Diagramme für die übrigen {len(m.members) - lim} Stäbe "
                                  "wurden nicht ausgegeben (Grenze max_member_diagrams)."))
                break
            if not mem.elements:
                continue
            b.append(self._h(3, f"Stab {mname}"))
            x_env = data = None
            if env is not None:
                x_env, data = self._member_envelope(env, mem)
            for q in ("N", "Vz", "My", "Mz", "Vy", "Mt"):
                unit = FORCE_UNITS[q]
                if data is not None and x_env is not None:
                    mn, mx, imn, imx = data[q]
                    if np.all(np.abs(mn) < 1e-6) and np.all(np.abs(mx) < 1e-6):
                        continue
                    j1, j2 = int(np.argmin(mn)), int(np.argmax(mx))
                    src = int(imn[j1]) if abs(mn[j1]) >= abs(mx[j2]) else int(imx[j2])
                    cname = env.names[src]
                    res = allres.get(cname)
                    if res is not None:
                        mf = res.member_forces(mem, env.n_stations)
                        xx, vv = mf["x"], mf[q]
                    else:
                        xx, vv = x_env, np.where(np.abs(mn) >= np.abs(mx), mn, mx)
                    svg_text = sv.draw_member_diagram(xx, vv, q, unit, W, 190, (mn, mx),
                                                      f"{mname}: {q} – maßgebend {cname}")
                    cap = (f"Stab {mname}: Verlauf {q} [{unit}], Umhüllende und "
                           f"Kombination {cname}")
                else:
                    mf = gres.member_forces(mem)
                    if np.all(np.abs(mf[q]) < 1e-6):
                        continue
                    svg_text = sv.draw_member_diagram(mf["x"], mf[q], q, unit, W, 190, None,
                                                      f"{mname}: {q} – {gname}")
                    cap = f"Stab {mname}: Verlauf {q} [{unit}] für {gname}"
                b.append(self._figure(svg_text, cap))
        return b

    # ============================================================ Kapitel 5
    def chapter_design(self) -> list:
        m = self.model
        b = [self._h(1, "Nachweise nach DIN EN 1993-1-1")]
        d = self.design if self.opt("design") else None
        if d is None or not getattr(d, "members", None):
            if not self.opt("design"):
                b.append(("p", "Die Ausgabe der Nachweise ist deaktiviert."))
            elif not m.members:
                b.append(("p", "Es wurden keine Nachweise geführt (keine Stäbe definiert)."))
            else:
                b.append(("p", "Es wurden keine Nachweise geführt (keine Nachweisergebnisse; "
                               "solve_all(..., design=True) mit GZT-Kombinationen verwenden)."))
            return b
        ds = m.design
        b.append(self._h(2, "Einstellungen"))
        st = d.settings or {}
        lt = st.get("BDK", ds.lt_method)
        kv = [("Teilsicherheitsbeiwert γ_M0", fmt(st.get("gamma_M0", ds.gamma_M0), 2)),
              ("Teilsicherheitsbeiwert γ_M1", fmt(st.get("gamma_M1", ds.gamma_M1), 2)),
              ("Interaktion Biegung und Druck", st.get("Methode", f"Anhang {ds.interaction_method}")
               + (" (Methode 2)" if "B" in str(st.get("Methode", ds.interaction_method))
                  else " (Methode 1)")),
              ("Biegedrillknicken", "allgemeiner Fall, 6.3.2.2" if lt == "general"
               else "gewalzte und gleichartige geschweißte Querschnitte, 6.3.2.3"),
              ("Nationaler Anhang", ds.national_annex),
              ("Nachweisstellen je Element", str(ds.stations)),
              ("Kombinationen (GZT)", ", ".join(d.combinations[:40])
               + (" …" if len(d.combinations) > 40 else ""))]
        b.append(("kv", kv, "Einstellungen der Nachweise"))
        # Uebersicht
        b.append(self._h(2, "Übersicht"))
        rows = [["Stab", "Querschnitt", "Material", "L [m]", "Klasse", "Ausnutzung",
                 "maßgebender Nachweis", "Kombination", "x [m]", "Status"]]
        for mc in d.members.values():
            g = mc.governing
            rows.append([mc.member, mc.section, mc.material, fmt(mc.L, 2), str(mc.cls),
                         Util(mc.util), g.get("name", "–"), g.get("combo", "–"),
                         fmt(g.get("x", 0.0), 2),
                         "erfüllt" if mc.util <= 1.0 else "NICHT erfüllt"])
        rows, note = self._truncate(rows, 400)
        b.append(("table", rows, "Ausnutzung je Stab (maßgebender Nachweis über alle "
                                 "GZT-Kombinationen)", None, ""))
        if note:
            b.append(("note", note))
        if self.opt("figures"):
            labels = [mc.member for mc in list(d.members.values())[:60]]
            vals = [mc.util for mc in list(d.members.values())[:60]]
            b.append(self._figure(sv.draw_bar_chart(labels, vals, 620, None, 1.0,
                                                    "Ausnutzung je Stab"),
                                  "Ausnutzungsgrade der Stäbe (Grenze 1.0)"))
            if m.nn:
                views = self._views()
                view = views[0] if len(views) == 1 else "iso"
                svg_text = sv.draw_structure(m, view, self.opt("figure_width"),
                                             self.opt("figure_height"), util=d.util_by_element(),
                                             field="util", show_supports=True, show_loads=False,
                                             title="Ausnutzung der Stäbe")
                b.append(self._figure(svg_text, "Ausnutzung der Stäbe (Farbskala)"))
        # Einzelnachweise
        b.append(self._h(2, "Nachweise im Einzelnen"))
        for mc in d.members.values():
            b.extend(self._member_design_blocks(mc))
        nf = [mc.member for mc in d.members.values() if mc.util > 1.0]
        if nf:
            self._warnings.append("Nachweise NICHT erfüllt für: " + ", ".join(nf))
        return b

    def _member_design_blocks(self, mc) -> list:
        m = self.model
        b = [self._h(3, f"Stab {mc.member}")]
        mem = m.members.get(mc.member)
        sec = m.sections.get(mc.section)
        mat = m.materials.get(mc.material)
        fy = mat.yield_strength(sec.t_max if sec else 0.0) if mat else 0.0
        L = mc.L
        kv = [("Querschnitt", f"{mc.section}" + (f" – {sec.describe()}" if sec else "")),
              ("Material", f"{mc.material}" + (f", f_y = {fy / 1e6:.0f} N/mm²" if fy else "")),
              ("Stablänge", f"{fmt(L, 3)} m, Elemente {_ids_text(mc.elements)}"),
              ("Querschnittsklasse (maßgebend)", str(mc.cls))]
        if mem is not None:
            kv.append(("Knicklängen L_cr,y / L_cr,z",
                       f"{fmt(mem.Lcr_y if mem.Lcr_y else mem.beta_y * L, 2)} m / "
                       f"{fmt(mem.Lcr_z if mem.Lcr_z else mem.beta_z * L, 2)} m"))
            kv.append(("Biegedrillknicken",
                       (f"L_LT = {fmt(mem.L_LT if mem.L_LT else L, 2)} m, k_z = {mem.k_z:g}, "
                        f"k_w = {mem.k_w:g}, Lastangriff "
                        + {"top": "Obergurt", "bottom": "Untergurt"}.get(mem.load_position,
                                                                          "Schubmittelpunkt"))
                       if mem.lt_check else "nicht nachgewiesen (ausgeschaltet)"))
        g = mc.governing
        if g:
            kv.append(("Maßgebender Nachweis",
                       f"{g.get('name', '')} ({KIND_NAMES.get(g.get('kind', ''), g.get('kind', ''))}), Kombination "
                       f"{g.get('combo', '')}, x = {fmt(g.get('x', 0.0), 2)} m"))
        kv.append(("Ausnutzung", Util(mc.util)))
        kv.append(("Status", "Nachweis erfüllt" if mc.util <= 1.0 else "Nachweis NICHT erfüllt"))
        b.append(("kv", kv, f"Stab {mc.member}"))
        ext = mc.extremes or {}
        if ext:
            rows = [["N_min [kN]", "N_max [kN]", "max |V_y| [kN]", "max |V_z| [kN]",
                     "max |M_t| [kNm]", "max |M_y| [kNm]", "max |M_z| [kNm]"],
                    [fmt(ext.get("N_min", 0) / 1e3, 2), fmt(ext.get("N_max", 0) / 1e3, 2),
                     fmt(ext.get("Vy_max", 0) / 1e3, 2), fmt(ext.get("Vz_max", 0) / 1e3, 2),
                     fmt(ext.get("Mt_max", 0) / 1e3, 2), fmt(ext.get("My_max", 0) / 1e3, 2),
                     fmt(ext.get("Mz_max", 0) / 1e3, 2)]]
            b.append(("table", rows, "Extremwerte der Schnittgrößen über alle GZT-Kombinationen",
                      None, ""))
        # Querschnittsnachweise
        if mc.section_checks:
            b.append(self._h(4, "Querschnittsnachweise (6.2)"))
            rows = [["Kombination", "x [m]", "Klasse", "N [kN]", "V_z [kN]", "M_y [kNm]",
                     "M_z [kNm]", "maßgebend", "Ausnutzung"]]
            for sc in mc.section_checks:
                rows.append([sc.get("combo", ""), fmt(sc.get("x", 0.0), 2),
                             str(sc.get("cls", "")), fmt(sc.get("N", 0.0) / 1e3, 2),
                             fmt(sc.get("Vz", 0.0) / 1e3, 2), fmt(sc.get("My", 0.0) / 1e3, 2),
                             fmt(sc.get("Mz", 0.0) / 1e3, 2), sc.get("name", ""),
                             Util(sc.get("util", 0.0))])
            rows, note = self._truncate(rows)
            b.append(("table", rows, "Maßgebende Nachweisstelle je Kombination", None, "compact"))
            if note:
                b.append(("note", note))
            best = max(mc.section_checks, key=lambda s: s.get("util", 0.0))
            rows = [["Nachweis", "Ausnutzung", "Nachweisführung"]]
            for name, (u, txt) in (best.get("checks") or {}).items():
                rows.append([name, Util(u), txt])
            b.append(("table", rows,
                      f"Einzelnachweise an der maßgebenden Stelle x = {fmt(best.get('x', 0.0), 2)} m, "
                      f"Kombination {best.get('combo', '')}, {best.get('class_text', '')}; "
                      f"N = {fmt(best.get('N', 0.0) / 1e3, 2)} kN, V_y = {fmt(best.get('Vy', 0.0) / 1e3, 2)} kN, "
                      f"V_z = {fmt(best.get('Vz', 0.0) / 1e3, 2)} kN, M_t = {fmt(best.get('Mt', 0.0) / 1e3, 2)} kNm, "
                      f"M_y = {fmt(best.get('My', 0.0) / 1e3, 2)} kNm, M_z = {fmt(best.get('Mz', 0.0) / 1e3, 2)} kNm",
                      None, ""))
        # Stabilitaet
        if mc.stability:
            b.append(self._h(4, "Stabilitätsnachweise (6.3)"))
            rows = [["Kombination", "N_Ed [kN]", "M_y,Ed [kNm]", "M_z,Ed [kNm]", "Klasse",
                     "maßgebend", "Ausnutzung"]]
            for stb in mc.stability:
                rows.append([stb.get("combo", ""), fmt(stb.get("N_Ed", 0.0) / 1e3, 2),
                             fmt(stb.get("My_Ed", 0.0) / 1e3, 2), fmt(stb.get("Mz_Ed", 0.0) / 1e3, 2),
                             str(stb.get("cls", "")), stb.get("governing", "") or "–",
                             Util(stb.get("util", 0.0))])
            rows, note = self._truncate(rows)
            b.append(("table", rows, "Stabilitätsnachweis je Kombination (N_Ed = Druckkraft, "
                                     "Momente als Beträge)", None, "compact"))
            if note:
                b.append(("note", note))
            best = max(mc.stability, key=lambda s: s.get("util", 0.0))
            det = best.get("details", {})
            kv = []

            def dget(k, f=1.0, digits=3):
                v = det.get(k)
                return fmt(v * f, digits) if isinstance(v, (int, float, np.floating)) else "–"

            kv.append(("Biegeknicken um y",
                       f"L_cr,y = {dget('Lcr_y', 1, 2)} m, N_cr,y = {dget('N_cr_y', 1e-3, 1)} kN, "
                       f"λ̄_y = {dget('lam_y')}, Knicklinie {det.get('curve_y', '–')}, "
                       f"χ_y = {dget('chi_y')}, N_b,y,Rd = {dget('N_b_y_Rd', 1e-3, 1)} kN"))
            kv.append(("Biegeknicken um z",
                       f"L_cr,z = {dget('Lcr_z', 1, 2)} m, N_cr,z = {dget('N_cr_z', 1e-3, 1)} kN, "
                       f"λ̄_z = {dget('lam_z')}, Knicklinie {det.get('curve_z', '–')}, "
                       f"χ_z = {dget('chi_z')}, N_b,z,Rd = {dget('N_b_z_Rd', 1e-3, 1)} kN"))
            if det.get("N_cr_T") is not None and np.isfinite(det.get("N_cr_T", np.inf)):
                kv.append(("Drillknicken",
                           f"N_cr,T = {dget('N_cr_T', 1e-3, 1)} kN, λ̄_T = {dget('lam_T')}, "
                           f"χ_T = {dget('chi_T')}, N_b,T,Rd = {dget('N_b_T_Rd', 1e-3, 1)} kN"))
            if det.get("M_cr") is not None and np.isfinite(det.get("M_cr", np.inf)):
                kv.append(("Biegedrillknicken",
                           f"M_cr = {dget('M_cr', 1e-3, 1)} kNm (C_1 = {dget('C1', 1, 3)}, "
                           f"{det.get('C1_text', '')}, L_LT = {dget('L_LT', 1, 2)} m), "
                           f"λ̄_LT = {dget('lam_LT')}, Knicklinie {det.get('curve_LT', '–')}, "
                           f"f = {dget('f_LT')}, χ_LT = {dget('chi_LT')}"))
            elif "chi_LT" in det:
                kv.append(("Biegedrillknicken", f"χ_LT = {dget('chi_LT')} (kein Nachweis "
                                                "erforderlich bzw. nicht anfällig)"))
            if "kyy" in det:
                kv.append(("Interaktionsbeiwerte (Anhang B)",
                           f"C_my = {dget('Cmy', 1, 3)}, C_mz = {dget('Cmz', 1, 3)}, "
                           f"k_yy = {dget('kyy')}, k_yz = {dget('kyz')}, k_zy = {dget('kzy')}, "
                           f"k_zz = {dget('kzz')}; n_y = N_Ed/(χ_y N_Rk/γ_M1) = {dget('n_y')}, "
                           f"n_z = {dget('n_z')}"))
            b.append(("kv", kv, f"Kennwerte des Stabilitätsnachweises, Kombination "
                                f"{best.get('combo', '')}"))
            rows = [["Nachweis", "Ausnutzung", "Nachweisführung"]]
            for name, (u, txt) in (best.get("checks") or {}).items():
                rows.append([name, Util(u), txt])
            if len(rows) > 1:
                b.append(("table", rows, "Stabilitätsnachweise für die maßgebende Kombination "
                                         f"{best.get('combo', '')} (Gl. 6.46, 6.54, 6.61, 6.62)",
                          None, ""))
            else:
                b.append(("p", "Kein Stabilitätsnachweis erforderlich (λ̄ ≤ 0.2 bzw. "
                               "N_Ed/N_cr ≤ 0.04)."))
        if mc.warnings:
            b.append(("list", [f"Hinweis: {w}" for w in mc.warnings]))
            self._warnings.extend(f"Stab {mc.member}: {w}" for w in mc.warnings)
        return b

    # ============================================================ Kapitel 6
    def chapter_beulen(self) -> list:
        """Beulnachweise der Blechfelder nach DIN EN 1993-1-5."""
        m = self.model
        b = [self._h(1, "Beulnachweise nach DIN EN 1993-1-5")]
        bl = self.beulen if self.opt("beulen") else None
        if bl is None or not getattr(bl, "felder", None):
            if not self.opt("beulen"):
                b.append(("p", "Die Ausgabe der Beulnachweise ist deaktiviert."))
            elif not m.beulfelder:
                b.append(("p", "Es sind keine Beulfelder festgelegt. Das Beulen "
                               "schlanker Blechfelder ist gesondert nachzuweisen; "
                               "das Schubbeulen der Stegbleche wird in Kapitel 5 "
                               "bei den Querschnittsnachweisen geführt."))
            else:
                b.append(("p", "Es wurden keine Beulnachweise geführt (keine "
                               "Flächenergebnisse)."))
            b.extend(self._abschnitt_lasteinleitung())
            return b
        st = bl.settings or {}
        b.append(self._h(2, "Grundlagen"))
        b.append(("list", [
            "Methode der reduzierten Spannungen nach Abschnitt 10: aus dem "
            "Spannungszustand des Feldes (σ_x, σ_z, τ) werden der Fließfaktor "
            "α_ult,k (Gl. 10.3) und der Beulfaktor α_cr (Gl. 10.6) gebildet; daraus "
            "λ̄_p = √(α_ult,k/α_cr).",
            "Beulwerte k_σ nach Tab. 4.1 beziehungsweise 4.2 (abhängig vom "
            "Spannungsverhältnis ψ und der Lagerung), k_τ nach A.3; Bezugsspannung "
            "σ_E = π² E t² / (12 (1−ν²) b²).",
            "Abminderungsbeiwerte ρ nach 4.4(2) für die Längsspannungen und χ_w "
            "nach Tab. 5.1 für den Schub; Nachweis nach Gl. (10.5). Zusätzlich wird "
            "die Vereinfachung 10.5(2) mit einem einzigen Beiwert ρ_min ausgewiesen.",
            f"γ_M1 = {fmt(st.get('gamma_M1', 1.1), 2)}, η = {fmt(st.get('eta', 1.2), 1)}; "
            f"geführt über {len(bl.kombinationen)} GZT-Kombinationen, die "
            "ungünstigste ist maßgebend.",
            "Längsversteifte Felder: σ_cr,p nach Anhang A.2.2 (eine oder zwei "
            "Steifen) beziehungsweise A.1(2) (ab drei Steifen), Schubbeulwert "
            "k_τ + k_τ,st nach A.3(2); zwischen Platten- und Knickstabverhalten "
            "wird nach 4.5.4 interpoliert (ρ_c aus ρ, χ_c und ξ). Die Steifen "
            "selbst werden nach Abschnitt 9 geprüft (Drillknicken 9.2.1(8), "
            "Mindeststeifigkeit starrer Quersteifen 9.3.3).",
            "Zylinderschalen werden nach DIN EN 1993-1-6, Abschnitt 8.5 geführt: "
            "kritische Beulspannungen nach Anhang D.1, Imperfektionsbeiwerte nach "
            "der Herstelltoleranzklasse, Abminderung χ nach 8.5.2(3) und "
            "Interaktion nach 8.5.3(3).",
        ]))
        b.append(self._h(2, "Übersicht"))
        rows = [["Beulfeld", "a [m]", "b [m]", "t [mm]", "σ_x [MPa]", "σ_z [MPa]",
                 "τ [MPa]", "λ̄_p", "ρ_x", "χ_w", "Ausnutzung", "Kombination",
                 "Status"]]
        for c in bl.felder.values():
            w = c.werte or {}
            rows.append([c.name, fmt(c.a, 2), fmt(c.b, 2), fmt(c.t * 1e3, 0),
                         fmt(w.get("sigma_x", 0.0) / 1e6, 1),
                         fmt(w.get("sigma_z", 0.0) / 1e6, 1),
                         fmt(w.get("tau", 0.0) / 1e6, 1),
                         fmt(w.get("lambda_p", 0.0), 3), fmt(w.get("rho_x", 1.0), 3),
                         fmt(w.get("chi_w", 1.0), 3), Util(c.util), c.kombination,
                         "erfüllt" if c.util <= 1.0 and not c.fehler
                         else ("nicht geführt" if c.fehler else "NICHT erfüllt")])
        b.append(("table", rows, "Beulfelder: Spannungen, Schlankheit und Ausnutzung",
                  None, ""))
        if self.opt("figures"):
            liste = [c for c in bl.felder.values() if not c.fehler][:60]
            if liste:
                b.append(self._figure(
                    sv.draw_bar_chart([c.name for c in liste], [c.util for c in liste],
                                      620, None, 1.0, "Ausnutzung je Beulfeld"),
                    "Ausnutzungsgrade der Beulnachweise (Grenze 1.0)"))

        b.append(self._h(2, "Nachweise im Einzelnen"))
        for c in bl.felder.values():
            b.append(self._h(3, f"Beulfeld {c.name}"))
            if c.fehler:
                b.append(("p", f"Der Nachweis konnte nicht geführt werden: {c.fehler}"))
                self._warnings.append(f"Beulfeld {c.name}: {c.fehler}")
                continue
            w = c.werte or {}
            bf = m.beulfelder.get(c.name)
            kv = []
            if bf is not None and bf.beschreibung:
                kv.append(("Beschreibung", bf.beschreibung))
            kv += [("Feld", f"a × b × t = {c.a:.2f} × {c.b:.2f} m × {c.t * 1e3:.0f} mm"
                            + (f", {bf.bezug()}" if bf is not None else "")),
                   ("Lagerung", "beidseitig gestützt" if (bf is None or bf.rand == "beidseitig")
                    else "einseitig gestützt (ein Rand frei)"),
                   ("Streckgrenze f_y", f"{c.fy / 1e6:.0f} N/mm²"),
                   ("maßgebende Kombination", c.kombination),
                   ("Spannungen (Druck positiv)",
                    f"σ_x = {w.get('sigma_x', 0) / 1e6:.1f}, "
                    f"σ_z = {w.get('sigma_z', 0) / 1e6:.1f}, "
                    f"τ = {w.get('tau', 0) / 1e6:.1f} N/mm²"),
                   ("Spannungsverhältnisse",
                    f"ψ_x = {w.get('psi_x', 1.0):.2f}, ψ_z = {w.get('psi_z', 1.0):.2f}"),
                   ("Bezugsspannung σ_E", f"{w.get('sigma_E', 0) / 1e6:.2f} N/mm²"),
                   ("Beulwerte",
                    f"k_σ,x = {w.get('k_sigma_x', 0):.2f}, k_σ,z = {w.get('k_sigma_z', 0):.2f}, "
                    f"k_τ = {w.get('k_tau', 0):.2f} (α = a/b = {w.get('alpha', 0):.2f})"),
                   ("kritische Spannungen",
                    f"σ_cr,x = {w.get('sigma_cr_x', 0) / 1e6:.1f}, "
                    f"σ_cr,z = {w.get('sigma_cr_z', 0) / 1e6:.1f}, "
                    f"τ_cr = {w.get('tau_cr', 0) / 1e6:.1f} N/mm²"),
                   ("α_ult,k (Gl. 10.3)", fmt(w.get("alpha_ult_k", 0.0), 3)),
                   ("α_cr (Gl. 10.6)", fmt(w.get("alpha_cr", 0.0), 3)),
                   ("Schlankheit λ̄_p", fmt(w.get("lambda_p", 0.0), 3)),
                   ("Abminderungsbeiwerte",
                    f"ρ_x = {w.get('rho_x', 1.0):.3f}, ρ_z = {w.get('rho_z', 1.0):.3f}, "
                    f"χ_w = {w.get('chi_w', 1.0):.3f}"),
                   ("Ausnutzung nach Gl. (10.5)", Util(c.util)),
                   ("Vereinfachung 10.5(2) mit ρ_min",
                    f"ρ_min = {w.get('rho_min', 1.0):.3f} → η = "
                    f"{fmt(w.get('eta_rho_min', 0.0), 3)}"),
                   ("Status", "Nachweis erfüllt" if c.util <= 1.0
                    else "Nachweis NICHT erfüllt")]
            b.append(("kv", kv, f"Beulfeld {c.name}"))
            zyl = w.get("zylinder")
            if zyl:
                me, um, sb = zyl["meridian"], zyl["umfang"], zyl["schub"]
                rows = [["Richtung", "σ_Ed [MPa]", "σ_Rcr [MPa]", "λ̄", "χ",
                         "σ_Rd [MPa]", "Ausnutzung"]]
                rows.append(["Meridian (x)", fmt(w.get("sigma_x", 0) / 1e6, 1),
                             fmt(me["sigma_Rcr"] / 1e6, 1), fmt(me["lambda"], 3),
                             fmt(me["chi"], 3), fmt(me["sigma_Rd"] / 1e6, 1),
                             Util(me["eta"])])
                rows.append(["Umfang (θ)", fmt(w.get("sigma_z", 0) / 1e6, 1),
                             fmt(um["sigma_Rcr"] / 1e6, 1), fmt(um["lambda"], 3),
                             fmt(um["chi"], 3), fmt(um["sigma_Rd"] / 1e6, 1),
                             Util(um["eta"])])
                rows.append(["Schub (xθ)", fmt(w.get("tau", 0) / 1e6, 1),
                             fmt(sb["sigma_Rcr"] / math.sqrt(3) / 1e6, 1),
                             fmt(sb["lambda"], 3), fmt(sb["chi"], 3),
                             fmt(sb.get("tau_Rd", 0) / 1e6, 1), Util(sb["eta"])])
                b.append(("table", rows, "Schalenbeulen je Spannungsrichtung "
                                         "(EN 1993-1-6, 8.5)", None, ""))
                b.append(("kv", [
                    ("Zylinder", f"r = {w.get('r', 0):.3f} m, t = {c.t * 1e3:.1f} mm, "
                                 f"l = {w.get('l', 0):.3f} m, r/t = {zyl['r_t']:.0f}"),
                    ("Längenparameter ω", f"{zyl['omega']:.1f} ({zyl['bereich']})"),
                    ("Herstelltoleranz", zyl["qualitaet"]),
                    ("Beiwerte", f"C_x = {fmt(zyl.get('C_x') or 0, 3)}, "
                                 f"C_θ = {fmt(zyl.get('C_theta') or 0, 3)}, "
                                 f"C_τ = {fmt(zyl.get('C_tau') or 0, 3)}"),
                    ("Imperfektionsbeiwerte",
                     f"α_x = {zyl['alpha_x']['alpha']:.3f} "
                     f"(Δw_k/t = {zyl['alpha_x'].get('Delta_wk_t', 0):.3f}), "
                     f"α_θ = {zyl['alpha_theta']:.2f}, α_τ = {zyl['alpha_tau']:.2f}"),
                    ("Interaktion 8.5.3(3)",
                     f"k_x = {zyl['k_x']:.2f}, k_θ = {zyl['k_theta']:.2f}, "
                     f"k_τ = {zyl['k_tau']:.2f}, k_i = {zyl['k_i']:.3f} → "
                     f"{fmt(zyl['interaktion'], 3)}"),
                ], f"Schalenbeulen {c.name}"))
            st = w.get("steifen") or []
            if st:
                rows = [["Steife", "Art", "Lage [mm]", "A_sl [cm²]", "I_sl [cm⁴]"]]
                for x in st:
                    rows.append([x.get("name") or "–", x.get("art", ""),
                                 fmt(x.get("lage", 0) * 1e3, 0),
                                 fmt(x.get("A_sl", 0) * 1e4, 2),
                                 fmt(x.get("I_sl", 0) * 1e8, 1)])
                b.append(("table", rows, "Steifen des Feldes", None, ""))
                kp = w.get("k_sigma_p") or {}
                kv2 = [("Verfahren für σ_cr,p", kp.get("verfahren", "–"))]
                if "a_c" in kp:
                    kv2.append(("Grenzlänge a_c (A.2.2)",
                                f"{kp['a_c']:.3f} m → {kp.get('zweig', '')}"))
                if "gamma" in kp:
                    kv2.append(("γ / δ (A.1)",
                                f"{fmt(kp['gamma'], 2)} / {fmt(kp['delta'], 4)}"))
                kv2 += [("k_τ unversteift + Zuschlag der Steifen",
                         f"{fmt(w.get('k_tau_unversteift', 0), 2)} + "
                         f"{fmt(w.get('k_tau_st', 0), 2)} = {fmt(w.get('k_tau', 0), 2)}")]
                if "sigma_cr_c" in w:
                    kv2 += [("σ_cr,c (Knickstab, 4.5.3)",
                             f"{w['sigma_cr_c'] / 1e6:.1f} N/mm²"),
                            ("ξ = σ_cr,p/σ_cr,c − 1", fmt(w.get("xi", 0.0), 3)),
                            ("χ_c (Knicklinie)", fmt(w.get("chi_c", 1.0), 3)),
                            ("ρ (Platte) → ρ_c (interpoliert, 4.5.4)",
                             f"{fmt(w.get('rho_platte', 1.0), 3)} → "
                             f"{fmt(w.get('rho_x', 1.0), 3)}")]
                b.append(("kv", kv2, "Längsversteifung"))
                sn = w.get("steifennachweise") or []
                if sn:
                    rows = [["Steife", "Nachweis", "Ergebnis", "Status"]]
                    for d in sn:
                        if d.get("gefuehrt"):
                            rows.append([d.get("name", ""),
                                         "Mindeststeifigkeit (9.3.3)" if d.get("art") == "quer"
                                         else "Drillknicken (9.2.1(8))",
                                         _pretty(d.get("text") or d.get("regel", ""))
                                         + (f" – I_st = {fmt(d.get('I_st', 0) * 1e8, 1)} cm⁴ "
                                            f"≥ {fmt(d.get('I_noetig', 0) * 1e8, 1)} cm⁴"
                                            if d.get("art") == "quer" else ""),
                                         "erfüllt" if d.get("ok") else "NICHT erfüllt"])
                        else:
                            rows.append([d.get("name", ""), "–",
                                         _pretty(d.get("hinweis", "")), "nicht geführt"])
                    b.append(("table", rows, "Nachweise der Steifen (Abschnitt 9)",
                              None, ""))
            if len(c.je_kombination) > 1:
                zeilen = sorted(c.je_kombination, key=lambda d: -d["eta"])
                rows = [["Kombination", "σ_x [MPa]", "σ_z [MPa]", "τ [MPa]", "λ̄_p",
                         "Ausnutzung"]]
                for d in zeilen:
                    rows.append([d["kombination"], fmt(d["sigma_x"] / 1e6, 1),
                                 fmt(d["sigma_z"] / 1e6, 1), fmt(d["tau"] / 1e6, 1),
                                 fmt(d["lambda_p"], 3), Util(d["eta"])])
                rows, note = self._truncate(rows, self.opt("max_detail_combinations") or 12)
                b.append(("table", rows, "Beulnachweis je Kombination (absteigend geordnet)",
                          None, ""))
                if note:
                    b.append(("note", note))
            if c.hinweise:
                b.append(("list", [f"Hinweis: {h}" for h in c.hinweise]))
        nf = [c.name for c in bl.felder.values() if c.util > 1.0]
        if nf:
            self._warnings.append("Beulnachweis NICHT erfüllt für: " + ", ".join(nf))
        b.extend(self._abschnitt_lasteinleitung())
        return b

    def _abschnitt_lasteinleitung(self) -> list:
        """Lasteinleitung nach DIN EN 1993-1-5, Abschnitt 6."""
        le = self.lasteinleitung
        if le is None or not getattr(le, "stellen", None):
            return []
        b = [self._h(2, "Lasteinleitung (Abschnitt 6)")]
        b.append(("list", [
            "Beulnachweis des Stegs unter einer örtlich eingeleiteten Querkraft: "
            "F_cr = 0,9 k_F E t_w³/h_w mit k_F nach Bild 6.1, wirksame Lastlänge "
            "ℓ_y nach 6.5 mit m_1 = f_yf b_f/(f_yw t_w) und m_2 = 0,02 (h_w/t_f)² "
            "für λ̄_F > 0,5.",
            "λ̄_F = √(ℓ_y t_w f_yw/F_cr), χ_F = 0,5/λ̄_F ≤ 1,0, L_eff = χ_F ℓ_y, "
            "F_Rd = f_yw L_eff t_w/γ_M1 (6.2).",
            "Wirken gleichzeitig Biegung und eine Querlast, gilt zusätzlich die "
            "Interaktion nach 7.2: η_2 + 0,8 η_1 ≤ 1,4.",
        ]))
        rows = [["Stelle", "Bezug", "Typ", "F_Ed [kN]", "F_Rd [kN]", "ℓ_y [mm]",
                 "λ̄_F", "χ_F", "Ausnutzung", "Kombination", "Status"]]
        for c in le.stellen.values():
            w = c.werte or {}
            rows.append([c.name, c.bezug, c.typ, fmt(c.F_Ed / 1e3, 1),
                         fmt(c.F_Rd / 1e3, 1), fmt(w.get("l_y", 0) * 1e3, 0),
                         fmt(w.get("lambda_F", 0), 3), fmt(w.get("chi_F", 1), 3),
                         Util(c.util), c.kombination,
                         "erfüllt" if c.util <= 1.0 and not c.fehler
                         else ("nicht geführt" if c.fehler else "NICHT erfüllt")])
        b.append(("table", rows, "Lasteinleitungsstellen", None, ""))
        for c in le.stellen.values():
            b.append(self._h(3, f"Lasteinleitung {c.name}"))
            if c.fehler:
                b.append(("p", f"Der Nachweis konnte nicht geführt werden: {c.fehler}"))
                self._warnings.append(f"Lasteinleitung {c.name}: {c.fehler}")
                continue
            w = c.werte
            kv = [("Bezug", c.bezug),
                  ("Art der Lasteinleitung", w.get("beschreibung", c.typ)),
                  ("Lasteinleitungslänge s_s", f"{w.get('s_s', 0) * 1e3:.0f} mm"),
                  ("Abstand der Quersteifen a",
                   f"{w.get('a', 0) * 1e3:.0f} mm" if w.get("a") else "keine"),
                  ("Beulwert k_F", fmt(w.get("k_F", 0), 3)),
                  ("F_cr = 0,9 k_F E t_w³/h_w", f"{w.get('F_cr', 0) / 1e3:.0f} kN"),
                  ("m_1 / m_2", f"{fmt(w.get('m_1', 0), 2)} / {fmt(w.get('m_2', 0), 2)}"),
                  ("wirksame Lastlänge ℓ_y", f"{w.get('l_y', 0) * 1e3:.0f} mm"),
                  ("Schlankheit λ̄_F", fmt(w.get("lambda_F", 0), 3)),
                  ("Abminderung χ_F = 0,5/λ̄_F ≤ 1", fmt(w.get("chi_F", 1), 3)),
                  ("L_eff = χ_F ℓ_y", f"{w.get('L_eff', 0) * 1e3:.0f} mm"),
                  ("F_Rd", f"{c.F_Rd / 1e3:.1f} kN"),
                  ("maßgebende Kombination", c.kombination),
                  ("F_Ed", f"{c.F_Ed / 1e3:.1f} kN"),
                  ("Ausnutzung η_2", Util(c.util)),
                  ("Status", "Nachweis erfüllt" if c.util <= 1.0
                   else "Nachweis NICHT erfüllt")]
            b.append(("kv", kv, f"Lasteinleitung {c.name}"))
            if c.hinweise:
                b.append(("list", [f"Hinweis: {h}" for h in c.hinweise]))
        nf = [c.name for c in le.stellen.values() if c.util > 1.0]
        if nf:
            self._warnings.append("Lasteinleitung NICHT erfüllt für: " + ", ".join(nf))
        return b

    # ============================================================ Kapitel 7
    def chapter_fatigue(self) -> list:
        m = self.model
        b = [self._h(1, "Ermüdungsnachweis nach DIN EN 1993-1-9")]
        f = self.fatigue if self.opt("fatigue") else None
        if f is None or not getattr(f, "members", None):
            if not self.opt("fatigue"):
                b.append(("p", "Die Ausgabe des Ermüdungsnachweises ist deaktiviert."))
            elif not m.fatigue_loads:
                b.append(("p", "Kein Ermüdungsnachweis erforderlich (keine Ermüdungslasten "
                               "definiert)."))
            else:
                b.append(("p", "Es wurden keine Ermüdungsnachweise geführt (keine Stäbe mit "
                               "Kerbfall oder keine Ergebnisse)."))
            return b
        from ..ec3.fatigue import DETAIL_EXAMPLES, sn_life, GAMMA_MF
        ds = m.design
        b.append(self._h(2, "Grundlagen"))
        b.append(("list", [
            "Nennspannungskonzept: Spannungsschwingbreiten Δσ aus der Differenz der "
            "Randspannungen (N/A ± M_y/W_el,y ± M_z/W_el,z) zwischen Ober- und Unterlast; "
            "Schub Δτ aus V/A_v.",
            "Wöhlerlinien nach Bild 7.1: m = 3 bis N_D = 5·10⁶ (Δσ_D = 0.737 Δσ_C), m = 5 bis "
            "N_L = 10⁸ (Δσ_L = 0.549 Δσ_D), darunter keine Schädigung; Schub m = 5 bis "
            "N_L = 10⁸ (Δτ_L = 0.457 Δτ_C).",
            f"Schadensakkumulation nach Palmgren-Miner: D = Σ n_i / N_Ri ≤ 1.0; "
            f"γ_Ff = {fmt(getattr(f, 'gamma_Ff', ds.gamma_Ff), 2)}, γ_Mf nach Tabelle 3.1 "
            "(schadenstolerant: 1.00 / 1.15, sicheres Leben: 1.15 / 1.35 für geringe / hohe "
            "Schadensfolgen).",
            "Ausnutzung = D_σ + D_τ (sinngemäß Gl. 8.3); zusätzlich wird die schadensäquivalente "
            "Schwingbreite Δσ_E,2 bei 2·10⁶ Lastspielen ausgewiesen.",
        ]))
        b.append(self._h(2, "Übersicht"))
        rows = [["Stab", "Kerbfall Δσ_C [MPa]", "γ_Mf", "max Δσ [MPa]", "Δσ_E,2 [MPa]",
                 "D_σ (Miner)", "D_τ", "Ausnutzung", "maßgebende Ermüdungslast"]]
        for fm in f.members.values():
            rows.append([fm.member, fmt(fm.category / 1e6, 0), fmt(fm.gamma_Mf, 2),
                         fmt(fm.dsig_max / 1e6, 1), fmt(fm.dsig_E2 / 1e6, 1), fmt(fm.D, 3),
                         fmt(fm.D_shear, 3), Util(fm.util), _pretty(fm.governing)])
        rows, note = self._truncate(rows, 400)
        b.append(("table", rows, "Ermüdungsnachweis je Stab", None, ""))
        if note:
            b.append(("note", note))
        b.append(self._h(2, "Nachweise im Einzelnen"))
        for fm in f.members.values():
            mem = m.members.get(fm.member)
            b.append(self._h(3, f"Stab {fm.member}"))
            cat_mpa = int(round(fm.category / 1e6))
            kv = [("Kerbfall Normalspannung Δσ_C",
                   f"{cat_mpa} MPa – {DETAIL_EXAMPLES.get(cat_mpa, 'Kerbfall nach Tabellen 8.1–8.10')}"),
                  ("Kerbfall Schub Δτ_C", f"{fm.category_shear / 1e6:.0f} MPa")]
            if mem is not None:
                kv.append(("Bemessungskonzept / Schadensfolgen",
                           ("schadenstolerant" if mem.assessment == "damage_tolerant"
                            else "sicheres Leben") + " / "
                           + ("gering" if mem.consequence == "low" else "hoch")
                           + f" → γ_Mf = {fmt(GAMMA_MF.get((mem.assessment, mem.consequence), fm.gamma_Mf), 2)}"))
            kv += [("Dauerfestigkeit Δσ_D (5·10⁶)", f"{0.737 * fm.category / fm.gamma_Mf / 1e6:.1f} MPa"),
                   ("Schwellenwert Δσ_L (10⁸)",
                    f"{0.549 * 0.737 * fm.category / fm.gamma_Mf / 1e6:.1f} MPa"),
                   ("Schädigung D_σ / D_τ", f"{fmt(fm.D, 4)} / {fmt(fm.D_shear, 4)}"),
                   ("Δσ_E,2 / (Δσ_C/γ_Mf)", f"{fm.dsig_E2 / 1e6:.1f} / "
                                            f"{fm.category / fm.gamma_Mf / 1e6:.1f} = {fmt(fm.util_E2, 3)}"),
                   ("Ausnutzung D_σ + D_τ", Util(fm.util)),
                   ("Status", "Nachweis erfüllt" if fm.util <= 1.0 else "Nachweis NICHT erfüllt")]
            b.append(("kv", kv, f"Ermüdung Stab {fm.member}"))
            rows = [["Ermüdungslast", "Δσ [MPa]", "n", "N_R", "n / N_R", "x [m]"]]
            for r in fm.ranges:
                NR = sn_life(r[0], fm.category, fm.gamma_Mf)
                rows.append([r[2], fmt(r[0] / 1e6, 1), f"{r[1]:.3g}",
                             f"{NR:.3g}" if np.isfinite(NR) else "∞",
                             fmt(r[1] / NR, 4) if np.isfinite(NR) and NR > 0 else "0",
                             fmt(r[3], 2)])
            b.append(("table", rows, "Spannungsschwingbreiten (Normalspannung, maßgebende "
                                     "Stelle je Ermüdungslast)", None, ""))
            if fm.ranges_shear and any(r[0] > 0 for r in fm.ranges_shear):
                rows = [["Ermüdungslast", "Δτ [MPa]", "n", "N_R", "n / N_R", "x [m]"]]
                for r in fm.ranges_shear:
                    NR = sn_life(r[0], fm.category_shear, fm.gamma_Mf, shear=True)
                    rows.append([r[2], fmt(r[0] / 1e6, 1), f"{r[1]:.3g}",
                                 f"{NR:.3g}" if np.isfinite(NR) else "∞",
                                 fmt(r[1] / NR, 4) if np.isfinite(NR) and NR > 0 else "0",
                                 fmt(r[3], 2)])
                b.append(("table", rows, "Schubspannungsschwingbreiten", None, ""))
            if self.opt("figures"):
                pts = [(r[0], r[1], r[2]) for r in fm.ranges]
                b.append(self._figure(
                    sv.draw_sn_curve(fm.category, pts, fm.gamma_Mf, 600, 330,
                                     f"Wöhlerlinie Stab {fm.member}"),
                    f"Wöhlerlinie Kerbfall {cat_mpa} (γ_Mf = {fm.gamma_Mf:.2f}) mit den "
                    f"Beanspruchungen des Stabes {fm.member}"))
            if fm.warnings:
                b.append(("list", [f"Hinweis: {w}" for w in fm.warnings]))
                self._warnings.extend(f"Ermüdung {fm.member}: {w}" for w in fm.warnings)
        nf = [fm.member for fm in f.members.values() if fm.util > 1.0]
        if nf:
            self._warnings.append("Ermüdungsnachweis NICHT erfüllt für: " + ", ".join(nf))
        return b

    # ============================================================ Kapitel 7
    def chapter_joints(self) -> list:
        """Anschluesse: jede Naht und jede Schraube mit ihrer Ausnutzung."""
        m = self.model
        b = [self._h(1, "Anschlüsse nach DIN EN 1993-1-8")]
        j = self.joints if self.opt("joints") else None
        if j is None or not getattr(j, "joints", None):
            if not self.opt("joints"):
                b.append(("p", "Die Ausgabe der Anschlussnachweise ist deaktiviert."))
            elif not m.joints:
                b.append(("p", "Im Modell ist kein Anschluss angelegt. Anschlüsse sind "
                               "dann gesondert nachzuweisen."))
            else:
                b.append(("p", "Es wurden keine Anschlussnachweise geführt "
                               "(keine Ergebnisse)."))
            return b
        from ..joints.anschluss import KURZ, vorlage
        b.append(self._h(2, "Grundlagen"))
        st = j.settings or {}
        b.append(("list", [
            "Schrauben nach DIN EN 1993-1-8, 3.6 und 3.7: Abscheren F_v,Rd, Lochleibung "
            "F_b,Rd, Zug F_t,Rd, Durchstanzen B_p,Rd, Interaktion Abscheren und Zug "
            "(Tab. 3.4) sowie Gleitfestigkeit F_s,Rd der Kategorien B und C (3.9).",
            "Zugzone geschraubter Stirnplatten über den äquivalenten T-Stummel nach 6.2.4 "
            "(Versagensmodus 1 bis 3, wirksame Längen nach Tab. 6.4/6.5).",
            "Kehl- und Stumpfnähte nach 4.5.3: Richtungsbezogenes Verfahren "
            "(σ_⊥, τ_⊥, τ_∥ mit β_w nach Tab. 4.1) und Vereinfachtes Verfahren; "
            "Nahtdicken nach 4.5.1.",
            "Bleche: Zug im Brutto- und Nettoquerschnitt (EN 1993-1-1, 6.2.3), "
            "Blockversagen nach 3.10.2, Rand- und Lochabstände nach Tab. 3.3.",
            "Ermüdung der Anschlussteile nach DIN EN 1993-1-9, Kerbfälle Tab. 8.1 "
            "(Schrauben, Bleche mit Loch) und Tab. 8.5 (Nähte); Schadensakkumulation "
            "nach Palmgren-Miner über alle Ermüdungslasten.",
            f"Teilsicherheitsbeiwerte: γ_M0 = {fmt(st.get('gamma_M0', 1.0), 2)}, "
            f"γ_M2 = {fmt(st.get('gamma_M2', 1.25), 2)}, "
            f"γ_Ff = {fmt(st.get('gamma_Ff', 1.0), 2)}.",
            "Die Schnittgrößen sind die Stabendschnittgrößen am Anschlusspunkt; jeder "
            f"Anschluss wird über alle {len(j.combinations)} GZT-Kombinationen geführt, "
            "die ungünstigste ist maßgebend.",
            "Momenten-Rotations-Verhalten: Anfangssteifigkeit S_j,ini = E z_eq² / Σ(1/k_i) "
            "nach dem Komponentenverfahren (6.3.1) mit den Steifigkeitsbeiwerten k_i "
            "nach Tab. 6.11; mehrere Schraubenreihen werden nach 6.3.3.1 zu einer "
            "Ersatzfeder zusammengefasst.",
            "Momententragfähigkeit M_j,Rd nach 6.2.7 aus den Reihenkräften und ihren "
            "Hebelarmen zum Druckpunkt; übersteigt die Zugkraft die Druckzone, wird sie "
            "von der untersten Reihe her abgebaut.",
            "Klassifizierung nach 5.2.2.5 (starr, nachgiebig, gelenkig anhand "
            "k_b E I_b / L_b) und 5.2.3 (voll-, teiltragfähig, gelenkig); "
            "Rotationsvermögen nach 6.4.2.",
            "In der Berechnung sitzt ein nachgiebiger Anschluss als Drehfeder am "
            "Stabende, mit S_j = S_j,ini/η nach der Vereinfachung 5.1.2(4).",
        ]))

        b.append(self._h(2, "Übersicht"))
        rows = [["Anschluss", "Typ", "Ort", "S_j,ini [MNm/rad]", "Klasse",
                 "M_j,Rd [kNm]", "Ausnutzung", "maßgebender Nachweis", "Kombination",
                 "D (Ermüdung)", "Status"]]
        for c in j.joints.values():
            g = c.gelenk
            rows.append([c.name, KURZ.get(c.typ, c.typ), c.ort,
                         _steifigkeit_text(g), g.klasse if g else "",
                         fmt(g.M_j_Rd / 1e3, 1) if g and g.M_j_Rd else "-",
                         Util(c.util), _pretty(c.massgebend or c.fehler), c.kombination,
                         Util(c.D) if c.D else "-",
                         "erfüllt" if c.eta <= 1.0 and not c.fehler
                         else ("nicht geführt" if c.fehler else "NICHT erfüllt")])
        b.append(("table", rows, "Anschlüsse: Steifigkeit, Tragfähigkeit, Ausnutzung",
                  None, ""))
        if self.opt("figures"):
            liste = [c for c in j.joints.values() if not c.fehler][:60]
            if liste:
                b.append(self._figure(
                    sv.draw_bar_chart([c.name for c in liste], [c.eta for c in liste],
                                      620, None, 1.0, "Ausnutzung je Anschluss"),
                    "Ausnutzungsgrade der Anschlüsse (Grenze 1.0; "
                    "Tragfähigkeit oder Ermüdung, was größer ist)"))

        b.append(self._h(2, "Nachweise im Einzelnen"))
        for c in j.joints.values():
            b.append(self._h(3, f"Anschluss {c.name}"))
            if c.fehler:
                b.append(("p", f"Der Nachweis konnte nicht geführt werden: {c.fehler}"))
                self._warnings.append(f"Anschluss {c.name}: {c.fehler}")
                continue
            e = m.elements[c.elem] if c.elem < len(m.elements) else None
            stab = next((n for n, mm in m.members.items() if c.elem in mm.elements), "")
            kv = [("Anschlusstyp", KURZ.get(c.typ, c.typ)),
                  ("Ort", c.ort + (f", Stab {stab}" if stab else "")
                   + (f", {e.sec} aus {e.mat}" if e is not None and e.sec else ""))]
            try:
                kv += vorlage(m, m.joints[c.name]).kennwerte()
            except Exception as ex:            # noqa: BLE001
                kv.append(("Geometrie", f"nicht darstellbar: {ex}"))
            kv += [("maßgebende Kombination", c.kombination),
                   ("Schnittgrößen am Anschluss",
                    ", ".join(f"{k} = {v / (1e3):.1f} " + ("kNm" if k.startswith("M") else "kN")
                              for k, v in c.kraefte.items())),
                   ("maßgebender Nachweis", _pretty(c.massgebend)),
                   ("Ausnutzung (Tragfähigkeit)", Util(c.util))]
            if c.ermuedung:
                kv.append(("Schädigung (Ermüdung)", Util(c.D)))
            kv.append(("Status", "Nachweis erfüllt" if c.eta <= 1.0
                       else "Nachweis NICHT erfüllt"))
            b.append(("kv", kv, f"Anschluss {c.name}"))

            g = c.gelenk
            if g is not None and (g.S_j_ini or g.klasse):
                kv2 = [("Anfangssteifigkeit S_j,ini", _steifigkeit_text(g) + " MNm/rad")]
                if g.z_eq:
                    kv2.append(("Hebelarm der Ersatzfeder z_eq",
                                f"{g.z_eq * 1e3:.0f} mm"))
                if math.isfinite(g.S_j) and g.S_j > 0:
                    kv2.append((f"Rechenwert S_j = S_j,ini/η (η = {fmt(g.eta, 1)})",
                                f"{g.S_j / 1e6:.1f} MNm/rad"))
                if g.grenze_starr:
                    kv2.append(("Grenzen der Klassifizierung (5.2.2.5)",
                                f"starr ab {g.grenze_starr / 1e6:.1f}, gelenkig bis "
                                f"{g.grenze_gelenkig / 1e6:.2f} MNm/rad"))
                kv2 += [("Klassifizierung Steifigkeit",
                         f"{g.klasse}" + (f" – {g.klasse_grund}" if g.klasse_grund else "")),
                        ("Klassifizierung Tragfähigkeit (5.2.3)", g.tragklasse or "–"),
                        ("Momententragfähigkeit M_j,Rd",
                         f"{g.M_j_Rd / 1e3:.1f} kNm" if g.M_j_Rd else "–"),
                        ("Rotationsvermögen (6.4.2)",
                         ("ausreichend – " if g.rotation_ok else "nicht nachgewiesen – ")
                         + g.rotation_grund),
                        ("in der Berechnung", c.modelliert or "–")]
                if g.phi_Cd:
                    kv2.append(("Verdrehung bei M_j,Rd (elastisch, mit S_j)",
                                f"{g.phi_Cd * 1e3:.2f} mrad"))
                b.append(("kv", kv2, f"Momenten-Rotations-Verhalten {c.name}"))
                if g.komponenten:
                    rows = [["Komponente", "k_i [mm]", "Bedeutung"]]
                    for kenn, kw, txt in g.komponenten:
                        rows.append([kenn, fmt(kw * 1e3, 3) if math.isfinite(kw) else "∞",
                                     _pretty(txt)])
                    b.append(("table", rows, "Steifigkeitsbeiwerte nach Tab. 6.11 "
                                             "(je Schraubenreihe, dann Druckzone)",
                              None, ""))
                if g.reihen:
                    rows = [["Reihe", "Hebelarm h_r [mm]", "k_eff,r [mm]",
                             "F_tr,Rd [kN]", "maßgebend"]]
                    for i, r in enumerate(g.reihen, 1):
                        rows.append([f"{i}", fmt(r.h * 1e3, 0),
                                     fmt(r.k_eff * 1e3, 3) if math.isfinite(r.k_eff) else "∞",
                                     fmt(r.F_Rd / 1e3, 1), _pretty(r.versagen)])
                    b.append(("table", rows, "Schraubenreihen der Zugzone (6.2.7, 6.3.3)",
                              None, ""))

            rows = [["Nachweis", "E_d", "R_d", "Einheit", "Ausnutzung", "Bemerkung"]]
            from ..joints.design import Check as _JCheck
            for ch in c.checks:
                f = _JCheck.FAKTOR.get(ch["einheit"], 1.0)
                einheit = "N/mm²" if ch["einheit"] == "N/mm^2" else ch["einheit"]
                rows.append([_pretty(ch["name"]), fmt(ch["E"] * f, 1), fmt(ch["R"] * f, 1),
                             einheit, Util(ch["eta"]), _pretty(ch["hinweis"])])
            b.append(("table", rows, f"Einzelnachweise {c.name} "
                                     f"(Kombination {c.kombination})", None, ""))

            if len(c.je_kombination) > 1:
                zeilen = sorted(c.je_kombination, key=lambda d: -d["eta"])
                rows = [["Kombination", "N [kN]", "V_z [kN]", "M_y [kNm]", "Ausnutzung",
                         "maßgebender Nachweis"]]
                for d in zeilen:
                    rows.append([d["kombination"], fmt(d.get("N", 0.0) / 1e3, 1),
                                 fmt(d.get("Vz", 0.0) / 1e3, 1),
                                 fmt(d.get("My", 0.0) / 1e3, 1),
                                 Util(d["eta"]), _pretty(d["massgebend"])])
                rows, note = self._truncate(rows, self.opt("max_detail_combinations") or 12)
                b.append(("table", rows, "Ausnutzung je Kombination (absteigend geordnet)",
                          None, ""))
                if note:
                    b.append(("note", note))

            if c.ermuedung:
                rows = [["Kerbfall Δσ_C [MPa]", "Steigung m", "γ_Mf", "Δσ [MPa]", "n",
                         "N_R", "n / N_R", "Ermüdungslast", "Kerbfallbeschreibung"]]
                for e2 in c.ermuedung:
                    for (ds, n), NR in zip(e2["stufen"], e2["N_R"]):
                        rows.append([f"{e2['kerbfall']:.0f}", f"{e2['steigung']}",
                                     fmt(e2["gamma_Mf"], 2), fmt(ds / 1e6, 1), f"{n:.3g}",
                                     f"{NR:.3g}" if np.isfinite(NR) else "∞",
                                     fmt(n / NR, 4) if np.isfinite(NR) and NR > 0 else "0",
                                     ", ".join(e2["lasten"]), _pretty(e2["beschreibung"])])
                    rows.append([f"Summe D (Kerbfall {e2['kerbfall']:.0f})", "", "", "",
                                 "", "", Util(e2["schaedigung"]), "",
                                 "Palmgren-Miner über alle Ermüdungslasten"])
                b.append(("table", rows, f"Ermüdungsnachweis {c.name} "
                                         "(Palmgren-Miner über alle Ermüdungslasten)",
                          None, ""))
            if c.hinweise:
                b.append(("list", [f"Hinweis: {_pretty(h)}" for h in c.hinweise]))

        nf = [c.name for c in j.joints.values() if c.eta > 1.0]
        if nf:
            self._warnings.append("Anschlussnachweis NICHT erfüllt für: " + ", ".join(nf))
        return b

    # ============================================================ Kapitel 8
    def chapter_gzg(self) -> list:
        """Verformungsnachweise im Grenzzustand der Gebrauchstauglichkeit."""
        m = self.model
        b = [self._h(1, "Verformungsnachweise (Grenzzustand der Gebrauchstauglichkeit)")]
        g = self.gzg if self.opt("gzg") else None
        if g is None or not getattr(g, "checks", None):
            if not self.opt("gzg"):
                b.append(("p", "Die Ausgabe der Verformungsnachweise ist deaktiviert."))
            elif not m.verformungsgrenzen:
                b.append(("p", "Es sind keine Verformungsgrenzen festgelegt. Die "
                               "Gebrauchstauglichkeit ist gesondert nachzuweisen."))
            else:
                b.append(("p", "Es wurden keine Verformungsnachweise geführt "
                               "(keine Ergebnisse der GZG-Kombinationen)."))
            return b
        from ..gzg import SITUATIONEN
        b.append(self._h(2, "Grundlagen"))
        b.append(("list", [
            "Nachgewiesen wird gegen die Kombinationen des Grenzzustands der "
            "Gebrauchstauglichkeit nach DIN EN 1990, 6.5.3 – charakteristisch (6.14b), "
            "häufig (6.15b) und quasi-ständig (6.16b); die ungünstigste ist maßgebend.",
            "Durchbiegung eines Stabes: w bezogen auf die **Sehne** zwischen den "
            "Stabenden. Sie wird aus der Momentenlinie gewonnen (w″ = M/EI, zweifach "
            "integriert, danach die Gerade durch die Stabenden abgezogen) und ist "
            "dadurch auch bei nur einem Element je Stab exakt.",
            "Knoten: Verschiebung oder Verdrehung gegenüber der Ausgangslage "
            "(Kragarmspitze, Stützenkopf). Punktpaar: Verschiebung zweier Knoten "
            "gegeneinander – für Dichtungen, Führungen, Fugen und Anschläge "
            "(DIN 19704-1).",
            "Eine Überhöhung w_c wird von der Durchbiegung abgezogen "
            "(DIN EN 1993-1-1, A.1.4.2: w = w_max − w_c).",
            f"Grundlage sind {len(g.kombinationen)} GZG-Kombinationen.",
        ]))
        b.append(self._h(2, "Übersicht"))
        rows = [["Nachweis", "Bezug", "Größe", "Situation", "Wert", "Grenzwert",
                 "Ausnutzung", "Kombination", "Stelle", "Status"]]
        for c in g.checks.values():
            rows.append([c.name, c.bezug, c.groesse,
                         SITUATIONEN.get(c.situation, c.situation or "alle GZG"),
                         c.werttext(), _pretty(c.grenztext), Util(c.util),
                         c.kombination, c.stelle,
                         "erfüllt" if c.util <= 1.0 and not c.fehler
                         else ("nicht geführt" if c.fehler else "NICHT erfüllt")])
        b.append(("table", rows, "Verformungsnachweise: Grenzwerte und Ausnutzung",
                  None, ""))
        if self.opt("figures"):
            liste = [c for c in g.checks.values() if not c.fehler][:60]
            if liste:
                b.append(self._figure(
                    sv.draw_bar_chart([c.name for c in liste], [c.util for c in liste],
                                      620, None, 1.0, "Ausnutzung je Verformungsnachweis"),
                    "Ausnutzungsgrade der Verformungsnachweise (Grenze 1.0)"))

        b.append(self._h(2, "Nachweise im Einzelnen"))
        for c in g.checks.values():
            b.append(self._h(3, f"Verformung {c.name}"))
            if c.fehler:
                b.append(("p", f"Der Nachweis konnte nicht geführt werden: {c.fehler}"))
                self._warnings.append(f"Verformung {c.name}: {c.fehler}")
                continue
            grenze = m.verformungsgrenzen.get(c.name)
            kv = [("Bezug", c.bezug),
                  ("Verformungsgröße", c.groesse),
                  ("Bemessungssituation",
                   SITUATIONEN.get(c.situation, c.situation or "alle GZG-Kombinationen")),
                  ("Grenzwert", _pretty(c.grenztext))]
            if c.ueberhoehung:
                kv.append(("Überhöhung w_c", f"{c.ueberhoehung * 1e3:.1f} mm"))
            kv += [("größter Wert", c.werttext()),
                   ("maßgebende Kombination", c.kombination),
                   ("Stelle", c.stelle),
                   ("Ausnutzung", Util(c.util)),
                   ("Status", "Nachweis erfüllt" if c.util <= 1.0
                    else "Nachweis NICHT erfüllt")]
            if grenze is not None and grenze.beschreibung:
                kv.insert(0, ("Beschreibung", grenze.beschreibung))
            b.append(("kv", kv, f"Verformungsnachweis {c.name}"))
            if len(c.je_kombination) > 1:
                zeilen = sorted(c.je_kombination, key=lambda d: -d["util"])
                rows = [["Kombination", "Wert", "Ausnutzung", "Stelle"]]
                f = 1e3
                for d in zeilen:
                    rows.append([d["kombination"], f"{d['wert'] * f:.2f} "
                                 + ("mrad" if c.winkel else "mm"),
                                 Util(d["util"]), d["stelle"]])
                rows, note = self._truncate(rows, self.opt("max_detail_combinations") or 12)
                b.append(("table", rows, "Verformung je Kombination (absteigend geordnet)",
                          None, ""))
                if note:
                    b.append(("note", note))
            if c.hinweise:
                b.append(("list", [f"Hinweis: {h}" for h in c.hinweise]))
        nf = [c.name for c in g.checks.values() if c.util > 1.0]
        if nf:
            self._warnings.append("Verformungsnachweis NICHT erfüllt für: " + ", ".join(nf))
        return b

    # ============================================================ Kapitel 9
    def chapter_summary(self) -> list:
        m = self.model
        b = [self._h(1, "Zusammenfassung")]
        kv = [("Modell", f"{m.name}: {m.nn} Knoten, {len(m.elements)} Elemente, "
                         f"{len(m.members)} Stäbe"),
              ("Lastfälle / Kombinationen", f"{len(self.cases)} / {len(self.combos)}")]
        # Verschiebungen
        best = None
        for key in ("SLS_CH", "SLS_FR", "SLS_QP", "ULS", "CASES"):
            env = self.envelopes.get(key)
            if env is not None and env.u_max.size:
                um = env.umag_max
                i = int(np.argmax(um))
                best = (key, float(um[i]), i)
                break
        if best is not None:
            kv.append((f"max. Verschiebung ({ENVELOPE_NAMES.get(best[0], best[0])})",
                       f"{best[1] * 1e3:.3f} mm am Knoten {best[2]}"))
        else:
            gname, gres = self._governing_result()
            if gres is not None:
                um = np.linalg.norm(gres.u[:, :3], axis=1)
                i = int(np.nanargmax(um))
                kv.append((f"max. Verschiebung ({gname})", f"{um[i] * 1e3:.3f} mm am Knoten {i}"))
        env = self.envelopes.get("ULS")
        if env is not None and getattr(env, "node_vm_max", None) is not None \
                and np.any(env.node_vm_max):
            kv.append(("max. Vergleichsspannung (GZT)",
                       f"{np.nanmax(env.node_vm_max) / 1e6:.1f} N/mm²"))
        d = self.design
        status_ok = True
        if d is not None and getattr(d, "members", None):
            worst = max(d.members.values(), key=lambda mc: mc.util)
            g = worst.governing
            kv.append(("max. Ausnutzung Nachweise EC3", Util(worst.util)))
            kv.append(("maßgebend", f"Stab {worst.member}: {g.get('name', '')}, Kombination "
                                    f"{g.get('combo', '')}, x = {fmt(g.get('x', 0.0), 2)} m"))
            nf = [mc.member for mc in d.members.values() if mc.util > 1.0]
            if nf:
                status_ok = False
        f = self.fatigue
        if f is not None and getattr(f, "members", None):
            worst = max(f.members.values(), key=lambda fm: fm.util)
            kv.append(("max. Schädigung Ermüdung", Util(worst.util)))
            kv.append(("maßgebend (Ermüdung)", f"Stab {worst.member}, Kerbfall "
                                               f"{worst.category / 1e6:.0f}: {_pretty(worst.governing)}"))
            if any(fm.util > 1.0 for fm in f.members.values()):
                status_ok = False
        bl = self.beulen
        if bl is not None and getattr(bl, "felder", None):
            worst = max(bl.felder.values(), key=lambda c: c.util)
            kv.append(("max. Ausnutzung Beulen (EN 1993-1-5)", Util(worst.util)))
            kv.append(("maßgebend (Beulen)",
                       f"{worst.name}: λ̄_p = {fmt((worst.werte or {}).get('lambda_p', 0), 3)}, "
                       f"{worst.kombination}"))
            if any(c.util > 1.0 or c.fehler for c in bl.felder.values()):
                status_ok = False
        li = self.lasteinleitung
        if li is not None and getattr(li, "stellen", None):
            worst = max(li.stellen.values(), key=lambda c: c.util)
            kv.append(("max. Ausnutzung Lasteinleitung", Util(worst.util)))
            if any(c.util > 1.0 or c.fehler for c in li.stellen.values()):
                status_ok = False
        gz = self.gzg
        if gz is not None and getattr(gz, "checks", None):
            worst = max(gz.checks.values(), key=lambda c: c.util)
            kv.append(("max. Ausnutzung Verformung (GZG)", Util(worst.util)))
            kv.append(("maßgebend (Verformung)",
                       f"{worst.name} ({worst.bezug}): {worst.werttext()} von "
                       f"{worst.grenztext}, {worst.kombination}"))
            if any(c.util > 1.0 or c.fehler for c in gz.checks.values()):
                status_ok = False
        aj = self.joints
        if aj is not None and getattr(aj, "joints", None):
            worst = max(aj.joints.values(), key=lambda c: c.eta)
            kv.append(("max. Ausnutzung Anschlüsse", Util(worst.eta)))
            kv.append(("maßgebend (Anschluss)",
                       f"{worst.name} ({worst.ort}): "
                       + (f"Ermüdung, D = {fmt(worst.D, 3)}" if worst.D > worst.util
                          else f"{_pretty(worst.massgebend)}, Kombination {worst.kombination}")))
            if any(c.eta > 1.0 or c.fehler for c in aj.joints.values()):
                status_ok = False
        b.append(("kv", kv, "Wesentliche Ergebnisse"))
        gefuehrt = ((d is not None and getattr(d, "members", None))
                    or (f is not None and getattr(f, "members", None))
                    or (aj is not None and getattr(aj, "joints", None))
                    or (gz is not None and getattr(gz, "checks", None))
                    or (bl is not None and getattr(bl, "felder", None))
                    or (li is not None and getattr(li, "stellen", None)))
        if gefuehrt:
            if status_ok:
                b.append(("status", "Alle Nachweise erfüllt.", True))
            else:
                b.append(("status", "Nachweise NICHT erfüllt – siehe die Nachweiskapitel.",
                          False))
        else:
            b.append(("status", "Es wurden keine Nachweise geführt; die Ergebnisse dienen der "
                                "Schnittgrößen- und Verformungsermittlung.", True))
        warn = list(dict.fromkeys(self._warnings))
        try:
            chk = [s for s in m.check() if s.startswith("FEHLER") or s.startswith("WARNUNG")]
        except Exception:
            chk = []
        warn += [f"Modellprüfung: {s}" for s in chk]
        if warn:
            b.append(("p", "Offene Hinweise und Warnungen:"))
            b.append(("list", warn))
        else:
            b.append(("p", "Es liegen keine offenen Hinweise oder Warnungen vor."))
        return b

    # ============================================================ Anhang
    def chapter_appendix(self) -> list:
        m = self.model
        b = [self._h(1, "Anhang", appendix=True)]
        b.append(self._h(2, "Modellprüfung"))
        try:
            msgs = m.check()
        except Exception as ex:      # Modellpruefung darf den Bericht nicht verhindern
            msgs = [f"FEHLER: Modellprüfung nicht möglich ({ex})"]
        if msgs:
            b.append(("list", msgs))
        else:
            b.append(("p", "Die Modellprüfung ergab keine Beanstandungen (Knoten, Elemente, "
                           "Materialien, Querschnitte, Lager, Lasten, Kombinationen, "
                           "Stäbe und Kontaktdefinitionen sind konsistent)."))
        b.append(self._h(2, "Rechenlauf und Parallelisierung"))
        info = self.info or {}
        kv = [("Programm", f"Statik3D {__version__}")]
        if info.get("time") is not None:
            kv.append(("Gesamtrechenzeit", f"{float(info['time']):.3f} s"))
        if info.get("parallel"):
            kv.append(("Parallelisierung", str(info["parallel"])))
        if info.get("solver"):
            kv.append(("Gleichungslöser", str(info["solver"])))
        if info.get("ndof") is not None:
            kv.append(("Freiheitsgrade gesamt / aktiv",
                       f"{info.get('ndof')} / {info.get('nfree', '–')}"))
        b.append(("kv", kv, "Rechenlauf"))
        rows = [["Ergebnis", "Art", "Rechenzeit [s]", "Löser", "Kontakt-Iterationen"]]
        for name, res in self.all_results():
            inf = res.info if isinstance(res.info, dict) else {}
            rows.append([name, "Überlagerung" if inf.get("superposition") else
                         {"case": "Lastfall", "combination": "Kombination"}.get(
                             getattr(res, "kind", ""), getattr(res, "kind", "")),
                         fmt(inf.get("time", 0.0), 3) if inf.get("time") is not None else "–",
                         str(inf.get("solver", "–")),
                         str(inf.get("contact_iterations", "–"))])
        rows, note = self._truncate(rows)
        b.append(("table", rows, "Rechenzeiten je Ergebnis", None, "compact"))
        if note:
            b.append(("note", note))
        return b

    # ============================================================ Rendering
    def _header_pairs(self) -> list:
        meta = self.model.meta or {}
        date = self.opt("date") or meta.get("datum") or \
            datetime.date.today().strftime("%d.%m.%Y")
        pos = " / ".join(x for x in (meta.get("bauteil", ""), meta.get("position", "")) if x)
        return [("Projekt", meta.get("projekt", "") or "–"),
                ("Bauteil / Position", pos or "–"),
                ("Auftraggeber", meta.get("auftraggeber", "") or "–"),
                ("Bearbeiter", meta.get("bearbeiter", "") or "–"),
                ("Datum", date),
                ("Programm", f"Statik3D, Version {__version__}"),
                ("Modell", self.model.name)]

    def _render_block_html(self, blk) -> str:
        kind = blk[0]
        if kind == "h":
            _, level, number, title, anchor = blk
            tag = f"h{min(level + 1, 5)}"
            cls = ' class="chapter"' if level == 1 else ""
            return f'<{tag} id="{anchor}"{cls}>{esc(number)}&nbsp;&nbsp;{esc(title)}</{tag}>'
        if kind == "p":
            return f"<p>{esc(blk[1])}</p>"
        if kind == "note":
            return f'<p class="note">{esc(blk[1])}</p>'
        if kind == "list":
            return "<ul>" + "".join(f"<li>{esc(x)}</li>" for x in blk[1]) + "</ul>"
        if kind == "table":
            _, rows, caption, align, cls = blk
            cap = f'<div class="caption">{esc(caption)}</div>' if caption else ""
            return f'<div class="tbl">{cap}{table(rows, True, align, cls)}</div>'
        if kind == "kv":
            _, pairs, caption = blk
            cap = f'<div class="caption">{esc(caption)}</div>' if caption else ""
            rows = []
            for k, v in pairs:
                if isinstance(v, Util):
                    vv = (f'<span class="util {"ok" if v.ok else "nok"}">'
                          f'{esc(fmt(v.value, v.digits))}</span>')
                elif isinstance(v, Raw):
                    vv = str(v)
                else:
                    vv = esc(_cell_text(v))
                rows.append(f"<tr><th>{esc(k)}</th><td>{vv}</td></tr>")
            return f'<div class="tbl">{cap}<table class="kv"><tbody>{"".join(rows)}</tbody></table></div>'
        if kind == "figure":
            _, svg_text, caption = blk
            return (f"<figure>{svg_text}"
                    + (f"<figcaption>{esc(caption)}</figcaption>" if caption else "")
                    + "</figure>")
        if kind == "status":
            _, txt, ok = blk
            return f'<div class="status {"ok" if ok else "nok"}">{esc(txt)}</div>'
        return ""

    def render_html_blocks(self, blocks) -> str:
        return "\n".join(self._render_block_html(b) for b in blocks)

    def chapter_html(self, name: str) -> str:
        """HTML eines einzelnen Kapitels ('general', 'system', 'actions', 'results',
        'design', 'fatigue', 'summary', 'appendix')."""
        self.blocks()
        fn = getattr(self, f"chapter_{name}")
        saved = (self._toc, list(self._num), self._appendix, list(self._warnings))
        try:
            return self.render_html_blocks(fn())
        finally:
            self._toc, num, self._appendix, self._warnings = saved
            self._num = num

    def html(self) -> str:
        """Vollstaendiges HTML5-Dokument (UTF-8, druckfaehig A4)."""
        blocks = self.blocks()
        body = self.render_html_blocks(blocks)
        meta = self._header_pairs()
        title = f"Statischer Bericht – {self.model.name}"
        proj = dict(meta).get("Projekt", "")
        head_rows = "".join(f"<tr><th>{esc(k)}</th><td>{esc(v)}</td></tr>" for k, v in meta)
        toc = []
        for level, number, t, anchor in self._toc:
            if level <= 2:
                toc.append(f'<li class="l{level}"><a href="#{anchor}">'
                           f'<span class="no">{esc(number)}</span> {esc(t)}</a></li>')
        return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="Statik3D {esc(__version__)}">
<title>{esc(title)}</title>
<style>
{CSS}
</style>
</head>
<body>
<div class="titlepage">
<div class="brand">Statik3D – Tragwerksberechnung</div>
<h1 class="doctitle">Statischer Bericht</h1>
<div class="subtitle">{esc(self.model.name)}{(" – " + esc(proj)) if proj and proj != "–" else ""}</div>
<table class="kv meta"><tbody>{head_rows}</tbody></table>
<div class="note">Prüffähige Dokumentation der Eingaben, Ergebnisse und Nachweise. Alle Werte in
kN, kNm, mm und N/mm², sofern nicht anders angegeben. Dieses Dokument lässt sich im Browser mit
Strg+P als PDF speichern.</div>
</div>
<nav class="toc">
<h2>Inhalt</h2>
<ul>
{chr(10).join(toc)}
</ul>
</nav>
{body}
<div class="footer">Statik3D {esc(__version__)} – {esc(title)}</div>
</body>
</html>
"""

    def to_html(self, path: str) -> str:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(self.html())
        return path

    def to_pdf(self, path: str) -> str:
        from .pdf import to_pdf
        return to_pdf(self, path)

    # ---- Markdown -----------------------------------------------------------
    def to_markdown(self) -> str:
        """Einfache Markdown-Fassung (Tabellen als Pipe-Tabellen, ohne Abbildungen)."""
        blocks = self.blocks()
        out = [f"# Statischer Bericht – {self.model.name}", ""]
        for k, v in self._header_pairs():
            out.append(f"- **{k}:** {v}")
        out.append("")
        for blk in blocks:
            kind = blk[0]
            if kind == "h":
                _, level, number, title, _a = blk
                out.append("")
                out.append("#" * min(level + 1, 6) + f" {number} {title}")
                out.append("")
            elif kind == "p":
                out.append(blk[1])
                out.append("")
            elif kind == "note":
                out.append(f"*{blk[1]}*")
                out.append("")
            elif kind == "list":
                out.extend(f"- {x}" for x in blk[1])
                out.append("")
            elif kind == "table":
                _, rows, caption, _al, _cls = blk
                if caption:
                    out.append(f"**{caption}**")
                    out.append("")
                out.append(_md_table(rows, True))
                out.append("")
            elif kind == "kv":
                _, pairs, caption = blk
                if caption:
                    out.append(f"**{caption}**")
                    out.append("")
                out.append(_md_table([["", ""]] + [[k, _cell_text(v)] for k, v in pairs], True))
                out.append("")
            elif kind == "figure":
                out.append(f"*[Abbildung: {blk[2]}]*")
                out.append("")
            elif kind == "status":
                out.append(f"> **{blk[1]}**")
                out.append("")
        return "\n".join(out)


# ==========================================================================
CSS = """
@page { size: A4; margin: 18mm 16mm 20mm 20mm; }
html { color-scheme: light; }
body { font-family: Helvetica, Arial, sans-serif; font-size: 10.5pt; color: #111; background: #fff;
       max-width: 190mm; margin: 0 auto; padding: 10mm 6mm; line-height: 1.35; }
h1, h2, h3, h4, h5 { color: #1f3b73; page-break-after: avoid; break-after: avoid; }
h1.doctitle { font-size: 26pt; margin: 6mm 0 2mm; border: none; }
h1.chapter, h2.chapter { font-size: 16pt; margin-top: 2em; padding-bottom: 2px;
             border-bottom: 2px solid #1f3b73; page-break-before: always; break-before: page; }
h3 { font-size: 13pt; margin: 1.4em 0 0.5em; }
h4 { font-size: 11.5pt; margin: 1.2em 0 0.4em; }
h5 { font-size: 10.5pt; margin: 1em 0 0.3em; }
p { margin: 0.4em 0 0.7em; }
ul { margin: 0.3em 0 0.8em 1.2em; padding: 0; }
li { margin: 0.15em 0; }
.brand { font-size: 10pt; color: #666; letter-spacing: 0.08em; text-transform: uppercase; }
.subtitle { font-size: 14pt; color: #333; margin-bottom: 6mm; }
.titlepage { page-break-after: always; break-after: page; }
.toc { page-break-after: always; break-after: page; }
.toc h2 { font-size: 14pt; border-bottom: 1px solid #1f3b73; }
.toc ul { list-style: none; margin: 0; padding: 0; }
.toc li.l1 { font-weight: bold; margin-top: 0.5em; }
.toc li.l2 { margin-left: 1.6em; font-weight: normal; }
.toc a { color: inherit; text-decoration: none; }
.toc .no { display: inline-block; min-width: 2.6em; }
.tbl { margin: 0.4em 0 1em; }
.caption { font-size: 9.5pt; font-weight: bold; color: #333; margin: 0.6em 0 0.2em; }
table { border-collapse: collapse; width: 100%; font-size: 9pt; page-break-inside: auto; }
table.compact { font-size: 8pt; }
thead { display: table-header-group; }
tfoot { display: table-footer-group; }
tr { page-break-inside: avoid; break-inside: avoid; }
th, td { border: 1px solid #b5b5b5; padding: 2px 5px; vertical-align: top; text-align: left; }
th { background: #e8edf5; font-weight: bold; }
td.num, th.num { text-align: right; font-family: "DejaVu Sans Mono", Consolas, "Courier New", monospace;
                 white-space: nowrap; }
td.ctr, th.ctr { text-align: center; }
table.kv th { width: 34%; background: #f3f5f9; font-weight: normal; }
table.kv td { font-family: inherit; }
table.meta { font-size: 10.5pt; }
table.meta th { width: 30%; }
.util { font-family: "DejaVu Sans Mono", Consolas, monospace; font-weight: bold; }
.util.ok { color: #1e7b34; }
.util.nok { color: #b00020; background: #fde8e8; }
figure { margin: 0.6em 0 1em; text-align: center; page-break-inside: avoid; break-inside: avoid; }
figure svg { max-width: 100%; height: auto; border: 1px solid #ddd; }
figcaption { font-size: 9pt; color: #444; margin-top: 0.3em; }
.status { padding: 0.6em 0.9em; margin: 0.8em 0; font-weight: bold; border-left: 6px solid; }
.status.ok { background: #e6f4ea; border-color: #1e7b34; color: #1e5a2a; }
.status.nok { background: #fdecea; border-color: #b00020; color: #7a0015; }
.note { font-size: 9pt; color: #555; font-style: italic; }
.footer { margin-top: 3em; font-size: 8.5pt; color: #777; border-top: 1px solid #ccc;
          padding-top: 0.4em; }
@media print {
  body { max-width: none; padding: 0; margin: 0; font-size: 10pt; }
  a { color: inherit; text-decoration: none; }
  figure svg { border: none; }
}
"""
