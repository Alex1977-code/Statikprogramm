"""
Kontaktfugen und freie Rechtecklasten - gegen geschlossene Werte geprueft.

Eine Kontaktfuge laesst sich nicht „ungefaehr" pruefen: entweder traegt sie
Druck und oeffnet unter Zug, oder sie tut es nicht. Geprueft wird darum an
zwei Wuerfeln uebereinander, deren Zugstab-Loesung in einer Zeile steht:

* **Druck** - die Fuge ist zu; die Stauchung muss die des durchverbundenen
  Stabes sein, N L /(E A), und die Auflagerkraft die aufgebrachte Last. Die
  Auflagerkraft trifft auf die Rechengenauigkeit genau; die Stauchung bleibt
  rund 2 % darunter, weil lineare Tetraeder bei dieser Netzweite so viel zu
  steif sind - darum steht dort 3 % als Schranke und nicht 0.
* **Zug** - die Fuge geht auf; durch das Fundament darf **keine** Kraft mehr
  gehen. Der Sollwert ist die Null, nicht ein kleiner Wert.
* **Passende und nicht passende Netze** - haben beide Koerper dieselbe
  Flaeche, teilen sie sich deren Knoten und die Fuge wird Knoten gegen Knoten
  angeschrieben. Hat jeder Koerper seine **eigene** Flaeche - so legt RFEM ein
  Volumenmodell an -, ist nur der gemeinsame Rand verschweisst: der wird
  getrennt, die Flaeche dazwischen traegt ein Kontaktpaar.
* **Verschieden feine Netze, Verbund, Spalt** - wie in ANSYS muessen die
  Flaechen einer Fuge weder deckungsgleich noch gleich fein vernetzt sein:
  das Kontaktpaar findet seine Gegenseite im Suchradius. Ein Verbund
  uebertraegt auch Zug, ein geschlossener Spalt (auf Beruehrung gesetzt)
  traegt sofort. Eine feine Achse in einer groben Bohrung mit Spiel findet
  die Bohrung nur dort, wo beide sich ueberdecken.
* **Freie Rechtecklast** - die Last wirkt in einem Fenster. Deckt das Fenster
  die ganze Flaeche, muss die Summe der Auflagerkraefte genau p mal A sein;
  deckt es nichts, darf keine Last entstehen; und jede belastete Elementseite
  muss mit ihrem Schwerpunkt im Fenster liegen.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import diagnose, fugen, mesher3d as M3, solver   # noqa: E402
from statik3d.model import DofBehaviour, Material, Model    # noqa: E402

RESULTS = []

E_STAHL = 210e9          # N/m^2 - S235
A_FUGE = 1.0             # m^2   - Querschnitt der Wuerfel
L_STAB = 2.0             # m     - Gesamthoehe der beiden Wuerfel


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FEHLER'} {name:58s} {detail}")
    return bool(ok)


def close(name, got, want, tol, unit=""):
    ok = abs(float(got) - float(want)) <= tol
    abw = abs(got - want) / abs(want) * 100 if want else 0.0
    return check(name, ok, f"{got:.6g}{unit} / {want:.6g}{unit}  Abw. {abw:.4f} %")


# --------------------------------------------------------------------------
# Baukasten
# --------------------------------------------------------------------------
class Bauer:
    """Legt Linien an und zaehlt die Namen selbst durch."""

    def __init__(self, model):
        self.m = model
        self.i = 0

    def linie(self, a, b):
        self.i += 1
        self.m.add_line(f"L{self.i}", [a, b], "polyline")
        return f"L{self.i}"


def zwei_bloecke(art: str = "gemeinsam", h: float = 0.5, h_oben: float = 0.0,
                ordnung: int = 1) -> Model:
    """Zwei Einheitswuerfel uebereinander, vernetzt.

    art = "gemeinsam": beide Koerper haben **dieselbe** Trennflaeche - der
          Vernetzer gibt ihnen dort dieselben Knoten (passende Netze).
    art = "eigene":    jeder Koerper hat seine **eigene** Trennflaeche ueber
          denselben Linien - nur der Rand ist gemeinsam (nicht passende
          Netze, so kommt es aus RFEM).
    h_oben > 0: der obere Wuerfel bekommt eine eigene, andere Kantenlaenge.
    ordnung = 2: tet10 statt tet4.
    """
    m = Model()
    m.add_material(Material.steel("S235"))
    P = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                  [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
                  [0, 0, 2], [1, 0, 2], [1, 1, 2], [0, 1, 2.]])
    m.add_nodes(P)
    b = Bauer(m)
    R = [[b.linie(o + i, o + (i + 1) % 4) for i in range(4)] for o in (0, 4, 8)]
    V01 = [b.linie(i, i + 4) for i in range(4)]
    V12 = [b.linie(i + 4, i + 8) for i in range(4)]
    m.add_flaeche("Boden", R[0], material="S235")
    m.add_flaeche("Dach", R[2], material="S235")
    if art == "gemeinsam":
        m.add_flaeche("Fuge", R[1], material="S235")
        fuge_u = fuge_o = "Fuge"
    else:
        m.add_flaeche("FugeU", R[1], material="S235")
        m.add_flaeche("FugeO", R[1], material="S235")
        fuge_u, fuge_o = "FugeU", "FugeO"
    unten, oben = [], []
    for i in range(4):
        m.add_flaeche(f"MU{i}", [R[0][i], V01[(i + 1) % 4], R[1][i], V01[i]],
                      material="S235")
        m.add_flaeche(f"MO{i}", [R[1][i], V12[(i + 1) % 4], R[2][i], V12[i]],
                      material="S235")
        unten.append(f"MU{i}")
        oben.append(f"MO{i}")
    k1 = m.add_koerper("Unten", ["Boden", fuge_u] + unten, material="S235")
    k2 = m.add_koerper("Oben", [fuge_o, "Dach"] + oben, material="S235")
    m.netz.ziellaenge = h
    m.netz.ordnung = ordnung
    cache = {}
    M3.mesh_koerper_frei(m, k1, log=[], cache=cache)
    M3.mesh_koerper_frei(m, k2, h=float(h_oben or 0.0), log=[], cache=cache)
    return m


def drei_bloecke() -> Model:
    """Wie zwei_bloecke("eigene"), dazu eine Rippe neben dem oberen Wuerfel,
    die dessen Seitenflaeche MO1 (x = 1) als eigene Randflaeche fuehrt -
    verschweisst. Ihre Unterkante ist die Linie R[1][1] auf der Fuge: die
    Knoten dort gehoeren Unten, Oben und Rippe."""
    m = Model()
    m.add_material(Material.steel("S235"))
    P = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                  [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
                  [0, 0, 2], [1, 0, 2], [1, 1, 2], [0, 1, 2.],
                  [2, 0, 1], [2, 1, 1], [2, 0, 2], [2, 1, 2.]])
    m.add_nodes(P)
    b = Bauer(m)
    R = [[b.linie(o + i, o + (i + 1) % 4) for i in range(4)] for o in (0, 4, 8)]
    V01 = [b.linie(i, i + 4) for i in range(4)]
    V12 = [b.linie(i + 4, i + 8) for i in range(4)]
    m.add_flaeche("Boden", R[0], material="S235")
    m.add_flaeche("Dach", R[2], material="S235")
    m.add_flaeche("FugeU", R[1], material="S235")
    m.add_flaeche("FugeO", R[1], material="S235")
    unten, oben = [], []
    for i in range(4):
        m.add_flaeche(f"MU{i}", [R[0][i], V01[(i + 1) % 4], R[1][i], V01[i]], material="S235")
        m.add_flaeche(f"MO{i}", [R[1][i], V12[(i + 1) % 4], R[2][i], V12[i]], material="S235")
        unten.append(f"MU{i}")
        oben.append(f"MO{i}")
    # Rippe: x von 1 bis 2, z von 1 bis 2; Knoten 5, 6, 9, 10 sind die von Oben
    l_6_13, l_13_12, l_12_5 = b.linie(6, 13), b.linie(13, 12), b.linie(12, 5)
    l_10_15, l_15_14, l_14_9 = b.linie(10, 15), b.linie(15, 14), b.linie(14, 9)
    l_12_14, l_13_15 = b.linie(12, 14), b.linie(13, 15)
    m.add_flaeche("RB", [R[1][1], l_6_13, l_13_12, l_12_5], material="S235")        # Boden der Rippe
    m.add_flaeche("RD", [R[2][1], l_10_15, l_15_14, l_14_9], material="S235")       # Dach der Rippe
    m.add_flaeche("RX", [l_13_12, l_12_14, l_15_14, l_13_15], material="S235")      # x = 2
    m.add_flaeche("RY0", [l_12_5, V12[1], l_14_9, l_12_14], material="S235")        # y = 0
    m.add_flaeche("RY1", [l_6_13, l_13_15, l_10_15, V12[2]], material="S235")       # y = 1
    k1 = m.add_koerper("Unten", ["Boden", "FugeU"] + unten, material="S235")
    k2 = m.add_koerper("Oben", ["FugeO", "Dach"] + oben, material="S235")
    k3 = m.add_koerper("Rippe", ["MO1", "RB", "RD", "RX", "RY0", "RY1"], material="S235")
    m.netz.ziellaenge = 0.5
    cache = {}
    for k in (k1, k2, k3):
        M3.mesh_koerper_frei(m, k, log=[], cache=cache)
    return m


def kontaktbedingung(m: Model, art: str, failure: str = "zug",
                     tangential: str = "free"):
    """Die Kontaktbedingung der Trennflaeche - wie sie aus RFEM kaeme."""
    t = (DofBehaviour("rigid") if tangential == "rigid"
         else DofBehaviour("free"))
    return m.add_kontaktbedingung(
        "Fuge",
        flaechennamen=["Fuge"] if art == "gemeinsam" else ["FugeO"],
        gegenflaechen=[] if art == "gemeinsam" else ["FugeU"],
        koerpernamen=["Oben"],
        behaviour={0: t, 1: t, 2: DofBehaviour("free", failure=failure)})


def _flaechenknoten(m: Model, z: float) -> list:
    """Knoten in der Hoehe z, die wirklich an einem Element haengen."""
    im = np.zeros(m.nn, bool)
    im[[int(x) for e in m.elements for x in e.nodes]] = True
    return [int(i) for i in np.flatnonzero(im & (np.abs(m.nodes[:, 2] - z) < 1e-9))]


def rechnen(m: Model, p: float, federn: float = 0.0, z_oben: float = 2.0):
    """Unten eingespannt, oben die Flaechenlast p [N/m^2].

    p ist wie in RFEM und in :class:`FaceLoad` gezaehlt: **positiv drueckt in
    den Koerper hinein**, hier also von oben nach unten. Die Last kommt als
    Flaechenlast auf die Deckelflaeche, nicht als Einzelkraefte - nur so ist
    die Spannung im Stab gleichmaessig und die Verkuerzung mit N L /(E A)
    nachzurechnen.

    federn > 0: die Oberseite haengt zusaetzlich in Federn dieser
    Gesamtsteifigkeit (in allen drei Richtungen). Ohne sie koennte der obere
    Wuerfel bei geoeffneter Fuge davonfliegen.
    """
    unten = _flaechenknoten(m, 0.0)
    oben = _flaechenknoten(m, z_oben)
    for i in unten:
        m.fix(i, [0, 1, 2])
    if federn > 0:
        k = federn / len(oben)
        for i in oben:
            m.fix(i, [0, 1, 2], stiffness=[k, k, k])
    lc = m.add_load_case("LF1")
    lc.gravity = [0, 0, 0]
    m.add_geometrielast("Dach", p, "flaeche", case="LF1")
    n = m.lasten_verteilen()
    assert n, "die Deckelflaeche ist nicht vernetzt"
    r = solver.solve_static(m, case="LF1")
    u = r.u.reshape(-1, 6)
    return {"r": r, "unten": unten, "oben": oben,
            "R_fundament": float(r.reactions[unten, 2].sum()),
            "R_gesamt": float(r.reactions[:, 2].sum()),
            "u_oben": float(u[oben, 2].mean())}


# --------------------------------------------------------------------------
# 1) Passende Netze: Knoten gegen Knoten
# --------------------------------------------------------------------------
def test_passende_netze_druck():
    m = zwei_bloecke("gemeinsam")
    fuge = m.flaechen["Fuge"]
    gruppen = fugen.gruppen_je_knoten(m)
    fugenknoten = {n for _e, nd, _n in fugen._dreiecke_der_fuge(m, [fuge]) for n in nd}
    check("vor der Trennung gehört jeder Fugenknoten beiden Bauteilen",
          all(gruppen[k] == {"Unten", "Oben"} for k in fugenknoten),
          f"{len(fugenknoten)} Fugenknoten")

    p = 1.0e6                               # N/m^2 Druck von oben
    F = p * A_FUGE                          # N   - Gesamtlast
    verbunden = rechnen(zwei_bloecke("gemeinsam"), p)
    soll = -F * L_STAB / (E_STAHL * A_FUGE)
    close("durchverbunden: Stauchung ist N L /(E A)",
          verbunden["u_oben"], soll, abs(soll) * 0.03, " m")

    kb = kontaktbedingung(m, "gemeinsam")
    log = []
    b = fugen.kontaktfuge_ausfuehren(m, kb, log)
    check("die Fuge wird ausgeführt", kb.ausgefuehrt and not b["grund"], b["grund"])
    check("jeder Fugenknoten ist verdoppelt", b["knoten"] == len(fugenknoten),
          f"{b['knoten']} von {len(fugenknoten)}")
    check("und trägt ein Spaltelement", b["spalt"] == b["knoten"],
          f"{b['spalt']} Spaltelemente")
    check("es entsteht kein Kontaktpaar (die Netze passen)",
          b["kontaktpaar"] == 0 and not m.contact_pairs, str(b["kontaktpaar"]))
    nach = fugen.gruppen_je_knoten(m)
    check("nach der Trennung gehört kein Knoten mehr beiden Bauteilen",
          all(len(v) == 1 for v in nach.values()),
          f"{sum(1 for v in nach.values() if len(v) > 1)} gemeinsame Knoten")

    getrennt = rechnen(m, p)
    close("Druck geht durch die Fuge: dieselbe Stauchung",
          getrennt["u_oben"], verbunden["u_oben"],
          abs(verbunden["u_oben"]) * 0.01, " m")
    close("und das Fundament trägt die volle Last",
          getrennt["R_fundament"], F, abs(F) * 1e-6, " N")


def test_passende_netze_zug():
    p = -1.0e6                              # N/m^2 Zug nach oben
    F = -p * A_FUGE                         # N   - Gesamtlast nach oben
    k_feder = 1.0e11
    verbunden = rechnen(zwei_bloecke("gemeinsam"), p, federn=k_feder)
    check("durchverbunden geht ein Teil des Zuges durch das Fundament",
          verbunden["R_fundament"] < -0.1 * F,
          f"R = {verbunden['R_fundament'] / 1e3:.1f} kN von {F / 1e3:.0f} kN")

    m = zwei_bloecke("gemeinsam")
    kb = kontaktbedingung(m, "gemeinsam")
    fugen.kontaktfuge_ausfuehren(m, kb, [])
    getrennt = rechnen(m, p, federn=k_feder)
    check("nach der Trennung trägt das Fundament keinen Zug mehr",
          abs(getrennt["R_fundament"]) <= 1e-6 * F,
          f"R = {getrennt['R_fundament']:.3e} N (Sollwert 0)")
    close("die Last hängt vollständig in den Federn",
          getrennt["R_gesamt"], -F, abs(F) * 1e-6, " N")
    check("und der obere Würfel hebt ab",
          getrennt["u_oben"] > 0.9 * F / k_feder,
          f"u = {getrennt['u_oben'] * 1e3:.4f} mm gegen F/k = {F / k_feder * 1e3:.4f} mm")


def test_vorzeichen_aus_der_geometrie():
    """„Ausfall bei Druck" aus der Datei meint dieselbe Fuge - Druck traegt."""
    p = 1.0e6
    m = zwei_bloecke("gemeinsam")
    kb = kontaktbedingung(m, "gemeinsam", failure="druck")
    log = []
    fugen.kontaktfuge_ausfuehren(m, kb, log)
    check("das umgekehrte Vorzeichen steht im Protokoll",
          any("Ausfall bei" in z and "z-Achse" in z for z in log),
          "; ".join(z for z in log if "z-Achse" in z)[:70])
    getrennt = rechnen(m, p)
    soll = -p * A_FUGE * L_STAB / (E_STAHL * A_FUGE)
    close("die Fuge trägt trotzdem Druck", getrennt["u_oben"], soll,
          abs(soll) * 0.03, " m")


# --------------------------------------------------------------------------
# 2) Nicht passende Netze: Rand trennen, Flaeche ueber ein Kontaktpaar
# --------------------------------------------------------------------------
def test_eigene_flaechen():
    m = zwei_bloecke("eigene")
    gruppen = fugen.gruppen_je_knoten(m)
    oben_f = m.flaechen["FugeO"]
    fugenknoten = {n for _e, nd, _n in fugen._dreiecke_der_fuge(m, [oben_f]) for n in nd}
    gemeinsam = [k for k in fugenknoten if len(gruppen[k]) > 1]
    check("bei eigenen Flächen ist nur der Rand verschweißt",
          0 < len(gemeinsam) < len(fugenknoten),
          f"{len(gemeinsam)} von {len(fugenknoten)} Fugenknoten")

    kb = kontaktbedingung(m, "eigene")
    log = []
    b = fugen.kontaktfuge_ausfuehren(m, kb, log)
    check("die Fuge wird ausgeführt", kb.ausgefuehrt and not b["grund"], b["grund"])
    check("der gemeinsame Rand wird getrennt", b["knoten"] == len(gemeinsam),
          f"{b['knoten']} von {len(gemeinsam)}")
    check("und die Fläche trägt ein Kontaktpaar",
          b["kontaktpaar"] == 1 and len(m.contact_pairs) == 1,
          f"{len(m.contact_pairs)} Kontaktpaare")
    nach = fugen.gruppen_je_knoten(m)
    check("danach gehört kein Knoten mehr beiden Bauteilen",
          all(len(v) == 1 for v in nach.values()),
          f"{sum(1 for v in nach.values() if len(v) > 1)} gemeinsame Knoten")
    cp = m.contact_pairs[0]
    check("Slave- und Masterknoten sind verschieden",
          not (set(cp.slave_nodes) & {int(x) for f in cp.master_faces for x in f}),
          f"{len(cp.slave_nodes)} Slave, {len(cp.master_faces)} Masterflächen")

    p = 1.0e6
    F = p * A_FUGE
    getrennt = rechnen(m, p)
    soll = -F * L_STAB / (E_STAHL * A_FUGE)
    close("das Kontaktpaar trägt den Druck", getrennt["u_oben"], soll,
          abs(soll) * 0.03, " m")
    close("und das Fundament trägt die volle Last",
          getrennt["R_fundament"], F, abs(F) * 1e-6, " N")


