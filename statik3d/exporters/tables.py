"""
Export als Tabellen im RFEM-Aufbau (CSV je Blatt in einem Ordner).

Die Blattnamen und Spaltenueberschriften folgen dem Tabellenexport von
RFEM/RSTAB so, wie der eigene Tabellenimport (importers/rfem_tables.SPECS) sie
liest; Statik3D liest den Ordner wieder ein.

Seit dem 14.11.2026 (Befund I2 der Einheiten-Agenten) passen die Koepfe zum
Import; bis dahin kam der Rundlauf verfaelscht zurueck: das Eigengewicht stand
als Erdbeschleunigung in der Spalte des Faktors (9,81fach), Federlager als
„Feder 5e+06“ ohne Einheit (frei), „I_y“ und „F_X“ wurden nicht erkannt
(freier Querschnitt mit I_y = 1e-9, Knotenlasten 0), Stablasten hatten keine
Spalte „p1“, Flaechen keine Begrenzungslinien, jeder Querschnitt den Werkstoff 1.

Je Stabelement steht eine Zeile in „1.7 Stäbe“ (Name des Stabzugs dabei), damit
Knoten, Knotenlasten und Stablasten auf ihren Elementen bleiben. Jede Schale
steht mit eigenen Randlinien in „1.10 Flächen“. Was der Aufbau nicht traegt
(Flaechen- und Temperaturlasten, Stablasten auf einem Abschnitt oder auf die
Projektion bezogen, Linien- und Flaechenlager, Gelenke ...), nennt der Hinweis
am Ende des Exports.
"""
from __future__ import annotations

import csv
import os
import re

import numpy as np

from ..model import Model
from . import _common as C

BLAETTER = ["1.1 Knoten", "1.2 Linien", "1.3 Materialien", "1.4 Querschnitte",
            "1.7 Stäbe", "1.10 Flächen", "1.13 Knotenlager",
            "2.1 Lastfälle", "3.1 Knotenlasten", "3.2 Stablasten"]

#: Erdbeschleunigung, mit der der Tabellenimport den Faktor des Eigengewichts
#: multipliziert (importers/rfem_tables: g = 9,81 * Faktor)
G_TABELLE = 9.81

_STABTYP = {"beam": "Balken", "truss": "Fachwerkstab", "seil": "Seil"}


def _zelle_lager(b) -> str:
    """Zelle eines Freiheitsgrads in „1.13 Knotenlager“: „starr“, „frei“ oder die
    Federsteifigkeit als Zahl (Einheit im Kopf: N/m bzw. Nm/rad), dazu Ausfall,
    Schlupf [m] und Reibung so, wie der Import (rfem_native.behaviour_from_text) sie
    liest."""
    if b.typ == "free":
        return "frei"
    t = "starr" if b.typ == "rigid" else f"{float(b.stiffness):.9g}"
    if b.failure:
        t += f", Ausfall bei {b.failure.capitalize()}"
    if b.slip:
        t += f", Schlupf {float(b.slip):.9g}"
    if b.mu:
        t += f", Reibung mu = {float(b.mu):.9g}"
    return t


def _lastfall_nummern(model: Model) -> dict:
    """{Lastfallname: Nummer}: „LF<n>“ behaelt n, die uebrigen bekommen freie
    Nummern - der Import nennt jeden Lastfall LF<Nr> und ordnet Lasten ueber die
    Nummer in der Spalte „Lastfall“ zu."""
    nummern: dict[str, int] = {}
    belegt: set = set()
    for name in model.load_cases:
        m = re.fullmatch(r"LF\s*(\d+)", str(name).strip(), re.IGNORECASE)
        if m and int(m.group(1)) not in belegt:
            nummern[name] = int(m.group(1))
            belegt.add(int(m.group(1)))
    frei = 1
    for name in model.load_cases:
        if name in nummern:
            continue
        while frei in belegt:
            frei += 1
        nummern[name] = frei
        belegt.add(frei)
    return nummern


