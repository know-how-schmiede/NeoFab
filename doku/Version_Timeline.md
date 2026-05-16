# Timeline NeoFab

## Version 0.8.10

Kostenstellenliste zeigt die Anzahl der Auftraege je Kostenstelle direkt nach der Spalte Aktiv
Kostenstelle bearbeiten zeigt unter dem Formular eine Liste der Auftraege, die diese Kostenstelle verwenden
Kostenstellen-Auswahl in Auftraegen zeigt nur aktive Kostenstellen
Druckauftrag bearbeiten enthaelt die Auswahlfelder Drucker-Typ und Filament-Material
Drucker-Typen enthalten Kostenfelder fuer Maschinenstundensatz, Wartung pro Stunde und Ruestkostenpauschale

## Version 0.8.9

Mitteilungen koennen mit der neuen Prioritaet Achtung eMail erstellt werden
Beim Erstellen einer Mitteilung mit Prioritaet Achtung eMail wird eine E-Mail an alle aktiven Benutzer versendet
Die E-Mail-Aktion fuer Mitteilungen mit Prioritaet Achtung eMail ist in den Systemeinstellungen / E-Mail konfigurierbar

## Version 0.8.8

Systemeinstellungen / E-Mail zeigt unter dem Test-Empfaenger eine Liste der Aktionen, bei denen E-Mails versendet werden
Mail-Aktionen fuer neue Bestellungen und Statusaenderungen koennen per Auswahlfeld aktiviert oder deaktiviert werden

## Version 0.8.7

Projektbilder koennen per Klick auf das Thumbnail in einer vergroesserten Lightbox-Ansicht angezeigt werden

## Version 0.8.6

Auftragslisten zeigen Druckauftraege als Status-Zusammenfassung gesamt / im Druck / abgeschlossen / Fehler
Statuszahlen der Druckauftraege sind farblich markiert fuer schnellen Ueberblick

## Version 0.8.5

G-Code-Auswertung durchsucht die komplette Datei nach Druckdauer, Filamentlaenge und Filamentgewicht
Bestehende Druckauftraege koennen fehlende G-Code-Werte beim Oeffnen der Auftragsseite nachtragen
Printjob-Startzeit wird beim Setzen des Status Print gestartet automatisch auf die aktuelle Zeit gesetzt
Geplante Startzeiten werden beim Admin-Wechsel auf Print gestartet durch die aktuelle Startzeit ersetzt
Anleitung zur automatischen G-Code-Druckparameteruebernahme erweitert

## Version 0.8.4

G-Code-Upload liest Slicer-Kommentare fuer Druckdauer, Filamentlaenge und Filamentgewicht aus
Automatisch ausgelesene G-Code-Werte bleiben im Druckauftrag manuell editierbar
OrcaSlicer-Format mit Einheiten in eckigen Klammern fuer Filamentlaenge und Filamentgewicht wird erkannt
Dokumentation zur automatischen G-Code-Druckparameteruebernahme inklusive Fehleranalyse ergaenzt

## Version 0.8.3

Material und Farbe werden nicht mehr am Auftrag, sondern pro 3D-Modell gespeichert
3D-Modell-Upload und Modell-Bearbeitung um Material- und Farbauswahl erweitert
Bestehende Auftragswerte fuer Material und Farbe werden einmalig auf vorhandene 3D-Modelle uebernommen
Neuer Auftrag um druckbezogene Felder Drucker-Typ, Filament-Material und Status reduziert
Order-Allgemein zeigt beim Anforderer zusaetzliche User-Details aus dem Profil an

## Version 0.8.2

Doppeltes Erstellen von Auftraegen durch Submit-Sperre und einmaliges Formular-Token verhindert
Admin-Nachrichten zeigen den konkreten Admin-Namen bzw. die Admin-E-Mail an
Doppeltes Speichern von Mitteilungen durch Submit-Sperre und einmaliges Formular-Token verhindert
Fehlende Projekt- und Freigabe-Spalten der Auftragsdatenbank werden automatisch nachgezogen

## Version 0.8.1

