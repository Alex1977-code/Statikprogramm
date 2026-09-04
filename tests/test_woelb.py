"""
Woelbkrafttorsion - gegen geschlossene Loesungen geprueft.

Die Woelbkrafttorsion ist einer der Nachweise, bei denen ein Zahlendreher
nicht auffaellt: das Ergebnis sieht immer plausibel aus. Darum wird hier
nichts mit frueheren Laeufen verglichen, sondern nur mit Werten, die in einer
Zeile nachzurechnen sind:

* **Kragtraeger mit Endtorsionsmoment**, an der Einspannung woelbbehindert:

      B(0)     = -T tanh(lambda L) / lambda
      theta(L) =  T (L - tanh(lambda L)/lambda) /(G I_t)

  Das ist die Loesung aus jedem Lehrbuch; ihr Grenzwert fuer lambda L -> 0 ist
  die reine Woelbkrafttorsion (B = -T L), fuer lambda L -> unendlich die reine
  St.-Venant-Torsion mit einer Randschicht der Laenge 1/lambda.

* **Gleichgewicht**: an jeder Stelle muss M_t,v + M_t,w = M_t sein - nicht
  ungefaehr, sondern auf die Rechengenauigkeit.

* **Gabellagerung an beiden Enden** mit konstantem Torsionsmoment: dann gibt
  es keine Woelbkrafttorsion. M_t,w muss ueberall genau null sein.

* **Woelbordinaten**: aus omega und S_omega zurueckgerechnet muss I_w
  denselben Wert ergeben wie die Querschnittstabelle - zwei ganz verschiedene
  Wege zu derselben Zahl.

* **Spannungen** eines IPE 300 unter einem Bimoment: sigma_w = B omega/I_w,
  von Hand nachgerechnet.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d.ec3 import woelb as W                      # noqa: E402
from statik3d.model import Material, Section             # noqa: E402
from statik3d.profiles import make_section                # noqa: E402

RESULTS = []
E = 210e9
G = 81e9


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FEHLER'} {name:58s} {detail}")
    return bool(ok)


def close(name, got, want, tol, unit=""):
    ok = abs(float(got) - float(want)) <= tol
    abw = abs(got - want) / abs(want) * 100 if want else 0.0
    return check(name, ok, f"{got:.6g}{unit} / {want:.6g}{unit}  Abw. {abw:.6f} %")


def ipe(name="IPE 300") -> Section:
    return make_section(name)


# --------------------------------------------------------------------------
# 1) Kragtraeger mit Endtorsionsmoment
# --------------------------------------------------------------------------
def test_kragtraeger():
    sec = ipe()
    L, T = 4.0, 5.0e3            # 4 m, 5 kNm
    x = np.linspace(0, L, 41)
    Mt = np.full_like(x, T)
    v = W.torsionsverlauf(L, sec.It, sec.Iw, E, G, x, Mt,
                          rand=("behindert", "frei"))
    lam = np.sqrt(G * sec.It / (E * sec.Iw))
    close("lambda aus G I_t /(E I_w)", v.lam, lam, lam * 1e-12, " 1/m")
    soll = -T * np.tanh(lam * L) / lam
    close("Bimoment an der Einspannung B(0) = -T tanh(λL)/λ",
          v.B[0], soll, abs(soll) * 1e-9, " Nm²")
    check("und es ist der größte Wert über die Länge",
          abs(v.B[0]) >= np.abs(v.B).max() - 1e-9, f"{v.B_max:.4g} Nm²")
    close("am freien Ende ist B = 0", v.B[-1], 0.0, abs(soll) * 1e-9, " Nm²")
    check("an der Einspannung läuft alles über Wölbkrafttorsion",
          abs(v.Mtv[0]) < 1e-9 * T, f"M_t,v(0) = {v.Mtv[0]:.3e} Nm")
    check("Gleichgewicht M_t,v + M_t,w = M_t an jeder Stelle",
          float(np.abs(v.Mtv + v.Mtw - Mt).max()) < 1e-9 * T,
          f"größte Abweichung {float(np.abs(v.Mtv + v.Mtw - Mt).max()):.3e} Nm")
    # Verdrehung am Ende: theta(L) = T (L - tanh(λL)/λ)/(G I_t).
    # theta' wird numerisch aufintegriert - ein von der Rechnung unabhaengiger
    # Weg; die Trapezregel braucht dafuer ein feines Raster.
    xf = np.linspace(0, L, 2001)
    vf = W.torsionsverlauf(L, sec.It, sec.Iw, E, G, xf, np.full_like(xf, T),
                           rand=("behindert", "frei"))
    theta = float(np.trapezoid(vf.theta_strich, xf))
    soll_t = T * (L - np.tanh(lam * L) / lam) / (G * sec.It)
    close("Verdrehung θ(L) = T(L − tanh(λL)/λ)/(G I_t)", theta, soll_t,
          abs(soll_t) * 1e-6, " rad")
    starr = T * L / (G * sec.It)
    check("die Wölbbehinderung macht den Träger steifer",
          theta < starr, f"{theta:.5f} rad statt {starr:.5f} rad "
                         f"(ohne Wölbbehinderung), λL = {lam * L:.3f}")


def test_grenzfaelle():
    """lambda L -> 0 und -> unendlich muessen die bekannten Grenzwerte geben."""
    sec = ipe()
    T = 1.0e3
    # (a) sehr kurzer Traeger: lambda L << 1 -> reine Woelbkrafttorsion, B = -T L
    L = 0.02
    x = np.linspace(0, L, 21)
    v = W.torsionsverlauf(L, sec.It, sec.Iw, E, G, x, np.full_like(x, T),
                          rand=("behindert", "frei"))
    close("λL → 0: B(0) → −T L (reine Wölbkrafttorsion)", v.B[0], -T * L,
          abs(T * L) * 1e-3, " Nm²")
    check("und der St.-Venant-Anteil verschwindet",
          v.anteil_woelb > 0.999, f"Wölbanteil {v.anteil_woelb:.5f}")
    # (b) sehr langer Traeger: B(0) -> -T/lambda, weit weg reine St.-Venant-Torsion
    L = 40.0
    x = np.linspace(0, L, 201)
    v = W.torsionsverlauf(L, sec.It, sec.Iw, E, G, x, np.full_like(x, T),
                          rand=("behindert", "frei"))
    lam = v.lam
    close("λL → ∞: B(0) → −T/λ", v.B[0], -T / lam, abs(T / lam) * 1e-6, " Nm²")
    fern = v.Mtv[x > 5 / lam]
    check("fern der Einspannung bleibt nur St.-Venant-Torsion",
          float(np.abs(fern - T).max()) < 1e-2 * T,
          f"M_t,v = {float(fern.min()):.1f} … {float(fern.max()):.1f} Nm von {T:.0f} Nm")
    check("die Randschicht ist rund 1/λ lang",
          abs(v.B[np.argmin(np.abs(x - 3 / lam))]) < 0.06 * abs(v.B[0]),
          f"1/λ = {1 / lam:.3f} m, B(3/λ)/B(0) = "
          f"{abs(v.B[np.argmin(np.abs(x - 3 / lam))] / v.B[0]):.4f}")


def test_gabellagerung():
    """Beide Enden gabelgelagert und konstantes M_t: keine Woelbkrafttorsion."""
    sec = ipe()
    L, T = 6.0, 2.0e3
    x = np.linspace(0, L, 31)
    v = W.torsionsverlauf(L, sec.It, sec.Iw, E, G, x, np.full_like(x, T),
                          rand=("frei", "frei"))
    check("gabelgelagert: M_t,w ist überall genau null",
          float(np.abs(v.Mtw).max()) < 1e-9 * T,
          f"größtes M_t,w = {float(np.abs(v.Mtw).max()):.3e} Nm")
    check("und B ebenfalls", v.B_max < 1e-9 * T * L, f"{v.B_max:.3e} Nm²")
    close("das ganze Moment läuft über St.-Venant", float(v.Mtv.mean()), T,
          T * 1e-9, " Nm")
    # Beide Enden woelbbehindert, konstantes Moment: symmetrischer Verlauf
    v2 = W.torsionsverlauf(L, sec.It, sec.Iw, E, G, x, np.full_like(x, T),
                           rand=("behindert", "behindert"))
    close("beidseits behindert: B ist antimetrisch", v2.B[0], -v2.B[-1],
          abs(v2.B[0]) * 1e-9, " Nm²")
    check("und an beiden Enden trägt nur die Wölbkrafttorsion",
          abs(v2.Mtv[0]) < 1e-9 * T and abs(v2.Mtv[-1]) < 1e-9 * T,
          f"{v2.Mtv[0]:.3e} / {v2.Mtv[-1]:.3e} Nm")


def test_sektorwerte():
    """Aus omega zurueckgerechnetes I_w muss die Querschnittstabelle treffen."""
    for name in ("IPE 300", "HEB 200", "HEA 400"):
        sec = make_section(name)
        sw = W.sektorwerte(sec)
        check(f"{name}: Wölbordinaten vorhanden", sw is not None)
        if sw is None:
            continue
        close(f"{name}: I_w aus ∫ω² t ds gegen die Tabelle",
              sw.Iw_probe, sec.Iw, sec.Iw * 1e-9, " m⁶")
        # omega_max von Hand: h_m b/4
        soll = (sec.h - sec.tf) * sec.b / 4.0
        close(f"{name}: ω_max = h_m b/4", sw.omega_max, soll, soll * 1e-12, " m²")
    for name in ("UPE 200", "UPN 200"):
        sec = make_section(name)
        sw = W.sektorwerte(sec)
        if not check(f"{name}: Wölbordinaten vorhanden", sw is not None):
            continue
        close(f"{name}: I_w aus ∫ω² t ds gegen die Tabelle",
              sw.Iw_probe, sec.Iw, sec.Iw * 1e-6, " m⁶")
    # Geschlossene und andere Querschnitte: keine Woelbordinaten, mit Grund
    rohr = Section.pipe("Rohr", 0.2, 0.008)
    check("Kreisrohr hat keine Wölbordinaten (und keinen Wölbwiderstand)",
          W.sektorwerte(rohr) is None and rohr.Iw == 0.0, f"I_w = {rohr.Iw}")


def test_spannungen():
    """sigma_w = B omega/I_w und tau_w = M_t,w S/(I_w t) - von Hand nachgerechnet."""
    sec = ipe()
    sw = W.sektorwerte(sec)
    B = np.array([12.0e3])           # 12 kNm^2
    Mtw = np.array([3.0e3])
    Mtv = np.array([1.0e3])
    sp = W.spannungen(sec, B, Mtw, Mtv)
    close("σ_w = B ω/I_w", sp["sigma_w"][0], float(B[0]) * sw.omega_max / sec.Iw,
          1.0, " N/m²")
    # Gegenprobe mit der geschlossenen Form 6 B /(t_f b^2 h_m)
    hm = sec.h - sec.tf
    soll = 6.0 * float(B[0]) / (sec.tf * sec.b ** 2 * hm)
    close("und in geschlossener Form 6 B/(t_f b² h_m)", sp["sigma_w"][0], soll,
          abs(soll) * 1e-9, " N/m²")
    close("τ_w = M_t,w S_ω/(I_w t_f)", sp["tau_w"][0],
          float(Mtw[0]) * sw.S_max / (sec.Iw * sec.tf), 1.0, " N/m²")
    soll_t = 1.5 * float(Mtw[0]) / (sec.tf * sec.b * hm)
    close("und in geschlossener Form 1,5 M_t,w/(t_f b h_m)", sp["tau_w"][0],
          soll_t, abs(soll_t) * 1e-9, " N/m²")
    close("τ_t = M_t,v t_max/I_t", sp["tau_t"][0],
          float(Mtv[0]) * sec.t_max / sec.It, 1.0, " N/m²")
    # Kreisrohr: keine Woelbordinaten, aber ein Grund dafuer
    rohr = Section.pipe("Rohr", 0.2, 0.008)
    sp2 = W.spannungen(rohr, B, Mtw, Mtv)
    check("beim Rohr steht der Grund statt einer geratenen Zahl",
          sp2["sigma_w"] is None and "nicht bekannt" in sp2["grund"],
          sp2["grund"])


def test_streckentorsion():
    """Gleichmaessige Streckentorsion: M_t laeuft linear, B bleibt endlich."""
    sec = ipe()
    L, mt = 6.0, 1.0e3               # 1 kNm/m
    x = np.linspace(0, L, 61)
    Mt = mt * (L - x)                # am freien Ende null
    v = W.torsionsverlauf(L, sec.It, sec.Iw, E, G, x, Mt,
                          rand=("behindert", "frei"))
    check("Gleichgewicht auch bei linearem M_t",
          float(np.abs(v.Mtv + v.Mtw - Mt).max()) < 1e-9 * mt * L,
          f"{float(np.abs(v.Mtv + v.Mtw - Mt).max()):.3e} Nm")
    check("an der Einspannung wieder kein St.-Venant-Anteil",
          abs(v.Mtv[0]) < 1e-9 * mt * L, f"{v.Mtv[0]:.3e} Nm")
    close("am freien Ende ist B = 0", v.B[-1], 0.0, mt * L * L * 1e-9, " Nm²")
    # Gegenprobe: die Gesamttorsion muss m_t L sein
    close("eingeleitetes Gesamtmoment", float(Mt[0]), mt * L, 1e-9, " Nm")


def test_nichtlinearer_verlauf():
    """Springt M_t im Feld, muss die Naeherung benannt werden."""
    sec = ipe()
    L = 6.0
    x = np.linspace(0, L, 61)
    Mt = np.where(x < L / 2, 3.0e3, 1.0e3)      # Sprung in Feldmitte
    v = W.torsionsverlauf(L, sec.It, sec.Iw, E, G, x, Mt,
                          rand=("behindert", "frei"))
    check("der Sprung im Torsionsverlauf wird gemeldet",
          "nicht linear" in v.hinweis, v.hinweis[:70])
    glatt = W.torsionsverlauf(L, sec.It, sec.Iw, E, G, x,
                              np.full_like(x, 2.0e3), rand=("behindert", "frei"))
    check("ein linearer Verlauf wird nicht gemeldet", not glatt.hinweis,
          glatt.hinweis or "(kein Hinweis)")


def test_am_ganzen_modell():
    """Kragtraeger mit Endtorsion: der Nachweis muss die Woelbspannung fuehren."""
    from statik3d import solver
    from statik3d.ec3 import design as D
    from statik3d.model import Model

    def bauen(rand):
        m = Model()
        m.add_material(Material.steel("S235"))
        m.add_section(ipe())
        L, n = 4.0, 8
        m.add_nodes(np.column_stack([np.linspace(0, L, n + 1),
                                     np.zeros(n + 1), np.zeros(n + 1)]))
        for i in range(n):
            m.add_element("beam", [i, i + 1], "S235", ipe().name)
        m.fix(0, "all")
        m.load_node(n, Mx=5.0e3, case="LF1")
        mem = m.add_member("S1", list(range(n)))
        mem.woelb_start, mem.woelb_ende = rand
        mem.lt_check = False
        return m, L

    m, L = bauen(("behindert", "frei"))
    an = solver.solve_all(m, design=True)
    mc = an.design.members["S1"]
    check("Wölbkrafttorsion wird im Nachweis geführt", bool(mc.woelb),
          f"{len(mc.woelb)} Einträge")
    w = mc.woelb[0]
    sec = ipe()
    # E und G kommen aus dem Werkstoff des Modells, nicht aus den Konstanten
    # oben - sonst prueft man gegen eine andere Zahl, als gerechnet wurde.
    mat = m.materials["S235"]
    lam = np.sqrt(mat.G * sec.It / (mat.E * sec.Iw))
    soll = 5.0e3 * np.tanh(lam * L) / lam
    close("B_max am ganzen Modell = T tanh(λL)/λ", abs(w["B_max"]), soll,
          soll * 1e-3, " Nm²")
    check("die Wölbnormalspannung steht im maßgebenden Nachweis",
          any("Wölbkrafttorsion" in k or "sigma_v" in k
              for b in mc.section_checks for k in b["checks"]),
          mc.governing.get("name", "-"))

    m2, _ = bauen(("frei", "frei"))
    an2 = solver.solve_all(m2, design=True)
    mc2 = an2.design.members["S1"]
    check("gabelgelagert entsteht kein Bimoment",
          abs(mc2.woelb[0]["B_max"]) < 1e-6 * soll,
          f"{mc2.woelb[0]['B_max']:.3e} Nm²")
    check("und die Wölbbehinderung erhöht die Ausnutzung",
          mc.util > mc2.util,
          f"{mc.util:.3f} (behindert) gegen {mc2.util:.3f} (gabelgelagert)")
    # Gegenprobe von Hand: sigma_w = 6 B/(t_f b^2 h_m) an der Einspannung
    hm = sec.h - sec.tf
    sig = 6.0 * soll / (sec.tf * sec.b ** 2 * hm)
    close("σ_w an der Einspannung von Hand nachgerechnet",
          w["sigma_w_max"], sig, sig * 1e-3, " N/m²")


def main():
    for t in (test_kragtraeger, test_grenzfaelle, test_gabellagerung,
              test_sektorwerte, test_spannungen, test_streckentorsion,
              test_nichtlinearer_verlauf, test_am_ganzen_modell):
        print(f"\n--- {t.__name__} ---")
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