def test_eigene_flaechen_zug():
    p = -1.0e6
    F = -p * A_FUGE
    k_feder = 1.0e11
    m = zwei_bloecke("eigene")
    kb = kontaktbedingung(m, "eigene")
    fugen.kontaktfuge_ausfuehren(m, kb, [])
    getrennt = rechnen(m, p, federn=k_feder)
    check("auch das Kontaktpaar überträgt keinen Zug",
          abs(getrennt["R_fundament"]) <= 1e-6 * F,
          f"R = {getrennt['R_fundament']:.3e} N (Sollwert 0)")


def test_fuge_ueber_gegenseite():
    """RFEM kann eine Freigabe auch ohne freigegebene Flaechen anlegen: nur der
    geloeste Koerper und die zugeordneten Flaechen der Gegenseite (so die
    Grundplatte auf ihren Unterlegblechen). Die Fuge entsteht dann aus den
    Randseiten des Koerpers auf diesen Flaechen - und traegt Druck wie sonst."""
    def bedingung(m):
        return m.add_kontaktbedingung(
            "Fuge", flaechennamen=[], gegenflaechen=["FugeU"], koerpernamen=["Oben"],
            behaviour={0: DofBehaviour("free"), 1: DofBehaviour("free"),
                       2: DofBehaviour("free", failure="zug")})
    m = zwei_bloecke("eigene")
    kb = bedingung(m)
    log = []
    b = fugen.kontaktfuge_ausfuehren(m, kb, log)
    check("ohne freigegebene Flächen wird die Fuge aus Körper und Gegenflächen gebildet",
          kb.ausgefuehrt and not b["grund"], b["grund"])
    check("… als Kontaktpaar mit getrenntem Rand", b["kontaktpaar"] == 1 and b["knoten"] > 0,
          f"{b['kontaktpaar']} Kontaktpaare, {b['knoten']} Knoten")
    nach = fugen.gruppen_je_knoten(m)
    check("danach gehört kein Knoten mehr beiden Bauteilen",
          all(len(v) == 1 for v in nach.values()),
          f"{sum(1 for v in nach.values() if len(v) > 1)} gemeinsame Knoten")
    p = 1.0e6
    F = p * A_FUGE
    getrennt = rechnen(m, p)
    soll = -F * L_STAB / (E_STAHL * A_FUGE)
    close("das Kontaktpaar trägt den Druck", getrennt["u_oben"], soll, abs(soll) * 0.03, " m")
    close("und das Fundament trägt die volle Last", getrennt["R_fundament"], F, abs(F) * 1e-6, " N")
    m2 = zwei_bloecke("eigene")
    fugen.kontaktfuge_ausfuehren(m2, bedingung(m2), [])
    zug = rechnen(m2, -p, federn=1.0e11)
    check("und überträgt keinen Zug", abs(zug["R_fundament"]) <= 1e-6 * F,
          f"R = {zug['R_fundament']:.3e} N (Sollwert 0)")
    m3 = zwei_bloecke("eigene")
    kb3 = m3.add_kontaktbedingung("Fuge", flaechennamen=[], gegenflaechen=[], koerpernamen=["Oben"],
                                  behaviour={2: DofBehaviour("free", failure="zug")})
    b3 = fugen.kontaktfuge_ausfuehren(m3, kb3, [])
    check("ohne Flächen und ohne Gegenflächen: ein Grund statt einer stillen Fuge",
          not kb3.ausgefuehrt and "Gegenflächen" in b3["grund"], b3["grund"])


def test_fuge_laesst_schweissnaht_ganz():
    """Eine Fuge loest den Koerper samt seiner angeschweissten Nachbarn: die
    Knoten, die er nur mit ihnen teilt, werden nicht verdoppelt, und die
    Nachbarn bekommen dieselben Kopien. Am Drehlager verlor der Lagerbock
    sonst an der Fugenkante den Anschluss an vier Rippen (12.09.2026)."""
    m = drei_bloecke()
    check("drei Koerper vernetzt", len(m.koerper) == 3 and all(k.elemente for k in m.koerper.values()))
    vorher = diagnose._abnahme_gemeinsame_flaechen(m)
    check("vor der Fuge: Oben und Rippe verbunden (keine Befunde)", not vorher,
          str([x.text[:60] for x in vorher]))
    gruppen = fugen.gruppen_je_knoten(m)
    dreifach = [k for k, v in gruppen.items() if v >= {"Unten", "Oben", "Rippe"}]
    check("Knoten der Fugenkante gehoeren Unten, Oben und Rippe", len(dreifach) > 0, f"{len(dreifach)} Knoten")
    check("verschweisste Gruppe von Oben ist Oben+Rippe, nicht Unten",
          fugen.verschweisste_gruppe(m, {"Oben"}, {"FugeO", "FugeU"}) == {"Oben", "Rippe"})
    kb = kontaktbedingung(m, "eigene")
    log = []
    b = fugen.kontaktfuge_ausfuehren(m, kb, log)
    check("Fuge ausgefuehrt, Kontaktpaar, Rippe mitgeloest",
          kb.ausgefuehrt and b["kontaktpaar"] == 1 and b.get("mitgeloest") == ["Rippe"], str(b))
    nachher = diagnose._abnahme_gemeinsame_flaechen(m)
    check("nach der Fuge: Oben und Rippe weiter verbunden (keine doppelten Knoten)",
          not [x for x in nachher if "Rippe" in x.objekt], str([x.text[:80] for x in nachher]))
    nach = fugen.gruppen_je_knoten(m)
    check("kein Knoten gehoert Unten und Oben oder Rippe zugleich",
          not any(("Unten" in v) and (v & {"Oben", "Rippe"}) for v in nach.values()),
          f"{sum(1 for v in nach.values() if 'Unten' in v and v & {'Oben', 'Rippe'})} Knoten")
    check("Rippe und Oben teilen weiter Knoten", any(v >= {"Oben", "Rippe"} for v in nach.values()))
    check("Protokoll nennt die mitgeloeste Rippe",
          any("Rippe" in z and "angeschweißt" in z for z in log), str([z for z in log if "Rippe" in z])[:120])


def test_alle_fugen():
    """kontaktfugen_ausfuehren: Summenbericht und Wiederholbarkeit."""
    m = zwei_bloecke("gemeinsam")
    kontaktbedingung(m, "gemeinsam")
    log = []
    g1 = fugen.kontaktfugen_ausfuehren(m, log)
    check("eine Fuge ausgeführt", g1["fugen"] == 1 and g1["offen"] == 0, str(g1))
    n_spalt = len(m.gap_elements)
    g2 = fugen.kontaktfugen_ausfuehren(m, [])
    check("ein zweiter Aufruf ändert nichts",
          g2["fugen"] == 0 and len(m.gap_elements) == n_spalt,
          f"{len(m.gap_elements)} Spaltelemente")

    # Eine Bedingung ohne Netz muss mit Grund gemeldet werden
    m2 = Model()
    m2.add_material(Material.steel("S235"))
    m2.add_kontaktbedingung("Leer", flaechennamen=["gibtsnicht"])
    log2 = []
    g3 = fugen.kontaktfugen_ausfuehren(m2, log2)
    check("was nicht geht, steht mit Grund im Protokoll",
          g3["offen"] == 1 and any("nicht ausgeführt" in z for z in log2),
          "; ".join(log2)[:70])


def _fremdkoerper(m: Model, x0: float, kante: float, h: float) -> None:
    """Ein grob vernetzter Quader weit weg - er hat mit keiner Fuge zu tun."""
    b = Bauer(m)
    b.i = 1000 + len(m.lines)
    i0 = len(m.nodes)
    m.add_nodes(np.array([[x0 + a * kante, y * kante, z * kante]
                          for z in (0, 1) for a, y in ((0, 0), (1, 0), (1, 1), (0, 1))], float))
    R = [[b.linie(i0 + o + k, i0 + o + (k + 1) % 4) for k in range(4)] for o in (0, 4)]
    V = [b.linie(i0 + k, i0 + k + 4) for k in range(4)]
    fl = ["FU", "FO"]
    m.add_flaeche("FU", R[0], material="S235")
    m.add_flaeche("FO", R[1], material="S235")
    for k in range(4):
        m.add_flaeche(f"FM{k}", [R[0][k], V[(k + 1) % 4], R[1][k], V[k]], material="S235")
        fl.append(f"FM{k}")
    M3.mesh_koerper_frei(m, m.add_koerper("Fremd", fl, material="S235"), h=h, log=[], cache={})


def test_suchradius_kommt_aus_der_fuge():
    """Der Suchradius muss das Netz **dieser Fuge** haben, nicht das des Modells.

    Gesucht wird gegen die Randseiten aller anderen Bauteile - und der
    Suchradius war deren Median-Kantenlaenge. Der Median haelt einen
    einzelnen groben Ausreisser heraus, nicht aber eine grobe Mehrheit: an
    einem Modell, das ueberwiegend grob vernetzt ist, bekam eine feine Fuge
    die grobe Netzweite. Im Drehlagermodell waren das 45 bis 50 mm fuer
    Fugen, deren eigenes Netz viel feiner ist - und ein Suchradius, der
    groesser ist als das Bauteil dick, paart Knoten ueber Luft hinweg.

    Geprueft an derselben Fuge, einmal allein und einmal neben einem groben
    Fremdkoerper, der mit ihr nichts zu tun hat: der Radius muss beide Male
    derselbe sein.
    """
    radien, anteile = [], []
    for fremd in (False, True):
        m = zwei_bloecke("eigene", h=0.25)
        if fremd:
            # Grob vernetzt und gross genug, dass er die **Mehrheit** der
            # Randfacetten stellt - nur dann verschiebt er den Median. Genau
            # so liegt es im Drehlagermodell: die feinen Stifte sind in der
            # Minderheit gegen Lagerbock, Achse und Deckel.
            _fremdkoerper(m, 20.0, 6.0, 1.0)
        kb = m.add_kontaktbedingung(
            "Fuge", flaechennamen=["FugeO"], gegenflaechen=["FugeU"], koerpernamen=["Oben"],
            behaviour={2: DofBehaviour("free", failure="zug")})
        b = fugen.kontaktfuge_ausfuehren(m, kb, [])
        radien.append(m.contact_pairs[-1].search_radius)
        anteile.append(b["anteil"])
    check("die Fuge wird in beiden Modellen ganz gefunden",
          min(anteile) > 0.99, f"{anteile[0]*100:.1f} % / {anteile[1]*100:.1f} %")
    check("der Suchradius hängt nicht am groben Fremdkörper",
          abs(radien[0] - radien[1]) < 1e-9,
          f"{radien[0]*1e3:.1f} mm allein / {radien[1]*1e3:.1f} mm mit Fremdkörper")
    check("und er hat die Größenordnung des Fugennetzes (250 mm), nicht des Fremdnetzes (1 m)",
          radien[1] < 0.5, f"{radien[1]*1e3:.1f} mm")

    # Eine Vorgabe aus der Kontaktbedingung ist eine Entscheidung und bleibt
    m2 = zwei_bloecke("eigene", h=0.25)
    kb2 = m2.add_kontaktbedingung(
        "Fuge", flaechennamen=["FugeO"], gegenflaechen=["FugeU"], koerpernamen=["Oben"],
        suchweite=0.4, behaviour={2: DofBehaviour("free", failure="zug")})
    fugen.kontaktfuge_ausfuehren(m2, kb2, [])
    close("ein vorgegebener Suchradius wird nicht überstimmt",
          m2.contact_pairs[-1].search_radius, 0.4, 1e-12, " m")


def test_diagnose_sieht_die_gegenseite():
    """Die Gegenseite eines Kontaktpaars haelt ihr Bauteil - die Diagnose muss
    das sehen.

    Ein Kontaktpaar aus einer Fuge traegt seine Gegenseite als **Facetten**
    (``master_faces``), nicht als Elementliste; ``master_elements`` bleibt leer.
    Wer nur die Elementliste liest, sieht die Gegenseite gar nicht und haelt
    jedes Bauteil, das ausschliesslich Gegenseite ist, fuer ein Teiltragwerk
    ohne Lager. Im Drehlagermodell waren das 66 von 88 Teilen - die
    Passstifte, die Unterlegbleche und die Grundplatte -, und die Rechnung
    brach mit "FEHLER: 66 Teiltragwerke ohne Lager" ab, obwohl der Kontakt
    sie alle haelt.
    """
    m = zwei_bloecke("eigene")
    kb = m.add_kontaktbedingung(
        "Fuge", flaechennamen=["FugeO"], gegenflaechen=["FugeU"], koerpernamen=["Oben"],
        behaviour={2: DofBehaviour("free", failure="zug")})
    fugen.kontaktfuge_ausfuehren(m, kb, [])
    cp = m.contact_pairs[-1]
    check("das Kontaktpaar trägt seine Gegenseite als Facetten, nicht als Elemente",
          bool(cp.master_faces) and not cp.master_elements,
          f"{len(cp.master_faces)} Facetten, {len(cp.master_elements)} Elemente")
    fest_kn = _flaechenknoten(m, 2.0)          # nur der geloeste Koerper ist gelagert
    for i in fest_kn:
        m.fix(i, [0, 1, 2])
    fest, kontakt = diagnose.gehaltene_knoten(m)
    unten = {int(k) for e in m.elements if str(getattr(e, "group", "")) == "Unten"
             for k in e.nodes}
    check("die Knoten der Gegenseite zählen als durch Kontakt gehalten",
          bool(unten & kontakt), f"{len(unten & kontakt)} von {len(unten)}")
    d = diagnose.diagnose(m)
    check("das Bauteil auf der Gegenseite gilt nicht als ungelagert",
          not d["ohne_lager"], f"{len(d['ohne_lager'])} ohne Lager")
    check("sondern als nur durch Kontakt gehalten",
          len(d["nur_kontakt"]) == 1, f"{len(d['nur_kontakt'])} nur Kontakt")
    check("und das Modell gilt als rechenbar", d["rechenbar"])
    z = diagnose.meldungen(m, d)
    check("kein FEHLER „Teiltragwerk ohne Lager“",
          not any(x.startswith("FEHLER") and "ohne Lager" in x for x in z),
          "; ".join(z)[:80] or "keine Meldung")
    check("stattdessen der Hinweis auf den Kontakt",
          any("Kontakt" in x for x in z), "; ".join(z)[:80] or "keine Meldung")
    # Gegenprobe: ohne das Kontaktpaar ist die Gegenseite wirklich ungelagert
    m.contact_pairs.clear()
    check("ohne das Kontaktpaar meldet die Diagnose das Teil zu Recht",
          len(diagnose.diagnose(m)["ohne_lager"]) == 1,
          str(len(diagnose.diagnose(m)["ohne_lager"])))


def test_lager_werden_mitgenommen():
    """Ein Lager am Fugenknoten muss auf beiden Seiten weiterwirken."""
    m = zwei_bloecke("gemeinsam")
    fuge = m.flaechen["Fuge"]
    knoten = sorted({n for _e, nd, _n in fugen._dreiecke_der_fuge(m, [fuge]) for n in nd})
    m.fix(knoten[0], [0, 1, 2])
    kb = kontaktbedingung(m, "gemeinsam")
    fugen.kontaktfuge_ausfuehren(m, kb, [])
    lager = [s for s in m.supports if s.dofs == [0, 1, 2]]
    check("das Lager am Fugenknoten liegt danach auf beiden Seiten",
          len(lager) == 2 and lager[0].node != lager[1].node,
          f"{len(lager)} Lager an {sorted(s.node for s in lager)}")


# --------------------------------------------------------------------------
# 3) Freie Rechtecklasten
# --------------------------------------------------------------------------
def _wuerfel(h: float = 0.5, ordnung: int = 1) -> Model:
    """Ein Einheitswuerfel, vernetzt - Deckel oben (ordnung = 2: tet10)."""
    m = Model()
    m.add_material(Material.steel("S235"))
    m.add_nodes(np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                          [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1.]]))
    b = Bauer(m)
    R = [[b.linie(o + i, o + (i + 1) % 4) for i in range(4)] for o in (0, 4)]
    V = [b.linie(i, i + 4) for i in range(4)]
    m.add_flaeche("Boden", R[0], material="S235")
    m.add_flaeche("Deckel", R[1], material="S235")
    mantel = []
    for i in range(4):
        m.add_flaeche(f"M{i}", [R[0][i], V[(i + 1) % 4], R[1][i], V[i]],
                      material="S235")
        mantel.append(f"M{i}")
    k = m.add_koerper("V1", ["Boden", "Deckel"] + mantel, material="S235")
    m.netz.ziellaenge = h
    m.netz.ordnung = ordnung
    M3.mesh_koerper_frei(m, k, log=[], cache={})
    return m


def _summe_reaktion(m: Model) -> float:
    for i in _flaechenknoten(m, 0.0):
        m.fix(i, [0, 1, 2])
    r = solver.solve_static(m, case="LF1")
    return float(r.reactions[:, 2].sum())


