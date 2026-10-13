"""Stabenden verteilend in ein Volumen einleiten (seit 13.10.2026).

Entscheidung des Anwenders vom 13.10.2026: eine Modelleinstellung, je
Stabende schaltbar; die Kopplung als RBE3 ohne Versteifung, flaechenanteilig
gewichtet; Einleitungsflaeche als Vorgabe die Stirnflaeche, wahlweise ein
Kreisring; bei Import und Rechenstart ein Hinweis, nichts automatisch
umstellen; im Ergebnis Kraftsumme und Moment je gekoppeltem Stabende pruefen
und die Stabenden kennzeichnen. Ergaenzt: Gewichte nach Ausschluss der
gebundenen Randknoten neu normieren, Lastschwerpunkt auf der Stabachse.

Proben:
1. Zugstab mittig auf einem Quader 20 x 20 x 40 mm (tet10): verteilt ist die
   Spannung in der Stirnflaeche F/A, an 1-3 Knoten eine Spitze; die Knoten
   der Flaeche verschieben sich wie unter der gleichmaessigen Flaechenlast
   (die Kopplung versteift nicht).
2. Kraftsumme und Moment der Kopplung gleich der Stabendkraft.
3. Moment am Stabende: Kragarm biegesteif, Torsion, Gelenk bleibt Gelenk.
4. Kreisring als Flaeche.
5. Schalter je Stabende vor dem Modell.
6. Speichern und Laden; eine Datei ohne Einstellung bleibt gleich.
7. Stirnflaeche mit Kontaktrand: gebundene Mitten heraus, Schwerpunkt
   zurueck auf die Achse, Kontakt rechnet.
8. Hinweise bei Import und Rechenstart; die Erkennung der Spannungsspitzen
   sieht eine Flaeche statt eines Punkts.

Aufruf:  python -m tests.test_stabeinleitung
"""
import json
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import diagnose, fugen, mesher3d as M3, solver, spitzenstellen   # noqa: E402
from statik3d import stabeinleitung as SE                                       # noqa: E402
from statik3d.model import Material, Model, NodalLoad, Section, Stabeinleitung   # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:78s} {detail}")
    return ok


class Bauer:
    def __init__(self, model):
        self.m = model
        self.i = 0

    def linie(self, a, b):
        self.i += 1
        self.m.add_line(f"L{self.i}", [a, b], "polyline")
        return f"L{self.i}"


A, B, C = 0.020, 0.020, 0.040            # Quader [m]
D16 = 0.016


def quader(h: float = 0.005, ordnung: int = 2) -> Model:
    """Quader A x B x C, vernetzt (tet10), Koerper V1, Stirnflaeche oben."""
    m = Model()
    m.add_material(Material.steel("S235"))
    m.add_nodes(np.array([[0, 0, 0], [A, 0, 0], [A, B, 0], [0, B, 0],
                          [0, 0, C], [A, 0, C], [A, B, C], [0, B, C]], float))
    b = Bauer(m)
    R = [[b.linie(o + i, o + (i + 1) % 4) for i in range(4)] for o in (0, 4)]
    V = [b.linie(i, i + 4) for i in range(4)]
    m.add_flaeche("Boden", R[0], material="S235")
    m.add_flaeche("Deckel", R[1], material="S235")
    mantel = []
    for i in range(4):
        m.add_flaeche(f"M{i}", [R[0][i], V[(i + 1) % 4], R[1][i], V[i]], material="S235")
        mantel.append(f"M{i}")
    k = m.add_koerper("V1", ["Boden", "Deckel"] + mantel, material="S235")
    m.netz.ziellaenge = h
    m.netz.ordnung = ordnung
    M3.mesh_koerper_frei(m, k, log=[], cache={})
    return m


def rund(m, name="Rund 16", d=D16):
    A_ = np.pi * d * d / 4
    I_ = np.pi * d ** 4 / 64
    m.add_section(Section(name, A_, I_, I_, 2 * I_))
    return name


def knoten_bei(m, z, nur_volumen=True):
    im = np.zeros(m.nn, bool)
    im[[int(x) for e in m.elements if e.typ in ("tet10", "tet4") for x in e.nodes]] = True
    return [int(i) for i in np.flatnonzero(im & (np.abs(m.nodes[:, 2] - z) < 1e-9))]


def naechster(m, p, kandidaten):
    kandidaten = np.asarray(kandidaten)
    return int(kandidaten[np.argmin(np.linalg.norm(m.nodes[kandidaten] - p, axis=1))])


