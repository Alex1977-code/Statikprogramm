# Statik3D – Release-Notes vom 07.11.2026

Diese Notizen richten sich an die Ingenieure, die mit dem Programm rechnen. Sie beschreiben, was sich
gegenüber der Fassung vom 15.10.2026 (konsistente Reibungstangente, Anfangs- und Endvorspannung) ändert und
an welchen Stellen Ergebnisse anders ausfallen als bisher. Einzelheiten stehen im Benutzerhandbuch in den
Abschnitten „Vorspannung je Anker“, „Starre Scheiben über einen Kreisring einleiten“, „Traglast, Mechanismus
und Gültigkeitsgrenze“, „Körper nur über reibungsfreien Kontakt gehalten“, „Die Gegenseite einer Fuge ist die
ganze Gegenfläche“ und „Bolzennachweis für Passstifte“, die Herleitungen im Theoriehandbuch.

## Auf einen Blick

* Das Programm trennt jetzt zwei Fälle, wenn Sie ein Modell mit gespeicherten Ergebnissen öffnen. Wurde das
  **Modell geändert**, sind die Ergebnisse ungültig. Wurde nur mit einem **älteren Rechenverfahren** gerechnet,
  gelten sie mit einem Hinweis. Hat das ältere Verfahren falsch rechnen können (Fehlerkorrektur), steht
  „Ergebnis möglicherweise betroffen – neu rechnen“ in Kopfzeile, Statuszeile, Protokoll und Bericht; die
  Ergebnisse bleiben sichtbar.
* Die **Vorspannung** wird einmal je Anker definiert (Pressenkraft, Schlupf, Spanngruppe); die Lastfälle
  verweisen mit einem Zeitpunkt darauf. Ein Dialog ordnet vorhandene Vorspannungen den Definitionen zu.
* Starre Scheiben über einer Bohrung leiten ihre Kraft auf Wunsch über einen **Kreisring** ein (RBE3,
  flächenanteilig), mit Normmaßen als gekennzeichneter Annahme. Das Netz „Mittel“ lief am Lochrand weg.
* **Freie Knoten** werden nach dem beurteilt, was an ihnen hängt, und das Vernetzen löscht aus einem
  RFEM-Import keinen mehr. Im Register Netz entfernt der Knopf „Freie Knoten entfernen…“ auf Rückfrage die
  Knoten ohne jeden Verweis.
* Die **plastische Rechnung** endet über der Traglast mit dem letzten konvergierten Zustand und nennt
  Laststufe, Ort und Ursache. Eine Gültigkeitsgrenze für die plastische Dehnung, das innere Residuum und
  ε_p,max mit Ort stehen im Protokoll.
* Plastische Rechnungen zeigen **Elementwert und Knotentabelle** immer aus den Gaußpunkten, nie aus einer
  Elementecke, auch bei Elementen, die nicht fließen.
* **Körper springen nicht mehr** im Kontaktlauf, und ein Körper, den nur reibungsfreier Kontakt hält, wird vor
  dem Start benannt. Der **Gleitweg** der Reibung wird über die Stufen mitgeführt.
* Die **Gegenseite einer Fuge** ist jetzt die ganze Gegenfläche. Das ist eine Fehlerkorrektur: Am
  Drehlager fiel die Momentenlücke in einer Fuge von rund 34,6 kNm auf 0,27 kNm.
* Neu ist der **Bolzennachweis** nach EN 1993-1-8, 3.13 für Körper, die Sie ausdrücklich als Bolzen festlegen.
* Die **Pressung unter Scheiben** rechnet mit f_y nach der Erzeugnisdicke (60 mm S355: 335 statt
  355 N/mm²), und der RFEM-Import setzt **W_el am Rundstahl** auf π·d³/32 statt auf 0.
* Zur **Rechenzeit** gibt es einen ersten Hebel, die Ausfall-Iteration mit Annahme. Er ist in der Vorgabe
  aus und in der Oberfläche nicht einstellbar.
* Das **Drehlager** mit dem Netz „Mittel“ (Zeichnungsstand, 618 943 tet10, 2,56 Mio. Freiheitsgrade)
  konvergiert mit diesem Stand: ε_p,max 1,26 %, ΣR = −ΣF, Rechenzeit 5 h 17 min. Die Zahlen und ihre
  Annahmen stehen unter „Wo Ergebnisse anders ausfallen“.

## Ergebnisstatus: Modell geändert oder älteres Rechenverfahren

Die Ergebnisdatei hält fest, mit welchem Modell und mit welchem Verfahren gerechnet wurde. Ändern Sie nach
der Rechnung etwas am Modell, also an Geometrie, Netz, Werkstoffen, Querschnitten, Lagern, Lasten, Kontakten
oder an einer Einstellung, die das Verfahren bestimmt, dann ist die Ergebnisdatei ungültig und wird nicht
geladen. Rechnet das Programm dasselbe Modell inzwischen anders, weil sich eine Vorgabe oder das Verfahren
geändert hat, sind die Ergebnisse gültig. Statuszeile und Protokoll sagen dann, womit gerechnet wurde und
was heute gilt, und eine neue Rechnung liefert die Ergebnisse nach dem aktuellen Verfahren.

Jeder Wechsel des Verfahrens ist eingestuft. Bei einer **Verbesserung** war das alte Verfahren richtig, das
neue ist besser oder schneller; es gibt nur den Hinweis. Bei einer **Fehlerkorrektur** konnte das alte
Verfahren falsch rechnen; das Ergebnis trägt den Status „Ergebnis möglicherweise betroffen – neu rechnen“,
und zwar in der Kopfzeile, vorn in der Statuszeile, im Protokoll und im Bericht. Der Status kommt nur, wenn
das Modell das betroffene Merkmal hat und die betroffene Rechenart im Ergebnis gerechnet ist; ein Modell
ohne Reibung bekommt also keinen Hinweis zum Reibverfahren. Lässt sich das Alter einer sehr alten
Ergebnisdatei nicht sicher erkennen, nennt der Status das, denn „lieber möglicherweise betroffen als still
gültig“.

