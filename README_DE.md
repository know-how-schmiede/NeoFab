![NeoFab Logo](images/Logo_NeoFab.png)

# NeoFab - Mehrsprachiges Auftragsmanagement fuer Werkstaetten

[English](README.md)

NeoFab ist eine Flask-basierte Webanwendung zur Verwaltung von Fertigungsauftraegen in Laboren, Werkstaetten, Makerspaces und Forschungsumgebungen. Die Anwendung unterstuetzt 3D-Druck-Workflows sowie weitere Auftragskategorien wie Plotter, CNC und Beschaffung.

Die Anwendung ist fuer mehrsprachige Nutzung ausgelegt. Englisch ist die Standardsprache, Deutsch und Franzoesisch werden ueber die mitgelieferten Uebersetzungsdateien unterstuetzt.

## Funktionen

- **Benutzerkonten und Rollen**
  Registrierung, Anmeldung, Self-Service-Passwort-Reset, optionale E-Mail-Aktivierung, Begruessungs-E-Mails, Benutzerprofile, Admin-Benutzer, deaktivierte Benutzer und Behandlung geloeschter Benutzer.

- **3D-Druck-Auftragsverwaltung**
  Strukturierte Auftragsdaten, Projektdaten, Fristen, Freigabeinformationen, Kostenstellen und Statusverfolgung.

- **Stabile Auftragsnummern**
  Auftrags-IDs sind gegen unbeabsichtigte Wiederverwendung nach dem Loeschen einzelner Auftraege geschuetzt. Administratoren koennen alle Auftragsdaten und die Auftragssequenz in den Systemeinstellungen mit ausdruecklichen Sicherheitsabfragen zuruecksetzen.

- **Auftragskategorien**
  Auftraege koennen Kategorien wie 3D-Druck, Plotter, CNC oder Beschaffung zugewiesen werden. Die Auftragsdetailansicht passt Reiter und Formulare an die gewaehlte Kategorie an.

- **Modell- und Dateiverwaltung**
  3D-Modelle, G-Code-Dateien und Dokumentationsanhaenge koennen je Auftrag hochgeladen und verwaltet werden.

- **Plotter- und Plakatverwaltung**
  Plotter-Auftraege verwenden einen eigenen Plakate-Reiter statt des 3D-Modell-/Bild-Reiters. Benutzer koennen mehrere JPG-, PNG- oder PDF-Plakatdateien mit Bemerkung, Anzahl und gewuenschtem Druckdatum hochladen.

- **Plotter-Plakatkosten**
  Plakate koennen einem Papier, einem Plotter-Typ und einer Plakatgroesse zugeordnet werden. NeoFab analysiert den Deckungsgrad und berechnet Positionskosten aus Papierkosten pro m2, ausgewaehlter Plakatflaeche, Deckungsgrad, Maschinenkosten pro Plakat, Wartungskosten pro Plakat, Anzahl und Ruestkosten.

- **Beschaffungsworkflow fuer Artikel**
  Beschaffungsauftraege verwenden einen eigenen Artikel-Reiter. Benutzer koennen Artikelname, Beschreibung, Lieferant, Artikellink, Anzahl und Stueckpreis inklusive MwSt. pflegen.

- **Upload von Beschaffungsnotizen**
  Jeder Beschaffungsartikel kann einen optionalen Notizanhang enthalten. Unterstuetzt werden Textdateien, Word-Dokumente, PDF-Dateien und LibreOffice-Dokumente.

- **Automatischer Beschaffungsstatus**
  Admins und Mitarbeiter koennen Artikel auf Bestellt oder Geliefert setzen. Der Status des Beschaffungsauftrags wird automatisch aktualisiert: ein bestellter oder gelieferter Artikel setzt den Auftrag auf In Bearbeitung, alle gelieferten Artikel setzen ihn auf Abgeschlossen.

- **Plakat-Thumbnails**
  Hochgeladene Plakatbilder zeigen Thumbnails in der Auftragsansicht. PDF-Dateien erhalten eine Vorschau der ersten Seite, wenn die Laufzeitumgebung dies unterstuetzt, andernfalls eine PDF-Ersatzvorschau.

- **Projektvideos**
  Auftraege koennen MP4-, WebM-, OGV-, OGG- oder MOV-Videos mit optionaler Kurznotiz und maximal 200 MB Uploadgroesse enthalten.

- **STL- und 3MF-Viewer**
  Browserbasierte Modellvorschau mit Zuruecksetzen, Grid, Achsen, Beschriftungen, Wireframe-Modus, Modellinformationen und Thumbnail-Unterstuetzung.

- **Druckauftragsverfolgung**
  Druckauftraege koennen mit Drucker, Material, Farbe, Druckstatus, Startzeit und Druckparametern erstellt und verwaltet werden.

- **3D-Druck-Kostenberechnung**
  Druckauftraege koennen Maschinen-, Material-, Mengen- und Ruestkosten aus Druckerprofilen, Filament-Materialien, G-Code-Metadaten und manuell gepflegten Druckparametern berechnen.

- **G-Code-Metadatenanalyse**
  G-Code-Uploads koennen Druckdauer, Filamentlaenge und Filamentgewicht aus Slicer-Kommentaren auslesen. Fehlende Werte koennen auch spaeter beim Oeffnen eines Auftrags ergaenzt werden.

- **Auftragslisten-Zusammenfassungen**
  Auftragslisten zeigen kompakte Status-Badges fuer Druckauftraege: Gesamtanzahl, laufende Drucke, abgeschlossene Drucke und fehlgeschlagene Drucke.

