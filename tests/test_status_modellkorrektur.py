"""
Status „Ergebnis möglicherweise betroffen“ für Korrekturen, die erst am
Modell wirken (Befund A10 der Prüfagenten vom 14.11.2026, Behebung am
selben Tag freigegeben).

(1) Doppelte Randlinien (Stand 37): die Korrektur wirkt erst nach dem
    Neuvernetzen, der Status verschwand aber nach „neu rechnen“. Platte
    4 x 2 m aus F1 und F2, F2 mit eigener Linie L7d auf L7: am getrennten
    Netz w_max 397,70 mm, neu vernetzt 149,59 mm (wie mit gemeinsamer
    Linie). Jetzt prüft das Merkmal das vorhandene Netz (getrennte Knoten auf
    der doppelten Linie) und bleibt als Korrektur am Modell stehen, bis neu
    vernetzt ist; beim Öffnen meldet der Ladehinweis „Schalennetz nicht
    verbunden“ auch die Doppellinie.
(2) Strömungsnumerischer Wasserdruck (Stand 32): das Druckfeld steht im
    Modell; eine Last von vor dem 12.11.2026 (Verlauf mit Feld, ohne
    gespeicherte Flächennormale) bleibt nach „neu rechnen“ falsch (Wand mit
    Elementen gegen den Umlauf: ΣF_y −61,22 statt +61,22 kN). Jetzt Korrektur
    am Modell mit Vorschlag „Wasserdruck neu erzeugen“.
(3) Kontaktfuge an Schalen (d2711c7, Stand 31): eine Fuge, die mit dem alten
    Stand ausgeführt ist, band ein Blech mit Normale vom Block weg an die
    200 mm entfernte Unterseite des Blocks. Jetzt Korrektur am Modell mit
    Vorschlag „Kontaktfugen neu ausführen“, solange ein Knoten der Fuge an
    einer entfernteren Gegenfläche hängt als der nächsten.
(4) Stand 38 trägt das Datum 14.11.2026, die Zweignamen der Stände stimmen.
(5) Eine Ausnahme in der Prüfung der doppelten Randlinien und der
    Schalenlage zählt als „möglicherweise betroffen“.

Aufruf:  python -m tests.test_status_modellkorrektur
"""
import contextlib
import io
import os
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_status_modell_"), "einstellungen.json")

import numpy as np  # noqa: E402

from statik3d import mesher, solver                                     # noqa: E402
from statik3d import rechenverfahren as rv                              # noqa: E402
from statik3d.model import DofBehaviour, Material, Model, ShellProp     # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK  ' if ok else 'FAIL'} {name:<96} {detail}")
    return bool(ok)


def still(f, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return f(*a, **kw)


def _betrifft(name, m) -> bool:
    mk = rv.merkmal(name)
    return bool(mk is not None and mk.betrifft(m))


def _status_neue_rechnung(m, an=None) -> str:
    """Status einer Ergebnisdatei, die das heutige Programm schreibt."""
    mm = rv.merkmale_der_datei({"verfahren": rv.angabe(m)}, m)
    return rv.bewerten(m, mm, an)["betroffen"]


# ---------------------------------------------------------------------------
# (1) Doppelte Randlinien
# ---------------------------------------------------------------------------
def platte_4m(doppelt: bool) -> Model:
    """Wie tests.test_netz_altbefunde.platte_4m: 4 x 2 m, t = 10 mm, gelenkig an
    x = 0 und x = 4, Eigengewicht; ``doppelt``: F2 hat an x = 2 die Linie L7d."""
    m = Model()
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("D10", 0.01))
    for p in [(0, 0, 0), (2, 0, 0), (4, 0, 0), (4, 2, 0), (2, 2, 0), (0, 2, 0)]:
        m.add_node(*p)
    for i, (a, b) in enumerate([(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 0), (1, 4)]):
        m.add_line(f"L{i + 1}", [a, b])
    m.add_flaeche("F1", ["L1", "L7", "L5", "L6"], material="S235", dicke="D10")
    if doppelt:
        m.add_line("L7d", [4, 1])
    m.add_flaeche("F2", ["L2", "L3", "L4", "L7d" if doppelt else "L7"], material="S235", dicke="D10")
    m.add_load_case("LF1", "G")
    m.case("LF1").gravity = [0, 0, -9.81]
    ls = m.add_line_support([], name="LL")
    ls.linien = ["L6", "L3"]
    for d in (0, 1, 2):
        ls.behaviour[d] = DofBehaviour("rigid")
    return m


