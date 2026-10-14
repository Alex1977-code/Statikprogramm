"""
Verfestigung bis f_u, danach ideal plastisch (13.10.2026).

Entscheidung des Anwenders vom 13.10.2026: „Option 1: bilinear mit E/100 bis f_u,
danach ideal plastisch (entspricht EN 1993-1-5 C.6). Verfestigungsmodul je
Werkstoff einstellbar, Vorgabe E/100, wählbar auch ohne Verfestigung (E/10 000).
f_u immer aus dem Werkstoff nehmen. Fehlt er, eine Meldung ausgeben und keinen
Vorgabewert setzen. Schrauben bis f_ub, Spannstahl f_p0,1k bis f_pk.“

Bis dahin verfestigte jeder Werkstoff ohne Grenze (σ_y = f_y + H ε_p): am
Drehlager stand der Schraubenkoerper V90 bei 560,6 N/mm2 und ε_p 9,69 % - ueber
f_u = 490 N/mm2.

Geprueft wird:

* die Rueckfuehrung am Punkt: verfestigender Ast unveraendert, ein Schritt ueber
  den Knick endet auf q = f_u, auf dem Plateau bleibt q = f_u;
* die konsistente Tangente in beiden Aesten und beim Wechsel im Schritt gegen
  den Differenzenquotienten - am Punkt und als ΔK am Netz (hex8, tet10);
* der einachsige Zugstab aus Volumen (hex8, tet10) ueber den Knick hinaus gegen
  die geschlossene bilineare Loesung mit Plateau;
* „ohne Verfestigung“ (E/10 000), fehlendes f_u mit Meldung (Protokoll und
  Netzabnahme), Schraube (f_yb bis f_ub) und Spannstahl (f_p0,1k bis f_pk, aus
  dem RFEM-Import, Werkstofftyp 15);
* Speichern und Laden, alte Dateien bekommen die Vorgabe;
* Rechnungen, die f_u nicht erreichen, bleiben bitgleich;
* die Werkstoffmaske (Verfestigung zur Wahl, Grenze angezeigt).

Aufruf:  python -m tests.test_verfestigung_grenze
"""
import dataclasses
import json
import os
import sqlite3
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_verfestigung_"), "einstellungen.json")

from statik3d import plastizitaet as pl, solver          # noqa: E402
from statik3d.model import Material, Model               # noqa: E402

RESULTS = []
_FENSTER = {}

E, NU, FY, FU = 210e9, 0.3, 355e6, 490e6
G = E / (2.0 * (1.0 + NU))
LAM = E * NU / ((1.0 + NU) * (1.0 - 2.0 * NU))
R01 = 0.01
H01 = E * R01 / (1.0 - R01)            # E_t = E/100 -> H = E/99


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:78s} {detail}")
    return ok


def nahe(name, ist, soll, tol, einheit=""):
    ist, soll = float(ist), float(soll)
    abw = abs(ist - soll) / (abs(soll) if abs(soll) > 1e-14 else 1.0)
    return check(name, abw <= tol, f"ist {ist:.8g} soll {soll:.8g} ({abw:.1e}) {einheit}")


def _versuch(eps):
    """Versuchsspannung D eps (Voigt, Ingenieurgleitungen)."""
    return pl._spannung(np.array([LAM]), np.array([G]), np.asarray(eps, float)[None, :])[0]


def _d_el():
    D = np.zeros((6, 6))
    for a in range(6):
        e = np.zeros(6)
        e[a] = 1.0
        D[:, a] = _versuch(e)
    return D


