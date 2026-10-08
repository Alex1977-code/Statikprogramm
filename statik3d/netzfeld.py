"""
Groessenfeld: die gewuenschte Kantenlaenge an jedem Ort - **eine** Groesse,
die alle Wege des Vernetzers lesen.

Warum es das braucht (Uebergabe vom 20.09.2026, Drehlager V15_4): 640 932
Tetraeder auf 108 Koerper, 85 % davon in acht Koerpern, alle acht mit der
**gleichen** Ziellaenge 50 mm vernetzt. Ihre Elementzahl kommt nicht aus h,
sondern aus der Huelle - Bohrungsraender, Kraenze, Ausrundungen mit 18 Grad
je Bogenabschnitt, ob die Bohrung nun etwas traegt oder nicht - und aus dem
Groessenfeld ``h_lokal = min(h, Randkante + WACHSTUM * Abstand)`` in
:func:`mesher3d.tetraedern`, das eine reine Funktion der Huelle ist. Es gab
keinen Kanal, ueber den eine Spannung, ein Fehlerindikator oder eine benannte
Stelle die Feinheit setzen konnte. Dieser Kanal ist das Groessenfeld.

Das Feld ist eine **Wolke von Quellen** (Ort, Kantenlaenge, Reichweite): im
Umkreis der Reichweite gilt die Kantenlaenge der Quelle, ausserhalb waechst
sie mit dem Wachstum WACHSTUM je Laengeneinheit - dieselbe Regel, mit der die
Kraenze in der Flaeche und das Tetraedernetz im Inneren schon arbeiten. Der
Wert an einem Ort ist das Minimum ueber alle Quellen, gedeckelt durch h_max:

    h(x) = min( h_max, min_k [ h_k + WACHSTUM * max(0, |x - x_k| - r_k) ] )

Weil jede Quelle mit demselben Wachstum kegelfoermig wirkt, ist das Feld von
sich aus **gradiert** - kein Nachbarelement ist mehr als (1 + WACHSTUM)-mal
so gross wie seines; niemand muss eine Gradation nachtraeglich glaetten.

Woher die Quellen kommen:

* **Netzverfeinerungen** in den Netzeinstellungen (``netz.verfeinerungen``):
  eine Kugel um einen Punkt, eine benannte Flaeche, Linie oder ein Koerper
  mit einer Kantenlaenge - was der Anwender fein haben will.
* **Feldpunkte** (``netz.feldpunkte``): Ort und Kantenlaenge je Punkt, wie
  sie der Fehlerschaetzer (:mod:`statik3d.netzfehler`) aus einem gerechneten
  Ergebnis ableitet - was das Ergebnis fein braucht.

Und wohin das Feld geht:

* in :func:`mesher3d.tetraedern` als weitere Schranke der Sollgroesse,
* in :class:`mesher3d.Linienteilung` als Teilung und Punktverteilung der
  Randlinien, in :func:`mesher3d._dreiecke_2d` als Weite des Flaechennetzes
  - denn die Huelle ist der Hebel: 3,4 Tetraeder je Randdreieck,
* an gmsh als Groessen-Rueckruf (``setSizeCallback``) und an MMG3D als
  ``.sol``-Metrik (:mod:`statik3d.vernetzer_extern`). Gemessen am Quader
  1 x 0,6 x 0,2 m, Huelle 50 mm, Feld 5 mm um einen Innenpunkt, 80 mm sonst
  (20.09.2026): gmsh HXT ueber den Rueckruf 8,1 mm im Zielbereich (0,1 s,
  11 837 Rueckrufe fuer 6 152 Tetraeder), MMG3D ueber die Metrik 12,8 mm bei
  fester Huelle und Guete min 0,507 (0,4 s). Der Weg ueber eine PostView-Liste
  taugt dagegen nicht: er interpoliert auf dem Hintergrundnetz und traf im
  Zielbereich 25 mm statt 5.

Das Feld haengt am Modell (``model.groessenfeld``), wird einmal je Lauf
gebildet (:func:`aufbauen`) und geht mit dem Modell in die Arbeitsprozesse.
Es wird **nicht** gespeichert - gespeichert werden seine Quellen in den
Netzeinstellungen, aus denen es jederzeit wieder entsteht.

Dazu die zweite Frage, die dieses Modul beantwortet: **welche Flaechen
bedeuten etwas?** Eine Bohrung, in der ein Bolzen sitzt (Kontakt), eine
Flaeche mit Last oder Lager, eine Flaeche, die zwei Koerper teilen - dort
entscheidet sich der Nachweis. Eine Durchgangsbohrung fuer eine Schraube,
die im Modell nicht vorkommt, oder eine Ausrundung tragen nichts; ihre Form
muss stimmen, nicht ihre Kerbspannung. Mit ``netz.nebenflaechen_grob``
bekommen die Linien solcher Nebenflaechen den groben Bogenwinkel
(:data:`BOGENWINKEL_GROB`), die bedeutenden behalten :data:`mesher3d.BOGENWINKEL`.
"""
from __future__ import annotations

import numpy as np

#: Wie schnell die Kantenlaenge von einer Quelle weg waechst [m je m].
#: Derselbe Wert wie mesher3d.WACHSTUM - das Feld und die Huellenregel
#: muessen dieselbe Steigung haben, sonst widersprechen sie sich am Rand.
WACHSTUM = 0.35

#: Bogenwinkel je Abschnitt an den Linien einer **Nebenflaeche** [Grad], wenn
#: ``netz.nebenflaechen_grob`` gesetzt ist: 45 Grad heisst acht Abschnitte je
#: Vollkreis. Das eingeschriebene Achteck hat 10 % weniger Flaeche als der
#: Kreis - fuer eine Bohrung, die nichts traegt, ist ihr Rauminhalt gegen den
#: des Bauteils belanglos, und die Kerbspannung dort prueft niemand. Traegt
#: sie doch (der Fehlerschaetzer sagt es), macht das Feld sie wieder fein.
BOGENWINKEL_GROB = 45.0

