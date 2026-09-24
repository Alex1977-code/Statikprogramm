"""
Gemeinsame Hilfsfunktionen der Importer.

* Log-Ausgabe (nie print, immer an eine Liste anhaengen)
* Knotenverwaltung mit Toleranz (doppelte Koordinaten -> ein Knoten)
* Standardmaterial / Standardquerschnitt
* Zahlen mit deutschem Dezimalkomma, Einheiten aus Spaltenueberschriften
* Polygon -> Schalenelemente (Dreieck, Viereck, Faecher-Triangulierung)
* Einwirkungskategorie aus Freitext
"""
from __future__ import annotations

import copy
import math
import re
from dataclasses import MISSING, fields
from typing import Optional

import numpy as np

from ..model import Model, Material, Section, ShellProp, LoadCase, ACTION_CATEGORIES
from .. import profiles

DEFAULT_TOL = 1e-6          # Knotentoleranz [m]
DEFAULT_STEEL = "S235"
DEFAULT_PROFILE = "IPE 200"


# --------------------------------------------------------------------------
# Protokoll
# --------------------------------------------------------------------------
def say(log: Optional[list], msg: str) -> None:
    """Meldung an das Importprotokoll anhaengen (falls vorhanden)."""
    if log is not None:
        log.append(msg)


def warn(log: Optional[list], msg: str) -> None:
    say(log, "WARNUNG: " + msg)


# --------------------------------------------------------------------------
# Knoten
# --------------------------------------------------------------------------
class NodeIndex:
    """Knoten mit Koordinatentoleranz verwalten.

    Neue Knoten werden gesammelt und mit flush() en bloc an das Modell
    angehaengt (Model.add_node kopiert bei jedem Aufruf das ganze Array).
    Bereits vorhandene Knoten des Modells werden beruecksichtigt, so dass ein
    Import an ein bestehendes Modell angeschlossen werden kann.
    """

    def __init__(self, model: Model, tol: float = DEFAULT_TOL):
        self.model = model
        self.tol = float(tol) if tol and tol > 0 else DEFAULT_TOL
        self._map: dict[tuple, int] = {}
        self._pending: list[tuple[float, float, float]] = []
        self._base = model.nn
        for i, p in enumerate(model.nodes):
            self._map.setdefault(self._key(p), i)

    def _key(self, p) -> tuple:
        return tuple(int(math.floor(float(c) / self.tol + 0.5)) for c in p)

    def find(self, x: float, y: float, z: float) -> Optional[int]:
        """Index eines vorhandenen Knotens an (x, y, z) oder None."""
        k = self._key((x, y, z))
        hit = self._map.get(k)
        if hit is not None:
            return hit
        # Nachbarzellen (Rundungsgrenzen)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    if dx == dy == dz == 0:
                        continue
                    hit = self._map.get((k[0] + dx, k[1] + dy, k[2] + dz))
                    if hit is not None:
                        p = self.get(hit)
                        if (abs(p[0] - x) <= self.tol and abs(p[1] - y) <= self.tol
                                and abs(p[2] - z) <= self.tol):
                            return hit
        return None

    def add(self, x: float, y: float, z: float) -> int:
        """Knoten holen oder anlegen; Rueckgabe Knotenindex."""
        x, y, z = float(x), float(y), float(z)
        hit = self.find(x, y, z)
        if hit is not None:
            return hit
        idx = self._base + len(self._pending)
        self._pending.append((x, y, z))
        self._map[self._key((x, y, z))] = idx
        return idx

    def get(self, idx: int) -> np.ndarray:
        """Koordinaten eines Knotens (auch noch nicht geschriebener)."""
        if idx < self._base:
            return self.model.nodes[idx]
        return np.asarray(self._pending[idx - self._base], float)

    def flush(self) -> int:
        """Gesammelte Knoten an das Modell anhaengen."""
        n = len(self._pending)
        if n:
            self.model.add_nodes(np.asarray(self._pending, float))
            self._base = self.model.nn
            self._pending = []
        return n

    def __len__(self) -> int:
        return self._base + len(self._pending)


def count_duplicate_nodes(model: Model, tol: float = DEFAULT_TOL) -> int:
    """Wie viele Knoten auf einem anderen liegen - ohne etwas zu aendern.

    Zusammenfuehren ist nicht immer richtig: an einer Kontaktfuge, einer
    Kontaktbedingung oder einem Gleitlager liegen die Knoten absichtlich
    aufeinander. Wer nur wissen will, wie viele es sind, fragt hier.
    """
    if model.nn == 0:
        return 0
    key = np.floor(model.nodes / tol + 0.5).astype(np.int64)
    return int(model.nn - len(np.unique(key, axis=0)))


def merge_duplicate_nodes(model: Model, tol: float = DEFAULT_TOL,
                          log: Optional[list] = None) -> int:
    """Doppelte Knoten zusammenfuehren, alle Verweise umhaengen.

    Wie mesher.merge_nodes, beruecksichtigt aber zusaetzlich die Knotenlasten
    *aller* Lastfaelle sowie Kontaktobjekte. Rueckgabe: Anzahl entfernter Knoten.
    ``log``: Protokoll fuer die Warnung, wenn zwei verschiedene gekruemmte
    Kantenmitten auf eine Kante fallen (:func:`_kantenmitten_umhaengen`).
    """
    if model.nn == 0:
        return 0
    key = np.floor(model.nodes / tol + 0.5).astype(np.int64)
    _, first, inverse = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inverse = np.asarray(inverse).reshape(-1)
    order = np.argsort(first)
    remap = np.zeros(len(first), dtype=int)
    remap[order] = np.arange(len(first))
    new_index = remap[inverse]
    n_removed = model.nn - len(first)
    if n_removed == 0:
        return 0
    new_nodes = np.zeros((len(first), 3))
    new_nodes[new_index] = model.nodes
    _umnummerieren(model, new_index, new_nodes, log)
    return n_removed


