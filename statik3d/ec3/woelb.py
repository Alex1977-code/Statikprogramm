"""
Woelbkrafttorsion offener Querschnitte (DIN EN 1993-1-1, 6.2.7).

Ein offener duennwandiger Querschnitt - ein I-Traeger, ein U-Profil - traegt
Torsion auf zwei Wegen zugleich:

* **St.-Venant-Torsion** ``M_t,v = G I_t theta'``: reine Schubspannungen ueber
  die Wanddicke, die Querschnitte verwoelben sich frei.
* **Woelbkrafttorsion** ``M_t,w = -E I_w theta'''``: wird das Verwoelben
  behindert - an einer Einspannung, an einer Stirnplatte, an einer
  Querschnittsaenderung -, entstehen **Normalspannungen**. Ihr Mass ist das
  **Woelbbimoment** ``B = -E I_w theta''``.

Beides zusammen ergibt das Torsionsmoment::

    M_t = M_t,v + M_t,w = G I_t theta' - E I_w theta'''

Bei einem I-Traeger ist I_t klein und I_w gross; ein solcher Traeger traegt
Torsion an einer Woelbeinspannung fast vollstaendig ueber Woelbkrafttorsion.
Rechnet man nur mit I_t, kommt eine Verdrehung heraus, die um ein Vielfaches
zu gross ist - und die Woelbnormalspannung, die den Nachweis oft bestimmt,
fehlt ganz.

Wie hier gerechnet wird
-----------------------

Das Stabelement des Programms kennt sechs Freiheitsgrade je Knoten und damit
nur die St.-Venant-Torsion. Der Verlauf ``M_t(x)`` aus der Rechnung ist
trotzdem richtig, solange der Torsionsweg **statisch bestimmt** ist - er folgt
dann allein aus dem Gleichgewicht. Auf diesem ``M_t(x)`` wird die
Differentialgleichung der Woelbkrafttorsion geschlossen geloest und der
Momentenanteil aufgeteilt.

Mit ``psi = theta'`` und ``lambda^2 = G I_t /(E I_w)`` wird aus der Gleichung
oben::

    psi'' - lambda^2 psi = -M_t(x) /(E I_w)

Die Loesung ist die Summe aus dem St.-Venant-Anteil und zwei Randschichten::

    psi(x) = M_t(x) /(G I_t) + P exp(-lambda x) + Q exp(-lambda (L - x))

Diese Schreibweise ist **numerisch stabil**: beide Exponentialglieder sind
hoechstens 1, waehrend ``cosh(lambda L)`` bei langen Traegern ueberlaeuft.
Daraus::

    M_t,v = G I_t psi
    M_t,w = M_t - M_t,v = -G I_t (P e^{-lambda x} + Q e^{-lambda (L-x)})
    B     = -E I_w psi' = -T1/lambda^2
            + (G I_t/lambda)(P e^{-lambda x} - Q e^{-lambda (L-x)})

Die beiden Konstanten kommen aus den Randbedingungen an den Stabenden:

===============  ==========================================
Rand             Bedingung
===============  ==========================================
``frei``         B = 0 (Gabellagerung, freies Ende)
``behindert``    psi = theta' = 0 (Einspannung, Stirnplatte)
===============  ==========================================

Sind beide Enden frei und ist ``M_t`` konstant, kommt P = Q = 0 heraus: dann
gibt es keine Woelbkrafttorsion, und das ist auch richtig so.

**Grenze.** Ist der Torsionsweg statisch unbestimmt, verteilt die
Woelbsteifigkeit die Torsionsmomente anders auf die Staebe, als die Rechnung
mit sechs Freiheitsgraden es tut. Der Anteil je Stab ist dann eine Naeherung;
das wird gemeldet und steht im Bericht.

Spannungen
----------

Aus B und M_t,w folgen mit den **Woelbordinaten** des Querschnitts::

    sigma_w = B omega / I_w                (Woelbnormalspannung)
    tau_w   = M_t,w S_omega /(I_w t)       (Woelbschubspannung)
    tau_t   = M_t,v t / I_t                (St.-Venant-Schub, offener QS)

Die Woelbordinaten sind fuer das I- und das U-Profil geschlossen angeschrieben
(:func:`sektorwerte`); ihre Richtigkeit ist daran zu pruefen, dass
``I_w = integral omega^2 t ds`` denselben Wert ergibt wie die
Querschnittstabelle - das prueft :mod:`tests.test_woelb` nach.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..model import Section

#: Randbedingungen der Verwoelbung an einem Stabende
RAENDER = ("frei", "behindert")


@dataclass
class Sektorwerte:
    """Woelbordinaten eines Querschnitts.

    omega_max:  groesste Woelbordinate [m^2] - dort ist sigma_w am groessten
    S_max:      groesstes Woelbflaechenmoment [m^4] mit der Wanddicke t dort
    t_S:        Wanddicke an der Stelle von S_max [m]
    ort_omega:  wo omega_max auftritt (Klartext fuer den Bericht)
    ort_S:      wo S_max auftritt
    """
    omega_max: float = 0.0
    S_max: float = 0.0
    t_S: float = 0.0
    ort_omega: str = ""
    ort_S: str = ""
    Iw_probe: float = 0.0        # aus den Ordinaten zurueckgerechnetes I_w


def sektorwerte(sec: Section) -> Sektorwerte | None:
    """Woelbordinaten fuer I- und U-Profile - sonst None.

    **I-Profil** (doppeltsymmetrisch, Schubmittelpunkt = Schwerpunkt): der Steg
    liegt auf der Achse durch den Pol, seine Woelbordinate ist null; die
    Flansche verwoelben sich gegenlaeufig.

        omega = (h_m/2)(y - b/2),  omega_max = h_m b/4
        S_omega am Steganschluss  = t_f h_m b^2/16

    **U-Profil**: der Schubmittelpunkt liegt um e neben dem Steg,

        e = 3 t_f b^2 /(6 t_f b + h_m t_w)

    Dadurch verwoelbt sich auch der Steg. Groesste Woelbordinate ist die am
    Flanschende oder am Steg, groesstes Woelbflaechenmoment liegt in Stegmitte.
    """
    h, b, tw, tf = sec.h, sec.b, sec.tw, sec.tf
    if sec.Iw <= 0 or min(h, b, tw, tf) <= 0:
        return None
    hm = h - tf                          # Abstand der Flanschmitten
    if sec.typ == "I":
        a = hm / 2.0
        omega = a * b / 2.0
        S = tf * hm * b ** 2 / 16.0
        # Probe: I_w = 2 * integral_0^b omega(y)^2 t_f dy  (der Steg traegt nichts)
        Iw = 2 * tf * a ** 2 * (b ** 3 / 12.0)
        return Sektorwerte(omega, S, tf, "Flanschende", "Flansch am Steg", Iw)
    if sec.typ == "U":
        a = hm / 2.0
        e = 3.0 * tf * b ** 2 / (6.0 * tf * b + hm * tw)
        omega = a * max(e, b - e)
        ort = "Flanschende" if b - e >= e else "Steg (Flanschhöhe)"
        # S_omega: vom Flanschende her aufsummiert, dann durch den halben Steg
        S_flansch = tf * a * (e ** 2 - (b - e) ** 2) / 2.0
        S_steg = S_flansch - e * tw * hm ** 2 / 8.0
        if abs(S_steg) / tw >= abs(S_flansch) / tf:
            S, t_S, ort_S = abs(S_steg), tw, "Stegmitte"
        else:
            S, t_S, ort_S = abs(S_flansch), tf, "Flansch am Steg"
        Iw = (e ** 2 * tw * hm ** 3 / 12.0
              + 2 * tf * a ** 2 * ((b - e) ** 3 + e ** 3) / 3.0)
        return Sektorwerte(omega, S, t_S, ort, ort_S, Iw)
    return None


@dataclass
class Torsionsverlauf:
    """Aufteilung des Torsionsmoments ueber die Stablaenge."""
    x: np.ndarray = field(default_factory=lambda: np.zeros(0))
    Mt: np.ndarray = field(default_factory=lambda: np.zeros(0))
    Mtv: np.ndarray = field(default_factory=lambda: np.zeros(0))
    Mtw: np.ndarray = field(default_factory=lambda: np.zeros(0))
    B: np.ndarray = field(default_factory=lambda: np.zeros(0))
    theta_strich: np.ndarray = field(default_factory=lambda: np.zeros(0))
    lam: float = 0.0
    lamL: float = 0.0
    rand: tuple = ("frei", "frei")
    hinweis: str = ""

    @property
    def B_max(self) -> float:
        return float(np.abs(self.B).max()) if len(self.B) else 0.0

    @property
    def anteil_woelb(self) -> float:
        """Groesster Anteil der Woelbkrafttorsion am Torsionsmoment [0..1]."""
        nenner = float(np.abs(self.Mt).max())
        if nenner <= 0:
            return 0.0
        return float(np.abs(self.Mtw).max()) / nenner


def torsionsverlauf(L: float, It: float, Iw: float, E: float, G: float,
                    x: np.ndarray, Mt: np.ndarray,
                    rand: tuple = ("frei", "frei")) -> Torsionsverlauf:
    """Das Torsionsmoment in St.-Venant- und Woelbanteil aufteilen.

    ``Mt`` wird als linear ueber die Stablaenge angenommen - das trifft alles,
    was aus Endmomenten und einer gleichmaessigen Streckentorsion entsteht, und
    damit den Regelfall. Aus den Stuetzstellen wird die Gerade im Sinne der
    kleinsten Quadrate gezogen; ist ``Mt`` schon linear, ist sie exakt.
    """
    x = np.asarray(x, float)
    Mt = np.asarray(Mt, float)
    out = Torsionsverlauf(x=x, Mt=Mt, rand=tuple(rand))
    if L <= 0 or len(x) == 0:
        return out
    # Gerade durch die Stuetzstellen: T0 + T1 x
    if len(x) > 1 and np.ptp(x) > 0:
        T1, T0 = np.polyfit(x, Mt, 1)
        # Ist M_t nicht linear - etwa weil im Feld ein Torsionsmoment
        # eingeleitet wird und der Verlauf springt -, ist die Gerade eine
        # Naeherung. Das muss gesagt werden, sonst steht im Statikdokument
        # eine Zahl, die niemand nachrechnen kann.
        rest = float(np.abs(Mt - (T0 + T1 * x)).max())
        gross = float(np.abs(Mt).max())
        if gross > 0 and rest > 0.02 * gross:
            out.hinweis = (f"M_t verläuft nicht linear (Abweichung von der "
                           f"Geraden {100 * rest / gross:.1f} %) – vermutlich "
                           "wird im Feld ein Torsionsmoment eingeleitet. Die "
                           "Aufteilung ist dann eine Näherung; für den genauen "
                           "Verlauf den Stab an der Einleitungsstelle teilen.")
    else:
        T0, T1 = float(Mt[0]), 0.0
    if Iw <= 0 or E <= 0:
        # Kein Woelbwiderstand: alles ueber St.-Venant.
        out.Mtv = Mt.copy()
        out.Mtw = np.zeros_like(Mt)
        out.B = np.zeros_like(Mt)
        out.theta_strich = Mt / (G * It) if G * It > 0 else np.zeros_like(Mt)
        out.hinweis = (out.hinweis + " " if out.hinweis else "") + \
            "kein Wölbwiderstand (I_w = 0) – reine St.-Venant-Torsion"
        return out
    if G * It <= 0:
        # Reine Woelbkrafttorsion: psi'' = -Mt/(E Iw), Polynomloesung
        return _reine_woelbtorsion(L, Iw, E, x, T0, T1, rand, Mt, out)

    lam = float(np.sqrt(G * It / (E * Iw)))
    out.lam = lam
    out.lamL = lam * L
    s = float(np.exp(-lam * L))
    GIt = G * It
    # Randbedingungen -> 2x2-System fuer P und Q
    A = np.zeros((2, 2))
    r = np.zeros(2)
    for k, (ende, wo) in enumerate(zip(rand, (0.0, L))):
        if ende == "behindert":                 # psi = 0
            A[k] = [np.exp(-lam * wo), np.exp(-lam * (L - wo))]
            r[k] = -(T0 + T1 * wo) / GIt
        else:                                   # B = 0
            A[k] = [np.exp(-lam * wo), -np.exp(-lam * (L - wo))]
            r[k] = T1 / (lam * GIt)
    try:
        P, Q = np.linalg.solve(A, r)
    except np.linalg.LinAlgError:
        P = Q = 0.0
        out.hinweis = ("die Randbedingungen der Verwölbung sind nicht "
                       "auflösbar – gerechnet wird ohne Wölbkrafttorsion")
    ex0 = np.exp(-lam * x)
    exL = np.exp(-lam * (L - x))
    rand_teil = P * ex0 + Q * exL
    out.theta_strich = (T0 + T1 * x) / GIt + rand_teil
    out.Mtv = GIt * out.theta_strich
    out.Mtw = Mt - out.Mtv
    out.B = -T1 / lam ** 2 + (GIt / lam) * (P * ex0 - Q * exL)
    return out


def _reine_woelbtorsion(L, Iw, E, x, T0, T1, rand, Mt, out) -> Torsionsverlauf:
    """Grenzfall I_t = 0: das ganze Moment laeuft ueber die Woelbkrafttorsion.

    Dann ist ``-E I_w psi'' = M_t`` und die Loesung ein Polynom. Die beiden
    Konstanten folgen wieder aus den Randbedingungen.
    """
    EIw = E * Iw
    # psi = -(T0 x^2/2 + T1 x^3/6)/EIw + a + b x ; B = -EIw psi'
    #     B = (T0 x + T1 x^2/2) - EIw * b
    A = np.zeros((2, 2))
    r = np.zeros(2)
    for k, (ende, wo) in enumerate(zip(rand, (0.0, L))):
        if ende == "behindert":                 # psi = 0
            A[k] = [1.0, wo]
            r[k] = (T0 * wo ** 2 / 2 + T1 * wo ** 3 / 6) / EIw
        else:                                   # B = 0
            A[k] = [0.0, -EIw]
            r[k] = -(T0 * wo + T1 * wo ** 2 / 2)
    try:
        a, b = np.linalg.solve(A, r)
    except np.linalg.LinAlgError:
        a = b = 0.0
        out.hinweis = ("bei I_t = 0 müssen die Enden verschieden gelagert "
                       "sein – gerechnet wird ohne Wölbkrafttorsion")
    out.theta_strich = -(T0 * x ** 2 / 2 + T1 * x ** 3 / 6) / EIw + a + b * x
    out.Mtv = np.zeros_like(x)
    out.Mtw = Mt.copy()
    out.B = (T0 * x + T1 * x ** 2 / 2) - EIw * b
    out.hinweis = out.hinweis or "I_t = 0 – reine Wölbkrafttorsion"
    return out


def spannungen(sec: Section, B: np.ndarray, Mtw: np.ndarray,
               Mtv: np.ndarray) -> dict:
    """sigma_w, tau_w und tau_t aus Bimoment und Momentenanteilen.

    Ohne bekannte Woelbordinaten (weder I- noch U-Profil) bleiben sigma_w und
    tau_w leer; das ist besser als eine geratene Zahl im Statikdokument.
    """
    sw = sektorwerte(sec)
    tmax = sec.t_max if sec.t_max > 0 else max(sec.tf, sec.tw)
    tau_t = np.abs(Mtv) * tmax / sec.It if sec.It > 0 else np.zeros_like(Mtv)
    if sw is None or sec.Iw <= 0:
        return {"sigma_w": None, "tau_w": None, "tau_t": tau_t, "sektor": None,
                "grund": "Wölbordinaten dieses Querschnitts sind nicht bekannt "
                         "(nur I- und U-Profile)"}
    sigma_w = np.abs(B) * sw.omega_max / sec.Iw
    tau_w = (np.abs(Mtw) * sw.S_max / (sec.Iw * sw.t_S)
             if sw.t_S > 0 else np.zeros_like(Mtw))
    return {"sigma_w": sigma_w, "tau_w": tau_w, "tau_t": tau_t, "sektor": sw,
            "grund": ""}


def woelbnachweis(sec: Section, E: float, G: float, L: float,
                  x: np.ndarray, Mt: np.ndarray,
                  rand: tuple = ("frei", "frei")) -> dict:
    """Wölbkrafttorsion eines Stabes: Verlauf, Spannungen und Kennzahlen.

    Rueckgabe ein Woerterbuch mit dem :class:`Torsionsverlauf`, den
    Spannungen an jeder Stelle und der massgebenden Stelle.
    """
    v = torsionsverlauf(L, sec.It, sec.Iw, E, G, x, Mt, rand)
    sp = spannungen(sec, v.B, v.Mtw, v.Mtv)
    out = {"verlauf": v, "sektor": sp["sektor"], "grund": sp["grund"],
           "sigma_w": sp["sigma_w"], "tau_w": sp["tau_w"], "tau_t": sp["tau_t"]}
    if sp["sigma_w"] is not None and len(sp["sigma_w"]):
        j = int(np.argmax(sp["sigma_w"]))
        out["x_max"] = float(x[j])
        out["sigma_w_max"] = float(sp["sigma_w"][j])
        out["B_max"] = float(v.B[j])
    else:
        out["x_max"] = 0.0
        out["sigma_w_max"] = 0.0
        out["B_max"] = v.B_max
    return out
