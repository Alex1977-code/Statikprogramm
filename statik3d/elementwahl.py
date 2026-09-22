"""
Elementwahl je Koerper: wo braucht es den quadratischen Tetraeder?

Der Wunsch des Anwenders vom 20.09.2026: "um rechenzeit zu sparen soll
erkannt werden ob biegung benoetigt wird und danach soll die berechnung
angepasst werden." Seit dem 22.09.2026 (Auftrag B2 an die Element-Sitzung):
**tet10 an den Nachweisstellen, tet4 sonst.** Dieses Modul schlaegt die
Ordnung je Koerper vor, aus einem Vorlauf mit dem vorhandenen Netz.

Warum nicht ueberall tet10: er macht die Matrix in den Koerpern groesser und
dichter, und die Faktorisierung ist der groesste Posten der Rechenzeit. Warum
nicht ueberall tet4: der lineare Tetraeder konvergiert in der Spannung nur
mit O(h) (Kragarm-Pruefkoerper, 22.09.2026: -266 / -166 / -70 N/mm2 bei 90 /
405 / 2295 FHG gegen den Sollwert 355), der tet10 mit O(h^2) (+14 / +4 / +1
bei 405 / 2295 / 15147). 1 N/mm2 erreicht der tet4 dort praktisch nicht.

Ein Koerper bekommt tet10, wenn

  (a) an ihm ein Nachweis gefuehrt wird (ein Volumenbereich mit Nachweis
      enthaelt Elemente von ihm) - sonst zaehlt dort nur die Steifigkeit, und
  (b) der Vorlauf es verlangt: der Fehlerschaetzer (Zienkiewicz/Zhu,
      netzfehler.indikator) zeigt fuer den Koerper mehr als ``ziel``
      bezogenen Fehler, **oder** der Koerper wird gebogen - die Normalspannung
      in seiner Hauptrichtung wechselt ueber ihn das Vorzeichen mit
      vergleichbarem Betrag (Biegeanteil beta, siehe :func:`biegeanteil`).

Der Anwender kann je Koerper uebersteuern (``Volumenkoerper.ordnung`` = 1
oder 2, wenn das Modell das Feld fuehrt). Das Protokoll nennt je Koerper
Ordnung und Grund (:func:`protokoll`).

Wie der Koerper dann vernetzt wird (Seitenmitten auf der wahren Geometrie),
ist Sache des Vernetzers; :func:`tet4_zu_tet10` macht es fuer Pruefkoerper
mit geraden Kanten. An der Grenze zu einem tet4-Koerper bindet die
Assemblierung die Seitenmitten (assemble.mittelknoten_bindungen).
"""
from __future__ import annotations

import numpy as np

#: Biegeanteil, ab dem ein Koerper als gebogen gilt: der kleinere der beiden
#: Betraege (groesste Zug-, groesste Druckspannung in der Hauptrichtung)
#: bezogen auf den groesseren. Reine Biegung 1, reiner Zug 0; am Kragarm-
#: Pruefkoerper (Querkraft am Ende, tet4-Vorlauf 8x2x4) 0,85, am gezogenen
#: Stab 0,00 (gemessen 22.09.2026, tests/test_elementwahl.py).
BIEGUNG_AB = 0.3
#: Bezogener Fehler (Energienorm) des Koerpers, ab dem der Vorlauf tet10
#: verlangt - das Ziel des Fehlerschaetzers (netzfehler.ZIEL).
FEHLER_AB = 0.05


def koerper_je_element(model) -> dict:
    """{Element: Koerpername} der Volumenelemente (Element.group)."""
    from . import elemente as EL
    vol = set(EL.VOLUMEN_TYPEN)
    return {i: str(getattr(e, "group", "")) for i, e in enumerate(model.elements) if e.typ in vol}


def koerper_mit_nachweis(model) -> set:
    """Die Koerper, an denen ein Volumennachweis gefuehrt wird."""
    kj = koerper_je_element(model)
    aus = set()
    for vb in (getattr(model, "volumenbereiche", None) or {}).values():
        if not getattr(vb, "design", True):
            continue
        for i in vb.elemente:
            k = kj.get(int(i))
            if k is not None:
                aus.add(k)
    return aus


