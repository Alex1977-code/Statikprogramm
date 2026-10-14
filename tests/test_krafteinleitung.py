"""
Feiner vernetzen an Krafteinleitungen ohne Flaeche (13.10.2026).

Wunsch des Anwenders vom 13.10.2026: „Netzabhängige Zonen sind zu groß, weil
elementweise auf grobem Netz bestimmt. Bitte über Radius bzw. max. 1–2
Elementringe begrenzen und im Lochbereich feiner bzw. quadratisch vernetzen.“
Dieser Teil ist das feinere Vernetzen: an einer starren Scheibe ueber einer
Bohrung (Kopplung nur am Lochrand) und an einem Stabende auf einem Volumen
legt das Groessenfeld (statik3d.netzfeld) vor dem Vernetzen Quellen an -
dieselben, die spitzenstellen.kandidaten nach dem Vernetzen als Linie bzw.
Punkt meldet.

Pruefkoerper: Platte 400 x 300 x 40 mm (Mittel, Ziellaenge 20 mm, tet10) mit
der Bohrung B1 (r 25,5 mm wie die Ankerringe des Drehlagers) unter einer
starren Scheibe mit Zugstab in der Mitte, einer freien Bohrung B2 (r 12 mm)
und einem Stabende auf der Unterseite. Gegenstand ist der Tetraederweg (Sweep
aus, wie tests/test_fein_smart.py).

Kriterien (vor dem Bau festgelegt):
  * Lochrand der Scheibe: 9 Grad je Abschnitt statt 18 - 80 statt 40 Knoten
    (Ecken und Seitenmitten) auf dem Kreis, Randkante dort r * 9 Grad +- 10 %;
    das Feld am Ring hoechstens diese Laenge;
  * Stabende: Feld dort h/2, die Kanten der angeschlossenen Elementseite
    hoechstens 0,65 mal so lang wie vorher (h/2 gegen h waere 0,5; der
    Flaechenmesher liefert Kanten bis 1,6 mal Feld, vorher wie nachher - die
    erste Fassung dieser Pruefung verlangte absolut h/2 * 1,3 und scheiterte
    mit 16 mm gegen 13 mm an diesem Messerverhalten, nicht an der Quelle);
  * sonst gleich: freie Bohrung B2 mit derselben Teilung, die Randknoten der
    fernen Seitenflaechen M2 und M3 dieselben; der Lochrand unten hat die
    Teilung des Lochrands oben (die Lochwand ist eine abgebildete Flaeche,
    gegenueberliegende Seiten werden gleich geteilt - Linienteilung);
  * ohne Schalter (Netzeinstellungen.krafteinleitung_fein aus), an Entwurf
    und an einem Modell ohne solche Stellen: Netz bitgleich zum Stand c379601;
  * Grenze in Unbekannten: Mittel vergroebert ueber Stufen, die letzte ist
    Mittel ohne Verfeinerung (bitgleich), darunter WARNUNG;
  * Speichern und Laden des Schalters, aeltere Dateien bekommen ihn ein;
  * Maske Netzeinstellungen: Haken „Krafteinleitungen ohne Fläche feiner
    vernetzen“.

Aufruf:  python -m tests.test_krafteinleitung
"""
import hashlib
import os
import sys
import tempfile
from contextlib import nullcontext

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_krafteinleitung_"), "einstellungen.json")

import numpy as np  # noqa: E402

from tests.test_netzfeld import platte_mit_bohrungen  # noqa: E402

RESULTS = []

#: Platte und Bohrungen [m]
A, B, T = 0.4, 0.3, 0.04
B1 = (0.12, 0.15, 0.0255)          # unter der starren Scheibe (Ankerring des Drehlagers)
B2 = (0.31, 0.15, 0.012)           # frei
STAB = (0.30, 0.06)                # Stabende auf der Unterseite (z = 0)
H = 0.02                           # Ziellaenge (eigene)

#: Netz-Hash am Stand c379601 (vor dem Bau), gemessen am 13.10.2026 mit
#: diesem Test (Windows, ein Arbeitsprozess): die Platte mit Scheibe und
#: Stabende bei Mittel und Entwurf, die Platte ohne beides bei Mittel.
HASH_C379601 = {
    ("scheibe", "mittel"): "28dec8ebbc22ec14",
    ("scheibe", "entwurf"): "a93502bd57f85298",
    ("ohne", "mittel"): "6363a4f3678065d1",
}


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FAIL'} {name:84s} {str(detail)[:170]}")
    return ok


def _es():
    from statik3d import elementstufe
    return elementstufe


