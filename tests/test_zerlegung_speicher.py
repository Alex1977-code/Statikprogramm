# -*- coding: utf-8 -*-
"""Der Pool macht Platz, bevor eine grosse Zerlegung kommt (Befund B3, 08.10.2026).

Am Drehlager startet das Programm 22 bis 25 Pool-Arbeiter (Bemessung nach dem
Speicher beim Start, als der Hauptprozess erst 2,7 GB hielt). Sie halten die
ganze Rechnung ueber untaetig 36 bis 37 GiB Arbeitssatz und 69 bis 72 GiB
Commit, auch waehrend PARDISO faktorisiert. Bei Mittel blieben vor der ersten
Zerlegung 44 GiB Commit frei, sie braucht rund 45 GiB.

Seither (solver.LinearSolver, parallel.platz_fuer_zerlegung): PARDISO macht erst
die Analyse (Phase 11) und sagt damit den Speicher der Zahlenphase voraus
(iparm 15, 16, 17). Reicht der freie Speicher nicht, schliesst das Programm den
Pool - er geht fuer die Nachlaeufe wieder auf, soweit der Speicher reicht -,
sagt es im Protokoll und faktorisiert erst dann. Reicht es auch ohne Pool nicht,
bricht es mit klarer Meldung ab (SpeicherReichtNicht), statt abzustuerzen.

Geprueft wird mit **gestelltem Speicher**: ``parallel.speicher_frei`` und
``speicher_eigen`` werden ersetzt; der Speicher haengt davon ab, wie viele
Arbeiter offen sind. Die Voraussage selbst ist die echte von PARDISO.

Aufruf:  python -m tests.test_zerlegung_speicher
"""
import contextlib
import io
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import assemble as asm, mesher, parallel, solver     # noqa: E402
from statik3d.model import Material, Model, NodalLoad             # noqa: E402

RESULTS = []
MiB = 2 ** 20

#: Wo es die Ausnahme noch nicht gibt (Gegenprobe ohne die Aenderung), faengt
#: ``except ()`` nichts - die Pruefung meldet dann "keine Ausnahme" statt 
#: mit einem AttributeError abzubrechen.
SpeicherReichtNicht = getattr(solver, "SpeicherReichtNicht", ())
_FEHLT = object()


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FEHLER'} {name:84s} {detail}")
    return bool(ok)


# --------------------------------------------------------------------------
# Modell, Matrix, gestellter Speicher
# --------------------------------------------------------------------------
def wuerfelmodell(n=12) -> Model:
    """Wuerfel aus Tetraedern (n^3 * 5 Elemente, ueber min_elements = 1500),
    unten gehalten, oben eine Last."""
    m = Model()
    m.add_material(Material("S", E=210e9, nu=0.3, rho=7850))
    ids = mesher.grid_box(m, "S", 1.0, 1.0, 1.0, n, n, n, typ="tet4")
    for nd in ids[:, :, 0].ravel():
        m.fix(int(nd), ["ux", "uy", "uz"])
    m.case().nodal_loads.append(NodalLoad(int(ids[-1, -1, -1]), [1.0e5, 0, 0, 0, 0, 0]))
    return m


def steifigkeit(m: Model):
    """Die freie Steifigkeit (CSC) wie StaticSystem sie aufstellt."""
    K = asm.stiffness(m, 1)
    fixed, _vals = asm.constrained_dofs(m, K)
    fi = np.where(~fixed)[0]
    return K[fi][:, fi].tocsc()


def voraussage_kb(K) -> dict:
    """iparm(15), (16), (17) nach der Analysephase - mit pypardiso unmittelbar,
    unabhaengig vom Programmcode."""
    import pypardiso
    solver._find_mkl()
    ps = pypardiso.PyPardisoSolver()
    solver._mkl_cbwr_festhalten(ps)
    Kr = K.tocsr()
    ps._check_A(Kr)
    ps.set_phase(11)
    ps._call_pardiso(Kr, np.zeros((Kr.shape[0], 1)))
    ip = ps.get_iparms()
    ps.free_memory(everything=True)
    return {i: int(ip[i]) for i in (15, 16, 17)}


