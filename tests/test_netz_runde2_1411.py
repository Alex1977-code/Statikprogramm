"""
Befunde A'10 (Teile Netz) und B'8 der Befundliste vom 14.11.2026 (zweite
Runde), zur Behebung freigegeben am 14.11.2026.

A'10a: Eine Kontaktbedingung zwischen zwei Schalen an ihrer gemeinsamen Linie
trennt die Netze gewollt (Knotenpaare in Model.getrennte_knoten). Die
Eingabepruefung warnte trotzdem „Schalennetz nicht verbunden“, das Merkmal
„schalennetz_getrennt“ meldete das Modell als betroffen, und kein
Neuvernetzen hob es auf (Beleg ag_pruef2_10/t2_fuge_schalen.py).

A'10b: Der Hinweis „Flächenlager nach Neuvernetzen prüfen“ hing am Namen des
Lagers: nach dem Umbenennen verschwand er samt Status, zwei Lager ohne Namen
teilten sich einen (t7_flaechenlager_hinweis.py). Jetzt traegt das Lager eine
feste Kennung, die nicht in die Rechenkennung eingeht.

B'8: Getrennte Netze an einer Rippe (Zwangslinie, „Linie in Fläche“) blieben
ohne Eingabepruefung und Status (Datei vom Stand c766722: Platte mit Rippe
14,591 statt 11,826 mm nach dem Neuvernetzen, t5b_rippe_alte_datei.py), und
Polylinie gegen Polylinie mit verschiedenen Zwischenknoten auf derselben
Strecke wurde nicht geteilt, nur im Protokoll gewarnt (397,70 statt 149,99 mm,
t4_polylinien.py). Jetzt zaehlen Zwangslinien in der Pruefung auf getrennte
Netze mit, Polylinien werden an fremden Knoten geteilt, und ein getrenntes
Netz dort meldet das neue Merkmal „schalennetz_rippe_polylinie“ (Stand 52).

Zwei Wege fuer die Zahlen: gezaehlte Netzknoten auf der Linie je Flaeche
gegen die Meldung; Durchbiegung mit Polylinien gegen dieselbe Platte mit
Einzellinien.

Aufruf:  python -m tests.test_netz_runde2_1411
"""
import contextlib
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_netz_runde2_"), "einstellungen.json")

import numpy as np  # noqa: E402

from statik3d import diagnose, mesher, solver                           # noqa: E402
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


def schalennetz_warnung(m) -> list:
    return [b.text for b in diagnose.eingabepruefung(m) if "Schalennetz" in b.text]


def betrifft(name, m) -> bool:
    mk = rv.merkmal(name)
    return bool(mk is not None and mk.betrifft(m))


def rippen(m) -> list:
    """mesher.getrennte_rippen_polylinien (vor der Behebung: gab es nicht)."""
    f = getattr(mesher, "getrennte_rippen_polylinien", None)
    return f(m) if f else []


def w_max(m) -> float:
    r = still(solver.solve_all, m, workers=1, combinations=False).cases["LF1"]
    dran = sorted({int(k) for e in m.elements for k in e.nodes})
    return float(np.abs(np.asarray(r.u)[dran, 2]).max())


def grundplatte(r1, r2, linien) -> Model:
    """Platte 4 x 2 m aus F1 (x 0..2) und F2 (x 2..4), t = 10 mm, gelenkig an
    x = 0 und x = 4, Eigengewicht; an x = 2 die Linien ``linien`` (Name ->
    Knoten), F1 mit ``r1``, F2 mit ``r2``. Knoten 6 = (2, 1), 7 = (2, 0,5)."""
    m = Model()
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("D10", 0.01))
    for p in [(0, 0, 0), (2, 0, 0), (4, 0, 0), (4, 2, 0), (2, 2, 0), (0, 2, 0), (2, 1, 0), (2, 0.5, 0)]:
        m.add_node(*p)
    for i, (a, b) in enumerate([(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 0)]):
        m.add_line(f"L{i + 1}", [a, b])
    for name, kn in linien.items():
        m.add_line(name, kn)
    m.add_flaeche("F1", ["L1"] + r1 + ["L5", "L6"], material="S235", dicke="D10")
    m.add_flaeche("F2", ["L2", "L3", "L4"] + r2, material="S235", dicke="D10")
    m.add_load_case("LF1", "G")
    m.case("LF1").gravity = [0, 0, -9.81]
    ls = m.add_line_support([], name="LL")
    ls.linien = ["L6", "L3"]
    for d in (0, 1, 2):
        ls.behaviour[d] = DofBehaviour("rigid")
    return m


