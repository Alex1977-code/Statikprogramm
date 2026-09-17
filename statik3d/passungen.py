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


#: Die drei Arten einer Paarung (DIN ISO 286) und was sie statisch bedeuten.
#: Der Anwender (17.09.2026) zu den Passstiften: bei Spielpassung dreht sich
#: der Stift zwar, aendert aber seine Lage nicht und faellt nicht heraus - das
#: System funktioniert; bei Uebergangs- und Presspassung haelt ihn die
#: Fuegekraft, und die Pressung ist eine zusaetzliche Spannung im System.
ARTEN = {
    "spiel": ("Spielpassung",
              "Die Welle ist immer kleiner als die Bohrung: der Stift liegt erst an, wenn er das "
              "Spiel durchfahren hat. Quer hält ihn dann die Form der Bohrung, längs seiner Achse "
              "nur Reibung - und die braucht Anpressung. Er kann sich um seine Achse drehen; seine "
              "Lage ändert das nicht, und er fällt nicht heraus."),
    "uebergang": ("Übergangspassung",
                  "Je nach Istmaß Spiel oder Übermaß. Im Übermaßfall hält die Fügekraft den Stift "
                  "statisch; im Spielfall gilt, was bei der Spielpassung steht. Für die "
                  "Tragfähigkeit ist das Höchstspiel der ungünstige Ansatz, für die Spannung das "
                  "Höchstübermaß - beide Rechnungen sind sinnvoll."),
    "press": ("Presspassung",
              "Die Welle ist immer größer als die Bohrung: die Fuge steht schon vor der Last unter "
              "Druck. Die Pressung ist eine zusätzliche Spannung im System, und über sie hält "
              "Reibung den Stift auch längs seiner Achse."),
}


def spiele(es: float, ei: float, ES: float, EI: float) -> tuple:
    """(Hoechst-, Mittel-, Mindestspiel) [m] - das Gegenstueck zu
    :func:`uebermasse`: Spiel ist negatives Uebermass.

        Hoechstspiel  S_max = ES - ei   (groesste Bohrung, kleinste Welle)
        Mindestspiel  S_min = EI - es   (kleinste Bohrung, groesste Welle)
    """
    hoechst, mittel, mindest = uebermasse(es, ei, ES, EI)
    return -mindest, -mittel, -hoechst


def art(es: float, ei: float, ES: float, EI: float) -> str:
    """Die Art der Paarung: ``"spiel"``, ``"uebergang"`` oder ``"press"``.

    Entschieden wird an den Grenzfaellen, nicht am Mittelwert: liegt die
    groesste Welle noch unter der kleinsten Bohrung, gibt es **immer** Spiel;
    liegt die kleinste Welle noch ueber der groessten Bohrung, gibt es
    **immer** Uebermass; dazwischen haengt es am Istmass.
    """
    hoechst, _mittel, mindest = uebermasse(es, ei, ES, EI)
    if hoechst <= 0.0:
        return "spiel"
    if mindest >= 0.0:
        return "press"
    return "uebergang"