def test_freie_rechtecklast():
    p = 1.0e5                           # N/m^2, von oben auf den Deckel
    ganz = {"art": "rechteck", "ursprung": [0, 0, 1], "u": [1, 0, 0], "v": [0, 1, 0],
            "von": [-0.1, -0.1], "bis": [1.1, 1.1]}
    m = _wuerfel()
    gl = m.add_geometrielast("Deckel", p, "flaeche", bereich=ganz, case="LF1")
    n = m.lasten_verteilen()
    check("das Fenster über der ganzen Fläche belastet sie auch ganz",
          n == len(m.flaechen["Deckel"].randseiten),
          f"{n} von {len(m.flaechen['Deckel'].randseiten)} Elementseiten")
    close("Summe der Auflagerkräfte ist p mal A", _summe_reaktion(m), p * 1.0,
          abs(p) * 1e-6, " N")

    # Halbes Fenster: jede belastete Seite muss mit ihrem Schwerpunkt darin liegen
    halb = dict(ganz, von=[-0.1, -0.1], bis=[0.5, 1.1])
    m2 = _wuerfel()
    gl2 = m2.add_geometrielast("Deckel", p, "flaeche", bereich=halb, case="LF1")
    n2 = m2.lasten_verteilen()
    seiten = m2.case("LF1").face_loads
    drin = all(gl2.trifft(m2._seitenmitte(f.elem, f.face)) for f in seiten)
    check("im halben Fenster liegt jede belastete Seite wirklich darin",
          drin and 0 < n2 < n, f"{n2} von {n} Elementseiten")
    R2 = _summe_reaktion(m2)
    check("und die Summe liegt bei der Hälfte von p mal A",
          0.3 * abs(p) < abs(R2) < 0.7 * abs(p),
          f"{R2 / 1e3:.2f} kN gegen {p / 1e3:.2f} kN für die ganze Fläche")

    # Fenster daneben: keine Last
    daneben = dict(ganz, von=[2.0, 2.0], bis=[3.0, 3.0])
    m3 = _wuerfel()
    m3.add_geometrielast("Deckel", p, "flaeche", bereich=daneben, case="LF1")
    check("ein Fenster neben der Fläche erzeugt keine Last",
          m3.lasten_verteilen() == 0, f"{len(m3.case('LF1').face_loads)} Elementlasten")

    # Das Fenster liegt in einer eigenen Ebene, nicht in der Flaechenebene
    schraeg = {"art": "rechteck", "ursprung": [0, 0, 0],
               "u": [0, 0, 1], "v": [0, 1, 0], "von": [0.9, -0.1], "bis": [1.1, 1.1]}
    m4 = _wuerfel()
    gl4 = m4.add_geometrielast("Deckel", p, "flaeche", bereich=schraeg, case="LF1")
    n4 = m4.lasten_verteilen()
    check("das Fenster darf in einer eigenen Ebene liegen",
          n4 == n and gl4.trifft([0.5, 0.5, 1.0]),
          f"{n4} Elementseiten (Fenster über z von 0.9 bis 1.1)")


def test_projizierte_last_wuerfel():
    """Last auf die **projizierte** Fläche - am Würfel geschlossen nachzurechnen."""
    p = 1.0e5
    m = _wuerfel()
    m.add_geometrielast("Deckel", p, "flaeche", richtung=[0, 0, -1],
                        case="LF1", projiziert=True)
    n = m.lasten_verteilen()
    close("senkrecht von oben: Summe ist p mal A", _summe_reaktion(m), p * 1.0,
          abs(p) * 1e-6, " N")
    check("und der Boden bleibt frei (er liegt im Windschatten)",
          n == len(m.flaechen["Deckel"].randseiten),
          f"{n} Elementseiten")

    # Schräg: getroffen werden Deckel **und** eine Seitenfläche, jede mit ihrem
    # Projektionsanteil. Die Summe ist p mal die Schattenfläche des Würfels.
    a = np.deg2rad(30.0)
    d = np.array([0.0, -np.sin(a), -np.cos(a)])
    m2 = _wuerfel()
    for f in ("Deckel", "M0", "M1", "M2", "M3", "Boden"):
        m2.add_geometrielast(f, p, "flaeche", richtung=d.tolist(),
                             case="LF1", projiziert=True)
    m2.lasten_verteilen()
    for i in _flaechenknoten(m2, 0.0):
        m2.fix(i, [0, 1, 2])
    for i in _flaechenknoten(m2, 1.0):
        m2.fix(i, [0, 1, 2])
    r = solver.solve_static(m2, case="LF1")
    R = r.reactions[:, :3].sum(axis=0)
    soll = -p * (np.cos(a) + np.sin(a)) * d          # Schattenfläche = cos+sin
    close("schräg: Summe ist p mal Schattenfläche (Betrag)",
          float(np.linalg.norm(R)), float(np.linalg.norm(soll)),
          abs(p) * 1e-6, " N")
    check("und sie zeigt genau in die Lastrichtung",
          float(np.linalg.norm(R / np.linalg.norm(R) - soll / np.linalg.norm(soll)))
          < 1e-9, f"{np.round(R / np.linalg.norm(R), 6)}")


def test_projizierte_last_bohrung():
    """Lagerpressung in einer Bohrung: die Summe ist p mal d mal l.

    Das ist der Fall aus RFEM: die freie Rechtecklast liegt als Fenster
    quer zur Bohrung, das Fenster misst Durchmesser mal Länge, und die
    Resultierende ist die Lagerkraft. Würde man p als Druck senkrecht zur
    **Fläche** deuten, hübe sich die Last über den Zylinder auf.
    """
    from tests.test_mesher3d import buchse, neues_modell
    ri, ra, h = 0.3, 0.5, 0.23
    p = 1.0e6
    m = neues_modell()
    k = buchse(m, ra, ri, h)
    m.netz.ziellaenge = 0.08
    M3.mesh_koerper_frei(m, k, log=[], cache={})
    d = np.array([1.0, 0.0, 0.0])
    for f in ("MantelI1", "MantelI2"):
        m.add_geometrielast(f, p, "flaeche", richtung=d.tolist(), case="LF1",
                            projiziert=True)
    n = m.lasten_verteilen()
    innen = sum(len(m.flaechen[f].randseiten or []) for f in ("MantelI1", "MantelI2"))
    check("nur die der Last zugewandte Hälfte der Bohrung wird belastet",
          0.4 * innen < n < 0.6 * innen, f"{n} von {innen} Elementseiten")
    for i in [int(x) for x in np.flatnonzero(
            np.abs(np.linalg.norm(m.nodes[:, :2], axis=1) - ra) < 1e-6)]:
        m.fix(i, [0, 1, 2])
    r = solver.solve_static(m, case="LF1")
    R = r.reactions[:, :3].sum(axis=0)
    soll = -p * 2 * ri * h * d
    close("die Resultierende ist p mal d mal l", float(R[0]), float(soll[0]),
          abs(soll[0]) * 0.03, " N")
    check("und quer dazu hebt sie sich auf",
          float(np.linalg.norm(R[1:])) < 1e-6 * abs(soll[0]),
          f"|R_quer| = {float(np.linalg.norm(R[1:])):.3e} N")


# --------------------------------------------------------------------------
# 3) Wie in ANSYS: verschieden feine Netze, Verbund, Spalt, Zylinder in Bohrung
# --------------------------------------------------------------------------
def test_verschieden_feine_netze():
    """Oben 0,15 m, unten 0,5 m (die Mindestteilung macht daraus 0,22 m): die
    Netze passen nirgends zusammen. Das
    Kontaktpaar muss die ganze Fuge finden - jeden Knoten der feinen Seite -
    und Druck wie der durchverbundene Stab tragen, Zug gar nicht."""
    m = zwei_bloecke("eigene", 0.5, 0.15)
    kb = kontaktbedingung(m, "eigene")
    log = []
    b = fugen.kontaktfuge_ausfuehren(m, kb, log)
    check("die Fuge wird als Kontaktpaar ausgeführt",
          kb.ausgefuehrt and b["kontaktpaar"] == 1, b["grund"])
    fugenknoten = {n for _e, nd, _n in fugen._dreiecke_der_fuge(m, [m.flaechen["FugeO"]]) for n in nd}
    cp = m.contact_pairs[0]
    check("jeder Knoten der feinen Fugenfläche ist Slave",
          set(cp.slave_nodes) == fugenknoten, f"{len(cp.slave_nodes)} von {len(fugenknoten)}")
    check("die ganze Kontaktseite findet ihre Gegenseite, ohne Spalt",
          abs(b["anteil"] - 1.0) < 1e-9 and b["spalt_max"] < 1e-9,
          f"Anteil {b['anteil']:.3f}, Spalt {b['spalt_max']:.2e} m")
    check("die Gegenseite ist die grobe Fläche (Vierecke oder Dreiecke, aber weniger als Slave-Knoten)",
          0 < len(cp.master_faces) < len(cp.slave_nodes), f"{len(cp.master_faces)} Masterflächen")
    p = 1.0e6
    F = p * A_FUGE
    getrennt = rechnen(m, p)
    soll = -F * L_STAB / (E_STAHL * A_FUGE)
    close("Druck: Stauchung wie im durchverbundenen Stab", getrennt["u_oben"], soll,
          abs(soll) * 0.03, " m")
    close("… und das Fundament trägt die volle Last", getrennt["R_fundament"], F, abs(F) * 1e-6, " N")
    m2 = zwei_bloecke("eigene", 0.5, 0.15)
    fugen.kontaktfuge_ausfuehren(m2, kontaktbedingung(m2, "eigene"), [])
    zug = rechnen(m2, -p, federn=1.0e11)
    check("Zug: die Fuge geht auf, das Fundament trägt nichts",
          abs(zug["R_fundament"]) <= 1e-6 * F, f"R = {zug['R_fundament']:.3e} N (Sollwert 0)")


def test_verbund():
    """Standardkontakt „Verbund“: Zug wird uebertragen - unter Zug dehnt sich
    der Stab wie durchverbunden, ohne Federn, die ihn halten muessten."""
    m = zwei_bloecke("eigene", 0.5, 0.15)
    kb = m.add_kontaktbedingung("Fuge", flaechennamen=["FugeO"], gegenflaechen=["FugeU"],
                                koerpernamen=["Oben"])
    kb.standard_anwenden("Verbund")
    b = fugen.kontaktfuge_ausfuehren(m, kb, [])
    cp = m.contact_pairs[0]
    check("Verbund: Zug und Haften stehen am Kontaktpaar",
          kb.ausgefuehrt and cp.zug and cp.haften and cp.mu == 0, b["grund"])
    p = -1.0e6
    F = p * A_FUGE
    r = rechnen(m, p)
    soll = -F * L_STAB / (E_STAHL * A_FUGE)
    close("Zug: Dehnung wie im durchverbundenen Stab", r["u_oben"], soll, abs(soll) * 0.03, " m")
    close("… und das Fundament trägt die volle Zugkraft", r["R_fundament"], F, abs(F) * 1e-6, " N")
    for name, zug, haften, mu in (("Ohne Trennung", True, False, 0.0), ("Reibungsfrei", False, False, 0.0),
                                  ("Reibungsbehaftet", False, False, 0.2), ("Rau", False, True, 0.0)):
        kb2 = m.add_kontaktbedingung("Probe " + name)
        kb2.standard_anwenden(name)
        b_n, b_t = kb2.dof_behaviour(2), kb2.dof_behaviour(0)
        check(f"Standardkontakt {name}: Wirkung je Richtung",
              (b_n.typ == "rigid") == zug and (b_t.typ == "rigid") == haften
              and abs(kb2.reibbeiwert() - mu) < 1e-12 and kb2.standard == name,
              kb2.describe())


def test_spalt_schliessen():
    """Der obere Wuerfel schwebt 1 mm ueber dem unteren. Auf Beruehrung gesetzt
    traegt die Fuge sofort; sonst bleibt der Spalt offen und der Wuerfel haengt
    in seinen Federn - das Fundament traegt nichts."""
    p = 1.0e6
    F = p * A_FUGE
    soll = -F * L_STAB / (E_STAHL * A_FUGE)
    for schliessen in (True, False):
        m = zwei_bloecke("eigene", 0.5, 0.15)
        kb = kontaktbedingung(m, "eigene")
        kb.spalt_schliessen = schliessen
        b = fugen.kontaktfuge_ausfuehren(m, kb, [])
        assert b["kontaktpaar"] == 1, b["grund"]
        oben = sorted({int(x) for e in m.koerper["Oben"].elemente for x in m.elements[e].nodes})
        m.nodes[oben, 2] += 0.001
        # Federn nur, wo der Wuerfel sonst davonfliegt: liegt er auf, wuerden
        # sie einen Teil der Last an der Fuge vorbei tragen
        r = rechnen(m, p, federn=0.0 if schliessen else 1.0e11, z_oben=2.001)
        if schliessen:
            close("Spalt geschlossen: der Stab trägt, als läge er auf", r["u_oben"], soll,
                  abs(soll) * 0.03, " m")
            close("… und das Fundament trägt die volle Last", r["R_fundament"], F, abs(F) * 1e-6, " N")
        else:
            check("Spalt offen: das Fundament trägt nichts, der Würfel hängt in den Federn",
                  abs(r["R_fundament"]) <= 1e-6 * F and abs(r["u_oben"] + F / 1.0e11) < 1e-6,
                  f"R = {r['R_fundament']:.3e} N, u = {r['u_oben']:.3e} m")


def test_zylinder_in_bohrung():
    """Eine fein vernetzte Achse (r = 100 mm, 3-mm-Facetten) in einer grob
    vernetzten Bohrung (r = 100,5 mm, 15-mm-Facetten) mit 0,5 mm Spiel: die
    Gegenseite wird nur dort gefunden, wo Achse und Bohrung sich ueberdecken -
    dort aber vollstaendig, mit dem Spiel als Abstand."""
    def mantel(m, r, z0, z1, n_phi, dz, nach_aussen):
        z = np.arange(z0, z1 + 1e-9, dz)
        phi = np.linspace(0, 2 * np.pi, n_phi, endpoint=False)
        ids = np.array([[m.add_node(r * np.cos(a), r * np.sin(a), zz) for a in phi] for zz in z])
        fac = []
        for i in range(len(z) - 1):
            for j in range(n_phi):
                k = (j + 1) % n_phi
                for nd in ((ids[i, j], ids[i, k], ids[i + 1, k]), (ids[i, j], ids[i + 1, k], ids[i + 1, j])):
                    c = m.nodes[list(nd)].mean(axis=0)
                    nrm = np.array([c[0], c[1], 0.0])
                    nrm /= np.linalg.norm(nrm)
                    fac.append((0, [int(x) for x in nd], nrm if nach_aussen else -nrm))
        return fac
    m = Model()
    achse = mantel(m, 0.100, 0.0, 0.3, 200, 0.003, True)
    bohrung = mantel(m, 0.1005, 0.1, 0.2, 42, 0.1 / 7, False)
    weite = fugen.suchweite(m, achse, bohrung)
    check("Suchradius ist die größere Kantenlänge (die der Bohrung, mit Diagonalen)",
          0.012 < weite < 0.022, f"{weite * 1e3:.1f} mm")
    paare, abstand = fugen.gegenseite_finden(m, achse, bohrung, weite)
    zc = np.array([m.nodes[nd].mean(axis=0)[2] for _e, nd, _n in achse])
    innen = (zc > 0.1 + 1e-6) & (zc < 0.2 - 1e-6)
    aussen = (zc < 0.1 - weite) | (zc > 0.2 + weite)
    gefunden = np.zeros(len(achse), bool)
    gefunden[list(paare)] = True
    check("jede Achsenfacette im Bereich der Bohrung findet die Bohrung",
          gefunden[innen].all(), f"{gefunden[innen].sum()} von {innen.sum()}")
    check("außerhalb des Suchradius findet keine etwas",
          not gefunden[aussen].any(), f"{gefunden[aussen].sum()} von {aussen.sum()}")
    d = abstand[innen]
    # Spiel 0,5 mm. Die Sehnen der 42-eckigen Bohrung liegen bis 0,28 mm
    # weiter innen - gemessen wird aber zur wahren Bohrung (Flaechenquadriken),
    # nicht zur Sehne: seit 13.09.2026 steht hier das Spiel, nicht das Spiel
    # minus Sehnenfehler
    check("im Überdeckungsbereich ist der Abstand das Spiel: 0,5 mm zur wahren Bohrung, nicht zur Sehne (0,22 … 0,5 mm)",
          abs(np.median(d) - 0.0005) < 2e-5 and abs(d.max() - 0.0005) < 3e-5 and abs(d.min() - 0.0005) < 3e-5,
          f"Median {np.median(d) * 1e3:.3f} mm, min {d.min() * 1e3:.3f}, max {d.max() * 1e3:.3f} mm")
    rand = gefunden & ~innen
    check("am Rand der Bohrung wird bis zum Suchradius zugeordnet - mit dem Abstand als Anfangsspalt",
          rand.any() and abstand[rand].max() <= weite + 1e-12, f"{rand.sum()} Facetten")
    check("die Gegenfacetten liegen alle in der Bohrung",
          all(0 <= j < len(bohrung) for j in paare.values()))


def test_starre_flaeche():
    """Eine starre Scheibe (RFEM: starre Flaeche, ohne Dicke) auf dem Dach des
    oberen Wuerfels, in ihrer Mitte das Ende eines Zugstabs, der nach oben zu
    einem festen Knoten laeuft. Die Scheibe haengt die Netzknoten darunter
    starr an das Stabende. Der Stab wird mit F_v vorgespannt: er zieht den
    Wuerfel nach oben, das Fundament traegt F_v, und die Knoten in der Scheibe
    bewegen sich wie das Stabende - starr."""
    from statik3d.model import Section
    m = zwei_bloecke("gemeinsam", 0.15)
    b = Bauer(m)
    ecken = [m.add_node(x, y, 2.0) for x, y in ((0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8))]
    linien = [b.linie(ecken[i], ecken[(i + 1) % 4]) for i in range(4)]
    m.add_flaeche("Scheibe", linien, material="S235")
    m.flaechen["Scheibe"].steifigkeit = "starr"
    mitte = m.add_node(0.5, 0.5, 2.0)
    oben = m.add_node(0.5, 0.5, 3.0)
    m.add_section(Section("Rund", 1e-4, 1e-9, 1e-9, 1e-9))
    e = m.add_element("truss", [mitte, oben], "S235", "Rund", group="Zugstab")
    m.add_member("Zugstab", [e])
    log = []
    b_ = fugen.starre_flaechen_koppeln(m, log)
    check("die starre Scheibe wird als Kopplung umgesetzt, Master ist das Stabende",
          b_["flaechen"] == 1 and b_["kopplungen"] >= 4 and not b_["offen"]
          and all(k.node_a == mitte for k in m.kopplungen), f"{b_} / {log[:1]}")
    check("die Scheibe zaehlt nicht als unvernetzte Flaeche",
          not m.flaeche_traegt("Scheibe"), m.flaechen["Scheibe"].kommentar)
    check("ein zweiter Aufruf legt die Kopplungen nicht doppelt an",
          fugen.starre_flaechen_koppeln(m, [])["kopplungen"] == len(m.kopplungen))
    slaves = sorted({int(k.node_b) for k in m.kopplungen})
    for i in _flaechenknoten(m, 0.0):
        m.fix(i, [0, 1, 2])
    m.fix(oben, "all")
    Fv = 50e3
    m.add_load_case("LF1").gravity = [0, 0, 0]
    m.add_vorspannung("Zugstab", Fv, case="LF1")
    r = solver.solve_static(m, case="LF1")
    unten = _flaechenknoten(m, 0.0)
    # Der Wuerfel gibt unter dem Zug etwas nach: um die Anhebung der Scheibe
    # wird der Stab weniger gedehnt, seine Kraft ist F_v - (EA/L) u_z
    u_m = r.u[mitte, :3]
    soll = Fv - 210e9 * 1e-4 / 1.0 * float(u_m[2])
    close("der vorgespannte Stab zieht am Wuerfel: das Fundament traegt die Stabkraft",
          -float(r.reactions[unten, 2].sum()), soll, 1e-6 * Fv, " N")
    close("… und der feste Stabknoten oben ebenso",
          float(r.reactions[oben, 2]), soll, 1e-6 * Fv, " N")
    check("die Stabkraft liegt knapp unter F_v (Nachgiebigkeit des Wuerfels)",
          0.999 * Fv < soll < Fv, f"{soll:.1f} N")
    abw = max(float(np.linalg.norm(r.u[s, :3] - u_m)) for s in slaves)
    check("die Knoten in der Scheibe bewegen sich wie das Stabende (starr)",
          abw <= 1e-3 * float(np.linalg.norm(u_m)) and float(np.linalg.norm(u_m)) > 0,
          f"Abweichung {abw:.2e} m bei u = {float(np.linalg.norm(u_m)):.2e} m")
    d = Model.from_dict(m.to_dict())
    check("Steifigkeitsart und Kopplungen ueberleben Speichern und Laden",
          d.flaechen["Scheibe"].steifigkeit == "starr" and len(d.kopplungen) == len(m.kopplungen))

    # Was die Kopplung **nicht** tut: ein Moment weitergeben. Sie fuehrt drei
    # Richtungen, nicht sechs, und in der Steifigkeitsmatrix steht sie
    # ausschliesslich auf Verschiebungsfreiheitsgraden - die Verdrehung des
    # Stabendes kommt in keiner Zeile vor. Das ist genau die Wirkung, die RFEM
    # hier ueber ein Liniengelenk vorschreibt (Verschiebungen starr,
    # Verdrehungen frei); die Volumenelemente unter der Scheibe haben ohnehin
    # keine Verdrehungsfreiheitsgrade, an denen ein Moment ankaeme.
    check("die Kopplung fuehrt nur die drei Verschiebungen",
          all(len(k.richtungen) == 3 and len(k.steifigkeiten) == 3
              for k in m.kopplungen),
          f"{len(m.kopplungen[0].richtungen)} Richtungen")
    from statik3d import assemble as _asm
    Kk = _asm.kopplungen(m)
    belegt = sorted({int(i) for i in Kk.tocoo().row} | {int(j) for j in Kk.tocoo().col})
    from statik3d.model import NDOF as _NDOF
    dreh = [i for i in belegt if i % _NDOF >= 3]
    check("und steht nur auf Verschiebungsfreiheitsgraden - kein Moment geht durch",
          not dreh, f"{len(belegt)} belegte Freiheitsgrade, davon {len(dreh)} Verdrehungen")


