"""
Fehlerschaetzer: wo ist das Netz zu grob - und wie fein muesste es sein?

„Fein genug" ist ohne Mass nicht entscheidbar. Das Mass hier ist der
**Spannungssprung** (Zienkiewicz/Zhu 1987): der lineare Tetraeder traegt eine
konstante Spannung je Element, die wahre Spannung ist stetig. Mittelt man
die Elementspannungen auf die Knoten (:func:`spannungen.knotenmittel`,
volumengewichtet), entsteht eine stetige, im Element linear verlaufende
Spannung sigma*, die der wahren naeher ist als die Elementspannung. Der
Unterschied ist der Fehlerindikator, gemessen in der Energienorm:

    eta_e^2 = Integral ueber das Element von (sigma* - sigma_e)^T C (sigma* - sigma_e) dV

mit C = D^-1 (Nachgiebigkeit des Werkstoffs). Fuer den geradflaechigen
Tetraeder mit linearem sigma* ist das Integral geschlossen:

    eta_e^2 = V/20 * [ (Sum_i e_i)^T C (Sum_i e_i) + Sum_i e_i^T C e_i ]

mit e_i = sigma*_i - sigma_e an den vier Ecken (Integral N_i N_j dV = V/20
fuer i != j, V/10 fuer i = j). Der Gesamtfehler bezogen auf die Energie der
Loesung,

    eta_rel = sqrt(Sum eta_e^2) / sqrt(U^2 + Sum eta_e^2),   U^2 = Sum V_e sigma_e^T C sigma_e,

ist die Zahl, an der „fein genug" entschieden wird (Ziel etwa 5 %).

Daraus die **neue Kantenlaenge** je Element (Zienkiewicz/Zhu): der zulaessige
Fehler wird gleich auf alle Elemente verteilt, e_zul = eta_zul / sqrt(N), und
jedes Element bekommt

    h_neu = h_alt * (e_zul / eta_e)^(1/p),   p = 1 fuer tet4, 2 fuer tet10,

begrenzt auf das Drittel bis Doppelte je Runde - grosse Spruenge in einem
Schritt sind Glueckssache, drei Runden mit begrenztem Schritt nicht. Wo der
Fehler klein ist, wird das Netz **groeber**; das ist der Hebel, der beim
Drehlager zaehlt: nicht feiner an der Kerbe, sondern groeber im Feld.

Was daraus wird: je Koerper eine eigene Kantenlaenge (``netz.koerper_h``,
das 90. Perzentil der neuen Kantenlaengen seiner Elemente - der Koerper
wird so grob, wie es neun Zehntel seiner Elemente vertragen) und
**Feldpunkte** (``netz.feldpunkte``) an den Elementen, die feiner bleiben
muessen als ihr Koerper. Aus beidem baut :mod:`statik3d.netzfeld` das
Groessenfeld des naechsten Durchgangs. Die Schleife selbst steht in
:mod:`statik3d.adaptiv`.

Der Indikator ist eine Schaetzung, kein Beweis: er sieht den Fehler der
Spannung im Element, nicht den der Verschiebung, und an einer Singularitaet
(einspringende Ecke, Lastrand) bleibt er endlich, wo der wahre Fehler es
nicht ist. Fuer die Frage „wo ist zu grob" ist er das uebliche und
ausreichende Mass.

**Knotendilatation** (``model.knotendilatation``, Element-Sitzung): dann ist
der volumetrische Anteil der Elementspannung schon knotengemittelt, und der
Sprung misst nur noch den deviatorischen Anteil - der Indikator wird
blinder, nicht blind (Hinweis der Loeser-Sitzung, 20.09.2026). Gemessen an
der Platte 0,4 x 0,24 x 0,08 m mit Bohrung unter Zug, 5 233 Tetraeder, mit
und ohne Schalter auf **demselben** Netz (21.09.2026):

    nu      eta_rel ohne  eta_rel mit  Rangkorrelation  oberstes Zehntel gleich
    0,300      12,1 %        11,4 %         0,973            430 von 523
    0,450      15,5 %        12,7 %         0,875            315 von 523
    0,499      27,3 %        14,1 %         0,433            157 von 523

Bei nu -> 0,5 ist nicht der Schalter das Problem, sondern sein Fehlen: ohne
ihn sperrt der tet4 (sigma_v max 151 statt 314 N/mm^2, |u| 0,177 statt
0,214 mm), und der Indikator misst dann die Sperre statt den Fehler. Mit
dem Schalter liegt der Schaetzer bei nu = 0,499 dort, wo er bei nu = 0,3
liegt. Fuer nahezu inkompressibles Verhalten (Fliessen) gehoert der Schalter
also an, und der Indikator liest die Spannung, die auch die Nachweise lesen.
"""
from __future__ import annotations

