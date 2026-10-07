"""
Nachtrag zur Fehlerliste, Paket Q5 (07.10.2026): Vernetzer.

* N08: Schalen auf Bogenlinien - ``mesher.kantenknoten`` setzte die
  Kantenmitte einer quadratischen Randkante auf die Sehnenmitte, beim
  Viertelkreisring (R = 2 m, sechs Teilungen, shell8) 17,1 mm neben den
  Bogen. ``Model.knoten_auf_linie`` und ``supports.lager_auf_netz`` fanden
  diese Mitten nicht: die Linienlast ging nur an die Ecken, das Linienlager
  hielt die Mitten nicht.
* N09: Verwaister Stuetzknoten eines Bogens - der Vernetzer legte neben den
  mittleren Knoten eines Bogens durch drei Punkte einen deckungsgleichen
  neuen; der alte hing an keinem Element, bekam von der Linienlast aber
  seinen Anteil, und der ging verloren (261,8 N von 3 141,5 N, 8,3 %).
* N37: Der eigene Vernetzer rief ``randtreue()`` in ``tetraedern`` ohne
  Abfangen; eine gescheiterte Messung brach den Koerper ab (und mit ihm das
  ganze Vernetzen), statt „nicht gemessen“ zu setzen wie beim fremden
  Vernetzer (F35).

Geprueft wird am Kreisringstueck (Innenradius 1 m, Aussenradius 2 m, die
Boegen durch drei Knoten) gegen die geschlossene Loesung: Bogenlaenge R phi,
konsistente Knotenlasten einer quadratischen Kante q L/6, 2 q L/3, q L/6 -
an der Probe aus dem Nachtrag und in einer Stichprobe ueber Oeffnungswinkel
und Teilung.

    python -m tests.test_nachtrag_q5
"""
import contextlib
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from statik3d.model import Model, Material, ShellProp  # noqa: E402
from statik3d import mesher, solver, supports  # noqa: E402

RESULTS = []


def check(name, ok, info=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:<78s} {info}")
    return bool(ok)


R1, R2, Q = 1.0, 2.0, -1000.0


def ring(phi_grad=90.0, nv=6, ordnung=2, dreiecke=False, typ="arc", nu=2, vernetzen=True):
    """Kreisringstueck mit dem Oeffnungswinkel ``phi_grad``: L1 radial bei 0,
    L2 aussen (Bogen durch 1, 4, 2), L3 radial bei phi, L4 innen (Bogen durch
    3, 5, 0). Knoten 4 und 5 sind die Stuetzknoten der Boegen in der Mitte.
    ``typ`` "polyline" macht aus den Boegen geknickte Polylinien."""
    m = Model("Ring")
    m.add_material(Material("S", E=210e9, nu=0.3))
    m.add_shell_prop(ShellProp("t", 0.02))
    p = np.radians(phi_grad)
    c, s, ch, sh = np.cos(p), np.sin(p), np.cos(p / 2), np.sin(p / 2)
    m.add_nodes([[R1, 0, 0], [R2, 0, 0], [R2 * c, R2 * s, 0], [R1 * c, R1 * s, 0],
                 [R2 * ch, R2 * sh, 0], [R1 * ch, R1 * sh, 0]])
    m.add_line("L1", [0, 1], "polyline")
    m.add_line("L2", [1, 4, 2], typ)
    m.add_line("L3", [2, 3], "polyline")
    m.add_line("L4", [3, 5, 0], typ)
    f = m.add_flaeche("F", ["L1", "L2", "L3", "L4"], material="S", dicke="t", teilung=[nu, nv])
    if vernetzen:
        with contextlib.redirect_stdout(io.StringIO()):
            mesher.mesh_flaeche(m, f, dreiecke=dreiecke, ordnung=ordnung)
    return m


def im_netz(m) -> set:
    return {int(n) for e in m.elements for n in e.nodes}


