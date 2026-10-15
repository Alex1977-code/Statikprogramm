"""Reibung mit konsistenter Tangente (contact.REIBUNGSTANGENTE, Entscheidung des
Anwenders vom 15.10.2026): Rueckabbildung des Coulomb-Gesetzes je Knoten, Haften als
Feder k_h relativ zur Knotensteifigkeit, Gleiten mit der Ableitung von mu p t/|t| nach u
(unsymmetrisch nur mit gleitenden Knoten), Normalbedingung exakt wie bisher.

Was hier belegt wird - jede Behauptung mit einer Zahl:

1. Schalter und Haftfaktor sind Einstellungen am Modell (Plastizitaet, NEUE_FELDER),
   mit der Vorgabe nicht in der Datei, gespeichert und geladen, in der Maske Berechnung.
2. Klotz mit Reibung auf einem Flaechenlager wie „Starr“ am Drehlager (uz Ausfall bei
   Zug, ux/uy Reibung mu 0,2), in x zusaetzlich von einer Zugfeder k_s gehalten: haftet
   bis F = mu N (0,999 mu N: kein Knoten gleitet), gleitet darueber (1,001 mu N: alle),
   Gleitweg s = (F - mu N)/k_s auf 1e-4 ueber die Lastgeschichte 0,5 ... 2 mu N,
   Reibkraft mu N, Gleichgewicht. Ruecknahme: am alten Stand traegt die feine
   Reststeifigkeit der gleitenden Knoten (1e-8 k_t je Knoten am steifen Klotz) die
   Kraft, und der Lauf heisst trotzdem konvergiert - Gleitweg 1 statt 100 um.
3. Vorgespanntes Blechpaket (Schraube mit Endvorspannung F_v, Fuge mu 0,3, Rueckhaltung
   k_s): haftet bis mu F_v, gleitet darueber mit (Q - mu F_v)/k_s; Runden je Lastfall.
4. Dissipation: je Laststufe und je Knoten ist die Reibarbeit F_t . Δs >= 0 (s der
   Gleitweg ohne den elastischen Anteil F_t/k_h).
5. Konvergenzrate: an den Pruefmodellen der Kontaktsuiten (Block mit Reibung, Stempel
   auf Sockel, Platte mit Ankern wie das Drehlager) weniger Runden als am alten Stand,
   Ergebnis gleich (u auf 1e-4).
6. Unsymmetrisch nur mit gleitenden Knoten: haften alle, gibt es keine Kopplungsspalte.
7. Reibungsfrei rechnet alles bitgleich, mit und ohne Schalter.

Aufruf:  python -m tests.test_reibungstangente
"""
import math
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_reibungstangente_"), "einstellungen.json")

from statik3d import contact, mesher, solver                   # noqa: E402
from statik3d.model import Material, Model, NodalLoad, Section  # noqa: E402

RESULTS = []
MU, N, K_S = 0.2, 100e3, 1e8


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:84s} {detail}")
    return ok


def _nl(n, fx, fy, fz):
    return NodalLoad(int(n), [fx, fy, fz, 0.0, 0.0, 0.0])


def klotz(anteile, mu=MU, k_s=K_S, E_klotz=210e12, rt=True):
    """Steifer Klotz 0,4 x 0,4 x 0,2 m (hex8 4 x 4 x 2) auf einem Lager wie „Starr“ am
    Drehlager: uz starr mit Ausfall bei Zug, ux/uy Reibung mu mit Bezug uz. Auflast N und
    Querkraft F = a mu N in x in der Lagerebene (kein Kippmoment); dazu in x ein
    Fachwerkstab k_s = EA/L von der Mitte der Unterseite zu einem festen Punkt. Je Anteil a
    ein Lastfall „F<a>“. Geschlossene Loesung: Gleitweg max(0, F - mu N)/k_s."""
    m = Model("Klotz mit Reibung")
    m.add_material(Material("Starr", E=E_klotz, nu=0.3))
    m.add_material(Material("Feder", E=210e9, nu=0.3))
    b = mesher.grid_box(m, "Starr", 0.4, 0.4, 0.2, 4, 4, 2, origin=(-0.2, -0.2, 0.0))
    unten = [int(x) for x in b[:, :, 0].ravel()]
    for n in unten:
        m.support(n, [2], uz=dict(failure="zug"), ux=dict(mu=mu, mu_ref=2), uy=dict(mu=mu, mu_ref=2))
    mitte = int(b[2, 2, 0])
    A = k_s * 1.0 / 210e9
    m.add_section(Section.circle("Feder", float(np.sqrt(4.0 * A / np.pi))))
    X = np.asarray(m.nodes, float)
    fest = m.add_node(X[mitte, 0] - 1.0, X[mitte, 1], X[mitte, 2])
    m.fix(fest, "all")
    e = m.add_element("truss", [fest, mitte], "Feder", "Feder")
    m.add_member("Feder", [e])
    m.load_cases.clear()
    for a in anteile:
        lf = f"F{a:g}"
        m.add_load_case(lf).gravity = [0.0, 0.0, 0.0]
        for n in unten:
            m.case(lf).nodal_loads.append(_nl(n, a * mu * N / len(unten), 0.0, -N / len(unten)))
    m.plastizitaet.reibungstangente = rt
    return m, unten, e