- **Konfigurierbare Dashboard-Auftragsliste**
  Die Dashboard-Auftragsliste unterstuetzt kombinierte Filter fuer Kategorie, Bereich und Status, eine persistente Freitextsuche, gespeicherte Browser-Session-Filter, sortierbare Spalten, Seitennavigation sowie systemweit konfigurierbare Sichtbarkeit und Reihenfolge der Dashboard-Spalten.

- **Integrierte Nachrichten**
  Eingebaute Kommunikation zwischen Benutzern und Admins, persistenter Gelesen-Status und optionale E-Mail-Benachrichtigungen.

- **Benachrichtigungssteuerung**
  Status-E-Mails, Begruessungs-E-Mails, Aktivierungslinks, Passwort-Reset-Links, SMTP-Tests, Mitteilungen und wichtige Nachrichten koennen ueber Anwendungseinstellungen und Benutzerpraeferenzen gesteuert werden.

- **Konsistente lokale Zeitverarbeitung**
  Oberflaeche, Logfile-Ansicht, Dashboard-Uhr, E-Mail-Benachrichtigungen, PDF-Exporte und Startzeiten von Druckauftraegen verwenden die konfigurierte NeoFab-Lokalzeit und eine UTC-sichere Speicherlogik.

- **Admin-Bereich**
  Verwaltung von Benutzern, Materialien, Farben, 3D-Druckerprofilen, Filament-Materialien, Plotter-Papieren, Plotter-Typen, Kostenstellen, Mitteilungen, Trainings-Playlists, Trainingsvideos, Logs und Auftraegen.

- **Archivierung und Bereinigung**
  Admins koennen Auftraege archivieren und dauerhaft inklusive Datenbankeintraegen und zugehoerigen Dateien loeschen.

- **Audit- und Log-Unterstuetzung**
  Logs enthalten Benutzeraktivitaeten, Auftragsaenderungen, Archivierungs- und Loeschvorgaenge, Datei-Bereinigungsdetails und Login-Zeitdiagnosen. Administratoren koennen optional eine automatische Loeschung nach einer konfigurierbaren Anzahl von Tagen aktivieren.

## Technik

- Python 3
- Flask
- SQLAlchemy
- Flask-Login
- Werkzeug Security
- Bootstrap 5
- Jinja-Templates
- SQLite, MariaDB oder PostgreSQL
- Gunicorn und systemd fuer Produktivinstallationen

## Projektstruktur

```text
neofab/
  app.py
  models.py
  notifications.py
  routes/
  static/
  templates/
  version.py
i18n/
  de.json
  en.json
  fr.json
doku/
  SETUP.md
  Version_Timeline.md
script/
  setupNeoFab
  setupNeoFabService
  upDateNeoFabService
  resetAdminPassword
images/
  Logo_NeoFab.png
  NeoFab_V0-8-6_*.jpg
```

## Einrichtung

Installations- und Wartungsskripte liegen im Verzeichnis `script/`.

Beginne mit der Setup-Dokumentation:

- [Script setup guide](script/README.md)
- [Allgemeine Setup-Hinweise](doku/SETUP.md)

Die wichtigsten Skripte sind:

- `script/setupNeoFab` - Basisinstallation und optionaler Start des Entwicklungsservers
- `script/setupNeoFabService` - Einrichtung eines systemd-Dienstes mit Gunicorn
- `script/upDateNeoFabService` - Aktualisierung einer bestehenden Dienstinstallation
- `script/resetAdminPassword` - Notfallskript zum Zuruecksetzen des Admin-Passworts

## Aktuelle Version

Aktuelle Anwendungsversion: **0.9.50**

Zu den letzten Aenderungen gehoeren Plotter-Stammdaten, Standardpapier je Plotter-Typ, Deckungsgradanalyse und eine Plakatkostenberechnung fuer Plotter-Auftraege.

Das Update-Skript installiert Python-Abhaengigkeiten aus `neofab/requirements.txt`, einschliesslich PyMuPDF zum Rendern der ersten Seite hochgeladener Plakat-PDFs als Thumbnail.

Die detaillierte Projekthistorie steht in [Version_Timeline.md](doku/Version_Timeline.md).

## Screenshots V0.8.6

### NeoFab Startseite

![NeoFab Startseite](images/NeoFab_V0-8-6_-00.jpg)

### STL- und 3MF-Viewer

![STL- und 3MF-Viewer](images/NeoFab_V0-8-6_-01.jpg)

### Systemeinstellungen

![Systemeinstellungen](images/NeoFab_V0-8-6_-02.jpg)

### Admin-Bereich

![Admin-Bereich](images/NeoFab_V0-8-6_-03.jpg)

### Benutzerprofil

![Benutzerprofil](images/NeoFab_V0-8-6_-04.jpg)

### Kommunikation und Chat

![Kommunikation und Chat](images/NeoFab_V0-8-6_-05.jpg)

### Druckauftraege

![Druckauftraege](images/NeoFab_V0-8-6_-06.jpg)

### 3D-Modelle im Auftrag

![3D-Modelle im Auftrag](images/NeoFab_V0-8-6_-07.jpg)

### Auftragsdokumentation

![Auftragsdokumentation](images/NeoFab_V0-8-6_-08.jpg)

### Auftragsuebersicht

![Auftragsuebersicht](images/NeoFab_V0-8-6_-09.jpg)

### Auftragsliste

![Auftragsliste](images/NeoFab_V0-8-6_-10.jpg)

### Login

![Login](images/NeoFab_V0-8-6_-11.jpg)

## Lizenz

Informationen zur Lizenzierung stehen in den enthaltenen Lizenzdateien.
