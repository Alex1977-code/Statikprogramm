"""
Netzguete: wie gut ist die **Form** der Elemente?

Ein FE-Ergebnis ist nur so gut wie das Netz, auf dem es steht. Lang gezogene,
flache oder schiefe Elemente machen die Steifigkeitsmatrix schlecht
konditioniert und die Spannungen an dieser Stelle unbrauchbar - die
Verschiebungen bleiben meist noch brauchbar, die Spannungen nicht.

Zwei Masse, beide so normiert, dass **1 die beste Form** ist:

* **Formguete** (ANSYS und RFEM: *element quality*) - misst, wie nah das
  Element an seiner regelmaessigen Gestalt ist.

  - Tetraeder:  q = 12 · (3V)^(2/3) / Σ l_i²  - der regelmaessige Tetraeder
    bekommt 1, der flache 0.
  - Dreieck:    q = 4√3 · A / Σ l_i²  - das gleichseitige Dreieck bekommt 1.
  - Viereck, Sechsflaechner, Keil, Pyramide: die **skalierte
    Jacobi-Determinante**, also das Minimum ueber alle Ecken von

        det[ e₁/|e₁|  e₂/|e₂|  e₃/|e₃| ]      (raeumlich)
        |e₁/|e₁| × e₂/|e₂||                   (eben)

    Der Wuerfel und das Quadrat bekommen 1, eine zur Ebene entartete Ecke 0.
    Eine **umgestuelpte** Ecke gibt einen negativen Wert; solche Elemente
    rechnen falsch und werden eigens gezaehlt.

* **Seitenverhaeltnis** (*aspect ratio*) - laengste durch kuerzeste Kante.
  Hier ist 1 das Beste, groessere Werte sind schlechter; fuer die
  gemeinsame Skala wird der Kehrwert gezeigt.

Staebe, Seile, Federn und Grenzschichten haben keine Form in diesem Sinn;
sie bekommen ``nan`` und bleiben in der Ansicht grau.

Die Berechnung ist je Elementart vektorisiert - ein Volumennetz mit einer
halben Million Tetraedern muss in Sekunden durch sein.
"""
from __future__ import annotations

import numpy as np

from . import elemente as _EL

#: Die Ecken jeder Elementart und, je Ecke, ihre Nachbarecken. Daraus
#: entstehen die Kantenvektoren fuer die skalierte Jacobi-Determinante.
ECKEN_NACHBARN: dict = {
    "hex8": [(0, (1, 3, 4)), (1, (2, 0, 5)), (2, (3, 1, 6)), (3, (0, 2, 7)),
             (4, (7, 5, 0)), (5, (4, 6, 1)), (6, (5, 7, 2)), (7, (6, 4, 3))],
    "pent6": [(0, (1, 2, 3)), (1, (2, 0, 4)), (2, (0, 1, 5)),
              (3, (5, 4, 0)), (4, (3, 5, 1)), (5, (4, 3, 2))],
    "pyr5": [(0, (1, 3, 4)), (1, (2, 0, 4)), (2, (3, 1, 4)), (3, (0, 2, 4))],
    "quad": [(0, (1, 3)), (1, (2, 0)), (2, (3, 1)), (3, (0, 2))],
}

#: Der Wert der skalierten Jacobi-Determinante an der Ecke der **besten**
#: Form dieser Art. Beim Wuerfel und beim Quadrat stossen die Kanten
#: rechtwinklig aufeinander, das gibt 1. Beim Keil ist die Grundflaeche ein
#: gleichseitiges Dreieck (60°, also sin 60° = √3/2), bei der Pyramide mit
#: gleich langen Kanten √2/2. Ohne diese Normierung bekaeme der beste Keil
#: nur 0,866 - genauso normieren es ANSYS und RFEM.
IDEAL: dict = {"hex8": 1.0, "quad": 1.0,
               "pent6": np.sqrt(3.0) / 2.0, "pyr5": np.sqrt(2.0) / 2.0}

#: Kanten je Elementart - fuer das Seitenverhaeltnis und die Kantenlaenge.
KANTEN: dict = {
    "tet": [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)],
    "tri": [(0, 1), (1, 2), (2, 0)],
    "quad": [(0, 1), (1, 2), (2, 3), (3, 0)],
    "hex8": [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
             (0, 4), (1, 5), (2, 6), (3, 7)],
    "pent6": [(0, 1), (1, 2), (2, 0), (3, 4), (4, 5), (5, 3), (0, 3), (1, 4), (2, 5)],
    "pyr5": [(0, 1), (1, 2), (2, 3), (3, 0), (0, 4), (1, 4), (2, 4), (3, 4)],
}