#: Hoechstzahl der Quellen, die bei der Auswertung je Punkt angesehen werden.
#: Die naechste Quelle ist nicht zwingend die massgebende (eine etwas fernere
#: mit kleinerem h kann kleiner sein); nach dem Ausduennen (siehe
#: Groessenfeld.abschliessen) sind die verbliebenen Quellen aber voneinander
#: unabhaengig, und unter den zwoelf naechsten ist die massgebende immer.
#: tests/test_netzfeld.py misst das gegen die Auswertung ueber alle Quellen.
NACHBARN = 12

#: Toleranz, unter der eine Quelle als von einer anderen ueberdeckt gilt und
#: wegfaellt (5 %): eine Quelle, deren Kegel ueberall hoechstens 5 % ueber
#: dem einer anderen liegt, aendert am Netz nichts.
UEBERDECKUNG = 0.05


class Groessenfeld:
    """Skalares Groessenfeld aus Kugelquellen mit Wachstumsschranke.

    ``h_max`` ist die groesste Kantenlaenge, die das Feld je nennt (die des
    Koerpers oder der Netzeinstellungen); ohne Quellen ist das Feld ueberall
    h_max und damit ohne Wirkung. ``bogenwinkel`` ist der Winkel je Abschnitt
    fuer Linien, die in ``grobe_linien`` stehen (siehe :func:`bedeutung`).
    """

    def __init__(self, h_max: float, wachstum: float = WACHSTUM):
        self.h_max = float(h_max) if h_max and h_max > 0 else float("inf")
        self.wachstum = max(float(wachstum), 1e-9)
        self._X: list = []
        self._h: list = []
        self._r: list = []
        self.X = np.zeros((0, 3))
        self.h = np.zeros(0)
        self.r = np.zeros(0)
        self._baum = None
        self.grobe_linien: frozenset = frozenset()
        self.bogenwinkel_grob: float = BOGENWINKEL_GROB
        #: Linien mit feinerem Bogenwinkel {Name: Grad} - die Boegen der
        #: Kontakt- und Lagerflaechen bei Fein (siehe :func:`fein_ziele`)
        self.feine_linien: dict = {}
        #: Traegt das Feld Quellen von Fein? Dann verdichtet das Flaechennetz
        #: im Dreiecksgitter (mesher3d._verdichten_2d_dreieck), sonst wie
        #: bisher - Mittel und Entwurf bleiben bitgleich
        self.dreiecksgitter: bool = False
        #: Woher die Quellen stammen, fuer das Protokoll: {Art: Anzahl}
        self.herkunft: dict = {}

    # ---- Quellen -----------------------------------------------------------
    def punkte(self, X, h, reichweite=0.0, art: str = "punkte") -> int:
        """Quellen hinzufuegen: Orte (n, 3), Kantenlaenge (n,) oder Zahl,
        Reichweite (n,) oder Zahl. Rueckgabe: Zahl der aufgenommenen Quellen
        (Quellen mit h >= h_max wirken nicht und werden weggelassen)."""
        X = np.atleast_2d(np.asarray(X, float)).reshape(-1, 3)
        if not len(X):
            return 0
        h = np.broadcast_to(np.asarray(h, float), (len(X),)).astype(float)
        r = np.broadcast_to(np.asarray(reichweite, float), (len(X),)).astype(float)
        gut = np.isfinite(h) & (h > 0) & (h < self.h_max) & np.all(np.isfinite(X), axis=1)
        if not gut.any():
            return 0
        self._X.append(X[gut])
        self._h.append(h[gut])
        self._r.append(np.maximum(r[gut], 0.0))
        self._baum = None
        n = int(gut.sum())
        self.herkunft[art] = self.herkunft.get(art, 0) + n
        return n

    def kugel(self, mitte, radius: float, h: float, art: str = "kugel") -> int:
        """Eine Kugel, in der die Kantenlaenge h gilt; ausserhalb waechst sie."""
        return self.punkte(np.asarray(mitte, float).reshape(1, 3), h, max(float(radius), 0.0), art)

    @property
    def leer(self) -> bool:
        return not self._X and not len(self.X)

    def abschliessen(self) -> int:
        """Die Quellen zusammenfuehren, ueberdeckte entfernen, Suchbaum bauen.
        Rueckgabe: Zahl der verbliebenen Quellen.

        Eine Quelle j ist ueberdeckt, wenn eine andere Quelle i ueberall
        hoechstens UEBERDECKUNG ueber ihr liegt. Weil beide Kegel dieselbe
        Steigung haben, genuegt dafuer die Pruefung am Ort von j:

            h_i + g * max(0, d_ij + r_j - r_i) <= h_j * (1 + UEBERDECKUNG)

        Zwei Stufen, beide ohne Schleife ueber die Quellen - eine Schleife
        mit Kugelabfrage je Quelle brauchte bei 5 000 Quellen 0,14 s, bei
        den Hunderttausenden eines Drehlager-Durchgangs Minuten:

        1. **Zellen**: je Groessenstufe (Oktave von h) und Zelle der Weite h
           bleibt nur die feinste Quelle. Zwei Quellen mit aehnlichem h in
           derselben Zelle sagen dasselbe.
        2. **Nachbarn**: jede Quelle wird gegen ihre NACHBARN naechsten
           geprueft; ueberdeckt eine feinere davon sie (Bedingung oben, mit
           der halben Toleranz, weil zwei Stufen aufeinander folgen koennen),
           faellt sie weg. Eine Ueberdeckung durch eine ferne Quelle bleibt
           dabei unentdeckt - die Quelle bleibt dann stehen und aendert am
           Feld nichts, denn das Minimum nimmt ohnehin die feinere.
        """
        from scipy.spatial import cKDTree
        if self._X:
            X = np.vstack([self.X] + self._X) if len(self.X) else np.vstack(self._X)
            h = np.concatenate([self.h] + self._h) if len(self.h) else np.concatenate(self._h)
            r = np.concatenate([self.r] + self._r) if len(self.r) else np.concatenate(self._r)
            self._X, self._h, self._r = [], [], []
        else:
            X, h, r = self.X, self.h, self.r
        if not len(X):
            self.X, self.h, self.r, self._baum = np.zeros((0, 3)), np.zeros(0), np.zeros(0), None
            return 0
        g = self.wachstum
        ordnung = np.argsort(h, kind="stable")
        X, h, r = X[ordnung], h[ordnung], r[ordnung]
        tol = 1.0 + 0.5 * UEBERDECKUNG          # zwei Stufen, zusammen UEBERDECKUNG
        # 1) Zellen je Groessenstufe: die feinste Quelle einer Zelle vertritt
        # sie; jede andere faellt weg, wenn die Vertreterin sie **nachweislich**
        # ueberdeckt (Bedingung oben) - blind zusammenlegen ginge nicht, eine
        # Quelle mit grosser Reichweite in derselben Zelle sagt etwas anderes.
        h_ref = float(h[0])
        stufe = np.floor(np.log2(np.maximum(h, 1e-300) / h_ref)).astype(np.int64)
        zelle = 0.5 * h_ref * (2.0 ** stufe)
        schl = np.column_stack([stufe, np.floor(X / zelle[:, None]).astype(np.int64)])
        _, erste, gruppe = np.unique(schl, axis=0, return_index=True, return_inverse=True)
        rep = erste[np.asarray(gruppe).ravel()]            # die feinste je Zelle (h ist sortiert)
        d = np.linalg.norm(X - X[rep], axis=1)
        wert = h[rep] + g * np.maximum(0.0, d + r - r[rep])
        weg = (rep != np.arange(len(X))) & (wert <= h * tol)
        X, h, r = X[~weg], h[~weg], r[~weg]
        # 2) Nachbarn: ueberdeckt eine feinere Quelle unter den naechsten?
        n = len(X)
        if n > 1:
            k = min(NACHBARN + 1, n)
            d, i = cKDTree(X).query(X, k=k)
            d, i = d[:, 1:], i[:, 1:]                     # die Quelle selbst nicht
            hj = h[:, None]
            wert = h[i] + g * np.maximum(0.0, d + r[:, None] - r[i])
            feiner = (h[i] < hj) | ((h[i] == hj) & (i < np.arange(n)[:, None]))
            weg = (feiner & (wert <= hj * tol)).any(axis=1)
            X, h, r = X[~weg], h[~weg], r[~weg]
        self.X, self.h, self.r = X, h, r
        self._baum = cKDTree(self.X) if len(self.X) else None
        return int(len(self.X))

    def _fertig(self):
        if self._X or (self._baum is None and len(self.X)):
            self.abschliessen()

    # ---- Auswertung ---------------------------------------------------------
    def __call__(self, X) -> np.ndarray:
        """Die Kantenlaenge an jedem Ort in X (n, 3) -> (n,) - **exakt**.

        Schneller Weg: die NACHBARN naechsten Quellen. Ob darunter die
        massgebende ist, sagt die Lipschitz-Schranke: die Quelle mit dem
        kleinsten Wert v_1 unter den naechsten liegt hoechstens im Abstand

            R = (v_1 - h_min) / g + r_max

        vom Ort - eine fernere kaeme mit ihrem Wachstum nicht mehr unter
        v_1. Reicht die Suche bis dahin (d_k >= R), ist das Minimum
        gefunden; sonst werden fuer diese Orte alle Quellen bis R geholt.
        Gemessen an 600 000 Zufallsquellen in 1 m^3 mit h von 3 bis 70 mm:
        siehe tests/test_netzfeld.py - die schnelle Antwort war dort mit
        zwoelf Nachbarn bis 18 % zu grob, mit der Schranke ist sie exakt.
        """
        X = np.atleast_2d(np.asarray(X, float)).reshape(-1, 3)
        aus = np.full(len(X), self.h_max)
        self._fertig()
        if self._baum is None or not len(X):
            return aus
        n_q, g = len(X), self.wachstum
        k = min(NACHBARN, len(self.X))
        d, i = self._baum.query(X, k=k)
        d = np.atleast_2d(d.reshape(n_q, k))
        i = np.atleast_2d(i.reshape(n_q, k))
        wert = self.h[i] + g * np.maximum(0.0, d - self.r[i])
        v = wert.min(axis=1)
        h_min = float(self.h.min())
        r_max = float(self.r.max()) if len(self.r) else 0.0
        R = (v - h_min) / g + r_max
        unsicher = np.flatnonzero((d[:, -1] < R) & (k < len(self.X)) & (v > h_min * (1.0 + 1e-12)))
        for j in unsicher:
            kand = self._baum.query_ball_point(X[j], float(R[j]))
            if len(kand) > k:
                kand = np.asarray(kand, int)
                dj = np.linalg.norm(self.X[kand] - X[j], axis=1)
                v[j] = min(v[j], float((self.h[kand] + g * np.maximum(0.0, dj - self.r[kand])).min()))
        return np.minimum(aus, v)

    def genau(self, X) -> np.ndarray:
        """Dieselbe Auswertung ueber **alle** Quellen - langsam, der Pruefstein
        fuer die schnelle Auswertung ueber die NACHBARN naechsten."""
        X = np.atleast_2d(np.asarray(X, float)).reshape(-1, 3)
        self._fertig()
        aus = np.full(len(X), self.h_max)
        if not len(self.X):
            return aus
        for j in range(len(X)):
            d = np.linalg.norm(self.X - X[j], axis=1)
            aus[j] = min(self.h_max, float((self.h + self.wachstum * np.maximum(0.0, d - self.r)).min()))
        return aus

    def wirkt(self, X, h: float) -> bool:
        """Liegt das Feld irgendwo in X unter h? (Dann lohnt es, es zu lesen.)"""
        if self.leer:
            return False
        return bool((self(X) < float(h) * (1.0 - 1e-9)).any())

    def bogenwinkel(self, linie: str, vorgabe: float) -> float:
        """Der Bogenwinkel je Abschnitt fuer diese Linie: an einer Linie mit
        feinerem Winkel (Fein, :data:`feine_linien`) der kleinere von beiden,
        an einer Nebenflaeche der grobe, sonst die Vorgabe."""
        fein = (getattr(self, "feine_linien", None) or {}).get(linie)
        if fein:
            return min(float(fein), float(vorgabe))
        return self.bogenwinkel_grob if linie in self.grobe_linien else float(vorgabe)

    # ---- Ausgabe -----------------------------------------------------------
    def als_feldpunkte(self) -> list:
        """Die Quellen als [[x, y, z, h, r], ...] - so stehen sie in den
        Netzeinstellungen (``netz.feldpunkte``) und in der Datei."""
        self._fertig()
        return [[float(x), float(y), float(z), float(h), float(r)]
                for (x, y, z), h, r in zip(self.X, self.h, self.r)]

    def sol_schreiben(self, pfad: str, Pn: np.ndarray, h_max: float = 0.0) -> np.ndarray:
        """Skalare Metrik je Knoten im Medit-Format (.sol) fuer MMG3D.
        Rueckgabe: die geschriebenen Werte."""
        Pn = np.asarray(Pn, float).reshape(-1, 3)
        werte = self(Pn)
        if h_max and h_max > 0:
            werte = np.minimum(werte, float(h_max))
        with open(pfad, "w", encoding="ascii") as f:
            f.write("MeshVersionFormatted 2\nDimension 3\n")
            f.write(f"SolAtVertices\n{len(werte)}\n1 1\n")
            f.write("\n".join(f"{w:.9g}" for w in werte))
            f.write("\nEnd\n")
        return werte

    def gmsh_rueckruf(self, h_max: float = 0.0):
        """Der Groessen-Rueckruf fuer ``gmsh.model.mesh.setSizeCallback``:
        das Minimum aus gmsh' eigener Groesse am Ort (``lc``, aus Huelle und
        Optionen) und dem Feld. Ein Punkt je Aufruf - gmsh fragt so; am
        Quader waren es acht Aufrufe je Netzknoten."""
        self._fertig()
        cap = float(h_max) if h_max and h_max > 0 else self.h_max

        def rueckruf(dim, tag, x, y, z, lc):
            wert = float(self(np.array([[x, y, z]]))[0])
            wert = min(wert, cap)
            if lc is not None and lc > 0:
                wert = min(wert, float(lc))
            return wert
        return rueckruf

    # ---- pickle: der Suchbaum wird im Arbeitsprozess neu gebaut -------------
    def __getstate__(self):
        self._fertig()
        d = dict(self.__dict__)
        d["_baum"] = None
        return d

    def __setstate__(self, d):
        self.__dict__.update(d)
        self._baum = None


