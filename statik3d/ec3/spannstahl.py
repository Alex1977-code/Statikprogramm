"""
Stabnachweis fuer Spannstahl nach EN 1992-1-1 bzw. Zulassung (13.10.2026).

Entscheidung des Anwenders vom 13.10.2026: die 16 Ankerstaebe Rund 40 des
Drehlagers (RFEM Material 3, Werkstofftyp 15, f_p0,1k 835, f_pk 1 030 N/mm²)
werden nicht nach EN 1993-1-1/-1-8 nachgewiesen, sondern als Spannstahl im
Spannungsquerschnitt A_s des Gewindes. Bis dahin lief ueber sie der
Querschnittsnachweis N_t,Rd = A f_y / gamma_M0 mit f_y = 835 N/mm².

Geprueft wird jeder Zustand, den das Programm kennt; massgebend ist der
unguenstigste (Ergaenzung des Anwenders vom selben Tag: „die Ankerkraft sinkt
unter Last, massgebend ist also der Vorspannzustand“):

* **Spannen** - sigma = N / A_s <= sigma_p,max = min(k1 f_pk; k2 f_p0,1k)
  mit k1 = 0,8, k2 = 0,9 (EN 1992-1-1, 5.10.2.1(1)). Herangezogen wird die
  eingegebene Vorspannkraft (``Vorspannung`` am Stab, oder die
  gleichwertige Temperaturlast eines Lastfalls der Kategorie P, wie der
  RFEM-Import sie schreibt) und jedes Ergebnis mit
  ``info["zustand"] == "spannen"`` (Schnittstelle fuer den kraftgesteuerten
  Spannschritt, Zweig vorspannung/kraft).
* **nach dem Verankern** - sigma <= sigma_pm0 = min(k7 f_pk; k8 f_p0,1k)
  mit k7 = 0,75, k8 = 0,85 (5.10.3(2)). Herangezogen wird das Ergebnis jedes
  Lastfalls, der nur Vorspannung traegt (am Drehlager LF398), und jedes
  Ergebnis mit ``info["zustand"] == "verankert"``. Gibt es keines, steht die
  eingegebene Vorspannkraft ohne Verluste da - mit Vermerk.
* **Lastzustand** - sigma <= f_pd = f_p0,1k / gamma_s, gamma_s = 1,15
  (3.3.6 bzw. Zulassung; Tab. 2.1N) in jeder GZT-Kombination, bei einer
  plastischen Rechnung in jeder abgelegten Laststufe
  (``info["laststufen"]``); sind keine abgelegt, gilt der Endzustand mit
  Vermerk.

Biegung im Gewinde gibt es in diesem Nachweis nicht: Momente werden genannt,
nicht nachgewiesen. Beide Spannungsgrenzen sind am Werkstoff ueberschreibbar
(``Material.sigma_pmax``/``sigma_pm0``), wenn die Zulassung abweicht.

Die Werkstoffart ist ``Material.art`` aus dem Paket plast/verfestigung
(6e11a7c): "Spannstahl" mit f_p0,1k in ``fy`` und f_pk in ``fu``. Rechnet die
kraftgesteuerte Vorspannung (Zweig vorspannung/kraft), stehen je Stab
``res.info["vorspannung"]["staebe"][Stab]`` mit N_spannen (gegen sigma_p,max)
und N_verankert (gegen sigma_pm0) - sie gehen vor die eingegebene Kraft.
"""
from __future__ import annotations

import numpy as np

from ..zahlen import zahl_text

#: Teilsicherheitsbeiwert des Spannstahls, staendige und voruebergehende
#: Bemessungssituation (EN 1992-1-1, Tab. 2.1N)
GAMMA_S = 1.15
#: sigma_p,max = min(K1 f_pk; K2 f_p0,1k) beim Spannen (EN 1992-1-1, 5.10.2.1(1))
K1, K2 = 0.8, 0.9
#: sigma_pm0 = min(K7 f_pk; K8 f_p0,1k) nach dem Verankern (EN 1992-1-1, 5.10.3(2))
K7, K8 = 0.75, 0.85

NORM_FPD = "EN 1992-1-1, 3.3.6 bzw. Zulassung"
NORM_SPANNEN = "EN 1992-1-1, 5.10.2.1"
NORM_VERANKERT = "EN 1992-1-1, 5.10.3"

ART = "Spannstahl"
GEWINDE_AUFGEWALZT = "aufgewalzt"
#: So steht die Auswahl in der Querschnittsmaske
GEWINDE_AUFGEWALZT_TEXT = "aufgewalzter Gewindestab (A_s = Nennquerschnitt)"