def getrennt_vernetzen(m) -> None:
    """Jede Fläche für sich (mesh_flaeche): an der doppelten Linie getrennte
    Netzknoten wie im Netz eines Stands vor dem 12.11.2026."""
    from statik3d import netzdichte as nd
    nd.anwenden(m, m.netz, list(m.flaechen.values()), [], [])
    with contextlib.redirect_stdout(io.StringIO()):
        for f in m.flaechen.values():
            mesher.mesh_flaeche(m, f, [])


def w_max(m, an=None) -> float:
    an = an or still(solver.solve_all, m, workers=1, combinations=False)
    dran = sorted({int(k) for e in m.elements for k in e.nodes})
    return float(np.abs(np.asarray(an.cases["LF1"].u)[dran, 2]).max())


def knoten_x2(m, f) -> set:
    return {int(k) for e in m.flaechen[f].elemente for k in m.elements[int(e)].nodes
            if abs(m.nodes[int(k)][0] - 2.0) < 1e-9}


def test_doppellinie_altes_netz():
    mk = rv.merkmal("doppelte_randlinien")
    m = platte_4m(True)
    getrennt_vernetzen(m)
    k1, k2 = knoten_x2(m, "F1"), knoten_x2(m, "F2")
    check("Nachstellung: F1 und F2 an L7/L7d getrennt vernetzt (nur die Linienenden gemeinsam)",
          len(k1 & k2) == 2 and len(k1) > 2 and len(k2) > 2,
          f"Knoten auf x = 2: F1 {len(k1)}, F2 {len(k2)}, gemeinsam {len(k1 & k2)}")
    lose = mesher.unverbundene_schalenlinien(m)
    check("unverbundene_schalenlinien fasst L7/L7d über den Teilplan zusammen und meldet sie",
          any(x[0] in ("L7", "L7d") and {x[1], x[2]} == {"F1", "F2"} for x in lose), str(lose))
    check("Merkmal „doppelte_randlinien“ ist eine Korrektur am Modell (Grund, Vorschlag Netz neu erzeugen)",
          mk is not None and mk.import_korrektur and bool(mk.modellgrund)
          and "Netz" in mk.vorschlag and "neu erzeugen" in mk.vorschlag,
          f"{mk.modellgrund!r} / {mk.vorschlag!r}" if mk else "fehlt")
    check("… betrifft das getrennte Netz", _betrifft("doppelte_randlinien", m))
    an = still(solver.solve_all, m, workers=1, combinations=False)
    w_alt = w_max(m, an)
    st = str(an.info.get("verfahren_betroffen", ""))
    check("nach „neu rechnen“ ohne Neuvernetzen: der Status bleibt (Analyse und neue Ergebnisdatei)",
          mk is not None and mk.titel in st and mk.titel in _status_neue_rechnung(m, an)
          and "neu erzeugen" in st and "Linie L7" in st,
          f"w_max {w_alt * 1e3:.2f} mm; {st[:160]!r}")
    # beim Oeffnen: Ladehinweis
    d = tempfile.mkdtemp(prefix="s3d_doppel_")
    p = os.path.join(d, "alt.json")
    m.save(p)
    m2 = still(Model.load, p)
    zeilen = [z for z in m2._ladehinweise if "Schalennetz nicht verbunden" in z]
    check("beim Öffnen: Ladehinweis „Schalennetz nicht verbunden … neu vernetzen“ nennt die Doppellinie",
          len(zeilen) == 1 and "F1/F2" in zeilen[0] and "L7d" in zeilen[0] and "12.11.2026" in zeilen[0],
          zeilen[0][:200] if zeilen else "kein Hinweis")
    # neu vernetzt: Status weg, Verformung wie mit gemeinsamer Linie
    still(mesher.modell_vernetzen, m2, [], workers=1)
    an2 = still(solver.solve_all, m2, workers=1, combinations=False)
    w_neu = w_max(m2, an2)
    g = platte_4m(False)
    still(mesher.modell_vernetzen, g, [], workers=1)
    w_gem = w_max(g)
    check("neu vernetzt: kein Status, kein Ladehinweis, w_max wie mit gemeinsamer Linie (zwei Wege)",
          not _betrifft("doppelte_randlinien", m2) and not an2.info.get("verfahren_betroffen")
          and not mesher.unverbundene_schalenlinien(m2) and abs(w_neu - w_gem) <= 1e-9 * w_gem
          and w_alt > 2.0 * w_neu,
          f"getrennt {w_alt * 1e3:.2f} mm, neu vernetzt {w_neu * 1e3:.2f} mm, gemeinsame Linie "
          f"{w_gem * 1e3:.2f} mm")


