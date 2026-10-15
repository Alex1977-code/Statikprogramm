"""
Stab als Schraube: Zug nach EN 1993-1-8, Tab. 3.4 im Spannungsquerschnitt
(13.10.2026).

Am Drehlager sind die Schrauben als Zugstab (Rund 16/20) mit einem
Schraubenkoerper modelliert. Ergaenzung des Anwenders vom 13.10.2026: der
Nachweis nimmt A_s nach der eingetragenen Schraubengroesse (M16 157 mm²,
M20 245 mm², EN ISO 898-1), die Steifigkeit bleibt beim Schaft. Ein Stab,
dessen Querschnitt eine Schraubengroesse M12 … M36 traegt (und der nicht aus
Spannstahl ist), wird darum nicht nach EN 1993-1-1 nachgewiesen, sondern auf
Zug:

    F_t,Ed <= F_t,Rd = k2 f_ub A_s / gamma_M2,  k2 = 0,9

mit f_ub = f_u des Werkstoffs (Schraube 8.8: 800 N/mm²) und gamma_M2 aus den
Nachweiseinstellungen. Abscheren, Lochleibung und Durchstanzen haengen am
Anschluss, den der Stab nicht kennt - sie gehoeren in den Anschluss
(joints.bolts).
"""
from __future__ import annotations

import numpy as np

from .spannstahl import ist_spannstahl, schraubengroesse, spannungsquerschnitt, gewinde_hinweis, M_GRENZE

ART = "Schraube"
K2 = 0.9
NORM = "EN 1993-1-8, Tab. 3.4"


def ist_schraube(sec, mat) -> bool:
    return bool(schraubengroesse(sec)) and not ist_spannstahl(mat)


def stab_nachweis(model, member, results: dict, n: int, mc, sec, mat):
    """Zugnachweis der Schraube in ``mc`` (MemberCheck) eintragen."""
    from ..joints.bolts import SIZES
    mc.art = ART
    g = schraubengroesse(sec)
    A_s, vermerk, _meldung = spannungsquerschnitt(sec)
    # passt das Gewinde zum Stabdurchmesser? Nur ein Hinweis (15.10.2026)
    if gewinde_hinweis(sec):
        mc.warnings.append(gewinde_hinweis(sec))
    d = SIZES[g][0] * 1e-3
    fub = float(mat.ultimate_strength(d) or 0.0)
    gM2 = float(getattr(model.design, "gamma_M2", 1.25) or 1.25)
    if fub <= 0:
        mc.fehler = f"Werkstoff {mat.name} ohne Zugfestigkeit f_u"
        mc.warnings.append(f"{mc.fehler} – Schraubennachweis nicht geführt; f_u (= f_ub) am Werkstoff "
                           "eintragen")
        return mc
    FtRd = K2 * fub * A_s / gM2
    ext = {k: 0.0 for k in ("N_min", "N_max", "Vy_max", "Vz_max", "Mt_max", "My_max", "Mz_max")}
    eintraege, momente, druck = [], [], []
    for cname, res in (results or {}).items():
        mf = res.member_forces(member, n)
        N = np.asarray(mf["N"], float)
        if not len(N):
            continue
        ext["N_min"] = min(ext["N_min"], float(N.min()))
        ext["N_max"] = max(ext["N_max"], float(N.max()))
        for k, key in (("Vy_max", "Vy"), ("Vz_max", "Vz"), ("Mt_max", "Mt"), ("My_max", "My"),
                       ("Mz_max", "Mz")):
            ext[k] = max(ext[k], float(np.abs(np.asarray(mf[key], float)).max()))
        if max(ext["My_max"], ext["Mz_max"]) > M_GRENZE:
            momente.append(cname)
        if float(N.min()) < -1.0:
            druck.append((cname, float(N.min())))
        j = int(np.argmax(N))
        Nt = max(float(N[j]), 0.0)
        eintraege.append({
            "zustand": "Lastzustand", "quelle": cname, "combo": cname, "N": Nt, "x": float(mf["x"][j]),
            "sigma": Nt / A_s, "grenze": FtRd, "grenzname": "F_t,Rd", "norm": NORM, "util": Nt / FtRd,
            "text": (f"F_t,Ed/F_t,Rd = {Nt / 1e3:.1f}/{FtRd / 1e3:.1f} kN; F_t,Rd = 0.9 · f_ub · A_s / γ_M2 = "
                     f"0.9 · {fub / 1e6:.0f} N/mm² · {A_s * 1e6:.0f} mm² / {gM2:.2f}")})
    mc.zustaende = eintraege
    mc.extremes = ext
    if momente:
        mc.warnings.append(f"Biegung in der Schraube wird nicht nachgewiesen: max |M_y| = "
                           f"{ext['My_max'] / 1e3:.3f} kNm, max |M_z| = {ext['Mz_max'] / 1e3:.3f} kNm")
    if druck:
        q, nmin = min(druck, key=lambda t: t[1])
        mc.warnings.append(f"Druck in der Schraube: N_min = {nmin / 1e3:.1f} kN ({q}) – nachgewiesen ist nur Zug")
    if not eintraege:
        return mc
    best = max(eintraege, key=lambda e: e["util"])
    mc.governing = {"name": f"Schraube {g}, Zug F_t,Rd ({NORM}; {vermerk})", "combo": best["combo"],
                    "x": best["x"], "util": best["util"], "text": best["text"], "kind": ART}
    mc.util = best["util"]
    return mc
