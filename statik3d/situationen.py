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

from .model import Model, GRUNDSTELLUNG


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
    if sit.stellung and sit.stellung != GRUNDSTELLUNG:
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
        log.append(f"  {sit.name}: {int((~aktiv).sum())} Elemente ohne Wirkung")
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