# --------------------------------------------------------------------------
# Bedeutung der Flaechen: wo entscheidet sich der Nachweis?
# --------------------------------------------------------------------------
def bedeutung(model) -> dict:
    """Welche Flaechen und Linien bedeuten etwas - und warum.

    Rueckgabe {"flaechen": {Name: Grund}, "linien": {Name: Grund},
    "neben_flaechen": set, "neben_linien": set}. Bedeutend ist eine Flaeche,
    wenn

    * eine **Last** an ihr haengt (Geometrielast auf der Flaeche oder ihrem
      Koerper, Linienlast auf einer ihrer Linien),
    * ein **Lager** auf ihr liegt (Flaechenlager an Flaechen, Linienlager an
      Linien),
    * eine **Kontaktbedingung** sie nennt (freigegebene Flaeche oder
      Gegenflaeche) - dort sitzt der Bolzen in der Bohrung,
    * sie **zwei Koerpern** gehoert (gemeinsame Flaeche - dort ist die Karte
      ohnehin bindend),
    * eine **Netzverfeinerung** sie oder eine ihrer Linien nennt,
    * ein Stabende oder eine starre Scheibe in sie integriert ist.

    Alles andere ist eine Nebenflaeche: die Wand einer Durchgangsbohrung ohne
    Bolzen, eine Ausrundung, die Aussenhaut. Ihre Linien duerfen groeber
    geteilt werden - der Fehlerschaetzer holt zurueck, was doch traegt.
    """
    flaechen: dict = {}
    linien: dict = {}

    def merke_f(name, grund):
        if name and name in model.flaechen and name not in flaechen:
            flaechen[name] = grund

    def merke_l(name, grund):
        if name and name in model.lines and name not in linien:
            linien[name] = grund

    # Lasten
    for lc in getattr(model, "load_cases", {}).values():
        for gl in getattr(lc, "geometrielasten", None) or []:
            if getattr(gl, "art", "flaeche") == "koerper":
                k = model.koerper.get(gl.ziel)
                for fn in (k.flaechen if k is not None else []):
                    merke_f(fn, f"Last auf Körper {gl.ziel}")
            else:
                merke_f(getattr(gl, "ziel", ""), "Last")
        for ll in getattr(lc, "linienlasten", None) or []:
            if getattr(ll, "art", "stab") == "linie":
                merke_l(getattr(ll, "ziel", ""), "Linienlast")
    # Lager
    for ss in getattr(model, "surface_supports", None) or []:
        for fn in (getattr(ss, "flaechen", None) or []):
            merke_f(fn, f"Flächenlager {ss.name}")
    for ls in getattr(model, "line_supports", None) or []:
        for ln in (getattr(ls, "linien", None) or []):
            merke_l(ln, f"Linienlager {ls.name}")
    # Kontakt
    for kb in (getattr(model, "kontaktbedingungen", None) or {}).values():
        for fn in list(getattr(kb, "flaechennamen", None) or []) + list(getattr(kb, "gegenflaechen", None) or []):
            merke_f(fn, f"Kontakt {kb.name}")
    # Gemeinsame Flaechen
    zaehler: dict = {}
    for k in (getattr(model, "koerper", None) or {}).values():
        for fn in (k.flaechen or []):
            zaehler[fn] = zaehler.get(fn, 0) + 1
    for fn, n in zaehler.items():
        if n > 1:
            merke_f(fn, "gemeinsame Fläche")
    # Netzverfeinerungen
    for v in (getattr(getattr(model, "netz", None), "verfeinerungen", None) or []):
        art = str(v.get("art", ""))
        if art == "flaeche":
            merke_f(v.get("name", ""), "Netzverfeinerung")
        elif art == "linie":
            merke_l(v.get("name", ""), "Netzverfeinerung")
        elif art == "koerper":
            k = model.koerper.get(v.get("name", ""))
            for fn in (k.flaechen if k is not None else []):
                merke_f(fn, "Netzverfeinerung")
    # Integrierte Knoten und Linien (Stabenden, starre Scheiben)
    for f in model.flaechen.values():
        if getattr(f, "integrierte_knoten", None) or getattr(f, "integrierte_linien", None):
            merke_f(f.name, "integrierter Knoten oder Linie")
    # Die Linien bedeutender Flaechen sind bedeutend; eine bedeutende Linie
    # macht ihre Flaechen aber nicht bedeutend (sonst zoege ein Linienlager
    # die ganze Platte mit).
    for fn in list(flaechen):
        f = model.flaechen.get(fn)
        if f is None:
            continue
        for ln in list(f.linien or []) + [x for loch in (f.oeffnungen or []) for x in loch]:
            merke_l(ln, flaechen[fn])
    # Nebenflaechen: alle Randflaechen von Koerpern, die nicht bedeutend sind
    koerperflaechen = {fn for k in (getattr(model, "koerper", None) or {}).values()
                       for fn in (k.flaechen or [])}
    neben_f = {fn for fn in koerperflaechen if fn not in flaechen}
    neben_l: set = set()
    for fn in neben_f:
        f = model.flaechen.get(fn)
        if f is None:
            continue
        for ln in list(f.linien or []) + [x for loch in (f.oeffnungen or []) for x in loch]:
            if ln not in linien:
                neben_l.add(ln)
    return {"flaechen": flaechen, "linien": linien,
            "neben_flaechen": neben_f, "neben_linien": neben_l}