def auf_x(m, f, x=2.0) -> set:
    X = np.asarray(m.nodes)
    return {int(k) for e in m.flaechen[f].elemente for k in m.elements[int(e)].nodes
            if abs(X[int(k)][0] - x) < 1e-9 and abs(X[int(k)][2]) < 1e-9}


def getrennt_vernetzen(m) -> None:
    """Jede Flaeche fuer sich (mesh_flaeche) - getrennte Netzknoten wie in
    einer Datei eines aelteren Stands."""
    from statik3d import netzdichte as nd
    nd.anwenden(m, m.netz, list(m.flaechen.values()), [], [])
    with contextlib.redirect_stdout(io.StringIO()):
        for f in m.flaechen.values():
            mesher.mesh_flaeche(m, f, [])


# ---------------------------------------------------------------------------
# A'10a: Kontaktbedingung zwischen zwei Schalen an der gemeinsamen Linie
# ---------------------------------------------------------------------------
def test_fuge_schalen():
    m = grundplatte(["L7"], ["L7"], {"L7": [1, 4]})
    kb = m.add_kontaktbedingung("KB1", flaechennamen=["F2"], koerpernamen=["F2"])
    for d in (0, 1, 2):
        kb.behaviour[d] = DofBehaviour("rigid")
    still(mesher.modell_vernetzen, m, [], workers=1)
    n1, n2 = auf_x(m, "F1"), auf_x(m, "F2")
    paare = sum(len(v) for v in (m.getrennte_knoten or {}).values())
    check("**A'10: Kontaktbedingung trennt F1/F2 an L7 gewollt – keine Warnung „Schalennetz nicht "
          "verbunden“, kein Status „schalennetz_getrennt“**",
          paare > 0 and not (n1 & n2) and not schalennetz_warnung(m) and not betrifft("schalennetz_getrennt", m)
          and not mesher.unverbundene_schalenlinien(m),
          f"Knoten auf L7: F1 {len(n1)}, F2 {len(n2)}, gemeinsam {len(n1 & n2)}, getrennte Paare {paare}; "
          f"{schalennetz_warnung(m)[:1]}")
    # Gegenprobe: dieselbe Trennung ohne Kontaktbedingung wird weiter gemeldet
    m2 = grundplatte(["L7"], ["L7"], {"L7": [1, 4]})
    getrennt_vernetzen(m2)
    check("… Gegenprobe: ohne Kontaktbedingung getrennt vernetzt – weiter gemeldet (Warnung und Status)",
          bool(schalennetz_warnung(m2)) and betrifft("schalennetz_getrennt", m2),
          str(schalennetz_warnung(m2)[:1])[:120])


# ---------------------------------------------------------------------------
# A'10b: Hinweis „Flächenlager nach Neuvernetzen prüfen“ beim Umbenennen
# ---------------------------------------------------------------------------
def platte_mit_lagern(namen) -> Model:
    m = Model()
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("D10", 0.01))
    for p in [(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0)]:
        m.add_node(*p)
    for i in range(4):
        m.add_line(f"L{i + 1}", [i, (i + 1) % 4])
    m.add_flaeche("F1", ["L1", "L2", "L3", "L4"], material="S235", dicke="D10")
    m.add_load_case("LF1", "G")
    still(mesher.modell_vernetzen, m, [], workers=1)
    els = list(m.flaechen["F1"].elemente)
    for i, nm in enumerate(namen):
        ss = m.add_surface_support(els[i::len(namen)][:10], name="x")
        ss.name = nm
        ss.behaviour[2] = DofBehaviour("spring", stiffness=1e7)
    return m