def lagern_frei(m):
    """Boden in z, dazu zwei Ecken gegen Verschieben und Drehen - die
    Querdehnung bleibt frei (gleichmaessiger Zustand)."""
    unten = knoten_bei(m, 0.0)
    for i in unten:
        m.fix(i, [2])
    m.fix(naechster(m, [0, 0, 0], unten), [0, 1])
    m.fix(naechster(m, [A, 0, 0], unten), [1])
    return unten


def zugstab(m, p=(A / 2, B / 2, C), laenge=0.05, typ="truss", umgekehrt=False, achse=(0, 0, 1)):
    sec = rund(m)
    fuss = m.add_node(*p)
    kopf = m.add_node(*(np.asarray(p, float) + laenge * np.asarray(achse, float)))
    nd = [kopf, fuss] if umgekehrt else [fuss, kopf]
    e = m.add_element(typ, nd, "S235", sec, group="Zug")
    m.add_member("S1", [e])
    return fuss, kopf, e


def lastfall(m, knoten, F):
    lc = m.add_load_case("LF1")
    lc.gravity = [0, 0, 0]
    lc.nodal_loads.append(NodalLoad(knoten, list(F) + [0.0] * (6 - len(F))))
    return lc


def stirnelemente(m, z=C):
    """Volumenelemente mit einer Seite in der Stirnflaeche (drei Ecken auf z)."""
    oben = set(knoten_bei(m, z))
    return [i for i, e in enumerate(m.elements) if e.typ == "tet10"
            and sum(1 for x in e.nodes[:4] if int(x) in oben) >= 3]


# --------------------------------------------------------------------------
def test_stirnflaeche_zug():
    print("\n--- 1. Zugstab auf der Stirnflaeche: F/A statt Spitze ---")
    F = 10e3
    soll = F / (A * B)                      # 25 N/mm2
    erg = {}
    for art in ("punkt", "stirn"):
        m = quader()
        lagern_frei(m)
        fuss, kopf, _e = zugstab(m)
        m.stabeinleitung = Stabeinleitung(art)
        log = []
        b = fugen.stabenden_koppeln(m, log)
        lastfall(m, kopf, [0, 0, F])
        r = solver.solve_static(m, case="LF1")
        el = stirnelemente(m)
        sz = np.array([r.solid_res[i][2] for i in el])
        oben = knoten_bei(m, C)
        sv = np.asarray(r.node_vm)[oben]
        erg[art] = dict(m=m, r=r, b=b, sz=sz, sv=sv, log=log, fuss=fuss, kopf=kopf)
        print(f"    {art}: sigma_zz der {len(el)} Stirnelemente {sz.min() / 1e6:.3f} … {sz.max() / 1e6:.3f} N/mm2, "
              f"sigma_v Knoten der Stirnflaeche {sv.min() / 1e6:.3f} … {sv.max() / 1e6:.3f} N/mm2 (F/A = "
              f"{soll / 1e6:.3f})")
    p, s = erg["punkt"], erg["stirn"]
    check("an 1-3 Knoten (wie RFEM): Spitze in der Stirnflaeche, sigma_v >= 3 F/A",
          p["sv"].max() >= 3 * soll and not any(SE.ist_verteilkopplung(sk) for sk in p["m"].starrkoerper),
          f"{p['sv'].max() / 1e6:.1f} N/mm2 gegen F/A {soll / 1e6:.1f}")
    sk = [x for x in s["m"].starrkoerper if SE.ist_verteilkopplung(x)]
    check("verteilt: eine RBE3 'Stabende K…' an allen Knoten der Stirnflaeche, keine starre Kopplung",
          len(sk) == 1 and sk[0].master == s["fuss"] and set(sk[0].slaves) == set(knoten_bei(s["m"], C))
          and not [k for k in s["m"].kopplungen if k.gruppe.startswith(fugen.STABENDE_GRUPPE)],
          f"{len(sk[0].slaves) if sk else 0} Knoten")
    check("Flaeche der Kopplung = Stirnflaeche 400 mm2 (Summe der Gewichte)",
          sk and abs(sum(sk[0].gewichte) - A * B) < 1e-12, f"{sum(sk[0].gewichte) * 1e6:.6f} mm2" if sk else "")
    check("verteilt: sigma_zz in allen Stirnelementen auf 2 % gleich F/A",
          np.all(np.abs(s["sz"] / soll - 1.0) < 0.02),
          f"{s['sz'].min() / soll:.5f} … {s['sz'].max() / soll:.5f} von F/A")
    check("verteilt: sigma_v an den Knoten der Stirnflaeche auf 2 % gleich F/A",
          np.all(np.abs(s["sv"] / soll - 1.0) < 0.02),
          f"{s['sv'].min() / soll:.5f} … {s['sv'].max() / soll:.5f} von F/A")
    check("das Protokoll nennt die verteilte Einleitung mit Flaeche und Knoten",
          any("verteilt eingeleitet" in z and "Stirnfläche 400,0 mm²" in z for z in s["log"]),
          next((z for z in s["log"] if "verteilt" in z), "")[:150])
    # Versteift nicht: dieselben Verschiebungen wie unter der konsistenten
    # Flaechenlast F/A ohne Stab
    m2 = quader()
    lagern_frei(m2)
    lc = m2.add_load_case("LF1")
    lc.gravity = [0, 0, 0]
    for q, w in zip(sk[0].slaves, sk[0].gewichte):
        lc.nodal_loads.append(NodalLoad(int(q), [0, 0, F * w / (A * B), 0, 0, 0]))
    r2 = solver.solve_static(m2, case="LF1")
    vol = sorted({int(x) for e in m2.elements for x in e.nodes})
    du = np.abs(s["r"].u[vol, :3] - r2.u[vol, :3]).max()
    check("die Kopplung versteift nicht: Volumenknoten wie unter der gleichmaessigen Flaechenlast",
          du <= 1e-6 * np.abs(r2.u[vol, :3]).max(), f"max |du| {du * 1e9:.4f} nm bei max |u| "
          f"{np.abs(r2.u[vol, :3]).max() * 1e6:.4f} um")
    return erg


