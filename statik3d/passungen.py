"""
Passungen: aus den Abmassen einer Paarung die Ueberdeckung rechnen.

Eine Passung steht auf der Zeichnung als Kurzzeichen - „Ø40 H7/s6". Was das
Programm braucht, ist eine Laenge: **wie viel** die beiden Teile zusammen zu
viel haben. Der Weg dahin fuehrt ueber die Abmasse, und die stehen in der
Passungstabelle der Zeichnung oder im Tabellenbuch:

* **Bohrung** (Innenmass): oberes Abmass ES, unteres Abmass EI
* **Welle**  (Aussenmass): oberes Abmass es, unteres Abmass ei

Alle vier beziehen sich auf dasselbe Nennmass und sind vorzeichenbehaftet;
bei einer Presspassung liegt die Welle ueber der Bohrung, ei ist also
groesser als ES.

Damit ist die Ueberdeckung eine Subtraktion:

    Hoechstuebermass   Ü_max = es - EI      (groesste Welle, kleinste Bohrung)
    Mindestuebermass   Ü_min = ei - ES      (kleinste Welle, groesste Bohrung)
    mittleres Uebermass       = (Ü_max + Ü_min) / 2

Ein negativer Wert ist kein Uebermass, sondern Spiel.

**Warum keine eingebaute Tabelle.** ISO 286 hat fuer jedes Nennmassfeld und
jede Toleranzlage eigene Werte; eine aus dem Gedaechtnis abgeschriebene
Tabelle waere nicht nachpruefbar, und ein Zahlendreher in ihr wuerde still zu
einer falschen Pressspannung fuehren. Eingegeben werden darum die vier
Abmasse, die auf der Zeichnung stehen - oder gleich die Gesamtueberdeckung.
Das Kurzzeichen wird als Beleg mitgefuehrt.
"""
from __future__ import annotations

#: Die Ansaetze, die eine Rechnung sinnvoll macht - und wofuer sie taugen.
ANSAETZE = {
    "hoechst": "Höchstübermaß (größte Welle, kleinste Bohrung) - größte Pressung",
    "mittel": "mittleres Übermaß - der Regelfall",
    "mindest": "Mindestübermaß (kleinste Welle, größte Bohrung) - kleinste "
               "Haltekraft, maßgebend für den Reibschluss",
}


def uebermasse(es: float, ei: float, ES: float, EI: float) -> tuple:
    """(Hoechst-, Mittel-, Mindestuebermass) aus den vier Abmassen [m].

    ``es``/``ei`` sind oberes und unteres Abmass der **Welle**, ``ES``/``EI``
    die der **Bohrung** - vorzeichenbehaftet, wie auf der Zeichnung. Ein
    negatives Ergebnis ist Spiel, kein Uebermass.
    """
    hoechst = float(es) - float(EI)
    mindest = float(ei) - float(ES)
    return hoechst, 0.5 * (hoechst + mindest), mindest


def uebermass(es: float, ei: float, ES: float, EI: float,
              ansatz: str = "mittel") -> float:
    """Die Gesamtueberdeckung [m] nach dem gewaehlten Ansatz (siehe
    :data:`ANSAETZE`)."""
    hoechst, mittel, mindest = uebermasse(es, ei, ES, EI)
    return {"hoechst": hoechst, "mindest": mindest}.get(str(ansatz), mittel)


def text(es: float, ei: float, ES: float, EI: float, nennmass: float = 0.0,
         kurzzeichen: str = "") -> str:
    """Die Paarung als Zeile fuer Protokoll und Bericht."""
    hoechst, mittel, mindest = uebermasse(es, ei, ES, EI)
    kopf = (f"Ø{nennmass * 1e3:g}" if nennmass else "Passung")
    if kurzzeichen:
        kopf += f" {kurzzeichen}"
    return (f"{kopf}: Bohrung ES {ES * 1e6:+g} / EI {EI * 1e6:+g} µm, "
            f"Welle es {es * 1e6:+g} / ei {ei * 1e6:+g} µm → Übermaß "
            f"{mindest * 1e6:+g} … {hoechst * 1e6:+g} µm, "
            f"im Mittel {mittel * 1e6:+g} µm")
