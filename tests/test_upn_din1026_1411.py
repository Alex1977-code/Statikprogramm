"""
Behebung vom 14.11.2026 (Runde k7, Agent „upn“, vom Anwender freigegeben):
Querschnittswerte der UPN nach DIN 1026-1 und DSTV-Import der U-Profile.

Bis Stand 59 mass Section.channel die Flanschdicke t_f eines UPN in der Mitte
des Flanschueberstands, (b + t_w)/2 vom Stegruecken, mit 8 % Neigung fuer alle
Groessen, und liess die Ausrundung r2 an der Flanschspitze weg (UPN 200:
A 32,86 statt 32,2 cm², I_y 1 966 statt 1 910 cm⁴). DIN 1026-1 misst t bei
h <= 300 im Abstand b/2 vom Stegruecken mit 8 % Neigung, bei h > 300 bei
(b + s)/2 mit 5 % Neigung; r1 (Steg/Flansch) und r2 (Flanschspitze) nach der
Norm. Der DSTV-Import legte U-Profile mit UPN-Tabellenmassen ohne Neigung an.

Zwei Wege je Zahl: das Programm (Polygon des Umrisses, Gausssche Formeln)
gegen eine Rasterintegration hier (Punkt fuer Punkt analytisch entschieden, ob
er im Umriss liegt) und gegen die Tabellenwerte (ArcelorMittal Europe, Profil-
tabelle UPN nach DIN 1026-1:2000-03; gleichlautend Schneider Bautabellen).

Aufruf:  python -m tests.test_upn_din1026_1411
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:96s} {detail}")
    return ok


def rel(ist, soll):
    return ist / soll - 1.0


# Masse (h, b, s, t, r1, r2) [mm] nach DIN 1026-1 und Tabellenwerte
# A [cm²], I_y [cm⁴], W_y [cm³], I_z [cm⁴], W_z [cm³], e_y [cm], I_T [cm⁴]
UPN_TAB = {
    80: ((80, 45, 6, 8, 8, 4), (11.0, 106, 26.5, 19.4, 6.36, 1.45, 2.16)),
    100: ((100, 50, 6, 8.5, 8.5, 4.5), (13.5, 206, 41.2, 29.3, 8.49, 1.55, 2.81)),
    140: ((140, 60, 7, 10, 10, 5), (20.4, 605, 86.4, 62.7, 14.8, 1.75, 5.68)),
    200: ((200, 75, 8.5, 11.5, 11.5, 6), (32.2, 1910, 191, 148, 27.0, 2.01, 11.9)),
    300: ((300, 100, 10, 16, 16, 8), (58.8, 8030, 535, 495, 67.8, 2.70, 37.4)),
    400: ((400, 110, 14, 18, 18, 9), (91.5, 20350, 1020, 846, 102, 2.65, 81.6)),
}


# --------------------------------------------------------------------------
# Zweiter Weg: Rasterintegration des wahren Umrisses
# --------------------------------------------------------------------------
def _im_umriss(x, z, h, b, s, t, r1, r2):
    """True, wo (x, z) im UPN liegt (x ab Stegruecken, z ab Profilmitte), nach
    DIN 1026-1: Neigung 8 % und t bei b/2 (h <= 300), sonst 5 % und t bei (b+s)/2."""
    neig, mess = (0.08, b / 2) if h <= 300 else (0.05, (b + s) / 2)
    zz = np.abs(z)
    zi = h / 2 - (t + neig * (mess - x))                   # Flanschinnenseite
    w = math.sqrt(1 + neig ** 2)
    innen = (x >= 0) & (x <= b) & (zz <= h / 2) & ((x <= s) | (zz >= zi))
    # Ausrundung r1: Mittelpunkt im Hohlraum, Sektor zwischen Steg und Flansch
    c1x = s + r1
    c1z = h / 2 - (t + neig * (mess - c1x)) - r1 * w
    a = np.arctan2(zz - c1z, x - c1x)
    a_fl = math.atan2(1.0, -neig)                          # Richtung zur Flanschinnenseite
    in_r1 = (a >= a_fl) & (a <= math.pi) & ((x - c1x) ** 2 + (zz - c1z) ** 2 >= r1 ** 2) & (x >= s) & (zz <= zi)
    # Ausrundung r2: Mittelpunkt im Werkstoff, Sektor zwischen Flansch und Spitze
    c2x = b - r2
    c2z = h / 2 - (t + neig * (mess - c2x)) + r2 * w
    a2 = np.arctan2(zz - c2z, x - c2x)
    a_fl2 = math.atan2(-1.0, neig)
    weg_r2 = (a2 >= a_fl2) & (a2 <= 0) & ((x - c2x) ** 2 + (zz - c2z) ** 2 >= r2 ** 2) & (zz >= zi) & (x <= b)
    return (innen | in_r1) & ~weg_r2


def raster(h, b, s, t, r1, r2, n=2400):
    """A, e_y (ab Stegruecken), I_y, I_z [mm-Einheiten] ueber ein Raster (Mittelpunktregel),
    obere Haelfte und gespiegelt."""
    dx, dz = b / n, (h / 2) / (n * h / b / 2)
    xs = (np.arange(n) + 0.5) * dx
    nz = int(round((h / 2) / dz))
    A = Sx = Ixx = Izz = 0.0
    for k0 in range(0, nz, 400):
        zs = (np.arange(k0, min(nz, k0 + 400)) + 0.5) * dz
        X, Z = np.meshgrid(xs, zs)
        m = _im_umriss(X, Z, h, b, s, t, r1, r2)
        da = dx * dz
        A += 2 * m.sum() * da
        Sx += 2 * (X * m).sum() * da
        Ixx += 2 * (X * X * m).sum() * da
        Izz += 2 * (Z * Z * m).sum() * da
    ey = Sx / A
    return A, ey, Izz, Ixx - A * ey * ey


# --------------------------------------------------------------------------
def test_upn_tabelle():
    from statik3d.profiles import make_section
    for n, ((h, b, s, t, r1, r2), T) in UPN_TAB.items():
        sec = make_section(f"UPN {n}")
        A, Iy, Iz = sec.A * 1e4, sec.Iy * 1e8, sec.Iz * 1e8
        Wy, Wz, ey = sec.Wel_y * 1e6, sec.Wel_z * 1e6, sec.yc * 1e2
        Ar, eyr, Iyr, Izr = raster(h, b, s, t, r1, r2)
        Ar, eyr, Iyr, Izr = Ar / 100, eyr / 10, Iyr / 1e4, Izr / 1e4
        check(f"UPN {n}: A, I_y, I_z, e_y wie die Rasterintegration (0,1 %)",
              max(abs(rel(A, Ar)), abs(rel(Iy, Iyr)), abs(rel(Iz, Izr)), abs(rel(ey, eyr))) < 1e-3,
              f"A {A:.3f}/{Ar:.3f}, I_y {Iy:.1f}/{Iyr:.1f}, I_z {Iz:.2f}/{Izr:.2f}, e_y {ey:.3f}/{eyr:.3f}")
        abw = {"A": rel(A, T[0]), "I_y": rel(Iy, T[1]), "W_y": rel(Wy, T[2]), "I_z": rel(Iz, T[3]),
               "W_z": rel(Wz, T[4]), "e_y": rel(ey, T[5])}
        # Ausnahme UPN 400, e_y: Tabelle 2,65 cm, Umriss nach DIN 1026-1 2,678 cm (+1,04 %,
        # 0,28 mm) auf beiden Wegen - ungeklaert; A, I_y, I_z treffen die Tabelle
        grenze = {("UPN 400", "e_y"): 0.011}
        check(f"UPN {n}: A, I_y, W_y, I_z, W_z, e_y höchstens 1 % neben der Tabelle DIN 1026-1"
              + (" (e_y 1,1 %)" if n == 400 else ""),
              all(abs(v) <= grenze.get((f"UPN {n}", k), 0.01) for k, v in abw.items()),
              ", ".join(f"{k} {v * 100:+.2f} %" for k, v in abw.items()))
    s = make_section("UPN 200")
    check("UPN 200: A = 32,19 cm² (vorher 32,86), I_y = 1 910,9 cm⁴ (vorher 1 966,2)",
          abs(s.A * 1e4 - 32.185) < 0.005 and abs(s.Iy * 1e8 - 1910.9) < 0.1,
          f"A {s.A * 1e4:.3f}, I_y {s.Iy * 1e8:.1f}")


def test_upn_gross():
    """UPN 320 bis 400: 5 % Neigung, t bei (b + s)/2 (DIN 1026-1, h > 300)."""
    from statik3d.profiles import make_section
    tab = {320: (75.8, 10870, 597, 2.60), 350: (77.3, 12840, 570, 2.40),
           380: (80.4, 15760, 615, 2.38), 400: (91.5, 20350, 846, 2.65)}
    for n, T in tab.items():
        s = make_section(f"UPN {n}")
        abw = (rel(s.A * 1e4, T[0]), rel(s.Iy * 1e8, T[1]), rel(s.Iz * 1e8, T[2]), rel(s.yc * 1e2, T[3]))
        g = (0.01, 0.01, 0.01, 0.011 if n == 400 else 0.01)       # UPN 400 e_y: siehe oben
        check(f"UPN {n}: A, I_y, I_z, e_y höchstens 1 % neben der Tabelle" + (" (e_y 1,1 %)" if n == 400 else ""),
              all(abs(v) <= gg for v, gg in zip(abw, g)), " ".join(f"{v * 100:+.2f} %" for v in abw))


def test_wpl_und_iw():
    from statik3d.profiles import make_section
    from statik3d.model import iw_u_profil
    from statik3d.ec3 import woelb as W
    # Wpl nach der Tabelle (cm³): y, z
    tab = {80: (32.2, 11.9), 100: (49.0, 16.2), 140: (103, 28.3), 200: (228, 51.8), 300: (632, 130),
           400: (1240, 190)}
    for n, (wy, wz) in tab.items():
        s = make_section(f"UPN {n}")
        a, b_ = rel(s.Wpl_y * 1e6, wy), rel(s.Wpl_z * 1e6, wz)
        check(f"UPN {n}: W_pl,y und W_pl,z höchstens 2 % neben der Tabelle (vorher W_pl,z bis 26 % darunter)",
              abs(a) <= 0.02 and abs(b_) <= 0.02, f"W_pl,y {a * 100:+.2f} %, W_pl,z {b_ * 100:+.2f} %")
    for n in (200, 300, 400):
        s = make_section(f"UPN {n}")
        neig, mess = (0.08, s.b / 2) if n <= 300 else (0.05, (s.b + s.tw) / 2)
        check(f"UPN {n}: I_w mit derselben Flanschgeometrie wie A und I (Neigung {neig:g}, t bei "
              f"{'b/2' if n <= 300 else '(b+s)/2'})",
              s.Iw == iw_u_profil(s.h, s.b, s.tw, s.tf, neig, mess), f"{s.Iw * 1e12:.1f} cm⁶")
        check(f"UPN {n}: Wölbordinaten treffen I_w (Probe)", abs(W.sektorwerte(s).Iw_probe / s.Iw - 1) < 1e-9)
    s = make_section("UPN 200")
    check("UPN 200: I_w 9 559,6 cm⁶ unverändert (Runde k6)", abs(s.Iw * 1e12 - 9559.6) < 0.05, f"{s.Iw * 1e12:.2f}")
    check("UPN 200: I_T unverändert (h s³ + 2 b t³)/3 = 11,70 cm⁴",
          s.It == (s.h * s.tw ** 3 + 2 * s.b * s.tf ** 3) / 3.0, f"{s.It * 1e8:.3f}")


def test_andere_bitgleich():
    """UPE, PFC und AISC-C bleiben bitgleich (Werte vom Stand d661c7c)."""
    from statik3d.profiles import make_section
    soll = {
        "UPE 200": ("0x1.7c2dd18bd445ep-9", "0x1.4051cb4dc9f68p-16", "0x1.f6a7a31acedfap-20",
                    "0x1.8d6012156d706p-27", "0x1.54a3eef4122a1p-15", "0x1.a368a2548ba5bp-6"),
        "UPE 400": ("0x1.2d3cfe4c801acp-7", "0x1.b7fe523b268c1p-13", "0x1.5e7f2446dd1b9p-17",
                    "0x1.1df1b051a727ep-22", "0x1.83feaffc21ed3p-13", "0x1.e7b6a7f85c838p-6"),
        "PFC 200x90x30": ("0x1.f0368c2755cabp-9", "0x1.a75b07cfb8862p-16", "0x1.a535cef3a5e17p-19",
                          "0x1.46b0e3d8e02f0p-26", "0x1.f42ecab702829p-15", "0x1.ff97c17a2f387p-6"),
        "C10x15.3": ("0x1.7c5a6ab2c2e18p-9", "0x1.d838b951d29f9p-16", "0x1.013fb358d61b3p-20",
                     "0x1.52a29573430f8p-27", "0x1.1953d58384117p-15", "0x1.08605fbfbcedbp-6"),
    }
    for nm, werte in soll.items():
        s = make_section(nm)
        ist = tuple(v.hex() for v in (s.A, s.Iy, s.Iz, s.Iw, s.Wpl_z, s.yc))
        check(f"{nm}: A, I_y, I_z, I_w, W_pl,z, e_y bitgleich zum Stand d661c7c", ist == werte, str(ist[:2]))


def _modell_mit(*querschnitte, benutzt=None):
    from statik3d.model import Model, Material
    m = Model("U")
    m.add_material(Material.steel("S235"))
    for s in querschnitte:
        m.add_section(s)
    n = [m.add_node(i * 3.0, 0, 0) for i in range(len(benutzt or []) + 1)]
    for i, nm in enumerate(benutzt or []):
        m.add_element("beam", [n[i], n[i + 1]], "S235", nm)
    return m


def _alt(nm, neu_name=None, taper=0.08):
    """Ein UPN mit den Werten bis Stand 59 (Streifenformel, t bei (b + t_w)/2, ohne r2),
    wie er in einer gespeicherten Datei steht."""
    from statik3d.profiles import UPN
    from statik3d.model import Section
    H, B, tw, tf, r = UPN[int(nm.split()[1])]
    return Section.channel(neu_name or nm, H * 1e-3, B * 1e-3, tw * 1e-3, tf * 1e-3, r * 1e-3, taper=taper)


def test_gespeichert():
    from statik3d.profiles import make_section
    from statik3d import rechenverfahren as rv
    alt = _alt("UPN 200")
    eig = _alt("UPN 200", "UPN 200 eigen")
    eig.A = 32.0e-4                                    # eigener Wert des Anwenders
    eig_iw = _alt("UPN 200", "UPN 200 Iw eigen")
    eig_iw.Iw = 9000e-12
    dstv_alt = _alt("UPN 200", "UPN 200 DSTV", taper=0.0)   # frueherer DSTV-Import ohne Neigung
    upe = make_section("UPE 200")
    aisc = make_section("C10x15.3")
    namen = ["UPN 200", "UPN 200 eigen", "UPN 200 Iw eigen", "UPN 200 DSTV", "UPE 200", "C10x15.3"]
    m = _modell_mit(alt, eig, eig_iw, dstv_alt, upe, aisc, benutzt=namen)
    erk = m.u_profile_iw_alt(nur_benutzt=True)
    check("Stand 60: gespeicherte UPN mit dem alten Formelwert erkannt (auch früherer DSTV-Import), "
          "eigener Wert, UPE und AISC nicht",
          erk == ["UPN 200", "UPN 200 Iw eigen", "UPN 200 DSTV"], erk)
    mk = rv.merkmal("upn_querschnitt")
    check("Merkmal upn_querschnitt mit Wechsel Stand 60, Fehlerkorrektur",
          mk is not None and mk.wechsel[-1].stand == 60 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR,
          mk and [w.stand for w in mk.wechsel])
    check("VERFAHRENSSTAND mindestens 60", rv.VERFAHRENSSTAND >= 60, rv.VERFAHRENSSTAND)
    t = rv.modell_betroffen(m)
    check("Status nennt die alten UPN und den Weg „Profiltabelle neu zuweisen“",
          "UPN 200 DSTV" in t and "UPN 200 Iw eigen" in t and "Profiltabelle neu zuweisen" in t, t[:300])
    zeilen = m.u_profile_iw_berichtigen()
    neu = make_section("UPN 200")
    s = m.sections["UPN 200"]
    check("berichtigt: A, I_y, I_z, W, e_y, I_w wie aus der Profiltabelle",
          all(getattr(s, f) == getattr(neu, f) for f in ("A", "Iy", "Iz", "Wel_y", "Wel_z", "Wpl_y", "Wpl_z",
                                                          "yc", "ymax", "Asy", "Asz", "Iw", "It")),
          f"A {s.A * 1e4:.3f}")
    check("berichtigt: eigener I_w 9 000 cm⁶ bleibt, die übrigen Werte neu",
          m.sections["UPN 200 Iw eigen"].Iw == 9000e-12 and m.sections["UPN 200 Iw eigen"].A == neu.A)
    check("eigener Wert A = 32,00 cm² bleibt unverändert", m.sections["UPN 200 eigen"].A == 32.0e-4)
    check("früherer DSTV-UPN berichtigt", m.sections["UPN 200 DSTV"].A == neu.A and m.sections["UPN 200 DSTV"].Iw == neu.Iw)
    check("Protokollzeile nennt A 32,86 → 32,19 cm²", zeilen and "32,86 → 32,19 cm²" in " ".join(zeilen), zeilen)
    check("danach kein Status mehr", "UPN" not in rv.modell_betroffen(m) and not m.u_profile_iw_alt(),
          rv.modell_betroffen(m)[:200])


def test_gross_iw_alt():
    """UPN 400 mit I_w aus Runde k6 (8 %, t bei b/2) und alten Querschnittswerten."""
    from statik3d.profiles import make_section
    from statik3d.model import iw_u_profil
    a = _alt("UPN 400")
    m = _modell_mit(a, benutzt=["UPN 400"])
    check("UPN 400 Stand 59 erkannt", m.u_profile_iw_alt() == ["UPN 400"], m.u_profile_iw_alt())
    check("… sein I_w ist der Wert aus Runde k6 (8 %, t bei b/2)",
          a.Iw == iw_u_profil(a.h, a.b, a.tw, a.tf, 0.08), f"{a.Iw * 1e12:.1f}")
    m.u_profile_iw_berichtigen()
    neu = make_section("UPN 400")
    check("… berichtigt auf I_w und A der Profiltabelle", m.sections["UPN 400"].Iw == neu.Iw
          and m.sections["UPN 400"].A == neu.A, f"{m.sections['UPN 400'].Iw * 1e12:.1f}")


def test_doppel_u():
    """Doppel-U aus UPN mit den Teilwerten bis Stand 59: Status „neu zusammensetzen“, keine
    stille Umrechnung (die Lage der Teile folgt dem frueheren e_y); das I_w nach C6 wird
    weiter erkannt und mit den Teilen von damals berichtigt."""
    from statik3d.profiles import make_section
    from statik3d.model import iw_u_profil_alt, u_bis59
    from statik3d import sections, rechenverfahren as rv
    c = u_bis59(make_section("UPN 200"))
    off = 0.005 + c.yc
    alt = sections.build("2 UPN 200", [(c, -off, 0, 0, True), (c, off, 0, 0, False)])
    c6 = sections.build("2 UPN 200 C6", [(c, -off, 0, 0, True), (c, off, 0, 0, False)])
    c6.Iw += 2 * (iw_u_profil_alt(c.h, c.b, c.tw, c.tf) - c.Iw)
    heute = sections.double_channel("2 UPN 200 neu", "UPN 200", gap=0.01)
    m = _modell_mit(alt, c6, heute, benutzt=["2 UPN 200", "2 UPN 200 C6", "2 UPN 200 neu"])
    t = rv.modell_betroffen(m)
    check("Doppel-U mit UPN-Teilen bis Stand 59: Status „neu zusammensetzen“, der heutige nicht",
          "2 UPN 200, 2 UPN 200 C6" in t and "neu zusammensetzen" in t and "2 UPN 200 neu" not in t, t[-260:])
    a0 = alt.A
    m.u_profile_iw_berichtigen()
    check("Doppel-U: A bleibt (keine stille Umrechnung)", m.sections["2 UPN 200"].A == a0)
    check("Doppel-U mit I_w nach C6: berichtigt auf 2 · 9 559,6 + Steiner mit den Teilen von damals",
          abs(m.sections["2 UPN 200 C6"].Iw - alt.Iw) <= 1e-9 * alt.Iw,
          f"{m.sections['2 UPN 200 C6'].Iw * 1e12:.1f} gegen {alt.Iw * 1e12:.1f}")


def test_dstv():
    from statik3d.importers import dstv as D
    from statik3d.profiles import make_section
    from statik3d.model import Section
    teil = {"profil": "Rinne", "code": "U", "hoehe": 200, "breite": 75, "stegdicke": 8.5,
            "flanschdicke": 11.5, "radius": 11.5}
    s = D.section_from_part(dict(teil))
    neu = make_section("UPN 200")
    check("DSTV: U mit den Tabellenmassen des UPN 200 hat die Werte der Profiltabelle",
          s.A == neu.A and s.Iy == neu.Iy and s.Iz == neu.Iz and s.Iw == neu.Iw, f"A {s.A * 1e4:.3f}")
    m = _modell_mit(s, benutzt=[s.name])
    check("DSTV: … und löst keine Frage beim Öffnen aus", m.u_profile_iw_alt() == [], m.u_profile_iw_alt())
    teil2 = dict(teil, radius=10.0)
    s2 = D.section_from_part(teil2)
    ref = Section.channel("x", 0.2, 0.075, 0.0085, 0.0115, 0.010)
    check("DSTV: U mit Nicht-Tabellenmassen bleibt ohne Neigung", s2.A == ref.A and s2.Iw == ref.Iw,
          f"A {s2.A * 1e4:.3f}")


def main():
    for t in (test_upn_tabelle, test_upn_gross, test_wpl_und_iw, test_andere_bitgleich, test_gespeichert,
              test_gross_iw_alt, test_doppel_u, test_dstv):
        try:
            t()
        except Exception as ex:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{t.__name__} ohne Ausnahme", False, repr(ex))
    ok = sum(1 for _, o in RESULTS if o)
    print(f"\n{ok}/{len(RESULTS)} Prüfungen bestanden")
    return 0 if ok == len(RESULTS) else 1


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