def test_naechste_punkte():
    """Der vektorisierte naechste Punkt auf Dreiecken liefert dasselbe wie der
    einzelne (Ericson) - Eckpunkte, Kanten und Inneres."""
    from statik3d.contact import closest_point_triangle, naechste_punkte_dreiecke
    rng = np.random.default_rng(7)
    A, B, C = (rng.normal(size=(500, 3)) for _ in range(3))
    p = rng.normal(size=3) * 0.7
    q, w = naechste_punkte_dreiecke(p, A, B, C)
    dq = max(np.linalg.norm(closest_point_triangle(p, A[i], B[i], C[i])[0] - q[i]) for i in range(500))
    rek = np.abs(w[:, :1] * A + w[:, 1:2] * B + w[:, 2:] * C - q).max()
    check("nächster Punkt: vektorisiert = einzeln", dq < 1e-12 and rek < 1e-12,
          f"max Abweichung {dq:.1e}, Rekonstruktion {rek:.1e}")


# --------------------------------------------------------------------------
# Der Spalt einer Fuge und der Formschluss
# --------------------------------------------------------------------------
def _facette(m, punkte, normale):
    """Eine Facette (Element, Knoten, Aussennormale) aus vier Punkten."""
    nd = [int(m.add_node(*p)) for p in punkte]
    return (0, nd, np.asarray(normale, float))


def test_spalt_laengs_der_normalen():
    """Der Spalt ist der Abstand SENKRECHT zur Fuge, nicht im Raum.

    An einem Absatz steht die Flanke des einen Teils regelmaessig ueber die
    des anderen hinaus. Beide liegen dann in derselben Ebene und beruehren
    sich - im Raum gemessen kaeme dort ein Spalt in Hoehe des Ueberstands
    heraus. Am Beispielmodell waren das 34,4 mm bei einem Normalabstand von
    0,000 mm.
    """
    m = Model()
    # Kontaktseite: eine Flanke in der Ebene x = 0, z von 0 bis 0,1
    seite = [_facette(m, [(0, 0, 0), (0, 0.1, 0), (0, 0.1, 0.1), (0, 0, 0.1)],
                      (-1, 0, 0))]
    # Gegenseite 1: dieselbe Ebene, aber 0,3 m hoeher - kein Gegenueber
    hoch = _facette(m, [(0, 0, 0.4), (0, 0.1, 0.4), (0, 0.1, 0.5), (0, 0, 0.5)],
                    (1, 0, 0))
    paare, abstand = fugen.gegenseite_finden(m, seite, [hoch], 0.5)
    check("Flanke ohne Gegenüber bleibt ungepaart (nur Querversatz)",
          not paare and not np.isfinite(abstand[0]),
          f"Paare {len(paare)}, Abstand {abstand[0]}")

    # Gegenseite 2: genau gegenueber, 3 mm entfernt -> Spalt = 3 mm
    m2 = Model()
    seite2 = [_facette(m2, [(0, 0, 0), (0, 0.1, 0), (0, 0.1, 0.1), (0, 0, 0.1)],
                       (-1, 0, 0))]
    gegen2 = [_facette(m2, [(-0.003, 0, 0), (-0.003, 0.1, 0),
                            (-0.003, 0.1, 0.1), (-0.003, 0, 0.1)], (1, 0, 0))]
    paare2, abstand2 = fugen.gegenseite_finden(m2, seite2, gegen2, 0.05)
    close("gegenüberliegende Fläche: Spalt = ihr Abstand", abstand2[0], 0.003,
          1e-9, " m")

    # Gegenseite 3: dieselbe Ebene, halb versetzt - sie ueberdeckt noch
    m3 = Model()
    seite3 = [_facette(m3, [(0, 0, 0), (0, 0.1, 0), (0, 0.1, 0.1), (0, 0, 0.1)],
                       (-1, 0, 0))]
    gegen3 = [_facette(m3, [(0, 0.05, 0.05), (0, 0.15, 0.05),
                            (0, 0.15, 0.15), (0, 0.05, 0.15)], (1, 0, 0))]
    paare3, abstand3 = fugen.gegenseite_finden(m3, seite3, gegen3, 0.05)
    check("halb versetzte, anliegende Fläche zählt mit Spalt null",
          bool(paare3) and abstand3[0] < 1e-12,
          f"Paare {len(paare3)}, Spalt {abstand3[0]:.3e} m")


def test_formschluss():
    """Wie viele Richtungen die Form der Fuge haelt.

    Eine ebene Fuge traegt eine Richtung (1/0/0), ein Absatz mit zwei Flanken
    alle drei. Die Fuge des Lagerbocks im Beispielmodell hat 0,78/0,13/0,09.
    """
    m = Model()
    eben = [_facette(m, [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], (0, 0, 1))]
    w, V = fugen.formschluss(m, eben)
    check("ebene Fuge hält nur eine Richtung",
          abs(w[0] - 1.0) < 1e-9 and w[1] < 1e-9 and w[2] < 1e-9,
          " / ".join(f"{x:.3f}" for x in w))
    check("und das ist ihre Normale", abs(abs(V[2, 0]) - 1.0) < 1e-9,
          str(np.round(V[:, 0], 3)))

    m2 = Model()
    # Boden 1 x 1 m und zwei Flanken 1 x 0,2 m in x und y
    absatz = [
        _facette(m2, [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], (0, 0, 1)),
        _facette(m2, [(0, 0, 0), (0, 1, 0), (0, 1, 0.2), (0, 0, 0.2)], (-1, 0, 0)),
        _facette(m2, [(0, 0, 0), (1, 0, 0), (1, 0, 0.2), (0, 0, 0.2)], (0, -1, 0)),
    ]
    w2, V2 = fugen.formschluss(m2, absatz)
    check("Absatz mit zwei Flanken hält alle drei Richtungen",
          int((w2 >= fugen.FORMSCHLUSS_MIN).sum()) == 3,
          " / ".join(f"{x:.3f}" for x in w2))
    close("und der Boden trägt 1/(1+0,2+0,2) der Fläche", w2[0], 1.0 / 1.4,
          1e-9)


def test_formschluss_meldung():
    """Was das Protokoll zur reibungsfreien Fuge sagt - Form statt Pauschale."""
    m = Model()
    kb = m.add_kontaktbedingung("Fuge")
    frei = DofBehaviour(typ="free")
    kn = DofBehaviour(typ="free", failure="druck")

    eben = [_facette(m, [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], (0, 0, 1))]
    log = []
    fugen._gleiten_melden(kb, kn, [frei, frei], 0.0, log, m, eben)
    text = " ".join(str(x) for x in log)
    check("ebene Fuge ohne Reibung: die Warnung bleibt",
          "frei gleiten" in text and "WARNUNG" in text.upper(), text[:90])

    m2 = Model()
    kb2 = m2.add_kontaktbedingung("Absatz")
    absatz = [
        _facette(m2, [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], (0, 0, 1)),
        _facette(m2, [(0, 0, 0), (0, 1, 0), (0, 1, 0.2), (0, 0, 0.2)], (-1, 0, 0)),
        _facette(m2, [(0, 0, 0), (1, 0, 0), (1, 0, 0.2), (0, 0, 0.2)], (0, -1, 0)),
    ]
    log2 = []
    fugen._gleiten_melden(kb2, kn, [frei, frei], 0.0, log2, m2, absatz)
    text2 = " ".join(str(x) for x in log2)
    check("Absatz ohne Reibung: kein Warnzeichen, sondern der Formschluss",
          "Form" in text2 and "kann nicht gleiten" in text2
          and "WARNUNG" not in text2.upper(), text2[:110])

    m3 = Model()
    kb3 = m3.add_kontaktbedingung("Nut")
    nut = [
        _facette(m3, [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], (0, 0, 1)),
        _facette(m3, [(0, 0, 0), (0, 1, 0), (0, 1, 0.2), (0, 0, 0.2)], (-1, 0, 0)),
    ]
    log3 = []
    fugen._gleiten_melden(kb3, kn, [frei, frei], 0.0, log3, m3, nut)
    text3 = " ".join(str(x) for x in log3)
    check("eine Flanke: hält in zwei Richtungen, die dritte wird benannt",
          "zwei Richtungen" in text3 and "Richtung y" in text3, text3[:130])

    log4 = []
    fugen._gleiten_melden(kb3, kn, [frei, frei], 0.3, log4, m3, nut)
    check("mit Reibung sagt die Meldung gar nichts", not log4, str(log4))


# --------------------------------------------------------------------------
# Ein Suchradius, deckungsgleiche Knoten, die Verteilung statt des Mittelwerts
# --------------------------------------------------------------------------
def test_ein_suchradius():
    """Modell und Protokoll nennen denselben Suchradius.

    Frueher stand im Kontaktpaar das Doppelte dessen, was das Protokoll
    nannte - 9 mm im Text, 18,5 mm im Modell, durchgaengig Faktor zwei. Der
    Loeser paarte damit Knoten, die weiter entfernt lagen als jede Facette,
    die zur Fuge gezaehlt worden war: am Beispielmodell an einer Fuge 213 von
    290 gepaarten Knoten mit mehr als 5 mm Spalt, der groesste 121 mm.
    """
    import re
    m = zwei_bloecke("eigene", h=0.25)
    kb = m.add_kontaktbedingung(
        "Fuge", flaechennamen=["FugeO"], gegenflaechen=["FugeU"], koerpernamen=["Oben"],
        behaviour={2: DofBehaviour("free", failure="zug")})
    log = []
    fugen.kontaktfuge_ausfuehren(m, kb, log)
    tr = re.search(r"Suchradius (\d+) mm", " ".join(log))
    r = float(m.contact_pairs[-1].search_radius)
    check("Protokoll und Modell nennen denselben Suchradius",
          tr is not None and abs(float(tr.group(1)) - r * 1e3) < 0.5,
          f"Protokoll {tr.group(1) if tr else '?'} mm, Modell {r * 1e3:.1f} mm")


def test_verteilung_statt_mittelwert():
    """Berichtet wird die Verteilung der Spaltmasse, nicht ihr Mittelwert.

    Die Verteilung an einer teilweise anliegenden Fuge ist zweigipflig: ein
    Teil liegt auf null, der Rest steht deutlich ab. Ein Mittelwert darueber
    beschreibt keinen Zustand - er nennt eine Zahl, die an keiner Stelle der
    Fuge vorkommt, und verdeckt, dass ein Teil gar nicht anliegt.
    """
    from statik3d.contact import verteilungstext
    w = np.array([0.0] * 61 + [0.040] * 39)
    t = verteilungstext(w, 0.0)
    close("der Mittelwert dieser Fuge waere", float(w.mean()), 0.0156, 1e-9, " m")
    check("genannt wird stattdessen der Anteil, der aufliegt",
          "61 % aufliegend" in t, t)
    check("der Median (0,00 mm), nicht der Mittelwert (15,60 mm)",
          "Median 0.00 mm" in t and "15.6" not in t, t)
    check("das 90. Perzentil und der größte Wert",
          "90 % unter 40.00 mm" in t and "größter 40.00 mm" in t, t)
    check("ohne Messwerte bleibt es bei einer klaren Auskunft",
          verteilungstext([], 0.0) == "kein Spalt gemessen", verteilungstext([], 0.0))

    m = zwei_bloecke("eigene", h=0.25)
    kb = m.add_kontaktbedingung(
        "Fuge", flaechennamen=["FugeO"], gegenflaechen=["FugeU"], koerpernamen=["Oben"],
        behaviour={2: DofBehaviour("free", failure="zug")})
    log = []
    fugen.kontaktfuge_ausfuehren(m, kb, log)
    zeile = next((z for z in log if "Kontaktpaar mit" in z), "")
    check("und dasselbe steht im Protokoll der Fuge",
          "aufliegend" in zeile and "90 % unter" in zeile and "im Mittel" not in zeile,
          zeile[:150])


def test_durchdringung_nicht_als_spalt():
    """Eine Durchdringung ist kein Spalt - das Protokoll nennt sie getrennt.

    Bis zum 15.09.2026 sammelten Kontaktaufbau und Fugensuche den
    **Betrag** des Abstands. Am Drehlager (gmsh-Netz) meldete die Zeile der
    Achse „Spalt 67 % aufliegend … größter 0.62 mm", obwohl an 207 Knoten die
    Achse bis 0,62 mm in der Buchse stak - und genau dort sassen die zwoelf
    groessten Knotenkraefte.
    """
    from scipy import sparse
    from statik3d.contact import ContactSystem, verteilungstext
    from statik3d.model import ContactPair
    t = verteilungstext([0.0, 0.0, 0.001, -0.0005, -0.0002], 1e-5)
    check("Verteilung: aufliegend, Spalt und Durchdringung getrennt",
          "40 % aufliegend" in t and "größter 1.00 mm" in t
          and "2 durchdringend, tiefste 0.50 mm" in t, t)
    check("ohne Durchdringung bleibt der Satz, wie er war",
          verteilungstext([0.0, 0.002], 1e-5) == "50 % aufliegend, Median 1.00 mm, 90 % unter 1.80 mm, "
                                                 "größter 2.00 mm", verteilungstext([0.0, 0.002], 1e-5))

    # Kontaktaufbau: ebene Master-Facette, ein Knoten 0,3 mm davor, zwei 0,5 mm dahinter
    m = Model()
    m.add_material(Material.steel("S235"))
    b = [int(m.add_node(*p_)) for p_ in [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]]
    s = [int(m.add_node(0.3, 0.5, 0.0003)), int(m.add_node(0.5, 0.5, -0.0005)),
         int(m.add_node(0.7, 0.5, -0.0005))]
    log = []
    m.contact_pairs.append(ContactPair("Eben", slave_nodes=s, master_faces=[b], search_radius=0.01))
    ContactSystem(m, sparse.identity(m.ndof, format="csr"), log)
    z = next((x for x in log if "Eben" in x), "")
    check("Kontaktaufbau: zwei Knoten durchdringen 0,5 mm, der Spalt ist 0,3 mm",
          "2 durchdringend, tiefste 0.50 mm" in z and "größter 0.30 mm" in z, z)

    # Fugensuche: die Gegenflaeche liegt 2 mm im Koerper der Kontaktseite
    m2 = Model()
    seite = [_facette(m2, [(0, 0, 0), (0, 0.1, 0), (0, 0.1, 0.1), (0, 0, 0.1)], (-1, 0, 0))]
    gegen = [_facette(m2, [(0.002, 0, 0), (0.002, 0.1, 0), (0.002, 0.1, 0.1), (0.002, 0, 0.1)], (1, 0, 0))]
    paare, abstand = fugen.gegenseite_finden(m2, seite, gegen, 0.05)
    close("Fugensuche: eine Durchdringung hat negativen Abstand", float(abstand[0]), -0.002, 1e-9, " m")
    check("… und wird trotzdem gepaart", paare == {0: 0}, str(paare))


def _mantelfacetten(m, r: float, n: int, h: float):
    """Ein n-Eck als Mantel: zwei Knotenringe, dazwischen n Vierecke."""
    w = 2.0 * np.pi * np.arange(n) / n
    unten = [int(m.add_node(r * np.cos(a), r * np.sin(a), 0.0)) for a in w]
    oben = [int(m.add_node(r * np.cos(a), r * np.sin(a), h)) for a in w]
    facetten = [[unten[i], unten[(i + 1) % n], oben[(i + 1) % n], oben[i]]
                for i in range(n)]
    return unten, oben, facetten


