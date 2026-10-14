"""Kopplungen an Knoten ohne wirksames Element (14.10.2026).

Befund am Drehlager (gestufter Spannschritt, Stand b3cfb22): Im Spannschritt
sind die Ankerstaebe inaktiv (vorspannkraft._spannzustand), ihre Enden tragen
nur das Kraeftepaar ±F_soll. assemble.kopplungen liess aber jede Kopplung weg,
an deren Knoten kein wirksames Element hing. Der obere Stabknoten ist zugleich
Master seiner starren Scheibe (K157 an F37) und hing dann an nichts: alle sechs
FHG automatisch gehalten (426 771 statt 426 867 Unbekannte), die Kraft ging in
diese Haltung statt in den Lochrand, je Spannstufe 16-mal „Knoten K157:
F_z = −314,900 kN an einem Knoten ohne Bauteil – Mechanismus“. Der Spannzustand
verformte die Platten nicht, und nach dem Verankern war N nicht F_soll.

Dieselbe Regel griff ueberall, wo ein System mit Elementmaske entsteht: in
Situationen mit abgeschalteten Elementen und - weil Model.grundmaske dann
immer eine Maske setzt - in **jeder** Rechnung, sobald ein Stab „aus“ ist.
Ein Last- oder Lagerknoten, den fugen.stabenden_koppeln an einen Koerper
haengt, verlor seine Kopplung, und seine Knotenlast fiel in load_vector still
weg (keine Meldung, ΣF stimmte mit dem verkuerzten Lastvektor).

Jetzt bleibt jede Kopplung, deren anderer Knoten wirksam ist
(situationen.kopplung_bleibt); die Kopplung eines Stabendes (RBE3) braucht
dazu einen wirksamen Koerperknoten.

Geprueft mit geschlossenen Loesungen (Federmodell): Quader hex8 1 x 1 x 1 m,
nu = 0, unten gelagert (k_B = E A / L = E), Anker von einem festen Fusspunkt
zum Master auf der Oberseite (k_A = E A_A / L_A).

1. Starre Scheibe: Spannschritt, Verankern, Zuglast - N = F_soll, der Quader
   im Spannzustand um F/k_B gestaucht, keine Meldung „Mechanismus“, ΣF/ΣM.
2. Stabende als RBE3 an den vier Knoten der Oberseite: dasselbe.
3. Lastknoten ueber stabenden_koppeln, ein Stab „aus“: die Last kommt an.
4. Derselbe Lastknoten in einer Situation mit abgeschaltetem Element.
4a. Drei Lagerknoten ueber stabenden_koppeln, ein Stab „aus“: sie tragen.
5. Ausgefallener Zugstab (nur Zug) mit Kopplung am Ende und Last am Master:
   kein neues System, die Kopplung bleibt (schon vorher richtig).
6. Ohne abgeschaltete Elemente aendert sich nichts: Kopplung zwischen zwei
   Knoten ohne wirksames Element faellt weiter weg.

Aufruf:  python -m tests.test_spannschritt_kopplung
"""
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_spannkopplung_"), "einstellungen.json")

from statik3d import fugen, solver                                  # noqa: E402
from statik3d import vorspannkraft as vk                            # noqa: E402
from statik3d.model import (Kopplung, Material, Model, NodalLoad, Section,   # noqa: E402
                            Volumenkoerper)

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:80s} {detail}")
    return ok


def nahe(name, ist, soll, tol, einheit=""):
    ist, soll = float(ist), float(soll)
    abw = abs(ist - soll) / (abs(soll) if abs(soll) > 1e-14 else 1.0)
    return check(name, abw <= tol, f"ist {ist:.9g} soll {soll:.9g} ({abw:.2e}) {einheit}")


E = 210e9
A_A = 0.5                   # Anker [m2], Laenge 2 m -> k_A = E/4
L_A = 2.0
K_A = E * A_A / L_A
K_B = E * 1.0 / 1.0         # Quader 1 x 1 x 1 m, nu = 0
F = 50e6                    # Sollkraft [N]
P = 20e6                    # Zuglast am Master [N]
INF = float("inf")
XYZ = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
#: Starre Kopplungen sind Straffedern 1e4 x der groessten Diagonale
#: (assemble.kopplungen): Verschiebungen und alles, was von der Nachgiebigkeit
#: abhaengt, liegen darum neben dem Federmodell - gemessen 1,0e-4 an der
#: Scheibe, 5,0e-4 am Stabende (RBE3, Gewichte 1/4). Weil die Straffeder sich
#: nach der groessten Diagonale des Systems richtet und der Spannschritt ohne
#: den Anker eine andere hat, liegt auch N nach dem Verankern im Ergebnis um
#: bis 2e-5 neben F_soll. Der Befund liegt mit 0,2 bis 1,0 weit darueber. Was
#: das Verriegeln exakt setzt (N_verankert), pruefen 1e-9.
TOL_STRAF = 1e-3


