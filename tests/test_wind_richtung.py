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


def hand_fx(w=None, d_geo=D):
    """Zweiter Weg: (c_pe,D − c_pe,E) · b · ∫ q_p(z) dz ueber die Wandhoehe -
    die Zonen- und Profilfunktionen der Norm, ohne Elemente und Lastverteilung.
    ``d_geo``: die Tiefe, die der Generator fuer h/d nimmt (alle Windobjekte)."""
    w = w or wm.Wind("W1", flaechen=[], richtung=[1.0, 0.0, 0.0])
    z = np.linspace(0.0, H, 4001)
    q = np.array([wm.q_p(max(zz, 0.0), w) for zz in z])
    integral = float(np.sum(0.5 * (q[1:] + q[:-1]) * np.diff(z)))
    return w.c_scd * (wm.cpe_luv(H / d_geo) - wm.cpe_lee(H / d_geo)) * B * integral


def kraft_der_flaechen(m, lastfall, flaechen):
    """Eigene Summe ueber den Lastvektor (assemble.load_vector), nur mit den
    Elementlasten auf ``flaechen`` - unabhaengig von wind.kontrollsumme."""
    from statik3d.assemble import load_vector
    from statik3d.model import LoadCase
    el = set()
    for n in flaechen:
        el |= {int(e) for e in m.flaechen[n].elemente}
    lc = LoadCase("nur_flaechen")
    lc.face_loads = [f for f in m.load_cases[lastfall].face_loads if int(f.elem) in el]
    return np.asarray(load_vector(m, lc), float)[:6 * m.nn].reshape(-1, 6)[:, :3].sum(axis=0)


BAU = {
    "Luv": [[0, 0, 0], [0, 0, H], [0, B, H], [0, B, 0]],      # n = -x
    "Lee": [[D, 0, 0], [D, B, 0], [D, B, H], [D, 0, H]],      # n = +x
    "S1": [[0, 0, 0], [D, 0, 0], [D, 0, H], [0, 0, H]],       # n = -y
    "S2": [[0, B, 0], [0, B, H], [D, B, H], [D, B, 0]],       # n = +y
    "Dach": [[0, 0, H], [D, 0, H], [D, B, H], [0, B, H]],     # n = +z
}


def einzelbau(namen, nach_aussen=True, x0=(0.0,), freie_wand=False):
    """Baukoerper aus Einzelschalen ohne gemeinsame Knoten (je x0 einer, Namen
    mit Vorsilbe A_, B_ ...), dazu wahlweise eine freie Wand 220 x 3 m bei
    x = −80 (Nachweis der Pruefagenten pruef_tmp/p4/wind2.py, wind3.py)."""
    m = neues_modell()
    koerper = []
    for k, x in enumerate(x0):
        vor = "" if len(x0) == 1 else "AB"[k] + "_"
        fl = []
        for name in namen:
            E = (np.asarray(BAU[name], float) + [x, 0.0, 0.0]).tolist()
            platte(m, vor + name, E if nach_aussen else E[::-1])
            fl.append(vor + name)
        koerper.append(fl)
    if freie_wand:
        platte(m, "FW", [[-80, -100, 0], [-80, 120, 0], [-80, 120, 3], [-80, -100, 3]])
    with contextlib.redirect_stdout(io.StringIO()):
        mesher.modell_vernetzen(m, log=[], workers=1)
    return m, koerper


