"""
Fortschritt und Fehlermeldungen: Speichern, Laden, Rechnen und entartete
Elemente.

Geprueft wird das, woran die Rechnung am echten Modell (Drehlager, 74 505
Knoten, 371 801 Elemente) gescheitert ist:

* Ein entarteter Tetraeder brach die ganze Berechnung ab. Jetzt findet ihn
  die Modellpruefung vorher, der Vernetzer legt ihn gar nicht erst an, und
  wenn doch einer durchkommt, nennt die Meldung Elementnummer und Knoten.
* Der Hinweis "Pool nicht verfuegbar" schrieb auf ``sys.stderr`` - in der
  gepackten exe ist der None, und der eigentliche Fehler verschwand hinter
  einem ``AttributeError``.
* Speichern, Laden und Rechnen melden jetzt, wie weit sie sind.

Aufruf:  python -m tests.test_fortschritt
"""
import os
import sys
import json
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import assemble, diagnose, parallel, solver          # noqa: E402
from statik3d.model import Model, Material, Section                # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK  ' if ok else 'FEHLER'} {name:62s} {detail}")
    return bool(ok)


def wuerfelmodell() -> Model:
    """Ein Wuerfel aus fuenf Tetraedern, unten gehalten."""
    m = Model("Wuerfel")
    m.add_material(Material("S355", E=210e9, nu=0.3, rho=7850))
    for p in [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
              (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]:
        m.add_node(*p)
    for t in [(0, 1, 3, 4), (1, 2, 3, 6), (1, 4, 5, 6), (3, 4, 6, 7), (1, 3, 4, 6)]:
        m.add_element("tet4", list(t), "S355")
    for k in (0, 1, 2, 3):
        m.fix(k, ["ux", "uy", "uz"])
    return m


# ==========================================================================
# 1  Entartete Elemente
# ==========================================================================
def test_entartete_elemente():
    m = wuerfelmodell()
    check("gesundes Netz: kein entartetes Element", not diagnose.entartete_elemente(m))

    # zwei Ecken auf demselben Knoten
    m2 = wuerfelmodell()
    i_doppelt = m2.add_element("tet4", [0, 1, 2, 2], "S355")
    tr = diagnose.entartete_elemente(m2)
    check("doppelter Knoten wird gefunden", [i for i, _t, _g in tr] == [i_doppelt],
          str(tr))
    check("Grund nennt den doppelten Knoten",
          any("derselbe" in g for _i, _t, g in tr), tr[0][2] if tr else "")

    # vier Punkte in einer Ebene (der Wuerfelboden)
    m3 = wuerfelmodell()
    i_flach = m3.add_element("tet4", [0, 1, 2, 3], "S355")
    tr = diagnose.entartete_elemente(m3)
    check("ebener Tetraeder wird gefunden", [i for i, _t, _g in tr] == [i_flach], str(tr))
    check("Grund nennt das fehlende Volumen",
          any("Volumen" in g for _i, _t, g in tr), tr[0][2] if tr else "")

    # duenn, aber gueltig: 0,1 mm Blech ueber 1 m - das ist kein Befund
    m4 = Model("duenn")
    m4.add_material(Material("S355", E=210e9, nu=0.3, rho=7850))
    for p in [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1e-4)]:
        m4.add_node(*p)
    m4.add_element("tet4", [0, 1, 2, 3], "S355")
    check("duennes, aber gueltiges Element bleibt unbeanstandet",
          not diagnose.entartete_elemente(m4),
          f"V = {1e-4 / 6:.2e} m^3")

    # Federn und Grenzschichten duerfen die Dicke null haben
    m5 = wuerfelmodell()
    m5.add_feder_prop("F1", k=[1e8] * 6)
    m5.add_node(0.0, 0.0, 0.0)
    m5.add_element("feder", [0, m5.nn - 1], "S355", sec="F1")
    check("Feder mit Laenge null ist kein Befund", not diagnose.entartete_elemente(m5))


