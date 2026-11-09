"""
Gruppe 6 der Befundliste (Befunde B2 bis B6 der Pruefagenten, 09.11.2026):
Exporte und Importe. Leitsatz: nichts geht still verloren - was ein Format
traegt, steht in der Datei; was nicht uebertragen wird, steht nach dem Export
als Hinweis mit Anzahl im Protokoll ("<Format>: nicht übertragen: ...").

Pruefkoerper (klein, mit Handformel als zweitem Weg):
  Stabwerk   Kragarm 1,23456789 m (RHS 300x200x10, S355) mit Einhaengetraeger
             2 m (Momentengelenk am Anfang, Rollenlager am Ende) und ein
             Haenger (Fachwerkstab RD 20, 1,5 m). Lasten: P = 40 kN am
             Gelenkknoten, q = 12 kN/m auf dem Einhaengetraeger, F = 25 kN am
             Haenger; zweiter Lastfall LF2.
               u_B = -(P + q*L2/2) * (L1³/(3 E Iy) + L1/(G Asz))  = -1,4536 mm
               u_E = -F*LH/(E A)                                  = -0,5684 mm
             Ohne Gelenk, ohne Stablast, mit gerundeter Laenge oder mit dem
             Fachwerkstab als Balken kommt eine andere Zahl heraus.
  Platte     2,0 x 0,5 x 0,02 m (ν = 0, 8 x 2 shell4), starres Linienlager an
             der Kante x = 0, Spitzenlast 1 kN: u = P L³/(3 E I) = -38,1 mm
             (das Netz liegt 0,4 % darunter).
  Schwelle   Stab 4 m auf Linienlager-Feder c = 5 MN/m², Knotenlasten
             q * Einflusslaenge mit q = 10 kN/m: u = q/c = -2 mm an jedem Knoten.

B2 IFC     Knoten nur noch an einer Stelle (Rundreise und die Koordinaten von
           Hand aus der Datei gelesen: Platzierung + Punkt), Werkstoff,
           Profil, Gelenk, Fachwerkstab, Lager und Lasten kommen zurueck.
B3 SAF     Stabendgelenke, "Axial force only", Linienlager an Schalenkante und
           Stab, Werkstoff je Stab; Flaechenlager als Hinweis.
B4 Abaqus/Nastran  volle Genauigkeit (Nastran im Grossfeld), CROD bzw. T3D2,
           Gelenk, Stablast, Schubflaechen; *DLOAD auf ALL mit *ELSET;
           Linien- und Flaechenlager als Hinweis.
B5 DXF     $INSUNITS im Kopf und beim Import gelesen, Symbole auf Ebenen
           STATIK3D_*, die der Import nicht als Tragwerk liest; fehlt die
           Einheit, nennt eine Warnung die angenommene.
B6         Der Lastfall LF1 der Datei heisst nach dem Abaqus- und dem
           IFC-Import "LF1" (vorher "LF1_2").

Aufruf:  python -m tests.test_gruppe6_exporte
"""
import os
import re
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

from statik3d import solver  # noqa: E402
from statik3d.model import Model, Material, Section, ShellProp  # noqa: E402
from statik3d.exporters import export_model  # noqa: E402
from statik3d.importers import import_file  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


# --------------------------------------------------------------------------
# Pruefkoerper
# --------------------------------------------------------------------------
L1, L2, LH = 1.23456789, 2.0, 1.5
P, Q, F = 40e3, 12e3, 25e3
RHS, RD = "RHS 300x200x10", "RD 20"


def _stabwerk():
    m = Model("G6")
    m.add_material(Material.steel("S355"))
    m.add_section(Section.rhs(RHS, 0.3, 0.2, 0.01))
    m.add_section(Section.circle(RD, 0.02))
    a = m.add_node(0, 0, 0)
    b = m.add_node(L1, 0, 0)
    c = m.add_node(L1 + L2, 0, 0)
    d = m.add_node(0, 2, 0)
    e = m.add_node(0, 2, -LH)
    e1 = m.add_element("beam", [a, b], "S355", RHS)
    e2 = m.add_element("beam", [b, c], "S355", RHS, hinges=[4])
    e3 = m.add_element("truss", [d, e], "S355", RD)
    m.add_member("Kragarm", [e1])
    m.add_member("Einhaengetraeger", [e2])
    m.add_member("Haenger", [e3])
    m.fix(a, "all")
    m.fix(c, [1, 2])
    m.fix(d, "all")
    m.fix(e, [0, 1, 3, 4, 5])
    m.load_node(b, Fz=-P, case="LF1")
    m.load_beam(e2, qz=-Q, case="LF1")
    m.load_node(e, Fz=-F, case="LF1")
    m.add_load_case("LF2", "Q", activate=False)
    m.load_node(b, Fz=-2 * P, case="LF2")
    return m


def _hand_stabwerk(m):
    """Zweiter Weg: Kragarm unter P + q*L2/2 mit Schubanteil, Zugstab."""
    s, w = m.sections[RHS], m.materials["S355"]
    G = w.E / (2 * (1 + w.nu))
    ub = -(P + Q * L2 / 2) * (L1 ** 3 / (3 * w.E * s.Iy) + L1 / (G * s.Asz))
    ue = -F * LH / (w.E * m.sections[RD].A)
    return ub, ue


