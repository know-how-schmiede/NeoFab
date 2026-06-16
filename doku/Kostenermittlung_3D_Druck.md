# Kostenermittlung fuer 3D-Drucker

Diese Anleitung beschreibt, wie NeoFab die Druckkosten eines Druckauftrags berechnet. Die Berechnung nutzt die Stammdaten aus den Bereichen **Drucker-Typen** und **Filament-Materialien** sowie die Angaben im Formular **Druckauftrag bearbeiten**.

Die Werte sind Kalkulationswerte fuer den internen Betrieb. Sie ersetzen keine buchhalterische Vollkostenrechnung und sollten regelmaessig an Einkaufspreise, Auslastung, Wartungsaufwand und lokale Abrechnungsregeln angepasst werden.

## Verwendete NeoFab-Felder

### Drucker-Typen

| Feld | Bedeutung |
| --- | --- |
| Maschinenstundensatz EUR/h | Der Maschinenstundensatz bildet pauschal die Anschaffungs- und Abschreibungskosten des Druckertyps ab. |
| Wartung pro Stunde EUR/h | Die Wartungskosten pro Stunde beruecksichtigen Verschleissteile, Reinigung, Instandhaltung und regelmaessige Servicearbeiten. |
| Ruestkostenpauschale | Einmaliger Betrag pro Druckauftrag fuer Vorbereitung, Slicer-Pruefung, Materialwechsel, Bettvorbereitung und Entnahme. |

### Filament-Materialien

| Feld | Bedeutung |
| --- | --- |
| Preis pro kg | Einkaufspreis der Filamentrolle. |
| Materialaufschlag in % | Sicherheitsaufschlag fuer Fehldrucke, Reste, Spulenwechsel und Materialverlust. |
| Trocknungspauschale | Optionaler Zuschlag, z. B. fuer PETG, TPU, PA oder andere hygroskopische Materialien. |
| Lager-/Handlingpauschale | Optionaler Zuschlag pro Auftrag fuer Lagerung, Bereitstellung und Handling. |
| Preis pro Gramm | Wird automatisch aus dem kg-Preis berechnet. |

### Druckauftrag bearbeiten

| Feld | Verwendung in der Berechnung |
| --- | --- |
| Drucker-Typ | Liefert Maschinenstundensatz, Wartung pro Stunde und Ruestkostenpauschale. |
| Filament-Material | Liefert Preis pro kg, Materialaufschlag, Trocknungspauschale und Lager-/Handlingpauschale. |
| Anzahl Drucke | Gibt an, wie oft derselbe G-Code-Druck benoetigt wird. |
| Druckdauer | Zeitbasis fuer Maschinen- und Wartungskosten. |
| Filamentgewicht | Materialmenge fuer die Filamentkosten. |

## Berechnungsformeln

### Preis pro Gramm

```text
Preis pro Gramm = Preis pro kg / 1000
```

Beispiel:

```text
26,00 EUR/kg / 1000 = 0,026 EUR/g
```

### Maschinenzeitkosten pro Druck

```text
Maschinenzeitkosten pro Druck =
  (Druckdauer in Minuten / 60)
  * (Maschinenstundensatz + Wartung pro Stunde)
```

Die Druckdauer wird in Stunden umgerechnet. Anschliessend werden Maschinenstundensatz und Wartung pro Stunde addiert. Diese Maschinenzeitkosten gelten fuer einen einzelnen Druck.

### Ruestkosten

```text
Ruestkosten = Ruestkostenpauschale
```

Die Ruestkostenpauschale wird einmal pro G-Code-Druckauftrag ergaenzt. Wenn derselbe G-Code mehrfach gedruckt wird, wird sie nicht mit der Anzahl der Drucke multipliziert.

### Materialkosten pro Druck

```text
Materialkosten pro Druck =
  Filamentgewicht in g
  * Preis pro Gramm
  * (1 + Materialaufschlag in % / 100)
  + Trocknungspauschale
  + Lager-/Handlingpauschale
```

Der Materialaufschlag deckt typische Verluste ab, die nicht direkt im Filamentgewicht des fertigen Drucks enthalten sind. Materialkosten gelten fuer einen einzelnen Druck und werden bei mehreren Drucken mit der Anzahl multipliziert.

### Kosten pro Druck

```text
Kosten pro Druck =
  Maschinenzeitkosten pro Druck
  + Materialkosten pro Druck
  + Ruestkostenpauschale
```

Diese Einzelansicht dient zur Bewertung eines einzelnen Drucks. Bei mehreren Drucken darf sie nicht einfach mit der Anzahl multipliziert werden, weil die Ruestkostenpauschale sonst mehrfach berechnet wuerde.

### Druck-Gesamtkosten

```text
Druck-Gesamtkosten =
  (Maschinenzeitkosten pro Druck + Materialkosten pro Druck)
  * Anzahl Drucke
  + Ruestkostenpauschale
```

NeoFab zeigt die Gesamtkosten in der Tabelle **Order / Druckauftraege** an. Im Formular **Druckauftrag bearbeiten** werden die Kosten pro Druck und die Gesamtkosten fuer die angegebene Anzahl angezeigt. Die Kostenstellen-Gesamtkosten verwenden dieselbe Formel.

## Beispielrechnung

Annahme fuer einen PETG-Druck auf einem Bambu Lab P1S:

