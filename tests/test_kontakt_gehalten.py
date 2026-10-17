"""Koerper, die seitlich nur ueber reibungsfreien Kontakt und Staebe ohne
Quersteifigkeit gehalten sind (Auftrag vom 17.10.2026).

Anlass: Die 16 Ankerplatten am Drehlager haengen nur am Anker (Fachwerkstab)
und an einem reibungsfreien Kontakt zu V14 - in RFEM genauso (Freigabe Typ 1,
Federkonstante 0 in der Ebene). Plastisch am feinen Netz rutschte eine Platte
weg, und erst die Mechanismus-Erkennung meldete es. Der Anwender: „gut wäre
ein verständlicher hinweis in statik3D wenn so etwas auftritt“.

Geprueft wird an einem Klotz (Einheitswuerfel) auf einem festen Block, nur
ueber das Kontaktpaar „Fuge“ verbunden, mit einem Zugstab S1, der ueber einen
starren Koerper (RBE2) an der Oberseite des Klotzes haengt und unten fest ist:

* ohne Reibung: ein Hinweis mit Koerper, Kontakt, Gegenkoerper, Stab, freien
  Richtungen und Abhilfe; elastisch als INFORMATION, plastisch als WARNUNG vor
  dem Start (Protokoll; in der Oberflaeche ein Dialog wie beim Kreisring),
* mit μ = 0,2 und seitlich gehalten: kein Hinweis,
* drei gleiche Kloetze: eine Zeile,
* die Traglastmeldung nennt den Koerper, wenn der Ort in ihm liegt.

Aufruf:  python -m tests.test_kontakt_gehalten
"""
import os
import sys
import types

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import plastizitaet as pl, singular as sg, solver       # noqa: E402
from statik3d.model import Section                                    # noqa: E402
from tests.test_freie_teile import platten_auf_block                  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FEHLER'} {name:84s} {str(detail)[:260]}")
    return bool(ok)


def kloetze(n: int = 1, mu: float = 0.0, seitlich: bool = False, plast: bool = False):
    """``n`` Kloetze P1 … Pn auf dem Block, je ein Zugstab S1 … Sn ueber RBE2."""
    m = platten_auf_block(n, mu=mu)
    m.add_section(Section.circle("Rund 20", 0.02))
    for i in range(n):
        e = next(e for e in m.elements if e.group == f"P{i + 1}")
        oben = [int(k) for k in e.nodes[4:8]]
        x0 = 2.0 * i
        kopf = int(m.add_node(x0 + 0.5, 0.5, 2.0))
        fuss = int(m.add_node(x0 + 0.5, 0.5, -2.0))
        m.add_starrkoerper(kopf, oben, art="RBE2", name=f"Kopf {i + 1}")
        st = m.add_element("truss", [kopf, fuss], "S235", "Rund 20", group="Anker")
        m.add_member(f"S{i + 1}", [st])
        m.fix(fuss, "all")
        if seitlich:
            m.fix(oben[0], [0, 1])
            m.fix(oben[1], [1])
    m.active_case = "LF1"
    m.plastizitaet = pl.Plastizitaet(an=bool(plast))
    return m


def test_erkennung():
    print("\n--- 1. Erkennung vor der Rechnung ---")
    h = sg.kontakt_gehalten(kloetze())
    check("ohne Reibung: genau ein Eintrag, der Klotz P1", len(h) == 1 and h[0]["koerper"] == ["P1"],
          str([x.get("koerper") for x in h]))
    if h:
        t = h[0]["text"]
        check("… der Text: nur über reibungsfreien Kontakt zu Block gehalten",
              "nur über reibungsfreien Kontakt" in t and "Block" in t and "Fuge" in t, t)
        check("… er nennt den Stab ohne Quersteifigkeit", "S1" in t and "Quersteifigkeit" in t, t)
        check("… und die freien Richtungen (Ebene x, y und Drehung um z)",
              "(x, y)" in h[0]["bewegung"] and "um z" in h[0]["bewegung"], h[0]["bewegung"])
        check("… elastisch und symmetrisch bleibt er liegen, plastisch kann er wegrutschen",
              "bleibt er liegen" in t and "wegrutschen" in t, t)
        check("… Abhilfe: Reibbeiwert (μ = 0,2 Stahl/Stahl) oder seitlich halten",
              "Reibbeiwert" in t and "μ = 0,2" in t and "seitlich halten" in t, t)
        check("… Art: rutscht", h[0].get("art") == "rutscht", h[0].get("art"))
    check("mit μ = 0,2: kein Hinweis", not sg.kontakt_gehalten(kloetze(mu=0.2)), "")
    check("seitlich gehalten: kein Hinweis", not sg.kontakt_gehalten(kloetze(seitlich=True)), "")
    m = platten_auf_block(1)
    h = sg.kontakt_gehalten(m)
    check("Platte ohne Anker (nur Kontakt): ebenfalls ein Hinweis, ohne Stab",
          len(h) == 1 and "Stab" not in h[0]["text"], str([x.get("text", "")[:120] for x in h]))
    h = sg.kontakt_gehalten(kloetze(3))
    check("drei gleiche Klötze: eine Zeile „3 Körper P1, P2, P3“",
          len(h) == 1 and h[0]["anzahl"] == 3 and h[0]["text"].startswith("3 Körper P1, P2, P3"),
          str([x.get("text", "")[:120] for x in h]))
    if h:
        check("… mit allen drei Stäben", all(s in h[0]["text"] for s in ("S1", "S2", "S3")), h[0]["text"])