def anschluss_zusammenfuehren(model: Model, n_ziel: int, tol: float = DEFAULT_TOL,
                              log: Optional[list] = None) -> tuple[int, list]:
    """Angehaengte Knoten (ab ``n_ziel``) auf gleich liegende Knoten davor
    legen - nur zwischen den beiden Teilen, nie innerhalb eines Teils.

    ``merge_duplicate_nodes`` ueber das ganze Modell verschweisst auch, was in
    einem Teil absichtlich aufeinanderliegt: die beiden Seiten einer
    ausgefuehrten Kontaktfuge. Gemessen beim Anhaengen eines JSON-Modells
    (Befund SV11, Nachbesserung 23.09.2026): zwei Bloecke mit Fuge "Ausfall
    bei Zug" und 200 kN Zug - allein 0,0 N am Fundament, angehaengt an ein
    leeres Ziel -198 152,7 N, weil 24 von 24 Spaltelementen danach einen
    Knoten mit sich selbst verbanden; an Kopfplatte_HEA_200.json 117 von 117.

    Zusammengefuehrt wird ein Knoten des angehaengten Teils nur, wenn an
    seiner Stelle genau ein Knoten des Ziels und genau einer des Anhangs
    liegt. Liegen dort in einem Teil mehrere (eine Fuge), ist nicht
    eindeutig, welcher anschliessen soll: dann bleibt alles getrennt, und
    die Stelle kommt zurueck. Die Knoten des Ziels behalten ihre Nummern.

    Rueckgabe: (Anzahl zusammengefuehrter Knoten, Koordinaten der
    uneindeutigen Stellen). ``log`` wie bei :func:`merge_duplicate_nodes`."""
    n_ziel = int(n_ziel)
    if n_ziel <= 0 or model.nn <= n_ziel:
        return 0, []
    key = np.floor(model.nodes / tol + 0.5).astype(np.int64)
    _, inverse = np.unique(key, axis=0, return_inverse=True)
    inverse = np.asarray(inverse).reshape(-1)
    inv_z, inv_q = inverse[:n_ziel], inverse[n_ziel:]
    g = int(inverse.max()) + 1
    cnt_z = np.bincount(inv_z, minlength=g)
    cnt_q = np.bincount(inv_q, minlength=g)
    erster_z = np.full(g, -1, dtype=np.int64)
    erster_z[inv_z[::-1]] = np.arange(n_ziel - 1, -1, -1)      # erster Zielknoten je Stelle
    eindeutig = (cnt_z[inv_q] == 1) & (cnt_q[inv_q] == 1)
    unklar = np.unique(inv_q[(cnt_z[inv_q] > 0) & ~eindeutig])
    stellen = [model.nodes[int(erster_z[s])].tolist() for s in unklar]
    n_merge = int(eindeutig.sum())
    if n_merge == 0:
        return 0, stellen
    new_index = np.arange(model.nn, dtype=np.int64)
    bleibt = ~eindeutig
    anhang = new_index[n_ziel:]                                 # Sicht, schreibt durch
    anhang[bleibt] = n_ziel + np.arange(int(bleibt.sum()))
    anhang[eindeutig] = erster_z[inv_q[eindeutig]]
    new_nodes = np.vstack([model.nodes[:n_ziel], model.nodes[n_ziel:][bleibt]])
    _umnummerieren(model, new_index, new_nodes, log)
    return n_merge, stellen


def _umnummerieren(model: Model, new_index, new_nodes, log: Optional[list] = None) -> None:
    """Neue Knotenliste setzen und jeden Knotenverweis umhaengen
    (``new_index[alt] = neu``); gleich gewordene Knoten in Linien, Linien-
    und Flaechenlagern einmal fuehren."""
    # Die Kantenmitten zuerst: welche ein tetp-Element liest, entscheiden die
    # alten Knotennummern der Elemente - die werden gleich umgehaengt
    _kantenmitten_umhaengen(model, new_index, new_nodes, log)
    model.nodes = new_nodes
    for e in model.elements:
        e.nodes = [int(new_index[n]) for n in e.nodes]
    for s in model.supports:
        s.node = int(new_index[s.node])
    for lc in model.load_cases.values():
        for l in lc.nodal_loads:
            l.node = int(new_index[l.node])
    for c in model.contact_supports:
        c.node = int(new_index[c.node])
    for g in model.gap_elements:
        g.node_a = int(new_index[g.node_a])
        g.node_b = int(new_index[g.node_b])
    for cp in model.contact_pairs:
        cp.slave_nodes = [int(new_index[n]) for n in cp.slave_nodes]
        cp.master_faces = [[int(new_index[n]) for n in f] for f in cp.master_faces]
    for ln in model.lines.values():
        seen, nodes = set(), []
        for n in ln.nodes:
            k = int(new_index[n])
            if not nodes or nodes[-1] != k:
                nodes.append(k)
            seen.add(k)
        ln.nodes = nodes
    for ls in model.line_supports:
        nodes = []
        for n in ls.nodes:
            k = int(new_index[n])
            if k not in nodes:
                nodes.append(k)
        ls.nodes = nodes
    for ss in model.surface_supports:
        ss.elements = [int(e) for e in ss.elements]
        nodes, areas = [], []
        pos: dict[int, int] = {}
        for i, n in enumerate(ss.nodes):
            k = int(new_index[n])
            a = ss.areas[i] if i < len(ss.areas) else 0.0
            if k in pos:
                if areas:
                    areas[pos[k]] += a          # Einflussflaechen addieren
            else:
                pos[k] = len(nodes)
                nodes.append(k)
                areas.append(a)
        ss.nodes = nodes
        ss.areas = areas if any(areas) else []
    _weitere_knotenverweise_umhaengen(model, new_index)