def test_flaechenlager_hinweis_umbenennen():
    from statik3d import ergebnisse as erg
    from statik3d.model import flaechenlager_neuvernetzen_hinweis, flaechenlager_neuvernetzen_offen
    mk = "flaechenlager_neuvernetzen"
    m = platte_mit_lagern(("FL1",))
    k0 = erg.rechenkennung(m)
    flaechenlager_neuvernetzen_hinweis(m, 30)
    check("A'10: die feste Kennung des Lagers ändert die Rechenkennung nicht (Ergebnisse bleiben gültig)",
          erg.rechenkennung(m) == k0 and bool(getattr(m.surface_supports[0], "kennung", "")))
    p = os.path.join(tempfile.mkdtemp(prefix="statik3d_fl_"), "m.json")
    still(m.save, p)
    m2 = Model.load(p)
    m2.surface_supports[0].name = "Bettung Nord"          # wie gui.main._lager_benennen
    check("**A'10: Flächenlager umbenannt (nach Speichern/Laden) – Hinweis und Status bleiben, unter dem "
          "neuen Namen**",
          flaechenlager_neuvernetzen_offen(m2) == ["Bettung Nord"] and betrifft(mk, m2),
          str(flaechenlager_neuvernetzen_offen(m2)))
    namen = m2.flaechenlager_geprueft("Bettung Nord")
    check("… Bestätigung unter dem neuen Namen erledigt ihn, Status weg",
          namen == ["Bettung Nord"] and not flaechenlager_neuvernetzen_offen(m2) and not betrifft(mk, m2),
          str(namen))
    # zwei Lager ohne Namen: je ein Hinweis, die Bestaetigung des einen laesst den anderen offen
    m3 = platte_mit_lagern(("", ""))
    flaechenlager_neuvernetzen_hinweis(m3, 30)
    hw = [h for h in m3.importhinweise if h.get("art") == "flaechenlager_neuvernetzen"]
    try:
        m3.flaechenlager_geprueft(lager=m3.surface_supports[0])
    except TypeError:                              # vor der Behebung: nur ueber den Namen
        m3.flaechenlager_geprueft(m3.surface_supports[0].name)
    offen = [h for h in hw if not h.get("erledigt")]
    import statik3d.model as _mod
    rest = (_mod.flaechenlager_neuvernetzen_offen_lager(m3)
            if hasattr(_mod, "flaechenlager_neuvernetzen_offen_lager") else [])
    check("**A'10: zwei Lager ohne Namen – je ein Hinweis; bestätigt wird nur das gewählte, das andere "
          "bleibt offen**",
          len(hw) == 2 and len(offen) == 1 and len(rest) == 1 and rest[0] is m3.surface_supports[1]
          and betrifft(mk, m3),
          f"Hinweise {len(hw)}, offen {len(offen)}")
    # Hinweis aus einer Datei von Stand 50/51 (nur Name): folgt nach dem ersten Lesen dem Lager
    m4 = platte_mit_lagern(("FL1",))
    m4.importhinweise = [{"art": "flaechenlager_neuvernetzen", "text": "alt", "objekte": ["FL1"],
                          "vorschlag": "", "erledigt": False, "datei": ""}]
    vorher = flaechenlager_neuvernetzen_offen(m4)
    m4.surface_supports[0].name = "FL1 neu"
    check("A'10: Hinweis von Stand 50/51 (nur mit Namen) folgt dem Lager nach dem Umbenennen",
          vorher == ["FL1"] and flaechenlager_neuvernetzen_offen(m4) == ["FL1 neu"],
          str(flaechenlager_neuvernetzen_offen(m4)))


