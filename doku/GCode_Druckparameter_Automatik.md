# Automatische Druckparameter aus G-Code

NeoFab kann beim Upload einer G-Code-Datei Druckdauer, Filamentlaenge und Filamentgewicht automatisch in den Druckauftrag uebernehmen. Die Werte werden nur aus Kommentarzeilen gelesen, die der Slicer in die G-Code-Datei schreibt. Manuell eingetragene Werte im Upload-Formular haben Vorrang und werden nicht ueberschrieben.

## Voraussetzungen

Damit die automatische Uebernahme funktioniert:

- Die Datei muss als `.gcode`, `.gco` oder `.gc` hochgeladen werden.
- Die Slicer-Kommentare duerfen beim Export nicht entfernt werden.
- Die relevanten Werte muessen als Kommentarzeilen in der G-Code-Datei enthalten sein. NeoFab durchsucht die Datei beim Upload nach bekannten Statistik-Zeilen.
- Die Werte muessen nach dem Slicen bereits als konkrete Zahlen in der Datei stehen, nicht als Platzhalter wie `{print_time}`.
- Druckdauer, Filamentlaenge und Filamentgewicht bleiben nach dem Upload manuell editierbar.

## Von NeoFab erkannte Werte

NeoFab erkennt aktuell diese typischen Kommentarformate:

```gcode
;TIME:2620
; estimated printing time (normal mode) = 43m 40s
; estimated print time = 1h 12m
; print time = 01:12:30

; filament used [mm] = 6045.38
; filament used [g] = 18.18
; total filament used [g] = 18.18
; Filament used: 6.04m
; Filament used: 6045.38mm
```

Ein OrcaSlicer-Block wie dieser wird z. B. korrekt gelesen:

```gcode
; filament used [mm] = 6045.38
; filament used [cm3] = 14.54
; filament used [g] = 18.18
; total filament used [g] = 18.18
; estimated printing time (normal mode) = 43m 40s
```

Daraus uebernimmt NeoFab:

- Druckdauer: `44 min`
- Filamentlaenge: `6.05 m`
- Filamentgewicht: `18.18 g`

## OrcaSlicer

OrcaSlicer schreibt die benoetigten Statistiken normalerweise automatisch ans Ende der exportierten G-Code-Datei. Nach dem Export sollte im Dateiende ein Block mit `filament used [...]` und `estimated printing time` sichtbar sein.

Vorgehen:

1. Modell normal slicen.
2. G-Code exportieren.
3. Datei in einem Texteditor oeffnen.
4. Am Ende der Datei nach diesen Zeilen suchen:

```gcode
; filament used [mm] = ...
; filament used [g] = ...
; total filament used [g] = ...
; estimated printing time (normal mode) = ...
```

Wenn die Zeilen fehlen:

- Pruefen, ob der Export als normaler G-Code erfolgt ist.
- Sicherstellen, dass keine Nachbearbeitung Kommentare aus der Datei entfernt.
- Optional kann in den Slicer-/Drucker-Einstellungen ein End-G-Code-Kommentarblock ergaenzt werden. Wichtig ist, dass der Slicer die Platzhalter beim Export in Zahlen aufloest.

Beispiel fuer einen kompatiblen Kommentarblock:

```gcode
; estimated printing time (normal mode) = {print_time}
; filament used [mm] = {used_filament}
; total filament used [g] = {total_weight}
```

Die genauen Platzhalter koennen je nach OrcaSlicer-Version und Profil variieren. OrcaSlicer dokumentiert die verfuegbaren Variablen in der Placeholder-/Variablen-Referenz.

## Bambu Studio

Bambu Studio basiert auf demselben Slicer-Umfeld wie OrcaSlicer und schreibt haeufig aehnliche Metadaten in die G-Code-Datei. Fuer NeoFab ist nicht der Slicer-Name entscheidend, sondern ob die Kommentarzeilen mit konkreten Zahlen vorhanden sind.

Vorgehen:

1. Modell slicen.
2. G-Code exportieren.
3. Datei in einem Texteditor pruefen.
4. Am Ende der Datei nach folgenden Zeilen suchen:

```gcode
; filament used [mm] = ...
; filament used [g] = ...
; total filament used [g] = ...
; estimated printing time (normal mode) = ...
```