import numpy as np

#: Bezogener Fehler in der Energienorm, unter dem ein Netz als fein genug gilt
ZIEL = 0.05
#: Um hoechstens diesen Faktor darf die Kantenlaenge je Runde feiner werden
FAKTOR_MIN = 1.0 / 3.0
#: ... und um hoechstens diesen groeber
FAKTOR_MAX = 2.0
#: Perzentil der neuen Kantenlaengen eines Koerpers, das seine eigene
#: Kantenlaenge wird: 90 heisst, neun Zehntel seiner Elemente duerfen so grob
#: sein; das letzte Zehntel haelt das Groessenfeld fein.
PERZENTIL_KOERPER = 90.0
#: Um hoechstens diesen Faktor darf die geschaetzte Elementzahl je Runde
#: wachsen. Ohne diese Schranke lief die Platte mit Bohrung von 52 801 auf
#: 1 300 025 Tetraeder in **einer** Runde (20.09.2026): die Gleichverteilung
#: nach Zienkiewicz/Zhu unterstellt, dass die Elementzahl gleich bleibt, und
#: das Drittel als kleinster Schritt gibt je Element bis zu 27 Kinder. Drei
#: Runden mit dem Dreifachen sind dasselbe Ziel - nur ohne den Sprung ins
#: Unbezahlbare.
WACHSTUM_MAX = 3.0
#: Um diesen Faktor legt der Vernetzer mehr Elemente, als Summe (h/h_neu)^3
#: sagt: das Feld verfeinert um jede Quelle herum einen Kegel, nicht nur das
#: Element, die Huelle folgt mit (3,4 Tetraeder je Randdreieck), und die
#: Verfeinerung setzt Kanten von etwa 0,8 h. Gemessen an der Platte mit fuenf
#: Bohrungen (20.09.2026): Schaetzung 3,0-fach, Netz 14,4-fach und 15,0-fach
#: - Faktor 4,8 und 5,0. Ohne diesen Faktor kostete jede Runde einen
#: Zwischenlauf ueber dem Budget (1 051 862 Tetraeder, 198 s), bevor die
#: Nachmessung ihn vergroeberte.
KALIBRIERUNG = 5.0
#: Elemente, deren Vergleichsspannung mindestens diesen Anteil der groessten
#: erreicht, werden **nicht** groeber. Die Energienorm mittelt ueber das
#: ganze Bauteil: eine schon aufgeloeste Kerbe hat dort einen kleinen Fehler
#: und wuerde wieder vergroebert (Platte: sigma_v max 497 -> 391 N/mm^2 von
#: einer Runde zur naechsten, 20.09.2026). Der Nachweis wird aber genau an
#: den hoch beanspruchten Stellen gefuehrt. Der Schutz gilt nur, wo es eine
#: **Konzentration** gibt (groesste Spannung ueber KONZENTRATION mal dem
#: Mittel) - bei gleichfoermiger Spannung ist jedes Element „hoch", und
#: nichts spraeche gegen ein groeberes Netz.
SPANNUNGSSCHUTZ = 0.5
KONZENTRATION = 2.0
#: Elementansatz -> Konvergenzordnung p der Spannung
ORDNUNG = {"tet4": 1, "tet10": 2, "hex8": 1, "hex20": 2, "pent6": 1, "pent15": 2, "pyr5": 1,
           "tetp2": 2, "tetp3": 3, "tetp4": 4}
