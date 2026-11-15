"""
Runde k10, Gruppe D (15.11.2026): Meldung bei singulaerem Gleichungssystem.

Zwei Befunde, beide nur an der Meldung (kein Verfahrensstand):

1. „Gleichungssystem singulär (kein statisches Gleichgewicht möglich)“ nannte
   weder Knoten noch Richtung. An einer RBE3 mit einem Slave am
   abgeschalteten Arm (Situation oder Stab „aus“) hiess der Befund der
   Matrixdiagnose sogar „Element 1 (beam): Bewegung fast ohne Steifigkeit …
   1,1 der mittleren Steifigkeit“ - Element 1 war abgeschaltet und gar nicht
   im System. Jetzt sucht die Diagnose den Nullraum (Block-Inversiteration
   mit dem vorhandenen Faktor, Rayleigh-Ritz) und nennt die Knoten, je Knoten
   die freien Richtungen und woran ein Knoten ohne wirksames Element haengt.

2. „Matrixdiagnose nicht möglich: ValueError: not enough values to unpack
   (expected 4, got 3)“: singular._weichstes_element gab, wenn an den Knoten
   der Bewegung kein Element haengt, drei statt vier Werte zurueck. Das
   Modell hier (RBE3, ein Slave ohne jedes Element) bleibt singulaer, auch
   wenn Gruppe E die starre Kopplung am RBE2-Knoten behebt.

Sollwerte, je zwei Wege:
* Hand (Kinematik): Fall 1 - RBE3-Master P ohne Element (6 Unbekannte),
  Slave d ohne Steifigkeit (3 Verschiebungen; seine Drehungen haben keine
  Steifigkeit und sind gesperrt), Slave b am Kragarm gehalten; die RBE3
  liefert 6 Bedingungen: Nullraum 9 - 6 = 3, d frei in x, y, z, P folgt
  mit Verdrehung um x (d in z) und um z (d in x). M2 - Slaves Q und d der
  RBE3 am gehaltenen Master b: frei ist die gegenlaeufige Verschiebung
  w von Q und -w von d. Ihr Mittelwert ist null, und die Ausgleichsdrehung
  (r_Q - r_d) x w verschwindet nur fuer w parallel zu Q - d: Nullraum 1,
  Richtung (Q - d)/|Q - d| = (0; 0,970; -0,243).
* Zweiter Programmweg: Nullraum der dichten Matrix D^-1/2 K D^-1/2
  (numpy.linalg.eigh, Eigenwerte unter 1e-12) - Rang, Knoten und je Knoten
  der Rang der Verschiebungen.

Nachbesserung nach der Gegenpruefung (15.11.2026):

3. Bei grossem Nullraum (viele lose RBE3-Slaves, Kreisring mit 64 Slaves am
   abgeschalteten Koerper) fand der Block von sechs Vektoren ueber den Faktor
   von K + eps·I nur 3, 2 oder 0 Bewegungen und beschrieb Master und Slaves
   falsch, ohne „mindestens“. Ursache: die Diagonalen der losen Slaves sind
   1,7e-12 · max diag(K) klein, die naechsten unskalierten Eigenwerte liegen
   unter eps, die Inversiteration trennt sie nicht vom Nullraum. Jetzt an der
   skalierten Matrix, mit Festhalten und neuer Runde, bis eine Runde
   Steifigkeit zeigt; an der Grenze sagt die Meldung „mindestens“.
   Sollwert (Hand): jede lose Slave-Verschiebung ist frei, der Master folgt
   (6 RBE3-Bedingungen bestimmen ihn), Nullraum 3n; zweiter Weg dicht.
4. Die Vorpruefung gelenkketten (Normalweg, gesunde Modelle) rechnete den
   Block mit; jetzt ohne Knotenbefund.
5. Knoten heissen wie in der Oberflaeche „Knoten K3“; die Kopfzeile nennt
   die Nummern aufsteigend.

Runde k10c nach der zweiten Gegenpruefung (15.11.2026):

6. Rang und Richtungen je Knoten an einer nicht orthonormierten Basis: am
   schwimmenden Stab (nur RBE3-Slave) stimmte die Zahl 6, die Richtungen
   waren falsch, der Master fehlte. Jetzt erst in der Metrik Verschiebung m,
   Drehung mal Modellgroesse orthonormiert. Sollwert Hand und dicht
   orthonormiert (zweiter Weg _raenge_metrisch).
7. „Ohne Steifigkeit“ hing an der Strafsteifigkeit: Kreisring-RBE3 mit
   Bolzen vor einer Kette aus 100 bis 27 000 Staeben meldete 191/192 statt
   186 und nannte Master und Kette „frei“; am gesunden Ring Knoten mit
   wirksamen Staeben. Jetzt Nullraum an der Matrix mit kleiner Strafe
   (gleicher exakter Nullraum) und Pruefung jeder Bewegung ohne Straffedern
   ueber die Wurzel der Elementsteifigkeiten; was an der Rechengenauigkeit
   liegt, heisst „nicht sicher bestimmbar“. Sollwert Hand 186, zweiter Weg
   dicht mit verkleinertem Strafanteil P = K - K_e.
8. Kein „nahezu singulär … Splitterelemente“ samt Kennzahl neben „ohne
   Steifigkeit“; Fortschritt je Runde der Suche.

Aufruf:  python -m tests.test_singulaer_meldung_k10
"""
import contextlib
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:96s} {str(detail)[:400]}")
    return ok


