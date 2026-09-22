"""
Spannungsnachweis fuer Volumenbereiche nach DIN EN 1993-1-1, 6.2.1(5),
mit den Hinweisen auf die Zaehigkeitsanforderungen nach DIN EN 1993-1-10.

Ein Volumen hat keinen Querschnitt: Klassifizierung, W_pl, Knicklaengen und
die Interaktionsformeln des Abschnitts 6 gehen darum nicht.  Was geht, ist
der **Spannungsnachweis am Punkt**, und den verlangt 6.2.1(5) ausdruecklich
als konservative Alternative:

    sigma_v,Ed = sqrt( sigma_x^2 + sigma_z^2 - sigma_x sigma_z + 3 tau^2 )
               <= f_y / gamma_M0

fuer den allgemeinen dreiachsigen Spannungszustand also die
Vergleichsspannung nach von Mises

    sigma_v = sqrt( 1/2 [ (s1-s2)^2 + (s2-s3)^2 + (s3-s1)^2 ] )

mit den Hauptspannungen s1 >= s2 >= s3.

Zusaetzlich ausgewiesen und beurteilt:

  * die **Hauptspannungen** und die groesste Schubspannung
    tau_max = (s1 - s3)/2 (Tresca als Vergleich),
  * die **Mehrachsigkeit** h = sigma_m / sigma_v mit
    sigma_m = (s1+s2+s3)/3.  Bei dreiachsigem Zug (s3 > 0) wird die
    Verformungsfaehigkeit stark eingeschraenkt; DIN EN 1993-1-10 verlangt
    dann eine Betrachtung der Stahlsorte und der Zaehigkeit.  Das Programm
    rechnet das nicht, sagt es aber deutlich.

**Spannungssingularitaeten**: An einspringenden Ecken, unter Einzellasten und
an Punktlagern waechst die Spannung mit jeder Netzverfeinerung; ein Nachweis
gegen f_y ist dort sinnlos.  Ein Volumenbereich kann darum als ``singular``
gekennzeichnet werden - dann werden die Spannungen berichtet, aber nicht als
Nachweis gefuehrt.  Unabhaengig davon prueft das Programm, wie stark die
Spitzenspannung ueber dem Mittel des Bereichs liegt, und weist auf eine
moegliche Singularitaet hin.

**Nicht enthalten**: Stabilitaet des Volumenkoerpers (die geometrische
Steifigkeit ist nur fuer Stabelemente gebildet), Plastizieren, Kriechen und
der Sproedbruchnachweis nach EN 1993-1-10 selbst. Die Ermuedung der Volumen
(Hauptspannung im Element) steht in ec3/fatigue.py.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

#: Ab welchem Verhaeltnis Spitzenspannung / Mittelwert im Bereich auf eine
#: moegliche Singularitaet hingewiesen wird
SPITZE_GRENZE = 5.0

#: Anteil von sigma_v, ab dem sigma_3 als echter Zug gilt (Rechenrauschen)
ZUG_SCHWELLE = 0.02


def hauptspannungen(s) -> np.ndarray:
    """Hauptspannungen s1 >= s2 >= s3 aus [sx, sy, sz, txy, tyz, tzx]."""
    sx, sy, sz, txy, tyz, tzx = (float(x) for x in s)
    T = np.array([[sx, txy, tzx], [txy, sy, tyz], [tzx, tyz, sz]])
    return np.sort(np.linalg.eigvalsh(T))[::-1]


def hauptrichtungen(s):
    """(Hauptspannungen, Richtungen als Spalten) - absteigend geordnet."""
    sx, sy, sz, txy, tyz, tzx = (float(x) for x in s)
    T = np.array([[sx, txy, tzx], [txy, sy, tyz], [tzx, tyz, sz]])
    w, v = np.linalg.eigh(T)
    o = np.argsort(w)[::-1]
    return w[o], v[:, o]


def vergleichsspannung(s) -> float:
    """von Mises aus dem Spannungsvektor [sx, sy, sz, txy, tyz, tzx]."""
    sx, sy, sz, txy, tyz, tzx = (float(x) for x in s)
    return math.sqrt(0.5 * ((sx - sy) ** 2 + (sy - sz) ** 2 + (sz - sx) ** 2)
                     + 3.0 * (txy ** 2 + tyz ** 2 + tzx ** 2))


def mehrachsigkeit(s1: float, s2: float, s3: float, sv: float) -> dict:
    """
    Mehrachsigkeit h = sigma_m/sigma_v und die Beurteilung.

    sigma_m ist die hydrostatische Spannung (s1+s2+s3)/3.  Bei h > 1/3 und
    dreiachsigem Zug ist die Verformungsfaehigkeit deutlich eingeschraenkt.

    "Dreiachsiger Zug" wird nur gemeldet, wenn die kleinste Hauptspannung
    wirklich Zug ist und nicht bloss Rechenrauschen: sie muss ueber
    ``ZUG_SCHWELLE`` der Vergleichsspannung und ueber 1 N/mm^2 liegen.
    Sonst meldete jeder einachsige Zugstab, dessen sigma_3 rechnerisch bei
    1e-14 N/mm^2 landet, einen dreiachsigen Zugzustand.
    """
    sm = (s1 + s2 + s3) / 3.0
    h = sm / sv if sv > 1e-9 else 0.0
    zug3 = s3 > max(ZUG_SCHWELLE * sv, 1e6)
    return {"sigma_m": sm, "h": h, "dreiachsiger_zug": bool(zug3),
            "kritisch": bool(zug3 and h > 1.0 / 3.0)}


def punkt_nachweis(s, fy: float, gamma_M0: float = 1.0) -> dict:
    """Spannungsnachweis an einem Punkt: alle Werte auf einen Blick."""
    s1, s2, s3 = hauptspannungen(s)
    sv = vergleichsspannung(s)
    fyd = fy / gamma_M0
    d = {"sigma": [float(x) for x in s], "s1": float(s1), "s2": float(s2),
         "s3": float(s3), "sigma_v": sv, "tau_max": float((s1 - s3) / 2.0),
         "f_yd": fyd, "eta": sv / fyd if fyd > 0 else 0.0,
         "eta_tresca": (float(s1 - s3) / fyd) if fyd > 0 else 0.0}
    d.update(mehrachsigkeit(s1, s2, s3, sv))
    return d


# ==========================================================================
@dataclass
class VolumenCheck:
    """Nachweis eines Volumenbereichs ueber alle GZT-Kombinationen."""
    name: str
    beschreibung: str = ""
    n_elemente: int = 0
    material: str = ""
    fy: float = 0.0
    util: float = 0.0
    kombination: str = ""
    element: int = -1
    werte: dict = field(default_factory=dict)
    je_kombination: list = field(default_factory=list)
    singular: bool = False
    hinweise: list = field(default_factory=list)
    fehler: str = ""

    def status(self) -> str:
        if self.fehler:
            return "nicht geführt"
        if self.singular:
            return "nur berichtet"
        return "erfüllt" if self.util <= 1.0 else "NICHT erfüllt"


@dataclass
class VolumenResults:
    bereiche: dict = field(default_factory=dict)
    kombinationen: list = field(default_factory=list)
    settings: dict = field(default_factory=dict)
    #: Kombinationen ohne Ergebnis ("nicht nachgewiesen"), siehe
    #: design._uls_results
    warnungen: list = field(default_factory=list)

    @property
    def util_max(self) -> float:
        return max((c.util for c in self.bereiche.values()
                    if not c.singular), default=0.0)

    def summary(self) -> str:
        from .design import warnzeilen
        return self._summary() + warnzeilen(self)

    def _summary(self) -> str:
        if not self.bereiche:
            return "Volumennachweise: keine Bereiche festgelegt"
        gefuehrt = [c for c in self.bereiche.values() if not c.singular and not c.fehler]
        schlecht = [c.name for c in gefuehrt if c.util > 1.0]
        fehler = [c.name for c in self.bereiche.values() if c.fehler]
        nur = [c.name for c in self.bereiche.values() if c.singular]
        s = f"Volumen (EN 1993-1-1, 6.2.1(5)): {len(self.bereiche)} Bereiche"
        if gefuehrt:
            worst = max(gefuehrt, key=lambda c: c.util)
            s += (f", max. Ausnutzung {worst.util:.3f} ({worst.name}: "
                  f"σ_v = {worst.werte.get('sigma_v', 0) / 1e6:.1f} von "
                  f"{worst.werte.get('f_yd', 0) / 1e6:.1f} N/mm²"
                  + (f", {worst.kombination}" if worst.kombination else "") + ")")
        if schlecht:
            s += f" - {len(schlecht)} NICHT erfüllt: " + ", ".join(schlecht)
        elif gefuehrt and not fehler:
            s += " - alle erfüllt"
        if nur:
            s += f" - {len(nur)} nur berichtet (Singularität): " + ", ".join(nur)
        if fehler:
            s += f" - {len(fehler)} nicht geführt: " + ", ".join(fehler)
        return s

    def table(self) -> list[list]:
        rows = [["Bereich", "Elemente", "Material", "f_y [MPa]", "σ_v [MPa]",
                 "σ_1 [MPa]", "σ_3 [MPa]", "Ausnutzung", "Kombination", "Status"]]
        for c in self.bereiche.values():
            w = c.werte or {}
            rows.append([c.name, str(c.n_elemente), c.material,
                         f"{c.fy / 1e6:.0f}",
                         f"{w.get('sigma_v', 0) / 1e6:.1f}",
                         f"{w.get('s1', 0) / 1e6:.1f}",
                         f"{w.get('s3', 0) / 1e6:.1f}",
                         f"{c.util:.3f}", c.kombination, c.status()])
        return rows


# --------------------------------------------------------------------------
def _elementspannungen(model, res, elemente) -> list:
    """
    Groesste Spannung je Element, ausgewertet an Mitte **und** Eckpunkten.

    Die Elementmitte allein reicht nicht: bei Biegung durch den Koerper liegt
    die Randspannung deutlich hoeher (am Kragarm aus Hexaedern 43,3 gegen
    60,3 N/mm^2, die Balkenloesung M/W ist 60,0). Rueckgabe je Element ein
    Tripel (Elementnummer, Spannungsvektor, Auswertepunkt).
    """
    from ..elements import solid as sl
    u = np.asarray(getattr(res, "u", None))
    if u is None or u.size == 0:
        return []
    u = u.ravel()
    out = []
    for i in elemente:
        e = model.elements[i]
        mat = model.materials.get(e.mat)
        if mat is None:
            continue
        X = np.asarray(model.nodes[e.nodes], float)
        try:
            ue = np.concatenate([u[int(n) * 6:int(n) * 6 + 3] for n in e.nodes])
            sp = sl.stress_points(e.typ, X, mat.E, mat.nu, ue)
        except Exception:
            sp = []
        roh = getattr(res, "solid_res", {}).get(i)
        if not sp:
            if roh is None:
                continue
            out.append((i, np.asarray(roh, float), "Mitte"))
            continue
        k = int(np.argmax([vergleichsspannung(x) for x in sp]))
        name = "Mitte" if k == 0 else f"Eckpunkt {k}"
        if roh is not None:
            # ``res.solid_res`` traegt seit dem 20.09.2026 schon den
            # **massgebenden** Auswertepunkt (solver._post_chunk), und zwar
            # mit allem, was sigma = D B u hier weglassen wuerde: der
            # plastischen Vorspannung D eps_p und - mit
            # Model.knotendilatation - dem gemittelten volumetrischen Anteil.
            # Gemessen am Stauchwuerfel (384 tet4, S355, p = 420 MPa,
            # Fliessen an, 20.09.2026): sigma_v,max 381,2 MPa im Ergebnis
            # gegen 3300,7 MPa neu gerechnet - Ausnutzung 1,07 gegen 9,3.
            # Die Nachrechnung hier benennt nur noch die **Stelle**.
            out.append((i, np.asarray(roh, float), name))
            continue
        out.append((i, np.asarray(sp[k], float), name))
    return out


def _koerper(model):
    """Zuordnung Volumenelement -> zusammenhaengender Koerper.

    Zwei Volumenelemente gehoeren zum selben Koerper, wenn sie einen Knoten
    teilen - ueber Nachbarn auch mittelbar. Gerechnet wird das als
    Zusammenhangskomponente des zweiteiligen Graphen Element/Knoten
    (``scipy.sparse.csgraph``) und nicht mit einer eigenen Schleife: bei den
    288 Elementen einer Pruefung ist die Art der Rechnung gleich, bei den
    645 934 Volumenelementen des Drehlagers nicht.

    Rueckgabe: ``(marke, gruppen)`` - Element -> Koerpernummer und
    Koerpernummer -> Elementliste.
    """
    import numpy as _np
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    from ..elemente import VOLUMEN_TYPEN
    idx, zeilen, spalten = [], [], []
    for i, e in enumerate(model.elements):
        if e.typ not in VOLUMEN_TYPEN:
            continue
        r = len(idx)
        idx.append(i)
        for k in e.nodes:
            zeilen.append(r)
            spalten.append(int(k))
    m = len(idx)
    if not m:
        return {}, {}
    n = m + int(model.nn)
    G = coo_matrix((_np.ones(len(zeilen)),
                    (_np.asarray(zeilen, int), m + _np.asarray(spalten, int))),
                   shape=(n, n))
    _anz, lab = connected_components(G, directed=False)
    marke, gruppen = {}, {}
    for r, i in enumerate(idx):
        g = int(lab[r])
        marke[i] = g
        gruppen.setdefault(g, []).append(i)
    return marke, gruppen


def _erzeugnisdicke(model, elemente, koerper=None) -> float:
    """Die Erzeugnisdicke eines Volumenbereichs [m] - die **kleinste**
    Abmessung des umschliessenden Quaders des **ganzen Koerpers**, zu dem
    seine Elemente gehoeren.

    EN 1993-1-1 Tab. 3.1 mindert die Streckgrenze mit der Erzeugnisdicke ab
    (S355: 355 N/mm2 bis 40 mm, darueber 335). Ein Volumenbereich hat keine
    Dicke im Sinne eines Querschnitts; er ist aus einem Erzeugnis gefertigt,
    und dessen Dicke ist die kleinste Abmessung: bei einer Platte ihre Dicke,
    bei einem Rundstahl sein Durchmesser, bei einem Block seine kuerzeste
    Kante.

    **Warum der ganze Koerper und nicht die Auswahl?** Weil die Auswahl dem
    Anwender gehoert. An einem Block 300 x 300 x 200 mm, vernetzt mit
    6 x 6 x 8 Elementen, misst der ganze Koerper 200 mm (f_y = 335), eine
    einzelne Elementlage aber 25 mm (f_y = 355): dieselbe Stelle, 6,0 % auf
    der **unsicheren** Seite, nur weil weniger markiert war. Der Koerper ist
    dagegen unabhaengig davon, was der Anwender gerade ausgewaehlt hat.

    Bei einem **geschweissten** Bauteil ist der Koerper umgekehrt zu dick -
    massgebend ist dort die Blechdicke. Darum ist die Dicke am Volumenbereich
    angebbar (``Volumenbereich.dicke``), die selbst gesetzte steht im Nachweis
    (``werte["dicke"]``), und wenn sie die Streckgrenze abmindert, sagt es der
    Bericht als Hinweis.

    Bis zum 22.09.2026 wurde mit ``yield_strength(0.0)`` gerechnet, also
    **immer mit der duennsten Stufe**: ein Lagerblock von 80 mm wies sich mit
    355 statt 335 N/mm2 nach, eta fiel rund 6 % zu klein aus - auf der
    unsicheren Seite. Der Stabnachweis macht es seit jeher richtig
    (``design.py``: ``mat.yield_strength(sec.t_max)``).
    """
    import numpy as _np
    marke, gruppen = koerper if koerper is not None else _koerper(model)
    kn = set()
    for i in elemente:
        i = int(i)
        if not 0 <= i < len(model.elements):
            continue
        for j in gruppen.get(marke.get(i, -1), (i,)):
            kn.update(int(x) for x in model.elements[j].nodes)
    if not kn:
        return 0.0
    X = _np.asarray(model.nodes, float)[sorted(kn)]
    d = X.max(axis=0) - X.min(axis=0)
    return float(d.min())


def _material(model, elemente, dicke: float = 0.0):
    """(Materialname, f_y) des Bereichs; f_y der schwaechste im Bereich.

    ``dicke`` ist die Erzeugnisdicke [m] fuer die Abminderung nach
    EN 1993-1-1 Tab. 3.1 - siehe :func:`_erzeugnisdicke`.
    """
    namen, fy = [], []
    for i in elemente:
        e = model.elements[i]
        mat = model.materials.get(e.mat)
        if mat is None:
            continue
        if e.mat not in namen:
            namen.append(e.mat)
        f = mat.yield_strength(dicke) or 0.0
        if f > 0:
            fy.append(f)
    return "/".join(namen), (min(fy) if fy else 0.0)


def check_volumen(model, analysis, combos: list = None, progress=None) -> VolumenResults:
    """Alle Volumenbereiche des Modells ueber alle GZT-Kombinationen nachweisen."""
    from .design import _uls_results
    warnungen: list = []
    ergebnisse = _uls_results(model, analysis, combos, warnungen=warnungen)
    ds = model.design
    out = VolumenResults(kombinationen=list(ergebnisse), settings={
        "gamma_M0": ds.gamma_M0,
        "Norm": "DIN EN 1993-1-1, 6.2.1(5) (Vergleichsspannung nach von Mises)"},
        warnungen=warnungen)
    koerper = _koerper(model)
    for i, (name, vb) in enumerate(model.volumenbereiche.items()):
        c = VolumenCheck(name, beschreibung=vb.beschreibung,
                         n_elemente=len(vb.elemente), singular=bool(vb.singular))
        if not vb.design:
            c.fehler = "Nachweis für diesen Bereich ausgeschaltet"
            out.bereiche[name] = c
            continue
        # Die Erzeugnisdicke: entweder am Bereich angegeben oder aus dem
        # zusammenhaengenden Koerper bestimmt (siehe _erzeugnisdicke). Sie
        # geht in die Abminderung nach EN 1993-1-1 Tab. 3.1 und steht weiter
        # unten im Nachweis - **nicht hier**: c.werte wird in der Schleife
        # ueber die Kombinationen durch das Ergebnis der massgebenden
        # Kombination ersetzt, was hier hineingeschrieben wird, ist weg.
        gesetzt = float(getattr(vb, "dicke", 0.0) or 0.0) > 0
        t_erz = (float(vb.dicke) if gesetzt
                 else _erzeugnisdicke(model, vb.elemente, koerper))
        c.material, c.fy = _material(model, vb.elemente, t_erz)
        _mat0, fy_duenn = _material(model, vb.elemente, 0.0)
        if c.fy <= 0:
            c.fehler = ("kein Material mit Streckgrenze im Bereich - "
                        "der Nachweis braucht f_y")
            out.bereiche[name] = c
            continue
        for kname, res in ergebnisse.items():
            werte = _elementspannungen(model, res, vb.elemente)
            if not werte:
                continue
            svs = np.array([vergleichsspannung(sp) for _e, sp, _pt in werte])
            j = int(np.argmax(svs))
            el, sp, punkt = werte[j]
            d = punkt_nachweis(sp, c.fy, ds.gamma_M0)
            d["sigma_v_mittel"] = float(svs.mean())
            d["spitze"] = float(svs[j] / svs.mean()) if svs.mean() > 0 else 1.0
            d["punkt"] = punkt
            c.je_kombination.append({"kombination": kname, "element": el,
                                     "sigma_v": d["sigma_v"], "eta": d["eta"],
                                     "s1": d["s1"], "s3": d["s3"]})
            if d["eta"] >= c.util:
                c.util, c.kombination, c.element, c.werte = (
                    d["eta"], kname, el, d)
        if not c.je_kombination:
            c.fehler = ("keine Volumenspannungen in den Ergebnissen - "
                        "wurde mit Volumenelementen gerechnet?" if ergebnisse else
                        "kein Ergebnis einer GZT-Kombination - siehe Warnung")
            out.bereiche[name] = c
            continue
        w = c.werte
        w["dicke"] = t_erz
        w["dicke_gesetzt"] = gesetzt
        if not gesetzt and c.fy < fy_duenn:
            c.hinweise.append(
                f"Erzeugnisdicke {t_erz * 1e3:.0f} mm angesetzt - die kleinste "
                "Abmessung des Körpers, zu dem die Elemente gehören. Die "
                f"Streckgrenze ist damit nach EN 1993-1-1 Tab. 3.1 auf "
                f"{c.fy / 1e6:.0f} N/mm² abgemindert (dünnste Stufe: "
                f"{fy_duenn / 1e6:.0f}). Ist das Bauteil aus Blechen "
                "geschweißt, ist die Blechdicke maßgebend und nicht die "
                "Abmessung des Körpers - dann die Erzeugnisdicke am "
                "Volumenbereich angeben.")
        if w.get("dreiachsiger_zug"):
            c.hinweise.append(
                f"Dreiachsiger Zug (σ_3 = {w['s3'] / 1e6:.1f} N/mm² > 0) bei einer "
                f"Mehrachsigkeit h = σ_m/σ_v = {w['h']:.2f}. Die "
                "Verformungsfähigkeit ist dort eingeschränkt; die Zähigkeit des "
                "Stahls ist nach DIN EN 1993-1-10 zu beurteilen (Stahlsorte, "
                "Erzeugnisdicke, tiefste Bauteiltemperatur). Dieser Nachweis wird "
                "hier nicht geführt.")
        if w.get("spitze", 1.0) > SPITZE_GRENZE and not c.singular:
            c.hinweise.append(
                f"Die Spitzenspannung liegt um den Faktor {w['spitze']:.1f} über "
                "dem Mittel des Bereichs. Das deutet auf eine Spannungs-"
                "singularität hin (einspringende Ecke, Einzellast, Punktlager). "
                "Dort wächst die Spannung mit jeder Netzverfeinerung; der "
                "Nachweis gegen f_y ist dann nicht aussagekräftig. Entweder die "
                "Ausrundung modellieren oder den Bereich als „singulär“ "
                "kennzeichnen und gesondert beurteilen.")
        if vb.ausrundung > 0:
            V = _bereichsvolumen(model, vb.elemente)
            h = (V / max(len(vb.elemente), 1)) ** (1 / 3)
            c.werte["elementgroesse"] = h
            c.werte["ausrundung"] = vb.ausrundung
            if h > vb.ausrundung / 3.0:
                c.hinweise.append(
                    f"Mittlere Elementgröße {h * 1e3:.1f} mm gegen Kerbradius "
                    f"{vb.ausrundung * 1e3:.1f} mm: für die Kerbspannung sollten "
                    "mindestens drei Elemente über den Radius liegen "
                    f"(h ≤ {vb.ausrundung / 3 * 1e3:.1f} mm). Das Netz ist dort "
                    "zu grob, die Spitzenspannung wird unterschätzt.")
        if c.singular:
            c.hinweise.append(
                "Der Bereich ist als singulär gekennzeichnet: die Spannungen "
                "werden berichtet, aber nicht als Nachweis geführt.")
        out.bereiche[name] = c
        if progress:
            progress(f"Volumenbereich {name} ({i + 1}/{len(model.volumenbereiche)})")
    return out


def _bereichsvolumen(model, elemente) -> float:
    """Summe der Elementvolumina [m^3]."""
    from ..elements import solid as sl
    V = 0.0
    for i in elemente:
        e = model.elements[i]
        X = np.asarray(model.nodes[e.nodes], float)
        try:
            if e.typ == "tet4":
                _dN, v = sl.tet4_shape_grad(X)
                V += abs(v)
            else:
                # Naeherung ueber die Bounding-Box des Elements
                d = X.max(axis=0) - X.min(axis=0)
                V += float(np.prod(d)) * (1.0 / 6.0 if e.typ == "tet10" else 1.0)
        except Exception:
            continue
    return V
