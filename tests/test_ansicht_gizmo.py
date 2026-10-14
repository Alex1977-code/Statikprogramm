"""
Ansichtspaket A (Entscheidung des Anwenders vom 13.10.2026, gebaut 14.10.2026):
Achsen-Gizmo statt Ansichtswuerfel, Drehpunkt am angeklickten Punkt, Umschalter
Perspektive/Parallelprojektion.

* Rechnung des Gizmos: Projektion der sechs Achsenenden, Tiefenfolge, Treffer
  der Enden, Klick-Richtungen mit unveraendertem Blickziel und Abstand;
* Drehen um einen Punkt: der Punkt bleibt im Bild an derselben Stelle, der
  Abstand Kamera - Blickziel bleibt, an den Polen weich gebremst, ohne Kippen;
* Perspektive/Parallelprojektion: gleiche Bildgroesse beim Umschalten, Zoom
  zum Zeiger in der Parallelprojektion, gemerkt in den Einstellungen;
* im Fenster: Gizmo statt Wuerfel, kein Achsenkreuz unten rechts, Klick,
  Zug und Knoepfe am Gizmo, die mittlere Taste dreht um den Punkt unter dem
  Zeiger (ohne Treffer um die Modellmitte).

Offscreen zeichnet VTK hier nicht (Fenstergroesse 0 x 0, kein Tiefenpuffer):
der Tiefenpuffer wird darum fuer die Pruefung durch einen festen Punkt ersetzt,
und ob ein Punkt im Bild stehen bleibt, rechnet die Pruefung aus der Kamera
nach (Lage im Kamerasystem). Den echten Tiefenpuffer prueft die Hauptsitzung
auf dem Desktop.

Aufruf:  python -m tests.test_ansicht_gizmo
"""
import json
import math
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_gizmo_"), "einstellungen.json")
os.environ.pop("STATIK3D_FENSTER", None)

import numpy as np                                      # noqa: E402

RESULTS = []
_FENSTER = {}


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _nav():
    from statik3d.gui import navigation as nav
    return nav


def _kamerasystem(P, F, U, punkt):
    """Lage von ``punkt`` im Kamerasystem (rechts, oben, Tiefe) - bleibt sie
    gleich, steht der Punkt im Bild an derselben Stelle, perspektivisch wie
    parallel."""
    P, F, U, X = (np.asarray(v, float) for v in (P, F, U, punkt))
    d = (F - P) / np.linalg.norm(F - P)
    u = U - d * float(U @ d)
    u /= np.linalg.norm(u)
    r = np.cross(d, u)
    v = X - P
    return np.array([v @ r, v @ u, v @ d])


def _drehmatrix(rng):
    q = rng.normal(size=4)
    q /= np.linalg.norm(q)
    a, b, c, d = q
    return np.array([[a*a+b*b-c*c-d*d, 2*(b*c-a*d), 2*(b*d+a*c)],
                     [2*(b*c+a*d), a*a-b*b+c*c-d*d, 2*(c*d-a*b)],
                     [2*(b*d-a*c), 2*(c*d+a*b), a*a-b*b-c*c+d*d]])