ZUSTAND_SPANNEN = "Spannen"
ZUSTAND_VERANKERT = "nach dem Verankern"
ZUSTAND_LAST = "Lastzustand"

#: Moment [Nm], ab dem ein Stab „Biegung“ hat: 1 Nmm - darunter ist es
#: Rundungsrest der Stabkraefte, kein Moment
M_GRENZE = 1e-3


def ist_spannstahl(mat) -> bool:
    """Werkstoffart Spannstahl (Material.werkstoffart, plast/verfestigung)."""
    if mat is None:
        return False
    art = mat.werkstoffart() if callable(getattr(mat, "werkstoffart", None)) else getattr(mat, "art", "")
    return art == ART


def f_p01k(mat) -> float:
    """f_p0,1k [Pa]: beim Spannstahl steht es in ``fy`` (RFEM-Import)."""
    return float(getattr(mat, "fy", None) or 0.0)


def f_pk(mat) -> float:
    """f_pk [Pa]: beim Spannstahl steht es in ``fu``."""
    return float(getattr(mat, "fu", None) or 0.0)


#: Ab hier sehen f_y / f_u aus wie f_p0,1k / f_pk eines Spannstahls [Pa]:
#: St 835/1030 am Drehlager; eine Schraube 10.9 (900/1000) liegt darunter
FY_SPANNSTAHL_AB, FU_SPANNSTAHL_UEBER = 800e6, 1000e6


def ladehinweise(model) -> list:
    """Zeilen fuers Protokoll beim Oeffnen: Werkstoffe ohne Art, deren f_y und
    f_u wie die eines Spannstahls aussehen (am Drehlager „Material 3 (DB 2309)“,
    vor dem 13.10.2026 importiert, 835/1030). Gesetzt wird nichts - die Art
    stellt der Anwender in der Werkstoffmaske."""
    from ..zahlen import zahl_text
    out = []
    for name, mat in (getattr(model, "materials", None) or {}).items():
        art = mat.werkstoffart() if callable(getattr(mat, "werkstoffart", None)) else getattr(mat, "art", "")
        fy, fu = float(mat.fy or 0.0), float(mat.fu or 0.0)
        if art or fy < FY_SPANNSTAHL_AB or fu <= FU_SPANNSTAHL_UEBER:
            continue
        out.append(f"Werkstoff „{name}“: f_y {zahl_text(fy / 1e6)} / f_u {zahl_text(fu / 1e6)} N/mm² sehen aus "
                   "wie f_p0,1k / f_pk eines Spannstahls, die Werkstoffart ist aber nicht gesetzt – ist es "
                   "Spannstahl, die Art in der Werkstoffmaske auf „Spannstahl“ stellen (dann gilt der "
                   "Stabnachweis nach EN 1992-1-1 bzw. Zulassung); gesetzt wurde nichts")
    return out


def f_pd(mat) -> float:
    return f_p01k(mat) / GAMMA_S


def _grenze(eingabe, a, fk, b, fp, formel):
    if eingabe:
        return float(eingabe), "Eingabe am Werkstoff (Zulassung)"
    kand = [w for w in ((a * fk) if fk else None, (b * fp) if fp else None) if w]
    return (min(kand) if kand else 0.0), formel


def sigma_p_max(mat) -> tuple:
    """(sigma_p,max [Pa], Herkunft): Eingabe am Werkstoff oder
    min(0,8 f_pk; 0,9 f_p0,1k) - am Drehlager min(824; 751,5) = 751,5 N/mm²."""
    return _grenze(getattr(mat, "sigma_pmax", None), K1, f_pk(mat), K2, f_p01k(mat),
                   f"min(0,8·f_pk; 0,9·f_p0,1k), {NORM_SPANNEN}")


def sigma_pm0(mat) -> tuple:
    """(sigma_pm0 [Pa], Herkunft): Eingabe am Werkstoff oder
    min(0,75 f_pk; 0,85 f_p0,1k) - am Drehlager min(772,5; 709,75) = 709,75 N/mm²."""
    return _grenze(getattr(mat, "sigma_pm0", None), K7, f_pk(mat), K8, f_p01k(mat),
                   f"min(0,75·f_pk; 0,85·f_p0,1k), {NORM_VERANKERT}")


def schraubengroessen() -> dict:
    """{"M12": A_s [m^2], …, "M36": …} nach EN ISO 898-1 (joints.bolts.SIZES:
    M16 157 mm², M20 245 mm²)."""
    from ..joints.bolts import SIZES
    return {k: v[1] * 1e-6 for k, v in SIZES.items() if 12.0 <= v[0] <= 36.0}