def test_doppellinie_kein_fehlalarm():
    m = platte_4m(True)
    still(mesher.modell_vernetzen, m, [], workers=1)
    mm = rv.merkmale_der_datei({"verfahren": {"stand": 30, "merkmale": {}}}, m)
    mk = rv.merkmal("doppelte_randlinien")
    check("Doppellinie mit heutigem Netz (verbunden): nicht betroffen, auch keine Ergebnisdatei vom Stand 30",
          not _betrifft("doppelte_randlinien", m) and mk.titel not in rv.bewerten(m, mm)["betroffen"],
          rv.bewerten(m, mm)["betroffen"][:120])
    check("… ohne Netz: nicht betroffen", not _betrifft("doppelte_randlinien", platte_4m(True)))


# ---------------------------------------------------------------------------
# (2) Strömungsnumerischer Wasserdruck
# ---------------------------------------------------------------------------
ECKEN_A = [[0, 0, 0], [2, 0, 0], [2, 0, 3], [0, 0, 3]]   # Umlauf: Normale −y


def _wand():
    m = Model("Wand")
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("t10", 0.010))
    m.add_nodes(np.asarray(ECKEN_A, float))
    lin = []
    for i in range(4):
        m.add_line(f"L{i}", [i, (i + 1) % 4])
        lin.append(f"L{i}")
    f = m.add_flaeche("W", lin, material="S235", dicke="t10")
    f.teilung = [8, 8]
    m.netz.ziellaenge = 3.0 / 8
    still(mesher.modell_vernetzen, m, log=[], workers=1)
    return m


def _wasser(m, **kw):
    from statik3d.wasserdruck import Wasserdruck, lasten_erzeugen
    for lc in m.load_cases.values():
        lc.geometrielasten = [g for g in lc.geometrielasten if (g.verlauf or {}).get("art") != "wasser"]
    wd = Wasserdruck("W1", flaechen=["W"], h_ow=2.5, **kw)
    still(lasten_erzeugen, m, wd)
    return wd


def _ohne_flaechennormale(m) -> int:
    n = 0
    for lc in m.load_cases.values():
        for gl in lc.geometrielasten:
            if (gl.verlauf or {}).get("art") == "wasser" and gl.verlauf.pop("normale_flaeche", None) is not None:
                n += 1
    return n


def test_wasserdruck_feld_alt():
    from statik3d.schalenlage import schalen_ausrichten
    mk = rv.merkmal("wasserdruck_feld")
    check("Merkmal „wasserdruck_feld“: Korrektur am Modell, Vorschlag Wasserdruck neu erzeugen",
          mk is not None and mk.import_korrektur and bool(mk.modellgrund)
          and "Wasserdruck" in mk.vorschlag and "neu erzeugen" in mk.vorschlag
          and mk.wechsel[-1].art == rv.FEHLERKORREKTUR,
          f"{mk.modellgrund!r} / {mk.vorschlag!r}" if mk else "fehlt")
    titel = mk.titel if mk else "Wasserdruck"
    m = _wand()
    _wasser(m, verfahren="numerisch", richtung=[0, 1, 0], ow_flaeche="W", ow_seite="Oberseite")
    check("heute erzeugt (Flächennormale im Verlauf): nicht betroffen", mk is not None and not _betrifft("wasserdruck_feld", m))
    n = _ohne_flaechennormale(m)
    # Zustand einer alten Datei: Elemente gegen den Umlauf, Feld ohne Flaechennormale
    for e in m.elements:
        if e.typ == "shell4":
            e.nodes = [e.nodes[0], e.nodes[3], e.nodes[2], e.nodes[1]]
    check("Last aus einer Datei vor dem 12.11.2026 (Feld ohne Flächennormale): betroffen",
          n > 0 and _betrifft("wasserdruck_feld", m), f"{n} Last(en) ohne Flächennormale")
    still(schalen_ausrichten, m)
    an = still(solver.solve_all, m, workers=1, combinations=False)
    st = str(an.info.get("verfahren_betroffen", ""))
    check("nach dem Ausrichten und „neu rechnen“: der Status bleibt mit Vorschlag",
          _betrifft("wasserdruck_feld", m) and titel in st and "Wasserdruck neu erzeugen" in st
          and titel in _status_neue_rechnung(m, an), st[:160])
    _wasser(m, verfahren="numerisch", richtung=[0, 1, 0], ow_flaeche="W", ow_seite="Oberseite")
    check("Wasserdruck neu erzeugt: nicht mehr betroffen",
          mk is not None and not _betrifft("wasserdruck_feld", m) and not rv.modell_betroffen(m))
    m2 = _wand()
    _wasser(m2, verfahren="analytisch", seite=1, absenkung=False)
    _ohne_flaechennormale(m2)
    check("analytisch ohne Flächennormale (rechnet beim Neurechnen richtig): nicht betroffen",
          mk is not None and not _betrifft("wasserdruck_feld", m2))