def test_deckungsgleiche_knoten_direkt():
    """Liegt ein Slave-Knoten auf einem Master-Knoten, wird nicht gesucht.

    Der Master ist dann dieser eine Knoten mit vollem Gewicht und der Spalt
    genau null - ohne Suche, ohne Projektion, wie in ANSYS. Was bleibt, ist
    die Richtung: sie aus einer der Facetten zu nehmen, die dort
    zusammenstossen, waere Zufall. An einem regelmaessigen n-Eck steht jede
    Facettennormale um pi/n neben der Flaechennormalen des Knotens - bei
    zwoelf Segmenten 15 Grad. Die flaechengewichtete Mittelung der Facetten
    trifft sie dagegen genau.
    """
    from scipy import sparse
    from statik3d.contact import ContactSystem
    from statik3d.model import ContactPair

    # 1) Ebene Fuge mit passenden Netzen: jeder Slave-Knoten liegt auf einem
    #    Master-Knoten
    m = zwei_bloecke("eigene", h=0.25)
    kb = m.add_kontaktbedingung(
        "Fuge", flaechennamen=["FugeO"], gegenflaechen=["FugeU"], koerpernamen=["Oben"],
        behaviour={2: DofBehaviour("free", failure="zug")})
    fugen.kontaktfuge_ausfuehren(m, kb, [])
    st = ContactSystem(m, sparse.identity(m.ndof, format="csr"))
    cons = [c for c in st.cons if c.kind == "surface"]
    einzeln = [c for c in cons if len(c.master[0]) == 1 and abs(c.master[1][0] - 1.0) < 1e-15]
    check("jeder deckungsgleiche Knoten haengt an genau einem Master",
          len(cons) > 0 and len(einzeln) == len(cons),
          f"{len(einzeln)} von {len(cons)} Bedingungen")
    check("der Anfangsspalt ist genau null - nicht fast null",
          all(c.g0 == 0.0 for c in cons),
          f"größter |g0| = {max((abs(c.g0) for c in cons), default=0.0):.1e} m")
    check("und die Richtung ist die Fugennormale",
          all(abs(abs(float(c.normal[2])) - 1.0) < 1e-12 for c in cons),
          f"kleinstes |n_z| = {min((abs(float(c.normal[2])) for c in cons), default=0.0):.12f}")

    # 2) Gekruemmter Master: die Facettennormale waere um pi/n daneben
    n = 12
    m2 = Model()
    m2.add_material(Material.steel("S235"))
    unten, oben, facetten = _mantelfacetten(m2, 0.5, n, 0.2)
    slave = [int(m2.add_node(*m2.nodes[k])) for k in unten]      # deckungsgleich
    m2.contact_pairs.append(ContactPair("Mantel", slave_nodes=slave,
                                        master_faces=facetten, search_radius=0.1))
    st2 = ContactSystem(m2, sparse.identity(m2.ndof, format="csr"))
    cons2 = [c for c in st2.cons if c.kind == "surface"]
    fehl = 0.0
    for c in cons2:
        p = m2.nodes[c.node]
        radial = np.array([p[0], p[1], 0.0])
        radial = radial / np.linalg.norm(radial)
        fehl = max(fehl, np.degrees(np.arccos(min(1.0, abs(float(c.normal @ radial))))))
    check("am Zwölfeck trifft die Richtung die Flächennormale des Knotens",
          len(cons2) == n and fehl < 1e-9,
          f"{len(cons2)} Bedingungen, größte Abweichung {fehl:.2e}° "
          f"(eine Facettennormale läge {180.0 / n:.0f}° daneben)")


def _kasten(m, x0, x1, y0, y1, z0, z1, name, h=0.1):
    """Ein Quader als eigener Koerper mit eigenen Flaechen, vernetzt."""
    i0 = m.nn
    m.add_nodes(np.array([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
                          [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]], float))
    b = Bauer(m)
    R = [[b.linie(i0 + o + i, i0 + o + (i + 1) % 4) for i in range(4)] for o in (0, 4)]
    V = [b.linie(i0 + i, i0 + i + 4) for i in range(4)]
    m.add_flaeche(f"{name}_B", R[0], material="S235")
    m.add_flaeche(f"{name}_D", R[1], material="S235")
    seiten = []
    for i in range(4):
        nm = f"{name}_M{i}"
        m.add_flaeche(nm, [R[0][i], V[(i + 1) % 4], R[1][i], V[i]], material="S235")
        seiten.append(nm)
    k = m.add_koerper(name, [f"{name}_B", f"{name}_D"] + seiten, material="S235")
    M3.mesh_koerper_frei(m, k, h=h, log=[], cache={})
    return k


def test_gegenseite_nur_im_genannten_bauteil():
    """Nennt die Bedingung die zugeordneten Flaechen der Gegenseite, so gehoert
    die Gegenseite **deren Bauteil** - nicht dem naechstbesten Teil daneben.

    Seit dem 15.09.2026 ist die Gegenseite sogar genau die genannten Flaechen
    (test_gegenseite_nur_auf_genannten_flaechen); das Bauteil folgt daraus.
    Ohne diese Schranke nimmt die Suche, was im Suchradius am naechsten liegt: am
    Drehlager hingen vier Knoten der Achse in der Fuge zur Buchse an einem
    Passstift und trugen unter Last 37 von 49 MN, 12,9 MN auf einem einzigen
    Knoten (14.09.2026).

    Das Modell stellt genau das nach: der obere Koerper steht ueber, und unter
    dem Ueberstand liegt ein Fremdteil, dessen Deckel die Fugenebene beruehrt.
    Fuer die ueberstehenden Facetten ist es die naechste Gegenflaeche
    ueberhaupt - die genannte Gegenflaeche reicht dort gar nicht hin.
    """
    m = Model()
    m.add_material(Material.steel("S235"))
    m.netz.ziellaenge = 0.5
    _kasten(m, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, "Unten", h=0.5)
    _kasten(m, 0.0, 1.4, 0.0, 1.0, 1.0, 2.0, "Oben", h=0.5)
    _kasten(m, 1.1, 1.3, 0.4, 0.6, 0.8, 1.0, "Stift", h=0.1)
    kb = m.add_kontaktbedingung("Fuge", flaechennamen=[], gegenflaechen=["Unten_D"],
                                koerpernamen=["Oben"],
                                behaviour={2: DofBehaviour("free", failure="zug")})
    log = []
    b = fugen.kontaktfuge_ausfuehren(m, kb, log)
    cp = m.contact_pairs[-1] if m.contact_pairs else None
    check("die Fuge wird als Kontaktpaar ausgeführt", b["kontaktpaar"] == 1, b.get("grund", ""))
    check("die Gegenseite ist das Bauteil der genannten Fläche - das Fremdteil gehört nicht dazu",
          cp is not None and cp.gegenkoerper == ["Unten"], str(cp.gegenkoerper if cp else None))
    gruppe = fugen.gruppen_je_knoten(m)
    fremd = [f for f in (cp.master_faces if cp else [])
             if any("Stift" in gruppe.get(int(n), set()) for n in f)]
    check("keine einzige Master-Facette stammt aus dem Fremdteil",
          not fremd, f"{len(fremd)} von {len(cp.master_faces) if cp else 0} Facetten")
    check("die Slave-Knoten liegen in der Fugenebene",
          cp is not None and all(abs(float(m.nodes[int(n)][2]) - 1.0) < 1e-9 for n in cp.slave_nodes),
          f"{len(cp.slave_nodes) if cp else 0} Knoten")


def test_gegenfacetten_folgen_dem_bauteil():
    """Loest eine spaetere Fuge das Bauteil, das eine fruehere als Gegenseite
    hat, muessen deren Gegenfacetten die neuen Knotennummern bekommen.

    Die Fuge verdoppelt die Knoten, die das geloeste Bauteil mit anderen
    teilt, und haengt **seine** Elemente an die Kopien. Ein Kontaktpaar, das
    vorher angelegt wurde, behielt die alten Nummern - und die gehoeren danach
    dem anderen Bauteil. Am Drehlager waren das 58 bis 73 Gegenfacetten in
    vier Fugen: „Deckel 2 (Typ 1)" lag mit Facetten wie [82528, 82529, 753]
    zur Haelfte auf der Achse V30 und zur anderen auf dem Passstift V101,
    nachdem „Achse (Typ 4)" die Achse von den Stiften geloest hatte; kein
    Element hatte diese Seite (15.09.2026).

    Modell (drei_bloecke): Fuge 1 loest Unten gegen FugeO - die Gegenfacetten
    liegen auf Oben, auch am Rand x = 1. Fuge 2 loest Oben von der Rippe, die
    mit Oben die Flaeche MO1 teilt; deren Unterkante ist genau dieser Rand.
    """
    m = drei_bloecke()
    zug = {2: DofBehaviour("free", failure="zug")}
    m.add_kontaktbedingung("Fuge", flaechennamen=["FugeU"], gegenflaechen=["FugeO"],
                           koerpernamen=["Unten"], behaviour=dict(zug))
    m.add_kontaktbedingung("Rippe", flaechennamen=["MO1"], koerpernamen=["Oben"],
                           behaviour=dict(zug))
    log = []
    g = fugen.kontaktfugen_ausfuehren(m, log)
    check("beide Fugen ausgeführt", g["fugen"] == 2 and not g["offen"], str(g))
    cp = next((c for c in m.contact_pairs if c.name == "Fuge"), None)
    check("Fuge 1 ist ein Kontaktpaar gegen Oben", cp is not None and cp.gegenkoerper == ["Oben"],
          str(cp.gegenkoerper if cp else None))
    seiten = {}
    for i, el in enumerate(m.elements):
        for n in el.nodes:
            seiten.setdefault(int(n), set()).add(i)

    def element_der(f):
        s = None
        for k in f:
            s = set(seiten.get(int(k), set())) if s is None else s & seiten.get(int(k), set())
        return s or set()

    getrennt = {int(k) for paar in m.getrennte_knoten.get("Rippe", []) for k in paar}
    am_rand = [f for f in (cp.master_faces if cp else []) if set(int(k) for k in f) & getrennt]
    check("Fuge 2 hat Knoten am Rand der Gegenfacetten von Fuge 1 verdoppelt",
          len(am_rand) > 0, f"{len(am_rand)} Gegenfacetten an verdoppelten Knoten")
    fremd = [f for f in (cp.master_faces if cp else [])
             if not any(m.elements[e].group == "Oben" for e in element_der(f))]
    check("jede Gegenfacette von Fuge 1 ist danach eine Seite eines Elements von Oben",
          cp is not None and not fremd,
          f"{len(fremd)} von {len(cp.master_faces) if cp else 0} ohne Element von Oben, z. B. "
          f"{[sorted(int(k) for k in f) for f in fremd[:2]]}")
    check("das Protokoll sagt, dass Gegenfacetten mitgenommen wurden",
          any("Gegenfacetten" in z and "mitgenommen" in z for z in log), "; ".join(log)[-160:])


def _zweigeteilt(m, name, h):
    """Quader 0..2 x 0..1 x 0..1, dessen Oberseite aus **zwei** Flaechen besteht
    (``_D1`` bis x = 1, ``_D2`` ab x = 1) - ein Bauteil, zwei Kontaktflaechen."""
    i0 = m.nn
    m.add_nodes(np.array([(x, y, z) for z in (0.0, 1.0) for y in (0.0, 1.0)
                          for x in (0.0, 1.0, 2.0)], float))

    def k(x, y, z):
        return i0 + z * 6 + y * 3 + x

    linien: dict = {}

    def li(a, c):
        key = tuple(sorted((a, c)))
        if key not in linien:
            linien[key] = f"{name}_L{len(linien)}"
            m.add_line(linien[key], [a, c], "polyline")
        return linien[key]

    def flaeche(nm, ring):
        m.add_flaeche(nm, [li(ring[i], ring[(i + 1) % len(ring)]) for i in range(len(ring))],
                      material="S235")
        return nm

    namen = [
        flaeche(f"{name}_B", [k(0, 0, 0), k(1, 0, 0), k(2, 0, 0), k(2, 1, 0), k(1, 1, 0), k(0, 1, 0)]),
        flaeche(f"{name}_D1", [k(0, 0, 1), k(1, 0, 1), k(1, 1, 1), k(0, 1, 1)]),
        flaeche(f"{name}_D2", [k(1, 0, 1), k(2, 0, 1), k(2, 1, 1), k(1, 1, 1)]),
        flaeche(f"{name}_V", [k(0, 0, 0), k(1, 0, 0), k(2, 0, 0), k(2, 0, 1), k(1, 0, 1), k(0, 0, 1)]),
        flaeche(f"{name}_H", [k(0, 1, 0), k(1, 1, 0), k(2, 1, 0), k(2, 1, 1), k(1, 1, 1), k(0, 1, 1)]),
        flaeche(f"{name}_L", [k(0, 0, 0), k(0, 1, 0), k(0, 1, 1), k(0, 0, 1)]),
        flaeche(f"{name}_R", [k(2, 0, 0), k(2, 1, 0), k(2, 1, 1), k(2, 0, 1)]),
    ]
    kp = m.add_koerper(name, namen, material="S235")
    M3.mesh_koerper_frei(m, kp, h=h, log=[], cache={})
    return kp


def test_gegenseite_nur_auf_genannten_flaechen():
    """Nennt die Kontaktbedingung Gegenflaechen, ist die Gegenseite **genau
    diese** - nicht jede Flaeche ihres Bauteils, die im Suchradius liegt.

    Bis zum 15.09.2026 wurde im Bauteil der genannten Flaechen geometrisch
    gesucht, weil die Liste als unvollstaendig galt. Am Drehlager deckten die
    genannten Flaechen aber jede der zwoelf Fugen zu 90,6 bis 100 %, und was
    ausserhalb trug, lag auf Nachbarflaechen: in „Achse (Typ 3)" 109 kN auf
    den Bohrungsstreifen F319/F320/F587/F588 neben den genannten
    F304/F305/F589/F590 („strikt auf die genannten Gegenflächen begrenzen").

    Das Modell: das Unterteil hat eine zweigeteilte Oberseite, genannt ist nur
    die linke Haelfte D1; das Oberteil liegt auf beiden. Vorher lagen 30 von 57
    Gegenfacetten auf D2.
    """
    from scipy import sparse
    from statik3d.assemble import SOLID_FACES
    from statik3d.contact import ContactSystem
    m = Model()
    m.add_material(Material.steel("S235"))
    m.netz.ziellaenge = 0.25
    _zweigeteilt(m, "Unten", 0.25)
    _kasten(m, 0.0, 2.0, 0.0, 1.0, 1.0, 2.0, "Oben", h=0.25)

    def facetten(fn):
        out = set()
        for e, j in m.flaechen[fn].randseiten:
            el = m.elements[int(e)]
            out.add(frozenset(int(el.nodes[i]) for i in SOLID_FACES[el.typ][int(j)]))
        return out

    d1, d2 = facetten("Unten_D1"), facetten("Unten_D2")
    kb = m.add_kontaktbedingung("Fuge", flaechennamen=["Oben_B"], gegenflaechen=["Unten_D1"],
                                koerpernamen=["Oben"],
                                behaviour={2: DofBehaviour("free", failure="zug")})
    b = fugen.kontaktfuge_ausfuehren(m, kb, [])
    cp = m.contact_pairs[-1] if m.contact_pairs else None
    check("die Fuge wird als Kontaktpaar ausgeführt", b["kontaktpaar"] == 1 and cp is not None,
          b.get("grund", ""))
    master = [frozenset(int(x) for x in f) for f in (cp.master_faces if cp else [])]
    check("jede Gegenfacette liegt auf der genannten Fläche D1, keine auf der Nachbarfläche D2",
          master and all(f in d1 for f in master) and not any(f in d2 for f in master),
          f"{sum(1 for f in master if f in d1)} auf D1, {sum(1 for f in master if f in d2)} auf D2, "
          f"von {len(master)}")
    st = ContactSystem(m, sparse.identity(m.ndof, format="csr"))
    bed = {int(c.node) for c in st.cons if c.kind == "surface"}
    x = {int(s): float(m.nodes[int(s)][0]) for s in (cp.slave_nodes if cp else [])}
    ueber_d1 = [s for s, xs in x.items() if xs <= 1.0 + 1e-9]
    ueber_d2 = [s for s, xs in x.items() if xs > 1.0 + 1e-9]
    check("über D1 trägt jeder Knoten des Oberteils, bis zur Grenze x = 1",
          ueber_d1 and all(s in bed for s in ueber_d1),
          f"{sum(1 for s in ueber_d1 if s in bed)} von {len(ueber_d1)}")
    check("über D2 keiner - dort ist keine Kontaktfläche genannt",
          not any(s in bed for s in ueber_d2),
          f"{sum(1 for s in ueber_d2 if s in bed)} von {len(ueber_d2)} gepaart")