def noetig_byte(K) -> int:
    """Was das Programm vor der Zahlenphase fordert - ohne die feste Reserve."""
    k = voraussage_kb(K)
    return int(getattr(parallel, "ZERLEGUNG_ZUSCHLAG", 1.15) * k[17] * 1024)


class Maschine:
    """Gestellter Speicher: ``frei_zu`` Byte sind frei (Commit und Arbeitsspeicher
    gleich), wenn kein Pool offen ist; jeder offene Arbeiter nimmt ``je`` Byte."""

    def __init__(self, frei_zu: int, je: int, phys=None):
        self.frei_zu, self.je = int(frei_zu), int(je)
        self.phys = None if phys is None else int(phys)       # Arbeitsspeicher getrennt vom Commit

    def offen(self) -> int:
        n, a = 0, parallel._AKTIV
        while a is not None:
            if a.pool is not None:
                n += a.w
            a = a.vorher
        return n

    def frei(self):
        c = max(1, self.frei_zu - self.offen() * self.je)       # 0 hiesse "keine Auskunft"
        if self.phys is None:
            return c, c
        return max(1, self.phys - self.offen() * self.je), c

    def eigen(self):
        return self.je


@contextlib.contextmanager
def gestellt(frei_zu: int, je: int, phys=None):
    """Speicherabfragen ersetzen; Reserve und Arbeiterzuschlag auf 1/0 gestellt,
    damit die Zahlen des Tests rechnen; die Pruefung greift schon bei kleinen
    Matrizen."""
    mc = Maschine(frei_zu, je, phys)
    setzen = [(parallel, "speicher_frei", mc.frei), (parallel, "speicher_eigen", mc.eigen),
              (parallel, "ZERLEGUNG_RESERVE", 0), (parallel, "ARBEITER_ZUSCHLAG", 1.0),
              (solver, "ZERLEGUNG_PRUEFEN_AB", 0)]
    alt = [(mod, name, getattr(mod, name, _FEHLT)) for mod, name, _ in setzen]
    for mod, name, wert in setzen:
        setattr(mod, name, wert)
    try:
        yield mc
    finally:
        for mod, name, wert in alt:
            if wert is _FEHLT:
                delattr(mod, name)
            else:
                setattr(mod, name, wert)


def _pid(model, idx):
    """Ein Block fuer map_elements: wer hat ihn gerechnet?"""
    return [os.getpid() for _ in idx]


def hinweis(ls) -> str:
    return str(getattr(ls, "speicher_hinweis", ""))


def residuum(K, ls) -> float:
    b = np.ones(K.shape[0])
    x = ls.solve(b)
    return float(np.linalg.norm(K @ x - b) / np.linalg.norm(b))


# --------------------------------------------------------------------------
# 1  Voraussage und Bitgleichheit
# --------------------------------------------------------------------------
def test_voraussage_wird_gelesen():
    m = wuerfelmodell()
    K = steifigkeit(m)
    echt = voraussage_kb(K)
    with gestellt(10 ** 12, 100 * MiB):
        ls = solver.LinearSolver(K)
    v = getattr(ls, "pardiso_voraussage", None) or {}
    check("Voraussage aus der Analysephase: iparm 15, 16, 17 stehen am Loeser",
          bool(v) and v.get("iparm15_kb", 0) > 0 and v.get("iparm16_kb", 0) > 0 and v.get("iparm17_kb", 0) > 0,
          str(v)[:80])
    check("… dieselben Zahlen, die PARDISO nach Phase 11 liefert",
          v.get("iparm15_kb") == echt[15] and v.get("iparm16_kb") == echt[16] and v.get("iparm17_kb") == echt[17],
          f"{echt}")
    check("… Spitze = max(iparm 15; 16 + 17)",
          v.get("spitze_kb") == max(echt[15], echt[16] + echt[17]), str(v.get("spitze_kb")))