# ---------------------------------------------------------------------------
# (3) Kontaktfuge an Schalen
# ---------------------------------------------------------------------------
def blech_auf_block(gegen_block: bool = False):
    """Blech (Schale) auf Block, wie tests.test_schalenlage_invariant._blech_auf_block:
    Randumlauf des Blechs mit Normale +z, vom Block weg (``gegen_block``: −z)."""
    from statik3d import fugen
    m = Model("Fuge")
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("t", 0.010))
    P = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                  [0, 0, .2], [1, 0, .2], [1, 1, .2], [0, 1, .2]], float)
    m.add_nodes(P)
    z = [0]

    def L(a, c):
        z[0] += 1
        m.add_line(f"L{z[0]}", [a, c])
        return f"L{z[0]}"
    R = [[L(o + i, o + (i + 1) % 4) for i in range(4)] for o in (0, 4)]
    V = [L(i, i + 4) for i in range(4)]
    m.add_flaeche("Boden", R[0], material="S235")
    m.add_flaeche("Oben", R[1], material="S235")
    mantel = [m.add_flaeche(f"M{i}", [R[0][i], V[(i + 1) % 4], R[1][i], V[i]], material="S235").name
              for i in range(4)]
    m.add_koerper("Block", ["Boden", "Oben"] + mantel, material="S235")
    m.add_flaeche("Blech", R[1][::-1] if gegen_block else R[1], material="S235", dicke="t")
    m.add_load_case("LF1", "Q")
    m.netz.ziellaenge, m.netz.dichte = 0.25, "eigene"
    still(mesher.modell_vernetzen, m, [], workers=1)
    for n in np.flatnonzero(np.abs(m.nodes[:, 2]) < 1e-9):
        m.fix(int(n), "all")
    kb = {0: DofBehaviour("rigid"), 1: DofBehaviour("rigid"), 2: DofBehaviour("rigid", failure="zug")}
    m.add_kontaktbedingung("K", flaechennamen=["Blech"], gegenkoerper=["Block"], behaviour=kb)
    still(fugen.kontaktfugen_ausfuehren, m, [])
    return m


def _boden_facetten(m) -> list:
    """Randseiten des Blocks in z = 0 (die Unterseite, an die der alte Stand band)."""
    from statik3d import fugen
    aus = []
    for e, nd, _n, _g in fugen._randseiten_aller(m):
        if m.elements[int(e)].typ.startswith("shell"):
            continue
        if np.all(np.abs(m.nodes[[int(k) for k in nd], 2]) < 1e-9):
            aus.append([int(k) for k in nd])
    return aus