def test_facettenspalt_bereinigt():
    """Der Spalt zaehlt zur wahren Flaeche, nicht zur Sehne der Facette.

    Eine passgenaue Achse (40 Knoten am Umfang) in einer Bohrung aus 36
    Facetten (r = 300 mm, Sehne 52 mm, Pfeilhoehe 1,1 mm - das Netz der
    Augenbleche des Drehlagers): nur die acht Knoten auf einer Ecke der
    Bohrung lagen vorher an, die uebrigen standen um die Pfeilhoehe "offen",
    und weil sie hinter der Sehne liegen, mit umgekehrter Normale (ins
    Blech). Am Drehlager trug die Achse so auf 27 von 1194 Knoten, mit
    387 kN auf einem einzigen (13.09.2026). Jetzt liegen alle an, jede
    Normale zeigt in die Achse. Ebene Facetten bleiben, wie sie sind: eine
    Kante wird nicht verrundet, ein Spalt ueber dem Beruehrungsband bleibt
    offen, eine Durchdringung ist eine Durchdringung - nur eine Schale hat
    kein Innen und richtet ihre Normale zum Knoten.
    """
    from scipy import sparse
    from statik3d.contact import ContactSystem, Flaechenquadriken, facetten_felder
    from statik3d.model import ContactPair, ShellProp

    # 1) Passgenaue Achse in der Bohrung
    r, n_b, n_a, h = 0.300, 36, 40, 0.1
    m = Model()
    m.add_material(Material.steel("S235"))
    _u, _o, facetten = _mantelfacetten(m, r, n_b, h)
    bohrung = [[f[1], f[0], f[3], f[2]] for f in facetten]     # Umlauf umgekehrt: Normale zur Achse hin
    wa = 2.0 * np.pi * np.arange(n_a) / n_a
    achse = [int(m.add_node(r * np.cos(a), r * np.sin(a), z)) for z in (0.0, h) for a in wa]
    m.contact_pairs.append(ContactPair("Achse", slave_nodes=achse, master_faces=bohrung,
                                       search_radius=0.1))
    log = []
    st = ContactSystem(m, sparse.identity(m.ndof, format="csr"), log)
    cons = [c for c in st.cons if c.kind == "surface"]
    deck = [c for c in cons if len(c.master[0]) == 1]
    check("jeder Achsknoten ist gepaart, acht davon liegen auf einer Ecke der Bohrung",
          len(cons) == 2 * n_a and len(deck) == 8,
          f"{len(cons)} Bedingungen, {len(deck)} deckungsgleich")
    check("alle liegen an: Anfangsspalt genau null, auch zwischen den Ecken (Pfeilhöhe 1,1 mm)",
          all(c.g0 == 0.0 for c in cons),
          f"größter |g0| = {max(abs(c.g0) for c in cons):.2e} m, "
          f"{sum(1 for c in cons if c.g0 == 0.0)} von {len(cons)} auf null")
    schief = -1.0
    for c in cons:
        p_ = m.nodes[c.node]
        e_r = np.array([p_[0], p_[1], 0.0]) / np.hypot(p_[0], p_[1])
        schief = max(schief, float(c.normal @ e_r))      # < 0: zur Achse hin
    check("und jede Normale zeigt in die Achse hinein, nicht ins Blech",
          schief < -0.999, f"größtes n·e_r = {schief:.4f}")
    check("das Protokoll nennt alle Knoten aufliegend",
          any("Achse" in z and "100 % aufliegend" in z for z in log),
          "; ".join(z for z in log if "Achse" in z)[:120])
    # die Naeherung selbst: die Sehnenmitte kommt auf den Kreis
    K4, g = facetten_felder(bohrung)
    Q = Flaechenquadriken(m.nodes, K4, g)
    mitte = m.nodes[bohrung[0]].mean(axis=0)
    qs, ns_ = Q.punkt(mitte, 0)
    close("die Sehnenmitte der Bohrung kommt auf den Kreis (Pfeilhöhe 1,14 mm, Rest unter 5 µm)",
          float(np.hypot(qs[0, 0], qs[0, 1])), r, 5e-6, " m")
    close("… und die Sehne lag um die Pfeilhöhe innen",
          float(np.hypot(mitte[0], mitte[1])), r * np.cos(np.pi / n_b), 1e-12, " m")

    # 2) Ebene Facetten bleiben, wie sie sind
    m2 = Model()
    m2.add_material(Material.steel("S235"))
    b = [int(m2.add_node(*p_)) for p_ in [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
                                          (1, 0, 1), (1, 1, 1)]]
    boden = [b[0], b[1], b[2], b[3]]                    # Normale +z
    wand = [b[1], b[4], b[5], b[2]]                     # x = 1, Normale -x (zur Ecke hin)
    lage = {"ecke": (0.95, 0.5, 0.001), "band": (0.5, 0.5, 0.00005),
            "offen": (0.5, 0.5, 0.0005), "hinter": (0.5, 0.5, -0.01)}
    ids = {k: int(m2.add_node(*v)) for k, v in lage.items()}
    m2.contact_pairs.append(ContactPair("Eben", slave_nodes=list(ids.values()),
                                        master_faces=[boden, wand], search_radius=0.1))
    st2 = ContactSystem(m2, sparse.identity(m2.ndof, format="csr"))
    von = {int(c.node): c for c in st2.cons if c.kind == "surface"}
    c = von[ids["ecke"]]
    check("an einer Kante wird nicht verrundet: 1 mm über dem Boden neben der Wand bleiben 1 mm, Normale +z",
          abs(c.g0 - 0.001) < 1e-9 and abs(c.normal[2] - 1.0) < 1e-12,
          f"g0 = {c.g0 * 1e3:.6f} mm, n = {np.round(c.normal, 6).tolist()}")
    c = von[ids["band"]]
    check("0,05 mm über dem Boden liegen im Berührungsband (ein Tausendstel des Suchradius): Spalt null",
          c.g0 == 0.0, f"g0 = {c.g0:.2e} m")
    c = von[ids["offen"]]
    check("0,5 mm bleiben offen", abs(c.g0 - 0.0005) < 1e-12, f"g0 = {c.g0 * 1e3:.4f} mm")
    c = von[ids["hinter"]]
    check("10 mm hinter der Facette sind eine Durchdringung - kein Spalt mit umgekehrter Normale",
          abs(c.g0 + 0.01) < 1e-12 and abs(c.normal[2] - 1.0) < 1e-12,
          f"g0 = {c.g0 * 1e3:.3f} mm, n_z = {c.normal[2]:+.3f}")

    # 3) Eine Schale hat kein Innen: die Normale zeigt zum Slave-Knoten
    m3 = Model()
    m3.add_material(Material.steel("S235"))
    m3.add_shell_prop(ShellProp("t", 0.01))
    sh = [int(m3.add_node(*p_)) for p_ in [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]]
    e = m3.add_element("shell4", sh, "S235", "t")
    unter = int(m3.add_node(0.5, 0.5, -0.01))
    m3.contact_pairs.append(ContactPair("Schale", slave_nodes=[unter], master_elements=[e],
                                        search_radius=0.1))
    st3 = ContactSystem(m3, sparse.identity(m3.ndof, format="csr"))
    cs3 = [c for c in st3.cons if c.kind == "surface"]
    check("unter einer Schale: Spalt 10 mm, Normale zum Knoten hin (-z)",
          len(cs3) == 1 and abs(cs3[0].g0 - 0.01) < 1e-12 and abs(cs3[0].normal[2] + 1.0) < 1e-12,
          f"{len(cs3)} Bedingungen" + (f", g0 = {cs3[0].g0 * 1e3:.3f} mm, n_z = {cs3[0].normal[2]:+.3f}" if cs3 else ""))


def test_kontakt_nur_auf_der_gegenflaeche():
    """Kontakt wirkt nur, wo die Gegenflaeche gegenuebersteht - ausserhalb nie.

    Bis zum 15.09.2026 durfte ein Knoten der Kontaktseite so weit neben seiner
    Gegenfacette liegen, wie deren Umkreis misst. Die Regel stammt von der
    Suche der Gegenseite, wo sie Facetten meint, die zur Haelfte ueber eine
    Kante ragen; fuer einen Knoten heisst sie: Kontakt jenseits des
    Flaechenrands. Am Drehlager trugen so Knoten der Achse bis 25 mm hinter dem
    Ende der Buchse V29 (1982 kN) und 8 mm hinter dem Ende von V16 (903 kN),
    und am Montageauge der Lochrand 3 mm hinter dem Passstiftende 708 kN auf
    einem Knoten („außerhalb der Flächen darf nie ein Kontakt wirken").

    Jetzt bekommt ein Knoten nur eine Facette, auf die er senkrecht faellt.
    Nachgelassen wird die Rundung und - an einer glatten Kante zwischen zwei
    Facetten bis zum Knickwinkel - der Kegel, den ein abstehender Knoten dort
    ueberstreicht. Geprueft an einer ebenen Flaeche und als Stichprobe an
    Achse und Bohrung ueber Facettenzahl, Versatz, Spiel und beide Seiten als
    Gegenflaeche: jeder Knoten ueber der Flaeche ist gepaart, auch auf ihrem
    Rand, keiner daneben.
    """
    from scipy import sparse
    from statik3d.contact import ContactSystem
    from statik3d.model import ContactPair

    # 1) Eben: Gegenflaeche 100 x 100 mm aus 10-mm-Vierecken, die Kontaktseite
    #    reicht im 2,5-mm-Raster bis 130 mm, anliegend und 0,3 mm abstehend
    m = Model()
    m.add_material(Material.steel("S235"))
    g = {(i, j): int(m.add_node(0.01 * i, 0.01 * j, 0.0)) for i in range(11) for j in range(11)}
    master = [[g[i, j], g[i + 1, j], g[i + 1, j + 1], g[i, j + 1]] for i in range(10) for j in range(10)]
    lage = {}
    for i in range(53):
        for y in (0.0025, 0.0525):
            for z in (0.0, 0.0003):
                lage[int(m.add_node(0.0025 * i, y, z))] = 0.0025 * i
    log = []
    m.contact_pairs.append(ContactPair("Eben", slave_nodes=list(lage), master_faces=master,
                                       search_radius=0.05))
    st = ContactSystem(m, sparse.identity(m.ndof, format="csr"), log)
    bed = {int(c.node) for c in st.cons if c.kind == "surface"}
    ueber = [k for k, x in lage.items() if x <= 0.1 + 1e-9]
    neben = [k for k, x in lage.items() if x > 0.1 + 1e-9]
    check("eben: jeder Knoten über der Fläche ist gepaart, auch auf ihrem Rand (x = 100 mm)",
          all(k in bed for k in ueber), f"{sum(1 for k in ueber if k in bed)} von {len(ueber)}")
    check("… und keiner daneben: 2,5 bis 30 mm hinter dem Rand trägt nichts",
          not any(k in bed for k in neben),
          f"{sum(1 for k in neben if k in bed)} von {len(neben)} gepaart, "
          f"der weiteste bei x = {max([lage[k] for k in neben if k in bed], default=0) * 1e3:.1f} mm")
    check("das Protokoll sagt, wie viele neben der Gegenfläche liegen",
          any("neben der Gegenfläche" in z and f"{len(neben)} " in z for z in log),
          "; ".join(log)[:160])

    # 2) Achse ueber die Bohrung hinaus - Stichprobe
    r, h, schritt = 0.300, 0.100, 0.010
    fehler = []
    faelle = 0
    for n_b in (16, 24, 36):
        for n_a in (40, 57):
            for versatz in (0.0, 0.37):
                for spiel in (0.0, 0.0005):
                    for gegen in ("Bohrung", "Achse"):
                        mz = Model()
                        mz.add_material(Material.steel("S235"))
                        _u, _o, fac = _mantelfacetten(mz, r, n_b, h)
                        if gegen == "Bohrung":
                            fac = [[f[1], f[0], f[3], f[2]] for f in fac]   # Normale zur Achse hin
                            r_s = r - spiel
                        else:
                            r_s = r + spiel                                # Knoten der Bohrung aussen
                        wa = 2.0 * np.pi * (np.arange(n_a) + versatz) / n_a
                        z_s = {}
                        for k in range(-3, 14):
                            z = k * h / 10
                            for a in wa:
                                z_s[int(mz.add_node(r_s * np.cos(a), r_s * np.sin(a), z))] = z
                        mz.contact_pairs.append(ContactPair("Fuge", slave_nodes=list(z_s),
                                                            master_faces=fac, search_radius=0.1))
                        stz = ContactSystem(mz, sparse.identity(mz.ndof, format="csr"))
                        bz = {int(c.node) for c in stz.cons if c.kind == "surface"}
                        drin = [k for k, z in z_s.items() if -1e-9 <= z <= h + 1e-9]
                        aus = [k for k, z in z_s.items() if not -1e-9 <= z <= h + 1e-9]
                        faelle += 1
                        fehlt = sum(1 for k in drin if k not in bz)
                        zuviel = sum(1 for k in aus if k in bz)
                        if fehlt or zuviel:
                            fehler.append(f"{n_b}-Eck, {n_a} Knoten, Versatz {versatz}, Spiel {spiel * 1e3:g} mm, "
                                          f"Gegenfläche {gegen}: {fehlt} fehlen, {zuviel} daneben")
    check(f"Achse und Bohrung, {faelle} Fälle (16/24/36 Facetten, 40/57 Knoten, Versatz, Spiel 0/0,5 mm, "
          "beide Seiten als Gegenfläche): über der Bohrung alle gepaart, 10 bis 30 mm dahinter keiner",
          not fehler, "; ".join(fehler[:3]))


def _mantelnetz(rng, r, h, art):
    """Ein Stueck Zylindermantel r, unregelmaessig aus Dreiecken vernetzt.

    art "gitter": gleichmaessige Winkelteilung h/r, laengs unregelmaessig
    0,2..0,45 h, jedes Viereck ueber eine zufaellige Diagonale geteilt - so
    vernetzt gmsh die Bohrungen des Drehlagers (9,47 Grad, 10,7 mm laengs).
    art "frei": ein um 30 % verwackeltes Gitter mit Kante h, Delaunay - die
    Dreiecke stehen schief zur Achse.
    Rueckgabe (Winkel, Hoehe) je Knoten und die Dreiecke als Indizes.
    """
    from scipy.spatial import Delaunay
    bogen, laenge = 8 * h / r, 6 * h
    if art == "gitter":
        th = np.linspace(0.0, bogen, 9)
        y = [0.0]
        while y[-1] < laenge - 0.45 * h:
            y.append(y[-1] + rng.uniform(0.2, 0.45) * h)
        y = np.array(y + [laenge])
        pts = np.array([(a, b) for a in th for b in y])
        k = lambda i, j: i * len(y) + j                                  # noqa: E731
        tri = []
        for i in range(len(th) - 1):
            for j in range(len(y) - 1):
                a, b, c, d = k(i, j), k(i + 1, j), k(i + 1, j + 1), k(i, j + 1)
                tri += ([(a, b, c), (a, c, d)] if rng.random() < 0.5 else [(a, b, d), (b, c, d)])
        return pts, np.array(tri), laenge, bogen
    n_t, n_y = int(round(bogen * r / h)) + 1, int(round(laenge / h)) + 1
    tt, yy = np.meshgrid(np.linspace(0, bogen, n_t), np.linspace(0, laenge, n_y), indexing="ij")
    tt = tt + rng.uniform(-0.3, 0.3, tt.shape) * bogen / (n_t - 1)
    yy = yy + rng.uniform(-0.3, 0.3, yy.shape) * laenge / (n_y - 1)
    tt[0], tt[-1], yy[:, 0], yy[:, -1] = 0.0, bogen, 0.0, laenge
    pts = np.column_stack([tt.ravel(), yy.ravel()])
    return pts, Delaunay(np.column_stack([pts[:, 0] * r, pts[:, 1]])).simplices, laenge, bogen


def test_facettenspalt_unregelmaessig():
    """Eine passgenaue Achse in einer **unregelmaessig** aus Dreiecken
    vernetzten Bohrung liegt ueberall an - die wahre Flaeche hinter den
    Facetten trifft den Kreis auf 1 µm.

    test_facettenspalt_bereinigt prueft den regelmaessigen Fall (Vierecke
    zwischen zwei Knotenringen). Am Drehlager mit gmsh-Netz (Bohrung V16,
    r = 302 mm, 51-mm-Kanten) lieferte der Kontaktaufbau trotzdem an 207 von
    550 Bedingungen g0 von -51 bis -618 µm: die Stuetzpunkte der allgemeinen
    Quadrik lagen auf vier gleichmaessig verteilten Winkellagen, symmetrisch
    zur Facette - dort ist z^2 (gerade in x) von 1 und x^2 nicht zu
    unterscheiden. Die Spaltenmatrix hatte die Kondition 1e14, galt dem
    Rangtest aber als voll, und zwischen den Stuetzpunkten lag die Flaeche bis
    0,68 mm daneben; 49 statt 179 Knoten trugen, einer 1289 kN. Schiefe
    Dreiecke (die Achse liegt nicht in der Facettenebene) liessen zudem 20 µm,
    weil die Glieder x z und y z fehlten.

    Stichprobe: Gitter wie gmsh und verwackeltes Delaunay-Netz, Bohrung und
    Achse als Gegenflaeche, Radien 150 bis 1000 mm, Netzweiten 20 und 50 mm,
    je drei Zufallsnetze; die Knoten der Gegenflaeche um 0,01 µm radial
    gerundet (ohne Rundung entscheidet der Zufall der Gleitkommarechnung, ob
    der Rangtest die unbestimmte Quadrik annimmt).
    """
    from scipy import sparse
    from statik3d.contact import ContactSystem, Flaechenquadriken, facetten_felder
    from statik3d.model import ContactPair
    schlimmste, ueber, faelle, durchdringend = (0.0, ""), 0, 0, 0
    for art in ("gitter", "frei"):
        for gegen in ("Bohrung", "Achse"):
            for r, h in ((0.15, 0.02), (0.302, 0.02), (0.302, 0.05), (0.6, 0.05), (1.0, 0.05)):
                for seed in range(3):
                    rng = np.random.default_rng(seed)
                    pts, tri, laenge, bogen = _mantelnetz(rng, r, h, art)
                    m = Model()
                    m.add_material(Material.steel("S235"))
                    rr = r + rng.uniform(-1e-11, 1e-11, len(pts))
                    ids = [int(m.add_node(ri * np.cos(a), y, ri * np.sin(a))) for (a, y), ri in zip(pts, rr)]
                    faces = []
                    for a, b, c in tri:
                        f = [ids[a], ids[b], ids[c]]
                        P = m.nodes[f]
                        aussen = float(np.cross(P[1] - P[0], P[2] - P[0]) @ (P.mean(axis=0) * [1, 0, 1])) > 0
                        faces.append(f if aussen == (gegen == "Achse") else f[::-1])
                    # 1) die wahre Flaeche an Zufallspunkten der inneren Facetten
                    K4, g = facetten_felder(faces)
                    Q = Flaechenquadriken(m.nodes, K4, g)
                    innen = [i for i, f in enumerate(faces)
                             if np.all(np.abs(pts[[ids.index(k) for k in f], 0] - bogen / 2) < 0.3 * bogen)
                             and np.all(np.abs(pts[[ids.index(k) for k in f], 1] - laenge / 2) < 0.3 * laenge)]
                    w = rng.dirichlet([1, 1, 1], (len(innen), 3))
                    E = m.nodes[np.array([faces[i] for i in innen])]
                    q = np.einsum("fkj,fjd->fkd", w, E).reshape(-1, 3)
                    qs, _ns = Q.punkt(q, np.repeat(innen, 3))
                    fehler = float(np.abs(np.hypot(qs[:, 0], qs[:, 2]) - r).max())
                    faelle += 1
                    ueber += int(fehler > 1e-6)
                    if fehler > schlimmste[0]:
                        schlimmste = (fehler, f"{art}, {gegen}, r {r * 1e3:.0f} mm, h {h * 1e3:.0f} mm, Netz {seed}")
                    # 2) der Kontaktaufbau meldet keine Durchdringung
                    wa = rng.uniform(0.3, 0.7, 60) * bogen
                    ya = rng.uniform(0.3, 0.7, 60) * laenge
                    slave = [int(m.add_node(r * np.cos(a), y, r * np.sin(a))) for a, y in zip(wa, ya)]
                    m.contact_pairs.append(ContactPair("F", slave_nodes=slave, master_faces=faces,
                                                       search_radius=0.005))
                    log = []
                    ContactSystem(m, sparse.identity(m.ndof, format="csr"), log)
                    durchdringend += int(any("durchdringend" in z for z in log))
    check(f"unregelmäßige Bohrung, {faelle} Fälle: die wahre Fläche trifft den Kreis auf 1 µm",
          ueber == 0, f"größter Fehler {schlimmste[0] * 1e6:.2f} µm ({schlimmste[1]}), über 1 µm in {ueber} Fällen")
    check("… und der Kontaktaufbau meldet für die passgenaue Achse keine Durchdringung",
          durchdringend == 0, f"in {durchdringend} von {faelle} Fällen")


