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
    """Ob die Kopplung ``kp`` bei der Knotenmaske ``kn`` (:func:`aktive_knoten`)
    wirkt: sobald einer ihrer Knoten wirksam ist. Weggelassen wird sie nur,
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
    """Maske (nn,): Knoten, die in der Rechnung mit ``aktiv`` mittragen - an
    ihnen haengt ein wirksames Element oder eine Kopplung, die bleibt
    (:func:`kopplung_bleibt`). Nur dort wirken Knotenlasten und Punktmassen
    (assemble.load_vector)."""
    kn = aktive_knoten(model, aktiv)
    if aktiv is None:
        return kn
    out = kn.copy()
    for kp in (getattr(model, "kopplungen", None) or []):
        if kopplung_bleibt(model, kp, kn):
            out[int(kp.node_a)] = True
            out[int(kp.node_b)] = True
    return out