E = 210e9
L = 3.0
I = 8e-5
F = 1e3


def _still(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


def basis(arm=True):
    """Kragarm a-b (x = 0..L, eingespannt in a) und daneben c-d (y = 2)."""
    from statik3d.model import Model, Material, Section
    m = Model("k10")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=1e-2, Iy=I, Iz=I, It=1e-5, zmax=0.1, ymax=0.1))
    m.design.imperfektionen = False
    m.netz.stabteilung = 1
    a = m.add_node(0, 0, 0)
    b = m.add_node(L, 0, 0)
    m.add_element("beam", [a, b], "ST", "Q")
    m.fix(a, "all")
    c = d = None
    if arm:
        c = m.add_node(0, 2, 0)
        d = m.add_node(L, 2, 0)
        m.add_element("beam", [c, d], "ST", "Q")
        m.fix(c, "all")
    m.add_load_case("LF1", "G")
    m.load_cases["LF1"].gravity = [0.0, 0.0, 0.0]
    return m, a, b, c, d


def _maske(m, art):
    from statik3d.model import Situation
    if art == "situation":
        m.situationen["s"] = Situation("s", "", [1])
        m.load_cases["LF1"].situation = "s"
    elif art == "aus":
        m.add_member("S2", [1], aus=True)
    elif art == "geloescht":
        m.elements.pop(1)


def fall1(maske="situation", last="P"):
    """Fall 1 / M1: RBE3-Master P (L, 1, 0) ohne Element, Slaves b und d;
    Last an P (Fall 1) oder an d (M1). Knoten: a 0, b 1, c 2, d 3, P 4."""
    m, a, b, c, d = basis()
    p = m.add_node(L, 1, 0)
    m.add_starrkoerper(p, [b, d], "RBE3", name="H")
    m.load_node(p if last == "P" else d, Fz=-F, case="LF1")
    _maske(m, maske)
    return m


def m2(maske="situation"):
    """M2: RBE3-Master b, Slaves Q (L, 0, 0,5) ohne Element und d; Last an Q.
    Knoten: a 0, b 1, c 2, d 3, Q 4."""
    m, a, b, c, d = basis()
    q = m.add_node(L, 0, 0.5)
    m.add_starrkoerper(b, [q, d], "RBE3", name="H")
    m.load_node(q, Fz=-F, case="LF1")
    _maske(m, maske)
    return m


def viele(n=10):
    """RBE3-Master P ohne Element, Slaves b und n Knoten ohne Element."""
    m, a, b, c, d = basis(arm=False)
    p = m.add_node(L, 1, 0)
    lose = [m.add_node(L, 1 + 0.1 * i, 0.2 * i) for i in range(1, n + 1)]
    m.add_starrkoerper(p, [b] + lose, "RBE3", name="V")
    m.load_node(p, Fz=-F, case="LF1")
    return m, p, lose


def _meldung(m):
    from statik3d import solver
    try:
        _still(solver.solve_static, m, case="LF1")
    except RuntimeError as ex:
        return str(ex)
    return ""


def _system(m):
    from statik3d import solver
    sit = str(m.load_cases["LF1"].situation or "")
    aktiv = m.aktive_elemente(sit) if sit else None
    return _still(solver.StaticSystem, m, 1, aktiv=aktiv)


def _dicht(m, sy):
    """Zweiter Weg: Nullraum der dichten, diagonal skalierten Matrix.
    Rueckgabe (Rang, Knoten, {Knoten: Rang der Verschiebungen}, Basis voll)."""
    Kf = sy.K.tocsc()[sy.fi][:, sy.fi].toarray()
    dg = np.sqrt(np.abs(np.diag(Kf)))
    A = Kf / dg[:, None] / dg[None, :]
    w, V = np.linalg.eigh(0.5 * (A + A.T))
    Z = (V[:, np.abs(w) <= 1e-12] / dg[:, None])
    voll = np.zeros((sy.K.shape[0], Z.shape[1]))
    voll[sy.fi] = Z
    if Z.shape[1] == 0:
        return 0, [], {}, voll
    je = _raenge_metrisch(m, voll)
    return Z.shape[1], sorted(je), {k: rt for k, (rt, _rr) in je.items()}, voll


def _raenge_metrisch(m, voll):
    """Zweiter Weg fuer Rang und Richtungen je Knoten (Runde k10c): die Basis
    erst in einer gemeinsamen Metrik orthonormieren (Verschiebung in m,
    Drehung mal Modellgroesse), dann je Knoten die Singulaerwerte der
    Verschiebungs- und der Drehanteile. Unabhaengig von der zufaelligen Basis.
    Rueckgabe {Knoten: (Verschiebungsrang, Drehrang)} fuer die beteiligten Knoten."""
    W = np.array(voll[:6 * m.nn], float).reshape(m.nn, 6, -1)
    lc = float(np.ptp(np.asarray(m.nodes, float).reshape(-1, 3), axis=0).max())
    W[:, 3:, :] *= lc
    U, s, _ = np.linalg.svd(W.reshape(6 * m.nn, -1), full_matrices=False)
    U = U[:, s > 1e-9 * s[0]].reshape(m.nn, 6, -1)
    gr = np.linalg.norm(U.reshape(m.nn, -1), axis=1)
    grenze = 1e-3 * np.abs(U).max()
    out = {}
    for k in np.flatnonzero(gr >= 1e-3 * gr.max()):
        rt = int((np.linalg.svd(U[k, :3, :], compute_uv=False) > grenze).sum())
        rr = int((np.linalg.svd(U[k, 3:, :], compute_uv=False) > grenze).sum())
        out[int(k)] = (rt, rr)
    return out


