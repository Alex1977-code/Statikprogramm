"""Zerlegung ueber Kontaktrunden weiterverwenden (statik3d.nachfuehrung, 09.10.2026).

Jede Kontaktrunde mit geaenderter Signatur zerlegte bis hierher neu, auch wenn
sich nur eine Bedingung oder eine Gleitrichtung geaendert hatte; am Drehlager
(Mittel) sind das rund 100 s je Runde gegen 6 bis 8 s fuer eine Loesung mit dem
vorhandenen Faktor. Die Nachfuehrung loest solche Runden mit dem alten Faktor und
einer Kapazitaetsmatrix auf den beruehrten Zeilen und Spalten und iteriert gegen
die neue Matrix nach; reicht das nicht, wird wie bisher neu zerlegt.

Was hier belegt wird - jede Behauptung mit einer Zahl:

1. Die Formel: an einem kleinen Sattelpunktsystem wie in StaticSystem.gerandet
   (Steifigkeit, Randzeilen, unsymmetrische Kopplungsspalten) mit weggefallenen
   und neuen Randzeilen, gedrehter Kopplungsspalte und geaendertem Steifigkeits-
   block stimmt die nachgefuehrte Loesung mit der direkten Zerlegung der neuen
   Matrix auf 1e-12 ueberein; Spalten, die schon geloest sind, werden nicht neu
   geloest.
2. Kontaktlaeufe mit Nachfuehrung ("immer") gegen ohne ("nie"): dieselbe Aktivmenge
   in jeder Runde, dieselbe Rundenzahl, derselbe Ausgang, Verschiebungen und
   Reaktionen auf 1e-9 relativ gleich - und weniger echte Zerlegungen.
   Pendelblock (tests.test_kontakt_pendeln) mit und ohne Pendelschutz, Block mit
   Anschlag (tet10), Block mit Reibung (Beispiel), fliessender Reibblock mit kleiner
   Querlast (Plastizitaet mit Kontakt, warm gestartete Laeufe, LF1 und K1).
   Gleichstand: am spiegelsymmetrischen fliessenden Reibblock entscheidet die letzte
   Stelle der Loesung, welcher von zwei gleich belasteten Knoten zuerst gleitet - dort
   trennen sich auch PARDISO und SuperLU ohne Nachfuehrung. Geprueft wird, dass die
   Nachfuehrung nicht weiter abweicht als der andere Loeser und alles konvergiert.
3. Rueckfall: lehnt die Nachfuehrung jede Runde ab (T_MAX = 0), rechnet der Lauf
   bitgleich wie ohne sie und zerlegt genauso oft.
4. Vorgabe "auto": kleine Modelle (Faktor unter NNZ_FAKTOR_MIN) rechnen bitgleich
   wie ohne Nachfuehrung.

Aufruf:  python -m tests.test_faktor_weiter
"""
import contextlib
import os
import sys

import numpy as np
from scipy import sparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import contact, solver                           # noqa: E402
from statik3d.examples_lib import block_friction_example       # noqa: E402
from tests import test_kontakt_pendeln as tp                   # noqa: E402

try:
    from statik3d import nachfuehrung as nfg                   # noqa: E402
except ImportError:                                            # Gegenprobe: Stand ohne Nachfuehrung
    nfg = None

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:78s} {detail}")
    return ok


@contextlib.contextmanager
def modus(wert, **grenzen):
    """Nachfuehrung "immer" / "nie" / "auto", dazu Grenzen (T_MAX ...) fuer diesen Block."""
    if nfg is None:
        yield
        return
    alt = {k: getattr(nfg, k) for k in ["MODUS"] + list(grenzen)}
    nfg.MODUS = wert
    for k, v in grenzen.items():
        setattr(nfg, k, v)
    try:
        yield
    finally:
        for k, v in alt.items():
            setattr(nfg, k, v)