def _quader(m):
    """hex8 1 x 1 x 1 m, unten in z gelagert, seitlich statisch bestimmt;
    Rueckgabe (untere, obere Knoten)."""
    m.add_material(Material("S", E=E, nu=0.0, rho=7850, fy=1e12, alpha=1e-5))
    n = [m.add_node(x, y, z) for z in (0.0, 1.0) for x, y in ((0, 0), (1, 0), (1, 1), (0, 1))]
    e = m.add_element("hex8", n, "S", "")
    m.koerper["V1"] = Volumenkoerper("V1", material="S", elemente=[int(e)])
    for i in n[:4]:
        m.fix(i, [2])
    m.fix(n[0], [0, 1])
    m.fix(n[1], [1])
    m.fix(n[3], [0])
    return n[:4], n[4:]


def _anker_modell(art):
    """Quader, Anker G-M; M haengt als Master einer starren Scheibe (``art``
    "scheibe") oder als Stabende RBE3 ("rbe3") an den vier Knoten der
    Oberseite. Lastfaelle V (nur Sollkraft) und VP (dazu P nach oben an M)."""
    m = Model("Anker an Quader")
    unten, oben = _quader(m)
    G = m.add_node(0.5, 0.5, -1.0)
    M = m.add_node(0.5, 0.5, 1.0)
    m.fix(G, "all")
    m.add_section(Section.circle("QA", float(np.sqrt(4.0 * A_A / np.pi))))
    e = m.add_element("truss", [G, M], "S", "QA")
    m.add_member("A1", [e])
    gruppe = (fugen.STARR_GRUPPE + "F1") if art == "scheibe" else (fugen.STABENDE_GRUPPE + f"K{M}")
    for s in oben:
        m.kopplungen.append(Kopplung(int(M), int(s), [list(v) for v in XYZ], [INF] * 3, gruppe))
    for lf in ("V", "VP"):
        m.add_load_case(lf).gravity = [0.0, 0.0, 0.0]
        m.add_vorspannung("A1", F, case=lf, sollkraft=True)
    m.case("VP").nodal_loads.append(NodalLoad(M, [0.0, 0.0, P, 0.0, 0.0, 0.0]))
    return m, e, M, oben


def _rechne(m, lf):
    meld = []
    r = solver.solve_static(m, case=lf, progress=lambda t, *a: meld.append(str(t)))
    return r, meld


def _fhg(meld):
    """Zahlen aus „Gleichungssystem aufgestellt (n aktive FHG)“ in der Reihenfolge."""
    out = []
    for z in meld:
        if z.startswith("Gleichungssystem aufgestellt ("):
            try:
                out.append(int(z.split("(")[1].split()[0]))
            except (IndexError, ValueError):
                pass
    return out


def _sigma_r(r):
    R = np.asarray(r.reactions, float).reshape(-1, 6)
    return R[:, :3].sum(axis=0)


def _gg_ok(name, r):
    g = r.info.get("gleichgewicht_global") or {}
    check(name, bool(g) and g.get("ok") and not solver.gueltigkeit(r.info),
          f"rel_F {g.get('rel_F')}, rel_M {g.get('rel_M')}, „{solver.gueltigkeit(r.info)[:60]}“")