def biegeanteil(model, res, elemente) -> float:
    """Wie stark wird der Koerper gebogen? 0 = gar nicht, 1 = reine Biegung.

    Hauptrichtung d: die Richtung der betragsgroessten Hauptspannung im
    Element mit der groessten Vergleichsspannung. sigma_dd = d^T sigma d je
    Element (Elementmittel solid_mittel, sonst solid_res). Biegung heisst:
    sigma_dd wechselt ueber den Koerper das Vorzeichen, und die Zugseite ist
    so gross wie die Druckseite - beta = min(max, -min) / max(|sigma_dd|).
    Ein gezogener Stab hat beta = 0, ein gebogener Balken nahe 1; eine
    einseitige Querkraft im Zugstab (Biegung mit Normalkraft) liegt dazwischen.
    """
    quelle = getattr(res, "solid_mittel", None) or res.solid_res
    S = [np.asarray(quelle[i], float) for i in elemente if i in quelle]
    if not S:
        return 0.0
    S = np.array(S)
    from .elements import solid as sl
    sv = np.array([sl.von_mises(s) for s in S])
    j = int(np.argmax(sv))
    T = np.array([[S[j, 0], S[j, 3], S[j, 5]], [S[j, 3], S[j, 1], S[j, 4]],
                  [S[j, 5], S[j, 4], S[j, 2]]])
    w, v = np.linalg.eigh(T)
    d = v[:, int(np.argmax(np.abs(w)))]
    sdd = (S[:, 0] * d[0] ** 2 + S[:, 1] * d[1] ** 2 + S[:, 2] * d[2] ** 2
           + 2 * S[:, 3] * d[0] * d[1] + 2 * S[:, 4] * d[1] * d[2] + 2 * S[:, 5] * d[0] * d[2])
    groesst = float(np.abs(sdd).max())
    if groesst <= 0.0:
        return 0.0
    return float(min(max(sdd.max(), 0.0), max(-sdd.min(), 0.0)) / groesst)


def fehler_je_koerper(model, ergebnisse) -> dict:
    """{Koerper: bezogener Fehler (Energienorm)} aus netzfehler.indikator."""
    from . import netzfehler
    ind = netzfehler.indikator(model, ergebnisse)
    if not ind.get("N"):
        return {}
    kj = koerper_je_element(model)
    eta2: dict = {}
    for i, e in zip(ind["ids"], ind["eta"]):
        k = kj.get(int(i), "")
        eta2[k] = eta2.get(k, 0.0) + float(e) ** 2
    # Energie der Loesung je Koerper aus der Elementspannung: U^2 = V s^T C s
    from .elements import solid as sl
    liste = ergebnisse if isinstance(ergebnisse, (list, tuple)) else [ergebnisse]
    res = liste[0]
    quelle = getattr(res, "solid_mittel", None) or res.solid_res
    U2: dict = {}
    for i, k in kj.items():
        if i not in quelle:
            continue
        e = model.elements[i]
        mat = model.materials[e.mat]
        s = np.asarray(quelle[i], float)
        C = np.linalg.inv(sl.D_matrix(mat.E, mat.nu))
        V = sl.solid_volume(e.typ, model.nodes[e.nodes])
        U2[k] = U2.get(k, 0.0) + V * float(s @ C @ s)
    return {k: float(np.sqrt(eta2[k] / (U2.get(k, 0.0) + eta2[k]))) if eta2[k] > 0 else 0.0
            for k in eta2}


