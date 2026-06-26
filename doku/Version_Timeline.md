# Timeline NeoFab

## Version 0.9.40

Benutzerverwaltung um eine Suche nach E-Mail, Vorname und Nachname erweitert
Datumsfilter in der Benutzerverwaltung ergaenzt, der wahlweise Erstelldatum oder letzten Login im angegebenen Von-bis-Bereich beruecksichtigt
Rollen- und Statusfilter fuer die Benutzerliste ergaenzt
Version in Anwendung und README auf 0.9.40 angehoben

## Version 0.9.39

Systemeinstellungen im Reiter Allgemein um die maximale sichtbare Zeichenanzahl fuer Artikel-Beschreibungen in Beschaffungsauftraegen erweitert
Artikel-Beschreibungen in Beschaffungsauftraegen werden in der Liste auf den konfigurierten Wert gekuerzt
Der vollstaendige Text der Artikel-Beschreibung bleibt als Tooltip sichtbar
Version in Anwendung und README auf 0.9.39 angehoben

## Version 0.9.38

Zeitangaben in Oberflaeche, Logfile-Ansicht, Dashboard-Uhr, E-Mail-Benachrichtigungen und PDF-Export auf eine gemeinsame Formatter-Logik umgestellt
UTC-Zeitstempel aus Audit-Logs werden in der Admin-Ansicht als konfigurierte NeoFab-Lokalzeit angezeigt
Lokale Eingaben fuer Druck-Startzeiten werden beim Speichern korrekt nach UTC zurueckgerechnet
Dashboard-Uhr an die konfigurierte NeoFab-Zeitzone und den Anzeige-Offset angepasst
Link-Farbe der NeoFab-Info-Seite fuer Hell- und Dunkelmodus kontrastreich angepasst
Design-Smoke-Test um Info-Links mit echter Content-Link-Klasse erweitert
Version in Anwendung und README auf 0.9.38 angehoben

## Version 0.9.37

Auftrags-IDs ueber eine eigene Sequenz gegen Wiederverwendung nach Einzel-Loeschungen abgesichert
Wartungsfunktion zum Loeschen aller Auftraege und Zuruecksetzen der Auftrags-IDs in die Systemeinstellungen verschoben
Reset der Auftragsdaten durch Checkbox und Eingabe von RESET mit zwei Sicherheitsabfragen abgesichert
Version in Anwendung und README auf 0.9.37 angehoben

## Version 0.9.36

Auftragsliste um eine zweite Filterzeile mit Freitextsuche erweitert
Freitextsuche durchsucht Titel, Anforderer und Erstelldatum der Auftraege
Suchbegriff bleibt beim Sortieren, Blaettern und Aendern der angezeigten Zeilen erhalten
Version in Anwendung und README auf 0.9.36 angehoben

## Version 0.9.35

Bereichsstammdaten in den Systemeinstellungen um eine eindeutige Kurzfassung erweitert
Kurzfassungen der Bereiche in der Auftragsliste anstelle der langen Bezeichner angezeigt
Lange Bereichsbezeichner in der Auftragsliste als Tooltip der Kurzfassung hinterlegt
Bereichs-Import und -Export um die Kurzfassung erweitert
Bestehende Bereiche bei der Datenbankaktualisierung kompatibel mit einer Kurzfassung vorbelegt
Auswahl der angezeigten Zeilen an das untere linke Ende der Auftragsliste verschoben
Systemeinstellungen um einen eigenen Reiter Dashboard erweitert
Sichtbarkeit der Spalten in der Auftragsliste systemweit konfigurierbar gemacht
Reihenfolge der Dashboard-Spalten ueber Hoch- und Runter-Schaltflaechen anpassbar gemacht
Dashboard-Spaltenkonfiguration in den Import und Export der Systemeinstellungen aufgenommen
Auftragsliste dynamisch anhand der gespeicherten Spaltenreihenfolge aufgebaut
Dokumentation Liste_Status_Infos.md mit Statusautomatiken und E-Mail-Ereignissen ergaenzt
Version in Anwendung und README auf 0.9.35 angehoben

## Version 0.9.34