Wenn Bambu Studio die Werte nicht ausgibt:

- Sicherstellen, dass die Datei als G-Code exportiert wurde und nicht nur ueber Cloud/Device gesendet wird.
- Nachbearbeitungs-Skripte pruefen, die Kommentare entfernen koennten.
- Falls eigene End-G-Code-Kommentare verwendet werden, muessen die Platzhalter beim Export zu Zahlen aufgeloest werden.

## PrusaSlicer

PrusaSlicer erzeugt in vielen Profilen ebenfalls Statistik-Kommentare am Ende der G-Code-Datei. NeoFab kann diese lesen, wenn sie in einem der oben genannten Formate enthalten sind.

Vorgehen:

1. Modell slicen.
2. `G-code exportieren` verwenden.
3. Datei in einem Texteditor oeffnen.
4. Am Ende der Datei nach Statistik-Kommentaren suchen:

```gcode
; filament used [mm] = ...
; filament used [g] = ...
; estimated printing time (normal mode) = ...
```

Falls die Werte fehlen:

- In PrusaSlicer pruefen, ob Kommentare oder Ausgabe-Metadaten durch Profile oder Post-Processing entfernt werden.
- Keine externen Skripte verwenden, die Kommentarzeilen loeschen.
- Bei eigenen Makros nur Platzhalter verwenden, die PrusaSlicer in Custom G-Code an dieser Stelle wirklich aufloest. Nicht jeder interne Wert ist in jedem Custom-G-Code-Feld verfuegbar.

## Kontrolle vor dem Upload

Vor dem Upload nach NeoFab reicht eine einfache Textsuche in der G-Code-Datei:

- Suche nach `estimated printing time`
- Suche nach `filament used`
- Suche nach `total filament used`

Wenn mindestens Druckzeit und Filamentwerte als konkrete Zahlen vorhanden sind, sollte NeoFab die Felder beim Upload automatisch fuellen.

## Wenn die Felder leer bleiben

Wenn nach dem Upload keine Werte in Druckdauer, Filamentlaenge oder Filamentgewicht angezeigt werden, liegt es meistens an einem der folgenden Punkte:

- Die G-Code-Datei enthaelt die Werte nicht als Kommentarzeilen.
- Die Werte stehen nur als Platzhalter in der Datei, z. B. `{print_time}` statt `43m 40s`.
- Ein Post-Processing-Skript oder ein Drucker-/Cloud-Export hat Kommentare entfernt.
- Der Slicer verwendet ein anderes Kommentarformat, das NeoFab noch nicht erkennt.
- Beim Upload wurden die Felder manuell leer gelassen und der Upload lief mit einer aelteren NeoFab-Version, die das Format noch nicht erkannt hat.

Pruefung:

1. G-Code-Datei in einem Texteditor oeffnen.
2. Nach `estimated printing time`, `filament used` oder `total filament used` suchen.
3. Pruefen, ob hinter dem Gleichheitszeichen konkrete Zahlen stehen.
4. Datei erneut in NeoFab hochladen.

Ein gueltiger OrcaSlicer-Ausschnitt sieht z. B. so aus:

```gcode
; filament used [mm] = 6045.38
; filament used [g] = 18.18
; total filament used [g] = 18.18
; estimated printing time (normal mode) = 43m 40s
```

NeoFab uebernimmt daraus:

- Druckdauer: `44`
- Filamentlaenge (m): `6.05`
- Filamentgewicht (g): `18.18`

Falls bestehende Druckauftraege aus einer aelteren Version noch leere Felder zeigen, die Auftragsseite erneut oeffnen. NeoFab versucht fehlende Werte aus vorhandenen G-Code-Dateien nachzutragen, sofern die Datei noch gespeichert ist und die Kommentarzeilen erkannt werden.

## Quellen

- OrcaSlicer Placeholder Variables: https://www.orcaslicer.com/wiki/developer_reference/built_in_placeholders_variables
- OrcaSlicer G-Code Output: https://www.orcaslicer.com/wiki/print_settings/others/others_settings_g_code_output
- PrusaSlicer Placeholder-Liste: https://help.prusa3d.com/article/list-of-placeholders_205643