LP, BP, TP, PP = 2.0, 0.5, 0.02, 1000.0
LS, CS, QS = 4.0, 5e6, 10e3


def _platte_und_schwelle():
    """Platte mit starrem Linienlager an der Schalenkante, Stab auf
    Linienlager-Feder. Der Werkstoff "Platte" steht absichtlich vor S355:
    SAF schrieb an jeden Querschnitt den ersten Werkstoff des Modells."""
    m = Model("G6F")
    m.add_material(Material("Platte", E=2.1e11, nu=0.0, rho=7850.0))
    m.add_material(Material.steel("S355"))
    m.add_shell_prop(ShellProp("t20", TP))
    m.add_section(Section.rhs(RHS, 0.3, 0.2, 0.01))
    nx, ny = 8, 2
    kn = [[m.add_node(LP * i / nx, BP * j / ny, 0.0) for j in range(ny + 1)] for i in range(nx + 1)]
    for i in range(nx):
        for j in range(ny):
            m.add_element("shell4", [kn[i][j], kn[i + 1][j], kn[i + 1][j + 1], kn[i][j + 1]],
                          "Platte", "t20")
    m.add_line_support(kn[0], name="Einspannung",
                       **{d: dict(typ="rigid") for d in ("ux", "uy", "uz", "rx", "ry", "rz")})
    for j, f in enumerate((0.25, 0.5, 0.25)):
        m.load_node(kn[nx][j], Fz=-PP * f, case="LF1")
    st = [m.add_node(LS * i / 4, 3.0, 0.0) for i in range(5)]
    el = [m.add_element("beam", [st[i], st[i + 1]], "S355", RHS) for i in range(4)]
    m.add_member("Schwelle", el)
    m.fix(st[0], [0, 1, 3, 5])
    m.add_line_support(st, name="Bettung", uz=dict(typ="spring", stiffness=CS))
    for k, einfluss in zip(st, (0.5, 1.0, 1.0, 1.0, 0.5)):
        m.load_node(k, Fz=-QS * einfluss, case="LF1")
    return m, kn[nx][1], st


def _rechnen(m):
    """Verschiebungen des ersten Lastfalls (nn x 6) und sein Name."""
    an = solver.solve_all(m, workers=1, combinations=False)
    name = next(iter(an.cases))
    return np.asarray(an.cases[name].u), name


def _rundreise(m, ordner, endung):
    p = os.path.join(ordner, m.name + endung)
    log_e, log_i = [], []
    export_model(m, p, log=log_e)
    m2 = import_file(p, log=log_i)
    return m2, log_e, log_i, p