Maximale Groesse fuer hochgeladene Dateien von 50 MB auf 200 MB angehoben
Upload-Pruefung im Server und Browser sowie die Groessenhinweise auf das neue Limit abgestimmt
Fehlermeldungen fuer zu grosse Dateien in Deutsch, Englisch und Franzoesisch auf 200 MB aktualisiert
G-Code-Metadatenanalyse fuer grosse Dateien auf relevante Bereiche am Dateianfang und Dateiende begrenzt
Worker-Timeouts nach grossen G-Code-Uploads durch vollstaendiges Durchsuchen der Datei verhindert
Reiter 3D-Modelle / Bilder um Projektvideos mit Wiedergabe, Download und Loeschfunktion erweitert
Video-Uploads bis maximal 200 MB sowie kurze bearbeitbare Bemerkungen je Video ergaenzt
Unterstuetzte Videoformate auf MP4, WebM, OGV, OGG und MOV begrenzt
Systemeinstellungen im Reiter Allgemein um optionale automatische Log-Loeschung erweitert
Aufbewahrungsdauer fuer Logdateien in Tagen administrativ konfigurierbar gemacht
Abgelaufene Tageslogs werden beim Anwendungsstart und danach hoechstens einmal taeglich automatisch entfernt
Version in Anwendung und README auf 0.9.34 angehoben

## Version 0.9.33

Login um Passwort-vergessen-Funktion mit E-Mail-Link erweitert
Passwort-Reset-Links werden kryptografisch sicher erzeugt, nur gehasht gespeichert und zeitlich begrenzt
Neue Reset-Anforderung entwertet bisherige ungenutzte Reset-Links desselben Benutzers
Passwort-Reset setzt ein neues Passwort ohne Admin-Eingriff und schuetzt die Anfrage gegen Account-Ermittlung
Gueltigkeitsdauer der bestehenden Link-Einstellung gilt nun fuer Aktivierungs- und Passwort-Reset-Links
Version in Anwendung und README auf 0.9.33 angehoben

## Version 0.9.32

Neue Benutzerkonten werden zunaechst inaktiv angelegt und muessen per E-Mail-Link aktiviert werden
Account-Aktivierung per E-Mail in den Systemeinstellungen als Option aktivierbar oder deaktivierbar gemacht
Admin-Benutzerbearbeitung um eine Aktion zum erneuten Versenden eines Aktivierungslinks erweitert
Aktivierungslinks werden als kryptografisch sichere Tokens erzeugt und nur gehasht in der Datenbank gespeichert
Gueltigkeitsdauer fuer Aktivierungslinks in den Systemeinstellungen konfigurierbar gemacht
Abgelaufene, ungueltige oder bereits verwendete Aktivierungslinks werden beim Login-/Aktivierungsprozess abgefangen
Begruessungs-E-Mail wird nach erfolgreicher Kontoaktivierung versendet
Version in Anwendung und README auf 0.9.32 angehoben

## Version 0.9.31

Button-Design systemweit vereinheitlicht und Bootstrap-Button-Varianten ueber zentrale NeoFab-CSS-Regeln harmonisiert
Primaere, sekundaere, Erfolgs-, Warn-, Info- und Gefahren-Buttons behalten unterschiedliche Farben, verwenden aber einheitliche Form, Rahmen, Schatten, Fokus- und Hover-Zustaende
Outline-Buttons deutlicher als Buttons erkennbar gemacht
Spezielle Vorschau- und 3D-Viewer-Buttons an die gemeinsame Button-Sprache angeglichen
Version in Anwendung und README auf 0.9.31 angehoben

## Version 0.9.30

G-Code-Druckauftraege um eine Anzahl fuer benoetigte Drucke erweitert
Kostenberechnung fuer G-Code-Druckauftraege beruecksichtigt mehrere Drucke in der Gesamtsumme
Ruestkostenpauschale wird bei mehreren Drucken nur einmal pro G-Code-Druckauftrag berechnet
Kostenstellen-Gesamtkosten verwenden dieselbe Mengen- und Ruestkostenlogik wie die Auftragsansicht
Dokumentation zur 3D-Druck-Kostenermittlung um Anzahl Drucke, Kosten pro Druck, Gesamtkosten und einmalige Ruestkosten erweitert
Willkommens-E-Mails fuer neu angelegte Benutzer verwenden konsistent die Sprache des neuen Benutzerkontos
Versionsnummer auf 0.9.30 angehoben