def test_modellpruefung_meldet_entartung():
    m = wuerfelmodell()
    m.load_node(4, Fz=-1000.0)
    check("gesundes Modell: keine Meldung",
          not [z for z in m.check() if "entartet" in z])

    m.add_element("tet4", [0, 1, 2, 3], "S355")
    zeilen = m.check()
    treffer = [z for z in zeilen if "entartet" in z]
    check("Modellpruefung meldet die Entartung", len(treffer) == 1,
          treffer[0][:100] if treffer else "")
    check("als WARNUNG, nicht als FEHLER - sonst rechnet das Modell gar nicht",
          bool(treffer) and treffer[0].startswith("WARNUNG"),
          treffer[0][:40] if treffer else "")
    check("die Meldung nennt Elementnummer, Folge und Abhilfe",
          bool(treffer) and "Element 6" in treffer[0]
          and "übergangen" in treffer[0] and "Vernetzen" in treffer[0])
    check("kein FEHLER, der die Rechnung sperrt",
          not [z for z in zeilen if z.startswith("FEHLER")],
          "; ".join(z for z in zeilen if z.startswith("FEHLER"))[:70])


def test_elementfehler_nennt_das_element():
    """Kommt doch ein entartetes Element bis in die Assemblierung, muss die
    Meldung sagen, welches - "entartetes Tet4" allein hilft bei 371 801
    Elementen niemandem."""
    m = wuerfelmodell()
    i = m.add_element("tet4", [0, 1, 2, 3], "S355")
    try:
        assemble._matrix_chunk(m, [i])
        check("entartetes Element bricht die Assemblierung ab", False, "kein Fehler")
        return
    except ValueError as ex:
        text = str(ex)
    check("entartetes Element bricht die Assemblierung ab", True)
    check("Meldung nennt die Elementnummer", f"Element {i + 1} " in text, text[:90])
    check("Meldung nennt die Elementart", "tet4" in text, text[:90])
    check("Meldung nennt die Knoten", "Knoten 1, 2, 3, 4" in text, text[:110])
    check("Meldung erklaert die Ursache",
          "Ebene" in text or "fallen" in text, text[-90:])


def test_vernetzer_laesst_entartete_weg():
    from statik3d import mesher3d
    m = wuerfelmodell()
    ecken = [[0, 1, 3, 4], [0, 1, 2, 3], [1, 2, 3, 6], [0, 1, 1, 4]]
    rest, weg = mesher3d._entartete_weglassen(m, ecken)
    check("der Vernetzer sortiert entartete Tetraeder aus", weg == 2, f"{weg} von 4")
    check("die gesunden bleiben in ihrer Reihenfolge",
          rest == [[0, 1, 3, 4], [1, 2, 3, 6]], str(rest))
    rest, weg = mesher3d._entartete_weglassen(m, [[0, 1, 3, 4]])
    check("ohne Befund wird nichts angefasst", weg == 0 and rest == [[0, 1, 3, 4]])


# ==========================================================================
# 2  Parallelrechnung: Hinweise ohne Konsole, echte Fehler durchreichen
# ==========================================================================
def test_hinweis_ohne_konsole():
    """In der gepackten exe ist sys.stderr None. Ein Hinweis darf daran nicht
    scheitern - genau das erzeugte den AttributeError, der den eigentlichen
    Fehler verdeckte."""
    alt = sys.stderr
    try:
        sys.stderr = None
        parallel._melden("[parallel] Probe\n")
        check("Hinweis ohne sys.stderr wirft nichts", True)
    except Exception as ex:                     # noqa: BLE001
        check("Hinweis ohne sys.stderr wirft nichts", False, str(ex))
    finally:
        sys.stderr = alt

    class Kaputt:
        def write(self, _t):
            raise OSError("Rohr zu")

    alt = sys.stderr
    try:
        sys.stderr = Kaputt()
        parallel._melden("[parallel] Probe\n")
        check("Hinweis auf einen kaputten Strom wirft nichts", True)
    except Exception as ex:                     # noqa: BLE001
        check("Hinweis auf einen kaputten Strom wirft nichts", False, str(ex))
    finally:
        sys.stderr = alt


def _chunk_mit_fehler(model, idx):
    raise ValueError("entartetes Tet4")


def test_fehler_aus_dem_arbeitsprozess():
    """Ein Fehler *aus* der Elementschleife ist ein Befund am Modell und muss
    unveraendert nach oben. Frueher fing die Pool-Absicherung ihn ab, rechnete
    still seriell weiter und lief in denselben Fehler."""
    try:
        parallel.map_elements(_chunk_mit_fehler, wuerfelmodell(), [0, 1, 2], workers=1)
        check("Fehler aus der Elementschleife kommt durch", False, "kein Fehler")
    except ValueError as ex:
        check("Fehler aus der Elementschleife kommt durch", "entartetes Tet4" in str(ex),
              str(ex)[:60])