#: Eckknoten je Typ - das Knotenmittel wird linear ueber die Ecken
#: interpoliert, auch bei den quadratischen Typen (tet10 ueber seine vier
#: Ecken, wie bisher).
ECKEN = {"tet4": 4, "tet10": 4, "hex8": 8, "hex20": 8, "pent6": 6, "pent15": 6, "pyr5": 5,
         "tetp2": 4, "tetp3": 4, "tetp4": 4}
#: Kanten je Typ (Eckknoten) fuer die mittlere Kantenlaenge
KANTEN = {4: [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)],
          8: [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)],
          6: [(0, 1), (1, 2), (2, 0), (3, 4), (4, 5), (5, 3), (0, 3), (1, 4), (2, 5)],
          5: [(0, 1), (1, 2), (2, 3), (3, 0), (0, 4), (1, 4), (2, 4), (3, 4)]}
#: Der lineare Typ mit denselben Ecken - seine Formfunktionen und Gausspunkte
#: rechnen das Integral der Energienorm ueber das Element
_LINEAR = {"tet4": "tet4", "tet10": "tet4", "hex8": "hex8", "hex20": "hex8",
           "pent6": "pent6", "pent15": "pent6", "pyr5": "pyr5",
           # Tetraeder mit Ordnung p: vorerst wie tet4 gelesen (Eckfehler linear
           # ueber die vier Ecken); die hoehere Ordnung ist nicht beruecksichtigt
           # - bericht() sagt es in einer eigenen Zeile
           "tetp2": "tet4", "tetp3": "tet4", "tetp4": "tet4"}
#: Hoechstzahl der Feldpunkte, die der Schaetzer schreibt; darueber werden
#: die Zellen der Vorausduennung verdoppelt (siehe feldpunkte)
FELDPUNKTE_MAX = 200_000


def _nachgiebigkeit(model, ids: np.ndarray) -> np.ndarray:
    """C = D^-1 je Element (n, 6, 6) - einmal je Werkstoff gerechnet."""
    from .elements.solid import D_matrix
    C = np.zeros((len(ids), 6, 6))
    je_mat: dict = {}
    for k, i in enumerate(ids):
        e = model.elements[int(i)]
        mat = model.materials.get(e.mat) if isinstance(model.materials, dict) else None
        E = float(getattr(mat, "E", 210e9) or 210e9)
        nu = float(getattr(mat, "nu", 0.3) or 0.3)
        schl = (E, nu)
        Cm = je_mat.get(schl)
        if Cm is None:
            Cm = np.linalg.inv(D_matrix(E, nu))
            je_mat[schl] = Cm
        C[k] = Cm
    return C


#: Ein Feld gleicher Bauart wie ``solid_res``, in dem der Loeser je Element
#: das **Mittel ueber die Gausspunkte** fuehrt, wenn er es fuehrt. Der
#: Schaetzer nimmt es bevorzugt.
#:
#: Warum: ``solid_res`` traegt fuer ein elastisches Element mit mehreren
#: Auswertepunkten den Punkt mit der **hoechsten** Vergleichsspannung, fuer
#: ein **fliessendes** dagegen nur die **Mitte** (Loeser-Sitzung, 21.09.2026).
#: In einem Netz mit fliessenden und elastischen Elementen nebeneinander
#: vergleicht der Zienkiewicz/Zhu-Sprung also Maximum gegen Mitte - genau an
#: der Fliessgrenze, wo der Indikator am meisten zu tun hat, und ein Teil des
#: gemessenen Sprungs ist dann der Regelwechsel und nicht das Netz. Fuer tet4
#: ist das gleichgueltig (ein Punkt), fuer hex8/pent6/pyr5 nicht. Die
#: Loeser-Sitzung kann das Mittel ohne Mehrkosten danebenstellen; sobald es da
#: ist, wirkt es hier ohne weitere Aenderung.
MITTELFELD = "solid_mittel"


