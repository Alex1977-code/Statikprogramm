"""
Wind auf Schalen wirkt in Windrichtung, auf Volumen und shell8 mit Rollen (A1, A2, 09.11.2026).

Befunde der Pruefagenten vom 09.11.2026:

A1 Der Windgenerator liefert p „positiv drueckt in den Koerper, gegen die
   Aussennormale“; die Schalenlast setzt p in Richtung der Elementnormalen an.
   An Schalen wirkten Luvdruck, Leesog und Dachsog darum gegen den Wind:
   Gebaeude 10 x 20 x 8 m, Wind +x, ΣF (−135; 0; −127) kN statt
   (+135; 0; +127) kN. Die Kontrollsumme zaehlte umgekehrt und passte zur
   Norm, darum fiel es nicht auf. Zudem hingen Luv und Lee an der
   Knotenreihenfolge der Flaeche.
A2 Rollen und Kontrollsumme kannten nur shell3/shell4: an Volumenrandflaechen
   und shell8 bekam jede Flaeche „seite“, die Kontrollsumme meldete 0,00 kN.

Aufruf:  python -m tests.test_wind_richtung
"""
import contextlib
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from statik3d import mesher, solver, wind as wm                         # noqa: E402
from statik3d.model import Material, Model, ShellProp                    # noqa: E402

RESULTS = []
D, B, H = 10.0, 20.0, 8.0


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK  ' if ok else 'FAIL'} {name:<78} {detail}")
    return bool(ok)


def neues_modell(ordnung=1):
    m = Model("Wind")
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("t10", 0.010))
    m.netz.ordnung = ordnung
    return m


def platte(m, name, ecken):
    base = m.nn
    m.add_nodes(np.asarray(ecken, float))
    lin = []
    for i in range(4):
        nm = f"{name}_L{i}"
        m.add_line(nm, [base + i, base + (i + 1) % 4])
        lin.append(nm)
    m.add_flaeche(name, lin, material="S235", dicke="t10")


def schalenbau(nach_aussen=True, ordnung=1):
    m = neues_modell(ordnung)
    W = {
        "Luv": [[0, 0, 0], [0, 0, H], [0, B, H], [0, B, 0]],      # n = -x
        "Lee": [[D, 0, 0], [D, B, 0], [D, B, H], [D, 0, H]],      # n = +x
        "S1": [[0, 0, 0], [D, 0, 0], [D, 0, H], [0, 0, H]],       # n = -y
        "S2": [[0, B, 0], [0, B, H], [D, B, H], [D, B, 0]],       # n = +y
        "Dach": [[0, 0, H], [D, 0, H], [D, B, H], [0, B, H]],     # n = +z
    }
    for name, E in W.items():
        platte(m, name, E if nach_aussen else E[::-1])
    with contextlib.redirect_stdout(io.StringIO()):
        mesher.modell_vernetzen(m, log=[], workers=1)
    return m, ["Luv", "Lee", "S1", "S2", "Dach"]


def volumenbau(teilung):
    m = neues_modell()
    P = np.array([[0, 0, 0], [D, 0, 0], [D, B, 0], [0, B, 0],
                  [0, 0, H], [D, 0, H], [D, B, H], [0, B, H]], float)
    m.add_nodes(P)
    z = {"i": 0}

    def linie(a, b):
        z["i"] += 1
        m.add_line(f"L{z['i']}", [a, b])
        return f"L{z['i']}"
    R = [[linie(o + i, o + (i + 1) % 4) for i in range(4)] for o in (0, 4)]
    V = [linie(i, i + 4) for i in range(4)]
    m.add_flaeche("Boden", R[0], material="S235")
    m.add_flaeche("Dach", R[1], material="S235")
    for i in range(4):
        m.add_flaeche(f"M{i}", [R[0][i], V[(i + 1) % 4], R[1][i], V[i]], material="S235")
    k = m.add_koerper("K", ["Boden", "Dach", "M0", "M1", "M2", "M3"], material="S235")
    k.teilung = [teilung] * 3
    with contextlib.redirect_stdout(io.StringIO()):
        mesher.modell_vernetzen(m, log=[], workers=1)
    return m, ["M0", "M1", "M2", "M3", "Dach"]


