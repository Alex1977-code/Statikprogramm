"""
Gemeinsames Abfangmuster fuer Meldungen in den Pruefungen (Teilpaket 9b,
03.10.2026).

Seit 9b hat das Fenster zwei Meldungsarten: ``error()`` fuer echte Fehler (das
rote Fenster „Fehler“) und ``hinweis()`` fuer Bedienhinweise (ohne Fenster: in
der Statuszeile, in der Meldungszeile der offenen Maske und im Protokoll mit
„HINWEIS:“). Bis dahin ersetzten die Pruefungen nur ``w.error`` durch eine
Liste. Kaeme an derselben Stelle jetzt ein Hinweis, saehe eine solche Pruefung
still „keine Meldung“ - eine Pruefung auf „es kam ein Fehler“ schluege fehl,
eine auf „es kam keiner“ bestuende weiter, obwohl die Stelle abgewiesen hat.

Darum fangen die Pruefungen beide Arten gemeinsam ab und werten sie getrennt
aus::

    from tests.meldungen import abfangen
    m = abfangen(w)                     # error und hinweis
    ...
    check("…", m.hinweis_mit("Zuerst Knoten in der Ansicht wählen"))
    check("…", not m.alle)              # weder Fehler noch Hinweis
    m.zurueck()                         # die vorigen Methoden wieder

Eine alte Sammelliste (``w.fehler_liste``, ``fehler_``) laesst sich mitgeben:
sie bekommt die Texte **beider** Arten, damit eine Pruefung „nichts gemeldet“
streng bleibt. Eine Pruefung, die an einer umgestellten Stelle bisher „es kam
ein Fehler“ pruefte, prueft danach positiv „es kam ein Hinweis mit diesem
Text“ (:meth:`Meldungen.hinweis_mit`, :meth:`Meldungen.zuletzt_hinweis`).

Zaehlen (Paket 13m): ein „Übernehmen“, waehrend dessen ``error()`` oder
``hinweis()`` kam, ist gescheitert. Der abgefangene Hinweis ist der echte des
Fensters - er oeffnet ohnehin nichts - und zaehlt darum wie im Programm. Der
abgefangene Fehler zaehlt ebenso (Vorgabe ``zaehlen=True``, Nachbesserung
03.10.2026, S4). Bis dahin ersetzten die Pruefungen ``w.error`` durch Listen,
die nicht zaehlten: ein abgewiesenes „Übernehmen“ galt in der Pruefung als
gelungen, im Programm nicht. Wo eine Suite das nicht vertraegt, steht
``zaehlen=False`` mit Begruendung beim Aufruf.

Fuer Attrappen (``mock.MagicMock`` als Fenster) liest :func:`aus_attrappe` die
Aufrufe von ``s.error`` und ``s.hinweis``.
"""
from __future__ import annotations

_FEHLT = object()


class Meldungen:
    """Die abgefangenen Meldungen in ihrer Reihenfolge: ``(art, text)`` mit
    art ``"fehler"`` oder ``"hinweis"``."""

    def __init__(self, eintraege=None):
        self.eintraege: list = list(eintraege or [])

    @property
    def fehler(self) -> list:
        return [t for a, t in self.eintraege if a == "fehler"]

    @property
    def hinweise(self) -> list:
        return [t for a, t in self.eintraege if a == "hinweis"]

    @property
    def alle(self) -> list:
        return [t for _a, t in self.eintraege]

    def hinweis_mit(self, *teile) -> bool:
        """Kam ein Hinweis, der alle ``teile`` enthaelt?"""
        return any(all(s in t for s in teile) for t in self.hinweise)

    def fehler_mit(self, *teile) -> bool:
        """Kam ein Fehler, der alle ``teile`` enthaelt?"""
        return any(all(s in t for s in teile) for t in self.fehler)

    def zuletzt_hinweis(self, *teile) -> bool:
        """Ist die letzte Meldung ein Hinweis, der alle ``teile`` enthaelt?"""
        return self._zuletzt("hinweis", teile)

    def zuletzt_fehler(self, *teile) -> bool:
        """Ist die letzte Meldung ein Fehler, der alle ``teile`` enthaelt?"""
        return self._zuletzt("fehler", teile)

    def _zuletzt(self, art, teile) -> bool:
        if not self.eintraege:
            return False
        a, t = self.eintraege[-1]
        return a == art and all(s in t for s in teile)

    def leeren(self) -> None:
        self.eintraege.clear()

    def __repr__(self) -> str:
        return f"Meldungen({self.eintraege!r})"