def mitten_abstand(m, r) -> tuple:
    """(Zahl, groesster Abstand [m]) der Kantenmitten, deren Kante mit beiden
    Ecken auf dem Kreis r liegt - Abstand der Mitte zum Kreis."""
    from statik3d.linienverteilung import kanten_mit_mitte
    tab = kanten_mit_mitte()
    n, d = 0, 0.0
    for e in m.elements:
        for a, b, k in tab.get(e.typ, ()):
            pa, pb = m.nodes[e.nodes[a]], m.nodes[e.nodes[b]]
            if abs(np.linalg.norm(pa[:2]) - r) < 1e-9 and abs(np.linalg.norm(pb[:2]) - r) < 1e-9:
                n += 1
                d = max(d, abs(float(np.linalg.norm(m.nodes[e.nodes[k]][:2])) - r))
    return n, d


def randkantenknoten(m, r) -> list:
    """Ecken und Mitten aller Elementkanten, deren Ecken auf dem Kreis r liegen
    - die Netzknoten der Randlinie, wo immer die Mitten liegen."""
    from statik3d.linienverteilung import kanten_mit_mitte
    tab = kanten_mit_mitte()
    out = set()
    for e in m.elements:
        nk = len(e.nodes) // 2 if e.typ in tab else len(e.nodes)
        kanten = [(a, b, k) for a, b, k in tab.get(e.typ, ())] or             [(i, (i + 1) % nk, None) for i in range(nk)]
        for a, b, k in kanten:
            pa, pb = m.nodes[e.nodes[a]], m.nodes[e.nodes[b]]
            if abs(np.linalg.norm(pa[:2]) - r) < 1e-9 and abs(np.linalg.norm(pb[:2]) - r) < 1e-9:
                out.update(int(e.nodes[x]) for x in (a, b) + ((k,) if k is not None else ()))
    return sorted(out)


def last_je_knoten(m, linie="L2", q=Q):
    """{Knoten: Fz} der Linienlast q (in z) auf der Linie."""
    ll = m.add_linienlast(linie, [0, 0, q], art="linie")
    out = {}
    for nl in m._linienlast_legen(ll):
        out[nl.node] = out.get(nl.node, 0.0) + float(nl.F[2])
    m.case().linienlasten.remove(ll)
    return out


