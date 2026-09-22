"""Halt fuer Teile ohne geschlossene Bedingung (17.09.2026).

Der nach oben gezogene Block des Beispiels "Block mit Reibung" verliert im
zweiten Schritt (fast) alle Kontaktbedingungen; ohne Halt ist das System
singulaer (tests/test_abbruch.py prueft diesen Abbruch mit abgeschaltetem
Halt). Mit dem Halt bleiben Bedingungen mit dem kleinsten Spalt geschlossen,
der Schritt wird noch einmal geloest, die Iteration konvergiert - und weil
der Block am Ende an den gehaltenen Punkten zieht, hebt er wirklich ab: der
Abbruch kommt dann mit der gehaltenen Lage als Teilergebnis und dem Zeiger.
Ein Stift, dessen gehaltene Punkte in Druck enden, laeuft durch.

Aufruf:  python -m tests.test_kontakthalt
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import solver                                   # noqa: E402
from statik3d.examples_lib import block_friction_example      # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:74s} {detail}")
    return ok


def _hochgezogen():
    m = block_friction_example()
    for l in m.case().nodal_loads:
        l.F[2] = abs(l.F[2])
    return m


def test_halt():
    """Der nach oben gezogene Block: der Halt rettet den Schritt (kein
    singulaeres System mehr), aber am Ende zieht der Block an den gehaltenen
    Punkten - er hebt wirklich ab. Dann kommt der Abbruch mit der gehaltenen
    Lage als Teilergebnis und dem Zeiger, statt eines stillen Ergebnisses."""
    m = _hochgezogen()
    alt = solver.StaticSystem.hilfsfesselung
    solver.StaticSystem.hilfsfesselung = lambda self: False
    ex = None
    try:
        solver.solve_static(m)
    except RuntimeError as e:
        ex = e
    finally:
        solver.StaticSystem.hilfsfesselung = alt
    check("Block nach oben gezogen: Abbruch, weil die gehaltenen Punkte Zug tragen (er hebt wirklich ab)",
          isinstance(ex, solver.KontaktAbbruch) and "gehaltenen Kontaktpunkten" in str(ex) and "Gleichgewicht" in str(ex),
          str(ex)[:140])
    if not isinstance(ex, solver.KontaktAbbruch):
        return
    r = ex.teilergebnis
    log = (r.info.get("contact_log") if r is not None else None) or []
    halt = [z for z in log if "Halt für Teile" in z]
    check("das Protokoll nennt das gehaltene Teil mit Bedingungen und Spalt",
          halt and "Teil 1" in halt[0] and "mit dem kleinsten Spalt" in halt[0] and "mm" in halt[0], str(halt[:1])[:160])
    check("das Teilergebnis ist die gehaltene Lage: endliche, kleine Verschiebung, Kontaktzustand mit gehaltenen Punkten",
          r is not None and np.isfinite(r.u).all() and float(np.abs(r.u[:, :3]).max()) < 1e-2
          and sum(1 for c in r.contact if c["status"] != "offen") >= 3,
          f"{float(np.abs(r.u[:, :3]).max()) * 1e3:.3f} mm" if r is not None else "")
    s = (r.singular if r is not None else None) or []
    check("Zeiger: der Block hebt ab und haengt an gehaltenen Punkten unter rund 90 kN Zug",
          s and s[0].art == "hebt ab" and "gehaltenen Punkten" in s[0].text and "kN Zug" in s[0].text
          and s[0].koerper == ["Teil 1"], str([x.text[:100] for x in s[:1]]))
    check("die Nummer der letzten geloesten Iteration ist die konvergierte, nicht 0", ex.iteration >= 2, str(ex.iteration))


def test_teile_bedingungen():
    """Eine Bedingung gehoert auch zum Teil ihrer Master-Knoten."""
    from statik3d.contact import ContactSystem
    from statik3d import assemble
    m = block_friction_example()
    system = solver.StaticSystem(m)
    cs = ContactSystem(m, system.K, [], None)
    cs.initialize()
    teile = solver._teile_bedingungen(m, cs)
    namen = {n for n, _kn, _c in teile}
    check("Block (Slave) und Platte (Master) haben Bedingungen", len(teile) >= 2, str(sorted(namen)))
    n_je = {n: len(c) for n, _kn, c in teile}
    check("die Platte als Master-Teil traegt dieselben Bedingungen wie der Block",
          len(set(n_je.values())) == 1, str(n_je))
    # alle Bedingungen oeffnen, dann halten: genau drei mit dem kleinsten Spalt sind zu
    for c in cs.cons:
        c.active = False
        c.g = float(np.random.default_rng(3).uniform(0, 1e-3))
    log = []
    ok = solver._freie_teile_halten(m, cs, log)
    zu = [c for c in cs.cons if c.active]
    kleinste = sorted(cs.cons, key=lambda c: c.g)[:3]
    check("Halt: drei Bedingungen mit dem kleinsten Spalt sind wieder zu, Protokollzeile",
          ok and len(zu) == 3 and set(map(id, zu)) == set(map(id, kleinste)) and log and "gehalten" in log[0], str(log[:1])[:120])
    check("ist genug zu, wird nichts gehalten", not solver._freie_teile_halten(m, cs, []))


def test_zug_am_teil_gemessen():
    """Ein Teil, das viel Druck abträgt, hebt nicht ab, weil an ein paar
    gehaltenen Punkten wenig zieht. Am Drehlager brach die Rechnung deswegen
    ab: 0,7 bis 20 kN Zug gegen 15 232 kN Schraubenvorspannung und 217,6 kN
    größte Kontaktkraft (19.09.2026, „kann es sein dass die abbruchschranke
    das problem ist“)."""
    from statik3d import solver as slv
    from statik3d.contact import Constraint

    class _CS:
        f_ref = 1.0e6                       # größte Knotenlast 1000 kN

    def _con(fn=0.0, g=0.0, kn=0.0, gehalten=False):
        c = Constraint(kind="surface", dofs=np.zeros(0, int), cn=np.zeros(0), ct=None,
                       g0=0.0, kn=kn, kt=0.0, mu=0.0, node=0, normal=np.array([0.0, 0.0, 1.0]))
        c.active, c.gehalten, c.Fn, c.g = True, gehalten, fn, g
        return c

    # Ein Teil mit 2000 kN Druck und 20 kN Zug an gehaltenen Punkten
    cons = [_con(fn=2.0e6)] + [_con(kn=1.0e6, g=0.02, gehalten=True)]
    alt_tb = slv._teile_bedingungen
    slv._teile_bedingungen = lambda model, cs: [("V30", {1}, cons)]
    try:
        zug = slv._gehaltene_unter_zug(None, _CS())
        check("20 kN Zug gegen 2000 kN Druck desselben Teils: kein Abheben", not zug,
              f"{[(n, round(k / 1e3, 1)) for n, _kn, _g, k, _c in zug]} kN")
        # Dasselbe Teil ohne Druck: der Zug hängt an nichts mehr
        cons2 = [_con(kn=1.0e6, g=0.02, gehalten=True)]
        slv._teile_bedingungen = lambda model, cs: [("V30", {1}, cons2)]
        zug2 = slv._gehaltene_unter_zug(None, _CS())
        check("ohne Druck bleibt es ein Abheben (der hochgezogene Block)",
              len(zug2) == 1 and abs(zug2[0][3] - 2.0e4) < 1.0, f"{zug2[0][3] / 1e3:.1f} kN" if zug2 else "nichts")
        # Und viel Zug gegen wenig Druck ebenfalls
        cons3 = [_con(fn=1.0e5)] + [_con(kn=1.0e6, g=0.02, gehalten=True)]
        slv._teile_bedingungen = lambda model, cs: [("V30", {1}, cons3)]
        check("20 kN Zug gegen 100 kN Druck (20 %): das ist ein Abheben",
              len(slv._gehaltene_unter_zug(None, _CS())) == 1)
        check("die Schwelle steht als Anteil im Modul", 0.0 < slv.ZUG_ANTEIL < 0.5, str(slv.ZUG_ANTEIL))
    finally:
        slv._teile_bedingungen = alt_tb


def _stift_bedingungen(n_um=8, r=0.05, h=0.08, kn=1e9, kt=1e9):
    """Bedingungen eines Stiftes in einer Bohrung: n_um Knoten je Ring, zwei
    Ringe im Abstand h, Normale radial nach aussen (der Stift schliesst den
    Spalt, wenn er nach aussen geht: cn = -radial). Tangenten sind Umfangs-
    und Achsrichtung. Rueckgabe (Bedingungen, Knotenlage)."""
    from statik3d.contact import Constraint
    cons, lage = [], {}
    for ring, z in enumerate((0.0, h)):
        for k in range(n_um):
            a = 2.0 * np.pi * k / n_um
            radial = np.array([np.cos(a), np.sin(a), 0.0])
            umfang = np.array([-np.sin(a), np.cos(a), 0.0])
            achse = np.array([0.0, 0.0, 1.0])
            knoten = ring * n_um + k
            lage[knoten] = np.array([r * np.cos(a), r * np.sin(a), z])
            dofs = np.array([knoten * 6, knoten * 6 + 1, knoten * 6 + 2])
            cons.append(Constraint(
                kind="surface", dofs=dofs, cn=-radial,
                ct=np.vstack([umfang, achse]), g0=1e-4, kn=kn, kt=kt, mu=0.0,
                node=knoten, normal=radial, label="Stift:Bohrung", haften=True))
    return cons, lage


def _starrmoden(lage, ndof_ges):
    """Feld (ndof_ges, 6): die sechs Starrkoerperbewegungen der Knoten in lage,
    um deren Schwerpunkt, Drehungen mit der groessten Ausladung skaliert."""
    o = np.mean(list(lage.values()), axis=0)
    L = max(float(np.linalg.norm(x - o)) for x in lage.values()) or 1.0
    P = np.zeros((ndof_ges, 6))
    for knoten, x in lage.items():
        r = x - o
        for k in range(3):
            e = np.zeros(3)
            e[k] = 1.0
            P[knoten * 6 + k, k] = 1.0
            P[knoten * 6:knoten * 6 + 3, 3 + k] = np.cross(e, r) / L
    return P


def _kc_auf_moden(cons, lage, schub_halt):
    """Kleinster Eigenwert von P^T Kc P: wie fest die Kontaktsteifigkeit die
    sechs Starrkoerperbewegungen des Stiftes haelt, wenn alle Bedingungen
    offen sind."""
    from statik3d.contact import ContactSystem
    cs = object.__new__(ContactSystem)
    cs.cons, cs.stabilising, cs.phase = cons, False, 1
    for c in cons:
        c.active = False
        c.schub_halt = schub_halt
    ndof = (max(int(c.node) for c in cons) + 1) * 6
    Kc, _Fc = cs.matrices(ndof)
    P = _starrmoden(lage, ndof)
    return float(np.linalg.eigvalsh(P.T @ (Kc @ P)).min())


def test_schub_haelt_den_stift():
    """Ein Stift, dessen Normalbedingungen alle offen stehen, wird von seiner
    Schubbindung gehalten - ohne sie ist die Kontaktsteifigkeit auf allen sechs
    Starrkoerperbewegungen null. Am Drehlager gemessen (19.09.2026): normal
    allein 2,2e-13 bis 3,6e-13, mit dem Schub aller Bedingungen 0,54 bis 0,71."""
    cons, lage = _stift_bedingungen()
    ohne = _kc_auf_moden(cons, lage, schub_halt=False)
    mit = _kc_auf_moden(cons, lage, schub_halt=True)
    check("offene Bedingungen ohne Schubhalt halten den Stift nicht",
          abs(ohne) < 1e-6, f"kleinster Eigenwert {ohne:.3e}")
    check("mit Schubhalt halten sie ihn in allen sechs Starrkoerperbewegungen",
          mit > 1e-3 * 1e9, f"kleinster Eigenwert {mit:.3e}")


class _FalscheBedingungsliste:
    """Nur so viel ContactSystem, wie _freie_teile_halten anfasst."""

    def __init__(self, cons):
        self.cons = cons


def _blech_bedingungen(n=16, a=0.10, kn=1e9, kt=1e9):
    """Bedingungen einer **ebenen** Fuge mit Reibung: Normale ueberall +z,
    Tangenten x und y. Gegenstueck zum Stift - hier haelt der Schub quer zur
    Ebene nichts."""
    from statik3d.contact import Constraint
    cons, lage = [], {}
    seite = int(np.sqrt(n))
    for k in range(seite * seite):
        x, y = a * (k % seite), a * (k // seite)
        lage[k] = np.array([x, y, 0.0])
        dofs = np.array([k * 6, k * 6 + 1, k * 6 + 2])
        cons.append(Constraint(
            kind="surface", dofs=dofs, cn=np.array([0.0, 0.0, 1.0]),
            ct=np.vstack([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]),
            g0=1e-4, kn=kn, kt=kt, mu=0.3, node=k,
            normal=np.array([0.0, 0.0, 1.0]), label="Blech:Fuge"))
    return cons, lage


def _modell_der_lage(lage):
    """Ein Objekt, das _schub_traegt genuegt: die Knotenkoordinaten."""
    X = [[0.0, 0.0, 0.0] for _ in range(max(lage) + 1)]
    for k, x in lage.items():
        X[k] = [float(v) for v in x]
    return type("Modell", (), {"nodes": X})()


def test_schub_traegt_misst_die_fuge():
    """Ob der Schub ein Teil haelt, entscheidet die Form der Fuge, nicht die
    Art der Bedingung: eine Bohrung fasst den Stift rundum, eine ebene Fuge
    haelt quer zu ihrer Ebene nichts - auch mit Reibung. Am Drehlager gemessen
    (19.09.2026): Stifte 0,536 bis 0,707."""
    stift, lage_s = _stift_bedingungen()
    blech, lage_b = _blech_bedingungen()
    v_stift = solver._schub_traegt(_modell_der_lage(lage_s), set(lage_s), stift)
    v_blech = solver._schub_traegt(_modell_der_lage(lage_b), set(lage_b), blech)
    check("die Bohrung haelt den Stift ueber den Schub", v_stift > solver.SCHUB_GRENZE,
          f"{v_stift:.3f} gegen Schwelle {solver.SCHUB_GRENZE:g}")
    check("die ebene Fuge haelt quer zu ihrer Ebene nichts",
          v_blech < solver.SCHUB_GRENZE, f"{v_blech:.3e}")
    check("zwischen beiden liegen Groessenordnungen",
          v_stift > 1e3 * max(v_blech, 1e-18), f"{v_stift:.3f} gegen {v_blech:.3e}")


# --------------------------------------------------------------------------
# Der Faktorisierungsschluessel: was die Matrix aendert, muss darin stehen
# --------------------------------------------------------------------------
def test_schub_halt_steht_im_schluessel():
    """Aendert der Schubhalt die Matrix, muss die Signatur sich aendern.

    ``ContactSystem.matrices`` legt fuer eine **inaktive** Bedingung mit
    ``schub_halt`` einen kt-Block in Kc. Bis zum 21.09.2026 kannte
    ``signatur()`` den Schubhalt nicht: eine Runde, in der ``schub_frei`` die
    Marke abraeumt, ohne dass active, slip oder yielding wechseln, gab
    dieselbe Signatur bei anderer Matrix - und ``StaticSystem.solve`` behielt
    die alte Faktorisierung. Geloest wurde dann mit einer Matrix, die um den
    Schubblock danebenlag.

    Geprueft wird beides: dass die Matrix sich wirklich aendert (sonst waere
    die Pruefung leer) und dass die Signatur es mitbekommt.
    """
    print("")
    print("--- Der Schubhalt im Faktorisierungsschluessel ---")
    from statik3d.contact import ContactSystem
    cons, lage = _stift_bedingungen()
    ndof = (max(lage) + 1) * 6
    cs = object.__new__(ContactSystem)     # wie in _kc_auf_moden: ohne Modell
    cs.cons, cs.stabilising, cs.phase = cons, False, 1
    for c in cs.cons:                      # alle offen, aber mit Schubhalt
        c.active = False
        c.slip = c.yielding = False
        c.schub_halt = True
    Kc_mit, _ = cs.matrices(ndof)
    sig_mit = cs.signatur()

    # schub_halt_loesen raeumt die Marke ab, sobald die Gruppe wieder traegt.
    # Hier traegt keine - genau der Fall, in dem sich active, slip und
    # yielding nicht ruehren.
    for c in cs.cons:
        c.schub_halt = False
    Kc_ohne, _ = cs.matrices(ndof)
    sig_ohne = cs.signatur()

    check("der Schubhalt aendert die Kontaktmatrix wirklich",
          Kc_mit.nnz > 0 and Kc_ohne.nnz == 0,
          f"{Kc_mit.nnz} gegen {Kc_ohne.nnz} Eintraege")
    check("active, slip und yielding sind dabei unveraendert",
          all(not c.active and not c.slip and not c.yielding for c in cs.cons),
          "alle Bedingungen offen geblieben")
    check("und die Signatur bekommt es mit", sig_mit != sig_ohne,
          "verschieden" if sig_mit != sig_ohne else "GLEICH - Loch im Schluessel")


def test_zusatzmatrix_kennt_ihre_belegung():
    """Zwei Zusatzmatrizen mit gleichen Werten an anderen Stellen sind
    verschieden - und der Schluessel muss das sehen.

    ``solver.zusatz_kenn`` hashte bis zum 21.09.2026 nur Form, Nichtnullzahl
    und Werte. Bei baugleichen Staeben (``solve_with_ausfall``) liefert der
    Ausfall dieselben 144 Eintraege an anderen Indizes; die alte
    Faktorisierung waere stehengeblieben.
    """
    print("")
    print("--- Die Zusatzmatrix im Faktorisierungsschluessel ---")
    from scipy import sparse
    from statik3d import solver as _s
    A = sparse.csr_matrix(np.array([[1.0, 0.0, 0.0],
                                    [0.0, 2.0, 0.0],
                                    [0.0, 0.0, 0.0]]))
    B = sparse.csr_matrix(np.array([[0.0, 1.0, 0.0],
                                    [2.0, 0.0, 0.0],
                                    [0.0, 0.0, 0.0]]))
    check("die Probe ist scharf: gleiche Form, Zahl und Werte",
          A.shape == B.shape and A.nnz == B.nnz
          and np.array_equal(np.sort(A.data), np.sort(B.data)),
          f"{A.nnz} Eintraege, Werte {sorted(A.data)}")
    check("aber andere Belegung", not np.array_equal(A.toarray(), B.toarray()))
    check("die Kennung unterscheidet sie", _s.zusatz_kenn(A) != _s.zusatz_kenn(B),
          "verschieden" if _s.zusatz_kenn(A) != _s.zusatz_kenn(B)
          else "GLEICH - Loch im Schluessel")
    check("dieselbe Matrix gibt dieselbe Kennung",
          _s.zusatz_kenn(A) == _s.zusatz_kenn(A.copy()))
    check("ohne Zusatzmatrix keine Kennung", _s.zusatz_kenn(None) is None)


def test_der_deckel_gilt_nicht_als_konvergenz():
    """Gibt die Nachpruefung der Reibung auf, darf niemand "konvergiert" melden.

    ``ContactSystem.update`` gibt ``False`` in **zwei** Faellen zurueck: wenn
    es fertig ist, und wenn es nach ``MAX_CYCLES`` Zustandswechseln aufgibt.
    ``solve_with_contact`` las bis zum 21.09.2026 beides als Konvergenz und
    setzte ``contact_converged`` auf wahr; die Warnung stand allein im
    ``contact_log``, das kaum jemand liest.

    Das ist keine Geschwindigkeitsfrage: **jede** Vergleichszahl, gegen die
    wir "aendert das Ergebnis nicht" pruefen, kann aus einem gedeckelten Lauf
    stammen, ohne dass es jemand sieht. Gefunden von der Loesersitzung am
    Quelltext.

    Geprueft mit einem kuenstlich niedrigen Deckel am Beispiel "Block mit
    Reibung" - der braucht mehrere Zustandswechsel, also greift er.
    """
    print("")
    print("--- Der Deckel der Reibungsnachpruefung ---")
    from statik3d import contact as _ct
    from statik3d.examples_lib import block_friction_example

    alt_max = _ct.MAX_CYCLES
    m = block_friction_example()
    r_frei = solver.solve_static(m)
    check("ohne Deckel konvergiert das Beispiel",
          bool(r_frei.info.get("contact_converged")),
          f"{r_frei.info.get('contact_iterations')} Schritte")

    _ct.MAX_CYCLES = 1
    try:
        r = solver.solve_static(block_friction_example())
    finally:
        _ct.MAX_CYCLES = alt_max
    log = " | ".join(r.info.get("contact_log") or [])
    gedeckelt = "abgebrochen" in log
    check("mit Deckel 1 bricht die Nachpruefung wirklich ab", gedeckelt,
          "Protokoll nennt den Abbruch" if gedeckelt else f"Protokoll: {log[:90]}")
    if gedeckelt:
        check("und dann meldet contact_converged NICHT konvergiert",
              r.info.get("contact_converged") is False,
              f"contact_converged = {r.info.get('contact_converged')}"
              + ("" if r.info.get("contact_converged") is False
                 else "  <- der alte Stand meldete wahr"))
        check("die Meldung nennt den Grund, nicht die Schrittzahl",
              any("Nachprüfung der Reibung" in t for t in (r.info.get("contact_log") or [])),
              "der Text unterscheidet Deckel und Schrittgrenze")


def test_deckel_merker_gilt_fuer_die_letzte_runde():
    """``update()`` sagt selbst, ob es **diese** Runde am Deckel beendet hat.

    Der Loeser las den Deckel an ``cs.cycles >= MAX_CYCLES`` ab. Der Zaehler
    bleibt nach dem Deckel aber stehen: laeuft die Schleife weiter (der
    Schubhalt wurde geloest) und endet eine spaetere Runde echt ohne Wechsel,
    sah das genauso aus. Jetzt setzt ``update()`` den Merker ``am_deckel``
    bei jedem Aufruf neu. Stumpf mit zwei Runden in Phase 2, Deckel 1: Runde
    1 wechselt (Deckel), Runde 2 wechselt nicht (fertig)."""
    print("")
    print("--- Der Deckelmerker gilt fuer die letzte Runde ---")
    from statik3d import contact as _ct
    cs = object.__new__(_ct.ContactSystem)
    cs.phase, cs.cycles, cs.settle, cs.log = 2, 0, 0, []
    cs.dF_slip, cs.f_ref = 0.0, 1.0
    folge = iter([True, False])
    cs._update_states = lambda u: next(folge)
    alt = _ct.MAX_CYCLES
    _ct.MAX_CYCLES = 1
    try:
        r1, d1 = cs.update(None), getattr(cs, "am_deckel", None)
        r2, d2 = cs.update(None), getattr(cs, "am_deckel", None)
    finally:
        _ct.MAX_CYCLES = alt
    check("Runde 1 endet am Deckel und sagt es", r1 is False and d1 is True,
          f"update {r1}, am_deckel {d1}")
    check("Runde 2 endet ohne Wechsel und ist nicht am Deckel", r2 is False and d2 is False,
          f"update {r2}, am_deckel {d2}")
    check("obwohl der Zaehler noch auf dem Deckel steht (die alte Probe hiesse: Deckel)",
          cs.cycles >= 1, f"cycles {cs.cycles}")


def test_deckel_am_tatsaechlichen_austritt():
    """Der Randfall im Loeser: gibt ``update()`` am Deckel auf, loest aber
    ``schub_halt_loesen()`` in derselben Runde etwas, laeuft die Schleife
    weiter. Endet sie spaeter echt ohne Wechsel, meldete der Loeser trotzdem
    den Deckel, weil ``cycles >= MAX_CYCLES`` stehen blieb (gefunden von der
    Loesersitzung am Quelltext, 22.09.2026).

    Nachgestellt am Block mit Reibung mit Deckel 1: ``schub_halt_loesen``
    meldet in jeder Runde, die am Deckel endet, einen geloesten Schubhalt.
    Die Schleife laeuft damit genau den Weg des Laufs ohne Deckel - der Deckel
    aendert nur den Rueckgabewert, die Zustaende setzt ``_update_states``
    ohnehin - und endet echt ohne Wechsel. Erwartet: konvergiert, dasselbe u
    wie ohne Deckel, und das Protokoll erzaehlt, warum es nach dem Deckel
    weiterging."""
    print("")
    print("--- Deckel, danach doch noch konvergiert ---")
    from statik3d import contact as _ct
    from statik3d.contact import ContactSystem
    from statik3d.examples_lib import block_friction_example

    r_frei = solver.solve_static(block_friction_example())

    alt = (_ct.MAX_CYCLES, ContactSystem._update_states, ContactSystem.update,
           ContactSystem.schub_halt_loesen)
    zaehler = {"deckel": 0}

    def zustaende(self, u):
        self._t_gewechselt = alt[1](self, u)
        return self._t_gewechselt

    def update(self, u):
        weiter = alt[2](self, u)
        # In Phase 2 gibt update() mit Wechsel nur am Deckel False zurueck
        self._t_deckel = (not weiter and self.phase == 2
                          and bool(getattr(self, "_t_gewechselt", False)))
        return weiter

    def schub_halt_loesen(self):
        n = alt[3](self)
        if getattr(self, "_t_deckel", False):
            zaehler["deckel"] += 1
            self._t_deckel = False
            return max(n, 1)
        return n

    _ct.MAX_CYCLES = 1
    ContactSystem._update_states = zustaende
    ContactSystem.update = update
    ContactSystem.schub_halt_loesen = schub_halt_loesen
    try:
        r = solver.solve_static(block_friction_example())
    finally:
        (_ct.MAX_CYCLES, ContactSystem._update_states, ContactSystem.update,
         ContactSystem.schub_halt_loesen) = alt
    check("der Deckel greift wirklich, und es geht danach weiter",
          zaehler["deckel"] >= 1, f"{zaehler['deckel']} Runden am Deckel")
    check("der Lauf endet echt ohne Wechsel und gilt als konvergiert",
          r.info.get("contact_converged") is True,
          f"contact_converged = {r.info.get('contact_converged')}")
    check("dieselben Schritte wie ohne Deckel",
          r.info.get("contact_iterations") == r_frei.info.get("contact_iterations"),
          f"{r.info.get('contact_iterations')} gegen {r_frei.info.get('contact_iterations')}")
    du = float(np.abs(r.u - r_frei.u).max())
    check("und dasselbe Ergebnis (max |du| = 0)", du == 0.0, f"max |du| = {du:.3e} m")
    log = r.info.get("contact_log") or []
    check("keine Deckelmeldung des Loesers ('nicht auskonvergiert')",
          not any("nicht auskonvergiert" in z for z in log), "")
    check("das Protokoll sagt, warum es nach dem Deckel weiterging",
          any("Schubhalt" in z and "weiter" in z for z in log),
          next((z for z in log if "Schubhalt" in z), "keine Zeile")[:110])


def _mit_einem_teil(name, fn):
    """fn() ausfuehren, waehrend _teile_bedingungen genau ein Teil mit den
    Bedingungen des uebergebenen Systems meldet. So prueft der Test die Auswahl
    des Halts, ohne ein Modell zu bauen - die Zuordnung Bedingung zu Teil hat
    ihren eigenen Test (test_teile_bedingungen)."""
    alt = solver._teile_bedingungen
    solver._teile_bedingungen = lambda model, cs: [
        (name, {int(c.node) for c in cs.cons}, list(cs.cons))]
    try:
        return fn()
    finally:
        solver._teile_bedingungen = alt


def test_halt_waehlt_den_schub():
    """Ein Teil mit Haftbindungen wird tangential gehalten - alle bindenden
    Bedingungen, nicht drei: am Drehlager halten drei mit 2e-18 gar nicht
    (19.09.2026). Ein Teil ohne Haften oder Reibung bekommt wie bisher den
    Normalhalt."""
    cons, _lage = _stift_bedingungen()
    for c in cons:
        c.active, c.schub_halt = False, False
    cs = _FalscheBedingungsliste(cons)
    log = []
    m = _modell_der_lage(_lage)
    gehalten = _mit_einem_teil("Stift", lambda: solver._freie_teile_halten(m, cs, log))
    check("der Halt greift", gehalten, str(log[:1])[:120])
    check("alle bindenden Bedingungen tragen den Schub, nicht drei",
          sum(1 for c in cons if c.schub_halt) == len(cons),
          f"{sum(1 for c in cons if c.schub_halt)} von {len(cons)}")
    check("keine Bedingung wurde dafuer geschlossen (kein Zug erfunden)",
          not any(c.active for c in cons),
          f"{sum(1 for c in cons if c.active)} geschlossen")
    check("das Protokoll nennt den Schubhalt",
          any("Schub" in z for z in log), str(log[:1])[:140])

    ohne, lage_o = _blech_bedingungen()
    for c in ohne:
        c.haften, c.mu, c.schub_halt, c.active, c.g = False, 0.0, False, False, 1e-4
    log2 = []
    cs2 = _FalscheBedingungsliste(ohne)
    m2 = _modell_der_lage(lage_o)
    _mit_einem_teil("Blech", lambda: solver._freie_teile_halten(m2, cs2, log2))
    check("ohne bindende Bedingungen bleibt es beim Normalhalt",
          sum(1 for c in ohne if c.active) == solver.HALT_MINDESTENS
          and not any(c.schub_halt for c in ohne),
          f"{sum(1 for c in ohne if c.active)} geschlossen")


def test_schub_halt_faellt_weg():
    """Der Schubhalt ist fuer den Schritt, nicht fuer das Ergebnis: sobald das
    Teil wieder geschlossene Bedingungen hat, wird er geloest. Sonst traegt er
    bis zum Schluss Schub, den es nicht gibt."""
    from statik3d.contact import ContactSystem
    cons, _lage = _stift_bedingungen()
    for c in cons:
        c.active, c.schub_halt = False, True
    cs = object.__new__(ContactSystem)
    cs.cons = cons
    check("offen: der Schubhalt bleibt",
          cs.schub_halt_loesen() == 0 and all(c.schub_halt for c in cons), "")
    cons[0].active = True
    geloest = cs.schub_halt_loesen()
    check("eine geschlossene Bedingung loest den Schubhalt des Teils",
          geloest == len(cons) and not any(c.schub_halt for c in cons),
          f"{geloest} geloest")


def test_schub_am_ende_wird_gemeldet():
    """Haengt ein Teil am Schluss noch am Schubhalt und traegt dort Kraft, ist
    das Ergebnis nicht belastbar - dann sagt es der Loeser, so wie er heute
    Zug an gehaltenen Punkten sagt."""
    from statik3d.contact import ContactSystem
    cons, lage = _stift_bedingungen()
    for c in cons:
        c.active, c.schub_halt = False, True
    cs = object.__new__(ContactSystem)
    cs.cons, cs.f_ref = cons, 1.0e4
    ndof = (max(int(c.node) for c in cons) + 1) * 6
    u = np.zeros(ndof)
    check("ohne Verschiebung traegt der Schubhalt nichts", not cs.schub_unter_last(u), "")
    for knoten in lage:
        u[knoten * 6] = 1.0e-4              # der Stift wandert in x
    traegt = cs.schub_unter_last(u)
    check("wandert das Teil, traegt der Schubhalt und wird genannt",
          traegt and "Stift" in traegt[0][0], str(traegt[:1])[:140])


def main():
    for t in (test_halt, test_teile_bedingungen, test_zug_am_teil_gemessen,
              test_schub_haelt_den_stift, test_schub_traegt_misst_die_fuge,
              test_halt_waehlt_den_schub, test_schub_halt_faellt_weg,
              test_schub_am_ende_wird_gemeldet,
              test_schub_halt_steht_im_schluessel,
              test_zusatzmatrix_kennt_ihre_belegung,
              test_der_deckel_gilt_nicht_als_konvergenz,
              test_deckel_merker_gilt_fuer_die_letzte_runde,
              test_deckel_am_tatsaechlichen_austritt):
        try:
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