# --------------------------------------------------------------------------
# 1) Rueckfuehrung am Punkt
# --------------------------------------------------------------------------
def test_rueckfuehrung_knick():
    eps_u = (FU - FY) / H01                    # plastische Dehnung am Knick
    # a) verfestigender Ast: bitgleich wie ohne Grenze
    rng = np.random.default_rng(1)
    gleich = 0
    for _ in range(20):
        tr = rng.normal(0.0, 250e6, 6)
        eq = float(abs(rng.normal(0.0, 0.01)))
        a = pl.rueckfuehrung(tr, FY, H01, G, eq, FU)
        b = pl.rueckfuehrung(tr, FY, H01, G, eq)
        if FY + H01 * (eq + b[2]) <= FU:
            gleich += int(np.array_equal(a[0], b[0]) and np.array_equal(a[1], b[1]) and a[2] == b[2])
        else:
            gleich += 1
    check("verfestigender Ast unter f_u: bitgleich wie ohne Grenze (20 Zustände)", gleich == 20, str(gleich))
    # b) ein Schritt ueber den Knick, einachsig, aus dem ungedehnten Zustand
    tr = np.array([20000e6, 0, 0, 0, 0, 0])
    s, d, dg = pl.rueckfuehrung(tr, FY, H01, G, 0.0, FU)
    nahe("ein Schritt über den Knick endet auf q = f_u", pl.vergleichsspannung(s), FU, 1e-12, "Pa")
    nahe("… Δγ = (q_trial − f_u)/(3G)", dg, (20000e6 - FU) / (3 * G), 1e-12)
    check("… und liegt hinter dem Knick (ε_p > (f_u − f_y)/H)", dg > eps_u, f"{dg:.5f} > {eps_u:.5f}")
    check("… volumentreu", abs(d[0] + d[1] + d[2]) < 1e-15, f"{d[0] + d[1] + d[2]:.1e}")
    # c) schon auf dem Plateau
    s, d, dg = pl.rueckfuehrung(np.array([600e6, 0, 0, 0, 0, 0]), FY, H01, G, 0.10, FU)
    nahe("auf dem Plateau (ε_p = 10 %): zurück auf q = f_u", pl.vergleichsspannung(s), FU, 1e-12, "Pa")
    s, d, dg = pl.rueckfuehrung(np.array([480e6, 0, 0, 0, 0, 0]), FY, H01, G, 0.10, FU)
    check("… unter f_u bleibt der Punkt elastisch", dg == 0.0, str(dg))
    # d) verfestigender Ast endet knapp unter dem Knick
    s, d, dg = pl.rueckfuehrung(np.array([700e6, 0, 0, 0, 0, 0]), FY, H01, G, 0.05, FU)
    nahe("knapp unter dem Knick: q = f_y + H (ε_p,n + Δγ)", pl.vergleichsspannung(s),
         FY + H01 * (0.05 + dg), 1e-12, "Pa")
    check("… und unter f_u", pl.vergleichsspannung(s) < FU, f"{pl.vergleichsspannung(s) / 1e6:.2f} N/mm²")
    # e) Schub ueber den Knick
    s, d, dg = pl.rueckfuehrung(np.array([0, 0, 0, 12000e6, 0, 0]), FY, H01, G, 0.0, FU)
    nahe("reiner Schub über den Knick: τ = f_u/√3", s[3], FU / np.sqrt(3.0), 1e-12, "Pa")
    # f) f_u < f_y: ideal plastisch ab f_y
    s, d, dg = pl.rueckfuehrung(np.array([900e6, 0, 0, 0, 0, 0]), FY, H01, G, 0.0, 300e6)
    nahe("f_u < f_y: ideal plastisch ab f_y", pl.vergleichsspannung(s), FY, 1e-12, "Pa")
    check("verfestigung_wirksam: H vor dem Knick, 0 dahinter",
          pl.verfestigung_wirksam(FY, H01, 0.5 * eps_u, FU) == H01
          and pl.verfestigung_wirksam(FY, H01, 1.5 * eps_u, FU) == 0.0
          and pl.verfestigung_wirksam(FY, H01, 1.5 * eps_u, None) == H01)


# --------------------------------------------------------------------------
# 2) Konsistente Tangente am Punkt gegen den Differenzenquotienten
# --------------------------------------------------------------------------
def _ast(eps, eps_p_alt, eq):
    """(σ, Ast) zur Gesamtdehnung: 0 elastisch, 1 verfestigend, 2 Plateau."""
    tr = _versuch(eps - eps_p_alt)
    s, d, dg = pl.rueckfuehrung(tr, FY, H01, G, eq, FU)
    if dg == 0.0:
        return s, 0
    return s, (2 if pl.verfestigung_wirksam(FY, H01, eq + dg, FU) == 0.0 else 1)


def test_tangente_knick_punkt():
    D_el = _d_el()
    rng = np.random.default_rng(4)
    faelle = {1: [], 2: [], "wechsel": []}
    for lauf in range(60):
        richtung = rng.normal(0.0, 1.0, 6)
        richtung[:3] -= richtung[:3].mean() * 0.5
        richtung /= np.linalg.norm(richtung)
        # drei Ausgangslagen: weit vor dem Knick, knapp davor, auf dem Plateau
        eq = (0.01, 0.06, 0.10)[lauf % 3]
        eps_p_alt = rng.normal(0.0, 2e-3, 6)
        eps_p_alt[:3] -= eps_p_alt[:3].mean()
        groesse = (2e-3, 2e-2, 5e-3)[lauf % 3] * (0.5 + rng.random())
        eps = eps_p_alt + groesse * richtung
        _s, ast = _ast(eps, eps_p_alt, eq)
        if ast == 0:
            continue
        tr = _versuch(eps - eps_p_alt)
        q = pl.vergleichsspannung(tr)
        dg = pl.rueckfuehrung(tr, FY, H01, G, eq, FU)[2]
        Hw = pl.verfestigung_wirksam(FY, H01, eq + dg, FU)
        dev = tr - ((tr[0] + tr[1] + tr[2]) / 3.0) * pl._EINS
        D_ep = D_el + pl.tangenten_differenz(dev[None, :], np.array([q]), np.array([dg]),
                                             np.array([G]), np.array([Hw]))[0]
        h = 1e-9
        num = np.zeros((6, 6))
        stabil = True
        for a in range(6):
            ep, em = eps.copy(), eps.copy()
            ep[a] += h
            em[a] -= h
            sp, ap = _ast(ep, eps_p_alt, eq)
            sm, am = _ast(em, eps_p_alt, eq)
            stabil = stabil and ap == ast and am == ast
            num[:, a] = (sp - sm) / (2 * h)
        if not stabil:
            continue
        abw = float(np.abs(D_ep - num).max() / np.abs(num).max())
        wechsel = ast == 2 and eq < (FU - FY) / H01
        faelle["wechsel" if wechsel else ast].append(abw)
    for k, text in ((1, "verfestigender Ast"), (2, "Plateau über f_u"),
                    ("wechsel", "Wechsel im Schritt (vor dem Knick → Plateau)")):
        v = faelle[k]
        check(f"D_ep = ∂σ/∂ε, {text} ({len(v)} Zustände)",
              len(v) >= 5 and max(v) < 1e-5, f"größte Abweichung {max(v) if v else float('nan'):.1e}")


