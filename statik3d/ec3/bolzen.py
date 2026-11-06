"""Bolzennachweis nach DIN EN 1993-1-8, 3.13 (Tabelle 3.10) fuer Passstifte (06.11.2026).

Ein Stift ist im Modell ein gewoehnlicher Volumenkoerper. Nachgewiesen wird er
nur, wenn der Anwender ihn als Bolzen festgelegt hat (``Volumenkoerper.bolzen``
= {"d": Durchmesser [m], "werkstoff": Name in ``materials``, optional "fuge":
Lage der Scherfuge auf der Achse [m]}). Fehlt Durchmesser oder Werkstoff oder
ein noetiger Festigkeitswert, steht dort „Nachweis nicht geführt“ mit Grund.
Es gibt keinen Vorgabewert, und nichts wird aus Name oder Form abgeleitet.

Tragfaehigkeiten (A = pi d^2/4, W_el = pi d^3/32):

    Abscheren   F_v,Rd = 0,6 A f_up / gamma_M2,   f_up = f_u des Bolzenwerkstoffs
    Lochleibung F_b,Rd = 1,5 t d f_y / gamma_M0,   f_y = min(f_yp, f_y des Partners)
    Biegung     M_Rd   = 1,5 W_el f_yp / gamma_M0
    Wechselwirkung  (M_Ed/M_Rd)^2 + (F_v,Ed/F_v,Rd)^2 <= 1

(Das min(f_yp, f_y Partner) der Lochleibung ist aus der Erinnerung an Tab. 3.10
gesetzt und **nicht gegen den Normtext geprueft**; im Repo liegt keine Norm.)

Schnittgroessen aus dem Gleichgewicht des Bolzens (nur Lastfaelle, nicht
Kombinationen: Kontakt ueberlagert sich nicht). Die Kraft auf den Bolzen sind
die Kontaktkraefte der Rechnung (``Results.contact``, F_vek): am Slave-Knoten im
Bolzen +F, an den Master-Knoten im Bolzen -w F. Je Partnerkoerper werden sie
zusammengefasst. Die Scherfuge liegt zwischen zwei Partnern in der Mitte
zwischen dem letzten Kontaktknoten des einen und dem ersten des anderen, oder
dort, wo der Anwender ``fuge`` angibt. Die Querkraft V_Ed ist der Anteil der
Resultierenden aller Partner einer Seite quer zur Achse, M_Ed das Moment dieser
Kraefte um die Achspunkt in der Fuge, quer zur Achse (Torsion bleibt aussen).
Das Moment haengt vom Netz ab (Lage der Kontaktknoten, Mitte zwischen
Kontaktknoten); die Ausgabe kennzeichnet es so. Die Dicke t eines Partners ist
sein Anteil an der Bolzenlaenge zwischen den Scherfugen bzw. Bolzenenden.
"""
from dataclasses import dataclass, field

import numpy as np

NETZABHAENGIG = ("Das Biegemoment ist netzabhängig (Lage der Kontaktknoten, Scherfuge in der Mitte "
                 "zwischen Kontaktknoten); die Wechselwirkung ist ein Netzergebnis.")
KEIN_NACHWEIS = "Nachweis nicht geführt"


@dataclass
class BolzenCheck:
    """Bolzennachweis eines Volumenkoerpers ueber alle Lastfaelle."""
    name: str
    d: float = 0.0
    werkstoff: str = ""
    fyp: float = 0.0
    fup: float = 0.0
    util: float = 0.0
    lastfall: str = ""
    werte: dict = field(default_factory=dict)
    je_lastfall: list = field(default_factory=list)
    hinweise: list = field(default_factory=list)
    fehler: str = ""

    def zeile(self) -> str:
        if self.fehler:
            return f"Bolzen {self.name}: {KEIN_NACHWEIS} ({self.fehler})"
        w = self.werte
        t = (f"Bolzen {self.name} (Ø {self.d * 1e3:.1f} mm, {self.werkstoff}): η = {self.util:.3f} "
                f"({self.lastfall}; Abscheren {w.get('eta_v', 0):.3f}, "
                f"Lochleibung {w.get('eta_b', 0):.3f}, Biegung {w.get('eta_M', 0):.3f}, "
                f"Wechselwirkung {w.get('eta_ww', 0):.3f}; V = {w.get('V', 0) / 1e3:.1f} kN, "
                f"M = {w.get('M', 0):.1f} Nm, netzabhängig)")
        return t.replace(".", ",")


