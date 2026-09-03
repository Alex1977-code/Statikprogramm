"""
Plattenbeulen nach DIN EN 1993-1-5.

Ein duennes Blech unter Druck oder Schub versagt nicht durch Fliessen, sondern
durch Ausbeulen. Dieses Modul enthaelt die Grundlagen dafuer:

**Beulwerte** k_sigma nach Tab. 4.1 (beidseitig gestuetzte Bleche) und Tab. 4.2
(einseitig gestuetzte Bleche), k_tau nach A.3.

**Bezugsspannung** sigma_E = pi^2 E t^2 / (12 (1 - nu^2) b^2), im Stahlbau
gelaeufig als 190000 (t/b)^2 N/mm^2.

**Abminderungsbeiwert** rho nach 4.4(2) beziehungsweise chi_w nach Tab. 5.1
fuer Schub.

**Schubbeulen** nach Abschnitt 5: V_b,Rd = chi_w f_yw h_w t_w / (sqrt(3) g_M1),
begrenzt auf eta f_yw h_w t_w / (sqrt(3) g_M1). Der Flanschanteil V_bf,Rd wird
nicht angesetzt - er liegt auf der sicheren Seite.

**Methode der reduzierten Spannungen** nach Abschnitt 10 fuer ein Beulfeld
unter einem beliebigen Spannungszustand (sigma_x, sigma_z, tau)::

    1/alpha_ult,k^2 = (sx/fy)^2 + (sz/fy)^2 - (sx/fy)(sz/fy) + 3 (tau/fy)^2
    1/alpha_cr      = ... Gl. (10.6) aus den drei Einzelbeulwerten
    lambda_p        = sqrt(alpha_ult,k / alpha_cr)
    Nachweis        Gl. (10.5) mit rho_x, rho_z und chi_w

Alle Formeln sind gegen die Zahlenwerte der Norm geprueft (tests/test_beulen.py).

Grenzen: Laengs- und Quersteifen sind **nicht** enthalten (k_sigma und k_tau
gelten fuer das unversteifte Blechfeld); ebenso wenig das Schalenbeulen nach
EN 1993-1-6 und die Lasteinleitung nach Abschnitt 6.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

E_STAHL = 210e9
NU = 0.3

#: Schubbeul-Beiwert eta (bis S460 nach DIN EN 1993-1-5/NA)
ETA_SCHUB = 1.2


def epsilon(fy: float) -> float:
    """eps = sqrt(235 / f_y) mit f_y in Pa."""
    return math.sqrt(235e6 / fy) if fy > 0 else 1.0


def sigma_E(t: float, b: float, E: float = E_STAHL, nu: float = NU) -> float:
    """Bezugsspannung des Beulens [Pa]: pi^2 E t^2 / (12 (1-nu^2) b^2)."""
    if b <= 0:
        return float("inf")
    return math.pi ** 2 * E * t ** 2 / (12.0 * (1.0 - nu ** 2) * b ** 2)


# --------------------------------------------------------------------------
# Beulwerte
# --------------------------------------------------------------------------
def k_sigma(psi: float, rand: str = "beidseitig", druck_am_rand: bool = True) -> float:
    """Beulwert k_sigma fuer Laengsspannungen.

    psi:  Spannungsverhaeltnis sigma_2 / sigma_1 (Druck positiv gerechnet,
          psi = 1 gleichmaessiger Druck, psi = -1 reine Biegung)
    rand: "beidseitig" (Tab. 4.1, z. B. Steg) oder "einseitig" (Tab. 4.2,
          z. B. Flanschhaelfte)
    druck_am_rand: nur bei "einseitig" - liegt die groessere Druckspannung am
          freien Rand (Tab. 4.2 oben) oder am gestuetzten (unten)?
    """
    p = float(psi)
    if rand == "beidseitig":
        if p >= 1.0:
            return 4.0
        if p > 0.0:
            return 8.2 / (1.05 + p)
        if p == 0.0:
            return 7.81
        if p > -1.0:
            return 7.81 - 6.29 * p + 9.78 * p ** 2
        if p >= -3.0:
            return 5.98 * (1.0 - p) ** 2
        return 5.98 * 16.0
    # einseitig gestuetzt (Tab. 4.2)
    if druck_am_rand:
        if p >= 1.0:
            return 0.43
        if p >= 0.0:
            return 0.578 / (p + 0.34)
        return 1.7 - 5.0 * p + 17.1 * p ** 2
    if p >= 1.0:
        return 0.43
    if p >= 0.0:
        return 0.57 - 0.21 * p + 0.07 * p ** 2
    return 0.57 - 0.21 * p + 0.07 * p ** 2


def k_tau(alpha: float, steifen: int = 0) -> float:
    """Schubbeulwert k_tau nach A.3(1) fuer das unversteifte Blechfeld.

    alpha = a / h_w (Seitenverhaeltnis). Laengssteifen sind nicht enthalten;
    ``steifen`` wird nur gemeldet, nicht gerechnet.
    """
    a = float(alpha)
    if a <= 0:
        return 5.34
    return 5.34 + 4.00 / a ** 2 if a >= 1.0 else 4.00 + 5.34 / a ** 2


# --------------------------------------------------------------------------
# Abminderungsbeiwerte
# --------------------------------------------------------------------------
def rho_platte(lam_p: float, psi: float = 1.0, rand: str = "beidseitig") -> float:
    """Abminderungsbeiwert rho nach 4.4(2)."""
    if lam_p <= 0:
        return 1.0
    if rand == "beidseitig":
        grenze = 0.5 + math.sqrt(max(0.085 - 0.055 * psi, 0.0))
        if lam_p <= grenze:
            return 1.0
        return min(1.0, (lam_p - 0.055 * (3.0 + psi)) / lam_p ** 2)
    if lam_p <= 0.748:
        return 1.0
    return min(1.0, (lam_p - 0.188) / lam_p ** 2)


def chi_w(lam_w: float, starre_endsteife: bool = False,
          eta: float = ETA_SCHUB) -> float:
    """Abminderungsbeiwert chi_w des Stegblechs, Tab. 5.1."""
    if lam_w < 0.83 / eta:
        return eta
    if lam_w < 1.08:
        return 0.83 / lam_w
    return 1.37 / (0.7 + lam_w) if starre_endsteife else 0.83 / lam_w


# --------------------------------------------------------------------------
# Schubbeulen eines Stegblechs (Abschnitt 5)
# --------------------------------------------------------------------------
def schubbeulen_noetig(hw: float, tw: float, fy: float, a: float = 0.0,
                       eta: float = ETA_SCHUB) -> tuple:
    """Ist der Schubbeulnachweis zu fuehren? (ja/nein, Grenze, Text) - 5.1(2)."""
    eps = epsilon(fy)
    if tw <= 0:
        return False, 0.0, "keine Stegdicke"
    if a > 0:
        kt = k_tau(a / hw) if hw > 0 else 5.34
        grenze = 31.0 * eps * math.sqrt(kt) / eta
        text = f"31 ε √k_τ/η = {grenze:.1f} (Quersteifen im Abstand a = {a:.2f} m)"
    else:
        grenze = 72.0 * eps / eta
        text = f"72 ε/η = {grenze:.1f} (nur Endquersteifen)"
    return (hw / tw > grenze), grenze, text


def schubbeulen(hw: float, tw: float, fy: float, a: float = 0.0,
                gamma_M1: float = 1.1, starre_endsteife: bool = False,
                eta: float = ETA_SCHUB) -> dict:
    """Schubbeultragfaehigkeit V_b,Rd eines Stegblechs nach Abschnitt 5.

    a: Abstand der Quersteifen [m]; 0 = nur Steifen an den Auflagern.
    Der Flanschanteil V_bf,Rd wird nicht angesetzt (sichere Seite).
    """
    eps = epsilon(fy)
    if hw <= 0 or tw <= 0:
        return {"V_b_Rd": 0.0, "fehler": "Stegabmessungen unbekannt"}
    if a > 0:
        kt = k_tau(a / hw)
        lam = hw / (37.4 * tw * eps * math.sqrt(kt))
        grund = f"λ̄_w = h_w/(37,4 t_w ε √k_τ), k_τ = {kt:.2f} (5.3(3))"
    else:
        kt = k_tau(0.0)
        lam = hw / (86.4 * tw * eps)
        grund = "λ̄_w = h_w/(86,4 t_w ε), nur Endquersteifen (5.3(3))"
    chi = chi_w(lam, starre_endsteife, eta)
    V_bw = chi * fy * hw * tw / (math.sqrt(3.0) * gamma_M1)
    V_max = eta * fy * hw * tw / (math.sqrt(3.0) * gamma_M1)
    return {"V_b_Rd": min(V_bw, V_max), "V_bw_Rd": V_bw, "V_max": V_max,
            "chi_w": chi, "lambda_w": lam, "k_tau": kt, "eta": eta,
            "grund": grund,
            "tau_cr": kt * sigma_E(tw, hw),
            "begrenzt": V_bw > V_max}


# --------------------------------------------------------------------------
# Lasteinleitung (Abschnitt 6)
# --------------------------------------------------------------------------
#: Lasteinleitungsarten nach Bild 6.1
EINLEITUNGSARTEN = {
    "a": "Kraft über einen Flansch, Weiterleitung über den Steg zum anderen "
         "Flansch (Bild 6.1 a)",
    "b": "Kraft über einen Flansch, Weiterleitung durch Schub im Steg "
         "(Bild 6.1 b)",
    "c": "Kraft am unversteiften Trägerende (Bild 6.1 c)",
}


def k_F(art: str, hw: float, a: float = 0.0, s_s: float = 0.0,
        c: float = 0.0) -> float:
    """Beulwert k_F der Lasteinleitung nach Bild 6.1."""
    if hw <= 0:
        return 6.0
    if art == "a":
        return 6.0 + 2.0 * (hw / a) ** 2 if a > 0 else 6.0
    if art == "b":
        return 3.5 + 2.0 * (hw / a) ** 2 if a > 0 else 3.5
    return min(2.0 + 6.0 * (s_s + c) / hw, 6.0)


def lasteinleitung(F_Ed: float, hw: float, tw: float, tf: float, bf: float,
                   fyw: float, fyf: float = 0.0, art: str = "a",
                   s_s: float = 0.0, a: float = 0.0, c: float = 0.0,
                   gamma_M1: float = 1.1, E: float = E_STAHL) -> dict:
    """Beulnachweis der Lasteinleitung nach EN 1993-1-5, Abschnitt 6.

        F_cr   = 0,9 k_F E t_w^3 / h_w                             (6.5(3))
        m_1    = f_yf b_f / (f_yw t_w),  m_2 = 0,02 (h_w/t_f)^2 fuer lam_F > 0,5
        l_y    nach 6.5(2) beziehungsweise 6.5(3) je Lasteinleitungsart
        lam_F  = sqrt(l_y t_w f_yw / F_cr),  chi_F = 0,5/lam_F <= 1,0   (6.4)
        L_eff  = chi_F l_y,  F_Rd = f_yw L_eff t_w / gamma_M1          (6.2)

    s_s: Lasteinleitungslaenge [m], a: Abstand der Quersteifen [m],
    c: Abstand vom Traegerende (nur Art c).
    """
    out = {"art": art, "beschreibung": EINLEITUNGSARTEN.get(art, art)}
    if hw <= 0 or tw <= 0 or tf <= 0 or bf <= 0 or fyw <= 0:
        out["fehler"] = "Stegabmessungen unvollständig"
        return out
    fyf = fyf or fyw
    kf = k_F(art, hw, a, s_s, c)
    F_cr = 0.9 * kf * E * tw ** 3 / hw
    m1 = fyf * bf / (fyw * tw)

    def ly_von(m2: float) -> float:
        if art in ("a", "b"):
            ly = s_s + 2.0 * tf * (1.0 + math.sqrt(max(m1 + m2, 0.0)))
            return min(ly, a) if a > 0 else ly
        le = min(kf * E * tw ** 2 / (2.0 * fyw * hw), s_s + c)
        l1 = le + tf * math.sqrt(max(m1 / 2.0 + (le / tf) ** 2 + m2, 0.0))
        l2 = le + tf * math.sqrt(max(m1 + m2, 0.0))
        return min(l1, l2)

    # 6.5(1): zuerst mit m_2 = 0 rechnen, dann pruefen ob lam_F > 0,5
    ly = ly_von(0.0)
    lam = math.sqrt(ly * tw * fyw / F_cr) if F_cr > 0 else float("inf")
    m2 = 0.02 * (hw / tf) ** 2 if lam > 0.5 else 0.0
    if m2:
        ly = ly_von(m2)
        lam = math.sqrt(ly * tw * fyw / F_cr) if F_cr > 0 else float("inf")
    chi = min(0.5 / lam, 1.0) if lam > 0 else 1.0
    L_eff = chi * ly
    F_Rd = fyw * L_eff * tw / gamma_M1
    out.update({"k_F": kf, "F_cr": F_cr, "m_1": m1, "m_2": m2, "l_y": ly,
                "lambda_F": lam, "chi_F": chi, "L_eff": L_eff, "F_Rd": F_Rd,
                "F_Ed": abs(F_Ed), "eta_2": abs(F_Ed) / F_Rd if F_Rd > 0 else float("inf"),
                "s_s": s_s, "a": a, "c": c})
    return out


def lasteinleitung_interaktion(eta_2: float, eta_1: float) -> dict:
    """Interaktion Lasteinleitung und Biegung, 7.2(1): eta_2 + 0,8 eta_1 <= 1,4."""
    w = eta_2 + 0.8 * eta_1
    return {"wert": w, "grenze": 1.4, "eta": w / 1.4, "ok": w <= 1.4 + 1e-9,
            "text": f"η_2 + 0,8 η_1 = {eta_2:.3f} + 0,8·{eta_1:.3f} = {w:.3f} ≤ 1,4"}


# --------------------------------------------------------------------------
# Versteifte Beulfelder (Anhang A und Abschnitt 4.5, 9)
# --------------------------------------------------------------------------
@dataclass
class Steife:
    """Eine Steife eines Beulfeldes.

    art:    "laengs" (in Richtung der Hauptdruckspannung) oder "quer"
    lage:   Abstand vom gedrueckten Rand [m] (Laengssteife) beziehungsweise
            vom Feldanfang [m] (Quersteife)
    A_sl:   Flaeche der Steife **allein** [m^2] - sie geht in
            delta = SUM A_sl/(b t) nach A.1(2) ein
    I_sl:   Traegheitsmoment der Steife **mit** mitwirkendem Blech um die
            Blechebene [m^4] - fuer gamma = I_sl/I_p und sigma_cr,sl
    A_sl_1: Flaeche der Steife **mit** mitwirkendem Blech [m^2] fuer
            sigma_cr,sl nach 4.5.3(3). 0 = aus je 15 eps t neben der Steife
            (Bild 4.4)
    I_T:    Torsionstraegheitsmoment der Steife [m^4] (fuer 9.2.1)
    I_p:    polares Traegheitsmoment um den Anschlusspunkt [m^4] (fuer 9.2.1)

    Fuer Quersteifen ist ``I_sl`` das Traegheitsmoment der Steife und ``lage``
    ihr Abstand zur naechsten Quersteife (9.3.3).
    """
    art: str = "laengs"
    lage: float = 0.0
    A_sl: float = 0.0
    I_sl: float = 0.0
    A_sl_1: float = 0.0
    I_T: float = 0.0
    I_p: float = 0.0
    name: str = ""

    def flaeche_mit_blech(self, t: float, fy: float) -> float:
        """A_sl,1 - Steife samt mitwirkendem Blech (je 15 eps t, Bild 4.4)."""
        if self.A_sl_1 > 0:
            return self.A_sl_1
        return self.A_sl + 2.0 * 15.0 * epsilon(fy) * t * t


def k_sigma_p_A1(a: float, b: float, t: float, steifen, psi: float = 1.0,
                 nu: float = NU) -> dict:
    """Beulwert k_sigma,p der laengsversteiften Platte nach Anhang A.1(2).

        gamma = I_sl / I_p,   delta = SUM A_sl / (b t),   alpha = a / b
        I_p   = b t^3 / (12 (1 - nu^2))

        alpha <= gamma^(1/4):  k = 2[(1+alpha^2)^2 + gamma - 1] / [alpha^2 (psi+1)(1+delta)]
        alpha >  gamma^(1/4):  k = 4 (1 + sqrt(gamma)) / [(psi+1)(1+delta)]

    A.1(1): gilt fuer Platten mit **mindestens drei** Laengssteifen; bei einer
    oder zwei Steifen ist A.2 massgebend (siehe ``sigma_cr_p``).
    """
    laengs = [x for x in steifen if x.art == "laengs"]
    if not laengs or b <= 0 or t <= 0 or a <= 0:
        return {"k_sigma_p": k_sigma(psi), "gamma": 0.0, "delta": 0.0,
                "versteift": False}
    I_p = b * t ** 3 / (12.0 * (1.0 - nu ** 2))
    I_sl = sum(x.I_sl for x in laengs)
    A_sl = sum(x.A_sl for x in laengs)
    gamma = I_sl / I_p if I_p > 0 else 0.0
    delta = A_sl / (b * t)
    alpha = a / b
    nenner = (psi + 1.0) * (1.0 + delta)
    if nenner <= 0:
        return {"k_sigma_p": k_sigma(psi), "gamma": gamma, "delta": delta,
                "versteift": True,
                "hinweis": "ψ ≤ -1: A.1(2) gilt nur für 0 ≤ ψ ≤ 1"}
    if alpha <= gamma ** 0.25:
        k = 2.0 * ((1.0 + alpha ** 2) ** 2 + gamma - 1.0) / (alpha ** 2 * nenner)
        zweig = "α ≤ γ^(1/4)"
    else:
        k = 4.0 * (1.0 + math.sqrt(gamma)) / nenner
        zweig = "α > γ^(1/4)"
    return {"k_sigma_p": max(k, k_sigma(psi)), "gamma": gamma, "delta": delta,
            "alpha": alpha, "zweig": zweig, "versteift": True,
            "I_sl": I_sl, "A_sl": A_sl, "I_p": I_p}


def sigma_cr_sl_A22(a: float, b: float, t: float, st, fy: float,
                    E: float = E_STAHL, nu: float = NU) -> dict:
    """Beulspannung einer Platte mit **einer** Laengssteife, A.2.2.

        a_c = 4,33 (I_sl,1 b_1^2 b_2^2 / (t^3 b))^(1/4)

        a >= a_c:  sigma_cr,sl = 1,05 E sqrt(I_sl,1 t^3 b) / (A_sl,1 b_1 b_2)
        a <  a_c:  sigma_cr,sl = pi^2 E I_sl,1/(A_sl,1 a^2)
                                 + E t^3 b a^2 / (4 pi^2 (1-nu^2) A_sl,1 b_1^2 b_2^2)

    Der erste Summand des zweiten Zweiges ist zugleich die Knickspannung des
    Ersatzstabes (4.5.3) - dadurch ist sigma_cr,p >= sigma_cr,c gesichert.
    """
    b1 = max(st.lage, 1e-9)
    b2 = max(b - st.lage, 1e-9)
    A1 = st.flaeche_mit_blech(t, fy)
    if A1 <= 0 or st.I_sl <= 0 or t <= 0 or b <= 0:
        return {"sigma_cr_sl": inf_(), "fehler": "Steifenquerschnitt unbekannt"}
    a_c = 4.33 * (st.I_sl * b1 ** 2 * b2 ** 2 / (t ** 3 * b)) ** 0.25
    euler = math.pi ** 2 * E * st.I_sl / (A1 * a ** 2) if a > 0 else inf_()
    if a >= a_c:
        s = 1.05 * E * math.sqrt(st.I_sl * t ** 3 * b) / (A1 * b1 * b2)
        zweig = "a ≥ a_c"
    else:
        bett = (E * t ** 3 * b * a ** 2
                / (4.0 * math.pi ** 2 * (1.0 - nu ** 2) * A1 * b1 ** 2 * b2 ** 2))
        s = euler + bett
        zweig = "a < a_c"
    return {"sigma_cr_sl": s, "a_c": a_c, "zweig": zweig, "b_1": b1, "b_2": b2,
            "A_sl_1": A1, "I_sl_1": st.I_sl, "sigma_cr_euler": euler}


def _extrapolation(b: float, lage: float, psi: float) -> float:
    """b_c / b_sl,c - Hochrechnung auf den gedrueckten Rand (4.5.3(3)).

    Bei gleichmaessigem Druck (psi = 1) gibt es keine Nulllinie im Feld; der
    Faktor ist dann 1. Sonst liegt die Nulllinie bei b/(1-psi) vom gedrueckten
    Rand.
    """
    if psi >= 1.0:
        return 1.0
    bc = b / (1.0 - psi)
    bsl = max(bc - lage, 1e-9)
    return bc / bsl


def sigma_cr_p(a: float, b: float, t: float, steifen, psi: float = 1.0,
               fy: float = 355e6, rand: str = "beidseitig",
               E: float = E_STAHL, nu: float = NU) -> dict:
    """Beulspannung des (versteiften) Feldes - A.1 ab drei Steifen, sonst A.2."""
    laengs = [x for x in steifen if x.art == "laengs"]
    sE = sigma_E(t, b, E, nu)
    if not laengs:
        k = k_sigma(psi, rand)
        return {"sigma_cr_p": k * sE, "k_sigma_p": k, "verfahren": "unversteift",
                "sigma_E": sE}
    if len(laengs) >= 3:
        d = k_sigma_p_A1(a, b, t, steifen, psi, nu)
        d.update({"sigma_cr_p": d["k_sigma_p"] * sE, "sigma_E": sE,
                  "verfahren": "Anhang A.1 (≥ 3 Längssteifen)"})
        return d
    st = max(laengs, key=lambda x: x.I_sl)
    d = sigma_cr_sl_A22(a, b, t, st, fy, E, nu)
    f = _extrapolation(b, st.lage, psi)
    s = d.get("sigma_cr_sl", inf_()) * f
    d.update({"sigma_cr_p": s, "sigma_E": sE, "extrapolation": f,
              "k_sigma_p": s / sE if sE > 0 else 0.0,
              "verfahren": ("Anhang A.2.2 (eine Längssteife)" if len(laengs) == 1
                            else "Anhang A.2.2, maßgebende der zwei Längssteifen")})
    if len(laengs) == 2:
        d["hinweis"] = ("Bei zwei Längssteifen verlangt A.2.1 zusätzlich die "
                        "Betrachtung beider Steifen gemeinsam; hier wird die "
                        "steifere allein geführt.")
    return d


def k_tau_st(a: float, hw: float, t: float, steifen) -> float:
    """Zuschlag k_tau,st der Laengssteifen zum Schubbeulwert, A.3(2).

        k_tau,st = 9 (h_w/a)^2 [ (I_sl/(t^3 h_w))^3 ]^(1/4)
                   >= 2,1/t (I_sl/h_w)^(1/3)
    """
    I_sl = sum(x.I_sl for x in steifen if x.art == "laengs")
    if I_sl <= 0 or hw <= 0 or t <= 0 or a <= 0:
        return 0.0
    w1 = 9.0 * (hw / a) ** 2 * ((I_sl / (t ** 3 * hw)) ** 3) ** 0.25
    w2 = (2.1 / t) * (I_sl / hw) ** (1.0 / 3.0)
    return max(w1, w2)


def sigma_cr_c(a: float, b: float, t: float, steifen, b_c: float = 0.0,
               b_sl_c: float = 0.0, E: float = E_STAHL, nu: float = NU,
               fy: float = 355e6, psi: float = 1.0) -> dict:
    """Knickspannung des laengsversteiften Feldes als Ersatzstab, 4.5.3.

    Ohne Laengssteife gilt die Platte selbst als Ersatzstab:
        sigma_cr,c = pi^2 E t^2 / (12 (1 - nu^2) a^2)
    Mit Steife:
        sigma_cr,sl = pi^2 E I_sl,1 / (A_sl,1 a^2), danach auf den gedrueckten
        Rand hochgerechnet: sigma_cr,c = sigma_cr,sl * b_c / b_sl,c
    """
    laengs = [x for x in steifen if x.art == "laengs"]
    if not laengs:
        s = math.pi ** 2 * E * t ** 2 / (12.0 * (1.0 - nu ** 2) * a ** 2) if a > 0 else inf_()
        return {"sigma_cr_c": s, "art": "unversteiftes Blech als Ersatzstab"}
    st = max(laengs, key=lambda x: x.I_sl)
    A1 = st.flaeche_mit_blech(t, fy)
    if A1 <= 0 or a <= 0 or st.I_sl <= 0:
        return {"sigma_cr_c": inf_(), "art": "Steifenquerschnitt unbekannt"}
    s_sl = math.pi ** 2 * E * st.I_sl / (A1 * a ** 2)
    f = _extrapolation(b, st.lage, psi) if not (b_c and b_sl_c) else b_c / b_sl_c
    bc = b_c or b
    bsl = b_sl_c or max(bc - st.lage, 1e-9)
    return {"sigma_cr_sl": s_sl, "sigma_cr_c": s_sl * f, "extrapolation": f,
            "i": math.sqrt(st.I_sl / A1), "A_sl_1": A1,
            "I_sl_1": st.I_sl, "b_c": bc, "b_sl_c": bsl,
            "art": "Steife als Ersatzstab (4.5.3(3))"}


def inf_() -> float:
    return float("inf")


def chi_c(lam_c: float, alpha_e: float) -> float:
    """Knickbeiwert chi_c der Knicklinie a (alpha = 0,21) mit alpha_e nach 4.5.3(5)."""
    if lam_c <= 0.2:
        return 1.0
    phi = 0.5 * (1.0 + alpha_e * (lam_c - 0.2) + lam_c ** 2)
    n = phi + math.sqrt(max(phi ** 2 - lam_c ** 2, 0.0))
    return min(1.0, 1.0 / n) if n > 0 else 1.0


def rho_c(rho: float, chi: float, xi: float) -> float:
    """Interpolation Plattenbeulen/Knickstabverhalten, 4.5.4(1).

        rho_c = (rho - chi_c) xi (2 - xi) + chi_c   mit 0 <= xi <= 1
    """
    x = min(max(xi, 0.0), 1.0)
    return (rho - chi) * x * (2.0 - x) + chi


# --------------------------------------------------------------------------
# Nachweis der Steifen (Abschnitt 9)
# --------------------------------------------------------------------------
def steife_drillknicken(st: Steife, fy: float, E: float = E_STAHL) -> dict:
    """Drillknicken einer Steife, 9.2.1(8): I_T / I_p >= 5,3 f_y / E."""
    if st.I_p <= 0 or st.I_T <= 0:
        return {"gefuehrt": False,
                "hinweis": "I_T oder I_p der Steife nicht angegeben - "
                           "das Drillknicken nach 9.2.1(8) ist gesondert zu prüfen"}
    grenze = 5.3 * fy / E
    v = st.I_T / st.I_p
    return {"gefuehrt": True, "I_T_I_p": v, "grenze": grenze,
            "ok": v >= grenze, "eta": grenze / v if v > 0 else float("inf"),
            "text": f"I_T/I_p = {v:.4f} ≥ 5,3 f_y/E = {grenze:.4f}"}


def quersteife_starr(I_st: float, hw: float, t: float, a: float) -> dict:
    """Mindeststeifigkeit einer starren Quersteife, 9.3.3(3).

        a / h_w < sqrt(2):  I_st >= 1,5 h_w^3 t^3 / a^2
        sonst:              I_st >= 0,75 h_w t^3
    """
    if hw <= 0 or t <= 0:
        return {"gefuehrt": False}
    if a > 0 and a / hw < math.sqrt(2.0):
        noetig = 1.5 * hw ** 3 * t ** 3 / a ** 2
        regel = "a/h_w < √2: I_st ≥ 1,5 h_w³ t³/a²"
    else:
        noetig = 0.75 * hw * t ** 3
        regel = "a/h_w ≥ √2: I_st ≥ 0,75 h_w t³"
    return {"gefuehrt": True, "I_noetig": noetig, "I_st": I_st,
            "ok": I_st >= noetig, "regel": regel,
            "eta": noetig / I_st if I_st > 0 else float("inf")}


# --------------------------------------------------------------------------
# Methode der reduzierten Spannungen (Abschnitt 10)
# --------------------------------------------------------------------------
def alpha_ult_k(sx: float, sz: float, tau: float, fy: float) -> float:
    """Kleinster Faktor, der die Fliessgrenze erreicht - Gl. (10.3)."""
    if fy <= 0:
        return float("inf")
    q = ((sx / fy) ** 2 + (sz / fy) ** 2 - (sx / fy) * (sz / fy)
         + 3.0 * (tau / fy) ** 2)
    return float("inf") if q <= 0 else 1.0 / math.sqrt(q)


def alpha_cr_gesamt(a_crx: float, a_crz: float, a_crt: float,
                    psi_x: float = 1.0, psi_z: float = 1.0) -> float:
    """Kleinster Faktor, der das Beulen einleitet - Gl. (10.6)."""
    ix = 1.0 / a_crx if a_crx and math.isfinite(a_crx) else 0.0
    iz = 1.0 / a_crz if a_crz and math.isfinite(a_crz) else 0.0
    it = 1.0 / a_crt if a_crt and math.isfinite(a_crt) else 0.0
    if ix <= 0 and iz <= 0 and it <= 0:
        return float("inf")
    A = (1.0 + psi_x) / 4.0 * ix + (1.0 + psi_z) / 4.0 * iz
    B = (A ** 2 + (1.0 - psi_x) / 2.0 * ix ** 2
         + (1.0 - psi_z) / 2.0 * iz ** 2 + it ** 2)
    s = A + math.sqrt(max(B, 0.0))
    return float("inf") if s <= 0 else 1.0 / s


def beulfeld(a: float, b: float, t: float, fy: float, sx: float = 0.0,
             sz: float = 0.0, tau: float = 0.0, psi_x: float = 1.0,
             psi_z: float = 1.0, rand: str = "beidseitig",
             gamma_M1: float = 1.1, starre_endsteife: bool = False,
             eta: float = ETA_SCHUB, E: float = E_STAHL, steifen=None) -> dict:
    """Nachweis eines Beulfeldes nach Abschnitt 10 (reduzierte Spannungen).

    a, b: Laenge und Breite des Feldes [m] (b quer zur Hauptdruckspannung),
    t: Blechdicke [m], fy: Streckgrenze [Pa].
    sx, sz: Druckspannungen [Pa] (Druck **positiv**), tau: Schubspannung [Pa].
    psi_x, psi_z: Spannungsverhaeltnisse der jeweiligen Richtung.

    Rueckgabe: alle Zwischenwerte und die beiden Ausnutzungen -
    ``eta_interaktion`` nach Gl. (10.5) und ``eta_rho_min`` nach der
    Vereinfachung 10.5(2).
    """
    out = {"a": a, "b": b, "t": t, "fy": fy, "sigma_x": sx, "sigma_z": sz,
           "tau": tau, "hinweise": []}
    if b <= 0 or t <= 0 or fy <= 0:
        out["fehler"] = "Abmessungen oder Streckgrenze fehlen"
        return out
    sE = sigma_E(t, b, E)
    alpha = a / b if b > 0 else 1.0
    st_liste = list(steifen or [])
    laengs = [x for x in st_liste if x.art == "laengs"]
    quer = [x for x in st_liste if x.art == "quer"]
    # Laengssteifen erhoehen den Beulwert der Platte (Anhang A.1 und A.3)
    if laengs:
        kp = sigma_cr_p(a, b, t, st_liste, psi_x, fy, rand, E)
        ksx = kp["k_sigma_p"]
        out["k_sigma_p"] = kp
    else:
        ksx = k_sigma(psi_x, rand)
    ksz = k_sigma(psi_z, rand)
    kt_un = k_tau(alpha)
    kt_st = k_tau_st(a, b, t, st_liste) if laengs else 0.0
    kt = kt_un + kt_st
    out.update({"sigma_E": sE, "alpha": alpha, "k_sigma_x": ksx,
                "k_sigma_z": ksz, "k_tau": kt, "k_tau_unversteift": kt_un,
                "k_tau_st": kt_st,
                "sigma_cr_x": ksx * sE, "sigma_cr_z": ksz * sE,
                "tau_cr": kt * sE,
                "steifen": [{"art": x.art, "lage": x.lage, "A_sl": x.A_sl,
                             "I_sl": x.I_sl, "name": x.name} for x in st_liste]})
    inf = float("inf")
    a_crx = (ksx * sE / sx) if sx > 0 else inf
    a_crz = (ksz * sE / sz) if sz > 0 else inf
    a_crt = (kt * sE / abs(tau)) if abs(tau) > 0 else inf
    a_cr = alpha_cr_gesamt(a_crx, a_crz, a_crt, psi_x, psi_z)
    a_ult = alpha_ult_k(sx, sz, tau, fy)
    out.update({"alpha_cr_x": a_crx, "alpha_cr_z": a_crz, "alpha_cr_tau": a_crt,
                "alpha_cr": a_cr, "alpha_ult_k": a_ult})
    if not math.isfinite(a_cr) or not math.isfinite(a_ult):
        out["lambda_p"] = 0.0
        out["rho_x"] = out["rho_z"] = out["chi_w"] = 1.0
        out["eta_interaktion"] = out["eta_rho_min"] = 0.0
        out["hinweise"].append("keine Beulbeanspruchung im Feld")
        return out
    lam = math.sqrt(a_ult / a_cr)
    rx = rho_platte(lam, psi_x, rand) if sx > 0 else 1.0
    rz = rho_platte(lam, psi_z, rand) if sz > 0 else 1.0
    cw = chi_w(lam, starre_endsteife, eta) if abs(tau) > 0 else 1.0
    # Knickstabaehnliches Verhalten: bei laengsversteiften Feldern zwischen
    # Plattenbeulen und Knicken interpolieren (4.5.3 und 4.5.4)
    if sx > 0:
        cc = sigma_cr_c(a, b, t, st_liste, E=E, fy=fy, psi=psi_x)
        s_cr_c = cc.get("sigma_cr_c", inf_())
        s_cr_p = ksx * sE
        if math.isfinite(s_cr_c) and s_cr_c > 0:
            xi = s_cr_p / s_cr_c - 1.0
            i_rad = cc.get("i", t / math.sqrt(12.0)) or t / math.sqrt(12.0)
            alpha_e = 0.34 + (0.09 / i_rad if i_rad > 0 else 0.0) if laengs else 0.21
            lam_c = math.sqrt(fy / s_cr_c) if s_cr_c > 0 else 0.0
            chi = chi_c(lam_c, alpha_e)
            rx_neu = rho_c(rx, chi, xi)
            out.update({"sigma_cr_c": s_cr_c, "xi": xi, "lambda_c": lam_c,
                        "chi_c": chi, "alpha_e": alpha_e, "rho_platte": rx,
                        "knickstab": cc.get("art", "")})
            rx = rx_neu
    fyd = fy / gamma_M1
    out.update({"lambda_p": lam, "rho_x": rx, "rho_z": rz, "chi_w": cw,
                "f_yd": fyd})
    # Nachweise der Steifen selbst (Abschnitt 9)
    st_checks = []
    for x in laengs:
        d = steife_drillknicken(x, fy, E)
        d["name"] = x.name or f"Längssteife bei {x.lage * 1e3:.0f} mm"
        st_checks.append(d)
    for x in quer:
        d = quersteife_starr(x.I_sl, b, t, x.lage or a)
        d["name"] = x.name or f"Quersteife bei {x.lage * 1e3:.0f} mm"
        d["art"] = "quer"
        st_checks.append(d)
    if st_checks:
        out["steifennachweise"] = st_checks
        for d in st_checks:
            if d.get("gefuehrt") and not d.get("ok", True):
                out["hinweise"].append(
                    f"{d['name']}: " + (d.get("text") or d.get("regel", ""))
                    + " ist NICHT erfüllt")
            elif not d.get("gefuehrt") and d.get("hinweis"):
                out["hinweise"].append(f"{d['name']}: {d['hinweis']}")
    # Gl. (10.5)
    tx = sx / (rx * fyd) if rx > 0 else inf
    tz = sz / (rz * fyd) if rz > 0 else inf
    tt = abs(tau) / (cw * fyd) if cw > 0 else inf
    q = tx ** 2 + tz ** 2 - tx * tz + 3.0 * tt ** 2
    out["eta_interaktion"] = math.sqrt(max(q, 0.0))
    # Vereinfachung 10.5(2): ein einziger Abminderungsbeiwert
    rho_min = min(rx if sx > 0 else 1.0, rz if sz > 0 else 1.0,
                  cw if abs(tau) > 0 else 1.0)
    out["rho_min"] = rho_min
    out["eta_rho_min"] = (1.0 / (rho_min * a_ult / gamma_M1)
                          if rho_min * a_ult > 0 else inf)
    if lam <= 0.5:
        out["hinweise"].append(
            f"λ̄_p = {lam:.3f} ≤ 0,5: das Feld beult nicht, maßgebend ist die "
            "Querschnittstragfähigkeit")
    return out


# --------------------------------------------------------------------------
# Beulfelder eines Modells
# --------------------------------------------------------------------------
def _rahmen(model, elemente) -> tuple:
    """(Ursprung, u, v, n) des Feldes: u laengs, v quer, n Normale.

    u zeigt in die laengere Ausdehnung des Feldes - das ist die Richtung a,
    quer dazu liegt b. Die Elemente muessen in einer Ebene liegen.
    """
    import numpy as np
    P = np.vstack([model.nodes[model.elements[int(e)].nodes] for e in elemente])
    mitte = P.mean(axis=0)
    Q = P - mitte
    # Normale aus der kleinsten Hauptrichtung der Punktwolke
    _u, _s, vt = np.linalg.svd(Q, full_matrices=False)
    n = vt[2]
    eben = float(np.max(np.abs(Q @ n)))
    e1, e2 = vt[0], vt[1]
    L1 = float(np.ptp(Q @ e1))
    L2 = float(np.ptp(Q @ e2))
    if L2 > L1:
        e1, e2, L1, L2 = e2, e1, L2, L1
    return mitte, e1, e2, n, L1, L2, eben


def _dreh(sig: tuple, phi: float) -> tuple:
    """Ebenen-Spannungstensor um phi drehen: (sx, sy, txy) -> (su, sv, tuv)."""
    c, s2 = math.cos(2.0 * phi), math.sin(2.0 * phi)
    sx, sy, txy = sig
    mitte = 0.5 * (sx + sy)
    halb = 0.5 * (sx - sy)
    su = mitte + halb * c + txy * s2
    sv = mitte - halb * c - txy * s2
    tuv = -halb * s2 + txy * c
    return su, sv, tuv


def feldspannungen(model, res, elemente, u, v) -> dict:
    """Membranspannungen des Feldes in den Feldachsen u und v [Pa].

    Druck wird **positiv** zurueckgegeben (so rechnet EN 1993-1-5).
    """
    import numpy as np
    from ..elements import shell as sh
    su_l, sv_l, t_l = [], [], []
    for i in elemente:
        i = int(i)
        d = res.shell_stress.get(i)
        if d is None:
            continue
        e = model.elements[i]
        t = model.shells[e.sec].t
        n = d["n"]
        sig = (float(n[0]) / t, float(n[1]) / t, float(n[2]) / t)
        X = model.nodes[e.nodes]
        T3, _a, _b = sh.shell_frame(X[0], X[1], X[2])
        ex = np.asarray(T3[0], float)
        phi = math.atan2(float(ex @ v), float(ex @ u))
        a, b, c = _dreh(sig, -phi)
        su_l.append(a)
        sv_l.append(b)
        t_l.append(c)
    if not su_l:
        return {}
    su = np.asarray(su_l)
    sv = np.asarray(sv_l)
    tt = np.asarray(t_l)
    return {"sigma_u_max": float(-su.min()), "sigma_u_min": float(-su.max()),
            "sigma_v_max": float(-sv.min()), "sigma_v_min": float(-sv.max()),
            "tau": float(np.abs(tt).max()), "n": len(su_l)}


def _steifen_von(bf) -> list:
    """Die Steifen eines Beulfeldes als ``Steife`` - egal wie sie ankommen."""
    from dataclasses import asdict as _asdict, is_dataclass
    felder = set(Steife.__dataclass_fields__)
    out = []
    for x in (getattr(bf, "steifen", None) or []):
        if isinstance(x, Steife):
            out.append(x)
            continue
        d = x if isinstance(x, dict) else (_asdict(x) if is_dataclass(x) else {})
        out.append(Steife(**{k: v for k, v in d.items() if k in felder}))
    return out


def _psi(smax: float, smin: float) -> float:
    """Spannungsverhaeltnis psi = sigma_2/sigma_1 mit Druck positiv."""
    if smax <= 0:
        return 1.0
    return max(min(smin / smax, 1.0), -4.0)


def _zylinderrahmen(model, elemente) -> tuple:
    """(Achse, Mitte, r, l) einer Zylinderschale aus ihren Elementen.

    Die Achse ist die Hauptrichtung der Punktwolke, bei der die Abstaende zur
    Achse am wenigsten streuen - fuer einen Zylinder ist das die Mantellinie.
    """
    import numpy as np
    P = np.vstack([model.nodes[model.elements[int(e)].nodes] for e in elemente])
    mitte = P.mean(axis=0)
    Q = P - mitte
    _u, _s, vt = np.linalg.svd(Q, full_matrices=False)
    beste, achse, radius = None, vt[0], 0.0
    for e in vt:
        d = Q - np.outer(Q @ e, e)
        rad = np.linalg.norm(d, axis=1)
        m = float(rad.mean())
        if m <= 0:
            continue
        streu = float(rad.std()) / m
        if beste is None or streu < beste:
            beste, achse, radius = streu, e, m
    laenge = float(np.ptp(Q @ achse))
    return achse, mitte, radius, laenge, (beste if beste is not None else 1.0)


def zylinderspannungen(model, res, elemente, achse, mitte) -> dict:
    """Membranspannungen in Meridian- und Umfangsrichtung [Pa], Druck positiv."""
    import numpy as np
    from ..elements import shell as sh
    sm, su, tt = [], [], []
    for i in elemente:
        i = int(i)
        d = res.shell_stress.get(i)
        if d is None:
            continue
        e = model.elements[i]
        t = model.shells[e.sec].t
        n = d["n"]
        sig = (float(n[0]) / t, float(n[1]) / t, float(n[2]) / t)
        X = model.nodes[e.nodes]
        T3, _a, _b = sh.shell_frame(X[0], X[1], X[2])
        ex = np.asarray(T3[0], float)
        ey = np.asarray(T3[1], float)
        nz = np.asarray(T3[2], float)
        # Meridianrichtung: die Achse, in die Tangentialebene projiziert
        m = np.asarray(achse, float) - float(np.asarray(achse, float) @ nz) * nz
        nrm = float(np.linalg.norm(m))
        if nrm < 1e-9:
            continue
        m = m / nrm
        phi = math.atan2(float(m @ ey), float(m @ ex))
        a, b, c = _dreh(sig, phi)
        sm.append(a)
        su.append(b)
        tt.append(c)
    if not sm:
        return {}
    sm = np.asarray(sm)
    su = np.asarray(su)
    tt = np.asarray(tt)
    return {"sigma_x": float(-sm.min()), "sigma_theta": float(-su.min()),
            "tau": float(np.abs(tt).max()), "n": len(sm)}


def check_zylinder(model, bf, res, fy: float = 0.0, gamma_M1: float = 1.1) -> dict:
    """Eine Zylinderschale nachweisen (EN 1993-1-6, Abschnitt 8.5)."""
    from .schalenbeulen import zylinder
    out = {"name": bf.name, "hinweise": [], "art": "zylinder"}
    try:
        achse, mitte, r_geo, l_geo, streu = _zylinderrahmen(model, bf.elemente)
    except Exception as ex:            # noqa: BLE001
        out["fehler"] = f"Geometrie nicht auswertbar: {ex}"
        return out
    r = bf.r or r_geo
    l = bf.l or l_geo
    e0 = model.elements[int(bf.elemente[0])]
    t = bf.t or model.shells[e0.sec].t
    if not fy:
        mat = model.materials.get(e0.mat)
        fy = (mat.yield_strength(t) if mat is not None else 0.0) or 235e6
    if streu > 0.05 and not bf.r:
        out["hinweise"].append(
            f"Die Abstände zur Achse streuen um {streu * 100:.1f} % - die "
            "Elemente bilden keinen sauberen Kreiszylinder. Radius und "
            "Beullänge besser von Hand angeben.")
    sp = zylinderspannungen(model, res, bf.elemente, achse, mitte)
    if not sp:
        out["fehler"] = "keine Flächenergebnisse für dieses Feld"
        return out
    z = zylinder(r=r, t=t, l=l, fy=fy, sigma_x=sp["sigma_x"],
                 sigma_theta=sp["sigma_theta"], tau=sp["tau"],
                 klasse=bf.qualitaet, rand=bf.randbedingung, gamma_M1=gamma_M1)
    out.update({"a": l, "b": 2 * math.pi * r, "t": t, "fy": fy, "r": r, "l": l,
                "sigma_x": z.sigma_x, "sigma_z": z.sigma_theta, "tau": z.tau,
                "eta_interaktion": z.util, "eta_rho_min": z.util,
                "lambda_p": z.werte.get("meridian", {}).get("lambda", 0.0),
                "rho_x": z.werte.get("meridian", {}).get("chi", 1.0),
                "rho_z": z.werte.get("umfang", {}).get("chi", 1.0),
                "chi_w": z.werte.get("schub", {}).get("chi", 1.0),
                "zylinder": z.werte, "spannungen": sp,
                "hinweise": out["hinweise"] + z.hinweise})
    if z.fehler:
        out["fehler"] = z.fehler
    return out


def check_beulfeld(model, bf, res, fy: float = 0.0, gamma_M1: float = 1.1) -> dict:
    """Ein Beulfeld gegen ein Ergebnis nachweisen (Abschnitt 10)."""
    out = {"name": bf.name, "hinweise": []}
    if not bf.elemente:
        out["fehler"] = "keine Elemente"
        return out
    if getattr(bf, "art", "eben") == "zylinder":
        return check_zylinder(model, bf, res, fy, gamma_M1)
    try:
        _mitte, u, v, _n, L1, L2, eben = _rahmen(model, bf.elemente)
    except Exception as ex:            # noqa: BLE001
        out["fehler"] = f"Geometrie nicht auswertbar: {ex}"
        return out
    a = bf.a or L1
    b = bf.b or L2
    e0 = model.elements[int(bf.elemente[0])]
    t = bf.t or model.shells[e0.sec].t
    if not fy:
        mat = model.materials.get(e0.mat)
        fy = (mat.yield_strength(t) if mat is not None else 0.0) or 235e6
    if eben > 0.02 * max(L1, L2, 1e-6):
        out["hinweise"].append(
            f"Die Elemente liegen nicht in einer Ebene (Abweichung {eben * 1e3:.0f} mm). "
            "Der Nachweis gilt für ebene Blechfelder; für gekrümmte Bleche ist "
            "EN 1993-1-6 maßgebend.")
    sp = feldspannungen(model, res, bf.elemente, u, v)
    if not sp:
        out["fehler"] = "keine Flächenergebnisse für dieses Feld"
        return out
    steifen = _steifen_von(bf)
    r = beulfeld(a=a, b=b, t=t, fy=fy,
                 sx=max(sp["sigma_u_max"], 0.0), sz=max(sp["sigma_v_max"], 0.0),
                 tau=sp["tau"],
                 psi_x=_psi(sp["sigma_u_max"], sp["sigma_u_min"]),
                 psi_z=_psi(sp["sigma_v_max"], sp["sigma_v_min"]),
                 rand=bf.rand, gamma_M1=gamma_M1,
                 starre_endsteife=bf.starre_endsteife, steifen=steifen)
    r["hinweise"] = out["hinweise"] + r.get("hinweise", [])
    r["name"] = bf.name
    r["spannungen"] = sp
    r["psi_x"] = _psi(sp["sigma_u_max"], sp["sigma_u_min"])
    r["psi_z"] = _psi(sp["sigma_v_max"], sp["sigma_v_min"])
    return r


@dataclass
class BeulCheck:
    """Nachweis eines Beulfeldes, gefuehrt ueber alle GZT-Kombinationen."""
    name: str
    a: float = 0.0
    b: float = 0.0
    t: float = 0.0
    fy: float = 0.0
    util: float = 0.0
    kombination: str = ""
    werte: dict = field(default_factory=dict)      # Zwischenwerte der massgebenden
    je_kombination: list = field(default_factory=list)
    hinweise: list = field(default_factory=list)
    fehler: str = ""

    def status(self) -> str:
        if self.fehler:
            return "nicht geführt"
        return "erfüllt" if self.util <= 1.0 else "NICHT erfüllt"


@dataclass
class BeulResults:
    felder: dict = field(default_factory=dict)
    kombinationen: list = field(default_factory=list)
    settings: dict = field(default_factory=dict)

    @property
    def util_max(self) -> float:
        return max((c.util for c in self.felder.values()), default=0.0)

    def summary(self) -> str:
        if not self.felder:
            return "Beulnachweise: keine Beulfelder festgelegt"
        schlecht = [c.name for c in self.felder.values() if c.util > 1.0]
        fehler = [c.name for c in self.felder.values() if c.fehler]
        worst = max(self.felder.values(), key=lambda c: c.util)
        s = (f"Beulen (EN 1993-1-5): {len(self.felder)} Felder, "
             f"{len(self.kombinationen)} Kombinationen, max. Ausnutzung "
             f"{worst.util:.3f} ({worst.name}"
             + (f", {worst.kombination}" if worst.kombination else "") + ")")
        if schlecht:
            s += f" - {len(schlecht)} NICHT erfüllt: " + ", ".join(schlecht)
        elif not fehler:
            s += " - alle erfüllt"
        if fehler:
            s += f" - {len(fehler)} nicht geführt: " + ", ".join(fehler)
        return s

    def table(self) -> list[list]:
        rows = [["Beulfeld", "a [m]", "b [m]", "t [mm]", "σ_x [MPa]", "σ_z [MPa]",
                 "τ [MPa]", "λ̄_p", "ρ_x", "χ_w", "Ausnutzung", "Kombination",
                 "Status"]]
        for c in self.felder.values():
            w = c.werte
            rows.append([c.name, f"{c.a:.2f}", f"{c.b:.2f}", f"{c.t * 1e3:.0f}",
                         f"{w.get('sigma_x', 0) / 1e6:.1f}",
                         f"{w.get('sigma_z', 0) / 1e6:.1f}",
                         f"{w.get('tau', 0) / 1e6:.1f}",
                         f"{w.get('lambda_p', 0):.3f}", f"{w.get('rho_x', 1):.3f}",
                         f"{w.get('chi_w', 1):.3f}", f"{c.util:.3f}",
                         c.kombination, c.status()])
        return rows


@dataclass
class EinleitungCheck:
    """Nachweis einer Lasteinleitung, gefuehrt ueber alle GZT-Kombinationen."""
    name: str
    bezug: str = ""
    typ: str = "a"
    F_Ed: float = 0.0
    F_Rd: float = 0.0
    util: float = 0.0
    kombination: str = ""
    werte: dict = field(default_factory=dict)
    je_kombination: list = field(default_factory=list)
    interaktion: dict = field(default_factory=dict)
    hinweise: list = field(default_factory=list)
    fehler: str = ""

    def status(self) -> str:
        if self.fehler:
            return "nicht geführt"
        return "erfüllt" if self.util <= 1.0 else "NICHT erfüllt"


@dataclass
class EinleitungResults:
    stellen: dict = field(default_factory=dict)
    kombinationen: list = field(default_factory=list)

    @property
    def util_max(self) -> float:
        return max((c.util for c in self.stellen.values()), default=0.0)

    def summary(self) -> str:
        if not self.stellen:
            return "Lasteinleitung: keine Stellen festgelegt"
        schlecht = [c.name for c in self.stellen.values() if c.util > 1.0]
        fehler = [c.name for c in self.stellen.values() if c.fehler]
        worst = max(self.stellen.values(), key=lambda c: c.util)
        s = (f"Lasteinleitung (EN 1993-1-5, 6): {len(self.stellen)} Stellen, "
             f"max. Ausnutzung {worst.util:.3f} ({worst.name}: "
             f"{worst.F_Ed / 1e3:.0f} von {worst.F_Rd / 1e3:.0f} kN"
             + (f", {worst.kombination}" if worst.kombination else "") + ")")
        if schlecht:
            s += f" - {len(schlecht)} NICHT erfüllt: " + ", ".join(schlecht)
        elif not fehler:
            s += " - alle erfüllt"
        if fehler:
            s += f" - {len(fehler)} nicht geführt: " + ", ".join(fehler)
        return s

    def table(self) -> list[list]:
        rows = [["Stelle", "Bezug", "Typ", "F_Ed [kN]", "F_Rd [kN]", "l_y [mm]",
                 "λ̄_F", "χ_F", "Ausnutzung", "Kombination", "Status"]]
        for c in self.stellen.values():
            w = c.werte
            rows.append([c.name, c.bezug, c.typ, f"{c.F_Ed / 1e3:.1f}",
                         f"{c.F_Rd / 1e3:.1f}",
                         f"{w.get('l_y', 0) * 1e3:.0f}",
                         f"{w.get('lambda_F', 0):.3f}", f"{w.get('chi_F', 1):.3f}",
                         f"{c.util:.3f}", c.kombination, c.status()])
        return rows


def _knotenlast(model, kombiname: str, knoten: int, richtung: int) -> float:
    """Die eingeleitete Knotenkraft [N] einer Kombination oder eines Lastfalls."""
    comb = model.combinations.get(kombiname)
    faktoren = comb.factors if comb is not None else {kombiname: 1.0}
    F = 0.0
    for lf, f in faktoren.items():
        lc = model.load_cases.get(lf)
        if lc is None:
            continue
        for nl in lc.nodal_loads:
            if int(nl.node) == int(knoten):
                F += f * float(nl.F[int(richtung)])
    return F


def _stegwerte(model, le) -> dict:
    """Stegabmessungen fuer die Lasteinleitung - aus dem Stab oder dem Knoten."""
    sec = None
    mat = None
    if le.stab and le.stab in model.members:
        mem = model.members[le.stab]
        if mem.elements:
            e = model.elements[mem.elements[0]]
            sec, mat = model.sections.get(e.sec), model.materials.get(e.mat)
    if sec is None:
        for e in model.elements:
            if e.typ in ("beam", "truss") and int(le.knoten) in [int(n) for n in e.nodes]:
                sec, mat = model.sections.get(e.sec), model.materials.get(e.mat)
                break
    if sec is None:
        return {"fehler": "kein Stabquerschnitt am Knoten gefunden - "
                          "den Stab im Nachweis angeben"}
    if sec.typ != "I" or sec.tw <= 0 or sec.tf <= 0:
        return {"fehler": f"Querschnitt „{sec.name}“ ist kein I-Profil - "
                          "die Lasteinleitung nach Abschnitt 6 gilt für "
                          "I-förmige Träger"}
    fy = (mat.yield_strength(sec.t_max) if mat is not None else 0.0) or 235e6
    return {"hw": sec.h - 2 * sec.tf, "tw": sec.tw, "tf": sec.tf, "bf": sec.b,
            "fyw": fy, "fyf": fy, "sec": sec.name}


def check_lasteinleitungen(model, analysis, combos: list = None,
                           progress=None) -> EinleitungResults:
    """Alle Lasteinleitungsstellen ueber alle GZT-Kombinationen nachweisen."""
    from .design import _uls_results
    ergebnisse = _uls_results(model, analysis, combos)
    ds = model.design
    out = EinleitungResults(kombinationen=list(ergebnisse))
    for i, (name, le) in enumerate(model.lasteinleitungen.items()):
        c = EinleitungCheck(name, le.bezug(), le.typ)
        sw = _stegwerte(model, le)
        if sw.get("fehler"):
            c.fehler = sw["fehler"]
            out.stellen[name] = c
            continue
        for kname, res in ergebnisse.items():
            if le.quelle == "auflager":
                R = getattr(res, "reactions", None)
                F = abs(float(R[le.knoten][le.richtung])) if R is not None and le.knoten in R else 0.0
            else:
                F = abs(_knotenlast(model, kname, le.knoten, le.richtung))
            if F <= 0:
                continue
            r = lasteinleitung(F, sw["hw"], sw["tw"], sw["tf"], sw["bf"],
                               sw["fyw"], sw["fyf"], le.typ, le.s_s, le.a, le.c,
                               ds.gamma_M1)
            if r.get("fehler"):
                c.fehler = r["fehler"]
                break
            eta = r["eta_2"]
            c.je_kombination.append({"kombination": kname, "F_Ed": F, "eta": eta})
            if eta >= c.util:
                c.util, c.kombination, c.werte = eta, kname, r
                c.F_Ed, c.F_Rd = F, r["F_Rd"]
        if not c.je_kombination and not c.fehler:
            c.fehler = ("keine Kraft an diesem Knoten - Quelle „Last“ oder "
                        "„Auflager“ prüfen")
        c.hinweise.append(f"Querschnitt {sw.get('sec', '')}: h_w = "
                          f"{sw['hw'] * 1e3:.0f} mm, t_w = {sw['tw'] * 1e3:.1f} mm")
        out.stellen[name] = c
        if progress:
            progress(f"Lasteinleitung {name} ({i + 1}/{len(model.lasteinleitungen)})")
    return out


def check_beulen(model, analysis, combos: list = None, progress=None) -> BeulResults:
    """Alle Beulfelder des Modells ueber alle GZT-Kombinationen nachweisen."""
    from .design import _uls_results
    ergebnisse = _uls_results(model, analysis, combos)
    ds = model.design
    out = BeulResults(kombinationen=list(ergebnisse), settings={
        "gamma_M1": ds.gamma_M1, "eta": ETA_SCHUB,
        "Norm": "DIN EN 1993-1-5, Abschnitt 10 (Methode der reduzierten Spannungen)"})
    for i, (name, bf) in enumerate(model.beulfelder.items()):
        c = BeulCheck(name)
        for kname, res in ergebnisse.items():
            r = check_beulfeld(model, bf, res, gamma_M1=ds.gamma_M1)
            if r.get("fehler"):
                c.fehler = r["fehler"]
                break
            eta = float(r.get("eta_interaktion", 0.0))
            c.je_kombination.append({"kombination": kname, "eta": eta,
                                     "sigma_x": r.get("sigma_x", 0.0),
                                     "sigma_z": r.get("sigma_z", 0.0),
                                     "tau": r.get("tau", 0.0),
                                     "lambda_p": r.get("lambda_p", 0.0)})
            if eta >= c.util:
                c.util, c.kombination, c.werte = eta, kname, r
                c.a, c.b, c.t, c.fy = r["a"], r["b"], r["t"], r["fy"]
                c.hinweise = list(r.get("hinweise", []))
        if not c.je_kombination and not c.fehler:
            c.fehler = "keine Ergebnisse"
        out.felder[name] = c
        if progress:
            progress(f"Beulfeld {name} ({i + 1}/{len(model.beulfelder)})")
    return out