def test_entartete_werden_uebergangen():
    """Ein Element ohne Ausdehnung hat weder Steifigkeit noch Masse. Es
    wegzulassen ist exakt, nicht genaehert - und die Rechnung laeuft."""
    gesund = wuerfelmodell()
    gesund.load_node(6, Fz=-100000.0)
    krank = wuerfelmodell()
    krank.add_element("tet4", [0, 1, 2, 3], "S355")        # eben
    krank.add_element("tet4", [4, 5, 6, 6], "S355")        # doppelter Knoten
    krank.load_node(6, Fz=-100000.0)

    idx = assemble.aktive_indizes(krank)
    check("die Assemblierung laesst sie weg", len(idx) == 5 and idx == list(range(5)),
          f"{len(idx)} von {len(krank.elements)}")
    check("ohne Befund bleibt jedes Element drin",
          assemble.aktive_indizes(gesund) == list(range(5)))

    ra = solver.solve_static(gesund)
    rb = solver.solve_static(krank)
    check("das Ergebnis ist bitgleich - kein Naeherungsfehler",
          ra.u[6, 2] == rb.u[6, 2], f"{ra.u[6, 2]:.12g} / {rb.u[6, 2]:.12g}")

    # Auch die Massenmatrix und der Nachlauf duerfen nicht darueber stolpern
    ma = assemble.mass(gesund)
    mb = assemble.mass(krank)
    check("auch die Massenmatrix kommt durch",
          abs(ma.diagonal().sum() - mb.diagonal().sum()) < 1e-9,
          f"{ma.diagonal().sum():.6g} / {mb.diagonal().sum():.6g}")

    # Situationsmaske und Entartung greifen zusammen
    aktiv = [True] * len(krank.elements)
    aktiv[0] = False
    idx = assemble.aktive_indizes(krank, aktiv)
    check("Situationsmaske und Entartung wirken zusammen", idx == [1, 2, 3, 4], str(idx))


def test_gleiche_geometrie_gleiches_urteil():
    """Der Kern des Befunds: zwei gespiegelte Kopien desselben flachen
    Bauteils bekamen gegensaetzliche Urteile.

    Das alte Mass war die Wurzel aus der Determinante der Streumatrix. Die
    Determinante multipliziert drei Eigenwerte und hebt das Rauschen der
    letzten Bits in die dritte Potenz; bei einer absoluten Schranke von
    1e-15 m entschied dann die Lage im Raum. Gemessen wird jetzt der
    kleinste Singulaerwert - die Ausdehnung senkrecht zur besten Ebene -,
    bezogen auf die Groesse des Bauteils.
    """
    rng = np.random.default_rng(0)
    u, v = np.linspace(0, 0.014, 5), np.linspace(0, 0.026, 4)
    eben = np.array([[a, b, 0.0] for a in u for b in v])      # 14 x 26 mm, flach

    urteile, alt_urteile = set(), set()
    for _ in range(20):
        Q, _r = np.linalg.qr(rng.normal(size=(3, 3)))
        P = eben @ Q.T + rng.normal(size=3) * 0.5
        urteile.add(bool(diagnose.entartete_punktwolke(P)))
        Xc = P - P.mean(axis=0)
        alt_urteile.add(float(np.sqrt(max(float(np.linalg.det((Xc.T @ Xc) / len(P))), 0.0))) > 1e-15)
    check("dasselbe flache Bauteil: 20 Lagen, ein Urteil", urteile == {True}, str(urteile))
    check("das alte Maß war uneindeutig (deshalb der Umbau)", len(alt_urteile) == 2,
          str(alt_urteile))

    # gespiegelt heisst dasselbe Urteil
    for achse in range(3):
        P = eben.copy()
        P[:, achse] *= -1.0
        check(f"gespiegelt an Achse {achse}: unverändert",
              bool(diagnose.entartete_punktwolke(P)))

    # Ein wirkliches Blech ist kein Befund - 0,1 mm bei 30 mm Größe
    dick = eben.copy()
    dick[:, 2] = rng.normal(size=len(dick)) * 1e-4
    check("0,1 mm dickes Blech gilt als tragend",
          not diagnose.entartete_punktwolke(dick))
    # und ein handfester Körper erst recht
    wuerfel = np.array([(x, y, z) for x in (0, 1) for y in (0, 1) for z in (0, 1)], float)
    check("Würfel gilt als tragend", not diagnose.entartete_punktwolke(wuerfel))
    check("weniger als vier Punkte spannen keinen Körper auf",
          diagnose.entartete_punktwolke(wuerfel[:3]))