#: Elementart -> (Familie fuer die Formel, Zahl der Eckknoten)
FORM: dict = {
    "tet4": ("tet", 4), "tet10": ("tet", 4),
    "hex8": ("hex8", 8), "hex20": ("hex8", 8),
    "pent6": ("pent6", 6), "pent15": ("pent6", 6),
    "pyr5": ("pyr5", 5),
    "shell3": ("tri", 3), "shell6": ("tri", 3),
    "ebene3": ("tri", 3), "ebene6": ("tri", 3),
    "shell4": ("quad", 4), "shell8": ("quad", 4),
    "ebene4": ("quad", 4), "ebene8": ("quad", 4),
}

#: Die Bewertungsstufen - so redet man in der Netzprüfung darüber.
STUFEN = [(0.70, "sehr gut"), (0.40, "gut"), (0.20, "brauchbar"),
          (0.05, "schlecht"), (-1e30, "unbrauchbar")]

#: Unter diesem Wert ist ein Element ein Splitter (ANSYS: sliver).
SPLITTER = 0.10

MASSE = ("formguete", "seitenverhaeltnis", "kantenlaenge")


def _eckpunkte(model, idx: np.ndarray, n_ecken: int):
    """Die Eckkoordinaten (n, n_ecken, 3) - bei quadratischen Elementen
    stehen die Ecken vorn, die Seitenmitten dahinter."""
    K = np.array([[int(x) for x in model.elements[i].nodes[:n_ecken]] for i in idx], dtype=int)
    if K.ndim != 2 or K.shape[1] != n_ecken:
        return None
    if (K < 0).any() or (K >= model.nn).any():
        return None
    return model.nodes[K]


def _skalierte_jacobi(X: np.ndarray, art: str) -> np.ndarray:
    """Minimum der skalierten Jacobi-Determinante ueber alle Ecken."""
    out = np.full(len(X), np.inf)
    for ecke, nachbarn in ECKEN_NACHBARN[art]:
        e = [X[:, n] - X[:, ecke] for n in nachbarn]
        L = [np.linalg.norm(v, axis=1) for v in e]
        gut = np.ones(len(X), bool)
        for l in L:
            gut &= l > 0
        eh = [np.divide(v, l[:, None], out=np.zeros_like(v), where=(l > 0)[:, None])
              for v, l in zip(e, L)]
        if len(eh) == 3:
            wert = np.einsum("ij,ij->i", eh[0], np.cross(eh[1], eh[2]))
        else:
            wert = np.linalg.norm(np.cross(eh[0], eh[1]), axis=1)
        wert = np.where(gut, wert, 0.0)
        out = np.minimum(out, wert)
    return np.where(np.isfinite(out), out, 0.0)


def _formguete(X: np.ndarray, art: str) -> np.ndarray:
    if art == "tet":
        V = np.abs(np.einsum("ij,ij->i", X[:, 1] - X[:, 0],
                             np.cross(X[:, 2] - X[:, 0], X[:, 3] - X[:, 0]))) / 6.0
        L2 = sum(np.sum((X[:, a] - X[:, b]) ** 2, axis=1) for a, b in KANTEN["tet"])
        q = np.zeros(len(X))
        mit = L2 > 0
        q[mit] = 12.0 * (3.0 * V[mit]) ** (2.0 / 3.0) / L2[mit]
        return np.clip(q, 0.0, 1.0)
    if art == "tri":
        A = 0.5 * np.linalg.norm(np.cross(X[:, 1] - X[:, 0], X[:, 2] - X[:, 0]), axis=1)
        L2 = sum(np.sum((X[:, a] - X[:, b]) ** 2, axis=1) for a, b in KANTEN["tri"])
        q = np.zeros(len(X))
        mit = L2 > 0
        q[mit] = 4.0 * np.sqrt(3.0) * A[mit] / L2[mit]
        return np.clip(q, 0.0, 1.0)
    return np.clip(_skalierte_jacobi(X, art) / IDEAL[art], -1.0, 1.0)


def _kantenlaengen(X: np.ndarray, art: str) -> np.ndarray:
    schl = "tet" if art == "tet" else art
    return np.stack([np.linalg.norm(X[:, a] - X[:, b], axis=1)
                     for a, b in KANTEN[schl]], axis=1)