def _zusammenfassen(knoten, flaechen) -> tuple[list, list]:
    """Knoten, die beim Zusammenfuehren gleich wurden, einmal fuehren; ihre
    Einflussflaechen addieren sich (wie bei ``SurfaceSupport.nodes``)."""
    out_k, out_a, pos = [], [], {}
    for i, n in enumerate(knoten):
        a = float(flaechen[i]) if i < len(flaechen) else 0.0
        if n in pos:
            out_a[pos[n]] += a
        else:
            pos[n] = len(out_k)
            out_k.append(n)
            out_a.append(a)
    return out_k, out_a


def _weitere_knotenverweise_umhaengen(model: Model, new_index) -> None:
    """Die Knotenverweise, die ``merge_duplicate_nodes`` bis zum 22.09.2026
    nicht umhaengte: sie zeigten nach dem Zusammenfuehren auf die alte
    Nummer, also auf einen anderen Knoten - oder hinter das Ende der Liste.

    Anlass ist das Anhaengen eines JSON-Modells (Befund SV11): es bringt
    Punktmassen, Starrkoerper, Zwangsverformungen, Kopplungen, die Ecken der
    Flaechen und die Einflussflaechen der Kontaktpaare mit, und das
    Zusammenfuehren danach nummeriert jeden Knoten hinter einem entfernten
    Doppel um. Gemessen am Pruefmodell (tests.test_importers,
    test_json_anhaengen_vollstaendig, ein Anschlussknoten bei (0, 0, 0)):
    ohne diese Zeilen lag jeder dieser Verweise einen Knoten daneben - die
    Zwangsverformung auf (2, 0, 0) statt (0, 0, 0), die Punktmasse auf
    (3, 0, 0) statt (0, 1, 0), die vier Flaechenecken um eine Ecke verrutscht
    und die letzte auf dem Quader nebenan.

    **Das wirkt auf jeden Import, nicht nur auf das Anhaengen.**
    ``merge_duplicate_nodes`` laeuft in der Nachbereitung von
    ``importers.import_file`` nach jedem Nicht-JSON-Import, der Knoten
    anlegt - also bei jedem .rf6 -, dazu im RFEM-Leser mit
    ``merge_nodes=True`` und fuer die uebrigen RFEM-Behaelter. Gemessen am
    Drehlager_V15_4_export.rf6 (23.09.2026, 617 Knoten zusammengefuehrt):
    vorher lagen 64 von 3128 Flaechenecken neben den Knoten ihrer Randlinien
    (bis 1815,9 mm), weitere 1380 zeigten hinter das Ende der Knotenliste,
    ebenso 10 von 168 integrierten Knoten; jetzt jeweils 0 (zweite Messung
    mit Aufteilung am 23.09.2026). Die Ecken liest
    "Spiel geben" (``spiel._fremde_nutzung``): an den 73 zylindrischen
    Koerpern bekommt ``spiel.trennen`` jetzt 359 statt 363 Knotenkopien
    (V16 und V29 je 2 weniger - Knoten, die nur eine verrutschte Ecke als
    fremd auswies), die 24 Linienkopien bleiben. Importzeit 1,1 s vorher,
    1,2 s jetzt (je ein Lauf, geometrischer Import ohne Netz).
    """
    def k(n) -> int:
        return int(new_index[int(n)])

    def ks(liste) -> list:
        return [k(n) for n in (liste or [])]

    def ks_einmal(liste) -> list:
        out = []
        for n in (liste or []):
            m = k(n)
            if m not in out:
                out.append(m)
        return out

    for ss in model.surface_supports:
        gruppen = []
        for g in (getattr(ss, "gruppen", None) or []):
            kn, fl = _zusammenfassen(ks(g[2]), list(g[3]) if len(g) > 3 else [])
            gruppen.append([g[0], g[1], kn, fl] + list(g[4:]))
        ss.gruppen = gruppen
    for lc in model.load_cases.values():
        for zv in (lc.zwangsverformungen or []):
            zv.node = k(zv.node)
    for cp in model.contact_pairs:
        kf = getattr(cp, "knotenflaechen", None) or {}
        neu: dict = {}
        for n, a in kf.items():
            neu[k(n)] = neu.get(k(n), 0.0) + float(a)
        cp.knotenflaechen = neu
        cp.rand_knoten = ks_einmal(getattr(cp, "rand_knoten", None))
    for kp in (getattr(model, "kopplungen", None) or []):
        kp.node_a, kp.node_b = k(kp.node_a), k(kp.node_b)
    model.getrennte_knoten = {name: [[k(a), k(b)] for a, b in paare]
                              for name, paare in (getattr(model, "getrennte_knoten", None)
                                                  or {}).items()}
    for pm in (getattr(model, "punktmassen", None) or []):
        pm.node = k(pm.node)
    for d in (getattr(model, "daempfer", None) or []):
        d.node_a = k(d.node_a)
        if int(d.node_b) >= 0:              # -1 = gegen den Boden
            d.node_b = k(d.node_b)
    for sk in (getattr(model, "starrkoerper", None) or []):
        # Keine Doppel entfernen: ``gewichte`` laeuft parallel zu ``slaves``
        sk.master, sk.slaves = k(sk.master), ks(sk.slaves)
    for f in (getattr(model, "flaechen", None) or {}).values():
        f.ecken = ks(f.ecken)
        f.integrierte_knoten = ks_einmal(f.integrierte_knoten)
    for le in (getattr(model, "lasteinleitungen", None) or {}).values():
        le.knoten = k(le.knoten)
    for v in (getattr(model, "verformungsgrenzen", None) or {}).values():
        v.knoten = ks(v.knoten)
    for s in (getattr(model, "subsysteme", None) or {}).values():
        s.knoten = ks_einmal(s.knoten)
    for ly in (getattr(model, "layer", None) or {}).values():
        ly.knoten = ks_einmal(ly.knoten)
    for st in (getattr(model, "stellungen", None) or []):
        an = st.get("antrieb") if isinstance(st, dict) else getattr(st, "antrieb", None)
        if an is not None:
            an = (k(an[0]), an[1])
            if isinstance(st, dict):
                st["antrieb"] = an
            else:
                st.antrieb = an


