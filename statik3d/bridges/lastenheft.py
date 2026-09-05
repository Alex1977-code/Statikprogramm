"""
Lastenheft für Stahlwasserbauten und bewegliche Brücken (DIN 19704, ZTV-ING).

Das Lastenheft erläutert **alle Einwirkungen, die anzusetzen sind**: was die
Einwirkung ist, woher sie kommt (normativer Hintergrund), wie sie angesetzt
wird (Ansatz und Formel), in welche Lastfallklasse sie gehört, mit welchen
Beiwerten sie kombiniert wird - und eine Skizze dazu. Was das Modell schon
kennt (Lastfälle mit ihrer Einwirkungsart, Wasserdruck- und Windgenerierer,
Stellungen), steht bei der jeweiligen Einwirkung mit dabei.

Zahlenwerte, die hier als Vorgabe stehen (Eisdruck, Temperaturunterschied,
Wichten), sind **Voreinstellungen und gegen die geltende Fassung der Norm
bzw. die Vorgaben des Betreibers zu bestätigen** - das Lastenheft weist
jeden solchen Wert aus. Fundstellen werden als Norm und Thema genannt, nicht
mit Abschnittsnummern behauptet.

    from statik3d.bridges.lastenheft import Lastenheft, lastfaelle_anlegen
    Lastenheft(model).to_html("lastenheft.html")
    lastfaelle_anlegen(model, ["G", "W_S", "W_V", "EIS"])
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..model import Model, ACTION_CATEGORIES
from ..report import svg as sv
from ..report.html import Report, esc
from .din19704 import EINWIRKUNGEN, KLASSEN, KLASSEN_TEXT, Regelwerk, pruefliste

#: Wichte von Stahl [kN/m³] (DIN EN 1991-1-1)
WICHTE_STAHL = 78.5
#: Dichte des Wassers [kg/m³] und Erdbeschleunigung [m/s²]
RHO_WASSER = 1000.0
G_ERD = 9.81

#: Voreinstellungen fuer Einwirkungen ohne Angabe im Modell - zu bestaetigen
VORGABEN = {
    "EIS": ("Eisdruck als Linienlast in Höhe des Wasserspiegels", 30.0, "kN/m"),
    "T": ("gleichmäßige Temperaturänderung gegenüber der Aufstelltemperatur", 30.0, "K"),
    "Q": ("Verkehrslast auf Bedienstegen und Bühnen", 5.0, "kN/m²"),
    "WIND_B": ("Winddruck während der Bewegung", 0.25, "kN/m²"),
    "SCHWALL": ("Wellenhöhe H für Wellendruck und Schwall", 0.5, "m"),
    "ANPRALL": ("Anprallkraft Treibgut/Schiff (Betreibervorgabe)", 500.0, "kN"),
}

#: Welche Einwirkungen ein Stahlwasserbau-Verschluss in der Regel bekommt
#: (Vorgabe fuer „Lastfaelle nach DIN 19704 anlegen“)
STANDARD = ["G", "G_A", "W_S", "W_V", "W", "T", "EIS", "Q_BEW", "A_M"]


@dataclass
class Einwirkung:
    key: str
    titel: str
    norm: str
    erlaeuterung: str
    ansatz: str
    formel: str = ""
    hinweise: list = field(default_factory=list)

    @property
    def klassen(self) -> list:
        return [k for k in ("LF1", "LF2", "LF3") if self.key in KLASSEN.get(k, [])]


EINWIRKUNGSTEXTE = [
    Einwirkung("G", "Eigengewicht der Konstruktion",
               "DIN 19704-1 (Einwirkungen), DIN EN 1991-1-1 (Wichten)",
               "Das Eigengewicht des Verschlusskörpers bzw. des Brückenüberbaus aus Stahl, "
               "Beplankung, Dichtungen und Beschichtung. Es wirkt in jeder Stellung in "
               "Richtung der Schwerkraft; bei Drehverschlüssen und Klappbrücken wandert sein "
               "Hebelarm mit der Stellung.",
               "Aus den Querschnitten und Dicken des Modells (ρ des Werkstoffs) als "
               "Eigengewicht des Lastfalls; Zuschläge für Beschichtung, Anbauten und "
               "Wasser in Hohlräumen als Zusatzlast.",
               "g = γ · V,  γ_Stahl = 78,5 kN/m³",
               ["ständig, in jeder Lastfallklasse",
                "günstig wirkendes Eigengewicht mit γ_F,inf (Abheben, Kippen)"]),
    Einwirkung("G_A", "Eigengewicht der Ausrüstung und des Antriebs",
               "DIN 19704-1, Herstellerangaben",
               "Antriebe, Getriebe, Hydraulikzylinder, Gegengewichte, Laufwerke, Riegel, "
               "Verkleidungen - alles, was am Tragwerk hängt und nicht aus dem Modell kommt.",
               "Knotenlasten bzw. Linienlasten an den Anschlusspunkten nach Herstellerangabe; "
               "Gegengewichte mit ihrer Lage je Stellung.",
               "G_A = Σ m_i · g",
               ["ständig; Gegengewichte auch als günstig wirkend prüfen"]),
    Einwirkung("W_S", "Wasserdruck, ständig (Stauziel)",
               "DIN 19704-1 (Wasserdruck), Betreibervorgabe für Stauziel und Unterwasser",
               "Der hydrostatische Druck des Oberwassers gegen das Unterwasser beim Stauziel: "
               "die Lastseite des Verschlusses, die im Regelbetrieb dauernd wirkt. Er nimmt "
               "linear mit der Tiefe zu; unter dem Verschluss wirkt der Auftrieb, oben der "
               "Überfall bzw. das Freibord.",
               "Der Wasserdruck-Generierer legt den Druck p(z) als Flächenlast auf die benetzten "
               "Flächen (Dichtlinie, Ober- und Unterwasser über Referenzflächen). Strömungs- "
               "numerisch (Potentialströmung im Schnitt) kommen Über- und Unterströmung, "
               "Absenkung und Sog dazu.",
               "p(z) = ρ · g · (h_OW − z) − ρ · g · (h_UW − z)  für z unter dem jeweiligen Spiegel",
               ["ständig (Stauziel); der Wasserstand ist eine Betreibervorgabe",
                "Auftrieb an der Unterseite und Sohlwasserdruck nicht vergessen"]),
    Einwirkung("W_V", "Wasserdruck, veränderlich (Betriebswasserstände)",
               "DIN 19704-1, Betreibervorgabe (HW, NW, Revisionsstände)",
               "Die Abweichungen vom Stauziel: Hochwasser, Niedrigwasser, abgesenktes Unterwasser, "
               "gestautes Oberwasser beim Ziehen, die Druckschwankungen der Strömung "
               "(Über-/Unterströmung, Wirbel, strömungsinduzierte Schwingungen).",
               "Je Betriebswasserstand ein Lastfall aus dem Wasserdruck-Generierer; die "
               "dynamische Druckschwankung als eigener Lastfall (Amplitude c_p' · ½ ρ v²); "
               "Schwingungsnachweis des Verschlusses nach Naudascher.",
               "p = ρ g Δh  und  p_dyn = c_p' · ½ ρ v²",
               ["veränderlich; als Leiteinwirkung mit γ_F und als Begleiteinwirkung mit ψ_0"]),
    Einwirkung("Q", "Verkehrslast",
               "DIN 19704-1 (Bedienstege), DIN EN 1991-1-1 (Nutzlasten), Betreibervorgabe",
               "Personen und Geräte auf Bedienstegen, Bühnen, Laufstegen und Treppen des "
               "Verschlusses oder der Brücke; bei beweglichen Brücken der Straßen- oder "
               "Bahnverkehr nach DIN EN 1991-2 in der geschlossenen Stellung.",
               "Flächenlast auf den begehbaren Flächen, ungünstigste Feldstellung; Verkehr "
               "auf Brücken nach den Lastmodellen der DIN EN 1991-2.",
               "q = 5,0 kN/m² (Vorgabe für Bedienstege, zu bestätigen)",
               ["veränderlich; nur in der Stellung, in der die Fläche zugänglich ist"]),
    Einwirkung("Q_BEW", "Betriebslast beim Bewegen",
               "DIN 19704-1, ZTV-ING (bewegliche Brücken)",
               "Alles, was beim Öffnen und Schließen zusätzlich wirkt: Reibung in Führungen, "
               "Lagern und Dichtungen, Massenkräfte beim Anfahren und Bremsen, Anhaften der "
               "Dichtung, Verkanten in den Führungen.",
               "Reibkräfte aus Normalkraft mal Reibbeiwert an den Führungen und Dichtungen "
               "(Gummi auf Stahl μ ≈ 0,5, gefettet 0,2 - zu bestätigen); Massenkräfte aus "
               "Beschleunigung und Masse; als Lastfall je Stellung.",
               "F_R = μ · N,  F_a = m · a",
               ["veränderlich; in jeder Zwischenstellung zu untersuchen (ZTV-ING)"]),
    Einwirkung("A_M", "Antriebsmoment, planmäßig",
               "DIN 19704-1, ZTV-ING, Herstellerangabe",
               "Das Moment bzw. die Kraft, mit der der Antrieb den Verschluss in der Stellung hält "
               "oder bewegt - im planmäßigen Betrieb das Nennmoment.",
               "Als Knotenmoment bzw. Zylinderkraft am Antriebsanschluss, je Stellung "
               "(Stellung.antrieb); Gleichgewicht mit Eigengewicht, Wasserdruck und Reibung.",
               "M_A = Σ (Lasten · Hebelarm) / η",
               ["veränderlich; Leiteinwirkung in LF1 und LF2"]),
    Einwirkung("A_MG", "Antriebsmoment, Grenzmoment der Rutschkupplung",
               "ZTV-ING, Herstellerangabe",
               "Das größte Moment, das der Antrieb überhaupt abgeben kann - begrenzt durch "
               "Rutschkupplung, Überdruckventil oder Motorkippmoment. Es wirkt beim Blockieren "
               "und im Störfall.",
               "Wie A_M, aber mit dem Grenzmoment; in LF2 als Sonderfall, in LF3 beim Verklemmen.",
               "M_AG = M_A,max (Kupplung)",
               ["Sonderfall (LF2) und außergewöhnlich (LF3)"]),
    Einwirkung("W", "Windlast im Ruhezustand",
               "DIN EN 1991-1-4 mit NA (Windzone, Geländekategorie, Böengeschwindigkeitsdruck)",
               "Wind auf den geschlossenen bzw. abgestellten Verschluss und die geöffnete Klappe: "
               "Böengeschwindigkeitsdruck q_p(z) aus Windzone und Geländekategorie, "
               "aerodynamische Beiwerte c_pe nach Bauteilform; bei Nachbarbauteilen "
               "Verschattung und Wirbel (Windkanal).",
               "Der Windgenerierer legt w = c_s c_d · c_pe · q_p(z) als Flächenlast an - nach "
               "Norm oder als numerischer Windkanal (Gitter-Boltzmann im Schnitt).",
               "w_e = c_s c_d · c_pe · q_p(z)",
               ["veränderlich; Windrichtungen getrennt als Lastfälle"]),
    Einwirkung("WIND_B", "Windlast während der Bewegung",
               "ZTV-ING (bewegliche Brücken), Betreibervorgabe für die Betriebswindgrenze",
               "Während des Öffnens und Schließens ist ein verminderter Wind anzusetzen: der "
               "Betrieb wird oberhalb einer festgelegten Windgeschwindigkeit eingestellt.",
               "Flächenlast aus dem Betriebs-Böengeschwindigkeitsdruck (Vorgabe 0,25 kN/m², zu "
               "bestätigen) in jeder Zwischenstellung.",
               "w_B = c_pe · q_B",
               ["Sonderfall (LF2) und außergewöhnlich (LF3)"]),
    Einwirkung("EIS", "Eisdruck, Eislast",
               "DIN 19704-1 (Eis), Betreibervorgabe (Eisfreihaltung)",
               "Der Druck einer geschlossenen Eisdecke gegen den Verschluss in Höhe des "
               "Wasserspiegels, dazu das Gewicht anhaftenden Eises (Vereisung) an Stegen und "
               "Aufbauten. Bei Eisfreihaltung (Umwälzung, Pressluft) darf der Eisdruck nach "
               "Vorgabe des Betreibers abgemindert werden.",
               "Linienlast in Höhe des Oberwasserspiegels quer zum Verschluss (Vorgabe 30 kN/m, "
               "zu bestätigen); Vereisung als Zusatzlast auf Aufbauten.",
               "F_Eis = p_Eis · L  (Linienlast am Wasserspiegel)",
               ["Sonderfall (LF2) und außergewöhnlich (LF3)"]),
    Einwirkung("T", "Temperatur",
               "DIN EN 1991-1-5 (Temperatureinwirkungen), DIN 19704-1",
               "Gleichmäßige Erwärmung und Abkühlung gegenüber der Aufstelltemperatur sowie der "
               "Unterschied zwischen besonnter und wasserberührter Seite; sie erzeugen Zwang "
               "in verriegelten Stellungen und an statisch unbestimmten Lagerungen.",
               "Temperaturlast auf die Bauteile (ΔT gleichmäßig ±30 K, Vorgabe, zu bestätigen; "
               "Unterschied Sonne/Wasser nach DIN EN 1991-1-5) je Stellung mit ihren Lagern.",
               "ε_T = α_T · ΔT,  α_T,Stahl = 1,2 · 10⁻⁵ 1/K",
               ["veränderlich; besonders in verriegelten Stellungen (Zwang)"]),
    Einwirkung("SCHWALL", "Schwall und Sunk, Wellendruck",
               "DIN 19704-1, DIN 19700 (Stauanlagen), Betreibervorgabe für Wellenhöhe",
               "Schnelle Wasserspiegeländerungen beim Schalten benachbarter Verschlüsse "
               "(Schwall, Sunk) und Wellendruck aus Wind- und Schiffswellen gegen den "
               "Verschluss.",
               "Zusätzlicher Druck aus der Wellenhöhe H am Wasserspiegel, nach unten "
               "abklingend (Sainflou); Schwall als kurzzeitiger Wasserstandssprung Δh.",
               "p_W ≈ ρ · g · H  am Spiegel",
               ["Sonderfall (LF2)"]),
    Einwirkung("ANPRALL", "Anprall (Schiff, Treibgut)",
               "DIN EN 1991-1-7 (außergewöhnliche Einwirkungen), Betreibervorgabe",
               "Stoß von Treibgut, Eisschollen oder eines Schiffes gegen den Verschluss oder die "
               "Brücke - außergewöhnlich, örtlich begrenzt, mit plastischer Reserve.",
               "Einzellast in Höhe des Wasserspiegels an ungünstigster Stelle (Vorgabe 500 kN, zu "
               "bestätigen); Tragwerk darf örtlich plastizieren, nicht versagen.",
               "F_A nach DIN EN 1991-1-7 bzw. Vorgabe",
               ["außergewöhnlich (LF3)"]),
    Einwirkung("KLEMM", "Verklemmen, Blockieren eines Antriebsstrangs",
               "ZTV-ING (bewegliche Brücken)",
               "Ein Antriebsstrang blockiert oder ein Riegel klemmt, während der Antrieb "
               "weiterzieht: das Grenzmoment wirkt einseitig, das Tragwerk wird verwunden.",
               "Grenzmoment A_MG auf einer Seite, Gegenlager gesperrt - je Antriebsstrang ein "
               "Lastfall in LF3.",
               "M = M_AG einseitig",
               ["außergewöhnlich (LF3)"]),
    Einwirkung("MONT", "Montage- und Revisionszustand",
               "DIN 19704-1, DIN EN 1991-1-6 (Bauzustände)",
               "Lasten beim Einheben, Abstellen auf Revisionsböcken, gezogene Dichtungen, "
               "Revisionsverschluss gesetzt und Kammer gelenzt (einseitiger Wasserdruck), "
               "Kranlasten und Personal.",
               "Je Zustand ein Lastfall mit der Lagerung des Zustands (Stellung mit deaktivierten "
               "Lagern); Kranlasten als Knotenlasten.",
               "",
               ["außergewöhnlich (LF3)"]),
    Einwirkung("ERD", "Erdbeben",
               "DIN EN 1998-1 mit NA, DIN 19704-1 (nur wo gefordert)",
               "Trägheitskräfte des Tragwerks und der mitschwingenden Wassermasse (hydrodynamischer "
               "Zusatzdruck) in Erdbebengebieten.",
               "Ersatzlastverfahren oder Antwortspektrum mit der Eigenfrequenz des Verschlusses "
               "(Modalanalyse); Wassermasse nach Westergaard als Zusatzmasse.",
               "F = m · S_d(T)",
               ["außergewöhnlich (LF3)"]),
]
TEXTE = {e.key: e for e in EINWIRKUNGSTEXTE}


# ==========================================================================
# Skizzen
# ==========================================================================
def _rahmen(w: int = 420, h: int = 240, titel: str = "") -> str:
    return sv.svg_open(w, h, titel)


def _verschluss(x: float, y: float, b: float, hoehe: float) -> str:
    """Der Verschlusskoerper als stehendes Rechteck auf der Sohle."""
    return (f'<rect x="{x:.1f}" y="{y - hoehe:.1f}" width="{b:.1f}" height="{hoehe:.1f}" '
            f'fill="{sv.COL_SHELL_FILL}" stroke="{sv.COL_BEAM}" stroke-width="1.6"/>')


def _sohle(x1: float, x2: float, y: float) -> str:
    s = sv.line(x1, x2 if False else x2, y, y, sv.COL_SUPPORT, 1.6) if False else \
        sv.line(x1, y, x2, y, sv.COL_SUPPORT, 1.6)
    for x in range(int(x1), int(x2), 12):
        s += sv.line(x, y, x - 6, y + 7, sv.COL_SUPPORT, 0.9)
    return s


def _wasser(x1: float, x2: float, y_spiegel: float, y_sohle: float, text_: str = "") -> str:
    s = (f'<rect x="{x1:.1f}" y="{y_spiegel:.1f}" width="{x2 - x1:.1f}" '
         f'height="{y_sohle - y_spiegel:.1f}" fill="#cfe3f5" fill-opacity="0.8"/>')
    s += sv.line(x1, y_spiegel, x2, y_spiegel, sv.COL_POS, 1.2)
    # Spiegel-Dreieck
    xm = (x1 + x2) / 2
    s += (f'<polygon points="{xm - 6:.1f},{y_spiegel - 9:.1f} {xm + 6:.1f},{y_spiegel - 9:.1f} '
          f'{xm:.1f},{y_spiegel:.1f}" fill="none" stroke="{sv.COL_POS}" stroke-width="1"/>')
    if text_:
        s += sv.text(xm, y_spiegel - 13, text_, 10, "middle", sv.COL_POS)
    return s


def _druckdreieck(x: float, y_oben: float, y_unten: float, breite: float, links: bool = True) -> str:
    """Hydrostatisches Druckdreieck mit Pfeilen gegen die Wand bei x."""
    s = ""
    n = 5
    for k in range(1, n + 1):
        y = y_oben + (y_unten - y_oben) * k / n
        l = breite * k / n
        if links:
            s += sv.arrow(x - l, y, x - 2, y)
        else:
            s += sv.arrow(x + l, y, x + 2, y)
    sgn = -1 if links else 1
    s += sv.line(x + sgn * 2, y_oben, x + sgn * breite, y_unten, sv.COL_LOAD, 1.0)
    return s


def skizze_wasserdruck(h_ow: float = 1.0, h_uw: float = 0.4, titel: str = "Wasserdruck") -> str:
    """Verschluss zwischen Ober- und Unterwasser mit den Druckdreiecken."""
    s = _rahmen(440, 250, titel)
    ys, hv = 200.0, 150.0
    xv = 210.0
    ho = max(0.05, min(1.0, h_ow)) * hv
    hu = max(0.0, min(1.0, h_uw)) * hv
    s += _wasser(20, xv, ys - ho, ys, "OW")
    if hu > 0:
        s += _wasser(xv + 40, 420, ys - hu, ys, "UW")
    s += _verschluss(xv, ys, 40, hv + 10)
    s += _sohle(10, 430, ys)
    s += _druckdreieck(xv, ys - ho, ys, min(90, ho * 0.8), links=True)
    if hu > 0:
        s += _druckdreieck(xv + 40, ys - hu, ys, min(60, hu * 0.8), links=False)
    s += sv.text(xv + 20, ys - hv - 16, "Verschluss", 10, "middle")
    s += sv.text(60, ys - ho + (ho * 0.8) / 2 + 4 if ho > 40 else ys - 10, "p = ρ·g·h", 10, "start", sv.COL_LOAD)
    s += sv.text(20, 236, "hydrostatischer Druck: linear mit der Tiefe; Auftrieb an der Sohle", 9)
    return s + "</svg>"


def skizze_eigengewicht(titel: str = "Eigengewicht") -> str:
    s = _rahmen(420, 220, titel)
    ys = 180.0
    s += _verschluss(160, ys, 100, 130)
    s += _sohle(20, 400, ys)
    for x in (180, 210, 240):
        s += sv.arrow(x, 70, x, 130)
    s += sv.text(210, 60, "g = γ · V", 11, "middle", sv.COL_LOAD)
    s += sv.text(20, 206, "Eigengewicht des Verschlusses und der Ausrüstung, in jeder Stellung lotrecht", 9)
    return s + "</svg>"


def skizze_ausruestung(titel: str = "Ausrüstung und Antrieb") -> str:
    s = _rahmen(420, 220, titel)
    ys = 180.0
    s += _verschluss(160, ys, 100, 120)
    s += _sohle(20, 400, ys)
    # Antrieb oben
    s += f'<rect x="200" y="30" width="60" height="22" fill="#e8e8e8" stroke="{sv.COL_SUPPORT}"/>'
    s += sv.text(230, 45, "Antrieb", 9, "middle")
    s += sv.line(230, 52, 230, 60, sv.COL_SUPPORT, 1.2)
    s += sv.arrow(230, 52, 230, 78)
    s += sv.text(250, 70, "G_A", 10, "start", sv.COL_LOAD)
    # Gegengewicht rechts
    s += f'<rect x="300" y="120" width="30" height="40" fill="#bbb" stroke="{sv.COL_SUPPORT}"/>'
    s += sv.line(260, 90, 315, 120, sv.COL_SUPPORT, 1.0, "3,2")
    s += sv.arrow(315, 160, 315, 178)
    s += sv.text(300, 112, "Gegengewicht", 9, "middle")
    s += sv.text(20, 206, "Anschlusslasten nach Herstellerangabe, Lage je Stellung", 9)
    return s + "</svg>"


def skizze_wind(titel: str = "Wind") -> str:
    s = _rahmen(420, 220, titel)
    ys = 180.0
    s += _verschluss(230, ys, 40, 140)
    s += _sohle(20, 400, ys)
    for y in (60, 85, 110, 135, 160):
        s += sv.arrow(120, y, 226, y)
    s += sv.text(130, 48, "w = c_s c_d · c_pe · q_p(z)", 11, "start", sv.COL_LOAD)
    s += sv.line(300, 40, 300, 180, sv.COL_SUPPORT, 0.8, "3,3")
    s += sv.text(305, 100, "Nachlauf / Verschattung", 9)
    s += sv.text(20, 206, "Böengeschwindigkeitsdruck nach Windzone und Gelände; Beiwerte nach Form", 9)
    return s + "</svg>"


def skizze_eis(titel: str = "Eisdruck") -> str:
    s = _rahmen(420, 220, titel)
    ys = 180.0
    s += _wasser(20, 230, 90, ys, "OW")
    s += f'<rect x="20" y="82" width="210" height="10" fill="#eef6ff" stroke="{sv.COL_POS}" stroke-width="0.8"/>'
    s += _verschluss(230, ys, 40, 140)
    s += _sohle(10, 400, ys)
    s += sv.arrow(150, 87, 226, 87, sv.COL_LOAD, 2.2, 8)
    s += sv.text(120, 72, "p_Eis [kN/m] am Spiegel", 10, "start", sv.COL_LOAD)
    s += sv.text(20, 206, "Eisdecke drückt in Höhe des Wasserspiegels; Vereisung als Zusatzgewicht", 9)
    return s + "</svg>"


def skizze_temperatur(titel: str = "Temperatur") -> str:
    s = _rahmen(420, 220, titel)
    ys = 180.0
    s += _wasser(20, 230, 80, ys, "Wasser")
    s += _verschluss(230, ys, 40, 140)
    s += _sohle(10, 400, ys)
    s += sv.text(330, 60, "Sonne", 11, "middle", "#d4ac0d", "bold")
    s += f'<circle cx="330" cy="40" r="10" fill="#f4d03f" stroke="#d4ac0d"/>'
    for y in (80, 110, 140):
        s += sv.arrow(320, y, 274, y, "#d4ac0d")
    s += sv.text(300, 170, "ΔT Sonne/Wasser", 9, "middle")
    s += sv.text(20, 206, "gleichmäßige ΔT und Unterschied Sonne/Wasser - Zwang in verriegelten Stellungen", 9)
    return s + "</svg>"


def skizze_antrieb(titel: str = "Antriebsmoment") -> str:
    s = _rahmen(420, 220, titel)
    ys = 180.0
    # Klappe um Drehpunkt
    s += sv.line(80, ys, 300, 100, sv.COL_BEAM, 6)
    s += f'<circle cx="80" cy="{ys}" r="6" fill="#fff" stroke="{sv.COL_SUPPORT}" stroke-width="1.5"/>'
    s += _sohle(20, 400, ys)
    # Momentbogen
    s += (f'<path d="M 110 150 A 40 40 0 0 1 120 {ys - 45}" fill="none" stroke="{sv.COL_LOAD}" '
          f'stroke-width="1.6"/>')
    s += sv.arrow(118, ys - 40, 128, ys - 30)
    s += sv.text(140, 135, "M_A (planmäßig) · M_AG (Grenzmoment)", 10, "start", sv.COL_LOAD)
    s += sv.arrow(260, 60, 260, 100)
    s += sv.text(270, 80, "G, W, Q_BEW", 9)
    s += sv.text(20, 206, "Antrieb hält oder bewegt die Klappe; Gleichgewicht je Stellung", 9)
    return s + "</svg>"


def skizze_bewegen(titel: str = "Betriebslast beim Bewegen") -> str:
    s = _rahmen(420, 220, titel)
    ys = 180.0
    s += f'<rect x="120" y="30" width="16" height="150" fill="#ddd" stroke="{sv.COL_SUPPORT}"/>'
    s += f'<rect x="284" y="30" width="16" height="150" fill="#ddd" stroke="{sv.COL_SUPPORT}"/>'
    s += _verschluss(136, ys - 20, 148, 90)
    s += _sohle(20, 400, ys)
    s += sv.arrow(210, 60, 210, 30, sv.COL_LOAD, 1.6)
    s += sv.text(220, 40, "Heben: F_A", 10, "start", sv.COL_LOAD)
    s += sv.arrow(136, 120, 136, 150)
    s += sv.arrow(284, 120, 284, 150)
    s += sv.text(150, 140, "F_R = μ·N (Führung, Dichtung)", 9, "start", sv.COL_LOAD)
    s += sv.text(20, 206, "Reibung an Führungen und Dichtungen, Massenkräfte beim Anfahren und Bremsen", 9)
    return s + "</svg>"


def skizze_anprall(titel: str = "Anprall") -> str:
    s = _rahmen(420, 220, titel)
    ys = 180.0
    s += _wasser(20, 230, 90, ys, "OW")
    s += _verschluss(230, ys, 40, 140)
    s += _sohle(10, 400, ys)
    s += f'<polygon points="60,80 150,80 165,92 45,92" fill="#8d6e63" stroke="#5d4037"/>'
    s += sv.arrow(170, 86, 226, 86, sv.COL_LOAD, 2.4, 9)
    s += sv.text(120, 66, "F_A (Stoß)", 10, "start", sv.COL_LOAD)
    s += sv.text(20, 206, "Einzellast in Höhe des Spiegels an ungünstigster Stelle - außergewöhnlich", 9)
    return s + "</svg>"


def skizze_schwall(titel: str = "Schwall und Wellen") -> str:
    s = _rahmen(420, 220, titel)
    ys = 180.0
    s += _wasser(20, 230, 100, ys, "")
    pts = " ".join(f"{x:.0f},{100 - 12 * math.sin((x - 20) / 18.0):.1f}" for x in range(20, 231, 6))
    s += f'<polyline points="{pts}" fill="none" stroke="{sv.COL_POS}" stroke-width="1.4"/>'
    s += _verschluss(230, ys, 40, 140)
    s += _sohle(10, 400, ys)
    s += sv.line(60, 88, 60, 112, sv.COL_SUPPORT, 0.8)
    s += sv.text(66, 104, "H", 10)
    s += _druckdreieck(230, 88, 150, 50, links=True)
    s += sv.text(20, 206, "Wellendruck am Spiegel (Sainflou), Schwall als Wasserstandssprung Δh", 9)
    return s + "</svg>"


def skizze_verklemmen(titel: str = "Verklemmen") -> str:
    s = _rahmen(420, 220, titel)
    ys = 180.0
    s += _verschluss(120, ys, 180, 100)
    s += _sohle(20, 400, ys)
    s += sv.arrow(120, 60, 120, 30, sv.COL_LOAD, 2.0, 8)
    s += sv.text(100, 25, "M_AG", 10, "start", sv.COL_LOAD)
    s += f'<rect x="292" y="60" width="16" height="30" fill="#c0392b" fill-opacity="0.5" stroke="{sv.COL_LOAD}"/>'
    s += sv.text(312, 80, "blockiert", 9, "start", sv.COL_LOAD)
    s += sv.text(20, 206, "ein Strang zieht mit dem Grenzmoment, der andere hält - Verwindung", 9)
    return s + "</svg>"


def skizze_montage(titel: str = "Montage und Revision") -> str:
    s = _rahmen(420, 220, titel)
    ys = 180.0
    s += _verschluss(140, ys - 30, 140, 90)
    for x in (150, 270):
        s += f'<rect x="{x - 8}" y="{ys - 30}" width="16" height="30" fill="#ddd" stroke="{sv.COL_SUPPORT}"/>'
    s += _sohle(20, 400, ys)
    s += sv.line(210, 20, 210, 60, sv.COL_SUPPORT, 1.2)
    s += sv.arrow(210, 30, 210, 58, sv.COL_LOAD, 1.6)
    s += sv.text(220, 40, "Kran", 9)
    s += sv.text(20, 206, "auf Revisionsböcken, Kammer gelenzt, Kranlasten - andere Lagerung als im Betrieb", 9)
    return s + "</svg>"


def skizze_erdbeben(titel: str = "Erdbeben") -> str:
    s = _rahmen(420, 220, titel)
    ys = 180.0
    s += _wasser(20, 230, 80, ys, "OW")
    s += _verschluss(230, ys, 40, 140)
    s += _sohle(10, 400, ys)
    s += sv.arrow(60, 195, 100, 195, sv.COL_LOAD, 2.0)
    s += sv.arrow(100, 205, 60, 205, sv.COL_LOAD, 2.0)
    s += sv.text(110, 203, "a_g", 10)
    s += _druckdreieck(230, 80, 170, 45, links=True)
    s += sv.text(150, 70, "hydrodynamischer Zusatzdruck", 9, "start", sv.COL_LOAD)
    return s + "</svg>"


def skizze_verkehr(titel: str = "Verkehrslast") -> str:
    s = _rahmen(420, 220, titel)
    ys = 180.0
    s += _verschluss(140, ys, 140, 120)
    s += f'<rect x="120" y="{ys - 128}" width="180" height="6" fill="#999" stroke="{sv.COL_SUPPORT}"/>'
    for x in range(130, 300, 20):
        s += sv.arrow(x, ys - 160, x, ys - 130)
    s += sv.text(210, ys - 166, "q = 5,0 kN/m² (Bediensteg)", 10, "middle", sv.COL_LOAD)
    s += _sohle(20, 400, ys)
    return s + "</svg>"


SKIZZEN = {
    "G": skizze_eigengewicht, "G_A": skizze_ausruestung, "W_S": None, "W_V": None,
    "Q": skizze_verkehr, "Q_BEW": skizze_bewegen, "A_M": skizze_antrieb, "A_MG": skizze_antrieb,
    "W": skizze_wind, "WIND_B": skizze_wind, "EIS": skizze_eis, "T": skizze_temperatur,
    "SCHWALL": skizze_schwall, "ANPRALL": skizze_anprall, "KLEMM": skizze_verklemmen,
    "MONT": skizze_montage, "ERD": skizze_erdbeben,
}


# ==========================================================================
# Lastfaelle anlegen
# ==========================================================================
def lastfaelle_anlegen(model: Model, auswahl=None, start_nr: int = 0, log: list = None) -> list:
    """Lastfaelle fuer die gewaehlten Einwirkungen anlegen (Namen = Schluessel,
    Beschreibung = Einwirkung, Kategorie = Schluessel, fortlaufende Nummer).
    Schon vorhandene Namen bekommen eine Zahl angehaengt. Rueckgabe: Namen."""
    auswahl = list(auswahl if auswahl is not None else STANDARD)
    nr = int(start_nr) if start_nr else model.naechste_lastfallnummer()
    angelegt = []
    for key in auswahl:
        if key not in ACTION_CATEGORIES:
            if log is not None:
                log.append(f"  {key}: keine Einwirkungskategorie - übersprungen")
            continue
        name = key
        k = 2
        while name in model.load_cases:
            name = f"{key} {k}"
            k += 1
        lc = model.add_load_case(name, key, EINWIRKUNGEN.get(key, ACTION_CATEGORIES[key][0]),
                                 activate=False)
        lc.nummer = nr
        nr += 1
        if key == "G":
            lc.gravity = [0.0, 0.0, -G_ERD]
        angelegt.append(name)
    if not model.active_case and angelegt:
        model.active_case = angelegt[0]
    if log is not None:
        log.append(f"{len(angelegt)} Lastfälle nach DIN 19704 angelegt: " + ", ".join(angelegt))
    return angelegt


# ==========================================================================
# Das Lastenheft
# ==========================================================================
class Lastenheft(Report):
    """Das Lastenheft als eigenes Dokument im Stil des Berichts."""

    def __init__(self, model: Model, regelwerk: Regelwerk = None, reihe=None, options: dict = None):
        super().__init__(model, None, options=options)
        self.regelwerk = regelwerk or Regelwerk()
        self.reihe = reihe

    # -- Inhalt ----------------------------------------------------------
    def blocks(self) -> list:
        if self._blocks is None:
            self._toc = []
            self._num = [0, 0, 0]
            self._appendix = False
            self._warnings = []
            b = []
            b += self.kapitel_rahmen()
            b += self.kapitel_uebersicht()
            b += self.kapitel_einwirkungen()
            b += self.kapitel_kombinationen()
            b += self.kapitel_pruefliste()
            self._blocks = b
        return self._blocks

    def _lastfaelle_je_art(self) -> dict:
        out: dict = {}
        for name, lc in self.model.load_cases.items():
            out.setdefault((lc.category or "").strip(), []).append(name)
        return out

    def kapitel_rahmen(self) -> list:
        m = self.model
        b = [self._h(1, "Zweck und normativer Rahmen")]
        b.append(("p", "Dieses Lastenheft nennt alle Einwirkungen, die für den Stahlwasserbau-Verschluss "
                       "bzw. die bewegliche Brücke anzusetzen sind: was die Einwirkung ist, aus welcher "
                       "Norm oder Vorgabe sie kommt, wie sie im Modell angesetzt wird, in welche "
                       "Lastfallklasse sie gehört und mit welchen Beiwerten sie kombiniert wird. Die "
                       "Skizzen zeigen den Ansatz."))
        b.append(("table", [["Regelwerk", "Gegenstand"],
                            ["DIN 19704-1", "Stahlwasserbauten - Berechnungsgrundlagen: Einwirkungen, "
                                           "Lastfallklassen LF1/LF2/LF3, Teilsicherheits- und Kombinationsbeiwerte"],
                            ["DIN 19704-2", "Stahlwasserbauten - Bauliche Durchbildung und Herstellung"],
                            ["DIN 19704-3", "Stahlwasserbauten - Elektrische Ausrüstung"],
                            ["ZTV-ING (bewegliche Brücken)", "Betriebsstellungen, Antriebsmomente, Wind während der "
                                                             "Bewegung, Verklemmen, Betriebsfestigkeit"],
                            ["DIN EN 1990 / 1991 (mit NA)", "Grundlagen; Wichten, Nutzlasten (1991-1-1), Wind "
                                                            "(1991-1-4), Temperatur (1991-1-5), Bauzustände (1991-1-6), "
                                                            "Anprall (1991-1-7), Verkehr auf Brücken (1991-2)"],
                            ["DIN EN 1993 (mit NA)", "Bemessung der Stahlbauteile, Ermüdung (1993-1-9)"],
                            ["Betreibervorgaben", "Stauziel und Betriebswasserstände, Eisfreihaltung, Betriebswind, "
                                                  "Anprall, Nutzungsdauer und Bewegungszahlen"]],
                  "Normativer Rahmen", None, ""))
        b.append(("note", "Zahlenwerte, die im Lastenheft als Vorgabe stehen (Beiwerte, Eisdruck, "
                          "Temperaturunterschied, Betriebswind, Anprall), sind Voreinstellungen des Programms "
                          "und gegen die geltende Fassung der Norm bzw. die Vorgaben des Betreibers zu "
                          "bestätigen. Fundstellen sind als Norm und Thema genannt."))
        rows = [["Angabe", "Wert"], ["Modell", m.name],
                ["Lastfälle", str(len(m.load_cases))],
                ["Stellungen", ", ".join(s.name for s in m.stellungen) or "–"],
                ["Wasserdruck-Generierer", ", ".join(getattr(m, "wasserdruecke", {}) or {}) or "–"],
                ["Windgenerierer", ", ".join(getattr(m, "winde", {}) or {}) or "–"]]
        b.append(("table", rows, "Das Modell", None, ""))
        return b

    def kapitel_uebersicht(self) -> list:
        rw = self.regelwerk
        b = [self._h(1, "Einwirkungen und Lastfallklassen")]
        b.append(("p", "DIN 19704-1 ordnet die Einwirkungen drei Lastfallklassen zu: "
                       + "; ".join(f"{k} = {KLASSEN_TEXT[k]}" for k in ("LF1", "LF2", "LF3")) + "."))
        je_art = self._lastfaelle_je_art()
        rows = [["Kürzel", "Einwirkung", "Art", "ψ₀", "LF1 γ_F", "LF2 γ_F", "LF3 γ_F", "Lastfälle im Modell"]]
        for e in EINWIRKUNGSTEXTE:
            kat = ACTION_CATEGORIES.get(e.key)
            psi0 = rw.psi0.get(e.key)
            art = "ständig" if e.key in rw.staendig else "veränderlich"
            if e.key in ("ANPRALL", "KLEMM", "MONT", "ERD"):
                art = "außergewöhnlich"

            def g(kl):
                f = rw.gamma_F.get(kl, {}).get(e.key)
                return "–" if f is None else f"{f.wert:.2f}" + ("" if f.bestaetigt else " *")
            rows.append([e.key, e.titel, art,
                         "–" if psi0 is None else f"{psi0.wert:.2f}" + ("" if psi0.bestaetigt else " *"),
                         g("LF1"), g("LF2"), g("LF3"),
                         ", ".join(je_art.get(e.key, [])) or "–"])
        b.append(("table", rows, "Einwirkungen, Lastfallklassen und Beiwerte (* = Voreinstellung, zu bestätigen)",
                  None, ""))
        fehlt = [e.key for e in EINWIRKUNGSTEXTE if e.key in STANDARD and not je_art.get(e.key)]
        if fehlt:
            b.append(("note", "Für diese üblichen Einwirkungen gibt es im Modell noch keinen Lastfall: "
                              + ", ".join(fehlt) + " - „Lastfälle nach DIN 19704 anlegen“ im Register Lasten."))
        return b

    def _werte_aus_modell(self, key: str) -> list:
        """Zeilen mit dem, was das Modell zu dieser Einwirkung schon kennt."""
        m = self.model
        rows = []
        je_art = self._lastfaelle_je_art()
        for name in je_art.get(key, []):
            lc = m.load_cases[name]
            n = (len(lc.nodal_loads) + len(lc.beam_loads) + len(lc.face_loads) + len(lc.geometrielasten)
                 + len(lc.linienlasten) + len(lc.temp_loads) + len(lc.zwangsverformungen))
            grav = [float(x) for x in (list(lc.gravity) if lc.gravity is not None else [])]
            g = " + Eigengewicht" if any(abs(x) > 0 for x in grav) else ""
            rows.append([f"Lastfall {name}" + (f" (Nr. {lc.nummer})" if getattr(lc, "nummer", 0) else ""),
                         f"{n} Lasten{g}" + (f", Situation {lc.situation}" if lc.situation else "")])
        if key in ("W_S", "W_V"):
            for name, wd in (getattr(m, "wasserdruecke", {}) or {}).items():
                rows.append([f"Wasserdruck {name}",
                             f"OW {wd.h_ow:g} m, UW {getattr(wd, 'h_uw', 0.0):g} m, ρ = {wd.rho:g} kg/m³, "
                             f"{'strömungsnumerisch' if getattr(wd, 'verfahren', '') == 'numerisch' else 'analytisch'}"
                             + (", überströmt" if wd.ueberstroemt else "") + (", unterströmt" if wd.unterstroemt else "")
                             + (f" → Lastfall {wd.lastfall}" if wd.lastfall else "")])
        if key in ("W", "WIND_B"):
            for name, w in (getattr(m, "winde", {}) or {}).items():
                rows.append([f"Wind {name}", f"Windzone {w.zone}, Gelände {w.profil}, c_s·c_d = {w.c_scd:g}, "
                                             f"{'Windkanal' if getattr(w, 'verfahren', '') == 'windkanal' else 'DIN EN 1991-1-4'}"
                                             + (f" → Lastfall {w.lastfall}" if w.lastfall else "")])
        if key in ("A_M", "A_MG"):
            for s in m.stellungen:
                if s.antrieb:
                    kn, mv = s.antrieb
                    rows.append([f"Stellung {s.name}", f"Antriebsmoment an Knoten {kn}: |M| = "
                                                        f"{math.sqrt(sum(float(v) ** 2 for v in mv)) / 1e3:.1f} kNm"])
        if key in VORGABEN and not rows:
            text_, wert, einheit = VORGABEN[key]
            rows.append(["Vorgabe (zu bestätigen)", f"{text_}: {wert:g} {einheit}"])
        return rows

    def kapitel_einwirkungen(self) -> list:
        m = self.model
        b = [self._h(1, "Die einzelnen Einwirkungen")]
        wds = getattr(m, "wasserdruecke", {}) or {}
        for e in EINWIRKUNGSTEXTE:
            b.append(self._h(2, f"{e.key} - {e.titel}"))
            b.append(("kv", [("Normativer Hintergrund", e.norm),
                             ("Lastfallklassen", ", ".join(e.klassen) or "–"),
                             ("Einwirkungsart", ACTION_CATEGORIES.get(e.key, ("–",))[0])], ""))
            b.append(("p", e.erlaeuterung))
            b.append(("p", "Ansatz: " + e.ansatz))
            if e.formel:
                b.append(("note", e.formel))
            if e.hinweise:
                b.append(("list", list(e.hinweise)))
            rows = self._werte_aus_modell(e.key)
            if rows:
                b.append(("table", [["Im Modell", "Angabe"]] + rows, "", None, ""))
            # Skizze
            if e.key in ("W_S", "W_V"):
                h_ow, h_uw = 1.0, 0.4
                if wds:
                    wd = next(iter(wds.values()))
                    hmax = max(float(wd.h_ow), float(getattr(wd, "h_uw", 0.0)), 1e-9)
                    h_ow, h_uw = float(wd.h_ow) / hmax, float(getattr(wd, "h_uw", 0.0)) / hmax
                b.append(("figure", skizze_wasserdruck(h_ow, h_uw, e.titel), f"Skizze: {e.titel}"))
            else:
                fn = SKIZZEN.get(e.key)
                if fn is not None:
                    b.append(("figure", fn(e.titel), f"Skizze: {e.titel}"))
        return b

    def kapitel_kombinationen(self) -> list:
        rw = self.regelwerk
        b = [self._h(1, "Kombinationen der Lastfallklassen")]
        b.append(("p", "Je Lastfallklasse und je veränderlicher Leiteinwirkung eine Kombination: "
                       "Σ γ_F,i G_i + γ_F,l Q_l + Σ γ_F,j ψ₀,j Q_j. Ständig sind "
                       + ", ".join(sorted(rw.staendig)) + ". „Kombinationen nach DIN 19704 bilden“ "
                       "(Register Berechnung) legt sie im Modell an."))
        rows = [["Klasse", "Bedeutung", "Einwirkungen"]]
        for kl in ("LF1", "LF2", "LF3"):
            rows.append([kl, KLASSEN_TEXT[kl], ", ".join(KLASSEN[kl])])
        b.append(("table", rows, "Lastfallklassen", None, ""))
        gm = [["Klasse", "γ_M0", "γ_M1", "γ_M2"]]
        for kl in ("LF1", "LF2", "LF3"):
            d = rw.gamma_M.get(kl, {})
            gm.append([kl] + [f"{d[w].wert:.2f}" + ("" if d[w].bestaetigt else " *") if w in d else "–"
                              for w in ("M0", "M1", "M2")])
        b.append(("table", gm, "Teilsicherheitsbeiwerte der Widerstände (* = zu bestätigen)", None, ""))
        offen = rw.offen()
        if offen:
            b.append(("note", f"{len(offen)} Beiwerte sind Voreinstellungen und noch zu bestätigen."))
        return b

    def kapitel_pruefliste(self) -> list:
        b = [self._h(1, "Prüfliste ZTV-ING (bewegliche Brücken)")]
        rows = [["Thema", "Stand", "Hinweis"]]
        for thema, ok, hinweis in pruefliste(self.reihe, self.model):
            rows.append([thema, "erfüllt" if ok else "offen", hinweis])
        b.append(("table", rows, "", None, ""))
        return b

    # -- Dokument --------------------------------------------------------
    def html(self) -> str:
        blocks = self.blocks()
        body = self.render_html_blocks(blocks)
        meta = self._header_pairs()
        from .. import __version__
        from ..report.html import CSS
        title = f"Lastenheft – {self.model.name}"
        head_rows = "".join(f"<tr><th>{esc(k)}</th><td>{esc(v)}</td></tr>" for k, v in meta)
        toc = []
        for level, number, t, anchor in self._toc:
            if level <= 2:
                toc.append(f'<li class="l{level}"><a href="#{anchor}">'
                           f'<span class="no">{esc(number)}</span> {esc(t)}</a></li>')
        return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="Statik3D {esc(__version__)}">
<title>{esc(title)}</title>
<style>
{CSS}
</style>
</head>
<body>
<div class="titlepage">
<div class="brand">Statik3D – Tragwerksberechnung</div>
<h1 class="doctitle">Lastenheft</h1>
<div class="subtitle">Anzusetzende Einwirkungen nach DIN 19704 und ZTV-ING – {esc(self.model.name)}</div>
<table class="kv meta"><tbody>{head_rows}</tbody></table>
<div class="note">Erläuterung aller Einwirkungen mit normativem Hintergrund, Ansatz, Lastfallklasse,
Beiwerten und Skizze. Voreinstellungen sind gekennzeichnet und zu bestätigen. Im Browser mit Strg+P als
PDF zu speichern.</div>
</div>
<nav class="toc">
<h2>Inhalt</h2>
<ul>
{chr(10).join(toc)}
</ul>
</nav>
{body}
<div class="footer">Statik3D {esc(__version__)} – {esc(title)}</div>
</body>
</html>
"""

    def to_markdown(self) -> str:
        md = super().to_markdown()
        return md.replace("# Statischer Bericht –", "# Lastenheft –", 1)


def lastenheft_schreiben(model: Model, pfad: str, regelwerk: Regelwerk = None, reihe=None) -> str:
    """Das Lastenheft als HTML-Datei (oder Markdown bei .md) schreiben."""
    lh = Lastenheft(model, regelwerk, reihe)
    if pfad.lower().endswith(".md"):
        with open(pfad, "w", encoding="utf-8") as fh:
            fh.write(lh.to_markdown())
        return pfad
    return lh.to_html(pfad)