def test_volumen_relativ_gemessen():
    """Die Grenze haengt an der Groesse des Bauteils, nicht an der
    Laengeneinheit: 1e-15 m³ absolut ist bei Metern unterhalb dessen, was
    sich ueberhaupt aufloesen laesst."""
    check("Null-Volumen bei 30 mm Größe ist entartet",
          diagnose.entartetes_volumen(1.8e-20, 0.031))
    check("dasselbe Volumen bei 1 µm Größe ist keines",
          not diagnose.entartetes_volumen(1.8e-20, 1e-6),
          f"Grenze {diagnose.ENTARTET_VOL_REL * 1e-18:.2e}")
    check("ein 0,1 mm dickes Blech von 1 m ist kein Befund",
          not diagnose.entartetes_volumen(1e-4, 1.41))
    check("ein Würfel von 1 m schon gar nicht",
          not diagnose.entartetes_volumen(1.0, 1.73))


def test_ein_kriterium():
    """Vernetzer und Rechenbarkeitspruefung duerfen sich nicht widersprechen:
    was der Vernetzer abgelehnt hat, gilt als abgelehnt."""
    from statik3d.model import OHNE_NETZ
    m = Model("K")
    m.add_material(Material("S235", E=210e9, nu=0.3, rho=7850))
    for p_ in [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)]:      # gesunder Körper
        m.add_node(*p_)
    for i, (a, b) in enumerate([(0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3)]):
        m.add_line(f"L{i}", [a, b])
    for nm, ls in [("F1", ["L0", "L1", "L2"]), ("F2", ["L0", "L4", "L3"]),
                   ("F3", ["L1", "L5", "L4"]), ("F4", ["L2", "L3", "L5"])]:
        m.add_flaeche(nm, ls, material="S235")
    k = m.add_koerper("V_gut", ["F1", "F2", "F3", "F4"], material="S235")
    check("geometrisch gesund: trägt", m.koerper_traegt("V_gut"))

    k.kommentar = f"{OHNE_NETZ} Vernetzen abgebrochen"
    check("die Entscheidung des Vernetzers hat Vorrang vor der Geometrie",
          not m.koerper_traegt("V_gut"), k.kommentar)
    check("und er zählt dann nicht als unvernetzt",
          diagnose.diagnose(m)["unvernetzte_koerper"] == [])

    k.elemente = [0]
    check("mit Elementen trägt er wieder", m.koerper_traegt("V_gut"))
    k.elemente = []
    k.kommentar = "1 Tetraeder (tet4), Kantenlänge 500 mm"     # Erfolgsbemerkung
    check("eine Erfolgsbemerkung ist keine Ablehnung", m.koerper_traegt("V_gut"), k.kommentar)


def _zylinder(m, name, r=0.02, hoehe=0.08, x0=0.0):
    """Ein Zylinder, wie ihn RFEM abliefert: zwei Mantelflaechen (je vier
    Knoten) und zwei Kreise aus je zwei Boegen. Vier Randflaechen, vier
    Eckknoten - und trotzdem kein Tetraeder."""
    a_u, b_u = m.add_node(x0 - r, 0, 0), m.add_node(x0 + r, 0, 0)
    a_o, b_o = m.add_node(x0 - r, 0, hoehe), m.add_node(x0 + r, 0, hoehe)
    for tag, (A, B, z) in {"u": (a_u, b_u, 0.0), "o": (a_o, b_o, hoehe)}.items():
        m.add_line(f"{name}_{tag}1", [A, B], "arc",
                   punkte=[(x0 - r, 0, z), (x0, r, z), (x0 + r, 0, z)])
        m.add_line(f"{name}_{tag}2", [B, A], "arc",
                   punkte=[(x0 + r, 0, z), (x0, -r, z), (x0 - r, 0, z)])
    m.add_line(f"{name}_v1", [a_u, a_o])
    m.add_line(f"{name}_v2", [b_u, b_o])
    m.add_flaeche(f"{name}_M1", [f"{name}_u1", f"{name}_v2", f"{name}_o1", f"{name}_v1"],
                  material="S355")
    m.add_flaeche(f"{name}_M2", [f"{name}_u2", f"{name}_v1", f"{name}_o2", f"{name}_v2"],
                  material="S355")
    m.add_flaeche(f"{name}_Boden", [f"{name}_u1", f"{name}_u2"], material="S355")
    m.add_flaeche(f"{name}_Deckel", [f"{name}_o1", f"{name}_o2"], material="S355")
    return m.add_koerper(name, [f"{name}_M1", f"{name}_M2", f"{name}_Boden",
                                f"{name}_Deckel"], material="S355")