# --------------------------------------------------------------------------
# 3) ΔK am Netz gegen den Differenzenquotienten (hex8, tet10)
# --------------------------------------------------------------------------
def _netz(typ, fu=FU):
    from tests import pruefkoerper as pk
    m, _ids = pk.quader(typ, 2, 1, 1, 1.0, 0.5, 0.5, E=E, nu=NU, fy=FY, verzerrung=0.0)
    m.materials["S"].fu = fu
    return m


def test_dk_knick_differenzenquotient():
    einst = pl.Plastizitaet(an=True, verfestigung=R01)
    alt = pl.H_TANGENTE
    for typ in ("hex8", "tet10"):
        m = _netz(typ)
        el = pl._solid_elemente(m, None)
        rng = np.random.default_rng(9)
        u = rng.normal(0.0, 1.5e-2, m.ndof)
        try:
            pl.H_TANGENTE = 0.0
            _F, z, info = pl._schritt_block(m, u, pl.Zustand(), einst, el, typ, [], tangente=True)
            dK = info["dK"].toarray()
            spalten = np.flatnonzero(np.abs(dK).sum(axis=0) > 0)
            num = np.zeros((m.ndof, len(spalten)))
            h = 1e-9
            for j, a in enumerate(spalten):
                up, um = u.copy(), u.copy()
                up[a] += h
                um[a] -= h
                num[:, j] = -(pl._schritt_block(m, up, pl.Zustand(), einst, el, typ, [])[0]
                              - pl._schritt_block(m, um, pl.Zustand(), einst, el, typ, [])[0]) / (2 * h)
            abw = float(np.abs(dK[:, spalten] - num).max()) / max(float(np.abs(num).max()), 1e-30)
            pl.H_TANGENTE = alt
            _F2, _z2, info2 = pl._schritt_block(m, u, pl.Zustand(), einst, el, typ, [], tangente=True)
            dK2 = info2["dK"].toarray()
            abw2 = float(np.abs(dK2[:, spalten] - num).max()) / max(float(np.abs(num).max()), 1e-30)
        finally:
            pl.H_TANGENTE = alt
        S, eq = _punkte(m, u, z)
        knick = (FU - FY) / H01
        n_pl = int(np.sum(eq > knick))
        n_vf = int(np.sum((eq > 0) & (eq <= knick)))
        from statik3d.elements import solid as sl
        sv = np.array([sl.von_mises(x) for x in S])
        auf = float(np.abs(sv[eq > knick] - FU).max()) / FU if n_pl else 1.0
        check(f"{typ}: die Punkte hinter dem Knick liegen auf q = f_u", n_pl > 0 and auf < 1e-9,
              f"Abw. {auf:.1e}, größtes σ_v {sv.max() / 1e6:.2f} N/mm²")
        check(f"{typ}: ΔK = −∂F_p/∂u über den Knick ({n_vf} Punkte verfestigend, {n_pl} auf dem Plateau)",
              n_pl > 0 and n_vf > 0 and abw < 1e-6, f"{abw:.2e} (ohne Boden H_TANGENTE)")
        check(f"{typ}: mit dem Boden H_TANGENTE weicht ΔK nur um den Boden ab",
              abw2 < 2e-3, f"{abw2:.2e}")


# --------------------------------------------------------------------------
# 4) Einachsiger Zugstab ueber den Knick
# --------------------------------------------------------------------------
def _zugstab(typ, mat: Material, eps, n=(3, 1, 1), L=0.3, b=0.1):
    """Quader an drei Symmetrieebenen gehalten, das Ende x = L um eps L
    gezogen (Weg vorgegeben, sonst gaebe es hinter f_u kein Gleichgewicht)."""
    from tests import pruefkoerper as pk
    m, _ids = pk.quader(typ, *n, L, b, b, E=mat.E, nu=mat.nu, fy=mat.fy)
    m.materials["S"] = dataclasses.replace(mat, name="S")
    lc = m.add_load_case("LF1")
    lc.gravity = [0, 0, 0]
    X = np.asarray(m.nodes, float)
    for k in range(m.nn):
        if abs(X[k, 0]) < 1e-12:
            m.fix(k, [0])
        if abs(X[k, 0] - L) < 1e-12:
            m.fix(k, [0], values=[eps * L])
        if abs(X[k, 1]) < 1e-12:
            m.fix(k, [1])
        if abs(X[k, 2]) < 1e-12:
            m.fix(k, [2])
    return m