def _elemente(model, res) -> list:
    """Die Volumenelemente mit Ergebnis, nach Typ: [(typ, Elementnummern,
    Eckknoten (n, k), Spannungen (n, 6))] - tet10 ueber seine vier Ecken,
    hex20 ueber acht, pent15 ueber sechs.

    Gelesen wird :data:`MITTELFELD`, wenn der Loeser es fuehrt, sonst
    ``solid_res``."""
    gruppen: dict = {}
    quelle = getattr(res, MITTELFELD, None) or res.solid_res
    for i, s_ in quelle.items():
        e = model.elements[int(i)]
        if e.typ not in ORDNUNG:
            continue
        s_ = np.asarray(s_, float).ravel()
        if s_.size < 6:
            continue
        k = ECKEN[e.typ]
        g = gruppen.setdefault(e.typ, ([], [], []))
        g[0].append(int(i))
        g[1].append([int(x) for x in e.nodes[:k]])
        g[2].append(s_[:6])
    aus = []
    for typ in sorted(gruppen):
        ids, K, S = gruppen[typ]
        aus.append((typ, np.asarray(ids, int), np.asarray(K, int), np.asarray(S, float)))
    return aus


def _tetraeder(model, res) -> tuple:
    """(Elementnummern, Eckknoten (n, 4), Spannungen (n, 6)) der Tetraeder
    mit Ergebnis - tet10 ueber seine vier Ecken. (Bleibt fuer Pruefungen; der
    Indikator liest alle Typen ueber _elemente.)"""
    for typ, ids, K, S in _elemente(model, res):
        if typ in ("tet4", "tet10"):
            return ids, K, S
    return np.zeros(0, int), np.zeros((0, 4), int), np.zeros((0, 6))


def _energienorm_quadrat(typ: str, X: np.ndarray, E: np.ndarray, C: np.ndarray) -> tuple:
    """(Integral der Energienorm des linear interpolierten Eckfehlers E (n, k,
    6) je Element, Volumen je Element) - fuer Tetraeder geschlossen, fuer
    Hexaeder, Keile und Pyramiden ueber die Gauss-Quadratur des linearen
    Typs (elements.solid._ISO): das Produkt zweier trilinearer Felder ist je
    Richtung vom Grad 2, zwei Punkte je Richtung integrieren es genau."""
    from .elements.solid import _ISO
    n = len(X)
    if typ == "tet4":
        V = np.abs(np.einsum("ij,ij->i", X[:, 1] - X[:, 0],
                             np.cross(X[:, 2] - X[:, 0], X[:, 3] - X[:, 0]))) / 6.0
        summe = E.sum(axis=1)
        q_summe = np.einsum("ni,nij,nj->n", summe, C, summe)
        q_ecken = np.einsum("nki,nij,nkj->n", E, C, E)
        return V / 20.0 * (q_summe + q_ecken), V
    N_dN, GP, W = _ISO[typ]
    eta2 = np.zeros(n)
    V = np.zeros(n)
    for g, w in zip(np.asarray(GP, float).reshape(-1, 3), np.asarray(W, float).ravel()):
        N, dN = N_dN(*g)
        N = np.asarray(N, float).ravel()
        dN = np.asarray(dN, float).reshape(len(N), 3)
        J = np.einsum("ki,nkj->nij", dN, X)                     # (n, 3, 3)
        detJ = np.abs(np.linalg.det(J))
        Eg = np.einsum("k,nkj->nj", N, E)                       # (n, 6) Fehler am Gausspunkt
        eta2 += w * detJ * np.einsum("ni,nij,nj->n", Eg, C, Eg)
        V += w * detJ
    return eta2, V


