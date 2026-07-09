# Plakat-Kostenermittlung

Diese Dokumentation beschreibt, wie NeoFab die Kosten fuer Plotter-Plakate ermittelt.

## Stammdaten

Die Berechnung verwendet Stammdaten aus dem Bereich `Admin > Plotter-Stammdaten`.

## Papierliste

In der Papierliste wird je Papier der Preis in `EUR/m2` gepflegt. Dieser Wert beschreibt die variablen Papier- beziehungsweise Flaechenkosten fuer einen voll gedeckten Quadratmeter.

Beispiel:

- Papierpreis: `12,00 EUR/m2`
- Plakatflaeche: `0,4996 m2`
- Deckungsgrad: `50 %`
- Papierkosten: `12,00 * 0,4996 * 0,50 = 3,00 EUR`

## Plotter-Typen

Beim Plotter-Typ werden die maschinenbezogenen Kosten gepflegt:

- `Maschinenkosten EUR/Plakat`
- `Wartung EUR/Plakat`
- `Ruestkosten EUR`
- optionales `Standardpapier`

Das Standardpapier wird beim Plakat-Upload automatisch ausgewaehlt, sobald der Plotter-Typ gewaehlt wird. Im Papierfeld wird dieses Papier als `Standard` gekennzeichnet.

## Plakatgroesse

Beim Upload wird die Plakatgroesse ausgewaehlt. Standard ist `A1`.

NeoFab verwendet folgende Flaechen:

| Format | Groesse | Flaeche |
| --- | --- | ---: |
| A3 | 0,297 x 0,420 m | ca. 0,1247 m2 |
| A2 | 0,420 x 0,594 m | ca. 0,2495 m2 |
| A1 | 0,594 x 0,841 m | ca. 0,4996 m2 |
| A0 | 0,841 x 1,189 m | ca. 0,9999 m2 |

## Deckungsgrad

Beim Hochladen analysiert NeoFab das Plakat und speichert den Deckungsgrad in Prozent.

Unterstuetzt werden:

- `JPG`
- `PNG`
- `PDF` mit Analyse der ersten Seite

Die Analyse zaehlt transparente und nahezu weisse Pixel als unbedruckte Flaeche. Alle anderen Pixel zaehlen als gedeckte Flaeche. Der Wert liegt zwischen `0 %` und `100 %`.

Wenn fuer ein altes Plakat noch kein Deckungsgrad gespeichert ist oder die Analyse nicht moeglich ist, rechnet NeoFab konservativ mit `100 %`.

## Kostenformel

Die Plakatkosten werden pro Plakatposition berechnet.

```text
Flaechenkosten = Plakatflaeche m2 * Papierpreis EUR/m2 * (Deckungsgrad / 100)

Kosten pro Plakat = Flaechenkosten
                  + Maschinenkosten EUR/Plakat
                  + Wartung EUR/Plakat

Gesamtkosten = (Kosten pro Plakat * Anzahl)
             + Ruestkosten EUR
```

Die Ruestkosten werden einmalig fuer die Plakatposition berechnet, nicht pro Exemplar.

## Beispielrechnung

Ausgangswerte:

- Format: `A1`
- Flaeche: `0,4996 m2`
- Deckungsgrad: `50 %`
- Papier: `12,00 EUR/m2`
- Maschinenkosten: `2,00 EUR/Plakat`
- Wartung: `0,50 EUR/Plakat`
- Anzahl: `3`
- Ruestkosten: `5,00 EUR`

Berechnung:

```text
Flaechenkosten = 0,4996 * 12,00 * 0,50 = 3,00 EUR
Kosten pro Plakat = 3,00 + 2,00 + 0,50 = 5,50 EUR
Gesamtkosten = 5,50 * 3 + 5,00 = 21,50 EUR
```

## Anzeige in NeoFab

Im Plakate-Reiter werden je hochgeladenem Plakat unter anderem angezeigt:

- Plakatgroesse
- Deckungsgrad
- Plotter-Typ
- Papier, inklusive `Standard`-Kennzeichnung, falls passend
- Gesamtkosten
- Kosten pro Plakat

Die gleichen Werte fliessen auch in Kostenstellen-Auswertungen und PDF-Ausgaben ein.