## Version 0.9.29

Benutzerprofil um eine Option zum Aktivieren oder Deaktivieren von Status-E-Mails erweitert
Statusbezogene E-Mail-Benachrichtigungen beruecksichtigen die persoenliche Benutzereinstellung fuer Admins und Auftragsersteller
Bestehende Benutzer erhalten die Einstellung automatisch mit aktivem Default, damit sich das bisherige Versandverhalten nicht ungewollt aendert
User-JSON-Export und -Import um die Status-E-Mail-Einstellung erweitert
Versionsnummer auf 0.9.29 angehoben

## Version 0.9.28

Neue E-Mail-Aktion fuer Begruessungs-E-Mails bei neu erstellten Benutzerkonten ergaenzt
Begruessungs-E-Mail wird an den neuen Benutzer und die Admins versendet, sofern die Aktion aktiv und SMTP konfiguriert ist
E-Mail-Text enthaelt eine freundliche NeoFab-Begruessung in der Sprache des Empfaengers sowie Hinweise zu Profil-Sprache und Hell-/Dunkel-Design
Kurzanleitung zur Auftragserstellung, Auftrags-Art, Mehrfach-Uploads, STL-3D-Viewer, Chat, Projektstatus und zentraler Datenhaltung in den Standardtext aufgenommen
Begruessungs-E-Mail-Texte fuer Deutsch, Englisch und Franzoesisch im Reiter Impressum / Datenschutz editierbar gemacht
Admin-Benutzerformular um eine Sprachauswahl erweitert, damit neu angelegte Admins direkt die passende Begruessung erhalten
E-Mail-Actions um Benutzer-Gruppe und fehlende Beschriftungen fuer bestehende Order-Actions ergaenzt
Versionsnummer auf 0.9.28 angehoben

## Version 0.9.27

Dashboard-Filter fuer Kategorie, Bereich und Status werden jetzt pro Browser-Session gespeichert
Beim erneuten Oeffnen des Dashboards werden die zuletzt gewaehlten Filter automatisch wieder angewendet
Die Auswahl Alle entfernt den gespeicherten Filterwert dauerhaft fuer die aktuelle Session
Versionsnummer auf 0.9.27 angehoben

## Version 0.9.26

Footer-Links mit eigener Theme-Klasse versehen und Kontraste fuer Hell- und Dunkelmodus verbessert
Reiter-Beschriftungen fuer Bootstrap-Tabs im Hell- und Dunkelmodus besser lesbar gemacht
Chatblasen-Farben angepasst, damit User-Nachrichten im Hell- und Dunkelmodus klar lesbar sind
Design-Kontrast-Test im Admin-Bereich um Hauptmenue, Reiter-Navigation, Chat und Footer-Elemente erweitert
Produktions-Logging von standardmaessigem DEBUG auf INFO umgestellt, optional per NEOFAB_LOG_LEVEL konfigurierbar
Gunicorn-Service-Setup fuer stabileren Betrieb auf gthread-Worker, mehrere Worker/Threads und laengeren Request-Timeout erweitert
Setup-Dokumentation fuer die empfohlenen Gunicorn-Produktionsparameter aktualisiert
Versionsnummer auf 0.9.26 angehoben

## Version 0.9.25

Bugfixing bzgl. Update, Fehler im Admin-Bereich entfernt
Versionsnummer auf 0.9.25 angehoben

## Version 0.9.24

Auftrags-Titelanzeige in den Listen angepasst: Titel beginnt jetzt mit der Order-ID im Schema #ID-Titel
Schema verwendet ein fuehrendes # als Nummern-Hinweis und den Bindestrich als Trenner vor dem eigentlichen Titel
Anzeige in Dashboard- und Admin-Listen entsprechend vereinheitlicht

## Version 0.9.23

Benutzer-Registrierung erweitert: Sprache kann jetzt direkt im Registrierungsformular aus einer Auswahlliste gewaehlt werden
Anrede im Registrierungsformular von Freitext auf sprachabhaengiges Auswahlfeld umgestellt
Anrede-Auswahl wird dynamisch an die gewaehlte Sprache angepasst und mit passenden Optionen befuellt
Serverseitige Registrierung validiert die Anrede gegen die erlaubten Werte der ausgewaehlten Sprache