def _bilinear(mat: Material, eps, r=R01):
    """σ(ε) einachsig: E bis f_y, dann E_t = r E bis f_u, danach f_u."""
    fy, fu = float(mat.fy), (float(mat.fu) if mat.fu else np.inf)
    if eps <= fy / mat.E:
        return mat.E * eps
    return min(fy + r * mat.E * (eps - fy / mat.E), fu)


def _rechnen(m, einst, log=None):
    m.plastizitaet = einst
    system = solver.StaticSystem(m)
    F = solver.case_loads(m, {"LF1": 1.0})[0]
    log = [] if log is None else log
    return pl.iteration(m, F, lambda Fg: system.solve(Fg), einst, log=log,
                        loesen_tangente=lambda Fg, dK: system.solve(Fg, K_extra=dK))


def _punkte(m, u, zustand):
    """Alle Spannungen und ε_p,eq an den Integrationspunkten."""
    sp = pl.punktspannungen(m, u, zustand)
    S = np.vstack([v[1] for v in sp.values()])
    eq = np.concatenate([np.ravel(zustand.eps_p_eq[i]) for i in sp])
    return S, eq


def _zug_pruefen(text, typ, mat, eps, r=R01, stufen=1, einst=None):
    m = _zugstab(typ, mat, eps)
    einst = einst or pl.Plastizitaet(an=True, verfestigung=R01, laststufen=stufen,
                                     iterationen=40, toleranz=1e-8)
    log = []
    u, z, F_p, info = _rechnen(m, einst, log)
    S, eq = _punkte(m, u, z)
    soll = _bilinear(mat, eps, r)
    ep_soll = eps - soll / mat.E
    abw_s = float(np.abs(S[:, 0] - soll).max()) / soll
    quer = float(np.abs(S[:, 1:]).max()) / soll
    abw_e = float(np.abs(eq - ep_soll).max()) / ep_soll
    check(f"{text}: σ_xx = {soll / 1e6:.2f} N/mm² an allen {len(S)} Punkten, quer null",
          info["konvergiert"] and abw_s < 1e-6 and quer < 1e-6,
          f"Abw. {abw_s:.1e}, quer {quer:.1e}, {info['iterationen']} Newton-Schritte, {info['verfahren']}")
    check(f"{text}: ε_p,eq = ε − σ/E = {ep_soll * 100:.3f} %", abw_e < 1e-6, f"Abw. {abw_e:.1e}")
    return m, info, log


def test_zugstab_bilinear():
    mat = Material("S355", E=E, nu=NU, rho=0.0, fy=FY, fu=FU)
    eps_u = FY / E + (FU - FY) / (R01 * E)
    print(f"   Knick bei ε = {eps_u * 100:.3f} % (ε_p = {(FU - FY) / H01 * 100:.3f} %)")
    for typ in ("hex8", "tet10"):
        _zug_pruefen(f"{typ} ε = 3 % (verfestigend)", typ, mat, 0.03)
        _zug_pruefen(f"{typ} ε = 10 % in einer Laststufe (über den Knick)", typ, mat, 0.10)
        _zug_pruefen(f"{typ} ε = 10 % in drei Laststufen", typ, mat, 0.10, stufen=3)
    # Durch den ganzen Loeser: geglaettete Knotenspannung = f_u
    m = _zugstab("hex8", mat, 0.10)
    m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=R01, laststufen=2, iterationen=40,
                                     toleranz=1e-8)
    res = solver.solve_static(m)
    S = np.asarray(res.solid_knoten["spannung"])
    from statik3d.elements import solid as sl
    sv = np.array([sl.von_mises(x) for x in S])
    pz = res.info.get("plastizitaet") or {}
    check("solve_static, hex8 ε = 10 %: σ_v an allen Knoten = f_u",
          pz.get("konvergiert") and float(np.abs(sv - FU).max()) / FU < 1e-6,
          f"{sv.min() / 1e6:.4f} bis {sv.max() / 1e6:.4f} N/mm², {pz.get('iterationen')} Newton-Schritte")