@contextlib.contextmanager
def runden_mitschreiben(buch: list):
    """Je Kontaktrunde die Zustandskennung (Aktivmenge, Haften/Gleiten, Fliessen)
    vor dem Update - in der Reihenfolge, in der die Laeufe rechnen."""
    alt = contact.ContactSystem.update

    def update(self, u, lam=None):
        buch.append((self.zustandskennung(), self.n_active, self.n_slip))
        return alt(self, u, lam)
    contact.ContactSystem.update = update
    try:
        yield
    finally:
        contact.ContactSystem.update = alt


def rechnen(bau, wert, alle=False, **grenzen):
    buch = []
    with modus(wert, **grenzen), runden_mitschreiben(buch):
        m = bau()
        if alle:
            erg = solver.solve_all(m).all_results()
        else:
            r = solver.solve_static(m)
            erg = {r.name or "LF": r}
    return erg, buch


def zaehlen(res, schluessel):
    """Summe ueber alle Kontaktlaeufe eines Ergebnisses (Laufbuch), sonst aus info."""
    inf = res.info or {}
    laeufe = inf.get("laeufe") or []
    if laeufe and schluessel == "contact_factorisations":
        return sum(int(lauf.get("faktorisierungen") or 0) for lauf in laeufe)
    return int(inf.get(schluessel, 0) or 0)