# --------------------------------------------------------------------------
# Rechnung ohne Fenster
# --------------------------------------------------------------------------
def test_gizmo_rechnung():
    nav = _nav()
    # Draufsicht: Kamera ueber dem Modell, X rechts, Y oben, Z zum Betrachter
    R = np.eye(3)
    pk = nav.gizmo_punkte(R, 56.0, 56.0, 38.0)
    lage = {p["name"]: (round(p["x"], 6), round(p["y"], 6)) for p in pk}
    check("Draufsicht: +x rechts, +y oben (Qt zählt y nach unten), ±z in der Mitte",
          lage["+x"] == (94.0, 56.0) and lage["-x"] == (18.0, 56.0) and lage["+y"] == (56.0, 18.0)
          and lage["-y"] == (56.0, 94.0) and lage["+z"] == (56.0, 56.0), str(lage))
    check("… hinterstes zuerst: −z zuerst, +z zuletzt",
          pk[0]["name"] == "-z" and pk[-1]["name"] == "+z", str([p["name"] for p in pk]))
    check("… ein Klick in die Mitte trifft das vordere Ende +z, nicht −z",
          nav.ende_unter(pk, 56.0, 56.0, 10.0) == "+z")
    check("… neben jeder Kugel kein Treffer", nav.ende_unter(pk, 75.0, 75.0, 10.0) == "")
    folge = nav.zeichenfolge(pk)
    i_linie = {w: i for i, (a, w) in enumerate(folge) if a == "linie"}
    i_ende = {w: i for i, (a, w) in enumerate(folge) if a == "ende"}
    check("Zeichenfolge: jede Linie steht direkt vor der Kugel ihres positiven Endes",
          all(i_ende["+" + a] == i_linie[a] + 1 for a in "xyz") and len(folge) == 9, str(folge))
    rng = np.random.default_rng(14)
    gut = True
    for _ in range(300):
        Rz = _drehmatrix(rng)
        pk = nav.gizmo_punkte(Rz, 56.0, 56.0, 38.0)
        t = [p["tiefe"] for p in pk]
        q = {p["name"]: p for p in pk}
        for a in "xyz":
            plus, minus = q["+" + a], q["-" + a]
            gut &= abs(plus["x"] + minus["x"] - 112.0) < 1e-9 and abs(plus["y"] + minus["y"] - 112.0) < 1e-9
            gut &= abs(plus["tiefe"] + minus["tiefe"]) < 1e-12
            gut &= abs(((plus["x"] - 56) / 38) ** 2 + ((plus["y"] - 56) / 38) ** 2 + plus["tiefe"] ** 2 - 1) < 1e-9
        gut &= t == sorted(t)
        # das vorderste Ende ist auch das, was ein Klick auf seine Mitte trifft
        vorn = pk[-1]
        gut &= nav.ende_unter(pk, vorn["x"], vorn["y"], 10.0) == vorn["name"]
    check("300 zufällige Kameralagen: Enden gegenüber, Länge 1, nach Tiefe sortiert, vorderstes wird getroffen", gut)


def test_klick_richtungen():
    nav = _nav()
    P, F = np.array([3.0, -4.0, 2.5]), np.array([0.4, 0.2, -0.1])
    d0 = float(np.linalg.norm(P - F))
    gut, text = True, []
    for name, _a, _v, r in nav.ACHSEN_ENDEN:
        P2, F2, U2 = nav.blick_aus(name, P, F)
        richtung = (P2 - F2) / np.linalg.norm(P2 - F2)
        rechts = np.cross((F2 - P2) / np.linalg.norm(F2 - P2), U2)
        ok = (np.allclose(F2, F) and abs(float(np.linalg.norm(P2 - F2)) - d0) < 1e-12
              and np.allclose(richtung, r) and abs(float(U2 @ richtung)) < 1e-12)
        if name in ("+z", "-z", "-y", "+y"):
            # X liegt in Drauf-, Unter- und Vorderansicht rechts (Rueckansicht links)
            ok &= np.allclose(rechts, (1, 0, 0) if name != "+y" else (-1, 0, 0))
        if name in ("+x", "-x", "+y", "-y"):
            ok &= np.allclose(U2, (0, 0, 1))       # Seitenansichten: Z oben
        gut &= bool(ok)
        text.append(f"{name}:{np.round(P2, 2).tolist()}")
    check("Klick auf ein Ende: Blick aus dieser Richtung, Blickziel und Abstand bleiben", gut, " ".join(text[:2]))
    P2, F2, U2 = nav.blick_aus("+z", P, F)
    check("Draufsicht (+z): Kamera über dem Modell, Blick in −Z, Y oben, X rechts",
          P2[2] > F2[2] and np.allclose(U2, (0, 1, 0)), str(np.round(P2, 3)))