def test_zylinder_ist_kein_tetraeder():
    """Der eigentliche Befund am Drehlager: die 48 „entarteten“ Volumen waren
    gebrauchte Stifte.

    Ein Zylinder aus zwei Mantelflaechen und zwei Kreisen hat vier
    Randflaechen und vier Eckknoten - dasselbe Zaehlergebnis wie ein
    Tetraeder. Die Kreise liefern gar keinen Ring, weil sich ein aus zwei
    Boegen geschlossener Kreis nicht als Kette aus Strecken lesen laesst. Das
    abgebildete Muster griff und las die vier Ecken - die auf zwei Kreisen
    liegen - als flachen Tetraeder.
    """
    from statik3d import mesher
    m = Model("Z")
    m.add_material(Material("S355", E=210e9, nu=0.3, rho=7850))
    k = _zylinder(m, "V51")
    flaechen = [m.flaechen[x] for x in k.flaechen]
    ringe = [f.randknoten(m) for f in flaechen]
    knoten = sorted({n for r in ringe for n in r})
    check("Zylinder: vier Randflächen, vier Eckknoten - wie ein Tetraeder",
          len(k.flaechen) == 4 and len(knoten) == 4, f"{len(k.flaechen)} / {len(knoten)}")
    check("die Kreise liefern keinen Ring", sorted(len(r) for r in ringe) == [0, 0, 4, 4],
          str([len(r) for r in ringe]))
    check("das Tetraedermuster greift nicht mehr",
          not mesher._dreiflaechner(ringe, flaechen, m))

    log = []
    els = mesher.mesh_koerper(m, k, log=log, h=0.01)
    check("der Zylinder wird vernetzt", len(els) > 100, f"{len(els)} Elemente")
    check("und zwar vom freien Vernetzer",
          all(m.elements[i].typ == "tet4" for i in els))
    check("er gilt danach als tragend", m.koerper_traegt("V51") and bool(k.elemente))

    from statik3d.elements import solid as _so
    ist = sum(abs(float(_so.solid_volume("tet4", m.nodes[[int(x) for x in m.elements[i].nodes]])))
              for i in els)
    soll = np.pi * 0.02 ** 2 * 0.08
    check("das Volumen trifft den Zylinder (Sehnenfehler des Polygonzugs)",
          abs(ist - soll) / soll < 0.06, f"{ist:.4e} / {soll:.4e} m³")


def test_abgebildete_muster_bleiben():
    """Echte Tetraeder und Sechsflaechner werden weiter abgebildet vernetzt -
    das schaerfere Muster darf sie nicht mit aussortieren."""
    from statik3d import mesher
    m = Model("T")
    m.add_material(Material("S355", E=210e9, nu=0.3, rho=7850))
    for p_ in [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)]:
        m.add_node(*p_)
    for i, (a, b) in enumerate([(0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3)]):
        m.add_line(f"L{i}", [a, b])
    for nm, ls in [("F1", ["L0", "L1", "L2"]), ("F2", ["L0", "L4", "L3"]),
                   ("F3", ["L1", "L5", "L4"]), ("F4", ["L2", "L3", "L5"])]:
        m.add_flaeche(nm, ls, material="S355")
    k = m.add_koerper("V_tet", ["F1", "F2", "F3", "F4"], material="S355")
    els = mesher.mesh_koerper(m, k, log=[], frei=False)
    check("Tetraeder: ein Element, abgebildet", len(els) == 1
          and m.elements[els[0]].typ == "tet4", str(els))

    m2 = Model("H")
    m2.add_material(Material("S355", E=210e9, nu=0.3, rho=7850))
    for p_ in [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
               (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]:
        m2.add_node(*p_)
    kanten = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
              (0, 4), (1, 5), (2, 6), (3, 7)]
    for i, (a, b) in enumerate(kanten):
        m2.add_line(f"K{i}", [a, b])
    seiten = {"unten": ["K0", "K1", "K2", "K3"], "oben": ["K4", "K5", "K6", "K7"],
              "v": ["K0", "K9", "K4", "K8"], "h": ["K2", "K11", "K6", "K10"],
              "l": ["K3", "K8", "K7", "K11"], "r": ["K1", "K10", "K5", "K9"]}
    for nm, ls in seiten.items():
        m2.add_flaeche(nm, ls, material="S355")
    k2 = m2.add_koerper("V_hex", list(seiten), material="S355")
    k2.teilung = [2, 2, 2]
    els2 = mesher.mesh_koerper(m2, k2, log=[], frei=False)
    check("Sechsflächner: 2×2×2 Hexaeder, abgebildet", len(els2) == 8
          and all(m2.elements[i].typ == "hex8" for i in els2), str(len(els2)))