def vorschlag(model, ergebnisse, biegung_ab: float = BIEGUNG_AB,
              fehler_ab: float = FEHLER_AB) -> dict:
    """{Koerper: {"ordnung", "grund", "biegung", "fehler", "nachweis"}} aus
    einem Vorlauf (``ergebnisse``: ein Results oder eine Liste). Nur Koerper
    aus Tetraedern werden vorgeschlagen; Sechsflaechner-Koerper (Sweep)
    bleiben, was sie sind."""
    liste = ergebnisse if isinstance(ergebnisse, (list, tuple)) else [ergebnisse]
    kj = koerper_je_element(model)
    je_koerper: dict = {}
    for i, k in kj.items():
        je_koerper.setdefault(k, []).append(i)
    mit_nachweis = koerper_mit_nachweis(model)
    fehler = fehler_je_koerper(model, list(liste))
    vorgaben = {}
    for name, vk in (getattr(model, "koerper", None) or {}).items():
        o = getattr(vk, "ordnung", None)
        if o in (1, 2):
            vorgaben[str(name)] = int(o)
    aus = {}
    for k, els in sorted(je_koerper.items()):
        typen = {model.elements[i].typ for i in els}
        if not typen <= {"tet4", "tet10"}:
            continue
        beta = max(biegeanteil(model, r, els) for r in liste)
        f = float(fehler.get(k, 0.0))
        nachweis = k in mit_nachweis
        if k in vorgaben:
            ordnung, grund = vorgaben[k], "vom Anwender vorgegeben"
        elif not nachweis:
            ordnung, grund = 1, "kein Nachweis am Körper - dort zählt die Steifigkeit"
        elif beta >= biegung_ab:
            ordnung, grund = 2, f"Nachweis und Biegung (Biegeanteil {beta:.2f})"
        elif f >= fehler_ab:
            ordnung, grund = 2, f"Nachweis und Fehlerschätzer {f * 100:.1f} % ≥ {fehler_ab * 100:.0f} %"
        else:
            ordnung, grund = 1, (f"Nachweis, aber ohne Biegung (Biegeanteil {beta:.2f}) und "
                                 f"Fehler {f * 100:.1f} % < {fehler_ab * 100:.0f} %")
        aus[k] = {"ordnung": ordnung, "grund": grund, "biegung": beta, "fehler": f,
                  "nachweis": nachweis, "elemente": len(els)}
    return aus


def protokoll(vorschlag_: dict) -> list:
    """Eine Zeile je Koerper: Ordnung und Grund."""
    return [f"Elementwahl {k}: {'tet10' if v['ordnung'] == 2 else 'tet4'} - {v['grund']} "
            f"({v['elemente']} Elemente)" for k, v in vorschlag_.items()]


def tet4_zu_tet10(model, koerper=None) -> int:
    """tet4 der Koerper (alle, wenn None) zu tet10 mit Kantenmitten auf
    **geraden** Kanten; gemeinsame Kanten bekommen denselben Mittelknoten.
    Fuer Pruefkoerper und Messungen - am Bauteil setzt der Vernetzer die
    Seitenmitten auf die wahre Geometrie. Rueckgabe: neue Knoten."""
    kanten = [(0, 1), (1, 2), (0, 2), (0, 3), (1, 3), (2, 3)]
    mitten: dict = {}
    neu = []
    X = np.asarray(model.nodes, float)
    zahl = model.nn
    for e in model.elements:
        if e.typ != "tet4" or (koerper is not None and e.group not in koerper):
            continue
        kn = [int(n) for n in e.nodes]
        for a, b in kanten:
            key = (min(kn[a], kn[b]), max(kn[a], kn[b]))
            if key not in mitten:
                mitten[key] = zahl
                neu.append(0.5 * (X[kn[a]] + X[kn[b]]))
                zahl += 1
        e.nodes = kn + [mitten[(min(kn[a], kn[b]), max(kn[a], kn[b]))] for a, b in kanten]
        e.typ = "tet10"
    if neu:
        model.nodes = np.vstack([X, np.asarray(neu)])
        # Ein Mittelknoten zwischen zwei gleich gelagerten Ecken ist ebenso
        # gelagert (Einspannung einer Seite), vorgegebene Werte gemittelt
        from .model import Support
        lager: dict = {}
        for sp in model.supports:
            if sp.stiffness is None and not sp.behaviour:
                lager.setdefault(int(sp.node), []).append(sp)
        for (a, b), m in mitten.items():
            for sa in lager.get(a, []):
                treffer = [sb for sb in lager.get(b, []) if list(sb.dofs) == list(sa.dofs)]
                if treffer:
                    va = sa.values or [0.0] * len(sa.dofs)
                    vb = treffer[0].values or [0.0] * len(sa.dofs)
                    werte = [0.5 * (x + y) for x, y in zip(va, vb)]
                    model.supports.append(Support(int(m), list(sa.dofs),
                                                  werte if any(werte) else None))
                    break
    return len(neu)