# --------------------------------------------------------------------------
# Pruefkoerper
# --------------------------------------------------------------------------
def platte(scheibe: bool = True, stabende: bool = True, scheibe2: bool = False):
    """Die Platte mit B1, B2; dazu auf Wunsch die starre Scheibe ueber B1
    (aus den Halbboegen des Lochrands, wie RFEM sie anlegt) mit Zugstab in
    der Mitte, ein Zugstab, der auf der Unterseite endet, und (``scheibe2``)
    eine zweite, kleinere Scheibe ueber B2."""
    from statik3d.model import Section
    m, _k = platte_mit_bohrungen(a=A, b=B, t=T, bohrungen=(B1, B2))
    m.add_section(Section("Rund", 1e-4, 1e-9, 1e-9, 1e-9))
    if scheibe:
        m.add_flaeche("Scheibe", ["B1O1", "B1O2"], material="S235")
        m.flaechen["Scheibe"].steifigkeit = "starr"
        mitte = m.add_node(B1[0], B1[1], T)
        oben = m.add_node(B1[0], B1[1], T + 0.5)
        e = m.add_element("truss", [mitte, oben], "S235", "Rund", group="Anker")
        m.add_member("Anker", [e])
    if scheibe2:
        m.add_flaeche("Scheibe2", ["B2O1", "B2O2"], material="S235")
        m.flaechen["Scheibe2"].steifigkeit = "starr"
        mitte = m.add_node(B2[0], B2[1], T)
        oben = m.add_node(B2[0], B2[1], T + 0.5)
        e = m.add_element("truss", [mitte, oben], "S235", "Rund", group="Anker2")
        m.add_member("Anker2", [e])
    if stabende:
        p = m.add_node(STAB[0], STAB[1], 0.0)
        q = m.add_node(STAB[0], STAB[1], -0.5)
        e = m.add_element("truss", [p, q], "S235", "Rund", group="Zugstab")
        m.add_member("Zugstab", [e])
    m.netz.dichte = "eigene"
    m.netz.ziellaenge = H
    return m


def vernetzen(m, stufe: str, kraft: bool = True, grenze: int = 0) -> tuple:
    """Wie ``statik3d --vernetzen`` (cli.py): elementstufe.beim_vernetzen und
    die Stufen der Grenze (elementstufe.fein_stufen) an mesher.modell_vernetzen,
    ein Arbeitsprozess, Tetraederweg. Rueckgabe (Ergebnis, Protokoll)."""
    from statik3d import mesher
    es = _es()
    m.netz = es.setzen(m.netz, stufe)
    m.netz.sweep = "aus"                 # Gegenstand ist der Tetraederweg
    m.netz.krafteinleitung_fein = bool(kraft)
    m.netz.hoechstens_unbekannte = int(grenze)
    log: list = []
    with es.beim_vernetzen(m, log) as w:
        stufen = es.fein_stufen(m, w) if hasattr(es, "fein_stufen") else None
        erg = mesher.modell_vernetzen(m, log, workers=1, stufen=stufen)
    return erg, [str(z) for z in log]


def netz_hash(m) -> str:
    s = hashlib.sha256()
    s.update(np.ascontiguousarray(np.asarray(m.nodes, float)).tobytes())
    for e in m.elements:
        s.update(e.typ.encode())
        s.update(np.asarray([int(x) for x in e.nodes], np.int64).tobytes())
    return s.hexdigest()[:16]


def ringknoten(m, bohrung, z: float) -> tuple:
    """Alle Netzknoten (Ecken und Seitenmitten) auf dem Kreis der Bohrung in
    der Hoehe z: (Zahl, groesste Winkelluecke zwischen Eckknoten [Grad],
    Randkante = Sehne zwischen benachbarten Eckknoten (Median) [m])."""
    cx, cy, r = bohrung
    vol = [e for e in m.elements if e.typ.startswith("tet")]
    alle = sorted({int(x) for e in vol for x in e.nodes})
    ecken = sorted({int(x) for e in vol for x in e.nodes[:4]})
    X = np.asarray(m.nodes, float)

    def auf(idx):
        P = X[idx]
        rho = np.hypot(P[:, 0] - cx, P[:, 1] - cy)
        return np.asarray(idx)[(np.abs(rho - r) < 1e-6) & (np.abs(P[:, 2] - z) < 1e-9)]
    n_alle = len(auf(alle))
    E = X[auf(ecken)]
    w = np.sort(np.arctan2(E[:, 1] - cy, E[:, 0] - cx))
    if len(w) < 2:
        return n_alle, 360.0, 0.0
    luecken = np.diff(np.concatenate([w, w[:1] + 2 * np.pi]))
    sehne = 2.0 * r * np.sin(luecken / 2.0)
    return n_alle, float(np.degrees(luecken.max())), float(np.median(sehne))