def test_drehen_um_punkt():
    nav = _nav()
    P, F, U = np.array([4.0, -3.0, 2.0]), np.array([0.5, 0.5, 0.5]), np.array([0.0, 0.0, 1.0])
    U = U - (F - P) / np.linalg.norm(F - P) * float(U @ ((F - P) / np.linalg.norm(F - P)))
    C = np.array([0.9, 0.1, 1.0])               # angeklickt, nicht das Blickziel
    vor = _kamerasystem(P, F, U, C)
    gut = True
    for az, ne in ((30.0, 0.0), (0.0, 20.0), (-45.0, -15.0), (170.0, 33.0)):
        P2, F2, U2 = nav.drehen_um_punkt(P, F, U, C, az, ne)
        nach = _kamerasystem(P2, F2, U2, C)
        gut &= bool(np.allclose(vor, nach, atol=1e-9))
        gut &= abs(np.linalg.norm(P2 - F2) - np.linalg.norm(P - F)) < 1e-9
        gut &= float(np.linalg.norm(F2 - C)) > 0.1    # das Blickziel springt nicht auf den Punkt
    check("Drehen um den angeklickten Punkt: er bleibt im Bild an derselben Stelle, Abstand bleibt", gut,
          f"Lage im Kamerasystem {np.round(vor, 4).tolist()}")
    # Gefuehl wie VTK: am Horizont dreht VTK (Azimuth/Elevation) genau so
    import vtk
    kam = vtk.vtkCamera()
    Ph, Fh = np.array([5.0, 0.0, 0.0]), np.zeros(3)
    kam.SetPosition(*Ph); kam.SetFocalPoint(*Fh); kam.SetViewUp(0, 0, 1)
    kam.Azimuth(-12.0)
    Pa, _f, _u = nav.drehen_um_punkt(Ph, Fh, (0, 0, 1), Fh, -12.0, 0.0)
    kam.SetPosition(*Ph); kam.SetFocalPoint(*Fh); kam.SetViewUp(0, 0, 1)
    kam.Elevation(9.0)
    Pe, _f, _u = nav.drehen_um_punkt(Ph, Fh, (0, 0, 1), Fh, 0.0, 9.0)
    kam2 = vtk.vtkCamera()
    kam2.SetPosition(*Ph); kam2.SetFocalPoint(*Fh); kam2.SetViewUp(0, 0, 1)
    kam2.Azimuth(-12.0)
    check("Vorzeichen wie bisher (VTK-Trackball): Azimut und Neigung am Horizont gleich",
          np.allclose(Pa, kam2.GetPosition(), atol=1e-9) and np.allclose(Pe, kam.GetPosition(), atol=1e-9),
          f"{np.round(Pa, 4).tolist()} / {np.round(Pe, 4).tolist()}")
    # Polbremse: immer weiter nach oben - die Kamera bleibt am Rand stehen
    Pp, Fp, Up = P.copy(), F.copy(), U.copy()
    phis = []
    for _ in range(40):
        Pp, Fp, Up = nav.drehen_um_punkt(Pp, Fp, Up, C, 0.0, 7.0)
        phis.append(nav.polwinkel(Fp - Pp))
    rand = math.pi - nav.POL_RAND
    check("Polbremse: beim Weiterziehen nach oben bleibt die Kamera genau am Rand stehen",
          all(b >= a - 1e-12 for a, b in zip(phis, phis[1:])) and abs(phis[-1] - rand) < 1e-9
          and max(phis) <= rand + 1e-9, f"zuletzt {math.degrees(phis[-1]):.4f}°, Rand {math.degrees(rand):.4f}°")
    # am Rand hin und her: kein Springen, jeder Schritt hoechstens so gross wie gezogen
    sprung = 0.0
    for k in range(40):
        vor_phi = nav.polwinkel(Fp - Pp)
        Pp, Fp, Up = nav.drehen_um_punkt(Pp, Fp, Up, C, 3.0, 0.5 if k % 2 else -0.4)
        sprung = max(sprung, abs(nav.polwinkel(Fp - Pp) - vor_phi))
    check("… am Anschlag hin und her ohne Flackern (kein Schritt größer als der Zug)",
          sprung <= math.radians(0.5) + 1e-9, f"größter Schritt {math.degrees(sprung):.4f}°")
    # aus der Draufsicht (genau am Pol): weiter hin geht nichts, weg geht voll
    Pd, Fd, Ud = nav.blick_aus("+z", P, F)
    P2, F2, U2 = nav.drehen_um_punkt(Pd, Fd, Ud, F, 0.0, 10.0)
    check("Draufsicht: weiter nach oben kippt nichts über den Pol",
          np.allclose(P2, Pd) and np.allclose(U2, Ud), str(np.round(P2, 4).tolist()))
    P2, F2, U2 = nav.drehen_um_punkt(Pd, Fd, Ud, F, 0.0, -10.0)
    check("… nach unten gezogen neigt sie um genau 10°",
          abs(math.degrees(math.pi - nav.polwinkel(F2 - P2)) - 10.0) < 1e-9 and P2[1] < Pd[1],
          f"{math.degrees(nav.polwinkel(F2 - P2)):.4f}°, y {P2[1]:.4f}")
    P2, F2, U2 = nav.drehen_um_punkt(Pd, Fd, Ud, F, 25.0, 0.0)
    check("… und dreht sich um die Hochachse (Z bleibt Blickrichtung)",
          np.allclose((F2 - P2) / np.linalg.norm(F2 - P2), (0, 0, -1)) and not np.allclose(U2, Ud))
    Pg, Fg, Ug = nav.drehen_um_punkt(P, F, U, C, 0.0, 200.0)
    check("Ein Riesenschritt (200°) kippt nicht über den Pol",
          nav.polwinkel(Fg - Pg) <= rand + 1e-9 and Ug @ np.array([0, 0, 1.0]) > 0,
          f"{math.degrees(nav.polwinkel(Fg - Pg)):.3f}°")