def test_einzelne_flaeche():
    """Befund 5 (11.11.2026): ein Flachdach allein, Wind +x, c_pe ueberall negativ.
    Das Vorzeichen entschied je Element normale · (punkt − mitte) mit der Mitte
    in der Dachebene - Rundungsrauschen: 3 von 98 Elementen bekamen Druck nach
    unten statt Sog. Eine Wand allein war je nach Linienrichtung luv oder lee."""
    for aussen in (True, False):
        art = "Linien nach aussen" if aussen else "Linien gedreht"
        m, (fl,) = einzelbau(["Dach"], aussen)
        F, kw = wind(m, fl)
        lc = m.load_cases[kw["lastfall"]]
        falsch = sum(1 for f in lc.face_loads
                     if f.p * float(m._seitennormale_oder_schale(int(f.elem), 0)[2]) < 0)
        check(f"Dach allein, {art}: jedes Element Sog nach oben (Elemente mit Kraft nach unten)",
              falsch == 0 and len(lc.face_loads) > 0, f"{falsch} von {len(lc.face_loads)}")
        F2 = kraft_der_flaechen(m, kw["lastfall"], fl)
        check(f"Dach allein, {art}: ΣF_z > 0, Kontrollsumme = eigene Summe ueber den Lastvektor",
              F[2] > 0 and np.allclose(np.asarray(kw["kontrolle"]["F"]), F2, rtol=1e-9, atol=1e-6),
              f"Kontrolle {np.round(np.asarray(kw['kontrolle']['F']) / 1e3, 2)}, Lastvektor "
              f"{np.round(F2 / 1e3, 2)} kN")
    werte = {}
    for aussen in (True, False):
        m, (fl,) = einzelbau(["Luv"], aussen)
        F, kw = wind(m, fl)
        werte[aussen] = (kw["rollen"]["Luv"], F)
    check("Wand quer zum Wind allein: Rolle luv bei beiden Linienrichtungen, gleiche Kraft in Windrichtung",
          werte[True][0] == werte[False][0] == "luv" and werte[True][1][0] > 0
          and np.allclose(werte[True][1], werte[False][1], rtol=1e-12, atol=1e-6),
          f"{werte[True][0]}/{werte[False][0]}, Fx {werte[True][1][0] / 1e3:.2f}/{werte[False][1][0] / 1e3:.2f} kN")
    # 12.11.2026: nach DIN EN 1991-1-4 ist eine einzeln stehende Wand eine
    # freistehende Wand (7.4), ein einzelnes Dach ein freistehendes Dach (7.3)
    # - gerechnet wird weiter nach der Lage, aber mit Hinweis
    m, (fl,) = einzelbau(["Luv"], True)
    _F, kw = wind(m, fl)
    h = kw.get("hinweise") or []
    check("Wand allein: Hinweis „freistehende Wand (7.4, c_p,net nach Tab. 7.9)“, auch in der Erläuterung",
          len(h) == 1 and "freistehende Wand (7.4" in h[0] and "als freie Wand einstufen" in h[0]
          and any(z.startswith("Hinweis: ") for z in wm.erlaeuterung(m.winde[list(m.winde)[0]], kw)),
          h[0][:110] if h else "kein Hinweis")
    m, (fl,) = einzelbau(["Dach"], True)
    _F, kw = wind(m, fl)
    h = kw.get("hinweise") or []
    check("Dach allein: Hinweis „freistehendes Dach (7.3)“", len(h) == 1 and "freistehendes Dach (7.3)" in h[0],
          h[0][:110] if h else "kein Hinweis")
    m, fl = einzelbau(list(BAU), True)
    _F, kw = wind(m, fl[0] if len(fl) == 1 else fl)
    check("geschlossener Baukörper aus Einzelschalen: kein Hinweis", not kw.get("hinweise"),
          str(kw.get("hinweise"))[:110])


def test_freie_wand_verschiebt_keine_mitte():
    """Befund 6 (11.11.2026): eine freie Wand 220 x 3 m bei x = −80 im selben Wind
    schob die Mitte der Huelle aus dem Gebaeude (lasten_erzeugen nahm sie mit,
    rollen nicht): ΣF_x der Gebaeudeflaechen −44,29 statt positiv."""
    for namen in (list(BAU), ["Luv", "Lee"]):
        for aussen in (True, False):
            m, (fl,) = einzelbau(namen, aussen, freie_wand=True)
            w = wm.Wind("W1", flaechen=fl, freie_waende=["FW"], richtung=[1.0, 0.0, 0.0])
            kw = wm.lasten_erzeugen(m, w)
            F = kraft_der_flaechen(m, w.lastfall, fl)
            soll = hand_fx(d_geo=kw["d"])
            art = f"{len(fl)} Flaechen, " + ("Linien nach aussen" if aussen else "Linien gedreht")
            check(f"Gebaeude mit freier Wand, {art}: Rollen luv/lee, ΣF_x der Gebaeudeflaechen "
                  f"= (c_pe,D − c_pe,E)(h/d)·b·∫q_p dz (2 %)",
                  kw["rollen"]["Luv"] == "luv" and kw["rollen"]["Lee"] == "lee" and F[0] > 0
                  and abs(F[0] - soll) / soll < 0.02,
                  f"{F[0] / 1e3:.2f} kN, Hand {soll / 1e3:.2f} kN (d = {kw['d']:.0f} m)")