def kanten_bei(m, punkt, radius: float) -> np.ndarray:
    """Kantenlaengen (Ecken) aller Volumenelemente mit einem Eckknoten
    hoechstens ``radius`` vom Punkt."""
    X = np.asarray(m.nodes, float)
    L = []
    p = np.asarray(punkt, float)
    for e in m.elements:
        if not e.typ.startswith("tet"):
            continue
        k = [int(x) for x in e.nodes[:4]]
        if (np.linalg.norm(X[k] - p, axis=1) > radius).all():
            continue
        for a, b in ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)):
            L.append(float(np.linalg.norm(X[k[a]] - X[k[b]])))
    return np.asarray(L)


def randknoten_flaeche(m, fn) -> set:
    """Die Knoten der Randseiten einer Flaeche als gerundete Orte (mm)."""
    X = np.asarray(m.nodes, float)
    aus = set()
    for ei, s in (m.flaechen[fn].randseiten or []):
        from statik3d.elements import solid as sl
        e = m.elements[int(ei)]
        for c in sl.FLAECHEN_ECKEN[e.typ][int(s)]:
            aus.add(tuple(np.round(X[int(e.nodes[c])] * 1e6).astype(int)))
    return aus


_NETZE = {}


def _vernetzt(name: str, stufe: str, kraft: bool):
    schl = (name, stufe, kraft)
    if schl not in _NETZE:
        m = platte(scheibe=name == "scheibe", stabende=name == "scheibe")
        erg, log = vernetzen(m, stufe, kraft)
        _NETZE[schl] = (m, erg, log)
    return _NETZE[schl]


# --------------------------------------------------------------------------
# 1) Lochrand unter der starren Scheibe
# --------------------------------------------------------------------------
def test_lochrand():
    mv, _, _ = _vernetzt("scheibe", "mittel", False)
    mn, _, log = _vernetzt("scheibe", "mittel", True)
    nv, gv, sv = ringknoten(mv, B1, T)
    nn, gn, sn = ringknoten(mn, B1, T)
    print(f"  Lochrand B1 oben: vorher {nv} Knoten, Lücke {gv:.2f}°, Randkante {sv * 1e3:.2f} mm; "
          f"nachher {nn} Knoten, Lücke {gn:.2f}°, Randkante {sn * 1e3:.2f} mm")
    print(f"  Elemente vorher {len(mv.elements)}, nachher {len(mn.elements)}; "
          f"Unbekannte vorher {3 * mv.nn}, nachher {3 * mn.nn}")
    check("Voraussetzung: vorher 40 Knoten am Lochrand (18° je Abschnitt, tet10)", nv == 40, f"{nv} Knoten")
    check("Lochrand der Scheibe: 80 Knoten (9° je Abschnitt)", nn == 80 and gn <= 9.0 + 0.5,
          f"{nn} Knoten, größte Lücke {gn:.2f}°")
    h_b = B1[2] * np.radians(9.0)
    check("… Randkante am Lochrand r · 9° ± 10 %", abs(sn - h_b) <= 0.1 * h_b,
          f"{sn * 1e3:.2f} mm, r · 9° = {h_b * 1e3:.2f} mm, vorher {sv * 1e3:.2f} mm")
    # Das Feld am Ring, wie es beim Vernetzen galt
    from statik3d import netzfeld
    es = _es()
    m = platte()
    m.netz = es.setzen(m.netz, "mittel")
    m.netz.krafteinleitung_fein = True
    m.netz = es.wirksam(m.netz, m)
    feld = netzfeld.aufbauen(m)
    w_ = np.linspace(0.0, 2 * np.pi, 37)[:-1]
    Q = np.column_stack([B1[0] + B1[2] * np.cos(w_), B1[1] + B1[2] * np.sin(w_), np.full(len(w_), T)])
    v = feld(Q) if feld is not None else np.full(len(Q), np.inf)
    check("… Feld am Lochrand höchstens r · 9° (+ 1 %)", float(np.max(v)) <= 1.01 * h_b,
          f"max {float(np.max(v)) * 1e3:.2f} mm")
    # zwei Elementringe um den Lochrand: im Abstand 2 h_B (in der Platte) noch h_B
    Q2 = np.column_stack([B1[0] + (B1[2] + 1.9 * h_b) * np.cos(w_), B1[1] + (B1[2] + 1.9 * h_b) * np.sin(w_),
                          np.full(len(w_), T)])
    v2 = feld(Q2) if feld is not None else np.full(len(Q2), np.inf)
    check("… im Umkreis r + 2 h_B ebenfalls h_B (zwei Elementringe)", float(np.max(v2)) <= 1.01 * h_b,
          f"max {float(np.max(v2)) * 1e3:.2f} mm im Abstand {1.9 * h_b * 1e3:.1f} mm")
    zeile = next((z for z in log if z.startswith("Elemente Mittel")), "")
    check("Protokoll: „Elemente Mittel: feiner an Krafteinleitungen ohne Fläche“ mit Ring und Stabende",
          "Krafteinleitungen ohne Fläche" in zeile and "1 Ring" in zeile and "1 Stabende" in zeile, zeile)
    # Nach dem Vernetzen haengt die Scheibe an allen Knoten des Lochrands
    k = mn.flaechen["Scheibe"].kommentar or ""
    check("… die starre Scheibe koppelt die 80 Knoten des Lochrands", "koppelt 80 Knoten" in k, k)
    # Die Stelle, wie sie spitzenstellen nach dem Vernetzen sieht: oertliches h
    from statik3d import spitzenstellen as sp
    sv_, sn_ = sp.kandidaten(mv), sp.kandidaten(mn)
    hv = [s["h"] for s in sv_ if s["quelle"] == sp.STARRE_SCHEIBE]
    hn = [s["h"] for s in sn_ if s["quelle"] == sp.STARRE_SCHEIBE]
    print(f"  spitzenstellen: h am Ring vorher {[round(x * 1e3, 2) for x in hv]} mm, "
          f"nachher {[round(x * 1e3, 2) for x in hn]} mm; Zone vorher "
          f"{[len(s['zone']) for s in sv_ if s['quelle'] == sp.STARRE_SCHEIBE]}, nachher "
          f"{[len(s['zone']) for s in sn_ if s['quelle'] == sp.STARRE_SCHEIBE]} Elemente")
    check("spitzenstellen: das örtliche h an der Scheibe ist kleiner (mindestens ein Drittel)",
          hv and hn and hn[0] <= hv[0] / 1.5, f"vorher {hv}, nachher {hn}")