Archivieren und Loeschen von Auftraegen werden detailliert im Logfile protokolliert
Datei- und Ordnerloeschungen beim endgueltigen Loeschen von Auftraegen werden mit Pfad und Anzahl protokolliert
Langsame Logins werden mit Schrittzeiten im Logfile protokolliert
Logfile-Details werden gekuerzt angezeigt und vollstaendig per Tooltip eingeblendet
Tooltip der Logfile-Details auf vollstaendige Bootstrap-Anzeige umgestellt

## Version 0.8.0

Admin-Bereich fuer Auftraege mit Archivieren und endgueltigem Loeschen inklusive Datenbank- und Datei-Bereinigung
Archivierte Auftraege werden im Dashboard nicht mehr angezeigt

## Version 0.7.12

STL-/3MF-Viewer um schaltbare Achsen und Achsenbeschriftungen erweitert
STL-/3MF-Viewer um schaltbare Wireframe-Darstellung erweitert
STL-/3MF-Viewer um Button zum Zuruecksetzen der Ansicht erweitert

## Version 0.7.11

Logfile in NeoFab_Log umbenannt
STL-/3MF-Viewer um schaltbares Grid und schaltbare Model-Info-Box erweitert

## Version 0.7.10

Angemeldete Admins koennen ihre eigene Rolle nicht mehr aendern

## Version 0.7.9

Admin-User koennen in der Benutzerverwaltung erstellt werden
Benutzer koennen deaktiviert oder als geloescht markiert werden
Deaktivierte und geloeschte Benutzer koennen sich nicht mehr anmelden und erhalten eine passende Login-Meldung
Statusaenderungen von Benutzern werden detailliert im Logfile protokolliert
Notfallscript zum Zuruecksetzen des Admin-Passworts aktiviert den Admin-User wieder

## Version 0.7.8

Logfiles koennen im Admin-Bereich nach Sicherheitsabfrage geloescht werden

## Version 0.7.7

Mehrere E-Mail-Empfaenger pro Kostenstelle fuer Status-Meldungen
Admin-Bereich fuer Logfiles mit taeglicher Ablage unter Jahr/Monat/Tag und Logging von An- und Abmeldungen
Logging fuer User-Erstellung und User-Bearbeitung

## Version 0.7.6

Notfallscript zum Zuruecksetzen eines Admin-Passworts ueber die Installations-Scripte

## Version 0.7.5

Kommunikation in der Auftragsdetailseite als eigener Tab und unterer Bereich standardmäßig zugeklappt

## Version 0.7.4

Admin-Bereich zur Verwaltung von Mitteilungen inklusive Bearbeiten, Löschen sowie JSON Ex- und Import

## Version 0.7.3

Gelesene Auftragsnachrichten werden persistent pro Benutzer gespeichert und bleiben nach erneutem Anmelden gelesen

## Version 0.7.2

Fehlermeldung bei zu großen STL-/3MF- und G-Code-Uploads
Anzeige der maximal erlaubten Dateigröße bei 3D-Modell- und G-Code-Uploads

## Version 0.7.1

Thumbnail-Erzeugung für 3MF-Dateien im 3D-Modell-Viewer

## Version 0.7.0

3MF-Dateien werden im 3D-Modell-Viewer angezeigt

## Version 0.6.19

Nach erfolgreichem Datei-Upload bleibt die Auftragsdetailseite im jeweiligen Upload-Reiter

## Version 0.6.18

MarkDown in Mitteilungen

## Version 0.6.17

Mitteilungen im Dashboard / Backend Admin

## Version 0.6.16

Bearbeiten Bilder

## Version 0.6.15

Bearbeiten 3D-Modelle

## Version 0.6.14

Optimierung UI "Auftrag stornieren" bei Order

## Version 0.6.13

Ergänzun PDF Export um Druckaufträge

## Version 0.6.12

Erstellung PlayListe für Tutorials

## Version 0.6.11

APP.py verkleinern, Funktionen in externe Module auslagern

## Version 0.6.10

JSON-Ex- und Import für alle Systemeinstellungen