def _zwei_prismen(n=5, r=0.30, dick=0.30, klein=0.05):
    """Zwei Fuenfeckprismen uebereinander mit **einer** gemeinsamen Flaeche.

    Fuenfeckig, damit der abgebildete Vernetzer nicht greift: es geht durch
    den freien Weg - denselben, den ein importiertes Volumenmodell nimmt.
    """
    m = Model("Fuge")
    m.add_material(Material.steel("S235"))
    m.netz.ziellaenge = 0.10
    # Der freie Weg ist der Gegenstand: ein Prisma waere sonst sweepbar
    # (statik3d.sweep, 20.09.2026) und bekaeme Hexaeder und Keile
    m.netz.sweep = False
    w = np.linspace(0, 2 * np.pi, n, endpoint=False)
    P = np.column_stack([r * np.cos(w), r * np.sin(w)])
    idx = []
    for z in (0.0, dick, dick + klein):
        i0 = m.nn
        m.add_nodes(np.column_stack([P, np.full(n, z)]))
        idx.append(i0)
    ringe = [[m.add_line(f"R{L}_{i}", [i0 + i, i0 + (i + 1) % n]).name for i in range(n)]
             for L, i0 in enumerate(idx)]
    senk = [[m.add_line(f"S{L}_{i}", [idx[L] + i, idx[L + 1] + i]).name for i in range(n)]
            for L in range(2)]
    m.add_flaeche("Boden", ringe[0], material="S235")
    m.add_flaeche("Fuge", ringe[1], material="S235")
    m.add_flaeche("Dach", ringe[2], material="S235")
    seiten = [[], []]
    for L in range(2):
        for i in range(n):
            nm = f"M{L}_{i}"
            m.add_flaeche(nm, [ringe[L][i], senk[L][(i + 1) % n], ringe[L + 1][i], senk[L][i]],
                          material="S235")
            seiten[L].append(nm)
    m.add_koerper("V_unten", ["Boden", "Fuge"] + seiten[0], material="S235")
    m.add_koerper("V_oben", ["Fuge", "Dach"] + seiten[1], material="S235")
    return m


def _fugenknoten(m, a="V_unten", b="V_oben"):
    """(auf der Fuge, davon geteilt, doppelt, haengend) - wie die Abnahme misst."""
    from statik3d.assemble import SOLID_FACES
    from scipy.spatial import cKDTree
    from statik3d import diagnose as D
    ra = D._freie_seiten_des_koerpers(m, m.koerper[a], SOLID_FACES)
    rb = D._freie_seiten_des_koerpers(m, m.koerper[b], SOLID_FACES)
    if ra is None or rb is None:
        return 0, 0, 0, 0
    N = np.asarray(m.nodes, float)
    ia, _ = ra
    ib, Tb = rb
    d = np.asarray(M3.abstand_zur_huelle(N[ia], N, Tb))
    auf = ia[d < 1e-5]
    if not len(auf):
        return 0, 0, 0, 0
    setb = set(int(x) for x in ib)
    gleich = np.array([int(i) in setb for i in auf])
    dk, _ = cKDTree(N[ib]).query(N[auf])
    return (len(auf), int(gleich.sum()),
            int(((~gleich) & (dk < 1e-6)).sum()),
            int(((~gleich) & (dk >= 1e-6)).sum()))


def test_gemeinsame_flaeche_konform():
    """Zwei Koerper mit derselben Randflaeche muessen dort **dieselben**
    Knoten benutzen - sonst stehen sie unverbunden nebeneinander, das Netz
    sieht von aussen tadellos aus, und keine Kraft geht hinueber.

    Zwei Wege, auf denen das schiefging, beide hier nachgebaut:

    * **Die Reihenfolge der Randflaechen.** Der Knoten-Cache schluesselte
      ueber „die erste Flaeche, die den Punkt benutzt". Ein Punkt auf einer
      gemeinsamen **Randlinie** gehoert aber zu mehreren Flaechen des
      Koerpers, und welche die erste ist, entscheidet die Reihenfolge der
      Liste - beim Import eine beliebige. Geschluesselt wird jetzt nach der
      **Herkunft** des Punktes (Linie und Nummer, Ecke nach ihrem Knoten).
    * **Verschiedene Kantenlaengen.** Jeder Koerper bildete seine Teilung
      selbst; wandte nur einer sein Dickenmass an, teilte er die gemeinsame
      Linie feiner als der Nachbar. Die Karten gelten jetzt modellweit und
      binden bei gemeinsamen Flaechen und Linien - der parallele Pfad bekommt
      sie mit.
    """
    from statik3d import diagnose as D
    from statik3d import mesher as MSH
    for titel, mach in (("Flächenreihenfolge", "reihenfolge"), ("verschiedene h", "dicke")):
        m = _zwei_prismen()
        if mach == "reihenfolge":
            k = m.koerper["V_oben"]
            k.flaechen = [f for f in k.flaechen if f.startswith("M")] + ["Fuge", "Dach"]
        else:
            m.netz.dickenmass = True
        MSH.koerper_vernetzen(m, list(m.koerper.values()), log=[], workers=2)
        auf, gleich, doppelt, haengend = _fugenknoten(m)
        check(f"{titel}: die Fuge trägt Knoten", auf > 10, f"{auf} Knoten")
        check(f"{titel}: alle Fugenknoten sind geteilt", gleich == auf,
              f"{gleich} von {auf}")
        check(f"{titel}: keine doppelten, keine hängenden", doppelt == 0 and haengend == 0,
              f"{doppelt} doppelt, {haengend} hängend")
        check(f"{titel}: die Abnahme meldet nichts",
              not [b for b in D.abnahme(m) if b.pruefung == "gemeinsame Fläche"])

    # Gegenproben - ohne sie pruefte der Test nichts: er liefe auch gruen,
    # wenn beide Ursachen zurueckkaemen. Sie tauschen Funktionen im Modul
    # aus, und das erreicht nur den eigenen Prozess: unter Windows startet
    # der Parallelbetrieb seine Arbeitsprozesse mit spawn und importiert das
    # Modul dort unveraendert (unter Linux erbt fork den Austausch - dort
    # fiel es nicht auf). Darum laeuft die erste Gegenprobe seriell,
    # workers=1: ihr Austausch (randschale) wirkt im Arbeitsprozess. Die
    # zweite bleibt parallel, workers=2: ihr Austausch (netzkarten) wirkt im
    # Hauptprozess, und nur im parallelen Pfad teilt jeder Koerper fuer sich
    # - seriell teilen beide ueber denselben Zwischenspeicher, und der
    # Befund traete gar nicht auf (0 haengende Knoten).
    m = _zwei_prismen()
    k = m.koerper["V_oben"]
    k.flaechen = [f for f in k.flaechen if f.startswith("M")] + ["Fuge", "Dach"]
    echt = M3.randschale
    def ohne_kennung(*a, **kw):
        P, T, b = echt(*a, **kw)
        b = dict(b); b["kennung"] = []          # wie vor dem 09.09.2026
        return P, T, b
    M3.randschale = ohne_kennung
    try:
        MSH.koerper_vernetzen(m, list(m.koerper.values()), log=[], workers=1)
    finally:
        M3.randschale = echt
    _auf, _gl, doppelt, _h = _fugenknoten(m)
    check("ohne die Herkunft wären die Knoten doppelt - der Test greift",
          doppelt > 0, f"{doppelt} doppelte Knoten")

    m = _zwei_prismen()
    m.netz.dickenmass = True
    echt_k = MSH.netzkarten
    MSH.netzkarten = lambda model, h=0.0: ({}, {}, None)   # wie vor dem 09.09.2026
    try:
        MSH.koerper_vernetzen(m, list(m.koerper.values()), log=[], workers=2)
    finally:
        MSH.netzkarten = echt_k
    _auf, _gl, _d, haengend = _fugenknoten(m)
    check("ohne die modellweiten Karten hingen Knoten frei - der Test greift",
          haengend > 0, f"{haengend} hängende Knoten")


def test_arbeiter_laden_aus_datei():
    """Der Arbeitsprozess bekommt einen Dateipfad, kein Modell. Unter Windows
    (spawn) blockiert sonst jeder Prozessstart, bis das Kind die Startargumente
    gelesen hat: am Drehlager (1,7 MB, 31 Prozesse) 31 x 0,83 s = 25,8 s, bevor
    der erste Arbeiter antwortete - mit Datei 1,8 s."""
    import pickle
    import tempfile
    from statik3d import mesher as MSH
    m = _zwei_prismen()
    karten = MSH.netzkarten(m)
    fd, pfad = tempfile.mkstemp(suffix=".pkl")
    os.close(fd)
    try:
        MSH._modell_fuer_arbeiter_schreiben(m, karten, pfad)
        MSH._koerper_arbeiter_init(pfad)
        check("der Arbeiter liest Modell und Karten aus der Datei",
              MSH._WORKER_MODEL is not None and len(MSH._WORKER_MODEL.koerper) == 2
              and MSH._WORKER_KARTEN is not None and len(MSH._WORKER_KARTEN) == 3,
              f"{type(MSH._WORKER_MODEL).__name__}, Karten {type(MSH._WORKER_KARTEN).__name__}")
    finally:
        MSH._WORKER_MODEL = MSH._WORKER_KARTEN = None
        os.remove(pfad)
    # Der parallele Pfad (Datei) liefert dasselbe Netz wie der serielle
    a = _zwei_prismen()
    MSH.koerper_vernetzen(a, list(a.koerper.values()), log=[], workers=1)
    b = _zwei_prismen()
    # Nur die Dateien **dieses** Laufs zaehlen: laeuft nebenan die
    # Oberflaechenpruefung, liegt deren Arbeiterdatei im selben Ordner
    # (run_all23 vom 13.09.2026 fiel so ueber eine fremde Datei)
    vorher = {f for f in os.listdir(tempfile.gettempdir()) if f.startswith("statik3d_netz_")}
    erg = MSH.koerper_vernetzen(b, list(b.koerper.values()), log=[], workers=2)
    check("parallel und seriell ergeben dieselbe Elementzahl",
          len(a.elements) == len(b.elements) and erg.get("prozesse") == 2,
          f"{len(a.elements)} / {len(b.elements)} auf {erg.get('prozesse')} Prozessen")
    neue = [f for f in os.listdir(tempfile.gettempdir())
            if f.startswith("statik3d_netz_") and f not in vorher]
    check("die Modelldatei der Arbeiter ist danach geloescht", not neue, str(neue[:3]))


def test_karten_einmal_je_lauf():
    """Die modellweiten Netzkarten entstehen einmal je Lauf, nicht je Koerper.
    Am Drehlager bildete jeder der 48 seriell vernetzten Koerper sie neu:
    48 x 1,5 s = 36 s, waehrend der parallele Pfad sie einmal (0,8 s) bildet."""
    from statik3d import mesher as MSH
    m = _zwei_prismen()
    echt = M3.kantenlaengen_karte
    zaehler = []

    def gezaehlt(*a, **kw):
        zaehler.append(1)
        return echt(*a, **kw)
    M3.kantenlaengen_karte = gezaehlt
    try:
        MSH.koerper_vernetzen(m, list(m.koerper.values()), log=[], workers=1)
    finally:
        M3.kantenlaengen_karte = echt
    check("zwei Koerper seriell: die Kantenlaengenkarte entsteht genau einmal",
          len(zaehler) == 1, f"{len(zaehler)} Aufrufe")
    check("und beide Koerper haben ein Netz", len(m.elements) > 0 and all(k.elemente for k in m.koerper.values()),
          f"{len(m.elements)} Elemente")


def test_naht_bleibt_verschweisst():
    """Starr in allen drei Richtungen bei Knoten fuer Knoten passenden Netzen ist
    eine Schweissnaht: nichts wird getrennt, kein Knoten verdoppelt (15.09.2026,
    die automatischen Kontakte entstehen als „starr" an jeder gemeinsamen
    Flaeche und duerfen das Netz nicht veraendern)."""
    from statik3d import kontakte
    m = zwei_bloecke("gemeinsam")
    kb = m.add_kontaktbedingung("Naht", flaechennamen=["Fuge"], koerpernamen=["Oben"], gegenkoerper=["Unten"])
    kb.standard_anwenden("Verbund")
    check("starr in allen Richtungen ist eine Naht", kontakte.ist_naht(kb))
    check("ein Paar mit Naht zaehlt nicht als Kontaktpaar", not fugen.kontaktpaare(m), str(fugen.kontaktpaare(m)))
    check("die verschweisste Gruppe von Oben enthaelt Unten",
          fugen.verschweisste_gruppe(m, {"Oben"}) == {"Oben", "Unten"}, str(fugen.verschweisste_gruppe(m, {"Oben"})))
    nn = m.nn
    log = []
    b = fugen.kontaktfuge_ausfuehren(m, kb, log)
    check("ausgefuehrt, ohne einen Knoten zu verdoppeln, ohne Kopplung und Spaltelement",
          kb.ausgefuehrt and m.nn == nn and b.get("verschweisst", 0) > 0 and b["knoten"] == 0
          and not m.kopplungen and not m.gap_elements and not m.contact_pairs, str(b))
    check("Protokoll und Tabelle sagen „verschweißt“",
          any("verschweißt" in z for z in log) and "verschweißt" in kb.art_der_trennung(m),
          kb.art_der_trennung(m))
    p = -1.0e6
    F = p * A_FUGE
    r = rechnen(m, p)
    soll = -F * L_STAB / (E_STAHL * A_FUGE)
    close("Zug: Dehnung wie im durchverbundenen Stab", r["u_oben"], soll, abs(soll) * 0.03, " m")
    # Gegenprobe: nur Druck ist keine Naht und trennt
    m2 = zwei_bloecke("gemeinsam")
    kb2 = m2.add_kontaktbedingung("Fuge", flaechennamen=["Fuge"], koerpernamen=["Oben"])
    kb2.standard_anwenden("Reibungsfrei")
    nn2 = m2.nn
    b2 = fugen.kontaktfuge_ausfuehren(m2, kb2, [])
    check("nur Druck ist keine Naht: die Fuge wird getrennt (Knoten verdoppelt)",
          not kontakte.ist_naht(kb2) and b2["knoten"] > 0 and m2.nn > nn2, str(b2))


def test_naht_loest_nachbarn_mit():
    """Ein automatischer starrer Kontakt zwischen Oben und Rippe (gemeinsame
    Flaeche MO1) darf die Schweissnaht nicht aufloesen: die Rippe loest sich
    an der Fuge weiter mit Oben, so wie ohne die Bedingung."""
    m = drei_bloecke()
    naht = m.add_kontaktbedingung("Rippe–Oben starr", flaechennamen=["MO1"], koerpernamen=["Rippe"],
                                  gegenkoerper=["Oben"], automatisch=True)
    naht.standard_anwenden("Verbund")
    check("verschweisste Gruppe von Oben ist Oben+Rippe trotz starrem Kontakt",
          fugen.verschweisste_gruppe(m, {"Oben"}, {"FugeO", "FugeU"}) == {"Oben", "Rippe"},
          str(fugen.verschweisste_gruppe(m, {"Oben"}, {"FugeO", "FugeU"})))
    # Die Naht zuerst: sie darf sich nicht am verschweissten Ring festfahren -
    # am Drehlager holte verschweisste_gruppe ueber die Rippen den Gegenkoerper
    # selbst herein, und dann fehlte die Gegenseite ("keine Gegenflaeche im
    # Suchradius", 15.09.2026)
    b0 = fugen.kontaktfuge_ausfuehren(m, naht, [])
    check("die Naht gilt sofort als verschweisst - ohne Suche nach einer Gegenseite",
          naht.ausgefuehrt and b0.get("verschweisst", 0) > 0 and b0["knoten"] == 0 and not b0["grund"], str(b0))
    naht.ausgefuehrt = False
    kb = kontaktbedingung(m, "eigene")
    b = fugen.kontaktfuge_ausfuehren(m, kb, [])
    check("Fuge ausgefuehrt, Rippe mitgeloest", kb.ausgefuehrt and b.get("mitgeloest") == ["Rippe"], str(b))
    b2 = fugen.kontaktfuge_ausfuehren(m, naht, [])
    check("die Naht selbst trennt nichts", naht.ausgefuehrt and b2.get("verschweisst", 0) > 0 and b2["knoten"] == 0,
          str(b2))
    nach = fugen.gruppen_je_knoten(m)
    check("Rippe und Oben teilen weiter Knoten", any(v >= {"Oben", "Rippe"} for v in nach.values()))


def _drei_im_ring() -> Model:
    """Drei Koerper, paarweise ueber gemeinsame Flaechen verschweisst - ein
    geschlossener Ring wie die Rippen um den Lagerbock des Drehlagers: A links
    unten, B rechts unten (teilen die Flaeche Mitte), C als Deckel ueber beiden
    (teilt DeckelA mit A und DeckelB mit B)."""
    m = Model()
    m.add_material(Material.steel("S235"))
    P = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
                  [2, 0, 0], [2, 1, 0], [2, 0, 1], [2, 1, 1],
                  [0, 0, 2], [1, 0, 2], [1, 1, 2], [0, 1, 2], [2, 0, 2], [2, 1, 2.]])
    m.add_nodes(P)
    b = Bauer(m)
    L = {}

    def l(i, j):
        key = (min(i, j), max(i, j))
        if key not in L:
            L[key] = b.linie(i, j)
        return L[key]

    def flaeche(name, folge):
        m.add_flaeche(name, [l(folge[k], folge[(k + 1) % len(folge)]) for k in range(len(folge))], material="S235")
    flaeche("BodenA", [0, 1, 2, 3]); flaeche("DeckelA", [4, 5, 6, 7]); flaeche("FrontA", [0, 1, 5, 4])
    flaeche("BackA", [3, 2, 6, 7]); flaeche("LinksA", [0, 3, 7, 4]); flaeche("Mitte", [1, 2, 6, 5])
    flaeche("BodenB", [1, 8, 9, 2]); flaeche("DeckelB", [5, 10, 11, 6]); flaeche("FrontB", [1, 8, 10, 5])
    flaeche("BackB", [2, 9, 11, 6]); flaeche("RechtsB", [8, 9, 11, 10])
    flaeche("DeckelC", [12, 13, 16, 17, 14, 15]); flaeche("FrontC", [4, 5, 10, 16, 13, 12])
    flaeche("BackC", [7, 6, 11, 17, 14, 15]); flaeche("LinksC", [4, 7, 15, 12]); flaeche("RechtsC", [10, 11, 17, 16])
    ka = m.add_koerper("A", ["BodenA", "DeckelA", "FrontA", "BackA", "LinksA", "Mitte"], material="S235")
    kb_ = m.add_koerper("B", ["Mitte", "BodenB", "DeckelB", "FrontB", "BackB", "RechtsB"], material="S235")
    kc = m.add_koerper("C", ["DeckelA", "DeckelB", "DeckelC", "FrontC", "BackC", "LinksC", "RechtsC"], material="S235")
    m.netz.ziellaenge = 0.5
    cache = {}
    for k in (ka, kb_, kc):
        M3.mesh_koerper_frei(m, k, log=[], cache=cache)
    return m