# --------------------------------------------------------------------------
# 2) Stabende auf der Unterseite
# --------------------------------------------------------------------------
def stabende_kanten(m) -> np.ndarray:
    """Die Kanten der Elementseite, an die das Stabende auf der Unterseite
    gekoppelt ist (fugen.stabenden_koppeln: drei Eckknoten einer Seite)."""
    X = np.asarray(m.nodes, float)
    p = np.array([STAB[0], STAB[1], 0.0])
    n = [i for i in range(m.nn) if np.linalg.norm(X[i] - p) < 1e-12]
    gr = {f"Stabende K{i}" for i in n}
    partner = sorted({int(k.node_b) for k in (m.kopplungen or []) if str(k.gruppe) in gr})
    return np.asarray([float(np.linalg.norm(X[a] - X[b])) for i, a in enumerate(partner) for b in partner[i + 1:]])


def test_stabende():
    mv, _, _ = _vernetzt("scheibe", "mittel", False)
    mn, _, _ = _vernetzt("scheibe", "mittel", True)
    p = (STAB[0], STAB[1], 0.0)
    Kv, Kn = stabende_kanten(mv), stabende_kanten(mn)
    Lv, Ln = kanten_bei(mv, p, H), kanten_bei(mn, p, H)
    mv_, mn_ = (float(np.median(Lv)) if len(Lv) else 0.0), (float(np.median(Ln)) if len(Ln) else 0.0)
    print(f"  Stabende: Kanten der gekoppelten Seite vorher {np.round(Kv * 1e3, 2).tolist()} mm, "
          f"nachher {np.round(Kn * 1e3, 2).tolist()} mm; Kanten im Umkreis h (Median) vorher "
          f"{mv_ * 1e3:.2f} mm ({len(Lv)}), nachher {mn_ * 1e3:.2f} mm ({len(Ln)})")
    check("Stabende auf der Unterseite: Kanten der gekoppelten Seite höchstens 0,65 · vorher",
          len(Kn) == 3 and len(Kv) == 3 and float(Kn.max()) <= 0.65 * float(Kv.max())
          and float(Kn.mean()) <= 0.65 * float(Kv.mean()),
          f"nachher bis {float(Kn.max()) * 1e3 if len(Kn) else 0:.2f} mm (Mittel {float(Kn.mean()) * 1e3 if len(Kn) else 0:.2f}), "
          f"vorher bis {float(Kv.max()) * 1e3 if len(Kv) else 0:.2f} mm (Mittel {float(Kv.mean()) * 1e3 if len(Kv) else 0:.2f}), "
          f"h/2 = {0.5 * H * 1e3:.1f} mm")
    check("… im Umkreis h um das Stabende feiner als vorher (Median der Kanten)", len(Ln) and mn_ < 0.8 * mv_,
          f"nachher {mn_ * 1e3:.2f} mm, vorher {mv_ * 1e3:.2f} mm")
    from statik3d import netzfeld
    es = _es()
    m = platte()
    m.netz = es.setzen(m.netz, "mittel")
    m.netz = es.wirksam(m.netz, m)
    feld = netzfeld.aufbauen(m)
    v = float(feld(np.array([p]))[0]) if feld is not None else np.inf
    check("… das Feld am Stabende ist h/2", abs(v - 0.5 * H) <= 1e-9, f"{v * 1e3:.3f} mm")