## Version 0.9.22

E-Mail-Versand erweitert: Bei jedem erfolgreichen Versand wird jetzt ein strukturierter Audit-Logeintrag im Log-File geschrieben
Protokolliert werden Versandart (z. B. neuer Auftrag, Statusaenderung, Mitteilung, SMTP-Test), Betreff sowie Empfaengerdaten
Dashboard-Statusfilter nutzt jetzt alle verfuegbaren Auftragsstatus aus der Statuskonfiguration und nicht nur aktuell in der Liste vorkommende Werte

## Version 0.9.21

Dashboard erweitert: In der Zeile mit der Zeilen-Auswahl sind jetzt zusaetzliche Filter fuer Kategorie, Bereich und Status verfuegbar
Die Filter stehen fuer Administratoren und Mitarbeiter im Dashboard bereit
Jedes Filter-Auswahlfeld beginnt mit dem Eintrag Alle
Filterwerte fuer Kategorie, Bereich und Status werden aus den in der Datenbank vorhandenen Auftragsdaten gebildet
Sortierung, Seitenwechsel und Zeilenanzahl behalten die ausgewaehlten Filterwerte bei

## Version 0.9.20

Systemweite Pruefung und Vereinheitlichung der Zeitdarstellung umgesetzt
Alle relevanten UI-Stellen mit Zeitangaben auf gemeinsame Formatter-Logik (`fmt_datetime`) umgestellt
Chat-, Dashboard-, Profil- und Admin-Ansichten zeigen Zeitangaben jetzt konsistent mit der konfigurierten Zeitdifferenz
Order-Detail und abgeleitete Listen/Metadaten verwenden ebenfalls die einheitliche Zeitformatierung
PDF-/Export-Kontexte fuer Auftragsdaten auf dieselbe Zeitlogik umgestellt, um Zeitabweichungen zu vermeiden

## Version 0.9.19

Systemeinstellungen (General) erweitert: Domain-Pruefung fuer Benutzerregistrierung kann per Checkbox aktiviert werden
Freigegebene Registrierungsdomains sind in den Systemeinstellungen als Semikolon-getrennte Liste konfigurierbar
Serverseitige Registrierung validiert E-Mail-Domain gegen die freigegebene Liste, wenn die Pruefung aktiv ist
Registrierungsseite zeigt bei aktiver Domain-Pruefung einen klaren Hinweis auf die erlaubten E-Mail-Domains
Neue Einstellungen sind im JSON-Export/-Import der Systemeinstellungen enthalten
Domain-Abgleich bei Registrierung gehaertet: robustere Normalisierung und Freigabepruefung inklusive Unterdomains
Registrierungs-Abbrueche schreiben jetzt detaillierte Audit-Logeintraege zur Fehleranalyse (inkl. Domain-Pruefdetails)
Delete-Log-Dateiname verkuerzt auf NeoFab_DelLog.log (Legacy-Name wird weiter als Delete-Log erkannt)

## Version 0.9.18