def schraubengroesse(sec) -> str:
    """Die Schraubengroesse des Querschnitts („M20“) oder ""."""
    g = str(getattr(sec, "gewinde", "") or "").strip().upper()
    return g if g in schraubengroessen() else ""


def spannungsquerschnitt(sec) -> tuple:
    """(A_s [m^2], Vermerk, Meldung) fuer den Nachweis im Gewinde.

    Reihenfolge: Schraubengroesse (Tabelle EN ISO 898-1), aufgewalzter
    Gewindestab (A_s = Nennquerschnitt, ohne Meldung), Eingabe A_s aus der
    Zulassung; sonst der Nennquerschnitt A mit der Meldung „A_s aus
    Zulassung eintragen“ (Entscheidung des Anwenders vom 13.10.2026)."""
    A = float(getattr(sec, "A", 0.0) or 0.0)
    g = schraubengroesse(sec)
    if g:
        As = schraubengroessen()[g]
        return As, f"A_s = {As * 1e6:.0f} mm² (Schraube {g}, EN ISO 898-1)", ""
    if str(getattr(sec, "gewinde", "") or "") == GEWINDE_AUFGEWALZT:
        return A, "aufgewalzter Gewindestab: A_s = Nennquerschnitt", ""
    As = getattr(sec, "A_s", None)
    if As and float(As) > 0:
        return float(As), "A_s aus Eingabe (Zulassung)", ""
    return A, "A_s = Nennquerschnitt", (
        f"Querschnitt {getattr(sec, 'name', '')}: A_s aus Zulassung eintragen – gerechnet "
        f"mit dem Nennquerschnitt A = {A * 1e6:.1f} mm²")


# --------------------------------------------------------------------------
# Vorspannung im Modell
# --------------------------------------------------------------------------
def _temperatur_vorspannung(model, lc, elemente: set) -> float:
    """Groesste Vorspannkraft [N] aus Temperaturlasten der Elemente - nur in
    einem Lastfall der Kategorie P (Vorspannung): so schreibt der RFEM-Import
    die Stabvorspannung (dT = -N_0/(E A alpha)); eine Abkuehlung in einem
    Temperaturlastfall ist keine Vorspannung."""
    if getattr(lc, "category", "") != "P":
        return 0.0
    N = 0.0
    for t in lc.eigene("temp_loads") if hasattr(lc, "eigene") else (lc.temp_loads or []):
        if int(getattr(t, "elem", -1)) in elemente and hasattr(t, "vorspannkraft"):
            N = max(N, float(t.vorspannkraft(model)))
    return N


def eingegebene_vorspannung(model, member) -> list:
    """[(Lastfall, N_0 [N])] - die Vorspannkraft, die der Anwender (oder die
    Quelldatei) fuer diesen Stab eingegeben hat, je Lastfall."""
    elemente = {int(e) for e in member.elements}
    out = []
    for name, lc in (getattr(model, "load_cases", None) or {}).items():
        N = 0.0
        for v in (getattr(lc, "vorspannungen", None) or []):
            if getattr(v, "art", "stab") == "stab" and str(getattr(v, "ziel", "")) == member.name:
                N = max(N, float(getattr(v, "kraft", 0.0) or 0.0))
        N = max(N, _temperatur_vorspannung(model, lc, elemente))
        if N > 0:
            out.append((name, N))
    return out


def ist_reine_vorspannung(model, lc) -> bool:
    """Traegt der Lastfall nur Vorspannung? Vorspannungen am Stab oder Koerper
    in jeder Kategorie; Temperaturlasten nur, wenn sie in einem Lastfall der
    Kategorie P an Zugstaeben Vorspannung erzeugen (RFEM-Import, am Drehlager
    LF398 „Vorspannung der Zuganker zum Zeitpunkt 0“)."""
    try:
        arten = lc.lasten_je_art()
    except Exception:                    # noqa: BLE001 - fremdes Objekt
        return False
    if not arten or set(arten) - {"vorspannung", "temperatur"}:
        return False
    if "temperatur" in arten:
        if getattr(lc, "category", "") != "P":
            return False
        for t in arten["temperatur"]:
            if not hasattr(t, "vorspannkraft") or t.vorspannkraft(model) <= 0:
                return False
    return True