# --------------------------------------------------------------------------
# 5) Ohne Verfestigung (E/10 000)
# --------------------------------------------------------------------------
def test_ohne_verfestigung():
    mat = Material("S355", E=E, nu=NU, rho=0.0, fy=FY, fu=FU, verfestigung=pl.VERFESTIGUNG_OHNE)
    check("„ohne Verfestigung“ ist E_t = E/10 000",
          pl.werkstoff_verfestigung(mat, pl.Plastizitaet()) == 1e-4
          and pl.verfestigung_text(mat.verfestigung) == "ohne Verfestigung (E/10 000)")
    for typ in ("hex8", "tet10"):
        _zug_pruefen(f"{typ} ohne Verfestigung, ε = 2 %", typ, mat, 0.02, r=1e-4)
    # die Vorgabe der Rechnung gilt nur fuer Werkstoffe ohne eigene Angabe
    m = _zugstab("hex8", mat, 0.02)
    m.materials["T"] = Material("T", E=E, nu=NU, fy=FY, fu=FU)
    einst = pl.Plastizitaet(an=True, verfestigung=0.05)
    check("eigene Angabe vor der Vorgabe der Rechnung (5 %)",
          pl.werkstoff_verfestigung(m.materials["S"], einst) == 1e-4
          and pl.werkstoff_verfestigung(m.materials["T"], einst) == 0.05)


# --------------------------------------------------------------------------
# 6) Fehlendes f_u: Meldung, kein Vorgabewert
# --------------------------------------------------------------------------
def test_fehlendes_fu():
    from statik3d import diagnose as dg
    mat = Material("S355", E=E, nu=NU, rho=0.0, fy=FY)            # ohne f_u
    m, info, log = _zug_pruefen("ohne f_u, ε = 10 %: ohne Grenze wie bisher", "hex8", mat, 0.10)
    zeile = "Plastizität: Werkstoff „S“ ohne f_u – Verfestigung ohne Grenze, bitte f_u eingeben"
    check("… Meldung im Protokoll, einmal", sum(1 for z in log if z == zeile) == 1,
          next((z for z in log if "ohne f_u" in z), "keine"))
    check("… kein Vorgabewert gesetzt (f_u bleibt leer)", m.materials["S"].fu is None,
          str(m.materials["S"].fu))
    m.plastizitaet.an = True
    w = [b for b in dg.abnahme(m, warnungen=True) if "f_u" in b.text]
    check("… Netzabnahme: eine WARNUNG mit Werkstoff und Bitte",
          len(w) == 1 and w[0].stufe == "WARNUNG" and "Werkstoff „S“ ohne f_u" in w[0].text
          and "bitte f_u eingeben" in w[0].text, w[0].text if w else "keine")
    m.plastizitaet.an = False
    check("… ohne Plastizität keine solche Warnung",
          not [b for b in dg.abnahme(m, warnungen=True) if "f_u" in b.text])
    s = Material("Schraube 10.9", E=E, nu=NU, fy=900e6)
    check("… bei einer Schraube heißt es f_ub", "ohne f_ub" in pl.meldung_ohne_grenze(s)
          and "bitte f_ub eingeben" in pl.meldung_ohne_grenze(s), pl.meldung_ohne_grenze(s))


# --------------------------------------------------------------------------
# 7) Schraube und Spannstahl
# --------------------------------------------------------------------------
_RFEM_SCHEMA = """
CREATE TABLE Material (id INTEGER PRIMARY KEY, version INTEGER, userID INTEGER,
                   impl_id bigint, impl_table TEXT);
CREATE TABLE MaterialImpl (id INTEGER PRIMARY KEY, version INTEGER, name TEXT,
                   parent_id bigint, databaseMaterialId bigint, materialType INTEGER);
CREATE TABLE MaterialData (id INTEGER PRIMARY KEY, version INTEGER, impl_id bigint,
                   properties_id bigint);
CREATE TABLE MaterialProperties (id INTEGER PRIMARY KEY, version INTEGER);
CREATE TABLE MaterialProperties_propertiesMap_keys (id INTEGER, container_order INTEGER, value TEXT);
CREATE TABLE MaterialProperties_propertiesMap_values (id INTEGER, container_order INTEGER,
                   reference_id bigint, reference_table TEXT);
CREATE TABLE MaterialPropertyDouble (id INTEGER PRIMARY KEY, version INTEGER,
                   propertyKey TEXT, valueSI REAL);
"""


def _rfem_werkstoff(typ, werte, name=""):
    """Ein Werkstoff wie RFEM 6 ihn speichert (MaterialImpl.materialType: 10
    Stahl, 15 Spannstahl) - durch rfem6_db._material."""
    from statik3d.importers import rfem6_db as r6
    con = sqlite3.connect(":memory:")
    con.executescript(_RFEM_SCHEMA)
    con.execute("INSERT INTO Material VALUES (1,1,3,1,'MaterialImpl')")
    con.execute("INSERT INTO MaterialImpl VALUES (1,1,?,1,2309,?)", (name, typ))
    con.execute("INSERT INTO MaterialData VALUES (1,1,1,1)")
    con.execute("INSERT INTO MaterialProperties VALUES (1,1)")
    for j, (k, v) in enumerate(werte.items()):
        con.execute("INSERT INTO MaterialPropertyDouble VALUES (?,1,?,?)", (j + 1, k, v))
        con.execute("INSERT INTO MaterialProperties_propertiesMap_keys VALUES (1,?,?)", (j, k))
        con.execute("INSERT INTO MaterialProperties_propertiesMap_values "
                    "VALUES (1,?,?,'MaterialPropertyDouble')", (j, j + 1))
    m = Model("rfem")
    log = []
    nm = r6._material(r6.Db(con), 1, m, {}, log)
    return m.materials[nm], log


