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


def zwei_bloecke(art: str = "gemeinsam", h: float = 0.5, h_oben: float = 0.0) -> Model:
    """Zwei Einheitswuerfel uebereinander, vernetzt.

    art = "gemeinsam": beide Koerper haben **dieselbe** Trennflaeche - der
          Vernetzer gibt ihnen dort dieselben Knoten (passende Netze).
    art = "eigene":    jeder Koerper hat seine **eigene** Trennflaeche ueber
          denselben Linien - nur der Rand ist gemeinsam (nicht passende
          Netze, so kommt es aus RFEM).
    h_oben > 0: der obere Wuerfel bekommt eine eigene, andere Kantenlaenge.
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
    M3.mesh_koerper_frei(m, k2, h=float(h_oben or 0.0), log=[], cache=cache)
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
    # Spiel 0,5 mm; die Sehnen der 42-eckigen Bohrung liegen bis 0,28 mm weiter innen
    check("im Überdeckungsbereich ist der Abstand das Spiel (0,5 mm, minus Sehnenfehler der Bohrung)",
          0.0002 < np.median(d) < 0.0005 and d.max() < 0.0006,
          f"Median {np.median(d) * 1e3:.2f} mm, max {d.max() * 1e3:.2f} mm")
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


def main():
    for t in (test_passende_netze_druck, test_passende_netze_zug,
              test_vorzeichen_aus_der_geometrie, test_eigene_flaechen,
              test_eigene_flaechen_zug, test_fuge_ueber_gegenseite, test_alle_fugen,
              test_suchradius_kommt_aus_der_fuge, test_diagnose_sieht_die_gegenseite,
              test_lager_werden_mitgenommen, test_verschieden_feine_netze, test_verbund,
              test_spalt_schliessen, test_zylinder_in_bohrung, test_starre_flaeche, test_naechste_punkte,
              test_spalt_laengs_der_normalen, test_formschluss,
              test_formschluss_meldung,
              test_ein_suchradius, test_verteilung_statt_mittelwert,
              test_deckungsgleiche_knoten_direkt,
              test_freie_rechtecklast,
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