def write_tables(model: Model, path: str, results=None, log: list = None,
                 delimiter: str = ";", **_) -> str:
    ordner = path if not os.path.splitext(path)[1] else os.path.splitext(path)[0]
    os.makedirs(ordner, exist_ok=True)

    def schreibe(name, kopf, zeilen):
        p = os.path.join(ordner, f"{name}.csv")
        with open(p, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f, delimiter=delimiter)
            w.writerow(kopf)
            w.writerows(zeilen)
        return len(zeilen)

    n = schreibe("1.1 Knoten", ["Knoten Nr.", "X [m]", "Y [m]", "Z [m]"],
                 [[i + 1, f"{p[0]:.6f}", f"{p[1]:.6f}", f"{p[2]:.6f}"]
                  for i, p in enumerate(model.nodes)])

    # ---- Werkstoffe und Querschnitte --------------------------------------
    mat_nr = {name: i + 1 for i, name in enumerate(model.materials)}
    schreibe("1.3 Materialien",
             ["Material Nr.", "Name", "E [N/m2]", "G [N/m2]", "nu", "rho [kg/m3]",
              "alpha [1/K]", "f_y [N/m2]", "f_u [N/m2]"],
             [[i + 1, name, f"{m.E:.9g}", f"{m.G:.9g}", f"{m.nu:.6g}",
               f"{m.rho:.9g}", f"{m.alpha:.6g}",
               f"{m.fy:.9g}" if m.fy else "", f"{m.fu:.9g}" if m.fu else ""]
              for i, (name, m) in enumerate(model.materials.items())])
    stab_el = C.beam_elements(model)
    # Der Import gibt einem Stab den Werkstoff seines Querschnitts: je Querschnitt
    # der Werkstoff der Stabelemente, die ihn tragen
    qs_mat: dict[str, list] = {}
    for i in stab_el:
        e = model.elements[i]
        if e.sec and e.mat not in qs_mat.setdefault(e.sec, []):
            qs_mat[e.sec].append(e.mat)
    mehrdeutig = sorted(k for k, v in qs_mat.items() if len(v) > 1)
    qs_nr = {name: i + 1 for i, name in enumerate(model.sections)}
    schreibe("1.4 Querschnitte",
             ["Querschnitt Nr.", "Bezeichnung", "Material Nr.", "A [m2]", "Iy [m4]",
              "Iz [m4]", "It [m4]", "h [m]", "b [m]"],
             [[i + 1, name, mat_nr.get((qs_mat.get(name) or [None])[0], 1), f"{s.A:.9g}",
               f"{s.Iy:.9g}", f"{s.Iz:.9g}", f"{s.It:.9g}", f"{s.h:.6g}", f"{s.b:.6g}"]
              for i, (name, s) in enumerate(model.sections.items())])
    if mehrdeutig:
        C.warn(log, "Tabellen: " + "; ".join(f"Querschnitt {k} mit den Werkstoffen {', '.join(qs_mat[k])}"
                                             for k in mehrdeutig)
               + " - im RFEM-Aufbau trägt der Querschnitt den Werkstoff, beim Einlesen gilt der erste "
                 "für alle Stäbe mit diesem Querschnitt.")

    # ---- Staebe: eine Zeile je Stabelement --------------------------------
    stabname = {}
    for name, elems in C.member_chains(model):
        for i in elems:
            stabname.setdefault(int(i), name)
    stab_nr = {i: k for k, i in enumerate(stab_el, 1)}
    staebe = []
    for i in stab_el:
        e = model.elements[i]
        na, nb = int(e.nodes[0]), int(e.nodes[1])
        staebe.append([stab_nr[i], stabname.get(i, f"E{i + 1}"), _STABTYP.get(e.typ, "Balken"),
                       na + 1, nb + 1, qs_nr.get(e.sec, ""), e.mat,
                       f"{np.degrees(float(e.roll)):.6f}",
                       f"{float(model.element_length(i)):.6f}"])
    schreibe("1.7 Stäbe", ["Stab Nr.", "Name", "Stabtyp", "Knoten Nr. Anfang", "Knoten Nr. Ende",
                           "Querschnitt Nr.", "Material", "Drehung [Grad]", "Länge [m]"],
             staebe)

    # ---- Linien und Flaechen: jede Schale mit eigenen Randlinien ----------
    linien = [[i + 1, ln.typ, ",".join(str(x + 1) for x in ln.nodes)]
              for i, ln in enumerate(model.lines.values())]
    flaechen = []
    n_mitte = 0
    for i in C.shell_elements(model):
        e = model.elements[i]
        ecken = [int(x) for x in e.nodes[:3 if e.typ in ("shell3", "shell6") else 4]]
        n_mitte += int(len(e.nodes) > len(ecken))
        nummern = []
        for a, b in zip(ecken, ecken[1:] + ecken[:1]):
            linien.append([len(linien) + 1, "polyline", f"{a + 1},{b + 1}"])
            nummern.append(str(len(linien)))
        flaechen.append([len(flaechen) + 1, "Standard", ",".join(nummern),
                         f"{model.shells[e.sec].t:.9g}" if e.sec in model.shells else "",
                         mat_nr.get(e.mat, "")])
    schreibe("1.2 Linien", ["Linie Nr.", "Typ", "Knoten Nr."], linien)
    schreibe("1.10 Flächen", ["Fläche Nr.", "Typ", "Begrenzungslinien", "Dicke [m]", "Material"],
             flaechen)

    # ---- Knotenlager ------------------------------------------------------
    n_vorgabe = sum(1 for s in model.supports if any(float(v) for v in (s.values or [])))
    n_grenz = sum(1 for s in model.supports for d in range(6) if s.dof_behaviour(d).limit)
    schreibe("1.13 Knotenlager",
             ["Nr.", "Knoten", "Name", "ux [N/m]", "uy [N/m]", "uz [N/m]",
              "phix [Nm/rad]", "phiy [Nm/rad]", "phiz [Nm/rad]"],
             [[i + 1, s.node + 1, s.name or ""]
              + [_zelle_lager(s.dof_behaviour(d)) for d in range(6)]
              for i, s in enumerate(model.supports)])

    # ---- Lastfaelle: Eigengewicht als Faktor -------------------------------
    lf_nr = _lastfall_nummern(model)
    zeilen = []
    for name, lc in model.load_cases.items():
        g = np.zeros(3) if lc.gravity is None else np.asarray(lc.gravity, float).ravel()[:3]
        mit = bool(np.any(g))
        zeilen.append([lf_nr[name], lc.description or name, lc.category, "ja" if mit else "nein"]
                      + [f"{float(x) / G_TABELLE:.9g}" if mit else "" for x in g])
    schreibe("2.1 Lastfälle",
             ["Lastfall Nr.", "Bezeichnung", "Einwirkungskategorie", "Eigengewicht",
              "Faktor in Richtung X", "Faktor in Richtung Y", "Faktor in Richtung Z"], zeilen)

    # ---- Knotenlasten -----------------------------------------------------
    kl = []
    for name, lc in model.load_cases.items():
        for l in lc.nodal_loads:
            kl.append([f"LF{lf_nr[name]}", l.node + 1] + [f"{float(v):.9g}" for v in l.F])
    schreibe("3.1 Knotenlasten",
             ["Lastfall", "Knoten", "Fx [N]", "Fy [N]", "Fz [N]",
              "Mx [Nm]", "My [Nm]", "Mz [Nm]"], kl)

    # ---- Stablasten: je Richtung eine Zeile -------------------------------
    sl = []
    n_teil = n_proj = 0
    for name, lc in model.load_cases.items():
        for l in lc.beam_loads:
            if int(l.elem) not in stab_nr:
                continue
            if l.teilweise:
                n_teil += 1
                continue
            if l.system != "local" and l.bezugslaenge == "projektion":
                n_proj += 1
                continue
            q1 = [float(v) for v in l.q]
            q2 = [float(v) for v in (l.q2 if l.q2 is not None else l.q)]
            for k in range(3):
                if not (q1[k] or q2[k]):
                    continue
                richtung = "xyz"[k] if l.system == "local" else "XYZ"[k] + "G"
                trapez = abs(q1[k] - q2[k]) > 1e-12 * max(abs(q1[k]), abs(q2[k]))
                sl.append([f"LF{lf_nr[name]}", stab_nr[int(l.elem)], "Kraft",
                           "Trapez" if trapez else "Gleichförmig", richtung,
                           f"{q1[k]:.9g}", f"{q2[k]:.9g}" if trapez else ""])
    schreibe("3.2 Stablasten",
             ["Lastfall", "Stab", "Lastart", "Lastverlauf", "Lastrichtung", "p1 [N/m]", "p2 [N/m]"], sl)

    C.say(log, f"Tabellen geschrieben: {len(BLAETTER)} Blätter, {n} Knoten -> {ordner}")
    C.nicht_uebertragen(log, "Tabellen", [
        (n_teil, "Stablast auf einem Abschnitt des Stabs", "Stablasten auf einem Abschnitt des Stabs"),
        (n_proj, "Stablast auf die projizierte Länge bezogen", "Stablasten auf die projizierte Länge bezogen"),
        (C.lastzahl(model, "face_loads"), "Flächenlast", "Flächenlasten"),
        (C.lastzahl(model, "temp_loads"), "Temperaturlast", "Temperaturlasten"),
        (len(model.line_supports), "Linienlager", "Linienlager"),
        (len(model.surface_supports), "Flächenlager", "Flächenlager"),
        (n_vorgabe, "Knotenlager mit vorgegebener Verschiebung (geht als Lager ohne Verschiebung hinaus)",
         "Knotenlager mit vorgegebener Verschiebung (gehen als Lager ohne Verschiebung hinaus)"),
        (n_grenz, "Grenzkraft eines Knotenlagers", "Grenzkräfte der Knotenlager"),
        (len(C.gelenkenden(model)), "Stabende mit Gelenk", "Stabenden mit Gelenk"),
        (n_mitte, "quadratische Schale (geht über ihre Eckknoten hinaus)",
         "quadratische Schalen (gehen über ihre Eckknoten hinaus)"),
        (len(C.solid_elements(model)), "Volumenelement", "Volumenelemente"),
    ] + C.weiteres(model))
    return ordner