def wind(m, flaechen):
    w = wm.Wind("W1", flaechen=flaechen, richtung=[1.0, 0.0, 0.0])
    kw = wm.lasten_erzeugen(m, w)
    F = np.asarray(solver.case_loads(m, {w.lastfall: 1.0}, None)[0], float).reshape(-1, 6)[:, :3].sum(axis=0)
    return F, kw


def hand_fx(w=None):
    """Zweiter Weg: (c_pe,D − c_pe,E) · b · ∫ q_p(z) dz ueber die Wandhoehe -
    die Zonen- und Profilfunktionen der Norm, ohne Elemente und Lastverteilung."""
    w = w or wm.Wind("W1", flaechen=[], richtung=[1.0, 0.0, 0.0])
    z = np.linspace(0.0, H, 4001)
    q = np.array([wm.q_p(max(zz, 0.0), w) for zz in z])
    integral = float(np.sum(0.5 * (q[1:] + q[:-1]) * np.diff(z)))
    return w.c_scd * (wm.cpe_luv(H / D) - wm.cpe_lee(H / D)) * B * integral


def test_schalen_wirken_in_windrichtung():
    fx_hand = hand_fx()
    for aussen in (True, False):
        m, fl = schalenbau(aussen)
        F, kw = wind(m, fl)
        art = "Normalen aussen" if aussen else "Normalen innen"
        # Ohne den Umbau: Fx = −135 kN (aussen) bzw. Luv und Lee vertauscht (innen)
        check(f"Schalenbau, {art}: Rollen luv/lee/dach unabhaengig von der Eingaberichtung",
              kw["rollen"]["Luv"] == "luv" and kw["rollen"]["Lee"] == "lee" and kw["rollen"]["Dach"] == "dach",
              str({k: kw["rollen"][k] for k in ("Luv", "Lee", "Dach")}))
        check(f"Schalenbau, {art}: Fx in Windrichtung = (c_pe,D − c_pe,E)·b·∫q_p dz (2 %)",
              F[0] > 0 and abs(F[0] - fx_hand) / fx_hand < 0.02,
              f"{F[0] / 1e3:.2f} kN, Hand {fx_hand / 1e3:.2f} kN")
        check(f"Schalenbau, {art}: Dachsog hebt (Fz > 0)", F[2] > 0, f"{F[2] / 1e3:.2f} kN")
        check(f"Schalenbau, {art}: Kontrollsumme = Lastvektor",
              np.allclose(np.asarray(kw["kontrolle"]["F"]), F, rtol=1e-6, atol=1e-3),
              f"{np.round(np.asarray(kw['kontrolle']['F']) / 1e3, 2)} kN")


def test_shell8_und_volumen():
    m, fl = schalenbau(True)
    F4, _ = wind(m, fl)
    m8, fl8 = schalenbau(True, ordnung=2)
    F8, kw8 = wind(m8, fl8)
    typen = {e.typ for e in m8.elements}
    check("quadratische Schalen: Rollen luv/lee/dach statt alle „seite“",
          kw8["rollen"]["Luv"] == "luv" and kw8["rollen"]["Lee"] == "lee" and kw8["rollen"]["Dach"] == "dach",
          f"{sorted(typen)} {kw8['rollen']}")
    check("quadratische Schalen: ΣF wie lineare Schalen (1 %), Kontrollsumme nicht 0",
          np.allclose(F8, F4, rtol=0.01) and kw8["kontrolle"]["n"] > 0
          and np.allclose(np.asarray(kw8["kontrolle"]["F"]), F8, rtol=1e-6, atol=1e-3),
          f"{np.round(F8 / 1e3, 2)} gegen {np.round(F4 / 1e3, 2)} kN")
    mv, flv = volumenbau(16)
    Fv, kwv = wind(mv, flv)
    check("Volumen: Rollen luv (x = 0), lee (x = 10), dach",
          kwv["rollen"]["M3"] == "luv" and kwv["rollen"]["M1"] == "lee" and kwv["rollen"]["Dach"] == "dach",
          str(kwv["rollen"]))
    check("Volumen 16 x 16 x 16: ΣF wie der Schalenbau (Zonen am Seitenschwerpunkt, 1 %)",
          np.allclose(Fv, F4, rtol=0.01), f"{np.round(Fv / 1e3, 2)} gegen {np.round(F4 / 1e3, 2)} kN")
    check("Volumen: Kontrollsumme = Lastvektor (bisher 0,00 kN)",
          np.allclose(np.asarray(kwv["kontrolle"]["F"]), Fv, rtol=1e-6, atol=1e-3),
          f"{kwv['kontrolle']['betrag'] / 1e3:.2f} kN")


