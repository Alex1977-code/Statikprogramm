# Vorschlag: Volumenlast je Lastfall und Faktoren für Kombinationen (Minor 2.2.0)

**Von:** Session B (Volumenmodul `volumen3d`), 28.09.2026, nach dem Gutachten zu den
Teilprojekten 3 und 4. **Status:** offen, Entscheidung des Anwenders.

## Anlass

Vertrag 2.1.0 führt `DetailModelSpec.body_load` als eine Volumenlast (3,) in N/mm³ ein, ohne
Zuordnung zu einem Lastfall. Das Volumenmodul setzt sie darum für **jeden** `ResultKey` an
(dokumentiert in `docs/Theoriehandbuch.md` 11.9, geprüft in `test_vertrag_fcm.test_lasten`).
Physikalisch stimmt das nur, wenn jeder Lastfall des Globalmodells das Eigengewicht enthält. Für
einen Lastfall ohne Eigengewicht, etwa „Wind“, liefern die Randverschiebungen des Globalmodells
ρ·g·V nicht mit; das Detail bekommt dann eine Last, die das Globalmodell nicht trägt, und die
Kopplungskontrolle weicht um genau diese Resultierende ab.

Dazu kommt: bei einem Kombinationsschlüssel (`ResultKey.combination_id`) greifen die
Flächenlasten nur über `load_case_id` und ohne Teilsicherheitsbeiwerte; auch `body_load` bekommt
keinen Faktor. Für Stahldetails ist der Betrag meist klein, für Wasserdruck auf großen Flächen
nicht.

## Vorgeschlagene Änderung

1. `DetailModelSpec.body_load` wird zu `body_loads: tuple[BodyLoad, ...] = ()` mit
   `BodyLoad(id: str, load_case_id: str, b: np.ndarray)` (N/mm³). Übergang: `body_load` bleibt
   in 2.2.0 als veraltetes Feld erhalten und wirkt wie heute auf alle Keys; das Hauptprogramm
   setzt künftig `body_loads`.
2. Für Kombinationen: `DetailModelSpec.combinations: dict[str, dict[str, float]]` (Kombinations-ID →
   Lastfall-ID → Faktor), damit das Volumenmodul Flächen- und Volumenlasten eines
   Kombinationsschlüssels mit denselben Faktoren überlagert, die das Globalmodell für die
   Randverschiebungen benutzt. Alternative: das Hauptprogramm löst Kombinationen selbst auf und
   übergibt nur Lastfall-Keys; dann genügt Punkt 1.
3. Vertragstext Abschnitt 6: Zuordnung wie bei `SurfaceLoad` („Lasten ohne passenden Key werden
   für diesen Key nicht angesetzt“), Kombinationsregel nach Punkt 2.

**Versionsstufe:** Minor (2.2.0), abwärtskompatibel durch das Übergangsfeld.

## Auswirkung

- **Hauptprogramm:** Maske „Lasten am Detail“ bekommt eine Lastfallspalte für Volumenlasten;
  die Kombinationsfaktoren liegen dort ohnehin vor.
- **Volumenmodul:** `_lasten_vorbereiten` ordnet Volumenlasten wie Flächenlasten je Lastfall zu;
  für Kombinationsschlüssel wird die rechte Seite als Faktorsumme gebildet. Aufwand gering, die
  Lastvektoren werden schon je Lastfall-ID gehalten.
- **Stub:** trägt die neuen Felder im Protokoll, rechnet weiter nie still.