Als Fehlerkorrektur eingestuft sind seit dieser Fassung die Traglast der plastischen Rechnung, der
Gleitweg der Reibung und die Gegenseite der Kontaktfugen (alle drei weiter unten), zusätzlich zu den
Einstufungen der Fassung vom 15.10.2026 (Reibungstangente, Deckel über alle Runden) und den Korrekturen am
RFEM-Import. Der Verfahrensstand in der Ergebnisdatei ist jetzt 5.

## Vorspannung einmal je Anker

Die Vorspannung eines Ankers wird einmal definiert, und die Lastfälle verweisen nur noch darauf. Eine
Definition legen Sie unter *Lasten → Vorspannung je Anker* an, im Modellbaum unter *Einwirkungen →
Vorspannung je Anker* oder in der Maske *Lasten → Vorspannung* über den Knopf „Vorspannung je Anker …“. Sie
enthält die Anker (etwa „S1–S16“), die Pressenkraft P_max, den Verankerungsschlupf Δs und die Spanngruppe.
Definitionen derselben Spanngruppe werden gleichzeitig gespannt, mehrere Gruppen nacheinander in
aufsteigender Nummer; früher gespannte Anker verlieren dann durch die elastische Verkürzung Kraft. Für den
Zeitpunkt ∞ geben Sie wahlweise P_∞ absolut oder den zeitabhängigen Verlust ΔP_t ein.

Im Lastfall wählen Sie im Feld „Vorspannung je Anker“ zwischen „keine“, dem Zeitpunkt 0 und dem Zeitpunkt ∞,
für alle Definitionen oder für eine. Im Zeitpunkt 0 spannt das Programm jeden Anker mit P_max, verriegelt ihn
und zieht den Schlupf ab; die Kraft danach ist P₀, und die rechnet das Programm. Im Zeitpunkt ∞ trägt jeder
Anker nach dem Verriegeln genau P_∞. Die Maske der Definition zeigt P₀ und beide Endwerte; liegt P_∞ über P₀,
wäre der Verlust negativ, und die Zeile sagt das, ohne etwas umzustellen. Bisherige Vorspannungen im Lastfall
(Endvorspannung, Anfangsvorspannung, eingeprägte Dehnung) bleiben lesbar und rechnen wie zuvor.

### Zuordnung vorhandener Vorspannungen

Unter *Lasten → Vorspannung → „Je Anker zuordnen …“* (im Modellbaum „Vorspannungen der Lastfälle
zuordnen …“) fasst der Dialog die Vorspannungen an denselben Stäben nach Wert zu Gruppen zusammen. Je Gruppe
zeigt er die Lastfälle mit ihren Kategorien und die Kraft, die nach der elastischen Verkürzung wirkt. Sie
ordnen jede Gruppe einem Zeitpunkt und einer Definition zu; als Vorschlag steht im Zeitpunkt 0 P_max gleich
dem Wert der Gruppe mit Δs = 0 und im Zeitpunkt ∞ P_∞ gleich dem Wert der Gruppe. Erst „Übernehmen“ stellt
die Lastfälle um. Alle anderen Lasten bleiben, auch eine echte Temperaturlast an einem anderen Bauteil, und
eine Gruppe ohne Zuordnung bleibt, wie sie ist. Eine aus RFEM übernommene Definition trägt den Vermerk „aus
RFEM übernommen – prüfen“. Am Drehlager sind es 952 kN als ΔT in 128 Lastfällen, 805 kN als ΔT in 293
Lastfällen und 944,7 kN Endvorspannung in LF1; mit 952 kN im Zeitpunkt 0 und 805 kN im Zeitpunkt ∞
verweisen danach 421 Lastfälle auf die Definition, und LF1 bleibt unverändert. Ob die Lastfälle mit 805 kN
den Zeitpunkt ∞ meinen und welcher Sollwert gilt, prüfen Sie in RFEM.

### Nachweise je Zustand

Der Spannstahlnachweis zählt nur gerechnete Lastfälle, als Lastfall oder in einer gerechneten Kombination.
Beim Spannen steht genau ein Eintrag je Definition mit P_max, kein Maximum über Lastfälle; nach dem
Verankern zählen nur Ergebnisse im Zeitpunkt 0, im Grenzzustand der Tragfähigkeit nennt jede Zeile den
Zustand, mit dem die Kombination gerechnet ist. Die Grenze nach dem Verankern ist die der Norm,
σ_pm0 = min(0,75·f_pk; 0,85·f_p0,1k) nach EN 1992-1-1, 5.10.3(2). Der Bericht hat unter der Übersicht der
Stabnachweise die Tabelle „Nachweise nach dem Zustand der Vorspannung je Anker“.

## Starre Scheiben über einen Kreisring einleiten

Eine starre Scheibe aus RFEM, die genau über einer Bohrung liegt, hängt die ganze Anker- oder
Schraubenkraft als Linie an den Lochrand. Dort fließt der Werkstoff netzabhängig; am Drehlager liefen die
Ankerplatten im Spannschritt am Lochrand weg. Jede starre Kreisscheibe mit einem Stabende in der Mitte hat
deshalb eine Einleitungsart: **Lochrand starr (bisher)** oder **Kreisring verteilend (RBE3,
flächenanteilig)**. Der Kreisring ist die Auflage von Mutter oder Scheibe, nämlich die Randseiten des Blechs
in der Ebene der Scheibe zwischen Innen- und Außendurchmesser auf der Seite, auf der die Mutter liegt. Das
Stabende hängt über eine Verteilkopplung an allen Knoten des Rings, flächenanteilig gewichtet. Die
Kopplung versteift den Ring nicht und erzeugt keine Spitzen an seinen Kanten. Die Geometrie bleibt
unverändert; die Umstellung ist nur eine Kopplungsart.