def _kantenmitten_umhaengen(model: Model, new_index, new_nodes,
                            log: Optional[list] = None) -> None:
    """Die gekruemmte Geometrie der Tetraeder mit Ordnung p
    (``model.tetp_kantenmitten``, {(a, b) mit a < b: Kantenmitte}) auf die
    neuen Knotennummern setzen. Aufzurufen, **bevor** die Elemente
    umnummeriert sind (``_umnummerieren``); ``new_nodes`` sind die neuen
    Koordinaten.

    Seit dem 23.09.2026 steht sie in der Modelldatei und kommt beim Anhaengen
    mit; ohne das hier zeigte nach dem Zusammenfuehren jede Kante hinter
    einem entfernten Doppel auf andere Knoten - eine Kantenmitte landete an
    einer fremden Kante oder wirkte nirgends mehr. Gemessen (zweimal,
    23.09.2026) an der Hohlkugel mit einem Zielknoten auf einer gekruemmten
    Kante: Geometrie der angehaengten Elemente bis 75,3 mm neben der Quelle,
    jetzt bitgleich (tests.test_importers,
    test_json_anhaengen_tetp_kantenmitten).

    Mitgenommen wird nur die Kantenmitte einer Kante (a, b), a < b, die in
    den alten Nummern Kante eines tetp-Elements ist; die uebrigen fallen
    weg. Solche verwaisten Schluessel laesst ``Model.netzknoten_loeschen``
    stehen (es fuehrt die Kantenmitten nicht mit), mit Knotennummern bis
    hinter das Ende der Liste. Bis zur Nachbesserung vom 23.09.2026 wurden
    sie hier indiziert: Anhaengen eines JSON-Modells an ein gespeichertes
    Modell, dessen tetp-Netz danach entfernt war (Hohlkugel 2 x 2, p = 3,
    und ein Stab; danach 38 Knoten, 126 Kantenmitten), brach mit IndexError
    ab - vor der Speicher-Kur (ec6448c) lief es durch (je zweimal gemessen;
    Pruefung tests.test_importers, test_json_anhaengen_nach_netz_entfernen).
    Nur die Schluessel hinter dem Ende zu verwerfen genuegt nicht: einer mit
    gueltiger Nummer wird beim Zusammenfuehren zur Kante eines
    tetp-Elements, sobald ein neuer Knoten auf deren Ecke faellt, und
    kruemmt sie still - mit dieser Variante gemessen (zweimal, 23.09.2026)
    nach netzknoten_loeschen und 7 hinzugefuegten Knoten, der letzte auf
    einer Ecke: eine gerade Kante 45,79 mm daneben, ohne Warnung (Pruefung
    tests.test_importers, test_zusammenfuehren_kantenmitte_ohne_element).
    Der Filter hier sieht nur die alten Nummern: ein verwaister Eintrag des
    Ziels, der mit ihnen schon Kante eines angehaengten Elements ist, kaeme
    durch, und ohne zusammenfallende Knoten laeuft diese Funktion gar nicht.
    Darum nimmt das Anhaengen vorher nur mit, was ein tetp-Element des
    Ziels bzw. der Quelle liest (anhaengen._Anhang._netz,
    model.tetp_kantenmitten_gelesen; an bc1dfe0 sonst bis 5555 mm,
    Pruefung test_json_anhaengen_verwaiste_kantenmitten).

    Fallen zwei Kanten von tetp-Elementen auf eine, gilt die Kante des
    tetp-Elements, das im Modell zuerst steht - beim Anhaengen die des
    Ziels, dessen Elemente vor denen der Quelle stehen -, und zwar gerade
    oder gekruemmt: eine gerade Kante hat keinen Eintrag, ihre Kantenmitte
    ist die Sehnenmitte. Kanten anderer Elemente sieht diese Funktion nicht:
    teilt ein tet4 die Kante, ist sie dort gerade (tetp.pflichtseiten gibt
    sie geometrie_modell als gerade_kanten), gleich welche Seite zuerst
    steht, und hier kommt keine Warnung - gemessen 24.09.2026 am
    Hohlzylinder, 8 gekruemmte Anschlusskanten, bis 3,769 mm (Pruefung
    test_json_anhaengen_tet4_nachbar). Bis zur
    Nachbesserung vom 24.09.2026 galt der zuerst eingetragene Eintrag, und
    ein fehlender zaehlte nicht: war eine Seite gerade und die andere
    gekruemmt, galt still die gekruemmte (gemessen an bc1dfe0, Hohlkugel an
    sich selbst gehaengt, eine Kante in einer der Dateien gerade: 1,885 mm,
    keine Warnung; Pruefung test_json_anhaengen_gerade_gegen_gekruemmt).
    Liegen die beiden Kantenmitten weiter auseinander als 1e-9 der
    Kantenlaenge (die Grenze, mit der tetp.aus_tet10 gekruemmt von gerade
    trennt), sagt es das Protokoll: die Elemente der anderen Seite rechnen
    dort mit einer anderen Geometrie als zuvor."""
    km = getattr(model, "tetp_kantenmitten", None)
    if not km:
        return
    from ..model import tetp_kanten
    alt = tetp_kanten(model.elements)            # alte Nummern, in Elementreihenfolge
    if not len(alt):
        model.tetp_kantenmitten = {}
        return
    ni = np.asarray(new_index, dtype=np.int64).reshape(-1)
    X = np.asarray(new_nodes, float)
    n_alt, n_neu = len(ni), len(X)
    # jede alte Kante einmal; erst = ihr erstes Auftreten in Elementreihenfolge
    code_alt, erst = np.unique(alt[:, 0] * n_alt + alt[:, 1], return_index=True)
    A = alt[erst]
    B = np.sort(ni[A], axis=1)                   # dieselben Kanten in den neuen Nummern
    _, gruppe, anzahl = np.unique(B[:, 0] * n_neu + B[:, 1], return_inverse=True,
                                  return_counts=True)
    gruppe = np.asarray(gruppe).reshape(-1)
    # der Eintrag je alter Kante (None: gerade); verwaiste Schluessel treffen keine
    schl = np.asarray(list(km), dtype=np.int64).reshape(-1, 2)
    im_netz = ((schl >= 0) & (schl < n_alt)).all(axis=1)
    code = np.where(im_netz, schl[:, 0] * n_alt + schl[:, 1], -1)
    pos = np.minimum(np.searchsorted(code_alt, code), len(code_alt) - 1)
    trifft = im_netz & (code_alt[pos] == code)
    eintrag: list = [None] * len(A)
    neu: dict = {}
    einfach = anzahl[gruppe] == 1
    for p, j, t in zip(km.values(), pos.tolist(), trifft.tolist()):
        if t:
            eintrag[j] = p
            if einfach[j]:                       # die neue Kante hat nur diese alte
                neu[(int(B[j, 0]), int(B[j, 1]))] = p
    abweichend, gerade_krumm, weiteste = 0, 0, 0.0
    mehr = np.flatnonzero(~einfach)
    if len(mehr):
        mehr = mehr[np.lexsort((erst[mehr], gruppe[mehr]))]
        for glieder in np.split(mehr, np.flatnonzero(np.diff(gruppe[mehr])) + 1):
            j0 = int(glieder[0])                 # die Kante des zuerst stehenden Elements
            a, b = int(B[j0, 0]), int(B[j0, 1])
            sehne = 0.5 * (X[a] + X[b])
            if eintrag[j0] is not None:
                neu[(a, b)] = eintrag[j0]
            gilt = sehne if eintrag[j0] is None else np.asarray(eintrag[j0], float)
            grenze = 1e-9 * max(float(np.linalg.norm(X[b] - X[a])), 1e-300)
            weit, mit_gerade = 0.0, False
            for j in glieder[1:].tolist():
                andere = sehne if eintrag[j] is None else np.asarray(eintrag[j], float)
                d = float(np.linalg.norm(andere - gilt))
                if d > grenze:
                    weit = max(weit, d)
                    mit_gerade = mit_gerade or ((eintrag[j] is None) != (eintrag[j0] is None))
            if weit > 0.0:
                abweichend += 1
                gerade_krumm += int(mit_gerade)
                weiteste = max(weiteste, weit)
    model.tetp_kantenmitten = neu
    if abweichend:
        gk = (f"; bei {gerade_krumm} davon war die Kante auf einer Seite gerade und auf der "
              "anderen gekrümmt" if gerade_krumm else "")
        warn(log, f"An {abweichend} Kante{'' if abweichend == 1 else 'n'} trafen beim "
                  "Zusammenführen der Knoten zwei verschiedene Kantenmitten (Tetraeder mit "
                  f"Ordnung p) aufeinander{gk}. Es gilt die Kante des Elements, das im Modell "
                  "zuerst steht - beim Anhängen die des Ziels -; die andere lag bis "
                  f"{weiteste * 1e3:.3g} mm daneben, und die Elemente der anderen Seite rechnen "
                  "dort mit der geltenden Kante. Bitte die Geometrie an der Anschlussfläche "
                  "prüfen.")