Globales Design-Token-System in custom.css eingefuehrt (Farben, Statusfarben, Abstaende, Radien, Schatten)
Navbar modernisiert mit klarer Hierarchie, aktivem Link-Highlight, Initialen-Avatar und diskreter Versionsanzeige
Status-Badges visuell vereinheitlicht (Pill-Form, konsistente Groessen und Farbverhalten)
Karten, Listen und Dialoge nutzen ein einheitliches Schatten- und Border-System fuer konsistente Tiefe
Formulare vereinheitlicht mit konsistenten Label-Stilen, Radius- und Fokusregeln
Dashboard-Auftragsliste fuer kleine Bildschirme optimiert und als strukturierte Kartenansicht dargestellt
Mobile Aktionsbuttons in Dashboard- und Admin-Listen fuer Touch-Bedienung als vollbreite, vertikale Button-Gruppen optimiert
Theme-Auswahl aus der Navbar entfernt und stattdessen eine persistente Hell/Dunkel-Auswahl in den Benutzereinstellungen ergaenzt
Badge-Farbkontraste fuer Light- und Dark-Theme vereinheitlicht und verbessert (inklusive Info-Variante)
Interne Admin-Seite fuer Design-Kontrast-Smoke-Tests hinzugefuegt (Alerts, Badges, Buttons, Formulare, Tabellen)
Design-Kontrast-Smoke-Test um eine Pass/Fail-Legende mit klarer Pruef-Checkliste erweitert
Design-Kontrast-Smoke-Test um Worst-Case-Szenarien erweitert (lange Texte, deaktivierte Controls, dichte Tabellenzeilen)
Design-Kontrast-Smoke-Test um eine Druckansicht erweitert (A4-optimierte Ausgabe ohne Navigation und Aktionsbuttons)
Druckansicht des Design-Kontrast-Smoke-Tests um Metadaten erweitert (Erstellzeitpunkt, aktuelles Theme, Version)
Light- und Dark-Theme visuell angeglichen: einheitliches Basis-Theme und Dark-Mode ueber CSS-Variablen statt Theme-Familienwechsel
Dark-Mode Feintuning fuer Dashboard/Admin vorgenommen (Tabellenkopf, Link-Kontrast, Paginierung, Outline-Buttons) fuer naehere Light/Dark-Anmutung
Lesbarkeit von Eingabefeldern im Dark-Mode weiter gehaertet (Input-/Textarea-/Select-Text, Placeholder, Disabled-Zustaende und Browser-Autofill)
Dashboard-Layout fuer breite Tabellen verbessert: breiterer Container und no-wrap fuer sortierbare Spaltenkoepfe inkl. Sortier-Icons

## Version 0.9.17

Auf der Register-Seite sind die Felder Anrede, Vorname und Nachname jetzt Pflichtfelder
Die Pruefung erfolgt sowohl im Formular als auch serverseitig bei der Registrierung

## Version 0.9.16

Dashboard zeigt eine neue Spalte Chat fuer alle User-Rollen
In der Spalte Chat wird bei neuen Chat-Nachrichten ein Mail-Icon als Badge angezeigt
Nach dem Lesen der Chat-Nachrichten im Auftrag wird das Icon beim erneuten Dashboard-Aufruf nicht mehr angezeigt
Die Reiter-Beschriftung wurde auf allen Seiten von Kommunikation auf Chat umbenannt
Der untere Chat-Bereich auf der Auftragsseite wird bei ungelesenen Chat-Nachrichten automatisch aufgeklappt und bleibt ohne neue Nachrichten eingeklappt

## Version 0.9.15

In der Plakate-Uebersicht bleibt der Button Loeschen bei Status Gedruckt sichtbar, ist fuer normale Benutzer aber deaktiviert
Solange ein Plakat noch nicht gedruckt ist, koennen normale Benutzer es weiterhin loeschen
Serverseitig ist das Loeschen gedruckter Plakate durch normale Benutzer ebenfalls gesperrt

## Version 0.9.14

Dashboard zeigt das aktuelle Datum und die aktuelle Uhrzeit direkt in der Uebersicht an

## Version 0.9.13

Systemeinstellungen enthalten einen neuen Reiter Bereiche zur Verwaltung von Bereichen
Bereiche koennen als JSON exportiert und importiert werden
Ein Bereich besteht aktuell nur aus einem Bezeichner
Beim Erstellen eines neuen Auftrags muss nach der Kategorie ein Bereich ausgewaehlt werden
Mitarbeiter und Administratoren koennen im Profil auswaehlen, welche Bereiche im Dashboard angezeigt werden

## Version 0.9.12

Im Reiter Artikel koennen Admin und Mitarbeiter den Artikelstatus jetzt auf Bestellt oder Geliefert setzen
Sobald bei einem Beschaffungsauftrag ein Artikel auf Bestellt oder Geliefert gesetzt wird, wechselt der Auftragsstatus automatisch auf In progress
Sobald alle Artikel eines Beschaffungsauftrags auf Geliefert stehen, wird der Auftragsstatus automatisch auf Abgeschlossen gesetzt

## Version 0.9.11