def test_kraftsumme(erg):
    print("\n--- 2. Kraftsumme der Kopplung gleich der Stabkraft ---")
    s = erg["stirn"]
    info = s["r"].info.get("stabenden_kraftsumme") or {}
    z = (info.get("je_stabende") or [{}])[0]
    print(f"    F_stab {np.round(z.get('F_stab', []), 6)}  F_kopplung {np.round(z.get('F_kopplung', []), 6)} N, "
          f"dF {z.get('dF', float('nan')):.3e} N, Toleranz {info.get('toleranz', float('nan')):.3e} N")
    check("geprueft: 1 Stabende, keine Abweichung",
          info.get("geprueft") == 1 and not info.get("abweichend"), str({k: info.get(k) for k in ("geprueft", "abweichend")}))
    check("Summe der Knotenkraefte der Kopplung = Stabkraft 10 kN (auf 1e-6 N)",
          abs(z.get("F_kopplung", [0, 0, 0])[2] - 10e3) < 1e-6 and z.get("dF", 1.0) <= z.get("toleranz", 0.0),
          f"{z.get('F_kopplung', [0, 0, 0])[2]:.9f} N")
    R = s["r"].reactions[:, :3].sum(axis=0)
    check("die Lager tragen die 10 kN", abs(R[2] + 10e3) < 1e-6 * 10e3, f"{R[2]:.6f} N")
    text = s["r"].summary()
    check("die Zusammenfassung nennt die Pruefung", "Stabenden verteilt" in text and "Kraftsumme und Moment" in text,
          next((x for x in text.splitlines() if "Stabenden verteilt" in x), "")[:150])


def _kragarm(art, hinge=False, last="quer", stuetze=False):
    m = quader()
    unten = knoten_bei(m, 0.0)
    for i in unten:
        m.fix(i, [0, 1, 2])
    sec = rund(m)
    fuss = m.add_node(A / 2, B / 2, C)
    mitte = m.add_node(A / 2, B / 2, C + 0.025)
    kopf = m.add_node(A / 2, B / 2, C + 0.05)
    e1 = m.add_element("beam", [fuss, mitte], "S235", sec, group="Balken",
                       hinges=[4, 5] if hinge else None)
    e2 = m.add_element("beam", [mitte, kopf], "S235", sec, group="Balken")
    m.add_member("S1", [e1, e2])
    m.stabeinleitung = Stabeinleitung(art)
    fugen.stabenden_koppeln(m, [])
    lc = m.add_load_case("LF1")
    lc.gravity = [0, 0, 0]
    if last == "quer":
        lc.nodal_loads.append(NodalLoad(mitte if stuetze else kopf, [1e3, 0, 0, 0, 0, 0]))
    else:
        lc.nodal_loads.append(NodalLoad(kopf, [0, 0, 0, 0, 0, 20.0]))
    if stuetze:
        m.fix(kopf, [0, 1, 5])
    r = solver.solve_static(m, case="LF1")
    return m, r