# --------------------------------------------------------------------------
# Material / Querschnitt / Schalendicke
# --------------------------------------------------------------------------
def steel_grade_from_text(text: str) -> Optional[str]:
    """'S 235 JR', 'S355', 'Baustahl S235' -> 'S235' (sonst None)."""
    if not text:
        return None
    m = re.search(r"S\s?(235|275|355|420|460)", str(text).upper())
    return f"S{m.group(1)}" if m else None


def ensure_material(model: Model, name: str = None, log: list = None,
                    quiet: bool = False) -> str:
    """Material sicherstellen und Namen zurueckgeben.

    name=None -> erstes vorhandenes Material, sonst Standardstahl S235.
    Enthaelt der Name eine Stahlsorte, wird diese verwendet.
    """
    if name and name in model.materials:
        return name
    if name is None:
        if model.materials:
            return next(iter(model.materials))
        name = DEFAULT_STEEL
    grade = steel_grade_from_text(name)
    if grade:
        model.add_material(Material.steel(grade, name))
        if not quiet:
            say(log, f"Material '{name}' als Baustahl {grade} angelegt")
    else:
        model.add_material(Material.steel(DEFAULT_STEEL, name))
        if not quiet:
            warn(log, f"Material '{name}' unbekannt - Kennwerte von {DEFAULT_STEEL} verwendet")
    return name