def test_fuge_schale_alt():
    from statik3d import fugen
    mk = rv.merkmal("fuge_an_schalen")
    check("Merkmal „fuge_an_schalen“: Korrektur am Modell, Vorschlag Kontaktfugen neu ausführen",
          mk is not None and mk.import_korrektur and bool(mk.modellgrund)
          and "Kontaktfugen neu ausführen" in mk.vorschlag and mk.wechsel[-1].art == rv.FEHLERKORREKTUR,
          f"{mk.modellgrund!r} / {mk.vorschlag!r}" if mk else "fehlt")
    titel = mk.titel if mk else "Kontaktfuge"
    m = blech_auf_block()
    cp = next((c for c in m.contact_pairs if c.name == "K"), None)
    check("heute ausgeführt (Blech mit Normale vom Block weg): nicht betroffen",
          mk is not None and cp is not None and not _betrifft("fuge_an_schalen", m),
          f"{len(cp.slave_nodes) if cp else 0} Knoten")
    check("… Blech mit Normale zum Block: nicht betroffen",
          mk is not None and not _betrifft("fuge_an_schalen", blech_auf_block(True)))
    # Zustand der Datei vom Stand eb88ecc (ag_pruef_10/fuge_blech_alt.json): die
    # Fuge band dieselben Knoten an die Unterseite des Blocks, 200 mm entfernt
    boden = _boden_facetten(m)
    cp.master_faces = boden
    an = still(solver.solve_all, m, workers=1, combinations=False, design=False)
    st = str(an.info.get("verfahren_betroffen", ""))
    check("Fuge an die 200 mm entfernte Unterseite gebunden: betroffen, Status bleibt nach „neu rechnen“",
          len(boden) == 16 and _betrifft("fuge_an_schalen", m) and titel in st
          and "Kontaktfugen neu ausführen" in st and "Kontaktbedingung K" in st
          and titel in _status_neue_rechnung(m, an), st[:200])
    still(fugen.kontaktfugen_zuruecksetzen, m, [])
    still(fugen.kontaktfugen_ausfuehren, m, [])
    check("Kontaktfugen neu ausgeführt: nicht mehr betroffen",
          mk is not None and not _betrifft("fuge_an_schalen", m) and not rv.modell_betroffen(m))


# ---------------------------------------------------------------------------
# (4) Daten und Zweige der Stände
# ---------------------------------------------------------------------------
def test_staende():
    w38 = rv.merkmal("versatz_starrer_arm").wechsel[-1]
    check("Stand 38 (Versatz als starrer Arm, 75a0a03 vom 14.11.2026): Datum 14.11.2026",
          w38.stand == 38 and w38.datum == "14.11.2026", w38.datum)
    zweige = {w.commit for mk in rv.MERKMALE for w in mk.wechsel}
    check("Zweig der Stände 36: „fix/k2-schale_beul“ (so heißt er im Archiv), nicht „fix/k2-schale-beul“",
          "fix/k2-schale-beul" not in zweige
          and all(rv.merkmal(n).wechsel[-1].commit == "fix/k2-schale_beul"
                  for n in ("anschluss_beta_w", "laminat_randspannung", "beulen_flaechenachsen")),
          str(sorted(z for z in zweige if "schale" in z)))


# ---------------------------------------------------------------------------
# (5) Ausnahme = möglicherweise betroffen
# ---------------------------------------------------------------------------
def test_ausnahmen():
    m = platte_4m(True)
    getrennt_vernetzen(m)

    def kaputt(*_a, **_k):
        raise RuntimeError("Prüfung nicht möglich")
    with mock.patch.object(mesher, "_teilplan", kaputt):
        a = rv._doppelte_randlinien(m)
    from statik3d import schalenlage
    with mock.patch.object(schalenlage, "plan", kaputt):
        b = rv._schalen_uneinheitlich(m)
    check("Ausnahme in der Prüfung der doppelten Randlinien: möglicherweise betroffen", a is True, repr(a))
    check("Ausnahme in der Prüfung der Schalenlage: möglicherweise betroffen", b is True, repr(b))
    leer = Model()
    check("… ohne Schalen ist nichts betroffen (keine Ausnahme)",
          rv._doppelte_randlinien(leer) is False and rv._schalen_uneinheitlich(leer) is False)


def main():
    tests = [test_doppellinie_altes_netz, test_doppellinie_kein_fehlalarm, test_wasserdruck_feld_alt,
             test_fuge_schale_alt, test_staende, test_ausnahmen]
    for t in tests:
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:               # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((f"{getattr(t, '__name__', 'test')} (Ausnahme: {ex})", False))
        sys.stdout.flush()
    nok = sum(1 for _n, ok in RESULTS if ok)
    print("=" * 96)
    print(f"Ergebnis: {nok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