# ---------------------------------------------------------------------------
# B'8: Rippe (Zwangslinie) mit getrenntem Netz
# ---------------------------------------------------------------------------
def platte_mit_rippe() -> Model:
    """Platte F1 2 x 2 m, Rippe F3 senkrecht bei x = 1 (z 0..0,5), Lr liegt in F1
    (wie ag_pruef2_10/t5_zwangslinie.py); gelenkig an x = 0 und x = 2."""
    m = Model()
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("D10", 0.01))
    for p in [(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0), (1, 0, 0), (1, 2, 0), (1, 0, .5), (1, 2, .5)]:
        m.add_node(*p)
    m.add_line("L1", [0, 1]); m.add_line("L2", [1, 2]); m.add_line("L3", [2, 3]); m.add_line("L4", [3, 0])
    m.add_line("Lr", [4, 5]); m.add_line("R1", [5, 7]); m.add_line("R2", [7, 6]); m.add_line("R3", [6, 4])
    m.add_flaeche("F1", ["L1", "L2", "L3", "L4"], material="S235", dicke="D10")
    m.add_flaeche("F3", ["Lr", "R1", "R2", "R3"], material="S235", dicke="D10")
    m.add_load_case("LF1", "G")
    m.case("LF1").gravity = [0, 0, -9.81]
    ls = m.add_line_support([], name="LL")
    ls.linien = ["L4", "L2"]
    for d in (0, 1, 2):
        ls.behaviour[d] = DofBehaviour("rigid")
    return m


def auf_lr(m, f) -> set:
    X = np.asarray(m.nodes)
    return {int(k) for e in m.flaechen[f].elemente for k in m.elements[int(e)].nodes
            if abs(X[int(k)][0] - 1.0) < 1e-9 and abs(X[int(k)][2]) < 1e-9}


def test_rippe_getrennt():
    m = platte_mit_rippe()
    still(mesher.modell_vernetzen, m, [], workers=1)
    a, b = auf_lr(m, "F1"), auf_lr(m, "F3")
    w_ref = w_max(m)
    check("B'8 Vorlauf: Rippe in einem Zug vernetzt – alle Knoten auf Lr gemeinsam, keine Meldung",
          a == b and len(a) > 2 and not schalennetz_warnung(m) and not betrifft("schalennetz_rippe_polylinie", m),
          f"F1 {len(a)}, F3 {len(b)}, gemeinsam {len(a & b)}; w_max {w_ref * 1e3:.3f} mm")
    # wie eine Datei vom Stand vor B9: nur die Rippe fuer sich neu vernetzt
    f3 = m.flaechen["F3"]
    m.elemente_loeschen(list(f3.elemente))
    f3.elemente = []
    f3.teilung = [7, 3]
    with contextlib.redirect_stdout(io.StringIO()):
        mesher.mesh_flaeche(m, f3, [])
    a, b = auf_lr(m, "F1"), auf_lr(m, "F3")
    w_alt = w_max(m)
    lose = rippen(m)
    warn = schalennetz_warnung(m)
    check("**B'8: Rippe mit getrenntem Netz an Lr – Eingabeprüfung warnt, Merkmal "
          "„schalennetz_rippe_polylinie“ (Stand 52) meldet, als Zwangslinie**",
          len(a & b) < len(a) and bool(warn) and "Lr" in warn[0] and betrifft("schalennetz_rippe_polylinie", m)
          and not betrifft("schalennetz_getrennt", m) and lose and lose[0][5] == "zwang",
          f"F1 {len(a)}, F3 {len(b)}, gemeinsam {len(a & b)}; w_max {w_alt * 1e3:.3f} mm; {warn[:1]}")
    mk = rv.merkmal("schalennetz_rippe_polylinie")
    wo = (mk.im_ergebnis(m, None) or "") if mk else ""
    check("… der Status nennt die Rippe an Lr", "Rippe" in wo and "Lr" in wo, wo)
    still(mesher.modell_vernetzen, m, [], workers=1)
    a, b = auf_lr(m, "F1"), auf_lr(m, "F3")
    w_neu = w_max(m)
    check("**B'8: nach dem Neuvernetzen verbunden, keine Meldung, w_max wie in einem Zug vernetzt "
          "(zwei Wege: Knotenzählung, Durchbiegung)**",
          a == b and not schalennetz_warnung(m) and not betrifft("schalennetz_rippe_polylinie", m)
          and abs(w_neu - w_ref) <= 1e-6 * w_ref and w_alt > w_neu,
          f"gemeinsam {len(a & b)} von {len(a)}; w_max getrennt {w_alt * 1e3:.3f}, neu {w_neu * 1e3:.3f}, "
          f"in einem Zug {w_ref * 1e3:.3f} mm")