def wirkung(es: float, ei: float, ES: float, EI: float, ansatz: str = "mittel") -> dict:
    """Was die Paarung fuer die Rechnung bedeutet.

    Rueckgabe {"art", "name", "bedeutung", "spiel", "uebermass", "text"}:
    ``spiel`` [m] wird als Eigenschaft der Fuge gesetzt, ``uebermass`` [m] als
    Last aufgebracht - eines von beiden ist null. ``ansatz`` waehlt wie in
    :data:`ANSAETZE` zwischen mittlerem, hoechstem und mindestem Wert; bei der
    Uebergangspassung heisst „hoechst" das Hoechstuebermass (groesste
    Pressung) und „mindest" das Hoechstspiel (kleinste Tragfaehigkeit).
    """
    a = art(es, ei, ES, EI)
    ue = uebermass(es, ei, ES, EI, ansatz)
    name, bedeutung = ARTEN[a]
    aus = {"art": a, "name": name, "bedeutung": bedeutung,
           "spiel": max(0.0, -ue), "uebermass": max(0.0, ue)}
    s_max, s_mit, s_min = spiele(es, ei, ES, EI)
    u_max, u_mit, u_min = uebermasse(es, ei, ES, EI)
    if a == "spiel":
        aus["text"] = (f"{name}: Spiel {s_min * 1e6:+.0f} … {s_max * 1e6:+.0f} µm am Durchmesser, "
                       f"im Mittel {s_mit * 1e6:+.0f} µm - gerechnet mit "
                       f"{aus['spiel'] * 1e6:.0f} µm Spiel")
    elif a == "press":
        aus["text"] = (f"{name}: Übermaß {u_min * 1e6:+.0f} … {u_max * 1e6:+.0f} µm am Durchmesser, "
                       f"im Mittel {u_mit * 1e6:+.0f} µm - gerechnet mit "
                       f"{aus['uebermass'] * 1e6:.0f} µm Übermaß")
    else:
        aus["text"] = (f"{name}: zwischen {s_max * 1e6:.0f} µm Spiel und {u_max * 1e6:.0f} µm Übermaß "
                       f"am Durchmesser - gerechnet mit "
                       + (f"{aus['uebermass'] * 1e6:.0f} µm Übermaß" if aus["uebermass"]
                          else f"{aus['spiel'] * 1e6:.0f} µm Spiel"))
    return aus


#: Die gaengigen Paarungen fuer Passstifte (Stift m6), nach dem Einsatzzweck
#: benannt - so, wie sie auf der Zeichnung stehen (17.09.2026, vom Anwender).
#: Die **Abmasse stehen hier nicht**: siehe der Hinweis oben im Modul. Was
#: hier steht, ist die Art, die aus der Paarung folgen muss - daran prueft
#: das Programm die eingetragenen Abmasse.
STIFTPASSUNGEN = {
    "fester Sitz (H7)": (
        "uebergang", "m6/H7",
        "Der Standard im Maschinenbau: der Stift sitzt fest und wird mit Hammer oder Presse "
        "montiert, er positioniert genau."),
    "sehr fester Sitz (N7)": (
        "press", "m6/N7",
        "Für Verbindungen unter extremen Kräften, die sich keinesfalls lockern dürfen; die "
        "Demontage ist oft nur durch Auspressen möglich."),
    "sehr fester Sitz (P7)": (
        "press", "m6/P7",
        "Wie N7, noch fester - Demontage durch Auspressen."),
    "leichte Demontage (H8)": (
        "spiel", "m6/H8",
        "Der Stift lässt sich von Hand oder mit wenig Kraft einschieben - für Teile, die zur "
        "Wartung oft zerlegt werden."),
    "leichte Demontage (F7)": (
        "spiel", "m6/F7",
        "Wie H8, mit mehr Spiel."),
}


def pruefen(es: float, ei: float, ES: float, EI: float, erwartet: str) -> str:
    """Passen die Abmasse zur erwarteten Art? Leerer Text heisst ja, sonst
    die Abweichung im Klartext.

    Der Sinn: das Programm bringt keine Abmass-Tabelle mit (siehe oben), also
    pruefe es wenigstens, ob die eingetippten Zahlen die Paarung ergeben, die
    auf der Zeichnung steht - ein vertauschtes Vorzeichen faellt so auf,
    bevor es zu einer falschen Pressspannung wird.
    """
    ist = art(es, ei, ES, EI)
    if ist == str(erwartet):
        return ""
    return (f"Die eingetragenen Abmaße ergeben eine {ARTEN[ist][0]}, erwartet war eine "
            f"{ARTEN[str(erwartet)][0]}. Abmaße und Kurzzeichen prüfen: Bohrung ES/EI, "
            f"Welle es/ei, jeweils mit Vorzeichen wie auf der Zeichnung.")


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
            f"im Mittel {mittel * 1e6:+g} µm ({ARTEN[art(es, ei, ES, EI)][0]})")
