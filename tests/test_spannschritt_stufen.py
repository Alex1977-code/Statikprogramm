"""Spannschritt einer Vorspannkraft in Stufen (14.10.2026).

Entscheidung des Anwenders vom 14.10.2026 (woertlich): „Vorspannung als
eigenen, ggf. gestuften Spannschritt vor den äußeren Lasten aufbringen (siehe
kraftgesteuerte Vorspannung).“ Bis dahin wirkte das Kraeftepaar F_soll im
Spannschritt in einem Zug: mit Kontakt ein Kontaktlauf von der Geometrie bis
zur vollen Kraft, mit Fliessen in jeder Laststufe der Plastizitaet die volle
Kraft (F_S = F). Jetzt waechst es in n gleichen Stufen (Plastizitaet.
spannstufen; 0 = automatisch: mit Kontakt oder Fliessen 3, sonst 1), jede vom
Zustand der vorigen aus.

Was hier belegt wird (Modelle aus tests.test_vorspannkraft):

1. Kontakt (Anker und Klemmteil ueber ein Spaltelement): automatisch drei
   Stufen, im Fortschritt „Stufe 1/3“ bis „3/3“; nach dem Verriegeln N = F_soll,
   mit Zuglast das Verspannungsschaubild - und dasselbe u wie in einem Schritt
   (die reibungsfreie Fuge ist vom Weg unabhaengig).
2. Fliessen (Wuerfel mit vier Ankern, er fliesst im Spannschritt): drei
   Stufen; Spannung und Dehnung wie in einem Schritt (einachsig und monoton,
   also wegunabhaengig), nach dem Verriegeln N = F_soll.
3. Linear (reihenweise, ohne Kontakt und Fliessen): ein Schritt.
4. Einstellung am Modell: Vorgabe 0, gespeichert und geladen, in der Maske.
5. Eine vorlaeufige Stufe des Spannschritts macht den Lastfall vorlaeufig.

Aufruf:  python -m tests.test_spannschritt_stufen
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
    tempfile.mkdtemp(prefix="statik3d_spannstufen_"), "einstellungen.json")

from statik3d import solver                                    # noqa: E402
from tests import test_vorspannkraft as tv                     # noqa: E402

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


def rechne(m, lf):
    meld = []
    r = solver.solve_static(m, case=lf, progress=lambda t, *a: meld.append(str(t)))
    return r, meld


def stufen(r):
    return (r.info.get("vorspannung") or {}).get("spannstufen")


def test_kontakt():
    print("\n--- Kontakt: drei Stufen, N = F_soll, wie in einem Schritt ---")
    m, H, el, eK = tv._federn(kontakt=True)
    r, meld = rechne(m, "V")
    st = [z for z in meld if z.startswith("Spannschritt Gruppe 1, Stufe")]
    check("automatisch drei Stufen (Kontakt)", stufen(r) == 3, f"spannstufen {stufen(r)}")
    check("  im Fortschritt Stufe 1/3, 2/3, 3/3 mit dem Anteil von F_soll",
          [z.split(":")[0] for z in st] == [f"Spannschritt Gruppe 1, Stufe {k}/3" for k in (1, 2, 3)]
          and "33,33 % von F_soll" in st[0], str(st))
    sv_ = ((r.info.get("vorspannung") or {}).get("staebe") or {}).get("A1", {})
    nahe("  nach dem Verriegeln N = F_soll", sv_.get("N_verankert", 0.0), tv.F1, 1e-9, "N")
    nahe("  ohne weitere Last N = F_soll", tv._N(r, el["A1"]), tv.F1, 1e-9, "N")
    r2, _m = rechne(m, "VP")
    nahe("  mit Zuglast N = F_soll + k_A/(k_A + k_K)·P", tv._N(r2, el["A1"]),
         tv.F1 + tv.K_A / (tv.K_A + tv.K_K) * tv.P, 1e-9, "N")
    m1, *_r = tv._federn(kontakt=True)
    m1.plastizitaet.spannstufen = 1
    r1, meld1 = rechne(m1, "V")
    du = float(np.abs(np.asarray(r.u) - np.asarray(r1.u)).max())
    um = float(np.abs(np.asarray(r1.u)).max())
    check("  ein Schritt (eingestellt): keine Stufen im Fortschritt, dasselbe u (wegunabhängig)",
          stufen(r1) == 1 and not any("Stufe" in z for z in meld1 if z.startswith("Spannschritt"))
          and du <= 1e-12 * um, f"max |Δu| {du:.2e} von {um:.3e} m")


def test_plastisch():
    print("\n--- Fließen im Spannschritt: drei Stufen wie ein Schritt ---")
    F = 100e6
    ergebnisse = {}
    for n in (0, 1):
        m, kopf, anker = tv._wuerfel((F,) * 4, plast=True, P_kopf=0.0)
        m.plastizitaet.spannstufen = n
        r, meld = rechne(m, "V")
        ergebnisse[n] = (r, meld, anker, kopf)
    r, meld, anker, kopf = ergebnisse[0]
    check("automatisch drei Stufen (Fließen)", stufen(r) == 3, f"spannstufen {stufen(r)}")
    vs = (r.info.get("vorspannung") or {}).get("staebe") or {}
    for k in range(1, 5):
        nahe(f"  A{k}: nach dem Verriegeln N = F_soll", vs.get(f"A{k}", {}).get("N_verankert", 0.0), F, 1e-9, "N")
    sp = ((getattr(r, "vorspannzustaende", None) or {}).get("spannen") or [None])[-1]
    sp1 = ((getattr(ergebnisse[1][0], "vorspannzustaende", None) or {}).get("spannen") or [None])[-1]
    Et = tv.ET * tv.E
    eps = tv.FY / tv.E + (4 * F - tv.FY) / Et
    if sp is not None and sp1 is not None:
        nahe("  Spannzustand: σ_zz = −4F/A", np.asarray(sp.solid_res[0])[2], -4 * F, 1e-8, "Pa")
        nahe("  Spannzustand: Kopf um (f_y/E + (σ − f_y)/E_t)·L gesenkt", np.asarray(sp.u)[kopf, 2].mean(),
             -eps, 1e-8, "m")
        du = float(np.abs(np.asarray(sp.u) - np.asarray(sp1.u)).max())
        check("  wie in einem Schritt (einachsig, monoton): max |Δu| ≤ 1e-8 der Senkung",
              du <= 1e-8 * eps, f"max |Δu| {du:.2e} m bei {eps:.3e} m")
    else:
        check("  Spannzustände abgelegt", False)
    check("  ein Schritt (eingestellt): spannstufen 1", stufen(ergebnisse[1][0]) == 1, str(stufen(ergebnisse[1][0])))


def test_linear():
    print("\n--- Linear, reihenweise: ein Schritt ---")
    m, H, el, eK = tv._federn(anker=(("A1", tv.A_A, tv.F1, 1), ("A2", tv.A_A2, tv.F2, 2)))
    r, meld = rechne(m, "V")
    check("ohne Kontakt und Fließen: eine Stufe, keine Stufen im Fortschritt",
          stufen(r) == 1 and not any(", Stufe " in z for z in meld if z.startswith("Spannschritt")),
          f"spannstufen {stufen(r)}, Weg {(r.info.get('vorspannung') or {}).get('weg')}")
    nahe("  A2 (zuletzt gespannt) behält F_2", tv._N(r, el["A2"]), tv.F2, 1e-9, "N")


def test_einstellung():
    print("\n--- Einstellung am Modell ---")
    from statik3d import vorspannkraft as vk
    from statik3d.model import Model
    from statik3d.plastizitaet import Plastizitaet
    check("Vorgabe 0 (automatisch)", getattr(Plastizitaet(), "spannstufen", None) == 0)
    m = Model("x")
    m.plastizitaet.spannstufen = 5
    m2 = Model.from_dict(m.to_dict())
    check("gespeichert und geladen", getattr(m2.plastizitaet, "spannstufen", None) == 5)
    d = m.to_dict()
    d["plastizitaet"].pop("spannstufen", None)
    check("ältere Datei ohne den Schlüssel: 0", getattr(Model.from_dict(d).plastizitaet, "spannstufen", None) == 0)
    mk, *_r = tv._federn(kontakt=True)
    ml, *_r = tv._federn()
    check("automatisch: Kontakt 3, linear 1; eingestellt gilt",
          getattr(vk, "spannstufen", lambda _m: None)(mk) == 3 and vk.spannstufen(ml) == 1
          and vk.spannstufen(m) == 5, "")
    from tests import test_fehler_p15 as p15
    w, app = p15._fenster()
    if not hasattr(w, "sp_spannstufen"):
        check("Maske Berechnung: Feld „Spannschritt in … Stufen“", False, "kein Feld")
        return
    w.model.plastizitaet.spannstufen = 4
    w._plast_anzeigen()
    check("Maske zeigt den Wert", w.sp_spannstufen.value() == 4, str(w.sp_spannstufen.value()))
    w.sp_spannstufen.setValue(0)
    w._plast_schreiben(w.model.plastizitaet)
    check("… „automatisch“ (0) zurück ins Modell", w.model.plastizitaet.spannstufen == 0
          and w.sp_spannstufen.text() == "automatisch", w.sp_spannstufen.text())


def test_vorlaeufig():
    print("\n--- Eine Spannstufe mit nicht konvergiertem Kontakt macht den Lastfall vorläufig ---")
    m, H, el, eK = tv._federn(kontakt=True)
    aufrufe = []
    alt_sl = solver._solve_loads

    def zaehlen(model, system, factors, name, *a, **k):
        aufrufe.append(name)
        if name == "Spannschritt Gruppe 1, Stufe 1/3":
            res = alt_sl(model, system, factors, name, *a, **k)
            res.info["vorlaeufig"] = {"grund": "kontakt", "text": "vorläufig – Kontakt nicht konvergiert "
                                      "in Kontaktlauf 1", "stellen": ["Kontaktlauf 1"]}
            return res
        return alt_sl(model, system, factors, name, *a, **k)
    solver._solve_loads = zaehlen
    try:
        r, _m = rechne(m, "V")
    finally:
        solver._solve_loads = alt_sl
    sp = ((getattr(r, "vorspannzustaende", None) or {}).get("spannen") or [None])[-1]
    t_sp = ((getattr(sp, "info", None) or {}).get("vorlaeufig") or {}).get("text", "")
    t = (r.info.get("vorlaeufig") or {}).get("text", "")
    check("Spannzustand nennt die Spannstufe 1/3", "Spannstufe 1/3" in t_sp, repr(t_sp))
    check("Lastfall: vorläufig wegen des Spannschritts, auch im Konvergenzstand",
          "Spannschritt" in t and "vorläufig" in solver.konvergenz_zustand(r.info),
          f"{t!r} / {solver.konvergenz_zustand(r.info)}")


def main() -> int:
    for t in (test_kontakt, test_plastisch, test_linear, test_einstellung, test_vorlaeufig):
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
    code = main()
    sys.stdout.flush()
    os._exit(code)