# --------------------------------------------------------------------------
# 3) Sonst bleibt das Netz gleich
# --------------------------------------------------------------------------
def test_sonst_gleich():
    mv, _, _ = _vernetzt("scheibe", "mittel", False)
    mn, _, _ = _vernetzt("scheibe", "mittel", True)
    for z in (0.0, T):
        a, b = ringknoten(mv, B2, z), ringknoten(mn, B2, z)
        check(f"freie Bohrung B2 (z = {z * 1e3:.0f} mm): dieselbe Teilung", a[0] == b[0] and abs(a[1] - b[1]) < 1e-6,
              f"vorher {a[0]} Knoten / {a[1]:.2f}°, nachher {b[0]} / {b[1]:.2f}°")
    for fn in ("M2", "M3"):
        a, b = randknoten_flaeche(mv, fn), randknoten_flaeche(mn, fn)
        check(f"ferne Seitenfläche {fn}: dieselben Randknoten", a == b and len(a) > 0,
              f"vorher {len(a)}, nachher {len(b)}, gemeinsam {len(a & b)}")
    nv, _, _ = ringknoten(mv, B1, 0.0)
    nn, _, _ = ringknoten(mn, B1, 0.0)
    no, _, _ = ringknoten(mn, B1, T)
    check("Lochrand B1 unten (40 mm unter der Scheibe): vorher 40, jetzt wie oben (die Lochwand ist abgebildet)",
          nv == 40 and nn == no == 80, f"vorher {nv}, nachher {nn} Knoten, oben {no}")


# --------------------------------------------------------------------------
# 4) Bitgleich: Schalter aus, Entwurf, Modell ohne Stellen
# --------------------------------------------------------------------------
def test_bitgleich():
    faelle = (("scheibe", "mittel", False), ("scheibe", "entwurf", True), ("ohne", "mittel", True))
    for name, stufe, kraft in faelle:
        m, _erg, log = _vernetzt(name, stufe, kraft)
        h = netz_hash(m)
        soll = HASH_C379601[(name, stufe)]
        was = {"scheibe": "Platte mit Scheibe und Stabende", "ohne": "Platte ohne beides"}[name]
        check(f"{was}, {stufe}, Schalter {'ein' if kraft else 'aus'}: Netz bitgleich zum Stand c379601",
              soll and h == soll, f"{h} (c379601: {soll or '-'}), {len(m.elements)} Elemente, {m.nn} Knoten")
        if stufe == "entwurf":
            check("… Entwurf bleibt linear (tet4) und ohne Verfeinerung, das Protokoll sagt nichts davon",
                  {e.typ for e in m.elements if not e.typ == "truss"} == {"tet4"}
                  and not any("Krafteinleitungen" in z for z in log),
                  sorted({e.typ for e in m.elements}))


# --------------------------------------------------------------------------
# 5) Fein: die Krafteinleitungen kommen dazu
# --------------------------------------------------------------------------
def test_fein():
    mf, _, log = _vernetzt("scheibe", "fein", True)
    n, g, _s = ringknoten(mf, B1, T)
    check("Fein: Lochrand der Scheibe ebenfalls 9° (80 Knoten)", n == 80 and g <= 9.5, f"{n} Knoten, {g:.2f}°")
    zeile = next((z for z in log if z.startswith("Elemente Fein")), "")
    check("… Protokoll „Elemente Fein“ nennt die Krafteinleitungen", "Krafteinleitungen ohne Fläche" in zeile, zeile)