def indikator(model, ergebnisse) -> dict:
    """Der Fehlerindikator je Volumenelement ueber ein oder mehrere Ergebnisse.

    ``ergebnisse``: ein :class:`solver.Results` oder eine Liste davon (die
    Lastfaelle, an denen sich das Netz ausrichten soll); je Element zaehlt
    der groesste Fehler ueber alle. Rueckgabe ein Woerterbuch mit den Reihen
    ``ids`` (Elementnummern), ``eta`` (Fehler je Element, Energienorm),
    ``h`` (mittlere Kantenlaenge), ``V`` (Volumen), ``sv`` (groesste
    Vergleichsspannung), ``zentren`` (n, 3) und den Zahlen ``eta_rel``
    (bezogener Gesamtfehler), ``U`` (Energienorm der Loesung), ``N``.
    Ohne Volumenelement mit Ergebnis ist ``N`` 0 und ``eta_rel`` 0.

    Gelesen werden alle Typen aus ORDNUNG - seit 21.09.2026 auch hex8,
    pent6 und pyr5 (gesweepte und zerlegte Koerper): das Knotenmittel ist
    volumengewichtet ueber **alle** Elemente am Knoten, das Integral der
    Energienorm laeuft fuer Hexaeder, Keile und Pyramiden ueber die
    Gauss-Quadratur (:func:`_energienorm_quadrat`). Ein Sechsflaechner mit
    einer Elementspannung wird dabei wie der Tetraeder als stueckweise
    konstant gelesen; das ist konservativ.
    """
    from . import spannungen as spn
    liste = list(ergebnisse) if isinstance(ergebnisse, (list, tuple)) else [ergebnisse]
    liste = [r for r in liste if r is not None and getattr(r, "solid_res", None)]
    leer = {"ids": np.zeros(0, int), "eta": np.zeros(0), "h": np.zeros(0), "V": np.zeros(0),
            "sv": np.zeros(0), "zentren": np.zeros((0, 3)), "eta_rel": 0.0, "U": 0.0,
            "N": 0, "p": np.zeros(0, int)}
    if not liste:
        return leer
    gruppen = _elemente(model, liste[0])
    if not gruppen:
        return leer
    ids_alle = np.concatenate([g[1] for g in gruppen])
    reihenfolge = {int(i): k for k, i in enumerate(ids_alle)}
    n_alle = len(ids_alle)
    nn = int(model.nn)
    # Volumen, Kantenlaenge, Schwerpunkt je Element - typweise
    V_alle = np.zeros(n_alle)
    h_alle = np.zeros(n_alle)
    zentren = np.zeros((n_alle, 3))
    lage = {}
    for typ, ids, K, _S in gruppen:
        idx = np.array([reihenfolge[int(i)] for i in ids], int)
        lage[typ] = idx
        X = model.nodes[K]
        _eta0, V = _energienorm_quadrat(_LINEAR[typ], X, np.zeros((len(ids), K.shape[1], 6)),
                                        np.zeros((len(ids), 6, 6)))
        V_alle[idx] = V
        kanten = KANTEN[K.shape[1]]
        h_alle[idx] = np.mean([np.linalg.norm(X[:, a_] - X[:, b_], axis=1) for a_, b_ in kanten], axis=0)
        zentren[idx] = X.mean(axis=1)
    C_alle = _nachgiebigkeit(model, ids_alle)
    eta2 = np.zeros(n_alle)
    U2 = 0.0
    sv = np.zeros(n_alle)
    for res in liste:
        gr = _elemente(model, res)
        ids_r = np.concatenate([g[1] for g in gr]) if gr else np.zeros(0, int)
        if len(ids_r) != n_alle or not np.array_equal(np.sort(ids_r), np.sort(ids_alle)):
            # Ein anderes Ergebnis mit anderen Elementen (anderes Netz) -
            # das gehoert nicht in dieselbe Schaetzung
            continue
        # Knotenmittel, volumengewichtet ueber alle Typen: ein grosses Element
        # neben einem kleinen soll den Knotenwert nicht nur nach Stueckzahl
        # bestimmen
        acc = np.zeros((nn, 6))
        gew = np.zeros(nn)
        S_alle = np.zeros((n_alle, 6))
        for typ, ids, K, S in gr:
            idx = np.array([reihenfolge[int(i)] for i in ids], int)
            S_alle[idx] = S
            V = V_alle[idx]
            k = K.shape[1]
            np.add.at(acc, K.ravel(), np.repeat(S * V[:, None], k, axis=0))
            np.add.at(gew, K.ravel(), np.repeat(V, k))
        mit = gew > 0
        stern = np.zeros((nn, 6))
        stern[mit] = acc[mit] / gew[mit][:, None]
        eta2_r = np.zeros(n_alle)
        for typ, ids, K, S in gr:
            idx = np.array([reihenfolge[int(i)] for i in ids], int)
            E = stern[K] - S[:, None, :]                        # (n, k, 6) Fehler je Ecke
            q, _V = _energienorm_quadrat(_LINEAR[typ], model.nodes[K], E, C_alle[idx])
            eta2_r[idx] = q
        eta2 = np.maximum(eta2, eta2_r)
        U2 = max(U2, float(np.sum(V_alle * np.einsum("ni,nij,nj->n", S_alle, C_alle, S_alle))))
        sv = np.maximum(sv, spn.volumen_werte(S_alle, "sv"))
    summe_eta2 = float(eta2.sum())
    eta_rel = np.sqrt(summe_eta2 / (U2 + summe_eta2)) if (U2 + summe_eta2) > 0 else 0.0
    p = np.array([ORDNUNG.get(model.elements[int(i)].typ, 1) for i in ids_alle], int)
    tetp = int(sum(1 for i in ids_alle if model.elements[int(i)].typ in ("tetp2", "tetp3", "tetp4")))
    return {"ids": ids_alle, "eta": np.sqrt(eta2), "h": h_alle, "V": V_alle, "sv": sv,
            "zentren": zentren, "eta_rel": float(eta_rel), "U": float(np.sqrt(U2)),
            "N": int(n_alle), "p": p, "tetp": tetp}