Umgestellt wird nur auf Ihre Anweisung, unter Netz → **Scheiben einleiten…**. Die Tabelle zeigt je Gruppe
gleicher Bohrung die Einleitung, Innen- und Außendurchmesser, die Herkunft des Maßes und die mittlere
Pressung F/A_Ring aus der Vorspannkraft im Verhältnis zu f_y. Der Außendurchmesser ist mit einem Normmaß
vorbelegt und als **Annahme** gekennzeichnet, bis Sie das Maß aus der Zeichnung eintragen. Ist der
Stabdurchmesser ein Nennmaß der Unterlegscheibe nach ISO 7089, gilt deren Außendurchmesser (M16 30 mm,
M20 37 mm); sonst ist es ein Gewindestab, und es gilt der Auflagedurchmesser der Sechskantmutter nach
ISO 4032 der nächsten Größe (Ø 40 → M42, 60 mm). Liegt die Pressung über 3 f_y, steht „Auflage prüfen
(Zeichnungsmaß)“ dort. Jede Umstellung ist ein Schritt, den Rückgängig (Strg+Z) zurücknimmt.

Vor einer plastischen Rechnung fragt das Programm deutlich nach, wenn es Stellen „Kraft ohne Fläche“ oder
starre Scheiben am Lochrand gibt, denn sie können die Konvergenz verhindern: „Abbrechen“, „Trotzdem
rechnen“ oder „Auf Kreisring umstellen und rechnen“. Alte Dateien und neue RFEM-Importe bleiben bei
„Lochrand starr“.

## Pressung nach Erzeugnisdicke

Die Pressung unter Scheiben rechnet mit f_y bei der Erzeugnisdicke des Körpers unter der Scheibe (kleinste
Abmessung seines umschließenden Quaders, EN 1993-1-1, Tab. 3.1). An einer 60 mm dicken Ankerplatte aus S355
sind das 335 statt 355 N/mm². Die Tabelle des Dialogs nennt f_y und die Dicke; lässt sich die Dicke nicht
bestimmen, steht der Werkstoffwert dort mit dem Hinweis „Dicke nicht bestimmbar“.

## Freie Knoten gestuft, nichts wird aus einem RFEM-Import gelöscht

Ein Knoten ohne Element wird danach beurteilt, was an ihm hängt. Greift eine Last oder Zwangsverformung an,
ist es ein **Fehler**: Die Last trägt kein Bauteil, und das Ergebnis ist „nicht gültig“. Ein Lager allein
ergibt die **Warnung** „Lager unwirksam“. Hängt weder Last noch Lager noch Kopplung an ihm, ist es nur eine
**Information** im Protokoll; am Drehlager waren es 67 Geometriepunkte der RFEM-Datei, die in der Geometrie
bleiben und nicht in die Rechnung eingehen.

Das Vernetzen löscht keinen dieser Knoten mehr, auch keinen, auf den nichts verweist, denn ein RFEM-Import
wird nicht selbständig in der Geometrie geändert. Gelöscht werden beim Vernetzen nur die Knoten des alten
Netzes. Wer die Knoten ohne jeden Verweis (keine Linie, Fläche, Last, Lager, Kopplung) loswerden will,
nimmt im Register Netz den Knopf **Freie Knoten entfernen…** (auch in der Befehlssuche): Das Programm nennt
die Zahl, fragt und entfernt nur nach „Ja“; Rückgängig bringt sie zurück.

Die Meldung „frei drehbar“ ist ebenfalls gestuft. Sie ist eine **Information**, wenn an der freien Bewegung
keine Last angreift und eine echte Zwangsbedingung (starre Kopplung, starrer Körper) den Freiheitsgrad
bestimmt. Das Programm misst das streng: Hält den Freiheitsgrad nur eine weiche Feder oder die
Pivot-Regularisierung des Gleichungslösers (wirksame Steifigkeit unter 10⁻⁹ der Hauptdiagonale), ist es
eine **Warnung**. Kraft und Moment solcher nur numerisch gehaltenen Freiheitsgrade gehen in die globale
Gleichgewichtskontrolle ein.

## Plastische Rechnung: Traglast, Mechanismus, Gültigkeitsgrenze

Über der Traglast gibt es bei ideal plastischem Werkstoff kein Gleichgewicht. Findet der Newton in einer
Laststufe keines, halbiert das Programm die Stufe bis zu viermal. Gelingt es auch dann nicht, endet die
Rechnung beim letzten konvergierten Zustand, und das Ergebnis heißt „NICHT gültig: Kein Gleichgewicht
gefunden bei Laststufe X (… % der Last). Mögliche Ursache: Traglast überschritten oder örtlicher
Mechanismus an <Ort>. Letzter konvergierter Lastanteil: … %.“ Der Ort ist das Element, dessen plastische
Dehnung zuletzt am stärksten wächst, mit Körper und Koordinate. Liegt er in einer netzabhängigen Zone oder
an einer Krafteinleitung (Knotenlast, starre Scheibe, Kreisring, starrer Körper), heißt die Ursache
„örtlicher Mechanismus an Krafteinleitung – Modell prüfen“. Gezeigt wird der letzte konvergierte Zustand,
gekennzeichnet in Zusammenfassung, Rechenliste, Protokoll und Bericht. Auch der Spannschritt einer
Endvorspannung halbiert seine Stufen, nennt den erreichten Anteil der Sollkraft und verriegelt dann nicht.
Wachsen die Verschiebungen im Newton, ohne dass er sich zusammenzieht, steht zusätzlich „Mechanismus“ mit
Knoten, Verschiebung und Dehnung dabei.

Anlass war ein Prüfblech mit Endvorspannung 900 kN, das „konvergiert“ mit einer plastischen Dehnung von
2 399 meldete: Der Spannschritt war nicht konvergiert, und der weggelaufene Zustand wurde verriegelt und
damit per Konstruktion im Gleichgewicht gerechnet.