def test_zwei_baukoerper():
    """Befund 7 (11.11.2026): zwei Gebaeude aus Einzelschalen bei x = 0 und x = 30
    bekamen eine gemeinsame Mitte zwischen sich - die Leewand des vorderen war
    „luv“, die Luvwand des hinteren „lee“. Baukoerper sind Flaechen, die sich
    beruehren (geometrisch), nicht erst solche mit gemeinsamen Knoten."""
    for aussen in (True, False):
        m, (fa, fb) = einzelbau(list(BAU), aussen, x0=(0.0, 30.0))
        w = wm.Wind("W1", flaechen=fa + fb, richtung=[1.0, 0.0, 0.0])
        kw = wm.lasten_erzeugen(m, w)
        r = kw["rollen"]
        art = "Linien nach aussen" if aussen else "Linien gedreht"
        teilen = getattr(wm, "baukoerper", None)          # vor dem 11.11.2026 nicht vorhanden
        gruppen = sorted(sorted(g) for g in teilen(m, fa + fb)) if teilen else None
        check(f"zwei Baukoerper, {art}: zwei Koerper aus je fuenf Einzelschalen",
              gruppen == sorted([sorted(fa), sorted(fb)]), str(gruppen))
        check(f"zwei Baukoerper, {art}: A_Luv/B_Luv luv, A_Lee/B_Lee lee",
              r["A_Luv"] == r["B_Luv"] == "luv" and r["A_Lee"] == r["B_Lee"] == "lee",
              str({k: r[k] for k in ("A_Luv", "A_Lee", "B_Luv", "B_Lee")}))
        soll = hand_fx(d_geo=kw["d"])
        FA, FB = kraft_der_flaechen(m, w.lastfall, fa), kraft_der_flaechen(m, w.lastfall, fb)
        check(f"zwei Baukoerper, {art}: ΣF_x je Koerper = (c_pe,D − c_pe,E)(h/d)·b·∫q_p dz (2 %)",
              all(F[0] > 0 and abs(F[0] - soll) / soll < 0.02 for F in (FA, FB)),
              f"A {FA[0] / 1e3:.2f}, B {FB[0] / 1e3:.2f} kN, Hand {soll / 1e3:.2f} kN")


def _als_alte_datei(m):
    """So steht eine Windlast in einer Datei eines aelteren Programmstands: ohne
    Aussenseite (und ohne die Mitte vom 09.11.2026)."""
    n = 0
    for lc in m.load_cases.values():
        for gl in lc.geometrielasten:
            v = gl.verlauf or {}
            if v.get("art") == "wind":
                v.pop("aussen", None)
                v.pop("mitte", None)
                (v.get("geometrie") or {}).pop("mitte", None)
                n += 1
    return n


