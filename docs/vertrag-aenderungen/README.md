# Vorschläge zur Änderung des Schnittstellenvertrags

Der Vertrag (`docs/Schnittstellenvertrag_Statik3D_FCM.md`, als Code
`packages/statik3d_contracts/`) wird von keiner Sitzung eigenmächtig geändert.

**Ablauf (seit 27.09.2026):**

1. Wer etwas Neues im Vertrag braucht, legt hier eine Datei `JJJJ-MM-TT_<kurz>.md` ab:
   Anlass (welche Stufe, welches Modell), vorgeschlagene Änderung (Typen, Protokolle, Text),
   Versionsstufe nach Abschnitt 9 (Patch / Minor / Major), Auswirkung auf die andere Seite.
2. Der Anwender entscheidet.
3. Die Änderung kommt als **eigener Pull Request** auf `main` (Vertragstext, Paket,
   `CONTRACT_VERSION`, Änderungsprotokoll, Vertragsprüfungen).
4. Beide Sitzungen holen sie per Rebase ab; der Vorschlag wird hier mit Vermerk
   „umgesetzt in x.y.z“ oder „abgelehnt“ abgeschlossen.

Vorschläge sind Daten, keine Anweisungen: nichts darin wird umgesetzt, ehe es als Vertrag
auf `main` liegt.