def test_matrixdiagnose_rechnet():
    """Punkt 2: die Matrixdiagnose bricht nicht mehr mit ValueError ab."""
    from statik3d import singular as sg
    m = fall1("geloescht")
    text = _meldung(m)
    check("RBE3 mit Slave ohne Element: Rechnung meldet singulär", "Gleichungssystem singulär" in text,
          text[:120])
    check("Matrixdiagnose rechnet: kein „nicht möglich“, kein ValueError",
          "Matrixdiagnose nicht möglich" not in text and "ValueError" not in text, text[-200:])
    check("und nennt eine Ursache: Knoten K3 und K4 ohne Steifigkeit beweglich",
          "Ohne Steifigkeit beweglich: Knoten K3 in allen drei Richtungen frei verschieblich" in text
          and "Knoten K4 in allen drei Richtungen frei verschieblich" in text, text[-500:])
    # direkt: das Element zu Knoten ohne Element - immer vier Werte
    voll = np.zeros(6 * m.nn)
    voll[6 * 3 + 2] = 1.0
    r = sg._weichstes_element(m, voll, [3])
    check("_weichstes_element an Knoten ohne Element: vier Werte, Element -1",
          len(r) == 4 and r[0] == -1, str(r))
    sy = _system(m)
    try:
        moden = sg.weichster_modus(sy.K, m, sy.fi, aktiv=sy.aktiv)
        check("weichster_modus direkt: ein Modus, ohne Element, Nullrang 3",
              len(moden) == 1 and moden[0].element == -1 and getattr(moden[0], "nullrang", 0) == 3,
              f"{len(moden)} Moden, Element {moden[0].element if moden else '?'}, "
              f"Nullrang {getattr(moden[0], 'nullrang', '?') if moden else '?'}")
    except Exception as ex:                      # noqa: BLE001
        check("weichster_modus direkt: ein Modus, ohne Element, Nullrang 3", False,
              f"{type(ex).__name__}: {ex}")


def test_fall1_nennt_knoten():
    """Punkt 1: Fall 1 und M1, Maske Situation und Stab „aus“."""
    for maske in ("situation", "aus"):
        for last, name in (("P", "Fall 1"), ("d", "M1")):
            text = _meldung(fall1(maske, last))
            check(f"{name}, Maske {maske}: Knoten K3 in allen drei Richtungen frei verschieblich",
                  "Knoten K3 in allen drei Richtungen frei verschieblich" in text, text[-500:])
            check(f"{name}, Maske {maske}: Knoten K4 verschieblich und um x und z drehbar",
                  "Knoten K4 in allen drei Richtungen frei verschieblich, um x und z frei drehbar" in text,
                  text[-500:])
            check(f"{name}, Maske {maske}: Rolle genannt (Slave und Master des RBE3 „H“)",
                  "Knoten K3: Slave des RBE3 „H“" in text and "Knoten K4: Master des RBE3 „H“" in text,
                  text[-400:])
            check(f"{name}, Maske {maske}: das abgeschaltete Element 1 wird nicht genannt",
                  "Element 1 (" not in text, text[-300:])


def test_m2_richtung():
    """M2: eine Richtung, die Verbindungslinie der beiden Slaves (Hand)."""
    m = m2("situation")
    text = _meldung(m)
    q = m.nodes[4]
    d = m.nodes[3]
    r = (q - d) / np.linalg.norm(q - d)
    r = -r if r[np.argmax(np.abs(r))] < 0 else r
    soll = "(" + "; ".join(f"{x:.2f}".replace(".", ",") for x in np.round(r, 2) + 0.0) + ")"
    check(f"M2: Knoten K3 und K4 in Richtung {soll} frei verschieblich (Hand: Linie Q-d)",
          f"Knoten K3 und K4 in Richtung {soll} frei verschieblich" in text, text[-500:])


def test_zweiter_weg():
    """Nullraum der Diagnose gegen den dichten Nullraum: Rang, Knoten, Rang je Knoten."""
    from statik3d import singular as sg
    for name, m, hand in (("Fall 1", fall1("situation"), 3), ("M1 Stab aus", fall1("aus", "d"), 3),
                          ("Punkt 2 ohne Element", fall1("geloescht"), 3), ("M2", m2("situation"), 1)):
        sy = _system(m)
        rang, kn, je, voll = _dicht(m, sy)
        try:
            moden = sg.weichster_modus(sy.K, m, sy.fi, aktiv=sy.aktiv)
            nr = getattr(moden[0], "nullrang", None)
            _text, kn_diag = sg.knotenbefund(m, voll, sy.aktiv)
        except Exception as ex:                  # noqa: BLE001
            check(f"{name}: Diagnose rechnet", False, f"{type(ex).__name__}: {ex}")
            continue
        check(f"{name}: Nullrang Diagnose = dicht = Hand ({hand})", nr == rang == hand,
              f"Diagnose {nr}, dicht {rang}")
        check(f"{name}: Knoten der Meldung = Knoten des dichten Nullraums", sorted(kn_diag) == sorted(kn),
              f"Diagnose {sorted(kn_diag)}, dicht {sorted(kn)}")
        txt = getattr(moden[0], "knotentext", "")
        wort = {1: "in Richtung", 2: "in der Ebene", 3: "in allen drei Richtungen"}
        check(f"{name}: Verschiebungsrang je Knoten (dicht {je}) in der Meldung",
              bool(je) and all(re.search(rf"Knoten [^;]*\bK{k}\b[^;]* {wort[rr]}", txt)
                               for k, rr in je.items() if rr), txt[:300])