def test_naht_im_ring():
    """Ein starrer Kontakt an einer gemeinsamen Flaeche in einem verschweissten
    Ring: der normale Weg holt ueber den Ring den Gegenkoerper selbst in die
    geloeste Gruppe und findet dann keine Gegenseite mehr - so standen am
    Drehlager 22 von 25 automatischen Kontakten (15.09.2026). Die Naht muss
    darum vor allem anderen als verschweisst gelten."""
    from statik3d import kontakte
    m = _drei_im_ring()
    check("drei Koerper vernetzt", all(k.elemente for k in m.koerper.values()),
          str({k: len(v.elemente) for k, v in m.koerper.items()}))
    check("der Ring: A-B, A-C und B-C teilen je eine Flaeche",
          fugen.verschweisste_gruppe(m, {"A"}, {"Mitte"}) == {"A", "B", "C"},
          str(fugen.verschweisste_gruppe(m, {"A"}, {"Mitte"})))
    naht = m.add_kontaktbedingung("A–B starr", flaechennamen=["Mitte"], koerpernamen=["A"], gegenkoerper=["B"],
                                  automatisch=True)
    naht.standard_anwenden("Verbund")
    check("starr an der gemeinsamen Flaeche: verschweisst, nicht zu steif",
          kontakte.ist_verschweisst(m, naht) and not naht.zu_steif(m), naht.zustand(m))
    nn = m.nn
    log = []
    b = fugen.kontaktfuge_ausfuehren(m, naht, log)
    check("ausgefuehrt als Naht: kein Knoten verdoppelt, kein Grund, nichts gesucht",
          naht.ausgefuehrt and b.get("verschweisst", 0) > 0 and b["knoten"] == 0 and not b["grund"] and m.nn == nn,
          str(b))
    # Gegenprobe: ohne den Fruehausstieg faehrt sich die Naht am Ring fest
    naht.ausgefuehrt = False
    echt = kontakte.ist_verschweisst
    kontakte.ist_verschweisst = lambda model, kb: False
    try:
        b2 = fugen.kontaktfuge_ausfuehren(m, naht, [])
    finally:
        kontakte.ist_verschweisst = echt
    check("ohne ihn: die Fuge findet keine Gegenseite (der Ring holt B in die geloeste Gruppe) - der Test greift",
          not naht.ausgefuehrt and "Gegenfläche" in b2["grund"] and "B" in b2.get("mitgeloest", []), str(b2))


def test_viereckfuge_zaehlt_ganz():
    """Die Fugenfläche eines Vierecks ist ganz, nicht halb.

    `_fuge_knotenweise` bildete die Facettenfläche aus **nur den ersten drei**
    Knoten (`X = model.nodes[nd[:3]]`). Die Facettenliste enthält aber
    Vierecke, sobald das Netz Hexaeder oder Viereckschalen hat: für eine
    Hexaederseite steht in `SOLID_FACES` ein Vierertupel. Bei einem Viereck war
    A damit nur das erste Dreieck - **die halbe Fläche**.

    Genau dieses A geht in die Normalfeder (`k_n = stiffness * A`) und in die
    Tangentialfedern. **Jede elastische Fuge auf einem Viereckenetz war um den
    Faktor zwei zu weich**, und weil es an einem Dreiecksnetz stimmt, sah der
    Unterschied beim Netzvergleich wie ein Netzeinfluss aus (22.09.2026).

    Geprüft wird die Federsteifigkeit, die am Ende herauskommt - nicht die
    Zwischengröße A - und zwar **auf dem echten Weg** durch
    `fugen.kontaktfuge_ausfuehren`. Die frühere Fassung dieser Prüfung rief
    die Fugenroutine nie auf, sondern rechnete die Formel im Test selbst nach;
    mit dem alten ``nd[:3]`` im Speicher bestand sie weiter (gemessen
    22.09.2026). So misst sie das Programm:

    * zwei hex8 übereinander, gemeinsame Fugenfläche 2,0 x 1,0 m (eine
      Viereckfacette, vier gemeinsame Knoten - passende Netze),
    * Federfuge c_n = 1e9 N/m³ normal, c_t = 1e8 N/m³ in beiden Tangenten.

    Soll: Σ k_n = c_n · 2,0 m² = 2,000e9 N/m, Σ k_t = 2 · c_t · 2,0 m²
    = 4,000e8 N/m. Mit dem alten ``nd[:3]`` kommt gemessen genau die Hälfte
    heraus (Σ k_n = 1,000e9 N/m, Verhältnis 0,5000).
    """
    c_n, c_t = 1.0e9, 1.0e8         # N/m^3 - Bettung normal / tangential
    A_fuge = 2.0 * 1.0              # m^2   - die gemeinsame Viereckflaeche
    m = Model("viereckfuge")
    m.add_material(Material.steel("S235"))
    for p in ([0, 0, 0], [2, 0, 0], [2, 1, 0], [0, 1, 0],
              [0, 0, 1], [2, 0, 1], [2, 1, 1], [0, 1, 1],
              [0, 0, 2], [2, 0, 2], [2, 1, 2], [0, 1, 2.]):
        m.add_node(*p)
    e0 = m.add_element("hex8", [0, 1, 2, 3, 4, 5, 6, 7], "S235", group="Unten")
    e1 = m.add_element("hex8", [4, 5, 6, 7, 8, 9, 10, 11], "S235", group="Oben")
    for i, (a, b) in enumerate(((4, 5), (5, 6), (6, 7), (7, 4))):
        m.add_line(f"L{i}", [a, b], "polyline")
    f = m.add_flaeche("Fuge", ["L0", "L1", "L2", "L3"], material="S235")
    # Deckel des unteren (Seite 1) und Grund des oberen Hexaeders (Seite 0):
    # beides dieselbe Viereckseite z = 1 - so traegt der Sweep sie ein.
    f.randseiten = [[e0, 1], [e1, 0]]
    kb = m.add_kontaktbedingung(
        "Fuge", flaechennamen=["Fuge"], gegenflaechen=[], koerpernamen=["Oben"],
        behaviour={0: DofBehaviour("spring", c_t), 1: DofBehaviour("spring", c_t),
                   2: DofBehaviour("spring", c_n)})
    log = []
    ber = fugen.kontaktfuge_ausfuehren(m, kb, log=log)
    check("die Fuge läuft Knoten gegen Knoten (4 Knoten verdoppelt, kein Kontaktpaar)",
          kb.ausgefuehrt and ber.get("knoten") == 4 and not ber.get("kontaktpaar"),
          str(ber))
    kn = [k.steifigkeiten[0] for k in m.kopplungen if len(k.richtungen) == 1]
    kt = [s for k in m.kopplungen if len(k.richtungen) == 2 for s in k.steifigkeiten]
    check("je Knoten eine Normal- und eine Tangentialkopplung",
          len(kn) == 4 and len(kt) == 8, f"{len(kn)} normal, {len(kt)} tangential")
    close("Σ Normalfedern = c_n · A (ganze Viereckfläche)", sum(kn), c_n * A_fuge,
          1e-9 * c_n * A_fuge, " N/m")
    close("Σ Tangentialfedern = 2 · c_t · A", sum(kt), 2.0 * c_t * A_fuge,
          1e-9 * c_t * A_fuge, " N/m")


# --------------------------------------------------------------------------
# tet10: Kontakt, Fugen und Flaechenlager sehen nur die Ecken - Sperre
# --------------------------------------------------------------------------
def _gemeinsame_knoten(m: Model) -> int:
    """Knoten, an denen Elemente zweier Koerper haengen."""
    grp: dict = {}
    for e in m.elements:
        for n in e.nodes:
            grp.setdefault(int(n), set()).add(str(getattr(e, "group", "")))
    return sum(1 for g in grp.values() if len(g) > 1)


def _ohne_sperre(f):
    """f() mit abgeschalteter Sperre - nur um zu belegen, was sie verhindert."""
    alt = fugen.quadratische_knoten
    fugen.quadratische_knoten = lambda model: {}
    try:
        return f()
    finally:
        fugen.quadratische_knoten = alt


def test_tet10_fuge_gesperrt():
    """Getrennt wird an den Ecken; die tet10-Seitenmitten blieben beiden
    Koerpern gemeinsam, und eine Fuge ohne Zugfestigkeit truege Zug.
    Gemessen am 22.09.2026 (Kantenlaenge 0,5, Einkern): 525,8 kN von 1000 kN
    bei passenden Netzen, 371,2 kN bei eigenen Flaechen, tet4 0 kN."""
    p = -1.0e6
    F = -p * A_FUGE
    for art in ("gemeinsam", "eigene"):
        m = zwei_bloecke(art, ordnung=2)
        check(f"{art}: das Netz ist tet10", {e.typ for e in m.elements} == {"tet10"},
              str(sorted({e.typ for e in m.elements})))
        nn, ne = m.nn, len(m.elements)
        kb = kontaktbedingung(m, art)
        try:
            fugen.kontaktfuge_ausfuehren(m, kb, [])
            gesperrt, text = False, ""
        except fugen.QuadratischeSeiten as ex:
            gesperrt, text = True, str(ex)
        check(f"{art}: das Trennen an tet10 bricht laut ab", gesperrt, text[:90])
        check(f"{art}: die Meldung nennt die Bedingung, den Typ und die Abhilfe",
              "Kontaktbedingung Fuge" in text and "tet10" in text and "linear" in text)
        check(f"{art}: das Modell bleibt unverändert (keine halbe Trennung)",
              m.nn == nn and len(m.elements) == ne and not kb.ausgefuehrt,
              f"Knoten {nn} -> {m.nn}")

        # Beleg, was die Sperre verhindert: ohne sie traegt die Fuge Zug. Bei
        # eigenen Flaechen entsteht ein Kontaktpaar, und das sperrt beim
        # Rechnen ein zweites Mal (contact.py) - darum auch dort ohne Sperre.
        m2 = zwei_bloecke(art, ordnung=2)
        kb2 = kontaktbedingung(m2, art)
        _ohne_sperre(lambda: fugen.kontaktfuge_ausfuehren(m2, kb2, []))
        g = _ohne_sperre(lambda: rechnen(m2, p, federn=1.0e11))
        check(f"{art}: ohne Sperre blieben Knoten gemeinsam und die Fuge trüge Zug",
              _gemeinsame_knoten(m2) > 0 and -g["R_fundament"] > 0.3 * F,
              f"{_gemeinsame_knoten(m2)} gemeinsame Knoten, "
              f"R = {-g['R_fundament'] / 1e3:.1f} kN von {F / 1e3:.0f} kN")


def test_tet10_verschweisst_erlaubt():
    """Starr in allen Richtungen bei passenden Netzen trennt nichts - das
    bleibt an tet10 erlaubt. Belegt wird, dass weder Ecken noch Mitten
    verdoppelt werden (sonst hinge die Fuge nur an den Mitten) und die Fuge
    Zug wie ein durchgehender Koerper traegt."""
    p = -1.0e6
    F = -p * A_FUGE
    k_feder = 1.0e11
    ganz = rechnen(zwei_bloecke("gemeinsam", ordnung=2), p, federn=k_feder)
    m = zwei_bloecke("gemeinsam", ordnung=2)
    nn = m.nn
    starr = DofBehaviour("rigid")
    kb = m.add_kontaktbedingung("Naht", flaechennamen=["Fuge"], gegenflaechen=[],
                                koerpernamen=["Oben"], behaviour={0: starr, 1: starr, 2: starr})
    try:
        b = fugen.kontaktfuge_ausfuehren(m, kb, [])
        ok, text = True, ""
    except fugen.QuadratischeSeiten as ex:
        b, ok, text = {}, False, str(ex)
    check("verschweißt an tet10: keine Sperre", ok, text[:90])
    check("verschweißt: ausgeführt, kein Knoten verdoppelt (weder Ecke noch Mitte)",
          kb.ausgefuehrt and m.nn == nn and b.get("knoten", 0) == 0,
          f"Knoten {nn} -> {m.nn}, verschweißt {b.get('verschweisst')}")
    g = rechnen(m, p, federn=k_feder)
    close("verschweißt: das Fundament trägt wie am durchgehenden Körper",
          g["R_fundament"], ganz["R_fundament"], abs(F) * 1e-6, " N")


def test_tet10_kontaktpaar_gesperrt():
    """Ein Kontaktpaar an tet10 (etwa aus einer Datei) sieht nur die Ecken -
    die Seitenmitten des Slave laufen ungehindert durch den Master."""
    m = zwei_bloecke("eigene", ordnung=2)
    unten = {i for i, e in enumerate(m.elements) if str(e.group) == "Unten"}
    oben_knoten = [n for n in _flaechenknoten(m, 1.0)
                   if any(n in m.elements[i].nodes for i, e in enumerate(m.elements)
                          if str(e.group) == "Oben")]
    m.add_contact_pair("Paar", oben_knoten[:4], master_elements=sorted(unten))
    for i in _flaechenknoten(m, 0.0):
        m.fix(i, [0, 1, 2])
    lc = m.add_load_case("LF1")
    lc.gravity = [0, 0, 0]
    m.add_geometrielast("Dach", 1.0e6, "flaeche", case="LF1")
    m.lasten_verteilen()
    try:
        solver.solve_static(m, case="LF1")
        gesperrt, text = False, ""
    except fugen.QuadratischeSeiten as ex:
        gesperrt, text = True, str(ex)
    check("Kontaktpaar an tet10: die Rechnung bricht laut ab",
          gesperrt and "Kontaktpaar Paar" in text, text[:90])


def test_tet10_flaechenlager_gesperrt():
    """Ein starres Flaechenlager hielt an tet10 nur die Ecken: gemessen am
    22.09.2026 24 von 77 Bodenknoten, die Oberseite sank um 41 % mehr als
    mit festgehaltenen Bodenknoten. An tet4 stimmt es und bleibt erlaubt."""
    from statik3d import supports
    p = 1.0e6

    def rechne(ordnung, lager):
        m = _wuerfel(0.5, ordnung=ordnung)
        unten = _flaechenknoten(m, 0.0)
        oben = _flaechenknoten(m, 1.0)
        if lager:
            ss = m.add_surface_support(name="Starr", ux=dict(typ="rigid"), uy=dict(typ="rigid"),
                                       uz=dict(typ="rigid"))
            ss.flaechen = ["Boden"]
        else:
            for i in unten:
                m.fix(i, [0, 1, 2])
        lc = m.add_load_case("LF1")
        lc.gravity = [0, 0, 0]
        m.add_geometrielast("Deckel", p, "flaeche", case="LF1")
        m.lasten_verteilen()
        r = solver.solve_static(m, case="LF1")
        return float(r.u.reshape(-1, 6)[oben, 2].mean()), m

    u_fest, _ = rechne(1, False)
    u_lager, _ = rechne(1, True)
    close("tet4: das starre Flächenlager hält wie feste Bodenknoten", u_lager, u_fest,
          abs(u_fest) * 1e-9, " m")
    try:
        rechne(2, True)
        gesperrt, text = False, ""
    except fugen.QuadratischeSeiten as ex:
        gesperrt, text = True, str(ex)
    check("tet10: das Flächenlager bricht laut ab", gesperrt and "Flächenlager Starr" in text,
          text[:90])
    u_fest2, m2 = rechne(2, False)
    check("tet10 ohne Flächenlager (Knoten fest) rechnet weiter", u_fest2 < 0,
          f"u = {u_fest2 * 1e3:.6f} mm")
    check("die Lagerzusammenfassung nennt die Sperre, statt abzubrechen",
          "gesperrt" in supports.summary(_mit_flaechenlager(_wuerfel(0.5, ordnung=2))))
    u_ohne, _ = _ohne_sperre(lambda: rechne(2, True))
    check("ohne Sperre sänke die Oberseite deutlich mehr (Seitenmitten ungelagert)",
          abs(u_ohne) > 1.2 * abs(u_fest2),
          f"{u_ohne * 1e3:.6f} mm gegen {u_fest2 * 1e3:.6f} mm")


def _mit_flaechenlager(m: Model) -> Model:
    ss = m.add_surface_support(name="Starr", ux=dict(typ="rigid"), uy=dict(typ="rigid"),
                               uz=dict(typ="rigid"))
    ss.flaechen = ["Boden"]
    return m


def main():
    for t in (test_tet10_fuge_gesperrt, test_tet10_verschweisst_erlaubt,
              test_tet10_kontaktpaar_gesperrt, test_tet10_flaechenlager_gesperrt,
              test_viereckfuge_zaehlt_ganz,test_fuge_laesst_schweissnaht_ganz, test_passende_netze_druck, test_passende_netze_zug,
              test_vorzeichen_aus_der_geometrie, test_eigene_flaechen,
              test_eigene_flaechen_zug, test_fuge_ueber_gegenseite, test_alle_fugen,
              test_suchradius_kommt_aus_der_fuge, test_diagnose_sieht_die_gegenseite,
              test_lager_werden_mitgenommen, test_verschieden_feine_netze, test_verbund,
              test_naht_bleibt_verschweisst, test_naht_loest_nachbarn_mit, test_naht_im_ring,
              test_spalt_schliessen, test_zylinder_in_bohrung, test_starre_flaeche, test_naechste_punkte,
              test_spalt_laengs_der_normalen, test_formschluss,
              test_formschluss_meldung,
              test_ein_suchradius, test_verteilung_statt_mittelwert,
              test_deckungsgleiche_knoten_direkt, test_facettenspalt_bereinigt,
              test_facettenspalt_unregelmaessig,
              test_gegenseite_nur_im_genannten_bauteil, test_kontakt_nur_auf_der_gegenflaeche,
              test_gegenseite_nur_auf_genannten_flaechen, test_gegenfacetten_folgen_dem_bauteil,
              test_durchdringung_nicht_als_spalt,
              test_freie_rechtecklast,
              test_projizierte_last_wuerfel, test_projizierte_last_bohrung,
              test_gemeinsame_flaeche_konform, test_arbeiter_laden_aus_datei, test_karten_einmal_je_lauf):
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