def test_schraube_spannstahl():
    from statik3d.joints import build
    from statik3d.joints.bolts import Bolt
    mb = Model("Schraube")
    a, b = mb.add_node(0, 0, 0), mb.add_node(0, 0, 0.03)
    build.add_bolt(mb, a, b, Bolt("M20", "10.9"))
    sm = mb.materials["Schraube 10.9"]
    check("Anschlussbau: Werkstoff „Schraube 10.9“ trägt die Art Schraube, f_yb 900, f_ub 1000",
          sm.art == "Schraube" and sm.werkstoffart() == "Schraube" and sm.fy == 900e6 and sm.fu == 1000e6
          and sm.grenze_name() == "f_ub" and sm.fliess_name() == "f_yb",
          f"{sm.art!r} {sm.fy} {sm.fu}")
    check("… eine alte Datei ohne Art erkennt die Schraube am Namen",
          Material("Schraube 8.8", fy=640e6, fu=800e6).werkstoffart() == "Schraube"
          and Material("S355", fy=355e6).werkstoffart() == "")
    schraube = Material("Schraube 10.9", E=E, nu=NU, rho=0.0, fy=900e6, fu=1000e6, art="Schraube")
    for typ in ("hex8", "tet10"):
        _zug_pruefen(f"{typ} Schraube 10.9, ε = 3 % (f_yb bis f_ub)", typ, schraube, 0.03)
        _zug_pruefen(f"{typ} Schraube 10.9, ε = 8 % (Plateau f_ub)", typ, schraube, 0.08)
    check("… Anzeige der Grenze: f_ub = 1000 N/mm²",
          pl.grenze_text(schraube).startswith("f_ub = 1000 N/mm²"), pl.grenze_text(schraube))
    # Spannstahl aus RFEM (Werkstofftyp 15, f_p0,1k und f_pk)
    sp, log = _rfem_werkstoff(15, {"E": 170e9, "nu": 0.3, "rho": 7850.0, "alpha": 1.2e-5,
                                   "f_p01k": 835e6, "f_pk": 1030e6})
    check("RFEM Typ 15: Spannstahl, f_p0,1k in f_y, f_pk in f_u",
          sp.art == "Spannstahl" and sp.fy == 835e6 and sp.fu == 1030e6
          and sp.grenze_name() == "f_pk" and sp.fliess_name() == "f_p0,1k",
          f"{sp.name}: {sp.art!r} {sp.fy} {sp.fu}")
    check("… das Importprotokoll nennt die Art und beide Kennwerte",
          any("Spannstahl" in z and "f_p0,1k = 835" in z and "f_pk = 1030" in z for z in log),
          next((z for z in log if "Material" in z), ""))
    st, _log = _rfem_werkstoff(10, {"E": 210e9, "nu": 0.3, "f_y": 355e6, "f_u": 490e6})
    check("RFEM Typ 10: Stahl, f_y und f_u", st.art == "" and st.grenze_name() == "f_u", repr(st.art))
    spm = dataclasses.replace(sp, rho=0.0)
    for typ in ("hex8", "tet10"):
        _zug_pruefen(f"{typ} Spannstahl, ε = 15 % (Plateau f_pk)", typ, spm, 0.15)
    check("… Anzeige der Grenze: f_pk = 1030 N/mm²",
          pl.grenze_text(sp).startswith("f_pk = 1030 N/mm²"), pl.grenze_text(sp))


# --------------------------------------------------------------------------
# 8) Speichern und Laden
# --------------------------------------------------------------------------
def test_speichern_laden():
    m = Model("Speichern")
    m.add_material(Material("A", fy=835e6, fu=1030e6, verfestigung=1e-4, art="Spannstahl"))
    m.add_material(Material("B", fy=355e6, fu=490e6))
    m.add_material(Material("C", fy=355e6, fu=490e6, verfestigung=0.004))
    pfad = os.path.join(tempfile.mkdtemp(prefix="verfestigung_"), "m.json")
    m.save(pfad)
    m2 = Model.load(pfad)
    a, b, c = (m2.materials[k] for k in "ABC")
    check("Speichern/Laden: Verfestigung und Art bleiben",
          a.verfestigung == 1e-4 and a.art == "Spannstahl" and b.verfestigung is None and b.art == ""
          and c.verfestigung == 0.004, f"{a.verfestigung} {a.art!r} {b.verfestigung} {c.verfestigung}")
    with open(pfad, encoding="utf-8") as f:
        d = json.load(f)
    for v in d["materials"].values():
        v.pop("verfestigung", None)
        v.pop("art", None)
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(d, f)
    m3 = Model.load(pfad)
    a3 = m3.materials["A"]
    check("alte Datei (ohne die Schlüssel): Vorgabe E/100 für jeden Werkstoff",
          all(x.verfestigung is None for x in m3.materials.values())
          and all(pl.werkstoff_verfestigung(x, m3.plastizitaet) == 0.01 for x in m3.materials.values()),
          str([x.verfestigung for x in m3.materials.values()]))
    check("… und die Grenze aus dem Werkstoff", a3.fu == 1030e6 and pl.werkstoff_grenze(a3) == 1030e6)