def test_vernetzer_ohne_volumen():
    """Vier Punkte in einer Ebene sind kein Koerper. In Dateien aus RFEM
    stehen solche Null-Volumen als Hilfsobjekte; der abgebildete Vernetzer
    machte daraus bisher ungeprueft einen Tetraeder - genau die 48 Elemente,
    an denen die Rechnung des Drehlagers scheiterte."""
    from statik3d import mesher
    m = Model("Null")
    m.add_material(Material("S235", E=210e9, nu=0.3, rho=7850))
    for p in [(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0)]:
        m.add_node(*p)
    for i, (a, b) in enumerate([(0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3)]):
        m.add_line(f"L{i}", [a, b])
    m.add_flaeche("F1", ["L0", "L1", "L2"], material="S235")
    m.add_flaeche("F2", ["L0", "L4", "L3"], material="S235")
    m.add_flaeche("F3", ["L1", "L5", "L4"], material="S235")
    m.add_flaeche("F4", ["L2", "L3", "L5"], material="S235")
    k = m.add_koerper("V_flach", ["F1", "F2", "F3", "F4"], material="S235")
    log = []
    els = mesher.mesh_koerper(m, k, log=log, frei=False)
    check("flacher Vierflaechner gibt kein Element", els == [] and k.elemente == [],
          str(els))
    check("und sagt warum", any("einer Ebene" in z and "V_flach" in z for z in log),
          (log[0] if log else "")[:100])
    check("es bleibt kein entartetes Element im Modell",
          not diagnose.entartete_elemente(m))

    # Und er darf danach nicht als „unvernetzt“ gelten: sonst fragt das
    # Programm vor jeder Rechnung nach einem Netz, das es nie geben kann -
    # genau die Schleife, in der das Drehlager-Modell stecken blieb.
    check("ein Körper ohne Rauminhalt trägt nichts", not m.koerper_traegt("V_flach"))
    d = diagnose.diagnose(m)
    check("er zählt nicht als unvernetzt", d["unvernetzte_koerper"] == [],
          str(d["unvernetzte_koerper"]))
    check("sondern eigens als Körper ohne Rauminhalt",
          d["koerper_ohne_volumen"] == ["V_flach"], str(d["koerper_ohne_volumen"]))
    zeilen = diagnose.meldungen(m)
    check("die Meldung ist ein Hinweis, keine Warnung „ohne Netz“",
          any(z.startswith("Hinweis") and "ohne Rauminhalt" in z for z in zeilen)
          and not any("Volumen ohne Netz" in z for z in zeilen),
          "; ".join(zeilen)[:100])
    check("und sie nennt den Körper beim Namen",
          any("V_flach" in z for z in zeilen))

    # Der gesunde Fall muss weiter ein Element geben
    m2 = Model("Tet")
    m2.add_material(Material("S235", E=210e9, nu=0.3, rho=7850))
    for p in [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)]:
        m2.add_node(*p)
    for i, (a, b) in enumerate([(0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3)]):
        m2.add_line(f"L{i}", [a, b])
    m2.add_flaeche("F1", ["L0", "L1", "L2"], material="S235")
    m2.add_flaeche("F2", ["L0", "L4", "L3"], material="S235")
    m2.add_flaeche("F3", ["L1", "L5", "L4"], material="S235")
    m2.add_flaeche("F4", ["L2", "L3", "L5"], material="S235")
    k2 = m2.add_koerper("V_gut", ["F1", "F2", "F3", "F4"], material="S235")
    check("ein gesunder Körper ohne Netz zählt weiter als unvernetzt",
          diagnose.diagnose(m2)["unvernetzte_koerper"] == ["V_gut"]
          and m2.koerper_traegt("V_gut"))
    els2 = mesher.mesh_koerper(m2, k2, log=[], frei=False)
    check("der gesunde Tetraeder wird weiter angelegt", len(els2) == 1, str(els2))
    check("und ist rechts orientiert (positives Volumen)",
          float(np.linalg.det(np.array(
              [m2.nodes[n] - m2.nodes[m2.elements[els2[0]].nodes[0]]
               for n in m2.elements[els2[0]].nodes[1:]]))) > 0)


