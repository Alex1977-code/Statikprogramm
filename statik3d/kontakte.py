"""Beruehrungen zwischen Volumenkoerpern - und die Kontakte, die daraus entstehen.

Wunsch vom 15.09.2026: „gut wäre, wenn du automatisch Kontakte anlegst, wenn
zwei Volumen sich berühren; Standard ist Druck und Zug und Schub starr" - und
im Namen soll stehen, was der Kontakt tut (starr, nur Druck, Druck/Schub …),
dazu eine Farbe je Wirkung, „das sieht man immer sehr schnell".

Gemessen am Drehlager (108 Koerper, 1375 Flaechen, 15.09.2026): 217
Koerperpaare beruehren sich, 25 davon ueber eine **gemeinsame** Flaeche
(dieselbe Flaeche in beiden Koerpern - der Vernetzer teilt dort die Knoten,
in RFEM „durchverbunden"), die uebrigen ueber je eigene, aufeinanderliegende
Flaechen; 23 Paare hatten keine Kontaktbedingung, alle 23 ueber gemeinsame
Flaechen. Aufliegende Flaechenpaare liegen unter 1 µm auseinander, das
naechste getrennte Paar bei 0,1 mm (Passstift im Loch, mit eigener
Kontaktbedingung) - die Toleranz 1e-5 der Modellgroesse (55 µm) liegt
dazwischen. Angrenzende Flaechen desselben Randes (nur eine Kante gemeinsam)
trafen mit Eck- und Kantenproben bis zu 25 % der Proben, aufliegende ueber
50 %; darum zaehlen hier nur **innere** Proben der Dreiecke (Schwerpunkt und
drei Punkte dazwischen), gewichtet mit der Dreiecksflaeche.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

#: Toleranz der Beruehrung, bezogen auf die Modellgroesse (characteristic_size)
BERUEHRUNG_RELATIV = 1e-5
#: … und absolut nie kleiner als das [m]
BERUEHRUNG_MIN = 1e-6
#: Flaechenanteil der inneren Proben, der auf der anderen Flaeche liegen muss
ANTEIL_AUFLIEGEND = 0.25
#: naechste Dreiecke je Probe (die Suche laeuft ueber die Schwerpunkte)
NACHBARN = 6

#: Farbe je Wirkung - dieselbe im Modellbaum und im Bild („Kontakte zeigen")
WIRKUNGSFARBEN = {"starr": "#7f8c8d", "nur Druck": "#e74c3c", "Druck, Reibung": "#f39c12",
                  "Druck/Schub": "#27ae60", "Zug/Druck": "#2980b9",
                  "Zug/Druck, Reibung": "#16a085", "Feder": "#8e44ad"}


@dataclass
class Beruehrung:
    """Zwei Koerper, die sich beruehren: ``a`` ist der kleinere (er wird an der
    Fuge geloest), ``gemeinsam`` die Flaechen, die beiden gehoeren, ``flaechen_a``
    und ``flaechen_b`` die je eigenen Flaechen, die aufeinanderliegen."""
    a: str
    b: str
    gemeinsam: list = field(default_factory=list)
    flaechen_a: list = field(default_factory=list)
    flaechen_b: list = field(default_factory=list)

    def flaechen(self) -> list:
        return list(self.gemeinsam) + list(self.flaechen_a) + list(self.flaechen_b)


@dataclass
class _Flaechendaten:
    P: np.ndarray
    T: np.ndarray
    proben: np.ndarray
    gewicht: np.ndarray
    lo: np.ndarray
    hi: np.ndarray
    mitten: np.ndarray


@dataclass
class _Koerperdaten:
    """Alle Flaechen eines Koerpers in einem Stueck: Dreiecke mit ihrer
    Flaechennummer, Proben mit Flaechennummer und Gewicht, ein Suchbaum ueber
    die Dreiecksschwerpunkte - einmal je Koerper, nicht je Paar."""
    flaechen: list
    P: np.ndarray
    T: np.ndarray
    tri_flaeche: np.ndarray
    proben: np.ndarray
    gewicht: np.ndarray
    probe_flaeche: np.ndarray
    gesamt: np.ndarray                 # Probengewicht je Flaeche
    lo: np.ndarray
    hi: np.ndarray
    mitten: np.ndarray
    baum: object = None


# --------------------------------------------------------------------------
# Wirkung in Worten und Farbe
# --------------------------------------------------------------------------
def ist_naht(kb) -> bool:
    """Starr in allen drei Richtungen: eine Schweissnaht, keine Fuge.

    So eine Bedingung trennt nichts - bei Knoten fuer Knoten passenden
    Netzen bleiben die Knoten gemeinsam (fugen.kontaktfuge_ausfuehren), und
    fuer die Nachbarschaft der Bauteile (fugen.verschweisste_gruppe,
    Kerbfall der Naht) zaehlt sie wie keine Bedingung.
    """
    return all(kb.dof_behaviour(d).typ == "rigid" for d in (0, 1, 2))


def ist_verschweisst(model, kb) -> bool:
    """Starr **an gemeinsamen Flaechen**: die Bedingung ist eine Schweissnaht
    und braucht keine Ausfuehrung - die Knoten sind schon gemeinsam.

    Gemeinsam heisst: jede Kontaktflaeche gehoert mindestens zwei Koerpern
    (und keine Gegenflaechen sind genannt). Ein starrer Kontakt zwischen je
    eigenen, aufeinanderliegenden Flaechen ist dagegen keine Naht im Netz: er
    braucht das Kontaktpaar, das die beiden Seiten bindet.
    """
    if not ist_naht(kb):
        return False
    flaechen = list(getattr(kb, "flaechennamen", None) or [])
    if not flaechen or getattr(kb, "gegenflaechen", None):
        return False
    besitzer: dict = {}
    for k in (getattr(model, "koerper", {}) or {}).values():
        for fn in (k.flaechen or []):
            besitzer[fn] = besitzer.get(fn, 0) + 1
    return all(besitzer.get(fn, 0) >= 2 for fn in flaechen)


def wirkungstext(kb) -> str:
    """Was der Kontakt tut, in zwei Worten - fuer den Namen und die Farbe.

    Druck traegt jede Fuge; genannt wird, was darueber hinaus gilt: „starr"
    (Zug und Schub uebertragen, wie verschweisst), „nur Druck" (hebt ab,
    gleitet frei), „Druck, Reibung", „Druck/Schub" (hebt ab, haftet),
    „Zug/Druck" (kein Abheben, gleitet), „Feder".
    """
    n, x, y = kb.dof_behaviour(2), kb.dof_behaviour(0), kb.dof_behaviour(1)
    if any(b.typ == "spring" for b in (n, x, y)):
        return "Feder"
    zug = n.typ == "rigid"
    schub = x.typ == "rigid" and y.typ == "rigid"
    reibung = kb.reibbeiwert() > 0
    if zug and schub:
        return "starr"
    if zug:
        return "Zug/Druck, Reibung" if reibung else "Zug/Druck"
    if schub:
        return "Druck/Schub"
    return "Druck, Reibung" if reibung else "nur Druck"


def wirkungsfarbe(kb) -> str:
    return WIRKUNGSFARBEN.get(wirkungstext(kb), WIRKUNGSFARBEN["nur Druck"])


def paar_von(kb):
    """(Koerper A, Koerper B) einer Bedingung - oder None, wenn einer fehlt."""
    a = list(getattr(kb, "koerpernamen", None) or [])
    b = list(getattr(kb, "gegenkoerper", None) or [])
    if not a or not b:
        return None
    return str(a[0]), str(b[0])


def name_fuer(model, kb, ausser: str = None) -> str:
    """Der Name eines automatischen Kontakts: „A–B Wirkung", eindeutig.

    Der Name traegt die Wirkung, damit man sie im Modellbaum sofort sieht;
    er wird nachgefuehrt, wenn die Wirkung sich aendert - solange der
    Anwender ihn nicht selbst gesetzt hat.
    """
    p = paar_von(kb)
    basis = f"{p[0]}–{p[1]} {wirkungstext(kb)}" if p else str(kb.name)
    vorhanden = set(getattr(model, "kontaktbedingungen", {}) or {}) - {ausser}
    if basis not in vorhanden:
        return basis
    k = 2
    while f"{basis} ({k})" in vorhanden:
        k += 1
    return f"{basis} ({k})"


# --------------------------------------------------------------------------
# Beruehrungen finden
# --------------------------------------------------------------------------
def toleranz(model) -> float:
    """Bis zu diesem Abstand liegen zwei Flaechen aufeinander."""
    try:
        gr = float(model.characteristic_size())
    except Exception:                        # noqa: BLE001 - leeres Modell
        gr = 0.0
    return max(BERUEHRUNG_MIN, BERUEHRUNG_RELATIV * gr)


def _flaechendaten(model, namen, raender=None, seiten=None, loecher=None) -> dict:
    """Je Flaeche: Dreiecke (dieselbe Zerlegung wie im Bild), innere Proben
    mit Flaechengewicht, umschliessender Quader."""
    from .gui.viewport import flaechenpolygone   # erst hier: zieht pyvista nach
    daten: dict = {}
    for name in namen:
        f = model.flaechen.get(name)
        if f is None:
            continue
        try:
            polys = flaechenpolygone(model, f, raender, seiten, loecher)
        except Exception:                    # noqa: BLE001 - eine kaputte Flaeche beruehrt nichts
            polys = []
        P: list = []
        T: list = []
        for Q in polys:
            Q = np.asarray(Q, float)
            if len(Q) < 3:
                continue
            b = len(P)
            P.extend(Q.tolist())
            T.extend([b, b + j, b + j + 1] for j in range(1, len(Q) - 1))
        if not T:
            continue
        P_ = np.asarray(P, float)
        T_ = np.asarray(T, int)
        A, B, C = P_[T_[:, 0]], P_[T_[:, 1]], P_[T_[:, 2]]
        fl = 0.5 * np.linalg.norm(np.cross(B - A, C - A), axis=1)
        ok = fl > 0
        if not ok.any():
            continue
        T_, A, B, C, fl = T_[ok], A[ok], B[ok], C[ok], fl[ok]
        mitten = (A + B + C) / 3.0
        proben = np.vstack([mitten, (4 * A + B + C) / 6.0, (A + 4 * B + C) / 6.0, (A + B + 4 * C) / 6.0])
        daten[name] = _Flaechendaten(P_, T_, proben, np.tile(fl / 4.0, 4),
                                     P_.min(axis=0), P_.max(axis=0), mitten)
    return daten


def _koerperdaten(k, daten: dict):
    """Die Flaechen eines Koerpers zu einem Stueck zusammenfassen - None,
    wenn keine seiner Flaechen Dreiecke hat."""
    flaechen = [fn for fn in (k.flaechen or []) if fn in daten]
    if not flaechen:
        return None
    P, T, tf, pr, gw, pf = [], [], [], [], [], []
    basis = 0
    for i, fn in enumerate(flaechen):
        d = daten[fn]
        P.append(d.P)
        T.append(d.T + basis)
        tf.append(np.full(len(d.T), i))
        pr.append(d.proben)
        gw.append(d.gewicht)
        pf.append(np.full(len(d.proben), i))
        basis += len(d.P)
    P_ = np.vstack(P)
    T_ = np.vstack(T)
    gw_ = np.concatenate(gw)
    pf_ = np.concatenate(pf)
    return _Koerperdaten(flaechen, P_, T_, np.concatenate(tf), np.vstack(pr), gw_, pf_,
                         np.bincount(pf_, weights=gw_, minlength=len(flaechen)),
                         P_.min(axis=0), P_.max(axis=0), P_[T_].mean(axis=1))


def _auflage(ka: _Koerperdaten, kb: _Koerperdaten, tol: float, tabu_a, tabu_b) -> tuple:
    """Welche Flaechen von ``ka`` liegen auf ``kb`` - und welche Flaechen von
    ``kb`` treffen sie dabei?

    Geprueft werden nur die Proben von ``ka`` im Quader von ``kb``; der
    Abstand ist der exakte zu den naechsten Dreiecken (Suchbaum ueber die
    Schwerpunkte). Eine Flaeche liegt auf, wenn mindestens ANTEIL_AUFLIEGEND
    ihres Probengewichts naeher als ``tol`` liegt; ``tabu`` sind die
    gemeinsamen Flaechen beider Koerper (sie treffen sich trivial).
    Rueckgabe (Flaechennummern von ka, Flaechennummern von kb).
    """
    from scipy.spatial import cKDTree
    from .mesher3d import punkt_dreieck_abstand
    im = np.all((ka.proben >= kb.lo - tol) & (ka.proben <= kb.hi + tol), axis=1)
    if tabu_a:
        im &= ~np.isin(ka.probe_flaeche, list(tabu_a))
    if not im.any():
        return [], set()
    q, pf, pw = ka.proben[im], ka.probe_flaeche[im], ka.gewicht[im]
    if kb.baum is None:
        kb.baum = cKDTree(kb.mitten)
    k = min(NACHBARN, len(kb.T))
    _, nn = kb.baum.query(q, k=k)
    nn = np.asarray(nn).reshape(len(q), k)
    d = np.full(len(q), np.inf)
    treffer = np.full(len(q), -1)
    for j in range(k):
        t = nn[:, j]
        tf = kb.tri_flaeche[t]
        dj = punkt_dreieck_abstand(q, kb.P[kb.T[t, 0]], kb.P[kb.T[t, 1]], kb.P[kb.T[t, 2]])
        if tabu_b:
            dj[np.isin(tf, list(tabu_b))] = np.inf
        besser = dj < d
        d[besser] = dj[besser]
        treffer[besser] = tf[besser]
    auf = d <= tol
    if not auf.any():
        return [], set()
    bedeckt = np.bincount(pf[auf], weights=pw[auf], minlength=len(ka.flaechen))
    anteil = bedeckt / np.maximum(ka.gesamt, 1e-300)
    liegt = [i for i in range(len(ka.flaechen)) if anteil[i] >= ANTEIL_AUFLIEGEND]
    getroffen = set(treffer[auf & np.isin(pf, liegt)].tolist()) if liegt else set()
    return liegt, getroffen


def beruehrungen(model, tol: float = None, raender=None, seiten=None, loecher=None) -> list:
    """Alle Koerperpaare, die sich beruehren - ueber gemeinsame oder
    aufeinanderliegende Flaechen. Rein geometrisch, ein Netz braucht es nicht.

    Vorfilter sind die umschliessenden Quader; was sich danach noch nahe
    kommt, wird ueber die Proben geprueft - je Koerperpaar zwei Suchen (die
    Proben des einen gegen die Dreiecke des anderen und umgekehrt), nicht je
    Flaechenpaar: am Drehlager (328 Paare nach Quader) dauerte die Suche je
    Flaechenpaar 26 s, je Koerperpaar mit einem Suchbaum je Koerper unter
    drei Sekunden. Der kleinere Koerper (Quaderdiagonale) ist ``a`` - er wird
    an der Fuge geloest, so wie ein Bolzen in der Platte und nicht die Platte
    am Bolzen.
    """
    koerper = list((getattr(model, "koerper", {}) or {}).values())
    if len(koerper) < 2:
        return []
    tol = toleranz(model) if tol is None else float(tol)
    namen = {fn for k in koerper for fn in (k.flaechen or [])}
    daten = _flaechendaten(model, namen, raender, seiten, loecher)
    kd = {k.name: _koerperdaten(k, daten) for k in koerper}
    aus: list = []
    for i, a in enumerate(koerper):
        ka = kd.get(a.name)
        if ka is None:
            continue
        for b in koerper[i + 1:]:
            kb = kd.get(b.name)
            if kb is None:
                continue
            if (ka.hi < kb.lo - tol).any() or (kb.hi < ka.lo - tol).any():
                continue
            gemeinsam = [fn for fn in ka.flaechen if fn in set(kb.flaechen)]
            tabu_a = {ka.flaechen.index(fn) for fn in gemeinsam}
            tabu_b = {kb.flaechen.index(fn) for fn in gemeinsam}
            liegt_a, trifft_b = _auflage(ka, kb, tol, tabu_a, tabu_b)
            liegt_b, trifft_a = _auflage(kb, ka, tol, tabu_b, tabu_a)
            fl_a = [ka.flaechen[j] for j in range(len(ka.flaechen)) if j in set(liegt_a) | trifft_a]
            fl_b = [kb.flaechen[j] for j in range(len(kb.flaechen)) if j in set(liegt_b) | trifft_b]
            if not gemeinsam and not fl_a:
                continue
            diag_a = float(np.linalg.norm(ka.hi - ka.lo))
            diag_b = float(np.linalg.norm(kb.hi - kb.lo))
            if diag_b < diag_a * (1 - 1e-9) or (abs(diag_b - diag_a) <= 1e-9 * max(diag_a, 1.0)
                                                and b.name < a.name):
                aus.append(Beruehrung(b.name, a.name, gemeinsam, fl_b, fl_a))
            else:
                aus.append(Beruehrung(a.name, b.name, gemeinsam, fl_a, fl_b))
    return aus


# --------------------------------------------------------------------------
# Kontakte anlegen und nachfuehren
# --------------------------------------------------------------------------
def kontakte_nachfuehren(model, log: list = None, tol: float = None,
                         raender=None, seiten=None, loecher=None) -> dict:
    """Fuer jedes Koerperpaar, das sich beruehrt und noch keine Kontaktbedingung
    hat, eine anlegen: starr (Standardkontakt „Verbund"), automatisch, der Name
    traegt die Wirkung. Rueckgabe {"neu": [...], "entfernt": [...],
    "beruehrungen": n}.

    Ein Paar gilt als versorgt, wenn eine Bedingung eine seiner beruehrenden
    Flaechen nennt oder die beiden Koerper als A und B fuehrt. Paare in
    ``model.kontakt_ausnahmen`` (vom Anwender geloeschte automatische
    Kontakte) bleiben ohne. Automatische Bedingungen, deren Paar sich nicht
    mehr beruehrt (Koerper verschoben oder geloescht), werden entfernt,
    solange sie noch nicht im Netz ausgefuehrt sind.
    """
    from .importers._common import say
    kbs = model.kontaktbedingungen
    ausnahmen = {frozenset(p) for p in (getattr(model, "kontakt_ausnahmen", None) or []) if len(p) == 2}
    ber = beruehrungen(model, tol, raender, seiten, loecher)
    paare = {frozenset((x.a, x.b)) for x in ber}
    entfernt: list = []
    for name, kb in list(kbs.items()):
        if getattr(kb, "automatisch", False) and not kb.ausgefuehrt:
            p = paar_von(kb)
            if p is None or frozenset(p) not in paare:
                del kbs[name]
                entfernt.append(name)
                if log is not None:
                    say(log, f"Kontakt {name} entfernt: die Körper berühren sich nicht mehr")
    genannt: set = set()
    koerperpaare: set = set()
    for kb in kbs.values():
        genannt |= set(getattr(kb, "flaechennamen", None) or [])
        genannt |= set(getattr(kb, "gegenflaechen", None) or [])
        for a in (getattr(kb, "koerpernamen", None) or []):
            for b in (getattr(kb, "gegenkoerper", None) or []):
                koerperpaare.add(frozenset((str(a), str(b))))
    neu: list = []
    for x in ber:
        p = frozenset((x.a, x.b))
        if p in ausnahmen or p in koerperpaare:
            continue
        if any(fn in genannt for fn in x.flaechen()):
            continue
        kb = model.add_kontaktbedingung(
            "?", koerpernamen=[x.a], gegenkoerper=[x.b],
            flaechennamen=list(x.gemeinsam) + list(x.flaechen_a), gegenflaechen=list(x.flaechen_b),
            automatisch=True, beschreibung="automatisch angelegt: die Körper berühren sich")
        kb.standard_anwenden("Verbund")
        del kbs["?"]
        kb.name = name_fuer(model, kb)
        kbs[kb.name] = kb
        genannt |= set(x.flaechen())
        neu.append(kb.name)
        if log is not None:
            say(log, f"Kontakt {kb.name}: {x.a} berührt {x.b} an {len(x.flaechen())} Flächen"
                     + (" (gemeinsame Fläche)" if x.gemeinsam and not x.flaechen_a else "")
                     + " - als starr (Verbund) angelegt; die Wirkung lässt sich rechts in der Maske ändern")
    return {"neu": neu, "entfernt": entfernt, "beruehrungen": len(ber)}