# --------------------------------------------------------------------------
# Festlegen durch den Anwender
# --------------------------------------------------------------------------
def bolzen_festlegen(model, namen, d: float, werkstoff: str, fuge=None) -> list:
    """Die Koerper ``namen`` als Bolzen festlegen. ValueError mit Grund bei
    unbekanntem Koerper oder Werkstoff oder d <= 0. Rueckgabe: Protokollzeilen."""
    if not d or float(d) <= 0.0:
        raise ValueError("Durchmesser fehlt")
    if werkstoff not in (model.materials or {}):
        raise ValueError(f"Werkstoff „{werkstoff}“ gibt es nicht")
    zeilen = []
    for n in namen:
        k = (model.koerper or {}).get(n)
        if k is None:
            raise ValueError(f"Volumen „{n}“ gibt es nicht")
    for n in namen:
        spec = {"d": float(d), "werkstoff": str(werkstoff)}
        if fuge is not None:
            spec["fuge"] = float(fuge)
        model.koerper[n].bolzen = spec
        zeilen.append(f"Bolzen {n}: Ø {float(d) * 1e3:g} mm, Werkstoff {werkstoff}")
    return zeilen


def bolzen_entfernen(model, namen) -> int:
    """Die Festlegung als Bolzen aufheben; Zahl der aufgehobenen."""
    n_ = 0
    for n in namen:
        k = (model.koerper or {}).get(n)
        if k is not None and k.bolzen:
            k.bolzen = {}
            n_ += 1
    return n_


def bolzenkoerper(model) -> dict:
    """{Name: Festlegung} der als Bolzen festgelegten Koerper."""
    return {n: dict(k.bolzen) for n, k in (getattr(model, "koerper", None) or {}).items()
            if getattr(k, "bolzen", None)}


# --------------------------------------------------------------------------
# Festigkeiten - nur was der Werkstoff selbst fuehrt
# --------------------------------------------------------------------------
def festigkeit(mat, t: float, was: str):
    """(Wert [Pa], Fehlertext) der Streckgrenze (``was`` = "fy") bzw.
    Zugfestigkeit ("fu") des Werkstoffs bei der Dicke t. Kein Vorgabewert:
    ohne Angabe im Werkstoff (Wert, Dickentabelle oder Stahlsorte) None; die
    Rueckfallregel „f_u = 1,3 f_y“ des Werkstoffs zaehlt nicht."""
    if mat is None:
        return None, "Werkstoff fehlt"
    sorte = mat._sorte()
    if was == "fy":
        if not (mat.fy_dicke or mat.fy or sorte):
            return None, f"f_y fehlt im Werkstoff {mat.name}"
        w = mat.yield_strength(t)
    else:
        if not (mat.fu_dicke or mat.fu or (sorte and not mat.fy)):
            return None, f"f_u fehlt im Werkstoff {mat.name}"
        w = mat.ultimate_strength(t)
    if not w or w <= 0:
        return None, f"{'f_y' if was == 'fy' else 'f_u'} fehlt im Werkstoff {mat.name}"
    return float(w), ""


# --------------------------------------------------------------------------
# Kraefte am Bolzen
# --------------------------------------------------------------------------
def _koerper_je_knoten(model, namen=None) -> dict:
    aus: dict = {}
    for kn, k in (model.koerper or {}).items():
        for e in (k.elemente or []):
            e = int(e)
            if 0 <= e < len(model.elements):
                for x in model.elements[e].nodes:
                    aus.setdefault(int(x), kn)
    return aus


def _achse(X: np.ndarray):
    """(Schwerpunkt, Achse a [Betrag 1, groesste Komponente positiv], s = Lage auf der Achse)."""
    c = X.mean(axis=0)
    _u, _s, vt = np.linalg.svd(X - c, full_matrices=False)
    a = vt[0]
    if a[int(np.argmax(np.abs(a)))] < 0:
        a = -a
    return c, a, (X - c) @ a


def kraefte_am_bolzen(model, res, kname: str, knoten_von: dict = None) -> dict:
    """Die Kontaktkraefte auf den Koerper ``kname``: {Partner: [(Punkt, Kraft)]}.
    Partner ist der Koerper der Gegenseite, bei Lagern „Lager“."""
    k = model.koerper[kname]
    Np = {int(x) for e in k.elemente for x in model.elements[int(e)].nodes}
    X = np.asarray(model.nodes, float)
    knoten_von = knoten_von if knoten_von is not None else _koerper_je_knoten(model)
    aus: dict = {}
    for c in (getattr(res, "contact", None) or []):
        if c.get("kind") == "dof_rot":
            continue
        F = np.asarray(c.get("F_vek", (0.0, 0.0, 0.0)), float)
        if not F.any():
            continue
        n = int(c["node"])
        master = c.get("master")
        if master is not None:
            mk = [int(x) for x in master[0]]
            mw = [float(w) for w in master[1]]
        else:
            mk, mw = [], []
        if n in Np:
            if mk and all(x in Np for x in mk):
                continue                                   # innere Bedingung des Bolzens selbst
            partner = knoten_von.get(mk[0], "?") if mk else "Lager"
            aus.setdefault(partner, []).append((X[n], F))
        for x, w in zip(mk, mw):
            if x in Np and n not in Np:
                aus.setdefault(knoten_von.get(n, "?"), []).append((X[x], -w * F))
    return aus