# --------------------------------------------------------------------------
# 9) Unter f_u bitgleich; der Unterschied H = E r/(1 − r) gegen E/100
# --------------------------------------------------------------------------
def test_unter_fu_bitgleich():
    check("Vorgabe E_t/E = 1 % = E/100: H = E/99 wie bisher",
          pl.Plastizitaet().verfestigung == 0.01 and pl.Plastizitaet().H(E) == E * 0.01 / 0.99
          and pl.werkstoff_verfestigung(Material("X"), pl.Plastizitaet()) == 0.01)
    for typ in ("hex8", "tet10"):
        erg = []
        for fu in (FU, None):
            mat = Material("S355", E=E, nu=NU, rho=0.0, fy=FY, fu=fu)
            m = _zugstab(typ, mat, 0.03)
            u, z, F_p, info = _rechnen(m, pl.Plastizitaet(an=True, verfestigung=R01, laststufen=2,
                                                          iterationen=40, toleranz=1e-8))
            erg.append((u, F_p, info["iterationen"]))
        check(f"{typ} ε = 3 % mit f_u = 490 und ohne f_u: u und F_p bitgleich",
              np.array_equal(erg[0][0], erg[1][0]) and np.array_equal(erg[0][1], erg[1][1])
              and erg[0][2] == erg[1][2], f"{erg[0][2]} / {erg[1][2]} Newton-Schritte")
    # Kragtraeger unter 1,20 M_el (Biegung, mehrachsig): f_u nie erreicht
    from tests import pruefkoerper as pk
    fy, b, h, L = 235e6, 0.2, 0.2, 1.0
    M = 1.2 * fy * b * h ** 2 / 6.0
    I = b * h ** 3 / 12.0
    us = []
    for fu in (360e6, None):
        m, _ids = pk.quader("hex8", 5, 1, 4, L, b, h, fy=fy)
        m.materials["S"].fu = fu
        for k in [n for n in range(m.nn) if abs(m.nodes[n, 0]) < 1e-9]:
            m.fix(int(k), "all")
        seiten = pk.randseiten(m, lambda X: bool(np.all(np.abs(X[:, 0] - L) < 1e-9)))
        pk.spannung_auf_seiten(m, seiten, lambda x: (M * (x[2] - h / 2) / I, 0.0, 0.0))
        m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=0.01, laststufen=2,
                                         iterationen=25, toleranz=1e-8)
        r = solver.solve_static(m)
        us.append((np.asarray(r.u if hasattr(r, "u") else r.displacements, float),
                   (r.info.get("plastizitaet") or {}).get("eps_p_max")))
    check("Kragträger 1,20 M_el mit f_u = 360 und ohne f_u: Verschiebungen bitgleich",
          np.array_equal(us[0][0], us[1][0]) and us[0][1] == us[1][1] and (us[0][1] or 0) > 0,
          f"ε_p max {us[0][1]:.3e}")
    # Der Unterschied, haette „E/100“ H gemeint (Zahlen fuer den Bericht)
    H100 = E / 100.0
    print(f"   H = E r/(1 − r) mit r = 1 %: {H01 / 1e6:.2f} N/mm², H = E/100: {H100 / 1e6:.2f} N/mm² "
          f"({(H01 - H100) / H100 * 100:.2f} %); σ_y bei ε_p = 5 %: {(FY + H01 * 0.05) / 1e6:.2f} "
          f"gegen {(FY + H100 * 0.05) / 1e6:.2f} N/mm²; f_u = 490 erreicht bei ε_p = "
          f"{(FU - FY) / H01 * 100:.3f} % gegen {(FU - FY) / H100 * 100:.3f} %")
    check("Lesart E_t = E/100 (Steigung der Gesamtkurve, EN 1993-1-5 Bild C.2): einachsige Tangente r E",
          abs(1.0 / (1.0 / E + 1.0 / H01) - 0.01 * E) < 1e-3)


# --------------------------------------------------------------------------
# 10) Werkstoffmaske
# --------------------------------------------------------------------------
def _fenster():
    if "w" in _FENSTER:
        return _FENSTER["w"], _FENSTER["app"]
    from PySide6 import QtWidgets
    from statik3d.gui.main import MainWindow
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = MainWindow()
    w.show()
    app.processEvents()
    w._fragen_knoepfe = lambda *a, **k: True
    w.fehler_liste = []
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w, w.fehler_liste, protokoll=True)
    _FENSTER.update(w=w, app=app)
    return w, app


