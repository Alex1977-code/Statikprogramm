"""Export als Nastran Bulk Data (.bdf).

Karten mit Zahlenwerten stehen im Grossfeldformat (Kartenname mit ``*``,
Felder zu 16 Zeichen), reine Nummernkarten im Kurzfeld. Bis zum 09.11.2026
standen alle Zahlen mit fuenf Stellen im Kurzfeld (Befund B4 der
Pruefagenten): Koordinaten, Steifigkeiten und Lasten kamen gerundet an.

Geschrieben werden GRID, MAT1 (E, nu, rho, alpha, f_y als ST), CBAR + PBAR
(Balken; Orientierungsvektor = lokale y-Achse, I1 = I_z, I2 = I_y, Schub-
flaechen als K1/K2, Randabstaende als Spannungspunkte, Stabendgelenke als
Pin-Flags), CROD + PROD (Fachwerkstab und Seil; bis zum 09.11.2026 gingen sie
als biegesteifer CBAR hinaus), Schalen und Volumen wie bisher, SPC1/SPC
(starre Lager, vorgegebene Verschiebung), CELAS2 (Lagerfedern), FORCE/MOMENT,
GRAV, PLOAD1 (Stablasten), PLOAD4 (Flaechenlasten) und LOAD (Kombinationen).

Was die Datei nicht traegt, steht nach dem Export als Hinweis mit Anzahl im
Protokoll (:func:`_common.nicht_uebertragen`).
"""
from __future__ import annotations

import numpy as np

from ..model import Model
from ..elements.beam3d import local_axes
from ..elements import solid as _sl
from . import _common as C

#: Volumentypen, deren Flaechenlast als PLOAD4 mit G1 und G3/G4 hinausgeht
#: (der eigene Import bestimmt die Seite nur bei diesen)
_PLOAD4_VOLUMEN = ("tet4", "tet10", "hex8")


def _i(v) -> str:
    return f"{int(v):8d}"[:8]


def _real(v) -> str:
    """Zahl mit so vielen Stellen, wie in ein 16 Zeichen breites Feld passen,
    immer mit Dezimalpunkt; der Exponent in der Nastran-Kurzform ohne „E“
    (1.25-5)."""
    v = float(v)
    if v == 0.0:
        return "0.0"
    for p in (None,) + tuple(range(17, 0, -1)):
        s = repr(v) if p is None else f"{v:.{p}g}"
        if "e" in s or "E" in s:
            m, ex = s.lower().split("e")
            if "." not in m:
                m += ".0"
            s = m + ("+" if int(ex) >= 0 else "-") + str(abs(int(ex)))
        elif "." not in s:
            s += ".0"
        if len(s) <= 16:
            return s
    return f"{v:.8E}"


def _feld(v) -> str:
    if v is None or v == "":
        return " " * 16
    if isinstance(v, (bool, int, np.integer)):
        return f"{int(v):16d}"
    if isinstance(v, str):
        return v.ljust(16)[:16]
    return _real(v).rjust(16)


def _gross(name: str, felder: list) -> list[str]:
    """Karte im Grossfeldformat: je Zeile vier Felder zu 16 Zeichen; jede
    Kurzfeldzeile (acht Felder) wird zu zwei Zeilen."""
    f = list(felder)
    while f and (f[-1] is None or f[-1] == ""):
        f.pop()
    f += [None] * (-len(f) % 8)
    zeilen = []
    for k in range(0, len(f), 4):
        kopf = (name + "*").ljust(8) if k == 0 else "*".ljust(8)
        zeilen.append((kopf + "".join(_feld(x) for x in f[k:k + 4])).rstrip())
    return zeilen