def _anker_pruefen(art):
    titel = "starre Scheibe (RBE2)" if art == "scheibe" else "Stabende (RBE3)"
    print(f"\n--- Anker über {titel} am Quader: Spannschritt, Verankern, Zuglast ---")
    alt = vk.LINEAR_WEG
    vk.LINEAR_WEG = vk.WEG_SPANNEN          # linear, aber mit Spannschritt
    try:
        m, e, M, oben = _anker_modell(art)
        r, meld = _rechne(m, "V")
        m2, e2, M2, _o = _anker_modell(art)
        r2, meld2 = _rechne(m2, "VP")
    finally:
        vk.LINEAR_WEG = alt
    vs = r.info.get("vorspannung") or {}
    check(f"{art}: gerechnet über Spannen und Verriegeln", vs.get("weg") == vk.WEG_SPANNEN, str(vs.get("weg")))
    mech = [z for z in meld + meld2 if "Mechanismus" in z]
    check(f"{art}: keine Meldung „Mechanismus“ (Spannschritt und Lasten)", not mech,
          (mech[0][:110] if mech else ""))
    fhg = _fhg(meld)
    check(f"{art}: Spannschritt mit derselben Zahl Unbekannter wie das ganze System",
          len(fhg) >= 2 and len(set(fhg)) == 1, f"FHG je System {fhg}")
    sp = ((getattr(r, "vorspannzustaende", None) or {}).get("spannen") or [None])[-1]
    if sp is None:
        check(f"{art}: Spannzustand abgelegt", False)
        return
    check(f"{art}: Spannzustand ohne Last an automatisch gehaltenen FHG",
          not sp.info.get("auto_gehalten"), str((sp.info.get("auto_gehalten") or [{}])[0].get("text", ""))[:110])
    uo = np.asarray(sp.u)[oben, 2]
    nahe(f"{art}: Spannzustand: Oberseite um F/k_B gestaucht (Mittel)", uo.mean(), -F / K_B, TOL_STRAF, "m")
    check(f"{art}:   … gleichmäßig (alle vier Knoten)", np.ptp(uo) <= 1e-9 * F / K_B,
          f"Spanne {np.ptp(uo):.2e} m")
    nahe(f"{art}: Spannzustand: Master folgt der Oberseite", np.asarray(sp.u)[M, 2], -F / K_B, TOL_STRAF, "m")
    st = (vs.get("staebe") or {}).get("A1", {})
    nahe(f"{art}: nach dem Verankern N = F_soll", st.get("N_verankert", 0.0), F, 1e-9, "N")
    nahe(f"{art}: ohne weitere Last N = F_soll im Ergebnis", float(r.beam_forces[int(e)]["N"][1]), F, TOL_STRAF, "N")
    nahe(f"{art}: Kopf in der Lage des Spannschritts", np.asarray(r.u)[M, 2], -F / K_B, TOL_STRAF, "m")
    sr = _sigma_r(r)
    check(f"{art}: nur Vorspannung: ΣR = 0 (innerer Zwang)", np.abs(sr).max() <= 1e-9 * F, f"ΣR {sr}")
    _gg_ok(f"{art}: globale Kontrolle ΣF/ΣM erfüllt (V)", r)
    nahe(f"{art}: mit Zuglast N = F_soll + k_A/(k_A + k_B)·P", float(r2.beam_forces[int(e2)]["N"][1]),
         F + K_A / (K_A + K_B) * P, TOL_STRAF, "N")
    nahe(f"{art}: mit Zuglast u_M = −F/k_B + P/(k_A + k_B)", np.asarray(r2.u)[M2, 2],
         -F / K_B + P / (K_A + K_B), TOL_STRAF, "m")
    nahe(f"{art}: mit Zuglast ΣR_z = −P", _sigma_r(r2)[2], -P, 1e-9, "N")
    _gg_ok(f"{art}: globale Kontrolle ΣF/ΣM erfüllt (VP)", r2)


def test_scheibe():
    _anker_pruefen("scheibe")


def test_rbe3():
    _anker_pruefen("rbe3")


def _lastknoten_modell():
    """Quader, Lastknoten L mitten auf der Oberseite (ohne Element), von
    stabenden_koppeln angehaengt, Last P nach unten; dazu ein Stab S1 abseits
    zwischen zwei festen Knoten (zum Abschalten)."""
    m = Model("Lastknoten")
    unten, oben = _quader(m)
    L = m.add_node(0.5, 0.5, 1.0)
    a = m.add_node(3.0, 0.0, 0.0)
    b = m.add_node(3.0, 0.0, 1.0)
    m.fix(a, "all")
    m.fix(b, "all")
    m.add_section(Section.circle("QS", 0.05))
    es = m.add_element("truss", [a, b], "S", "QS")
    m.add_member("S1", [es])
    lc = m.add_load_case("LF1")
    lc.gravity = [0.0, 0.0, 0.0]
    lc.nodal_loads.append(NodalLoad(L, [0.0, 0.0, -P, 0.0, 0.0, 0.0]))
    fugen.stabenden_koppeln(m, [])
    return m, L, oben, es