# --------------------------------------------------------------------------
# 6) Grenze in Unbekannten
# --------------------------------------------------------------------------
def test_grenze():
    es = _es()
    m0, _, _ = _vernetzt("scheibe", "mittel", True)
    u0 = 3 * m0.nn
    mp, _, _ = _vernetzt("scheibe", "mittel", False)
    u_plain = 3 * mp.nn
    check("Voraussetzung: die Krafteinleitungen kosten Unbekannte", u0 > u_plain, f"{u0} gegen {u_plain}")
    m = platte()
    erg, log = vernetzen(m, "mittel", True, grenze=u0 - 3)
    k = int(erg.get("stufe", 0) or 0)
    zeilen = [z for z in log if "Netzgrenze" in z]
    check("Grenze 3 unter Mittel: gröber über die Stufen, Ergebnis unter der Grenze",
          k >= 1 and 3 * m.nn <= u0 - 3, f"Stufe {k}, {3 * m.nn} Unbekannte")
    check("… Protokoll nennt die Stufe von Mittel („Mittel Stufe“)", any("Mittel Stufe" in z for z in zeilen),
          zeilen[-1] if zeilen else "keine Zeile „Netzgrenze“")
    check("… keine WARNUNG", not [z for z in log if z.startswith("WARNUNG") and "Unbekannte" in z])
    check("… danach stehen die gespeicherten Netzeinstellungen da (Mittel, ohne Quellen, quelle leer)",
          es.stufe(m.netz) == "mittel" and not [v for v in (m.netz.verfeinerungen or [])
                                               if str(v.get("art", "")).startswith("fein_")]
          and not m.netz.quelle)
    m = platte()
    erg, log = vernetzen(m, "mittel", True, grenze=u_plain - 3)
    warn = [z for z in log if z.startswith("WARNUNG") and "Unbekannte" in z]
    check("Grenze unter Mittel ohne Verfeinerung: letzte Stufe, bitgleich Mittel ohne Verfeinerung, WARNUNG",
          netz_hash(m) == netz_hash(mp) and bool(warn) and int(erg.get("stufe", 0) or 0) >= 1,
          f"Stufe {erg.get('stufe')}, {netz_hash(m)} / {netz_hash(mp)}, {warn[:1]}")