def test_alte_windlasten():
    """Befund 40 (11.11.2026): eine Windlast aus einer alten Modelldatei wirkt nach
    dem Oeffnen weiter gegen den Wind; die Ergebnisdatei einer neuen Rechnung
    trug keinen Status mehr. Jetzt: Ladehinweis, und der Status haengt am Modell
    - er bleibt nach dem Neurechnen und geht erst mit dem Neuerzeugen."""
    import tempfile
    from statik3d import ergebnisse as erg, rechenverfahren as rv
    m, fl = huelle()
    for i in np.where(np.abs(m.nodes[:, 2]) < 1e-9)[0]:
        m.fix(int(i))
    F_neu, kw = wind(m, fl)
    lf = kw["lastfall"]
    n = _als_alte_datei(m)
    d = tempfile.mkdtemp(prefix="wind_alt_")
    p = os.path.join(d, "wind_alt.json")
    m.save(p)
    m2 = Model.load(p)
    F_alt = np.asarray(solver.case_loads(m2, {lf: 1.0}, None)[0], float).reshape(-1, 6)[:, :3].sum(axis=0)
    hinw = [z for z in getattr(m2, "_ladehinweise", []) if "Windlasten neu erzeugen" in z]
    check("alte Windlasten: Ladehinweis „Windlasten neu erzeugen“ beim Oeffnen",
          n == 5 and len(hinw) == 1 and "Wind W1" in hinw[0], hinw[0] if hinw else "keiner")
    mk = rv.merkmal("wind_flaechen")
    check("alte Windlasten: Merkmal am Modell (Korrektur am Modell, betrifft)",
          mk is not None and mk.import_korrektur and mk.betrifft(m2),
          f"ΣF nach dem Oeffnen {np.round(F_alt / 1e3, 2)} kN")
    with contextlib.redirect_stdout(io.StringIO()):
        an = solver.solve_all(m2, design=False)
    st0 = str(an.info.get("verfahren_betroffen") or "")
    check("alte Windlasten, neu gerechnet (dieselbe Sitzung): Status sofort, genau einmal",
          st0.count("Windlast auf Flächen") == 1 and "Windlasten neu erzeugen" in st0 and "RFEM" not in st0,
          st0 or "kein Status")
    m2.save(p)
    erg.schreiben(erg.pfad_zu(p), m2, an)
    a2 = erg.lesen(erg.pfad_zu(p), Model.load(p))
    st = str(a2.info.get("verfahren_betroffen") or "")
    check("alte Windlasten, neu gerechnet und geoeffnet: Status bleibt, „Windlasten neu erzeugen“",
          st.count("Windlast auf Flächen") == 1 and "Windlasten neu erzeugen" in st and "RFEM" not in st, st or "kein Status")
    wm.lasten_erzeugen(m2, m2.winde["W1"])
    F_neu2 = np.asarray(solver.case_loads(m2, {lf: 1.0}, None)[0], float).reshape(-1, 6)[:, :3].sum(axis=0)
    check("neu erzeugt: kein Merkmal mehr, ΣF wie frisch erzeugt (in Windrichtung)",
          not mk.betrifft(m2) and F_neu2[0] > 0 and np.allclose(F_neu2, F_neu, rtol=1e-12, atol=1e-6),
          f"{np.round(F_neu2 / 1e3, 2)} kN")
    with contextlib.redirect_stdout(io.StringIO()):
        an = solver.solve_all(m2, design=False)
    m2.save(p)
    erg.schreiben(erg.pfad_zu(p), m2, an)
    m3 = Model.load(p)
    a3 = erg.lesen(erg.pfad_zu(p), m3)
    st = str(a3.info.get("verfahren_betroffen") or "")
    check("neu erzeugt, gerechnet und geoeffnet: kein Status zur Windlast, kein Ladehinweis",
          "Windlast" not in st and not any("Windlasten" in z for z in m3._ladehinweise), st or "kein Status")


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


def huelle():
    """Waende und Dach teilen ihre Linien, gemischt eingegebene Linienrichtungen."""
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
    return m, ["M0", "M1", "M2", "M3", "Dach"]


def test_zusammenhaengende_huelle():
    """Waende und Dach teilen ihre Linien (so baut man es): die Aussenseite kommt
    aus der Mitte der zusammenhaengenden Huelle, mit gemischt eingegebenen
    Linienrichtungen."""
    m, fl = huelle()
    F, kw = wind(m, fl)
    _m4, fl4 = schalenbau(True)
    F4, _ = wind(_m4, fl4)
    check("zusammenhaengende Schalenhuelle: Rollen luv (x = 0), lee (x = 10), dach",
          kw["rollen"]["M3"] == "luv" and kw["rollen"]["M1"] == "lee" and kw["rollen"]["Dach"] == "dach",
          str(kw["rollen"]))
    check("zusammenhaengende Schalenhuelle: ΣF wie der Schalenbau aus Einzelwaenden (1 %)",
          np.allclose(F, F4, rtol=0.01), f"{np.round(F / 1e3, 2)} gegen {np.round(F4 / 1e3, 2)} kN")


def test_verfahrenstabelle():
    """Windlasten eines aelteren Programmstands: „Ergebnis möglicherweise betroffen“.
    Seit dem 11.11.2026 (Befund 40) haengt das Merkmal an den Lasten im Modell:
    frisch erzeugte betrifft es nicht mehr, alte ohne Aussenseite schon."""
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("wind_flaechen")
    m, fl = schalenbau(True)
    ohne = neues_modell()
    wind(m, fl)
    neu = mk.betrifft(m) if mk else None
    _als_alte_datei(m)
    check("Verfahrenstabelle: „wind_flaechen“ Fehlerkorrektur Stand 8, betrifft nur Modelle mit alten Windlasten "
          "auf Flächen",
          mk is not None and mk.wechsel[-1].art == rv.FEHLERKORREKTUR and mk.wechsel[-1].stand == 8
          and rv.VERFAHRENSSTAND >= 8 and mk.betrifft(m) and not neu and not mk.betrifft(ohne))


def main():
    for t in (test_schalen_wirken_in_windrichtung, test_shell8_und_volumen, test_zusammenhaengende_huelle,
              test_einzelne_flaeche, test_freie_wand_verschiebt_keine_mitte, test_zwei_baukoerper,
              test_alte_windlasten, test_verfahrenstabelle):
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