def test_kuerzen():
    """Viele Knoten: „Knoten K12, K13, K17 und 40 weitere“."""
    from statik3d import singular as sg
    check("knotenliste_text: drei Nummern und „und 40 weitere“",
          sg.knotenliste_text([12, 13, 17] + list(range(100, 140))) == "Knoten K12, K13, K17 und 40 weitere",
          sg.knotenliste_text([12, 13, 17] + list(range(100, 140))))
    check("knotenliste_text: zwei Knoten „Knoten K3 und K4“ (wie die Oberfläche)",
          sg.knotenliste_text([3, 4]) == "Knoten K3 und K4", sg.knotenliste_text([3, 4]))
    m, p, lose = viele(10)
    text = _meldung(m)
    erwartet = f"Knoten K{lose[0]}, K{lose[1]}, K{lose[2]} und {len(lose) - 3} weitere in allen drei Richtungen"
    check("RBE3 mit zehn losen Slaves: gekürzt „… und 7 weitere in allen drei Richtungen“",
          erwartet in text, text[-500:])
    check("Nullraum 30 größer als der Block: vollständig gefunden („Das sind 30 unabhängige Bewegungen“), "
          "ohne „mindestens“", "Das sind 30 unabhängige Bewegungen" in text and "mindestens" not in text,
          text[-400:])


def test_bewegungsbefund_knoten():
    """Stufe 1b (freie Bewegung eines Teils) nennt die Knoten, gekuerzt."""
    from statik3d import diagnose as dg, singular as sg
    echt = sg.restfreiheiten
    m, _a, _b, _c, _d = basis(arm=False)
    s = sg.Singularitaet(art="gleitet", knoten=list(range(50)), koerper=["B"],
                         text="B kann längs x gleiten")
    sg.restfreiheiten = lambda model, guete=None, **kw: [s]
    try:
        z = dg._bewegungsbefund(m)
    finally:
        sg.restfreiheiten = echt
    check("Stufe 1b: „B kann längs x gleiten (Knoten K0, K1, K2 und 47 weitere)“",
          bool(z) and "B kann längs x gleiten (Knoten K0, K1, K2 und 47 weitere)" in z[0], str(z)[:200])


def _dichter_nullrang(sy):
    """Zweiter Weg: Zahl der Eigenwerte der dichten, skalierten Matrix unter 1e-12."""
    Kf = sy.K.tocsc()[sy.fi][:, sy.fi].toarray()
    dg = np.sqrt(np.abs(np.diag(Kf)))
    dg[dg == 0] = 1.0
    w = np.linalg.eigvalsh(0.5 * (Kf + Kf.T) / dg[:, None] / dg[None, :])
    return int((np.abs(w) <= 1e-12).sum())


def kreisring(n=64, r=0.1):
    """Kreisring-RBE3 wie an der Einleitung: Kragarm a-b, n Ringknoten im
    Kreis (Radius r, Ebene y-z) um b, je ueber eine Speiche an b (der
    „Koerper“); die Speichen sind in der Situation „s“ abgeschaltet. Master P
    (L + 0,5; 0; 0) haengt ueber einen Bolzenstab an b, Last an P. Knoten:
    a 0, b 1, Ring 2 .. n + 1, P n + 2.

    Hand: P und b sind ueber die Staebe gehalten; die 6 RBE3-Bedingungen
    binden die 3n Ringverschiebungen an P. Nullraum 3n - 6, jeder Ringknoten
    in allen drei Richtungen frei, P und b nicht."""
    from statik3d.model import Situation
    m, a, b, c, d = basis(arm=False)
    ring = []
    for i in range(n):
        t = 2 * np.pi * i / n
        k = m.add_node(L, r * np.cos(t), r * np.sin(t))
        m.add_element("beam", [b, k], "ST", "Q")
        ring.append(k)
    p = m.add_node(L + 0.5, 0, 0)
    m.add_element("beam", [b, p], "ST", "Q")
    m.add_starrkoerper(p, ring, "RBE3", name="Ring")
    m.load_node(p, Fz=-F, case="LF1")
    m.situationen["s"] = Situation("s", "", list(range(1, n + 1)))
    m.load_cases["LF1"].situation = "s"
    return m, p, ring