Neue Auftragskategorie Beschaffung wurde hinzugefuegt
Beschaffung verwendet in der Auftragsansicht den neuen Reiter Artikel anstelle des Reiters Plakate
Im Reiter Artikel koennen jetzt Artikelname, Artikel-Beschreibung, Lieferant, Artikel-Link, Anzahl und Preis pro Stueck inkl. MwSt erfasst werden
Pro Artikel kann eine Upload-Bemerkung als Datei hinterlegt und wieder heruntergeladen werden
Fuer Upload-Bemerkungen im Reiter Artikel sind Text-, Word-, PDF- und LibreOffice-Dateien erlaubt

## Version 0.9.10

Im Auftragsbereich wurde das neue Formularfeld Projekt-Gruppe ergaenzt
Projekt-Gruppe kann beim Erstellen und Bearbeiten eines Auftrags gepflegt werden
Projekt-Gruppe wird in den Auftragsdaten sowie im PDF-Export mit ausgegeben
Mitarbeiter koennen Druckauftraege jetzt ebenfalls hochladen, bearbeiten und loeschen
Bei 3D-Druck-Auftraegen wird der Auftragsstatus im Reiter Allgemein automatisch auf Abgeschlossen gesetzt, sobald alle Druckauftraege den Status Druck beendet haben

## Version 0.9.9

Beim Erstellen eines Druckauftrags wird der Auftragsstatus im Dashboard automatisch von New auf In progress gesetzt
Admin und Mitarbeiter koennen Plakatdateien in der Auftragsansicht auf den Status Gedruckt setzen
Der Plakatstatus wird als Badge in der Plakatliste angezeigt und als eigener Status-Button bei den Aktionen eingeblendet
Bei Plotter-Auftraegen setzt das Dashboard den Auftragsstatus automatisch auf Gedruckt, sobald alle Plakate gedruckt sind
Sind bei einem Plotter-Auftrag erst einzelne Plakate gedruckt, wird der Auftragsstatus im Dashboard automatisch als In progress gefuehrt
Order-Statusmeldungen (Neu, In Bearbeitung, Pausiert, Abgeschlossen, Storniert) sind jetzt in allen Sprachen lokalisiert und durchgaengig konsistent
Druckauftrags-Statusmeldungen sind in Deutsch, Englisch und Franzoesisch sprachlich vereinheitlicht und als konsistente Zustandsbegriffe hinterlegt

## Version 0.9.8

Dashboard-Dateizaehler zeigt bei Plotter-Auftraegen die hochgeladenen Plakatdateien statt 3D-Druckdateien
Dashboard blendet Druckauftrags-Zusammenfassung bei Plotter-Auftraegen aus

## Version 0.9.7

Admin-Bereich fasst Material, Drucker-Typen, Filament-Materialien und Farben unter 3D Druck Stammdaten zusammen
Drucker-Typen und Filament-Materialien koennen als JSON exportiert und importiert werden
Dashboard-Auftragsliste kann auf 10, 25 oder 50 Zeilen begrenzt und seitenweise durchblaettert werden
Standard-Zeilenanzahl fuer das Dashboard ist in den Systemeinstellungen unter Allgemein konfigurierbar

## Version 0.9.6

Plotter-Auftraege verwenden im PDF-Export der Projektdokumentation eine eigene Plakat-Sektion
3D-Druck-spezifische Bereiche wie 3D-Dateien, Material, Farbe, Druckauftraege und Filamentwerte werden bei Plotter-PDFs ausgeblendet
Plakatdateien werden im Plotter-PDF mit Dateityp, Thumbnail, Anzahl, gewuenschtem Druckdatum und Bemerkung ausgegeben
Der Fallback-PDF-Export beruecksichtigt Plotter-Auftraege ebenfalls ohne 3D-Druck-Informationen

## Version 0.9.5

Dashboard-Auftragsliste kann nach Kategorie, Titel, Status, Owner und Erstelldatum sortiert werden
Sortierbare Spalten zeigen die aktuelle Sortierrichtung direkt im Tabellenkopf
Die Kategorie ersetzt weiterhin die bisherige ID-Spalte in der Dashboard-Auftragsliste

## Version 0.9.4

Admin-Benutzerverwaltung erlaubt die Zuweisung der allgemeinen Rolle Mitarbeiter
Mitarbeiter koennen im eigenen Profil auswaehlen, welche Auftragskategorien zusaetzlich im Dashboard angezeigt werden
Administratoren koennen diese Dashboard-Kategorien auch in der Benutzerverwaltung fuer Mitarbeiter setzen
Beim Speichern von Benutzern werden nur bekannte Rollen uebernommen
Alte spezialisierte Mitarbeiterrollen werden automatisch auf die Rolle Mitarbeiter migriert

