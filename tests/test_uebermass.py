"""
Übermaß als Lastfall: Presspassung, Pressspannung, Schub über die Reibung.

Ein Passstift hält sein Bauteil nicht, weil er im Loch steckt, sondern weil
er zu dick dafür ist: das Übermaß erzeugt eine Pressspannung, und über den
Reibbeiwert der Fuge trägt sie Schub. Genau das wird hier nachgerechnet -
gegen geschlossene Werte, nicht gegen „ungefähr":

* **Ebene Fuge.** Zwei Würfel übereinander, unten und oben in z gehalten, die
  Fuge dazwischen mit einem Übermaß δ. Jeder Würfel ist eine Feder E·A/L; in
  Reihe geschaltet nehmen beide zusammen δ auf, und die Pressspannung ist
  σ = δ·E/(2·L). Der lineare Sechsflächner bildet diesen gleichförmigen
  Dehnungszustand exakt ab - übrig bleibt nur, dass die Kontaktfeder eine
  endliche Steifigkeit hat und den Spalt nicht ganz auf null drückt.
* **Zylindrische Fuge.** Angegeben wird die Gesamtüberdeckung, also das
  Übermaß am **Durchmesser**; radial schließt die Fuge davon die Hälfte. Das
  lässt sich ohne Kesselformel prüfen: dasselbe Modell mit einem Übermaß von
  40 µm muss auf dieselbe Stelle kommen wie eines mit einem Anfangsspalt von
  20 µm - und ein Anfangsspalt von 40 µm auf das Doppelte.
* **Schub über die Reibung.** Mit Presspassung und µ trägt die Fuge eine
  Querlast unterhalb µ·N vollständig: die Auflagerkraft ist die Querlast, und
  kein Knoten gleitet. Ohne Presspassung hält nichts - dann sagt die
  Singularitätenanzeige, dass genau diese Querlast ins Nichts geht.
* **Kombination.** Das Übermaß geht mit dem Beiwert seines Lastfalls ein wie
  jede andere Last.

Aufruf:  python -m tests.test_uebermass
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import solver                                       # noqa: E402
from statik3d.model import (Combination, ContactPair, Material,   # noqa: E402
                            Model, Uebermass)

RESULTS = []

E_STAHL = 210e9          # N/m^2
L_WUERFEL = 1.0          # m
A_FUGE = 1.0             # m^2
UEBER = 1.0e-4           # m   - 100 µm Gesamtüberdeckung der ebenen Fuge
MU = 0.3


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FEHLER'} {name:62s} {detail}")
    return bool(ok)


def close(name, got, want, tol, unit=""):
    ok = abs(float(got) - float(want)) <= tol
    abw = abs(got - want) / abs(want) * 100 if want else 0.0
    return check(name, ok, f"{got:.8g}{unit} / {want:.8g}{unit}  Abw. {abw:.5f} %")


# --------------------------------------------------------------------------
# Ebene Fuge: zwei Würfel übereinander
# --------------------------------------------------------------------------
def zwei_wuerfel(mu: float = 0.0, ueber: float = 0.0, quer: float = 0.0,
                 oben_gehalten: bool = False, faktor: float = 0.0) -> Model:
    """Zwei Einheitswürfel, Fuge in der Mitte, beide Deckel in z gehalten.

    Gehalten wird nur, was gehalten werden muss: die Deckel in z, dazu drei
    Verschiebungen gegen das Wegdriften. Eine volle Einspannung würde die
    Querdehnung behindern und die Fuge um Prozente steifer machen - dann wäre
    σ = δ·E/(2·L) nicht mehr der richtige Wert, sondern nur ein Näherungswert.

    Die Gegenseite ist **eine** ausdrückliche Facette. Nähme man den Würfel
    als Master, lägen die Fugenknoten zugleich auf den Kanten seiner vier
    Seitenflächen: welche davon die Fuge ist, wäre nicht mehr entscheidbar.
    """
    m = Model()
    m.add_material(Material.steel("S235"))
    U = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                  [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1.]])
    m.add_nodes(np.vstack([U, U + np.array([0, 0, 1.0])]))
    m.add_element("hex8", list(range(8)), "S235", group="Unten")
    m.add_element("hex8", list(range(8, 16)), "S235", group="Oben")
    for k in range(4):
        m.fix(k, [2])
    m.fix(0, [0, 1])
    m.fix(1, [1])
    for k in (12, 13, 14, 15):
        m.fix(k, [2])
    if oben_gehalten:
        m.fix(12, [0, 1])
        m.fix(13, [1])
    m.contact_pairs.append(ContactPair("Fuge", slave_nodes=[8, 9, 10, 11],
                                       master_faces=[[4, 5, 6, 7]], mu=mu,
                                       search_radius=0.5))
    lc = m.add_load_case("LF1")
    lc.gravity = [0, 0, 0]
    if ueber:
        lc.uebermasse.append(Uebermass("Fuge", ueber, passmass="ebene Fuge"))
    for k in (12, 13, 14, 15):
        if quer:
            m.load_node(k, Fx=quer / 4)
    if faktor:
        m.combinations["KO"] = Combination("KO", {"LF1": faktor})
    return m


def test_ebene_fuge():
    soll = UEBER * E_STAHL / (2 * L_WUERFEL)
    r = solver.solve_static(zwei_wuerfel(ueber=UEBER, oben_gehalten=True), case="LF1")
    close("ebene Fuge: Pressspannung sigma = delta·E/(2·L)",
          -r.solid_res[0][2], soll, 1e-4 * soll, " N/m²")
    close("und die Auflagerkraft ist sigma mal der Fugenfläche",
          r.reactions[:4, 2].sum(), soll * A_FUGE, 1e-4 * soll, " N")
    check("das Protokoll nennt die erkannte Fugenform",
          any("eben" in z and "Übermaß" in z for z in r.info.get("contact_log", [])),
          "; ".join(z for z in r.info.get("contact_log", []) if "Übermaß" in z))
    ohne = solver.solve_static(zwei_wuerfel(oben_gehalten=True), case="LF1")
    check("ohne Übermaß bleibt die Fuge kraftlos",
          abs(float(ohne.reactions[:4, 2].sum())) < 1e-6,
          f"{float(ohne.reactions[:4, 2].sum()):g} N")


def test_kombination_skaliert():
    """Das Übermaß geht mit dem Beiwert seines Lastfalls ein."""
    m = zwei_wuerfel(ueber=UEBER, oben_gehalten=True, faktor=2.0)
    r1 = solver.solve_static(m, case="LF1")
    r2 = solver.solve_combination(m, m.combinations["KO"])
    close("Kombination mit 2,0: die doppelte Pressspannung",
          -r2.solid_res[0][2], -2.0 * r1.solid_res[0][2],
          1e-6 * abs(r1.solid_res[0][2]), " N/m²")


# --------------------------------------------------------------------------
# Zylindrische Fuge: Passstift in der Nabe
# --------------------------------------------------------------------------
def _rohr(m: Model, r_i: float, r_a: float, gruppe: str, N: int = 8) -> tuple:
    """Ein N-Eck-Rohr aus Sechsflächnern; (Innenknoten, Außenknoten) je Ebene."""
    w = np.arange(N) * 2 * np.pi / N
    innen, aussen = [], []
    for z in (0.0, 1.0):
        innen.append([m.add_node(r_i * np.cos(a), r_i * np.sin(a), z) for a in w])
        aussen.append([m.add_node(r_a * np.cos(a), r_a * np.sin(a), z) for a in w])
    for i in range(N):
        j = (i + 1) % N
        m.add_element("hex8", [innen[0][i], aussen[0][i], aussen[0][j], innen[0][j],
                               innen[1][i], aussen[1][i], aussen[1][j], innen[1][j]],
                      "S235", group=gruppe)
    return innen, aussen


def passung(ueber: float = 0.0, spalt: float = 0.0) -> Model:
    """Ein Passstift (Rohr 10…20 mm) in einer Nabe (Rohr 20…40 mm)."""
    m = Model()
    m.add_material(Material.steel("S235"))
    s_i, s_a = _rohr(m, 0.010, 0.020, "Stift")
    n_i, n_a = _rohr(m, 0.020, 0.040, "Nabe")
    N = len(n_i[0])
    faces = [[n_i[0][i], n_i[1][i], n_i[1][(i + 1) % N], n_i[0][(i + 1) % N]]
             for i in range(N)]
    m.contact_pairs.append(ContactPair(
        "Passung", slave_nodes=sorted(set(s_a[0] + s_a[1])), master_faces=faces,
        search_radius=0.005, gap=spalt))
    for k in n_a[0] + n_a[1]:
        m.fix(k, [0, 1, 2])
    for k in s_i[0] + s_i[1]:
        m.fix(k, [2])
    lc = m.add_load_case("LF1")
    lc.gravity = [0, 0, 0]
    if ueber:
        lc.uebermasse.append(Uebermass("Passung", ueber, passmass="Ø40 H7/s6"))
    return m


def test_zylindrische_fuge():
    d = 4.0e-5                       # 40 µm am Durchmesser
    r = solver.solve_static(passung(ueber=d), case="LF1")
    check("zylindrische Fuge wird als solche erkannt",
          any("zylindrisch" in z for z in r.info.get("contact_log", [])),
          "; ".join(z for z in r.info.get("contact_log", []) if "Übermaß" in z))
    # Radial schliesst die Fuge die Haelfte - nachgewiesen ohne Kesselformel:
    # dasselbe Modell mit einem Anfangsspalt dieser halben Groesse.
    halb = solver.solve_static(passung(spalt=0.5 * d), case="LF1")
    ganz = solver.solve_static(passung(spalt=d), case="LF1")
    u, uh, ug = (float(np.abs(x.u[:, :3]).max()) for x in (r, halb, ganz))
    close("40 µm am Durchmesser wirken wie 20 µm Spaltschluss", u, uh, 1e-12 * uh, " m")
    close("und 40 µm Spaltschluss geben das Doppelte", ug, 2.0 * uh, 1e-9 * uh, " m")
    check("ohne Übermaß bleibt die Passung kraftlos",
          float(np.abs(solver.solve_static(passung(), case="LF1").u).max()) == 0.0)


# --------------------------------------------------------------------------
# Schubtragfähigkeit aus Presspassung und Reibung
# --------------------------------------------------------------------------
def test_schub_ueber_die_reibung():
    N = UEBER * E_STAHL / (2 * L_WUERFEL) * A_FUGE      # Presskraft
    T = 0.4 * MU * N                                    # sicher unter mu·N
    r = solver.solve_static(zwei_wuerfel(mu=MU, ueber=UEBER, quer=T), case="LF1")
    close("Presspassung mit Reibung trägt die Querlast ganz",
          -r.reactions[:4, 0].sum(), T, 1e-6 * T, " N")
    check("und kein Knoten der Fuge gleitet dabei",
          set(c.get("status") for c in r.contact) == {"Haften"},
          str(sorted({c.get("status") for c in r.contact})))
    check("die Schubtragfähigkeit mu·N ist größer als die Querlast",
          MU * N > T, f"mu·N = {MU * N / 1e3:.0f} kN gegen T = {T / 1e3:.0f} kN")

    # Ohne Presspassung hält in der Fugenebene nichts - und das Programm sagt
    # es mit der Kraft, die dabei ins Nichts geht.
    frei = solver.solve_static(zwei_wuerfel(quer=T), case="LF1")
    laengs = [x for x in frei.singular if x.verschiebung() and abs(x.t[0]) > 0.99]
    check("ohne Presspassung gleitet das Bauteil in Lastrichtung",
          len(laengs) == 1, str([x.text for x in frei.singular]))
    close("und genau die Querlast geht ins Nichts",
          laengs[0].kraft if laengs else 0.0, T, 1e-6 * T, " N")


def test_passung_aus_abmassen():
    """Aus den vier Abmaßen der Zeichnung wird die Überdeckung.

    Gerechnet an Ø40 H7/s6: Bohrung H7 = +25/0 µm, Welle s6 = +59/+43 µm.
    Höchstübermaß es − EI = 59 µm, Mindestübermaß ei − ES = 43 − 25 = 18 µm,
    im Mittel 38,5 µm. Die Abmaße stammen aus der Passungstabelle der
    Zeichnung - das Programm bringt keine eigene mit (siehe passungen.py).
    """
    from statik3d import passungen as pss
    es, ei, ES, EI = 59e-6, 43e-6, 25e-6, 0.0
    hoechst, mittel, mindest = pss.uebermasse(es, ei, ES, EI)
    close("Höchstübermaß es − EI", hoechst * 1e6, 59.0, 1e-9, " µm")
    close("Mindestübermaß ei − ES", mindest * 1e6, 18.0, 1e-9, " µm")
    close("mittleres Übermaß", mittel * 1e6, 38.5, 1e-9, " µm")
    close("und der Ansatz wählt aus", pss.uebermass(es, ei, ES, EI, "mindest") * 1e6,
          18.0, 1e-9, " µm")
    t = pss.text(es, ei, ES, EI, 0.040, "H7/s6")
    check("der Beleg nennt Nennmaß, Abmaße und die Spanne",
          "Ø40" in t and "H7/s6" in t and "+18" in t and "+59" in t, t)
    # Spiel statt Uebermass: Bohrung H7, Welle f7 (es = -25, ei = -50 µm)
    _h, _m, mind = pss.uebermasse(-25e-6, -50e-6, 25e-6, 0.0)
    check("eine Spielpassung kommt negativ heraus", mind < 0,
          f"{mind * 1e6:g} µm")


def test_datenmodell():
    m = zwei_wuerfel(ueber=UEBER)
    u = m.case("LF1").uebermasse[0]
    check("Übermaß nennt Fuge und Größe", "Fuge" in u.bezug() and "100" in u.bezug(),
          u.bezug())
    check("es steht als eigene Lastart im Lastfall",
          "uebermass" in m.case("LF1").lasten_je_art(),
          str(list(m.case("LF1").lasten_je_art())))
    d = m.to_dict()
    m2 = Model.from_dict(d)
    u2 = m2.case("LF1").uebermasse
    check("und übersteht Speichern und Laden",
          len(u2) == 1 and u2[0].ziel == "Fuge"
          and abs(u2[0].ueberdeckung - UEBER) < 1e-15
          and u2[0].passmass == "ebene Fuge", str(u2))
    m3 = zwei_wuerfel()
    try:
        m3.add_uebermass("gibt es nicht", 1e-4)
        check("ein Übermaß ohne Fuge wird abgewiesen", False, "keine Ausnahme")
    except KeyError as ex:
        check("ein Übermaß ohne Fuge wird abgewiesen", "gibt es nicht" in str(ex),
              str(ex)[:70])
    m3.add_uebermass("Fuge", 5e-5, passmass="H7/s6")
    check("add_uebermass legt es im aktiven Lastfall an",
          len(m3.case().uebermasse) == 1
          and m3.case().uebermasse[0].passmass == "H7/s6")


def main():
    for f in (test_ebene_fuge, test_kombination_skaliert, test_zylindrische_fuge,
              test_schub_ueber_die_reibung, test_passung_aus_abmassen,
              test_datenmodell):
        print(f"\n--- {f.__name__} ---")
        try:
            f()
        except Exception as ex:          # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{f.__name__} ohne Ausnahme", False, str(ex)[:80])
    n_ok = sum(1 for _n, ok in RESULTS if ok)
    print("\n" + "=" * 60)
    print(f"Ergebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
