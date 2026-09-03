"""
Bewegliche Brücken und Stahlwasserbauten: Stellungen des Systems,
Lastfallklassen nach DIN 19704 und die ZTV-ING-Prüfliste.

Aufruf:  python -m tests.test_bridges
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d.model import Model, Material, Section, ACTION_CATEGORIES  # noqa: E402
from statik3d.bridges.positions import (Stellung, Stellungsreihe, drehmatrix,  # noqa: E402
                                        Umhuellende)
from statik3d.bridges.din19704 import (Regelwerk, KLASSEN, EINWIRKUNGEN,  # noqa: E402
                                       bewegungen, pruefliste, KLASSEN_TEXT)

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FAIL'} {name:56s} {detail}")
    return ok


def close(name, got, want, tol, unit=""):
    err = abs(got - want)
    rel = err / abs(want) if want else err
    return check(name, err <= tol * max(1.0, abs(want)),
                 f"{got:.6g}{unit} / {want:.6g}{unit}  Abw. {rel * 100:.3f} %")


def _klappe(L: float = 12.0, n_el: int = 3) -> tuple:
    m = Model("Klappbruecke")
    m.add_material(Material.steel("S355"))
    m.add_section(Section.from_profile("HEB 300"))
    n = [m.add_node(L * i / n_el, 0.0, 0.0) for i in range(n_el + 1)]
    for i in range(n_el):
        m.add_element("beam", [n[i], n[i + 1]], "S355", "HEB 300", group="klappe")
    m.support(n[0], "all", name="Drehlager")
    m.support(n[-1], [2], name="Endauflager")
    m.set_gravity(-9.81)
    m.auto_members()
    return m, n


# --------------------------------------------------------------------------
# 1) Drehung
# --------------------------------------------------------------------------
def test_drehung():
    R = drehmatrix((0, 0, 1), math.radians(90.0))
    v = R @ np.array([1.0, 0.0, 0.0])
    close("Drehung 90 Grad um z: x -> y", float(v[1]), 1.0, 1e-12)
    check("Drehung 90 Grad um z: x-Anteil null", abs(float(v[0])) < 1e-12)
    check("Drehmatrix ist orthogonal",
          np.allclose(R @ R.T, np.eye(3), atol=1e-12))
    close("Determinante = 1", float(np.linalg.det(R)), 1.0, 1e-12)
    check("Achse Null -> Einheitsmatrix",
          np.allclose(drehmatrix((0, 0, 0), 1.0), np.eye(3)))

    m, n = _klappe()
    st = Stellung("S", 90.0, dreh_achse=(0, 1, 0), dreh_punkt=(0, 0, 0),
                  dreh_winkel=-90.0, dreh_gruppen=["klappe"])
    m2 = st.modell(m)
    p_end = m2.nodes[n[-1]]
    close("Klappe 90 Grad: Endknoten steht senkrecht (z)", float(p_end[2]), 12.0, 1e-9, " m")
    check("Klappe 90 Grad: x-Anteil null", abs(float(p_end[0])) < 1e-9,
          f"x = {float(p_end[0]):.3g}")
    close("Drehpunkt bleibt liegen", float(np.linalg.norm(m2.nodes[n[0]])), 0.0, 1e-12)
    check("Grundmodell unveraendert", abs(float(m.nodes[n[-1]][0]) - 12.0) < 1e-12,
          f"x = {float(m.nodes[n[-1]][0])}")


# --------------------------------------------------------------------------
# 2) Stellungen: Lager, Lastfaelle, Antrieb
# --------------------------------------------------------------------------
def test_stellungen():
    m, n = _klappe()
    m.add_load_case("Verkehr", "Q", activate=False)
    m.add_load_case("Wind", "W", activate=False)

    st = Stellung("S2", 40.0, "geöffnet", lager_aus=["Endauflager"])
    m2 = st.modell(m)
    check("Lager abgeschaltet", len(m2.supports) == 1, f"{len(m2.supports)}")
    check("verbleibendes Lager ist das Drehlager",
          m2.supports[0].name == "Drehlager", m2.supports[0].name)

    st2 = Stellung("S3", 0.0, lager_aktiv=["Endauflager"])
    m3 = st2.modell(m)
    check("nur benanntes Lager greift", len(m3.supports) == 1 and
          m3.supports[0].name == "Endauflager", str([s.name for s in m3.supports]))

    st3 = Stellung("S4", 0.0, faelle=["LF1", "Verkehr"])
    m4 = st3.modell(m)
    check("nur die genannten Lastfaelle", sorted(m4.load_cases) == ["LF1", "Verkehr"],
          str(sorted(m4.load_cases)))

    st4 = Stellung("S5", 30.0, antrieb=(n[0], (0.0, 250e3, 0.0)))
    m5 = st4.modell(m)
    check("Antriebslastfall angelegt", "Antrieb S5" in m5.load_cases,
          str([k for k in m5.load_cases if "Antrieb" in k]))
    lc = m5.load_cases["Antrieb S5"]
    close("Antriebsmoment als Knotenlast", float(lc.nodal_loads[0].F[4]), 250e3, 1e-9, " Nm")

    check("Beschriftung nennt Winkel und Text",
          "40" in st.beschriftung() and "geöffnet" in st.beschriftung(),
          st.beschriftung())


# --------------------------------------------------------------------------
# 3) Stellungsreihe rechnen und umhuellen
# --------------------------------------------------------------------------
def test_reihe():
    m, n = _klappe()
    r = Stellungsreihe(m, "Klappbruecke Hafenkanal")
    r.add(Stellung("S1", 0.0, "geschlossen"))
    for w in (20.0, 45.0, 70.0, 82.0):
        r.add(Stellung(f"S{int(w)}", w, f"geöffnet {w:g}°", lager_aus=["Endauflager"],
                       dreh_achse=(0, 1, 0), dreh_punkt=(0, 0, 0), dreh_winkel=-w,
                       dreh_gruppen=["klappe"]))
    check("fuenf Stellungen", len(r) == 5, str(len(r)))
    u = r.rechnen(nachweise=True)
    check("alle Stellungen gerechnet", len(u.ergebnisse) == 5 and not u.fehlerhaft,
          f"{len(u.ergebnisse)} ohne Fehler")

    # geschlossen ist steifer als geoeffnet
    e0 = r.ergebnis("S1")
    e20 = r.ergebnis("S20")
    check("geschlossen verformt sich weniger als geöffnet", e0.u_max < e20.u_max,
          f"{e0.u_max * 1e3:.2f} mm < {e20.u_max * 1e3:.2f} mm")
    # mit steigendem Winkel naehert sich der Kragarm der Schwerkraft an
    reihe = [r.ergebnis(f"S{int(w)}").u_max for w in (20.0, 45.0, 70.0, 82.0)]
    check("Verformung nimmt mit dem Winkel ab",
          all(a > b for a, b in zip(reihe[:-1], reihe[1:])),
          ", ".join(f"{v * 1e3:.1f}" for v in reihe))

    check("Umhüllende nennt die maßgebende Stellung",
          u.massgebende_stellung.startswith("S20"), u.massgebende_stellung)
    close("Umhüllende u_max = größter Einzelwert", u.u_max, max(
        e.u_max for e in u.ergebnisse), 1e-12, " m")
    check("Umhüllende eta > 0", u.eta > 0, f"eta = {u.eta:.3f}")

    k = u.kurve()
    check("Kurve nach Winkel geordnet", [x[0] for x in k] == sorted(x[0] for x in k),
          str([x[0] for x in k]))
    check("Kurve enthaelt alle Stellungen", len(k) == 5, str(len(k)))

    R = u.reaktionen()
    check("Auflagerkräfte je Knoten mit maßgebender Stellung",
          all("Fz" in v for v in R.values()) and R, str(sorted(R)))
    # Gleichgewicht: das Drehlager traegt in der offenen Stellung alles
    e82 = r.ergebnis("S82")
    Fz = float(np.asarray(e82.ergebnis.reactions).reshape(-1, 6)[:, 2].sum())
    G = sum(m.element_length(i) * m.sections["HEB 300"].A * 7850.0 * 9.81
            for i in range(len(m.elements)))
    close("offene Stellung: Summe R_z = Eigengewicht", Fz, G, 1e-3, " N")

    b = u.bericht()
    check("Bericht nennt Stellungen und Umhüllende",
          "Umhüllende" in b and "S20" in b and "Auflagerkräfte" in b)

    # fehlerhafte Stellung wird gemeldet, nicht verschwiegen
    r2 = Stellungsreihe(m)
    r2.add(Stellung("X", 0.0, lager_aus=["Drehlager", "Endauflager"]))
    u2 = r2.rechnen()
    check("Stellung ohne Lager wird als Fehler ausgewiesen",
          len(u2.fehlerhaft) == 1, str(len(u2.fehlerhaft)))
    check("Bericht nennt den Fehler", "Nicht gerechnet" in u2.bericht())

    # Stellungsreihe aus Winkeln
    r3 = Stellungsreihe(m)
    st = r3.aus_winkeln([0, 30, 60, 90], achse=(0, 1, 0), gruppen=["klappe"])
    check("aus_winkeln legt vier Stellungen an", len(st) == 4 and len(r3) == 4)
    check("aus_winkeln setzt Drehwinkel", [s.dreh_winkel for s in st] == [0, 30, 60, 90],
          str([s.dreh_winkel for s in st]))


# --------------------------------------------------------------------------
# 4) DIN 19704: Lastfallklassen und Kombinationen
# --------------------------------------------------------------------------
def test_din19704():
    fehlt = {e for ks in KLASSEN.values() for e in ks} - set(ACTION_CATEGORIES)
    check("alle Einwirkungen sind Einwirkungskategorien", not fehlt, str(sorted(fehlt)))
    check("drei Lastfallklassen", sorted(KLASSEN) == ["LF1", "LF2", "LF3"],
          str(sorted(KLASSEN)))
    check("jede Klasse hat einen Klartext",
          all(k in KLASSEN_TEXT for k in KLASSEN))
    check("außergewöhnliche Einwirkungen nur in LF3",
          "KLEMM" in KLASSEN["LF3"] and "KLEMM" not in KLASSEN["LF1"])

    rw = Regelwerk()
    check("Beiwerte sind zunächst unbestätigt", len(rw.offen()) > 20,
          f"{len(rw.offen())} offen")
    b = rw.bericht()
    check("Bericht kennzeichnet unbestätigte Werte", "zu bestätigen" in b)
    rw.faktor("LF1", "G", 1.35, "DIN 19704-1, geprüft")
    check("gesetzter Wert gilt als bestätigt",
          rw.gamma_F["LF1"]["G"].bestaetigt and
          not any("gamma_F[LF1][G]" == x.split(" =")[0] for x in rw.offen()),
          rw.gamma_F["LF1"]["G"].quelle)
    close("gesetzter Wert wird verwendet", float(rw.gamma_F["LF1"]["G"]), 1.35, 1e-12)

    m, n = _klappe()
    m.load_cases["LF1"].category = "G"
    for nm, kat in (("Ausruestung", "G_A"), ("Verkehr", "Q"), ("Wind", "W"),
                    ("WindBew", "WIND_B"), ("Antrieb", "A_M"), ("Klemmen", "KLEMM")):
        m.add_load_case(nm, kat, activate=False)
    log = []
    k = rw.kombinationen(m, log=log)
    check("Kombinationen angelegt", len(k) >= 8, f"{len(k)}")
    check("Namen mit Präfix DIN", all(x.startswith("DIN LF") for x in k), k[0])
    check("Protokoll nennt die offenen Beiwerte",
          any("bestätigen" in z for z in log))

    lf1 = [x for x in k if x.startswith("DIN LF1")]
    f = m.combinations[lf1[0]].factors
    close("LF1: ständige Einwirkung mit gamma_F", f["LF1"], 1.35, 1e-12)
    check("LF1 enthält keine außergewöhnliche Einwirkung",
          "Klemmen" not in f, str(sorted(f)))
    check("LF1: Leiteinwirkung voll, Begleiteinwirkung mit psi_0",
          any(abs(v - 1.5) < 1e-9 for kk, v in f.items() if kk != "LF1")
          and any(abs(v - 1.5 * 0.6) < 1e-9 for v in f.values()),
          ", ".join(f"{kk}={v:g}" for kk, v in f.items()))
    lf3 = [x for x in k if x.startswith("DIN LF3")]
    check("LF3 vorhanden und enthält das Verklemmen",
          lf3 and any("Klemmen" in m.combinations[x].factors for x in lf3),
          str(lf3))
    f3 = m.combinations[lf3[0]].factors
    close("LF3: ständige Einwirkung mit gamma_F = 1,0", f3["LF1"], 1.0, 1e-12)
    check("Beschreibung nennt die Leiteinwirkung",
          "Leiteinwirkung" in m.combinations[lf1[0]].description,
          m.combinations[lf1[0]].description[:60])

    # nur eine Klasse
    m2, _n = _klappe()
    m2.load_cases["LF1"].category = "G"
    m2.add_load_case("Verkehr", "Q", activate=False)
    k2 = Regelwerk().kombinationen(m2, klassen=["LF2"])
    check("Auswahl der Klasse wirkt", all(x.startswith("DIN LF2") for x in k2), str(k2))


# --------------------------------------------------------------------------
# 5) ZTV-ING-Prüfliste und Lastwechsel
# --------------------------------------------------------------------------
def test_ztv_ing():
    close("Lastwechsel = Bewegungen je Jahr mal Jahre",
          bewegungen(4 * 365, 100), 146000.0, 1e-12)

    m, n = _klappe()
    r = Stellungsreihe(m)
    p = pruefliste(r, m)
    check("Prüfliste liefert Themen", len(p) >= 5, str(len(p)))
    themen = {t for t, _ok, _h in p}
    check("Betriebsstellungen werden geprüft", "Betriebsstellungen" in themen)
    check("wenige Stellungen -> offen",
          not dict((t, ok) for t, ok, _h in p)["Betriebsstellungen"])
    check("Betriebsfestigkeit bleibt offen (nicht ableitbar)",
          not dict((t, ok) for t, ok, _h in p)["Betriebsfestigkeit"])

    r.add(Stellung("S1", 0.0))
    r.add(Stellung("S2", 40.0, lager_aus=["Endauflager"]))
    r.add(Stellung("S3", 82.0, lager_aus=["Endauflager"],
                   antrieb=(n[0], (0.0, 100e3, 0.0))))
    for nm, kat in (("WindBew", "WIND_B"), ("Klemmen", "KLEMM"), ("Grenzmoment", "A_MG")):
        m.add_load_case(nm, kat, activate=False)
    p2 = dict((t, ok) for t, ok, _h in pruefliste(r, m))
    check("drei Stellungen -> erfüllt", p2["Betriebsstellungen"])
    check("Antriebsmoment erkannt", p2["Antriebsmoment"])
    check("Wind während der Bewegung erkannt", p2["Wind während der Bewegung"])
    check("Verklemmen erkannt", p2["Verklemmen"])
    check("Verriegelung erkannt", p2["Verriegelung und Endlagerung"])
    check("mit A_MG kein Hinweis auf das Grenzmoment",
          "Grenzmoment der Kupplung" not in p2, str(sorted(p2)))


def main():
    for t in (test_drehung, test_stellungen, test_reihe, test_din19704, test_ztv_ing):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
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