# --------------------------------------------------------------------------
# N08
# --------------------------------------------------------------------------
def test_n08_probe():
    """Viertelkreisring wie im Nachtrag: R = 2 m, 2 x 6 Elemente, shell8 und
    shell6. Mitten auf dem Bogen, von knoten_auf_linie gefunden, Linienlast
    konsistent verteilt, Resultierende q R phi."""
    L = R2 * np.pi / 2
    Le = L / 6
    for typ, dreiecke in (("shell8", False), ("shell6", True)):
        m = ring(90.0, 6, 2, dreiecke)
        check(f"N08 {typ}: Aufbau", {e.typ for e in m.elements} == {typ}, str({e.typ for e in m.elements}))
        for r, name in ((R2, "außen"), (R1, "innen")):
            n, d = mitten_abstand(m, r)
            check(f"N08 {typ}: Kantenmitten {name} auf dem Bogen (vorher 17,110 mm daneben)",
                  n >= 6 and d < 1e-9, f"{n} Mitten, größter Abstand {d * 1e3:.6f} mm")
        kn = m.knoten_auf_linie("L2")
        netz = im_netz(m)
        check(f"N08 {typ}: knoten_auf_linie findet 7 Ecken und 6 Mitten",
              len(kn) == 13 and all(n in netz for n, _s in kn),
              f"{len(kn)} Knoten, ohne Element {[n for n, _s in kn if n not in netz]}")
        F = last_je_knoten(m)
        summe = sum(F.values())
        check(f"N08 {typ}: Resultierende der Linienlast = q · Bogenlänge",
              abs(summe - Q * L) < 1e-6 * abs(Q * L),
              f"{summe:.6f} N, Soll {Q * L:.6f} N")
        soll = {}
        for i, (n, _s) in enumerate(kn):
            soll[n] = Q * Le * (2 / 3 if i % 2 else (1 / 6 if i in (0, 12) else 1 / 3))
        abw = max(abs(F.get(n, 0.0) - soll[n]) for n in soll) / abs(Q * Le)
        check(f"N08 {typ}: Knotenlasten q L/6, 2 q L/3, q L/3 … (konsistent)",
              abw < 1e-6, f"größte Abweichung {abw:.1e} · q L_e; Mitte {F.get(kn[1][0], 0.0):.3f} "
                          f"Soll {soll[kn[1][0]]:.3f} N")
        # Linienlager auf dem Bogen haelt alle Netzknoten der Linie
        ls = m.add_line_support([1, 2], name="Bogen", ux=dict(typ="rigid"), uy=dict(typ="rigid"),
                                uz=dict(typ="rigid"), phix=dict(typ="rigid"), phiy=dict(typ="rigid"),
                                phiz=dict(typ="rigid"))
        ls.linien = ["L2"]
        supports.lager_auf_netz(m)
        aussen = randkantenknoten(m, R2)
        check(f"N08 {typ}: lager_auf_netz nimmt alle 13 Netzknoten des Bogens",
              len(aussen) == 13 and sorted(ls.nodes) == aussen,
              f"{len(ls.nodes)} Knoten, ohne Lager {sorted(set(aussen) - set(ls.nodes))}")
        m.add_linienlast("L4", [0, 0, Q], art="linie")
        m.lasten_verteilen()
        r = solver.solve_static(m)
        u_max = float(np.abs(r.u[aussen, :3]).max())
        check(f"N08 {typ}: das Linienlager hält jeden Knoten auf dem Bogen fest",
              len(aussen) == 13 and u_max < 1e-15, f"{len(aussen)} Knoten, max |u| {u_max:.3e} m")
        Rz = float(r.reactions[:, 2].sum())
        check(f"N08 {typ}: Lagerkraft = Last q · R1 · phi",
              abs(Rz + Q * R1 * np.pi / 2) < 1e-6 * abs(Q * R1 * np.pi / 2),
              f"{Rz:.6f} N, Soll {-Q * R1 * np.pi / 2:.6f} N")


def test_n08_stichprobe():
    """Oeffnungswinkel 30 bis 270 Grad, Teilung 1 bis 9, shell8 und shell6:
    jede Kantenmitte auf dem Bogen, alle 2 n + 1 Netzknoten gefunden, keiner
    ohne Element, Resultierende q R phi."""
    fehler = []
    n_faelle = 0
    for phi in (30.0, 90.0, 150.0, 200.0, 270.0):
        for nv in (1, 2, 3, 5, 6, 9):
            for dreiecke in (False, True):
                n_faelle += 1
                m = ring(phi, nv, 2, dreiecke)
                netz = im_netz(m)
                for r, linie in ((R2, "L2"), (R1, "L4")):
                    _n, d = mitten_abstand(m, r)
                    kn = m.knoten_auf_linie(linie)
                    L = r * np.radians(phi)
                    F = last_je_knoten(m, linie)
                    summe = sum(F.values())
                    lose = [n for n, _s in kn if n not in netz]
                    if d > 1e-9 or len(kn) != 2 * nv + 1 or lose or abs(summe - Q * L) > 1e-6 * abs(Q * L):
                        fehler.append(f"{phi:.0f}° n={nv} {'shell6' if dreiecke else 'shell8'} {linie}: "
                                      f"Abstand {d * 1e3:.3f} mm, {len(kn)} Knoten, lose {lose}, "
                                      f"Summe {summe / (Q * L):.7f} q L")
    check(f"N08 Stichprobe: {n_faelle} Ringstücke, beide Bögen", not fehler,
          f"{len(fehler)} abweichend: " + "; ".join(fehler[:4]))


