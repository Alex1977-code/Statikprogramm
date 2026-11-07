"""Gleitweg-Speicher der Reibungstangente (17.10.2026, kontakt/pendeln-rt).

Befund: die Rueckabbildung rechnete mit dem ganzen Tangentialweg dt = C_t u seit der
Ausgangslage. Nach einer Stufe mit Gleiten (hier der Spannschritt) zog die Haftfeder
den Knoten im Lastfall zur Ausgangslage zurueck; die Reibkraft trieb die Bewegung an,
statt ihr entgegenzuwirken (negative Dissipation), und wo der Klotz haften muesste,
glitt er weiter.

Pruefkoerper: Klotz 0,4 m (tet4, 4 x 4 x 4) mit Reibung mu 0,3 auf einer starren, festen
Platte. Ein flacher Anker mit Endvorspannung 100 kN an der Seite x = +0,2 nahe der
Sohle zieht ihn im Spannschritt in +x gegen eine Feder (Stab zur Wand bei x = -1,2);
im Lastfall wirkt zusaetzlich eine Querkraft H in -x. Am Ende des Spannschritts gleitet
der Klotz, die Reibkraft liegt an der Grenze (-11,1 kN). Mit H = 20 kN braucht der
Klotz +8,9 kN Reibung, weniger als die Grenze: er haftet. Mit H = 80 kN gleitet er
zurueck, die Reibung wirkt in +x.

Pruefgroesse: die Dissipation je Reibknoten und Stufe, D = -f . du >= 0 (f die
Reibkraft auf den Knoten am Ende der Stufe, du sein Weg in der Stufe; die Platte ist
fest, der Weg ist der Gleitweg).

Aufruf:  python -m tests.test_gleitweg
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np                                                  # noqa: E402

from statik3d import contact, mesher, solver                        # noqa: E402
from statik3d.model import Material, Model, Section, ShellProp      # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:86s} {str(detail)[:200]}")
    return ok


def klotz(H, laststufen=None):
    m = Model("Klotz mit Reibung")
    m.add_material(Material("S235", E=210e9, nu=0.3, rho=0.0))
    m.add_material(Material("Starr", E=210e12, nu=0.3, rho=0.0))
    m.add_shell_prop(ShellProp("t = 50 mm", 0.05))
    pl = mesher.grid_plate(m, "Starr", "t = 50 mm", 1.0, 1.0, 2, 2, origin=(-0.5, -0.5, 0))
    for k in pl.ravel():
        m.fix(int(k), "all")
    platte = list(range(len(m.elements)))
    box = mesher.grid_box(m, "S235", 0.4, 0.4, 0.4, 4, 4, 4, origin=(-0.2, -0.2, 0.0), typ="tet4")
    unten = [int(k) for k in box[:, :, 0].ravel()]
    m.add_contact_pair("Klotz/Platte", unten, platte, mu=0.3)
    A = int(box[-1, 2, 1])                  # Seite x = +0,2, z = 0,1
    B = int(box[0, 2, 2])                   # Seite x = -0,2, halbe Hoehe
    P = m.add_node(1.2, 0.0, -0.3)
    W = m.add_node(-1.2, 0.0, 0.2)
    m.fix(P, "all")
    m.fix(W, "all")
    m.add_section(Section("Anker", np.pi * 0.02 ** 2 / 4, 1e-8, 1e-8, 2e-8))
    m.add_section(Section("Feder", 2.6e-4, 1e-8, 1e-8, 2e-8))
    ea = m.add_element("truss", [A, P], "S235", "Anker")
    m.add_member("S1", [ea])
    m.add_element("truss", [B, W], "S235", "Feder")
    lc = m.add_load_case("LF1")
    lc.gravity = [0, 0, 0]
    m.add_vorspannung("S1", 100e3, case="LF1", sollkraft=True)
    if H:
        m.load_node(B, Fx=-H)
    m.active_case = "LF1"
    m.plastizitaet.an = False
    if laststufen:
        # Plastizitaet mit Laststufen (nichts fliesst: f_y hoch) - die Stufen des Lastfalls
        m.materials["S235"].fy = 1e12
        m.plastizitaet.an = True
        m.plastizitaet.laststufen = int(laststufen)
    return m, unten


def _stand(res, nn):
    """(u (nn, 3), Kontaktkraft je Knoten (nn, 3), {Knoten: (aktiv, gleitet)}) eines Ergebnisses."""
    u = np.asarray(res.u, float)[:nn * 6].reshape(-1, 6)[:, :3].copy()
    f = np.zeros((nn, 3))
    st = {}
    for c in res.contact or []:
        k = int(c["node"])
        f[k] += np.asarray(c["F_vek"], float)
        st[k] = (c["status"] != "offen", c["status"] == "Gleiten")
    return u, f, st


def rechnen(m):
    """Loesen; Rueckgabe das Ergebnis und die Staende am Ende des Spannschritts und
    des Lastfalls."""
    r = solver.solve_static(m, workers=1)
    vz = getattr(r, "vorspannzustaende", None) or {}
    sp = (vz.get("spannen") or [None])[-1]
    return r, [_stand(sp, m.nn), _stand(r, m.nn)]


def dissipation(vor, nach, knoten):
    """{Knoten: D = -f . du} der aktiven Knoten in der Stufe von ``vor`` nach ``nach``
    (in der Ebene; f am Ende der Stufe)."""
    u0 = np.zeros_like(nach[0]) if vor is None else vor[0]
    out = {}
    for k in knoten:
        if not nach[2].get(k, (False, False))[0]:
            continue
        du = nach[0][k, :2] - u0[k, :2]
        out[k] = -float(nach[1][k, :2] @ du)
    return out


def bewerten(H, laststufen=None):
    m, unten = klotz(H, laststufen)
    r, laeufe = rechnen(m)
    sp, lf = laeufe
    akt = [k for k in unten if lf[2].get(k, (False, False))[0]]
    gl = [k for k in akt if lf[2][k][1]]
    D_lf = dissipation(sp, lf, unten)
    D_sp = dissipation(None, sp, unten)
    du = np.array([lf[0][k, 0] - sp[0][k, 0] for k in akt])
    fx = float(lf[1][akt, 0].sum())
    return {"r": r, "laeufe": laeufe, "akt": akt, "gl": gl, "D_lf": D_lf, "D_sp": D_sp,
            "du": du, "fx": fx, "fx_sp": float(sp[1][unten, 0].sum()), "fz": float(abs(lf[1][unten, 2].sum())),
            "konv": bool(r.info.get("contact_converged"))}


def _neg(D, F_ref=1e3, weg_ref=1e-6):
    """Knoten mit negativer Dissipation (unter -F_ref * weg_ref = -1 mJ)."""
    return [k for k, v in D.items() if v < -F_ref * weg_ref]


def test_ruecknahme():
    print("\n--- Rücknahme (ohne Gleitweg-Speicher): der Befund ---")
    alt = contact.GLEITWEG_SPEICHER
    try:
        contact.GLEITWEG_SPEICHER = False
        e = bewerten(20e3)
    finally:
        contact.GLEITWEG_SPEICHER = alt
    check("H = 20 kN ohne Speicher: der Klotz gleitet weiter in -x, die Reibkraft treibt ihn "
          "(negative Dissipation)",
          len(e["gl"]) > 0 and len(_neg(e["D_lf"])) > 0 and e["du"].mean() < -1e-4,
          f"gleitend {len(e['gl'])}/{len(e['akt'])}, negativ {len(_neg(e['D_lf']))}, "
          f"Weg {1e3 * e['du'].mean():+.4f} mm, Reibkraft x {e['fx'] / 1e3:+.2f} kN")


def test_haften():
    print("\n--- H = 20 kN: der Klotz haftet im Lastfall ---")
    e = bewerten(20e3)
    check("Spannschritt: der Klotz gleitet in +x, die Reibkraft wirkt dagegen (D ≥ 0 je Knoten)",
          e["fx_sp"] < 0 and not _neg(e["D_sp"]) and len(e["D_sp"]) > 0,
          f"Reibkraft x {e['fx_sp'] / 1e3:+.2f} kN, negativ {len(_neg(e['D_sp']))} von {len(e['D_sp'])}")
    # Der Klotz haelt als Ganzes; Knoten, an denen die Umlagerung die Grenze erreicht,
    # duerfen oertlich gleiten (gemessen 17.10.2026: 8 von 11 an der Grenze, Weg bis
    # 0,16 um) - Coulomb erlaubt das, der Klotz bewegt sich nicht
    kap = 0.3 * e["fz"]
    check("Lastfall: konvergiert, der Klotz bewegt sich nicht (Weg in der Stufe unter 1 µm)",
          e["konv"] and float(np.abs(e["du"]).max()) < 1e-6,
          f"örtlich an der Grenze {len(e['gl'])}/{len(e['akt'])}, |Weg| bis {1e6 * float(np.abs(e['du']).max()):.3f} µm")
    check("… Reibkraft in +x unter der Kapazität μ ΣFn (die Querkraft nimmt die Vorspannung zurück)",
          0.0 < e["fx"] < kap, f"Reibkraft x {e['fx'] / 1e3:+.2f} kN, μ ΣFn {kap / 1e3:.2f} kN")
    check("… Dissipation je Knoten ≥ 0", not _neg(e["D_lf"]), f"negativ {len(_neg(e['D_lf']))}")


def test_gleiten_zurueck():
    print("\n--- H = 80 kN: der Klotz gleitet zurück, die Reibung wirkt in +x ---")
    e = bewerten(80e3)
    check("Lastfall: konvergiert, alle aktiven gleiten in -x, Reibkraft in +x",
          e["konv"] and len(e["gl"]) == len(e["akt"]) > 0 and e["du"].max() < 0 and e["fx"] > 0,
          f"gleitend {len(e['gl'])}/{len(e['akt'])}, Weg {1e3 * e['du'].mean():+.4f} mm, "
          f"Reibkraft x {e['fx'] / 1e3:+.2f} kN")
    check("… Dissipation je Knoten ≥ 0 in beiden Stufen",
          not _neg(e["D_lf"]) and not _neg(e["D_sp"]),
          f"negativ Lastfall {len(_neg(e['D_lf']))}, Spannschritt {len(_neg(e['D_sp']))}")


def test_laststufen():
    print("\n--- Laststufen der Plastizität im Lastfall (2 Stufen, nichts fließt) ---")
    e1 = bewerten(20e3)
    e2 = bewerten(20e3, laststufen=2)
    du = float(np.abs(np.asarray(e2["r"].u) - np.asarray(e1["r"].u)).max())
    ref = float(np.abs(np.asarray(e1["r"].u)).max())
    check("H = 20 kN in zwei Laststufen: haftet ebenso, u und Status wie in einer Stufe (u bis 1e-3)",
          e2["konv"] and len(e2["gl"]) == len(e1["gl"]) and du <= 1e-3 * ref,
          f"an der Grenze {len(e2['gl'])} (eine Stufe {len(e1['gl'])}), max |Δu| {du:.2e} m bei {ref:.2e} m")
    aufrufe = []
    alt = solver._KontaktImNewton.stufe_fertig

    def zaehlen(self):
        aufrufe.append(1)
        return alt(self)
    solver._KontaktImNewton.stufe_fertig = zaehlen
    try:
        e3 = bewerten(80e3, laststufen=2)
    finally:
        solver._KontaktImNewton.stufe_fertig = alt
    e4 = bewerten(80e3)
    d3 = float(np.abs(np.asarray(e3["r"].u) - np.asarray(e4["r"].u)).max())
    r4 = float(np.abs(np.asarray(e4["r"].u)).max())
    # je Rechnung mit zwei Laststufen einmal, nach Stufe 1 (nicht nach der letzten): die drei
    # Spannstufen (spannstufen = 3) rechnen ebenfalls plastisch in zwei Stufen, dazu der Lastfall
    check("H = 80 kN: der Gleitweg wird nach Stufe 1 fortgeschrieben (3 Spannstufen + Lastfall), "
          "u wie in einer Stufe (bis 1e-3)",
          len(aufrufe) == 4 and d3 <= 1e-3 * r4, f"fortgeschrieben {len(aufrufe)}-mal, max |Δu| {d3:.2e} m bei {r4:.2e} m")
    check("H = 80 kN in zwei Laststufen: gleitet zurück (alle aktiven gleiten), Dissipation je Knoten ≥ 0",
          e3["konv"] and e3["du"].max() < 0 and e3["fx"] > 0 and not _neg(e3["D_lf"])
          and len(e3["gl"]) == len(e3["akt"]) > 0,
          f"gleitend {len(e3['gl'])}/{len(e3['akt'])}, Reibkraft x {e3['fx'] / 1e3:+.2f} kN, "
          f"negativ {len(_neg(e3['D_lf']))}")


def test_fremder_warmstart():
    print("\n--- Warmstart aus einem anderen Lastfall bringt keinen Gleitweg mit ---")
    from statik3d import contact as ct
    cs = ct.ContactSystem.__new__(ct.ContactSystem)
    cs.cons = []
    z = {"gleitweg": [np.array([1.0, 2.0])], "gleitweg_ende": [np.array([3.0, 4.0])]}
    w = solver.gleitweg_fortschreiben(z)
    check("gleitweg_fortschreiben: Ende wird Anfang, Marke Lastweg, das Original bleibt",
          w is not z and w.get("lastweg") is True and np.allclose(w["gleitweg"][0], [3.0, 4.0])
          and np.allclose(z["gleitweg"][0], [1.0, 2.0]) and "lastweg" not in z, str(w.get("gleitweg")))


def test_warmstart_uebernahme():
    print("\n--- Welcher Start den Gleitweg mitbringt (solve_with_contact) ---")
    m, _unten = klotz(80e3)
    system = solver.StaticSystem(m, 1)
    F = solver.case_loads(m, {"LF1": 1.0})[0]
    out = solver.solve_with_contact(m, system, F)
    z = dict(out[4]["contact_state"])
    cs = system._kontaktsystem
    n = len(cs.cons)
    z["gleitweg"] = [np.array([1e-4, 0.0]) for _ in range(n)]
    erg = {}
    for name, kw in (("fremd", dict(start=z, fortsetzung=False)),
                     ("fortgesetzt", dict(start=z, fortsetzung=True)),
                     ("Lastweg", dict(start=dict(z, lastweg=True), fortsetzung=False))):
        solver.solve_with_contact(m, system, F, **kw)
        erg[name] = sum(1 for g in cs.gleitweg() if g is not None)
    check("fremder Zustand ohne, fortgesetzter und Lastweg (Spannschritt) mit Gleitweg",
          erg["fremd"] == 0 and erg["fortgesetzt"] == n and erg["Lastweg"] == n, str(erg))
    sp = dict(out[4]["contact_state"])
    check("die Sicherung trägt den Gleitweg am Ende des Laufs (gleitweg_ende) je Bedingung",
          len(sp.get("gleitweg_ende") or []) == n
          and sum(1 for g in sp["gleitweg_ende"] if g is not None) > 0, f"{n} Bedingungen")


def test_rechenverfahren():
    print("\n--- Fehlerkorrektur im Rechenverfahren (Stand 4) ---")
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("gleitweg")
    m, _u = klotz(20e3)
    m2, _u2 = klotz(20e3)
    for lc in m2.load_cases.values():
        lc.vorspannungen = []                  # nur die Querkraft, eine Stufe
    m3, _u3 = klotz(20e3)
    m3.contact_pairs[0].mu = 0.0               # ohne Reibung
    check("Merkmal „gleitweg“ als Fehlerkorrektur, Stand 4 = VERFAHRENSSTAND; betrifft Reibung + Spannschritt, "
          "nicht einstufig, nicht ohne Reibung",
          mk is not None and mk.wechsel[-1].art == rv.FEHLERKORREKTUR and mk.wechsel[-1].stand == 4
          and rv.VERFAHRENSSTAND == 4 and mk.betrifft(m) and not mk.betrifft(m2) and not mk.betrifft(m3),
          f"{mk.modellmerkmal if mk else 'fehlt'}")


def main():
    test_ruecknahme()
    test_haften()
    test_gleiten_zurueck()
    test_laststufen()
    test_fremder_warmstart()
    test_warmstart_uebernahme()
    test_rechenverfahren()
    n_f = sum(1 for _n, ok in RESULTS if not ok)
    print(f"\n{len(RESULTS) - n_f} von {len(RESULTS)} Prüfungen bestanden")
    return 1 if n_f else 0


if __name__ == "__main__":
    sys.exit(main())
