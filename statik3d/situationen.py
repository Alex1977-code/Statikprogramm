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


def kopplung_bleibt(model: Model, kp, kn: np.ndarray, tot: np.ndarray = None) -> bool:
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
    die Kopplung braucht darum einen wirksamen Koerperknoten (node_b).

    ``tot`` (seit Verfahrensstand 71, Runde k10c, 15.11.2026): Maske (nn,) der
    Knoten abgeschalteter Elemente (:func:`abgeschaltete_knoten`). Ein
    Koerperknoten ohne jedes Element ist kein Knoten eines abgeschalteten
    Koerpers; dann bleibt die Kopplung auch ueber den wirksamen Stabknoten
    (node_a) - dieselbe Regel wie bei der verteilenden Kopplung eines
    Stabendes (:func:`huelle`). Ohne ``tot`` gilt die Regel bis Stand 70 (nur
    ueber node_b; fuer die Merkmale in rechenverfahren). Bis dahin entfiel die
    Kopplung unter jeder Maske, auch einer Einsermaske: Kragarm 3 m, Kopplung
    „Stabende“ vom Ende b an Q ohne Element, 1 kN an Q - mit Maske w(b) =
    0 mm und Summe Rz 0 N, ohne Maske und in der Gegenrechnung 0,5357 mm und
    1 000 N, Gleichgewichtskontrolle „ok“."""
    a, b = int(kp.node_a), int(kp.node_b)
    if str(getattr(kp, "gruppe", "") or "").startswith(_stabende_gruppe()):
        if kn[b]:
            return True
        return tot is not None and bool(kn[a]) and not bool(tot[b])
    return bool(kn[a] or kn[b])


def _stabende_gruppe() -> str:
    from .fugen import STABENDE_GRUPPE
    return STABENDE_GRUPPE


def wirksame_knoten(model: Model, aktiv, kn: np.ndarray = None) -> np.ndarray:
    """Maske (nn,): Knoten, die in der Rechnung mit ``aktiv`` mittragen. Nur
    dort wirken Knotenlasten und Punktmassen (assemble.load_vector), und nur
    Kopplungen an ihnen bleiben (assemble.kopplungen).

    Ausgangspunkt sind die Knoten mit einem wirksamen Element
    (:func:`aktive_knoten`, als ``kn`` mitzugeben, wenn schon bekannt) und die
    Lagerknoten ohne wirksames Element - auch die, an denen nur abgeschaltete
    Elemente haengen: Sie tragen selbst, wie in der Gegenrechnung mit
    geloeschten Elementen, in der sie Lagerknoten ohne Element sind. Von dort
    die Huelle ueber Kopplungen und Starrkoerper bis zum Fixpunkt:

    * eine Kopplung, die bleibt (:func:`kopplung_bleibt`): beide Knoten;
    * ein Starrkoerper (RBE2 oder RBE3), an dem der Master oder ein Slave
      wirksam ist: alle seine Knoten. Bei der verteilenden Kopplung eines
      Stabendes (stabeinleitung.ist_verteilkopplung) loest ein wirksamer
      Slave aus - der Master nur, wenn keiner ihrer Slaves Knoten eines
      abgeschalteten Elements ist: Ist der Koerper abgeschaltet, lebt er ueber
      den Stab nicht wieder auf (wie bei der Kopplung eines Stabendes, die
      einen wirksamen Koerperknoten braucht, :func:`kopplung_bleibt`); ein
      Slave ohne jedes Element ist aber kein Koerperknoten. Dieselbe Regel
      wie theorie3._wirksame_knoten_th3.
      Die Abweisung nach Theorie III. Ordnung (theorie3._th3_wirkung) zaehlt
      den Anschluss eines Stabendes seit Runde k10 auch, wenn nur das
      Stabende mittraegt und die Koerperseite ueber Starrkoerper und
      Kopplungen einen Lager- oder Lastknoten oder ein zweites Stabende
      erreicht.

    Ein Starrkoerper oder eine Kopplung, deren ganze Kette an keinem
    wirksamen Element und keinem Lagerknoten haengt (ein ganz abgeschalteter
    Nebenarm), bleibt unwirksam wie bisher.

    Massstab ist die Gegenrechnung, in der die abgeschalteten Elemente
    geloescht sind und alles andere bleibt; in allen Sonden der Gegenpruefung
    vom 15.11.2026 mit loesbarer Gegenrechnung stimmt die Regel mit ihr
    ueberein. Die Steifigkeit der Starrkoerper baut assemble.starrkoerper
    ohnehin immer ein, die Maske entscheidet nur ueber Lasten und Kopplungen.

    Bis zum 15.11.2026 (Verfahrensstand 64) zaehlten nur die Kopplungen und
    nur eine Stufe: Eine Last an einem Knoten ohne Element, der ueber einen
    Starrkoerper (oder eine Kette Knoten ohne Element - Starrkoerper -
    Kopplung - Element) angebunden ist, fiel bei jeder Elementmaske still weg
    (Situation mit abgeschaltetem Element, Stab „aus“): Kragarm 3 m, Last
    1 kN per RBE2 am Ende, w = 0,0000 statt 0,5357 mm. Im ersten Entwurf
    derselben Runde loeste bei der RBE3 nur ein wirksamer Slave aus, und nur
    der Master wurde wirksam: Last 1 kN an einem Slave Q ohne Element, Master
    am wirksamen Kragarmende - w = 0 statt 0,5357 mm, Summe der
    Auflagerkraefte 0 (Gegenpruefung vom 15.11.2026).

    Bis Verfahrensstand 66 (Runde k10, 15.11.2026) zaehlte ein Lagerknoten
    nur, wenn im ganzen Modell kein Element an ihm haengt, und die
    verteilende Kopplung loeste nur ueber einen Slave aus. Toter Arm c-d mit
    Lager an c, Y per Feder an c, 5 kN an Y: Summe Rz 1 000 statt 6 000 N
    (Fall M8); Stabende-Kopplung mit Master am wirksamen Kragarmende b und
    einzigem Slave Q ohne Element, 1 kN an Q: w = 0 statt 0,5357 mm (Fall V1)
    - beide Male mit Gleichgewichtskontrolle „ok“. Die Maske bis Stand 66
    liefert :func:`huelle` mit ``bis_66=True`` (rechenverfahren, Merkmal
    maske_lager_verteilung).

    Bis Verfahrensstand 70 (Runde k10c, 15.11.2026) brauchte die Kopplung
    eines Stabendes (fugen.STABENDE_GRUPPE) immer einen wirksamen
    Koerperknoten, auch wenn an ihm gar kein Element haengt: Kragarm 3 m,
    Kopplung „Stabende“ vom Ende b an Q ohne Element, 1 kN an Q - unter jeder
    Maske (Situation, Stab „aus“, Einsermaske) w(b) = 0 mm und Summe Rz 0 N,
    ohne Maske und in der Gegenrechnung 0,5357 mm und 1 000 N. Seither
    dieselbe Regel wie bei der verteilenden Kopplung: der Stabknoten loest aus,
    wenn der Koerperknoten nicht Knoten eines abgeschalteten Elements ist
    (:func:`kopplung_bleibt` mit ``tot``). Die Maske bis Stand 70 liefert
    :func:`huelle` mit ``bis_70=True`` (Merkmal maske_stabende_kopplung)."""
    return huelle(model, aktiv, kn)


def huelle(model: Model, aktiv, kn: np.ndarray = None, bis_66: bool = False,
           bis_70: bool = False) -> np.ndarray:
    """:func:`wirksame_knoten`; ``bis_66``: die Regel bis Verfahrensstand 66 -
    Lagerknoten nur ohne jedes Element, verteilende Kopplung nur ueber einen
    Slave (fuer das Merkmal maske_lager_verteilung) - und die Kopplung eines
    Stabendes nur ueber den Koerperknoten wie bis Stand 70; ``bis_70``: nur
    diese, die Regel bis Verfahrensstand 70 (Merkmal maske_stabende_kopplung)."""
    if aktiv is None:
        return aktive_knoten(model, aktiv) if kn is None else np.array(kn, dtype=bool, copy=True)
    kn = aktive_knoten(model, aktiv) if kn is None else np.asarray(kn, dtype=bool)
    out = kn.copy()
    nn = len(out)
    out |= _lagerknoten_ohne_element(model, kn, aktiv, abgeschaltete=not bis_66)
    kopp = list(getattr(model, "kopplungen", None) or [])
    # kopplung_bleibt fuer alle Kopplungen auf einmal (am Drehlager Tausende,
    # je Lastfall ein Aufruf): Stabende nur ueber node_b, sonst eine Seite
    ka = np.fromiter((int(kp.node_a) for kp in kopp), dtype=np.int64, count=len(kopp))
    kb = np.fromiter((int(kp.node_b) for kp in kopp), dtype=np.int64, count=len(kopp))
    gruppe = _stabende_gruppe()
    nur_b = np.fromiter((str(getattr(kp, "gruppe", "") or "").startswith(gruppe) for kp in kopp),
                        dtype=bool, count=len(kopp))
    sk_liste = []                         # (Ausloeser, alle Knoten) je Starrkoerper
    from .stabeinleitung import ist_verteilkopplung
    tot = None                            # Knoten abgeschalteter Elemente (erst bei Bedarf)
    # Kopplung eines Stabendes: auch der Stabknoten loest aus, wenn ihr
    # Koerperknoten nicht Knoten eines abgeschalteten Elements ist (Stand 71)
    b_frei = np.zeros(len(kopp), dtype=bool)
    if nur_b.any() and not (bis_66 or bis_70):
        tot = abgeschaltete_knoten(model, aktiv, nn)
        b_frei = nur_b & ~tot[kb]
    for sk in (getattr(model, "starrkoerper", None) or []):
        master = int(sk.master)
        slaves = [int(x) for x in (sk.slaves or []) if 0 <= int(x) < nn and int(x) != master]
        if not slaves:
            continue
        alle = np.array(slaves + ([master] if 0 <= master < nn else []), dtype=np.int64)
        ausloeser = alle
        if ist_verteilkopplung(sk):
            if tot is None and not bis_66:
                tot = abgeschaltete_knoten(model, aktiv, nn)
            # Slaves ohne jedes Element (kein Koerperknoten): auch der Master loest aus
            if bis_66 or tot[np.array(slaves, dtype=np.int64)].any():
                ausloeser = np.array(slaves, dtype=np.int64)
        sk_liste.append((ausloeser, alle))
    while True:
        vorher = int(out.sum())
        if len(kopp):
            bleibt = np.where(nur_b, out[kb] | (b_frei & out[ka]), out[ka] | out[kb])
            out[ka[bleibt]] = True
            out[kb[bleibt]] = True
        for ausloeser, alle in sk_liste:
            if out[ausloeser].any():
                out[alle] = True
        if int(out.sum()) == vorher:
            return out


def abgeschaltete_knoten(model: Model, aktiv, nn: int = None) -> np.ndarray:
    """Maske (nn,): Knoten, an denen ein abgeschaltetes Element haengt."""
    nn = int(model.nn) if nn is None else nn
    out = np.zeros(nn, dtype=bool)
    if aktiv is None:
        return out
    els = model.elements
    for i in np.flatnonzero(~np.asarray(aktiv, dtype=bool)):
        for n in els[int(i)].nodes:
            if 0 <= int(n) < nn:
                out[int(n)] = True
    return out


def _lagerknoten_ohne_element(model: Model, kn: np.ndarray, aktiv, abgeschaltete: bool = True) -> np.ndarray:
    """Maske (nn,): Knoten mit Lager, an denen kein wirksames Element haengt
    (``kn`` sind die Knoten mit wirksamem Element, :func:`aktive_knoten`).

    ``abgeschaltete`` (seit Verfahrensstand 67, Runde k10, 15.11.2026): auch
    ein Lagerknoten, an dem nur abgeschaltete Elemente haengen, traegt selbst -
    in der Gegenrechnung mit geloeschten Elementen ist er ein Lagerknoten ohne
    Element. Bis dahin (``abgeschaltete=False``, die Regel bis Stand 66) zaehlte
    er nicht, und eine Last, die ueber eine Kopplung an ihm haengt, entfiel
    still: toter Arm c-d, Lager an c, Y per Feder an c, 5 kN an Y - Summe Rz
    1 000 statt 6 000 N, Gleichgewichtskontrolle „ok“ (Fall M8 der zweiten
    Gegenpruefung k9).

    Mit ``abgeschaltete=False`` genuegt der Blick auf die abgeschalteten
    Elemente (bis zum 15.11.2026 ein Lauf ueber alle Elemente, am Drehlager
    rund 0,4 s je Aufruf)."""
    nn = len(kn)
    out = np.zeros(nn, dtype=bool)
    lager = {int(s.node) for s in (getattr(model, "supports", None) or [])
             if 0 <= int(getattr(s, "node", -1)) < nn and not kn[int(s.node)]}
    if not lager:
        return out
    if not abgeschaltete:
        els = model.elements
        for i in np.flatnonzero(~np.asarray(aktiv, dtype=bool)):
            lager.difference_update(int(n) for n in els[int(i)].nodes)
            if not lager:
                return out
    for n in lager:
        out[n] = True
    return out
