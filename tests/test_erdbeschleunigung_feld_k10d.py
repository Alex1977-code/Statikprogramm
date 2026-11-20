"""
Behebung vom 16.11.2026, Runde k10d: Erdbeschleunigung eines Lastfalls als
numpy-Feld.

Die Erdbeschleunigung eines Lastfalls (``LoadCase.gravity``) ist nach dem
Laden eine Liste, nach ``Model.set_gravity``, dem Setter ``Model.gravity = …``
und schon nach dem Lesen von ``Model.gravity`` (die Oberflaeche liest es fuer
das Haekchen „Eigengewicht“) ein numpy-Feld. Bis Stand 65 pruefte der Code an
sechs Stellen mit ``lc.gravity or [...]`` auf den Wahrheitswert; mit einem Feld
aus drei Zahlen ist der mehrdeutig (ValueError):

* rechenverfahren._fachwerk_mit_querlast und _querlast_lastfaelle warfen; die
  Statusbewertung fing das ab und liess das Merkmal „Fachwerkstab mit
  Querlast“ still weg - eine Ergebnisdatei vom alten Verfahren (qL²/24 statt
  qL²/8 im Feld) blieb ohne „möglicherweise betroffen“.
* rechenverfahren._maske_kette_lastfaelle (Punktmasse unter Eigengewicht an
  einem Knoten, der seit Stand 65 mittraegt) ebenso: das Merkmal
  „Knotenlast über Starrkörper bei abgeschalteten Elementen“ fehlte still.
* rechenverfahren._versatz_achsen_arm fiel in seinen Ausnahmezweig und
  meldete „betroffen“ auch ohne Stabmasse (zu vorsichtig, hier nur auf
  Gleichheit mit der Liste geprueft).
* vorspannkraft._nur_vorspannung und vorspannung.gruppen_finden warfen:
  „Lasten › Vorspannung › Je Anker zuordnen …“ brach ab, der Importhinweis
  bekam die Kraft X nach der Rechnung nicht (der Aufrufer schluckt die
  Ausnahme).

Die gemeinsame Hilfsfunktion model.erdbeschleunigung / hat_erdbeschleunigung
liest Liste, Tupel, Feld und None gleich.

Sollwerte, je zwei Wege: Anker A (A = 10 cm²) und Klemmteil K (40 cm²),
beide L = 2 m zwischen Boden und Kopf, Vorspannung N0 = 100 kN als
eingepraegte Dehnung: Hand X = N0 kK / (kA + kK) = 100 · 40 / 50 = 80 kN;
Gegenrechnung N im Anker aus der statischen Rechnung des Lastfalls.
Merkmale: Referenz ist dasselbe Modell mit der Erdbeschleunigung als Liste.

Aufruf:  python -m tests.test_erdbeschleunigung_feld_k10d
"""
import contextlib
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:96s} {str(detail)[:240]}")
    return ok