## Version 0.6.9

MarkDown für Impressum und Datenschutz

## Version 0.6.8

Spalte Anzahl Druckaufträge im Dashboard

## Version 0.6.7

Status-Meldungen Editieren, Systemeinstellugnen Ex- und Import

## Version 0.6.6

Layout-Anpassungen Druckaufträge und Statusanzeige Tab Allgemein

## Version 0.6.5

Upload G-Code Files / Verwaltung G-Code Files

## Version 0.6.4

Erweiterung Datenmodell Drucker, Filament, Vorbereitung für G-Code Analyse

## Version 0.6.3

PDF-Tutorial unter Tutorials

## Version 0.6.2

PDF-Export: incl. STL-Thumbnail

## Version 0.6.1

Farbwähler STL Viewer

## Version 0.6.0

STL-Viewer

## Version 0.5.9

CSS Anpassungen

## Version 0.5.8

Footer mit Impressum und Datenschutz

## Version 0.5.7

Anpassungen Felder Projektdokumentation

## Version 0.5.6

Ergänzung Bemerkung bei Bild-Upload

## Version 0.5.5

Update-Script, Datum und Zeit bei PDF-Export

## Version 0.5.4

Setup-Scripte

## Version 0.5.3

Export und Import Tutorials

## Version 0.5.2

Info-eMail bei neuer Order

## Version 0.5.1

Vorbereitungen Status-Emails versenden (Backend)

## Version 0.5.0

Sortierfunktion Video-Tutorials und neues Release

## Version 0.4.13

Tutorial-Videos Youtube einbinden

## Version 0.4.12

Tumpnail bei Bilder-Upload

## Version 0.4.11

Module aus app.py auslagern

## Version 0.4.9

Session-Variablen, automatisches Ausloggen mit Konfig

## Version 0.4.8

Logo

## Version 0.4.7

PDF Export mit Template

## Version 0.4.6

PDF Download Order-Details

## Version 0.4.5

Bemerkung und Anzahl bei Datei-Upload 3D Modelle

## Version 0.4.4

Franzöische Übersetzung

## Version 0.4.3

i18n Umbau

## Version 0.4.2

Sprachenauswahl, Vorbereitung für i18n

## Version 0.4.1

Orders mit Tabs - Ordnung schaffen

## Version 0.4.0

Hinzufügen von Feldern für Projektdokumentation / Plakat usw...

## Version 0.3.11

Kostenstellen bei Order

## Version 0.3.10

JSON-Export Cost Center Master Data

## Version 0.3.9

Automatischer Reload Nachrichten auf Order-Seite

## Version 0.3.8

Kostenstellen

## Version 0.3.7

Export/Import Material

## Version 0.3.6

Export/Import Colors / Sicherheitsabfrage beim Löschen Color / Löschen der Farben beim Import

## Version 0.3.5

Farbwähler für Admin / Farben

## Version 0.3.4

My Profile für User

## Version 0.3.3

FavIcon Integration

## Version 0.3.2

app.py und Dashboard.html aufgeräumt

## Version 0.3.1

File löschen, Badge-Icon für STL / 3mf, File-Anzahl in Dashboard

## Version 0.3.0

File-Upload in Uploud-Verzeichnis, mehrere 3D Modelle können hochgeladen werden

## Version 0.2.1

ChatNachrichten in Order / NachrichtenFomular entfernt

## Version 0.2.0

TemplateSystem integriert

## Version 0.1.7

Farbvorschau in Stammdaten, OrderNew und OrderEdit

## Version 0.1.6

Farben und Material (Admin / Orders)

## Version 0.1.5

Felder im Auftrag ergänzen und editierbar machen

## Version 0.1.4

Integration Nachrichten Auftrag

## Version 0.1.3

Integration Grundlagen Auftrag

## Version 0.1.2

User-Verwaltung, DB-Update, User-Formular erweitert

## Version 0.1.1

Versions-Nummerierung integriert

## Version 0.1.0

Landing-Page / Admin-User / Dashboard Template / LogIn