## Version 0.9.3

Plakatdateien koennen in der Auftragsansicht bearbeitet werden
Bemerkung, Anzahl und gewuenschtes Druckdatum lassen sich nachtraeglich aendern
Plakatdateien koennen inklusive Originaldatei und Thumbnail geloescht werden

## Version 0.9.2

Plakatdateien zeigen in der Auftragsansicht ein Thumbnail in der Liste der hochgeladenen Plakate
JPG- und PNG-Dateien werden als echte Bildvorschau verkleinert
PDF-Dateien erhalten nach Moeglichkeit eine Vorschau der ersten Seite, andernfalls eine PDF-Vorschaukachel
Poster-Thumbnails werden separat gespeichert und ueber eine geschuetzte Route ausgeliefert

## Version 0.9.1

Plotter-Auftraege verwenden in der Order-Ansicht den Reiter Plakate statt 3D-Modelle / Bilder
Plakate koennen als JPG, PNG oder PDF mit Bemerkung, Anzahl und gewuenschtem Druckdatum hochgeladen werden
Plakatdateien werden separat von 3D-Modellen gespeichert und koennen je Auftrag mehrfach hinterlegt werden
Bestehende Plotter-Kategorien werden automatisch auf den neuen Plakate-Reiter migriert

## Version 0.9.0

Auftraege erhalten eine Kategorie als Stammdatum, initial mit 3D-Druck, Plotter und CNC-Fraesen
Bestehende Auftraege werden automatisch der Kategorie 3D-Druck zugeordnet
Generische Work-Job- und Kategorie-Berechtigungsmodelle als langfristige Basis fuer nicht additive Fertigungsauftraege ergaenzt
Neue Auftraege koennen direkt mit einer Kategorie angelegt werden
Auftragsdetails zeigen nur die fuer die Kategorie sichtbaren Reiter; 3D-Druckauftraege behalten den Druckauftrags-Reiter
G-Code-Druckauftraege sind serverseitig auf 3D-Druckauftraege beschraenkt

## Version 0.8.12

Kostenstelle bearbeiten enthaelt einen PDF-Export mit Kostenstellendaten, Exportdatum und den zugeordneten Auftraegen
Druckauftraege speichern Drucker-Typ und Filament-Material individuell je Druckauftrag statt gemeinsam am Auftrag
Druckauftragstabelle zeigt den Drucker-Typ je Druckauftrag und berechnet Kosten mit den individuellen Druckauftrag-Werten

## Version 0.8.11

Anleitung zur Kostenermittlung fuer 3D-Drucker im Doku-Ordner ergaenzt
Berechnungsformeln fuer Maschinenkosten, Materialkosten und Druck-Gesamtkosten dokumentiert
Beispielwerte fuer Drucker-Typen und Filament-Materialien mit aktuellen Marktbeispielen ergaenzt
Kostenstelle bearbeiten zeigt in der Auftragsliste die Gesamtkosten je Auftrag und die Summe aller Auftraege der Kostenstelle

## Version 0.8.10

Kostenstellenliste zeigt die Anzahl der Auftraege je Kostenstelle direkt nach der Spalte Aktiv
Kostenstelle bearbeiten zeigt unter dem Formular eine Liste der Auftraege, die diese Kostenstelle verwenden
Kostenstellen-Auswahl in Auftraegen zeigt nur aktive Kostenstellen
Druckauftrag bearbeiten enthaelt die Auswahlfelder Drucker-Typ und Filament-Material
Drucker-Typen enthalten Kostenfelder fuer Maschinenstundensatz, Wartung pro Stunde und Ruestkostenpauschale
Filament-Materialien enthalten Preis pro kg, Materialaufschlag, Trocknungspauschale, Handlingpauschale und berechneten Preis pro Gramm
Druckauftrag bearbeiten berechnet Druckkosten aus Druckdauer, Filamentgewicht, Drucker-Typ und Filament-Material
Druckauftragstabelle zeigt die berechneten Gesamtkosten nach der Spalte Filament

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