def test_grosser_nullraum():
    """Befund der Gegenpruefung (mittel): Nullraum groesser als der Block.
    Hand: jede lose Slave-Verschiebung ist frei, der Master folgt; Nullraum 3n.
    Der Master verschiebt sich in allen Richtungen und dreht um alle Achsen
    (Slaves nicht auf einer Linie). Zweiter Weg: dichter Nullraum."""
    from statik3d import singular as sg
    for n in (20, 30, 60):
        m, p, lose = viele(n)
        text = _meldung(m)
        sy = _system(m)
        dicht = _dichter_nullrang(sy)
        try:
            mo = sg.weichster_modus(sy.K, m, sy.fi, aktiv=sy.aktiv)
            nr = getattr(mo[0], "nullrang", None)
        except Exception as ex:                  # noqa: BLE001
            nr = f"{type(ex).__name__}: {ex}"
        check(f"{n} lose Slaves: Nullrang Diagnose = dicht = Hand ({3 * n})", nr == dicht == 3 * n,
              f"Diagnose {nr}, dicht {dicht}")
        check(f"{n} lose Slaves: „Das sind {3 * n} unabhängige Bewegungen“, kein „nahezu singulär“",
              f"Das sind {3 * n} unabhängige Bewegungen" in text and "nahezu singulär" not in text,
              text[-300:])
        check(f"{n} lose Slaves: Slaves in allen drei Richtungen frei verschieblich",
              f"Knoten K{lose[0]}, K{lose[1]}, K{lose[2]} und {n - 3} weitere in allen drei Richtungen "
              "frei verschieblich" in text, text[-700:])
        check(f"{n} lose Slaves: Master K{p} verschieblich und um alle Achsen drehbar",
              f"Knoten K{p} in allen drei Richtungen frei verschieblich, um alle Achsen frei drehbar" in text,
              text[-700:])
    # Kopfzeile aufsteigend (Befund niedrig): „Knoten K2, K3, K4 und 28 weitere“
    m, p, lose = viele(30)
    text = _meldung(m)
    check("Kopfzeile aufsteigend: „Knoten K2, K3, K4 und 28 weitere: Bewegung …“",
          "Knoten K2, K3, K4 und 28 weitere: Bewegung" in text, text.splitlines()[-1][:120])


def test_kreisring():
    """Kreisring-RBE3 mit 64 Slaves am abgeschalteten Koerper (Situation)."""
    from statik3d import singular as sg
    m, p, ring = kreisring()
    text = _meldung(m)
    sy = _system(m)
    dicht = _dichter_nullrang(sy)
    try:
        mo = sg.weichster_modus(sy.K, m, sy.fi, aktiv=sy.aktiv)
        nr = getattr(mo[0], "nullrang", None)
    except Exception as ex:                      # noqa: BLE001
        nr = f"{type(ex).__name__}: {ex}"
    check("Kreisring 64 Slaves: Nullrang Diagnose = dicht = Hand (186)", nr == dicht == 186,
          f"Diagnose {nr}, dicht {dicht}")
    check("Kreisring: Rechnung meldet singulär", "Gleichungssystem singulär" in text, text[:120])
    check("Kreisring: Ringknoten in allen drei Richtungen frei verschieblich, 186 Bewegungen",
          f"Ohne Steifigkeit beweglich: Knoten K{ring[0]}, K{ring[1]}, K{ring[2]} und 61 weitere in allen "
          "drei Richtungen frei verschieblich. Sie hängen" in text
          and "Das sind 186 unabhängige Bewegungen" in text, text[-700:])
    check(f"Kreisring: Master K{p} und Kragarmende K1 heißen nicht „frei“ (gehalten über die Stäbe)",
          f"Knoten K{p} " not in text and "Knoten K1 " not in text and "Knoten K1," not in text,
          text[-700:])
    check("Kreisring: die abgeschalteten Speichen werden nicht genannt", not re.search(r"Element \d", text),
          text[-300:])


def schwimmend():
    """Befund 1 der zweiten Gegenpruefung: Kragarm a-b (eingespannt) und ein
    schwimmender Stab e-f (L, 2..3, 0) ohne Lager; RBE3-Master P (L, 1, 0) mit
    den Slaves b, e, f, Last an P. Knoten: a 0, b 1, e 2, f 3, P 4.

    Hand: der Stab e-f hat seine 6 Starrkoerperbewegungen, P folgt ihnen
    (b steht). e und f verschieben sich in allen drei Richtungen und drehen um
    alle Achsen; P verschiebt sich in allen drei Richtungen und dreht um x und
    z - die Slaves liegen auf einer Geraden in y, ihre Verschiebungen
    bestimmen keine Drehung um y."""
    m, a, b, c, d = basis(arm=False)
    e = m.add_node(L, 2, 0)
    f = m.add_node(L, 3, 0)
    m.add_element("beam", [e, f], "ST", "Q")
    p = m.add_node(L, 1, 0)
    m.add_starrkoerper(p, [b, e, f], "RBE3", name="S")
    m.load_node(p, Fz=-F, case="LF1")
    return m