# ==========================================================================
# 3  Speichern und Laden mit Fortschritt
# ==========================================================================
def _folge_pruefen(vorsatz, schritte):
    anteile = [a for a, _t in schritte]
    check(f"{vorsatz}: es wird gemeldet", len(schritte) >= 3, f"{len(schritte)} Meldungen")
    check(f"{vorsatz}: Anteile steigen nie zurueck",
          all(b >= a - 1e-9 for a, b in zip(anteile, anteile[1:])),
          f"{anteile[:3]} … {anteile[-2:]}")
    check(f"{vorsatz}: Anteile bleiben in 0…1",
          all(-1e-9 <= a <= 1.0 + 1e-9 for a in anteile),
          f"min {min(anteile):.2f}, max {max(anteile):.2f}")
    check(f"{vorsatz}: jede Meldung hat einen Text",
          all(isinstance(t, str) and t for _a, t in schritte))


def test_speichern_mit_fortschritt():
    m = wuerfelmodell()
    m.load_node(4, Fz=-1000.0)
    pfad = os.path.join(tempfile.mkdtemp(), "modell.json")
    schritte = []
    m.save(pfad, fortschritt=lambda a, t: schritte.append((a, t)))
    _folge_pruefen("Speichern", schritte)
    check("Speichern: am Ende 100 %", abs(schritte[-1][0] - 1.0) < 1e-9, f"{schritte[-1][0]:.3f}")
    check("Speichern: Knoten und Elemente werden einzeln genannt",
          any("Knoten" in t for _a, t in schritte) and any("Element" in t for _a, t in schritte))

    with open(pfad, encoding="utf-8") as f:
        d = json.load(f)
    check("die Datei ist gueltiges JSON", isinstance(d, dict) and "elements" in d)
    check("alle Schluessel sind da", len(d) == len(m.to_dict()), f"{len(d)} Schluessel")

    schritte = []
    m2 = Model.load(pfad, fortschritt=lambda a, t: schritte.append((a, t)))
    _folge_pruefen("Laden", schritte)
    check("Laden: die Datei wird blockweise gelesen",
          any("Datei lesen" in t for _a, t in schritte))
    check("Laden: am Ende 100 %", abs(schritte[-1][0] - 1.0) < 1e-9, f"{schritte[-1][0]:.3f}")
    check("gelesenes Modell ist dasselbe",
          m2.nn == m.nn and len(m2.elements) == len(m.elements)
          and np.allclose(m2.nodes, m.nodes), f"{m2.nn} Knoten, {len(m2.elements)} Elemente")
    check("Lasten und Lager kommen mit",
          len(m2.supports) == len(m.supports)
          and m2.case().n_loads == m.case().n_loads)

    # ohne Rueckruf muss alles unveraendert laufen
    m3 = Model.load(pfad)
    check("Laden ohne Rueckruf liefert dasselbe",
          m3.nn == m.nn and len(m3.elements) == len(m.elements))
    pfad2 = os.path.join(os.path.dirname(pfad), "ohne.json")
    m.save(pfad2)
    check("Speichern ohne Rueckruf schreibt dieselbe Datei",
          json.load(open(pfad2, encoding="utf-8")) == d)