def _lineare_flaechenlast(M_y: float, V_x: float):
    """Quader wie _kragarm, statt des Stabes die konsistente Flaechenlast
    sigma_zz = M_y (x - A/2) / I und tau_zx = V_x / A auf der Stirnflaeche."""
    from statik3d.elements import solid as sl
    m = quader()
    for i in knoten_bei(m, 0.0):
        m.fix(i, [0, 1, 2])
    lc = m.add_load_case("LF1")
    lc.gravity = [0, 0, 0]
    I = B * A ** 3 / 12
    oben = set(knoten_bei(m, C))
    f: dict = {}
    for e in m.elements:
        for fl in sl.FLAECHEN[e.typ]:
            kn = [int(e.nodes[x]) for x in fl]
            if all(q in oben for q in kn):
                d = sl.seiten_integration_stapel(m.nodes[kn][None])
                pk = d["punkte"][0]
                t = np.zeros((len(pk), 3))
                t[:, 2] = -M_y * (pk[:, 0] - A / 2) / I
                t[:, 0] = V_x / (A * B)
                fk = (d["dA"][0][:, None, None] * d["N"][:, :, None] * t[:, None, :]).sum(axis=0)
                for q, v in zip(kn, fk):
                    f[q] = f.get(q, 0) + v
    for q, v in f.items():
        lc.nodal_loads.append(NodalLoad(q, list(v) + [0, 0, 0]))
    return m, solver.solve_static(m, case="LF1")


def test_moment():
    print("\n--- 3. Moment am Stabende: biegesteif, Torsion, Gelenk ---")
    m, r = _kragarm("stirn")
    info = r.info.get("stabenden_kraftsumme") or {}
    z = (info.get("je_stabende") or [{}])[0]
    M = np.asarray(z.get("M_kopplung", [0, 0, 0]))
    # Bezug: dieselbe Schnittkraft als konsistente Flaechenlast (Navier-Spannung
    # M x / I und Schub V / A) ohne Stab
    m2, r2 = _lineare_flaechenlast(50.0, 1e3)
    def zz(mm_, rr, z0, z1):
        el = [i for i, e in enumerate(mm_.elements) if e.typ == "tet10"
              and z0 <= mm_.nodes[e.nodes[:4]].mean(axis=0)[2] <= z1]
        s = np.array([rr.solid_res[i][2] for i in el])
        return max(s.max(), -s.min())
    s_st, s_tief = zz(m, r, C - 0.004, C), zz(m, r, C - 0.012, C - 0.008)
    b_st, b_tief = zz(m2, r2, C - 0.004, C), zz(m2, r2, C - 0.012, C - 0.008)
    print(f"    Kragarm 50 mm, 1 kN quer: M_stab {np.round(z.get('M_stab', []), 6)} Nm, M_kopplung "
          f"{np.round(M, 6)} Nm, dM {z.get('dM', float('nan')):.3e} Nm")
    print(f"    groesstes |sigma_zz| der Elemente an der Stirnflaeche {s_st / 1e6:.2f} N/mm2 (konsistente "
          f"lineare Flaechenlast {b_st / 1e6:.2f}), 8-12 mm darunter {s_tief / 1e6:.2f} ({b_tief / 1e6:.2f})")
    check("biegesteif: das Moment der Kopplung um den Durchstosspunkt ist F L = 50 Nm",
          abs(abs(M[1]) - 50.0) < 1e-6 * 50 and z.get("dM", 1) <= z.get("toleranz_M", 0), f"{M[1]:.9f} Nm")
    check("biegesteif: Kraftsumme 1 kN quer", abs(z.get("F_kopplung", [0])[0] - 1e3) < 1e-6,
          f"{z.get('F_kopplung', [0])[0]:.9f} N")
    check("biegesteif: 8-12 mm unter der Flaeche dieselbe Biegespannung wie unter der konsistenten "
          "linearen Flaechenlast (auf 1 %)", abs(s_tief / b_tief - 1.0) < 0.01, f"{s_tief / b_tief:.4f}")
    check("biegesteif: an der Flaeche selbst hoechstens 10 % ueber der konsistenten Last",
          s_st / b_st < 1.10, f"{s_st / b_st:.4f}")
    m, r = _kragarm("stirn", last="torsion")
    z = ((r.info.get("stabenden_kraftsumme") or {}).get("je_stabende") or [{}])[0]
    M = np.asarray(z.get("M_kopplung", [0, 0, 0]))
    check("Torsion 20 Nm um die Stabachse geht als Moment in die Flaeche",
          abs(M[2] - 20.0) < 1e-6 * 20 and z.get("dM", 1) <= z.get("toleranz_M", 0), f"{np.round(M, 9)} Nm")
    # Statisch unbestimmt: Balken 50 mm, oben quer gehalten, 1 kN in der Mitte.
    # Biegesteif nimmt die Flaeche ein Moment auf - klein, weil der Quader unter
    # der Querkraft 500 N selbst um V L^2 / (2 E I) = 1,4e-4 rad kippt, fast so
    # viel wie das Balkenende gelenkig (P L^2 / (16 E I) = 2,3e-4 rad). Mit
    # Gelenk ist es genau null.
    m, r = _kragarm("stirn", stuetze=True)
    z = ((r.info.get("stabenden_kraftsumme") or {}).get("je_stabende") or [{}])[0]
    M_starr = np.asarray(z.get("M_kopplung", [0, 0, 0]))
    m, r = _kragarm("stirn", hinge=True, stuetze=True)
    z = ((r.info.get("stabenden_kraftsumme") or {}).get("je_stabende") or [{}])[0]
    M_gel = np.asarray(z.get("M_kopplung", [0, 0, 0]))
    print(f"    Balken 50 mm, 1 kN in der Mitte, oben gehalten: Moment an der Flaeche biegesteif "
          f"{np.round(M_starr, 6)} Nm, mit Momentengelenk {np.round(M_gel, 9)} Nm")
    check("biegesteif gestuetzt: die Flaeche nimmt ein Biegemoment auf",
          abs(M_starr[1]) > 1e-3, f"{M_starr[1]:.4f} Nm")
    check("Gelenk bleibt Gelenk: an der Flaeche kein Biegemoment (unter 1e-9 F L)",
          np.linalg.norm(M_gel[:2]) < 1e-9 * 1e3 * 0.05 and z.get("dF", 1) <= z.get("toleranz", 0)
          and z.get("dM", 1) <= z.get("toleranz_M", 0),
          f"|M_x, M_y| {np.linalg.norm(M_gel[:2]):.3e} Nm, Kraftsumme {np.round(z.get('F_kopplung', []), 3)} N")