Unter *Berechnung › Plastizität › Gültigkeitsgrenze ε_p* (Vorgabe 20 %) und je Werkstoff im Feld
**Bruchdehnung** stellen Sie ein, ab welcher plastischen Dehnung das ganze Ergebnis „nicht gültig:
außerhalb der Theorie kleiner Verzerrungen“ ist. **Netzabhängige Zonen** nimmt das Programm von dieser
Grenze aus und warnt nur, wenn alle folgenden Bedingungen erfüllt sind. Die Zone ist vom Programm als
auffällige Stelle markiert, und jedes Element über der Grenze liegt in ihr. Die Rechnung ist konvergiert,
und das Residuum der inneren Kräfte an allen freien Freiheitsgraden liegt unter der Toleranz. In der letzten
Laststufe kommt kein Element über der Grenze dazu, und in der vorletzten lag schon eines darüber. Fehlt
eine Bedingung, bleibt das Ergebnis „nicht gültig“, und der Text nennt die fehlende.

Jede plastische Rechnung nennt in Protokoll und Zusammenfassung ε_p,max mit Körper, Element und Koordinate
sowie ΣR und ΣM der Lagerkräfte. Das **innere Residuum** (äußere Last gegen die inneren Kräfte der Elemente,
bei einer Endvorspannung gegen die Sollkraft) steht in der Gleichgewichtskontrolle, am Ende jeder Laststufe
und im Ingenieurkriterium des Kontaktlaufs. Ab 1 % der Lasten ist das Ergebnis nicht gültig.

## Plastische Ergebnisse aus den Gaußpunkten

In einer plastischen Rechnung tragen Elementwert und Knotentabelle des Ergebnisses immer die
Integrationspunkte, nie eine Elementecke, und das gilt auch für Elemente, die nicht fließen. Die Färbung
tat das schon seit dem 13.10.2026; Elementwert, Knotentabelle, Export und Auswertungen lasen bisher die
Ecken. Am Drehlager (Mittel) standen so an 124 Elementen mit fast entarteter Ecke bis 14 379 N/mm², wo die
Gaußpunkte desselben Elements höchstens 344 N/mm² haben. Elastische Rechnungen bleiben beim größten
Auswertepunkt, und die Nachweise lesen, was sie vorher lasen. Ein Vergleich mit einer analytischen Lösung
gehört deshalb an den Radius des Punkts und nicht an den Knoten, und die Hill-Prüfung rechnet seit dieser
Fassung so.

## Körper nur über reibungsfreien Kontakt gehalten

Vor jeder Rechnung prüft das Programm je Körper, was ihn als starren Körper hält: Lager, Kontakte (die
Normale; in der Fugenebene nur mit Reibbeiwert oder Haften), Spaltelemente, Kopplungen, mit anderen
Bauteilen geteilte Knoten und Stäbe, Fachwerkstäbe und Seile nur längs. Bleibt eine Richtung frei, die eine
Reibung in der Fuge halten würde, steht ein Hinweis im Klartext da, mit Name des Körpers, freier Richtung,
der Fuge oder Freigabe (Name aus dem Modell) und der Abhilfe, etwa „Reibbeiwert in der Fuge setzen (z. B.
μ = 0,2 nach EN 1090-2, Klasse D), Federkonstante > 0 oder seitliche Halterung“. Bei elastischer Rechnung
ist es eine Information, bei plastischer eine Warnung vor dem Start, und die Oberfläche fragt wie beim
Kreisring nach („Abbrechen“, „Reibbeiwert setzen…“, „Trotzdem rechnen“). Nichts wird automatisch geändert;
„Reibbeiwert setzen…“ trägt den Wert erst nach Ihrer Bestätigung in die genannten Fugen ein, als ein Schritt
mit Rückgängig. Anlass sind die Ankerplatten am Drehlager, die nur am Anker und am reibungsfreien Kontakt
hängen und plastisch am feinen Netz wegrutschten.

Meldet eine abgebrochene plastische Rechnung ihren Ort in einem solchen Körper, heißt die Ursache
„örtlicher Mechanismus: Körper … rutscht, er ist nur über reibungsfreien Kontakt gehalten – Reibung
ansetzen oder halten“. Bewegt sich ein nicht gehaltener Körper im Ergebnis als Ganzes um mehr als ein
Tausendstel seiner Größe, steht „Körper … bewegt sich als Ganzes um … mm in Richtung … – nicht gehalten“ als
Warnung da; unter Ergebnisse → Freie Bewegungen hebt ein Klick die Knoten in der 3D-Ansicht hervor und
zeichnet einen Pfeil.

## Körper springen nicht mehr im Kontaktlauf

Anlass waren Ankerplatten, die im Kontaktlauf als starre Körper sprangen (V4 um 180 mm, V7 um 101 mm), ohne
dass sich der Körper verformte. Vier Bausteine schützen davor.

* Die Fuge hat im Dialog das Feld **Kontaktstart** mit „nach Spalt (Vorgabe)“ und „geschlossen“. Bei
  „geschlossen“ beginnt der Lauf mit allen Knoten der Fuge geschlossen, mit dem echten Spalt, und Zug öffnet
  sie. Das ist sinnvoll, wenn Teile planmäßig anliegen.
* Eine Runde, die einem Teil den Halt nehmen würde, öffnet nur dann Bedingungen, wenn alle Bedingungen des
  Teils öffnen wollen; sonst bleibt die stärker gezogene Hälfte offen. Ein Halt unter echtem Zug endet wie
  bisher mit einem Abbruch.
* Vor jeder Lösung werden ungehaltene Teile gehalten oder mit einer kleinen Kontaktstabilisierung (10⁻⁶
  der Kontaktsteifigkeit) versehen. Ihre Kraft steht am Ende im Protokoll und warnt ab 0,1 % der Last.
* Springt ein Teil um mehr als seine Elementgröße bei einem Verformungsanteil unter 10⁻³, wird die Runde
  verworfen und gedämpft wiederholt; das Protokoll sagt „Körper … in dieser Runde nicht gehalten“.

Zum Halten zählen Körper, die sich Knoten teilen, als ein Teil. Am Drehlager hatten die Knaggen mit der
Grundplatte je 97 Knoten gemeinsam und wurden deshalb fälschlich als frei angesehen. Ein kleiner Zug an
gehaltenen Punkten (unter dem Anteil der Kontaktkraft, den die Einstellung „Restwechsel“ erlaubt) gilt jetzt
als offen und wird gemeldet, statt die Rechnung abzubrechen.