| Eingabe | Wert |
| --- | ---: |
| Anzahl Drucke | 3 |
| Druckdauer | 240 Minuten |
| Filamentgewicht | 120 g |
| Maschinenstundensatz | 0,40 EUR/h |
| Wartung pro Stunde | 0,30 EUR/h |
| Ruestkostenpauschale | 1,50 EUR |
| Preis pro kg | 26,00 EUR |
| Materialaufschlag | 12 % |
| Trocknungspauschale | 0,80 EUR |
| Lager-/Handlingpauschale | 0,50 EUR |

Berechnung:

```text
Preis pro Gramm = 26,00 / 1000 = 0,026 EUR/g

Maschinenzeitkosten pro Druck =
  (240 / 60) * (0,40 + 0,30)
  = 4 * 0,70
  = 2,80 EUR

Materialkosten pro Druck =
  120 * 0,026 * 1,12 + 0,80 + 0,50
  = 4,79 EUR

Kosten pro Druck =
  2,80 + 4,79 + 1,50
  = 9,09 EUR

Druck-Gesamtkosten fuer 3 Drucke =
  (2,80 + 4,79) * 3 + 1,50
  = 24,27 EUR
```

## Sinnvolle Beispielwerte fuer Drucker-Typen

Die folgenden Werte sind gerundete Startwerte fuer NeoFab. Die Maschinenstundensaetze wurden aus typischen Anschaffungspreisen und einer angenommenen Nutzungsbasis von mehreren tausend Druckstunden abgeleitet. Bei geringer Auslastung sollten die Werte hoeher angesetzt werden.

| Drucker-Typ | Marktbeispiel, Stand 16.05.2026 | Maschinenstundensatz EUR/h | Wartung pro Stunde EUR/h | Ruestkostenpauschale EUR |
| --- | --- | ---: | ---: | ---: |
| Desktop Einstieg | Bambu Lab A1 Mini, offizieller EU-Shop ab ca. 179 EUR | 0,15 | 0,20 | 1,00 |
| Desktop Standard | Bambu Lab A1, offizieller EU-Shop ab ca. 289 EUR | 0,25 | 0,25 | 1,00 |
| Geschlossener CoreXY | Bambu Lab P1S, offizieller EU-Shop ab ca. 449 EUR | 0,40 | 0,30 | 1,50 |
| Premium CoreXY | Bambu Lab X1C, offizieller EU-Shop ab ca. 999 EUR | 0,80 | 0,40 | 2,00 |
| Prusa Workhorse | Original Prusa MK4S, offizieller Prusa-Vergleich assembled ab ca. 999 USD | 0,70 | 0,35 | 1,50 |
| Prusa CoreXY | Prusa CORE One+, offizieller Prusa-Vergleich assembled ab ca. 1.299 USD | 0,90 | 0,40 | 2,00 |

## Sinnvolle Beispielwerte fuer Filament-Materialien

| Filament-Material | Marktbeispiel, Stand 16.05.2026 | Preis pro kg EUR | Materialaufschlag % | Trocknungspauschale EUR | Lager-/Handlingpauschale EUR |
| --- | --- | ---: | ---: | ---: | ---: |
| PLA Standard | 3DJake/Polymaker PolyTerra PLA ca. 14,99 EUR/kg, Prusament PLA meist ca. 29,99 EUR/kg | 22,00 | 10 | 0,00 | 0,50 |
| PETG Standard | Bambu Lab PETG HF/PLA Basic im EU-Shop ca. 25,99 EUR pro 1 kg; Prusament PETG als gaengiges technisches Material | 26,00 | 12 | 0,80 | 0,50 |
| TPU 95A | Bambu TPU 95A HF offizieller EU-Shop ca. 34,99 EUR/kg | 35,00 | 15 | 1,00 | 1,00 |
| PA / Nylon | Technische PA- und PA-CF-Filamente liegen je nach Hersteller deutlich hoeher als PLA/PETG | 75,00 | 20 | 2,00 | 1,00 |

## Pflege der Werte

1. Einkaufspreise bei Filament-Materialien nach jeder groesseren Bestellung pruefen.
2. Maschinenstundensatz mindestens jaehrlich anhand von Anschaffungskosten, erwarteter Nutzungsdauer und Auslastung anpassen.
3. Wartung pro Stunde erhoehen, wenn Duesen, Hotends, Druckplatten, Riemen oder Lager regelmaessig ersetzt werden.
4. Ruestkostenpauschale nach tatsaechlichem Personalaufwand staffeln, z. B. niedriger fuer Standard-PLA und hoeher fuer Spezialmaterialien.
5. Trocknungspauschale nur dort setzen, wo Materialtrocknung wirklich Teil des Prozesses ist.

## Quellen fuer Beispielwerte

- Bambu Lab EU Store, Druckerpreise: https://eu.store.bambulab.com/de/collections/3d-printer
- Bambu Lab EU Store, Filamentuebersicht: https://eu.store.bambulab.com/pages/bambu-filament
- Bambu Lab EU Store, TPU 95A HF: https://eu.store.bambulab.com/products/tpu-95a-hf/
- Prusa CORE One+ / MK4S Vergleich: https://www.prusa3d.com/product/prusa-core-one/
- Prusament PLA Preise: https://prusament.com/materials/pla/
- Prusament PETG Eigenschaften: https://prusament.com/de/materials/prusament-petg/
- 3DJake Filamentpreise als Marktvergleich: https://www.3djake.de/filament