def test_werkstoffmaske():
    from PySide6 import QtWidgets
    w, app = _fenster()
    w.new_model()
    app.processEvents()
    m = w.model
    m.add_material(Material("Stahl", E=E, nu=NU, fy=FY, fu=FU))
    m.add_material(Material("Litze", E=170e9, nu=0.3, fy=835e6, fu=1030e6, art="Spannstahl"))
    m.add_material(Material("Ohne", E=E, nu=NU, fy=FY))

    def maske(name):
        mk = w._objektmaske("werkstoff", name) or w.maskenrand.maske
        app.processEvents()
        return mk

    mk = maske("Stahl")
    cb = mk._felder.get("verfestigung")
    gr = mk._felder.get("grenze")
    check("Werkstoffmaske: Feld „Verfestigung“ zur Wahl, Vorgabe E/100",
          isinstance(cb, QtWidgets.QComboBox) and cb.isEditable() and cb.currentText() == "Vorgabe E/100"
          and cb.findText("ohne Verfestigung (E/10 000)") >= 0,
          cb.currentText() if cb is not None else "kein Feld")
    check("… zeigt die Grenze f_u mit der plastischen Dehnung am Knick",
          isinstance(gr, QtWidgets.QLabel) and "f_u = 490 N/mm²" in gr.text() and "6,36 %" in gr.text(),
          gr.text() if gr is not None else "kein Feld")
    cb.setCurrentText("ohne Verfestigung (E/10 000)")
    mk.anwenden()
    app.processEvents()
    check("„ohne Verfestigung“ + Übernehmen: Werkstoff E_t/E = 1e-4",
          m.materials["Stahl"].verfestigung == 1e-4, str(m.materials["Stahl"].verfestigung))
    mk = maske("Stahl")
    check("… die Maske zeigt es wieder", mk._felder["verfestigung"].currentText() == "ohne Verfestigung (E/10 000)",
          mk._felder["verfestigung"].currentText())
    mk._felder["verfestigung"].setCurrentText("E/250")
    mk.anwenden()
    app.processEvents()
    nahe("„E/250“ eingetippt: E_t/E = 0,004", m.materials["Stahl"].verfestigung or 0.0, 0.004, 1e-12)
    mk = maske("Stahl")
    n_vorher = len(w.fehler_liste)
    mk._felder["verfestigung"].setCurrentText("viel")
    mk.anwenden()
    app.processEvents()
    check("„viel“: nicht übernommen, Hinweis", m.materials["Stahl"].verfestigung == 0.004
          and any("nicht verstanden" in str(t) for t in w.fehler_liste[n_vorher:]),
          str(w.fehler_liste[n_vorher:])[:120])
    mk = maske("Stahl")
    mk._felder["verfestigung"].setCurrentText("Vorgabe E/100")
    mk.anwenden()
    app.processEvents()
    check("„Vorgabe E/100“: wieder ohne eigene Angabe", m.materials["Stahl"].verfestigung is None,
          str(m.materials["Stahl"].verfestigung))
    mk = maske("Litze")
    check("Spannstahl: die Maske nennt f_pk", "f_pk = 1030 N/mm²" in mk._felder["grenze"].text(),
          mk._felder["grenze"].text())
    mk._felder["verfestigung"].setCurrentText("ohne Verfestigung (E/10 000)")
    mk.anwenden()
    app.processEvents()
    check("… Übernehmen behält die Art Spannstahl", m.materials["Litze"].art == "Spannstahl"
          and m.materials["Litze"].verfestigung == 1e-4, repr(m.materials["Litze"].art))
    mk = maske("Ohne")
    check("ohne f_u: die Maske bittet um f_u",
          "f_u fehlt" in mk._felder["grenze"].text() and "bitte f_u eingeben" in mk._felder["grenze"].text(),
          mk._felder["grenze"].text())
    # Der Dialog „Werkstoff bearbeiten“ verliert die Angaben nicht
    from statik3d.gui import dialogs as dg
    d = dg.MaterialDialog(None, m.materials["Litze"])
    neu = d.result_material()
    check("Werkstoffdialog: Verfestigung und Art bleiben", neu.verfestigung == 1e-4 and neu.art == "Spannstahl",
          f"{neu.verfestigung} {neu.art!r}")
    d.deleteLater()


def main():
    for t in (test_rueckfuehrung_knick, test_tangente_knick_punkt, test_dk_knick_differenzenquotient,
              test_zugstab_bilinear, test_ohne_verfestigung, test_fehlendes_fu,
              test_schraube_spannstahl, test_speichern_laden, test_unter_fu_bitgleich,
              test_werkstoffmaske):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    sys.stdout.flush()
    return 0 if not schlecht else 1


if __name__ == "__main__":
    # ein Fenster ist offen (test_werkstoffmaske): ohne Rueckfrage beenden
    os._exit(main())