def _still(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


def _versuch(fn, *a, **kw):
    """(Ergebnis, None) oder (None, „Ausnahme: …“)."""
    try:
        return fn(*a, **kw), None
    except Exception as ex:              # noqa: BLE001
        return None, f"{type(ex).__name__}: {str(ex)[:90]}"


G = 9.81
#: die Arten, eine Erdbeschleunigung anzugeben
WIE = ("liste", "set_gravity", "setter", "gelesen", "tupel")


def _g_setzen(m, wie, g=-G, fall="LF1"):
    """Erdbeschleunigung (0, 0, g) in ``fall`` auf die Art ``wie``."""
    if wie == "liste":
        m.load_cases[fall].gravity = [0.0, 0.0, g]
    elif wie == "tupel":
        m.load_cases[fall].gravity = (0.0, 0.0, g)
    elif wie == "set_gravity":
        m.set_gravity(g, case=fall)
    else:
        m.active_case = fall
        if wie == "setter":
            m.gravity = [0.0, 0.0, g]
        else:                                      # gelesen: Model.gravity wandelt in ein Feld
            m.load_cases[fall].gravity = [0.0, 0.0, g]
            _ = m.gravity
    return m


# --------------------------------------------------------------------------
# 1) die Hilfsfunktion
# --------------------------------------------------------------------------
def test_hilfsfunktion():
    from statik3d import model as mm
    from statik3d.model import LoadCase
    f = getattr(mm, "erdbeschleunigung", None)
    h = getattr(mm, "hat_erdbeschleunigung", None)
    if not check("model.erdbeschleunigung und hat_erdbeschleunigung vorhanden", f is not None and h is not None):
        return
    for wert, soll in (([0.0, 0.0, -G], [0.0, 0.0, -G]), (np.array([1.0, 2.0, -G]), [1.0, 2.0, -G]),
                       ((0.0, 0.0, 0.0), [0.0, 0.0, 0.0]), (None, [0.0, 0.0, 0.0]),
                       (np.zeros(3), [0.0, 0.0, 0.0])):
        lc = LoadCase("X")
        lc.gravity = wert
        ist = f(lc)
        check(f"erdbeschleunigung({type(wert).__name__} {wert}) = {soll}, hat = {any(soll)}",
              isinstance(ist, np.ndarray) and ist.shape == (3,) and np.array_equal(ist, soll)
              and h(lc) is bool(any(soll)), f"{ist} {h(lc)}")
    check("ohne Attribut gravity: Nullvektor, keine Erdbeschleunigung",
          np.array_equal(f(object()), np.zeros(3)) and h(object()) is False)


# --------------------------------------------------------------------------
# 2) Merkmal „Fachwerkstab mit Querlast“
# --------------------------------------------------------------------------
def _fachwerk(wie, schraeg=True, g=-G):
    from statik3d.model import Model, Material, Section
    m = Model("G")
    m.add_material(Material("ST", E=210e9, nu=0.3, rho=7850.0, fy=355e6))
    m.add_section(Section("Q", A=1e-3, Iy=1e-6, Iz=1e-6, It=1e-7, zmax=0.05, ymax=0.05))
    a = m.add_node(0, 0, 0)
    b = m.add_node(3, 0, 1) if schraeg else m.add_node(0, 0, 3)
    m.add_element("truss", [a, b], "ST", "Q")
    m.fix(a, "all")
    m.fix(b, "all")
    return _g_setzen(m, wie, g)


def _betroffen_alt(m, name):
    """Status einer Ergebnisdatei, die das Merkmal ``name`` mit dem alten
    Wert gerechnet hat (alle anderen wie heute)."""
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal(name)
    mer = dict(rv.aktuelle_merkmale(m))
    mer[name] = mk.wechsel[-1].alt
    return rv.betroffen(m, mer)


def test_fachwerk_querlast():
    from statik3d import rechenverfahren as rv
    titel = rv.merkmal("fachwerk_querlast").titel
    ref = _betroffen_alt(_fachwerk("liste"), "fachwerk_querlast")
    check("Referenz (Liste): Datei mit altem Verfahren, schräger Fachwerkstab unter Eigengewicht → betroffen",
          titel in ref, ref[:160])
    for wie in WIE:
        m = _fachwerk(wie)
        r, ex = _versuch(rv._fachwerk_mit_querlast, m)
        check(f"g als {wie}: _fachwerk_mit_querlast schräg = True, ohne Ausnahme", ex is None and r is True,
              ex or r)
        r, ex = _versuch(rv._querlast_lastfaelle, m)
        check(f"g als {wie}: _querlast_lastfaelle = {{LF1}}", ex is None and r == {"LF1"}, ex or r)
        t = _betroffen_alt(m, "fachwerk_querlast")
        check(f"g als {wie}: Status nennt „{titel}“ wie mit der Liste", titel in t, t[:160])
        for schraeg, g, text in ((False, -G, "lotrecht unter Eigengewicht"), (True, 0.0, "schräg ohne Eigengewicht")):
            m2 = _fachwerk(wie, schraeg=schraeg, g=g)
            r, ex = _versuch(rv._fachwerk_mit_querlast, m2)
            check(f"g als {wie}: Fachwerkstab {text}: nicht betroffen", ex is None and r is False, ex or r)


# --------------------------------------------------------------------------
# 3) Merkmal „Knotenlast über Starrkörper bei abgeschalteten Elementen“
#    (Punktmasse unter Eigengewicht, Runde k9)
# --------------------------------------------------------------------------
def test_maske_punktmasse():
    from statik3d import rechenverfahren as rv
    from tests.test_maske_starrkoerper_k9 import modell, MASSE
    titel = rv.merkmal("maske_starrkoerper_last").titel

    def bau(wie):
        m, _b, p = modell("rbe2", "situation")
        m.add_punktmasse(p, MASSE)
        return _g_setzen(m, wie)
    ref = _betroffen_alt(bau("liste"), "maske_starrkoerper_last")
    check("Referenz (Liste): Punktmasse am RBE2-Knoten, Situation, Eigengewicht → betroffen", titel in ref,
          ref[:160])
    for wie in WIE:
        m = bau(wie)
        r, ex = _versuch(rv._maske_kette_lastfaelle, m)
        check(f"g als {wie}: _maske_kette_lastfaelle = {{LF1}}", ex is None and r == {"LF1"}, ex or r)
        t = _betroffen_alt(m, "maske_starrkoerper_last")
        check(f"g als {wie}: Status nennt „{titel}“ wie mit der Liste", titel in t, t[:160])
        m0 = bau(wie)
        _g_setzen(m0, wie, 0.0)
        r, ex = _versuch(rv._maske_kette_lastfaelle, m0)
        check(f"g als {wie}, g = 0: Punktmasse ohne Eigengewicht trägt nichts, nicht betroffen",
              ex is None and r == set(), ex or r)


# --------------------------------------------------------------------------
# 4) Merkmal „Achsen, Stablast und Sollkraft an Stäben mit Versatz“
# --------------------------------------------------------------------------
def test_versatz_eigengewicht():
    from statik3d import rechenverfahren as rv
    from statik3d.model import Model, Material, Section

    def bau(wie, rho):
        m = Model("V")
        m.add_material(Material("ST", E=210e9, nu=0.3, rho=rho, fy=355e6))
        m.add_section(Section("Q", A=1e-2, Iy=8e-5, Iz=8e-5, It=1e-5, zmax=0.1, ymax=0.1))
        a, b = m.add_node(0, 0, 0), m.add_node(4, 0, 0)
        m.add_element("beam", [a, b], "ST", "Q", exzentrizitaet=[[0, 0, 0.5], [0, 0, 0.5]])
        m.fix(a, "all")
        m.load_cases["LF1"].theorie = "III"
        return _g_setzen(m, wie)
    for rho in (0.0, 7850.0):
        soll = rv._versatz_achsen_arm(bau("liste", rho))
        check(f"Referenz (Liste), Dichte {rho:.0f}: betroffen = {rho > 0}", soll is (rho > 0), soll)
        for wie in WIE[1:]:
            ist = rv._versatz_achsen_arm(bau(wie, rho))
            check(f"g als {wie}, Dichte {rho:.0f}: betroffen wie mit der Liste ({soll})", ist is soll, ist)


# --------------------------------------------------------------------------
# 5) Vorspannung: Gruppen je Anker und Importhinweis nach der Rechnung
# --------------------------------------------------------------------------
E = 210e9
L = 2.0
A_A, A_K = 1e-3, 4e-3
N0 = 100e3
ALPHA = 1e-5
X_HAND = N0 * (E * A_K / L) / (E * A_A / L + E * A_K / L)        # 80 kN


def _anker(wie):
    """Boden G (fest), Kopf H (nur z frei); Anker A und Klemmteil K als
    Fachwerkstaebe G-H. LT: Vorspannung N0 als Temperatur auf A, g = 0;
    LV: N0 als eingepraegte Dehnung F_v (Lasten › Vorspannung), g = 0;
    LG: wie LT, mit Eigengewicht."""
    from statik3d.model import LoadCase, Material, Model, Section, TempLoad
    m = Model("Anker")
    m.add_material(Material("Stahl", E=E, nu=0.3, rho=7850.0, alpha=ALPHA))
    g0 = m.add_node(0.0, 0.0, 0.0)
    g2 = m.add_node(0.0, 0.0, 0.0)
    h = m.add_node(0.0, 0.0, L)
    m.fix(g0, "all")
    m.fix(g2, "all")
    m.fix(h, [0, 1, 3, 4, 5])
    el = {}
    for name, A, k in (("A", A_A, g0), ("K", A_K, g2)):
        m.add_section(Section.circle("Q_" + name, float(np.sqrt(4.0 * A / np.pi))))
        el[name] = m.add_element("truss", [k, h], "Stahl", "Q_" + name)
        m.add_member(name, [el[name]])
    m.load_cases.pop("LF1", None)
    for lf in ("LT", "LV", "LG"):
        m.load_cases[lf] = LoadCase(lf, category="P")
    for lf in ("LT", "LG"):
        m.load_cases[lf].temp_loads.append(TempLoad(el["A"], -N0 / (E * A_A * ALPHA)))
    m.add_vorspannung("A", N0, case="LV")
    for lf, g in (("LT", 0.0), ("LV", 0.0), ("LG", -G)):
        _g_setzen(m, wie, g, lf)
    m.active_case = "LT"
    return m, el


def test_vorspannung():
    from statik3d import solver
    from statik3d import vorspannung as vsp
    from statik3d import vorspannkraft as vk
    ref = None
    for wie in WIE:
        m, el = _anker(wie)
        erg = {lf: _still(solver.solve_static, m, case=lf) for lf in ("LT", "LV", "LG")}
        n = {lf: float(r.beam_forces[int(el["A"])]["N"][1]) for lf, r in erg.items()}
        n_fuss = {lf: float(r.beam_forces[int(el["A"])]["N"][0]) for lf, r in erg.items()}
        if wie == "liste":
            ref = n
            check(f"Gegenrechnung: N im Anker LT = Hand X = {X_HAND / 1e3:.3f} kN",
                  abs(n["LT"] - X_HAND) <= 1e-6 * X_HAND, f"{n['LT'] / 1e3:.6f} kN")
            check(f"Gegenrechnung: N im Anker LV = Hand X = {X_HAND / 1e3:.3f} kN",
                  abs(n["LV"] - X_HAND) <= 1e-6 * X_HAND, f"{n['LV'] / 1e3:.6f} kN")
            check("Gegenrechnung: Eigengewicht ändert N am Fuß des Ankers (LG ≠ LT)",
                  abs(n_fuss["LG"] - n_fuss["LT"]) > 1.0, f"{n_fuss['LG'] / 1e3:.6f} / {n_fuss['LT'] / 1e3:.6f} kN")
        else:
            check(f"g als {wie}: N im Anker wie mit der Liste (LT, LV, LG)",
                  all(abs(n[k] - ref[k]) <= 1e-9 * X_HAND for k in n), n)
        for lf, soll in (("LT", True), ("LV", False), ("LG", False)):
            r, ex = _versuch(vk._nur_vorspannung, m, m.load_cases[lf])
            check(f"g als {wie}: _nur_vorspannung({lf}) = {soll}", ex is None and r is soll, ex or r)
        gr, ex = _versuch(vsp.gruppen_finden, m, erg)
        if not check(f"g als {wie}: gruppen_finden mit Ergebnissen ohne Ausnahme", ex is None, ex):
            continue
        by = {g["art"]: g for g in gr}
        gdt, gfv = by.get(vsp.ART_DT), by.get(vsp.ART_DEHNUNG)
        check(f"g als {wie}: ΔT-Gruppe LT+LG, X = N(LT) = Hand, nur aus LT",
              gdt is not None and sorted(gdt["faelle"]) == ["LG", "LT"] and gdt["X"] is not None
              and all(abs(x - X_HAND) <= 1e-6 * X_HAND for x in gdt["X"])
              and "LT" in gdt["X_herkunft"] and "LG" not in gdt["X_herkunft"],
              gdt and (gdt["faelle"], gdt["X"], gdt["X_herkunft"]))
        check(f"g als {wie}: F_v-Gruppe LV, X = N(LV) = Hand aus dem Ergebnis",
              gfv is not None and gfv["X"] is not None and all(abs(x - X_HAND) <= 1e-6 * X_HAND for x in gfv["X"])
              and "LV" in gfv["X_herkunft"], gfv and (gfv["faelle"], gfv["X"], gfv["X_herkunft"]))
        # Importhinweis: X nach der Rechnung nachreichen (Import konnte nicht rechnen)
        hinw = _still(vk.import_hinweise, m)
        for h_ in m.importhinweise:
            if h_.get("art") == "vorspannung":
                h_["X"] = None
        texte, ex = _versuch(vk.hinweise_nachreichen, m, erg)
        h_ = next((x for x in m.importhinweise if x.get("art") == "vorspannung"), None)
        check(f"g als {wie}: Importhinweis bekommt X = N(LT) = Hand nach der Rechnung, nur aus LT",
              ex is None and bool(hinw) and h_ is not None and h_.get("X") is not None
              and all(abs(x - X_HAND) <= 1e-6 * X_HAND for x in h_["X"]) and h_.get("X_aus") == ["LT"]
              and len(texte or []) == 1,
              ex or (h_ and (h_.get("X"), h_.get("X_aus")), texte))


def main():
    for t in (test_hilfsfunktion, test_fachwerk_querlast, test_maske_punktmasse, test_versatz_eigengewicht,
              test_vorspannung):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:          # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
        sys.stdout.flush()
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    sys.stdout.flush()
    return 0 if not schlecht else 1


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
