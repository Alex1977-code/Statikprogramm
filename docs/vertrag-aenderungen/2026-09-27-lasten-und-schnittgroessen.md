# Vorschlag zur Vertragsänderung: Lasten im Detailmodell, Vorzeichen der Schnittgrößen

**Von:** Session B (Volumenmodul `volumen3d`), 27.09.2026
**Betrifft:** `Schnittstellenvertrag_Statik3D_FCM.md` 2.0.0, Abschnitte 5 und 6
**Versionsstufe (Abschnitt 9):** Minor → 2.1.0 (nur neue optionale Felder und eine
Klarstellung, keine Änderung bestehender Bedeutung)

Der Vertrag wird nicht von dieser Sitzung geändert; der Anwender entscheidet und bringt die
Änderung als eigenen Pull Request auf `main`.

---

## 1. Lasten im Detailmodell (`detail.py`)

**Anlass.** `DetailModelSpec` kennt nur die Kopplung über Schnittebenen. Ein Detail kann aber
eigene Lasten tragen, die das Globalmodell nicht liefert: Wasserdruck auf die Detailoberfläche,
Eigengewicht des Ausschnitts, Kontaktdruck einer Auflagerplatte. Teilprojekt 1 rechnet solche
Lasten schon über die interne Schnittstelle (`FcmProblem.traktion / druck / volumenlast`,
verifiziert am Lamé-Zylinder und an der Kirsch-Platte), die Oberfläche kann sie ohne
Vertragsfeld aber nicht anbieten.

**Vorschlag.** Zwei optionale Felder mit leerem Standard, Typ `SurfaceLoad` aus `nonlinear.py`
wiederverwendet (Flächenauswahl über `SurfaceSelector.named_surface` = Name der CSG-Grundform,
`box` oder `cylinder`):

```python
@dataclass(frozen=True)
class DetailModelSpec:
    ...
    loads: tuple[SurfaceLoad, ...] = ()            # Druck, Traktion oder Resultierende je Fläche
    body_load: np.ndarray | None = None            # (3,) N/mm³, z. B. Eigengewicht rho*g
```

`SurfaceLoad.load_case_id` ordnet die Last dem `ResultKey.load_case_id` zu; Lasten ohne
passenden Key werden für diesen Key nicht angesetzt. `pressure` positiv drückt auf die
Fläche (t = −p n), wie in 6a.

**Auswirkung.** Hauptprogramm: Maske „Lasten am Detail“ im Knoten „Detailmodelle (Volumen)“.
`volumen3d`: Abbildung auf die vorhandenen Aufrufe, keine Rechenänderung. Stubs: unverändert
gültig (leere Vorgabe).

---

## 2. Vorzeichen und Seite der Schnittgrößen (`coupling.py`)

**Anlass.** `SectionForces` ist beschrieben als „Resultierende am Schnitt, bezogen auf
`CutPlane.origin`, globale Achsen“. Offen bleibt, **auf welche Seite** sich die Resultierende
bezieht. Der Stub (`StubGlobalFieldProvider.section_forces`) liefert unabhängig von
`CutPlane.normal` die Schnittgrößen der Stabkonvention (Kraft auf die +x-Seite). Die FCM-Seite
integriert die Traktion mit der Normalen aus dem Detail heraus, F = ∫ σ·n dA, also die Kraft,
die der abgeschnittene Teil auf das Detail ausübt. Für die Ebene mit Normale −x haben beide
das entgegengesetzte Vorzeichen; die Kopplungskontrolle meldet dann eine Abweichung von
rund 200 %, obwohl beide Seiten stimmen (gemessen 27.09.2026, `packages/volumen3d/volumen3d/tests/test_vertrag_fcm.py`).

**Vorschlag.** Klarstellung im Docstring von `SectionForces` und `GlobalFieldProvider.section_forces`:

> Kraft und Moment, die der abgeschnittene Teil des Globalmodells auf das Detail ausübt
> (Traktion σ·n integriert über den Schnitt, n = `CutPlane.normal`, aus dem Detail heraus).
> Für einen Stab mit lokaler x-Achse in Richtung n sind das die Schnittgrößen der Stabkonvention,
> gegen n das Negative davon.

Der Stub wird entsprechend angepasst (Vorzeichen aus `plane.normal[0]`).

**Auswirkung.** Hauptprogramm: der spätere echte Provider setzt das Vorzeichen aus der Lage der
Schnittebene zum Stab. `volumen3d`: keine Änderung; die Kopplungskontrolle wird für beide
Ebenen aussagekräftig. Vertragsprüfung: eine zusätzliche Zeile für die Ebene mit Normale −x.

---

## 3. Hinweis zur Verschiebungskopplung (keine Vertragsänderung)

Die ebene Querschnittskinematik eines Stabs enthält keine Querkontraktion und keine
Schubverformung. `volumen3d` gibt darum an Schnittebenen nur die Normalkomponente punktweise
vor und in der Ebene die drei Resultierenden (Querkräfte, Torsion) als Mittelwertzwänge; die
Kopplungskontrolle weist Abweichungen zum schubstarren Globalmodell aus (Segment 3 h:
Moment +37 %, unabhängig durch Timoshenko-Rechnung bestätigt). Liefert der Provider eines
Tages Timoshenko-Kinematik oder Verwölbung, ändert sich am Vertrag nichts.