def test_zusammenhaengende_huelle():
    """Waende und Dach teilen ihre Linien (so baut man es): die Aussenseite kommt
    aus der Mitte der zusammenhaengenden Huelle, mit gemischt eingegebenen
    Linienrichtungen."""
    m = neues_modell()
    P = np.array([[0, 0, 0], [D, 0, 0], [D, B, 0], [0, B, 0],
                  [0, 0, H], [D, 0, H], [D, B, H], [0, B, H]], float)
    m.add_nodes(P)
    z = {"i": 0}

    def linie(a, b):
        z["i"] += 1
        m.add_line(f"L{z['i']}", [a, b])
        return f"L{z['i']}"
    R = [[linie(o + i, o + (i + 1) % 4) for i in range(4)] for o in (0, 4)]
    V = [linie(i, i + 4) for i in range(4)]
    m.add_flaeche("Dach", R[1][::-1], material="S235", dicke="t10")          # gedreht eingegeben
    for i in range(4):
        lin = [R[0][i], V[(i + 1) % 4], R[1][i], V[i]]
        m.add_flaeche(f"M{i}", lin if i % 2 else lin[::-1], material="S235", dicke="t10")
    with contextlib.redirect_stdout(io.StringIO()):
        mesher.modell_vernetzen(m, log=[], workers=1)
    F, kw = wind(m, ["M0", "M1", "M2", "M3", "Dach"])
    _m4, fl4 = schalenbau(True)
    F4, _ = wind(_m4, fl4)
    check("zusammenhaengende Schalenhuelle: Rollen luv (x = 0), lee (x = 10), dach",
          kw["rollen"]["M3"] == "luv" and kw["rollen"]["M1"] == "lee" and kw["rollen"]["Dach"] == "dach",
          str(kw["rollen"]))
    check("zusammenhaengende Schalenhuelle: ΣF wie der Schalenbau aus Einzelwaenden (1 %)",
          np.allclose(F, F4, rtol=0.01), f"{np.round(F / 1e3, 2)} gegen {np.round(F4 / 1e3, 2)} kN")


def test_verfahrenstabelle():
    """Alte Ergebnisse mit Wind auf Flaechen: „Ergebnis möglicherweise betroffen“."""
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("wind_flaechen")
    m, fl = schalenbau(True)
    ohne = neues_modell()
    wind(m, fl)
    check("Verfahrenstabelle: „wind_flaechen“ Fehlerkorrektur Stand 8, betrifft nur Modelle mit Wind auf Flächen",
          mk is not None and mk.wechsel[-1].art == rv.FEHLERKORREKTUR and mk.wechsel[-1].stand == 8
          and rv.VERFAHRENSSTAND >= 8 and mk.betrifft(m) and not mk.betrifft(ohne))


def main():
    for t in (test_schalen_wirken_in_windrichtung, test_shell8_und_volumen, test_zusammenhaengende_huelle,
              test_verfahrenstabelle):
        try:
            t()
        except Exception as ex:               # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((f"{t.__name__} (Ausnahme: {ex})", False))
    nok = sum(1 for _n, ok in RESULTS if ok)
    print("=" * 92)
    print(f"Ergebnis: {nok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    sys.exit(main())