def zustaende_sammeln(model, analysis) -> dict:
    """{Name: (Results, "spannen" | "verankert")} - die Ergebnisse, die einen
    Vorspannzustand zeigen: Lastfaelle nur mit Vorspannung (nach dem
    Verankern) und jedes Ergebnis mit ``info["zustand"]`` (Spannschritt des
    kuenftigen kraftgesteuerten Vorspannens)."""
    out: dict = {}
    if not hasattr(analysis, "cases"):
        return out
    gruppen = [getattr(analysis, "cases", None) or {}, getattr(analysis, "combinations", None) or {},
               getattr(analysis, "alternativen", None) or {}]
    for g in gruppen:
        for name, res in g.items():
            info = getattr(res, "info", None) or {}
            z = str(info.get("zustand", "") or "")
            if z in ("spannen", "verankert"):
                out[name] = (res, z)
            elif isinstance(info.get("vorspannung"), dict) and (info["vorspannung"].get("staebe") or {}):
                # kraftgesteuerte Vorspannung (vorspannung/kraft): N_spannen und
                # N_verankert je Stab stehen im Ergebnis
                out[name] = (res, "vorspannkraft")
    for name, res in (getattr(analysis, "cases", None) or {}).items():
        lc = (getattr(model, "load_cases", None) or {}).get(name)
        if name not in out and lc is not None and ist_reine_vorspannung(model, lc):
            out[name] = (res, "verankert")
    return out


# --------------------------------------------------------------------------
# Nachweis
# --------------------------------------------------------------------------
def _eintrag(zustand, quelle, combo, N, x, A_s, grenze, grenzname, norm, herkunft=""):
    sigma = abs(float(N)) / A_s
    util = sigma / grenze if grenze > 0 else float("inf")
    text = (f"σ = |N| / A_s = {abs(N) / 1e3:.1f} kN / {A_s * 1e6:.1f} mm² = {sigma / 1e6:.1f} N/mm² "
            f"≤ {grenzname} = {grenze / 1e6:.2f} N/mm²" + (f" ({herkunft})" if herkunft else ""))
    return {"zustand": zustand, "quelle": quelle, "combo": combo, "N": float(N), "x": float(x),
            "sigma": sigma, "grenze": float(grenze), "grenzname": grenzname, "norm": norm,
            "util": float(util), "text": text}


