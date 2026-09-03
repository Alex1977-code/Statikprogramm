"""
Geometrie aus dem HiCAD-Szenenteil (SZN).

Der Aufbau wurde an echten Dateien ausgelesen und ist hier belegt, nicht
geraten. Eine SZN beginnt mit der Kennung::

    FILE-CONTAINER ISD  1.0\\0

Danach folgt ein Strom aus **Fortran-Saetzen**: jeder Satz steht zwischen zwei
gleichen 32-Bit-Laengen (``<n><Daten:n><n>``), wie es die unformatierte
sequentielle Ausgabe von Fortran schreibt - der Rechenkern von HiCAD kommt aus
dieser Welt. Die Satzkette endet in beiden Prueffiles punktgenau am Dateiende;
das ist der Beleg, dass der Aufbau stimmt.

Der Behaelter ist in Abschnitte geteilt. Jeder Abschnitt beginnt mit dem Satz
``FILE-CONT-SECTION``, danach die Groesse, die Namenslaenge und der Name:

    ================  ==================================================
    ``SZN_HEA``       Kopf der Szene
    ``SZN_KRP``       Koerper (Rumpfdaten)
    ``SZ_LEAF``       ein Blatt der Szene - **ein Bauteil oder Feature**
    ``CESF_LF``       Flaechen-/Kantenzusatz zum Blatt
    ``TFBF_LF``       Zusatz zum Blatt
    ================  ==================================================

Ein ``SZ_LEAF`` fuehrt drei Saetze: Nummer, Anzahl der Eintraege und die
Eintragsliste mit **40 Byte je Eintrag**::

    x, y, z   3 x float64   Koordinate in Millimetern
    a, t      2 x uint32    Kennung und Art
    c, e      2 x uint32    Zusatz (in den Prueffiles 0)

Die Art ``t`` unterscheidet:

    =====  ========================================================
    1      Konstruktionspunkt (Kontur, Hilfspunkt)
    2      Eckpunkt des Koerpers
    5      Richtungsvektor (Einheitsvektor, z. B. die Auszugsrichtung)
    3      seltener Sonderfall
    4003   **Achse des Bauteils** - zwei Punkte, Anfang und Ende
    50003  Bezugssystem (Ursprung und zwei Achspunkte)
    =====  ========================================================

Die Art 4003 ist der Schluessel: Wo sie steht, nennt HiCAD die Stabachse
unmittelbar - in der Prueffile fuer 21 Bauteile, und die Laengen sind runde
Werte (928,0 mm, 5518,0 mm), die Achsen liegen genau auf den Profilschwerlinien.
Der Querschnitt wird senkrecht zu dieser Achse aus den Eckpunkten gemessen und
in den mitgelieferten Teiletabellen gesucht: 206,0 x 78,9 mm findet 'U 200',
100,1 mm findet 'Fl 100x10', 60,9 mm findet 'Fl 60x20'.

Daraus laesst sich je Bauteil die **Lage im Bauwerk** bestimmen: die
Hauptachse der Punktwolke ist die Stabachse, ihre Ausdehnung die Laenge, die
beiden Querausdehnungen sind Hoehe und Breite des Querschnitts. Der Querschnitt
wird ueber diese gemessenen Masse in den mitgelieferten Teiletabellen gesucht.

**Was das ist und was nicht.** Das ist eine aus den Konstruktionspunkten
abgeleitete Ersatzgeometrie - ein Stabmodell an der richtigen Stelle, kein
Nachbau des HiCAD-Volumenmodells. Die Flaechen- und Kantentopologie steht in
den Abschnitten ``CESF_LF``/``TFBF_LF`` in einer Form, die hier nicht gedeutet
wird. Wer die genaue Geometrie braucht, nimmt den von HiCAD vorgesehenen Weg
(SDNF, DSTV-NC, IFC, STEP).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

import numpy as np

#: Kennung am Anfang einer SZN
MAGIC = b"FILE-CONTAINER ISD  1.0\x00"

#: Name des Abschnitts, der einen neuen Abschnitt einleitet
SECTION = b"FILE-CONT-SECTION"

#: Laenge eines Eintrags in der Punktliste eines Blattes
ENTRY = 40

#: Arten der Eintraege (belegt an den Prueffiles)
PUNKT_ARTEN = (1, 2)
ECKPUNKT = 2
RICHTUNG = 5
#: Achse eines Bauteils: zwei Punkte
ACHSE = 4003
#: Bezugssystem: Ursprung und zwei Achspunkte
BEZUG = 50003

#: Millimeter -> Meter
MM = 1e-3


class SznError(ValueError):
    """Die Datei ist kein lesbarer SZN-Behaelter."""


# --------------------------------------------------------------------------
# Satzstrom
# --------------------------------------------------------------------------
def is_szn(data: bytes) -> bool:
    return data[:len(MAGIC)] == MAGIC


def records(data: bytes, strict: bool = False) -> list[tuple[int, bytes]]:
    """Alle Fortran-Saetze als [(Offset, Daten)].

    strict=True verlangt, dass die Kette punktgenau am Dateiende endet.
    """
    if not is_szn(data):
        raise SznError("Kein SZN-Behaelter (Kennung fehlt)")
    pos, out = len(MAGIC), []
    n_data = len(data)
    while pos + 8 <= n_data:
        (n,) = struct.unpack_from("<I", data, pos)
        if n > n_data - pos - 8:
            break
        (n2,) = struct.unpack_from("<I", data, pos + 4 + n)
        if n2 != n:
            break
        out.append((pos, data[pos + 4:pos + 4 + n]))
        pos += 8 + n
    if strict and pos != n_data:
        raise SznError(f"Satzkette endet bei {pos}, Datei ist {n_data} Byte lang")
    return out


def sections(recs: list) -> list[tuple[str, int, int]]:
    """[(Name, erster Satz nach dem Namen, letzter Satz)] aller Abschnitte."""
    marken = [i for i, (_p, b) in enumerate(recs) if b[:len(SECTION)] == SECTION]
    out = []
    for k, i in enumerate(marken):
        # <FILE-CONT-SECTION> <Groesse> <Namenslaenge> <Name>
        if i + 3 >= len(recs):
            break
        name = recs[i + 3][1].rstrip(b"\0").decode("latin-1", "replace")
        ende = marken[k + 1] if k + 1 < len(marken) else len(recs)
        out.append((name, i + 4, ende))
    return out


# --------------------------------------------------------------------------
# Blaetter (Bauteile)
# --------------------------------------------------------------------------
@dataclass
class Blatt:
    """Ein Blatt der Szene: Nummer und Punktwolke in Metern."""
    nummer: int
    punkte: np.ndarray = field(default_factory=lambda: np.zeros((0, 3)))
    arten: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=int))

    @property
    def koerperpunkte(self) -> np.ndarray:
        """Punkte, die den Koerper beschreiben (ohne Richtungsvektoren)."""
        return self.punkte[np.isin(self.arten, PUNKT_ARTEN)]


def leaves(data: bytes) -> list[Blatt]:
    """Alle Blaetter der Szene mit ihren Punkten (in Metern)."""
    recs = records(data)
    out = []
    for name, i0, i1 in sections(recs):
        if name != "SZ_LEAF":
            continue
        teile = [b for _p, b in recs[i0:i1]]
        if len(teile) < 2 or len(teile[0]) != 4 or len(teile[1]) != 4:
            continue
        nummer = struct.unpack("<I", teile[0])[0]
        n = struct.unpack("<I", teile[1])[0]
        if not n or len(teile) < 3 or len(teile[2]) != n * ENTRY:
            out.append(Blatt(nummer))
            continue
        roh = teile[2]
        xyz = np.frombuffer(roh, dtype="<f8").reshape(n, 5)[:, :3] * MM
        art = np.frombuffer(roh, dtype="<u4").reshape(n, 10)[:, 7]
        out.append(Blatt(nummer, np.ascontiguousarray(xyz),
                         np.ascontiguousarray(art.astype(int))))
    return out


# --------------------------------------------------------------------------
# Lage und Abmessungen eines Bauteils
# --------------------------------------------------------------------------
@dataclass
class Koerper:
    """Lage und Abmessungen eines Bauteils."""
    nummer: int
    art: str                 # "stab" | "blech" | "sonstiges"
    p1: np.ndarray           # Anfang der Achse [m]
    p2: np.ndarray           # Ende der Achse [m]
    achse: np.ndarray        # Einheitsvektor der Achse
    L: float                 # Laenge [m]
    h: float                 # groessere Querabmessung [m]
    b: float                 # kleinere Querabmessung [m]
    n_punkte: int = 0
    quelle: str = ""         # "Achse 4003" oder "Hauptachse der Punktwolke"

    def beschreibung(self) -> str:
        return (f"Teil {self.nummer}: {self.art}, L = {self.L * 1e3:.0f} mm, "
                f"Querschnitt {self.h * 1e3:.1f} x {self.b * 1e3:.1f} mm "
                f"({self.quelle})")


def _querschnitt(pts: np.ndarray, p1: np.ndarray, e1: np.ndarray) -> tuple:
    """Hoehe und Breite senkrecht zur Achse (grosse Abmessung zuerst)."""
    if len(pts) < 3:
        return 0.0, 0.0
    q = pts - p1
    q = q - np.outer(q @ e1, e1)
    _u, _s, vt = np.linalg.svd(q - q.mean(0), full_matrices=False)
    d = []
    for k in range(min(2, len(vt))):
        w = q @ vt[k]
        d.append(float(w.max() - w.min()))
    while len(d) < 2:
        d.append(0.0)
    return max(d), min(d)


def koerper(blatt: Blatt, min_laenge: float = 0.1, schlank: float = 3.0,
            max_dicke: float = 0.08) -> Koerper:
    """Achse, Laenge und Querabmessungen eines Blattes.

    Nennt das Blatt seine Achse selbst (Art 4003), wird sie genommen - das ist
    die Angabe von HiCAD, nicht unsere Schaetzung. Sonst wird die Hauptachse
    der Punktwolke bestimmt (Singulaerwertzerlegung) und als solche gekennzeichnet.
    """
    A = blatt.punkte[blatt.arten == ACHSE]
    pts = blatt.koerperpunkte
    ecken = blatt.punkte[blatt.arten == ECKPUNKT]
    if len(A) >= 2:
        p1, p2 = A[0], A[-1]
        L = float(np.linalg.norm(p2 - p1))
        if L > 1e-9:
            e1 = (p2 - p1) / L
            h, b = _querschnitt(ecken if len(ecken) >= 3 else pts, p1, e1)
            return Koerper(blatt.nummer, "stab", p1, p2, e1, L, h, b,
                           len(pts), "Achse 4003")
    if len(pts) < 4:
        return Koerper(blatt.nummer, "sonstiges", np.zeros(3), np.zeros(3),
                       np.array([1.0, 0.0, 0.0]), 0.0, 0.0, 0.0, len(pts), "-")
    c = pts.mean(0)
    _u, _s, vt = np.linalg.svd(pts - c, full_matrices=False)
    e1 = vt[0]
    t = (pts - c) @ e1
    L = float(t.max() - t.min())
    h, b = _querschnitt(pts, c, e1)
    art = "sonstiges"
    if L >= min_laenge and L >= schlank * h:
        art = "stab"
    elif b <= max_dicke and h > 3 * b and L >= min_laenge:
        art = "blech"
    return Koerper(blatt.nummer, art, c + e1 * t.min(), c + e1 * t.max(),
                   e1, L, h, b, len(pts), "Hauptachse der Punktwolke")


# --------------------------------------------------------------------------
# Querschnitt zu gemessenen Abmessungen suchen
# --------------------------------------------------------------------------
def passendes_profil(h: float, b: float, profile: dict, grenze: float = 0.06,
                     ueber: float = 2.6, unter: float = 1.15) -> tuple:
    """Querschnitt, dessen Katalogmasse zu den gemessenen Massen passen.

    Entscheidend ist die **grosse** Abmessung: sie steht in der Punktwolke
    genau - 206,0 mm fuer ein U 200, 100,1 mm fuer ein Fl 100x10, 701,2 mm
    fuer ein HEB 700. Sie muss innerhalb von ``grenze`` stimmen.

    Die **kleine** Abmessung darf nur nach oben abweichen: die Wolke enthaelt
    auch die Punkte der angeschweissten Nachbarteile, also messen wir dort
    hoechstens zu gross, nie zu klein. Ein Profil, das breiter waere als
    gemessen (Faktor ``unter``), kann es darum nicht sein und wird verworfen;
    nach oben sind bis ``ueber`` erlaubt.

    Rueckgabe: (Name, Abweichung h [m], Abweichung b [m]) oder (None, 0, 0).
    """
    best, bestfehler = None, None
    for name, sec in profile.items():
        sh = float(getattr(sec, "h", 0.0) or 0.0)
        sb = float(getattr(sec, "b", 0.0) or 0.0)
        if sh <= 0 or sb <= 0:
            continue
        kh, kb = (sh, sb) if sh >= sb else (sb, sh)
        fh = abs(kh - h) / max(h, 1e-6)
        if fh > grenze:
            continue
        if kb > b * unter or kb * ueber < b:
            continue
        fehler = fh + 0.05 * abs(kb - b) / max(b, 1e-6)
        if bestfehler is None or fehler < bestfehler:
            best, bestfehler = (name, kh, kb), fehler
    if best is None:
        return (None, 0.0, 0.0)
    return (best[0], h - best[1], b - best[2])


# --------------------------------------------------------------------------
# Bauteile der Szene
# --------------------------------------------------------------------------
def teile(data: bytes, **kw) -> list[Koerper]:
    """Alle Bauteile der Szene mit Lage und Abmessungen."""
    return [koerper(bl, **kw) for bl in leaves(data)]


def _flaeche(k: Koerper) -> float:
    return k.h * k.b


#: Kleinere Teile werden nicht als Stab uebernommen (Schrauben, Stifte, Zapfen)
MIN_LAENGE = 0.10          # [m]
MIN_HOEHE = 0.008          # [m]
MIN_BREITE = 0.003         # [m]


def staebe(data: bytes, nur_achse: bool = True, min_laenge: float = MIN_LAENGE,
           min_hoehe: float = MIN_HOEHE, min_breite: float = MIN_BREITE,
           **kw) -> list[Koerper]:
    """Die stabartigen Bauteile, Doppelnennungen derselben Achse entfernt.

    HiCAD fuehrt ein Bauteil und die daran angeschweisste Baugruppe als eigene
    Blaetter mit **derselben** Achse. Behalten wird das Blatt mit dem kleineren
    Querschnitt - das ist das Profil selbst, nicht die Baugruppe.
    """
    ks = [k for k in teile(data, **kw)
          if k.art == "stab"
          and (not nur_achse or k.quelle == "Achse 4003")
          and k.L >= min_laenge and k.h >= min_hoehe and k.b >= min_breite]
    nach_achse: dict = {}
    for k in ks:
        # Achse auf 1 mm gerundet als Schluessel, Richtung ohne Vorzeichen
        a = tuple(np.round(k.p1 * 1e3).astype(int))
        b = tuple(np.round(k.p2 * 1e3).astype(int))
        key = (a, b) if a <= b else (b, a)
        vor = nach_achse.get(key)
        if vor is None or _flaeche(k) < _flaeche(vor):
            nach_achse[key] = k
    return sorted(nach_achse.values(), key=lambda k: k.nummer)


def uebersicht(data: bytes) -> str:
    """Kurze Uebersicht ueber die Geometrie der Szene."""
    ks = teile(data)
    st = staebe(data)
    blech = [k for k in ks if k.art == "blech"]
    z = [f"SZN-Szene: {len(ks)} Blaetter, {sum(k.n_punkte for k in ks)} Punkte",
         f"  Staebe mit eigener Achse: {len(st)}, blechartig: {len(blech)}"]
    for k in st:
        z.append("  " + k.beschreibung())
    return "\n".join(z)


# --------------------------------------------------------------------------
# Stabmodell aufbauen
# --------------------------------------------------------------------------
def in_modell(data: bytes, model, profile: dict = None, material: str = None,
              toleranz: float = 0.005, log: list = None, **kw) -> dict:
    """Die Staebe der Szene als Stabelemente in ein Modell legen.

    profile:   Querschnitte, in denen der passende gesucht wird (Name -> Section)
    material:  Werkstoff der Staebe (Name im Modell)
    toleranz:  Knoten, die naeher zusammenliegen, werden zusammengefuehrt [m]

    Rueckgabe: {"staebe": n, "knoten": n, "ohne_profil": [...]}
    """
    from ..model import Section
    from . import _common as C

    st = staebe(data, **kw)
    if not st:
        return {"staebe": 0, "knoten": 0, "ohne_profil": []}
    profile = profile or {}
    if material is None:
        material = next(iter(model.materials), None)
    if material is None:
        from ..model import Material
        model.add_material(Material.steel("S235"))
        material = "S235"

    knoten: dict = {}

    def knoten_nr(p) -> int:
        key = tuple(np.round(np.asarray(p, float) / toleranz).astype(int))
        if key in knoten:
            return knoten[key]
        i = model.add_node(float(p[0]), float(p[1]), float(p[2]))
        knoten[key] = i
        return i

    ohne, n_stab = [], 0
    for k in st:
        name, dh, db = passendes_profil(k.h, k.b, profile)
        if name is None:
            # Kein Katalogprofil passt: Ersatzrechteck aus den gemessenen
            # Massen, damit das Modell rechenbar bleibt - und benannt, damit
            # niemand es fuer ein Katalogprofil haelt.
            name = C.unique_name(model.sections,
                                 f"gemessen {k.h * 1e3:.0f}x{k.b * 1e3:.0f}")
            model.add_section(Section.rectangle(name, k.b, k.h))
            ohne.append((k.nummer, name))
            C.say(log, f"  Teil {k.nummer}: kein Katalogprofil zu "
                       f"{k.h * 1e3:.1f} x {k.b * 1e3:.1f} mm - Ersatzrechteck "
                       f"'{name}' angelegt (zu pruefen)")
        else:
            if name not in model.sections and name in profile:
                model.add_section(profile[name])
            C.say(log, f"  Teil {k.nummer}: L = {k.L * 1e3:.0f} mm, gemessen "
                       f"{k.h * 1e3:.1f} x {k.b * 1e3:.1f} mm -> '{name}' "
                       f"(Abweichung {dh * 1e3:+.1f} / {db * 1e3:+.1f} mm)")
        i = knoten_nr(k.p1)
        j = knoten_nr(k.p2)
        if i == j:
            continue
        model.add_element("beam", [i, j], material, name, group="HiCAD")
        n_stab += 1
    return {"staebe": n_stab, "knoten": len(knoten), "ohne_profil": ohne}


def zusammenhang(model, log: list = None) -> dict:
    """Wie viele Teiltragwerke, und wie weit liegen die Stabenden auseinander?

    Die Achsen der Querstaebe enden an der Aussenkante der Pfosten, nicht auf
    deren Achse - im Stabmodell bleibt dort eine Luecke von etwa der halben
    Profilhoehe. Das wird gemessen und benannt, statt die Knoten stillschweigend
    zu verschieben: wie weit zusammengefuehrt wird, entscheidet der Aufsteller.

    Rueckgabe: {"teile": n, "luecke": kleinster Abstand zweier Knoten aus
    verschiedenen Teilen [m]}
    """
    n = int(model.nn)
    if n == 0:
        return {"teile": 0, "luecke": 0.0}
    eltern = list(range(n))

    def wurzel(i):
        while eltern[i] != i:
            eltern[i] = eltern[eltern[i]]
            i = eltern[i]
        return i

    for e in model.elements:
        ns = [int(x) for x in e.nodes]
        for k in ns[1:]:
            a, b = wurzel(ns[0]), wurzel(k)
            if a != b:
                eltern[b] = a
    gruppe = {}
    for i in range(n):
        gruppe.setdefault(wurzel(i), []).append(i)
    X = np.asarray(model.nodes, float)[:, :3] if len(model.nodes) else np.zeros((0, 3))
    luecke = 0.0
    if len(gruppe) > 1 and len(X) == n:
        marke = np.empty(n, dtype=int)
        for g, (_w, idx) in enumerate(gruppe.items()):
            marke[idx] = g
        best = None
        for i in range(n):
            d = np.linalg.norm(X - X[i], axis=1)
            d[marke == marke[i]] = np.inf
            if len(d):
                w = float(d.min())
                if best is None or w < best:
                    best = w
        luecke = best or 0.0
    if log is not None and len(gruppe) > 1:
        log.append(f"Das Stabmodell zerfaellt in {len(gruppe)} Teile; der kleinste "
                   f"Abstand zweier Knoten aus verschiedenen Teilen ist "
                   f"{luecke * 1e3:.1f} mm (die Querstaebe enden an der Aussenkante "
                   f"der Pfosten). Mit 'Knoten zusammenfuehren' und einer Toleranz "
                   f"ueber {luecke * 1e3:.0f} mm entsteht ein zusammenhaengendes System.")
    return {"teile": len(gruppe), "luecke": luecke}


def verbinden(model, toleranz: float = 0.03, log: list = None) -> int:
    """Stabenden, die naeher als *toleranz* beieinander liegen, zusammenlegen.

    Anders als das Zusammenfuehren doppelter Knoten (Raster) wird hier nach dem
    **tatsaechlichen Abstand** geclustert: die Querstaebe enden an der
    Aussenkante der Pfosten, ihre Achsen laufen also um die halbe Profilhoehe
    daneben vorbei. Der neue Knoten liegt im Mittel der zusammengelegten - die
    Achsen werden dadurch um diesen Betrag verschoben, was im Protokoll steht.

    Rueckgabe: Anzahl der entfernten Knoten.
    """
    from ._common import merge_duplicate_nodes
    n = int(model.nn)
    if n < 2 or toleranz <= 0:
        return 0
    X = np.asarray(model.nodes, float)[:, :3]
    eltern = list(range(n))

    def wurzel(i):
        while eltern[i] != i:
            eltern[i] = eltern[eltern[i]]
            i = eltern[i]
        return i

    paare = 0
    for i in range(n):
        d = np.linalg.norm(X - X[i], axis=1)
        for j in np.nonzero(d <= toleranz)[0]:
            a, b = wurzel(i), wurzel(int(j))
            if a != b:
                eltern[b] = a
                paare += 1
    if not paare:
        return 0
    gruppen: dict = {}
    for i in range(n):
        gruppen.setdefault(wurzel(i), []).append(i)
    # Knoten auf den Gruppenschwerpunkt legen und mit engem Raster verschmelzen
    for idx in gruppen.values():
        if len(idx) > 1:
            X[idx] = X[idx].mean(0)
    model.nodes = X
    weg = merge_duplicate_nodes(model, max(toleranz * 1e-3, 1e-6))
    if log is not None and weg:
        log.append(f"{weg} Stabenden bis {toleranz * 1e3:.0f} mm Abstand "
                   f"zusammengelegt; die betroffenen Achsen verschieben sich um "
                   f"bis zu {toleranz * 1e3:.0f} mm.")
    return weg


def _naechster_punkt_auf_segment(p, a, b):
    """Fusspunkt des Lots von p auf das Segment a-b und der Parameter 0..1."""
    d = b - a
    ll = float(d @ d)
    if ll <= 1e-18:
        return a.copy(), 0.0
    t = float((p - a) @ d) / ll
    t = min(max(t, 0.0), 1.0)
    return a + t * d, t


def an_staebe_anschliessen(model, radius: float = 0.12, log: list = None) -> dict:
    """Freie Stabenden an den naechsten Stab anschliessen.

    Ein Querstab endet in HiCAD an der **Aussenkante** des Pfostens; seine
    Achse laeuft um die halbe Profilhoehe daneben vorbei. Im Stabmodell haengt
    er dadurch in der Luft. Hier wird jedes freie Ende auf die Achse des
    naechsten Stabes gelotet, dieser dort geteilt und beides verbunden.

    Was das kostet, steht im Protokoll: der Querstab wird um den Lotabstand
    laenger oder kuerzer, und die Ausmitte des Anschlusses wird **nicht**
    abgebildet. Wer sie braucht, setzt an dieser Stelle eine starre Kopplung.

    Rueckgabe: {"angeschlossen": n, "geteilt": n, "groesster_versatz": [m]}
    """
    grad: dict = {}
    for e in model.elements:
        if e.typ != "beam":
            continue
        for k in e.nodes:
            grad[int(k)] = grad.get(int(k), 0) + 1
    frei = [k for k, v in grad.items() if v == 1]
    n_an = n_teil = 0
    versatz_max = 0.0
    for k in frei:
        X = np.asarray(model.nodes, float)
        p = X[k][:3].copy()
        eigene = [i for i, e in enumerate(model.elements)
                  if e.typ == "beam" and k in [int(x) for x in e.nodes]]
        best = None
        for i, e in enumerate(model.elements):
            if e.typ != "beam" or i in eigene:
                continue
            ns = [int(x) for x in e.nodes]
            a, b = X[ns[0]][:3], X[ns[-1]][:3]
            f, t = _naechster_punkt_auf_segment(p, a, b)
            dist = float(np.linalg.norm(f - p))
            if dist <= radius and (best is None or dist < best[0]):
                best = (dist, i, f, t, ns)
        if best is None:
            continue
        dist, i, f, t, ns = best
        L = float(np.linalg.norm(X[ns[-1]][:3] - X[ns[0]][:3]))
        model.nodes[k] = f
        versatz_max = max(versatz_max, dist)
        n_an += 1
        # Liegt der Fusspunkt im Feld, wird der getroffene Stab dort geteilt
        if L > 0 and 1e-6 < t < 1 - 1e-6 and min(t, 1 - t) * L > 1e-4:
            e = model.elements[i]
            hinten = int(ns[-1])
            e.nodes = [int(ns[0]), int(k)]
            neu = model.add_element("beam", [int(k), hinten], e.mat, e.sec,
                                    group=e.group)
            el = model.elements[neu] if isinstance(neu, int) else neu
            try:
                el.roll = e.roll
            except AttributeError:
                pass
            n_teil += 1
        elif t <= 1e-6 or t >= 1 - 1e-6:
            # Fusspunkt liegt auf einem Stabende: Knoten verschmelzen
            ziel = int(ns[0] if t <= 0.5 else ns[-1])
            for e in model.elements:
                e.nodes = [ziel if int(x) == k else int(x) for x in e.nodes]
    if log is not None and n_an:
        log.append(f"{n_an} freie Stabenden an den naechsten Stab angeschlossen "
                   f"({n_teil} Staebe dafuer geteilt); groesster Versatz "
                   f"{versatz_max * 1e3:.1f} mm. Die Ausmitte des Anschlusses ist "
                   f"dabei nicht abgebildet.")
    from ._common import merge_duplicate_nodes
    merge_duplicate_nodes(model, 1e-6)
    return {"angeschlossen": n_an, "geteilt": n_teil, "groesster_versatz": versatz_max}