## Gleitweg der Reibung über die Stufen

Die konsistente Tangente rechnete in einer Stufe nach einer Stufe mit Gleiten mit dem ganzen Weg seit der
Ausgangslage. Die Haftfeder zog den Knoten dann zur Ausgangslage zurück, und die Reibkraft trieb die
Bewegung an: Ein Klotz, der nach dem Spannschritt hätte haften müssen, ließ 17 von 17 Knoten weitergleiten,
mit negativer Dissipation. Jetzt führt jeder Reibknoten seinen Gleitweg mit, der am Ende jeder konvergierten
Spann- und Laststufe fortgeschrieben wird; die Haftkraft folgt aus dem Weg seit dem letzten Gleiten. Die
Rechnung des Klotzes liefert damit Dissipation je Knoten und Stufe von mindestens null, und zwei Laststufen
rechnen wie eine (Unterschied 2·10⁻⁹ m).

Das ist eine Fehlerkorrektur und betrifft Kontakt mit μ > 0 in mehrstufiger Rechnung, also mit
Spannschritt oder Plastizität. Ob in einer früheren Stufe ein Knoten glitt, steht in der Ergebnisdatei
nicht; ein solches Ergebnis trägt deshalb den Status „möglicherweise betroffen“.

## Die Gegenseite einer Fuge ist die ganze Gegenfläche

Bis zu dieser Fassung gehörte zur Gegenseite einer Fuge nur, was die Facetten der Kontaktseite als nächste
Gegenfacette trafen. War die Gegenseite feiner vernetzt als die Kontaktseite, war das ein kleiner,
zufälliger Teil der Fläche, und die übrigen Knoten meldeten fälschlich „neben der Gegenfläche“. Jetzt
gehört jede Facette der genannten Gegenflächen dazu, die sich mit der Kontaktseite überdeckt. Unabhängig
davon stufte die Mortar-Überdeckung eine zu 99,98 % überdeckte Facette auf einer gekrümmten Fuge als
teilweise überdeckt ein; sie wird jetzt mit der Krümmung der Facette beurteilt, und auf ebenen Fugen
ändert sich nichts.

Am Drehlager (Netz Mittel, Fuge „Achse (Typ 3)“, Körper V16) lag nur ein Siebtel der Gegenfläche in der
Liste: 1 333 von 9 027 Dreiecken. Die Fuge hat jetzt 663 statt 177 Bedingungen. Der Abstand zwischen
Slave und Masterpunkt fiel von 24,82 auf 0,83 mm, und die Momentenlücke ΣM der Kontaktkräfte, mit den
Kräften der Rechnung davor nachgerechnet, fiel von rund 34,6 kNm auf 0,27 kNm. Am Entwurfsnetz änderten
sich fünf Fugen; im echten Lauf fiel die Lücke von 1,0 auf 0,3 kNm, und ε_p,max fiel von 1,34 % auf 0,84 %
(Körper V35).

Das wirkt auch bei gespeicherten Modellen ohne Ihr Zutun: Datei und Netz bleiben, wie sie sind, und die
Gegenseite wird beim Rechnen aus dem Netz bestimmt. Es ist eine Fehlerkorrektur mit dem Verfahrensmerkmal
„Gegenseite der Kontaktfugen“. Betroffen sind Modelle mit einer Fuge aus einem Kontaktpaar (ungleiche
Netze); ihre Ergebnisse von davor tragen den Status „möglicherweise betroffen – neu rechnen“.

## Bolzennachweis nach EN 1993-1-8, 3.13

Ein Stift ist im Modell ein gewöhnlicher Volumenkörper; das Programm erkennt ihn nicht von selbst und leitet
nichts aus Name oder Form ab. Nachgewiesen wird nur ein Körper, den Sie im Rechtsklickmenü der Volumen mit
**Als Bolzen nachweisen…** festlegen (Rückgängig mit Strg+Z). Der Dialog verlangt den **Durchmesser** und den
**Werkstoff**; beides ist Pflicht, es gibt keinen Vorgabewert. Fehlt Durchmesser, Werkstoff, f_u oder f_y,
steht dort „Nachweis nicht geführt“ mit dem Grund. Der Dialog fragt außerdem die Lage der Scherfuge ab.

Der Nachweis nach Tab. 3.10 läuft für die Lastfälle, nicht für Kombinationen, weil sich Kontakt nicht
überlagert. Er umfasst das Abscheren F_v,Rd = 0,6·A·f_up/γ_M2, die Lochleibung F_b,Rd = 1,5·t·d·f_y/γ_M0 je
Partnerkörper, die Biegung M_Rd = 1,5·W_el·f_yp/γ_M0 und die Wechselwirkung (M_Ed/M_Rd)² + (F_v,Ed/F_v,Rd)²
≤ 1. Für die Lochleibung gilt f_y als der kleinere Wert von Bolzen und Partner. Querkraft und Moment in der
Scherfuge folgen aus dem Gleichgewicht der Kontaktkräfte, die die Partnerkörper auf den Bolzen ausüben; die
Dicke t eines Partners ist sein Anteil an der Bolzenlänge zwischen den Scherfugen. **Das Moment ist
netzabhängig** (Lage der Kontaktknoten), und die Ausgabe sagt es. Am echten Stift überlappen die
Kontaktbereiche der Partner an der Fuge um Rundungs- und Knotenabstände; eine Überlappung bis 1 % der
Bolzenlänge gilt deshalb als Berühren, und die Kraft zählt nach Partner statt nach Lage. Die Zeile je Bolzen
steht in der Zusammenfassung des Volumennachweises. Das Festlegen ändert die Ergebnisse der Rechnung nicht,
und die Modelldatei enthält das Feld nur, wenn Sie einen Bolzen festgelegt haben.

## W_el am Rundstahl aus RFEM