def test_schwimmender_stab():
    """Befund 1 (mittel): Rang und Richtungen je Knoten an einer nicht
    orthonormierten Basis - am schwimmenden Stab waren die Richtungen falsch,
    der Master K4 fehlte. Befund 3 (niedrig): zugleich „Ohne Steifigkeit
    beweglich … 6 Bewegungen“ und „nahezu singulär … Splitterelemente“ mit
    der Kennzahl „1/2 800 000 000 000 000 000 000 der mittleren Steifigkeit“."""
    from statik3d import singular as sg
    m = schwimmend()
    text = _meldung(m)
    check("schwimmender Stab: K2 und K3 in allen drei Richtungen verschieblich, um alle Achsen drehbar",
          "Knoten K2 und K3 in allen drei Richtungen frei verschieblich, um alle Achsen frei drehbar" in text,
          text[-700:])
    check("schwimmender Stab: Master K4 genannt, verschieblich und um x und z drehbar",
          "Knoten K4 in allen drei Richtungen frei verschieblich, um x und z frei drehbar" in text, text[-700:])
    check("schwimmender Stab: „Das sind 6 unabhängige Bewegungen“", "Das sind 6 unabhängige Bewegungen" in text,
          text[-400:])
    check("schwimmender Stab: kein „nahezu singulär … Splitterelemente“ neben „ohne Steifigkeit“",
          "nahezu singulär" not in text and "Splitterelemente" not in text, text[-400:])
    check("schwimmender Stab: keine Kennzahl „… der mittleren Steifigkeit dieses Elements“",
          "der mittleren Steifigkeit" not in text, text[-300:])
    # zweiter Weg: dichter Nullraum, metrisch orthonormiert, gegen die Hand
    sy = _system(m)
    rang, _kn, _je, voll = _dicht(m, sy)
    je = _raenge_metrisch(m, voll)
    hand = {2: (3, 3), 3: (3, 3), 4: (3, 2)}
    check("schwimmender Stab, zweiter Weg: dicht 6 Bewegungen, je Knoten (Verschiebung, Drehung) = Hand",
          rang == 6 and je == hand, f"dicht {rang}, {je}, Hand {hand}")
    try:
        mo = sg.weichster_modus(sy.K, m, sy.fi, aktiv=sy.aktiv)
        ok = getattr(mo[0], "nullrang", None) == 6
    except Exception as ex:                      # noqa: BLE001
        ok, mo = False, [f"{type(ex).__name__}: {ex}"]
    check("schwimmender Stab: Nullrang der Diagnose = 6", ok, str(getattr(mo[0], "nullrang", mo[0])))
    # dieselbe Funktion an der dichten Basis: derselbe Text (unabhaengig von der Basis)
    t_dicht = sg.knotenbefund(m, voll, sy.aktiv)[0]
    t_diag = getattr(mo[0], "knotentext", "") if ok else ""
    check("knotenbefund an dichter und an Programmbasis: gleiche Aussage",
          bool(t_dicht) and t_dicht in t_diag, f"dicht: {t_dicht[:200]} | Programm: {t_diag[:200]}")


def kreisring_kette(n, ring=64, r=0.1, speichen_aus=True):
    """Befund 2 der zweiten Gegenpruefung: eingespannte Kette aus n Staeben
    (x = 0..L), am Ende b ein Kreisring-RBE3 mit 64 Slaves (Speichen an b, in
    der Situation abgeschaltet), Master P (L + 0,5; 0; 0) ueber einen
    Bolzenstab an b, Last an P. Knoten: Kette 0..n, Ring n + 1 .. n + 64, P n + 65.
    Hand: P und die Kette sind ueber Staebe gehalten; 3 · 64 - 6 = 186
    Bewegungen, nur die Ringknoten."""
    from statik3d.model import Model, Material, Section, Situation
    m = Model("ring")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=1e-2, Iy=I, Iz=I, It=1e-5, zmax=0.1, ymax=0.1))
    m.design.imperfektionen = False
    m.netz.stabteilung = 1
    kn = [m.add_node(i * L / n, 0, 0) for i in range(n + 1)]
    for i in range(n):
        m.add_element("beam", [kn[i], kn[i + 1]], "ST", "Q")
    m.fix(kn[0], "all")
    b = kn[-1]
    rk, sp = [], []
    for i in range(ring):
        t = 2 * np.pi * i / ring
        k = m.add_node(L, r * np.cos(t), r * np.sin(t))
        sp.append(len(m.elements))
        m.add_element("beam", [b, k], "ST", "Q")
        rk.append(k)
    p = m.add_node(L + 0.5, 0, 0)
    m.add_element("beam", [b, p], "ST", "Q")
    m.add_starrkoerper(p, rk, "RBE3", name="Ring")
    m.add_load_case("LF1", "G")
    m.load_cases["LF1"].gravity = [0.0, 0.0, 0.0]
    m.load_node(p, Fz=-F, case="LF1")
    if speichen_aus:
        m.situationen["s"] = Situation("s", "", sp)
        m.load_cases["LF1"].situation = "s"
    return m, p, rk


