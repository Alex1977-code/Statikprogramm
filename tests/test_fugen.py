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
* **Freie Rechtecklast** - die Last wirkt in einem Fenster. Deckt das Fenster
  die ganze Flaeche, muss die Summe der Auflagerkraefte genau p mal A sein;
  deckt es nichts, darf keine Last entstehen; und jede belastete Elementseite
  muss mit ihrem Schwerpunkt im Fenster liegen.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import fugen, mesher3d as M3, solver          # noqa: E402
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


def zwei_bloecke(art: str = "gemeinsam", h: float = 0.5) -> Model:
    """Zwei Einheitswuerfel uebereinander, vernetzt.

    art = "gemeinsam": beide Koerper haben **dieselbe** Trennflaeche - der
          Vernetzer gibt ihnen dort dieselben Knoten (passende Netze).
    art = "eigene":    jeder Koerper hat seine **eigene** Trennflaeche ueber
          denselben Linien - nur der Rand ist gemeinsam (nicht passende
          Netze, so kommt es aus RFEM).
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
    cache = {}
    M3.mesh_koerper_frei(m, k1, log=[], cache=cache)
    M3.mesh_koerper_frei(m, k2, log=[], cache=cache)
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


def rechnen(m: Model, p: float, federn: float = 0.0):
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
    oben = _flaechenknoten(m, 2.0)
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
def _wuerfel(h: float = 0.5) -> Model:
    """Ein Einheitswuerfel, vernetzt - Deckel oben."""
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


def main():
    for t in (test_passende_netze_druck, test_passende_netze_zug,
              test_vorzeichen_aus_der_geometrie, test_eigene_flaechen,
              test_eigene_flaechen_zug, test_alle_fugen,
              test_lager_werden_mitgenommen, test_freie_rechtecklast,
              test_projizierte_last_wuerfel, test_projizierte_last_bohrung):
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