def test_bitgleich_wie_heute():
    """Analyse und Zahlenphase getrennt (11, dann 22) rechnet dasselbe wie Phase 12."""
    import pypardiso
    m = wuerfelmodell()
    K = steifigkeit(m)
    solver._find_mkl()
    ps = pypardiso.PyPardisoSolver()
    solver._mkl_cbwr_festhalten(ps)
    solver._mkl_threads_setzen(ps, solver.threads_vorgabe("pardiso"))
    Kr = K.tocsr()
    ps.factorize(Kr)
    rng = np.random.default_rng(7)
    b = rng.standard_normal(K.shape[0])
    x_alt = ps.solve(Kr, b)
    ip_alt = {i: int(ps.get_iparms()[i]) for i in (14, 15, 16)}
    ps.free_memory(everything=True)
    with gestellt(10 ** 12, 100 * MiB):
        ls = solver.LinearSolver(K)
    x_neu = ls.solve(b)
    check("getrennte Phasen 11 und 22 geben bitgleich dieselbe Loesung wie Phase 12",
          np.array_equal(x_alt, x_neu), f"groesste Abweichung {float(np.abs(x_alt - x_neu).max()):.1e}")
    check("… dieselben gestoerten Pivots und derselbe Speicher der Analyse",
          ls.gestoerte_pivots == ip_alt[14]
          and ls.pardiso_kennzahlen["speicher_kb"]["15"] == ip_alt[15]
          and ls.pardiso_kennzahlen["speicher_kb"]["16"] == ip_alt[16], str(ip_alt))
    check("… und der Loeser meldet PARDISO", ls.backend == "pardiso", ls.backend)


def test_kleine_matrix_wird_nicht_angefasst():
    """Unter der Schwelle (ZERLEGUNG_PRUEFEN_AB) bleibt es bei Phase 12."""
    m = wuerfelmodell()
    K = steifigkeit(m)
    ls = solver.LinearSolver(K)           # Vorgabeschwelle, kein gestellter Speicher
    check("unter der Schwelle: keine Voraussage, kein Hinweis, PARDISO rechnet",
          not getattr(ls, "pardiso_voraussage", {}) and hinweis(ls) == ""
          and ls.backend == "pardiso" and residuum(K, ls) < 1e-8,
          f"{K.nnz / 1e6:.2f} Mio. Eintraege, Schwelle {getattr(solver, 'ZERLEGUNG_PRUEFEN_AB', '-')}")


# --------------------------------------------------------------------------
# 2  Der Pool macht Platz
# --------------------------------------------------------------------------
def test_pool_wird_vor_der_zerlegung_geschlossen_und_kommt_zurueck():
    m = wuerfelmodell()
    K = steifigkeit(m)
    noetig = noetig_byte(K)
    PW = 100 * MiB
    idx = list(range(len(m.elements)))
    # Der Pool startet unter gestelltem Speicher: der Hauptprozess haelt beim Start PW,
    # und es ist reichlich frei - danach wird der freie Speicher knapp gestellt
    with gestellt(10 ** 12, PW) as mc, parallel.arbeiter(m, workers=5) as a:
        if not check("Vorbedingung: ein Pool mit 5 Arbeitern ist offen", a.pool is not None and a.w == 5,
                     f"w {a.w}, Pool {a.pool}"):
            return
        # 4,5 Arbeiter Platz ueber dem Bedarf: mit 5 offenen fehlt es, ohne Pool reicht es,
        # und fuer die Nachlaeufe passen danach zwei Arbeiter wieder hinein
        mc.frei_zu = noetig + int(4.5 * PW)
        frei_offen = mc.frei()[1]
        check("Vorbedingung: mit dem offenen Pool ist weniger frei, als die Zerlegung braucht",
              frei_offen < noetig, f"frei {frei_offen / MiB:.0f} MiB, noetig {noetig / MiB:.1f} MiB")
        fehler = io.StringIO()
        with contextlib.redirect_stderr(fehler):
            ls = solver.LinearSolver(K)
        check("der Pool ist vor der Zerlegung geschlossen", a.pool is None and mc.offen() == 0,
              f"Pool {a.pool}")
        check("das Protokoll sagt es: 5 Arbeiter, geschlossen, die Zahlen",
              "5 Arbeiter" in hinweis(ls) and "geschlossen" in hinweis(ls) and "Frei waren" in hinweis(ls),
              hinweis(ls)[:110])
        check("… auch auf der Konsole", "[parallel]" in fehler.getvalue() and "geschlossen" in fehler.getvalue(),
              fehler.getvalue().strip()[:60])
        check("die Zerlegung ist richtig (Residuum klein), PARDISO",
              ls.backend == "pardiso" and residuum(K, ls) < 1e-8)
        with contextlib.redirect_stderr(io.StringIO()):
            r = parallel.map_elements(_pid, m, idx)
        check("fuer den Nachlauf geht der Pool wieder auf, mit zwei Arbeitern",
              a.pool is not None and a.w == 2 and any(p != os.getpid() for p in r),
              f"w {a.w}, Prozesse {len(set(r))}")
        # Pool wieder offen (2 Arbeiter): die naechste Zerlegung hat Platz, ein Hinweis kommt nicht
        with contextlib.redirect_stderr(io.StringIO()):
            ls_b = solver.LinearSolver(K)
        check("die naechste Zerlegung findet Platz: der Pool bleibt, kein neuer Hinweis",
              a.pool is not None and hinweis(ls_b) == "", f"w {a.w}, Hinweis '{hinweis(ls_b)}'")
    # Pool zu, und fuer die Nachlaeufe passt nur ein Arbeiter in den Rest: bleibt zu, rechnet seriell
    with gestellt(10 ** 12, PW) as mc, parallel.arbeiter(m, workers=5) as a:
        mc.frei_zu = noetig + int(2.5 * PW)
        with contextlib.redirect_stderr(io.StringIO()):
            ls2 = solver.LinearSolver(K)
            r2 = parallel.map_elements(_pid, m, idx)
        check("passt nur ein Arbeiter in den Rest, bleibt der Pool zu und der Nachlauf laeuft seriell",
              a.pool is None and set(r2) == {os.getpid()} and "geschlossen" in hinweis(ls2),
              f"Pool {a.pool}, Prozesse {len(set(r2))}")
    # ohne gestellten Speicher: der Pool oeffnet beim naechsten Block wieder normal
    with parallel.arbeiter(m, workers=2) as a:
        check("ein neuer Block danach startet seinen Pool wie immer", a.pool is not None and a.w == 2)