def test_kreisring():
    print("\n--- 4. Kreisring als Flaeche ---")
    m = quader(h=0.004)
    lagern_frei(m)
    fuss, kopf, _e = zugstab(m)
    m.stabeinleitung = Stabeinleitung("ring", 0.006, 0.016)
    log = []
    fugen.stabenden_koppeln(m, log)
    sk = [x for x in m.starrkoerper if SE.ist_verteilkopplung(x)]
    soll = np.pi / 4 * (0.016 ** 2 - 0.006 ** 2)
    A_ = sum(sk[0].gewichte) if sk else 0.0
    print(f"    Kreisring 6/16 mm: Flaeche der Kopplung {A_ * 1e6:.3f} mm2, Soll {soll * 1e6:.3f} mm2, "
          f"{len(sk[0].slaves) if sk else 0} Knoten; Protokoll: {next((z for z in log if 'verteilt' in z), '')}")
    check("Kreisring: Flaeche auf 1 % gleich pi/4 (da² - di²)", sk and abs(A_ / soll - 1) < 0.01,
          f"{A_ * 1e6:.3f} / {soll * 1e6:.3f} mm2")
    X = m.nodes[sk[0].slaves] - np.array([A / 2, B / 2, C]) if sk else np.zeros((0, 3))
    r_ = np.linalg.norm(X[:, :2], axis=1)
    check("Kreisring: Knoten nur an den Seiten, die der Ring trifft (keiner ausserhalb Ø 16 mm + eine Seite)",
          sk and r_.max() < 0.008 + 0.004 * 1.5 and r_.min() < 0.008, f"r {r_.min() * 1e3:.2f} … {r_.max() * 1e3:.2f} mm")
    lastfall(m, kopf, [0, 0, 10e3])
    r = solver.solve_static(m, case="LF1")
    info = r.info.get("stabenden_kraftsumme") or {}
    check("Kreisring: Kraftsumme gleich Stabkraft", info.get("geprueft") == 1 and not info.get("abweichend"),
          f"dF {info.get('max_dF', float('nan')):.3e} N")
    st = [s for s in spitzenstellen.kandidaten(m, zonen=False)
          if s["quelle"] in (spitzenstellen.STABENDE, spitzenstellen.STARRKOERPER)]
    check("Kreisring: die Erkennung der Spannungsspitzen sieht eine Flaeche, keine Stelle", not st,
          str([(s["quelle"], s["art"]) for s in st]))
    # eigener Ring am Stabende vor dem des Modells
    m.members["S1"].einleitung = {"A": {"art": "ring", "d_innen": 0.0, "d_aussen": 0.010}}
    fugen.stabenden_koppeln(m, [])
    sk = [x for x in m.starrkoerper if SE.ist_verteilkopplung(x)]
    soll2 = np.pi / 4 * 0.010 ** 2
    check("Kreisring je Stabende (Vollkreis Ø 10 mm) vor dem Ring des Modells",
          sk and abs(sum(sk[0].gewichte) / soll2 - 1) < 0.01,
          f"{sum(sk[0].gewichte) * 1e6:.3f} / {soll2 * 1e6:.3f} mm2" if sk else "")


