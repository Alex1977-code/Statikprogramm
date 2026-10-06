"""
Stellungen des Systems - bewegliche Brücken und Stahlwasserbauten.

Eine Klappbrücke, eine Drehbrücke oder ein Hubtor ist in jeder Stellung ein
anderes Tragwerk: Lager greifen oder nicht, Riegel sind gezogen, das
Eigengewicht wirkt unter einem anderen Winkel, der Antrieb hält ein anderes
Moment. Deshalb wird jede **Stellung** als eigener Rechenlauf geführt und am
Ende die Umhüllende über alle Stellungen gebildet.

    Stellung        Name, Winkel, welche Lager greifen, welche Lastfälle sie
                    rechnet (nur zugewiesene, ohne Zuordnung keine),
                    Drehachse und Drehwinkel für die bewegten Bauteile
    Stellungsreihe  alle Stellungen eines Bauwerks, gerechnet und ausgewertet
    Umhüllende      größte Ausnutzung, Schnittgröße und Auflagerkraft über alle
                    Stellungen, mit Angabe der maßgebenden Stellung

    from statik3d.bridges.positions import Stellung, Stellungsreihe
    reihe = Stellungsreihe(modell)
    lf = list(modell.load_cases)
    reihe.add(Stellung("S1", 0.0,   "geschlossen", lager_aktiv=["Endauflager"], faelle=lf))
    reihe.add(Stellung("S3", 32.0,  "im Öffnen", faelle=lf))
    reihe.add(Stellung("S5", 82.0,  "offen", lager_aktiv=["Ruhelager"], faelle=lf))
    erg = reihe.rechnen()
    print(erg.bericht())
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from ..model import Model


def _massgebend(analyse, m: Model):
    """Das Ergebnis mit der groessten Verformung: Kombination, sonst Lastfall."""
    alle = analyse.all_results()
    if not alle:
        return None
    def betrag(r):
        if r is None or getattr(r, "u", None) is None:
            return -1.0
        return float(np.abs(np.asarray(r.u).reshape(-1, 6)[:, :3]).max())
    return max(alle.values(), key=betrag)


def drehmatrix(achse, winkel: float) -> np.ndarray:
    """Drehmatrix um eine Achse durch den Ursprung (Rodrigues), Winkel im Bogenmaß."""
    a = np.asarray(achse, float)
    n = np.linalg.norm(a)
    if n <= 0:
        return np.eye(3)
    a = a / n
    K = np.array([[0.0, -a[2], a[1]], [a[2], 0.0, -a[0]], [-a[1], a[0], 0.0]])
    return np.eye(3) + math.sin(winkel) * K + (1.0 - math.cos(winkel)) * (K @ K)


@dataclass
class Stellung:
    """Eine Stellung des Systems.

    name:         Kurzname, z. B. "S3"
    winkel:       Stellungswinkel in Grad (nur zur Beschriftung und für die
                  Kurve η über den Winkel)
    beschreibung: Klartext, z. B. "im Öffnen, Riegel gezogen"
    lager_aktiv:  Namen der Lager, die in dieser Stellung greifen. Leer =
                  alle Lager greifen. Lager ohne Namen bleiben immer aktiv.
    lager_aus:    Knotenlager, die in dieser Stellung ausdrücklich nicht
                  greifen (wirkt zusätzlich zu lager_aktiv). Jede Lagerart hat
                  ihre eigene Liste (lager_aus, linienlager_aus,
                  flaechenlager_aus) und ihren eigenen Schlüssel: den Namen des
                  Lagers, sonst seinen Standardnamen wie im Modellbaum („Lager 2“,
                  „Linienlager 1“, „Flächenlager 1“; Model.lagerschluessel). Bis
                  zum 06.10.2026 stand hier die Nummer ab 0, und ein Eintrag in
                  lager_aus schaltete zugleich das Linien- und das Flächenlager
                  mit derselben Nummer ab; ältere Dateien werden beim Laden
                  umgestellt (lagerschluessel_umstellen).
    faelle:       Lastfälle, die in dieser Stellung gelten - nur sie rechnet die
                  Stellungsreihe. Leer = keine (seit 02.10.2026, Zusage an den
                  Anwender: „nur das gerechnet wird was auch zugewiesen wurde“;
                  bis dahin hiess leer „alle“, aeltere Dateien bekommen darum
                  beim Laden alle, Model.from_dict).
    kombinationen: Kombinationen, die in dieser Stellung gelten. Leer = alle,
                  die nur aus den geltenden Lastfällen bestehen.
    dreh_achse / dreh_punkt / dreh_winkel:
                  Drehung der bewegten Bauteile: Achse, ein Punkt darauf und der
                  Winkel in Grad. Gedreht werden die Knoten der Gruppen in
                  dreh_gruppen (leer = alle Knoten ohne Knotenlager; Knoten
                  auf Linien- und Flächenlagern bewegen sich mit, siehe
                  _bewegte_knoten). Dieselben Knoten verschiebt verschiebung.
    dreh_gruppen: Elementgruppen, die sich mitbewegen.
    antrieb:      (Knoten, Momentenvektor [Nm]) - das Antriebsmoment, das die
                  Stellung hält. Wird als Knotenlast in einem eigenen Lastfall
                  aufgebracht.
    """
    name: str
    winkel: float = 0.0
    beschreibung: str = ""
    lager_aktiv: list = field(default_factory=list)
    lager_aus: list = field(default_factory=list)
    faelle: list = field(default_factory=list)
    kombinationen: list = field(default_factory=list)
    dreh_achse: tuple = (0.0, 1.0, 0.0)
    dreh_punkt: tuple = (0.0, 0.0, 0.0)
    dreh_winkel: float = 0.0
    dreh_gruppen: list = field(default_factory=list)
    antrieb: tuple = None
    windlast: float = 0.0
    # -- Lage gegenueber der Ausgangsstellung und Wirkung (Maske rechts) ----
    #: Ausgangsstellung: Name einer anderen Stellung, auf deren Lage die
    #: eigene Verschiebung und Verdrehung aufsetzen; "" = das unbewegte Modell
    basis: str = ""
    #: Verschiebung der bewegten Knoten [m] gegenueber der Ausgangsstellung
    verschiebung: tuple = (0.0, 0.0, 0.0)
    #: Was in dieser Stellung nicht wirkt - Staebe, Flaechen und Volumen ueber
    #: ihre Elemente, Gelenke werden biegesteif, Lager greifen nicht
    staebe_aus: list = field(default_factory=list)
    flaechen_aus: list = field(default_factory=list)
    koerper_aus: list = field(default_factory=list)
    gelenke_aus: list = field(default_factory=list)
    linienlager_aus: list = field(default_factory=list)
    flaechenlager_aus: list = field(default_factory=list)

    def beschriftung(self) -> str:
        t = f"{self.name} ({self.winkel:g}°)"
        return t + (f" - {self.beschreibung}" if self.beschreibung else "")

    def lastfall_umbenennen(self, alt: str, neu: str) -> None:
        """Die Lastfallliste folgt dem Umbenennen eines Lastfalls. Seit dem
        02.10.2026 rechnet eine Stellung nur ihre Liste; ein alter Name darin
        liess sie mit „Lastfall … gibt es im Modell nicht“ scheitern."""
        self.faelle = [neu if f == alt else f for f in self.faelle]

    # -- Modell fuer diese Stellung -------------------------------------
    def modell(self, basis: Model, log: list = None) -> Model:
        """Das Modell dieser Stellung: verschobene und gedrehte Geometrie,
        wirksame Lager und Gelenke, Lasten, abgeschaltete Elemente."""
        m = basis.copy()
        m.name = f"{basis.name} - {self.name}"
        self.anwenden(m, basis, log)
        self._faelle(m, log)
        self._deaktivieren(m, basis, log)
        if self.antrieb:
            self._antrieb(m, log)
        return m

    def anwenden(self, m: Model, basis: Model, log: list = None, kette=None,
                 nur_lage: bool = False):
        """Lage und Wirkung dieser Stellung auf die Kopie *m* von *basis* legen.

        Erst die Ausgangsstellung (ihre Lage, rekursiv), dann die eigene
        Verschiebung und Verdrehung; danach - nur fuer die Stellung selbst,
        nicht fuer die Kette - die Lager, die nicht greifen, und die Gelenke,
        die biegesteif werden.
        """
        kette = set(kette or ()) | {self.name}
        if self.basis and self.basis not in kette and hasattr(basis, "stellung"):
            st = basis.stellung(self.basis)
            if st is not None:
                st.anwenden(m, basis, log, kette, nur_lage=True)
        idx = self._bewegte_knoten(basis)
        v = np.asarray(self.verschiebung or (0.0, 0.0, 0.0), float).ravel()[:3]
        if len(idx) and np.any(np.abs(v) > 0):
            m.nodes[idx] = m.nodes[idx] + v
            if log is not None:
                log.append(f"  {self.name}: {len(idx)} Knoten um ({v[0]:g}, {v[1]:g}, {v[2]:g}) m "
                           "verschoben")
        if self.dreh_winkel:
            self._drehen(m, log, idx)
        if not nur_lage:
            self._lager(m, log)
            self._gelenke(m, log)

    def deaktivierte_elemente(self, basis: Model) -> list:
        """Die Elemente der abgeschalteten Staebe, Flaechen und Volumen."""
        els: set = set()
        for name in self.staebe_aus:
            mem = basis.members.get(name)
            if mem is not None:
                els.update(int(e) for e in (mem.elements or []))
        for name in self.flaechen_aus:
            f = basis.flaechen.get(name)
            if f is not None:
                els.update(int(e) for e in (f.elemente or []))
        for name in self.koerper_aus:
            k = basis.koerper.get(name)
            if k is not None:
                els.update(int(e) for e in (k.elemente or []))
        return sorted(e for e in els if 0 <= e < len(basis.elements))

    def _deaktivieren(self, m: Model, basis: Model, log: list = None):
        """Abgeschaltete Elemente: als Situation im Stellungsmodell, damit der
        Loeser sie ohne Steifigkeit und Last fuehrt - die Elementnummern
        bleiben, sonst liesse sich keine Umhuellende ueber die Stellungen bilden."""
        els = self.deaktivierte_elemente(basis)
        if not els:
            return
        from ..model import Situation
        name = f"Stellung {self.name}"
        m.situationen[name] = Situation(name, "", list(els),
                                        f"Elemente ohne Wirkung in Stellung {self.name}")
        for lc in m.load_cases.values():
            lc.situation = name
        for c in m.combinations.values():
            c.situation = name
        if log is not None:
            log.append(f"  {self.name}: {len(els)} {'Element' if len(els) == 1 else 'Elemente'} ohne Wirkung ("
                       + ", ".join(self.staebe_aus + self.flaechen_aus + self.koerper_aus) + ")")

    def _gelenke(self, m: Model, log: list = None):
        """Gelenke, die in dieser Stellung nicht wirken, werden biegesteif:
        ihre Freigaben und Federn gehen von den Elementen herunter, an denen
        sie gesetzt wurden."""
        weg = []
        for name in self.gelenke_aus:
            h = m.hinges.get(name)
            if h is None:
                continue
            frei = set(h.released())
            federn = {d for d, _k in h.springs()}
            for e in (getattr(h, "elemente", None) or []):
                if 0 <= int(e) < len(m.elements):
                    el = m.elements[int(e)]
                    el.hinges = [d for d in el.hinges if d not in frei]
                    el.hinge_springs = [(d, k) for d, k in el.hinge_springs if d not in federn]
            weg.append(name)
        if weg and log is not None:
            log.append(f"  {self.name}: Gelenke biegesteif: " + ", ".join(weg))

    def _bewegte_knoten(self, m: Model) -> np.ndarray:
        if self.dreh_gruppen:
            idx = set()
            for e in m.elements:
                if e.group in self.dreh_gruppen:
                    idx.update(int(n) for n in e.nodes)
            return np.fromiter(sorted(idx), dtype=int, count=len(idx))
        fest = {s.node for s in m.supports}
        return np.array([i for i in range(m.nn) if i not in fest], dtype=int)

    def _drehen(self, m: Model, log: list = None, idx=None):
        if idx is None:
            idx = self._bewegte_knoten(m)
        if not len(idx):
            return
        R = drehmatrix(self.dreh_achse, math.radians(self.dreh_winkel))
        p0 = np.asarray(self.dreh_punkt, float)
        m.nodes[idx] = (m.nodes[idx] - p0) @ R.T + p0
        if log is not None:
            log.append(f"  {self.name}: {len(idx)} Knoten um {self.dreh_winkel:g}° "
                       f"um die Achse {tuple(self.dreh_achse)} gedreht")

    #: Die drei Lagerarten: (Art, Liste im Modell, Feld der Stellung, Wort, Titel
    #: des Feldes in der Maske). Jede Art liest nur ihr Feld.
    _LAGERFELDER = (("lager", "supports", "lager_aus", "Knotenlager", "Deaktivierte Knotenlager"),
                    ("linienlager", "line_supports", "linienlager_aus", "Linienlager",
                     "Deaktivierte Linienlager"),
                    ("flaechenlager", "surface_supports", "flaechenlager_aus", "Flächenlager",
                     "Deaktivierte Flächenlager"))

    @staticmethod
    def _eintraege(liste) -> list:
        return [str(x).strip() for x in (liste or []) if str(x).strip()]

    def _lager(self, m: Model, log: list = None):
        """Die Lager, die in dieser Stellung nicht greifen, aus der Kopie nehmen.

        Jede Lagerart liest nur ihre eigene Liste und nennt ihre Lager mit dem
        Schluessel, den auch der Modellbaum zeigt (Model.lagerschluessel: der Name,
        sonst „Lager 2“, „Linienlager 1“, „Flächenlager 1“). Bis zum 06.10.2026
        las jede Art auch ``lager_aus``, mit Namen **und** Nummer: ein Eintrag „0“
        schaltete das Knotenlager 0, das Linienlager 0 und das Flaechenlager 0
        zugleich ab (F07). ``lager_aktiv`` gilt weiter fuer die Namen aller Arten.
        Ein Eintrag, der kein Lager seiner Art nennt, steht im Protokoll."""
        ein = set(self._eintraege(self.lager_aktiv))
        schluessel = {art: Model.lagerschluessel(art, getattr(m, liste))
                      for art, liste, _feld, _wort, _titel in self._LAGERFELDER}
        namen = {art: {(s.name or "").strip() for s in getattr(m, liste)} - {""}
                 for art, liste, _feld, _wort, _titel in self._LAGERFELDER}
        entfernt = []
        ohne = []
        for art, liste, feld, wort, titel in self._LAGERFELDER:
            eintraege = self._eintraege(getattr(self, feld))
            aus = set(eintraege)
            rest = []
            for key, s in zip(schluessel[art], getattr(m, liste)):
                nm = (s.name or "").strip()
                # ein Eintrag ist der Schluessel (Model.lagerschluessel) oder der Name; ein
                # Name, den mehrere Lager tragen, meint sie alle - so wie bisher
                if key in aus or (nm and nm in aus) or (ein and nm and nm not in ein):
                    entfernt.append(key)
                    continue
                rest.append(s)
            # Eintraege, die kein Lager dieser Art nennen
            for x in eintraege:
                if x in schluessel[art] or x in namen[art]:
                    continue
                woanders = [(w2, t2) for a2, _l2, _f2, w2, t2 in self._LAGERFELDER
                            if a2 != art and (x in schluessel[a2] or x in namen[a2])]
                text = f"  {self.name}: „{x}“ in „{titel}“ nennt kein {wort}"
                if woanders:
                    text += (" – " + " und ".join(f"ein {w2}" for w2, _t in woanders) + " heißt so; es gehört in „"
                             + "“ bzw. „".join(t2 for _w, t2 in woanders) + "“")
                elif x.isdecimal():
                    text += " – seit dem 06.10.2026 zählt der Name wie im Modellbaum, nicht die Nummer"
                ohne.append(text + " (ohne Wirkung)")
            setattr(m, liste, rest)
        if log is not None:
            if entfernt:
                log.append(f"  {self.name}: Lager ohne Wirkung: " + ", ".join(sorted(set(entfernt))))
            log.extend(ohne)

    def lagerschluessel_umstellen(self, m: Model) -> list:
        """Lagerlisten einer **alten** Stellung auf die Namen wie im Modellbaum umstellen.

        Bis zum 06.10.2026 standen unbenannte Lager mit ihrer Nummer ab 0 in den
        Listen, und ``lager_aus`` traf ein Lager jeder Art, beim Namen oder bei der
        Nummer (F07, F30). Jetzt hat jede Art ihre Liste und ihren Schluessel
        (Model.lagerschluessel). Beim Laden wird, so wie es damals gemeint war:

        * eine Nummer in einer Lagerliste zum Schluessel des Lagers dieser Nummer in
          der Art der Liste - die Maske schrieb sie fuer Knotenlager („0“ wird „Lager 1“,
          hat das Lager einen Namen, wird es dieser);
        * ein Name in ``lager_aus``, der **kein** Knotenlager, wohl aber ein Linien-
          oder Flaechenlager nennt, in die Liste dieser Art (er traf es bisher dort);
        * ein Eintrag, der schon ein Schluessel oder ein Name ist, bleibt.

        Was die alte Nummer ausserdem traf (das Linien- und das Flaechenlager mit
        derselben Nummer), trifft sie nicht mehr; die Zeilen sagen es. Ein zweites
        Umstellen aendert nichts mehr. Rueckgabe: die Zeilen fuer das Protokoll
        (leer, wenn nichts umzustellen war)."""
        schluessel = {art: Model.lagerschluessel(art, getattr(m, liste))
                      for art, liste, _feld, _wort, _titel in self._LAGERFELDER}
        namen = {art: {(s.name or "").strip() for s in getattr(m, liste)} - {""}
                 for art, liste, _feld, _wort, _titel in self._LAGERFELDER}
        wort = {art: w for art, _l, _f, w, _t in self._LAGERFELDER}
        titel = {art: t for art, _l, _f, _w, t in self._LAGERFELDER}
        feld_von = {art: f for art, _l, f, _w, _t in self._LAGERFELDER}
        neu = {feld: [] for _a, _l, feld, _w, _t in self._LAGERFELDER}
        umgestellt = []         # „0“ → „Lager 1“, je Liste
        mehr = []               # was die alte Nummer ausserdem traf
        verschoben = []         # Namen, die in eine andere Liste gehen

        def trifft(art, x) -> bool:
            return x in schluessel[art] or x in namen[art]

        for art, _liste, feld, _w, _t in self._LAGERFELDER:
            eintraege = self._eintraege(getattr(self, feld))
            if not eintraege:
                continue
            ziel = neu[feld]
            for x in eintraege:
                if trifft(art, x):
                    ziel.append(x)
                    continue
                if x.isdecimal() and int(x) < len(schluessel[art]):
                    neuer = schluessel[art][int(x)]
                    ziel.append(neuer)
                    umgestellt.append(f"„{titel[art]}“: „{x}“ → „{neuer}“")
                    if feld == "lager_aus":
                        for art2 in ("linienlager", "flaechenlager"):
                            if int(x) < len(schluessel[art2]) and not trifft(art2, x):
                                mehr.append(f"die Nummer „{x}“ in „{titel[art]}“ schaltete bisher auch das "
                                            f"{wort[art2]} „{schluessel[art2][int(x)]}“ ab - jetzt nur noch das "
                                            f"{wort[art]} „{neuer}“; war das {wort[art2]} gemeint, es in „"
                                            f"{titel[art2]}“ anhaken")
                    continue
                if feld == "lager_aus":
                    ziel_art = [a2 for a2 in ("linienlager", "flaechenlager") if x in namen[a2]]
                    if ziel_art:
                        for a2 in ziel_art:
                            neu[feld_von[a2]].append(x)
                        verschoben.append(f"„{x}“ stand in „{titel[art]}“, nennt aber ein "
                                          + " und ein ".join(wort[a2] for a2 in ziel_art)
                                          + " - jetzt in „" + "“ bzw. „".join(titel[a2] for a2 in ziel_art) + "“")
                        continue
                ziel.append(x)
        zeilen = []
        for _art, _liste, feld, _w, _t in self._LAGERFELDER:
            neue_liste = list(dict.fromkeys(neu[feld]))          # ohne Doppelte, in der Reihenfolge
            if neue_liste != self._eintraege(getattr(self, feld)):
                setattr(self, feld, neue_liste)
        if umgestellt:
            zeilen.append(f"Stellung {self.name}: Lager stehen jetzt mit ihrem Namen wie im Modellbaum statt "
                          "mit ihrer Nummer - " + "; ".join(umgestellt))
        zeilen += [f"Stellung {self.name}: {z}" for z in mehr + verschoben]
        return zeilen

    def _faelle(self, m: Model, log: list = None):
        if not self.faelle:
            # Leer heisst seit dem 02.10.2026 „keine“: die Stellungsreihe rechnet
            # eine solche Stellung gar nicht erst (Stellungsreihe.rechnen). Das
            # Modell selbst - Lage, Lager, Gelenke, etwa fuer die Vorschau oder
            # eine Situation - behaelt dann seine Lastfaelle unveraendert.
            return
        behalten = set(self.faelle)
        unbekannt = sorted(behalten - set(m.load_cases))
        if unbekannt:
            # Ohne diese Pruefung raeumt remove_load_case alle Lastfaelle ab und
            # legt einen leeren Ersatzlastfall an - die Stellung waere sinnlos.
            raise ValueError(f"Stellung '{self.name}': Lastfall "
                             + ", ".join(f"'{x}'" for x in unbekannt)
                             + " gibt es im Modell nicht. Vorhanden: "
                             + ", ".join(sorted(m.load_cases)))
        entfernt = [name for name in m.load_cases if name not in behalten]
        # Alternativen, die nur aus entfernten Lastfaellen bestehen, entfallen
        # (Combination.lastfall_entfernen) - fuer das Protokoll vorher gezaehlt
        alt_weg = [(c.name, i) for c in m.combinations.values()
                   for i, a in enumerate(c.alternativen, 1)
                   if entfernt and set(a) <= set(entfernt)]
        # remove_load_case nimmt seit dem 23.09.2026 die Ermuedungslasten
        # schon selbst mit (Befund B105): Lasten aus zwei Zustaenden mit einem
        # dieser Lastfaelle entfallen, ein Verlauf verliert das Glied. Fuer
        # das Protokoll unten zaehlen sie trotzdem, und ob ein Verlauf in der
        # Stellung bleibt, entscheiden seine Glieder **vor** dem Kuerzen
        # (fehlt, unten) - darum der Stand davor
        erm_vorher = {n: list(f.folge or []) for n, f in m.fatigue_loads.items()}
        for name in entfernt:
            # nimmt den Lastfall auch aus den Faktoren und den Alternativen
            # jeder Kombination (Combination.lastfall_entfernen, Befund B105)
            m.remove_load_case(name)
        # Eine Ergebniskombination hat factors leer und bleibt, solange ihr
        # eine Alternative bleibt. Bis ec6448c fiel hier jede Kombination mit
        # leeren factors ohne Meldung weg: am Kragarm mit EK1 = 1,35 LF1 oder
        # 1,35 LF1 + 1,5 LF2 ergab die Stellung mit allen Lastfaellen eta
        # 0,1702 statt 0,3702, weil der Nachweis auf die Lastfaelle zurueckfiel
        # (gemessen 23.09.2026).
        k_weg = []
        for name in list(m.combinations):
            c = m.combinations[name]
            if not set(c.factors) <= behalten or not (c.factors or c.alternativen):
                del m.combinations[name]
                k_weg.append(name)
        # Ermuedungslasten, deren Zustand in dieser Stellung fehlt, entfallen mit:
        # sonst bricht die ganze Stellung an einem Verweis ins Leere ab. Bei
        # einem Verlauf zaehlen seine Glieder - nur sie liest der
        # Ermuedungsnachweis von Staeben und Volumen (ec3.fatigue),
        # case_max/case_min eines Verlaufs liest er nicht; bis ec6448c
        # entschieden sie hier: ein Verlauf mit case_max "" (rfem6_db)
        # entfiel in jeder solchen Stellung. (Der Ermuedungsnachweis der
        # Anschluesse, joints/anschluss.py, zaehlt einen Verlauf seit B094
        # ebenfalls nach seinen Gliedern; die Stellungsreihe rechnet ohnehin
        # keine Ermuedung.) Ein Glied
        # darf eine Kombination sein (die Oberflaeche nimmt sie an, gui/main.py
        # add_fatigue_load; ec3.fatigue liest sie aus all_results) - darum
        # gelten auch die Kombinationen, die oben stehen blieben. 8daa37e
        # pruefte nur gegen die Lastfaelle, und ein Verlauf ueber K1 = G + Q1
        # entfiel in der Stellung faelle=[G, Q1], obwohl K1 blieb
        # (Gegenpruefung 23.09.2026).
        zustaende = behalten | set(m.combinations)

        # Ein Verlauf mit einem Glied ausserhalb der Stellung entfaellt ganz,
        # wie eine Last aus zwei Zustaenden; gekuerzt wird er hier nicht, denn
        # ohne das Glied waere es eine andere Lastfolge (andere Schwingbreiten),
        # die niemand angelegt hat. Darum die Glieder von vor remove_load_case.
        def fehlt(f) -> bool:
            folge = erm_vorher.get(f.name) or getattr(f, "folge", None)
            if folge:
                return not set(folge) <= zustaende
            return (f.case_max not in behalten
                    or (f.case_min is not None and f.case_min not in behalten))
        weg = [f.name for f in m.fatigue_loads.values() if fehlt(f)]
        for name in weg:
            del m.fatigue_loads[name]
        for f in m.fatigue_loads.values():
            if getattr(f, "folge", None):
                # ein stehengebliebenes case_max/case_min eines Verlaufs, dessen
                # Lastfall hier fehlt, meldete Model.check bis B067 als FEHLER
                # und wies die Stellung ab, obwohl kein Nachweis es bei einem
                # Verlauf liest; seither prueft Model.check es nicht mehr.
                # Geleert wird es trotzdem, damit die Kopie keinen Verweis
                # auf einen Lastfall traegt, den es in ihr nicht gibt.
                if f.case_max and f.case_max not in m.load_cases and f.case_max not in m.combinations:
                    f.case_max = ""
                if f.case_min and f.case_min not in m.load_cases and f.case_min not in m.combinations:
                    f.case_min = None
        # Im Protokoll jede Ermuedungslast, die hier fehlt - auch die, die
        # remove_load_case schon genommen hat (Befund B105)
        weg = [n for n in erm_vorher if n not in m.fatigue_loads]
        if log is not None:
            log.append(f"  {self.name}: Lastfälle {', '.join(sorted(behalten))}")
            if k_weg:
                log.append(f"  {self.name}: Kombinationen ohne Lastfall entfallen: "
                           + ", ".join(k_weg))
            # die Alternativen einer ganz entfallenen Kombination nennt die
            # Zeile davor schon
            alt_weg = [f"{k} [{i}]" for k, i in alt_weg if k not in k_weg]
            if alt_weg:
                log.append(f"  {self.name}: Alternativen ohne Lastfall entfallen: "
                           + ", ".join(alt_weg))
            if weg:
                log.append(f"  {self.name}: Ermüdungslasten ohne Lastfall entfallen: "
                           + ", ".join(sorted(weg)))

    def _antrieb(self, m: Model, log: list = None):
        knoten, moment = self.antrieb
        name = f"Antrieb {self.name}"
        if name not in m.load_cases:
            m.add_load_case(name, "Q", f"Antriebsmoment in Stellung {self.name}",
                            activate=False)
        Mx, My, Mz = [float(v) for v in moment]
        m.load_node(int(knoten), Mx=Mx, My=My, Mz=Mz, case=name)
        for c in m.combinations.values():
            if any(f > 0 for f in c.factors.values()):
                c.factors.setdefault(name, 1.0)
            # ebenso jede Alternative einer Ergebniskombination (factors leer):
            # bis ec6448c blieb sie ohne Antrieb - am Kragarm eta 0,3702 wie
            # ohne Antrieb statt 0,4255 wie die gleichwertige K2 (Mz 50 kNm,
            # gemessen 23.09.2026)
            for a in c.alternativen:
                if any(f > 0 for f in a.values()):
                    a.setdefault(name, 1.0)
        if log is not None:
            log.append(f"  {self.name}: Antriebsmoment |M| = "
                       f"{np.linalg.norm(moment) / 1e3:.1f} kNm an Knoten {knoten + 1}")


@dataclass
class StellungsErgebnis:
    """Ergebnis einer einzelnen Stellung."""
    stellung: Stellung
    modell: Model = None
    analyse: object = None
    ergebnis: object = None
    nachweise: object = None
    eta: float = 0.0
    massgebend: str = ""
    u_max: float = 0.0
    reaktion: np.ndarray = None
    fehler: str = ""

    @property
    def warnungen(self) -> list:
        """Was der Stabnachweis dieser Stellung nicht fuehren konnte
        (Kombination ohne Ergebnis, etwa mit ``kombinationen=False``) - leer,
        wenn alles nachgewiesen ist oder keine Nachweise verlangt waren."""
        return list(getattr(self.nachweise, "warnungen", None) or [])

    @property
    def nachgewiesen(self) -> bool:
        """Ob der Stabnachweis ueberhaupt etwas nachgewiesen hat."""
        return bool(getattr(self.nachweise, "members", None))

    @property
    def ok(self) -> bool:
        # Nicht nachgewiesen ist nicht erfuellt - weder mit Warnungen
        # (Kombination ohne Ergebnis) noch ohne jeden gefuehrten Stabnachweis
        # (nachweise=False, kein Stab mit Nachweis). Im ausgelieferten Stand
        # 54b6f9a kam mit kombinationen=False keine Warnung: die Staebe wurden
        # gegen die Lastfaelle mit Faktor 1 nachgewiesen (Stauwand eta 0,2909
        # aus "Wasser", Halle 0,2776 aus "LF1", ok True); eta 0 mit ok True gab
        # es dort mit nur GZG-Kombinationen (Halle). Bis ec6448c galt eine
        # Stellung ohne Warnung und ohne Nachweis als ok (Klappe mit
        # nachweise=False: eta 0, ok True). Alles gemessen 23.09.2026.
        return (not self.fehler and self.nachgewiesen and not self.warnungen
                and self.eta <= 1.0 + 1e-9)


class Stellungsreihe:
    """Alle Stellungen eines Bauwerks: rechnen, umhüllen, auswerten.

    Jede Stellung wird als eigenes Modell gerechnet. Danach steht fest, welche
    Stellung für welchen Nachweis maßgebend ist - die Angabe, die bei
    beweglichen Brücken zählt.
    """

    def __init__(self, modell: Model, name: str = ""):
        self.basis = modell
        self.name = name or modell.name
        self.stellungen: list[Stellung] = []
        self.ergebnisse: list[StellungsErgebnis] = []
        self.log: list[str] = []
        #: nach rechnen(): Stellungen ohne zugewiesene Lastfaelle (nicht gerechnet)
        #: und Lastfaelle, die keiner Stellung zugewiesen sind
        self.ohne_lastfaelle: list[str] = []
        self.lastfaelle_ohne_stellung: list[str] = []

    def add(self, stellung: Stellung) -> Stellung:
        self.stellungen.append(stellung)
        return stellung

    def aus_winkeln(self, winkel, achse=(0, 1, 0), punkt=(0, 0, 0),
                    gruppen=None, praefix: str = "S", faelle=None) -> list:
        """Stellungsreihe aus einer Winkelliste erzeugen (gleiche Drehachse).
        ``faelle``: die Lastfaelle jeder Stellung - ohne sie rechnet die Reihe
        die Stellungen nicht (Stellung.faelle)."""
        out = []
        for i, w in enumerate(winkel, 1):
            out.append(self.add(Stellung(
                f"{praefix}{i}", float(w),
                "geschlossen" if abs(w) < 1e-9 else f"gedreht um {w:g}°",
                faelle=list(faelle or []),
                dreh_achse=achse, dreh_punkt=punkt, dreh_winkel=float(w),
                dreh_gruppen=list(gruppen or []))))
        return out

    # -- Rechnen ---------------------------------------------------------
    def rechnen(self, kombinationen: bool = True, nachweise: bool = False,
                workers: int = None, progress=None) -> "Umhuellende":
        """Alle Stellungen rechnen. Rueckgabe: Umhuellende ueber alle Stellungen."""
        from .. import solver
        self.ergebnisse = []
        self.log = []
        self.ohne_lastfaelle = []
        for i, st in enumerate(self.stellungen, 1):
            if progress:
                progress(f"Stellung {i}/{len(self.stellungen)}: {st.beschriftung()}")
            self.log.append(f"Stellung {st.beschriftung()}")
            if not st.faelle:
                # Nur Zugewiesenes wird gerechnet (02.10.2026) - bis dahin
                # rechnete eine Stellung ohne Zuordnung alle Lastfaelle
                self.log.append(f"  {st.name}: keine Lastfälle zugewiesen - nicht gerechnet")
                self.ohne_lastfaelle.append(st.name)
                continue
            e = StellungsErgebnis(stellung=st)
            try:
                m = st.modell(self.basis, self.log)
                e.modell = m
                fehler = [z for z in m.check() if z.startswith("FEHLER")]
                if fehler:
                    e.fehler = "; ".join(fehler[:3])
                    self.log.append(f"  {st.name}: {e.fehler}")
                    self.ergebnisse.append(e)
                    continue
                an = solver.solve_all(m, workers=workers,
                                      combinations=kombinationen and bool(m.combinations),
                                      envelopes=True)
                e.analyse = an
                r = _massgebend(an, m)
                e.ergebnis = r
                if r is not None and r.u is not None:
                    u = np.asarray(r.u).reshape(-1, 6)
                    e.u_max = float(np.abs(u[:, :3]).max())
                if r is not None and r.reactions is not None:
                    e.reaktion = np.asarray(r.reactions).reshape(-1, 6)
                if nachweise and m.members:
                    from ..ec3 import design as ec3d
                    e.nachweise = ec3d.check_members(m, an)
                    e.eta = float(e.nachweise.util_max)
                    schlimm = max(e.nachweise.members.values(),
                                  key=lambda x: x.util, default=None)
                    if schlimm is not None:
                        g = schlimm.governing or {}
                        e.massgebend = (f"{schlimm.member}: "
                                        + (g.get("name") or g.get("text") or "-"))
                self.log.append(f"  {st.name}: u_max = {e.u_max * 1e3:.3f} mm"
                                + (f", eta = {e.eta:.3f}" if nachweise else ""))
                # Kombinationen ohne Ergebnis (etwa mit kombinationen=False)
                # werden nicht mehr still durch die Lastfaelle ersetzt - das
                # Protokoll nennt jede, StellungsErgebnis.ok ist dann False,
                # und Umhuellende.bericht/warnhinweis sagen es beim eta
                for w in e.warnungen:
                    self.log.append(f"  {st.name}: WARNUNG {w}")
            except Exception as ex:      # noqa: BLE001
                e.fehler = f"{type(ex).__name__}: {ex}" if str(ex).strip() else type(ex).__name__
                self.log.append(f"  {st.name}: FEHLER {e.fehler}")
            self.ergebnisse.append(e)
        # Was keiner Stellung zugewiesen ist, wird nicht gerechnet - vermerkt
        # (Zusage an den Anwender, 24.09.2026)
        zugewiesen = {f for s in self.stellungen for f in (s.faelle or [])}
        self.lastfaelle_ohne_stellung = [n for n in self.basis.load_cases if n not in zugewiesen]
        if self.lastfaelle_ohne_stellung:
            self.log.append("Lastfälle in keiner Stellung (nicht gerechnet): "
                            + ", ".join(self.lastfaelle_ohne_stellung))
        return Umhuellende(self)

    # -- Zugriff ---------------------------------------------------------
    def __len__(self) -> int:
        return len(self.stellungen)

    def ergebnis(self, name: str) -> StellungsErgebnis:
        for e in self.ergebnisse:
            if e.stellung.name == name:
                return e
        raise KeyError(f"Stellung '{name}' nicht gerechnet")


class Umhuellende:
    """Größte Werte über alle Stellungen, mit der maßgebenden Stellung."""

    def __init__(self, reihe: Stellungsreihe):
        self.reihe = reihe
        self.ergebnisse = [e for e in reihe.ergebnisse if not e.fehler]
        self.fehlerhaft = [e for e in reihe.ergebnisse if e.fehler]

    @property
    def ohne_lastfaelle(self) -> list:
        """Stellungen ohne zugewiesene Lastfaelle - nicht gerechnet (seit
        02.10.2026; als Eigenschaft, damit aeltere Ablagen sie nicht brauchen)."""
        return list(getattr(self.reihe, "ohne_lastfaelle", None) or [])

    def nicht_gerechnet_text(self) -> str:
        """„ (1 mit FEHLER, 2 ohne Lastfälle, siehe Protokoll)“ - oder leer."""
        teile = ([f"{len(self.fehlerhaft)} mit FEHLER"] if self.fehlerhaft else []) \
            + ([f"{len(self.ohne_lastfaelle)} ohne Lastfälle"] if self.ohne_lastfaelle else [])
        return f" ({', '.join(teile)}, siehe Protokoll)" if teile else ""

    @property
    def eta(self) -> float:
        return max((e.eta for e in self.ergebnisse), default=0.0)

    @property
    def massgebende_stellung(self) -> str:
        if not self.ergebnisse:
            return ""
        e = max(self.ergebnisse, key=lambda x: x.eta)
        return e.stellung.beschriftung()

    @property
    def u_max(self) -> float:
        return max((e.u_max for e in self.ergebnisse), default=0.0)

    def stellung_mit_groesstem_u(self) -> str:
        if not self.ergebnisse:
            return ""
        return max(self.ergebnisse, key=lambda x: x.u_max).stellung.beschriftung()

    @property
    def unvollstaendig(self) -> list:
        """Die gerechneten Stellungen, deren Stabnachweis nicht alles
        nachweisen konnte (StellungsErgebnis.warnungen)."""
        return [e for e in self.ergebnisse if e.warnungen]

    @property
    def eta_bestimmt(self) -> bool:
        """True nur, wenn in einer Stellung wirklich ein Stabnachweis gefuehrt
        wurde - sonst ist eta = 0 keine Ausnutzung, mit oder ohne Warnungen,
        und auch dann, wenn gar keine Stellung gerechnet ist. Bis ec6448c hing
        es an den Warnungen: mit nachweise=False (Operation stellungen_rechnen
        mit "nachweise": false) oder ohne Stab mit Nachweis kam keine, und es
        hiess "eta = 0.000" (Stauwand, drei Stellungen, und die Klappe;
        gemessen 23.09.2026; Befund B036). Ohne jedes Ergebnis galt eta bis
        zum 23.09.2026 ebenso als bestimmt: „eta = 0.000“ nach zwei am FEHLER
        gescheiterten Stellungen (Befund B064). kurztext und bericht nennen
        den Fall ohne Ergebnis eigens („keine Stellung gerechnet“)."""
        return any(e.nachgewiesen for e in self.ergebnisse)

    def warnhinweis(self) -> str:
        """Leer, wenn alles nachgewiesen ist - sonst der Zusatz, der hinter
        jedes eta gehoert. Im ausgelieferten Stand 54b6f9a gab es mit
        ``rechnen(kombinationen=False, nachweise=True)`` keine Warnung: die
        Staebe wurden gegen die Lastfaelle mit Faktor 1 nachgewiesen
        (Stauwand "eta = 0.291" aus "Wasser", Halle "eta = 0.278" aus "LF1",
        0 WARN-Zeilen im Protokoll; gemessen 23.09.2026)."""
        unvoll = self.unvollstaendig
        if not unvoll:
            return ""
        n = sum(len(e.warnungen) for e in unvoll)
        return (f" – NICHT VOLLSTÄNDIG NACHGEWIESEN: {n} Warnung{'en' if n > 1 else ''} in "
                + ", ".join(e.stellung.name for e in unvoll) + " (siehe Protokoll)")

    def kurztext(self) -> str:
        """Die eine Zeile nach dem Rechnen: eta mit maßgebender Stellung und
        dem Warnhinweis - oder, wenn nichts gerechnet oder nachgewiesen
        wurde, genau das."""
        if not self.ergebnisse:
            return "eta nicht bestimmt – keine Stellung gerechnet" + self.nicht_gerechnet_text()
        if not self.eta_bestimmt:
            return "eta nicht bestimmt – kein Stabnachweis geführt" + self.warnhinweis()
        return (f"eta = {self.eta:.3f}"
                + (f", maßgebend {self.massgebende_stellung}" if self.massgebende_stellung
                   else "")
                + self.warnhinweis())

    def reaktionen(self) -> dict:
        """Größte Auflagerkraft je Knoten und Richtung über alle Stellungen.

        Rueckgabe: {knoten: {"Fx": (wert, stellung), ...}} - nur Knoten mit Lager.
        """
        out: dict = {}
        for e in self.ergebnisse:
            if e.reaktion is None:
                continue
            for s in e.modell.supports:
                n = int(s.node)
                zeile = e.reaktion[n]
                d = out.setdefault(n, {})
                for k, name in enumerate(("Fx", "Fy", "Fz", "Mx", "My", "Mz")):
                    v = float(zeile[k])
                    alt = d.get(name)
                    if alt is None or abs(v) > abs(alt[0]):
                        d[name] = (v, e.stellung.beschriftung())
        return out

    def kurve(self) -> list:
        """[(Winkel, eta, u_max, Stellungsname)] - für die Kurve über den Winkel."""
        return sorted([(e.stellung.winkel, e.eta, e.u_max, e.stellung.name)
                       for e in self.ergebnisse])

    def bericht(self) -> str:
        z = [f"Stellungen des Systems - {self.reihe.name}", "=" * 78,
             f"{'Stellung':<10s}{'Winkel':>9s}{'u_max':>12s}{'eta':>9s}  Beschreibung"]
        for e in self.reihe.ergebnisse:
            st = e.stellung
            if e.fehler:
                z.append(f"{st.name:<10s}{st.winkel:>8.1f}°{'-':>12s}{'-':>9s}  "
                         f"FEHLER: {e.fehler[:40]}")
            else:
                # ohne jeden gefuehrten Nachweis ist eta = 0 keine Zahl, auch
                # ohne Warnung (nachweise=False, kein Stab mit Nachweis)
                eta = f"{e.eta:>9.3f}" if e.nachgewiesen else f"{'-':>9s}"
                z.append(f"{st.name:<10s}{st.winkel:>8.1f}°{e.u_max * 1e3:>10.3f} mm"
                         f"{eta}  {st.beschreibung}"
                         + ("  (NICHT VOLLSTÄNDIG NACHGEWIESEN)" if e.warnungen else ""))
        z.append("-" * 78)
        if not self.ergebnisse:
            z.append("Umhüllende: eta nicht bestimmt – keine Stellung gerechnet"
                     + (" (siehe „Nicht gerechnet“)" if self.fehlerhaft or self.ohne_lastfaelle else ""))
        elif not self.eta_bestimmt:
            z.append("Umhüllende: eta nicht bestimmt – in keiner Stellung wurde ein "
                     "Stabnachweis geführt"
                     + (" (siehe „Nicht nachgewiesen“)" if self.unvollstaendig else ""))
        else:
            z.append(f"Umhüllende: eta = {self.eta:.3f}"
                     + (f", maßgebend in {self.massgebende_stellung}"
                        if self.massgebende_stellung else "")
                     + (" – NICHT VOLLSTÄNDIG NACHGEWIESEN (siehe „Nicht nachgewiesen“)"
                        if self.unvollstaendig else ""))
        z.append(f"größte Verformung {self.u_max * 1e3:.3f} mm"
                 + (f" in {self.stellung_mit_groesstem_u()}" if self.ergebnisse else ""))
        r = self.reaktionen()
        if r:
            z.append("")
            z.append("Größte Auflagerkräfte über alle Stellungen:")
            z.append(f"{'Knoten':>8s}{'F_z [kN]':>12s}  maßgebend")
            for n in sorted(r):
                v, st = r[n].get("Fz", (0.0, ""))
                z.append(f"{n + 1:>8d}{v / 1e3:>12.2f}  {st}")
        if self.unvollstaendig:
            z.append("")
            z.append("Nicht nachgewiesen:")
            for e in self.unvollstaendig:
                w = e.warnungen
                z.append(f"  {e.stellung.beschriftung()}: {len(w)} "
                         f"Warnung{'en' if len(w) > 1 else ''}")
                z += [f"    WARNUNG: {x}" for x in w[:5]]
                if len(w) > 5:
                    z.append(f"    … und {len(w) - 5} weitere (siehe Protokoll)")
        if self.fehlerhaft or self.ohne_lastfaelle:
            z.append("")
            z.append("Nicht gerechnet:")
            for e in self.fehlerhaft:
                z.append(f"  {e.stellung.beschriftung()}: {e.fehler[:60]}")
            for name in self.ohne_lastfaelle:
                z.append(f"  {name}: keine Lastfälle zugewiesen")
        rest = list(getattr(self.reihe, "lastfaelle_ohne_stellung", None) or [])
        if rest:
            z.append("")
            z.append("Lastfälle in keiner Stellung (nicht gerechnet): " + ", ".join(rest[:20])
                     + (f" … und {len(rest) - 20} weitere" if len(rest) > 20 else ""))
        return "\n".join(z)
