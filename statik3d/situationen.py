"""
Situationen: eine Stellung des Systems und die Elemente, die darin nicht wirken.

Jeder Lastfall und jede Kombination gehoert zu einer Situation. Die
Grundstellung ist unbewegt mit allen Elementen; eine andere Situation dreht
die bewegten Teile (Stellung aus ``bridges.positions``) und schaltet die
genannten Elemente ab. Gerechnet wird jede Situation mit ihrem eigenen
Gleichungssystem: abgeschaltete Elemente liefern keine Steifigkeit, keine
Last und keine Schnittgroessen; Knoten, an denen dann nichts mehr haengt,
werden festgehalten (sie haetten sonst keine Steifigkeit).
"""
from __future__ import annotations

import numpy as np

from .model import Model


def situationsmodell(model: Model, name: str = "") -> tuple:
    """(Modell, Aktivmaske oder None, Protokollzeilen) der Situation.

    Ohne Stellung ist das Modell das Original (keine Kopie); mit Stellung
    eine Kopie mit gedrehten Knoten und den in der Stellung wirksamen Lagern.
    Die Lastfaelle bleiben alle erhalten - welche gelten, sagt der Lastfall
    selbst ueber seine Situation.
    """
    sit = model.situation(name)
    log: list[str] = []
    m = model
    # 'Grundstellung' ist nur ohne Stellung dieses Namens unbewegt
    # (Model.stellung_unbewegt, dieselbe Regel wie aktive_elemente und check)
    if not model.stellung_unbewegt(sit.stellung):
        st = model.stellung(sit.stellung)
        if st is None:
            raise ValueError(f"Situation '{sit.name}': Stellung '{sit.stellung}' unbekannt")
        m = model.copy()
        m.name = f"{model.name} – {sit.name}"
        # Die Schalen behalten die Lage des Grundmodells (Befund A6,
        # 14.11.2026): ausgerichtet wird in der Geometrie des Grundmodells,
        # danach nicht mehr - die Lage aendert die Rechnung nicht, und in der
        # Stellung waere jede Normale eine andere
        from .schalenlage import lage_festhalten
        log.extend(f"  {sit.name}: {z}" for z in lage_festhalten(m))
        # Ausgangsstellung, Verschiebung, Verdrehung, Lager und Gelenke der
        # Stellung - alles, was ihre Lage und Wirkung ausmacht
        st.anwenden(m, model, log)
        m.stellungen = list(model.stellungen)
    aktiv = None
    maske = model.aktive_elemente(sit.name)
    if not maske.all():
        aktiv = maske
        if not aktiv.any():
            raise ValueError(f"Situation '{sit.name}': alle Elemente deaktiviert")
        n_aus = int((~aktiv).sum())
        log.append(f"  {sit.name}: {n_aus} {'Element' if n_aus == 1 else 'Elemente'} ohne Wirkung")
    return m, aktiv, log


def aktive_knoten(model: Model, aktiv) -> np.ndarray:
    """Maske (nn,): True, wo mindestens ein wirksames Element haengt."""
    if aktiv is None:
        return np.ones(model.nn, dtype=bool)
    kn = np.zeros(model.nn, dtype=bool)
    for i, e in enumerate(model.elements):
        if aktiv[i]:
            kn[[int(n) for n in e.nodes]] = True
    return kn


def kopplung_bleibt(model: Model, kp, kn: np.ndarray) -> bool:
    """Ob die Kopplung ``kp`` bei der Knotenmaske ``kn`` (seit 15.11.2026
    :func:`wirksame_knoten`, bis dahin :func:`aktive_knoten`) wirkt: sobald
    einer ihrer Knoten wirksam ist. Weggelassen wird sie nur,
    wenn an beiden Seiten kein wirksames Element haengt - dann verbaende sie
    zwei Knoten, die nichts tragen.

    Bis zum 14.10.2026 musste an **beiden** Knoten ein wirksames Element
    haengen. Ein Master ohne eigenes Element (Ankerende im Spannschritt, die
    Staebe sind dort inaktiv; Last- und Lagerknoten, die fugen.stabenden_koppeln
    an einen Koerper haengt) verlor so seine Kopplung, sobald irgendeine Maske
    gesetzt war - im Spannschritt, in einer Situation mit abgeschaltetem
    Element und, ueber Model.grundmaske, in jeder Rechnung mit einem Stab
    „aus“. Seine Kraft ging in die automatische Haltung (Meldung
    „Mechanismus“, am Drehlager 16-mal je Spannstufe) oder fiel in
    assemble.load_vector still weg.

    Ausnahme Stabende (fugen.STABENDE_GRUPPE, RBE3 an 1-4 Knoten des
    Koerpers): Der Stabknoten folgt dem Mittel der Koerperknoten. Sind die
    abgeschaltet, haetten sie nur die Straffeder und waeren frei beweglich -
    die Kopplung braucht darum einen wirksamen Koerperknoten (node_b)."""
    a, b = int(kp.node_a), int(kp.node_b)
    if str(getattr(kp, "gruppe", "") or "").startswith(_stabende_gruppe()):
        return bool(kn[b])
    return bool(kn[a] or kn[b])