def test_ortho_rechnung():
    nav = _nav()
    s = nav.parallelmassstab(7.5, 30.0)
    check("Parallelmaßstab = Abstand · tan(Blickwinkel/2), zurück derselbe Abstand",
          abs(s - 7.5 * math.tan(math.radians(15.0))) < 1e-12
          and abs(nav.abstand_aus_massstab(s, 30.0) - 7.5) < 1e-12, f"{s:.6f}")
    az, ne = nav.zug_drehung(48.0, -24.0, 96.0)
    check("Zug am Gizmo: über den Durchmesser 180°, Maus rechts dreht die Kamera nach links",
          abs(az + 90.0) < 1e-12 and abs(ne + 45.0) < 1e-12, f"{az}, {ne}")


# --------------------------------------------------------------------------
# Im Fenster
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
    # Offscreen zeichnet VTK nicht; ein Zeichenaufruf mit gesetzter Groesse
    # stuerzte ab (gemessen 14.10.2026). Gezeichnet wird darum nie.
    w.plotter.render = lambda *a, **k: None
    from tests.test_fugen import _wuerfel
    w.model = _wuerfel(0.5)
    w.refresh_all()
    app.processEvents()
    _FENSTER.update(w=w, app=app)
    return w, app


def _kamera(w):
    k = w.plotter.renderer.GetActiveCamera()
    return (np.asarray(k.GetPosition(), float), np.asarray(k.GetFocalPoint(), float),
            np.asarray(k.GetViewUp(), float))


def _maus(app, wid, typ, pos, knopf, knoepfe):
    from PySide6 import QtCore, QtGui
    pos = QtCore.QPointF(pos)
    ev = QtGui.QMouseEvent(typ, pos, QtCore.QPointF(wid.mapToGlobal(pos.toPoint())),
                           knopf, knoepfe, QtCore.Qt.NoModifier)
    app.sendEvent(wid, ev)


def _klick(app, wid, pos):
    from PySide6 import QtCore
    _maus(app, wid, QtCore.QEvent.MouseButtonPress, pos, QtCore.Qt.LeftButton, QtCore.Qt.LeftButton)
    _maus(app, wid, QtCore.QEvent.MouseButtonRelease, pos, QtCore.Qt.LeftButton, QtCore.Qt.NoButton)
    app.processEvents()


def _zoom_zaehlen(w):
    zaehler = []
    alt = w.zoom_alles
    w.zoom_alles = lambda: (zaehler.append(1), alt())
    return zaehler, lambda: setattr(w, "zoom_alles", alt)


def test_fenster_aufbau():
    from statik3d.gui import masken as msk
    w, app = _fenster()
    g = getattr(w, "achsengizmo", None)
    check("Oben rechts steht das Achsen-Gizmo", isinstance(g, getattr(msk, "Achsengizmo", ())) and g.isVisible(),
          type(g).__name__)
    check("… der Ansichtswürfel ist ganz weg", not hasattr(msk, "Ansichtswuerfel")
          and not hasattr(w, "ansichtswuerfel"))
    if g is None:
        return
    check("… 112 px groß, darunter die Knöpfe alles, iso, ortho",
          g.width() == 112 and [k for k, _t, _h in g.KNOEPFE] == ["zoom", "iso", "ortho"],
          f"{g.width()} x {g.height()} px")
    w.redraw()
    app.processEvents()
    check("Kein Achsenkreuz mehr unten rechts (add_axes entfällt)",
          getattr(w.plotter.renderer, "axes_widget", None) is None)