# --------------------------------------------------------------------------
# 6b) Die Stufen der Krafteinleitungen (ohne Vernetzen)
# --------------------------------------------------------------------------
def test_stufen():
    """Welche Ringe die Stufen behalten (groesster Radius zuerst) und wie Mittel
    und Fein vergroebern - nur Geometrie und Netzeinstellungen, kein Vernetzen."""
    from dataclasses import replace
    from statik3d import netzfeld
    es = _es()
    m = platte(scheibe2=True)
    st = netzfeld.krafteinleitungen(m)
    radien = sorted(round(s["r"] * 1e3, 1) for s in st["ringe"])
    check("zwei Ringe erkannt: r 12 mm und r 25,5 mm, dazu ein Stabende", radien == [12.0, 25.5] and len(st["punkte"]) == 1,
          f"{radien}, {len(st['punkte'])} Stabende(n)")
    namen = {a: sorted(s["name"] for s in netzfeld.kraft_ziele(m, m.netz, 9.0, 0.5, st, a)["ringe"])
             for a in (1.0, 0.5, 0.25, 0.0)}
    check("Ringanteil 1: beide Ringe; 0,5 und 0,25: nur der größere (Scheibe); 0: keiner",
          namen[1.0] == ["Scheibe", "Scheibe2"] and namen[0.5] == ["Scheibe"] and namen[0.25] == ["Scheibe"]
          and namen[0.0] == [], str(namen))
    z = netzfeld.kraft_ziele(m, m.netz, 9.0, 0.5, st, 0.5)
    check("… das Ergebnis nennt alle Ringe des Modells (für den Text)", z["ringe_gesamt"] == 2, z["ringe_gesamt"])
    # Mittel: fuenf Stufen, die letzte ohne Quellen und bitgleich zu den gespeicherten Einstellungen
    m.netz = es.setzen(m.netz, "mittel")
    basis = m.netz
    ein = es.fein_stufen(m, basis)
    check("Mittel mit Krafteinleitungen hat Stufen (eine Funktion), nicht None", ein is not None)
    if ein is None:
        return
    arten = []
    for k in range(es.KRAFT_STUFEN_ANZAHL):
        n = ein(k)
        arten.append(sorted({v["art"] for v in n.verfeinerungen}) if n is not None else None)
    check("… Stufe 5 gibt es nicht (None)", ein(es.KRAFT_STUFEN_ANZAHL) is None and ein(-1) is None)
    check("… Stufe 0: Ringe und Stabende; Stufe 1: ebenso; Stufe 2 und 3: nur das Stabende; Stufe 4: nichts",
          arten[0] == ["fein_kraft_punkt", "fein_kraft_ring"] and arten[1] == arten[0]
          and arten[2] == ["fein_kraft_punkt"] and arten[3] == ["fein_kraft_punkt"] and arten[4] == [], str(arten))
    n0, n1 = ein(0), ein(1)
    r0 = sorted(v["name"] for v in n0.verfeinerungen if v["art"] == "fein_kraft_ring")
    r1 = sorted(v["name"] for v in n1.verfeinerungen if v["art"] == "fein_kraft_ring")
    check("… Stufe 0: beide Ringe, Stufe 1: nur der größte", r0 == ["Scheibe", "Scheibe2"] and r1 == ["Scheibe"],
          f"{r0} / {r1}")
    h3 = [v["h"] for v in ein(3).verfeinerungen]
    h2 = [v["h"] for v in ein(2).verfeinerungen]
    check("… Stufe 3: das Stabende h/1,5 statt h/2", len(h2) == 1 and abs(h3[0] / h2[0] - (1 / 1.5) / 0.5) < 1e-9,
          f"{h2} / {h3}")
    letzte = ein(es.KRAFT_STUFEN_ANZAHL - 1)
    check("… Stufe 4 ist Mittel bitgleich (bis auf den Text quelle)", replace(letzte, quelle="") == replace(basis, quelle=""),
          letzte.quelle)
    texte = [ein(k).quelle for k in range(es.KRAFT_STUFEN_ANZAHL)]
    print("  Texte der Stufen von Mittel:")
    for t in texte:
        print("   ", t)
    check("… Texte: „Mittel Stufe 1: Ringe 9° (das größte Viertel), Stabenden h/2“ und „ohne Ringe“",
          texte[1] == "Mittel Stufe 1: Ringe 9° (das größte Viertel), Stabenden h/2"
          and texte[2] == "Mittel Stufe 2: ohne Ringe, Stabenden h/2", str(texte))
    # Fein: die Krafteinleitungen bleiben auf Stufe 0, bis Fein selbst Mittel ist, dann Stufen von Mittel
    m.netz = es.setzen(m.netz, "fein")
    fe = es.fein_stufen(m, m.netz)
    soll = es.FEIN_STUFEN_ANZAHL + es.KRAFT_STUFEN_ANZAHL - 1
    check(f"Fein mit Krafteinleitungen hat {soll} Stufen ({es.FEIN_STUFEN_ANZAHL} von Fein, dahinter die von Mittel)",
          fe is not None and fe(soll - 1) is not None and fe(soll) is None)
    ringe_in = [sorted({v["art"] for v in fe(k).verfeinerungen if "kraft" in v["art"]}) for k in range(soll)]
    check("… Fein Stufe 0 bis 4 (Mittel von Fein) tragen die vollen Krafteinleitungen (Ringe und Stabende)",
          all(r == ["fein_kraft_punkt", "fein_kraft_ring"] for r in ringe_in[:es.FEIN_STUFEN_ANZAHL]), str(ringe_in))
    check("… danach vergröbern sie wie bei Mittel (größter Ring und Stabende, nur Stabende, Stabende, nichts)",
          ringe_in[es.FEIN_STUFEN_ANZAHL:] == [["fein_kraft_punkt", "fein_kraft_ring"], ["fein_kraft_punkt"],
                                                ["fein_kraft_punkt"], []], str(ringe_in[es.FEIN_STUFEN_ANZAHL:]))
    check("… die letzte Stufe von Fein ist Mittel bitgleich (bis auf Stufe und Text)",
          replace(fe(soll - 1), quelle="", stufe="mittel") == replace(basis, quelle=""), fe(soll - 1).quelle)
    print("  Texte der Stufen von Fein:", [fe(k).quelle for k in range(soll)])
    # Vernetzt: Stufe 0 verfeinert beide Ringe, Stufe 1 nur den groesseren (B1, r 25,5 mm); B2 (r 12 mm) bleibt bei Mittel
    from statik3d import mesher
    erg = {}
    for j in (0, 1):
        mm_ = platte(scheibe=True, stabende=False, scheibe2=True)
        mm_.netz = es.setzen(mm_.netz, "mittel")
        mm_.netz.sweep = "aus"
        log: list = []
        with es.beim_vernetzen(mm_, log, k=j):
            mesher.modell_vernetzen(mm_, log, workers=1)
        erg[j] = (ringknoten(mm_, B1, T)[0], ringknoten(mm_, B2, T)[0])
    print(f"  Knoten am Lochrand oben (B1, B2): Stufe 0 {erg[0]}, Stufe 1 {erg[1]}")
    check("Vernetzt: Stufe 0 teilt beide Lochränder 9° (80 und 80 Knoten), Stufe 1 nur den größeren (80 und 40)",
          erg[0] == (80, 80) and erg[1] == (80, 40), f"{erg}")