def test_vorrang():
    print("\n--- 5. Schalter je Stabende vor der Modelleinstellung ---")
    def art_nach(modell, ende=None, umgekehrt=False):
        m = quader(h=0.01)
        fuss, kopf, _e = zugstab(m, umgekehrt=umgekehrt)
        m.stabeinleitung = Stabeinleitung(modell)
        if ende is not None:
            m.members["S1"].einleitung = ende
        fugen.stabenden_koppeln(m, [])
        rbe = [x for x in m.starrkoerper if SE.ist_verteilkopplung(x)]
        kp = [k for k in m.kopplungen if k.gruppe.startswith(fugen.STABENDE_GRUPPE)]
        return "stirn" if rbe else "punkt" if kp else "frei"
    faelle = [("punkt", None, False, "punkt"), ("stirn", None, False, "stirn"),
              ("stirn", {"A": {"art": "punkt"}}, False, "punkt"),
              ("punkt", {"A": {"art": "stirn"}}, False, "stirn"),
              ("stirn", {"E": {"art": "punkt"}}, False, "stirn"),       # das andere Ende
              ("punkt", {"E": {"art": "stirn"}}, True, "stirn"),        # Stab umgekehrt: das Ende E liegt im Volumen
              ("stirn", {"A": {}}, False, "stirn")]                     # leer = wie Modell
    for modell, ende, um, soll in faelle:
        ist = art_nach(modell, ende, um)
        check(f"Modell {modell}, Stabende {ende}{' (umgekehrt)' if um else ''}: {soll}", ist == soll, ist)


def test_speichern_laden():
    print("\n--- 6. Speichern und Laden ---")
    m = quader(h=0.01)
    fuss, kopf, _e = zugstab(m)
    m.stabeinleitung = Stabeinleitung("ring", 0.006, 0.016)
    m.members["S1"].einleitung = {"A": {"art": "stirn"}}
    fugen.stabenden_koppeln(m, [])
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "a.json")
        m.save(p)
        m2 = Model.load(p)
        sk1 = [x for x in m.starrkoerper if SE.ist_verteilkopplung(x)]
        sk2 = [x for x in m2.starrkoerper if SE.ist_verteilkopplung(x)]
        check("Modelleinstellung kommt zurueck (Kreisring 6/16 mm)",
              m2.stabeinleitung == Stabeinleitung("ring", 0.006, 0.016), str(m2.stabeinleitung))
        check("Einstellung je Stabende kommt zurueck", m2.members["S1"].einleitung == {"A": {"art": "stirn"}},
              str(m2.members["S1"].einleitung))
        check("die verteilende Kopplung kommt mit Knoten und Gewichten zurueck",
              len(sk2) == 1 and sk2[0].slaves == sk1[0].slaves and sk2[0].gewichte == sk1[0].gewichte
              and sk2[0].kommentar == sk1[0].kommentar, sk2[0].kommentar if sk2 else "")
        m2.save(os.path.join(d, "b.json"))
        check("Laden und wieder Speichern aendert nichts", open(p, "rb").read() == open(os.path.join(d, "b.json"), "rb").read())
        # ohne Einstellung: kein neuer Schluessel
        alt = quader(h=0.01)
        zugstab(alt)
        fugen.stabenden_koppeln(alt, [])
        q = os.path.join(d, "alt.json")
        alt.save(q)
        dd = json.load(open(q, encoding="utf-8"))
        check("ohne Einstellung: kein Schluessel 'stabeinleitung', kein 'einleitung' am Stab",
              "stabeinleitung" not in dd and all("einleitung" not in x for x in dd["members"]))
        Model.load(q).save(os.path.join(d, "alt2.json"))
        check("ohne Einstellung: Laden und Speichern bitgleich",
              open(q, "rb").read() == open(os.path.join(d, "alt2.json"), "rb").read())