# --------------------------------------------------------------------------
# Das Feld aus dem Modell
# --------------------------------------------------------------------------
def _gitter_im_polygon(ringe: list, abstand: float) -> np.ndarray:
    """Gitterpunkte (Zellmitten, Weite hoechstens ``abstand``) innerhalb der
    ebenen Ringe (aussen, Loecher) - leer, wenn es zu viele wuerden."""
    from .mesher3d import _in_polygon_2d
    lo, hi = ringe[0].min(axis=0), ringe[0].max(axis=0)
    nx = int(np.ceil((hi[0] - lo[0]) / abstand))
    ny = int(np.ceil((hi[1] - lo[1]) / abstand))
    if not 0 < nx * ny <= 250_000:
        return np.zeros((0, 2))
    u = lo[0] + (np.arange(nx) + 0.5) * (hi[0] - lo[0]) / nx
    v = lo[1] + (np.arange(ny) + 0.5) * (hi[1] - lo[1]) / ny
    K = np.stack(np.meshgrid(u, v, indexing="ij"), -1).reshape(-1, 2)
    return K[_in_polygon_2d(K, ringe)]


def _flaechenpunkte_krumm(model, f, punkte: list, abstand: float) -> np.ndarray:
    """Punkte auf einer **gekruemmten** Flaeche (Paket F1, 07.10.2026).

    Bis zum 07.10.2026 lag das Gitter in der Ausgleichsebene des Randes: an
    einer halben Bohrungswand r = 60 mm bis 23 mm neben der Flaeche, und die
    Quellen deckten die Wand nicht (gemessen mit tests/test_fein_smart.py).
    Jetzt liegt jeder Punkt auf der wahren Flaeche:

    * **Zylinder** (:func:`mesher3d.zylinderpassung`): das Gitter in der
      Abwicklung (Bogenlaenge quer, Achse laengs), wie
      :func:`mesher3d._zylindernetz` sie vernetzt, und zurueck auf den
      Zylinder gehoben - gleichmaessig in der Bogenlaenge;
    * **Kegel, Kugel, windschiefes Viereck**: das Gitter in der
      Ausgleichsebene, mit dem Projektor der Flaeche
      (:func:`mesher3d.flaechenprojektoren`) auf die Flaeche gesetzt;
    * jede andere gekruemmte Flaeche: nur der Rand - ein Punkt daneben waere
      schlechter als keiner.
    """
    from types import SimpleNamespace

    from . import mesher3d as M3
    alle = np.vstack(punkte)
    if abstand <= 0:
        return alle
    achse = M3.zylinderpassung(model, f, alle)
    if achse is not None:
        c, d, r = np.asarray(achse[0], float), np.asarray(achse[1], float), float(achse[2])
        d = d / max(float(np.linalg.norm(d)), 1e-300)
        hilf = np.array([1.0, 0.0, 0.0]) if abs(d[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        e1 = np.cross(hilf, d)
        e1 /= np.linalg.norm(e1)
        e2 = np.cross(d, e1)
        rel = alle - c
        w = np.sort(np.arctan2(rel @ e2, rel @ e1))
        luecken = np.diff(np.concatenate([w, w[:1] + 2 * np.pi]))
        schnitt = w[int(np.argmax(luecken))] + float(luecken.max()) / 2.0

        def eben(P3):
            rel3 = P3 - c
            wi = np.mod(np.arctan2(rel3 @ e2, rel3 @ e1) - schnitt, 2 * np.pi)
            return np.stack([r * wi, rel3 @ d], axis=1)
        K = _gitter_im_polygon([eben(R) for R in punkte], abstand)
        if not len(K):
            return alle
        wi = K[:, 0] / r + schnitt
        innen = c + np.outer(K[:, 1], d) + r * (np.outer(np.cos(wi), e1) + np.outer(np.sin(wi), e2))
        return np.vstack([alle, innen])
    try:
        proj = M3.flaechenprojektoren(model, SimpleNamespace(flaechen=[f.name])).get(f.name)
    except Exception:                       # noqa: BLE001 - dann nur der Rand
        proj = None
    if proj is None:
        return alle
    c, e1, e2, _n, _abw = M3.ausgleichsebene(alle)
    K = _gitter_im_polygon([np.stack([(R - c) @ e1, (R - c) @ e2], axis=1) for R in punkte], abstand)
    if not len(K):
        return alle
    return np.vstack([alle, proj(c + K[:, :1] * e1 + K[:, 1:] * e2)])


def _flaechenpunkte(model, f, abstand: float) -> np.ndarray:
    """Punkte auf einer Flaeche im Abstand ``abstand``: der Rand abgetastet
    und ein Gitter in der Ausgleichsebene innerhalb des Randpolygons - an
    einer gekruemmten Flaeche auf der wahren Flaeche
    (:func:`_flaechenpunkte_krumm`, seit 07.10.2026)."""
    from .mesher3d import _in_polygon_2d, ausgleichsebene, ist_eben
    rand = np.asarray(f.randpunkte(model, 24), float)
    if len(rand) < 3:
        return np.zeros((0, 3))
    loecher = [np.asarray(P, float) for P in f.oeffnungspunkte(model, 24)]
    punkte = [rand] + loecher
    if not ist_eben(np.vstack(punkte)):
        return _flaechenpunkte_krumm(model, f, punkte, abstand)
    c, e1, e2, n, abw = ausgleichsebene(rand)
    ringe = [np.stack([(R - c) @ e1, (R - c) @ e2], axis=1) for R in punkte]
    lo, hi = ringe[0].min(axis=0), ringe[0].max(axis=0)
    aus = [np.vstack(punkte)]
    if abstand > 0:
        nx = int(np.ceil((hi[0] - lo[0]) / abstand))
        ny = int(np.ceil((hi[1] - lo[1]) / abstand))
        if 0 < nx * ny <= 250_000:
            u = lo[0] + (np.arange(nx) + 0.5) * (hi[0] - lo[0]) / nx
            v = lo[1] + (np.arange(ny) + 0.5) * (hi[1] - lo[1]) / ny
            K = np.stack(np.meshgrid(u, v, indexing="ij"), -1).reshape(-1, 2)
            K = K[_in_polygon_2d(K, ringe)]
            if len(K):
                aus.append(c + K[:, :1] * e1 + K[:, 1:] * e2)
    return np.vstack(aus)


def _linienpunkte(model, name: str, abstand: float) -> np.ndarray:
    from .mesher3d import _linienlaenge, _linienpunkte as _lp
    L = _linienlaenge(model, name)
    n = max(1, int(np.ceil(L / abstand))) if abstand > 0 else 8
    return np.asarray(_lp(model, name, min(n, 2000)), float)


# --------------------------------------------------------------------------
# Fein: Quellen an Kontakt-, Lager- und Lastflaechen und an ihren Boegen
# --------------------------------------------------------------------------
#: Abtastweite der Flaechenquellen von Fein, bezogen auf ihre Kantenlaenge
#: h_F: mit sqrt(2) h_F liegt jeder Punkt der Flaeche hoechstens h_F - die
#: Reichweite der Quelle - von einer Quelle entfernt, die Flaeche ist also
#: lueckenlos h_F (mit 2 h_F wie bei einer Netzverfeinerung des Anwenders
#: stiege das Feld in der Mitte einer Gitterzelle auf 1,15 h_F).
FEIN_ABTASTUNG = 2.0 ** 0.5


def _linien_von(f) -> list:
    return list(f.linien or []) + [x for loch in (f.oeffnungen or []) for x in loch]


def _gekruemmt(model, f) -> bool:
    """Liegt die Flaeche nicht in einer Ebene (Bohrungswand, Radius, Kegel)?"""
    from .mesher3d import ist_eben
    try:
        P = [np.asarray(f.randpunkte(model, 8), float)]
        P += [np.asarray(Q, float) for Q in f.oeffnungspunkte(model, 8)]
        P = np.vstack([Q for Q in P if len(Q)])
    except Exception:                       # noqa: BLE001
        return False
    return len(P) >= 4 and not ist_eben(P)


def _kontaktpaar_flaechen(model, kb_namen: set) -> set:
    """Flaechen, auf denen ein **Kontaktpaar** liegt, das nicht aus einer
    Kontaktbedingung stammt (die nennen ihre Flaechen selbst; ihre Paare
    tragen ihren Namen, fugen.kontaktfugen_zuruecksetzen). Ein Kontaktpaar
    kennt nur Knoten: eine Flaeche gehoert dazu, wenn eine ihrer Randseiten
    im vorhandenen Netz ganz auf Slave-Knoten oder Master-Facetten liegt."""
    paare = [cp for cp in (getattr(model, "contact_pairs", None) or []) if cp.name not in kb_namen]
    if not paare:
        return set()
    from .elements import solid as sl
    S: set = set()
    for cp in paare:
        S.update(int(n) for n in (cp.slave_nodes or []))
        for fc in (cp.master_faces or []):
            S.update(int(n) for n in fc)
    aus: set = set()
    if not S:
        return aus
    for fn, f in (getattr(model, "flaechen", None) or {}).items():
        for ei, s in (f.randseiten or []):
            try:
                e = model.elements[int(ei)]
                ecken = sl.FLAECHEN_ECKEN[e.typ][int(s)]
            except (IndexError, KeyError):
                continue
            if all(int(e.nodes[c]) in S for c in ecken):
                aus.add(fn)
                break
    return aus


def fein_ziele(model, netz=None, bogenwinkel: float = 9.0, flaechenfaktor: float = 0.5) -> dict:
    """Was Fein an diesem Modell feiner macht (Paket F1, 07.10.2026).

    **Flaechen** - nur Randflaechen von Koerpern:

    * *Kontakt*: Flaechen aktiver, nicht verschweisster Kontaktbedingungen
      (freigegebene Flaechen und Gegenflaechen; die geloeste Seite liegt
      raeumlich darauf) und Flaechen unter einem Kontaktpaar
      (:func:`_kontaktpaar_flaechen`),
    * *Lager*: Flaechen der Flaechenlager,
    * *Last*: Flaechen mit einer Flaechenlast (Geometrielast auf der Flaeche;
      eine Last auf einen ganzen Koerper und eine Temperatur machen keine
      Flaeche zur Lastflaeche).

    Auf ihnen gilt h_F = ``flaechenfaktor`` * h_Mittel, wobei h_Mittel die
    Kantenlaenge ist, mit der Mittel den feinsten Koerper an dieser Flaeche
    vernetzt (Netzdichte bzw. Ziellaenge, eigene Kantenlaenge je Koerper,
    Mindestteilung - netzdichte.elementlaenge und mesher3d._kantenlaenge).

    **Boegen** (Anwender 07.10.2026: „Alle an Kontakt- und Lagerflaechen
    vorab“): jede krumme Linie im Rand oder in einer Oeffnung einer Kontakt-
    oder Lagerflaeche, dazu die krummen Linien jeder **gekruemmten** Flaeche
    (Bohrungswand, Radius), die eine Linie mit einer Kontakt- oder
    Lagerflaeche teilt - also an sie grenzt. Sie bekommen ``bogenwinkel``
    Grad je Abschnitt, wenn das mehr Abschnitte gibt als die Vorgabe
    (mesher3d.BOGENWINKEL, 18 Grad), und als Linienquelle die Laenge eines
    Abschnitts h_B, hoechstens h_F. Boegen an Lastflaechen und Boegen ohne
    Kontakt oder Lager bleiben wie bei Mittel.

    Rueckgabe {"flaechen": {Name: "Kontakt" | "Lager" | "Last"}, "h_mittel":
    {Flaeche: m}, "h": {Flaeche: h_F}, "boegen": {Linie: h_B},
    "bogenwinkel", "flaechenfaktor"}. Gespeichert wird davon nichts.
    """
    from . import mesher3d as M3
    from . import netzdichte as nd
    from .kontakte import ist_verschweisst
    netz = netz if netz is not None else model.netz
    koerper = list((getattr(model, "koerper", None) or {}).values())
    koerperflaechen = {fn for k in koerper for fn in (k.flaechen or []) if fn in model.flaechen}
    flaechen: dict = {}

    def merke(fn, art):
        if fn in koerperflaechen and fn not in flaechen:
            flaechen[fn] = art
    kb_namen: set = set()
    for kb in (getattr(model, "kontaktbedingungen", None) or {}).values():
        kb_namen.add(kb.name)
        if getattr(kb, "aus", False) or ist_verschweisst(model, kb):
            continue
        for fn in list(getattr(kb, "flaechennamen", None) or []) + list(getattr(kb, "gegenflaechen", None) or []):
            merke(fn, "Kontakt")
    for fn in sorted(_kontaktpaar_flaechen(model, kb_namen)):
        merke(fn, "Kontakt")
    for ss in (getattr(model, "surface_supports", None) or []):
        for fn in (getattr(ss, "flaechen", None) or []):
            merke(fn, "Lager")
    for lc in (getattr(model, "load_cases", None) or {}).values():
        for gl in (getattr(lc, "geometrielasten", None) or []):
            if getattr(gl, "art", "flaeche") == "koerper" or getattr(gl, "lastart", "druck") == "temperatur":
                continue
            merke(str(getattr(gl, "ziel", "")), "Last")
    # Kantenlaenge von Mittel je Koerper - nur fuer Koerper an einer Zielflaeche
    h_mittel: dict = {}
    for k in koerper:
        an = [fn for fn in (k.flaechen or []) if fn in flaechen]
        if not an:
            continue
        try:
            hk = float(nd.elementlaenge(model, netz, k)["h"])
            hk = float(M3._kantenlaenge(model, k, hk, []))
        except Exception:                   # noqa: BLE001 - eine Schaetzung darf nie sperren
            continue
        if hk <= 0:
            continue
        for fn in an:
            h_mittel[fn] = min(h_mittel.get(fn, hk), hk)
    faktor = float(flaechenfaktor)
    h = {fn: faktor * hm for fn, hm in h_mittel.items()}
    # Boegen an Kontakt- und Lagerflaechen
    boegen: dict = {}
    vorgabe = M3.bogenwinkel_vorgabe(model)
    if bogenwinkel and float(bogenwinkel) < vorgabe:
        kl = {fn for fn, art in flaechen.items() if art in ("Kontakt", "Lager") and fn in h}
        kandidaten: dict = {}
        for fn in kl:
            for ln in _linien_von(model.flaechen[fn]):
                kandidaten[ln] = min(kandidaten.get(ln, h[fn]), h[fn])
        an_linie: dict = {}
        for fn in koerperflaechen:
            for ln in _linien_von(model.flaechen[fn]):
                an_linie.setdefault(ln, set()).add(fn)
        for fn in sorted(koerperflaechen - kl):
            f = model.flaechen[fn]
            nachbarn = {g for ln in _linien_von(f) for g in an_linie.get(ln, ()) if g in kl}
            if not nachbarn or not _gekruemmt(model, f):
                continue
            hf = min(h[g] for g in nachbarn)
            for ln in _linien_von(f):
                kandidaten[ln] = min(kandidaten.get(ln, hf), hf)
        for ln in sorted(kandidaten):
            line = model.lines.get(ln)
            if line is None or (line.typ or "polyline") == "polyline":
                continue
            try:
                n_fein = M3._bogenabschnitte(model, ln, float(bogenwinkel))
                if n_fein <= M3._bogenabschnitte(model, ln, vorgabe):
                    continue                # gerade oder kaum gekruemmt: nichts zu tun
                L = float(M3._linienlaenge(model, ln))
            except Exception:               # noqa: BLE001
                continue
            if L > 0:
                boegen[ln] = min(kandidaten[ln], L / n_fein)
    return {"flaechen": flaechen, "h_mittel": h_mittel, "h": h, "boegen": boegen,
            "bogenwinkel": float(bogenwinkel), "flaechenfaktor": faktor}


def fein_verfeinerungen(ziele: dict) -> list:
    """Die Quellen von Fein als Eintraege fuer ``netz.verfeinerungen`` - nur
    fuer die Dauer des Vernetzens (elementstufe.wirksam), nie gespeichert:
    ``{"art": "fein_flaeche", "name", "h", "h_mittel", "grund"}`` und
    ``{"art": "fein_bogen", "name", "h", "winkel"}``. :func:`aufbauen` tastet
    sie ab. Eine Flaechenquelle mit h_F >= h_Mittel (Faktor 1) wirkt nicht
    und entfaellt, damit die letzte Vergroeberungsstufe bitgleich Mittel ist."""
    aus = []
    for fn, art in ziele["flaechen"].items():
        hf, hm = ziele["h"].get(fn), ziele["h_mittel"].get(fn)
        if hf and hm and hf < hm * (1.0 - 1e-12):
            aus.append({"art": "fein_flaeche", "name": fn, "h": float(hf), "h_mittel": float(hm), "grund": art})
    for ln, hb in ziele["boegen"].items():
        aus.append({"art": "fein_bogen", "name": ln, "h": float(hb), "winkel": float(ziele["bogenwinkel"])})
    return aus


def aufbauen(model, h_max: float = 0.0, log: list = None) -> "Groessenfeld | None":
    """Das Groessenfeld des Modells aus den Netzeinstellungen - oder None,
    wenn nichts darin steht und das Feld ohne Wirkung waere.

    ``h_max``: die groesste Kantenlaenge (0 = Ziellaenge der
    Netzeinstellungen). Netzverfeinerungen sind Woerterbuecher
    ``{"art": "kugel", "mitte": [x, y, z], "radius": r, "h": h}``,
    ``{"art": "flaeche" | "linie" | "koerper", "name": ..., "h": h}``;
    Feldpunkte sind ``[x, y, z, h]`` oder ``[x, y, z, h, r]``. Dazu kommen
    bei Fein, nur fuer die Dauer des Vernetzens, ``{"art": "fein_flaeche",
    "name", "h", "h_mittel"}`` und ``{"art": "fein_bogen", "name", "h",
    "winkel"}`` (:func:`fein_verfeinerungen`, seit 07.10.2026).
    """
    netz = getattr(model, "netz", None)
    if netz is None:
        return None
    if h_max <= 0:
        h_max = float(getattr(netz, "ziellaenge", 0.0) or 0.0)
    if h_max <= 0:
        from .mesher3d import STANDARDLAENGE
        h_max = STANDARDLAENGE
    h_min = float(getattr(netz, "h_min", 0.0) or 0.0)
    verfeinerungen = list(getattr(netz, "verfeinerungen", None) or [])
    # Die Quellen von Fein nennen die Kantenlaenge von Mittel ihrer Flaeche
    # (nach Netzdichte je Koerper). Das Feld darf darunter nicht deckeln: eine
    # Ziellaenge, die kleiner ist als die Laenge eines Koerpers aus der
    # Netzdichte, machte sonst den ganzen Koerper feiner.
    h_fein = [float(v.get("h_mittel", 0.0) or 0.0) for v in verfeinerungen
              if str(v.get("art", "")).startswith("fein_")]
    if h_fein:
        h_max = max(h_max, max(h_fein))
    feld = Groessenfeld(h_max)
    feine: dict = {}
    for v in verfeinerungen:
        try:
            art = str(v.get("art", ""))
            h = float(v.get("h", 0.0) or 0.0)
            if h_min > 0:
                h = max(h, h_min)
            if h <= 0:
                continue
            if art == "fein_flaeche":
                # Fein (Paket F1): die Flaeche lueckenlos h, eine Elementlage
                # (Reichweite h), davon wachsend
                f = model.flaechen.get(str(v.get("name", "")))
                if f is not None:
                    feld.punkte(_flaechenpunkte(model, f, FEIN_ABTASTUNG * h), h, h, "Fein-Fläche")
            elif art == "fein_bogen":
                # Fein: der Bogen einer Kontakt- oder Lagerflaeche mit dem
                # feineren Bogenwinkel - in der Linienteilung (feine_linien)
                # und als Linienquelle mit h_B fuer Flaechen, Inneres, gmsh
                # und MMG3D
                name = str(v.get("name", ""))
                if name in model.lines:
                    feld.punkte(_linienpunkte(model, name, 0.5 * h), h, 0.0, "Fein-Bogen")
                    w = float(v.get("winkel", 0.0) or 0.0)
                    if w > 0:
                        feine[name] = min(w, feine.get(name, w))
            elif art == "kugel":
                feld.kugel(v.get("mitte", [0, 0, 0]), float(v.get("radius", 0.0) or 0.0), h, "Kugel")
            elif art == "flaeche":
                f = model.flaechen.get(str(v.get("name", "")))
                if f is not None:
                    P = _flaechenpunkte(model, f, 2.0 * h)
                    feld.punkte(P, h, h, "Fläche")
            elif art == "linie":
                if str(v.get("name", "")) in model.lines:
                    P = _linienpunkte(model, str(v["name"]), 2.0 * h)
                    feld.punkte(P, h, h, "Linie")
            elif art == "koerper":
                k = model.koerper.get(str(v.get("name", "")))
                for fn in (k.flaechen if k is not None else []):
                    f = model.flaechen.get(fn)
                    if f is not None:
                        feld.punkte(_flaechenpunkte(model, f, 2.0 * h), h, h, "Körper")
        except Exception as ex:             # noqa: BLE001 - eine Verfeinerung darf nie sperren
            if log is not None:
                log.append(f"WARNUNG: Netzverfeinerung {v} nicht lesbar ({ex}) - übergangen.")
    fp = getattr(netz, "feldpunkte", None) or []
    if fp:
        A = np.asarray(fp, float).reshape(len(fp), -1)
        if A.shape[1] >= 4:
            h = A[:, 3]
            if h_min > 0:
                h = np.maximum(h, h_min)
            r = A[:, 4] if A.shape[1] >= 5 else np.zeros(len(A))
            feld.punkte(A[:, :3], h, r, "Feldpunkte")
    # Bedeutung der Flaechen: grobe Linien an Nebenflaechen
    if bool(getattr(netz, "nebenflaechen_grob", False)):
        b = bedeutung(model)
        feld.grobe_linien = frozenset(b["neben_linien"])
    feld.feine_linien = feine
    feld.dreiecksgitter = any(str(v.get("art", "")).startswith("fein_") for v in verfeinerungen)
    if feld.leer and not feld.grobe_linien and not feld.feine_linien:
        return None
    n = feld.abschliessen()
    if log is not None:
        from .importers import _common as C
        teile = ", ".join(f"{k} {v}" for k, v in feld.herkunft.items())
        C.say(log, f"Größenfeld: {n} Quellen" + (f" ({teile})" if teile else "")
                   + (f", {len(feld.grobe_linien)} Linien an Nebenflächen mit "
                      f"{feld.bogenwinkel_grob:.0f}° je Bogenabschnitt" if feld.grobe_linien else "")
                   + (f", {len(feine)} Bögen mit {min(feine.values()):g}° je Abschnitt" if feine else ""))
    return feld


def am_modell(model) -> "Groessenfeld | None":
    """Das am Modell haengende Feld (``model.groessenfeld``) oder None."""
    return getattr(model, "groessenfeld", None)