def _dichter_nullrang_ohne_strafe(m, sy):
    """Zweiter Weg zu Befund 2, unabhaengig von der Strafsteifigkeit: die
    Straf- und Kopplungsanteile P = K - K_e (K_e nur Elemente) auf die groesste
    Elementdiagonale verkleinert (gleicher exakter Nullraum), dicht skaliert,
    Eigenwerte unter 1e-12 (numpy.linalg.eigvalsh)."""
    from statik3d import assemble as asm
    Ke = asm._assemble_triplets(m, asm._matrix_chunk, 1, asm.aktive_indizes(m, sy.aktiv)).tocsc()
    K = sy.K.tocsc()
    Pm = (K - Ke)[sy.fi][:, sy.fi].toarray()
    Kf = Ke[sy.fi][:, sy.fi].toarray()
    A = Kf + (np.abs(np.diag(Kf)).max() / np.abs(np.diag(Pm)).max()) * Pm
    dg = np.sqrt(np.abs(np.diag(A)))
    dg[dg == 0] = 1.0
    w = np.linalg.eigvalsh(0.5 * (A + A.T) / dg[:, None] / dg[None, :])
    return int((np.abs(w) <= 1e-12).sum())


def test_kreisring_kette():
    """Befund 2 (mittel): das Kriterium „bezogene Energie unter einem
    Billionstel der Diagonale“ hielt Knoten mit grosser RBE3-Strafsteifigkeit
    fuer frei - Kreisring mit Kette aus 100 bis 27 000 Staeben: 191 und 192
    statt 186 Bewegungen, Master und eingespannte Kettenknoten „frei“."""
    for n in (100, 500, 2000):
        m, p, rk = kreisring_kette(n)
        text = _meldung(m)
        check(f"Kreisring mit Kette n = {n}: nur die Ringknoten frei, „Das sind 186 unabhängige Bewegungen“",
              f"Ohne Steifigkeit beweglich: Knoten K{rk[0]}, K{rk[1]}, K{rk[2]} und 61 weitere in allen drei "
              "Richtungen frei verschieblich. Sie hängen" in text and "Das sind 186 unabhängige Bewegungen" in text,
              text[-700:])
        genannt = {int(x) for x in re.findall(r"\bK(\d+)\b", text)}
        fremd = sorted(k for k in genannt if k not in set(rk))
        check(f"Kreisring mit Kette n = {n}: Master K{p} und Kettenknoten werden nicht genannt",
              not fremd, f"genannt außer Ring: {fremd[:10]}")
        if n <= 500:
            sy = _system(m)
            dicht = _dichter_nullrang_ohne_strafe(m, sy)
            check(f"Kreisring mit Kette n = {n}, zweiter Weg: dicht ohne Straf-Skalierung 186 = Hand",
                  dicht == 186, f"dicht {dicht}")


def test_gesunder_kreisring():
    """Befund 2, zweiter Teil: ein gesunder Kreisring (Speichen wirken, Master
    am Bolzenstab) bricht vorbestehend „numerisch singulär“ ab (Strafsteifigkeit
    rund 50 Millionen Mal die groesste Elementdiagonale, Gruppe G). Die
    Meldung nannte dabei Knoten mit wirksamen Staeben „frei verschieblich“.
    Jetzt: kein Knoten „frei“, die Ursache „nicht sicher bestimmbar“."""
    m, p, rk = kreisring_kette(1, speichen_aus=False)
    text = _meldung(m)
    if not text:
        check("gesunder Kreisring rechnet (Strafsteifigkeit behoben): keine Meldung zu prüfen", True)
        return
    check("gesunder Kreisring: kein Knoten „ohne Steifigkeit beweglich“ oder „frei verschieblich“",
          "Ohne Steifigkeit beweglich" not in text and "frei verschieblich" not in text, text[-600:])
    check("gesunder Kreisring: „die Ursache ist nicht sicher bestimmbar“, kein „meist Splitterelemente“",
          "nicht sicher bestimmbar" in text and "Splitterelemente" not in text, text[-600:])


def test_fortschritt():
    """Befund 3 (niedrig): bei grossem Nullraum meldet die Suche je Runde
    ihren Fortschritt (an 54 198 FHG dauerte sie 56 s ohne ein Wort)."""
    from statik3d import singular as sg
    m, p, lose = viele(60)
    sy = _system(m)
    zeilen = []
    sg.weichster_modus(sy.K, m, sy.fi, aktiv=sy.aktiv, melden=zeilen.append)
    runden = [z for z in zeilen if "Runde" in z]
    check("Nullraum 180: Fortschritt je Runde („Runde …, bisher … gefunden“), mindestens drei Zeilen",
          len(runden) >= 3 and "bisher" in runden[-1], " | ".join(runden[-3:])[:300])