def section_from_designation(designation: str, name: str = None) -> Optional[Section]:
    """Profil aus der Datenbank (None, wenn unbekannt)."""
    if not designation:
        return None
    try:
        return profiles.make_section(designation, name or designation)
    except (KeyError, ValueError):
        return None


def ensure_section(model: Model, name: str = None, log: list = None,
                   fallback: str = DEFAULT_PROFILE) -> str:
    """Querschnitt sicherstellen: vorhandener Name, Profilbezeichnung oder Fallback."""
    if name and name in model.sections:
        return name
    if name:
        sec = section_from_designation(name, name)
        if sec is not None:
            model.add_section(sec)
            say(log, f"Querschnitt '{name}' aus Profildatenbank")
            return name
        warn(log, f"Querschnitt '{name}' unbekannt - {fallback} verwendet")
    if fallback in model.sections:
        return fallback
    sec = section_from_designation(fallback, fallback)
    if sec is None:
        sec = Section.i_profile(fallback, 0.200, 0.100, 0.0056, 0.0085, 0.012)
    model.add_section(sec)
    return fallback


def ensure_shell_prop(model: Model, name: str = None, t: float = None,
                      log: list = None) -> str:
    """Schalendicke sicherstellen. Ohne Angabe: erste vorhandene oder t = 10 mm."""
    if name and name in model.shells:
        return name
    if t is None or t <= 0:
        if name is None and model.shells:
            # **Das Erben bleibt, aber es wird genannt.** Eine Flaeche ohne
            # eigene Dickenangabe bekam stumm die Dicke der zuerst gelesenen:
            # gemessen 20 mm statt der 10 mm des Rueckfalls, also
            # Biegesteifigkeit (20/10)^3 = 8fach und die Spannung aus Moment um
            # den Faktor 4 zu klein - und welcher Wert es wird, haengt allein
            # daran, welche Flaeche zuerst in der Datei stand.
            #
            # Genannt wird **einmal je Protokoll** und nicht je Aufruf: diese
            # Funktion wird auch je Element gerufen (infocad_txt.py), eine
            # Zeile je Aufruf waere eine Flut (gemessen 40 Zeilen statt 1).
            erbe = next(iter(model.shells))
            meldung = ("WARNUNG: Keine Dicke angegeben - Schalen ohne eigene "
                       f"Dicke erben '{erbe}' "
                       f"({model.shells[erbe].t * 1e3:g} mm)")
            if log is not None and meldung not in log:
                log.append(meldung)
            return erbe
        t = 0.010
        warn(log, f"Keine Dicke fuer Schale '{name or 't10'}' - 10 mm angenommen")
    name = name or f"t{t * 1e3:g}"
    if name not in model.shells:
        model.add_shell_prop(ShellProp(name, float(t)))
    return name


def unique_name(existing, base: str) -> str:
    """Eindeutigen Namen erzeugen (base, base_2, base_3, ...)."""
    if base not in existing:
        return base
    k = 2
    while f"{base}_{k}" in existing:
        k += 1
    return f"{base}_{k}"


# --------------------------------------------------------------------------
# Zahlen / Einheiten / Text
# --------------------------------------------------------------------------
_NUM_RE = re.compile(r"^[+-]?(\d+([.,]\d*)?|[.,]\d+)([eE][+-]?\d+)?$")