def _ende_pos(g, name):
    from PySide6 import QtCore
    p = {q["name"]: q for q in g.punkte()}[name]
    return QtCore.QPointF(p["x"], p["y"])


def test_gizmo_klick_und_zug():
    from PySide6 import QtCore, QtGui
    w, app = _fenster()
    g = getattr(w, "achsengizmo", None)
    if g is None:
        check("Gizmo: Klick und Zug (kein Gizmo)", False)
        return
    w.blickrichtung("iso")
    app.processEvents()
    P0, F0, _U0 = _kamera(w)
    d0 = float(np.linalg.norm(P0 - F0))
    zaehler, zurueck = _zoom_zaehlen(w)
    try:
        # jedes Ende so, dass es sichtbar ist: in der Draufsicht liegt −z genau
        # hinter +z, ein Klick in die Mitte trifft dann +z
        for name in ("+x", "-y", "+z", "+y", "-x", "-z"):
            _klick(app, g, _ende_pos(g, name))
            P, F, U = _kamera(w)
            richtung = dict((n, r) for n, _a, _v, r in _nav().ACHSEN_ENDEN)[name]
            check(f"Klick auf das Ende {name}: Blick aus {name}, Blickziel und Abstand bleiben, kein Einpassen",
                  np.allclose((P - F) / np.linalg.norm(P - F), richtung) and np.allclose(F, F0)
                  and abs(float(np.linalg.norm(P - F)) - d0) < 1e-9 and not zaehler,
                  f"{np.round(P, 3).tolist()}, Zoom {len(zaehler)}")
        # Ziehen dreht um das Blickziel; ein Zug ist kein Klick (aus der
        # Schraegansicht - in der Draufsicht aendert ein Zug quer nur Bildoben)
        w.blickrichtung("iso")
        app.processEvents()
        gewaehlt = []
        g.gewaehlt.connect(gewaehlt.append)
        start = _ende_pos(g, "+x")
        P1, F1, _U1 = _kamera(w)
        _maus(app, g, QtCore.QEvent.MouseButtonPress, start, QtCore.Qt.LeftButton, QtCore.Qt.LeftButton)
        for k in range(1, 6):
            _maus(app, g, QtCore.QEvent.MouseMove, start + QtCore.QPointF(-6 * k, 4 * k),
                  QtCore.Qt.NoButton, QtCore.Qt.LeftButton)
        _maus(app, g, QtCore.QEvent.MouseButtonRelease, start + QtCore.QPointF(-30, 20),
              QtCore.Qt.LeftButton, QtCore.Qt.NoButton)
        app.processEvents()
        P2, F2, _U2 = _kamera(w)
        check("Ziehen am Gizmo dreht um das Blickziel (Blickziel und Abstand bleiben), wählt nichts",
              np.linalg.norm(P2 - P1) > 1e-3 and np.allclose(F2, F1)
              and abs(np.linalg.norm(P2 - F2) - np.linalg.norm(P1 - F1)) < 1e-9 and not gewaehlt,
              f"{np.round(P1, 3).tolist()} -> {np.round(P2, 3).tolist()}")
        # unter 4 px Weg bleibt es ein Klick
        _maus(app, g, QtCore.QEvent.MouseButtonPress, _ende_pos(g, "+y"), QtCore.Qt.LeftButton,
              QtCore.Qt.LeftButton)
        _maus(app, g, QtCore.QEvent.MouseMove, _ende_pos(g, "+y") + QtCore.QPointF(2, 1),
              QtCore.Qt.NoButton, QtCore.Qt.LeftButton)
        _maus(app, g, QtCore.QEvent.MouseButtonRelease, _ende_pos(g, "+y") + QtCore.QPointF(2, 1),
              QtCore.Qt.LeftButton, QtCore.Qt.NoButton)
        app.processEvents()
        check("… 3 px Weg sind noch ein Klick", gewaehlt == ["+y"], str(gewaehlt))
    finally:
        zurueck()


