"""
Runde k10 (15.11.2026), Nachbesserung zu Theorie III. Ordnung, Stand 66.

Die Gegenpruefung des ersten Entwurfs (tests/test_th3_anschluss_k10.py) fand
Anschluesse eines Stabendes an einen abgeschalteten Koerper, die Theorie I.
Ordnung mitrechnet (die Starrkoerper baut assemble.starrkoerper immer ein),
Theorie III. Ordnung aber still nicht. Der Entwurf kannte als „gelagert“ nur
Knotenlager direkt am Koerperknoten:
* RBE3 „Stabende 1“ an einer abgeschalteten Schale mit Flaechenlager:
  Theorie I. Ordnung w(b) = 0,0000 mm (der Master folgt dem Mittel seiner
  gehaltenen Slaves), Theorie III. Ordnung still 0,5357 mm (vorher KeyError);
* dasselbe an abgeschalteten Staeben mit Linienlager, und ueber einen RBE2
  an einem gelagerten Knoten eines abgeschalteten Stabes (Kette): Theorie I.
  Ordnung und Gegenrechnung (Staebe geloescht) 0,0000 mm, Theorie III.
  Ordnung 0,5357 mm;
* zwei Kragarmenden per RBE3 „Stabende“ an denselben Knoten eines
  abgeschalteten, ungelagerten Stabzugs: Theorie I. Ordnung und
  Gegenrechnung w(b) = 0,4377 mm, w(b2) = 0,0980 mm (der Stabzug koppelt die
  Enden), Theorie III. Ordnung still 0,5357 und 0,0000 mm.
Jetzt mit Klartext abgewiesen, auch in der Modellpruefung, und vom Merkmal
theorie3_stabende_anschluss erfasst (theorie3._ankerknoten, _th3_wirkung).

Zu weit griff der Entwurf bei einer starren Kopplung „Stabende“ an einem
Knoten Q ohne Element, ohne Last und ohne Lager: Sie traegt nichts (Theorie
I. und III. Ordnung 0,5357 mm = F L³/(3 E I)) und wurde trotzdem abgewiesen
und gekennzeichnet. Das Merkmal griff ausserdem, wenn sich bei einem schon
abgewiesenen Lastfall nur der Text der Abweisung aenderte.

Aufruf:  python -m tests.test_th3_lager_kette_k10
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import tests.test_th3_anschluss_k10 as T  # noqa: E402

RESULTS = T.RESULTS
check = T.check
HAND = T.HAND
F = T.F
L = T.L


def _merkmal():
    from statik3d import rechenverfahren as rv
    return rv.merkmal("theorie3_stabende_anschluss")


def _gerechnet(m, name, knoten, soll, text=T.WIRKT_SK):
    """Seit Stand 77 (Runde k10e, Fehler Nr. 27; bis Stand 76 hiess die
    Funktion _abgewiesen): (Rechnung nach Theorie III. Ordnung ohne Ausnahme
    und Fehler, w der ``knoten`` = ``soll`` (Theorie I. Ordnung derselben
    Rechnung) auf 0,0001 mm; Wirkung nennt ``name`` und die Modellpruefung
    meldet keinen FEHLER; Detail)"""
    m.load_cases["LF1"].theorie = "III"
    pr = T.th3_pruefung(m)
    wk = T.wirkung_pruefung(m)
    an, u, R, f, ex = T.rechne(m, "III")
    ok_r = not ex and not f and T.ist_th3(an)
    w = [float("nan") if ex else -u[k, 2] for k in knoten]
    ok_r = ok_r and all(abs(x - y) <= 1e-7 for x, y in zip(w, soll))
    ok_p = any(text in z and name in z for z in wk) and not any(z.startswith("FEHLER") for z in pr)
    return ok_r, ok_p, ((ex or f)[:150] + f" | Th III {[round(x * 1e3, 6) for x in w]} mm, Th I "
                        f"{[round(x * 1e3, 6) for x in soll]} mm | {[z[:80] for z in wk]} {pr}")


def _w_th1(m, knoten):
    an, u, R, f, ex = T.rechne(m, "I")
    return (float("nan") if ex else -u[knoten, 2]), ex


# --------------------------------------------------------------------------
# Modelle der Gegenpruefung
# --------------------------------------------------------------------------
def schale_flaechenlager():
    """Kragarm a-b, RBE3 „Stabende 1“ von b an die vier Knoten einer Schale,
    die ein Flaechenlager haelt (keine Knotenlager); Schale abgeschaltet."""
    from statik3d.stabeinleitung import STABENDE
    m, a, b = T.basis()
    n = T.platte(m, L, fest=False)
    m.add_surface_support([1], **{k: dict(typ="rigid") for k in ("ux", "uy", "uz")})
    m.add_starrkoerper(b, n, "RBE3", name=STABENDE + "1")
    m.load_node(b, Fz=-F)
    T.situation(m, [1])
    return m, b


def staebe_linienlager(geloescht=False):
    """RBE3 „Stabende 1“ an drei Knoten zweier Staebe, gehalten von einem
    Linienlager; die Staebe abgeschaltet (``geloescht``: Gegenrechnung ohne sie)."""
    from statik3d.stabeinleitung import STABENDE
    m, a, b = T.basis()
    c = m.add_node(L, -0.2, 0)
    d = m.add_node(L, 0.2, 0)
    e = m.add_node(L, 0.0, 0.2)
    if not geloescht:
        m.add_element("beam", [c, d], "ST", "Q")
        m.add_element("beam", [d, e], "ST", "Q")
    starr = dict(typ="rigid")
    m.add_line_support([c, d, e], **{k: starr for k in ("ux", "uy", "uz", "phix", "phiy", "phiz")})
    m.add_starrkoerper(b, [c, d, e], "RBE3", name=STABENDE + "1")
    m.load_node(b, Fz=-F)
    if not geloescht:
        T.situation(m, [1, 2])
    return m, b


def kette_rbe2(geloescht=False):
    """RBE3 „Stabende 1“ an c, d, e; diese per RBE2 „Scheibe“ an den
    eingespannten Knoten g eines Stabes g-h; alle drei Staebe abgeschaltet."""
    from statik3d.stabeinleitung import STABENDE
    m, a, b = T.basis()
    c = m.add_node(L, -0.2, 0)
    d = m.add_node(L, 0.2, 0)
    e = m.add_node(L, 0.0, 0.2)
    g = m.add_node(L, 0, -0.5)
    h = m.add_node(L, 0, -1.0)
    if not geloescht:
        m.add_element("beam", [c, d], "ST", "Q")
        m.add_element("beam", [d, e], "ST", "Q")
        m.add_element("beam", [g, h], "ST", "Q")
    m.fix(g, "all")
    m.add_starrkoerper(g, [c, d, e], "RBE2", name="Scheibe")
    m.add_starrkoerper(b, [c, d, e], "RBE3", name=STABENDE + "1")
    m.load_node(b, Fz=-F)
    if not geloescht:
        T.situation(m, [1, 2, 3])
    return m, b


def zwei_enden(geloescht=False):
    """Kragarme a-b und a2-b2 (y = 1), beide Enden per RBE3 „Stabende“ an
    dieselben drei Knoten eines abgeschalteten, ungelagerten Stabzugs; Last
    nur an b."""
    from statik3d.stabeinleitung import STABENDE
    m, a, b = T.basis()
    a2 = m.add_node(0, 1, 0)
    b2 = m.add_node(L, 1, 0)
    m.add_element("beam", [a2, b2], "ST", "Q")
    m.fix(a2, "all")
    c = m.add_node(L, 0.3, 0)
    d = m.add_node(L, 0.7, 0)
    e = m.add_node(L, 0.5, 0.2)
    if not geloescht:
        m.add_element("beam", [c, d], "ST", "Q")
        m.add_element("beam", [d, e], "ST", "Q")
    m.add_starrkoerper(b, [c, d, e], "RBE3", name=STABENDE + "1")
    m.add_starrkoerper(b2, [c, d, e], "RBE3", name=STABENDE + "2")
    m.load_node(b, Fz=-F)
    if not geloescht:
        T.situation(m, [2, 3])
    return m, b, b2


def q_ohne_last():
    """Starre Kopplung „Stabende“ b-Q, Q ohne Element, ohne Last, ohne Lager."""
    from statik3d.model import Kopplung
    from statik3d.fugen import STABENDE_GRUPPE
    m, a, b = T.basis()
    q = m.add_node(L, 0, 0)
    m.kopplungen.append(Kopplung(b, q, T.EINS, [float("inf")] * 3, STABENDE_GRUPPE + "K9"))
    m.load_node(b, Fz=-F)
    return m, b, q


def k8_mit_zweiter_kopplung():
    """Zwei Kragarme, Enden starr gekoppelt (schon in Runde k8 abgewiesen),
    dazu eine zweite starre Kopplung „Stabende“ an Q ohne Element mit Last."""
    from statik3d.model import Kopplung
    from statik3d.fugen import STABENDE_GRUPPE
    m, a, b = T.basis()
    c = m.add_node(0, 0, 0)
    d = m.add_node(L, 0, 0)
    m.add_element("beam", [c, d], "ST", "Q")
    m.fix(c, "all")
    m.kopplungen.append(Kopplung(b, d, T.EINS, [float("inf")] * 3, STABENDE_GRUPPE + "K9"))
    q = m.add_node(L, 0, 0)
    m.kopplungen.append(Kopplung(b, q, T.EINS, [float("inf")] * 3, STABENDE_GRUPPE + "K8"))
    m.load_node(b, Fz=-F)
    m.load_node(q, Fz=-F)
    return m


# --------------------------------------------------------------------------
# Pruefungen
# --------------------------------------------------------------------------
def test_flaechenlager():
    m, b = schale_flaechenlager()
    w1, ex1 = _w_th1(m, b)
    check("Flächenlager an abgeschalteter Schale: Theorie I. Ordnung w(b) = 0 (Master folgt den gehaltenen "
          "Slaves)", not ex1 and abs(w1) < 1e-3 * HAND, f"{ex1} w {w1 * 1e3:.6f} mm")
    m, b = schale_flaechenlager()
    ok_r, ok_p, det = _gerechnet(m, "Stabende 1", [b], [w1])
    check("… Theorie III. Ordnung gerechnet (seit Stand 77), w(b) = Theorie I. Ordnung = 0 statt still "
          "0,5357 mm", ok_r, det)
    check("… Wirkung „Stabende 1“, Modellprüfung ohne FEHLER", ok_p, det)


def test_linienlager():
    m, b = staebe_linienlager()
    w1, ex1 = _w_th1(m, b)
    m2, b2 = staebe_linienlager(True)
    w2, ex2 = _w_th1(m2, b2)
    check("Linienlager an abgeschalteten Stäben: Theorie I. Ordnung = Gegenrechnung (Stäbe gelöscht) = 0",
          not ex1 and not ex2 and abs(w1 - w2) <= 1e-9 and abs(w1) < 1e-3 * HAND,
          f"w {w1 * 1e3:.6f} mm, Gegenrechnung {w2 * 1e3:.6f} mm")
    m, b = staebe_linienlager()
    ok_r, ok_p, det = _gerechnet(m, "Stabende 1", [b], [w1])
    check("… Theorie III. Ordnung gerechnet, w(b) = Theorie I. Ordnung = Gegenrechnung statt still 0,5357 mm",
          ok_r, det)
    check("… Wirkung „Stabende 1“, Modellprüfung ohne FEHLER", ok_p, det)


def test_kette():
    m, b = kette_rbe2()
    w1, ex1 = _w_th1(m, b)
    m2, b2 = kette_rbe2(True)
    w2, ex2 = _w_th1(m2, b2)
    check("Kette RBE3 - RBE2 - gelagerter Knoten, alles abgeschaltet: Theorie I. Ordnung = Gegenrechnung = 0",
          not ex1 and not ex2 and abs(w1 - w2) <= 1e-9 and abs(w1) < 1e-3 * HAND,
          f"w {w1 * 1e3:.6f} mm, Gegenrechnung {w2 * 1e3:.6f} mm")
    m, b = kette_rbe2()
    ok_r, ok_p, det = _gerechnet(m, "Stabende 1", [b], [w1])
    check("… Theorie III. Ordnung gerechnet, w(b) = Theorie I. Ordnung = Gegenrechnung statt still 0,5357 mm",
          ok_r, det)
    check("… Wirkung „Scheibe“ und „Stabende 1“, Modellprüfung ohne FEHLER", ok_p and "Scheibe" in det, det)


def test_zwei_enden():
    m, b, b2 = zwei_enden()
    _an, u, _R, _f, ex = T.rechne(m, "I")
    m2, c, c2 = zwei_enden(True)
    _an2, u2, _R2, _f2, ex2 = T.rechne(m2, "I")
    ok = not ex and not ex2
    if ok:
        w, w_2, g, g_2 = -u[b, 2], -u[b2, 2], -u2[c, 2], -u2[c2, 2]
        ok = (abs(w - g) <= 1e-9 and abs(w_2 - g_2) <= 1e-9 and w_2 > 0.1 * HAND and w < 0.9 * HAND)
        det = f"w(b) {w * 1e3:.4f} / {g * 1e3:.4f} mm, w(b2) {w_2 * 1e3:.4f} / {g_2 * 1e3:.4f} mm"
    else:
        det = ex or ex2
    check("Zwei Stabenden am selben abgeschalteten Stabzug: Theorie I. Ordnung = Gegenrechnung, der Stabzug "
          "koppelt die Enden", ok, det)
    m, b, b2 = zwei_enden()
    ok_r, ok_p, det = _gerechnet(m, "Stabende 2", [b, b2], [-u[b, 2], -u[b2, 2]] if not ex else [0.0, 0.0])
    check("… Theorie III. Ordnung gerechnet, w(b), w(b2) = Theorie I. Ordnung = Gegenrechnung statt still "
          "0,5357 und 0,0000 mm", ok_r, det)
    check("… Wirkung „Stabende 1“ und „Stabende 2“, Modellprüfung ohne FEHLER", ok_p and "Stabende 1" in det, det)


def test_q_ohne_last():
    m, b, q = q_ohne_last()
    w1, ex1 = _w_th1(m, b)
    m, b, q = q_ohne_last()
    m.load_cases["LF1"].theorie = "III"
    pr = T.th3_pruefung(m)
    an, u, R, f, ex = T.rechne(m, "III")
    w3 = float("nan") if ex else -u[b, 2]
    check("Kopplung „Stabende“ an Q ohne Element, Last und Lager: Theorie III. Ordnung gerechnet, keine "
          "Meldung", not ex and not f and not pr
          and str(an.cases["LF1"].info.get("theorie", "")).startswith("III"),
          f"{(ex or f)[:120]!r} {pr}")
    check("… w(b) = Theorie I. Ordnung = F L³/(3 E I)",
          abs(w3 - w1) <= 1e-4 * HAND and abs(w3 - HAND) <= 1e-4 * HAND,
          f"III {w3 * 1e3:.6f} mm, I {w1 * 1e3:.6f} mm, Hand {HAND * 1e3:.6f} mm")


def test_merkmal():
    from statik3d import solver
    from statik3d.theorie3 import kopplung_wirkung_modell as kopplung_sperre_modell
    mk = _merkmal()
    if not check("Merkmal theorie3_stabende_anschluss vorhanden", mk is not None):
        return
    faelle = []
    for name, bau in (("Flächenlager", lambda: schale_flaechenlager()[0]),
                      ("Linienlager", lambda: staebe_linienlager()[0]),
                      ("Kette", lambda: kette_rbe2()[0]),
                      ("zwei Stabenden", lambda: zwei_enden()[0])):
        m = bau()
        m.load_cases["LF1"].theorie = "III"
        faelle.append((name, mk.betrifft(m)))
    check("betrifft: Flächenlager, Linienlager, Kette und zwei Stabenden ja", all(x for _n, x in faelle), faelle)
    m, b, q = q_ohne_last()
    m.load_cases["LF1"].theorie = "III"
    check("betrifft: Kopplung „Stabende“ an Q ohne Element, Last und Lager nein (richtig gerechnet)",
          not mk.betrifft(m), mk.betrifft(m))
    m = k8_mit_zweiter_kopplung()
    m.load_cases["LF1"].theorie = "III"
    neu = kopplung_sperre_modell(m)
    alt = kopplung_sperre_modell(m, alt=True)
    check("betrifft: schon nach der alten Regel wirksam (bis Stand 76 abgewiesen), nur der Text ändert sich - "
          "nein",
          alt and neu and set(alt) != set(neu) and not mk.betrifft(m),
          f"alt {list(alt)[:1]} neu {list(neu)[:1]} betrifft {mk.betrifft(m)}")
    m = kette_rbe2()[0]
    m.load_cases["LF1"].theorie = "III"
    an = T._still(solver.solve_all, m, workers=1, design=False)
    check("im Ergebnis: Kette nennt LF1", "LF1" in (mk.im_ergebnis(m, an) or ""), mk.im_ergebnis(m, an))


def main():
    for t in (test_flaechenlager, test_linienlager, test_kette, test_zwei_enden, test_q_ohne_last,
              test_merkmal):
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