def test_stufe_und_protokoll():
    print("\n--- 2. Information elastisch, Warnung plastisch – vor dem Start ---")
    z = sg.kontakt_gehalten_zeilen(kloetze())
    check("elastisch: eine Zeile INFORMATION", len(z) == 1 and z[0].startswith("INFORMATION: "), str(z)[:200])
    z = sg.kontakt_gehalten_zeilen(kloetze(plast=True))
    check("plastisch: eine Zeile „WARNUNG – BITTE LESEN“", len(z) == 1 and z[0].startswith("WARNUNG – BITTE LESEN: "),
          str(z)[:200])
    check("mit Reibung: keine Zeile", not sg.kontakt_gehalten_zeilen(kloetze(mu=0.2, plast=True)), "")
    meld = []
    r = solver.solve_static(kloetze(), case="LF1", progress=lambda t, *a: meld.append(str(t)))
    check("die Rechnung (elastisch) meldet die Zeile vor dem Start ins Protokoll",
          any(x.startswith("INFORMATION: ") and "reibungsfreien Kontakt" in x for x in meld),
          [x for x in meld if "Kontakt" in x][:2])
    check("… und rechnet", r is not None and r.u is not None, "")


def test_oberflaeche():
    print("\n--- 3. Oberfläche: plastisch fragt ein Dialog wie beim Kreisring ---")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
    os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
    from PySide6 import QtWidgets
    from statik3d.gui.main import MainWindow
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = MainWindow()
    w._fragen_knoepfe = lambda *a, **k: True
    gefragt = []
    w._kontakthalt_frage = lambda h, _g=gefragt: (_g.append(h), "abbrechen")[1]
    w.model = kloetze(plast=True)
    check("plastisch, Antwort „Abbrechen“: es wird nicht gerechnet", w._kontakthalt_bestaetigen() is False
          and len(gefragt) == 1, f"{len(gefragt)} Fragen")
    w._kontakthalt_frage = lambda h, _g=gefragt: (_g.append(h), "rechnen")[1]
    check("… „Trotzdem rechnen“: es wird gerechnet", w._kontakthalt_bestaetigen() is True, "")
    check("… das Protokoll trägt die Warnung",
          "WARNUNG – BITTE LESEN" in w.log.toPlainText() and "reibungsfreien Kontakt" in w.log.toPlainText(), "")
    gefragt.clear()
    w.model = kloetze(plast=False)
    check("elastisch: keine Frage, es wird gerechnet", w._kontakthalt_bestaetigen() is True and not gefragt, "")
    w.model = kloetze(mu=0.2, plast=True)
    check("mit Reibung: keine Frage", w._kontakthalt_bestaetigen() is True and not gefragt, "")
    w.close()


def test_traglastmeldung():
    print("\n--- 4. Kein Gleichgewicht mit Ort im Klotz: die Meldung nennt den Körper ---")
    m = kloetze()
    el = next(i for i, e in enumerate(m.elements) if e.group == "P1")
    konv = types.SimpleNamespace(eps_p_eq={})
    fehl = types.SimpleNamespace(eps_p_eq={el: np.array([0.3])})
    ort = pl.traglast_ort(m, konv, fehl, None, None)
    u = pl.traglast_ursache(ort)
    check("Ort im Klotz P1: „örtlicher Mechanismus: Körper P1 rutscht, er ist nur über reibungsfreien Kontakt "
          "gehalten – Reibung ansetzen oder halten“",
          u.startswith("örtlicher Mechanismus: Körper P1 rutscht, er ist nur über reibungsfreien Kontakt gehalten "
                       "– Reibung ansetzen oder halten"), u)
    tl = {"lastfaktor": 0.5, "versuch": 0.75, "stufe": 3, "ort": ort, "ursache": u}
    t = pl.traglast_text(tl)
    check("… im Satz des Anwenders", t.startswith("Kein Gleichgewicht gefunden bei Laststufe 3") and
          "Mögliche Ursache: örtlicher Mechanismus: Körper P1 rutscht" in t, t)
    mech = {"knoten": int(m.elements[el].nodes[0]), "text": "Mechanismus: …"}
    ort = pl.traglast_ort(m, konv, types.SimpleNamespace(eps_p_eq={}), mech, None)
    check("ohne Zuwachs von ε_p: der Knoten des Mechanismus im Klotz genügt",
          pl.traglast_ursache(ort).startswith("örtlicher Mechanismus: Körper P1"), pl.traglast_ursache(ort))
    m = kloetze(mu=0.2)
    ort = pl.traglast_ort(m, konv, fehl, None, None)
    check("mit Reibung: nicht als reibungsfrei gehalten gemeldet", "reibungsfreien" not in pl.traglast_ursache(ort),
          pl.traglast_ursache(ort))


def main():
    for f in (test_erkennung, test_stufe_und_protokoll, test_traglastmeldung, test_oberflaeche):
        try:
            f()
        except Exception as ex:                     # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{f.__name__} ohne Ausnahme", False, f"{type(ex).__name__}: {ex}")
    n_f = sum(1 for _n, ok in RESULTS if not ok)
    print(f"\n{len(RESULTS) - n_f} von {len(RESULTS)} Prüfungen bestanden")
    sys.stdout.flush()
    os._exit(1 if n_f else 0)


if __name__ == "__main__":
    main()