def blechpaket(anteile, mu=0.3, Fv=100e3, k_s=5e7, rt=True, n=4, t=0.02, b=0.12):
    """Zwei Bleche (hex8, steif: E 2,1e14), das obere b x b x t, das untere doppelt so breit
    (die Randknoten des oberen liegen innen, ihre Normale ist z) und unten fest; Fuge mu
    (Kontaktpaar, exakte Normalbedingung). Schraube Rund 16 (E 2,1e11) von der Mitte der
    Unterseite des unteren zur Mitte der Oberseite des oberen Blechs, Endvorspannung F_v
    (Spannschritt). Querkraft Q = a mu F_v in x auf die Oberseite, Rueckhaltung in x mit
    k_s. Geschlossene Loesung: Haften bis mu F_v, dann Gleitweg (Q - mu F_v)/k_s."""
    m = Model("Blechpaket")
    m.add_material(Material("Blech", E=210e12, nu=0.3))
    m.add_material(Material("Stahl", E=210e9, nu=0.3))
    unten = mesher.grid_box(m, "Blech", 2 * b, 2 * b, t, 2 * n, 2 * n, 2, origin=(-b, -b, -t))
    n_unten = len(m.elements)
    for k in unten[:, :, 0].ravel():
        m.fix(int(k), "all")
    oben = mesher.grid_box(m, "Blech", b, b, t, n, n, 2, origin=(-b / 2, -b / 2, 0.0))
    fuge = [int(k) for k in oben[:, :, 0].ravel()]
    m.add_contact_pair("Fuge", fuge, list(range(n_unten)), mu=mu)
    m.add_section(Section.circle("Rund 16", 0.016))
    e_s = m.add_element("truss", [int(unten[n, n, 0]), int(oben[n // 2, n // 2, -1])], "Stahl", "Rund 16")
    m.add_member("Schraube", [e_s])
    X = np.asarray(m.nodes, float)
    seite = int(oben[0, n // 2, 1])
    m.add_section(Section.circle("Feder", float(np.sqrt(4.0 * (k_s / 210e9) / np.pi))))
    fest = m.add_node(X[seite, 0] - 1.0, X[seite, 1], X[seite, 2])
    m.fix(fest, "all")
    e_f = m.add_element("truss", [fest, seite], "Stahl", "Feder")
    m.add_member("Feder", [e_f])
    deckel = [int(k) for k in oben[:, :, -1].ravel()]
    m.load_cases.clear()
    for a in anteile:
        lf = f"Q{a:g}"
        m.add_load_case(lf).gravity = [0.0, 0.0, 0.0]
        m.add_vorspannung("Schraube", Fv, case=lf, sollkraft=True)
        for k in deckel:
            m.case(lf).nodal_loads.append(_nl(k, a * mu * Fv / len(deckel), 0.0, 0.0))
    m.plastizitaet.reibungstangente = rt
    return m, fuge, e_s, e_f


class _Gemerkt:
    """Das Kontaktsystem des letzten Laufs (bei results()) und die Systemmatrizen je Runde."""

    def __enter__(self):
        self.cs, self.D, self.sym = None, [], []
        self._res, self._sm = contact.ContactSystem.results, contact.ContactSystem.system_matrizen
        me = self

        def res(cs):
            me.cs = cs
            return me._res(cs)

        def sm(cs, ndof):
            aus = me._sm(cs, ndof)
            me.D.append(getattr(cs, "D_kopplung", None) is not None)
            Kc = aus[0]
            me.sym.append(float(abs(Kc - Kc.T).max()) if Kc.nnz else 0.0)
            return aus
        contact.ContactSystem.results = res
        contact.ContactSystem.system_matrizen = sm
        return self

    def __exit__(self, *a):
        contact.ContactSystem.results = self._res
        contact.ContactSystem.system_matrizen = self._sm


def _runden(r):
    return sum(int(e.get("schritte") or 0) for e in (r.info or {}).get("laeufe") or [])


def _gg(r):
    return float(((r.info or {}).get("gleichgewicht_global") or {}).get("rel_F", float("nan")))


def _reibknoten(cs, u):
    """[(Index, gleitet, d_t (2,), F_t (2,), mu Fn, k_h)] der aktiven Reibknoten."""
    aus = []
    for i, c in enumerate(cs.cons):
        if c.active and c.ct is not None and c.mu > 0 and not c.haften:
            dt = np.array([c.ct[0] @ u[c.dofs], c.ct[1] @ u[c.dofs]])
            # (am Stand ohne Reibungstangente die Haftfeder k_t - fuer die Gegenprobe)
            kh = cs._k_haft(c) if hasattr(cs, "_k_haft") else c.kt
            aus.append((i, bool(c.slip), dt, np.asarray(c.Ft, float), c.mu * max(c.Fn, 0.0), kh))
    return aus


# --------------------------------------------------------------------------
def test_einstellungen():
    print("\n--- Einstellungen am Modell: Vorgabe, Speichern und Laden, NEUE_FELDER, Maske ---")
    from statik3d.model import NEUE_FELDER
    from statik3d.plastizitaet import Plastizitaet
    pz = Plastizitaet()
    check("Vorgabe: Reibungstangente aus (bis zur Abnahme am Drehlager), Haftfaktor 1000",
          getattr(pz, "reibungstangente", None) is False and getattr(pz, "haft_faktor", None) == 1000.0
          and contact.HAFT_FAKTOR == 1000.0,
          f"{getattr(pz, 'reibungstangente', None)}, {getattr(pz, 'haft_faktor', None)}")
    vg = NEUE_FELDER.get("plastizitaet", {})
    check("in NEUE_FELDER mit der Vorgabe (alte Ergebnisdateien passen weiter)",
          vg.get("reibungstangente", None) is False and vg.get("haft_faktor") == 1000.0, str(sorted(vg)))
    m = Model("x")
    d0 = m.to_dict()["plastizitaet"]
    check("mit der Vorgabe nicht in der Datei", "reibungstangente" not in d0 and "haft_faktor" not in d0,
          str(sorted(d0)))
    m.plastizitaet.reibungstangente, m.plastizitaet.haft_faktor = True, 250.0
    m2 = Model.from_dict(m.to_dict())
    check("gespeichert und geladen",
          (getattr(m2.plastizitaet, "reibungstangente", None), getattr(m2.plastizitaet, "haft_faktor", None))
          == (True, 250.0))
    an, f = solver.reibungstangente(m2)
    check("der Löser liest beide (solver.reibungstangente)", an is True and f == 250.0, f"{an}, {f}")
    from tests import test_fehler_p15 as p15
    w, _app = p15._fenster()
    if not hasattr(w, "cb_reibungstangente"):
        check("Maske Berechnung: Schalter und Haftsteifigkeit in der Gruppe „Kontaktlauf“", False, "keine Felder")
        return
    w.model.plastizitaet.reibungstangente, w.model.plastizitaet.haft_faktor = True, 250.0
    w._plast_anzeigen()
    check("Maske Berechnung zeigt beide Werte",
          w.cb_reibungstangente.isChecked() and abs(w.sp_haft_faktor.value() - 250.0) < 1e-9,
          f"{w.cb_reibungstangente.isChecked()}, {w.sp_haft_faktor.value()}")
    w.cb_reibungstangente.setChecked(False)
    w.sp_haft_faktor.setValue(40.0)
    w._plast_schreiben(w.model.plastizitaet)
    check("… und schreibt sie ins Modell",
          w.model.plastizitaet.reibungstangente is False and w.model.plastizitaet.haft_faktor == 40.0,
          f"{w.model.plastizitaet.reibungstangente}, {w.model.plastizitaet.haft_faktor}")


def test_klotz():
    print("\n--- Klotz mit Reibung: Gleitbeginn bei mu N, Gleitweg (F - mu N)/k_s ---")
    anteile = (0.5, 0.999, 1.001, 1.25, 1.5, 2.0)
    m, unten, e = klotz(anteile)
    for a in anteile:
        with _Gemerkt() as g:
            r = solver.solve_static(m, case=f"F{a:g}")
        u = np.asarray(r.u, float).reshape(-1, 6)
        s = float(u[unten, 0].mean())
        soll = max(0.0, (a - 1.0) * MU * N) / K_S
        kn = _reibknoten(g.cs, np.asarray(r.u, float).ravel())
        n_gl = sum(1 for k in kn if k[1])
        ft = sum(float(c["Ft"]) for c in r.contact or [])
        konv = bool(r.info.get("contact_converged")) and not solver.kontakt_vorlaeufig(r.info)
        if a < 1.0:
            ok = konv and n_gl == 0 and abs(s) < 1e-9 and abs(ft - a * MU * N) < 1e-6 * MU * N
            check(f"F = {a:g} mu N: haftet (kein Knoten gleitet), Reibkraft F, Weg < 1 nm",
                  ok and _gg(r) < 1e-6, f"{n_gl}/{len(kn)} gleiten, Weg {s * 1e9:.3g} nm, Σ|F_t| {ft / 1e3:.4f} kN, "
                  f"{_runden(r)} Runden")
        else:
            # Toleranz des Weges: 1e-4 und der Rest, bei dem der Lauf endet (RESIDUUM_ANTEIL
            # der Kontaktkraft N, ueber die Feder k_s); Gleichgewicht ebenso auf 1e-6
            tol = 1e-4 * soll + contact.RESIDUUM_ANTEIL * N / K_S
            ok = (konv and n_gl == len(kn) and abs(s - soll) <= tol
                  and abs(ft - MU * N) < 1e-6 * MU * N and _gg(r) < 1e-6)
            check(f"F = {a:g} mu N: alle gleiten, Weg (F - mu N)/k_s auf 1e-4, Reibkraft mu N, Gleichgewicht",
                  ok, f"{n_gl}/{len(kn)} gleiten, Weg {s * 1e6:.5f} µm (soll {soll * 1e6:.5f}), "
                  f"Σ|F_t| {ft / 1e3:.5f} kN, rel_F {_gg(r):.1e}, {_runden(r)} Runden")
        check(f"  F = {a:g} mu N: höchstens 8 Runden", _runden(r) <= 8, f"{_runden(r)}")
    # Ruecknahme: alter Stand (primal-dual) am selben Modell
    m0, unten0, _e0 = klotz((1.5,), rt=False)
    r0 = solver.solve_static(m0, case="F1.5")
    s0 = float(np.asarray(r0.u, float).reshape(-1, 6)[unten0, 0].mean())
    check("Rücknahme (Schalter aus): Gleitweg weit unter (F - mu N)/k_s, Gleichgewicht verletzt",
          s0 < 0.1 * 0.5 * MU * N / K_S and _gg(r0) > 1e-2,
          f"Weg {s0 * 1e6:.3f} µm statt {0.5 * MU * N / K_S * 1e6:.1f}, rel_F {_gg(r0):.2e}, "
          f"konvergiert {r0.info.get('contact_converged')}")


def test_lastgeschichte_dissipation():
    print("\n--- Lastgeschichte 0,5 … 2 mu N: Gleitweg und Dissipation je Stufe und Knoten ---")
    anteile = (0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0)
    m, unten, _e = klotz(anteile)
    vorher = None
    d_min, d_sum, fehler_weg = float("inf"), 0.0, 0.0
    for a in anteile:
        with _Gemerkt() as g:
            r = solver.solve_static(m, case=f"F{a:g}")
        u = np.asarray(r.u, float).ravel()
        kn = _reibknoten(g.cs, u)
        # Gleitweg ohne den elastischen Anteil F_t/k_h
        s = {i: dt - Ft / kh for i, _gl, dt, Ft, _l, kh in kn}
        Ft = {i: Ftv for i, _gl, _dt, Ftv, _l, _kh in kn}
        soll = max(0.0, (a - 1.0) * MU * N) / K_S
        fehler_weg = max(fehler_weg, abs(float(np.asarray(r.u).reshape(-1, 6)[unten, 0].mean()) - soll))
        if vorher is not None:
            for i in s:
                if i in vorher:
                    d = float(Ft[i] @ (s[i] - vorher[i]))
                    d_min = min(d_min, d)
                    d_sum += d
        vorher = s
    check("Gleitweg über die Lastgeschichte auf 1e-4 von (F - mu N)/k_s", fehler_weg < 1e-4 * MU * N / K_S,
          f"größter Fehler {fehler_weg * 1e9:.3g} nm bei {MU * N / K_S * 1e6:.0f} µm")
    check("Dissipation je Stufe und Knoten F_t · Δs >= 0 (bis 1e-9 J)", d_min >= -1e-9,
          f"kleinste {d_min:.3e} J, Summe {d_sum:.4f} J")
    soll_d = MU * N * 1.0 * MU * N / K_S       # mu N mal Gleitweg bei 2 mu N
    check("Summe der Dissipation = mu N × Gleitweg (auf 1e-4)", abs(d_sum - soll_d) <= 1e-4 * soll_d,
          f"{d_sum:.5f} J, soll {soll_d:.5f} J")


def test_blechpaket():
    print("\n--- Vorgespanntes Blechpaket unter Querkraft: Haften bis mu F_v, dann Gleiten ---")
    mu, Fv, k_s = 0.3, 100e3, 5e7
    anteile = (0.5, 0.95, 1.05, 1.5)
    m, fuge, e_s, e_f = blechpaket(anteile)
    vorher, d_min = None, float("inf")
    for a in anteile:
        with _Gemerkt() as g:
            r = solver.solve_static(m, case=f"Q{a:g}")
        uu = np.asarray(r.u, float)
        s = float(uu.reshape(-1, 6)[fuge, 0].mean())
        soll = max(0.0, (a - 1.0) * mu * Fv) / k_s
        kn = _reibknoten(g.cs, uu.ravel())
        n_gl = sum(1 for k in kn if k[1])
        ein = [c for c in r.contact or [] if str(c.get("label", "")).startswith("Fuge")]
        fn = sum(float(c["Fn"]) for c in ein)
        ftx = -sum(float(c["F_vek"][0]) for c in ein)
        laeufe = r.info.get("laeufe") or []
        konv = bool(r.info.get("contact_converged")) and not solver.kontakt_vorlaeufig(r.info)
        runden = [int(x.get("schritte") or 0) for x in laeufe]
        if a < 1.0:
            check(f"Q = {a:g} mu F_v: das Blech haftet (Weg < 10 nm, Feder trägt nichts), Fn = F_v",
                  konv and abs(s) < 1e-8 and abs(r.beam_forces[e_f]["N"][1]) < 1e-4 * Fv
                  and abs(fn - Fv) < 1e-4 * Fv,
                  f"Weg {s * 1e9:.3g} nm, gleitend {n_gl}/{len(kn)}, ΣFn {fn / 1e3:.3f} kN, Runden {runden}")
        else:
            check(f"Q = {a:g} mu F_v: alle gleiten, Weg (Q - mu F_v)/k_s auf 1e-3, Reibkraft mu F_v",
                  konv and n_gl == len(kn) and abs(s - soll) <= 1e-3 * soll and abs(ftx - mu * fn) < 1e-5 * Fv,
                  f"Weg {s * 1e6:.4f} µm (soll {soll * 1e6:.3f}), gleitend {n_gl}/{len(kn)}, "
                  f"Reibkraft {ftx / 1e3:.4f} kN (mu ΣFn {mu * fn / 1e3:.4f}), Runden {runden}")
        check(f"  Q = {a:g} mu F_v: je Kontaktlauf höchstens 10 Runden", max(runden) <= 10, str(runden))
        sl = {i: dt - Ft / kh for i, _gl, dt, Ft, _l, kh in kn}
        if vorher is not None:
            Ft = {i: f for i, _gl, _dt, f, _l, _kh in kn}
            for i in sl:
                if i in vorher:
                    d_min = min(d_min, float(Ft[i] @ (sl[i] - vorher[i])))
        vorher = sl
    check("Dissipation je Stufe und Knoten >= 0 (bis 1e-9 J)", d_min >= -1e-9, f"kleinste {d_min:.3e} J")


def _modelle():
    from statik3d.examples_lib import block_friction_example
    from tests import test_kontakt_warmstart as kw
    from tests import test_plastizitaet as tp

    def stempel():
        m = tp._drehlagerartiges_modell()
        m.plastizitaet.an = False
        return m

    def anschlag():
        # Block auf einem Lager wie „Starr“ mit Anschlag (tests/test_kontakt_pendeln): mit der
        # Reibungstangente blieb er bis zum Phasenwechsel bei Wechseln nur der Reibungstangente
        # in Phase 1 und pendelte dort bis max_iter (120 Runden)
        from tests.test_kontakt_pendeln import block_auf_reiblager
        return block_auf_reiblager("tet4", 0.25, 1.2, 0.0, True)[0]
    return (("Block mit Reibung", block_friction_example), ("Stempel auf Sockel", stempel),
            ("Block mit Anschlag, tet4", anschlag),
            ("Platte mit Ankern (plastisch, wie Drehlager)", kw.platte),
            ("Stempel auf Sockel, plastisch", tp._drehlagerartiges_modell))


def test_konvergenzrate():
    print("\n--- Konvergenzrate: Runden gegen den alten Stand, gleiches Ergebnis, Coulomb ---")
    for name, bau in _modelle():
        aus = {}
        for rt in (False, True):
            m = bau()
            m.plastizitaet.reibungstangente = rt
            with _Gemerkt() as g:
                r = solver.solve_static(m)
            aus[rt] = (r, g.cs)
        (r0, _cs0), (r1, cs1) = aus[False], aus[True]
        u0, u1 = np.asarray(r0.u, float), np.asarray(r1.u, float)
        du = float(np.abs(u1 - u0).max()) / float(np.abs(u0).max())
        winkel, kegel = 0.0, 0.0
        for _i, gl, dt, Ft, lim, _kh in _reibknoten(cs1, u1.ravel()):
            if gl and np.linalg.norm(dt) > 0 and np.linalg.norm(Ft) > 0:
                cw = float(dt @ Ft) / (np.linalg.norm(dt) * np.linalg.norm(Ft))
                winkel = max(winkel, math.degrees(math.acos(max(-1.0, min(1.0, cw)))))
            elif not gl:
                kegel = max(kegel, float(np.linalg.norm(Ft)) / max(lim, 1e-300))
        konv = bool(r1.info.get("contact_converged")) and not solver.kontakt_vorlaeufig(r1.info)
        check(f"{name}: konvergiert, weniger Runden, u wie vorher auf 1e-4",
              konv and _runden(r1) < _runden(r0) and du < 1e-4,
              f"{_runden(r0)} -> {_runden(r1)} Runden, Δu {du:.1e}")
        check(f"  {name}: Reibkraft längs des Wegs (< 0,001 Grad), Haften im Kegel",
              winkel < 1e-3 and kegel <= 1.0 + 1e-9, f"{winkel:.2e} Grad, |F_t|/mu Fn {kegel:.6f}")


def test_symmetrie():
    print("\n--- Unsymmetrisch nur mit gleitenden Knoten ---")
    m, _u, _e = klotz((0.5, 1.5))
    with _Gemerkt() as g:
        solver.solve_static(m, case="F0.5")
    check("alle haften: keine Kopplungsspalte, Kc symmetrisch", not any(g.D) and max(g.sym) == 0.0,
          f"Spalte in {sum(g.D)} von {len(g.D)} Runden, |Kc - Kc^T| {max(g.sym):.1e}")
    with _Gemerkt() as g:
        solver.solve_static(m, case="F1.5")
    check("gleitend: Kopplungsspalte (unsymmetrisch), Kc selbst symmetrisch", any(g.D) and max(g.sym) == 0.0,
          f"Spalte in {sum(g.D)} von {len(g.D)} Runden, |Kc - Kc^T| {max(g.sym):.1e}")


def test_reibungsfrei_bitgleich():
    print("\n--- Reibungsfrei: bitgleich mit und ohne Schalter ---")
    from tests.test_kontakt_exakt import _block_auf_platte
    for name, bau in (("Block auf Platte, mu 0", lambda: _block_auf_platte(mu=0.0)),
                      ("Blechpaket, mu 0", lambda: blechpaket((0.0,), mu=0.0)[0])):
        us = []
        for rt in (False, True):
            m = bau()
            m.plastizitaet.reibungstangente = rt
            r = solver.solve_static(m)
            us.append(np.asarray(r.u, float))
        check(f"{name}: u bitgleich", np.array_equal(us[0], us[1]),
              f"max|Δu| {float(np.abs(us[0] - us[1]).max()):.1e}")


def main() -> int:
    for t in (test_einstellungen, test_klotz, test_lastgeschichte_dissipation, test_blechpaket,
              test_konvergenzrate, test_symmetrie, test_reibungsfrei_bitgleich):
        try:
            t()
        except Exception as ex:             # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{t.__name__} läuft ohne Ausnahme", False, str(ex)[:120])
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print("\n" + "=" * 60)
    print(f"Ergebnis: {n_ok}/{len(RESULTS)} Prüfungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