# --------------------------------------------------------------------------
# 7) Speichern, Laden, Maske
# --------------------------------------------------------------------------
def test_speichern_laden():
    from statik3d.model import Model, Netzeinstellungen
    check("Netzeinstellungen: krafteinleitung_fein, Vorgabe ein",
          getattr(Netzeinstellungen(), "krafteinleitung_fein", None) is True)
    m = platte()
    m.netz.krafteinleitung_fein = False
    ordner = tempfile.mkdtemp(prefix="statik3d_kraft_")
    pfad = os.path.join(ordner, "p.json")
    m.save(pfad)
    m2 = Model.load(pfad)
    check("… gespeichert und geladen (aus bleibt aus)", getattr(m2.netz, "krafteinleitung_fein", None) is False)
    import json
    with open(pfad, encoding="utf-8") as f:
        d = json.load(f)
    d.get("netz", {}).pop("krafteinleitung_fein", None)
    alt = os.path.join(ordner, "alt.json")
    with open(alt, "w", encoding="utf-8") as f:
        json.dump(d, f)
    m3 = Model.load(alt)
    check("… ältere Datei ohne das Feld: ein (die neue Regel gilt beim Neuvernetzen)",
          getattr(m3.netz, "krafteinleitung_fein", None) is True)


_FENSTER = {}
FEHLER = []


def test_maske():
    from PySide6 import QtWidgets
    from statik3d.gui.main import MainWindow
    from tests.meldungen import abfangen
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = MainWindow()
    w.show()
    app.processEvents()
    w._fragen_knoepfe = lambda *a, **k: True
    w.meldungen = abfangen(w, FEHLER)
    _FENSTER.update(w=w, app=app)
    m = platte()
    m.netz = _es().setzen(m.netz, "mittel")
    w.model = m
    w._MainWindow__init_defaults()
    w.analysis = None
    w.results = None
    w.refresh_all()
    app.processEvents()
    w.maske_netzeinstellungen()
    app.processEvents()
    mk = w.maskenrand.maske
    f = mk._felder.get("krafteinleitung_fein")
    check("Maske Netzeinstellungen: Haken „Krafteinleitungen ohne Fläche feiner vernetzen“",
          f is not None and getattr(mk, "_feldtexte", {}).get("krafteinleitung_fein")
          == "Krafteinleitungen ohne Fläche feiner vernetzen", ", ".join(mk._felder))
    if f is not None:
        check("… angehakt (Vorgabe)", f.isChecked())
        hinweis = getattr(mk, "_hinweise", {}).get("krafteinleitung_fein", "")
        check("… mit Hinweis (starre Scheiben, Stabenden, Mittel und Fein)",
              "starre Scheibe" in hinweis and "Stabend" in hinweis and "Mittel" in hinweis, hinweis)
        kt = str(mk.werte().get("kantenlaenge", ""))
        check("… die wirksame Kantenlänge nennt die Krafteinleitungen", "Krafteinleitungen" in kt, kt)
        f.setChecked(False)
        app.processEvents()
        kt2 = str(mk.werte().get("kantenlaenge", ""))
        check("… ohne Haken nennt die wirksame Kantenlänge sie nicht mehr (folgt dem Haken)",
              "Krafteinleitungen" not in kt2 and bool(kt2), kt2)
        mk.anwenden()
        app.processEvents()
        check("Übernehmen: krafteinleitung_fein = aus", getattr(w.model.netz, "krafteinleitung_fein", None) is False)
    w.maskenrand.schliessen()


def main():
    import faulthandler
    faulthandler.dump_traceback_later(1800, exit=True)
    gruppen = (test_lochrand, test_stabende, test_sonst_gleich, test_bitgleich, test_fein, test_stufen,
               test_grenze, test_speichern_laden, test_maske)
    auswahl = [a for a in sys.argv[1:] if not a.startswith("-")]
    for t in gruppen:
        if auswahl and not any(a in t.__name__ for a in auswahl):
            continue
        print(f"\n--- {t.__name__} ---")
        try:
            with nullcontext():
                t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    failed = [n for n, ok in RESULTS if not ok]
    if failed:
        print("FEHLGESCHLAGEN:", failed)
    return 0 if not failed else 1


if __name__ == "__main__":
    # Das Hauptfenster (test_maske) ohne Rueckfrage beenden
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