Die RFEM-Datei führt für einen Rundstahl kein elastisches Widerstandsmoment, und der Import hat dort 0
eingetragen. Er setzt jetzt W_el = π·d³/32 (Ø 40: 6,28 cm³). Das wirkt nur, wo eine Randspannung aus Biegung
gebildet wird, also bei der Ermüdung und bei Klasse 3; für reine Zugstäbe ohne Biegung ändert sich nichts.
Bereits gespeicherte Modelle bleiben unverändert; das Widerstandsmoment tragen Sie in der Maske des
Querschnitts selbst ein.

## Rechenzeit: Ausfall-Iteration mit Annahme (Hebel 1)

Bisher begann die Ausfall-Iteration der Zug- und Druckstäbe bei jeder Lösung mit allen Stäben, auch in jedem
Newton-Schritt der Plastizität, obwohl dort meist dieselben Stäbe ausfallen wie im Schritt davor. Jede
Lösung kostete so mindestens zwei Kontaktläufe. Mit der neuen Einstellung `ausfall_annehmen` nimmt das
Programm ab der zweiten Lösung eines Lastfalls an, dass dieselben Stäbe ausgefallen sind wie in der Lösung
davor, rechnet damit einen Kontaktlauf und prüft nach: Jeder aktive Zugstab muss Zug tragen, jeder
ausgefallene muss sich verkürzen, gemessen an der Längenänderung zwischen seinen Endknoten. Nur wenn das
verletzt ist, folgt eine zweite Runde wie bisher. Die Bedingung ist dieselbe, nur der Startpunkt ist ein
anderer.

**Die Einstellung ist in der Vorgabe aus und in der Oberfläche nicht erreichbar.** Es gibt kein Feld dafür;
sie steht nur im Modell (`plastizitaet.ausfall_annehmen`) und lässt sich im Skript oder in der Modelldatei
setzen. Gespeichert wird sie nur, wenn sie von der Vorgabe abweicht. Sie bleibt aus, bis die Messung am
Drehlager entschieden hat. Die Einstellungen `spannstufen` (Berechnung → Einstellungen, Gruppe „Kontaktlauf
und Spannschritt“, Feld „Spannschritt in … Stufen“) und `laststufen` (dieselbe Maske, Gruppe „Plastizität
der Volumen“, Feld „Laststufen“) gab es schon vorher und sind in der Oberfläche erreichbar.

Gemessen wurde am Drehlager-Entwurf, noch vor der Korrektur der Gegenseite. Bisher waren 163
Zerlegungen nötig; der Hebel 1 allein brauchte 138, und Hebel 1 zusammen mit je 2 Spann- und 2 Laststufen
brauchte 103 Zerlegungen. Die Abweichungen der Ankerkräfte und der Kräfte an den Knaggen lagen unter
0,003 %, ε_p,max war 0,535 % am selben Ort, und die Verschiebungen wichen höchstens 0,030 % von u_max ab.
An der Prüfplatte mit Strebe und Fließen
sind es 13 statt 24 Kontaktläufe und 124 statt 228 Runden bei derselben Lösung auf 1,4·10⁻¹⁰ m.

Mit der Korrektur der Gegenseite wurde die Messung am Entwurf wiederholt. Der Hebel 1 mit je 2 Spann- und
2 Laststufen brauchte 107 statt 168 Zerlegungen. ε_p,max blieb bei 0,84 % (0,8406 gegen 0,8420 %), die Kraft
der Knaggen in z bei 2 128,9 kN (Unterschied 0,09 kN), die Verschiebungen wichen höchstens 0,180 µm ab
(0,016 % von u_max), die Lagerkräfte höchstens 0,018 kN.

**Am Netz „Mittel“ ist die Gleichwertigkeit nicht gemessen.** Das Ergebnis weiter unten ist mit diesen
Einstellungen gerechnet, ein Vergleichslauf mit den Vorgaben fehlt. Es brauchte 127 Zerlegungen und 5 h 17 min.
Der Hauptprozess belegte dort bis 87 GB Commit, jeder Arbeitsprozess 3,4 GB. Vier statt acht Arbeiter ändern
die ersten 50 Zerlegungen nicht (alle 70 Fortschrittszeilen gleich) und machen die Rechnung nicht merklich
langsamer; bei 136 GB Commit-Grenze blieben so mindestens 17,6 GB statt zuletzt 3,8 GB frei.

## Weitere Änderungen

* **Netzeinstellung wirkt erst nach dem Vernetzen.** Wer „Mittel“ übernimmt und gleich rechnet, rechnet mit
  dem alten Netz. Das Modell merkt sich jetzt, mit welcher Einstellung das Netz entstand, und weist beim
  Übernehmen der Einstellung und beim Start der Rechnung darauf hin, wenn sie abweicht („Elemente Mittel
  statt Entwurf“). Gesperrt wird nichts; *Netz → Vernetzen* wendet die Einstellung an.
* **Update-Knopf** bietet nur noch eine neuere Fassung an (Versionsnummer, bei Gleichheit das Baudatum).
* **Lastkategorien und Stabtypen aus RFEM** sind in die Einstufung aufgenommen: Ein Modell, das vor den
  Korrekturen des Imports übernommen und noch nicht nachgelesen wurde, trägt den Status, solange Sie die
  Lager, Stabtypen oder Vorspannung nicht nachgelesen oder umgestellt haben.
* **Zwei neue Warnungen.** Eine Grenzkraft ohne Ausfall und ohne Schlupf wirkt nur in Druckrichtung; das
  meldet das Programm jetzt je Lager im Kontaktprotokoll und in der Zusammenfassung. Eine Zwangsverformung an
  einem Freiheitsgrad ohne Lager bleibt unwirksam; das steht jetzt auch im Ergebnis, in der Zusammenfassung
  und in der Überlagerung. Die Rechnung ändert sich dadurch nicht.
* **Feld im Winddialog umbenannt.** „c_f Vorgabe“ heißt jetzt „c_f,0 Vorgabe (wird mit ψ_λ abgemindert)“,
  weil die Eingabe wie bisher noch mit ψ_λ multipliziert wird. Die Rechnung ändert sich dadurch nicht.