def test_genug_speicher_bleibt_alles_wie_heute():
    m = wuerfelmodell()
    K = steifigkeit(m)
    noetig = noetig_byte(K)
    PW = 100 * MiB
    with gestellt(10 ** 12, PW) as mc, parallel.arbeiter(m, workers=5) as a:
        mc.frei_zu = noetig + 9 * PW            # mit 5 offenen Arbeitern bleiben noetig + 4 PW frei
        pool0, w0 = a.pool, a.w
        fehler = io.StringIO()
        with contextlib.redirect_stderr(fehler):
            ls = solver.LinearSolver(K)
        check("genug Speicher: derselbe Pool, dieselbe Arbeiterzahl, kein Hinweis",
              a.pool is pool0 and a.w == w0 == 5 and hinweis(ls) == "" and fehler.getvalue() == "",
              f"w {a.w}, Hinweis '{hinweis(ls)}'")
        r = parallel.map_elements(_pid, m, list(range(len(m.elements))))
        check("… und der Nachlauf nimmt weiter den Pool", any(p != os.getpid() for p in r))
        check("… die Voraussage ist trotzdem festgehalten",
              bool((getattr(ls, "pardiso_voraussage", None) or {}).get("iparm17_kb")))
        # die ganze Rechnung: alter Weg (Phase 12, unter der Schwelle, seriell) gegen neuen (geteilt, im Pool)
    ref = solver.solve_static(m, workers=1)
    with gestellt(10 ** 12, PW) as mc, parallel.arbeiter(m, workers=5) as a:
        mc.frei_zu = noetig + 9 * PW
        pool0 = a.pool
        zeilen = []
        res = solver.solve_static(m, progress=lambda t, x=None: zeilen.append(str(t)))
        check("genug Speicher, ganze Rechnung: Verschiebungen bitgleich mit dem alten Weg, Pool unveraendert, "
              "keine Zeile zum Pool",
              np.array_equal(np.asarray(res.u), np.asarray(ref.u)) and a.pool is pool0
              and not any("Pool" in z for z in zeilen),
              f"groesste Abweichung {float(np.abs(np.asarray(res.u) - np.asarray(ref.u)).max()):.1e}")
    # ohne Pool (kleines Modell, eine Kette …) und genug Speicher: nichts zu tun
    with gestellt(noetig + 9 * PW, PW):
        ls = solver.LinearSolver(K)
        check("ohne Pool und genug Speicher: Zerlegung wie immer, kein Hinweis",
              hinweis(ls) == "" and ls.backend == "pardiso" and residuum(K, ls) < 1e-8)