def _quer(v: np.ndarray, a: np.ndarray) -> np.ndarray:
    return v - float(v @ a) * a


def bolzen_lastfall(model, res, kname: str, spec: dict, mat, ds, knoten_von: dict = None) -> dict:
    """Der Bolzennachweis eines Koerpers fuer ein Ergebnis. Rueckgabe: Woerterbuch
    mit ``fehler`` (leer = gefuehrt) oder den Werten (V, M, eta_*, partner ...)."""
    d = float(spec["d"])
    A = np.pi * d * d / 4.0
    W = np.pi * d ** 3 / 32.0
    fyp, f1 = festigkeit(mat, d, "fy")
    fup, f2 = festigkeit(mat, d, "fu")
    if fyp is None or fup is None:
        return {"fehler": f1 or f2}
    k = model.koerper[kname]
    X = np.asarray(model.nodes, float)
    Np = sorted({int(x) for e in k.elemente for x in model.elements[int(e)].nodes})
    if len(Np) < 4:
        return {"fehler": "Körper ohne Netz"}
    c0, a, s_all = _achse(X[Np])
    s0, s1 = float(s_all.min()), float(s_all.max())
    senkrecht = np.linalg.norm((X[Np] - c0) - np.outer(s_all, a), axis=1)
    d_mess = 2.0 * float(senkrecht.max())
    hinweise = []
    if abs(d_mess - d) > 0.1 * d:
        hinweise.append(f"gemessener Durchmesser {d_mess * 1e3:.1f} mm weicht vom angegebenen "
                        f"{d * 1e3:.1f} mm ab (gerechnet mit dem angegebenen)")
    teile = kraefte_am_bolzen(model, res, kname, knoten_von)
    if not teile:
        return {"fehler": "keine Kontaktkraft am Körper (Lastfall ohne Kontaktergebnis)"}
    summe = np.zeros(3)
    ein = {}
    for p, liste in teile.items():
        R = sum((F for _x, F in liste), np.zeros(3))
        summe += R
        s = np.array([float((x - c0) @ a) for x, _F in liste])
        ein[p] = {"R": R, "smin": float(s.min()), "smax": float(s.max()),
                  "smitte": float(np.average(s, weights=[np.linalg.norm(F) + 1e-30 for _x, F in liste]))}
    gross = max(np.linalg.norm(_quer(e["R"], a)) for e in ein.values())
    reihe = sorted((p for p in ein if np.linalg.norm(_quer(ein[p]["R"], a)) >= 1e-3 * max(gross, 1e-30)),
                   key=lambda p: ein[p]["smitte"])
    if len(reihe) < 2 and "fuge" not in spec:
        return {"fehler": "nur ein Partner trägt Kraft ein - die Scherfuge ist nicht eindeutig; "
                          "Lage der Scherfuge angeben"}
    ebenen = []
    if "fuge" in spec:
        ebenen = [float(spec["fuge"]) + s0]
    else:
        for p, q in zip(reihe[:-1], reihe[1:]):
            if ein[p]["smax"] > ein[q]["smin"] + 1e-9:
                return {"fehler": f"die Kontaktbereiche von {p} und {q} überlappen auf der Achse - "
                                  "Lage der Scherfuge angeben"}
            ebenen.append(0.5 * (ein[p]["smax"] + ein[q]["smin"]))
    # Zellen der Partner: Bolzenlaenge zwischen den Ebenen
    grenzen = [s0] + ebenen + [s1]
    FvRd = 0.6 * A * fup / ds.gamma_M2
    MRd = 1.5 * W * fyp / ds.gamma_M0
    fugen = []
    for j, sf in enumerate(ebenen):
        xf = c0 + a * sf
        V = 0.0
        M = 0.0
        unten = np.zeros(3)
        mom = np.zeros(3)
        for p, liste in teile.items():
            for x, F in liste:
                if float((x - c0) @ a) <= sf:
                    unten += F
                    mom += np.cross(x - xf, F)
        V = float(np.linalg.norm(_quer(unten, a)))
        M = float(np.linalg.norm(_quer(mom, a)))
        eta_v = V / FvRd
        eta_M = M / MRd
        fugen.append({"s": sf - s0, "V": V, "M": M, "eta_v": eta_v, "eta_M": eta_M,
                      "eta_ww": eta_M ** 2 + eta_v ** 2, "F_vRd": FvRd, "M_Rd": MRd})
    # Lochleibung je Partner
    from ..scheibeneinleitung import dicke_koerper
    partner = []
    for p in reihe:
        i = reihe.index(p)
        t = grenzen[i + 1] - grenzen[i] if len(grenzen) - 1 == len(reihe) else s1 - s0
        F_b = float(np.linalg.norm(_quer(ein[p]["R"], a)))
        zeile = {"name": p, "F": F_b, "t": t}
        kp = (model.koerper or {}).get(p)
        mp = (model.materials or {}).get(getattr(kp, "material", "")) if kp is not None else None
        fyb, grund = festigkeit(mp, dicke_koerper(model, p) or 0.0, "fy") if kp is not None else (None, "Lager")
        if fyb is None:
            zeile["fehler"] = f"Lochleibung an {p} nicht geführt: {grund or 'kein Körper'}"
        else:
            fy = min(fyp, fyb)
            Fb = 1.5 * t * d * fy / ds.gamma_M0
            zeile.update(fy=fy, F_bRd=Fb, eta_b=F_b / Fb)
        partner.append(zeile)
    eta_b = max((z.get("eta_b", 0.0) for z in partner), default=0.0)
    f0 = max(fugen, key=lambda f: f["eta_v"] + f["eta_M"])
    abw = float(np.linalg.norm(summe))
    if abw > 0.05 * max(f0["V"], 1e-30):
        hinweise.append(f"Gleichgewicht der Kontaktkräfte am Bolzen nicht erfüllt (Rest {abw / 1e3:.2f} kN "
                        f"gegen V = {f0['V'] / 1e3:.2f} kN): es wirken Kräfte, die nicht über Kontakt "
                        "kommen (Lasten, Verbund, starre Kopplung)")
    eta_ww = f0["eta_ww"]
    return {"fehler": "", "V": f0["V"], "M": f0["M"], "eta_v": f0["eta_v"], "eta_M": f0["eta_M"],
            "eta_ww": eta_ww, "eta_b": eta_b, "F_vRd": FvRd, "M_Rd": MRd, "fugen": fugen,
            "partner": partner, "gleichgewicht_rest": abw, "hinweise": hinweise,
            "util": max(f0["eta_v"], eta_b, f0["eta_M"], eta_ww), "fyp": fyp, "fup": fup,
            "achse": a.tolist(), "gemessen_d": d_mess}