def parse_number(value) -> Optional[float]:
    """Zahl aus Zelle: float, '1,5', '1.234,5', '3.5 kN', '-' -> None."""
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s or s in ("-", "--", "—"):
        return None
    # Einheit hinter der Zahl abschneiden ("3.5 kN")
    m = re.match(r"^([+-]?[\d.,]+(?:[eE][+-]?\d+)?)", s)
    if not m:
        return None
    s = m.group(1)
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):       # 1.234,5 (deutsch)
            s = s.replace(".", "").replace(",", ".")
        else:                                 # 1,234.5 (englisch)
            s = s.replace(",", "")
    elif "," in s:
        if s.count(",") == 1:
            s = s.replace(",", ".")           # 1,5
        else:
            s = s.replace(",", "")            # 1,234,567
    if not _NUM_RE.match(s):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def is_truthy(value) -> bool:
    """'x', 'Ja', 'Yes', 'True', '1', Haken -> True."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    s = str(value).strip().lower()
    return s in ("x", "ja", "yes", "y", "j", "true", "wahr", "1", "1.0", "✓", "✔",
                 "fest", "fixed", "rigid", "starr", "gesperrt", "ja.")


# Einheitenfaktoren -> SI. Schluessel werden normalisiert (klein, ohne Leerzeichen,
# Hochzahlen als ^n).
_UNITS = {
    # Laenge
    "m": 1.0, "mm": 1e-3, "cm": 1e-2, "dm": 1e-1, "km": 1e3,
    "in": 0.0254, "ft": 0.3048,
    # Flaeche / Traegheitsmomente
    "m^2": 1.0, "cm^2": 1e-4, "mm^2": 1e-6,
    "m^3": 1.0, "cm^3": 1e-6, "mm^3": 1e-9,
    "m^4": 1.0, "cm^4": 1e-8, "mm^4": 1e-12,
    "m^6": 1.0, "cm^6": 1e-12, "mm^6": 1e-18,
    # Kraft / Moment
    "n": 1.0, "kn": 1e3, "mn": 1e6, "kgf": 9.80665, "lbf": 4.448222,
    "nm": 1.0, "knm": 1e3, "mnm": 1e6, "ncm": 1e-2, "kncm": 10.0,
    # Streckenlast / Flaechenlast
    "n/m": 1.0, "kn/m": 1e3, "mn/m": 1e6, "n/mm": 1e3, "kn/mm": 1e6, "kn/cm": 1e5,
    "n/m^2": 1.0, "kn/m^2": 1e3, "mn/m^2": 1e6, "n/mm^2": 1e6, "kn/cm^2": 1e7,
    "kn/mm^2": 1e9, "mpa": 1e6, "gpa": 1e9, "kpa": 1e3, "pa": 1.0,
    "n/m^3": 1.0, "kn/m^3": 1e3,
    # Steifigkeiten
    "n/rad": 1.0, "nm/rad": 1.0, "knm/rad": 1e3, "mnm/rad": 1e6,
    "kn/rad": 1e3, "mn/rad": 1e6, "knm/°": 1e3 * 180 / math.pi,
    # Dichte / Winkel / Temperatur
    "kg/m^3": 1.0, "t/m^3": 1e3, "g/cm^3": 1e3,
    "°": math.pi / 180.0, "deg": math.pi / 180.0, "grad": math.pi / 180.0, "rad": 1.0,
    "1/k": 1.0, "1/°c": 1.0, "k": 1.0, "°c": 1.0,
}
_SUPERSCRIPT = str.maketrans({"²": "^2", "³": "^3", "⁴": "^4", "⁶": "^6"})


def normalize_unit(text: str) -> str:
    s = str(text).strip().translate(_SUPERSCRIPT).lower()
    s = s.replace(" ", "").replace("**", "^")
    s = re.sub(r"([a-z])(\d)", r"\1^\2", s)       # mm2 -> mm^2
    return s


def unit_factor(header: str, default: float = 1.0) -> float:
    """Einheitenfaktor aus einer Spaltenueberschrift wie 'Kraft Fx [kN]'.

    Gesucht wird der letzte Klammerausdruck [..] bzw. (..) mit bekannter Einheit.
    """
    if not header:
        return default
    found = re.findall(r"[\[(]([^\[\]()]+)[\])]", str(header))
    for u in reversed(found):
        f = _UNITS.get(normalize_unit(u))
        if f is not None:
            return f
    return default


def clean_text(value) -> str:
    """Zelle als bereinigter Text ('' fuer None)."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def norm_key(text) -> str:
    """Spaltenname normalisieren: klein, Umlaute vereinfacht, Einheiten entfernt."""
    s = clean_text(text).lower()
    s = re.sub(r"[\[(][^\[\]()]*[\])]", " ", s)          # Einheiten entfernen
    s = (s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
         .replace("φ", "phi").replace("ϕ", "phi").replace("ψ", "psi").replace("ν", "nu")
         .replace("γ", "gamma").replace("α", "alpha"))
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return s.strip()


def split_list(text, sep: str = r"[;,\s]+") -> list[str]:
    """'1;2;3' / '1, 2' / '1 2' -> ['1', '2', '3']."""
    s = clean_text(text)
    if not s:
        return []
    return [p for p in re.split(sep, s) if p]


def expand_ranges(items: list[str]) -> list[str]:
    """['1-3', '5'] -> ['1', '2', '3', '5'] (RFEM-Listen)."""
    out = []
    for it in items:
        m = re.match(r"^(\d+)\s*-\s*(\d+)$", it)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            out.extend(str(k) for k in range(min(a, b), max(a, b) + 1))
        else:
            out.append(it)
    return out


def category_from_text(text, default: str = "Q") -> str:
    """Einwirkungskategorie (Schluessel in ACTION_CATEGORIES) aus Freitext."""
    s = norm_key(text)
    if not s:
        return default
    if re.search(r"staendig|permanent|dead|eigengewicht|self ?weight|\bg\b", s):
        return "G"
    if re.search(r"vorspann|prestress|\bp\b", s):
        return "P"
    if re.search(r"schnee|snow", s):
        return "S_H" if re.search(r"1000|ueber|above", s) else "S"
    if re.search(r"wind", s):
        return "W"
    if re.search(r"temperatur|thermal|\bt\b", s):
        return "T"
    if re.search(r"wasser|hydro|water", s):
        return "H"
    if re.search(r"setzung|settlement", s):
        return "SET"
    if re.search(r"ermued|fatigue", s):
        return "FAT"
    if re.search(r"aussergew|accident|erdbeben|seismic|seism|anprall|explosion|fire|brand", s):
        return "A"
    if re.search(r"kran|crane", s):
        return "Q_K"
    m = re.search(r"(?:kat(?:egorie)?|cat(?:egory)?)\.?\s*([a-h])\b", s)
    if m:
        cat = "Q_" + m.group(1).upper()
        if cat in ACTION_CATEGORIES:
            return cat
    if re.search(r"nutz|verkehr|imposed|live|variable|veraenderlich|traffic|\bq\b", s):
        return "Q"
    return default