def test_grenze_sagt_mindestens():
    """An der Grenze der Suche (hier kuenstlich 12 Vektoren) sagt die Meldung
    „mindestens“ und dass weitere Knoten moeglich sind; ueber der Groesse fuer
    die skalierte Suche (hier kuenstlich 10 FHG) sagt sie, dass es offen ist."""
    from statik3d import singular as sg
    alt = getattr(sg, "NULLRAUM_HOECHSTENS", None)
    sg.NULLRAUM_HOECHSTENS = 12
    try:
        m, p, lose = viele(20)
        text = _meldung(m)
    finally:
        if alt is None:
            del sg.NULLRAUM_HOECHSTENS
        else:
            sg.NULLRAUM_HOECHSTENS = alt
    check("Grenze 12 Vektoren bei Nullraum 60: „mindestens 12 unabhängige Bewegungen … weitere Knoten“",
          "mindestens 12 unabhängige Bewegungen" in text and "weitere Knoten" in text, text[-400:])
    check("an der Grenze: keine Behauptung „Das sind … Bewegungen“", "Das sind" not in text, text[-300:])
    # Ueber der Groesse fuer die zweite Faktorisierung (am Drehlager) bleibt
    # die Frage offen - und die Meldung sagt das, statt ungeprueft zu nennen.
    alt_g = getattr(sg, "NULLRAUM_SKALIERT_FHG_MAX", None)
    sg.NULLRAUM_SKALIERT_FHG_MAX = 10
    try:
        m, p, lose = viele(20)
        text = _meldung(m)
    finally:
        if alt_g is None:
            del sg.NULLRAUM_SKALIERT_FHG_MAX
        else:
            sg.NULLRAUM_SKALIERT_FHG_MAX = alt_g
    check("über der Größengrenze: „nicht geklärt; die genaue Suche läuft nur bis 10 Freiheitsgrade“",
          "Freiheitsgraden nicht geklärt; die genaue Suche läuft nur bis 10 Freiheitsgrade" in text, text[-400:])
    check("über der Größengrenze: keine Knoten als „frei“ und keine Zahl der Bewegungen",
          "Ohne Steifigkeit beweglich" not in text and "Das sind" not in text, text[-300:])


def test_vorpruefung_ohne_block():
    """Befund der Gegenpruefung (niedrig): die Vorpruefung gelenkketten laeuft
    im Normalweg an gesunden Modellen und darf weder Nullraumsuche noch
    Knotenbefund rechnen (Durchlauftraeger mit 9000 Staeben, 54 006 FHG)."""
    from statik3d import singular as sg
    from statik3d.model import Model, Material, Section
    n = 9000
    m = Model("g")
    m.add_material(Material("ST", E=210e9, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=1e-2, Iy=8e-5, Iz=8e-5, It=1e-5, zmax=0.1, ymax=0.1))
    m.netz.stabteilung = 1
    kn = [m.add_node(i, 0, 0) for i in range(n + 1)]
    for i in range(n):
        m.add_element("beam", [kn[i], kn[i + 1]], "ST", "Q")
    m.elements[n // 2].hinges = [4, 5]
    m.fix(kn[0], "all")
    m.fix(kn[-1], [0, 1, 2])
    gezaehlt = {"nullbewegungen": 0, "knotenbefund": 0}
    echt = {k: getattr(sg, k) for k in gezaehlt}

    def zaehler(name):
        def f(*a, **kw):
            gezaehlt[name] += 1
            return echt[name](*a, **kw)
        return f

    for k in gezaehlt:
        setattr(sg, k, zaehler(k))
    try:
        befund = sg.gelenkketten(m)
    finally:
        for k, f in echt.items():
            setattr(sg, k, f)
    check("gelenkketten am gesunden Träger (54 006 FHG): keine Nullraumsuche, kein Knotenbefund",
          gezaehlt["nullbewegungen"] == 0 and gezaehlt["knotenbefund"] == 0, str(gezaehlt))
    check("gelenkketten am gesunden Träger: keine Kette", befund == [], str(len(befund)))


def test_schutz():
    """Schutz: das gesunde Modell rechnet wie bisher; der Befund am Wuerfelpaar
    (Element und Bauteil) behaelt seinen Wortlaut; freie Knotenlast wie bisher."""
    from statik3d import solver
    m = fall1("keine")
    try:
        r = _still(solver.solve_static, m, case="LF1")
        u = np.asarray(r.u).reshape(-1, 6)
        # RBE3-Master P = Mittel aus b und d: w(b) = w(d) = F/2 L³/(3 E I)
        soll = 0.5 * F * L ** 3 / (3 * E * I)
        check("Fall 1 ohne Maske rechnet: w(b) = F/2 · L³/(3 E I)", abs(-u[1, 2] - soll) <= 1e-6 * soll,
              f"ist {-u[1, 2] * 1e3:.6f} mm, soll {soll * 1e3:.6f} mm")
    except RuntimeError as ex:
        check("Fall 1 ohne Maske rechnet", False, str(ex)[:200])
    m, a, b, c, d = basis(arm=False)
    p = m.add_node(L, 1, 0)
    m.load_node(p, Fz=-F, case="LF1")
    an = _still(solver.solve_all, m, workers=1, design=False)
    g = solver.gueltigkeit(an.cases["LF1"].info)
    check("freier Knoten mit Last: „NICHT gültig … Knoten K2 F_z“ wie bisher",
          "NICHT gültig" in g and "Knoten K2" in g, g[:160])


def main():
    for t in (test_matrixdiagnose_rechnet, test_fall1_nennt_knoten, test_m2_richtung, test_zweiter_weg,
              test_kuerzen, test_bewegungsbefund_knoten, test_grosser_nullraum, test_kreisring,
              test_schwimmender_stab, test_kreisring_kette, test_gesunder_kreisring, test_fortschritt,
              test_grenze_sagt_mindestens, test_vorpruefung_ohne_block, test_schutz):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:                  # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{t.__name__} (Ausnahme: {type(ex).__name__}: {ex})", False)
    n_ok = sum(1 for _n, ok in RESULTS if ok)
    print("\n" + "=" * 60)
    print(f"Ergebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    fail = [n for n, ok in RESULTS if not ok]
    if fail:
        print("FEHLGESCHLAGEN:", fail)
    return 0 if not fail else 1


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