class Abfang(Meldungen):
    """Haelt ``error`` und ``hinweis`` eines Fensters fest, bis :meth:`zurueck`."""

    def __init__(self, w, liste=None, protokoll=False, rufen=None, zaehlen=True):
        super().__init__()
        self.w = w
        self.liste = liste
        self.protokoll = protokoll
        self.rufen = rufen
        self.zaehlen = zaehlen
        self._alt = {n: vars(w).get(n, _FEHLT) for n in ("error", "hinweis")}

    def _neu(self, art, msg) -> None:
        text = str(msg)
        self.eintraege.append((art, text))
        if self.liste is not None:
            self.liste.append(text)
        if callable(self.rufen):
            self.rufen(art, text)

    def error(self, msg, *_a, **_k) -> None:
        """Wie MainWindow.error, nur ohne das rote Fenster; mit ``zaehlen``
        gezaehlt wie dort (ein „Übernehmen“ mit Fehler ist gescheitert, Paket
        13m), mit ``protokoll`` mit der FEHLER-Zeile."""
        self._neu("fehler", msg)
        w = self.w
        if self.zaehlen:
            w._fehlerzahl = getattr(w, "_fehlerzahl", 0) + 1
        if self.protokoll and getattr(w, "log", None) is not None:
            w.log.appendPlainText("FEHLER: " + str(msg))

    def hinweis(self, msg, *_a, **_k) -> None:
        """Der echte Hinweis des Fensters - er oeffnet nichts, zaehlt selbst und
        schreibt Statuszeile, Maske und Protokoll."""
        self._neu("hinweis", msg)
        echt = getattr(type(self.w), "hinweis", None)
        if callable(echt):
            echt(self.w, msg)
        else:
            w = self.w
            w._fehlerzahl = getattr(w, "_fehlerzahl", 0) + 1
            if self.protokoll and getattr(w, "log", None) is not None:
                w.log.appendPlainText("HINWEIS: " + str(msg))

    def zurueck(self) -> None:
        """Die Methoden von vorher wieder einsetzen (auch eine andere Attrappe)."""
        for n, alt in self._alt.items():
            if alt is _FEHLT:
                vars(self.w).pop(n, None)
            else:
                setattr(self.w, n, alt)

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        self.zurueck()
        return False


def abfangen(w, liste=None, protokoll=False, rufen=None, zaehlen=True) -> Abfang:
    """``w.error`` und ``w.hinweis`` abfangen; ``liste`` bekommt die Texte
    beider Arten, ``protokoll`` schreibt die FEHLER-Zeile wie das Fenster,
    ``rufen(art, text)`` wird je Meldung gerufen (etwa ein check(..., False)),
    ``zaehlen`` zaehlt den Fehler im Fehlerzaehler wie MainWindow.error (der
    Hinweis zaehlt immer); ``zaehlen=False`` nur mit Begruendung beim Aufruf."""
    a = Abfang(w, liste, protokoll, rufen, zaehlen)
    w.error = a.error
    w.hinweis = a.hinweis
    return a


def aus_attrappe(s) -> Meldungen:
    """Die Meldungen einer MagicMock-Attrappe: Aufrufe von ``s.error`` und
    ``s.hinweis`` (je erstes Argument) - die Reihenfolge zwischen beiden Arten
    kennt die Attrappe nicht, erst alle Fehler, dann alle Hinweise."""
    def texte(aufrufe):
        return [str(c.args[0]) for c in aufrufe.call_args_list if c.args]
    return Meldungen([("fehler", t) for t in texte(s.error)]
                     + [("hinweis", t) for t in texte(s.hinweis)])