#: Kalibrierung fuer Netze aus Hexaedern und Keilen (Sweep). Gemessen an der
#: gesweepten Platte 0,4 x 0,24 x 0,08 m mit Bohrung unter Zug, zwei adaptive
#: Runden mit Budget 3x und Kalibrierung 1 (21.09.2026): der Sweep legte
#: 1 928 statt der geschaetzten 1 323 Elemente (1,46-fach) und 6 156 statt
#: 4 368 (1,41-fach) - die Lagen folgen der feinsten Feldgroesse ueber die
#: ganze Dicke, das sieht die Summe (h/h_neu)^3 nicht. Darum 1,5; die
#: Nachmessung der Schleife faengt den Rest. Fuer Tetraeder bleibt es bei 5.
KALIBRIERUNG_HEX = 1.5


def kalibrierung_fuer(model, ind: dict) -> float:
    """Die Kalibrierung der Elementzahl-Schaetzung nach dem Elementgemisch
    des Indikators: Tetraeder KALIBRIERUNG, Hexaeder/Keile KALIBRIERUNG_HEX,
    dazwischen anteilig nach der Elementzahl."""
    ids = ind.get("ids")
    if ids is None or not len(ids):
        return KALIBRIERUNG
    n_tet = sum(1 for i in ids if model.elements[int(i)].typ in ("tet4", "tet10"))
    f = n_tet / float(len(ids))
    return float(KALIBRIERUNG * f + KALIBRIERUNG_HEX * (1.0 - f))