# --------------------------------------------------------------------------
# Geometrie
# --------------------------------------------------------------------------
def polygon_to_shells(model: Model, node_ids: list[int], mat: str, prop: str,
                      group: str = "default", log: list = None,
                      what: str = "Flaeche") -> list[int]:
    """Polygon (Knotenindizes) in Schalenelemente umsetzen.

    3 Knoten -> shell3, 4 -> shell4, mehr -> Faecher-Triangulierung mit Warnung.
    Doppelte aufeinanderfolgende Knoten werden entfernt.
    """
    ids = []
    for n in node_ids:
        if not ids or ids[-1] != n:
            ids.append(int(n))
    if len(ids) > 1 and ids[0] == ids[-1]:
        ids.pop()
    if len(ids) < 3:
        warn(log, f"{what}: weniger als 3 verschiedene Knoten - uebersprungen")
        return []
    out = []
    if len(ids) == 3:
        out.append(model.add_element("shell3", ids, mat, prop, group=group))
    elif len(ids) == 4:
        out.append(model.add_element("shell4", ids, mat, prop, group=group))
    else:
        warn(log, f"{what}: Polygon mit {len(ids)} Knoten wurde als Faecher trianguliert - "
                  f"fuer die Berechnung sollte ein feineres Netz erzeugt werden")
        for i in range(1, len(ids) - 1):
            out.append(model.add_element("shell3", [ids[0], ids[i], ids[i + 1]],
                                         mat, prop, group=group))
    return out


def roll_from_vector(p1, p2, vec, axis: str = "y") -> float:
    """Verdrehwinkel [rad], damit die lokale y- (oder z-) Achse eines Stabes von
    p1 nach p2 in Richtung 'vec' (projiziert senkrecht zur Stabachse) zeigt."""
    from ..elements.beam3d import local_axes
    try:
        T3, _ = local_axes(np.asarray(p1, float), np.asarray(p2, float), 0.0)
    except ValueError:
        return 0.0
    ex, ey, ez = T3
    v = np.asarray(vec, float)
    v = v - np.dot(v, ex) * ex
    n = np.linalg.norm(v)
    if n < 1e-12:
        return 0.0
    v /= n
    if axis == "y":
        return float(math.atan2(np.dot(v, ez), np.dot(v, ey)))
    return float(math.atan2(-np.dot(v, ey), np.dot(v, ez)))


def subdivide_line(nodes: NodeIndex, p1, p2, n: int) -> list[int]:
    """Knotenkette von p1 nach p2 mit n Abschnitten (n+1 Knoten)."""
    p1 = np.asarray(p1, float)
    p2 = np.asarray(p2, float)
    n = max(1, int(n))
    return [nodes.add(*(p1 + (p2 - p1) * (k / n))) for k in range(n + 1)]


# --------------------------------------------------------------------------
# Lastfaelle
# --------------------------------------------------------------------------
#: Die Eigenschaften eines Lastfalls: alle Felder ausser dem Namen und den
#: Lastlisten (die Felder mit ``default_factory``, dazu das Eigengewicht).
#: Aus dem Datenmodell abgeleitet und nicht aufgezaehlt - bis zum 22.09.2026
#: legte das Anhaengen eines JSON-Modells neue Lastfaelle nur mit Name,
#: Kategorie und Beschreibung an; psi, gamma, Grundlast, Situation, Theorie,
#: Nummer und Exklusivgruppe fielen auf die Vorgabe (Befund SV11: Grundlast
#: True kam als False an). Ein kuenftig ergaenztes Feld kommt so von selbst mit.
LASTFALL_EIGENSCHAFTEN = tuple(f.name for f in fields(LoadCase)
                               if f.name != "name" and f.default_factory is MISSING)


def get_or_add_case(model: Model, name: str, category: str = "Q",
                    description: str = "", vorlage: LoadCase = None, **kw):
    """Lastfall holen oder anlegen (ohne den aktiven Lastfall zu wechseln).

    vorlage: ein Lastfall, dessen Eigenschaften (:data:`LASTFALL_EIGENSCHAFTEN`)
             ein **neu angelegter** uebernimmt - auch Kategorie und
             Beschreibung; ``kw`` geht vor (etwa eine umbenannte Situation).
             Ein vorhandener Lastfall bleibt, wie er ist: ob seine
             Eigenschaften zur Vorlage passen, prueft der Aufrufer.
    """
    if name in model.load_cases:
        return model.load_cases[name]
    if vorlage is not None:
        eig = {f: copy.deepcopy(getattr(vorlage, f)) for f in LASTFALL_EIGENSCHAFTEN}
        eig.update(kw)
        category = eig.pop("category", category)
        description = eig.pop("description", description)
        kw = eig
    if category not in ACTION_CATEGORIES:
        category = "Q"
    return model.add_load_case(name, category, description, activate=False, **kw)


def drop_empty_default_case(model: Model, name: str = "LF1") -> bool:
    """Leeren Standardlastfall entfernen, wenn der Import eigene Lastfaelle brachte."""
    lc = model.load_cases.get(name)
    if lc is None or len(model.load_cases) < 2 or lc.n_loads:
        return False
    for c in model.combinations.values():
        if name in c.factors:
            return False
    for f in model.fatigue_loads.values():
        if name in (f.case_max, f.case_min):
            return False
    model.remove_load_case(name)
    return True