def _lastknoten_pruefen(was, m, L, oben, unten_idx=None):
    k = [kp for kp in m.kopplungen if int(kp.node_a) == L]
    check(f"{was}: stabenden_koppeln hängt den Lastknoten an den Quader", len(k) >= 1, f"{len(k)} Kopplungen")
    r, meld = _rechne(m, "LF1")
    sr = _sigma_r(r)
    nahe(f"{was}: die Last kommt an: ΣR_z = P", sr[2], P, 1e-9, "N")
    uo = np.asarray(r.u)[oben, 2]
    check(f"{was}: der Quader ist gestaucht (Oberseite senkt sich)", float(uo.mean()) < -0.5 * P / K_B,
          f"u_z Mittel {uo.mean():.4e} m, Federmodell um −P/k_B = {-P / K_B:.4e} m")
    mech = [z for z in meld if "Mechanismus" in z]
    check(f"{was}: keine Meldung „Mechanismus“", not mech, (mech[0][:110] if mech else ""))
    g = r.info.get("gleichgewicht_global") or {}
    F_last = (g.get("F_last") or [0, 0, 0])[2]
    nahe(f"{was}: die Gleichgewichtskontrolle sieht die Last (F_last,z = −P)", F_last, -P, 1e-9, "N")
    _gg_ok(f"{was}: ΣF/ΣM erfüllt", r)


def test_stab_aus():
    print("\n--- Lastknoten über stabenden_koppeln, ein Stab „aus“ ---")
    m, L, oben, es = _lastknoten_modell()
    m.members["S1"].aus = True
    _lastknoten_pruefen("Stab aus", m, L, oben)


def test_situation():
    print("\n--- Lastknoten über stabenden_koppeln, Situation mit abgeschaltetem Element ---")
    from statik3d.model import Situation
    m, L, oben, es = _lastknoten_modell()
    m.situationen["ohne S1"] = Situation("ohne S1", "", [int(es)], "S1 abgeschaltet")
    m.load_cases["LF1"].situation = "ohne S1"
    _lastknoten_pruefen("Situation", m, L, oben)


def test_lagerknoten():
    print("\n--- Lagerknoten über stabenden_koppeln, ein Stab „aus“ ---")
    m = Model("Lagerknoten")
    m.add_material(Material("S", E=E, nu=0.0, rho=7850, fy=1e12, alpha=1e-5))
    n = [m.add_node(x, y, z) for z in (0.0, 1.0) for x, y in ((0, 0), (1, 0), (1, 1), (0, 1))]
    e = m.add_element("hex8", n, "S", "")
    m.koerper["V1"] = Volumenkoerper("V1", material="S", elemente=[int(e)])
    m.fix(n[0], [0, 1])
    m.fix(n[1], [1])
    m.fix(n[3], [0])
    # senkrecht nur ueber drei Lagerknoten ohne Element auf der Unterseite
    lager = [m.add_node(x, y, 0.0) for x, y in ((0.25, 0.25), (0.75, 0.25), (0.5, 0.75))]
    for k in lager:
        m.fix(k, "all")
    a = m.add_node(3.0, 0.0, 0.0)
    b = m.add_node(3.0, 0.0, 1.0)
    m.fix(a, "all")
    m.fix(b, "all")
    m.add_section(Section.circle("QS", 0.05))
    m.add_member("S1", [m.add_element("truss", [a, b], "S", "QS")])
    m.members["S1"].aus = True
    lc = m.add_load_case("LF1")
    lc.gravity = [0.0, 0.0, 0.0]
    for k in n[4:]:
        lc.nodal_loads.append(NodalLoad(k, [0.0, 0.0, -P / 4.0, 0.0, 0.0, 0.0]))
    fugen.stabenden_koppeln(m, [])
    check("stabenden_koppeln hängt die drei Lagerknoten an den Quader",
          {int(kp.node_a) for kp in m.kopplungen} == set(lager), f"{len(m.kopplungen)} Kopplungen")
    try:
        r, meld = _rechne(m, "LF1")
    except Exception as ex:          # noqa: BLE001
        check("rechnet (Quader senkrecht über die Lagerknoten gehalten)", False, f"{type(ex).__name__}: {str(ex)[:110]}")
        return
    R = np.asarray(r.reactions, float).reshape(-1, 6)
    nahe("die Lagerknoten tragen die Last: ΣR_z an ihnen = P", R[lager, 2].sum(), P, 1e-9, "N")
    check("keine freie Bewegung (Hilfsfesselung)", not getattr(r, "singular", None),
          str(getattr(r, "singular", None))[:110])
    uo = np.asarray(r.u)[n[4:], 2]
    check("der Quader senkt sich um die Größe P/k_B (Lager über Straffedern)",
          -3.0 * P / K_B < float(uo.mean()) < -0.5 * P / K_B,
          f"u_z oben {uo.mean():.4e} m, P/k_B = {P / K_B:.4e} m")
    _gg_ok("ΣF/ΣM erfüllt", r)