def test_gizmo_bild():
    from PySide6 import QtCore, QtGui
    w, app = _fenster()
    g = getattr(w, "achsengizmo", None)
    if g is None:
        check("Gizmo gezeichnet (kein Gizmo)", False)
        return
    w.blickrichtung("+z")              # Draufsicht: X rechts, Y oben
    app.processEvents()

    def bild(ueber):
        g._ueber = ueber
        pm = QtGui.QPixmap(g.size())
        pm.fill(QtGui.QColor("#ffffff"))
        g.render(pm)
        return pm.toImage()

    ohne, mit = bild(False), bild(True)
    g._ueber = False

    def farbe(img, p):
        c = img.pixelColor(int(round(p.x())), int(round(p.y())))
        return c.red(), c.green(), c.blue()
    # unterhalb der Mitte: dort steht nicht der Buchstabe
    unter = QtCore.QPointF(0.0, 0.7 * g.kugel_r())
    rx, gy = farbe(ohne, _ende_pos(g, "+x") + unter), farbe(ohne, _ende_pos(g, "+y") + unter)
    check("Draufsicht: +X rot gefüllt rechts, +Y grün gefüllt oben",
          rx[0] > 150 and rx[1] < 110 and gy[1] > 120 and gy[0] < 110, f"{rx} {gy}")
    hohl = farbe(ohne, _ende_pos(g, "-x"))
    check("… das negative Ende ist hohl (innen hell)", min(hohl) > 170, str(hohl))
    # dunkle Kontur: am Rand der Kugel +X ein dunkler Punkt
    p = _ende_pos(g, "+x")
    rand = min(sum(farbe(ohne, QtCore.QPointF(p.x() + g.kugel_r() + dx, p.y() + dy)))
               for dx in (-1.0, -0.5, 0.0, 0.5, 1.0) for dy in (-1.0, 0.0, 1.0))
    check("… jede Kugel hat eine dunkle Kontur", rand < 300, str(rand))
    nicht_weiss = lambda img: sum(1 for x in range(0, img.width(), 2) for y in range(0, g.GROESSE, 2)
                                  if img.pixelColor(x, y).name() != "#ffffff")
    check("Der Grundkreis erscheint nur beim Überfahren", nicht_weiss(mit) > nicht_weiss(ohne) + 200,
          f"{nicht_weiss(ohne)} -> {nicht_weiss(mit)} Punkte")


def test_knoepfe_und_ortho():
    from statik3d.gui import fenster as fen
    w, app = _fenster()
    g = getattr(w, "achsengizmo", None)
    if g is None:
        check("Knöpfe unter dem Gizmo (kein Gizmo)", False)
        return
    felder = {s: r.center() for r, s, _t in g._felder()}
    zaehler, zurueck = _zoom_zaehlen(w)
    try:
        _klick(app, g, felder["zoom"])
        check("Knopf „alles“: Zoom alles", len(zaehler) == 1, str(len(zaehler)))
        _klick(app, g, felder["iso"])
        P, F, _U = _kamera(w)
        r = (P - F) / np.linalg.norm(P - F)
        check("Knopf „iso“: isometrische Ansicht mit Zoom alles",
              np.allclose(np.abs(r), [3 ** -0.5] * 3, atol=1e-6) and len(zaehler) == 2, str(np.round(r, 3)))
    finally:
        zurueck()
    kam = w.plotter.renderer.GetActiveCamera()
    if kam.GetParallelProjection():
        _klick(app, g, felder["ortho"])
    P, F, _U = _kamera(w)
    d = float(np.linalg.norm(P - F))
    _klick(app, g, felder["ortho"])
    soll = d * math.tan(math.radians(kam.GetViewAngle()) / 2)
    check("Knopf „ortho“: Parallelprojektion, Bildgröße in der Zielebene bleibt (Maßstab = d·tan(fov/2))",
          kam.GetParallelProjection() and abs(kam.GetParallelScale() - soll) < 1e-9 * max(soll, 1)
          and g.ortho, f"Maßstab {kam.GetParallelScale():.6g}, soll {soll:.6g}")
    _P, F2, _U = _kamera(w)
    check("… das Blickziel bleibt", np.allclose(F2, F))
    gemerkt = {}
    try:
        with open(os.environ["STATIK3D_EINSTELLUNGEN"], encoding="utf-8") as f:
            gemerkt = json.load(f).get("ansicht", {})
    except (OSError, ValueError):
        pass
    check("… gemerkt in den Einstellungen (Schlüssel „ansicht“)", gemerkt.get("projektion") == "ortho",
          str(gemerkt))
    # Zoom zum Zeiger in der Parallelprojektion: der Punkt unter dem Zeiger bleibt
    ren = w.plotter.renderer
    rw = w.plotter.render_window
    alt_tief = w._oberflaeche_unter_zeiger
    w._oberflaeche_unter_zeiger = lambda x, y: None   # offscreen gibt es keinen Tiefenpuffer
    try:
        rw.SetSize(800, 600)
        x, y = 210.0, 160.0
        vorher = w._bildpunkt_in_welt(x, y)
        s0 = kam.GetParallelScale()
        w.zoom_zum_zeiger(2.0, x, 600 - 1 - y)
        ren.SetWorldPoint(*vorher, 1.0)
        ren.WorldToDisplay()
        nach = np.asarray(ren.GetDisplayPoint()[:2], float)
        check("Zoom zum Zeiger in der Parallelprojektion: Maßstab halbiert, Punkt bleibt liegen",
              abs(kam.GetParallelScale() - s0 / 2) < 1e-9 * s0 and np.linalg.norm(nach - [x, y]) < 0.5,
              f"Wanderung {np.linalg.norm(nach - [x, y]):.3f} px")
    finally:
        w._oberflaeche_unter_zeiger = alt_tief
    # zurueck: perspektivisch, im Abstand des Massstabs
    s1 = kam.GetParallelScale()
    _klick(app, g, felder["ortho"])
    P3, F3, _U = _kamera(w)
    soll_d = s1 / math.tan(math.radians(kam.GetViewAngle()) / 2)
    check("Zurück auf perspektivisch: Abstand = Maßstab / tan(fov/2), Blickziel bleibt",
          not kam.GetParallelProjection() and abs(float(np.linalg.norm(P3 - F3)) - soll_d) < 1e-9 * soll_d
          and not g.ortho, f"{np.linalg.norm(P3 - F3):.6g} / {soll_d:.6g}")
    check("… gemerkt: perspektivisch", fen.ansicht_wert("projektion") == "perspektive",
          str(fen.ansicht_wert("projektion")))
    # Beim Start gilt, was gemerkt ist
    fen.ansicht_merken("projektion", "ortho")
    w._projektion_laden()
    check("Beim Start gilt die gemerkte Projektion", bool(kam.GetParallelProjection()) and g.ortho)
    w.projektion_setzen(False)