def test_n08_modell_vernetzen():
    """Derselbe Ring ueber modell_vernetzen (Ordnung 2 aus den Netzeinstellungen,
    Lasten verteilen im Nachlauf)."""
    m = ring(90.0, 6, vernetzen=False)
    m.netz.ordnung = 2
    m.add_linienlast("L2", [0, 0, Q], art="linie")
    with contextlib.redirect_stdout(io.StringIO()):
        mesher.modell_vernetzen(m, [], workers=1)
    n, d = mitten_abstand(m, R2)
    summe = sum(nl.F[2] for nl in m.case().nodal_loads)
    L = R2 * np.pi / 2
    check("N08 modell_vernetzen: Mitten auf dem Bogen, Linienlast q · Bogenlänge",
          n > 0 and d < 1e-9 and abs(summe - Q * L) < 1e-6 * abs(Q * L),
          f"{n} Mitten, Abstand {d * 1e3:.6f} mm, Summe {summe:.4f} N (Soll {Q * L:.4f} N)")


# --------------------------------------------------------------------------
# N09
# --------------------------------------------------------------------------
def test_n09_stuetzknoten():
    """Der Stuetzknoten des Bogens (Knoten 4): bei gerader Teilung liegt ein
    Netzknoten auf ihm - dann ist er es selbst, kein deckungsgleicher neuer;
    bei ungerader Teilung (linear) haengt er an keinem Element und bekommt
    nichts. Die Lagerkraft an L1 ist immer die ganze Last."""
    for typ in ("arc", "polyline"):
        for nv in (6, 5):
            for ordnung in (1, 2):
                m = ring(90.0, nv, ordnung, typ=typ)
                netz = im_netz(m)
                fall = f"{typ} n={nv} Ordnung {ordnung}"
                doppelt = mesher.doppelte_knoten(m)
                if nv % 2 == 0 or (ordnung == 2 and typ == "arc"):
                    check(f"N09 {fall}: Stützknoten 4 ist Netzknoten, kein doppelter daneben",
                          4 in netz and 5 in netz and doppelt == 0,
                          f"Knoten 4 im Netz {4 in netz}, doppelte Knoten {doppelt}")
                else:
                    check(f"N09 {fall}: kein doppelter Knoten", doppelt == 0, f"doppelte Knoten {doppelt}")
                kn = m.knoten_auf_linie("L2")
                lose = [n for n, _s in kn if n not in netz]
                for n, _s in m.knoten_auf_linie("L1"):
                    m.fix(n, "all")
                ll = m.add_linienlast("L2", [0, 0, Q], art="linie")
                F = m._linienlast_legen(ll)
                an_losen = sum(nl.F[2] for nl in F if nl.node not in netz)
                summe = sum(nl.F[2] for nl in F)
                m.lasten_verteilen()
                r = solver.solve_static(m)
                RL1 = float(sum(r.reactions[n, 2] for n, _s in m.knoten_auf_linie("L1")))
                check(f"N09 {fall}: kein Knoten ohne Element bekommt Last, Lagerkraft an L1 = Last",
                      not lose and an_losen == 0.0 and abs(RL1 + summe) < 1e-9 * abs(summe),
                      f"lose {lose}, an ihnen {an_losen:.3f} N, L1 {RL1:.3f} N von {-summe:.3f} N "
                      f"({(RL1 + summe) / summe * 100:.2f} % fehlen)")
                ls = m.add_line_support([1, 2], name="Bogen", uz=dict(typ="spring", stiffness=1e8))
                ls.linien = ["L2"]
                supports.lager_auf_netz(m)
                w = supports.tributary_lengths(m, ls.nodes)
                lose_w = sum(w.get(n, 0.0) for n in ls.nodes if n not in netz)
                check(f"N09 {fall}: Linienlager nur an Netzknoten, keine Einflusslänge an losen",
                      all(n in netz for n in ls.nodes) and lose_w == 0.0,
                      f"ohne Element {[n for n in ls.nodes if n not in netz]}, deren Einflusslänge "
                      f"{lose_w:.4f} m von {sum(w.values()):.4f} m")