def guete(model, mass: str = "formguete") -> np.ndarray:
    """Je Element ein Wert; ``nan``, wo das Mass keinen Sinn hat (Staebe,
    Federn, Grenzschichten, kaputte Knotenverweise).

    ``mass``: ``"formguete"`` (0 … 1, 1 = beste Form), ``"seitenverhaeltnis"``
    (kuerzeste durch laengste Kante, 1 = alle Kanten gleich lang) oder
    ``"kantenlaenge"`` (laengste Kante in m).
    """
    if mass not in MASSE:
        raise ValueError(f"unbekanntes Maß '{mass}' - möglich: {', '.join(MASSE)}")
    out = np.full(len(model.elements), np.nan)
    gruppen: dict = {}
    for i, e in enumerate(model.elements):
        if e.typ in FORM:
            gruppen.setdefault(e.typ, []).append(i)
    for typ, liste in gruppen.items():
        art, n_ecken = FORM[typ]
        idx = np.asarray(liste, int)
        X = _eckpunkte(model, idx, n_ecken)
        if X is None:
            continue
        if mass == "formguete":
            out[idx] = _formguete(X, art)
        else:
            L = _kantenlaengen(X, art)
            if mass == "kantenlaenge":
                out[idx] = L.max(axis=1)
            else:
                lang = L.max(axis=1)
                out[idx] = np.where(lang > 0, L.min(axis=1) / np.maximum(lang, 1e-300), 0.0)
    return out


def bewertung(wert: float) -> str:
    """Die Stufe zu einem Formgütewert."""
    if not np.isfinite(wert):
        return "ohne Form"
    for grenze, name in STUFEN:
        if wert >= grenze:
            return name
    return "unbrauchbar"


def kennwerte(model, mass: str = "formguete", q: np.ndarray = None) -> dict:
    """Kennzahlen zum Netz: Anzahl, min, Mittel, Stufen, schlechteste
    Elemente. ``q`` kann eine schon berechnete Reihe sein."""
    q = guete(model, mass) if q is None else np.asarray(q, float)
    mit = np.isfinite(q)
    n = int(mit.sum())
    d = {"mass": mass, "bewertet": n, "elemente": len(q), "ohne_form": int(len(q) - n)}
    if not n:
        return dict(d, min=float("nan"), mittel=float("nan"), max=float("nan"),
                    stufen=[], splitter=0, umgestuelpt=0, schlechteste=[])
    w = q[mit]
    d.update(min=float(w.min()), mittel=float(w.mean()), max=float(w.max()))
    if mass == "formguete":
        stufen, rest = [], np.ones(len(w), bool)
        for grenze, name in STUFEN:
            drin = rest & (w >= grenze)
            stufen.append((name, int(drin.sum()), float(grenze)))
            rest &= ~drin
        d["stufen"] = stufen
        d["splitter"] = int((w < SPLITTER).sum())
        d["umgestuelpt"] = int((w < 0).sum())
    else:
        d["stufen"] = []
        d["splitter"] = 0
        d["umgestuelpt"] = 0
    ordnung = np.argsort(np.where(mit, q, np.inf))
    d["schlechteste"] = [(int(i), float(q[i])) for i in ordnung[:20] if mit[i]]
    return d


def bericht(model, mass: str = "formguete", q: np.ndarray = None) -> list:
    """Die Kennzahlen als Zeilen fuers Protokoll."""
    d = kennwerte(model, mass, q)
    name = {"formguete": "Formgüte", "seitenverhaeltnis": "Seitenverhältnis",
            "kantenlaenge": "Kantenlänge"}[mass]
    if not d["bewertet"]:
        return [f"Netzqualität ({name}): kein Element mit auswertbarer Form "
                f"({d['elemente']} Elemente)"]
    einheit = " m" if mass == "kantenlaenge" else ""
    z = [f"Netzqualität ({name}): {d['bewertet']} Elemente bewertet, "
         f"min {d['min']:.3f}{einheit}, Mittel {d['mittel']:.3f}{einheit}, "
         f"max {d['max']:.3f}{einheit}"
         + (f"; {d['ohne_form']} ohne Form (Stäbe, Federn, Grenzschichten)"
            if d["ohne_form"] else "")]
    if d["stufen"]:
        anteil = lambda k: 100.0 * k / max(1, d["bewertet"])          # noqa: E731
        z.append("  " + ", ".join(f"{nm} {k} ({anteil(k):.1f} %)"
                                  for nm, k, _g in d["stufen"] if k))
    if d["splitter"]:
        z.append(f"  {d['splitter']} Splitter unter {SPLITTER:.2f} - dort sind die "
                 "Spannungen unbrauchbar; feiner vernetzen oder die Geometrie "
                 "an der Stelle bereinigen")
    if d["umgestuelpt"]:
        n = d["umgestuelpt"]
        z.append(f"  {n} umgestülpte{'s' if n == 1 else ''} Element{'' if n == 1 else 'e'} "
                 "(negative Jacobi-Determinante) - "
                 + ("das rechnet" if n == 1 else "die rechnen")
                 + " falsch und muss neu vernetzt werden"
                 if n == 1 else
                 f"  {n} umgestülpte Elemente (negative Jacobi-Determinante) - "
                 "die rechnen falsch und müssen neu vernetzt werden")
    if d["schlechteste"]:
        z.append("  schlechteste: " + ", ".join(
            f"Element {i + 1} ({model.elements[i].typ}) {v:.3f}"
            for i, v in d["schlechteste"][:5]))
    return z