def check_bolzen(model, analysis) -> dict:
    """Alle als Bolzen festgelegten Koerper ueber alle Lastfaelle:
    {Name: BolzenCheck}. Kombinationen zaehlen nicht (Kontakt ueberlagert sich
    nicht)."""
    out: dict = {}
    spec_je = bolzenkoerper(model)
    if not spec_je:
        return out
    ds = model.design
    knoten_von = _koerper_je_knoten(model)
    faelle = dict(getattr(analysis, "cases", None) or {})
    for name, spec in spec_je.items():
        c = BolzenCheck(name, d=float(spec.get("d") or 0.0), werkstoff=str(spec.get("werkstoff") or ""))
        out[name] = c
        if c.d <= 0.0:
            c.fehler = "Durchmesser nicht angegeben"
            continue
        mat = (model.materials or {}).get(c.werkstoff)
        if not c.werkstoff or mat is None:
            c.fehler = "Werkstoff nicht angegeben" if not c.werkstoff else f"Werkstoff „{c.werkstoff}“ gibt es nicht"
            continue
        k = (model.koerper or {}).get(name)
        if k is None or not k.elemente:
            c.fehler = "Körper ohne Netz"
            continue
        letzter = ""
        for lf, res in faelle.items():
            if res is None or not getattr(res, "contact", None):
                letzter = f"{lf}: kein Kontaktergebnis"
                continue
            w = bolzen_lastfall(model, res, name, spec, mat, ds, knoten_von)
            if w["fehler"]:
                letzter = f"{lf}: {w['fehler']}"
                c.fyp, c.fup = w.get("fyp", c.fyp), w.get("fup", c.fup)
                if "f_y fehlt" in w["fehler"] or "f_u fehlt" in w["fehler"]:
                    c.fehler = w["fehler"]
                    break
                continue
            w["lastfall"] = lf
            c.fyp, c.fup = w["fyp"], w["fup"]
            c.je_lastfall.append(w)
        if c.fehler:
            continue
        if not c.je_lastfall:
            c.fehler = letzter or "kein Lastfall im Ergebnis"
            continue
        m = max(c.je_lastfall, key=lambda w: w["util"])
        c.util, c.lastfall, c.werte = m["util"], m["lastfall"], m
        c.hinweise = [NETZABHAENGIG] + list(dict.fromkeys(h for w in c.je_lastfall for h in w["hinweise"]))
    return out


def zeilen(bolzen: dict) -> list:
    """Die Zeilen fuer die Ausgabe des Volumennachweises."""
    return [c.zeile() for c in (bolzen or {}).values()]