def neue_kantenlaengen(ind: dict, ziel: float = ZIEL, faktor_min: float = FAKTOR_MIN,
                       faktor_max: float = FAKTOR_MAX, h_min: float = 0.0,
                       h_max: float = 0.0, wachstum_max: float = WACHSTUM_MAX,
                       kalibrierung: float = KALIBRIERUNG,
                       spannungsschutz: float = SPANNUNGSSCHUTZ) -> np.ndarray:
    """Die neue Kantenlaenge je Element nach Zienkiewicz/Zhu.

    Der zulaessige Gesamtfehler ``ziel`` (bezogen, Energienorm) wird gleich
    auf die N Elemente verteilt; ein Element mit dem xi-fachen davon wird um
    xi^(1/p) feiner, eines mit einem Bruchteil entsprechend groeber. Der
    Schritt ist auf [faktor_min, faktor_max] begrenzt, das Ergebnis auf
    [h_min, h_max] (0 = keine Grenze).

    ``spannungsschutz``: Elemente mit mindestens diesem Anteil der groessten
    Vergleichsspannung werden nicht groeber (siehe SPANNUNGSSCHUTZ).

    Dazu das **Budget**: die geschaetzte neue Elementzahl, ``kalibrierung``
    mal Summe (h/h_neu)^3 (siehe KALIBRIERUNG), darf hoechstens
    ``wachstum_max`` mal N sein. Liegt sie darueber, werden alle neuen
    Kantenlaengen um denselben Faktor angehoben - die Verteilung bleibt
    (fein, wo der Fehler gross ist), nur der Massstab aendert sich.
    """
    eta, h, p = ind["eta"], ind["h"], ind.get("p")
    N = int(ind.get("N", len(eta)))
    if not N:
        return np.zeros(0)
    p = np.asarray(p if p is not None else np.ones(N), float)
    gesamt = np.sqrt(ind["U"] ** 2 + float(np.sum(eta ** 2)))
    e_zul = float(ziel) * gesamt / np.sqrt(N)
    with np.errstate(divide="ignore", invalid="ignore"):
        xi = np.where(eta > 0, eta / max(e_zul, 1e-300), 0.0)
        faktor = np.where(xi > 0, xi ** (-1.0 / p), faktor_max)
    faktor = np.clip(faktor, faktor_min, faktor_max)
    sv = np.asarray(ind.get("sv", np.zeros(N)), float)
    hoch = np.zeros(N, bool)
    if (spannungsschutz and spannungsschutz > 0 and len(sv) == N and sv.max() > 0
            and float(sv.max()) > KONZENTRATION * float(sv.mean())):
        hoch = sv >= float(spannungsschutz) * float(sv.max())
        faktor = np.where(hoch, np.minimum(faktor, 1.0), faktor)

    def begrenzen(hn):
        if h_min and h_min > 0:
            hn = np.maximum(hn, float(h_min))
        if h_max and h_max > 0:
            hn = np.minimum(hn, float(h_max))
        return hn
    h_neu = begrenzen(h * faktor)
    if wachstum_max and wachstum_max > 0:
        kal = float(kalibrierung) if kalibrierung and kalibrierung > 0 else 1.0
        n_neu = kal * float(np.sum((h / np.maximum(h_neu, 1e-300)) ** 3))
        if n_neu > wachstum_max * N:
            s = (n_neu / (wachstum_max * N)) ** (1.0 / 3.0)
            grob = np.minimum(h * faktor * s, h * faktor_max)
            grob = np.where(hoch, np.minimum(grob, h), grob)
            h_neu = begrenzen(grob)
    return h_neu


def _koerper_je_element(model, ids: np.ndarray) -> np.ndarray:
    """Name des Koerpers je Element ("" ohne Koerper)."""
    von: dict = {}
    for k in (getattr(model, "koerper", None) or {}).values():
        for e in (k.elemente or []):
            von[int(e)] = k.name
    return np.array([von.get(int(i), "") for i in ids], dtype=object)


def koerper_kantenlaengen(model, ind: dict, h_neu: np.ndarray, perzentil: float = PERZENTIL_KOERPER,
                          faktor_min: float = FAKTOR_MIN, faktor_max: float = FAKTOR_MAX,
                          h_min: float = 0.0, h_max: float = 0.0) -> dict:
    """Die eigene Kantenlaenge je Koerper fuer den naechsten Durchgang:
    das ``perzentil`` der neuen Kantenlaengen seiner Elemente, begrenzt auf
    [faktor_min, faktor_max] mal seiner bisherigen Kantenlaenge (aus
    netz.koerper_h, sonst aus der Netzdichte). Rueckgabe {Name: h}."""
    from . import netzdichte as nd
    netz = getattr(model, "netz", None)
    namen = _koerper_je_element(model, ind["ids"])
    aus: dict = {}
    for k in (getattr(model, "koerper", None) or {}).values():
        drin = namen == k.name
        if not drin.any():
            continue
        bisher = float((getattr(netz, "koerper_h", None) or {}).get(k.name, 0.0) or 0.0)
        if bisher <= 0:
            try:
                bisher = float(nd.elementlaenge(model, netz, k)["h"])
            except Exception:               # noqa: BLE001
                bisher = float(np.max(ind["h"][drin]))
        wunsch = float(np.percentile(h_neu[drin], perzentil))
        neu = float(np.clip(wunsch, bisher * faktor_min, bisher * faktor_max))
        if h_min and h_min > 0:
            neu = max(neu, float(h_min))
        if h_max and h_max > 0:
            neu = min(neu, float(h_max))
        aus[k.name] = neu
    return aus