def stab_nachweis(model, member, results: dict, n: int, mc, sec, mat, zustaende: dict = None):
    """Den Spannstahlnachweis des Stabes in ``mc`` (MemberCheck) eintragen."""
    mc.art = ART
    A_s, vermerk, meldung = spannungsquerschnitt(sec)
    fp = f_p01k(mat)
    if fp <= 0 or A_s <= 0:
        mc.fehler = (f"Spannstahl {mat.name} ohne f_p0,1k" if fp <= 0
                     else f"Querschnitt {sec.name} ohne Fläche")
        mc.warnings.append(f"{mc.fehler} – Nachweis nicht geführt; f_p0,1k am Werkstoff bzw. A_s am "
                           "Querschnitt eintragen oder am Stab „Nachweis nach EC3“ ausschalten")
        return mc
    if meldung:
        mc.warnings.append(meldung)
    fpd = fp / GAMMA_S
    pmax, h_pmax = sigma_p_max(mat)
    pm0, h_pm0 = sigma_pm0(mat)
    ext = {k: 0.0 for k in ("N_min", "N_max", "Vy_max", "Vz_max", "Mt_max", "My_max", "Mz_max")}
    eintraege: list = []
    momente: list = []
    druck: list = []

    def aus_ergebnis(res, quelle, combo, zustand, grenze, grenzname, norm, herkunft="", extrem=False):
        mf = res.member_forces(member, n)
        N = np.asarray(mf["N"], float)
        if not len(N):
            return
        My, Mz = np.abs(np.asarray(mf["My"], float)), np.abs(np.asarray(mf["Mz"], float))
        if extrem:
            ext["N_min"] = min(ext["N_min"], float(N.min()))
            ext["N_max"] = max(ext["N_max"], float(N.max()))
            for k, key in (("Vy_max", "Vy"), ("Vz_max", "Vz"), ("Mt_max", "Mt"), ("My_max", "My"),
                           ("Mz_max", "Mz")):
                ext[k] = max(ext[k], float(np.abs(np.asarray(mf[key], float)).max()))
        if max(float(My.max()), float(Mz.max())) > M_GRENZE:
            momente.append((quelle, float(My.max()), float(Mz.max())))
        if float(N.min()) < -1.0:
            druck.append((quelle, float(N.min())))
        j = int(np.argmax(np.abs(N)))
        eintraege.append(_eintrag(zustand, quelle, combo, N[j], mf["x"][j], A_s, grenze, grenzname,
                                  norm, herkunft))

    # Lastzustaende: jede GZT-Kombination, bei plastischer Rechnung jede
    # abgelegte Laststufe
    for cname, res in (results or {}).items():
        info = getattr(res, "info", None) or {}
        stufen = info.get("laststufen") or []
        for k, st in enumerate(stufen, 1):
            lam = (getattr(st, "info", None) or {}).get("lam")
            q = f"{cname}, Laststufe {k}" + (f" (λ = {zahl_text(float(lam), tausender=False, stellen=4, punkt=True)})"
                                             if lam is not None else "")
            aus_ergebnis(st, q, cname, ZUSTAND_LAST, fpd, "f_pd", NORM_FPD, "f_p0,1k / γ_s")
        if info.get("plastizitaet") and not stufen:
            mc.warnings.append(f"Laststufen der Plastizität von {cname} nicht abgelegt – nachgewiesen "
                               "ist der Endzustand")
        aus_ergebnis(res, cname, cname, ZUSTAND_LAST, fpd, "f_pd", NORM_FPD, "f_p0,1k / γ_s", extrem=True)
    # Spannen: die eingegebene Vorspannkraft und Ergebnisse eines Spannschritts
    eingaben = eingegebene_vorspannung(model, member)
    for lcname, N0 in eingaben:
        eintraege.append(_eintrag(ZUSTAND_SPANNEN, f"{lcname}: eingegebene Vorspannkraft", lcname, N0, 0.0,
                                  A_s, pmax, "σ_p,max", NORM_SPANNEN, h_pmax))
    verankert = False
    for name, (res, z) in (zustaende or {}).items():
        if z == "spannen":
            aus_ergebnis(res, f"{name} (Spannschritt)", name, ZUSTAND_SPANNEN, pmax, "σ_p,max",
                         NORM_SPANNEN, h_pmax)
        elif z == "verankert":
            verankert = True
            aus_ergebnis(res, f"{name} (Ergebnis, nur Vorspannung)", name, ZUSTAND_VERANKERT, pm0,
                         "σ_pm0", NORM_VERANKERT, h_pm0)
        elif z == "vorspannkraft":
            d = ((getattr(res, "info", None) or {}).get("vorspannung", {}).get("staebe") or {}).get(member.name)
            if not d:
                continue
            if d.get("N_spannen") is not None:
                eintraege.append(_eintrag(ZUSTAND_SPANNEN, f"{name}: N_spannen (Vorspannkraft, Spannschritt)",
                                          name, float(d["N_spannen"]), 0.0, A_s, pmax, "σ_p,max",
                                          NORM_SPANNEN, h_pmax))
            if d.get("N_verankert") is not None:
                verankert = True
                eintraege.append(_eintrag(ZUSTAND_VERANKERT, f"{name}: N_verankert (Vorspannkraft)", name,
                                          float(d["N_verankert"]), 0.0, A_s, pm0, "σ_pm0", NORM_VERANKERT,
                                          h_pm0))
    if not verankert:
        for lcname, N0 in eingaben:
            eintraege.append(_eintrag(
                ZUSTAND_VERANKERT, f"{lcname}: eingegebene Vorspannkraft, ohne Verluste angesetzt "
                "(kein Ergebnis eines Lastfalls nur mit Vorspannung)", lcname, N0, 0.0, A_s, pm0,
                "σ_pm0", NORM_VERANKERT, h_pm0))
    mc.zustaende = eintraege
    mc.extremes = ext
    if momente:
        q, my, mz = max(momente, key=lambda t: max(t[1], t[2]))
        mc.warnings.append(f"Biegung im Gewinde wird nicht nachgewiesen: max |M_y| = {my / 1e3:.3f} kNm, "
                           f"max |M_z| = {mz / 1e3:.3f} kNm ({q}) – nachgewiesen ist nur σ = |N| / A_s")
    if druck:
        q, nmin = min(druck, key=lambda t: t[1])
        mc.warnings.append(f"Druck im Spannstahlstab: N_min = {nmin / 1e3:.1f} kN ({q}) – nachgewiesen ist "
                           "|N| / A_s, Knicken nicht")
    if not eintraege:
        return mc
    g = max(eintraege, key=lambda e: e["util"])
    mc.governing = {"name": f"Spannstahl, {g['zustand']}: σ ≤ {g['grenzname']} ({g['norm']}; {vermerk})",
                    "combo": g["combo"], "x": g["x"], "util": g["util"],
                    "text": g["text"] + f"; {g['quelle']}", "kind": ART}
    mc.util = g["util"]
    return mc