# ---------------------------------------------------------------------------
# B'8: Polylinie gegen Polylinie mit verschiedenen Zwischenknoten
# ---------------------------------------------------------------------------
def test_polylinie_gegen_polylinie():
    ref = grundplatte(["La", "Lb", "Lc"], ["La", "Lb", "Lc"], {"La": [1, 7], "Lb": [7, 6], "Lc": [6, 4]})
    still(mesher.modell_vernetzen, ref, [], workers=1)
    w_ref = w_max(ref)
    for art, lin, r1, r2 in (("anders", {"L7p": [1, 6, 4], "L7q": [1, 7, 4]}, ["L7p"], ["L7q"]),
                             ("teil", {"L7p": [1, 6, 4], "L7q": [1, 7, 6, 4]}, ["L7p"], ["L7q"])):
        m = grundplatte(r1, r2, lin)
        log = []
        still(mesher.modell_vernetzen, m, log, workers=1)
        a, b = auf_x(m, "F1"), auf_x(m, "F2")
        w = w_max(m)
        warn = [z for z in log if "nicht geteilt" in z]
        check(f"**B'8 Polylinie gegen Polylinie ({art}): an den fremden Knoten geteilt – alle Knoten auf "
              "x = 2 gemeinsam, w_max wie mit Einzellinien (zwei Wege)**",
              a == b and len(a) > 2 and abs(w - w_ref) <= 1e-6 * w_ref and not warn
              and not schalennetz_warnung(m),
              f"F1 {len(a)}, F2 {len(b)}, gemeinsam {len(a & b)}; w_max {w * 1e3:.2f} mm, Einzellinien "
              f"{w_ref * 1e3:.2f} mm; {warn[:1]}")
    # ein Netz von vorher (getrennt) wird gemeldet
    m = grundplatte(["L7p"], ["L7q"], {"L7p": [1, 6, 4], "L7q": [1, 7, 4]})
    getrennt_vernetzen(m)
    a, b = auf_x(m, "F1"), auf_x(m, "F2")
    lose = rippen(m)
    warn = schalennetz_warnung(m)
    check("**B'8: getrenntes Netz Polylinie gegen Polylinie – Eingabeprüfung und Merkmal "
          "„schalennetz_rippe_polylinie“ melden es**",
          len(a & b) < len(a) and bool(warn) and betrifft("schalennetz_rippe_polylinie", m)
          and lose and all(x[5] == "polylinie" for x in lose),
          f"gemeinsam {len(a & b)} von {len(a)}; {warn[:1]}")


def test_merkmal_stand():
    mk = rv.merkmal("schalennetz_rippe_polylinie")
    check("Merkmal „schalennetz_rippe_polylinie“: Korrektur am Modell, Fehlerkorrektur Stand 52, "
          "Verfahrensstand ≥ 52",
          mk is not None and mk.import_korrektur and mk.wechsel[-1].stand == 52
          and mk.wechsel[-1].art == rv.FEHLERKORREKTUR and rv.VERFAHRENSSTAND >= 52,
          f"{mk.wechsel if mk else '-'}")


def main():
    for t in (test_fuge_schalen, test_flaechenlager_hinweis_umbenennen, test_rippe_getrennt,
              test_polylinie_gegen_polylinie, test_merkmal_stand):
        try:
            t()
        except Exception as ex:                    # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{getattr(t, '__name__', 'test')} ohne Ausnahme", False, f"{type(ex).__name__}: {ex}")
    n_ok = sum(1 for _n, ok in RESULTS if ok)
    print(f"\n{n_ok}/{len(RESULTS)} Prüfungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