def test_zu_wenig_speicher_auch_ohne_pool_meldet_klar():
    m = wuerfelmodell()
    K = steifigkeit(m)
    noetig = noetig_byte(K)
    PW = 100 * MiB
    knapp = max(1, noetig // 2)
    for be in ("auto", "pardiso"):
        with gestellt(10 ** 12, PW) as mc, parallel.arbeiter(m, workers=5) as a:
            mc.frei_zu = knapp
            try:
                with contextlib.redirect_stderr(io.StringIO()):
                    ls = solver.LinearSolver(K, backend=be)
                check(f"zu wenig auch ohne Pool ({be}): Abbruch mit Meldung", False,
                      f"keine Ausnahme, Loeser {ls.backend}")
            except SpeicherReichtNicht as ex:
                t = str(ex)
                check(f"zu wenig auch ohne Pool ({be}): Abbruch mit Meldung statt Absturz",
                      "Speicher" in t and "MiB" in t and "5 Arbeiter" in t and "geschlossen" in t,
                      t[:150])
                check(f"… keine RuntimeError ({be}): die hiesse 'Lagerung pruefen'",
                      not isinstance(ex, (RuntimeError, ValueError)) and isinstance(ex, solver.LoeserAusfall))
                check(f"… der Pool ist dabei zu ({be}): der Speicher war frei zu machen", a.pool is None)
            except Exception as ex:                       # noqa: BLE001
                check(f"zu wenig auch ohne Pool ({be}): Abbruch mit Meldung", False,
                      f"{type(ex).__name__}: {ex}"[:110])
    # kein Pool offen: dieselbe Meldung, ohne Rede vom Pool
    with gestellt(knapp, PW):
        try:
            solver.LinearSolver(K)
            check("zu wenig ohne Pool und ohne offenen Block: Abbruch mit Meldung", False, "keine Ausnahme")
        except SpeicherReichtNicht as ex:
            check("zu wenig ohne offenen Block: Abbruch mit Meldung, ohne vom Pool zu reden",
                  "Speicher" in str(ex) and "Rechenpools" not in str(ex), str(ex)[:110])
        except Exception as ex:                           # noqa: BLE001
            check("zu wenig ohne offenen Block: Abbruch mit Meldung", False, f"{type(ex).__name__}: {ex}"[:110])


def test_nur_der_arbeitsspeicher_knapp_warnt_und_rechnet():
    """Reicht der Commit-Speicher, der Arbeitsspeicher aber nicht, lagert Windows aus: langsam,
    aber ohne Absturz. Dann wird gewarnt und gerechnet (unter Windows; sonst ist der
    Arbeitsspeicher die harte Grenze)."""
    import platform
    if platform.system() != "Windows":
        return
    m = wuerfelmodell()
    K = steifigkeit(m)
    noetig = noetig_byte(K)
    with gestellt(10 ** 12, 100 * MiB, phys=max(1, noetig // 2)):
        ls = solver.LinearSolver(K)
    check("Commit reicht, Arbeitsspeicher nicht: Warnung im Hinweis und die Zerlegung laeuft",
          "Achtung" in hinweis(ls) and "Arbeitsspeicher" in hinweis(ls) and "lagert aus" in hinweis(ls)
          and ls.backend == "pardiso" and residuum(K, ls) < 1e-8, hinweis(ls)[:100])


def test_rechnung_ganz_durch_protokoll_und_abbruch():
    """Im ganzen Rechenweg (solve_static): das Protokoll bekommt die Zeile, das
    Ergebnis bleibt bitgleich; zu wenig Speicher kommt als diese Meldung heraus
    und nicht als 'Gleichungssystem singulaer'."""
    m = wuerfelmodell()
    K = steifigkeit(m)
    noetig = noetig_byte(K)
    PW = 100 * MiB
    ref = solver.solve_static(m, workers=1)
    import pypardiso
    fertig = [False]                       # ist die Zahlenphase (Phase 22) schon durch?
    echt_call = pypardiso.PyPardisoSolver._call_pardiso

    def beobachtet(self, A, b):
        r = echt_call(self, A, b)
        if self.phase == 22:
            fertig[0] = True
        return r

    zeilen = []                            # (Text, Zerlegung schon fertig?)
    pypardiso.PyPardisoSolver._call_pardiso = beobachtet
    try:
        with gestellt(10 ** 12, PW) as mc, parallel.arbeiter(m, workers=5):
            mc.frei_zu = noetig + int(4.5 * PW)
            with contextlib.redirect_stderr(io.StringIO()):
                res = solver.solve_static(m, progress=lambda t, a=None: zeilen.append((str(t), fertig[0])))
        check("Protokoll der Rechnung nennt das Schliessen des Pools, genau einmal",
              sum(1 for z, _ in zeilen if "Arbeiter" in z and "geschlossen" in z) == 1,
              next((z for z, _ in zeilen if "geschlossen" in z), "keine Zeile")[:100])
        check("… und zwar **vor** der Zerlegung, nicht erst danach (sie kann Minuten dauern)",
              any("geschlossen" in z and not f for z, f in zeilen), str([f for z, f in zeilen if "geschlossen" in z]))

        class AbbruchProbe(Exception):
            """Wie gui.worker.Abgebrochen: der Fortschrittsaufruf wirft."""

        def abbrechend(t, a=None):
            if "geschlossen" in str(t):                  # der Abbruch bleibt gesetzt (wie im Worker)
                raise AbbruchProbe("Abbruch beim Hinweis")

        fertig[0] = False
        spaeter = []
        with gestellt(10 ** 12, PW) as mc, parallel.arbeiter(m, workers=5):
            mc.frei_zu = noetig + int(4.5 * PW)
            try:
                with contextlib.redirect_stderr(io.StringIO()):
                    solver.solve_static(m, progress=lambda t, a=None: (abbrechend(t), spaeter.append(str(t))))
                check("ein Abbruch beim Hinweis: die Rechnung bricht ab", False, "lief durch")
            except AbbruchProbe:
                check("ein Abbruch beim Hinweis reisst die Zerlegung nicht in den Ausweichweg: "
                      "er kommt als Abbruch an, ohne 'ausgewichen'",
                      not any("ausgewichen" in z for z in spaeter), str(spaeter)[:80])
            except Exception as ex:                           # noqa: BLE001
                check("ein Abbruch beim Hinweis kommt als Abbruch an", False, f"{type(ex).__name__}: {ex}"[:100])
    finally:
        pypardiso.PyPardisoSolver._call_pardiso = echt_call
    check("das Ergebnis ist bitgleich mit dem ohne gestellten Speicher",
          np.array_equal(np.asarray(res.u), np.asarray(ref.u)),
          f"groesste Abweichung {float(np.abs(np.asarray(res.u) - np.asarray(ref.u)).max()):.1e}")
    with gestellt(10 ** 12, PW) as mc, parallel.arbeiter(m, workers=5):
        mc.frei_zu = max(1, noetig // 2)
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                solver.solve_static(m)
            check("zu wenig Speicher in solve_static: klare Meldung", False, "keine Ausnahme")
        except SpeicherReichtNicht as ex:
            t = str(ex)
            check("zu wenig Speicher in solve_static: klare Meldung, nicht 'singulaer'",
                  "singul" not in t.lower() and "Speicher" in t, t[:110])
        except Exception as ex:                               # noqa: BLE001
            check("zu wenig Speicher in solve_static: klare Meldung", False,
                  f"{type(ex).__name__}: {str(ex)[:100]}")


def main():
    for t in (test_voraussage_wird_gelesen, test_bitgleich_wie_heute, test_kleine_matrix_wird_nicht_angefasst,
              test_pool_wird_vor_der_zerlegung_geschlossen_und_kommt_zurueck,
              test_genug_speicher_bleibt_alles_wie_heute,
              test_zu_wenig_speicher_auch_ohne_pool_meldet_klar,
              test_nur_der_arbeitsspeicher_knapp_warnt_und_rechnet,
              test_rechnung_ganz_durch_protokoll_und_abbruch):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:                               # noqa: BLE001
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