## Wo Ergebnisse anders ausfallen

* **Prüfmatrix, Zeile P2 (Hill-Rohr unter Innendruck, σ_v(b)):** Die Knotentabelle trägt jetzt den nächsten
  Integrationspunkt, und die Prüfung vergleicht deshalb mit Hill am Radius dieses Punkts statt am Knoten, bei
  gleicher Grenze von 1 N/mm². Alle neun Zellen bleiben gelb. Beim Entwurf mit hex8 geht σ_v(b) von −6,87 auf
  −8,00 N/mm², bei Mittel tet10 von +7,55 auf −3,92 N/mm², bei Mittel hex20 von −45,79 auf −46,77 N/mm², bei
  Fein tet10 von +2,98 auf −1,70 N/mm² und bei Fein hex20 von −5,00 auf −4,99 N/mm². tet4 geht bei h = 25 mm
  von +99,64 auf +77,51 N/mm² und bei h = 3,125 mm von +75,35 auf +72,33 N/mm². Das ist der größte Wert über
  die Knoten. Das Mittel über die Außenfläche liegt in der Abnahme `test_plastizitaet` bei −0,93 N/mm² (tet10
  8 × 4) und −0,48 N/mm² (hex8 32 × 16), und die ist grün. Die Prüfmatrix steht weiter bei 86 grünen, 32
  gelben, 0 roten und 2 gesperrten Zellen.
* **Gleitweg-Speicher:** Am Prüfmodell der Fehlerliste (Block mit Reibung, der fließt) ändert sich u_max im
  Lastfall LF1 um −0,00006 % bei 20 statt 21 Runden und in der Kombination K1 um −0,0004 % bei 23 statt 21
  Runden. Bei Toleranz 10⁻⁸ oder 8 Laststufen sind alte und neue Rechnung bitgleich.
* **Ein Lauf, der vorher scheinbar konvergierte und mit einem Sprung von 980 mm endete,** heißt jetzt „nicht
  konvergiert“ und trägt die Warnung zur Kontaktstabilisierung (Stabilisierungskraft über 0,1 % der Last).
  Ein Modell, das früher singulär abbrach und ein Ergebnis verweigerte, liefert jetzt ein Ergebnis, das nie
  still gilt (Prüfung `test_abbruch`).
* **Pressung und W_el:** Die Pressung unter Scheiben rechnet mit f_y nach der Erzeugnisdicke (60 mm S355:
  335 statt 355 N/mm²), und wo der Import W_el eines Rundstahls brauchte, steht nun π·d³/32 statt 0.
* **Gegenseite der Fuge:** Siehe oben. Ergebnisse von Modellen mit ungleichen Netzen an einer Fuge ändern
  sich, am Drehlager in den Kontaktkräften und im Moment der Fuge deutlich.
* **Plastische Ergebnisse** zeigen an Elementecken mit stark verzerrtem Element jetzt den Gaußpunktwert;
  Spitzen an solchen Ecken verschwinden aus Elementwert und Knotentabelle.
* **Kontaktläufe mit Pendeln** (Reststeifigkeit ganz rutschender Gruppen jetzt einmal je Lauf entschieden):
  Das Pendelmodell der Kontaktprüfungen mit Tangente braucht 23 statt 27 Runden, und eine Platte auf einer
  Reibfuge 7 statt 40 Runden.

### Drehlager, Entwurf: Abnahme gegen den Stand vom 15.10.2026

Dasselbe Modell (Entwurf, Reibungstangente, Vorgabe-Einstellungen) wurde mit diesem Stand neu gerechnet. Die
Lagerkräfte stimmen auf 0,01 kN überein, die Kräfte der Anker S1 bis S16 auf eine Nachkommastelle in kN, und es
fallen dieselben Zugstäbe aus (S24, S25, S35). Die Momentenlücke ΣM fällt von 1,09 auf 0,31 kNm, die Kraft der
Knaggen in z von 2 120 auf 2 109 kN und ε_p,max von 1,30 % auf 0,90 %. Der Lauf braucht 147 statt 101 Zerlegungen.

Die Abnahme mit μ = 1 ist nicht sauber durchgelaufen. Die Lagerkräfte stimmen auf 0,01 kN, die Ankerkräfte auf eine
Nachkommastelle und die Kraft der Knaggen auf 2 kN mit dem Stand vom 15.10.2026 überein, und ε_p,max fällt von 1,30 %
auf 0,90 %. Im Spannschritt konvergierte der Kontaktlauf aber in allen drei Stufen nicht, das Ergebnis heißt deshalb
„vorläufig – Kontakt nicht konvergiert in Spannschritt“. Der Lauf brauchte 863 statt 297 Zerlegungen und 3 h 51 min.
Bei der Abnahme RT und bei μ = 0,2 tritt das nicht auf; die Ursache ist nicht untersucht.

### Drehlager, Netz „Mittel“: Ergebnis dieses Stands

Gerechnet ist der Lastfall LF1 des Zeichnungsstands mit μ = 0,2, der Endvorspannung 944,4 kN der Anker und den
Annahmen, die im Modell als solche stehen: Kreisringe mit Normmaßen und die 20 Passstifte Ø 25 mm als
St ISO 2338 mit f_u = 400 und f_y = 235 N/mm², bis der echte Wert aus Zeichnung oder Herstellerangabe vorliegt.
Die Ergebnisse sind deshalb vorläufig. Zum Vergleich steht das Entwurfsnetz mit denselben Einstellungen.

