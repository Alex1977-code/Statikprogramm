"""Die eingebauten Beispiele der Bibliothek: die acht bisherigen Beispiele
(statik3d.examples_lib) und die sechs Testmodelle vom 09.11.2026.

Die Parametertabelle nennt Ingenieureinheiten (m, mm, kN, kN/m, kN/m²,
Grad); umgerechnet wird hier. Die Grenzen halten das Modell baubar und das
Netz in vernuenftiger Groesse, sie sind keine Bemessungsgrenzen.
"""
from __future__ import annotations

from . import Beispiel, Parameter as P
from . import testmodelle as tm
from .. import examples_lib as ex


def _gate(w):
    return ex.gate_example(w["b"], w["h"], w["h_w"], w["t"] / 1e3)


def _gate_pruefen(w):
    return ["Stauhöhe über der Wandhöhe"] if w["h_w"] > w["h"] else []


BEISPIELE = [
    # ---------------- Stabwerk ----------------
    Beispiel("frame", "Rahmen", "Stabwerk",
             "Zweistieliger Rahmen HEA 200 aus S355, Fußpunkte eingespannt, mit Dachgleichlast und "
             "einer Horizontallast am Riegelanfang; Eigengewicht wirkt mit.",
             [P("L", "Spannweite", 6.0, "m", 1.0, 40.0), P("h", "Höhe", 4.0, "m", 1.0, 20.0),
              P("q", "Dachlast", 15.0, "kN/m", 0.0, 500.0), P("H", "Horizontallast", 12.0, "kN", 0.0, 1000.0)],
             lambda w: ex.frame_example(w["L"], w["h"], w["q"] * 1e3, w["H"] * 1e3)),
    Beispiel("truss", "Fachwerk", "Stabwerk",
             "Ebener Fachwerkträger aus Rohren RO 168/8, S355, Nutzlast in den Untergurtknoten.",
             [P("L", "Länge", 15.0, "m", 2.0, 80.0), P("h", "Höhe", 2.0, "m", 0.3, 10.0),
              P("nf", "Felder", 5, "", 2, 30, ganzzahl=True), P("F", "Knotenlast", 40.0, "kN", 0.0, 2000.0)],
             lambda w: ex.truss_bridge_example(w["L"], w["h"], w["nf"], w["F"] * 1e3)),
    Beispiel("hall", "Hallenrahmen", "Stabwerk",
             "Zweigelenkrahmen HEB 300 / IPE 500 aus S355 mit Lastfällen Eigengewicht, Schnee, Wind links "
             "und rechts (Ausschlussgruppe) und Kranlast, Kombinationen nach DIN EN 1990 und Ermüdung. "
             "Dachaufbau und Wind wirken über den Binderabstand.",
             [P("L", "Spannweite", 15.0, "m", 5.0, 60.0), P("h", "Traufhöhe", 6.0, "m", 2.0, 25.0),
              P("s_k", "Schnee", 0.85, "kN/m²", 0.0, 10.0), P("e", "Binderabstand", 6.0, "m", 1.0, 15.0)],
             lambda w: ex.hall_frame_example(w["L"], w["h"], w["s_k"] * 1e3, w["e"])),
    Beispiel("contact", "Abhebendes Lager", "Stabwerk",
             "Träger IPE 200 mit Kragarm auf zwei Lagern; das hintere Lager kann abheben, unter dem "
             "Kragarmende sitzt ein Anschlag mit Spalt (nichtlineare Rechnung).",
             [P("L", "Trägerlänge", 6.0, "m", 1.0, 30.0), P("F", "Einzellast", 30.0, "kN", 0.0, 1000.0),
              P("spalt", "Spalt am Anschlag", 3.0, "mm", 0.0, 100.0)],
             lambda w: ex.contact_example(w["L"], w["F"] * 1e3, w["spalt"] / 1e3)),
    Beispiel("wippkran", "Doppellenkerwippkran", "Stabwerk",
             "Portalkran mit Drehteil, Ausleger mit Bolzen, Rüssel, Lenker und Wippzylinder; Lastfälle "
             "Eigengewicht mit Gegengewicht, Hublast an der Rüsselspitze und Wind quer.",
             [P("hublast", "Hublast", 320.0, "kN", 0.0, 5000.0),
              P("gegengewicht", "Gegengewicht", 400.0, "kN", 0.0, 5000.0),
              P("ausleger", "Auslegerlänge", 24.0, "m", 8.0, 50.0),
              P("winkel", "Auslegerwinkel", 40.0, "°", 10.0, 80.0),
              P("wind", "Wind quer", 2.0, "kN/m", 0.0, 20.0)],
             tm.wippkran),
    Beispiel("foerderband", "Förderbandbrücke", "Stabwerk",
             "Geneigte Fachwerkbrücke mit Windverbänden, unten auf Knotenlagern, oben auf einem "
             "eingespannten Stützbock; Lastfälle Eigengewicht, Fördergut und Wind quer.",
             [P("felder", "Felder", 12, "", 2, 40, ganzzahl=True), P("feld", "Feldlänge", 3.0, "m", 1.0, 10.0),
              P("neigung", "Neigung", 12.0, "°", 0.0, 30.0), P("hoehe", "Höhe", 2.5, "m", 0.5, 8.0),
              P("breite", "Breite", 3.0, "m", 1.0, 10.0),
              P("foerdergut", "Fördergut je Untergurt", 2.5, "kN/m", 0.0, 50.0),
              P("wind", "Wind auf der Luvseite", 1.2, "kN/m", 0.0, 20.0)],
             tm.foerderband, pruefen_fn=tm._foerderband_pruefen),
    # ---------------- Flaechentragwerk ----------------
    Beispiel("plate", "Platte", "Flächentragwerk",
             "Vierseitig gelenkig gelagerte Stahlplatte aus S235 unter Flächenlast; das Netz hat etwa "
             "8 Elemente je Meter.",
             [P("a", "Seite a", 3.0, "m", 0.5, 20.0), P("b", "Seite b", 2.0, "m", 0.5, 20.0),
              P("t", "Dicke", 12.0, "mm", 2.0, 200.0), P("p", "Flächenlast", 5.0, "kN/m²", 0.0, 1000.0)],
             lambda w: ex.plate_example(w["a"], w["b"], w["t"] / 1e3, w["p"] * 1e3)),
    Beispiel("gate", "Stauwand", "Flächentragwerk",
             "Stauwandplatte aus S355 mit drei Riegeln HEB 200, seitlich und unten gelagert, Wasserdruck "
             "dreieckförmig, Kombinationen und Ermüdung (Stauwechsel).",
             [P("b", "Breite", 4.0, "m", 1.0, 30.0), P("h", "Höhe", 3.0, "m", 1.0, 20.0),
              P("h_w", "Stauhöhe", 3.0, "m", 0.1, 20.0), P("t", "Dicke", 12.0, "mm", 4.0, 100.0)],
             _gate, pruefen_fn=_gate_pruefen),
    Beispiel("stemmtor", "Stemmtor", "Flächentragwerk",
             "Ein Torflügel unter dem Stemmwinkel 1:3 mit Haut, sieben Riegeln, Vertikalsteifen und "
             "Endschotten; Wasser Betrieb und Revision über den Wasserdruckgenerator.",
             [P("breite", "Flügelbreite", 7.0, "m", 2.0, 20.0), P("hoehe", "Höhe", 8.0, "m", 2.0, 25.0),
              P("ow", "Oberwasser", 7.0, "m", 0.5, 25.0), P("uw", "Unterwasser (0 = trocken)", 2.5, "m", 0.0, 25.0),
              P("haut", "Hautblech", 14.0, "mm", 6.0, 50.0)],
             tm.stemmtor, pruefen_fn=tm._stau_pruefen),
    Beispiel("hubtor", "Hubtor", "Flächentragwerk",
             "Hubtor mit Haut, vier Riegeln und Querschotten etwa alle 2 m, auf Rollenbahnen und an "
             "Hubseilen gelagert; Wasser über den Wasserdruckgenerator.",
             [P("stuetzweite", "Stützweite", 12.0, "m", 2.0, 40.0), P("hoehe", "Höhe", 5.0, "m", 1.0, 20.0),
              P("ow", "Oberwasser", 5.0, "m", 0.5, 20.0), P("uw", "Unterwasser (0 = trocken)", 1.0, "m", 0.0, 20.0),
              P("haut", "Hautblech", 12.0, "mm", 6.0, 50.0)],
             tm.hubtor, pruefen_fn=tm._stau_pruefen),
    Beispiel("fischbauchklappe", "Fischbauchklappe", "Flächentragwerk",
             "Geneigte Stauklappe mit geschlossenem Fischbauch, Drehachse am Fuß und zwei Zylindern; "
             "Lastfälle Eigengewicht, Wasser und Eisdruck.",
             [P("stuetzweite", "Stützweite", 15.0, "m", 3.0, 50.0), P("hoehe", "Stauhöhe", 3.0, "m", 0.5, 10.0),
              P("neigung", "Neigung", 70.0, "°", 30.0, 90.0),
              P("ow", "Oberwasser", 3.0, "m", 0.2, 10.0), P("uw", "Unterwasser (0 = trocken)", 0.8, "m", 0.0, 10.0),
              P("eis", "Eisdruck", 50.0, "kN/m", 0.0, 500.0), P("haut", "Hautblech", 14.0, "mm", 6.0, 50.0),
              P("tiefe_rand", "Bauchtiefe am Rand", 0.35, "m", 0.1, 3.0),
              P("tiefe_mitte", "Bauchtiefe in der Mitte", 1.0, "m", 0.1, 3.0),
              P("felder", "Felder", 10, "", 2, 40, ganzzahl=True)],
             tm.fischbauchklappe, pruefen_fn=lambda w: _klappe_pruefen(w)),
    # ---------------- Volumen ----------------
    Beispiel("solid", "Konsole", "Volumen",
             "Volumenmodell einer eingespannten Konsole aus S355 (hex8) mit Endlast an der oberen "
             "Stirnkante; etwa 20 Elemente je Meter.",
             [P("L", "Länge", 1.0, "m", 0.1, 5.0), P("b", "Breite", 0.3, "m", 0.1, 2.0),
              P("h", "Höhe", 0.4, "m", 0.1, 2.0), P("F", "Endlast", 50.0, "kN", 0.0, 10000.0)],
             lambda w: ex.solid_example(w["L"], w["b"], w["h"], w["F"] * 1e3)),
    Beispiel("friction", "Reibung", "Volumen",
             "Stahlblock (Volumen) auf starrer Platte mit Reibkontakt, Auflast und Horizontalkraft; "
             "je nach Verhältnis haftet oder gleitet der Block teilweise.",
             [P("mu", "Reibbeiwert μ", 0.3, "", 0.0, 1.0), P("N", "Auflast", 90.0, "kN", 0.0, 10000.0),
              P("H", "Horizontalkraft", 20.0, "kN", 0.0, 10000.0)],
             lambda w: ex.block_friction_example(w["mu"], w["N"] * 1e3, w["H"] * 1e3)),
    Beispiel("spurlager", "Spurlager", "Volumen",
             "Spurplatte mit Zapfen und aufgesetzte Spurpfanne (zwei Körper) mit Reibkontakt; "
             "Torgewicht und Horizontalkraft als Flächenlast auf dem Pfannendeckel.",
             [P("torgewicht", "Torgewicht", 600.0, "kN", 0.0, 20000.0),
              P("horizontal", "Horizontalkraft", 250.0, "kN", 0.0, 10000.0),
              P("mu", "Reibbeiwert μ", 0.15, "", 0.0, 1.0),
              P("zapfen", "Zapfendurchmesser", 180.0, "mm", 60.0, 340.0),
              P("spiel", "Spiel am Radius", 0.5, "mm", 0.05, 5.0)],
             tm.spurlager, pruefen_fn=lambda w: ([] if w["zapfen"] / 2 + w["spiel"] < 180.0 else
                                                 ["Bohrung zu groß für die Pfanne (Außenradius 200 mm)"])),
]


def _klappe_pruefen(w):
    f = _stau(w)
    if w["tiefe_rand"] > w["tiefe_mitte"]:
        f.append("Bauchtiefe am Rand größer als in der Mitte")
    return f


def _stau(w):
    f = []
    if w["ow"] > w["hoehe"]:
        f.append("Oberwasser über der Stauhöhe")
    if w["uw"] >= w["ow"]:
        f.append("Unterwasser muss unter dem Oberwasser liegen")
    return f
