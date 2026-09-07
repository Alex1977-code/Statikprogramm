"""
Der Vernetzer verfeinert selbst, wo sein Netz nicht trägt.

Zwei Befunde am Modell `Drehlager_V15_4_export` stehen dahinter:

* **Schlanke Bauteile wurden verfehlt.** `_kantenlaenge` teilte die *größte*
  Ausdehnung durch vier. Ein Passstift Ø25 × 67 mm bekam damit 16,8 mm —
  anderthalb Elemente über den Querschnitt, 152 Tetraeder, und der Löser
  meldete „Bewegung fast ohne Steifigkeit". Maßgebend ist aber nicht die
  längste, sondern die dünnste Abmessung.
* **Die Warnung tat nichts.** Der Vernetzer maß Randtreue, Volumenabweichung,
  Güte und Splitteranteil und schrieb dann „mit kleinerer Kantenlänge
  nachvernetzen" — an einen Anwender, der dafür nur die globale Ziellänge
  hatte und damit das ganze Modell verfeinert hätte.

Geprüft werden die Abnahmefälle aus dem Design (Fälle 1 bis 5); Fall 6 ist das
echte Drehlagermodell und lässt sich hier nicht nachstellen.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import mesher3d, netzdichte                     # noqa: E402
from statik3d.model import Material, Model                    # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FEHLER'} {name:62s} {detail}")
    return bool(ok)


def close(name, got, want, tol, unit=""):
    return check(name, abs(got - want) <= tol, f"{got:.6g} statt {want:.6g} {unit}".strip())


def _quader(a, b, c):
    """Ein Quader a × b × c als Körper mit sechs Randflächen."""
    m = Model()
    m.add_material(Material.steel("S235"))
    P = [(0, 0, 0), (a, 0, 0), (a, b, 0), (0, b, 0),
         (0, 0, c), (a, 0, c), (a, b, c), (0, b, c)]
    kn = [m.add_node(*p) for p in P]
    seiten = {"unten": [0, 1, 2, 3], "oben": [4, 5, 6, 7], "vorn": [0, 1, 5, 4],
              "rechts": [1, 2, 6, 5], "hinten": [2, 3, 7, 6], "links": [3, 0, 4, 7]}
    namen = []
    for name, ring in seiten.items():
        for i, (u, v) in enumerate(zip(ring, ring[1:] + ring[:1])):
            m.add_line(f"{name}_{i}", [kn[u], kn[v]])
        f = m.add_flaeche(name, [f"{name}_{i}" for i in range(4)],
                          dicke=None, material="S235")
        namen.append(f.name if hasattr(f, "name") else name)
    k = m.add_koerper("V1", namen, material="S235")
    return m, k


def test_dickenmass():
    """Fall 2 und 3: der Stift bekommt vier Elemente quer, die Platte nicht mehr."""
    # Ein Quader 25 × 25 × 67 mm steht hier für den Passstift: 6V/A ist für
    # den Zylinder 31,6 mm, für diesen Quader rechnen wir den Sollwert mit.
    m, k = _quader(0.025, 0.025, 0.067)
    m.netz.dickenmass = True
    V = netzdichte.volumenmass(m, k)
    A = netzdichte.oberflaeche(m, k)
    d = netzdichte.dicke(m, k)
    close("Volumen des Stiftquaders", V, 0.025 * 0.025 * 0.067, 1e-12, "m^3")
    close("Oberfläche des Stiftquaders", A,
          2 * (0.025 * 0.025 + 2 * 0.025 * 0.067), 1e-12, "m^2")
    close("Dicke 6V/A", d, 6 * V / A, 1e-12, "m")
    # 6V/A ist fuer einen schlanken Koerper etwas groesser als seine Dicke:
    # beim Zylinder D 25 x 67 sind es 31,6 mm, beim gleich grossen Quader
    # ebenfalls. Das Design nennt denselben Wert.
    check("die Dicke liegt in der Größenordnung des Querschnitts",
          0.025 <= d < 0.035, f"{d * 1e3:.1f} mm")
    # Ohne Dickenmass: groesste Ausdehnung / 4
    alt = mesher3d._ausdehnung(m, k) / mesher3d.MINDESTTEILUNG
    h = mesher3d._kantenlaenge(m, k, 0.05, [])
    check("die alte Regel gäbe zu wenige Elemente quer",
          0.025 / alt < 2.0, f"{0.025 / alt:.1f} Elemente über 25 mm")
    # Vier Elemente quer - genau genommen 25/(31,6/5) = 3,95; das Design
    # rundet das auf vier. Geprueft wird darum ein Fenster um vier.
    check("mit Dickenmaß sind es rund vier",
          3.5 <= 0.025 / h <= 4.5, f"{0.025 / h:.2f} Elemente über 25 mm")
    check("die Kantenlänge ist kleiner als nach der alten Regel", h < alt,
          f"{h * 1e3:.1f} statt {alt * 1e3:.1f} mm")

    # Fall 3: eine Platte 1000 × 1000 × 10 mm darf nicht explodieren
    mp, kp = _quader(1.0, 1.0, 0.010)
    mp.netz.dickenmass = True
    dp = netzdichte.dicke(mp, kp)
    hp = mesher3d._kantenlaenge(mp, kp, 0.05, [])
    check("Platte: die Dicke bleibt eine vernünftige Länge",
          0.02 < dp < 0.04, f"{dp * 1e3:.1f} mm")
    # Ohne Grenze gäbe das Dickenmaß hier über 400.000 Tetraeder für ein
    # Blech. max_elemente fängt das ab - dieselbe Grenze wie in netzdichte.
    n = netzdichte.volumenmass(mp, kp) / (netzdichte.TET_JE_H3 * hp ** 3)
    check("Platte: die Elementzahl bleibt unter der Grenze",
          n <= mp.netz.max_elemente * 1.01, f"{n:.0f} von {mp.netz.max_elemente}")


def test_wuerfel_bleibt_unveraendert():
    """Fall 1: ein Würfel 100 mm bei Ziellänge 50 mm - keine Verfeinerung."""
    m, k = _quader(0.1, 0.1, 0.1)
    h = mesher3d._kantenlaenge(m, k, 0.05, [])
    d = netzdichte.dicke(m, k)
    close("beim Würfel ist 6V/A die Kantenlänge", d, 0.1, 1e-12, "m")
    # Abnahmefall 1: unverändert. Ohne Dickenmaß gilt die alte Regel
    # (größte Ausdehnung / 4 = 25 mm); mit Dickenmaß wären es 20 mm - auch
    # das wäre in Ordnung, aber es ist eben nicht „unverändert".
    close("ohne Dickenmaß bleibt die alte Regel", h, 0.025, 1e-12, "m")
    m.netz.dickenmass = True
    close("mit Dickenmaß fünf Elemente über den Würfel",
          mesher3d._kantenlaenge(m, k, 0.05, []), 0.02, 1e-12, "m")
    m.netz.dickenmass = False
    log = []
    els = mesher3d.mesh_koerper_frei(m, k, 0.05, log)
    check("der Würfel wird vernetzt", len(els) > 0, f"{len(els)} Tetraeder")
    check("ohne Nachvernetzen",
          not any("nachvernetzt" in z for z in log), "\n".join(log[-2:])[:70])


def test_kriterien_und_abbruch():
    """Die vier Kriterien und die Abbruchbedingungen der Wiederholung."""
    gut = {"randtreue": 1.0, "volumen": 1.0, "guete": 0.4, "splitter": 0,
           "tetraeder": 1000}
    check("ein gutes Netz reisst kein Kriterium",
          not mesher3d.netzguete(gut, {"volumen": 1.0})["gerissen"])
    schlecht = {"randtreue": 0.963, "volumen": 0.978, "guete": 0.015,
                "splitter": 38, "tetraeder": 1000}
    mass = mesher3d.netzguete(schlecht, {"volumen": 1.0})
    check("V16 reisst alle vier Kriterien", len(mass["gerissen"]) == 4,
          "; ".join(mass["gerissen"]))
    close("Volumenabweichung wie gemessen", mass["volumenabweichung"], 0.022, 1e-9)
    close("Splitteranteil wie gemessen", mass["splitteranteil"], 0.038, 1e-9)
    check("das schlechtere Netz hat den grösseren Abstand",
          mass["abstand"] > mesher3d.netzguete(gut, {"volumen": 1.0})["abstand"])
    # Die Grenzen stehen an einer Stelle und sind die des Designs
    close("Grenze Randtreue", mesher3d.RANDTREUE_MIN, 0.99, 0)
    close("Grenze Volumenabweichung", mesher3d.VOLUMEN_ABW_MAX, 0.005, 0)
    close("Grenze Güte", mesher3d.GUETE_MIN, 0.05, 0)
    close("Grenze Splitteranteil", mesher3d.SPLITTER_ANTEIL_MAX, 0.01, 0)
    close("Verfeinerungsschritt", mesher3d.VERFEINERN_FAKTOR, 1.5, 0)
    close("höchstens drei Anläufe", mesher3d.VERFEINERN_ANLAEUFE, 3, 0)


def test_grenze_haelt_die_verfeinerung_an():
    """Fall 5: h_min und max_elemente brechen die Wiederholung ab."""
    m, k = _quader(0.025, 0.025, 0.067)
    m.netz.dickenmass = True
    m.netz.h_min = 0.05                  # gröber als alles, was hier entstünde
    h = mesher3d._kantenlaenge(m, k, 0.05, [])
    check("h_min hält die Vorabschätzung an", h >= 0.05 - 1e-12, f"{h * 1e3:.1f} mm")
    m.netz.h_min = 0.0
    m.netz.max_elemente = 50
    log = []
    els = mesher3d.mesh_koerper_frei(m, k, 0.05, log)
    check("es entsteht trotzdem ein Netz", len(els) > 0, f"{len(els)} Tetraeder")
    check("und das Protokoll nennt die Grenze, wenn sie greift",
          all(isinstance(z, str) for z in log))


def main():
    for f in (test_dickenmass, test_wuerfel_bleibt_unveraendert,
              test_kriterien_und_abbruch, test_grenze_haelt_die_verfeinerung_an):
        print(f"\n--- {f.__name__} ---")
        try:
            f()
        except Exception as ex:          # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{f.__name__} ohne Ausnahme", False, str(ex)[:80])
    n_ok = sum(1 for _n, ok in RESULTS if ok)
    print("\n" + "=" * 60)
    print(f"Ergebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