def _stabende_gruppe() -> str:
    from .fugen import STABENDE_GRUPPE
    return STABENDE_GRUPPE


def wirksame_knoten(model: Model, aktiv) -> np.ndarray:
    """Maske (nn,): Knoten, die in der Rechnung mit ``aktiv`` mittragen. Nur
    dort wirken Knotenlasten und Punktmassen (assemble.load_vector), und nur
    Kopplungen an ihnen bleiben (assemble.kopplungen).

    Ausgangspunkt sind die Knoten mit einem wirksamen Element
    (:func:`aktive_knoten`) und die Lagerknoten, an denen im ganzen Modell
    kein Element haengt - sie tragen selbst. Von dort die Huelle ueber
    Kopplungen und Starrkoerper bis zum Fixpunkt:

    * eine Kopplung, die bleibt (:func:`kopplung_bleibt`): beide Knoten;
    * ein Starrkoerper RBE2 mit einem wirksamen Knoten (Master oder Slave):
      alle seine Knoten - sie folgen einander starr;
    * ein Starrkoerper RBE3 (auch die verteilende Kopplung eines Stabendes,
      stabeinleitung.ist_verteilkopplung) mit einem wirksamen Slave: der
      Master, der den Slaves folgt. Die Slaves selbst nicht - die RBE3
      versteift sie nicht, ein Slave ohne eigenes Element haette nur die
      Strafsteifigkeit der sechs Zeilen.

    Ein Starrkoerper oder eine Kopplung, deren ganze Kette an keinem
    wirksamen Element und keinem solchen Lagerknoten haengt (ein ganz
    abgeschalteter Nebenarm), bleibt unwirksam wie bisher.

    Bis zum 15.11.2026 (Verfahrensstand 64) zaehlten nur die Kopplungen und
    nur eine Stufe: Eine Last an einem Knoten ohne Element, der ueber einen
    Starrkoerper (oder eine Kette Knoten ohne Element - Starrkoerper -
    Kopplung - Element) angebunden ist, fiel bei jeder Elementmaske still weg
    (Situation mit abgeschaltetem Element, Stab „aus“): Kragarm 3 m, Last
    1 kN per RBE2 am Ende, w = 0,0000 statt 0,5357 mm."""
    kn = aktive_knoten(model, aktiv)
    if aktiv is None:
        return kn
    out = kn.copy()
    nn = len(out)
    out |= _lagerknoten_ohne_element(model, nn)
    kopp = list(getattr(model, "kopplungen", None) or [])
    # kopplung_bleibt fuer alle Kopplungen auf einmal (am Drehlager Tausende,
    # je Lastfall ein Aufruf): Stabende nur ueber node_b, sonst eine Seite
    ka = np.fromiter((int(kp.node_a) for kp in kopp), dtype=np.int64, count=len(kopp))
    kb = np.fromiter((int(kp.node_b) for kp in kopp), dtype=np.int64, count=len(kopp))
    gruppe = _stabende_gruppe()
    nur_b = np.fromiter((str(getattr(kp, "gruppe", "") or "").startswith(gruppe) for kp in kopp),
                        dtype=bool, count=len(kopp))
    sk_liste = []
    from .stabeinleitung import ist_verteilkopplung
    for sk in (getattr(model, "starrkoerper", None) or []):
        master = int(sk.master)
        slaves = [int(x) for x in (sk.slaves or []) if 0 <= int(x) < nn and int(x) != master]
        if not slaves or not 0 <= master < nn:
            continue
        rbe2 = str(getattr(sk, "art", "RBE2")).upper() == "RBE2" and not ist_verteilkopplung(sk)
        sk_liste.append((master, slaves, rbe2))
    while True:
        vorher = int(out.sum())
        if len(kopp):
            bleibt = np.where(nur_b, out[kb], out[ka] | out[kb])
            out[ka[bleibt]] = True
            out[kb[bleibt]] = True
        for master, slaves, rbe2 in sk_liste:
            if rbe2:
                if out[master] or out[slaves].any():
                    out[master] = True
                    out[slaves] = True
            elif out[slaves].any():
                out[master] = True
        if int(out.sum()) == vorher:
            return out


def _lagerknoten_ohne_element(model: Model, nn: int) -> np.ndarray:
    """Maske (nn,): Knoten mit Lager, an denen im ganzen Modell kein Element
    haengt (Lager ueber einen Starrkoerper oder eine Kopplung angebunden).
    Ein Lagerknoten eines abgeschalteten Elements zaehlt nicht."""
    out = np.zeros(nn, dtype=bool)
    lager = {int(s.node) for s in (getattr(model, "supports", None) or [])
             if 0 <= int(getattr(s, "node", -1)) < nn}
    if not lager:
        return out
    mit_element = set()
    for e in model.elements:
        mit_element.update(int(n) for n in e.nodes)
    for n in lager - mit_element:
        out[n] = True
    return out
