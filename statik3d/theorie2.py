"""
Theorie II. Ordnung und Ersatzimperfektionen nach DIN EN 1993-1-1, 5.2 und 5.3.

Drei Dinge stecken hier drin:

1. **alpha_cr** je Kombination aus dem linearen Verzweigungsproblem
   (K + lambda K_g) v = 0 mit dem Spannungszustand der Kombination als
   Grundzustand.  Nach 5.2.1(3) darf nach Theorie I. Ordnung gerechnet
   werden, solange

        alpha_cr = F_cr / F_Ed >= 10   (elastische Berechnung)
        alpha_cr >= 15                 (plastische Berechnung)

2. **Ersatzimperfektionen** nach 5.3.2.  Statt die Geometrie zu verziehen
   werden nach 5.3.2(7) aequivalente Lasten angesetzt - das ist gleichwertig
   und laesst das Netz unberuehrt:

        Schiefstellung  phi = phi_0 alpha_h alpha_m       (5.3.2(3)a)
                        H_Ed = phi N_Ed  je Stiel, als Kraeftepaar
        Vorkruemmung    e_0 nach Tab. 5.1 je Knicklinie
                        q = 8 N_Ed e_0 / L^2 quer zum Stab,
                        dazu die Endquerkraefte 4 N_Ed e_0 / L

   phi_0 = 1/200; alpha_h = 2/sqrt(h) mit 2/3 <= alpha_h <= 1,0;
   alpha_m = sqrt(0,5 (1 + 1/m)).  h ist die Bauwerkshoehe, m die Zahl der
   Stiele einer Reihe, die mindestens 50 % der mittleren Stielnormalkraft
   tragen (5.3.2(3)) - deshalb wird m je Kombination aus den Normalkraeften
   bestimmt, nicht geraten.

3. **Gleichgewicht am verformten System**: (K + K_g(N)) u = F, iterativ, weil
   K_g von den Normalkraeften abhaengt und diese von u.  Die Normalkraefte
   und die Ersatzlasten werden in jedem Schritt neu gebildet.

Wichtig und im Bericht gesagt: nach Theorie II. Ordnung gilt die
**Superposition nicht mehr**.  Jede Kombination wird einzeln gerechnet;
Ergebnisse duerfen nicht mehr aus Lastfallergebnissen ueberlagert werden.

Nicht enthalten: Theorie III. Ordnung (grosse Verformungen), Fliessgelenke,
die Imperfektionsform aus der Knickeigenform nach 5.3.2(11) (dafuer wird die
Eigenform zwar berechnet, aber nur als alpha_cr ausgewertet), und
Imperfektionen fuer Aussteifungsverbaende nach 5.3.3.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import numpy as np

from . import assemble as asm
from . import zahlen as zl
from .elements import beam3d as bm
from .model import Model

NDOF = 6

#: Vorkruemmung e_0/L nach Tabelle 5.1, je Knicklinie
E0_ELASTISCH = {"a0": 1 / 350, "a": 1 / 300, "b": 1 / 250, "c": 1 / 200, "d": 1 / 150}
E0_PLASTISCH = {"a0": 1 / 300, "a": 1 / 250, "b": 1 / 200, "c": 1 / 150, "d": 1 / 100}

PHI_0 = 1.0 / 200.0

#: Ab welchem Winkel zur Lotrechten ein Stab noch als Stiel gilt [Grad]
STIEL_WINKEL = 30.0


# ==========================================================================
# Ersatzimperfektionen (5.3.2)
# ==========================================================================
def alpha_h(h: float) -> float:
    """Abminderung nach der Bauwerkshoehe, 5.3.2(3)a: 2/sqrt(h), 2/3 <= a_h <= 1."""
    if h <= 0:
        return 1.0
    return float(min(max(2.0 / math.sqrt(h), 2.0 / 3.0), 1.0))


def alpha_m(m: int) -> float:
    """Abminderung nach der Stielzahl, 5.3.2(3)a: sqrt(0,5 (1 + 1/m))."""
    m = max(int(m), 1)
    return float(math.sqrt(0.5 * (1.0 + 1.0 / m)))


def schiefstellung(h: float, m: int, phi_0: float = PHI_0) -> dict:
    """Schiefstellung phi = phi_0 alpha_h alpha_m mit allen Zwischenwerten."""
    ah, am = alpha_h(h), alpha_m(m)
    return {"phi_0": phi_0, "h": float(h), "m": int(m), "alpha_h": ah,
            "alpha_m": am, "phi": float(phi_0 * ah * am)}


def e0_durch_L(kurve: str, elastisch: bool = True) -> float:
    """Vorkruemmung e_0/L nach Tabelle 5.1."""
    tab = E0_ELASTISCH if elastisch else E0_PLASTISCH
    return tab.get(kurve, tab["c"])


# --------------------------------------------------------------------------
def _elementachse(model: Model, e):
    X = model.nodes[e.nodes]
    v = np.asarray(X[1], float) - np.asarray(X[0], float)
    L = float(np.linalg.norm(v))
    return (v / L if L > 0 else v), L


def stiele(model: Model) -> dict:
    """
    Stiele des Tragwerks: Staebe, deren Achse hoechstens ``STIEL_WINKEL`` von
    der Lotrechten abweicht.  Rueckgabe {Stabname: (Elementliste, Laenge)}.
    """
    grenze = math.cos(math.radians(STIEL_WINKEL))
    out = {}
    for name, mem in model.members.items():
        if not mem.elements:
            continue
        e = model.elements[mem.elements[0]]
        if e.typ not in ("beam", "truss"):
            continue
        v, _ = _elementachse(model, e)
        if abs(v[2]) >= grenze:
            L = model.member_length(mem)
            out[name] = (list(mem.elements), L)
    return out


def bauwerkshoehe(model: Model) -> float:
    """Hoehe des Tragwerks aus der Bounding-Box (z-Richtung)."""
    lo, hi = model.bbox()
    return float(hi[2] - lo[2])


def _member_N(model: Model, mem, res) -> float:
    """Mittlere Normalkraft eines Stabes [N], Druck negativ (wie im Ergebnis)."""
    try:
        mf = res.member_forces(mem, 3)
    except Exception:
        return 0.0
    return float(np.mean(mf["N"]))


def stielkraefte(model: Model, res) -> dict:
    """Normalkraft je Stiel; nur Druck zaehlt (Zugstiele bekommen keine
    Ersatzlast aus der Schiefstellung)."""
    out = {}
    for name, (_els, _L) in stiele(model).items():
        N = _member_N(model, model.members[name], res)
        if N < 0:
            out[name] = -N            # Druck positiv
    return out


def massgebende_stiele(kraefte: dict) -> list:
    """
    Stiele, die mindestens 50 % der mittleren Stielnormalkraft tragen
    (5.3.2(3)): nur sie zaehlen fuer m.
    """
    if not kraefte:
        return []
    mittel = sum(kraefte.values()) / len(kraefte)
    return [k for k, v in kraefte.items() if v >= 0.5 * mittel]


def imperfektionsrichtung(model: Model, res, vorgabe=None) -> np.ndarray:
    """
    Richtung der Schiefstellung in der Grundrissebene, 5.3.2(4).

    Die Schiefstellung wirkt in der **massgebenden waagerechten Richtung**,
    nicht gleichzeitig in beiden.  Massgebend ist die Richtung, in die sich
    das Tragwerk ohnehin verschiebt: gemittelt ueber die gedrueckten Stiele
    wird die waagerechte Verschiebung des Kopfes gegen den Fuss gebildet.  So
    wirkt die Ersatzlast immer unguenstig.  Verschiebt sich nichts (reine
    Vertikallast am symmetrischen System), wird die globale x-Richtung
    genommen; ``vorgabe`` ueberschreibt die Wahl.
    """
    if vorgabe is not None:
        v = np.asarray(vorgabe, float).ravel()[:2]
        n = float(np.linalg.norm(v))
        if n > 0:
            return np.array([v[0] / n, v[1] / n, 0.0])
    u = getattr(res, "u", None)
    if u is not None:
        u = np.asarray(u, float)
        v = np.zeros(2)
        for name, (els, _L) in stiele(model).items():
            ea, eb = model.elements[els[0]], model.elements[els[-1]]
            na, nb = int(ea.nodes[0]), int(eb.nodes[-1])
            if model.nodes[na][2] > model.nodes[nb][2]:
                na, nb = nb, na
            if nb < u.shape[0] and na < u.shape[0]:
                v += u[nb, :2] - u[na, :2]
        n = float(np.linalg.norm(v))
        if n > 1e-12:
            return np.array([v[0] / n, v[1] / n, 0.0])
        # keine Stiele: groesste waagerechte Verschiebung ueberhaupt
        if u.ndim == 2 and u.shape[0]:
            k = int(np.argmax(np.abs(u[:, 0]) + np.abs(u[:, 1])))
            w = u[k, :2]
            n = float(np.linalg.norm(w))
            if n > 1e-12:
                return np.array([w[0] / n, w[1] / n, 0.0])
    return np.array([1.0, 0.0, 0.0])


def ersatzlasten_schiefstellung(model: Model, res, richtung=None) -> tuple:
    """
    Aequivalente Horizontalkraefte aus der Schiefstellung, 5.3.2(7).

    Je Stiel wird H = phi N_Ed am Kopf in Richtung der Schiefstellung
    angesetzt und am Fuss abgezogen - das ergibt genau das Kraeftepaar aus
    Bild 5.3 und laesst die Summe der Auflagerkraefte unberuehrt.

    Rueckgabe (F, info) mit F als Lastvektor ueber alle FHG.
    """
    F = np.zeros(model.ndof)
    kraefte = stielkraefte(model, res)
    if not kraefte:
        return F, {"phi": 0.0, "je_stiel": [], "H_gesamt": 0.0,
                   "hinweis": "keine gedrückten Stiele gefunden - "
                              "keine Schiefstellung angesetzt"}
    m = len(massgebende_stiele(kraefte))
    h = bauwerkshoehe(model)
    sk = schiefstellung(h, m)
    phi = sk["phi"]
    d = imperfektionsrichtung(model, res, richtung)
    je_stiel = []
    for name, N in kraefte.items():
        mem = model.members[name]
        ea = model.elements[mem.elements[0]]
        eb = model.elements[mem.elements[-1]]
        n_unten, n_oben = int(ea.nodes[0]), int(eb.nodes[-1])
        if model.nodes[n_unten][2] > model.nodes[n_oben][2]:
            n_unten, n_oben = n_oben, n_unten
        H = phi * N
        F[n_oben * NDOF:n_oben * NDOF + 3] += H * d
        F[n_unten * NDOF:n_unten * NDOF + 3] -= H * d
        je_stiel.append({"stab": name, "N_Ed": N, "H_Ed": H,
                         "knoten_oben": n_oben, "knoten_unten": n_unten})
    sk["je_stiel"] = je_stiel
    sk["richtung"] = [float(x) for x in d]
    sk["H_gesamt"] = float(sum(x["H_Ed"] for x in je_stiel))
    return F, sk


def _knicklinie(model: Model, mem) -> tuple:
    """(Knicklinie, Section, f_y) fuer die schwache Achse."""
    from .ec3.stability import buckling_curve
    e = model.elements[mem.elements[0]]
    sec = model.sections.get(e.sec)
    mat = model.materials.get(e.mat)
    if sec is None or mat is None:
        return "c", sec, 235e6
    fy = mat.yield_strength(sec.t_max) or 235e6
    return buckling_curve(sec, fy, "z"), sec, fy


def vorkruemmung_noetig(model: Model, mem, Nc: float) -> dict:
    """
    Kriterium 5.3.2(6): die Vorkruemmung eines Einzelstabes ist nur
    anzusetzen, wenn der Stab biegesteif angeschlossen und schlank genug ist:

        lambda_quer > 0,5 sqrt(A f_y / N_Ed)

    lambda_quer wird um die schwache Achse mit der Knicklaenge L_cr,z des
    Stabes gebildet.
    """
    kurve, sec, fy = _knicklinie(model, mem)
    if sec is None or Nc <= 0:
        return {"noetig": False, "grund": "keine Druckkraft"}
    e = model.elements[mem.elements[0]]
    mat = model.materials.get(e.mat)
    L = model.member_length(mem)
    Lcr = mem.Lcr_z if mem.Lcr_z else mem.beta_z * L
    if Lcr <= 0 or sec.Iz <= 0 or mat is None:
        return {"noetig": True, "grund": "Knicklänge unbekannt - "
                                         "auf der sicheren Seite angesetzt"}
    Ncr = math.pi ** 2 * mat.E * sec.Iz / Lcr ** 2
    meldung = mat.dicke_ohne_wert(sec.t_max, "fy") if hasattr(mat, "dicke_ohne_wert") else ""
    if meldung:
        # Ueber 80 mm ohne Dickentabelle kein f_y (Befund C4). Das Kriterium
        # braucht es nicht: lambda / (0,5 sqrt(A f_y/N_Ed)) = 2 sqrt(N_Ed/N_cr),
        # f_y kuerzt sich heraus. Bis zum 14.11.2026 stand hier still lambda und
        # Grenze mit f_y = 235 N/mm² (Befund A'11 der zweiten Runde); die
        # Entscheidung war dieselbe, die Zahlen nicht.
        noetig = Nc > Ncr / 4.0
        return {"noetig": noetig, "kurve": kurve, "L_cr": Lcr, "meldung": meldung,
                "grund": (f"N_Ed = {Nc / 1e3:.0f} kN {'>' if noetig else '≤'} N_cr,z/4 = {Ncr / 4e3:.0f} kN "
                          "(5.3.2(6) ohne f_y: λ̄ / (0,5 √(A f_y/N_Ed)) = 2 √(N_Ed/N_cr))"
                          + ("" if noetig else " → nach 5.3.2(6) nicht erforderlich")
                          + f"; {meldung}")}
    lam = math.sqrt(sec.A * fy / Ncr) if Ncr > 0 else 0.0
    grenze = 0.5 * math.sqrt(sec.A * fy / Nc)
    return {"noetig": lam > grenze, "lambda": lam, "grenze": grenze,
            "kurve": kurve, "L_cr": Lcr,
            "grund": (f"λ̄ = {lam:.3f} > 0,5 √(A f_y/N_Ed) = {grenze:.3f}"
                      if lam > grenze else
                      f"λ̄ = {lam:.3f} ≤ 0,5 √(A f_y/N_Ed) = {grenze:.3f} → "
                      "nach 5.3.2(6) nicht erforderlich")}


def _kraft_am_stabende(model: Model, el, j: int, f, F: np.ndarray) -> None:
    """Die Kraft ``f`` (global, (3,)) am Stabende ``j`` (0 Anfang, 1 Ende) des
    Elements ``el`` in den Lastvektor F: am Knoten, bei einem Balken mit
    Versatz der Stabenden dazu das Moment des starren Arms a_j x f - die
    Kraft greift am versetzten Stabende an, nicht am Knoten (Runde k10d,
    16.11.2026; bis dahin ohne Arm: Stab 6,5 m mit Arm 0,5 m in Stabrichtung
    am Ende, Theorie II. Ordnung Mz 11,26 statt 12,67 kNm)."""
    nd = int(el.nodes[j])
    f = np.asarray(f, float)
    F[nd * NDOF:nd * NDOF + 3] += f
    if el.typ != "beam":
        return
    rr = bm.versatz_vektoren(getattr(el, "exzentrizitaet", None))
    if rr is None:
        return
    X = np.asarray(model.nodes[el.nodes[:2]], float)
    T3n, _l = bm.local_axes(X[0], X[1], el.roll)
    F[nd * NDOF + 3:nd * NDOF + 6] += np.cross(T3n.T @ rr[j], f)


def ersatzlasten_vorkruemmung(model: Model, res, elastisch: bool = True,
                              alle: bool = False, stablasten: dict = None) -> tuple:
    """
    Aequivalente Querlasten aus der Vorkruemmung, 5.3.2(7), Bild 5.4:

        q = 8 N_Ed e_0 / L^2   ueber die Stablaenge, quer zur Stabachse
        V = 4 N_Ed e_0 / L     an beiden Enden entgegengesetzt

    Angesetzt wird in der lokalen **y**-Richtung des Stabes: e_0 stammt aus
    der Knicklinie fuer die schwache Achse z, und Knicken um z bedeutet
    Ausweichen in y (die y-Achse des ersten Elements gilt fuer den ganzen
    Stab; V greift an den Stabenden an, mit Versatz am versetzten Stabende,
    :func:`_kraft_am_stabende`).  Nur gedrueckte Staebe bekommen eine Vorkruemmung, und
    nur die nach 5.3.2(6) schlanken (``alle=True`` setzt sie fuer alle an).

    ``stablasten`` (ein leeres dict): q wirkt auf den Balken als Streckenlast
    im Element - Festeinspannkraefte wie eine Streckenlast des Anwenders, in
    F eingebaut (asm.stablasten_einbauen, mit Gelenken und Versatz), und im
    dict unter "feq" (lokale Ersatzknotenlasten je Element) und "q"
    (Abschnitte je Element) fuer Stabendkraefte und Feld. So rechnet Theorie
    II. Ordnung seit Verfahrensstand 74 (Runde k10d, 16.11.2026). Bis dahin
    ging q je Element halb und halb als Knotenkraft an die Elementknoten: in
    einem Element je Stab hoben sich diese Kraefte mit V an den Stabenden
    auf, und die Vorkruemmung fehlte still ganz (IPE 300, 6 m, 200 kN,
    Stabteilung 1: Mz 0 statt 11,52 kNm); in wenigen Teilen fehlte das
    Feldmoment zwischen den Knoten (3 Teile 10,36, 5 Teile 11,11 kNm).
    Ohne ``stablasten`` (Theorie III. Ordnung, deren Stablasten im
    mitgehenden System fest sind) wie bisher als Knotenkraefte - dort teilt
    statik3d.stabteilung den Stab fein genug (vorkruemmung_mindest). Auch
    Theorie II. Ordnung teilt gedrueckte Staebe mit Ersatzimperfektionen
    mindestens in 10 Teile (stabteilung.fein_system, Nachbesserung 2): in
    einem Element ist die Streckenlast bei Versatz in Stabrichtung und bei
    Federgelenken ungenau (Arm 1,0 m: 17,29 statt 13,87 kNm).
    """
    F = np.zeros(model.ndof)
    je_stab, uebersprungen, meldungen = [], [], []
    feq_v: dict = {}
    q_v: dict = {}
    for name, mem in model.members.items():
        if not mem.elements:
            continue
        if model.elements[mem.elements[0]].typ not in ("beam", "truss"):
            continue
        N = _member_N(model, mem, res)
        if N >= 0:                              # Zug: keine Vorkruemmung
            continue
        Nc = -N
        L = model.member_length(mem)
        if L <= 0:
            continue
        krit = vorkruemmung_noetig(model, mem, Nc)
        if krit.get("meldung") and krit["meldung"] not in meldungen:
            meldungen.append(krit["meldung"])
        if not alle and not krit["noetig"]:
            uebersprungen.append({"stab": name, "grund": krit["grund"]})
            continue
        kurve, _sec, _fy = _knicklinie(model, mem)
        e0 = e0_durch_L(kurve, elastisch) * L
        q = 8.0 * Nc * e0 / L ** 2
        els = [int(x) for x in mem.elements]
        ea = model.elements[els[0]]
        T3a, _ = asm.stab_achsen(model, ea)
        # eine Richtung fuer den ganzen Stab: die lokale y-Achse seines
        # ersten Elements, global. Bis Stand 73 je Element die eigene - ein
        # umgedrehtes Element bekam q gegen die anderen (Runde k10d)
        y_stab = np.asarray(T3a[1], float)
        for ie in els:
            el = model.elements[ie]
            # Achsen und Laenge des Stabs (mit verschiedenem Versatz zwischen
            # den versetzten Enden, wie member_length; 12.11.2026)
            T3, Le = asm.stab_achsen(model, el)
            ql = T3 @ (q * y_stab)
            ql[0] = 0.0                           # quer zum Stab
            if stablasten is not None and el.typ == "beam":
                # als Streckenlast in lokalen Achsen, wie asm.element_equivalent_loads
                # und element_distributed_loads eine Last des Anwenders
                Lel = model.element_length(ie)
                phy, phz = asm.stab_schubparameter(model, el, Lel)
                feq_v[ie] = feq_v.get(ie, np.zeros(12)) + asm.trapezoid_fixed_end_forces(
                    ql, ql, Lel, phy, phz)
                q_v[ie] = asm.abschnitte_zusammen(q_v.get(ie), [0.0, Lel, *ql, *ql])
                continue
            fk = 0.5 * Le * (T3.T @ ql)           # global, je Stabende des Elements
            for j in (0, 1):
                _kraft_am_stabende(model, el, j, fk, F)
        # V an den Enden des Stabs (bei umgedrehtem erstem oder letztem
        # Element der andere Knoten) und am versetzten Stabende: mit Versatz
        # das Moment des Arms dazu. Bis Stand 73 immer nodes[0] des ersten und
        # nodes[-1] des letzten Elements, ohne Arm (Runde k10d)
        from .stabteilung import _vorwaerts
        ja = 0 if _vorwaerts(model, els, 0) else 1
        jb = 1 if _vorwaerts(model, els, len(els) - 1) else 0
        V = 4.0 * Nc * e0 / L
        _kraft_am_stabende(model, ea, ja, -V * y_stab, F)
        _kraft_am_stabende(model, model.elements[els[-1]], jb, -V * y_stab, F)
        je_stab.append({"stab": name, "L": L, "kurve": kurve, "e0_L": e0 / L,
                        "e_0": e0, "N_Ed": Nc, "q": q, "V": V,
                        "lambda": krit.get("lambda", 0.0),
                        "grenze": krit.get("grenze", 0.0)})
    if feq_v:
        asm.stablasten_einbauen(model, feq_v, F)
    if stablasten is not None:
        stablasten["feq"] = feq_v
        stablasten["q"] = q_v
    aus = {"je_stab": je_stab, "uebersprungen": uebersprungen,
           "elastisch": elastisch, "anzahl": len(je_stab)}
    if meldungen:
        # Staebe ohne f_y (ueber 80 mm, Befund C4): Kriterium ohne f_y, Knicklinie
        # wie fuer f_y unter 460 N/mm² (14.11.2026)
        aus["meldungen"] = meldungen
    return F, aus


def normalkraefte_kg(model: Model, u: np.ndarray, aktiv=None, n_anfang: dict = None,
                     feq: dict = None) -> dict:
    """{Element: Normalkraft} der Balken (nicht Fachwerkstab, Seil), wie sie
    asm.geometric_stiffness fuer K_g nimmt (Zug positiv). ``feq``
    (solver.case_loads): die Stablasten - ein Laengsgelenk traegt die Last in
    Stabrichtung (asm.stab_normalkraft, Befund B1 vom 14.11.2026)."""
    n_anfang = n_anfang or {}
    feq = feq or {}
    out = {}
    for i, e in enumerate(model.elements):
        if e.typ not in asm.LINE_TYPES or e.typ in ("truss", "seil"):
            continue
        if aktiv is not None and not aktiv[i]:
            continue
        out[i] = asm.stab_normalkraft(model, e, u, n_anfang.get(i, 0.0), f0=feq.get(i))
    return out


# ==========================================================================
# alpha_cr (5.2.1)
# ==========================================================================
def alpha_cr(model: Model, system, u: np.ndarray, nmodes: int = 1, n_anfang: dict = None,
             feq: dict = None, endkraefte: dict = None) -> dict:
    """
    Kleinster positiver Verzweigungslastfaktor zum Verformungszustand ``u``.

    Geloest wird (K + alpha K_g) v = 0 in der Form -K_g v = mu K v mit
    alpha = 1/mu; gesucht ist das groesste positive mu.

    ``n_anfang`` {Element: Normalkraft der Anfangsdehnung}
    (solver.anfangsnormalkraefte, seit dem 13.10.2026): Temperatur,
    Vorspannung und Verriegelung zaehlen in K_g mit wie im Ergebnis. Bis
    dahin las K_g nur E A Δl/L - ein Zugband mit 70 kN Anfangsdehnung, das im
    Ergebnis +6,50 kN traegt, stand mit -63,50 kN darin (alpha_cr 1,688), und
    ein Stab unter reinem Temperatur-Zwang hatte "keine Normalkräfte".

    K_g nimmt nur die Elemente, die im ``system`` wirken (``system.aktiv``:
    Situation, abgeschaltete Staebe), wie K und wie solve_theorie2 und
    solve_buckling. Bis zum 14.10.2026 baute alpha_cr K_g aus allen
    Elementen: ein in der Situation abgeschalteter Fachwerkstab neben einer
    Kragstuetze, dessen Enden sich mit ihr bewegen, stand mit seiner
    rechnerischen Normalkraft darin: gedrueckt alpha_cr 4,354 statt 4,798
    (-9 %), gezogen 5,341 statt 4,798 (+11 %, auf der unsicheren Seite;
    tests/test_stab_nachzug.py).

    Dazu das **Einzelknicken** der gedrueckten Fachwerkstaebe
    (:func:`einzelstab_knicken`, seit 14.10.2026): ``einzelstaebe`` (Liste,
    kleinstes zuerst), ``alpha_cr_stab`` und ``stab`` (der massgebende Stab;
    inf und "" ohne gedrueckten Fachwerkstab). ``alpha_cr`` bleibt das des
    Systems und entscheidet weiter nach 5.2.1(3).

    Rueckgabe {"alpha_cr": ..., "modus": Eigenvektor, "fehler": "",
    "einzelstaebe": [...], "alpha_cr_stab": ..., "stab": ...}.

    ``feq`` (solver.case_loads): die Stablasten fuer den Armanteil der Staebe
    mit Versatz (asm.versatz_arm_kg, seit dem 14.11.2026); alpha_cr nimmt
    davon den symmetrischen Teil - eine untere Schranke, siehe dort.
    ``endkraefte`` (Results.beam_end der Elemente einer Sollkraft,
    solver._soll_endkraefte): deren Stabendkraft mit der Verriegelung.
    """
    einzel = einzelstab_knicken(model, u, getattr(system, "aktiv", None), n_anfang, feq)
    stab = {"einzelstaebe": einzel,
            "alpha_cr_stab": einzel[0]["alpha_cr"] if einzel else math.inf,
            "stab": einzel[0]["stab"] if einzel else ""}
    Kg = asm.geometric_stiffness(model, u, getattr(system, "aktiv", None), n_anfang=n_anfang,
                                 feq=feq, symmetrisch=True, endkraefte=endkraefte)
    fi = system.fi
    Kgff = Kg[fi][:, fi].tocsc()
    if Kgff.shape[0] < 3 or abs(Kgff).max() == 0:
        return {"alpha_cr": math.inf, "fehler": "keine Normalkräfte - "
                                                "kein Verzweigungsproblem", **stab}
    try:
        mu, vecs = groesstes_mu(system.Kff, Kgff, k=nmodes)
    except Exception as exc:                       # pragma: no cover
        return {"alpha_cr": math.inf, "fehler": f"Eigenwertlöser: {exc}", **stab}
    if mu is None:
        return {"alpha_cr": math.inf,
                "fehler": "kein positiver Verzweigungslastfaktor", **stab}
    modus = np.zeros(model.ndof)
    modus[fi] = vecs[:, 0]
    mx = float(np.abs(modus).max())
    if mx > 0:
        modus /= mx
    a = float(1.0 / mu[0])
    grob = stabteilung_grob(model, u, a, getattr(system, "aktiv", None), n_anfang, feq)
    return {"alpha_cr": a, "modus": modus, "fehler": "", **stab,
            "teilung_grob": grob, "hinweis_teilung": teilung_hinweis(grob)}


#: Ab diesem Verhaeltnis alpha_cr |N| / (pi^2 E I / l^2) eines Balkenelements
#: (l seine Laenge) ist die kubische Biegelinie fuer die Knickfigur zu grob:
#: bei 1 (Euler-Fall 2 in einem Element) liegt alpha_cr 21,6 % zu hoch, bei
#: 0,25 (zwei Elemente bzw. Kragstuetze in einem) 0,75 %.
TEILUNG_GRENZE = 0.3


def stabteilung_grob(model: Model, u: np.ndarray, a_cr: float, aktiv=None, n_anfang: dict = None,
                     feq: dict = None) -> list:
    """Gedrueckte Balkenelemente, die fuer die Knickfigur zu lang sind
    (Befund A9 der Pruefagenten, 09.11.2026): alpha_cr |N| erreicht
    TEILUNG_GRENZE der Euler-Last des einzelnen Elements. Die Verzweigung
    rechnet je Element mit einer kubischen Biegelinie; mit einem Element je
    Knickhalbwelle liegt alpha_cr bis 21,6 % zu hoch (unsichere Seite), und
    bis dahin sagte das Programm nichts. Rueckgabe [(Verhaeltnis, Element,
    Stab)], das groesste zuerst."""
    if not math.isfinite(a_cr) or a_cr <= 0:
        return []
    from .solver import _stab_namen
    namen = _stab_namen(model)
    eltern = getattr(model, "_stabteilung_eltern", None) or {}
    out = []
    for i, N in normalkraefte_kg(model, u, aktiv, n_anfang, feq).items():
        if N >= 0.0:
            continue
        e = model.elements[i]
        sec = model.sections[e.sec]
        # eine an beiden Enden gelenkige Ebene prueft einzelstab_knicken
        frei = set(int(x) for x in (e.hinges or []))
        Is = [Ia for Ia, d1, d2 in ((sec.Iy, 4, 10), (sec.Iz, 5, 11)) if not (d1 in frei and d2 in frei)]
        if not Is:
            continue
        I = min(Is)
        l = model.element_length(i)
        if I <= 0 or l <= 0:
            continue
        v = a_cr * (-N) / (math.pi ** 2 * model.materials[e.mat].E * I / l ** 2)
        if v >= TEILUNG_GRENZE:
            # intern geteilt (statik3d.stabteilung): das Element des Modells nennen
            j = int(eltern.get(int(i), int(i)))
            out.append((float(v), j, str(namen.get(i, ""))))
    out.sort(reverse=True)
    gesehen, eindeutig = set(), []
    for v, j, name in out:
        if j not in gesehen:
            gesehen.add(j)
            eindeutig.append((v, j, name))
    return eindeutig


def teilung_hinweis(grob: list) -> str:
    """Der Satz zu :func:`stabteilung_grob` ("" ohne Befund)."""
    if not grob:
        return ""
    v, i, name = grob[0]
    # Elementnummer ab 0 wie in Tabellen und Modellbaum (C13; Befund 13/35,
    # 11.11.2026 - davor „Element {i + 1}“, das Element danach)
    wo = f"Element {i}" + (f" (Stab {name})" if name else "")
    mehr = f" und {len(grob) - 1} weitere" if len(grob) > 1 else ""
    return (f"α_cr: Stabteilung zu grob – {wo}{mehr} ist für die Knickfigur zu lang; "
            f"α_cr kann bis 22 % zu hoch liegen (unsichere Seite). Gedrückte Stäbe in "
            f"mindestens vier Elemente teilen.")


def einzelstab_knicken(model: Model, u: np.ndarray, aktiv=None, n_anfang: dict = None,
                       feq: dict = None) -> list:
    """Das Knicken der einzelnen gedrueckten Fachwerkstaebe (Elementtyp
    truss, auch „nur Druck“; ein Zugstab faellt bei Druck aus):
    alpha_cr,i = pi^2 E I / (L^2 N_Ed) je Stab. Knicklaenge L ist die
    Systemlaenge, gelenkig: die Laenge des Stabs aus seinen Elementen, ein
    Element ohne Stab mit seiner Laenge. I ist das kleinere der beiden
    Hauptachsen (Iy, Iz), N_Ed die groesste Druckkraft seiner Elemente im
    Zustand ``u`` wie im Ergebnis (mit der Anfangsdehnung ``n_anfang``).
    Rueckgabe je gedrueckten Stab {stab, L, N (Druck positiv), I, achse, E,
    alpha_cr}, das kleinste alpha_cr zuerst.

    Die geometrische Steifigkeit des Fachwerkstabs ist die Saitenform N/L
    (asm.geometric_stiffness): sie haelt den Stab zwischen seinen Knoten
    gerade, sein Ausknicken dort steht in der Verzweigung des Systems nicht.
    Bis zum 14.10.2026 nannte das Programm nur das alpha_cr des Systems: ein
    Fachwerk, dessen Druckstab laengst knickt, stand mit einem hohen alpha_cr
    da (tests/test_stab_querlast.py)."""
    from .solver import _stab_namen
    namen = _stab_namen(model)
    n_anfang = n_anfang or {}
    feq = feq or {}             # Stablasten: Laengsgelenk mit Last in Stabrichtung (B1)
    je_stab: dict = {}
    pendel: dict = {}
    for i, e in enumerate(model.elements):
        if aktiv is not None and not aktiv[i]:
            continue
        if e.typ != "truss":
            # Balken aus einem Element, an beiden Enden in einer Ebene
            # gelenkig (09.11.2026, mit A7): seine K_g ist dort die Saite wie
            # beim Fachwerkstab, sein Ausknicken zwischen den Knoten steht
            # nicht in der Verzweigung - es kommt hierher
            if e.typ in ("seil",) or e.typ not in asm.LINE_TYPES:
                continue
            frei = set(int(x) for x in (e.hinges or []))
            ebenen = [(achse, d1, d2) for achse, d1, d2 in (("y", 4, 10), ("z", 5, 11))
                      if d1 in frei and d2 in frei]
            if not ebenen:
                continue
            pendel[i] = ebenen
        elif getattr(e, "nur", "") == "zug":
            continue
        N = asm.stab_normalkraft(model, e, u, n_anfang.get(i, 0.0), f0=feq.get(i))
        # ab 0 wie in Tabellen und Modellbaum (C13; Befund 35, 11.11.2026) - fuer
        # Fachwerkstab und Gelenkbalken gleich, sonst traefen sich zwei Namen
        name = namen.get(i, f"Element {i}") if i not in pendel else f"Element {i}"
        alt = je_stab.get(name)
        if alt is None or -N > alt[0]:
            je_stab[name] = (-N, i)
    out = []
    for name, (Nc, i) in je_stab.items():
        if Nc <= 0:
            continue
        e = model.elements[i]
        mat = model.materials[e.mat]
        sec = model.sections[e.sec]
        mem = model.members.get(name)
        L = model.member_length(mem) if mem is not None else model.element_length(i)
        if i in pendel:
            I, achse = min(((sec.Iy if a == "y" else sec.Iz), a) for a, _d1, _d2 in pendel[i])
        else:
            I, achse = (sec.Iz, "z") if sec.Iz <= sec.Iy else (sec.Iy, "y")
        if L <= 0 or I <= 0:
            continue
        a = math.pi ** 2 * mat.E * I / (L ** 2 * Nc)
        out.append({"stab": str(name), "L": float(L), "N": float(Nc), "I": float(I),
                    "achse": achse, "E": float(mat.E), "alpha_cr": float(a)})
    out.sort(key=lambda d: d["alpha_cr"])
    return out


def _definit_zerlegen(C):
    """C symmetrisch ohne Zeilentausch zerlegen: (Zerlegung, positiv definit?).

    Mit symmetrischer Umordnung und ohne Pivottausch ist P C P^T = L D L^T
    und diag(U) = D; nach dem Traegheitssatz ist C genau dann positiv
    definit, wenn alle Pivots positiv sind. Fuer positiv definites C ist die
    Zerlegung ohne Tausch stabil - sie dient danach als Shift-invert.
    """
    from scipy.sparse.linalg import splu
    try:
        lu = splu(C.tocsc(), permc_spec="MMD_AT_PLUS_A", diag_pivot_thresh=0.0,
                  options={"SymmetricMode": True})
    except RuntimeError:                           # exakt singulaer
        return None, False
    definit = (np.array_equal(lu.perm_r, lu.perm_c)
               and bool(np.all(lu.U.diagonal() > 0.0)))
    return lu, definit


def groesstes_mu(Kff, Kgff, k: int = 1, schaetzwert: float = None):
    """Die ``k`` groessten mu von -K_g v = mu K v, das groesste zuerst.

    Rueckgabe (mu, Eigenvektoren je Spalte) oder (None, None), wenn schon
    der Schaetzwert aus Schritt 1 nicht ueber 1e-12 liegt (alpha_cr ueber
    1e12: keine Verzweigung in Lastrichtung). ``schaetzwert`` ersetzt
    Schritt 1 (nur fuer die Pruefung, ob ein schlechter Schaetzwert
    trotzdem mu_max liefert).

    K ist das Skalarprodukt, nicht -K_g. Bis zum 23.09.2026 stand in
    alpha_cr eigsh(K, M=-K_g, sigma=0): ARPACK setzt fuer M ein positiv
    (semi)definites Skalarprodukt voraus, mit gezogenen und gedrueckten
    Staeben zugleich ist -K_g aber indefinit; am Zweigelenkrahmen
    (tests/test_theorie2.py, Lastfall W) kamen 200 verschiedene Werte unter
    3,6 statt 77,33 heraus. K ist nach dem Einbau der Lager positiv definit,
    die mu sind reell.

    Drei Schritte statt eines Aufrufs eigsh(-K_g, M=K, 'LA'): Der
    Regelmodus trennt dicht beieinander liegende groesste mu nur muehsam. Am
    symmetrischen Geschossrahmen (4 x 4 Felder, 4 Geschosse, 5856 FHG,
    Lastfall G) liegen die 40 groessten mu innerhalb 3,1e-4 von mu_max
    (dicht gerechnet), und der Regelmodus brauchte 52,5 s je Aufruf, mit
    6 x 6 Feldern und 6 Geschossen (16992 FHG) 1527 s (gemessen 24.09.2026,
    Stand 9dc88a3). Um eine Verschiebung s knapp ueber mu_max werden die
    Abstaende zu 1/(mu - s) gespreizt:

      1. Schaetzwert theta: Regelmodus mit lockerer Toleranz 1e-3. theta ist
         ein Rayleigh-Quotient, also theta <= mu_max. Reiner Zug (Zugstab
         der Pruefung): theta = -3,9e-4, dicht groesstes mu 4e-17, also
         "kein positiver".
      2. s = theta (1 + 1e-3); ob s wirklich ueber mu_max liegt, sagt der
         Traegheitssatz: s K + K_g ist genau dann positiv definit, wenn kein
         mu >= s ist. Sonst s schrittweise zehnmal weiter weg (am Rahmen mit
         16992 FHG lag s = theta (1 + 1e-4) noch darunter).
      3. Shift-invert um s: das mu naechst s ist mu_max.

    Jetzt (24.09.2026, mit Aufbau von K_g): 5856 FHG 0,24 s, bis auf 8e-15
    gleich dem dichten Bezug 11,25497228790; 16992 FHG 0,9 bis 1,0 s. Der
    alte Aufruf eigsh(K, M=-K_g, sigma=0) allein brauchte 0,18 bzw. 0,7 s.
    Toleranz der Stufe 3: 1e-10. Mit 0 dauerte das Verfahren am
    16992-FHG-Rahmen 1,5 bis 1,6 statt 0,6 s (ohne K_g), und die groesste
    Abweichung vom dichten Bezug an 46 Zustaenden (Halle, Zweigelenkrahmen)
    blieb 5,3e-12. Der feste Startvektor macht den Rechenweg gleich; ohne
    ihn gaben 200 Aufrufe unter K1 des Zweigelenkrahmens 198 verschiedene
    Werte, mit ihm einen. Allgemein zugesagt ist Bitgleichheit nicht
    (Theoriehandbuch 5.1a).
    """
    from scipy.sparse.linalg import eigsh, LinearOperator
    n = Kgff.shape[0]
    A = (-Kgff).tocsc()
    v0 = np.random.default_rng(0).standard_normal(n)
    if schaetzwert is None:
        theta = float(np.max(eigsh(A, k=1, M=Kff, which="LA", v0=v0, tol=1e-3,
                                   return_eigenvectors=False)))
    else:
        theta = float(schaetzwert)
    if not theta > 1e-12:
        return None, None
    for stufe in range(9):
        s = theta * (1.0 + 1e-3 * 10.0 ** stufe)
        lu, definit = _definit_zerlegen(s * Kff + Kgff)
        if definit:
            break
    else:
        raise RuntimeError("keine Verschiebung über dem größten Eigenwert gefunden")
    # (A - s K)^-1 = -(s K + K_g)^-1
    op = LinearOperator((n, n), dtype=float,
                        matvec=lambda x: -lu.solve(np.asarray(x, dtype=float).ravel()))
    mu, vecs = eigsh(A, k=max(1, min(k, n - 2)), M=Kff, sigma=s, which="LM",
                     v0=v0, OPinv=op, tol=1e-10)
    folge = np.argsort(mu)[::-1]
    return mu[folge], vecs[:, folge]


def erforderlich(a_cr: float, plastisch: bool = False) -> dict:
    """Kriterium 5.2.1(3): Theorie II. Ordnung noetig?"""
    grenze = 15.0 if plastisch else 10.0
    return {"alpha_cr": a_cr, "grenze": grenze, "noetig": a_cr < grenze,
            "text": (f"α_cr = {a_cr:.2f} < {grenze:.0f} → Theorie II. Ordnung "
                     "erforderlich (5.2.1(3))" if a_cr < grenze else
                     f"α_cr = {a_cr:.2f} ≥ {grenze:.0f} → Theorie I. Ordnung "
                     "ausreichend (5.2.1(3))")}


# ==========================================================================
# Gleichgewicht am verformten System
# ==========================================================================
@dataclass
class Th2Info:
    """Was bei einer Kombination nach Theorie II. Ordnung passiert ist."""
    kombination: str = ""
    alpha_cr: float = math.inf
    grenze: float = 10.0
    # Einzelknicken der gedrueckten Fachwerkstaebe (14.10.2026,
    # einzelstab_knicken): kleinstes alpha_cr,i, sein Stab, alle Druckstaebe
    alpha_cr_stab: float = math.inf
    stab_massgebend: str = ""
    einzelstaebe: list = field(default_factory=list)
    gerechnet: bool = False
    iterationen: int = 0
    konvergenz: float = 0.0
    schiefstellung: dict = field(default_factory=dict)
    vorkruemmung: dict = field(default_factory=dict)
    u_max_I: float = 0.0
    u_max_II: float = 0.0
    zuwachs: float = 0.0
    hinweise: list = field(default_factory=list)
    fehler: str = ""

    @property
    def alpha_cr_gesamt(self) -> float:
        """min(System; Einzelstab)."""
        return min(self.alpha_cr, getattr(self, "alpha_cr_stab", math.inf))

    def stab_aus(self, ac: dict) -> None:
        """Die Einzelstabwerte aus dem Ergebnis von :func:`alpha_cr` uebernehmen."""
        self.alpha_cr_stab = float(ac.get("alpha_cr_stab", math.inf))
        self.stab_massgebend = str(ac.get("stab", "") or "")
        self.einzelstaebe = list(ac.get("einzelstaebe") or [])

    def text(self) -> str:
        if self.fehler:
            return f"nicht geführt: {self.fehler}"
        if not self.gerechnet:
            return erforderlich(self.alpha_cr, self.grenze > 10.0)["text"]
        return (f"Theorie II. Ordnung, {self.iterationen} Iterationen, "
                f"Verformungszuwachs {self.zuwachs * 100:+.1f} %")


def _voll_loesen(system, K_extra, F: np.ndarray, us=None) -> np.ndarray:
    """(K + K_extra) u = F mit der vollen, unsymmetrischen Matrix (SuperLU,
    scipy spsolve) auf den freien FHG, mit den vorgegebenen Verschiebungen
    ``us`` wie StaticSystem.solve - fuer die Iteration nach Theorie II.
    Ordnung, wenn sie mit dem schiefsymmetrischen Armanteil als Last stockt
    (Verfahrensstand 41). Die Loeser des Systems (ama, PARDISO symmetrisch)
    verlangen Symmetrie; Stabwerke sind klein genug fuer die direkte Loesung.
    Mit Hilfsfesselung (freie Bewegung) gibt es diesen Weg nicht."""
    from scipy.sparse.linalg import spsolve
    if getattr(system, "_rand", 0):
        raise RuntimeError("freie Bewegung mit Hilfsfesselung - die volle Matrix ist singulär")
    fi, si = system.fi, system.si
    u = system.vals.copy()
    rhs = np.asarray(F, float)[fi].copy()
    if us is not None:
        u[si] += us[si]
        idx, k = system._federn()
        if idx.size:
            f_f = np.zeros(system.model.ndof)
            f_f[idx] = k * us[idx]
            rhs = rhs + f_f[fi]
    Kt = (system.K + K_extra).tocsr()
    if np.any(u[si]):
        rhs = rhs - Kt[fi][:, si] @ u[si]
    x = np.asarray(spsolve(Kt[fi][:, fi].tocsc(), rhs), float)
    if not np.all(np.isfinite(x)):
        raise RuntimeError("volle Matrix singulär")
    u[fi] = x
    return u


def solve_theorie2(model: Model, factors: dict, name: str, system=None,
                   imperfektionen: bool = True, elastisch: bool = True,
                   max_iter: int = 30, tol: float = 1e-6,
                   richtung=None, alle_vorkruemmungen: bool = False,
                   progress=None, stabteilung: bool = True):
    """
    Eine Kombination am verformten System rechnen.

    ``stabteilung``: Balken intern teilen (statik3d.stabteilung, seit
    12.11.2026) - gerechnet wird am geteilten Modell, das Ergebnis gilt fuer
    die Knoten und Elemente von ``model``.

    Vorgehen:
      1. Loesung nach Theorie I. Ordnung (Grundzustand)
      2. alpha_cr dazu bestimmen
      3. iterativ: Normalkraefte -> K_g und Ersatzlasten -> neue Loesung,
         bis sich die Verformungen nicht mehr aendern

    Rueckgabe (Results, Th2Info).
    """
    from .solver import (StaticSystem, case_loads, case_prescribed, postprocess, Results,
                         ausweich_info, ausweichgruende_zaehlen, anfangsnormalkraefte)
    from .vorspannkraft import theorie_sperre
    sperre = theorie_sperre(model, factors, "II")
    if sperre:
        # Vorspannkraft (Soll nach Verankerung, 13.10.2026): das Ergebnis nach
        # Theorie I. Ordnung bleibt stehen und wird gekennzeichnet
        return Results(name=name, kind="combination", model=model), Th2Info(kombination=name, fehler=sperre)
    ll_hinweise = []
    if stabteilung:
        from .stabteilung import fein_system, zurueck, laengslast_hinweise, kraefte_theorie1
        system = system or StaticSystem(model)
        # Stab mit Last in Stabrichtung in weniger als vier gerechneten
        # Elementen: Hinweis, kein geaenderter Wert (Runde k7, 14.11.2026)
        ll_hinweise = laengslast_hinweise(model, factors, getattr(system, "aktiv", None), 1,
                                          kraefte=lambda: kraefte_theorie1(model, system, factors))
        # mit Ersatzimperfektionen gedrueckte Staebe mindestens in
        # TEILUNG_VORKRUEMMUNG Teilen, auch bei Stabteilung 1 (Runde k10d,
        # Nachbesserung 2, Stand 74): in einem Element war die Vorkruemmung
        # bei Versatz in Stabrichtung und bei Federgelenken falsch
        fein = fein_system(model, system, factors, vorkruemmung=bool(imperfektionen),
                           hinweise=ll_hinweise)
        if fein is not None:
            m2, sys2, abb = fein
            res2, info = solve_theorie2(m2, factors, name, sys2, imperfektionen=imperfektionen,
                                        elastisch=elastisch, max_iter=max_iter, tol=tol,
                                        richtung=richtung, alle_vorkruemmungen=alle_vorkruemmungen,
                                        progress=progress, stabteilung=False)
            info.hinweise.extend(h for h in ll_hinweise if h not in info.hinweise)
            return zurueck(model, res2, abb), info
    t0 = time.time()
    system = system or StaticSystem(model)
    # Das Ergebnis ersetzt die lineare Kombination - ein Ausweichen des
    # Gleichungsloesers muss es darum selbst tragen (Befund K2, 22.09.2026)
    ausweich_vorher = ausweichgruende_zaehlen(system)
    aktiv = getattr(system, "aktiv", None)          # Situation: abgeschaltete Elemente
    F, feq, q, temp = case_loads(model, factors, aktiv)
    us = case_prescribed(model, factors)
    # Normalkraefte der Anfangsdehnung (Temperatur, Vorspannung) fuer K_g -
    # wie im Ergebnis (13.10.2026)
    n_anf = anfangsnormalkraefte(model, factors, aktiv)

    # --- Theorie I. Ordnung als Ausgangspunkt
    u1 = system.solve(F, us=us)
    res1 = Results(name=name, kind="combination", model=model)
    from .solver import auto_gehalten_abtrennen, verschiebungen_eintragen
    verschiebungen_eintragen(model, res1, u1, system.reactions(u1, F))
    # Last an automatisch gehaltenen FHG: nie still (14.10.2026)
    auto_gehalten_abtrennen(model, getattr(system, "auto", None), res1, F, aktiv)
    postprocess(model, u1, res1, feq, q, temp, aktiv=aktiv)

    info = Th2Info(kombination=name, u_max_I=float(np.abs(u1).max()))
    info.hinweise.extend(ll_hinweise)
    # Stab mit Druck und Biegung, Biegedrillknicken nicht anderweitig erfasst:
    # K_G hat kein Momentenglied - Hinweis, kein geaenderter Wert (Runde k8)
    from .bdk_hinweis import hinweis_th2 as bdk_hinweis, merken as bdk_merken
    bdk_merken(info, *bdk_hinweis(model, aktiv, res=res1))
    ac = alpha_cr(model, system, u1, n_anfang=n_anf, feq=feq)
    info.alpha_cr = ac["alpha_cr"]
    info.stab_aus(ac)
    if ac.get("fehler"):
        info.hinweise.append(ac["fehler"])
    if ac.get("hinweis_teilung"):
        info.hinweise.append(ac["hinweis_teilung"])
    if info.alpha_cr <= 1.0:
        # Ueber der Verzweigungslast hat (K + K_g) u = F zwar eine Loesung,
        # aber keine brauchbare: am Druckkragarm (tests/test_umhuellende.py,
        # Druck 1e6 N, alpha_cr 0,756) kam u_y an der Spitze -10,100 mm gegen
        # linear +3,321 mm heraus, als gerechnet uebernommen, ohne Fehler
        # und Hinweis; die Zusammenfassung meldete "Verformungszuwachs
        # +204.2 %" (gemessen 23.09.2026). Mit dem Fehler uebernehmen
        # check_theorie2 und _lastfaelle_hoeherer_ordnung das Ergebnis nicht,
        # und der Bericht nennt die Zeile "nicht geführt".
        info.fehler = (f"α_cr = {info.alpha_cr:.2f} ≤ 1: die Last liegt über der "
                       "Verzweigungslast, am verformten System gibt es kein "
                       "Gleichgewicht – Aussteifung, Querschnitte oder Lasten prüfen")
        if progress:
            progress(f"{name}: α_cr = {info.alpha_cr:.2f} ≤ 1, nicht gerechnet")
        return res1, info

    u = u1.copy()
    res = res1
    Fges = F.copy()
    # Stockt die Iteration mit dem schiefsymmetrischen Armanteil als Last,
    # loest sie mit der vollen unsymmetrischen Matrix weiter (``voll``, eigene
    # max_iter Schritte); bleibt sie dann unkonvergiert, ist es ein Fehler
    # (Verfahrensstand 41, 14.11.2026). Bis dahin stockte sie an sehr weichen
    # Stuetzen mit Versatz (alpha_cr 1,4: nach 30 Schritten 0,355 % Aenderung,
    # phi_x 10,17 statt 2,64 mrad) und gab das Ergebnis als gerechnet aus.
    voll = False
    schritte_voll = 0
    konv_vor = math.inf
    nicht_konvergiert = False
    it = 0
    while True:
        it += 1
        Fimp = np.zeros(model.ndof)
        feq_it, q_it = feq, q
        if imperfektionen:
            Fs, s_info = ersatzlasten_schiefstellung(model, res, richtung)
            # die Vorkruemmung als Streckenlast im Element (Verfahrensstand
            # 74): ihre Festeinspannkraefte und Abschnitte zu denen der Lasten
            sl_v: dict = {}
            Fv, v_info = ersatzlasten_vorkruemmung(model, res, elastisch,
                                                   alle=alle_vorkruemmungen, stablasten=sl_v)
            Fimp = Fs + Fv
            info.schiefstellung, info.vorkruemmung = s_info, v_info
            if sl_v.get("feq"):
                feq_it = dict(feq)
                for i_, f_ in sl_v["feq"].items():
                    feq_it[i_] = feq_it.get(i_, 0.0) + f_
                q_it = dict(q)
                for i_, z_ in sl_v["q"].items():
                    q_it[i_] = asm.abschnitte_zusammen(q_it.get(i_), z_)
        Fges = F + Fimp
        # mit dem Armanteil der Staebe mit Versatz (14.11.2026): voll, die
        # Statik des gedrehten Arms wie nach Theorie III. Ordnung - der
        # symmetrische Teil in der Matrix, der schiefsymmetrische als Last aus
        # dem vorigen Schritt (die Matrix bleibt symmetrisch, ama); ohne
        # Versatz ist K_schief None und alles wie bisher
        if voll:
            Kg = asm.geometric_stiffness(model, u, aktiv, n_anfang=n_anf, feq=feq_it)
            K_schief = None
        else:
            Kg = asm.geometric_stiffness(model, u, aktiv, n_anfang=n_anf, feq=feq_it, symmetrisch=True)
            K_schief = asm.versatz_arm_schief(model, u, aktiv, feq_it)
        # dieselben Normalkraefte wie in K_g fuer die Stabendkraefte und das
        # Feld (A8, 09.11.2026: postprocess rechnet sie mit k + k_G)
        n_geo = normalkraefte_kg(model, u, aktiv, n_anf, feq)
        try:
            if voll:
                u_neu = _voll_loesen(system, Kg, Fges, us)
            else:
                u_neu = system.solve(Fges if K_schief is None else Fges - K_schief @ u, K_extra=Kg, us=us)
        except Exception as exc:
            info.fehler = f"Gleichungssystem singulär (α_cr ≈ 1?): {exc}"
            break
        d = float(np.abs(u_neu - u).max())
        bezug = max(float(np.abs(u_neu).max()), 1e-12)
        u = u_neu
        res = Results(name=name, kind="combination", model=model)
        verschiebungen_eintragen(model, res, u, system.reactions(
            u, Fges, K_extra=Kg if K_schief is None else Kg + K_schief))
        auto_gehalten_abtrennen(model, getattr(system, "auto", None), res, Fges, aktiv)
        postprocess(model, u, res, feq_it, q_it, temp, aktiv=aktiv, n_geo=n_geo)
        info.iterationen = it
        info.konvergenz = d / bezug
        if d / bezug < tol:
            break
        if voll:
            schritte_voll += 1
            if schritte_voll >= max_iter:
                nicht_konvergiert = True
                break
        elif K_schief is not None and ((it >= 3 and info.konvergenz > 0.5 * konv_vor) or it >= max_iter):
            # stockt: die Aenderung faellt nicht mehr wenigstens auf die Haelfte
            voll = True
            info.hinweise.append(
                f"Theorie II. Ordnung: die Iteration mit dem Armanteil des Versatzes als Last stockte "
                f"nach {it} Schritten (Änderung {zl.zahl_text(info.konvergenz * 100, stellen=3)} %) – "
                "weiter mit der vollen unsymmetrischen Matrix")
        elif it >= max_iter:
            break
        konv_vor = info.konvergenz
    if it >= max_iter and not voll and not info.fehler and info.konvergenz >= tol:
        info.hinweise.append(
            f"Die Iteration ist nach {max_iter} Schritten nicht konvergiert "
            f"(letzte Änderung {info.konvergenz * 100:.3f} %). Das Tragwerk ist "
            "sehr verformungsweich - α_cr prüfen.")
    if nicht_konvergiert and not info.fehler:
        info.fehler = (
            f"Theorie II. Ordnung nicht konvergiert: auch mit der vollen unsymmetrischen Matrix "
            f"(Armanteil des Versatzes) nach {it} Schritten noch "
            f"{zl.zahl_text(info.konvergenz * 100, stellen=3)} % Änderung – kein Ergebnis nach Theorie "
            f"II. Ordnung. Das Tragwerk ist sehr verformungsweich (α_cr = "
            f"{zl.zahl_text(info.alpha_cr, stellen=4)}); Aussteifung, Querschnitte oder Lasten prüfen")

    info.gerechnet = not info.fehler
    info.u_max_II = float(np.abs(u).max())
    if info.u_max_I > 0:
        info.zuwachs = info.u_max_II / info.u_max_I - 1.0
    res.info.update({"typ": model.combinations[name].typ if name in model.combinations else "",
                     "theorie": "II. Ordnung", "alpha_cr": info.alpha_cr,
                     "alpha_cr_stab": info.alpha_cr_stab, "stab_massgebend": info.stab_massgebend,
                     "iterationen": info.iterationen, "time": time.time() - t0,
                     "factors": dict(factors), "solver": system.backend,
                     "ndof": model.ndof, "nfree": len(system.fi),
                     **ausweich_info(system, ausweich_vorher)})
    # Zug-/Druckstaebe: Theorie II. Ordnung iteriert den Ausfall nicht - ein
    # Zugstab mit Druck steht mit Namen und Kraft im Ergebnis (13.10.2026)
    from .solver import zugstaebe_pruefen
    zugstaebe_pruefen(model, res, F, aktiv, progress=progress)
    if progress:
        progress(f"{name}: Theorie II. Ordnung, {info.iterationen} Iterationen")
    return res, info


# ==========================================================================
# Ergebnisse ueber alle Kombinationen
# ==========================================================================
@dataclass
class Th2Results:
    """Sammlung der Theorie-II-Informationen aller Kombinationen."""
    kombinationen: dict = field(default_factory=dict)     # name -> Th2Info
    settings: dict = field(default_factory=dict)

    @property
    def alpha_cr_min(self) -> float:
        w = [i.alpha_cr for i in self.kombinationen.values()
             if math.isfinite(i.alpha_cr)]
        return min(w) if w else math.inf

    @property
    def einzelstab_min(self) -> tuple:
        """(alpha_cr,i, Stab, Kombination) des kleinsten Einzelstabknickens
        ueber alle Kombinationen - (inf, "", "") ohne gedrueckten Fachwerkstab."""
        best = (math.inf, "", "")
        for n, i in self.kombinationen.items():
            a = getattr(i, "alpha_cr_stab", math.inf)
            if math.isfinite(a) and a < best[0]:
                best = (a, i.stab_massgebend, n)
        return best

    @property
    def zuwachs_max(self) -> float:
        return max((i.zuwachs for i in self.kombinationen.values()), default=0.0)

    def summary(self) -> str:
        if not self.kombinationen:
            return "Theorie II. Ordnung: nicht gerechnet"
        n2 = sum(1 for i in self.kombinationen.values() if i.gerechnet)
        a = self.alpha_cr_min
        a_st, stab, _k = self.einzelstab_min
        s = (f"Theorie II. Ordnung: {n2} von {len(self.kombinationen)} Kombinationen "
             f"am verformten System")
        if math.isfinite(a_st):
            # min(System; Einzelstab) mit dem massgebenden Stab (14.10.2026)
            s += (f", min. α_cr = {min(a, a_st):.2f} (System "
                  + (f"{a:.2f}" if math.isfinite(a) else "∞")
                  + f"; Einzelstab {a_st:.2f}, Stab {stab})")
        elif math.isfinite(a):
            s += f", min. α_cr = {a:.2f}"
        if n2:
            s += f", max. Verformungszuwachs {self.zuwachs_max * 100:+.1f} %"
        fehler = [n for n, i in self.kombinationen.items() if i.fehler]
        if fehler:
            s += f" - {len(fehler)} nicht geführt: " + ", ".join(fehler)
        # Stabteilung zu grob fuer die Knickfigur (A9, 09.11.2026): nie still
        grob = next((h for i in self.kombinationen.values() for h in i.hinweise
                     if h.startswith("α_cr: Stabteilung zu grob")), "")
        if grob:
            s += f" - {grob}"
        return s

    def table(self) -> list[list]:
        rows = [["Kombination", "α_cr", "α_cr Einzelstab", "Grenze", "Verfahren", "Iterationen",
                 "u_I [mm]", "u_II [mm]", "Zuwachs"]]
        for n, i in self.kombinationen.items():
            a_st = getattr(i, "alpha_cr_stab", math.inf)
            rows.append([n, f"{i.alpha_cr:.2f}" if math.isfinite(i.alpha_cr) else "∞",
                         f"{a_st:.2f} ({i.stab_massgebend})" if math.isfinite(a_st) else "–",
                         f"{i.grenze:.0f}",
                         "II. Ordnung" if i.gerechnet else "I. Ordnung",
                         str(i.iterationen) if i.gerechnet else "-",
                         f"{i.u_max_I * 1e3:.2f}",
                         f"{i.u_max_II * 1e3:.2f}" if i.gerechnet else "-",
                         f"{i.zuwachs * 100:+.1f} %" if i.gerechnet else "-"])
        return rows


def check_theorie2(model: Model, analysis, combos: list = None, system=None,
                   progress=None, systeme: dict = None, erzwungen=None) -> Th2Results:
    """
    Alle GZT-Kombinationen nach Theorie II. Ordnung rechnen und die
    Ergebnisse der Berechnung **ersetzen**.

    ``model.design.theorie2``:
        "aus"   nichts tun
        "auto"  je Kombination alpha_cr bestimmen und nur rechnen, wenn
                alpha_cr unter der Grenze nach 5.2.1(3) liegt
        "ein"   immer am verformten System rechnen

    Eine **Ergebniskombination** (Alternativen, ``factors`` leer) wird nicht
    selbst gerechnet, sondern jede ihrer Alternativen als eigene Zeile
    "EK [k]"; die Ergebnisse gehen nach ``analysis.alternativen``, nicht nach
    ``analysis.combinations``, und solve_all faltet daraus die Umhuellende
    der EK. Vorher rechnete diese Funktion die EK mit ``factors = {}``: ein
    Nullergebnis, das als "am verformten System gerechnet" gezaehlt und in
    ``analysis.combinations`` abgelegt wurde (Befund FE12, 22.09.2026).
    Identische Alternativen mehrerer EK werden einmal gerechnet.
    """
    from dataclasses import replace
    from .solver import StaticSystem, alternativen_der_kombination
    ds = model.design
    modus = getattr(ds, "theorie2", "aus")
    out = Th2Results(settings={
        "modus": modus,
        "imperfektionen": bool(getattr(ds, "imperfektionen", True)),
        "plastisch": bool(getattr(ds, "th2_plastisch", False)),
        "grenze": 15.0 if getattr(ds, "th2_plastisch", False) else 10.0,
        "richtung": getattr(ds, "th2_richtung", None),
        "alle_vorkruemmungen": bool(getattr(ds, "th2_alle_vorkruemmungen", False)),
        "Norm": "DIN EN 1993-1-1, 5.2 und 5.3"})
    erzwungen = set(erzwungen or ())
    if modus == "aus" and not erzwungen:
        return out
    names = combos if combos is not None else [
        n for n, c in model.combinations.items() if c.is_uls]
    if modus == "aus":
        # Nur die ausdruecklich auf II. Ordnung gestellten Kombinationen
        names = [n for n in names if n in erzwungen]
        out.settings["modus"] = "je Kombination"
    if not names:
        return out
    system = system or StaticSystem(model, progress=progress)
    grenze = out.settings["grenze"]
    basis = model
    # (Zeile, Kombination, Faktoren, ist Alternative einer Ergebniskombination)
    auftraege = []
    for n in names:
        c = basis.combinations[n]
        if c.ist_umhuellende:
            auftraege += [(name, n, teile, True) for name, teile in alternativen_der_kombination(c)]
        else:
            auftraege.append((n, n, dict(c.factors), False))
    gemerkt: dict = {}
    for k, (zeile, n, faktoren, alternative) in enumerate(auftraege):
        combo = basis.combinations[n]
        # Die Kombination rechnet in ihrer Situation (eigenes Modell und System)
        sit = getattr(combo, "situation", "") or "Grundstellung"
        if systeme and sit in systeme:
            model, system = systeme[sit]
        else:
            model = basis
        if not any(f for f in faktoren.values()):
            # Nichts belastet: ein Nullergebnis waere kein Ergebnis nach II.
            # Ordnung, sondern gar keins - es bleibt beim linearen.
            info = Th2Info(kombination=zeile, grenze=grenze)
            info.hinweise.append("keine Lastfälle mit Faktor ≠ 0 – nichts am verformten "
                                 "System zu rechnen")
            out.kombinationen[zeile] = info
            continue
        schluessel = ((sit, n in erzwungen, tuple(sorted(faktoren.items())))
                      if alternative else None)
        if schluessel is not None and schluessel in gemerkt:
            res, info = gemerkt[schluessel]
            out.kombinationen[zeile] = replace(info, kombination=zeile,
                                               hinweise=list(info.hinweise))
            # die Staebe des Hinweises Biegedrillknicken sind keine Felder:
            # replace nimmt sie nicht mit (Gegenpruefung k8, 15.11.2026)
            for _attr in ("bdk_staebe", "bdk_ec3_staebe"):
                if hasattr(info, _attr):
                    setattr(out.kombinationen[zeile], _attr, list(getattr(info, _attr)))
            if res is not None and analysis is not None:
                _alternative_ablegen(analysis, zeile, res)
            continue
        if modus == "auto" and n not in (erzwungen or ()):
            # Grundzustand und alpha_cr zuerst
            from .solver import case_loads, case_prescribed, anfangsnormalkraefte
            # am intern geteilten Modell wie die Rechnung selbst (12.11.2026):
            # mit einem Element je Stab lag alpha_cr bis 22 % zu hoch, und die
            # Kombination fiel womoeglich zu Unrecht unter die Grenze
            from .stabteilung import fein_system, laengslast_hinweise, kraefte_theorie1
            fein = fein_system(model, system, faktoren)
            # Hinweis Last in Stabrichtung bei weniger als vier gerechneten
            # Elementen (Runde k7) - auch wenn nur alpha_cr bestimmt wird
            ll_hinweise = laengslast_hinweise(
                model, faktoren, getattr(system, "aktiv", None), 1,
                kraefte=lambda: kraefte_theorie1(model, system, faktoren))
            m_a, s_a = (fein[0], fein[1]) if fein is not None else (model, system)
            F, _feq, _q, _temp = case_loads(m_a, faktoren, getattr(s_a, "aktiv", None))
            from .vorspannkraft import sollkraefte
            if sollkraefte(m_a, faktoren):
                # Vorspannkraft (Sollkraft): der Grundzustand mit Spannschritt
                # und Verriegelung, N und Armanteil aus diesem Ergebnis wie im
                # Knicken (Verfahrensstand 41, 14.11.2026). Bis dahin fehlte die
                # Verriegelung hier ganz - am Zugband mit 70 kN „keine
                # Normalkräfte“, alpha_cr ∞ statt 801,6
                from .solver import _solve_loads, _anfang_im_ergebnis, _soll_endkraefte
                r_s = _solve_loads(m_a, s_a, faktoren, zeile, "combination")
                u1 = np.zeros(m_a.ndof)
                u1[:m_a.nn * 6] = np.asarray(r_s.u, float).ravel()[:m_a.nn * 6]
                ac = alpha_cr(m_a, s_a, u1,
                              n_anfang=_anfang_im_ergebnis(m_a, r_s, faktoren, getattr(s_a, "aktiv", None)),
                              feq=_feq,
                              endkraefte=_soll_endkraefte(m_a, r_s, faktoren, getattr(s_a, "aktiv", None)))
            else:
                u1 = s_a.solve(F, us=case_prescribed(m_a, faktoren))
                ac = alpha_cr(m_a, s_a, u1,
                              n_anfang=anfangsnormalkraefte(m_a, faktoren, getattr(s_a, "aktiv", None)),
                              feq=_feq)
            info = Th2Info(kombination=zeile, alpha_cr=ac["alpha_cr"], grenze=grenze,
                           u_max_I=float(np.abs(u1).max()))
            info.stab_aus(ac)
            if ac.get("fehler"):
                info.hinweise.append(ac["fehler"])
            if ac.get("hinweis_teilung"):
                info.hinweise.append(ac["hinweis_teilung"])
            info.hinweise.extend(ll_hinweise)
            if ac["alpha_cr"] >= grenze:
                # nur alpha_cr: Hinweis Biegedrillknicken wie in solve_theorie2 (Runde k8)
                from .bdk_hinweis import hinweis_th2 as bdk_hinweis, merken as bdk_merken
                bdk_merken(info, *bdk_hinweis(m_a, getattr(s_a, "aktiv", None), u=u1, feq=_feq, q=_q))
                out.kombinationen[zeile] = info
                if schluessel is not None:
                    gemerkt[schluessel] = (None, info)
                if progress:
                    progress(f"{zeile}: α_cr = {ac['alpha_cr']:.1f} ≥ {grenze:.0f} "
                             f"({k + 1}/{len(auftraege)})")
                continue
        res, info = solve_theorie2(
            model, faktoren, zeile, system,
            imperfektionen=out.settings["imperfektionen"],
            elastisch=not out.settings["plastisch"],
            richtung=out.settings["richtung"],
            alle_vorkruemmungen=out.settings["alle_vorkruemmungen"])
        info.grenze = grenze
        out.kombinationen[zeile] = info
        if alternative:
            res.info["typ"] = combo.typ
            if sit != "Grundstellung":
                res.info["situation"] = sit
        if not info.fehler and analysis is not None:
            if alternative:
                _alternative_ablegen(analysis, zeile, res)
            else:
                analysis.combinations[n] = res
        if schluessel is not None:
            gemerkt[schluessel] = (None if info.fehler else res, info)
        if progress:
            progress(f"{zeile}: Theorie II. Ordnung ({k + 1}/{len(auftraege)})")
    return out


def _alternative_ablegen(analysis, name: str, res) -> None:
    """Das Ergebnis einer Alternative "EK [k]" in ``analysis.alternativen``
    ablegen - dort sucht es die Umhuellende der EK und jeder Nachweis."""
    ablage = getattr(analysis, "alternativen", None)
    if ablage is None:
        ablage = {}
        try:
            analysis.alternativen = ablage
        except AttributeError:
            return
    ablage[name] = res