def test_kontaktrand():
    print("\n--- 7. Stirnflaeche mit Kontaktrand (gebundene Mitten) ---")
    from tests.test_fugen import kontaktbedingung, zwei_bloecke, _flaechenknoten
    m = zwei_bloecke("gemeinsam", ordnung=2)
    kb = kontaktbedingung(m, "gemeinsam", tangential="rigid")
    fugen.kontaktfuge_ausfuehren(m, kb, [])
    sec = rund(m)
    fuss = m.add_node(1.0, 0.5, 1.5)               # Mitte der Seitenflaeche x = 1 des oberen Wuerfels
    kopf = m.add_node(1.3, 0.5, 1.5)
    e = m.add_element("truss", [fuss, kopf], "S235", sec, group="Zug")
    m.add_member("S1", [e])
    for i in _flaechenknoten(m, 0.0):
        m.fix(i, [0, 1, 2])
    m.fix(kopf, [1, 2])
    lc = m.add_load_case("LF1")
    lc.gravity = [0, 0, 0]
    m.add_geometrielast("Dach", 1e6, "flaeche", case="LF1")
    m.lasten_verteilen()
    lc.nodal_loads.append(NodalLoad(kopf, [10e3, 0, 0, 0, 0, 0]))
    m.stabeinleitung = Stabeinleitung("stirn")
    log = []
    fugen.stabenden_koppeln(m, log)
    sk = [x for x in m.starrkoerper if SE.ist_verteilkopplung(x)]
    from statik3d import assemble as asm
    asm.mittelknoten_auf_sehne(m)
    bind = {int(t[0]) for t in asm.mittelknoten_bindungen(m)}
    wk = SE.wirksame_gewichte(m, sk[0]) if sk else {}
    print(f"    Stirnflaeche {len(sk[0].slaves) if sk else 0} Knoten, davon gebundene Mitten "
          f"{len(set(sk[0].slaves) & bind) if sk else 0}, ausgeschlossen {wk.get('ausgeschlossen')}; Schwerpunkt "
          f"neben der Achse vor dem Ausgleich {wk.get('abstand_vorher', 0) * 1e3:.4f} mm, danach "
          f"{wk.get('abstand_nachher', 0) * 1e3:.2e} mm, groesste Aenderung eines Gewichts "
          f"{wk.get('aenderung', 0) * 100:.2f} %")
    check("die Stirnflaeche hat gebundene Mitten am Kontaktrand, sie sind ausgeschlossen",
          sk and wk.get("ausgeschlossen", 0) > 0 and not (set(wk["slaves"].tolist()) & bind),
          f"{wk.get('ausgeschlossen')} ausgeschlossen")
    check("Summe der wirksamen Gewichte 1", sk and abs(float(np.sum(wk["w"])) - 1.0) < 1e-12)
    check("der Ausschluss verschiebt den Schwerpunkt (vorher > 1 mm neben der Achse) ...",
          wk.get("abstand_vorher", 0) > 1e-3, f"{wk.get('abstand_vorher', 0) * 1e3:.3f} mm")
    check("... der Ausgleich legt ihn zurueck auf die Stabachse (Restabstand < 1e-9 mm)",
          wk.get("abstand_nachher", 1) < 1e-12, f"{wk.get('abstand_nachher', 0) * 1e3:.2e} mm")
    try:
        r = solver.solve_static(m, case="LF1")
        fehler = ""
    except Exception as ex:                           # noqa: BLE001
        r, fehler = None, f"{type(ex).__name__}: {ex}"
    check("die Rechnung laeuft (kein Abbruch an gebundenen Mitten)", r is not None, fehler[:150])
    if r is None:
        return
    info = r.info.get("stabenden_kraftsumme") or {}
    z = (info.get("je_stabende") or [{}])[0]
    print(f"    F_kopplung {np.round(z.get('F_kopplung', []), 6)} N, M_kopplung {np.round(z.get('M_kopplung', []), 6)} Nm "
          f"um den Durchstosspunkt, dF {z.get('dF', float('nan')):.3e}, dM {z.get('dM', float('nan')):.3e}, "
          f"Toleranz {z.get('toleranz', float('nan')):.3e}")
    check("Kontaktrand: Kraftsumme 10 kN und Moment um den Durchstosspunkt null, in der Toleranz",
          info.get("geprueft") == 1 and not info.get("abweichend") and abs(z["F_kopplung"][0] - 10e3) < 1e-3
          and np.linalg.norm(z["M_kopplung"]) < 1e-3, f"{z.get('F_kopplung', [0])[0]:.6f} N")
    check("Kontakt konvergiert", solver.kontakt_konvergiert(r.info) if hasattr(solver, "kontakt_konvergiert") else True)