def rel(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    bez = max(float(np.abs(b).max()) if b.size else 0.0, 1e-300)
    return float(np.abs(a - b).max()) / bez if a.size else 0.0


# --------------------------------------------------------------------------
# 1. Die Formel an einem kleinen Sattelpunktsystem
# --------------------------------------------------------------------------
def _sattel(K, E, B, G):
    nf, m = K.shape[0], B.shape[0]
    return sparse.bmat([[K + E, G.T], [B, sparse.csr_matrix((m, m))]], format="csr")


def test_formel():
    print("\n--- Kapazitaetsmatrix gegen direkte Zerlegung (kleines Sattelpunktsystem) ---")
    if nfg is None:
        check("Modul statik3d.nachfuehrung vorhanden", False, "ImportError")
        return
    rng = np.random.default_rng(7)
    nf, m = 60, 12
    A = sparse.random(nf, nf, density=0.08, random_state=1, format="csr")
    K = (A @ A.T + sparse.eye(nf) * 5.0).tocsr()
    E0 = sparse.csr_matrix((nf, nf))
    zeilen = []
    for _ in range(m + 6):
        j = rng.choice(nf, 3, replace=False)
        r = sparse.csr_matrix((rng.standard_normal(3), ([0, 0, 0], j)), shape=(1, nf))
        zeilen.append(r)
    B0 = sparse.vstack(zeilen[:m], format="csr")
    G0 = B0.copy()
    with modus("immer"):
        ls0 = solver.LinearSolver(_sattel(K, E0, B0, G0))
        basis = nfg.Basis(ls0, K.tocsc(), E0, B0, G0)
        # neue Matrix: Zeilen 2 und 5 weg, zwei neue Zeilen, Spalte von Zeile 7 gedreht
        # (Kopplung D), Steifigkeitsblock an drei Freiheitsgraden geaendert
        behalten = [i for i in range(m) if i not in (2, 5)]
        B1 = sparse.vstack([B0[behalten], zeilen[m], zeilen[m + 1]], format="csr")
        D = sparse.lil_matrix(B1.shape)
        k7 = behalten.index(7)
        D[k7, [3, 4]] = [0.3, -0.2]
        G1 = (B1 + D.tocsr()).tocsr()
        dE = sparse.lil_matrix((nf, nf))
        dE[10, 10], dE[10, 11], dE[11, 10], dE[11, 11], dE[40, 40] = 2.0, -1.0, -1.0, 2.0, 0.5
        E1 = dE.tocsr()
        A1 = _sattel(K, E1, B1, G1)
        b = rng.standard_normal(A1.shape[0])
        # Loesen mit dem Faktor ohne Pruefsumme: bitgleich wie pypardiso.solve
        R = rng.standard_normal((ls0.n, 3))
        check("Loesungsphase ohne Pruefsumme bitgleich wie der gewoehnliche Weg",
              np.array_equal(nfg.faktor_loesen(ls0, R), ls0._solve(R))
              and np.array_equal(nfg.faktor_loesen(ls0, R[:, 0]), ls0._solve(R[:, 0])),
              f"Loeser {ls0.backend}")
        x_direkt = solver.LinearSolver(A1).solve(b)
        B1s, G1s = B1.tocsr(), G1.tocsr()
        B1s.sort_indices(), G1s.sort_indices()
        nf1 = basis.nachfuehren(E1, B1s, G1s)
        x = nf1.solve(b)
        geloest = basis.spalten_geloest
        check("nachgefuehrt = direkt zerlegt (weg, neu, Kopplung, Steifigkeit)",
              rel(x, x_direkt) <= 1e-12 and nf1.residuum <= nf1.ziel,
              f"Abweichung {rel(x, x_direkt):.1e}, Residuum {nf1.residuum:.1e}, |T| {len(nf1.T)}, "
              f"Spalten geloest {geloest}")
        # dieselbe Aenderung noch einmal: nichts neu zu loesen
        nf2 = basis.nachfuehren(E1, B1s, G1s)
        x2 = nf2.solve(b)
        check("  zweite Runde mit denselben Beruehrten: keine neue Spalte",
              basis.spalten_geloest == geloest and rel(x2, x_direkt) <= 1e-12,
              f"Spalten geloest {basis.spalten_geloest}, Abweichung {rel(x2, x_direkt):.1e}")
        # singulaere neue Matrix (eine Zeile doppelt): abgelehnt statt falsch
        B3 = sparse.vstack([B0, B0[3]], format="csr")
        B3.sort_indices()
        try:
            nf3 = basis.nachfuehren(E0, B3, B3)
            nf3.solve(rng.standard_normal(nf + m + 1))
            abgelehnt = False
        except nfg.Abgelehnt as ex:
            abgelehnt, grund = True, str(ex)
        check("  singulaere neue Matrix: abgelehnt (dann wird neu zerlegt)", abgelehnt,
              grund[:90] if abgelehnt else "nicht abgelehnt")


# --------------------------------------------------------------------------
# 2./3./4. Kontaktlaeufe
# --------------------------------------------------------------------------
def fliessender_reibblock_schief():
    """Der fliessende Reibblock (tests.test_kontakt_pendeln) mit einer kleinen Querlast,
    die nach x zunimmt: ohne Spiegelsymmetrie gibt es keine zwei Knoten mit gleich
    grosser Kegelueberschreitung (siehe test_gleichstand)."""
    m = tp.fliessender_reibblock()
    X = np.asarray(m.nodes, float)
    oben = [i for i in range(len(X)) if abs(X[i, 2] - 0.4) < 1e-9 and abs(X[i, 0]) <= 0.2 + 1e-9]
    for n in oben:
        m.load_node(n, Fy=4000.0 / len(oben) * (1.0 + X[n, 0]))
    return m


FAELLE = [
    ("Pendelblock mit Schutz (h 0,25)", lambda: tp.lager_in_flaechenachsen(), True, False),
    ("Pendelblock ohne Schutz, Deckel (h 0,25)", lambda: tp.lager_in_flaechenachsen(), False, False),
    ("Block mit Anschlag, tet10", lambda: tp.block_auf_reiblager("tet10", 0.25, 1.2, 0.0, True)[0], True, False),
    ("Block mit Reibung (Beispiel)", block_friction_example, True, False),
    ("Fliessender Reibblock, schief (Plastizitaet, warm)", fliessender_reibblock_schief, True, True),
]


def _vergleich(name, bau, schutz, alle):
    with tp.schutz(schutz):
        e0, buch0 = rechnen(bau, "nie", alle)
        e1, buch1 = rechnen(bau, "immer", alle)
    ok_alle = True
    for n in e0:
        r0, r1 = e0[n], e1[n]
        du, dR = rel(r1.u, r0.u), rel(r1.reactions, r0.reactions)
        f0, f1 = zaehlen(r0, "contact_factorisations"), zaehlen(r1, "contact_factorisations")
        it0, it1 = r0.info.get("contact_iterations"), r1.info.get("contact_iterations")
        k0, k1 = r0.info.get("contact_converged"), r1.info.get("contact_converged")
        g0, g1 = tp.grund(r0), tp.grund(r1)
        ok = (buch1 == buch0 and it1 == it0 and k1 == k0 and g1 == g0 and du <= 1e-9 and dR <= 1e-9)
        ok_alle &= ok
        check(f"{name} {n}: wie neu zerlegt", ok,
              f"Runden {it1} ({it0}), Aktivmengen gleich {buch1 == buch0} ({len(buch1)}), Ausgang {g1}, "
              f"|du| {du:.1e}, |dR| {dR:.1e}")
        check(f"  {n}: weniger echte Zerlegungen", f1 < f0 or f0 <= 1,
              f"{f1} statt {f0} Zerlegungen")
    return ok_alle


def test_kontaktlaeufe():
    print("\n--- Kontaktlaeufe: Nachfuehrung (immer) gegen Neuzerlegung (nie) ---")
    for name, bau, schutz, alle in FAELLE:
        _vergleich(name, bau, schutz, alle)


@contextlib.contextmanager
def loeser(backend):
    from statik3d import parallel
    st = parallel.settings()
    alt = st.solver_backend
    st.solver_backend = backend
    try:
        yield
    finally:
        st.solver_backend = alt


def gespiegelt(m, a):
    """Knotenwerte (nn, >=3) an der Ebene y = 0 gespiegelt: Wert des Spiegelknotens,
    y-Anteil mit umgekehrtem Vorzeichen (nur die Verschiebungen/Kraefte)."""
    X = np.asarray(m.nodes, float)
    a = np.asarray(a, float)[:, :3]
    # Platte und Blockunterseite haben Knoten an denselben Orten: je Ort die Knoten in
    # ihrer Reihenfolge, der k-te dort spiegelt sich auf den k-ten am Spiegelort
    je_ort, rang = {}, []
    for x in X:
        k = (round(x[0], 9), round(x[1], 9) + 0.0, round(x[2], 9))
        rang.append(len(je_ort.setdefault(k, [])))
        je_ort[k].append(len(rang) - 1)
    spiegel = []
    for i, x in enumerate(X):
        lst = je_ort.get((round(x[0], 9), round(-x[1], 9) + 0.0, round(x[2], 9)), [])
        spiegel.append(lst[rang[i]] if rang[i] < len(lst) else -1)
    spiegel = np.array(spiegel)
    if np.any(spiegel < 0):
        return None
    return a[spiegel] * np.array([1.0, -1.0, 1.0])


def test_gleichstand():
    print("\n--- Gleichstand im symmetrischen Modell: die Rundung entscheidet, nicht die Nachfuehrung ---")
    # Am spiegelsymmetrischen fliessenden Reibblock ueberschreiten zwei Knoten (y = +-0,2)
    # den Reibkegel gleich weit (Bedingungen 20 und 24, |Ft| 1 690 N bei mu Fn 1 133 N);
    # die Liniensuche stellt nur einen ins Gleiten, und welcher das ist, entscheidet die
    # letzte Stelle der Loesung. Gemessen 09.10.2026: ohne Nachfuehrung trennen sich
    # PARDISO und SuperLU dort schon nach der 4. Runde, die Nachfuehrung nach der 33.
    # SuperLU kommt danach zum selben Endzustand zurueck, die Nachfuehrung zu seinem
    # Spiegelbild (y -> -y): gleiche Kraefte an den gespiegelten Knoten, u_max auf 15
    # Stellen gleich. Bei einem symmetrischen Modell ist das Spiegelbild einer Loesung
    # ebenso eine Loesung - geprueft wird darum gegen das Ergebnis oder sein Spiegelbild.
    with tp.schutz(True):
        e0, _ = rechnen(tp.fliessender_reibblock, "nie", True)
        e1, _ = rechnen(tp.fliessender_reibblock, "immer", True)
        with loeser("superlu"):
            e2, _ = rechnen(tp.fliessender_reibblock, "nie", True)
    m = tp.fliessender_reibblock()
    for n in e0:
        r0, r1, r2 = e0[n], e1[n], e2[n]
        u0s, R0s = gespiegelt(m, r0.u), gespiegelt(m, r0.reactions)
        d_direkt = max(rel(np.asarray(r1.u)[:, :3], np.asarray(r0.u)[:, :3]),
                       rel(np.asarray(r1.reactions)[:, :3], np.asarray(r0.reactions)[:, :3]))
        d_spiegel = (float("inf") if u0s is None else
                     max(rel(np.asarray(r1.u)[:, :3], u0s), rel(np.asarray(r1.reactions)[:, :3], R0s)))
        d_superlu = rel(r2.u, r0.u)
        pz = [(r.info.get("plastizitaet") or {}).get("konvergiert") for r in (r0, r1, r2)]
        kk = [bool(r.info.get("contact_converged")) for r in (r0, r1, r2)]
        check(f"Fliessender Reibblock (symmetrisch) {n}: Ergebnis oder sein Spiegelbild",
              all(pz) and all(kk) and min(d_direkt, d_spiegel) <= 1e-9,
              f"Abweichung direkt {d_direkt:.1e}, gegen das Spiegelbild {d_spiegel:.1e}; "
              f"SuperLU ohne Nachfuehrung {d_superlu:.1e}; Plastizitaet {pz}, Kontakt {kk}")


def test_rueckfall_und_auto():
    print("\n--- Rueckfall (jede Nachfuehrung abgelehnt) und Vorgabe auto: bitgleich ---")
    bau = lambda: tp.block_auf_reiblager("tet10", 0.25, 1.2, 0.0, True)[0]  # noqa: E731
    with tp.schutz(True):
        e0, b0 = rechnen(bau, "nie")
        e1, b1 = rechnen(bau, "immer", T_MAX=0)
        e2, b2 = rechnen(bau, "auto")
    r0, r1, r2 = (next(iter(e.values())) for e in (e0, e1, e2))
    for name, r, b in (("immer mit T_MAX = 0 (alles abgelehnt)", r1, b1), ("auto (kleines Modell)", r2, b2)):
        du = float(np.max(np.abs(np.asarray(r.u) - np.asarray(r0.u))))
        dR = float(np.max(np.abs(np.asarray(r.reactions) - np.asarray(r0.reactions))))
        f, f0 = zaehlen(r, "contact_factorisations"), zaehlen(r0, "contact_factorisations")
        check(f"{name}: bitgleich wie nie, gleich viele Zerlegungen",
              du == 0.0 and dR == 0.0 and b == b0 and f == f0
              and int(r.info.get("contact_nachfuehrungen", 0) or 0) == 0,
              f"max |du| {du:.1e}, max |dR| {dR:.1e}, Zerlegungen {f} ({f0}), "
              f"Nachfuehrungen {r.info.get('contact_nachfuehrungen')}")


def main() -> int:
    for t in (test_formel, test_kontaktlaeufe, test_gleichstand, test_rueckfall_und_auto):
        try:
            t()
        except Exception as ex:             # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{t.__name__} laeuft ohne Ausnahme", False, str(ex)[:120])
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print("\n" + "=" * 60)
    print(f"Ergebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