def test_mittlere_taste_drehpunkt():
    from PySide6 import QtCore
    w, app = _fenster()
    ia = w.plotter.interactor
    stil = w.plotter.iren.style
    w.blickrichtung("iso")
    app.processEvents()
    gefragt = []
    C = np.array([1.0, 0.25, 0.8])             # ein Punkt auf der Seite x = 1, nicht das Blickziel
    alt_tief = w._oberflaeche_unter_zeiger
    w._oberflaeche_unter_zeiger = lambda x, y: (gefragt.append((x, y)), C.copy())[1]
    try:
        P0, F0, U0 = _kamera(w)
        vor = _kamerasystem(P0, F0, U0, C)
        druck = QtCore.QPointF(150, 120)
        _maus(app, ia, QtCore.QEvent.MouseButtonPress, druck, QtCore.Qt.MiddleButton, QtCore.Qt.MiddleButton)
        check("Mittlere Taste: der Drehpunkt kommt aus dem Tiefenpuffer an der Druckstelle",
              gefragt[:1] == [w._qt_nach_vtk(druck)], str(gefragt[:1]))
        check("… VTK dreht nicht selbst (eigene Drehung statt StartRotate)", stil.GetState() == 0,
              f"Zustand {stil.GetState()}")
        for k in range(1, 7):
            _maus(app, ia, QtCore.QEvent.MouseMove, druck + QtCore.QPointF(9 * k, -5 * k),
                  QtCore.Qt.NoButton, QtCore.Qt.MiddleButton)
        P1, F1, U1 = _kamera(w)
        nach = _kamerasystem(P1, F1, U1, C)
        check("Der angeklickte Punkt bleibt nach der Drehung im Bild an derselben Stelle",
              np.linalg.norm(P1 - P0) > 1e-3 and np.allclose(vor, nach, atol=1e-9),
              f"Lage {np.round(vor, 4).tolist()} -> {np.round(nach, 4).tolist()}")
        check("… das Blickziel springt nicht auf den Punkt, der Abstand bleibt",
              np.linalg.norm(F1 - C) > 0.05 and abs(np.linalg.norm(P1 - F1) - np.linalg.norm(P0 - F0)) < 1e-9)
        _maus(app, ia, QtCore.QEvent.MouseButtonRelease, druck + QtCore.QPointF(54, -30),
              QtCore.Qt.MiddleButton, QtCore.Qt.NoButton)
        app.processEvents()
        P2, _F, _U = _kamera(w)
        _maus(app, ia, QtCore.QEvent.MouseMove, druck + QtCore.QPointF(90, 0), QtCore.Qt.NoButton,
              QtCore.Qt.NoButton)
        check("Nach dem Loslassen dreht nichts mehr", np.allclose(_kamera(w)[0], P2)
              and getattr(w, "_dreh", None) is None)
        # ohne Treffer: um die Modellmitte
        w._oberflaeche_unter_zeiger = lambda x, y: None
        mitte = np.array([0.5, 0.5, 0.5])
        P0, F0, U0 = _kamera(w)
        vor = _kamerasystem(P0, F0, U0, mitte)
        _maus(app, ia, QtCore.QEvent.MouseButtonPress, druck, QtCore.Qt.MiddleButton, QtCore.Qt.MiddleButton)
        _maus(app, ia, QtCore.QEvent.MouseMove, druck + QtCore.QPointF(40, 25), QtCore.Qt.NoButton,
              QtCore.Qt.MiddleButton)
        _maus(app, ia, QtCore.QEvent.MouseButtonRelease, druck + QtCore.QPointF(40, 25),
              QtCore.Qt.MiddleButton, QtCore.Qt.NoButton)
        P1, F1, U1 = _kamera(w)
        check("Ohne Treffer dreht die mittlere Taste um die Modellmitte",
              np.linalg.norm(P1 - P0) > 1e-3 and np.allclose(vor, _kamerasystem(P1, F1, U1, mitte), atol=1e-9))
        # Polbremse im Fenster: aus der Draufsicht nach unten gezogen (Kamera hoeher) kippt nichts
        w.blickrichtung("+z")
        app.processEvents()
        P0, F0, U0 = _kamera(w)
        _maus(app, ia, QtCore.QEvent.MouseButtonPress, druck, QtCore.Qt.MiddleButton, QtCore.Qt.MiddleButton)
        _maus(app, ia, QtCore.QEvent.MouseMove, druck + QtCore.QPointF(0, 60), QtCore.Qt.NoButton,
              QtCore.Qt.MiddleButton)
        P1, F1, U1 = _kamera(w)
        _maus(app, ia, QtCore.QEvent.MouseMove, druck + QtCore.QPointF(0, 0), QtCore.Qt.NoButton,
              QtCore.Qt.MiddleButton)
        P2, F2, _U2 = _kamera(w)
        _maus(app, ia, QtCore.QEvent.MouseButtonRelease, druck, QtCore.Qt.MiddleButton, QtCore.Qt.NoButton)
        check("Draufsicht: weiter nach oben gezogen kippt nichts, zurück gezogen neigt sie",
              np.allclose(P1, P0) and np.allclose(U1, U0) and P2[2] < P0[2] - 1e-6
              and _nav().polwinkel(F2 - P2) < math.pi - _nav().POL_RAND + 1e-9,
              f"{np.round(P0, 3).tolist()} / {np.round(P1, 3).tolist()} / {np.round(P2, 3).tolist()}")
    finally:
        w._oberflaeche_unter_zeiger = alt_tief


def main():
    tests = [test_gizmo_rechnung, test_klick_richtungen, test_drehen_um_punkt, test_ortho_rechnung,
             test_fenster_aufbau, test_gizmo_klick_und_zug, test_gizmo_bild,
             # die mittlere Taste vor den Knoepfen: dort bekommt das Renderfenster
             # eine Groesse, und danach darf nichts mehr den Tiefenpuffer lesen
             test_mittlere_taste_drehpunkt, test_knoepfe_und_ortho]
    for t in tests:
        try:
            t()
        except Exception as ex:                  # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{t.__name__} lief durch", False, f"{type(ex).__name__}: {ex}")
    n_ok = sum(1 for _n, ok in RESULTS if ok)
    print(f"\n{n_ok}/{len(RESULTS)} Prüfungen bestanden")
    sys.stdout.flush()
    os._exit(0 if n_ok == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