def _pinflag(e, ende: int) -> str:
    return "".join(str(int(d) % 6 + 1) for d in sorted(set(int(d) for d in (e.hinges or [])))
                   if int(d) // 6 == ende)


def write_bdf(model: Model, path: str, results=None, log: list = None, **_) -> str:
    faelle = list(model.load_cases)
    sid_von = {name: k for k, name in enumerate(faelle, 1)}
    bulk: list[str] = []

    # ---- Knoten ------------------------------------------------------------
    for i, p in enumerate(model.nodes, 1):
        bulk += _gross("GRID", [i, None, float(p[0]), float(p[1]), float(p[2])])

    # ---- Werkstoffe ---------------------------------------------------------
    mat_id = {n: i for i, n in enumerate(model.materials, 1)}
    for name, m in model.materials.items():
        bulk.append(f"$ Werkstoff {mat_id[name]}: {name}")
        fy = getattr(m, "fy", None)
        bulk += _gross("MAT1", [mat_id[name], float(m.E), None, float(m.nu), float(m.rho),
                                float(m.alpha), None, None, float(fy) if fy else None])

    # ---- Elemente und Eigenschaften ----------------------------------------
    prop_id: dict[tuple, int] = {}
    eigenschaften: list[str] = []
    karten: list[str] = []
    eid_von: dict[int, int] = {}
    n_ohne_qs = n_ohne_dicke = n_seil = n_fachwerk = 0
    # Tetraeder mit Ordnung p und Elemente ohne Karte (Befund 17, 11.11.2026:
    # beide fielen bis dahin mit „else: continue“ ohne ein Wort weg)
    tetp_linear: list[int] = []
    ohne_karte: list[int] = []

    def pid(key) -> tuple[int, bool]:
        neu = key not in prop_id
        if neu:
            prop_id[key] = len(prop_id) + 1
        return prop_id[key], neu

    eid = 0
    for idx, e in enumerate(model.elements):
        n = [int(x) + 1 for x in e.nodes]
        mid = mat_id.get(e.mat, 1)
        if e.typ == "beam":
            eid += 1
            s = model.sections.get(e.sec)
            p, neu = pid(("bar", e.sec, e.mat))
            if neu:
                if s is None:
                    n_ohne_qs += 1
                A = float(s.A) if s else 1e-3
                eigenschaften.append(f"$ Querschnitt {p}: {e.sec}")
                felder = [p, mid, A, float(s.Iz) if s else 1e-6, float(s.Iy) if s else 1e-6,
                          float(s.It) if s else 1e-6, None, None]
                ym = float(getattr(s, "ymax", 0.0) or 0.0) if s else 0.0
                zm = float(getattr(s, "zmax", 0.0) or 0.0) if s else 0.0
                if ym or zm:
                    felder += [ym, zm, -ym, zm, -ym, -zm, ym, -zm]
                else:
                    felder += [None] * 8
                k1 = float(s.Asy) / A if s and s.Asy and A else None
                k2 = float(s.Asz) / A if s and s.Asz and A else None
                felder += [k1, k2]
                eigenschaften += _gross("PBAR", felder)
            T3, _L = local_axes(model.nodes[int(e.nodes[0])], model.nodes[int(e.nodes[1])],
                                float(e.roll or 0.0))
            ey = [float(v) if abs(v) > 1e-15 else 0.0 for v in T3[1]]
            felder = [eid, p, n[0], n[1], ey[0], ey[1], ey[2], None]
            pa, pb = _pinflag(e, 0), _pinflag(e, 1)
            if pa or pb:
                felder += [int(pa) if pa else None, int(pb) if pb else None]
            karten += _gross("CBAR", felder)
        elif e.typ in ("truss", "seil"):
            eid += 1
            n_seil += e.typ == "seil"
            n_fachwerk += 1
            s = model.sections.get(e.sec)
            p, neu = pid(("rod", e.sec, e.mat))
            if neu:
                if s is None:
                    n_ohne_qs += 1
                eigenschaften.append(f"$ Querschnitt {p}: {e.sec}")
                eigenschaften += _gross("PROD", [p, mid, float(s.A) if s else 1e-3,
                                                 float(s.It) if s else 1e-6])
            karten.append("CROD    " + _i(eid) + _i(p) + _i(n[0]) + _i(n[1]))
        elif e.typ.startswith("shell") and e.typ in ("shell3", "shell4", "shell6", "shell8"):
            eid += 1
            t = model.shells.get(e.sec)
            p, neu = pid(("shell", e.sec, e.mat))
            if neu:
                if t is None:
                    n_ohne_dicke += 1
                eigenschaften += _gross("PSHELL", [p, mid, float(t.t) if t else 0.01])
            if e.typ == "shell3":
                karten.append("CTRIA3  " + _i(eid) + _i(p) + _i(n[0]) + _i(n[1]) + _i(n[2]))
            elif e.typ == "shell4":
                karten.append("CQUAD4  " + _i(eid) + _i(p) + _i(n[0]) + _i(n[1])
                              + _i(n[2]) + _i(n[3]))
            else:
                karte = "CTRIA6  " if e.typ == "shell6" else "CQUAD8  "
                karten.append(karte + _i(eid) + _i(p) + "".join(_i(x) for x in n[:6]))
                if e.typ == "shell8":
                    karten.append("        " + "".join(_i(x) for x in n[6:8]))
        elif e.typ in ("tet4", "tet10", "tetp2", "tetp3", "tetp4"):
            # tetp: die vier Eckknoten als linearer CTETRA - Nastran kennt die
            # hierarchischen Ansaetze hoeherer Ordnung nicht; der Hinweis sagt es
            if e.typ.startswith("tetp"):
                tetp_linear.append(idx)
            eid += 1
            p, neu = pid(("solid", e.mat))
            if neu:
                eigenschaften.append("PSOLID  " + _i(p) + _i(mid))
            karten.append("CTETRA  " + _i(eid) + _i(p) + "".join(_i(x) for x in n[:4]))
        elif e.typ in ("hex8", "hex20", "pent6", "pent15", "pyr5"):
            eid += 1
            p, neu = pid(("solid", e.mat))
            if neu:
                eigenschaften.append("PSOLID  " + _i(p) + _i(mid))
            karte = {"hex8": "CHEXA   ", "hex20": "CHEXA   ", "pent6": "CPENTA  ",
                     "pent15": "CPENTA  ", "pyr5": "CPYRAM  "}[e.typ]
            if e.typ in ("hex20", "pent15"):
                # Kantenmitten in Nastran-Folge (senkrecht vor oben), siehe
                # importers.nastran.nastran_folge
                from ..importers.nastran import nastran_folge
                n = nastran_folge(n)
            karten.append(karte + _i(eid) + _i(p) + "".join(_i(x) for x in n[:6]))
            rest = n[6:]
            while rest:
                karten.append("        " + "".join(_i(x) for x in rest[:8]))
                rest = rest[8:]
        else:
            if not C.von_weiteres(e):
                ohne_karte.append(idx)
            continue
        eid_von[idx] = eid
    n_elemente = eid
    bulk += eigenschaften + karten

    # ---- Lager -------------------------------------------------------------
    n_feder = 0
    for s in model.supports:
        starr, werte, federn = [], [], []
        for d in range(6):
            b = s.dof_behaviour(d)
            if b.typ == "rigid":
                v = 0.0
                if s.values and d in s.dofs and s.dofs.index(d) < len(s.values):
                    v = float(s.values[s.dofs.index(d)] or 0.0)
                (werte.append((d, v)) if v else starr.append(d))
            elif b.typ == "spring" and float(b.stiffness):
                federn.append((d, float(b.stiffness)))
        if starr:
            bulk.append("SPC1    " + _i(1) + "".join(str(d + 1) for d in starr).rjust(8)
                        + _i(s.node + 1))
        for d, v in werte:
            bulk += _gross("SPC", [1, s.node + 1, d + 1, v])
        for d, k in federn:
            eid += 1
            n_feder += 1
            bulk += _gross("CELAS2", [eid, k, s.node + 1, d + 1])

    # ---- Lasten ------------------------------------------------------------
    belegt = set()
    n_stablast_rest = n_flaeche_rest = 0
    for name in faelle:
        k = sid_von[name]
        lc = model.load_cases[name]
        vor = len(bulk)
        bulk.append(f"$ Lastfall {k}: {name}")
        for nl in lc.nodal_loads:
            F = [float(v) for v in nl.F[:3]]
            if any(F):
                bulk += _gross("FORCE", [k, nl.node + 1, None, 1.0, F[0], F[1], F[2]])
            M = [float(v) for v in nl.F[3:6]]
            if any(M):
                bulk += _gross("MOMENT", [k, nl.node + 1, None, 1.0, M[0], M[1], M[2]])
        g = [float(v) for v in np.asarray(lc.gravity, float)]
        if any(g):
            bulk += _gross("GRAV", [k, None, 1.0, g[0], g[1], g[2]])
        for bl in lc.beam_loads:
            e = model.elements[int(bl.elem)] if 0 <= int(bl.elem) < len(model.elements) else None
            if e is None or e.typ != "beam" or int(bl.elem) not in eid_von:
                n_stablast_rest += 1
                continue
            q1 = [float(v) for v in bl.q]
            q2 = [float(v) for v in (bl.q2 if bl.q2 is not None else bl.q)]
            lokal = bl.system == "local"
            proj = (not lokal) and getattr(bl, "bezugslaenge", "") == "projektion"
            if bl.teilweise:
                L = float(model.element_length(int(bl.elem)))
                a = float(bl.a or 0.0)
                b = L if bl.b is None else float(bl.b)
                if proj:
                    skala, x1, x2 = "FRPR", a / L, b / L
                else:
                    skala, x1, x2 = "LE", a, b
            else:
                skala, x1, x2 = ("FRPR" if proj else "FR"), 0.0, 1.0
            for achse in range(3):
                if q1[achse] or q2[achse]:
                    typ = "F" + "XYZ"[achse] + ("E" if lokal else "")
                    bulk += _gross("PLOAD1", [k, eid_von[int(bl.elem)], typ, skala,
                                              x1, q1[achse], x2, q2[achse]])
        for fl in lc.face_loads:
            i = int(fl.elem)
            e = model.elements[i] if 0 <= i < len(model.elements) else None
            if e is None or i not in eid_von or not float(fl.p):
                n_flaeche_rest += bool(e is None or i not in eid_von)
                continue
            richtung = None
            if fl.direction is not None:
                try:
                    richtung = [float(v) for v in fl.direction][:3]
                except (TypeError, ValueError):
                    n_flaeche_rest += 1
                    continue
            p = float(fl.p)
            felder = [k, eid_von[i], p, None, None, None]
            if e.typ.startswith("shell"):
                felder += [None, None]
            elif e.typ in _PLOAD4_VOLUMEN:
                ecken = list(_sl.FLAECHEN_ECKEN[e.typ][int(fl.face)])
                kn = [int(x) for x in e.nodes]
                if e.typ == "hex8":
                    g1, g34 = kn[ecken[0]], kn[ecken[2]]
                else:
                    g1 = kn[ecken[0]]
                    g34 = kn[[c for c in range(4) if c not in ecken][0]]
                felder += [g1 + 1, g34 + 1]
            else:
                n_flaeche_rest += 1
                continue
            if richtung is not None:
                felder += [None, richtung[0], richtung[1], richtung[2]]
            bulk += _gross("PLOAD4", felder)
        if len(bulk) - vor > 1:
            belegt.add(name)
        else:
            bulk.pop()

    # ---- Kombinationen als LOAD-Karten -------------------------------------
    komb_sid: dict[str, int] = {}
    n_komb_rest = 0
    for name, c in model.combinations.items():
        faktoren = [(float(f), sid_von[lf]) for lf, f in c.factors.items()
                    if lf in sid_von and lf in belegt and float(f)]
        fremd = [lf for lf in c.factors if lf not in sid_von]
        if getattr(c, "alternativen", None) or fremd or not faktoren:
            n_komb_rest += 1
            continue
        sid = len(faelle) + len(komb_sid) + 1
        komb_sid[name] = sid
        bulk.append(f"$ Kombination {sid}: {name} ({c.typ})")
        felder = [sid, 1.0]
        for f, l in faktoren:
            felder += [f, l]
        bulk += _gross("LOAD", felder)

    # ---- Kopf --------------------------------------------------------------
    z = ["$ Statik3D-Export: " + model.name,
         "$ Einheiten m, N, kg; Karten mit Zahlenwerten im Grossfeldformat",
         "SOL 101", "CEND",
         "TITLE = " + model.name[:60], "DISP = ALL", "STRESS = ALL",
         "SPC = 1"]
    nr = 0
    for name in faelle:
        nr += 1
        z.append(f"SUBCASE {nr}")
        z.append(f"  LABEL = {name[:60]}")
        if name in belegt:
            z.append(f"  LOAD = {sid_von[name]}")
    for name, sid in komb_sid.items():
        nr += 1
        z.append(f"SUBCASE {nr}")
        z.append(f"  LABEL = {name[:60]}")
        z.append(f"  LOAD = {sid}")
    z.append("BEGIN BULK")
    z += bulk
    z.append("ENDDATA")
    with open(path, "w", encoding="ascii", errors="replace") as f:
        f.write("\n".join(z) + "\n")

    C.say(log, f"Nastran Bulk Data geschrieben: {model.nn} Knoten, {n_elemente} Elemente, "
               f"{len(model.supports)} Lager, {len(faelle)} Lastfälle, "
               f"{len(komb_sid)} Kombinationen -> {path}")
    C.say(log, "Nastran: Die Zahlen stehen im Großfeldformat mit voller Genauigkeit. "
               "Werkstoffe, Querschnitte, Lastfälle und Kombinationen tragen in der Datei "
               "Nummern; ihre Namen stehen als Kommentar und als LABEL dabei, der eigene "
               "Import nennt sie „MAT n“, „PID n“, „SID n“ und „LOAD n“.")
    if n_ohne_qs or n_ohne_dicke:
        C.warn(log, "Nastran: " + ", ".join(t for t in (
            C.anzahl(n_ohne_qs, "Stabeigenschaft", "Stabeigenschaften")
            + " ohne Querschnitt im Modell (mit A = 0,001 m² und I = 0,000001 m⁴ geschrieben)"
            if n_ohne_qs else "",
            C.anzahl(n_ohne_dicke, "Schaleneigenschaft", "Schaleneigenschaften")
            + " ohne Dicke im Modell (mit 0,01 m geschrieben)" if n_ohne_dicke else "") if t)
            + ". Bitte im Modell ergänzen.")
    n_gelenkfeder = len({(i, int(x[0]) // 6) for i, e in enumerate(model.elements)
                         for x in (getattr(e, "hinge_springs", None) or [])})
    n_lager_nl = sum(1 for s in model.supports if s.nonlinear)
    n_form = sum(1 for s in model.sections.values() if s.typ != "free" or getattr(s, "parts", None))
    n_fu = sum(1 for m in model.materials.values() if getattr(m, "fu", None))
    n_plast = sum(1 for m in model.materials.values()
                  if getattr(m, "verfestigung", None) is not None
                  or getattr(m, "Ep", None) is not None)
    kategorien = {lc.category for lc in model.load_cases.values()} - {"G"}
    C.nicht_uebertragen(log, "Nastran", [
        C.elementhinweis(model, tetp_linear, "Tetraeder mit Ordnung p", "Tetraeder mit Ordnung p",
                         "(geht als linearer Tetraeder CTETRA über die vier Eckknoten hinaus; die "
                         "Ansätze höherer Ordnung kennt die Karte nicht, er rechnet dort steifer)",
                         "(gehen als lineare Tetraeder CTETRA über die vier Eckknoten hinaus; die "
                         "Ansätze höherer Ordnung kennt die Karte nicht, sie rechnen dort steifer)"),
        C.elementhinweis(model, ohne_karte, "Element", "Elemente",
                         "ohne passende Nastran-Karte (fehlt ganz in der Datei; für ebene "
                         "Elemente kennt Nastran im Grundumfang keine Karte)",
                         "ohne passende Nastran-Karte (fehlen ganz in der Datei; für ebene "
                         "Elemente kennt Nastran im Grundumfang keine Karte)"),
        (n_seil, "Seil (geht als Fachwerkstab CROD hinaus)",
         "Seile (gehen als Fachwerkstäbe CROD hinaus)"),
        (n_gelenkfeder, "Stabende mit Gelenkfeder", "Stabenden mit Gelenkfeder"),
        (n_form, "Querschnittsform mit Maßen (es stehen Fläche, Trägheitsmomente, "
                 "Schubflächen und Randabstände in der Datei)",
         "Querschnittsformen mit Maßen (es stehen Fläche, Trägheitsmomente, "
         "Schubflächen und Randabstände in der Datei)"),
        (sum(1 for n in model.sections if not any(k[1] == n for k in prop_id
                                                  if k[0] in ("bar", "rod"))),
         "Querschnitt, den kein Stab benutzt", "Querschnitte, die kein Stab benutzt"),
        (n_fu, "Zugfestigkeit eines Werkstoffs", "Zugfestigkeiten der Werkstoffe"),
        (n_plast, "Werkstoffgesetz mit Verfestigung", "Werkstoffgesetze mit Verfestigung"),
        (n_lager_nl, "Knotenlager mit Ausfall, Schlupf, Reibung oder Grenzkraft (es geht "
                     "als beidseitig wirkendes starres oder gefedertes Lager hinaus)",
         "Knotenlager mit Ausfall, Schlupf, Reibung oder Grenzkraft (sie gehen als "
         "beidseitig wirkende starre oder gefederte Lager hinaus)"),
        (len(model.line_supports), "Linienlager", "Linienlager"),
        (len(model.surface_supports), "Flächenlager", "Flächenlager"),
        (n_stablast_rest, "Stablast auf einem Fachwerkstab oder Seil",
         "Stablasten auf Fachwerkstäben oder Seilen"),
        (n_flaeche_rest, "Flächenlast, die sich nicht als PLOAD4 schreiben lässt (Hexaeder "
                         "mit Seitenmittenknoten, Prisma, Pyramide)",
         "Flächenlasten, die sich nicht als PLOAD4 schreiben lassen (Hexaeder mit "
         "Seitenmittenknoten, Prismen, Pyramiden)"),
        (C.lastzahl(model, "temp_loads"), "Temperaturlast", "Temperaturlasten"),
        (len(kategorien) and sum(1 for lc in model.load_cases.values() if lc.category != "G"),
         "Lastfallkategorie (der eigene Import setzt „G“)",
         "Lastfallkategorien (der eigene Import setzt „G“)"),
        (len(komb_sid), "Art einer Kombination (der eigene Import setzt „USER“)",
         "Arten der Kombinationen (der eigene Import setzt „USER“)"),
        (n_komb_rest, "Ergebniskombination oder Kombination ohne Lasten in der Datei",
         "Ergebniskombinationen oder Kombinationen ohne Lasten in der Datei"),
    ] + C.weiteres(model))
    return path