| Größe | Entwurf (tet4) | Mittel (tet10) |
|---|---|---|
| Zerlegungen | 107 | 127 |
| Newton-Schritte, Zustand | 7, konvergiert | 7, konvergiert |
| ΣR [kN] | (3 968,6; −604,3; 9 259,4) | (3 971,2; −604,7; 9 265,5) |
| ΣM, Lager gegen Lasten [kNm] | (−0,30; 0,00; 0,32) | (−0,36; 0,00; 0,08) |
| ε_p,max | 0,84 %, V35 | 1,26 %, V20 |
| Elemente fließend | 681 | 4 427 |
| u_max | 1,134 mm | 1,194 mm |
| Knaggen, Kraft in z | 2 128,9 kN | 1 852,4 kN |
| Anker S1–S16 | 943,8 bis 945,4 kN | 943,8 bis 945,5 kN |
| Schrauben S49–S53 | 40,1 / 77,8 / 107,6 / 112,8 / 109,8 kN | 38,8 / 75,6 / 107,8 / 113,9 / 110,1 kN |
| Ausgefallene Zugstäbe | S24, S25, S35 | S24, S25 |
| Stifte, größtes η_v | 1,18 (V103) | 0,97 (V93) |
| Stifte, größtes η_ww | 3,77 (V94) | 2,02 (V94) |
| Stifte mit η_v > 1 / η_ww > 1, von 20 | 4 / 10 | 0 / 5 |

ε_p,max liegt in der Ankerplatte V20 bei (0,214; 0,527; 0,237) m und entsteht beim Spannen: Nach dem
Spannschritt sind es schon 1,257 %. Das liegt deutlich unter der Grenze von 5 % für den Volumennachweis. Die
Kräfte in x und y laufen auf beiden Netzen über die Knaggen; ihre Kraft in z ändert sich mit dem Netz um 13 %
und ist damit nicht auskonvergiert. Die Biegung der Stifte ist netzabhängig. Nach dem Abscheren halten am Netz
„Mittel“ alle Stifte, nach der Wechselwirkung fünf nicht (V94, V93, V95, V103, V63), und allein bei V94 liegt
schon die Biegung allein über 1 (η_M = 1,25).

Nicht erfüllt sind auf beiden Netzen außerdem der Zug der Schrauben S51 bis S53 (M16 8.8, Ausnutzung 1,19 bis
1,26) und der Spannstahl S1 bis S16 nach dem Verankern (σ = 751,5 gegen σ_pm0 = 709,75 N/mm²). Der Spannstahlwert
folgt aus der angesetzten Vorspannung und nicht aus der Rechnung; welche Kraft gilt, ist am Modell zu prüfen.

## Hinweise zum Umstieg

* Dateien von vorher lassen sich weiter öffnen. Die neuen Felder (Vorspannungsdefinitionen, Einleitung
  über Kreisring, Bolzen, Kontaktstart, Gültigkeitsgrenze, `ausfall_annehmen`) stehen nur in der
  Modelldatei, wenn sie von der Vorgabe abweichen. Bestehende Modelldateien bleiben unverändert; die
  Korrektur der Gegenseite wirkt beim Lesen des Netzes, nicht in der Datei.
* Ergebnisdateien von vorher werden geladen. Haben die Rechnungen Kontakt mit Reibung und mehrere Stufen,
  Plastizität oder Fugen mit ungleichen Netzen, tragen sie den Status „möglicherweise betroffen – neu
  rechnen“, bis Sie neu rechnen.
* Ein Drehlager aus RFEM zeigt weiter die Hinweise zu Zugstäben, Lagerreibung und Vorspannung; keiner davon
  ändert etwas von selbst. Die Zuordnung der Vorspannungen und die Umstellung der Scheiben auf den
  Kreisring führen Sie selbst aus.
* Vor einer plastischen Rechnung fragt das Programm nach starren Scheiben am Lochrand und nach Körpern, die
  nur reibungsfreier Kontakt hält. Beides ist eine Rückfrage, keine Sperre.

## Nicht enthalten

Folgende Punkte sind bekannt und bewusst nicht in diesem Stand:

* Die Hebel H2 und H3 zur Rechenzeit am Drehlager (Zweig `loeser/drehlager-zeit-2`); der Hebel 1 ist
  gebaut, aber ausgeschaltet.
* Ein Vergleichslauf am Netz „Mittel“ mit den Vorgaben statt mit Hebel 1 und je 2 Stufen.
* Eine Prüfung, ob zweimaliges Neuvernetzen dasselbe Netz liefert.
* Ein Feld in der Oberfläche für `ausfall_annehmen`.
* Eine automatische Umwandlung von ΔT in Vorspannung; es gibt nur den Hinweis und die Umwandlung auf Ihre
  Anweisung.
* Der Nachweis für Klaffen und Gleiten der Fuge der Anker; für Passstifte gibt es den Bolzennachweis, aber
  nur für Körper, die Sie selbst festlegen.
* Zylinderachsen für die Lastflächen F142 und F159 des Drehlagers (die RFEM-Orientierung dort ist für die
  gemeinte Einleitung falsch).
* Der Listenbefund: Diagnose, Bericht, Elementstufe und Netzfeld lesen die rohe Liste der Gegenfacetten der
  Kontaktpaare (`diagnose.py`, `report/html.py`, `elementstufe.py`, `netzfeld.py`), nicht die ganze
  Gegenseite.
* Maskenfelder für die übrigen Kontaktschalter (Öffnen begrenzen, Sprungprüfung, Vorab-Halten); nur der
  Kontaktstart hat ein Feld.
* Der Sammelbefehl „Einwirkung für mehrere Lastfälle“.
* Linienlasten in lokalen Achsen.
* Der Hebelarm-Anteil der Feder.
* Die ΣM-Kontrolle in Theorie II. Ordnung.
* Die Kopie des Werkstoffs bei Verbindungen und Vorlagen.
* Die Ermüdung des Spannstahls.
* Nachtrag 2 der Fehlerliste (M01 bis M47).
* Schalen mit Kontakt.
* Ein symmetrischer Löser (Hebel etwa 48 % je Zerlegung; die Matrix ist mit gleitenden Reibknoten
  unsymmetrisch).
* Die ama-LU (Zweig `loeser/ama-uebernahme`).
* Die Linux-Fassung.
* Die Ursache, warum das Drehlager mit μ = 1 in allen drei Spannstufen als „vorläufig – Kontakt nicht
  konvergiert“ endet; sie ist zurückgestellt.