def feldpunkte(model, ind: dict, h_neu: np.ndarray, koerper_h: dict = None,
               spielraum: float = 0.9, hoechstens: int = FELDPUNKTE_MAX) -> list:
    """Die Quellen des Groessenfelds fuer den naechsten Durchgang.

    Ein Element wird Quelle, wenn seine neue Kantenlaenge unter
    ``spielraum`` mal der Kantenlaenge seines Koerpers liegt - alles andere
    erledigt die Kantenlaenge des Koerpers. Quelle heisst: Ort = Schwerpunkt,
    h = neue Kantenlaenge, Reichweite = halbe alte Kantenlaenge.

    Vorausgeduennt wird ueber Zellen: je Groessenstufe (Oktave von h) und
    Zelle der doppelten Kantenlaenge bleibt die feinste Quelle. Am Netz mit
    600 000 Elementen blieben sonst Hunderttausende Quellen, die das Feld
    dann Punkt fuer Punkt ausduennen muesste (netzfeld.Groessenfeld
    .abschliessen ist eine Python-Schleife). Rueckgabe [[x, y, z, h, r], ...].
    """
    if not len(h_neu):
        return []
    koerper_h = koerper_h or {}
    namen = _koerper_je_element(model, ind["ids"])
    grenze = np.array([float(koerper_h.get(n, 0.0) or 0.0) for n in namen])
    ohne = grenze <= 0
    if ohne.any():
        # Ohne Koerperkantenlaenge zaehlt die groesste alte Kantenlaenge
        grenze[ohne] = float(np.max(ind["h"])) if len(ind["h"]) else np.inf
    wahl = h_neu < spielraum * grenze
    if not wahl.any():
        return []
    X = ind["zentren"][wahl]
    h = h_neu[wahl]
    r = 0.5 * ind["h"][wahl]
    h_ref = float(h.min())
    faktor = 2.0
    for _ in range(12):
        stufe = np.floor(np.log2(np.maximum(h, 1e-300) / h_ref)).astype(int)
        zelle = h_ref * (2.0 ** stufe) * faktor
        ix = np.floor(X / zelle[:, None]).astype(np.int64)
        schl = np.column_stack([stufe, ix])
        ordnung = np.argsort(h, kind="stable")
        _, erste = np.unique(schl[ordnung], axis=0, return_index=True)
        wahl2 = ordnung[erste]
        if len(wahl2) <= hoechstens:
            break
        faktor *= 2.0
    X, h, r = X[wahl2], h[wahl2], r[wahl2]
    return [[float(a), float(b), float(c), float(d), float(e)]
            for (a, b, c), d, e in zip(X, h, r)]


def bericht(ind: dict) -> list:
    """Der Indikator als Zeilen fuers Protokoll."""
    if not ind.get("N"):
        return ["Fehlerschätzer: kein Tetraeder mit Ergebnis"]
    eta = ind["eta"]
    z = [f"Fehlerschätzer: {ind['N']} Tetraeder, bezogener Fehler {ind['eta_rel'] * 100:.1f} % "
         f"der Energienorm (Ziel {ZIEL * 100:.0f} %)"]
    if len(eta):
        anteil = float(np.sum(np.sort(eta ** 2)[::-1][:max(1, len(eta) // 10)]) / max(np.sum(eta ** 2), 1e-300))
        z.append(f"  das Zehntel der Elemente mit dem größten Fehler trägt {anteil * 100:.0f} % des "
                 f"Gesamtfehlers; Kantenlängen {np.min(ind['h']) * 1e3:.1f} … {np.max(ind['h']) * 1e3:.1f} mm")
    if ind.get("tetp"):
        z.append(f"  Tetraeder mit Ordnung p ({ind['tetp']}): der Schätzer behandelt sie vorerst "
                 "wie tet4 – die höhere Ordnung ist nicht berücksichtigt.")
    return z