def test_hinweise_und_spitzen():
    print("\n--- 8. Hinweise und Erkennung der Spannungsspitzen ---")
    m = quader(h=0.01)
    lagern_frei(m)
    fuss, kopf, _e = zugstab(m)
    fugen.stabenden_koppeln(m, [])
    h = SE.hinweis(m)
    check("Hinweis an 1-3 Knoten: „1 Stabende hängt an … Volumenknoten – verteilende Einleitung …“",
          h.startswith("1 Stabende hängt an") and "verteilende Einleitung über die Stirnfläche möglich "
          "(Modelleinstellung oder je Stabende)" in h, h)
    bef = diagnose.abnahme(m, warnungen=True)
    zeilen = [b.text for b in bef if b.pruefung == SE.PRUEFUNG]
    check("Netzabnahme (Rechenstart): der Hinweis als WARNUNG, nichts umgestellt",
          len(zeilen) == 1 and zeilen[0] == h and m.stabeinleitung.art == "punkt"
          and not any(SE.ist_verteilkopplung(x) for x in m.starrkoerper), zeilen[0] if zeilen else "")
    st = [s for s in spitzenstellen.kandidaten(m, zonen=False) if s["quelle"] == spitzenstellen.STABENDE]
    check("an 1-3 Knoten erkennt spitzenstellen das Stabende als Punkt", len(st) == 1 and st[0]["art"] == "Punkt",
          str([(s["art"], s["n_knoten"]) for s in st]))
    m.stabeinleitung = Stabeinleitung("stirn")
    fugen.stabenden_koppeln(m, [])
    st = [s for s in spitzenstellen.kandidaten(m, zonen=False)
          if s["quelle"] in (spitzenstellen.STABENDE, spitzenstellen.STARRKOERPER)]
    check("verteilt eingeleitet: keine Stelle mehr - eine Flaeche, kein Punkt", not st,
          str([(s["quelle"], s["art"]) for s in st]))
    check("verteilt eingeleitet: kein Hinweis mehr", SE.hinweis(m) == "", SE.hinweis(m))
    # Import ohne Netz: integrierter Knoten auf einer Randflaeche
    ohne = Model()
    ohne.add_material(Material.steel("S235"))
    ohne.add_nodes(np.array([[0, 0, 0], [A, 0, 0], [A, B, 0], [0, B, 0],
                             [0, 0, C], [A, 0, C], [A, B, C], [0, B, C]], float))
    b = Bauer(ohne)
    R = [[b.linie(o + i, o + (i + 1) % 4) for i in range(4)] for o in (0, 4)]
    V = [b.linie(i, i + 4) for i in range(4)]
    ohne.add_flaeche("Boden", R[0], material="S235")
    ohne.add_flaeche("Deckel", R[1], material="S235")
    for i in range(4):
        ohne.add_flaeche(f"M{i}", [R[0][i], V[(i + 1) % 4], R[1][i], V[i]], material="S235")
    ohne.add_koerper("V1", ["Boden", "Deckel"] + [f"M{i}" for i in range(4)], material="S235")
    f_, k_, _e = zugstab(ohne)
    ohne.flaechen["Deckel"].integrierte_knoten.append(f_)
    h2 = SE.hinweis(ohne)
    check("ohne Netz (Import): „1 Stabende liegt auf Volumen und hängt nach dem Vernetzen an 1–3 Volumenknoten …“",
          h2.startswith("1 Stabende liegt auf Volumen und hängt nach dem Vernetzen an 1–3 Volumenknoten"), h2)
    from statik3d import importers
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "ohne.json")
        ohne.save(p)
        log = []
        importers.import_file(p, log=log)
    check("der Import nennt den Hinweis im Protokoll", any(h2 in z for z in log),
          next((z for z in log if "Stabende" in z), "")[:150])


def main():
    tests = [test_stirnflaeche_zug, test_kraftsumme, test_moment, test_kreisring, test_vorrang,
             test_speichern_laden, test_kontaktrand, test_hinweise_und_spitzen]
    erg = None
    for t in tests:
        try:
            if t is test_stirnflaeche_zug:
                erg = t()
            elif t is test_kraftsumme:
                if erg is None:
                    raise RuntimeError("Probe 1 fehlt")
                t(erg)
            else:
                t()
        except Exception as ex:      # noqa: BLE001
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