def test_zugstab_ausfall():
    print("\n--- Ausgefallener Zugstab mit Kopplung am Ende, Last am Master ---")
    m = Model("Zugstab fällt aus")
    unten, oben = _quader(m)
    G = m.add_node(0.5, 0.5, -1.0)
    M = m.add_node(0.5, 0.5, 1.0)
    m.fix(G, "all")
    m.add_section(Section.circle("QA", float(np.sqrt(4.0 * A_A / np.pi))))
    e = m.add_element("truss", [G, M], "S", "QA")
    m.elements[e].nur = "zug"
    m.add_member("Z1", [e])
    for s in oben:
        m.kopplungen.append(Kopplung(int(M), int(s), [list(v) for v in XYZ], [INF] * 3,
                                     fugen.STARR_GRUPPE + "F1"))
    lc = m.add_load_case("LF1")
    lc.gravity = [0.0, 0.0, 0.0]
    lc.nodal_loads.append(NodalLoad(M, [0.0, 0.0, -P, 0.0, 0.0, 0.0]))
    r, meld = _rechne(m, "LF1")
    check("Zugstab unter Druck fällt aus", any("1 Stab trägt nicht" in z or "ausgefallen" in z for z in meld)
          or abs(float(r.beam_forces[int(e)]["N"][1])) <= 1e-9 * P,
          f"N {float(r.beam_forces[int(e)]['N'][1]):.4g} N")
    nahe("der Quader trägt P allein: u_M = −P/k_B", np.asarray(r.u)[M, 2], -P / K_B, TOL_STRAF, "m")
    nahe("ΣR_z = P (alles am Quader)", _sigma_r(r)[2], P, 1e-9, "N")
    mech = [z for z in meld if "Mechanismus" in z]
    check("keine Meldung „Mechanismus“", not mech, (mech[0][:110] if mech else ""))
    _gg_ok("ΣF/ΣM erfüllt", r)


def test_beide_seiten_tot():
    print("\n--- Absicht bleibt: Kopplung zwischen zwei Knoten ohne wirksames Element fällt weg ---")
    from statik3d import assemble as asm
    from statik3d.situationen import aktive_knoten, kopplung_bleibt
    m, e, M, oben = _anker_modell("scheibe")
    aktiv = np.ones(len(m.elements), bool)
    aktiv[0] = False                       # der Quader aus, Anker wirksam
    kn = aktive_knoten(m, aktiv)
    check("Quader aus, Master am Anker: Scheibe bleibt (Master wirksam)",
          all(kopplung_bleibt(m, kp, kn) for kp in m.kopplungen))
    aktiv[:] = False
    kn = aktive_knoten(m, aktiv)
    check("alles aus: keine Kopplung bleibt", not any(kopplung_bleibt(m, kp, kn) for kp in m.kopplungen))
    m3, e3, M3, oben3 = _anker_modell("rbe3")
    aktiv = np.ones(len(m3.elements), bool)
    aktiv[0] = False                       # Quader aus: das Stabende haette keinen Koerper
    kn = aktive_knoten(m3, aktiv)
    check("Stabende (RBE3) ohne wirksamen Körperknoten fällt weg (sonst frei bewegliche Knoten)",
          not any(kopplung_bleibt(m3, kp, kn) for kp in m3.kopplungen))
    aktiv = np.ones(len(m3.elements), bool)
    aktiv[1] = False                       # Anker aus, Quader wirksam: bleibt
    kn = aktive_knoten(m3, aktiv)
    check("Stabende (RBE3) mit inaktivem Stab und wirksamem Körper bleibt",
          all(kopplung_bleibt(m3, kp, kn) for kp in m3.kopplungen))
    K0 = asm.stiffness(m, 1, None)
    K1 = asm.stiffness(m, 1, np.ones(len(m.elements), bool))
    check("Maske ganz wirksam = ohne Maske, bitgleich", (K0 != K1).nnz == 0)


def main():
    for t in (test_scheibe, test_rbe3, test_stab_aus, test_situation, test_lagerknoten, test_zugstab_ausfall,
              test_beide_seiten_tot):
        try:
            t()
        except Exception as ex:                 # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{t.__name__} ohne Ausnahme", False, f"{type(ex).__name__}: {ex}")
    fehler = [n for n, ok in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(fehler)} von {len(RESULTS)} Prüfungen bestanden")
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