# --------------------------------------------------------------------------
# N37
# --------------------------------------------------------------------------
def _wirft(*_a, **_k):
    raise MemoryError("Probe N37")


def test_n37_randtreue_eigener_vernetzer():
    """Eigener Vernetzer, randtreue() wirft: der Koerper bekommt sein Netz,
    die Randtreue gilt als nicht gemessen (wie F35 beim fremden Vernetzer)."""
    from statik3d import diagnose as dg
    from statik3d import mesher3d as M3
    from statik3d.model import Material as Mat
    from tests.test_diagnose import _extrudiert
    L = [(0, 0), (2, 0), (2, 0.5), (0.5, 0.5), (0.5, 2), (0, 2)]
    # (a) tetraedern selbst, an der Huelle des L-Prismas
    m = Model("L")
    m.add_material(Mat.steel("S235"))
    k = _extrudiert(m, L, 0.0, 0.4)
    with contextlib.redirect_stdout(io.StringIO()):
        P, T, _ber = M3.randschale(m, k, 0.25, [])
    echt = M3.randtreue
    M3.randtreue = _wirft
    try:
        try:
            _Pn, TET, tb = M3.tetraedern(P, T, 0.25)
            aus = f"{len(TET)} Tetraeder, randtreue {tb.get('randtreue')}, Fehler {tb.get('randtreue_fehler')!r}"
            ok = len(TET) > 0 and tb.get("randtreue") == 0.0 and "MemoryError" in str(tb.get("randtreue_fehler"))
        except MemoryError as ex:
            aus, ok = f"Ausnahme {type(ex).__name__}: {ex}", False
    finally:
        M3.randtreue = echt
    check("N37 tetraedern: gescheiterte Messung heißt „nicht gemessen“", ok, aus)
    # (b) der ganze Weg ueber modell_vernetzen
    m = Model("L")
    m.add_material(Mat.steel("S235"))
    k = _extrudiert(m, L, 0.0, 0.4)
    m.netz.sweep = False
    m.netz.vernetzer = "eigener"
    log = []
    M3.randtreue = _wirft
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            mesher.modell_vernetzen(m, log, workers=1, hs={"K": 0.25})
        aus = "kehrt zurück"
    except MemoryError as ex:
        aus = f"Ausnahme {type(ex).__name__}: {ex}"
    finally:
        M3.randtreue = echt
    check("N37 eigener Vernetzer: der Körper bekommt sein Netz",
          aus == "kehrt zurück" and len(k.elemente) > 0, f"{aus}, {len(k.elemente)} Elemente")
    check("N37 eigener Vernetzer: der Körper trägt den Grund",
          "MemoryError" in str(getattr(k, "randtreue_fehler", "")) and k.randtreue == 0.0,
          f"randtreue {k.randtreue}, Grund {getattr(k, 'randtreue_fehler', None)!r}")
    zeilen = [z for z in log if "Randtreue ließ sich nicht messen" in z]
    nach = [z for z in log if "nachvernetzt" in z and "Randtreue" in z]
    check("N37 eigener Vernetzer: das Protokoll sagt es, kein Nachvernetzen wegen der Randtreue",
          len(zeilen) >= 1 and not nach, (zeilen[0] if zeilen else "keine Zeile")[:110])
    bef = [b for b in dg.abnahme(m, warnungen=True) if "Randtreue" in b.pruefung]
    check("N37 eigener Vernetzer: Abnahme „Randtreue nicht geprüft“",
          [b.pruefung for b in bef] == ["Randtreue nicht geprüft"],
          str([(b.pruefung, b.stufe) for b in bef]) or "keine Befunde")


def main():
    for t in (test_n08_probe, test_n08_stichprobe, test_n08_modell_vernetzen,
              test_n09_stuetzknoten, test_n37_randtreue_eigener_vernetzer):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    failed = [n for n, ok in RESULTS if not ok]
    if failed:
        print("FEHLGESCHLAGEN:", failed)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
