"""Plastizitaet der Volumenelemente (17.09.2026): von Mises mit isotroper
linearer Verfestigung. Zwei Wege - die **Anfangsdehnungs-Iteration** bei
fester Steifigkeit (unten) und, seit dem 20.09.2026 als Vorgabe, **Newton
mit der konsistenten elastoplastischen Tangente** (ganz unten).

Der alte Weg zuerst, denn der zweite setzt darauf auf.

Warum so: der Loeser dieses Programms ist linear-elastisch plus Kontakt
(Aktivmengen-Iteration mit fester Faktorisierung). Ein Fliessen laesst sich
darauf setzen, ohne die Steifigkeitsmatrix anzufassen: die plastische
Dehnung eps_p jedes Elements ist eine Anfangsdehnung, genau wie eine
Temperaturdehnung oder die Vorspannung. Ihre aequivalenten Knotenlasten
F_p = ∫ Bᵀ D eps_p dV kommen zur aeusseren Last, die Spannung ist
σ = D (ε − eps_p). Die Iteration

    u_k = K⁻¹ (F + F_p(eps_p,k-1)),   eps_p,k = Rueckfuehrung(D ε(u_k) − D eps_p,k-1)

ist das Anfangssteifigkeitsverfahren: jeder Schritt ist eine lineare
Loesung (mit Kontakt eine Kontakt-Iteration, warm gestartet), die
Faktorisierung bleibt. Es konvergiert linear - langsam bei grossflaechigem
Fliessen, schnell bei oertlichem (Bohrungskanten, Lochleibung), und dafuer
ist es gedacht. Laststufen halten die Rueckfuehrung auf dem Pfad.

Rueckfuehrung (radial return, von Mises, isotrope Verfestigung H):

    s = dev σ_trial,  q = sqrt(3/2 s:s),  f = q − (fy + H ε_p,eq)
    f > 0:  Δγ = f / (3G + H),  n = 3/2 s / q,  σ = σ_trial − 2G Δγ n,
            Δε_p = Δγ n (Ingenieurgleitungen: doppelte Schubanteile),  Δε_p,eq = Δγ

Uniaxial: σ = fy + H ε_p und ε = σ/E + ε_p - die lineare Verfestigung mit der
Tangente E_t = E H / (E + H). Die Verfestigung wird als E_t/E angegeben.

**Grenze f_u (seit dem 13.10.2026):** bilinear bis f_u, danach ideal
plastisch - σ_y = min(fy + H ε_p, fu), Entscheidung des Anwenders („entspricht
EN 1993-1-5 C.6“). E_t/E steht je Werkstoff (Material.verfestigung, Vorgabe
E/100, „ohne Verfestigung“ E/10 000), f_u kommt immer aus dem Werkstoff (bei
Schrauben f_ub, bei Spannstahl f_pk). Ein Schritt ueber den Knick endet exakt
auf q = fu, die Tangente rechnet dort mit H = 0 (:func:`rueckfuehrung`,
:func:`verfestigung_wirksam`). Fehlt f_u, verfestigt der Werkstoff ohne
Grenze wie bis dahin, und das Protokoll sagt es. Bis zum 13.10.2026 gab es
keine Grenze: am Drehlager erreichte der Schraubenkoerper V90 560,6 N/mm2 bei
ε_p 9,69 % - ueber f_u = 490 N/mm2.

Voigt-Reihenfolge wie in elements.solid: xx, yy, zz, xy, yz, xz; Dehnungen
mit Ingenieurgleitungen.

**Zweiter Weg - konsistente Tangente (20.09.2026):** die Anfangsdehnungs-
Iteration zieht sich mit dem Faktor 1 − E_t/E zusammen. Bei 1 % Verfestigung
sind das 0,99 je Schritt (rund 700 Schritte fuer 1e-3); die Aitken-
Beschleunigung ueberschiesst dort und bleibt bei einer Aenderung von 1e-1
stehen - der Zugversuch lag bei 1,5 fy um 28,5 % daneben. Darum wird die
Steifigkeit nun voreingestellt je Schritt neu aufgestellt und faktorisiert,
mit der zur Rueckfuehrung **konsistenten** elastoplastischen Tangente (Simo
& Hughes, Box 3.2), nicht mit der kontinuierlichen:

    D_ep = K δ⊗δ + 2G θ (I − δ⊗δ/3) − 2G θ̄ N⊗N
    θ = 1 − 3G Δγ / q_trial,  θ̄ = 1/(1 + H/3G) − (1 − θ),  N = s_trial/‖s_trial‖

Das ist die Ableitung der Rueckfuehrung nach der Gesamtdehnung. Die Folge
ist damit ein Newton-Verfahren und haengt nicht mehr an der Verfestigung:
der Zugversuch braucht bei 1 % zwei bis vier Schritte je Laststufe statt
"nicht konvergiert". Bezahlt wird es mit **einer Faktorisierung je Schritt**
statt einer je Rechnung - siehe :func:`iteration`.

ΔK ist seit dem Zustand je Gausspunkt (20.09.2026) fuer **jeden**
Volumentyp die exakte Ableitung −∂F_p/∂u: gemessen am 22.09.2026 gegen
zentrale Differenzen auf 0,8e-9 bis 1,7e-9 (tet4, hex8 mit Moden, tet10,
hex20, pent6, pent15, pyr5 - die Groesse des Differenzenfehlers), und der
Newton konvergiert quadratisch (Kragtraeger unter 1,20 M_el: hex8 1,8e-3 ->
2,5e-6 -> 2,3e-12, tet10 2,1e-3 -> 2,4e-6 -> 8,5e-12). Die fruehere Angabe
"bei tet10 bis 53 %, bei hex8 rund 1 % Abweichung" stammte aus der Zeit, als
eps_p an der Elementmitte hing, und galt seitdem nicht mehr
(tests/test_plastizitaet.py, test_tangente_exakt_fuer_jeden_typ und
test_newton_konvergiert_quadratisch).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

#: Voigt-Hilfen
_EINS = np.array([1.0, 1.0, 1.0, 0.0, 0.0, 0.0])
_SCHUB = np.array([1.0, 1.0, 1.0, 2.0, 2.0, 2.0])

#: Deviatorischer Projektor I − δ⊗δ/3 als Voigt-Matrix. In dieser Schreibweise
#: ist D_AB = C_ijkl ohne Zusatzfaktoren, weil der Faktor 2 aus der Symmetrie
#: des zweiten Indexpaares in der Ingenieurgleitung steckt - darum 1/2 auf den
#: Schubplaetzen (Probe: mit θ = 1 und θ̄ = 0 kommt genau lam*P + diag(2G,2G,2G,G,G,G)
#: heraus, also die Matrix von :func:`_spannung`).
_P_DEV = np.array([
    [2.0 / 3.0, -1.0 / 3.0, -1.0 / 3.0, 0.0, 0.0, 0.0],
    [-1.0 / 3.0, 2.0 / 3.0, -1.0 / 3.0, 0.0, 0.0, 0.0],
    [-1.0 / 3.0, -1.0 / 3.0, 2.0 / 3.0, 0.0, 0.0, 0.0],
    [0.0, 0.0, 0.0, 0.5, 0.0, 0.0],
    [0.0, 0.0, 0.0, 0.0, 0.5, 0.0],
    [0.0, 0.0, 0.0, 0.0, 0.0, 0.5],
])

#: Die beiden Wege durch die Plastizitaet - siehe :func:`iteration`
WEGE = ("tangente", "anfangsdehnung")

#: Wie Newton und Kontakt zusammen iterieren - siehe :func:`_newton`; der
#: erste ist die Vorgabe. "gemeinsam" ist seit dem 06.10.2026 als Versuch
#: gekennzeichnet (Fehlerliste F12): die Oberflaeche nennt ihn „gemeinsam
#: (Versuch)“, und jedes so gerechnete Ergebnis traegt GEMEINSAM_WARNUNG.
KONTAKT_WEGE = ("verschachtelt", "gemeinsam")

#: Die Warnung eines Ergebnisses, das mit ``kontakt = "gemeinsam"`` gerechnet
#: ist (Fehlerliste vom 06.10.2026, F12; vorher warnte nur der Tooltip der
#: Auswahl): an Reibung nahe der Grenzlast endet die gemeinsame Iteration in
#: einem anderen Zustand als die verschachtelte, beide "konvergiert" (bis
#: 78 N/mm2, Theoriehandbuch § 5e.3). Der Loeser setzt dann
#: ``res.info["plastizitaet"]["kontakt"] = "gemeinsam"`` und schreibt
#: "WARNUNG: Iteration „gemeinsam“ (Versuch) ..." ins Protokoll der
#: Plastizitaet und in den Fortschritt (solver._plastizitaet_rechnen); die
#: Zusammenfassung des Ergebnisses nennt sie (solver.Results.summary), die der
#: Rechnung und die Hinweise des Berichts gebuendelt ueber alle Ergebnisse
#: (solver.gemeinsam_gebuendelt). Der Text sagt mit Absicht nichts ueber die
#: Konvergenz - die Rechenliste liest den Zustand eines Postens aus den
#: Meldungen (gui.rechenliste.zustand_aus_meldung) -, und mit dem Vorsatz
#: "WARNUNG: Iteration „gemeinsam“ (Versuch) " passt er in die 160 Zeichen
#: ihrer Spalte "Meldung".
GEMEINSAM_WARNUNG = ("kann nahe der Grenzlast einen anderen Weg durch die Reibung nehmen als "
                     "„verschachtelt“; mit „verschachtelt“ gegenprüfen")

#: Abbruch einer Laststufe (Einstellung ``Plastizitaet.abbruch``, seit dem
#: 13.10.2026; Plan Singularitaeten vom 10.10.2026, Paket 3); der erste ist die
#: Vorgabe. Entscheidung des Anwenders vom 10.10.2026: Spannungsspitzen und
#: Singularitaeten „sollten nicht dafür sorgen dass sich die rechenzeit
#: verlängert“, und das neue Kriterium ist gleich die Vorgabe.
#:
#: * "ingenieurmaessig": eine Laststufe ist konvergiert, wenn die Aenderung von
#:   F_p **ausserhalb** der auffaelligen Zonen (spitzenstellen, Paket 1) unter
#:   der Toleranz liegt, die Kraft durch jede auffaellige Stelle sich um
#:   hoechstens :data:`SPITZEN_KRAFT`, die Verschiebung ausserhalb der Zonen
#:   um hoechstens :data:`SPITZEN_VERSCHIEBUNG` und sigma_v an den
#:   Integrationspunkten ausserhalb der Zonen um hoechstens
#:   :data:`SPITZEN_SPANNUNG` aendert (:func:`_zonen_mass`).
#:   Am selben Mass entscheidet sich das Halbieren einer weglaufenden Stufe und
#:   die Schlussabnahme. Die Zonen rechnen weiter plastisch mit - nur ihr
#:   Beitrag zum Mass faellt weg; ihre Werte stehen mit der letzten Aenderung
#:   als „nicht auskonvergiert“ im Ergebnis. Ausgenommen wird nur, was Paket 1
#:   als auffaellig kennzeichnet (am Drehlager die 16 Ankerringe); ohne
#:   auffaellige Stelle ist es Schritt fuer Schritt das strenge Kriterium.
#: * "streng": die Aenderung von F_p ueber das ganze Modell, wie bis zum
#:   13.10.2026. Am Drehlager trugen die Zonen der 16 Ankerringe 97 bis 99 %
#:   des Quadrats dieser Aenderung (Plan, Abschnitt 2) - das Mass war praktisch
#:   eines der netzabhaengigen Spitzen.
#:
#: Die Zonen bestimmt der Loeser (solver._SpitzenImNewton) nach jedem
#: Newton-Schritt aus dem aktuellen Zustand; einmal auffaellig, bleibt eine
#: Stelle innerhalb des Lastfalls ausgenommen. Das Protokoll nennt je Schritt
#: die Aenderung in und ausserhalb der Zonen in beiden Wegen.
ABBRUCH_WEGE = ("ingenieurmaessig", "streng")
#: Kraft durch jede auffaellige Stelle (Stabkraft bzw. Resultierende der
#: Kopplung am Master): hoechstens so viel relative Aenderung im letzten
#: Schritt. Was eine nicht auskonvergierte Zone nach aussen gibt, ist eine
#: Kraeftegruppe im Gleichgewicht, die abklingt - nur die Kraft, die durch die
#: Stelle geht, klingt nicht ab: am Drehlager haengt die Ankerkraft an der
#: Einsenkung des Rings, rund 66 kN je mm (Plan, Abschnitt 3 „Risiken“).
SPITZEN_KRAFT = 5e-3
#: Verschiebung ausserhalb der Zonen (und ohne die Knoten und Master der
#: auffaelligen Stellen): hoechstens so viel Aenderung im letzten Schritt,
#: bezogen auf die groesste Verschiebung dort. Der Plan nannte 1 %. Das ist
#: genau die Grenze seiner eigenen Abnahme (u ausserhalb hoechstens 1 % neben
#: dem strengen Ergebnis): ein Newton, der an der Zone nur noch linear
#: konvergiert (am Ring der Ankerplatte rund 0,5 je Schritt), steht nach dem
#: Abbruch etwa um die letzte Aenderung neben seiner Loesung. Viel enger geht
#: aber auch nicht: pendelt eine Zone (Ankerplatte mit feinem Netz, Periode
#: drei Schritte, 13.10.2026), bewegt sie die Knoten ausserhalb im Takt um
#: 0,28 bis 0,46 % - mit 1e-3 kam die Stufe nie an, „nicht konvergiert“ nach
#: 25 Schritten, wo F_p ausserhalb sich gar nicht und die Ankerkraft um
#: 0,1 % aenderte. 0,5 % liegt dazwischen, mit dem Faktor 2 unter der Abnahme
#: und gleich der Grenze fuer die Kraft; am groben Netz der Ankerplatte
#: brauchte es dieselben 14 Newton-Schritte wie 1 % (1e-3: 17, streng: 29),
#: bei 0,2 N/mm2 und 0,17 % Abweichung ausserhalb (sp3_werk/p5_serie.out).
SPITZEN_VERSCHIEBUNG = 5e-3
#: sigma_v an jedem Integrationspunkt ausserhalb der Zonen: hoechstens so viel
#: Aenderung [Pa] zwischen den letzten beiden Newton-Schritten. Seit dem
#: 14.10.2026 - Ingenieurkriterium des Anwenders („Spannungen auf 1 N/mm²
#: stabil“). Mit den Zonen aus zwei Elementringen (r + 2 h, spitzen/zeigen
#: 373c6a1) liegen Elemente ausserhalb der Zone, die die alte Zone max(4 h; r)
#: noch enthielt; an der Ankerplatte der Pruefung standen sie nach dem Abbruch
#: ohne diese Bedingung bis 3,26 N/mm² neben der strengen Rechnung (15
#: Newton-Schritte, Kraft und Verschiebung in ihren Grenzen).
SPITZEN_SPANNUNG = 1e6

#: Kleinster Verfestigungsmodul **der Tangente**, bezogen auf 3G. Bei sehr
#: kleiner Verfestigung ist D_ep in Fliessrichtung fast singulaer (Eigenwert
#: 2G (H/3G)/(1 + H/3G)), und oberhalb der Grenzlast wird es K + ΔK auch: am
#: Rohr nach Hill (tests.messung_rohr_plastisch, E_t/E = 1e-12, 23.09.2026)
#: brach der Loeser dort mit "Gleichungssystem singulaer" ab und nannte ein
#: Element als Splitter. Mit dem Boden meldet der Newton "nicht konvergiert".
#: Nur ΔK sieht den Boden; die Rueckfuehrung rechnet mit dem wahren H, das
#: Ergebnis im Gleichgewicht ist davon frei. 1e-6 war zu klein (ueber der
#: Grenzlast wieder singulaer), 1e-3 kostete 13 statt 9 Schritte bei 0,97 p_L.
#: Ab E_t/E = 1,2e-4 (nu = 0,3) greift der Boden nicht - dort, also bei jeder
#: ueblichen Verfestigung, rechnet der Newton bitgleich wie vorher.
#: Seit dem 13.10.2026 greift er auch auf dem Plateau ueber f_u (H = 0) und
#: bei „ohne Verfestigung“ (E_t/E = 1e-4 liegt unter 1,2e-4): dort ist die
#: Tangente um diesen Boden steifer als die konsistente.
H_TANGENTE = 1e-4

#: Verfestigung je Werkstoff (Material.verfestigung, seit dem 13.10.2026) als
#: Steigung des plastischen Asts der Spannungs-Dehnungs-Linie E_t/E.
#: Entscheidung des Anwenders: „bilinear mit E/100 bis f_u, danach ideal
#: plastisch (entspricht EN 1993-1-5 C.6) … Vorgabe E/100, wählbar auch ohne
#: Verfestigung (E/10 000)“. EN 1993-1-5 Bild C.2 zeichnet die Steigungen in
#: das σ-ε-Bild, also als Tangente der **Gesamtkurve** E_t, nicht als
#: Verfestigungsmodul H der Fliessbedingung σ_y = f_y + H ε_p. Mit
#: E_t = E H/(E + H) ist dann H = E r/(1 − r): fuer E/100 H = E/99
#: (2121,2 N/mm2 bei E = 210 000), fuer E/10 000 H = E/9 999 (21,0 N/mm2).
#: Das ist genau die Lesart der bisherigen Einstellung E_t/E = 1 %; Rechnungen,
#: die f_u nicht erreichen, bleiben darum bitgleich. Haette „E/100“ H gemeint,
#: waere H 2100 statt 2121,2 N/mm2 (1 % weicher), f_u = 490 bei f_y = 355
#: erst bei ε_p = 6,43 % statt 6,36 % erreicht.
VERFESTIGUNG_VORGABE = 0.01
VERFESTIGUNG_OHNE = 1e-4


@dataclass
class Plastizitaet:
    """Einstellungen (am Modell): Fliessen rechnen, Verfestigung E_t/E,
    Laststufen, Iterationen je Stufe, Toleranz (Aenderung der plastischen
    Knotenlasten gegen die aeussere Last).

    ``verfahren`` waehlt den Weg: ``"tangente"`` ist das Newton-Verfahren mit
    der konsistenten elastoplastischen Tangente (eine Faktorisierung je
    Schritt, dafuer wenige Schritte, unabhaengig von der Verfestigung),
    ``"anfangsdehnung"`` die Anfangsdehnungs-Iteration bei fester Steifigkeit
    (eine Faktorisierung je Rechnung, dafuer linear mit dem Faktor 1 − E_t/E).

    ``kontakt`` gilt nur mit Kontakt: ``"verschachtelt"`` (Vorgabe) iteriert
    den Kontakt in jedem Newton-Schritt aus, ``"gemeinsam"`` laesst den
    Loeser die Kontaktiteration innerhalb einer Laststufe abkuerzen (und in
    beiden Wegen den elastischen Vorlauf weg) - weniger Zerlegungen, an
    Reibung nahe der Grenzlast aber ein anderes Ergebnis; siehe
    :func:`_newton`. Seit dem 06.10.2026 ist "gemeinsam" als Versuch
    gekennzeichnet und jedes so gerechnete Ergebnis traegt eine Warnung
    (:data:`GEMEINSAM_WARNUNG`). Ein unbekannter Wert rechnet verschachtelt,
    und der Loeser meldet ihn.
    """
    an: bool = False
    #: E_t/E fuer jeden Werkstoff ohne eigene Angabe (Material.verfestigung
    #: None, seit dem 13.10.2026 die Vorgabe der Werkstoffe); 0,01 = E/100
    verfestigung: float = VERFESTIGUNG_VORGABE
    laststufen: int = 3
    iterationen: int = 25
    toleranz: float = 1e-3
    verfahren: str = "tangente"
    #: Punkte ueber die Dicke des hex8 (Richtung t, im Sweep die Lagen), wenn
    #: Fliessen gerechnet wird: n >= 3 legt n Gauss-Lobatto-Punkte in t (die
    #: aeussersten auf der Oberflaeche), 2 laesst die 2x2x2-Gaussregel. Warum
    #: (Auftrag A2, gemessen 22.09.2026, Kragtraeger 200 x 200 mm unter
    #: 1,20 M_el, Randfaser nach der Momenten-Kruemmungs-Beziehung 236,35
    #: N/mm2 und eps_p 0,0315 %): mit 2x2x2 fliesst eine Lage **nicht** (der
    #: aeusserste Punkt bei 57,7 % der halben Hoehe zeigt 162 N/mm2), zwei
    #: Lagen auch nicht (219); mit fuenf Lobatto-Punkten trifft schon eine
    #: Lage die Randfaser auf -0,20 N/mm2, zwei auf -0,20, vier auf -0,07
    #: (eps_p -15 / -15 / -5 %). Drei Punkte reichen bei einer Lage nicht
    #: (+45 N/mm2: die Regel kennt nur Rand und Mitte und legt das ganze
    #: plastische Moment auf die Randfaser). Fuer Parallelepipede ist die
    #: elastische Steifigkeit mit jeder Regel >= 2 Punkten dieselbe.
    dicke_punkte: int = 5
    kontakt: str = KONTAKT_WEGE[0]
    #: Abbruch einer Laststufe (:data:`ABBRUCH_WEGE`, seit dem 13.10.2026):
    #: "ingenieurmaessig" (Vorgabe) nimmt die auffaelligen netzabhaengigen
    #: Spitzen aus dem Mass der Konvergenz aus, "streng" misst ueber das ganze
    #: Modell wie bis dahin. Eine Datei ohne den Schluessel rechnet die
    #: Vorgabe; ein unbekannter Wert ebenso, und der Loeser meldet ihn.
    abbruch: str = ABBRUCH_WEGE[0]
    #: Konvergenz des Kontaktlaufs ueber Ingenieurgroessen (14.10.2026,
    #: Entscheidung des Anwenders): pendelt der Status von Kontaktknoten mit
    #: Periode 2, wird er eingefroren und geprueft (solver.PENDEL_STABILISIEREN).
    #: Der Lauf gilt als konvergiert, wenn die Restwechsel zusammen hoechstens
    #: ``pendel_kraft_anteil`` der Kontaktkraft tragen (Vorgabe 0,1 %) und ihre
    #: Klaffung bzw. Durchdringung hoechstens ``pendel_weg`` [m] ist (Vorgabe
    #: 1 µm). Gilt fuer jeden Kontaktlauf, auch ohne Fliessen; eine Schranke 0
    #: schaltet die Regel ab (streng wie vor dem 14.10.2026).
    pendel_kraft_anteil: float = 1.0e-3
    pendel_weg: float = 1.0e-6
    #: Spannschritt einer Vorspannkraft (Soll nach Verankerung) in so vielen
    #: gleichen Stufen (statik3d.vorspannkraft.spannstufen, 14.10.2026); 0 heisst
    #: automatisch: mit Kontakt oder Fliessen gestuft, sonst ein Schritt.
    spannstufen: int = 0
    #: Kontaktstatus der ersten Laststufe kalt, wenn ihre Last nicht proportional
    #: zur Last des Vorlaufs ist (Vorschlag 1, Entscheidung des Anwenders vom
    #: 14.10.2026; :func:`nicht_proportional`). Nur der Kontaktstatus wird
    #: zurueckgesetzt, nie der plastische Zustand; bei proportionalen Stufen
    #: bleibt der Warmstart. Vorgabe an: am Drehlager (V36, Starr mit mu 0,1)
    #: pendelte der warme Start der Stufe 1 aus dem Vorlauf mit voller Last am
    #: Deckel, kalt gestartet nicht (v36_werk, 14.10.2026).
    kaltstart_nicht_proportional: bool = True

    #: Einstellungen, die am 14.10.2026 dazukamen, mit ihrer Vorgabe: mit ihr
    #: stehen sie nicht in der Modelldatei (:meth:`als_dict`)
    NEU_14_10 = {"pendel_kraft_anteil": 1.0e-3, "pendel_weg": 1.0e-6, "spannstufen": 0,
                 "kaltstart_nicht_proportional": True}

    def als_dict(self) -> dict:
        """Zum Speichern (Model.to_dict): die Einstellungen vom 14.10.2026 nur,
        wenn sie von ihrer Vorgabe abweichen - wie Vorspannung.als_dict. Sonst
        wuchs eine aeltere Datei beim Laden und Speichern um 75 Byte
        (tests/test_vorspannkraft: „alte Datei … bitgleich“, 6431 / 6506 Byte),
        und jede Ergebnisdatei passte nicht mehr zu ihrem Modell, denn die
        Rechenkennung (ergebnisse.rechenkennung) liest dieselbe Form. Eine Datei
        ohne die Schluessel bekommt beim Laden die Vorgabe."""
        d = asdict(self)
        for k, v in self.NEU_14_10.items():
            if k in d and d[k] == v:
                del d[k]
        return d

    def H(self, E: float) -> float:
        """Verfestigungsmodul H aus der Tangente E_t = r E: H = E r / (1 - r)."""
        r = max(0.0, min(float(self.verfestigung), 0.999))
        return float(E) * r / (1.0 - r)


def vergleichsspannung(sig) -> float:
    sig = np.asarray(sig, float)
    # (a + b + c) / 3 statt sig[:3].mean(): numpys mean kostet auf drei
    # Zahlen rund 5 µs Aufrufaufwand, bei 1,94 Mio. Aufrufen je
    # Plastizitaetsschritt also ueber 10 s (cProfile 19.09.2026)
    p = (sig[0] + sig[1] + sig[2]) / 3.0
    s = sig - p * _EINS
    return float(np.sqrt(1.5 * (s[0] ** 2 + s[1] ** 2 + s[2] ** 2) + 3.0 * (s[3] ** 2 + s[4] ** 2 + s[5] ** 2)))


def rueckfuehrung(sig_trial, fy: float, H: float, G: float, eps_p_eq: float = 0.0,
                  fu: float = None) -> tuple:
    """Radial return. Rueckgabe (σ, Δε_p (Voigt, Ingenieurgleitungen), Δγ).

    ``fu`` (seit dem 13.10.2026): die Grenze der Verfestigung - bilinear bis
    f_u, danach ideal plastisch (Entscheidung des Anwenders, EN 1993-1-5 C.6):

        σ_y(ε_p) = min(fy + H ε_p, fu)

    Der Knick wird exakt behandelt. Liegt der Punkt schon auf dem Plateau oder
    laeuft der Schritt ueber den Knick (fy + H (ε_p,n + Δγ_H) > fu mit dem Δγ_H
    des verfestigenden Asts), endet er auf der Fliessflaeche q = fu:
    Δγ = (q_trial − fu)/(3G). Das ist die einzige Loesung von
    q_trial − 3G Δγ = σ_y(ε_p,n + Δγ), denn die linke Seite faellt und die
    rechte steigt nicht. Ohne ``fu`` (None, 0) wie bis dahin ohne Grenze; ist
    fu < fy, gilt fy als Grenze (ideal plastisch ab fy)."""
    sig = np.asarray(sig_trial, float)
    p = (sig[0] + sig[1] + sig[2]) / 3.0
    s = sig - p * _EINS
    q = vergleichsspannung(sig)
    grenze = max(float(fu), float(fy)) if fu else np.inf
    f = q - min(float(fy) + float(H) * float(eps_p_eq), grenze)
    if f <= 0.0 or q <= 0.0:
        return sig.copy(), np.zeros(6), 0.0
    dgamma = f / (3.0 * float(G) + float(H))
    if float(fy) + float(H) * (float(eps_p_eq) + dgamma) > grenze:
        dgamma = (q - grenze) / (3.0 * float(G))      # auf dem Plateau bzw. ueber den Knick
    n = 1.5 * s / q                                   # Tensorkomponenten
    sig_neu = sig - 2.0 * float(G) * dgamma * n
    d_eps_p = dgamma * n * _SCHUB                     # Ingenieurgleitungen
    return sig_neu, d_eps_p, float(dgamma)


def verfestigung_wirksam(fy: float, H: float, eps_p_eq_neu: float, fu: float = None) -> float:
    """Das H, mit dem die konsistente Tangente eines Punkts rechnet: H auf dem
    verfestigenden Ast, 0 auf dem Plateau ueber fu (auch nach einem Schritt
    ueber den Knick - dort ist dΔγ/dq_trial = 1/(3G)). ``eps_p_eq_neu`` ist
    die plastische Vergleichsdehnung **nach** der Rueckfuehrung."""
    if not fu:
        return float(H)
    grenze = max(float(fu), float(fy))
    return 0.0 if float(fy) + float(H) * float(eps_p_eq_neu) > grenze else float(H)


# --------------------------------------------------------------------------
# Verfestigung und Grenze je Werkstoff (13.10.2026)
# --------------------------------------------------------------------------
def werkstoff_verfestigung(mat, einst: "Plastizitaet" = None) -> float:
    """E_t/E eines Werkstoffs: seine eigene Angabe (Material.verfestigung),
    sonst die Vorgabe der Rechnung (``einst.verfestigung``, Vorgabe E/100);
    auf 0 bis 0,999 begrenzt wie :meth:`Plastizitaet.H`."""
    r = getattr(mat, "verfestigung", None)
    if r is None:
        r = getattr(einst, "verfestigung", VERFESTIGUNG_VORGABE) if einst is not None \
            else VERFESTIGUNG_VORGABE
    return max(0.0, min(float(r), 0.999))


def werkstoff_grenze(mat):
    """Die Grenze der Verfestigung [Pa]: f_u des Werkstoffs (bei Schrauben
    f_ub, bei Spannstahl f_pk - sie stehen alle in ``Material.fu``) oder None.

    **Immer aus dem Werkstoff** (Entscheidung des Anwenders vom 13.10.2026):
    kein 1,3 f_y wie Material.ultimate_strength, keine Sortentabelle und keine
    Dickentabelle - so wie die Fliessgrenze auch nur ``Material.fy`` liest.
    Fehlt f_u, verfestigt der Werkstoff ohne Grenze wie bis zum 13.10.2026,
    und die Rechnung meldet es (:func:`meldung_ohne_grenze`)."""
    fu = getattr(mat, "fu", None)
    return float(fu) if fu and float(fu) > 0.0 else None


def meldung_ohne_grenze(mat) -> str:
    """Die Zeile fuer einen Werkstoff mit Streckgrenze, aber ohne f_u."""
    gn = mat.grenze_name() if hasattr(mat, "grenze_name") else "f_u"
    return (f"Werkstoff „{mat.name}“ ohne {gn} – Verfestigung ohne Grenze, "
            f"bitte {gn} eingeben")


def werkstoffe_ohne_grenze(model, aktiv=None) -> list:
    """Die Werkstoffe der Volumenelemente, die fliessen koennen (f_y), aber
    keine Grenze der Verfestigung haben (f_u fehlt) - fuer die Netzabnahme."""
    namen = {model.elements[i].mat for i in _solid_elemente(model, aktiv)}
    aus = []
    for nm in sorted(str(n) for n in namen):
        mat = model.materials.get(nm)
        if mat is not None and getattr(mat, "fy", None) and werkstoff_grenze(mat) is None:
            aus.append(mat)
    return aus


def _zahl(x: float) -> str:
    """Eine Zahl fuer den Anwender: kurz, mit Komma."""
    return f"{x:g}".replace(".", ",")


def _e_durch(r: float) -> str:
    """„E/100“, „E/10 000“ - der Nenner mit Leerzeichen als Tausendertrenner."""
    n = 1.0 / r
    if abs(n - round(n)) < 1e-6 * n:
        t = f"{int(round(n)):,}".replace(",", " ")
    else:
        t = f"{n:.4g}".replace(".", ",")
    return f"E/{t}"


#: Die Wahl der Werkstoffmaske (gui.main, Feld „Verfestigung“)
VERFESTIGUNG_TEXT_OHNE = "ohne Verfestigung (E/10 000)"


def verfestigung_text(r, vorgabe: float = VERFESTIGUNG_VORGABE) -> str:
    """Der Text der Werkstoffmaske zu Material.verfestigung: None ->
    „Vorgabe E/100“ (bzw. der Wert der Rechnung), 1e-4 -> „ohne Verfestigung
    (E/10 000)“, sonst „E/250“."""
    if r is None:
        return f"Vorgabe {_e_durch(vorgabe)}" if vorgabe > 0 else "Vorgabe ideal plastisch"
    if abs(float(r) - VERFESTIGUNG_OHNE) <= 1e-12:
        return VERFESTIGUNG_TEXT_OHNE
    if float(r) <= 0.0:
        return "ideal plastisch (E_t = 0)"
    return _e_durch(float(r))


def verfestigung_lesen(text) -> tuple:
    """(ok, Wert oder None fuer die Vorgabe, Grund) aus dem Text der
    Werkstoffmaske: „Vorgabe …“, „ohne Verfestigung …“ oder „E/n“ mit n > 1
    (Leerzeichen als Tausendertrenner, Komma oder Punkt als Dezimalzeichen)."""
    import re
    t = str(text or "").strip()
    if not t or t.lower().startswith("vorgabe"):
        return True, None, ""
    if t.lower().startswith("ohne"):
        return True, VERFESTIGUNG_OHNE, ""
    m = re.fullmatch(r"(?i)e\s*/\s*([0-9][0-9 ]*(?:[.,][0-9]+)?)\s*", t)
    if m:
        n = float(m.group(1).replace(" ", "").replace(",", "."))
        if n > 1.0:
            return True, 1.0 / n, ""
    return False, None, (f"Verfestigung „{t}“ nicht verstanden – „Vorgabe E/100“, "
                         f"„{VERFESTIGUNG_TEXT_OHNE}“ oder die Steigung als E/n "
                         "(n größer als 1, etwa E/250) eintragen. Nicht übernommen.")


def grenze_text(mat, einst: "Plastizitaet" = None) -> str:
    """Die Anzeige der Werkstoffmaske: welche Grenze, ihr Wert und die
    plastische Dehnung, bei der sie erreicht ist - oder dass sie fehlt."""
    gn, fn = mat.grenze_name(), mat.fliess_name()
    fu = werkstoff_grenze(mat)
    if fu is None:
        return f"{gn} fehlt – Verfestigung ohne Grenze, bitte {gn} eingeben"
    text = f"{gn} = {fu / 1e6:g} N/mm²".replace(".", ",")
    fy = getattr(mat, "fy", None)
    if not fy:
        return text + f", ohne {fn} bleibt der Werkstoff elastisch"
    if fu <= float(fy):
        return text + f" ≤ {fn}: ideal plastisch ab {fn}"
    r = werkstoff_verfestigung(mat, einst)
    if r <= 0.0:
        return text + ", danach ideal plastisch"
    H = float(mat.E) * r / (1.0 - r)
    ep = (fu - float(fy)) / H
    return text + f", erreicht bei ε_p = {ep * 100:.2f} %, danach ideal plastisch".replace(".", ",")


def tangenten_differenz(dev, q, dgamma, G, H):
    """ΔD = D_ep − D_el (n,6,6) fuer fliessende Elemente, konsistent zur
    Rueckfuehrung in :func:`rueckfuehrung`.

    ``dev`` ist der Deviator der **Versuchsspannung** (Tensorkomponenten in
    Voigt-Reihenfolge), ``q`` ihre Vergleichsspannung, ``dgamma`` das Δγ der
    Rueckfuehrung. Mit θ = 1 − 3G Δγ/q und θ̄ = 1/(1 + H/3G) − (1 − θ):

        D_ep − D_el = 2G (θ − 1) (I − δ⊗δ/3) − 2G θ̄ N⊗N

    Der Kugelanteil faellt heraus - Fliessen ist volumentreu, D_ep und D_el
    unterscheiden sich nur deviatorisch. Darum traegt ΔK nur dort Eintraege,
    wo Elemente fliessen, und es bleibt duenn.

    Fuer H > 0 bleibt D_ep positiv definit: der Eigenwert in Richtung N ist
    2G(θ − θ̄) = 2G (H/3G)/(1 + H/3G) > 0, quer dazu 2Gθ = 2G (fy + H ε_p)/q > 0.
    """
    G = np.asarray(G, float)
    H = np.asarray(H, float)
    q = np.asarray(q, float)
    theta_1 = -3.0 * G * np.asarray(dgamma, float) / q          # θ − 1
    quer = 1.0 / (1.0 + H / (3.0 * G)) + theta_1                # θ̄
    N = np.asarray(dev, float) * (np.sqrt(1.5) / q)[:, None]    # s/‖s‖, ‖s‖ = q/√1,5
    dD = (2.0 * G * theta_1)[:, None, None] * _P_DEV[None, :, :]
    dD -= (2.0 * G * quer)[:, None, None] * (N[:, :, None] * N[:, None, :])
    return dD


def _B_stapel(g):
    """Verzerrungsmatrix B (m,6,3k) aus den Ableitungen g (m,k,3) - dieselbe
    Belegung wie elements.solid._B_from_grad, nur ueber einen Stapel."""
    m, k = g.shape[0], g.shape[1]
    B = np.zeros((m, 6, 3 * k))
    B[:, 0, 0::3] = g[:, :, 0]
    B[:, 1, 1::3] = g[:, :, 1]
    B[:, 2, 2::3] = g[:, :, 2]
    B[:, 3, 0::3] = g[:, :, 1]
    B[:, 3, 1::3] = g[:, :, 0]
    B[:, 4, 1::3] = g[:, :, 2]
    B[:, 4, 2::3] = g[:, :, 1]
    B[:, 5, 0::3] = g[:, :, 2]
    B[:, 5, 2::3] = g[:, :, 0]
    return B


def _dk_block(d, fliesst, dev, q, dgamma, G, H, ndof):
    """ΔK = Σ_gp ∫ Bᵀ (D_ep − D_el) B dV der fliessenden **Gausspunkte**.

    Das ist die konsistente Tangente: seit dem 20.09.2026 haengt eps_p an der
    Dehnung **an jedem Gausspunkt** (siehe :class:`Zustand`), also ist

        ∂F_p/∂u = Σ_gp w |J| Bᵀ_gp D (∂eps_p,gp/∂ε_gp) B_gp = −Σ_gp w |J| Bᵀ ΔD B.

    Vorher stand hier die Mittelpunktfassung V Bᵀ_m ΔD B_m, und das war zu
    ihrer Zeit richtig: eps_p hing allein an der Dehnung in der Mitte, F_p
    reagierte auf keine Biegemode, und die Gausspunktfassung war deshalb in
    genau diesen Moden zu weich - am Reibblock (hex8,
    tests.test_plastizitaet.test_kontakt) lief sie mit dem Faktor rund 100 je
    Schritt davon (1,7e0 → 1,0e36 in 19 Schritten), waehrend die
    Mittelpunktfassung in 4 Schritten konvergierte (20.09.2026). Mit dem
    Zustand je Gausspunkt faellt dieser Grund weg: F_p reagiert jetzt auf
    dieselben Moden, die ΔK weicher macht.

    ΔD ist negativ semidefinit und symmetrisch, K + ΔK also positiv definit -
    CHOLMOD im Loeser vertraegt keine unsymmetrische Matrix.

    Gerechnet wird in Bloecken von rund 16 MB je Zwischenfeld (ke, Zeilen,
    Spalten sind alle (m, 3k, 3k)): am Drehlager waeren 646.706 Tetraeder auf
    einmal 745 MB allein fuer die Zeilennummern, bei hex20 (60x60 je Element)
    das Fuenfundzwanzigfache.
    """
    from scipy import sparse
    # Ohne (oder mit sehr kleiner) Verfestigung haelt ein Boden die Tangente
    # regulaer - siehe H_TANGENTE; die Rueckfuehrung bleibt beim wahren H
    H = np.maximum(H, H_TANGENTE * 3.0 * G)
    nz = 3 * d["k"]
    zeilen, spalten, werte = [], [], []
    gr = max(1, 2_000_000 // (nz * nz))
    eas = d.get("eas")
    if eas is not None:
        # Mit inkompatiblen Moden muss ΔK **genauso kondensiert** werden wie K
        # selbst, sonst passt die Tangente nicht zur Last:
        #     ΔK = (Kuu+ΔKuu) − (Kua+ΔKua)(Kaa+ΔKaa)^-1 (Kua+ΔKua)ᵀ
        #          − [Kuu − Kua Kaa^-1 Kuaᵀ]
        # Ohne den kondensierten Anteil lief der Newton am Kragtraeger mit
        # vier hex8-Lagen auf 1e50 davon (20.09.2026); damit konvergiert er.
        betroffen = np.flatnonzero(fliesst.any(axis=0))
        if betroffen.size == 0:
            return sparse.csr_matrix((ndof, ndof))
        for a0 in range(0, betroffen.size, gr):
            teil = betroffen[a0:a0 + gr]
            mm = len(teil)
            na = eas["Ba"].shape[3]
            dKuu = np.zeros((mm, nz, nz))
            dKua = np.zeros((mm, nz, na))
            dKaa = np.zeros((mm, na, na))
            for gp, (_dNg, gew) in enumerate(d["lasten"]):
                maske = fliesst[gp][teil]
                if not maske.any():
                    continue
                qg = q[gp][teil]
                # tangenten_differenz ist bei dgamma = 0 **nicht** null (der
                # Term θ̄ bleibt stehen) - die nicht fliessenden Punkte
                # muessen darum ausdruecklich geloescht werden.
                dD = tangenten_differenz(dev[gp][teil], np.where(qg > 0.0, qg, 1.0),
                                         dgamma[gp][teil], G[gp][teil], H[gp][teil])
                dD[~maske] = 0.0
                B = _b_punkt(d, gp, teil)
                Ba = eas["Ba"][gp][teil]
                w = gew[teil][:, None, None]
                dDB = np.einsum("nij,njk->nik", dD, B)
                dDBa = np.einsum("nij,njk->nik", dD, Ba)
                dKuu += w * np.einsum("nji,njk->nik", B, dDB)
                dKua += w * np.einsum("nji,njk->nik", B, dDBa)
                dKaa += w * np.einsum("nji,njk->nik", Ba, dDBa)
            Kua_e = eas["Kua"][teil]
            Kaa_e = eas["Kaa"][teil]
            A1 = Kua_e + dKua
            ke = (dKuu
                  - np.einsum("nij,njk->nik", A1,
                              np.linalg.solve(Kaa_e + dKaa, A1.transpose(0, 2, 1)))
                  + np.einsum("nij,njk->nik", Kua_e,
                              np.linalg.solve(Kaa_e, Kua_e.transpose(0, 2, 1))))
            ke = 0.5 * (ke + ke.transpose(0, 2, 1))     # gegen Rundung symmetrisch
            dd = d["dofs"][teil]
            zeilen.append(np.repeat(dd, nz, axis=1).ravel())
            spalten.append(np.tile(dd, (1, nz)).ravel())
            werte.append(ke.reshape(-1))
        return sparse.coo_matrix((np.concatenate(werte),
                                  (np.concatenate(zeilen), np.concatenate(spalten))),
                                 shape=(ndof, ndof)).tocsr()
    for gp, (_dNg, gew) in enumerate(d["lasten"]):
        stellen = np.flatnonzero(fliesst[gp])
        if stellen.size == 0:
            continue
        for a0 in range(0, stellen.size, gr):
            teil = stellen[a0:a0 + gr]
            dd = d["dofs"][teil]
            B = _b_punkt(d, gp, teil)
            dD = tangenten_differenz(dev[gp][teil], q[gp][teil], dgamma[gp][teil],
                                     G[gp][teil], H[gp][teil])
            ke = gew[teil][:, None, None] * np.einsum(
                "nji,njk->nik", B, np.einsum("nij,njk->nik", dD, B))
            zeilen.append(np.repeat(dd, nz, axis=1).ravel())
            spalten.append(np.tile(dd, (1, nz)).ravel())
            werte.append(ke.reshape(-1))
    if not werte:
        return sparse.csr_matrix((ndof, ndof))
    return sparse.coo_matrix((np.concatenate(werte),
                              (np.concatenate(zeilen), np.concatenate(spalten))),
                             shape=(ndof, ndof)).tocsr()


class Zustand:
    """Plastische Dehnungen je **Gausspunkt**: {i: eps_p (P,6)}, {i: eps_p_eq (P,)}.

    Bis zum 20.09.2026 stand hier ein Wert je Element, gemessen in der
    Elementmitte. Beim ``tet4`` ist das dasselbe - ein Gausspunkt, konstante
    Dehnung -, beim Sechsflaechner war es falsch: unter reiner Biegung ist die
    Spannung in der Elementmitte **null**, und der Gradient der inkompatiblen
    Moden diag(-2r, -2s, -2t) verschwindet dort ebenfalls. Die Mitte ist genau
    der eine Punkt, an dem der hex8 seine Biegung nicht zeigt.

    Gemessen am Kragtraeger 200 x 200 mm unter reiner Biegung mit dem
    1,20-fachen des elastischen Grenzmoments (fy = 235 N/mm2, Randfaser also
    282 N/mm2 - sie **muss** fliessen), 20.09.2026:

        Lagen ueber die Hoehe    1       2       4       8    tet4 (4)
        sigma_v max [N/mm2]    0,0   146,0   223,5   239,3     235,7
        fliessende Elemente      0       0       0       8         2

    Mit einer hex8-Lage meldete das Programm null Spannung und kein
    fliessendes Element - unter einem Moment, das den Querschnitt
    plastifiziert. Die Durchbiegung stimmte dabei: das Element **trug**
    richtig, es berichtete nur nicht.

    ``sigma0`` {i: (6,)} ist die Anfangsspannung, die nicht aus dem Fliessen
    kommt: die einer Vorspannung als Koerper (assemble.solid_prestress, im
    Loeser temp["sigma0"]), je Element konstant. Die wahre Spannung ist
    σ = D(ε − ε_p) − σ₀, und so prueft die Rueckfuehrung seit dem 10.10.2026
    (_schritt_teil, _schritt_schleife). Bis dahin rechnete sie mit
    D(ε − ε_p) und sah σ₀ nicht: eine Temperatur im Volumen ist isotrop und
    aendert den Deviator nicht, eine einachsige Bolzenvorspannung aber sehr
    wohl. Am Bolzen mit F_v = 0,98 f_y A und Klemmpaket
    (tests/test_vorspannung_fliessen.py) floss bei 1,3 P_y nichts, angezeigt
    wurden 362,3 statt 355,2 N/mm2. Der Wert wird nicht kopiert, sondern
    weitergereicht - er aendert sich in einer Rechnung nicht (die Vorspannung
    wirkt ab der ersten Laststufe voll, stufenlast).
    """

    def __init__(self, sigma0: dict = None):
        self.eps_p: dict = {}
        self.eps_p_eq: dict = {}
        self.sigma0: dict = dict(sigma0 or {})

    def kopie(self) -> "Zustand":
        z = Zustand()
        z.eps_p = {i: np.array(v, float, copy=True) for i, v in self.eps_p.items()}
        z.eps_p_eq = {i: np.array(v, float, copy=True) for i, v in self.eps_p_eq.items()}
        z.sigma0 = self.sigma0
        return z

    def fliessend(self) -> list:
        """Elemente, in denen **mindestens ein** Gausspunkt fliesst."""
        return [i for i, v in self.eps_p_eq.items() if float(np.max(v)) > 0.0]

    def eq_max(self) -> float:
        """Groesste plastische Vergleichsdehnung ueber alle Punkte."""
        if not self.eps_p_eq:
            return 0.0
        return float(max(float(np.max(v)) for v in self.eps_p_eq.values()))


def _punktfeld(v, P: int, spalten: int) -> np.ndarray:
    """Einen gespeicherten Zustandswert auf die Form (P,) bzw. (P,spalten)
    bringen - auch wenn er aus einer aelteren Rechnung je Element stammt."""
    a = np.asarray(v, float)
    ziel = (P,) if spalten == 0 else (P, spalten)
    if a.shape == ziel:
        return a
    if spalten == 0:
        return np.broadcast_to(a.reshape(-1)[:1], ziel).copy() if a.size == 1 \
            else np.broadcast_to(a.reshape(-1), ziel).copy()
    return np.broadcast_to(a.reshape(-1, spalten)[0], ziel).copy() if a.size == spalten \
        else a.reshape(ziel)


def _solid_elemente(model, aktiv=None) -> list:
    from . import assemble as asm
    idx = asm.aktive_indizes(model, aktiv)
    return [i for i in idx if model.elements[i].typ in asm.SOLID_TYPES]


def _stapel(model, elemente: list, typ: str) -> list:
    """Geometrie- und Werkstoffdaten der Elemente eines Typs - je Gruppe des
    Dehnungsoperators ein Eintrag (bei den isoparametrischen Typen genau einer).

    Die Kinematik kommt aus **dem** Operator des Elements
    (elements.solid.dehnungsoperator), den auch Steifigkeit und
    Spannungsrueckrechnung lesen. Bis zum 22.09.2026 stellte die Plastizitaet
    ihre Gradienten hier selbst aus _ISO auf - dieselben Zahlen, aber ein
    zweiter Weg: haette ein Element eine andere Kinematik bekommen (B-bar,
    mehr Punkte ueber die Dicke), haetten Steifigkeit und Fliessen still mit
    zwei verschiedenen gerechnet.

    Haengt nur am Netz und an den Werkstoffen, nicht an der Verschiebung -
    darum wird es am Modell gemerkt und ueber die Schritte einer Rechnung
    wiederverwendet (am Drehlager kostet der Aufbau rund 5,7 s, jeder weitere
    Schritt danach 1,4 s statt 51,5 s). Der Schluessel ist der Operator
    selbst (sein Fingerabdruck umfasst Elemente und Koordinaten) und die
    Werkstoffwerte - bis zum 22.09.2026 waren es Typ, Zahl, erstes und letztes
    Element, und ein geaenderter E-Modul blieb unbemerkt.

    ``lasten`` traegt je Integrationspunkt die Gradienten (oder None bei einem
    allgemeinen B) und das Gewicht w*|det J|; daraus entstehen die plastischen
    Knotenlasten f = ∫ Bᵀ σ0 dV. Bei tet4 ist das ein Punkt und das Gewicht
    gleich dem Volumen, bei hex8 sind es acht.
    """
    from .elements import solid as sl
    idx = np.asarray(elemente, dtype=np.int64)
    ops = sl.dehnungsoperator(model, typ, idx, merken=True)
    namen = tuple(model.elements[int(i)].mat for i in idx)
    # f_u und die eigene Verfestigung gehoeren seit dem 13.10.2026 dazu: ein
    # geaenderter Werkstoff darf nicht mit den alten Werten weiterrechnen
    wkey = (hash(namen), tuple(sorted(
        (nm, float(model.materials[nm].E), float(model.materials[nm].nu),
         getattr(model.materials[nm], "fy", None), getattr(model.materials[nm], "fu", None),
         getattr(model.materials[nm], "verfestigung", None)) for nm in set(namen))))
    cache = getattr(model, "_plast_stapel", None)
    if cache is None:
        cache = model._plast_stapel = {}
    alt = cache.get(typ)
    if alt is not None and alt[0] is ops and alt[1] == wkey:
        return alt[2]
    daten_liste = []
    for op in ops:
        daten_liste.append(_stapel_teil(model, op))
    cache[typ] = (ops, wkey, daten_liste)
    return daten_liste


def _stapel_teil(model, op) -> dict:
    """Die Daten eines Operators: Werkstoffe je Element, FHG, Lasten, Moden."""
    from .elements import solid as sl
    idx = op.idx
    n = op.n
    E = np.empty(n); nu = np.empty(n)
    fy = np.zeros(n); hat_fy = np.zeros(n, bool)
    # Grenze der Verfestigung (inf ohne f_u) und eigene Verfestigung E_t/E
    # (nan = Vorgabe der Rechnung) je Element - seit dem 13.10.2026
    fu = np.full(n, np.inf); r_eigen = np.full(n, np.nan)
    ohne: set = set()
    meldungen: dict = {}            # Werkstoff -> Zeile (ohne f_u, f_u < f_y)
    for a, i in enumerate(idx):
        mat = model.materials[model.elements[int(i)].mat]
        E[a], nu[a] = float(mat.E), float(mat.nu)
        f = getattr(mat, "fy", None)
        if f:
            fy[a], hat_fy[a] = float(f), True
            g = werkstoff_grenze(mat)
            if g is None:
                if mat.name not in meldungen:
                    meldungen[mat.name] = meldung_ohne_grenze(mat)
            else:
                fu[a] = max(g, float(f))
                if g < float(f) and mat.name not in meldungen:
                    meldungen[mat.name] = (
                        f"Werkstoff „{mat.name}“: {mat.grenze_name()} = {_zahl(g / 1e6)} N/mm² kleiner "
                        f"als {mat.fliess_name()} = {_zahl(float(f) / 1e6)} N/mm² – ideal plastisch ab "
                        f"{mat.fliess_name()}")
        else:
            ohne.add(model.elements[int(i)].mat)
        rv = getattr(mat, "verfestigung", None)
        if rv is not None:
            r_eigen[a] = float(rv)
    lam = E * nu / ((1.0 + nu) * (1.0 - 2.0 * nu))
    mu = E / (2.0 * (1.0 + nu))
    lasten = [(op.g[p] if op.nur_gradienten else None, op.w[p]) for p in range(op.P)]
    daten = {"typ": op.typ, "idx": idx, "k": op.k, "op": op,
             "lasten": lasten, "dofs": op.dofs(), "E": E, "nu": nu, "fy": fy,
             "hat_fy": hat_fy, "ohne_fy": ohne, "lam": lam, "mu": mu,
             "fu": fu, "r_eigen": r_eigen, "grenze_meldungen": meldungen}
    if op.Ba is not None:
        daten["eas"] = _eas_daten(op, E, nu)
    return daten


#: Runden des Element-Newtons fuer die inkompatiblen Moden. Gemessen
#: 20.09.2026 am Kragtraeger und am Reibblock: drei bis vier Runden genuegen,
#: acht sind die Sicherung fuer schlecht geformte Elemente.
EAS_RUNDEN = 8
EAS_TOLERANZ = 1e-10


def _eas_daten(op, E, nu) -> dict:
    """Die inneren Moden eines Operators (hex8: Wilson-Moden) als Stapel:
    Ba je Integrationspunkt, Kua, Kaa, D.

    Der hex8 traegt seine Biegung ueber drei Wilson-Moden (1-r^2, 1-s^2,
    1-t^2), die in der Elementmatrix kondensiert werden. Rechnet die
    Plastizitaet ohne sie, passen plastische Lasten und Steifigkeit nicht
    zusammen: die Lasten regen Biegemoden an, in denen die kondensierte
    Steifigkeit viel weicher ist. Gemessen am Kragtraeger unter 1,20 M_el
    (20.09.2026, acht hex8-Lagen ueber die Hoehe): ohne die Moden in der
    Plastizitaet meldete das Programm 40 von 40 Elementen fliessend mit
    eps_p,eq 25,1 % (Stand 20.09.2026; der Weg ohne Moden ist nicht mehr da
    und nicht nachgemessen). Mit ihnen sind es 16 von 40 mit eps_p,eq 0,42 %
    (nachgemessen 22.09.2026 mit 2x2x2 Gausspunkten, tests/test_plastizitaet.py,
    test_sechsflaechner_fliesst_unter_biegung). Hier stand bis dahin "richtig
    sind 2 von 40 mit 0,025 %" - das widersprach dem Handbuch (0,42 %) und
    der Pruefung.

    Kua = Σ w |J| Bᵀ D Ba, Kaa = Σ w |J| Baᵀ D Ba - aus demselben Operator
    wie die Steifigkeit (elements.solid.matrizen_aus_operator).
    """
    from .elements import solid as sl
    D = sl.D_stapel(E, nu, op.n)
    _Kuu, Kua, Kaa = sl.matrizen_aus_operator(op, D, ohne_kuu=True)
    return {"Ba": op.Ba, "Kua": Kua, "Kaa": Kaa, "D": D}


def _b_punkt(d, p, stellen=None) -> np.ndarray:
    """B (m,6,3k) am Integrationspunkt p fuer die Elemente ``stellen``."""
    dNg = d["lasten"][p][0]
    if dNg is not None:
        return _B_stapel(dNg if stellen is None else dNg[stellen])
    B = d["op"].b(p)
    return B if stellen is None else B[stellen]


def _dehnung_punkt(d, p, ue_flach) -> np.ndarray:
    """Voigt-Dehnung (n,6) am Integrationspunkt p (ohne innere Moden)."""
    dNg = d["lasten"][p][0]
    if dNg is not None:
        return _dehnung(dNg, ue_flach.reshape(len(ue_flach), d["k"], 3))
    return (d["op"].b(p) @ ue_flach[:, :, None])[:, :, 0]


def _eas_alpha(eas, lam, mu2, eps_p, lasten, ue_flach) -> np.ndarray:
    """Die inneren Freiheitsgrade alpha (n,9) zu einer Verschiebung und einer
    plastischen Dehnung.

    Aus der Stationaritaet nach alpha (Σ Baᵀ sigma dV = 0) folgt
        Kaa alpha = h_p − Kuaᵀ u,      h_p = Σ w |J| Baᵀ D eps_p.
    """
    h = _eas_h(eas, lam, mu2, eps_p, lasten)
    rechts = h - np.einsum("nji,nj->ni", eas["Kua"], ue_flach)
    # numpy 2 deutet (n,9) neben (n,9,9) als Matrix, nicht als Stapel von
    # Vektoren - die letzte Achse muss ausgeschrieben werden.
    return np.linalg.solve(eas["Kaa"], rechts[..., None])[..., 0]


def _eas_h(eas, lam, mu2, eps_p, lasten) -> np.ndarray:
    """h_p = Σ_gp w |J| Baᵀ D eps_p  (n,9) - die plastische Last der Moden."""
    Ba = eas["Ba"]
    n = Ba.shape[1]
    h = np.zeros((n, Ba.shape[3]))
    for gp, (_dNg, gew) in enumerate(lasten):
        s0 = _spannung(lam, mu2, eps_p[gp])
        h += gew[:, None] * np.einsum("nji,nj->ni", Ba[gp], s0)
    return h


def _dehnung(dN, ue):
    """Voigt-Dehnungen (n,6) aus den Ableitungen (n,k,3) und den
    Knotenverschiebungen (n,k,3) - xx, yy, zz, xy, yz, zx mit
    Ingenieurgleitungen, wie in elements.solid._B_from_grad."""
    exx = np.einsum("nka,nka->n", dN[:, :, 0:1], ue[:, :, 0:1])
    eyy = np.einsum("nka,nka->n", dN[:, :, 1:2], ue[:, :, 1:2])
    ezz = np.einsum("nka,nka->n", dN[:, :, 2:3], ue[:, :, 2:3])
    gxy = (np.einsum("nk,nk->n", dN[:, :, 1], ue[:, :, 0])
           + np.einsum("nk,nk->n", dN[:, :, 0], ue[:, :, 1]))
    gyz = (np.einsum("nk,nk->n", dN[:, :, 2], ue[:, :, 1])
           + np.einsum("nk,nk->n", dN[:, :, 1], ue[:, :, 2]))
    gzx = (np.einsum("nk,nk->n", dN[:, :, 2], ue[:, :, 0])
           + np.einsum("nk,nk->n", dN[:, :, 0], ue[:, :, 2]))
    return np.stack([exx, eyy, ezz, gxy, gyz, gzx], axis=1)


def _spannung(lam, mu2, eps):
    """sigma = D eps (n,6), ohne die Werkstoffmatrix zu bauen."""
    spur = lam * (eps[:, 0] + eps[:, 1] + eps[:, 2])
    sig = np.empty_like(eps)
    sig[:, 0] = spur + 2.0 * mu2 * eps[:, 0]
    sig[:, 1] = spur + 2.0 * mu2 * eps[:, 1]
    sig[:, 2] = spur + 2.0 * mu2 * eps[:, 2]
    sig[:, 3] = mu2 * eps[:, 3]
    sig[:, 4] = mu2 * eps[:, 4]
    sig[:, 5] = mu2 * eps[:, 5]
    return sig


def _schritt_block(model, u, zustand: Zustand, einst: Plastizitaet, elemente: list,
                   typ: str, log: list = None, tangente: bool = False) -> tuple:
    """Ein Schritt fuer einen Stapel gleichen Typs - dieselbe Rechnung wie
    :func:`_schritt_schleife`, nur als Feldoperationen.

    Gerechnet wird an **jedem Gausspunkt**, nicht in der Elementmitte (siehe
    :class:`Zustand`). Beim tet4 ist das ein Punkt und aendert nichts; beim
    hex8 sind es acht, und erst damit sieht die Plastizitaet die Biegung.

    ``tangente=True`` gibt in info["dK"] zusaetzlich
    ΔK = Σ_gp ∫ Bᵀ (D_ep − D_el) B dV der fliessenden Punkte zurueck.

    Liefert der Dehnungsoperator mehrere Gruppen (verschiedene Punkt- oder
    Knotenzahl), rechnet jede fuer sich; die Ergebnisse werden addiert.
    """
    teile = _stapel(model, elemente, typ)
    if len(teile) == 1:
        return _schritt_teil(model, u, zustand, einst, teile[0], log, tangente)
    F_p = np.zeros(model.ndof)
    neu = zustand.kopie()
    n_fl, q_max, dK = 0, 0.0, None
    sv_teile: list = []
    sv_punkte: list = []
    for d in teile:
        Fb, zb, ib = _schritt_teil(model, u, zustand, einst, d, log, tangente)
        F_p += Fb
        for i in d["idx"]:
            i = int(i)
            if i in zb.eps_p:
                neu.eps_p[i] = zb.eps_p[i]
                neu.eps_p_eq[i] = zb.eps_p_eq[i]
        n_fl += ib["fliessend"]
        q_max = max(q_max, ib["q_max"])
        sv_teile.extend(ib.get("sv_teile") or [])
        sv_punkte.extend(ib.get("sv_punkte") or [])
        if tangente:
            dK = ib["dK"] if dK is None else (dK + ib["dK"])
    info = {"fliessend": n_fl, "q_max": q_max, "sv_teile": sv_teile, "sv_punkte": sv_punkte}
    if tangente:
        info["dK"] = dK
    return F_p, neu, info


def _schritt_teil(model, u, zustand: Zustand, einst: Plastizitaet, d: dict,
                  log: list = None, tangente: bool = False) -> tuple:
    """:func:`_schritt_block` fuer eine Gruppe des Dehnungsoperators."""
    idx, dofs, k = d["idx"], d["dofs"], d["k"]
    lam, mu2 = d["lam"], d["mu"]
    lasten = d["lasten"]
    P = len(lasten)
    n = len(idx)
    ue_flach = np.asarray(u, float)[dofs]
    eps_p = np.zeros((P, n, 6))
    eps_p_eq = np.zeros((P, n))
    hatte = np.zeros(n, bool)
    if zustand.eps_p:
        platz = {int(i): a for a, i in enumerate(idx)}
        for i, v in zustand.eps_p.items():
            a = platz.get(int(i))
            if a is None:
                continue
            eps_p[:, a, :] = _punktfeld(v, P, 6)
            eps_p_eq[:, a] = _punktfeld(zustand.eps_p_eq.get(i, 0.0), P, 0)
            hatte[a] = True
    # Werkstoffwerte je (Gausspunkt, Element), P-fach gelegt
    m = P * n
    eqF = eps_p_eq.reshape(m)
    fyF = np.tile(d["fy"], P)
    hatF = np.tile(d["hat_fy"], P)
    EF = np.tile(d["E"], P)
    nuF = np.tile(d["nu"], P)
    # Verfestigung je Werkstoff (eigene Angabe, sonst die der Rechnung) und
    # ihre Grenze f_u (inf ohne f_u) - seit dem 13.10.2026; ohne eigene
    # Angabe und ohne f_u dieselben Zahlen wie vorher
    r_glob = max(0.0, min(float(einst.verfestigung), 0.999))
    r_el = d.get("r_eigen")
    r_el = np.full(n, r_glob) if r_el is None else \
        np.clip(np.where(np.isnan(r_el), r_glob, r_el), 0.0, 0.999)
    rF = np.tile(r_el, P)
    H = EF * rF / (1.0 - rF)
    grF = np.tile(d["fu"], P) if d.get("fu") is not None else np.full(m, np.inf)
    G = EF / (2.0 * (1.0 + nuF))
    eps_B = np.stack([_dehnung_punkt(d, p, ue_flach) for p in range(P)])      # (P,n,6)
    # Anfangsspannung der Vorspannung als Koerper (Zustand.sigma0), je Element
    # konstant: sie gehoert in die Versuchsspannung. Die inneren Moden des
    # hex8 und pent6 sieht sie nicht, denn Σ w|J| Ba = 0 (Taylor-Korrektur;
    # gemessen an verzerrten Elementen 1e-16) - wie im linearen Lastvektor
    # (assemble.solid_initial_stress_loads), der sie dort auch nicht ansetzt.
    s0n = None
    if getattr(zustand, "sigma0", None):
        s0n = np.zeros((n, 6))
        for a, i in enumerate(idx):
            v = zustand.sigma0.get(int(i))
            if v is not None:
                s0n[a] = np.asarray(v, float)
        if not s0n.any():
            s0n = None

    def rueckfuehren(alpha):
        """Versuchsspannung, Rueckfuehrung und neuer Zustand zu einem alpha."""
        sig = np.empty((P, n, 6))
        for q_ in range(P):
            e_ges = eps_B[q_] if alpha is None else \
                eps_B[q_] + np.einsum("nij,nj->ni", eas["Ba"][q_], alpha)
            sig[q_] = _spannung(lam, mu2, e_ges - eps_p[q_])
            if s0n is not None:
                sig[q_] -= s0n
        sigF = sig.reshape(m, 6)
        p_hyd = (sigF[:, 0] + sigF[:, 1] + sigF[:, 2]) / 3.0
        dev = sigF.copy()
        dev[:, 0] -= p_hyd
        dev[:, 1] -= p_hyd
        dev[:, 2] -= p_hyd
        q = np.sqrt(1.5 * (dev[:, 0] ** 2 + dev[:, 1] ** 2 + dev[:, 2] ** 2)
                    + 3.0 * (dev[:, 3] ** 2 + dev[:, 4] ** 2 + dev[:, 5] ** 2))
        # Fliessgrenze bilinear bis f_u, danach ideal plastisch (rueckfuehrung)
        f = q - np.minimum(fyF + H * eqF, grF)
        fliesst = hatF & (f > 0.0) & (q > 0.0)
        dgamma = np.zeros(m)
        np.divide(f, 3.0 * G + H, out=dgamma, where=fliesst)
        # Auf dem Plateau oder ueber den Knick: der Punkt endet auf q = f_u,
        # und die Tangente rechnet dort mit H = 0
        plateau = fliesst & (fyF + H * (eqF + dgamma) > grF)
        Hw = H
        if plateau.any():
            dgamma[plateau] = (q[plateau] - grF[plateau]) / (3.0 * G[plateau])
            Hw = np.where(plateau, 0.0, H)
        richtung = 1.5 * dev / np.where(q > 0.0, q, 1.0)[:, None]
        eps_p_neu = (eps_p.reshape(m, 6) + dgamma[:, None] * richtung * _SCHUB[None, :]
                     ).reshape(P, n, 6)
        sig_neu = sigF - 2.0 * G[:, None] * dgamma[:, None] * richtung
        return sigF, dev, q, fliesst, dgamma, eps_p_neu, sig_neu, Hw

    # Beim hex8 gehoeren die inkompatiblen Moden in die Plastizitaet
    # (siehe _eas_daten). alpha und eps_p haengen voneinander ab und werden
    # **im Element gemeinsam** geloest: R(alpha) = Σ w Baᵀ sigma = 0, mit der
    # elastoplastischen Tangente als Jacobi-Matrix. Gestaffelt - alpha aus dem
    # vorigen eps_p - lief der Reibblock auf eps_p 1e15 % davon (20.09.2026).
    eas = d.get("eas")
    alpha = None
    if eas is not None:
        alpha = _eas_alpha(eas, lam, mu2, eps_p, lasten, ue_flach)
        gew_alle = np.stack([gew for _dNg, gew in lasten])           # (P,n)
        for _runde in range(EAS_RUNDEN):
            _sF, dv, qq, fl, dg, _ep, s_neu, Hw = rueckfuehren(alpha)
            s_neu_p = s_neu.reshape(P, n, 6)
            R = np.zeros((n, eas["Ba"].shape[3]))
            for q_ in range(P):
                R += gew_alle[q_][:, None] * np.einsum("nji,nj->ni", eas["Ba"][q_],
                                                       s_neu_p[q_])
            if float(np.abs(R).max()) <= EAS_TOLERANZ * max(1.0, float(np.abs(s_neu).max())):
                break
            dD = tangenten_differenz(dv, np.where(qq > 0.0, qq, 1.0), dg, G, Hw)
            dD[~fl] = 0.0
            dD = dD.reshape(P, n, 6, 6)
            J = np.zeros((n, eas["Ba"].shape[3], eas["Ba"].shape[3]))
            for q_ in range(P):
                Dep = eas["D"] + dD[q_]
                J += gew_alle[q_][:, None, None] * np.einsum(
                    "nji,njk->nik", eas["Ba"][q_],
                    np.einsum("nij,njk->nik", Dep, eas["Ba"][q_]))
            alpha = alpha - np.linalg.solve(J, R[..., None])[..., 0]
    sigF, dev, q, fliesst, dgamma, eps_p_neu, sig_neu, Hw = rueckfuehren(alpha)
    eq_neu = (eqF + dgamma).reshape(P, n)
    p_neu = (sig_neu[:, 0] + sig_neu[:, 1] + sig_neu[:, 2]) / 3.0
    q_neu = np.sqrt(1.5 * ((sig_neu[:, 0] - p_neu) ** 2 + (sig_neu[:, 1] - p_neu) ** 2
                           + (sig_neu[:, 2] - p_neu) ** 2)
                    + 3.0 * (sig_neu[:, 3] ** 2 + sig_neu[:, 4] ** 2 + sig_neu[:, 5] ** 2))
    # Neuer Zustand und plastische Knotenlasten - nur fuer Elemente, die an
    # mindestens einem Punkt fliessen oder schon eine Dehnung tragen
    neu = zustand.kopie()
    fliesst_e = fliesst.reshape(P, n).any(axis=0)
    traegt = fliesst_e | hatte
    F_p = np.zeros(model.ndof)
    stellen = np.flatnonzero(traegt)
    if stellen.size:
        for a in stellen:
            neu.eps_p[int(idx[a])] = eps_p_neu[:, a, :].copy()
            neu.eps_p_eq[int(idx[a])] = eq_neu[:, a].copy()
        # F_p = Σ_gp w |J| Bᵀ D eps_p - jeder Gausspunkt mit seiner eigenen
        # plastischen Dehnung. Vorher trug jedes Element **eine**; damit
        # reagierte F_p auf keine Biegemode, und die Gausspunktfassung der
        # Tangente lief deshalb davon (siehe _dk_block).
        fe = np.zeros((len(stellen), k, 3))
        fe_B = np.zeros((len(stellen), 3 * k))
        for q_, (dNg, gew) in enumerate(lasten):
            w = gew[stellen][:, None]                           # (m,1)
            s0 = _spannung(lam[stellen], mu2[stellen], eps_p_neu[q_][stellen])
            if dNg is None:
                # allgemeines B des Operators (etwa mit B-bar): f = Bᵀ s0
                fe_B += w * np.einsum("nji,nj->ni", d["op"].b(q_)[stellen], s0)
                continue
            g = dNg[stellen]                                    # (m,k,3)
            fe[:, :, 0] += w * (g[:, :, 0] * s0[:, 0, None] + g[:, :, 1] * s0[:, 3, None]
                                + g[:, :, 2] * s0[:, 5, None])
            fe[:, :, 1] += w * (g[:, :, 1] * s0[:, 1, None] + g[:, :, 0] * s0[:, 3, None]
                                + g[:, :, 2] * s0[:, 4, None])
            fe[:, :, 2] += w * (g[:, :, 2] * s0[:, 2, None] + g[:, :, 1] * s0[:, 4, None]
                                + g[:, :, 0] * s0[:, 5, None])
        fe = fe.reshape(len(stellen), 3 * k) + fe_B
        if eas is not None:
            # Kondensiert: F_p = Σ Bᵀ D eps_p dV − Kua Kaa^-1 h_p. Ohne den
            # zweiten Term traegt die Last Biegeanteile, die die kondensierte
            # Steifigkeit gar nicht sieht - die Iteration laeuft dann davon.
            h_neu = _eas_h(eas, lam, mu2, eps_p_neu, lasten)[stellen]
            fe = fe - np.einsum(
                "nij,nj->ni", eas["Kua"][stellen],
                np.linalg.solve(eas["Kaa"][stellen], h_neu[..., None])[..., 0])
        np.add.at(F_p, dofs[stellen].ravel(), fe.reshape(-1))
    if d["ohne_fy"] and log is not None:
        _einmal(log, "Plastizität: Werkstoffe ohne Streckgrenze bleiben elastisch - "
                + ", ".join(sorted(d["ohne_fy"])))
    if log is not None:
        # ohne f_u (oder f_u < f_y) einmal je Werkstoff und Lastfall (13.10.2026)
        for nm in sorted(d.get("grenze_meldungen") or {}):
            _einmal(log, "Plastizität: " + d["grenze_meldungen"][nm])
    # q_max zaehlt nur Werkstoffe mit Streckgrenze: die Schleife ueberspringt
    # die uebrigen ganz (19.09.2026, vom Vergleichstest gefunden)
    q_max = float(q_neu[hatF].max()) if (m and hatF.any()) else 0.0
    # sigma_v je Element: der groesste Integrationspunkt nach der Rueckfuehrung,
    # also dort, wo die Fliessbedingung gilt - fuer die Zonen der
    # netzabhaengigen Spitzen (solver._SpitzenImNewton, 13.10.2026)
    info = {"fliessend": int(fliesst_e.sum()), "q_max": q_max,
            "sv_teile": [(idx, q_neu.reshape(P, n).max(axis=0))],
            # und je Punkt, fuer die Aenderung ausserhalb der Zonen (14.10.2026)
            "sv_punkte": [(idx, q_neu.reshape(P, n))]}
    if tangente:
        # H der Tangente: 0 auf dem Plateau ueber f_u (seit dem 13.10.2026)
        info["dK"] = _dk_block(d, fliesst.reshape(P, n), dev.reshape(P, n, 6),
                               q.reshape(P, n), dgamma.reshape(P, n),
                               G.reshape(P, n), Hw.reshape(P, n), model.ndof)
    return F_p, neu, info


def schritt(model, u, zustand: Zustand, einst: Plastizitaet, elemente: list, log: list = None,
            tangente: bool = False) -> tuple:
    """Ein Schritt der Anfangsdehnungs-Iteration: aus u die Versuchsspannung
    D(ε − eps_p) − σ₀ je Element (σ₀ = ``zustand.sigma0``, die Vorspannung als
    Koerper), Rueckfuehrung, neue eps_p, plastische Knotenlasten
    F_p = Σ ∫ Bᵀ D eps_p dV. Rueckgabe (F_p, Zustand, info).

    ``tangente=True`` legt ΔK der konsistenten Tangente in info["dK"] dazu."""
    from . import assemble as asm
    from .elements import solid as sl
    # Blockweise: die Schleife kostet am Drehlager 80 µs je Element, und das
    # bei null fliessenden - es ist der Aufrufaufwand, nicht die Physik
    # (19.09.2026). Gerechnet wird je Elementtyp ein Stapel; die Schleife
    # bleibt fuer unbekannte Typen und als Referenz des Vergleichstests.
    if not elemente:
        from scipy import sparse
        leer = {"fliessend": 0, "q_max": 0.0, "sv_teile": []}
        if tangente:
            leer["dK"] = sparse.csr_matrix((model.ndof, model.ndof))
        return np.zeros(model.ndof), zustand.kopie(), leer
    from .elements import solid as sl
    je_typ: dict = {}
    for i in elemente:
        je_typ.setdefault(model.elements[i].typ, []).append(i)
    if any(t not in sl.OPERATOREN for t in je_typ):
        if tangente:
            raise NotImplementedError("konsistente Tangente nur fuer die bekannten "
                                      "Volumenelementtypen")
        return _schritt_schleife(model, u, zustand, einst, elemente, log)
    if len(je_typ) == 1:
        typ, liste = next(iter(je_typ.items()))
        return _schritt_block(model, u, zustand, einst, liste, typ, log, tangente)
    # Gemischtes Netz: je Typ ein Stapel, die Ergebnisse zusammenlegen
    F_p = np.zeros(model.ndof)
    neu = zustand.kopie()
    n_fliesst, q_max = 0, 0.0
    dK = None
    sv_teile: list = []
    sv_punkte: list = []
    for typ, liste in je_typ.items():
        Fb, zb, ib = _schritt_block(model, u, zustand, einst, liste, typ, log, tangente)
        F_p += Fb
        for i in liste:
            if i in zb.eps_p:
                neu.eps_p[i] = zb.eps_p[i]
                neu.eps_p_eq[i] = zb.eps_p_eq[i]
        n_fliesst += ib["fliessend"]
        q_max = max(q_max, ib["q_max"])
        sv_teile.extend(ib.get("sv_teile") or [])
        sv_punkte.extend(ib.get("sv_punkte") or [])
        if tangente:
            dK = ib["dK"] if dK is None else (dK + ib["dK"])
    info = {"fliessend": n_fliesst, "q_max": q_max, "sv_teile": sv_teile, "sv_punkte": sv_punkte}
    if tangente:
        info["dK"] = dK
    return F_p, neu, info


def _schritt_schleife(model, u, zustand: Zustand, einst: Plastizitaet, elemente: list,
                      log: list = None) -> tuple:
    """Derselbe Schritt, Element fuer Element und Gausspunkt fuer Gausspunkt -
    die Referenz fuer alles, was nicht im Stapel geht, und der Vergleich im
    Test (tests/test_plastizitaet.py).

    Bewusst ein eigener Weg: die B-Matrix wird hier je Punkt aufgestellt
    (``sl._ISO``), nicht ueber den Stapel. Stimmen beide ueberein, ist es
    keine gemeinsame Verwechslung.
    """
    from . import assemble as asm
    from .elements import solid as sl
    F_p = np.zeros(model.ndof)
    neu = zustand.kopie()
    n_fliesst = 0
    q_max = 0.0
    ohne_fy: set = set()
    ohne_fu: dict = {}
    for i in elemente:
        e = model.elements[i]
        mat = model.materials[e.mat]
        fy = getattr(mat, "fy", None)
        if not fy:
            ohne_fy.add(e.mat)
            continue
        E, nu = float(mat.E), float(mat.nu)
        G = E / (2.0 * (1.0 + nu))
        # Verfestigung je Werkstoff und ihre Grenze f_u (13.10.2026)
        r = werkstoff_verfestigung(mat, einst)
        H = E * r / (1.0 - r)
        fu = werkstoff_grenze(mat)
        if fu is None:
            ohne_fu.setdefault(mat.name, meldung_ohne_grenze(mat))
        D = sl.D_matrix(E, nu)
        k = sl._KNOTENZAHL[e.typ]
        X = np.asarray(model.nodes, float)[list(e.nodes)[:k]]
        dofs = asm.element_dofs(e, model)
        ue = np.asarray(u, float)[dofs]
        fn, GP, W = sl._ISO[e.typ]
        P = len(GP)
        eps_p_alt = _punktfeld(zustand.eps_p.get(i, np.zeros((P, 6))), P, 6)
        eq_alt = _punktfeld(zustand.eps_p_eq.get(i, 0.0), P, 0)
        eps_p_neu = np.array(eps_p_alt, float, copy=True)
        eq_neu = np.array(eq_alt, float, copy=True)
        # B-Matrix und Gewicht je Integrationspunkt aus dem Dehnungsoperator
        # **dieses einen** Elements - dieselbe Kinematik wie Steifigkeit und
        # Stapel (bei hex8 mit projizierter Volumendehnung, sonst stimmten
        # Steifigkeit und Fliessen nicht ueberein). Unabhaengig bleibt hier
        # die Rechnung: Element fuer Element, Punkt fuer Punkt, mit
        # rueckfuehrung() statt der Feldoperationen des Stapels.
        op1 = sl.dehnungsoperator(model, e.typ, [i])[0]
        if op1.P != P:
            GP = [None] * op1.P
            P = op1.P
            eps_p_alt = _punktfeld(zustand.eps_p.get(i, np.zeros((P, 6))), P, 6)
            eq_alt = _punktfeld(zustand.eps_p_eq.get(i, 0.0), P, 0)
            eps_p_neu = np.array(eps_p_alt, float, copy=True)
            eq_neu = np.array(eq_alt, float, copy=True)
        Bs = [op1.b(p_)[0] for p_ in range(P)]
        gew_p = [float(op1.w[p_][0]) for p_ in range(P)]
        # Anfangsspannung der Vorspannung als Koerper - wie im Stapel
        s0 = np.asarray((getattr(zustand, "sigma0", None) or {}).get(i, np.zeros(6)), float)
        # Mit inneren Moden (hex8) werden alpha und eps_p im Element gemeinsam
        # geloest (siehe _eas_daten); Kua, Kaa und Ba aus dem Einzeloperator.
        Ba_p, Kua, Kaa, alpha = None, None, None, None
        if op1.Ba is not None:
            _Kuu, Kua, Kaa = sl.matrizen_aus_operator(op1, D, ohne_kuu=True)
            Kua, Kaa = Kua[0], Kaa[0]
            Ba_p = [op1.Ba[p_][0] for p_ in range(P)]
            h_alt = sum(gew_p[gp] * (Ba_p[gp].T @ (D @ eps_p_alt[gp])) for gp in range(P))
            alpha = np.linalg.solve(Kaa, h_alt - Kua.T @ ue)

        def durchgang(alpha_):
            """Rueckfuehrung an allen Gausspunkten zu einem alpha."""
            erg = []
            for gp in range(P):
                eps_ges = Bs[gp] @ ue
                if Ba_p is not None:
                    eps_ges = eps_ges + Ba_p[gp] @ alpha_
                erg.append((D @ (eps_ges - eps_p_alt[gp]) - s0,)
                           + rueckfuehrung(D @ (eps_ges - eps_p_alt[gp]) - s0,
                                           float(fy), H, G, float(eq_alt[gp]), fu))
            return erg

        if Ba_p is not None:
            for _runde in range(EAS_RUNDEN):
                erg = durchgang(alpha)
                R = sum(gew_p[gp] * (Ba_p[gp].T @ erg[gp][1]) for gp in range(P))
                gr = max(1.0, max(float(np.abs(x[1]).max()) for x in erg))
                if float(np.abs(R).max()) <= EAS_TOLERANZ * gr:
                    break
                Jm = np.zeros((Ba_p[0].shape[1], Ba_p[0].shape[1]))
                for gp in range(P):
                    sig_tr, _s_neu, _d_eps, dgam = erg[gp]
                    dD = np.zeros((6, 6))
                    if dgam > 0:
                        pm = (sig_tr[0] + sig_tr[1] + sig_tr[2]) / 3.0
                        dv = np.array(sig_tr, float, copy=True)
                        dv[:3] -= pm
                        Hw = verfestigung_wirksam(float(fy), H, float(eq_alt[gp]) + dgam, fu)
                        dD = tangenten_differenz(dv[None, :],
                                                 np.array([vergleichsspannung(sig_tr)]),
                                                 np.array([dgam]), np.array([G]),
                                                 np.array([Hw]))[0]
                    Jm += gew_p[gp] * (Ba_p[gp].T @ ((D + dD) @ Ba_p[gp]))
                alpha = alpha - np.linalg.solve(Jm, R)
        fe = np.zeros(3 * k)
        fliesst_hier = False
        for gp, (_sig_tr, sig_neu, d_eps_p, dgamma) in enumerate(durchgang(alpha)):
            q_max = max(q_max, vergleichsspannung(sig_neu))
            if dgamma > 0:
                fliesst_hier = True
                eps_p_neu[gp] = eps_p_alt[gp] + d_eps_p
                eq_neu[gp] = float(eq_alt[gp]) + dgamma
            fe += gew_p[gp] * (Bs[gp].T @ (D @ eps_p_neu[gp]))
        if Ba_p is not None:
            h_neu = sum(gew_p[gp] * (Ba_p[gp].T @ (D @ eps_p_neu[gp])) for gp in range(P))
            fe = fe - Kua @ np.linalg.solve(Kaa, h_neu)
        if fliesst_hier or i in neu.eps_p:
            neu.eps_p[i] = eps_p_neu
            neu.eps_p_eq[i] = eq_neu
            if fliesst_hier:
                n_fliesst += 1
            np.add.at(F_p, dofs, fe)
    if ohne_fy and log is not None:
        _einmal(log, "Plastizität: Werkstoffe ohne Streckgrenze bleiben elastisch - " + ", ".join(sorted(ohne_fy)))
    if log is not None:
        for nm in sorted(ohne_fu):
            _einmal(log, "Plastizität: " + ohne_fu[nm])
    return F_p, neu, {"fliessend": n_fliesst, "q_max": q_max}


def _einmal(log: list, zeile: str) -> None:
    """Eine Zeile nur einmal ins Protokoll eines Lastfalls (``log`` beginnt in
    solver._plastizitaet_rechnen je Lastfall leer). „Werkstoffe ohne
    Streckgrenze bleiben elastisch“ stand bis zum 13.10.2026 einmal je
    Schritt da: am Koerper-Bolzen (tests.test_vorspannung_sofort) in 11 von
    13 Zeilen."""
    if zeile not in log:
        log.append(zeile)


def _stabstatus_offen(kontakt) -> str:
    """Zugstaebe in der Konvergenzbedingung (Entscheidung des Anwenders vom
    13.10.2026): leer, wenn der Status der Zug-/Druckstaebe und Seile steht -
    sonst der Grund vom Loeser (solver._KontaktImNewton.stabstatus_offen). Ein
    Schritt, dessen Loesung Staebe ausfallen oder wieder tragen liess, ist
    nicht konvergiert, auch wenn F_p sich nicht mehr aendert - streng wie
    ingenieurmaessig. Ohne Loeser (kein Kontakt, keine Ausfallstaebe) und
    ohne solche Staebe immer leer: dort rechnet alles wie bisher."""
    f = getattr(kontakt, "stabstatus_offen", None) if kontakt is not None else None
    return f() if f is not None else ""


#: Kontaktlauf konvergiert als Bedingung der Konvergenz einer Laststufe -
#: VORBEREITET, NICHT EINGESCHALTET (14.10.2026). Entscheidung des Anwenders:
#: „Konvergenz des Kontaktlaufs über Ingenieurgrößen definieren … Erst dann die
#: Bedingung „Kontaktlauf konvergiert“ ins Abbruchkriterium aufnehmen“ und
#: „Kontaktbedingung erst nach der V36-Klärung einbauen“. Eingeschaltet gilt ein
#: Newton-Schritt (und der Abschluss) nur als konvergiert, wenn der letzte volle
#: Kontaktlauf konvergiert ist - streng oder nach Ingenieurgroessen
#: (solver.PENDEL_STABILISIEREN, ABSCHLUSS_INGENIEUR); sonst rechnet die Stufe
#: weiter wie bei offenem Stabstatus. Vorschlag aus dem Paket 3 der
#: Singularitaeten (sp3, 13.10.2026): laeufe[-1]["konvergiert"]. Aus heisst:
#: :func:`_kontakt_offen` gibt immer "" zurueck, alles rechnet wie vorher. Wird
#: nach der V36-Klaerung und auf Freigabe des Anwenders auf True gesetzt.
KONTAKT_IN_KONVERGENZ = False


def _kontakt_offen(kontakt) -> str:
    """Leer, solange :data:`KONTAKT_IN_KONVERGENZ` aus ist, und eingeschaltet,
    wenn der letzte volle Kontaktlauf konvergiert ist - sonst der Grund vom
    Loeser (solver._KontaktImNewton.kontakt_offen). Ohne Loeser immer leer."""
    if not KONTAKT_IN_KONVERGENZ:
        return ""
    f = getattr(kontakt, "kontakt_offen", None) if kontakt is not None else None
    return f() if f is not None else ""


def _offen(kontakt) -> str:
    """Was einer sonst konvergierten Stufe noch fehlt: der Stabstatus
    (:func:`_stabstatus_offen`) oder - eingeschaltet - der Kontaktlauf
    (:func:`_kontakt_offen`); "" heisst nichts."""
    return _stabstatus_offen(kontakt) or _kontakt_offen(kontakt)


def _offen_was(grund: str) -> str:
    """„steht der Stabstatus nicht“ - oder beim Kontaktlauf „ist der Kontaktlauf
    nicht konvergiert“ (der Grund von :func:`_kontakt_offen` beginnt mit „Kontakt:“)."""
    return ("ist der Kontaktlauf nicht konvergiert" if str(grund).startswith("Kontakt:")
            else "steht der Stabstatus nicht")


def _schlussabnahme(rest: float, toleranz: float) -> bool:
    """Die Abnahme am Schluss: passt F_p zur Loesung des Abschlusses?
    ``rest`` ist die Aenderung von F_p, die die Rueckfuehrung (von der Basis
    der letzten Laststufe) an dieser Loesung ergibt, bezogen auf |F| wie das
    Kriterium der Iteration.

    Bis zum 23.09.2026 pruefte das niemand: der Abschluss loest elastisch mit
    dem F_p des letzten Newton-Schritts, mit Kontakt in einem eigenen, voll
    auskonvergierten Lauf - und der kann den Kontaktzustand noch aendern. Am
    gequetschten Block (tests/test_solver_ext, mu 0,3, eps_p 12 %) blieb so
    ein Rest von 2,5e-4 bei Toleranz 1e-4, gemeldet wurde "konvergiert".
    Gerechnet wird sie nur, wenn der Loesungsweg selbst iteriert (Kontakt,
    ausfallende Zugstaebe - der Loeser gibt dann ``kontakt`` mit): sonst ist
    der Abschluss die Newton-Loesung selbst, und der Rest lag in 14 Faellen
    ohne Kontakt hoechstens bei 1,5e-7 gegen Toleranzen von 1e-3 und 1e-2
    (Gegenpruefung 24.09.2026) - eine Rueckfuehrung mehr je Lastfall ohne
    Nutzen. Eine eigene Funktion, damit die Ruecknahmeprobe sie abschalten
    kann (tests/test_plastizitaet.test_ruecknahme_der_schlussabnahme)."""
    return rest <= toleranz


#: Bezug der Aenderung ohne aeussere Last: die plastische Last selbst (seit
#: 25.09.2026). Schalter fuer die Ruecknahmeprobe in den Tests.
BEZUG_PLASTISCHE_LAST = True

#: Hoechstens so viele Newton-Schritte vom Abschluss aus, wenn die
#: Schlussabnahme verfehlt wird (_newton, 27.09.2026). 0 = wie bis dahin:
#: pruefen und "nicht konvergiert" melden.
ABSCHLUSS_NACHSCHRITTE = 5
#: Laeuft der Newton einer Laststufe weg - die Aenderung waechst zweimal
#: hintereinander, nachdem sie einmal gefallen war -, wird die Stufe vom
#: Startwert an in zwei halben Stufen wiederholt, hoechstens so oft je
#: urspruenglicher Stufe (28.09.2026). Gemessen am gequetschten Block mit
#: Reibung primal-dual: mit 1 und 8 Laststufen konvergiert, mit 4 lief Stufe 3
#: weg (Aenderung 1,6 - 1,8 - 4,4 - 7,2 - ... - 26, nach 40 Schritten "nicht
#: konvergiert") - ob eine Rechnung konvergierte, hing an der Teilung der
#: Last. Mit dem Halbieren (2 Stufen: dreimal, 4 Stufen: zweimal) geben 1, 2, 4
#: und 8 Laststufen denselben Zustand: u_max 42,667 mm, eps_p 12,99 %.
#: Dasselbe Kriterium beendet schon die abgekuerzte Iteration
#: (solver._KontaktImNewton.naechster).
HALBIEREN_MAX = 4

#: Die Zeile im Protokoll, wenn Temperaturlasten oder Vorspannungen mitwirken
#: (siehe stufenlast)
SOFORT_VOLL = ("Temperaturlasten und Vorspannungen wirken ab der ersten Laststufe voll, "
               "gesteigert werden nur die übrigen Lasten")


def stufenlast(F, F_sofort, lam: float):
    """Die Last einer Stufe mit dem Lastfaktor ``lam``: F_S + lam (F - F_S).

    Temperaturlasten und Vorspannkraefte wirken seit dem 10.10.2026 ab der
    ersten Stufe voll, gesteigert wird nur der Rest - in den Laststufen hier,
    in den halbierten Stufen und in der Theorie III. Ordnung
    (theorie3.solve_theorie3). Entscheidung des Anwenders: „temperaturlast
    immer sofort vorhanden berücksichtigen denn ohne vorspannung mehr
    verformung und dann längere rechenzeit“. Am Drehlager steht die
    Ankervorspannung als Temperaturlast im LF1 (dT -445,6 K, rund 952 kN je
    Stab bei voller Behinderung) und wuchs bis dahin mit den Stufen mit: in
    der ersten von drei wirkte ein Drittel. Weil der Anwender es mit der
    Vorspannung begruendet, gilt dasselbe fuer eine als Vorspannkraft
    eingegebene Vorspannung (model.Vorspannung, im Stab und als Koerper).
    ``F_sofort`` ist der Anteil von Temperatur und Vorspannung an F mit dem
    Faktor der Kombination (solver.case_sofort).

    Ohne beides (``F_sofort`` None) ist es bitgleich lam * F wie bisher, und
    in der letzten Stufe (lam = 1) immer die volle Last F."""
    if F_sofort is None or lam == 1.0:
        return lam * F
    return F_sofort + lam * (F - F_sofort)


#: Schranke fuer "proportional" (Vorschlag 1, 14.10.2026): die Stufenlast gilt als
#: proportional zur Last des Vorlaufs, wenn ihr Rest nach der besten Skalierung
#: hoechstens dieser Anteil ihres Betrags ist (:func:`nicht_proportional`). Warum
#: 1e-3: ein Faktor lam * F ist bis auf die Rundung (1e-16) proportional, also
#: genuegte jede Schranke ueber 1e-12, damit proportionale Stufen bitgleich warm
#: bleiben. Hoeher liegt sie, damit eine kleine Temperatur- oder Vorspannlast
#: neben einer grossen gestuften Last den Warmstart nicht kostet: ein Rest von
#: 0,1 % der Stufenlast verschiebt die Kontaktkraefte hoechstens in der
#: Groessenordnung, die der Kontaktlauf als Restwechsel ohnehin annimmt
#: (Plastizitaet.pendel_kraft_anteil 0,1 % der Kontaktkraft, Weg 0,1 % u_max im
#: Ingenieurkriterium). Am Drehlager (LF1) ist die Vorspannung kein kleiner Rest.
PROPORTIONAL_SCHRANKE = 1.0e-3


def nicht_proportional(F, F_sofort, lam: float) -> float:
    """Der Anteil der Stufenlast F_k = F_S + lam (F - F_S) (:func:`stufenlast`),
    der nicht proportional zur Last ``F`` des Vorlaufs ist: |F_k - a F| / |F_k|
    mit dem besten Faktor a = F_k . F / F . F. Ohne Temperatur und Vorspannung
    (``F_sofort`` None) und in der letzten Stufe ist die Stufe proportional (0).

    Warum (Vorschlag 1, 14.10.2026): ein Kontaktzustand ohne Anfangsspalt ist
    positiv homogen in der Last - der Zustand des Vorlaufs mit der vollen Last
    passt zu jedem Vielfachen. Wirken Temperatur und Vorspannung ab der ersten
    Stufe voll (10.10.2026), ist die Stufenlast kein Vielfaches mehr; der warme
    Start aus dem Gleitzustand des Vorlaufs pendelte am Drehlager (V36) bis zum
    Deckel, kalt gestartet nicht."""
    if F_sofort is None or lam == 1.0:
        return 0.0
    F = np.asarray(F, float)
    F_k = np.asarray(stufenlast(F, F_sofort, lam), float)
    nk = float(np.linalg.norm(F_k))
    nF = float(F @ F)
    if nk <= 0.0:
        return 0.0
    if nF <= 0.0:
        return 1.0
    a = float(F_k @ F) / nF
    return float(np.linalg.norm(F_k - a * F)) / nk


def _bezug(norm_F: float, F_p_neu: np.ndarray) -> float:
    """Bezugsgroesse der Aenderung ||F_p,neu - F_p||: die aeussere Last ||F||.

    Fehlt sie - ein Uebermass, eine Vorspannung oder eine Lagerverschiebung
    als einzige Last, F = 0 -, war der Bezug bis zum 25.09.2026 die Zahl 1,
    und die Aenderung stand als absolute Zahl in Newton gegen die Toleranz:
    die Presspassung der Pruefmatrix (zwei Wuerfel, Uebermass bis 300 N/mm2)
    rechnete exakt (sigma_v 0,000 N/mm2 neben der Loesung) und meldete
    nach 3 x 60 Newton-Schritten trotzdem "nicht konvergiert" - die letzte
    Aenderung 0,0972 N gegen Knotenkraefte von 1e8 N. Ohne aeussere Last ist
    der Bezug jetzt die plastische Last selbst; gibt es auch die nicht,
    fliesst nichts, und jede Aenderung ist 0. Mit aeusserer Last aendert
    sich nichts (Bezug wie bisher ||F||).
    """
    if norm_F > 0.0 or not BEZUG_PLASTISCHE_LAST:
        return norm_F or 1.0
    return float(np.linalg.norm(F_p_neu)) or 1.0


def _zonen_mass(zonen, diff: float, tol: float, u, F_p_neu, F_p_alt, zustand, s_info, bezug: float,
                lam: float, stufe: str, schritt_nr) -> tuple:
    """(Mass, erreicht, Messung) eines Newton-Schritts.

    Ohne ``zonen`` (der Loeser gibt keine, wenn das Modell keine Stelle „Kraft
    ohne Fläche“ hat) ist das Mass die Aenderung ``diff`` von F_p ueber das
    ganze Modell und erreicht heisst ``diff <= tol`` - wie bis zum 13.10.2026.
    Mit ``zonen`` misst der Loeser (solver._SpitzenImNewton.messen) aus dem
    aktuellen Zustand, welche Stellen auffaellig sind, und die Aenderungen in
    und ausserhalb ihrer Zonen. Gibt es auffaellige Zonen und gilt
    ``Plastizitaet.abbruch = "ingenieurmaessig"``, ist das Mass die Aenderung
    von F_p **ausserhalb** der Zonen, und erreicht heisst zusaetzlich: die
    Kraft durch jede auffaellige Stelle aendert sich um hoechstens
    :data:`SPITZEN_KRAFT`, die Verschiebung ausserhalb der Zonen um hoechstens
    :data:`SPITZEN_VERSCHIEBUNG` und sigma_v an jedem Integrationspunkt
    ausserhalb der Zonen um hoechstens :data:`SPITZEN_SPANNUNG` (seit dem
    14.10.2026). Sonst (streng, oder keine auffaellige Zone)
    bleibt es bei ``diff`` - die Messung steht dann nur im Protokoll.

    **Was streng konvergiert, ist auch ingenieurmaessig konvergiert**
    (``diff <= tol`` genuegt immer): die Bedingungen fuer Kraft und
    Verschiebung kommen nur dazu, wo die Zonen ausgenommen werden, und duerfen
    keine Stufe laenger machen als das strenge Kriterium. Am Drehlager
    (Entwurf, LF1, 13.10.2026) aenderte der Kontakt, dessen Laeufe dort am
    Deckel enden, die Verschiebung ausserhalb der Zonen um 6,6 % in einem
    Schritt, in dem F_p ueberall unter der Toleranz blieb - und zu Beginn
    jeder Stufe enthaelt die Aenderung von u den Lastschritt selbst (47,8 %
    beim Uebergang auf Stufe 2/7, F_p unveraendert). Ohne diese Regel haette
    „ingenieurmaessig“ dort mehr Schritte gebraucht als „streng“."""
    if zonen is None:
        return diff, diff <= tol, None
    mess = zonen.messen(u, F_p_neu, F_p_alt, zustand, s_info, bezug, lam, stufe=stufe, schritt=schritt_nr)
    if not _zonen_greifen(zonen, mess):
        return diff, diff <= tol, mess
    mass = float(mess["aussen"])
    return mass, bool(diff <= tol or (mass <= tol and mess["erfuellt"])), mess


def _zonen_greifen(zonen, mess) -> bool:
    """Gilt fuer diese Messung das ingenieurmaessige Kriterium?"""
    return bool(zonen is not None and mess is not None and mess.get("zonen") and zonen.ingenieur)


def _zonen_melden(mess, log, progress) -> None:
    """Die Zeile einer Messung (Aenderung in und ausserhalb der Zonen, Kraefte
    der auffaelligen Stellen) ins Protokoll und in den Fortschritt."""
    if not mess or not mess.get("zeile"):
        return
    if log is not None:
        log.append(mess["zeile"])
    if progress is not None:
        progress(mess["zeile"])


def _mass_text(zonen, mess, diff: float, mass: float) -> str:
    """„Änderung 1.2e-02“ - oder mit Zonen das Mass ausserhalb und die Kraft."""
    if not _zonen_greifen(zonen, mess):
        return f"Änderung {diff:.2e}"
    return f"Änderung außerhalb der Zonen {mass:.2e}, {mess.get('kurz', '')}".rstrip(", ")


def _stufe_gemeinsam(model, F, k: int, stufen: int, u, basis: "Zustand", F_p, einst: "Plastizitaet",
                     elemente: list, norm_F: float, info: dict, log, progress, _loesen,
                     kontakt, faktor: float = None, letzte: bool = None, F_sofort=None, zonen=None):
    """Eine Laststufe des Newton mit abgekuerztem Kontakt - die gemeinsame
    Iteration von Fliessen und Kontakt (siehe :func:`_newton`). ``u`` ist der
    Startwert der Stufe, mit voll auskonvergiertem Kontakt geloest.

    Rueckgabe ``None``: die Stufe ist vom Startwert an verschachtelt zu
    wiederholen (``kontakt.naechster`` hat so entschieden). Sonst
    (konvergiert, u, F_p, Zustand, rest): konvergiert heisst, die Aenderung
    liegt unter der Toleranz **und** die Loesung dazu war nicht abgekuerzt.
    ``rest`` ist nur gesetzt, wenn u schon der Abschluss ist (letzte Stufe)
    und die Schlussabnahme an ihm bestanden hat. Mit auffaelligen Zonen und
    ``abbruch = "ingenieurmaessig"`` gilt das Mass von :func:`_zonen_mass`
    (seit dem 13.10.2026) - fuer das Urteil, fuer ``rest`` und fuer
    ``kontakt.naechster``.

    Wie der verschachtelte Newton hoechstens ``iterationen`` Schritte; der
    Schritt, der eine abgekuerzte Loesung mit vollem Kontakt abnimmt
    ("Abnahme", in der letzten Stufe der Abschluss), zaehlt nicht mit - sonst
    hiesse eine Stufe "nicht konvergiert", die im letzten erlaubten Schritt
    die Toleranz trifft und nur noch abzunehmen ist. Welche Schritte
    abgekuerzt werden und wann die Stufe verschachtelt wiederholt wird,
    entscheidet der Loeser (``kontakt.naechster``), nicht diese Schleife."""
    n_max = int(max(1, einst.iterationen))
    tol = float(einst.toleranz)
    # Lastfaktor und "letzte Stufe" kommen seit dem Halbieren (HALBIEREN_MAX)
    # vom Aufrufer; ohne Angabe wie bisher k/stufen. Temperatur und
    # Vorspannung wirken voll (stufenlast, 10.10.2026)
    lam_k = (k / stufen) if faktor is None else float(faktor)
    F_k = stufenlast(F, F_sofort, lam_k)
    letzte = (k == stufen) if letzte is None else bool(letzte)
    F_p_stufe, zustand_stufe = F_p, basis
    abschluss = None            # (F_p, Zustand), mit denen der Abschluss gerechnet ist
    je_schritt: list = []       # die Aenderungen dieser Stufe, fuer kontakt.naechster
    it, grenze = 0, n_max
    while it < grenze:
        it += 1
        F_p_neu, zustand_neu, s_info = schritt(model, u, basis, einst, elemente, log,
                                               tangente=True)
        bezug = _bezug(norm_F, F_p_neu)
        diff = float(np.linalg.norm(F_p_neu - F_p_stufe)) / bezug
        mass, ok, mess = _zonen_mass(zonen, diff, tol, u, F_p_neu, F_p_stufe, zustand_neu, s_info, bezug,
                                     lam_k, f"{k}/{stufen}", it)
        info["iterationen"] += 1
        info["verlauf"].append((k, it, diff, s_info["fliessend"]))
        if progress is not None:
            progress(f"Plastizität: Laststufe {k}/{stufen}, Newton-Schritt {it}: "
                     f"{s_info['fliessend']} {'Element fließt' if s_info['fliessend'] == 1 else 'Elemente fließen'}, Änderung {diff:.2e}")
        _zonen_melden(mess, log, progress)
        if ok and not kontakt.abgekuerzt():
            if getattr(kontakt, "deckel_in_stufe", lambda: False)():
                # ein voller Kontaktlauf dieser Stufe endete am Deckel: nicht
                # abnehmen, verschachtelt wiederholen (solver._KontaktImNewton)
                return None
            if abschluss is not None:
                # Schlussabnahme bestanden: F_p und Zustand sind die, mit denen
                # der Abschluss gerechnet ist - wie verschachtelt
                return True, u, abschluss[0], abschluss[1], mass
            return True, u, F_p_neu, zustand_neu, None
        F_p_stufe, zustand_stufe = F_p_neu, zustand_neu
        abschluss = None
        je_schritt.append(mass)
        if ok:
            # Unter der Toleranz, aber die Loesung dazu war abgekuerzt: ein
            # Schritt mit vollem Kontakt nimmt sie ab, ausserhalb des Budgets
            grenze += 1
            if letzte:
                u = _loesen(F + F_p_neu, None, "Abschluss", None, None, True)
                abschluss = (F_p_neu, zustand_neu)
                continue
            art, voll = "Abnahme", True
        else:
            wahl = kontakt.naechster(je_schritt)
            if wahl == "zurueck":
                return None
            art, voll = "Newton", wahl != "kurz"
        dK = s_info["dK"]
        if dK.nnz == 0:
            u = _loesen(F_k + F_p_neu, None, art, k, it, voll)
        else:
            u = _loesen(F_k + F_p_neu + dK @ u, dK, art, k, it, voll)
            info["faktorisierungen"] += 1
    # Budget aufgebraucht: war nichts abgekuerzt, ist das der verschachtelte
    # Newton selbst und sein Urteil gilt - sonst wiederholen
    if kontakt.wiederholen():
        return None
    return False, u, F_p_stufe, zustand_stufe, None


def _newton(model, F, loesen, loesen_tangente, einst: Plastizitaet, elemente: list,
            norm_F: float, info: dict, log: list = None, progress=None,
            kontakt=None, F_sofort=None, sigma0=None, zonen=None, start=None) -> tuple:
    """Newton mit der konsistenten Tangente - siehe :func:`iteration`.

    **Netzabhaengige Spitzen** (seit dem 13.10.2026): ``zonen`` vom Loeser
    (solver._SpitzenImNewton) misst nach jedem Newton-Schritt, welche Stellen
    „Kraft ohne Fläche“ auffaellig sind, und die Aenderungen in und ausserhalb
    ihrer Zonen; mit ``Plastizitaet.abbruch = "ingenieurmaessig"`` entscheidet
    das Mass ausserhalb ueber Konvergenz, Halbieren und Schlussabnahme
    (:func:`_zonen_mass`). Ohne auffaellige Zone und ohne ``zonen`` rechnet
    jeder Schritt wie vorher.

    Die Rueckfuehrung geht in jedem Schritt vom Zustand am **Anfang der
    Laststufe** aus (``basis``), nicht vom letzten Schritt: nur dann ist
    F_p eine Funktion von u allein und D_ep wirklich ihre Ableitung. Die
    Anfangsdehnungs-Iteration schreibt eps_p dagegen von Schritt zu Schritt
    fort - dasselbe im Grenzwert, aber nicht differenzierbar.

    **Mit Kontakt** (23./24.09.2026; ebenso mit ausfallenden Zugstaeben)
    gibt der Loeser ``kontakt`` mit (solver._KontaktImNewton); ohne ihn
    rechnet dieser Newton Aufruf fuer Aufruf wie vor dem 23.09.2026. Mit ihm
    kommen zwei Dinge dazu:

    * die **Schlussabnahme** (:func:`_schlussabnahme`): der Abschluss ist ein
      eigener, voll auskonvergierter Kontaktlauf und kann den Kontaktzustand
      noch aendern - "konvergiert" heisst nur, wenn F_p auch an seiner
      Loesung passt. Besteht sie nicht, heisst es "nicht konvergiert"; es wird
      nicht weitergerechnet (wie im verschachtelten Weg).
    * mit ``kontakt.gemeinsam`` (Einstellung ``kontakt = "gemeinsam"``) die
      **gemeinsame Iteration** von Fliessen und Kontakt: jede Laststufe
      beginnt mit voll auskonvergiertem Kontakt, ihre Newton-Schritte duerfen
      mit abgekuerztem Kontakt rechnen (``loesen(..., voll=False)``: der
      Loeser bricht die Kontaktiteration nach einem Schritt ab und reicht
      ihren Zustand weiter), und die Stufe endet erst mit einer Loesung, die
      nicht abgekuerzt war (:func:`_stufe_gemeinsam`). Welche Schritte
      abgekuerzt werden, entscheidet der Loeser; gibt er auf, wird die Stufe
      vom Startwert an **verschachtelt** wiederholt - mit dem vollen Budget,
      Schritt fuer Schritt wie ohne ``gemeinsam``. Warum der Rueckfall die
      ganze Stufe wiederholt statt vom erreichten Stand weiterzurechnen: am
      gequetschten Block mit vier Laststufen lief der abgekuerzte Newton weg,
      und vom weggelaufenen Stand kam auch der volle Kontakt nicht mehr
      zurueck (327 statt 84 Zerlegungen, "nicht konvergiert", wo
      verschachtelt konvergiert; Gegenpruefung 24.09.2026).

    Die gemeinsame Iteration rechnet einen **anderen** Weg durch die
    Reibung: an Modellen nahe der Grenzlast lag die Vergleichsspannung bis zu
    78 N/mm2 neben der verschachtelten, beide "konvergiert"
    (Theoriehandbuch § 5e.3). Darum ist sie nicht die Vorgabe; ob sie es
    wird, entscheidet der Anwender. Bis zum 06.10.2026 warnte davor nur der
    Tooltip der Auswahl - das Ergebnis selbst sah aus wie ein verschachtelt
    gerechnetes (Fehlerliste F12). Seitdem heisst sie in der Oberflaeche
    „gemeinsam (Versuch)“, und der Loeser haengt jedem so gerechneten
    Ergebnis :data:`GEMEINSAM_WARNUNG` an (solver._plastizitaet_rechnen);
    die Rechnung selbst ist dieselbe geblieben.

    Mit Kontakt steht jeder Loeseraufruf mit seiner Art in ``info["aufrufe"]``
    (Art, Laststufe, Schritt) - daraus baut der Loeser das Laufbuch.
    """
    info["verfahren"] = "tangente"
    stufen = int(max(1, einst.laststufen))
    gemeinsam = kontakt is not None and bool(kontakt.gemeinsam)
    aufrufe = info.setdefault("aufrufe", []) if kontakt is not None else None
    # Lastanteil je Aufruf, parallel zu ``aufrufe`` (14.10.2026): die
    # Kennzeichnung „vorläufig – Kontakt nicht konvergiert in Stufe …“
    # (solver.kontakt_vorlaeufig) nennt die Stufe mit ihrem Lastanteil - nach
    # dem Halbieren sagt die Nummer allein nicht, welche Last gemeint ist
    lasten = info.setdefault("aufrufe_last", []) if kontakt is not None else None
    stufe_last = [0.0]

    def _loesen(Fg, dK, art, k_, it_, voll=True):
        if aufrufe is not None:
            aufrufe.append((art, k_, it_))
            lasten.append(1.0 if art == "Abschluss" else float(stufe_last[0]))
        if gemeinsam:
            return loesen(Fg, voll=voll) if dK is None else loesen_tangente(Fg, dK, voll=voll)
        return loesen(Fg) if dK is None else loesen_tangente(Fg, dK)

    basis = Zustand(sigma0)
    F_p = np.zeros(model.ndof)
    if start is not None:
        # vom Spannschritt einer Vorspannkraft aus (iteration, ``start``)
        basis, F_p = start[0], np.array(start[1], float, copy=True)
    u = None
    diff = 0.0
    basis_anfang = basis
    rest = None                 # gemeinsam: der Abschluss hat die letzte Stufe schon abgenommen
    # Lastfaktoren der Stufen mit ihrer Halbierungstiefe; eine weglaufende
    # Stufe wird vom Startwert an in zwei halben wiederholt (HALBIEREN_MAX)
    faktoren = [(k_ / stufen, 0) for k_ in range(1, stufen + 1)]
    info["halbiert"] = 0
    lam_alt = 0.0
    k = 0
    while k < len(faktoren):
        lam_k, tiefe = faktoren[k]
        stufe_last[0] = lam_k
        k += 1
        letzte = k == len(faktoren)
        # Temperatur und Vorspannung wirken ab der ersten Stufe voll, auch in
        # einer halbierten (stufenlast, 10.10.2026)
        F_k = stufenlast(F, F_sofort, lam_k)
        basis_anfang = basis
        # Was ein Ruecksprung an den Stufenanfang braucht: Loesung, Zustand,
        # F_p und - mit Kontakt - der Kontaktzustand vor dem Startwert
        vorher = (u, basis, F_p)
        marke = kontakt.merken() if kontakt is not None and hasattr(kontakt, "merken") else None
        # die Bezugsmessung der Zonen am Stufenanfang (der Stand der vorigen Stufe)
        z_marke = zonen.merken() if zonen is not None else None
        # Startwert der Laststufe: elastische Loesung mit dem bisherigen F_p -
        # ein Rueckwaertseinsetzen auf der schon vorhandenen Faktorisierung
        u = _loesen(F_k + F_p, None, "Laststufe", k, 0)
        F_p_stufe, zustand_stufe = F_p, basis
        vorab = None
        if gemeinsam:
            u_start = u
            kontakt.stufe_beginnt()
            vorab = _stufe_gemeinsam(model, F, k, stufen, u, basis, F_p, einst, elemente,
                                     norm_F, info, log, progress, _loesen, kontakt,
                                     faktor=lam_k, letzte=letzte, F_sofort=F_sofort, zonen=zonen)
            if vorab is None:
                # Verschachtelt wiederholen, vom Startwert der Stufe: der
                # Loeser setzt den Kontaktzustand auf den nach dem Startwert
                # zurueck, und die Schleife unten beginnt wieder bei ihm
                kontakt.zurueck()
                u = u_start
                if zonen is not None:
                    zonen.zurueck(z_marke)
        if vorab is not None:
            konvergiert, u, F_p_stufe, zustand_stufe, rest = vorab
            if not konvergiert:
                info["konvergiert"] = False
                diff = info["verlauf"][-1][2]
                if log is not None:
                    log.append(f"Plastizität: Laststufe {k} nach {einst.iterationen} "
                               f"Newton-Schritten nicht konvergiert (Änderung {diff:.2e} > "
                               f"{einst.toleranz:g})")
            basis, F_p = zustand_stufe, F_p_stufe
            lam_alt = lam_k
            continue
        je_schritt: list = []
        gefallen = False
        weglauf = False
        erreicht = False
        mass, mess = 0.0, None
        stab_offen = ""
        for it in range(1, int(max(1, einst.iterationen)) + 1):
            F_p_neu, zustand_neu, s_info = schritt(model, u, basis, einst, elemente, log,
                                                   tangente=True)
            bezug = _bezug(norm_F, F_p_neu)
            diff = float(np.linalg.norm(F_p_neu - F_p_stufe)) / bezug
            mass, ok, mess = _zonen_mass(zonen, diff, float(einst.toleranz), u, F_p_neu, F_p_stufe,
                                         zustand_neu, s_info, bezug, lam_k, f"{k}/{len(faktoren)}", it)
            F_p_stufe, zustand_stufe = F_p_neu, zustand_neu
            info["iterationen"] += 1
            info["verlauf"].append((k, it, diff, s_info["fliessend"]))
            if progress is not None:
                progress(f"Plastizität: Laststufe {k}/{len(faktoren)}, Newton-Schritt {it}: "
                         f"{s_info['fliessend']} {'Element fließt' if s_info['fliessend'] == 1 else 'Elemente fließen'}, Änderung {diff:.2e}")
            _zonen_melden(mess, log, progress)
            # Zugstaebe in der Konvergenzbedingung (13.10.2026): streng wie
            # ingenieurmaessig ist die Stufe erst mit stehendem Stabstatus
            # konvergiert
            stab_offen = _offen(kontakt) if ok else ""
            if stab_offen:
                ok = False
                if log is not None:
                    log.append(f"Plastizität: Laststufe {k}/{len(faktoren)}, Newton-Schritt {it}: "
                               f"{stab_offen} - noch nicht konvergiert")
            if ok:
                erreicht = True
                break
            je_schritt.append(mass)
            if len(je_schritt) >= 2 and je_schritt[-1] < je_schritt[-2]:
                gefallen = True
            if (gefallen and len(je_schritt) >= 3 and tiefe < HALBIEREN_MAX
                    and je_schritt[-1] > je_schritt[-2] > je_schritt[-3]):
                weglauf = True
                break
            if (tiefe < HALBIEREN_MAX and marke is not None
                    and getattr(kontakt, "deckel_seit", lambda _m: False)(marke)):
                # Ein Kontaktlauf dieser Stufe endete am Deckel: auf dieser Loesung
                # weiterzurechnen hiesse raten - halbieren wie beim Weglaufen. Am
                # gequetschten Block (4 Stufen) standen so 650 von 752 Zerlegungen
                # in verworfenen Versuchen, je Lauf 69 bis zur Grenze der
                # Richtungsrunden (28.09.2026)
                weglauf = True
                break
            dK = s_info["dK"]
            if dK.nnz == 0:
                # Nichts fliesst gerade (etwa beim Entlasten): die Tangente ist
                # die elastische, und dafuer gibt es die Faktorisierung schon
                u = _loesen(F_k + F_p_neu, None, "Newton", k, it)
            else:
                u = _loesen(F_k + F_p_neu + dK @ u, dK, "Newton", k, it)
                info["faktorisierungen"] += 1
        if weglauf:
            # Zurueck an den Stufenanfang, die Stufe in zwei halben wiederholen
            u, basis, F_p = vorher
            mitte = 0.5 * (lam_alt + lam_k)
            faktoren[k - 1] = (lam_k, tiefe + 1)
            faktoren.insert(k - 1, (mitte, tiefe + 1))
            k -= 1
            info["halbiert"] += 1
            verworfen = kontakt.zurueck_an(marke) if marke is not None else None
            if zonen is not None:
                zonen.zurueck(z_marke)
            if log is not None:
                if len(je_schritt) >= 3 and je_schritt[-1] > je_schritt[-2] > je_schritt[-3]:
                    wo = " außerhalb der Zonen" if _zonen_greifen(zonen, mess) else ""
                    warum = (f"läuft weg (Änderung{wo} {je_schritt[-3]:.2e} - {je_schritt[-2]:.2e} - "
                             f"{je_schritt[-1]:.2e})")
                else:
                    warum = "- ein Kontaktlauf endete nicht konvergiert"
                log.append(f"Plastizität: Laststufe bis {lam_k * 100:.4g} % der Last {warum}; "
                           f"sie wird vom Startwert an in zwei halben Stufen wiederholt"
                           + ("" if verworfen is None else f" ({verworfen} Kontaktläufe verworfen)"))
            continue
        if not erreicht:
            info["konvergiert"] = False
            if log is not None:
                log.append(f"Plastizität: Laststufe {k} nach {einst.iterationen} Newton-Schritten "
                           f"nicht konvergiert ({stab_offen or _mass_text(zonen, mess, diff, mass)}"
                           f"{'' if stab_offen else f' > {einst.toleranz:g}'})")
        basis, F_p = zustand_stufe, F_p_stufe
        lam_alt = lam_k
    stufen_gerechnet = len(faktoren)
    stab_offen = ""
    tol = float(einst.toleranz)
    abgenommen = None           # Urteil der Schlussabnahme (nur mit Kontakt)
    rest_mass, mess = rest, None
    if rest is None:
        # Die letzte Loesung gehoert zum letzten Zustand: im Gleichgewicht ist
        # K u = F + F_p, also genau diese elastische Loesung
        u = _loesen(F + F_p, None, "Abschluss", None, None)
        if kontakt is not None:
            F_p_ende, _z, _i = schritt(model, u, basis_anfang, einst, elemente, None)
            bezug = _bezug(norm_F, F_p_ende)
            rest = float(np.linalg.norm(F_p_ende - F_p)) / bezug
            # mit auffaelligen Zonen (ingenieurmaessig): F_p ausserhalb, Kraft
            # und Verschiebung gegen den Stand, an dem F_p gerechnet ist
            rest_mass, _ok, mess = _zonen_mass(zonen, rest, tol, u, F_p_ende, F_p, _z, _i, bezug, 1.0,
                                               "Abschluss", None)
            _zonen_melden(mess, log, progress)
            # was streng abgenommen ist, ist es auch ingenieurmaessig (_zonen_mass)
            abgenommen = _schlussabnahme(rest, tol) or (_zonen_greifen(zonen, mess)
                                                        and _schlussabnahme(rest_mass, tol)
                                                        and bool(mess["erfuellt"]))
            # Zugstaebe (13.10.2026): auch der Abschluss darf den Stabstatus
            # nicht mehr aendern - sonst rechnen die Nachschritte weiter
            stab_offen = _offen(kontakt)
            abgenommen = abgenommen and not stab_offen
            # Nachiteration vom Abschluss aus (27.09.2026): der volle
            # Kontaktlauf des Abschlusses kann u so verschieben, dass F_p nicht
            # mehr passt. Bis dahin hiess das "nicht konvergiert", Schluss. Ein
            # Newton, der die Abnahme verfehlt, versucht sie erst: je Runde ein
            # Newton-Schritt mit der Tangente an der Abschlussloesung (Basis
            # weiter der Anfang der letzten Stufe) und ein neuer Abschluss.
            # Gemessen am Stempel mit ganz gleitender Fuge (feine Reststeifig-
            # keit, K5): Rest 4,75e-3 nach dem ersten Abschluss bei Toleranz
            # 1e-3 - die grobe Feder hatte den Stempel vorher mit 211 kN
            # verborgener Kraft festgehalten.
            nach = 0
            while (nach < ABSCHLUSS_NACHSCHRITTE and info["konvergiert"]
                   and not abgenommen):
                nach += 1
                F_p_neu, zustand_neu, s_info = schritt(model, u, basis_anfang, einst, elemente, log,
                                                       tangente=True)
                info["iterationen"] += 1
                info["verlauf"].append((stufen_gerechnet, -nach, rest, s_info["fliessend"]))
                if progress is not None:
                    progress(f"Plastizität: Abschluss verfehlt (Änderung {rest:.2e}), Nachschritt {nach}: "
                             f"{s_info['fliessend']} {'Element fließt' if s_info['fliessend'] == 1 else 'Elemente fließen'}")
                dK = s_info["dK"]
                if dK.nnz == 0:
                    u = _loesen(F + F_p_neu, None, "Newton", stufen_gerechnet, -nach)
                else:
                    u = _loesen(F + F_p_neu + dK @ u, dK, "Newton", stufen_gerechnet, -nach)
                    info["faktorisierungen"] += 1
                F_p, basis, _s = schritt(model, u, basis_anfang, einst, elemente, None)
                if zonen is not None:
                    # Bezug der naechsten Messung: der Stand, an dem F_p gerechnet ist
                    zonen.messen(u, F_p, F_p, basis, _s, _bezug(norm_F, F_p), 1.0, nur_bezug=True)
                u = _loesen(F + F_p, None, "Abschluss", None, None)
                F_p_ende, _z, _i = schritt(model, u, basis_anfang, einst, elemente, None)
                bezug = _bezug(norm_F, F_p_ende)
                rest = float(np.linalg.norm(F_p_ende - F_p)) / bezug
                rest_mass, _ok, mess = _zonen_mass(zonen, rest, tol, u, F_p_ende, F_p, _z, _i, bezug, 1.0,
                                                   "Abschluss", None)
                _zonen_melden(mess, log, progress)
                abgenommen = _schlussabnahme(rest, tol) or (_zonen_greifen(zonen, mess)
                                                            and _schlussabnahme(rest_mass, tol)
                                                            and bool(mess["erfuellt"]))
                stab_offen = _offen(kontakt)
                abgenommen = abgenommen and not stab_offen
            if nach and log is not None:
                log.append(f"Plastizität: Abschluss nach {nach} Nachschritt{'' if nach == 1 else 'en'} "
                           f"{'bestanden' if abgenommen else 'weiter verfehlt'} "
                           f"({_mass_text(zonen, mess, rest, rest_mass)}, Toleranz {einst.toleranz:g}"
                           f"{'; ' + stab_offen if stab_offen else ''})")
    if rest is not None:
        info["rest_abschluss"] = rest
        if abgenommen is None:
            # gemeinsam: die letzte Stufe hat den Abschluss schon abgenommen,
            # ``rest`` ist dort das Mass von _zonen_mass
            abgenommen = _schlussabnahme(rest, tol)
        if info["konvergiert"] and not abgenommen:
            info["konvergiert"] = False
            if log is not None:
                if stab_offen:
                    log.append(f"Plastizität: an der Lösung des Abschlusses {_offen_was(stab_offen)} "
                               f"({stab_offen}) - nicht konvergiert")
                else:
                    log.append(f"Plastizität: an der Lösung des Abschlusses passt F_p nicht mehr "
                               f"({_mass_text(zonen, mess, rest, rest_mass)} > {einst.toleranz:g}) - nicht konvergiert")
    info["fliessend"] = len(basis.fliessend())
    info["eps_p_max"] = basis.eq_max()
    if zonen is not None and log is not None:
        zeile = zonen.schlusszeile()
        if zeile:
            log.append(zeile)
    if log is not None:
        log.append(f"Plastizität: {info['fliessend']} {'Element fließt' if info['fliessend'] == 1 else 'Elemente fließen'}, ε_p,eq max "
                   f"{info['eps_p_max'] * 100:.3f} %, {info['iterationen']} "
                   f"{'Newton-Schritt' if info['iterationen'] == 1 else 'Newton-Schritte'} in "
                   f"{stufen_gerechnet} {'Laststufe' if stufen_gerechnet == 1 else 'Laststufen'}"
                   + (f" ({info['halbiert']}-mal halbiert)" if info.get("halbiert") else "")
                   + f" ({info['faktorisierungen']} Faktorisierungen, konsistente Tangente)"
                   + ("" if info["konvergiert"] else " - nicht konvergiert"))
    return u, basis, F_p, info


def iteration(model, F, loesen, einst: Plastizitaet, aktiv=None, log: list = None,
              progress=None, loesen_tangente=None, kontakt=None, F_sofort=None,
              sigma0=None, zonen=None, start=None) -> tuple:
    """Laststufen und Fliess-Iteration. ``loesen(F_ges)`` liefert u fuer die
    Gesamtlast bei der **elastischen** Steifigkeit (mit Kontakt: eine
    Kontakt-Iteration, die Faktorisierung bleibt). Rueckgabe
    (u, Zustand, F_p, info) fuer die volle Last.

    Zwei Wege, ``einst.verfahren`` waehlt:

    * ``"tangente"`` (Vorgabe) - Newton mit der konsistenten elastoplastischen
      Tangente. Braucht ``loesen_tangente(F_ges, dK)``: loest mit der
      Steifigkeit K + dK, also **je Schritt eine neue Faktorisierung**. Die
      Fortschreibung in Gesamtform ist

          (K + ΔK) u_{k+1} = F_k + F_p(u_k) + ΔK u_k,

      identisch zu ΔK-Newton auf dem Residuum F_k + F_p − K u (die
      Randbedingungen und der Kontakt bleiben dem Loeser ueberlassen). Die
      Rueckfuehrung geht in jedem Schritt vom Zustand am **Anfang der
      Laststufe** aus - nur so ist die Tangente wirklich die Ableitung.
    * ``"anfangsdehnung"`` - die alte Fixpunktfolge bei fester Steifigkeit
      mit Aitken-Relaxation. Eine Faktorisierung je Rechnung, aber linear mit
      dem Faktor 1 − E_t/E: bei 1 % Verfestigung 0,99 je Schritt.

    Ohne ``loesen_tangente`` (etwa aus einem Test, der nur ``system.solve``
    hergibt) faellt "tangente" auf "anfangsdehnung" zurueck.

    ``kontakt`` (vom Loeser, wenn sein Loesungsweg selbst iteriert - Kontakt,
    ausfallende Zugstaebe): die Schlussabnahme in beiden Wegen (seit dem
    25.09.2026 auch in der Anfangsdehnung) und, nur im Newton und wenn
    gewaehlt, die gemeinsame Iteration von Fliessen und Kontakt - siehe
    :func:`_newton`. Ohne ihn, und im Weg "anfangsdehnung" immer, bleibt
    jeder Aufruf ein voller Kontaktlauf.

    ``F_sofort`` (solver.case_sofort): der Anteil der Temperaturlasten und
    Vorspannkraefte an F. Er wirkt seit dem 10.10.2026 ab der ersten
    Laststufe voll, gesteigert wird nur der Rest (:func:`stufenlast`); das
    Protokoll sagt es in einer Zeile. None rechnet wie bisher.

    ``sigma0`` {Element: (6,)}: die Anfangsspannung einer Vorspannung als
    Koerper (temp["sigma0"] aus solver.case_loads, mit den Faktoren der
    Kombination). Die Rueckfuehrung prueft seit dem 10.10.2026 die wahre
    Spannung D(ε − ε_p) − σ₀ (siehe :class:`Zustand`). Voll und unveraendert
    ueber alle Stufen, denn die Vorspannung wirkt ab der ersten voll
    (``F_sofort``).

    ``zonen`` (solver._SpitzenImNewton, seit dem 13.10.2026): die Stellen
    „Kraft ohne Fläche“ des Modells - im Newton das Kriterium
    ``Plastizitaet.abbruch`` (:data:`ABBRUCH_WEGE`, :func:`_zonen_mass`) und
    je Schritt eine Zeile im Protokoll. Die Anfangsdehnung misst wie bisher
    (ihr Abbruch am geschaetzten Fehler ist ein anderer).

    ``start`` (Zustand, F_p) (seit dem 13.10.2026, statik3d.vorspannkraft):
    der plastische Zustand, von dem die erste Laststufe ausgeht - der des
    Spannschritts einer Vorspannkraft (Soll nach Verankerung). Ohne ihn
    beginnt jede Rechnung jungfraeulich wie bisher. Die Anfangsspannung
    ``sigma0`` ist die dieser Rechnung, nicht die des Starts.
    """
    elemente = _solid_elemente(model, aktiv)
    zustand = Zustand(sigma0)
    F = np.asarray(F, float)
    norm_F = float(np.linalg.norm(F))      # 0 ohne aeussere Last - dann greift _bezug
    F_p = np.zeros(model.ndof)
    if start is not None:
        zustand = start[0].kopie()
        zustand.sigma0 = dict(sigma0 or {})
        F_p = np.array(start[1], float, copy=True)
    u = None
    info = {"laststufen": int(max(1, einst.laststufen)), "iterationen": 0, "konvergiert": True,
            "fliessend": 0, "eps_p_max": 0.0, "verlauf": [], "faktorisierungen": 0,
            "verfahren": "anfangsdehnung"}
    if not elemente:
        u = loesen(F)
        return u, zustand, F_p, info
    if F_sofort is not None:
        F_sofort = np.asarray(F_sofort, float)
        info["sofort_voll"] = True
        if log is not None:
            log.append("Plastizität: " + SOFORT_VOLL)
    from .elements import solid as sl
    # Ohne Verfestigung ist D_ep in Fliessrichtung singulaer (Eigenwert
    # 2G(θ − θ̄) = 2G (H/3G)/(1 + H/3G) = 0) - dann rechnet die
    # Anfangsdehnungs-Iteration. Ebenso bei einem Elementtyp ohne Stapel.
    # Newton mit dem Boden H_TANGENTE ginge auch (am Rohr nach Hill bei
    # c/a = 1,5 5 bis 7 statt 11 bis 37 Schritte, bei 0,97 p_L 12 bis 16 statt
    # 22 bis 132; gemessen 23.09.2026); ob er schneller ist,
    # entscheidet am Drehlager die Zeit (Zerlegung 3,41 s gegen 0,32 s je
    # Rueckwaertseinsetzen), nicht die Schrittzahl - noch nicht gemessen.
    # Seit dem 13.10.2026 traegt jeder Werkstoff seine Verfestigung: der Newton
    # rechnet, wenn jeder Werkstoff mit Streckgrenze verfestigt (ohne eigene
    # Angabe die der Rechnung - dann wie bisher einst.H(1.0) > 0). Das Plateau
    # ueber f_u haelt der Boden H_TANGENTE regulaer.
    mats = {model.elements[i].mat for i in elemente}
    r_alle = [werkstoff_verfestigung(model.materials[nm], einst) for nm in mats
              if nm in model.materials and getattr(model.materials[nm], "fy", None)]
    verfestigt = min(r_alle) > 0.0 if r_alle else einst.H(1.0) > 0.0
    kann_tangente = (loesen_tangente is not None and verfestigt
                     and all(model.elements[i].typ in sl.OPERATOREN for i in elemente))
    if str(getattr(einst, "verfahren", "tangente")) == "tangente" and kann_tangente:
        return _newton(model, F, loesen, loesen_tangente, einst, elemente, norm_F, info,
                       log, progress, kontakt, F_sofort, zustand.sigma0, zonen,
                       start=None if start is None else (zustand, F_p))
    stufen = int(max(1, einst.laststufen))
    for k in range(1, stufen + 1):
        lam = k / stufen
        F_k = stufenlast(F, F_sofort, lam)
        # Aitken-Relaxation der Fixpunktfolge F_p: das Anfangssteifigkeits-
        # verfahren zieht sich mit dem Faktor E_t/E zusammen - bei 2 %
        # Verfestigung 0,98 je Schritt, 60 Schritte brachten 65 % des Wegs.
        # Aitken schaetzt den Faktor aus zwei Residuen und springt an den
        # Fixpunkt (Zugversuch: 6 statt > 60 Schritte); zwischen 0,5 und 200
        # begrenzt, je Laststufe neu begonnen.
        omega, r_alt = 1.0, None
        # Jede Rueckfuehrung geht vom Zustand am Anfang der Laststufe aus, wie
        # beim Newton: dann ist F_p eine Funktion von u allein, und der
        # Fixpunkt ist die Loesung. Bis zum 23.09.2026 wurde der Zustand von
        # Schritt zu Schritt fortgeschrieben - mit der Aitken-Ueberrelaxation
        # (bis 200) sammelte sich plastische Dehnung entlang des
        # Iterationswegs an, und die Folge "konvergierte" auf einen anderen
        # Punkt: am Rohr nach Hill (tet10 8 x 4, ideal plastisch) u 0,99901 bei
        # Toleranz 1e-3 und 0,99933 bei 1e-6 statt 0,99863 wie der Newton;
        # seitdem 0,99863 wie er (tests/test_plastizitaet.py,
        # test_anfangsdehnung_trifft_den_newton).
        basis = zustand
        aenderungen: list = []
        for it in range(1, int(max(1, einst.iterationen)) + 1):
            u = loesen(F_k + F_p)
            F_p_neu, zustand_neu, s_info = schritt(model, u, basis, einst, elemente, log)
            r = F_p_neu - F_p
            diff = float(np.linalg.norm(r)) / _bezug(norm_F, F_p_neu)
            info["iterationen"] += 1
            info["verlauf"].append((k, it, diff, s_info["fliessend"]))
            if progress is not None:
                progress(f"Plastizität: Laststufe {k}/{stufen}, Schritt {it}: {s_info['fliessend']} Elemente "
                         f"fließen, Änderung {diff:.2e}")
            # Abbruch am **geschaetzten Fehler**, nicht an der Aenderung allein:
            # die Folge zieht sich mit ρ zusammen, und der Fehler des
            # angenommenen F_p ist rund ρ/(1 − ρ) mal die Aenderung - bei
            # ρ → 1 (ideal plastisch nahe der Grenzlast) viel mehr. ρ ist der
            # groessere von zwei Werten: das groesste Verhaeltnis
            # aufeinanderfolgender Aenderungen der letzten drei Schritte (faengt
            # Wachstum) und die mittlere Rate ueber bis zu acht Schritte (Aitken-
            # Spruenge machen kurze steile Abfaelle, unter denen die Folge mit
            # rund 0,93 je Schritt weiterkriecht). Das Aitken-ω selbst
            # (1/(1 − λ) im skalaren Modell) taugt nicht: nach einem Sprung
            # schaetzte es λ = 0,04 in einer Folge, die sichtlich stand. Nie
            # lockerer als die Aenderung selbst; im ersten Schritt einer Stufe
            # ist ρ noch unbekannt.
            # Gemessen 23.09.2026 am Rohr nach Hill, Toleranz 1e-3, groesste
            # Abweichung von σ_v an den Knoten gegen den Newton, vorher -> jetzt
            # (Schritte): bei 0,97 p_L tet10 8 x 4 3,86 -> 0,44 N/mm2 (26 -> 55),
            # tet10 16 x 8 1,97 -> 0,03 (26 -> 67; ohne die mittlere Rate 0,68),
            # hex8 32 x 16 0,67 -> 0,00 (22 -> 24); bei c/a = 1,5 hoechstens
            # 0,35 -> 0,09. Nahe der Grenzlast vergroessert die fast singulaere
            # Tangente jeden Rest in F_p - dort waere der Newton der richtige
            # Weg (siehe kann_tangente oben).
            # tests/test_plastizitaet.py, test_anfangsdehnung_trifft_den_newton.
            aenderungen.append(diff)
            if diff == 0.0:
                fehler = 0.0
            elif len(aenderungen) < 2:
                fehler = np.inf
            else:
                a3 = aenderungen[-4:]
                rho = max(y / x if x > 0.0 else np.inf for x, y in zip(a3[:-1], a3[1:]))
                a8 = aenderungen[-9:]
                if a8[0] > 0.0:
                    rho = max(rho, (a8[-1] / a8[0]) ** (1.0 / (len(a8) - 1)))
                fehler = diff * max(1.0, rho / (1.0 - rho)) if rho < 1.0 else np.inf
            # Zugstaebe in der Konvergenzbedingung (13.10.2026) wie im Newton
            stab_offen = _offen(kontakt) if fehler <= float(einst.toleranz) else ""
            if stab_offen and log is not None:
                log.append(f"Plastizität: Laststufe {k}/{stufen}, Schritt {it}: {stab_offen} - "
                           "noch nicht konvergiert")
            if fehler <= float(einst.toleranz) and not stab_offen:
                F_p, zustand = F_p_neu, zustand_neu
                break
            if r_alt is not None:
                d = r - r_alt
                dd = float(d @ d)
                if dd > 0:
                    omega = float(min(200.0, max(0.5, -omega * float(r_alt @ d) / dd)))
            F_p = F_p + omega * r
            zustand = zustand_neu
            r_alt = r
        else:
            info["konvergiert"] = False
            if log is not None:
                log.append(f"Plastizität: Laststufe {k} nach {einst.iterationen} Schritten nicht konvergiert "
                           f"(Änderung {diff:.2e}, geschätzter Fehler {fehler:.2e} > {einst.toleranz:g})")
    # Die letzte Loesung gehoert zum letzten Zustand
    u = loesen(F + F_p)
    if kontakt is not None:
        # Schlussabnahme wie im Newton (_schlussabnahme, 25.09.2026): mit
        # Kontakt ist der Abschluss ein eigener voller Kontaktlauf und kann den
        # Kontaktzustand noch aendern. In der Anfangsdehnung ist das seltener
        # als im Newton - jeder ihrer Schritte loest genau so wie der Abschluss,
        # und ihr Abbruch am geschaetzten Fehler haelt die naechste Aenderung
        # unter der Toleranz: gemessen am gequetschten Block und am ideal
        # plastischen Block mit Reibung (Stand 7163f37) lag der Rest an allen
        # "konvergiert" bei <= 6,1e-6 gegen 1e-4. Ausgeschlossen ist ein
        # Umspringen des Kontakts genau im Abschluss aber nicht; die Pruefung
        # kostet eine Rueckfuehrung je Lastfall.
        F_p_ende, _z, _i = schritt(model, u, basis, einst, elemente, None)
        rest = float(np.linalg.norm(F_p_ende - F_p)) / _bezug(norm_F, F_p_ende)
        info["rest_abschluss"] = rest
        stab_offen = _offen(kontakt)
        if info["konvergiert"] and stab_offen:
            info["konvergiert"] = False
            if log is not None:
                log.append(f"Plastizität: an der Lösung des Abschlusses {_offen_was(stab_offen)} "
                           f"({stab_offen}) - nicht konvergiert")
        if info["konvergiert"] and not _schlussabnahme(rest, float(einst.toleranz)):
            info["konvergiert"] = False
            if log is not None:
                log.append(f"Plastizität: an der Lösung des Abschlusses passt F_p nicht mehr "
                           f"(Änderung {rest:.2e} > {einst.toleranz:g}) - nicht konvergiert")
    info["fliessend"] = len(zustand.fliessend())
    info["eps_p_max"] = zustand.eq_max()
    if log is not None:
        log.append(f"Plastizität: {info['fliessend']} {'Element fließt' if info['fliessend'] == 1 else 'Elemente fließen'}, ε_p,eq max {info['eps_p_max'] * 100:.3f} %, "
                   f"{info['iterationen']} {'Schritt' if info['iterationen'] == 1 else 'Schritte'} in "
                   f"{stufen} {'Laststufe' if stufen == 1 else 'Laststufen'}"
                   + ("" if info["konvergiert"] else " - nicht konvergiert"))
    return u, zustand, F_p, info


def sigma0_je_element(model, zustand: Zustand) -> dict:
    """{Element: D eps_p} - die Anfangsspannung fuer den Spannungsnachlauf
    (σ = D ε − D eps_p), im Schluessel "sigma0" von temp.

    Der Zustand haelt eps_p je Integrationspunkt; hier wird ueber sie
    gemittelt - **gewichtet** mit den Gewichten des Dehnungsoperators (seit
    22.09.2026; vorher ungewichtet, was bei einer Lobatto-Regel ueber die
    Dicke die Randpunkte mit 1/10 statt 9/90 bzw. die Mitte mit 1/5 statt
    32/45 zaehlte). Beim tet4 (ein Punkt) ist es derselbe Wert wie frueher,
    bei 2x2x2 an einem Parallelepiped ebenso (gleiche Gewichte)."""
    from .elements import solid as sl
    aus = {}
    je_typ: dict = {}
    for i in zustand.eps_p:
        je_typ.setdefault(model.elements[i].typ, []).append(int(i))
    for typ, liste in je_typ.items():
        gew = {}
        if typ in sl.OPERATOREN:
            for op in sl.dehnungsoperator(model, typ, liste):
                for a, i in enumerate(op.idx):
                    gew[int(i)] = op.w[:, a] / op.w[:, a].sum()
        for i in liste:
            e = model.elements[i]
            mat = model.materials[e.mat]
            ep = np.asarray(zustand.eps_p[i], float).reshape(-1, 6)
            w = gew.get(i)
            mittel = ep.mean(axis=0) if w is None or len(w) != len(ep) else w @ ep
            aus[i] = sl.D_matrix(float(mat.E), float(mat.nu)) @ mittel
    return aus


def punktspannungen(model, u, zustand: Zustand) -> dict:
    """{Element: (xi (P,3), sigma (P,6))} der Elemente mit plastischem Zustand -
    die Spannung an **jedem Integrationspunkt**, sigma = D (B u + B_a alpha - eps_p).

    Dort und nur dort ist der plastische Zustand bekannt; jeder dieser Werte
    liegt auf oder in der verfestigten Fliessflaeche. Die Auswertepunkte
    (Mitte, Ecken) liegen woanders - an einer Ecke waechst die Dehnung ueber
    die der Punkte hinaus, eps_p bleibt zurueck, und die gemeldete Spannung
    schoss ueber die Fliessflaeche (gemessen 20.09.2026 am Reibblock: 2,93
    gegen die Grenze 1,42 MPa). Darum nimmt der Nachlauf fuer fliessende
    Elemente diese Punkte (solver._post_chunk).

    Die inneren Moden (hex8) folgen aus der Stationaritaet bei festem eps_p:
    Kaa alpha = h_p - Kua^T u (siehe _eas_alpha) - im Gleichgewicht ist das
    dasselbe alpha, das der Element-Newton des letzten Schritts fand.
    """
    from .elements import solid as sl
    if not zustand.eps_p:
        return {}
    je_typ: dict = {}
    for i in zustand.eps_p:
        typ = model.elements[int(i)].typ
        if typ in sl.OPERATOREN:
            je_typ.setdefault(typ, []).append(int(i))
    u = np.asarray(u, float).ravel()
    aus = {}
    for typ, liste in je_typ.items():
        for op in sl.dehnungsoperator(model, typ, sorted(liste)):
            d = _stapel_teil(model, op)
            n, P = op.n, op.P
            ue_flach = u[d["dofs"]]
            eps_p = np.zeros((P, n, 6))
            for a, i in enumerate(op.idx):
                eps_p[:, a, :] = _punktfeld(zustand.eps_p[int(i)], P, 6)
            alpha = None
            if d.get("eas") is not None:
                alpha = _eas_alpha(d["eas"], d["lam"], d["mu"], eps_p, d["lasten"], ue_flach)
            sig = np.empty((n, P, 6))
            for p in range(P):
                eps = sl.dehnung_mit_moden(op, p, ue_flach, alpha)
                sig[:, p, :] = _spannung(d["lam"], d["mu"], eps - eps_p[p])
            xi = None if op.xi is None else np.asarray(op.xi, float)
            for a, i in enumerate(op.idx):
                aus[int(i)] = (xi, sig[a])
    return aus