def test_ergebnis_bleibt_gleich():
    """Der Umbau auf blockweises Schreiben darf am Rechenergebnis nichts
    aendern: Kragarm mit geschlossener Loesung, einmal direkt, einmal ueber
    Datei."""
    m = Model("Kragarm")
    m.add_material(Material("S355", E=210e9, nu=0.3, rho=0.0))
    m.add_section(Section("Q", A=1e-2, Iy=1e-5, Iz=1e-5, It=1e-5))
    m.add_node(0, 0, 0)
    m.add_node(2.0, 0, 0)
    m.add_element("beam", [0, 1], "S355", "Q")
    m.fix(0, ["ux", "uy", "uz", "rx", "ry", "rz"])
    m.load_node(1, Fz=-1000.0)
    r1 = solver.solve_static(m)
    pfad = os.path.join(tempfile.mkdtemp(), "kragarm.json")
    m.save(pfad, fortschritt=lambda a, t: None)
    r2 = solver.solve_static(Model.load(pfad, fortschritt=lambda a, t: None))
    ana = -1000.0 * 2.0 ** 3 / (3 * 210e9 * 1e-5)
    check("Kragarm trifft die Handrechnung", abs(r1.u[1, 2] - ana) < 1e-12 * abs(ana),
          f"{r1.u[1, 2]:.9g} / {ana:.9g}")
    check("nach Speichern und Laden dasselbe Ergebnis",
          abs(r2.u[1, 2] - r1.u[1, 2]) < 1e-14, f"{r2.u[1, 2]:.9g}")


# ==========================================================================
# 4  Fortschritt der Berechnung
# ==========================================================================
def test_rechnung_meldet_anteil():
    m = wuerfelmodell()
    m.load_node(4, Fz=-1000.0)

    schritte = []

    def melden(text, anteil=None):
        schritte.append((anteil, text))

    solver.solve_static(m, melden)
    mit = [(a, t) for a, t in schritte if a is not None]
    check("die Rechnung meldet Anteile", len(mit) >= 2, f"{len(mit)} von {len(schritte)}")
    check("Anteile steigen", all(b >= a for (a, _), (b, _) in zip(mit, mit[1:])),
          str([round(a, 2) for a, _t in mit]))
    check("am Ende steht 100 %", abs(mit[-1][0] - 1.0) < 1e-9, f"{mit[-1][0]:.2f}")
    check("Aufstellen und Faktorisieren werden genannt",
          any("aufgestellt" in t for _a, t in schritte)
          and any("Faktorisiert" in t for _a, t in schritte))


def test_alter_rueckruf_bleibt_gueltig():
    """Ein Empfaenger, der nur Text kennt (Protokoll, Kommandozeile), darf
    vom Anteil nichts merken."""
    m = wuerfelmodell()
    m.load_node(4, Fz=-1000.0)
    texte = []
    solver.solve_static(m, lambda text: texte.append(text))
    check("Rueckruf mit einem Parameter laeuft weiter", len(texte) >= 2, f"{len(texte)} Zeilen")
    check("er bekommt nur Text", all(isinstance(t, str) for t in texte))

    gemeldet = []
    solver._melde(lambda t: gemeldet.append(t), "nur Text", 0.5)
    check("_melde faellt auf den Text zurueck", gemeldet == ["nur Text"], str(gemeldet))
    gemeldet = []
    solver._melde(lambda t, a=None: gemeldet.append((t, a)), "mit Anteil", 0.25)
    check("_melde reicht den Anteil durch", gemeldet == [("mit Anteil", 0.25)], str(gemeldet))
    solver._melde(None, "ohne Empfaenger", 0.5)
    check("_melde ohne Empfaenger tut nichts", True)


def main():
    print("=" * 92)
    print("STATIK3D - Fortschritt, entartete Elemente, Fehlermeldungen")
    print("=" * 92)
    for t in (test_entartete_elemente, test_modellpruefung_meldet_entartung,
              test_elementfehler_nennt_das_element, test_vernetzer_laesst_entartete_weg,
              test_zylinder_ist_kein_tetraeder, test_abgebildete_muster_bleiben,
              test_vernetzer_ohne_volumen, test_gleiche_geometrie_gleiches_urteil,
              test_volumen_relativ_gemessen, test_ein_kriterium,
              test_hinweis_ohne_konsole, test_fehler_aus_dem_arbeitsprozess,
              test_entartete_werden_uebergangen,
              test_speichern_mit_fortschritt, test_ergebnis_bleibt_gleich,
              test_rechnung_meldet_anteil, test_alter_rueckruf_bleibt_gueltig):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:                     # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(t.__name__, False, str(ex)[:80])
    print("\n" + "=" * 92)
    nok = sum(1 for _n, ok in RESULTS if ok)
    print(f"Ergebnis: {nok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN: " + "; ".join(schlecht))
    return 0 if nok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