def _lesen(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def _abw(m, m2):
    """Groesste Abweichung der Knotenkoordinaten [m]; inf, wenn die Zahl nicht stimmt."""
    if m2.nn != m.nn:
        return float("inf")
    return float(np.abs(np.asarray(m2.nodes) - np.asarray(m.nodes)).max())


def _typen(m):
    return [(e.typ, sorted(int(h) for h in (e.hinges or []))) for e in m.elements]


def _lager(m):
    return sorted((int(s.node), tuple(sorted(int(d) for d in s.dofs))) for s in m.supports)


def _hinweis(log, fmt):
    """Die Zeile "<Format>: nicht übertragen: ..." des Exportprotokolls."""
    return next((z for z in log if f"{fmt}: nicht übertragen:" in z), "")


def _nah(a, b, rel):
    return abs(a - b) <= rel * abs(b)


SOLL_TYPEN = [("beam", []), ("beam", [4]), ("truss", [])]
SOLL_LAGER = [(0, (0, 1, 2, 3, 4, 5)), (2, (1, 2)), (3, (0, 1, 2, 3, 4, 5)), (4, (0, 1, 3, 4, 5))]


def _verformung(name, m, m2, rel):
    """u_B und u_E der Rundreise gegen die Handformel und gegen die Rechnung
    am Ausgangsmodell (zwei Wege zur selben Zahl)."""
    ub_h, ue_h = _hand_stabwerk(m)
    u0, _ = _rechnen(m)
    try:
        u2, _ = _rechnen(m2)
        ub, ue = float(u2[1, 2]), float(u2[4, 2])
    except Exception as ex:          # noqa: BLE001
        return check(name, False, f"Rechnung nach der Rundreise scheitert: {ex}")
    ok = (_nah(float(u0[1, 2]), ub_h, 1e-9) and _nah(float(u0[4, 2]), ue_h, 1e-9)
          and _nah(ub, ub_h, rel) and _nah(ue, ue_h, rel)
          and _nah(ub, float(u0[1, 2]), rel) and _nah(ue, float(u0[4, 2]), rel))
    return check(name, ok, f"u_B {ub * 1e3:.6f} mm, u_E {ue * 1e3:.6f} mm; Hand {ub_h * 1e3:.6f} / "
                           f"{ue_h * 1e3:.6f}; Ausgang {u0[1, 2] * 1e3:.6f} / {u0[4, 2] * 1e3:.6f}")


# --------------------------------------------------------------------------
# Dateien von Hand lesen (zweiter Weg, ohne die Importer des Programms)
# --------------------------------------------------------------------------
def _step_argumente(s):
    """Argumente einer STEP-Instanz auf der obersten Klammerebene trennen."""
    out, tiefe, start, text = [], 0, 0, False
    for i, ch in enumerate(s):
        if ch == "'":
            text = not text
        elif not text:
            if ch == "(":
                tiefe += 1
            elif ch == ")":
                tiefe -= 1
            elif ch == "," and tiefe == 0:
                out.append(s[start:i].strip())
                start = i + 1
    out.append(s[start:].strip())
    return out


def _ifc_knoten(pfad):
    """Globale Lage jedes IFCSTRUCTURALPOINTCONNECTION, von Hand aus der Datei:
    Ursprung der Platzierung (IFCLOCALPLACEMENT, auch verkettet) plus der Punkt
    der Darstellung (IFCVERTEXPOINT). Die Platzierungen des Exports sind
    ungedreht; so liest jedes IFC-Programm die Lage."""
    inst = {int(z.group(1)): (z.group(2), z.group(3))
            for z in re.finditer(r"^#(\d+)\s*=\s*([A-Z0-9_]+)\((.*)\);\s*$", _lesen(pfad), re.M)}

    def arg(i):
        return _step_argumente(inst[i][1])

    def nr(s):
        return int(s.strip("()").split(",")[0].strip().lstrip("#"))

    def punkt(i):
        assert inst[i][0] == "IFCCARTESIANPOINT", inst[i]
        return np.array([float(x) for x in inst[i][1].strip("()").split(",")])

    def ursprung(i):
        rel, achsen = arg(i)[:2]
        o = ursprung(nr(rel)) if rel.startswith("#") else np.zeros(3)
        return o + punkt(nr(arg(nr(achsen))[0]))

    out = {}
    for i, (typ, _) in inst.items():
        if typ != "IFCSTRUCTURALPOINTCONNECTION":
            continue
        a = arg(i)
        darstellung = nr(arg(nr(a[6]))[2])                # IFCPRODUCTDEFINITIONSHAPE -> Darstellung
        ecke = nr(arg(darstellung)[3])                    # IFCTOPOLOGYREPRESENTATION -> IFCVERTEXPOINT
        out[a[2].strip("'")] = ursprung(nr(a[5])) + punkt(nr(arg(ecke)[0]))
    return out


_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _xlsx_blatt(pfad, name):
    """Ein Blatt der XLSX-Datei von Hand (zipfile + XML): Liste von Zeilen als
    {Spaltenkopf: Wert}; None, wenn es das Blatt nicht gibt."""
    with zipfile.ZipFile(pfad) as z:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        nr = {s.get("name"): s.get("sheetId") for s in wb.iter(_NS + "sheet")}
        if name not in nr:
            return None
        ws = ET.fromstring(z.read(f"xl/worksheets/sheet{nr[name]}.xml"))
    zeilen = []
    for row in ws.iter(_NS + "row"):
        z = {}
        for c in row.iter(_NS + "c"):
            sp = re.match(r"[A-Z]+", c.get("r")).group(0)
            t, v = c.find(f"{_NS}is/{_NS}t"), c.find(_NS + "v")
            z[sp] = t.text if t is not None else (float(v.text) if v is not None else None)
        zeilen.append(z)
    if not zeilen:
        return []
    kopf = zeilen[0]
    return [{kopf[sp]: w for sp, w in z.items() if sp in kopf} for z in zeilen[1:]]


def _bdf_knoten(pfad):
    """Knotenkoordinaten von Hand aus den GRID-Karten: Grossfeld (GRID*, 16
    Zeichen je Feld, z im ersten Feld der Folgezeile) oder Kleinfeld (8 Zeichen)."""
    zeilen = _lesen(pfad).splitlines()
    out = {}
    for i, w in enumerate(zeilen):
        if w.startswith("GRID*"):
            out[int(w[8:24])] = (float(w[40:56]), float(w[56:72]), float(zeilen[i + 1][8:24]))
        elif w.startswith("GRID"):
            out[int(w[8:16])] = (float(w[24:32]), float(w[32:40]), float(w[40:48]))
    return out


def _inp_knoten(pfad):
    """Knotenkoordinaten von Hand aus dem Block *NODE."""
    out, drin = {}, False
    for w in _lesen(pfad).splitlines():
        if w.startswith("*"):
            drin = w.split(",")[0].strip().upper() == "*NODE"        # nicht *NODE OUTPUT, *NODE PRINT
            continue
        if drin and w.strip():
            t = [x.strip() for x in w.split(",")]
            out[int(t[0])] = tuple(float(x) for x in t[1:4])
    return out


def _dxf_paare(pfad):
    z = _lesen(pfad).splitlines()
    return [(int(z[i].strip()), z[i + 1].strip()) for i in range(0, len(z) - 1, 2)]


def _dxf_linien_je_ebene(pfad):
    """Anzahl der LINE-Elemente je Ebene, von Hand aus den Gruppencodes."""
    out, art = {}, None
    for code, wert in _dxf_paare(pfad):
        if code == 0:
            art = wert
        elif code == 8 and art == "LINE":
            out[wert] = out.get(wert, 0) + 1
            art = None
    return out


def _dxf_kopfwert(pfad, variable):
    paare = _dxf_paare(pfad)
    for i, (code, wert) in enumerate(paare[:-1]):
        if code == 9 and wert == variable:
            return paare[i + 1]
    return None


# --------------------------------------------------------------------------
# B2: IFC
# --------------------------------------------------------------------------
def test_b2_ifc():
    m = _stabwerk()
    with tempfile.TemporaryDirectory() as d:
        m2, log_e, log_i, p = _rundreise(m, d, ".ifc")
        check("B2 IFC: Rundreise liefert dieselben 5 Knoten an derselben Stelle",
              _abw(m, m2) < 1e-12, f"{m2.nn} Knoten, größte Abweichung {_abw(m, m2):.3g} m")
        # zweiter Weg: Platzierung + Punkt von Hand aus der Datei
        lage = _ifc_knoten(p)
        soll = {f"N{i + 1}": np.asarray(m.nodes[i]) for i in range(m.nn)}
        abw = max((float(np.abs(lage[k] - soll[k]).max()) for k in soll if k in lage), default=float("inf"))
        check("B2 IFC: Platzierung + Punkt aus der Datei gelesen = Modellkoordinaten",
              set(lage) == set(soll) and abw < 1e-12, f"{len(lage)} Punkte, größte Abweichung {abw:.3g} m")
        w = m2.materials.get("S355")
        check("B2 IFC: Werkstoff S355 mit E, f_y und f_u kommt zurück",
              w is not None and _nah(w.E, 2.1e11, 1e-12) and _nah(w.fy, 355e6, 1e-12)
              and _nah(w.fu, m.materials["S355"].fu, 1e-12) and list(m2.materials) == ["S355"],
              f"Werkstoffe {[(n, x.E, x.fy, x.fu) for n, x in m2.materials.items()]}")
        s, s0 = m2.sections.get(RHS), m.sections[RHS]
        r, r0 = m2.sections.get(RD), m.sections[RD]
        ok = (s is not None and r is not None
              and all(_nah(getattr(s, a), getattr(s0, a), 1e-9) for a in ("A", "Iy", "Iz", "It", "Asy", "Asz", "h", "b", "tw"))
              and all(_nah(getattr(r, a), getattr(r0, a), 1e-9) for a in ("A", "Iy", "h"))
              and s.typ == s0.typ and r.typ == r0.typ)
        check("B2 IFC: Profile mit Form, Maßen, Kennwerten und Schubflächen kommen zurück", ok,
              f"{[(n, x.typ, x.h, x.b, x.tw, x.A, x.Asz) for n, x in m2.sections.items()]}")
        check("B2 IFC: Momentengelenk, Fachwerkstab und die 4 Lager kommen zurück",
              _typen(m2) == SOLL_TYPEN and _lager(m2) == SOLL_LAGER, f"{_typen(m2)}, Lager {_lager(m2)}")
        _verformung("B2 IFC: Rundreise rechnet u_B und u_E wie die Handformel (Lasten, Gelenk, Profil)",
                    m, m2, 1e-9)
    # Was IFC nicht traegt, steht als Hinweis mit Anzahl da
    mf, _, _ = _platte_und_schwelle()
    with tempfile.TemporaryDirectory() as d:
        log = []
        export_model(mf, os.path.join(d, "f.ifc"), log=log)
        h = _hinweis(log, "IFC")
        check("B2 IFC: Hinweis nennt die 2 Linienlager, die nicht übertragen werden",
              "2 Linienlager" in h and h.startswith("WARNUNG"), h[:160] or "(kein Hinweis)")


# --------------------------------------------------------------------------
# B3: SAF
# --------------------------------------------------------------------------
def test_b3_saf_stabwerk():
    m = _stabwerk()
    with tempfile.TemporaryDirectory() as d:
        m2, log_e, log_i, p = _rundreise(m, d, ".xlsx")
        check("B3 SAF: Momentengelenk und Fachwerkstab kommen zurück",
              _typen(m2) == SOLL_TYPEN and _abw(m, m2) < 1e-12 and _lager(m2) == SOLL_LAGER,
              f"{_typen(m2)}")
        # zweiter Weg: die Blaetter von Hand gelesen
        staebe = _xlsx_blatt(p, "StructuralCurveMember") or []
        gelenke = _xlsx_blatt(p, "RelConnectsStructuralMember") or []
        verhalten = {z.get("Name"): z.get("Behaviour in analysis") for z in staebe}
        frei = [(z.get("Member"), z.get("Position"), [k for k in ("ux", "uy", "uz", "fix", "fiy", "fiz")
                                                      if z.get(k) == "Free"]) for z in gelenke]
        check("B3 SAF: Datei nennt „Axial force only“ am Hänger und das Gelenk fiy am Einhängeträger",
              verhalten == {"Kragarm": "Standard", "Einhaengetraeger": "Standard", "Haenger": "Axial force only"}
              and frei == [("Einhaengetraeger", "Begin", ["fiy"])], f"{verhalten}, Gelenke {frei}")
        _verformung("B3 SAF: Rundreise rechnet u_B und u_E wie die Handformel", m, m2, 1e-9)


def test_b3_saf_linienlager():
    m, spitze, st = _platte_und_schwelle()
    u0, _ = _rechnen(m)
    hand_platte = -PP * LP ** 3 / (3 * 2.1e11 * BP * TP ** 3 / 12)
    hand_schwelle = -QS / CS
    with tempfile.TemporaryDirectory() as d:
        m2, log_e, log_i, p = _rundreise(m, d, ".xlsx")
        ll = {l.name: (sorted(int(n) for n in l.nodes),
                       {int(k): (b.typ, float(b.stiffness)) for k, b in l.behaviour.items()})
              for l in m2.line_supports}
        kante = sorted(int(n) for n in m.line_supports[0].nodes)
        soll = {"Einspannung": (kante, {k: ("rigid", 0.0) for k in range(6)}),
                "Bettung": (sorted(st), {2: ("spring", CS)})}
        check("B3 SAF: Linienlager an Schalenkante (starr) und Stab (Feder 5 MN/m²) kommen zurück",
              ll == soll, f"{ll}")
        # zweiter Weg: die Blaetter von Hand
        kanten = _xlsx_blatt(p, "StructuralEdgeConnection") or []
        stab = _xlsx_blatt(p, "StructuralCurveConnection") or []
        check("B3 SAF: Datei führt 2 Kantenabschnitte „Einspannung“ und die Bettung 5 MN/m² am Stab",
              len(kanten) == 2 and all(z.get("uz") == "Rigid" and z.get("fiy") == "Rigid" for z in kanten)
              and len(stab) == 1 and stab[0].get("Member") == "Schwelle" and stab[0].get("uz") == "Flexible"
              and any(_nah(float(v), 5.0, 1e-12) for k, v in stab[0].items() if k.startswith("Stiffness Z")),
              f"{len(kanten)} Kantenzeilen, Stab {[(z.get('Member'), z.get('uz')) for z in stab]}")
        try:
            u2, _ = _rechnen(m2)
            up, us = float(u2[spitze, 2]), np.asarray(u2[st, 2], float)
        except Exception as ex:      # noqa: BLE001
            up, us = float("nan"), np.full(len(st), np.nan)
            print("   Rechnung nach der Rundreise scheitert:", ex)
        check("B3 SAF: Platte an der Einspannung biegt sich wie vorher (Hand P L³/3EI, Netz 0,4 % darunter)",
              _nah(up, float(u0[spitze, 2]), 1e-9) and _nah(up, hand_platte, 5e-3),
              f"{up * 1e3:.4f} mm, Ausgang {u0[spitze, 2] * 1e3:.4f}, Hand {hand_platte * 1e3:.4f}")
        check("B3 SAF: Schwelle auf der Bettung senkt sich überall um q/c = 2 mm",
              bool(np.all(np.abs(us - hand_schwelle) <= 1e-9 * abs(hand_schwelle)))
              and bool(np.all(np.abs(np.asarray(u0[st, 2]) - hand_schwelle) <= 1e-9 * abs(hand_schwelle))),
              f"{np.round(us * 1e3, 6)} mm, Hand {hand_schwelle * 1e3:.6f}")
        # Werkstoff je Stab: der Querschnitt trug immer den ersten Werkstoff des Modells
        mats = sorted({e.mat for e in m2.elements if e.typ == "beam"})
        qs = {z.get("Name"): z.get("Material") for z in (_xlsx_blatt(p, "StructuralCrossSection") or [])}
        check("B3 SAF: die Stäbe behalten ihren Werkstoff S355 (in der Datei am Querschnitt und nach der Rundreise)",
              mats == ["S355"] and qs.get(RHS) == "S355", f"Stäbe {mats}, Querschnitt in der Datei {qs}")


def test_b3_saf_hinweise():
    # ein Querschnitt mit zwei Werkstoffen: jeder Stab behaelt seinen, der Export sagt es
    m = Model("G6W")
    m.add_material(Material.steel("S235"))
    m.add_material(Material.steel("S355"))
    m.add_section(Section.rhs(RHS, 0.3, 0.2, 0.01))
    k = [m.add_node(x, 0, 0) for x in (0.0, 1.0, 2.0)]
    m.add_member("A", [m.add_element("beam", [k[0], k[1]], "S235", RHS)])
    m.add_member("B", [m.add_element("beam", [k[1], k[2]], "S355", RHS)])
    m.fix(k[0], "all")
    m.load_node(k[2], Fz=-1000.0, case="LF1")
    with tempfile.TemporaryDirectory() as d:
        m2, log_e, log_i, p = _rundreise(m, d, ".xlsx")
        warn = [z for z in log_e if "verschiedenen Werkstoffen" in z]
        check("B3 SAF: ein Querschnitt mit zwei Werkstoffen - jeder Stab behält seinen, der Export nennt es",
              [e.mat for e in m2.elements] == ["S235", "S355"] and len(warn) == 1 and "1 Querschnitt wird" in warn[0],
              f"{[e.mat for e in m2.elements]}; {(warn or ['(keine Meldung)'])[0][:90]}")
    # Flaechenlager traegt der SAF-Export nicht: Hinweis mit Anzahl
    m = Model("G6FL")
    m.add_material(Material.steel("S355"))
    m.add_shell_prop(ShellProp("t20", 0.02))
    kn = [m.add_node(x, y, 0) for x, y in ((0, 0), (1, 0), (1, 1), (0, 1))]
    e = m.add_element("shell4", kn, "S355", "t20")
    m.fix(kn[0], [0, 1, 5])
    m.fix(kn[1], [1])
    m.add_surface_support(elements=[e], name="Bettung", uz=dict(typ="spring", stiffness=2e7))
    m.load_node(kn[2], Fz=-100.0, case="LF1")
    with tempfile.TemporaryDirectory() as d:
        fehlt = []
        for endung, fmt in ((".xlsx", "SAF"), (".inp", "Abaqus"), (".bdf", "Nastran"), (".ifc", "IFC"), (".dxf", "DXF")):
            log = []
            export_model(m, os.path.join(d, "fl" + endung), log=log)
            h = _hinweis(log, fmt)
            if "1 Flächenlager" not in h or not h.startswith("WARNUNG"):
                fehlt.append(fmt)
        check("B3/B4 Flächenlager: SAF, Abaqus, Nastran, IFC und DXF nennen „1 Flächenlager“ als nicht übertragen",
              not fehlt, f"ohne Hinweis: {fehlt}" if fehlt else "")


# --------------------------------------------------------------------------
# B4: Abaqus und Nastran
# --------------------------------------------------------------------------
def test_b4_nastran():
    m = _stabwerk()
    with tempfile.TemporaryDirectory() as d:
        m2, log_e, log_i, p = _rundreise(m, d, ".bdf")
        kn = _bdf_knoten(p)
        x2 = kn.get(2, (float("nan"),) * 3)[0]
        check("B4 Nastran: GRID trägt x = 1,23456789 mit voller Genauigkeit (von Hand aus dem Feld gelesen)",
              x2 == L1 and _abw(m, m2) == 0.0, f"Feld {x2!r}, Rundreise Abweichung {_abw(m, m2):.3g} m")
        zeilen = _lesen(p).splitlines()
        karten = [w[:8].strip().rstrip("*") for w in zeilen if w[:1].isalpha()]
        check("B4 Nastran: der Fachwerkstab steht als CROD mit PROD in der Datei, die Balken als CBAR",
              karten.count("CROD") == 1 and karten.count("PROD") == 1 and karten.count("CBAR") == 2
              and _typen(m2) == SOLL_TYPEN,
              f"CROD {karten.count('CROD')}, PROD {karten.count('PROD')}, CBAR {karten.count('CBAR')}; {_typen(m2)}")
        _verformung("B4 Nastran: Rundreise rechnet u_B und u_E wie die Handformel (Gelenk, Stablast, Schubfläche)",
                    m, m2, 1e-9)
    mf, _, _ = _platte_und_schwelle()
    with tempfile.TemporaryDirectory() as d:
        log = []
        export_model(mf, os.path.join(d, "f.bdf"), log=log)
        h = _hinweis(log, "Nastran")
        check("B4 Nastran: Hinweis nennt die 2 Linienlager, die nicht übertragen werden",
              "2 Linienlager" in h and h.startswith("WARNUNG"), h[:160] or "(kein Hinweis)")


def test_b4_abaqus():
    m = _stabwerk()
    with tempfile.TemporaryDirectory() as d:
        m2, log_e, log_i, p = _rundreise(m, d, ".inp")
        kn = _inp_knoten(p)
        x2 = kn.get(2, (float("nan"),) * 3)[0]
        check("B4 Abaqus: *NODE trägt x = 1,23456789 mit voller Genauigkeit (von Hand gelesen)",
              x2 == L1 and _abw(m, m2) == 0.0, f"Zeile {x2!r}, Rundreise Abweichung {_abw(m, m2):.3g} m")
        kopf = [w.upper().replace(" ", "") for w in _lesen(p).splitlines() if w.startswith("*") and not w.startswith("**")]
        check("B4 Abaqus: der Fachwerkstab steht als T3D2 in der Datei, das Gelenk als *RELEASE",
              sum(1 for w in kopf if w.startswith("*ELEMENT,") and "TYPE=T3D2" in w) == 1
              and sum(1 for w in kopf if w.startswith("*RELEASE")) == 1 and _typen(m2) == SOLL_TYPEN,
              f"{_typen(m2)}")
        _verformung("B4 Abaqus: Rundreise rechnet u_B und u_E wie die Handformel (Gelenk, Stablast, Schubfläche)",
                    m, m2, 1e-9)
    # *DLOAD auf ALL: der Satz ALL muss in der Datei stehen
    m = Model("G6E")
    m.add_material(Material.steel("S355"))
    m.add_section(Section.rhs(RHS, 0.3, 0.2, 0.01))
    a = m.add_node(0, 0, 0)
    b = m.add_node(2.5, 0, 0)
    m.add_element("beam", [a, b], "S355", RHS)
    m.fix(a, "all")
    m.gravity = [0.0, 0.0, -9.81]
    gewicht = m.materials["S355"].rho * m.sections[RHS].A * 2.5 * 9.81      # zweiter Weg: ρ A L g
    with tempfile.TemporaryDirectory() as d:
        m2, log_e, log_i, p = _rundreise(m, d, ".inp")
        text = _lesen(p).upper().replace(" ", "")
        saetze = set(re.findall(r"ELSET=([A-Z0-9_\-]+)", text))
        benutzt = set(re.findall(r"^([A-Z][A-Z0-9_\-]*),GRAV,", text, re.M))
        an = solver.solve_all(m2, workers=1, combinations=False)
        rz = float(np.asarray(next(iter(an.cases.values())).reactions)[:, 2].sum())
        check("B4 Abaqus: *DLOAD ... GRAV nennt nur Elementsätze, die in der Datei stehen; Auflagerkraft = ρ A L g",
              benutzt == {"ALL"} and benutzt <= saetze and _nah(rz, gewicht, 1e-9),
              f"benutzt {sorted(benutzt)}, vorhanden {sorted(saetze)}; ΣRz {rz:.3f} N, Hand {gewicht:.3f} N")
    mf, _, _ = _platte_und_schwelle()
    with tempfile.TemporaryDirectory() as d:
        log = []
        export_model(mf, os.path.join(d, "f.inp"), log=log)
        h = _hinweis(log, "Abaqus")
        check("B4 Abaqus: Hinweis nennt die 2 Linienlager, die nicht übertragen werden",
              "2 Linienlager" in h and h.startswith("WARNUNG"), h[:160] or "(kein Hinweis)")


# --------------------------------------------------------------------------
# B5: DXF
# --------------------------------------------------------------------------
def _dxf_von_hand(kopf, x2):
    return ("  0\nSECTION\n  2\nHEADER\n" + kopf + "  0\nENDSEC\n  0\nSECTION\n  2\nENTITIES\n"
            "  0\nLINE\n  8\nTRAEGER\n 10\n0.0\n 20\n0.0\n 30\n0.0\n 11\n" + x2 + "\n 21\n0.0\n 31\n0.0\n"
            "  0\nENDSEC\n  0\nEOF\n")


def test_b5_dxf():
    m = _stabwerk()
    with tempfile.TemporaryDirectory() as d:
        m2, log_e, log_i, p = _rundreise(m, d, ".dxf")
        check("B5 DXF: der Kopf nennt die Einheit Meter ($INSUNITS = 6, von Hand gelesen)",
              _dxf_kopfwert(p, "$INSUNITS") == (70, "6"), f"{_dxf_kopfwert(p, '$INSUNITS')}")
        laengen = sorted(round(float(np.linalg.norm(m2.nodes[e.nodes[1]] - m2.nodes[e.nodes[0]])), 12)
                         for e in m2.elements)
        check("B5 DXF: Rundreise liefert dasselbe Stabwerk (5 Knoten, 3 Stäbe 1,23456789 / 1,5 / 2 m)",
              _abw(m, m2) == 0.0 and len(m2.elements) == 3 and laengen == [L1, LH, L2],
              f"{m2.nn} Knoten, {len(m2.elements)} Elemente, Längen {laengen[:6]}, Abweichung {_abw(m, m2):.3g} m")
        # die Vorwahl des Importdialogs kommt aus derselben Stelle (ohne Fenster geprueft)
        try:
            from statik3d.importers.dxf import einheit_der_datei
            vorwahl = einheit_der_datei(p)
            fehlt = einheit_der_datei(os.path.join(d, "gibt_es_nicht.dxf"))
        except Exception as ex:      # noqa: BLE001
            vorwahl, fehlt = repr(ex)[:80], "?"
        check("B5 DXF: die Vorwahl des Importdialogs liest aus dem eigenen Export Meter mit Faktor 1",
              isinstance(vorwahl, tuple) and vorwahl[0] == "Meter" and vorwahl[1] == 1.0 and fehlt is None,
              f"{vorwahl}, fehlende Datei: {fehlt}")
        # zweiter Weg: die Ebenen von Hand gezaehlt
        ebenen = _dxf_linien_je_ebene(p)
        tragwerk = {k: n for k, n in ebenen.items() if not k.startswith("STATIK3D_")}
        check("B5 DXF: außerhalb der Ebenen STATIK3D_* liegen genau die 3 Stablinien (Symbole auf eigener Ebene)",
              sum(tragwerk.values()) == 3 and ebenen.get("STATIK3D_LAGER", 0) > 0, f"{ebenen}")
        h = _hinweis(log_e, "DXF")
        check("B5 DXF: Hinweis nennt Gelenk, Lager und Lasten, die eine Zeichnung nicht trägt",
              all(t in h for t in ("1 Stabendgelenk", "4 Knotenlager", "3 Knotenlasten", "1 Stablast")),
              h[:200] or "(kein Hinweis)")
        # handgeschriebene Dateien: ohne Einheit, in mm, in m
        erg = {}
        for name, kopf, x2 in (("ohne", "", "5000.0"), ("mm", "  9\n$INSUNITS\n 70\n4\n", "5000.0"),
                               ("m", "  9\n$INSUNITS\n 70\n6\n", "5.0")):
            q = os.path.join(d, f"hand_{name}.dxf")
            with open(q, "w") as f:
                f.write(_dxf_von_hand(kopf, x2))
            log = []
            mh = import_file(q, log=log)
            erg[name] = (float(np.linalg.norm(mh.nodes[1] - mh.nodes[0])) if mh.nn == 2 else float("nan"), log)
        warn = [z for z in erg["ohne"][1] if z.startswith("WARNUNG") and "keine Längeneinheit" in z]
        check("B5 DXF: ohne $INSUNITS bleibt es bei Millimetern, eine Warnung nennt die angenommene Einheit",
              abs(erg["ohne"][0] - 5.0) < 1e-12 and len(warn) == 1 and "Millimeter" in warn[0],
              f"Länge {erg['ohne'][0]} m; {(warn or ['(keine Warnung)'])[0][:110]}")
        check("B5 DXF: $INSUNITS = 6 wird als Meter gelesen, $INSUNITS = 4 als Millimeter (je 5 m)",
              abs(erg["m"][0] - 5.0) < 1e-12 and abs(erg["mm"][0] - 5.0) < 1e-12
              and any("Meter ($INSUNITS = 6)" in z for z in erg["m"][1])
              and any("Millimeter ($INSUNITS = 4)" in z for z in erg["mm"][1]),
              f"m: {erg['m'][0]} m, mm: {erg['mm'][0]} m")


# --------------------------------------------------------------------------
# B6: Lastfallname nach dem Abaqus- und dem IFC-Import
# --------------------------------------------------------------------------
INP_VON_HAND = """*HEADING
Kragarm von Hand
*NODE
1, 0.0, 0.0, 0.0
2, 2.0, 0.0, 0.0
*ELEMENT, TYPE=B31, ELSET=TRAEGER
1, 1, 2
*BEAM SECTION, ELSET=TRAEGER, MATERIAL=STAHL, SECTION=RECT
0.1, 0.2
0.0, 1.0, 0.0
*MATERIAL, NAME=STAHL
*ELASTIC
2.1E11, 0.3
*BOUNDARY
1, 1, 6
*STEP, NAME=LF1
*STATIC
*CLOAD
2, 3, -1000.0
*END STEP
*STEP, NAME=LF2
*STATIC
*CLOAD
2, 3, -2000.0
*END STEP
"""


def test_b6_lastfallname():
    m = _stabwerk()
    with tempfile.TemporaryDirectory() as d:
        for endung, fmt in ((".inp", "Abaqus"), (".ifc", "IFC")):
            m2, log_e, log_i, p = _rundreise(m, d, endung)
            lasten = {n: int(l.n_loads) for n, l in m2.load_cases.items()}
            check(f"B6 {fmt}: die Lastfälle heißen nach der Rundreise LF1 und LF2 (3 Lasten und 1 Last)",
                  lasten == {"LF1": 3, "LF2": 1}, f"{lasten}")
        # zweiter Weg: eine von Hand geschriebene Datei, die den Namen selbst nennt
        q = os.path.join(d, "hand.inp")
        with open(q, "w") as f:
            f.write(INP_VON_HAND)
        mh = import_file(q, log=[])
        # Gegenprobe im selben Schritt: an ein Modell mit belegtem LF1 angehaengt
        # bleibt dessen LF1 unberuehrt, der Lastfall der Datei heisst LF1_2
        mv = Model("voll")
        mv.add_material(Material.steel("S235"))
        mv.add_section(Section.circle(RD, 0.02))
        k1, k2 = mv.add_node(0, 5, 0), mv.add_node(1, 5, 0)
        mv.add_element("beam", [k1, k2], "S235", RD)
        mv.fix(k1, "all")
        mv.load_node(k2, Fz=-5.0, case="LF1")
        import_file(q, model=mv, log=[])
        check("B6 Abaqus: *STEP, NAME=LF1 wird „LF1“; an ein Modell mit belegtem LF1 angehängt bleibt es bei LF1_2",
              list(mh.load_cases) == ["LF1", "LF2"] and list(mv.load_cases) == ["LF1", "LF1_2", "LF2"],
              f"frisch {list(mh.load_cases)}, angehängt {list(mv.load_cases)}")


def main():
    for t in (test_b2_ifc, test_b3_saf_stabwerk, test_b3_saf_linienlager, test_b3_saf_hinweise,
              test_b4_nastran, test_b4_abaqus, test_b5_dxf, test_b6_lastfallname):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:          # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    sys.exit(main())
