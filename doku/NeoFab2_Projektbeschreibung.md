# NeoFab2 – Projektbeschreibung und Umsetzungsauftrag

Stand: 17.09.2026. Dieses Dokument beschreibt die Planung; es implementiert keine Anwendung und autorisiert keine Löschung von Bestandsdaten.

Die [Funktionsmatrix](NeoFab2_Funktionsmatrix.md) ergänzt diese Spezifikation um den erfassten NeoFab-Bestand, stabile Funktions-IDs, Zielzuordnungen, Quellanker und Prüfkriterien. Codex soll sie vor jedem Arbeitspaket lesen und den Umsetzungsnachweis bei Änderungen fortführen. Als Vorschlag markierte Modulgrenzen sind vor Umsetzung zu entscheiden.

## 1. Ziel und verbindliche Rahmenbedingungen

NeoFab2 wird als neue modulare Webanwendung in einem eigenen Repository aufgebaut. Zuerst entsteht ein unabhängig lauffähiges Core-System. Fachfunktionen werden anschließend einzeln als Plugins ergänzt.

Aus NeoFab werden ausschließlich Benutzer übernommen. Alte Aufträge einschließlich Nachrichten, Terminen, Anhängen und Fertigungsdaten müssen nicht migriert werden. Der bevorstehende Semesterwechsel ist der gewünschte Umstellungsanlass, aber noch kein festgelegtes Lieferdatum. NeoFab bleibt bis zur Umstellung unverändert nutzbar.

Stammdaten wie Maschinen, Materialien und Kostenstellen sind keine automatisch zugesagte Migration. Ihre optionale Übernahme wird vor Umsetzung des jeweiligen Plugins entschieden. Bestehende Geschäftslogik darf nach Prüfung wiederverwendet werden; eine vollständige Kopie der bisherigen Architektur ist nicht das Ziel.

## 2. Erfasster Ausgangsstand

- Repository: NeoFab.
- Anwendungsversion: 0.9.62 aus `neofab/version.py`.
- Git-Referenz: `2673096675db2ccfb824abca0946607e87416819`.
- Arbeitsverzeichnis vor Erstellung dieses Dokuments: ohne von Git gemeldete Änderungen.
- Grundlage: statische Sichtung von Code und Dokumentation, kein Laufzeit- oder Produktionsaudit. Die Referenz erfasst den Quellstand, nicht den Inhalt produktiver Datenbanken oder Uploads.

| Bereich | Vorhandener Stand | Einordnung für NeoFab2 |
|---|---|---|
| Benutzer | Anmeldung, Registrierung, Rollen, Profile, Aktivierung, Passwort-Reset, deaktivierte und gelöschte Konten | Core; Benutzerimport |
| Oberfläche | Flask/Jinja, Bootstrap, Dashboard, Deutsch/Englisch/Französisch, Darstellungseinstellungen | Gemeinsame Oberfläche neu strukturieren |
| Aufträge | Kategorien, Bereiche, Nummerierung, Status, Archivierung, Dateien, Nachrichten | Späteres gemeinsames Auftragsmodul |
| 3D-Druck | Modelle, Viewer, G-Code, Druckaufträge, Maschinen, Materialien, Kosten | Späteres Fachplugin |
| Transferdruck | Neu geplanter Funktionsbereich; hier kein bestehender Fachworkflow erfasst | Eigenständiges zukünftiges Fachplugin |
| Plotten | Plakatdateien, Vorschauen, Papier, Plotter, Formate, Deckungsgrad und Kosten | Späteres Fachplugin |
| Beschaffung | Artikel, Anhänge, Preise, Bestell- und Lieferstatus | Späteres Fachplugin |
| CNC/Fräsen | Kategorien und allgemeine Arbeitsaufträge vorhanden | Fachlicher Umfang vor Plugin-Umsetzung klären; keine Gleichwertigkeit mit 3D-Druck unterstellen |
| Termine | Auftragsgebundene Anfragen, Vorschläge, Auswahl, Bestätigung und Kalenderdarstellung | Später abgrenzen; kein bestehendes allgemeines Veranstaltungsmodell |
| Lernmaterialien | Trainingsvideos, Playlists und PDF-Anhänge | Optionales Lernmaterial-Plugin |
| Workshops | Kein eigenständiges Veranstaltungs- und Anmeldemodell erkennbar | Erstes neues Fachplugin |
| Betrieb | Einstellungen, SMTP, Benachrichtigungen, Zeitbehandlung, Audit-Logs, Setup-/Update-Skripte | Core-Dienste und neue Betriebsdokumentation |

Wichtige Codebezüge im bisherigen Repository:

- `neofab/app.py`: globaler Flask-Anwendungsstart, Fachrouten, Dashboard und zahlreiche Schema-Anpassungen.
- `neofab/models.py`: gemeinsame Modelldatei mit direkten Beziehungen zwischen Benutzer-, Auftrags- und Fertigungsdaten.
- `neofab/routes/admin.py`: bestehendes Admin-Blueprint als Modularisierungsansatz.
- `neofab/auth_utils.py`: Rollenprüfung und Sitzungszeitlimit.
- `neofab/notifications.py`: E-Mail-Versand mit zahlreichen fachbezogenen Funktionen.
- `neofab/schema_utils.py`: eigene Schema-Hilfen, teilweise ausdrücklich SQLite-spezifisch.
- `neofab/templates/base.html`: fest eingebaute Navigation.
- `neofab/config.py`, `neofab/time_utils.py`, `neofab/i18n_utils.py`: Einstellungen, Zeit und Sprache.
- `doku/` und `script/`: Fach- und Betriebsdokumentation.

Es besteht noch kein allgemeiner Plugin-Vertrag. Die README nennt SQLite, MariaDB und PostgreSQL; eine durchgängige Kompatibilität ist damit nicht nachgewiesen. NeoFab2 soll nur Datenbanken als unterstützt ausweisen, die tatsächlich geprüft werden.

## 3. Repository-Entscheidung

Empfehlung: ein Repository `NeoFab2` für Core und zunächst alle eigenen Plugins. Ein Plugin ist eine fachlich und technisch getrennte Erweiterung, nicht zwingend ein eigenes Git-Repository oder ein eigener Dienst.

Vorteile: gemeinsame Änderungen an Schnittstellen und ihren Nutzern, eine reproduzierbare Installation, gemeinsame Integrationstests und weniger Abstimmungsaufwand. Core und Plugins erhalten trotzdem eigene Verantwortungsgrenzen und Plugin-Versionsangaben.

Separate Plugin-Repositories werden sinnvoll, wenn andere Teams sie unabhängig entwickeln, eigene Veröffentlichungszyklen benötigen oder Plugins separat vertrieben werden. Das ist eine spätere Entscheidung. Keine Git-Submodule für den Einstieg.

Vorgeschlagene Struktur; Namen dürfen bei der Initialisierung konsistent angepasst werden:

```text
NeoFab2/
  pyproject.toml
  src/neofab2/
    __init__.py              # create_app
    core/                   # Benutzer, Rechte, Einstellungen, Oberfläche
    services/               # Benachrichtigungen, Dateien, Hintergrundaufgaben
    plugin_api/             # dokumentierte Erweiterungsschnittstellen
    plugins/
      workshops/            # erst nach Core-Abnahme
      orders/               # gemeinsame Auftragsbasis, später
      plotting/             # später
      procurement/          # später
      printing3d/           # eigenständiges 3D-Druck-Plugin, später
      transfer_printing/    # eigenständiges Transferdruck-Plugin, später
      milling/              # später
    templates/
    static/
  migrations/               # zentrale, geordnete Migrationen mit Modulzuordnung
  tests/
    core/
    plugin_contract/
    integration/
    fixtures/plugins/       # minimales Testplugin, keine Fachfunktion
  doku/
    NeoFab2_Projektbeschreibung.md
    NeoFab2_Projektstart_Codex.md
    Version_Timeline.md
    SETUP.md
    architecture.md
    plugin-development.md
    operations.md
  script/
    README.md
    setupNeoFab
    setupNeoFabService
    upDateNeoFabService
    resetAdminPassword
```

## 4. Technisches Zielbild

Planungsbasis ist ein modularer Monolith: eine Flask-Anwendung mit Application Factory, SQLAlchemy, Jinja und gemeinsamer Datenbank. Dies nutzt vorhandene Erfahrung und wiederverwendbare Logik. Konkrete unterstützte Python-/Bibliotheksversionen und die produktive Datenbank werden beim Projektstart festgelegt und dokumentiert. Keine parallele Unterstützung mehrerer Datenbanken ohne entsprechenden Testumfang.

Der Core darf keine Fachplugins importieren oder deren Tabellen voraussetzen. Plugins verwenden veröffentlichte Schnittstellen statt interner Core-Implementierungen. Fachübergreifende Zugriffe erfolgen über deklarierte Schnittstellen und Abhängigkeiten, nicht über beliebige gegenseitige Modellimporte. Benutzerbezogene Fremdschlüssel in Plugin-Tabellen sind zulässig; Benutzerbeziehungen zu jedem Plugin gehören nicht ins Core-Modell.

Anwendungsstart und Schemaänderungen werden getrennt. Versionierte Migrationen, beispielsweise mit Alembic, laufen als expliziter Bereitstellungsschritt; keine spontanen `ALTER TABLE`-Operationen in normalen Seitenaufrufen. In der ersten gemeinsamen Distribution gibt es eine zentral geordnete Migrationshistorie mit klarer Zuordnung zum jeweiligen Modul. Ein unabhängiger Paketinstaller ist zunächst nicht vorgesehen.

## 5. Erste Ausbaustufe: Core

### Funktionsumfang

- Anmeldung und Abmeldung, sichere Sitzungen und konfigurierbare Inaktivitätsgrenze.
- Benutzerverwaltung, Profile, Aktivieren/Deaktivieren, kontrollierter Administrator-Erstzugang.
- Konfigurierbare Registrierung, E-Mail-Aktivierung und Passwort-Reset.
- Rollen als Bündel von Berechtigungen; Ausgangsrollen Benutzer, Mitarbeiter und Administrator. Bisherige Rollenwerte beim Import explizit zuordnen.
- Zentrale Rechteprüfung auch auf Serverseite. Plugins deklarieren Rechte wie `workshops.manage_own` und `workshops.manage_all`; Objektbesitz wird zusätzlich geprüft.
- Gemeinsames responsives Layout, Navigation, Startseite ohne Auftragsabhängigkeit, Profil- und Admin-Seiten.
- Sprachunterstützung DE/EN/FR mit definiertem Fallback sowie konsistente UTC-Speicherung und konfigurierbare lokale Anzeige.
- Systemeinstellungen, SMTP-Konfiguration mit Testversand, konfigurierbare Impressums-/Datenschutzinhalte.
- Technischer Benachrichtigungsdienst: persistente Versandaufträge, Zustellstatus und kontrollierte Wiederholungen. Fachliche Empfänger und Texte kommen aus dem jeweiligen Modul.
- Minimale Ausführung fälliger Aufgaben über einen dokumentierten Worker oder CLI-Aufruf; kein eigener umfangreicher Workflow-Baukasten.
- Gemeinsamer Dateidienst mit Modulzuordnung und Berechtigungsprüfung, soweit für Plugin-Vertrag und sichere Bereinigung erforderlich.
- Audit-Logs, nachvollziehbare Fehler, Betriebsstatus sowie dokumentierte Installation, Updates, Sicherung und Wiederherstellung.
- Plugin-Übersicht mit Version, Abhängigkeiten, Kompatibilität und Aktivierungszustand.
- Benutzerimport mit Vorschau und Ergebnisbericht.

### Bewusst noch nicht enthalten

Keine produktiven Workshops, Aufträge, Fertigungsfunktionen, Beschaffung, Terminverwaltung oder Lernmaterialien. Kein Plugin-Marktplatz, kein Code-Upload über die Weboberfläche, kein Nachladen fremden Codes während des Betriebs, keine Microservices. Ein kleines Testplugin dient ausschließlich dem Nachweis der Schnittstellen.

### Abnahmekriterien

1. Der Core startet mit leerer Datenbank nach expliziter Migration und ohne aktive Fachplugins.
2. Anmeldung, Kontostatus, Rechteprüfung, Aktivierung und Passwort-Reset sind einschließlich wichtiger Fehlerfälle geprüft.
3. Benutzer können administrative Aktionen weder über die Oberfläche noch per direktem HTTP-Aufruf ausführen.
4. Ein Testplugin bindet eine Seite, einen Menüeintrag und ein Recht über den Plugin-Vertrag ein. Deaktivierung sperrt auch direkte Zugriffe und seine Aufgaben.
5. Fehlende oder inkompatible Abhängigkeiten verhindern eine Aktivierung mit verständlicher Fehlermeldung. Das Entfernen benötigter Abhängigkeiten wird verhindert.
6. Benutzerimport wurde mit synthetischen Daten geprüft: wiederholter Import erzeugt keine Duplikate, Kontostatus und Rollen bleiben korrekt, Zugangsdaten erscheinen nicht im Log.
7. Ein SMTP-Ausfall vernichtet keine gespeicherten fachlichen Vorgänge; Versandfehler sind sichtbar und erneut bearbeitbar. Wiederholungen dürfen vermeidbare Doppelzustellungen nicht erzeugen; exakt einmalige externe SMTP-Zustellung wird nicht versprochen.
8. Migration einer vorherigen Testschema-Version, Sicherung und Wiederherstellung werden nachvollziehbar geprüft.
9. Installation, Betrieb und Entwicklung eines Plugins sind so dokumentiert, dass kein Wissen aus diesem Chat erforderlich ist.
10. Basisinstallation, Service-Einrichtung, Update und Notfall-Passwort-Reset sind über die vertrauten Skripte gemäß Abschnitt 11 bedienbar und in einer isolierten Testinstallation geprüft.

## 6. Minimaler Plugin-Vertrag

Jedes Plugin deklariert Kennung, Anzeigename, Version, unterstützte Plugin-API-Version und Abhängigkeiten. Es kapselt seine Routen/Blueprints, Fachmodelle, Templates, Übersetzungen, Einstellungen und Berechtigungen.

Der Core stellt Registrierungspunkte für Navigation, Admin-Einstellungen, Berechtigungen, Benachrichtigungen und fällige Aufgaben bereit. Erweiterungen werden nur nach Prüfung ihrer Metadaten und Abhängigkeiten aktiviert. Ein defektes optionales Plugin darf nicht stillschweigend als aktiv angezeigt werden; Startfehler und eingeschränkter Betrieb müssen ausdrücklich erkennbar sein.

Aktivierungsänderungen erfolgen zunächst mit kontrolliertem Neustart aller Web- und Worker-Prozesse. Deaktivierung ist keine Deinstallation und löscht keine Tabellen oder Dateien. Noch wartende Plugin-Aufgaben werden pausiert. Ein Plugin ist vertrauenswürdiger Python-Code mit Prozessrechten; die Plugin-Struktur ist keine Sicherheits-Sandbox.

Plugin-spezifische Tabellen und Dateien besitzen eindeutige Namensräume. Core-Migrationen dürfen keine Fachplugin-Tabellen benötigen. Die gemeinsame Distribution darf installierte, aber deaktivierte Plugins beim geregelten Schema-Update berücksichtigen. Weitere Lifecycle-Details werden vor einer späteren getrennten Paketverteilung ergänzt.

## 7. Benutzerübernahme und Umstellung

Der Import liest einen geschützten Export oder eine Kopie der bisherigen Datenbank ausschließlich lesend. Er importiert keine Aufträge oder Dateien und verschickt im Probelauf keine E-Mails.

Zu übernehmen: stabile Quellzuordnung, E-Mail, Passwort-Hash soweit kompatibel, benötigte Profilfelder, Sprache, Darstellung, Aktivstatus und sinnvoll zuordenbare Präferenzen. Eine Quell-ID-Zuordnung macht wiederholte Importe nachvollziehbar; gleiche numerische Ziel-IDs sind ohne migrierte Aufträge nicht zwingend erforderlich.

Vor Ausführung festlegen: Behandlung gelöschter Konten, unbekannter Rollen und kollidierender E-Mail-Adressen. Deaktivierte oder noch nicht aktivierte Konten dürfen durch den Import nicht aktiv werden. Alte Sitzungen, Aktivierungs- und Reset-Tokens werden nicht übernommen. Fachbezogene Einstellungen und Berechtigungen werden nicht blind kopiert. Hash-Kompatibilität wird mit kontrollierten Testkonten nachgewiesen; unbrauchbare Hashes erfordern einen gezielten Reset.

Es gibt keine dauerhafte Synchronisierung zwischen beiden Anwendungen. Ein letzter Import folgt auf einen vereinbarten kurzen Änderungsstopp für Benutzerkonten im Altsystem. Danach ist NeoFab2 die führende Benutzerverwaltung. Ein dokumentierter Rückfallplan berücksichtigt, dass nach der Freischaltung neue Konten und Vorgänge nur in NeoFab2 existieren.

Das Abschalten oder Löschen des bisherigen Systems ist eine spätere explizite Betriebsentscheidung und kein Bestandteil der Core-Implementierung.

## 8. Weitere Ausbaustufen

### Erstes Fachplugin: Workshops und Schulungen

- Mitarbeiter und Admins erstellen Entwürfe und veröffentlichen Veranstaltungen.
- Titel, Beschreibung, Veranstalter, Ort, Beginn/Ende, Teilnehmerlimit und Anmeldeschluss.
- An- und Abmeldung durch Benutzer; Schutz vor Doppelanmeldung und Überbuchung auch bei parallelen Anfragen.
- Veranstalter verwalten eigene Angebote, Admins alle Angebote; Teilnehmerdaten nur für Berechtigte.
- Bestätigung, Änderungs- und Absageinformationen sowie dauerhaft einsehbare Mitteilungshistorie.
- Später: Wartelisten, Erinnerungen, Serientermine, Teilnahmebescheinigungen und Qualifikationsnachweise.
- Keine Abhängigkeit vom Auftragsmodul.

### Auftragsbasis und Fertigungsplugins

Vor dem ersten auftragsbasierten Plugin entsteht ein gemeinsames `orders`-Modul für Auftragsnummer, Besitzer, grundlegenden Lebenszyklus und gemeinsame Kommunikation. Plotten, Beschaffung, 3D-Druck, Transferdruck und Fräsen werden jeweils als eigenständige Plugins umgesetzt und ergänzen ihre Fachdaten, Formulare und Abläufe. Welche Funktionen tatsächlich gemeinsam sind, wird anhand der ersten beiden Plugins überprüft statt vorab umfassend abstrahiert.

### Eigenständiges Plugin: 3D-Druck

`printing3d` kapselt Modell-Uploads und Vorschauen, G-Code und Metadaten, Druckaufträge, Druckerprofile, Filamente, Farben, Druckstatus und Kostenberechnung. Vorhandene Logik ist eine Referenz, kein verpflichtender Komplettumfang der ersten Plugin-Version. Der konkrete Erstumfang wird vor Implementierung festgelegt. Der Core enthält keine druckspezifischen Felder oder Abläufe; das Plugin verwendet die gemeinsame Auftragsbasis und technische Core-Dienste.

### Eigenständiges Plugin: Transferdruck

`transfer_printing` wird unabhängig von Plotten und 3D-Druck aktivierbar. Als fachlicher Planungsrahmen dienen Motivdateien, Trägermaterial beziehungsweise Artikel, Druckposition, Motivgröße, Stückzahl, Produktionsstatus und Kosten. Das konkrete Druckverfahren (zum Beispiel DTF, Sublimation oder Transferfolie), Material-/Artikelverwaltung und die Kostenformel sind vor Umsetzung abzustimmen; diese Beispiele sind noch keine zugesagten Funktionen. Gemeinsame technische Dateifunktionen können wiederverwendet werden, ohne eine zwingende Abhängigkeit vom Plotter-Plugin einzuführen.

### Reihenfolge und Termine

Priorität nach Workshops vorschlagsweise Plotten oder Beschaffung, dann weitere Dienste nach Semesterbedarf. Reihenfolge und Umfang sind noch nicht verbindlich. Bestehende Berechnungen dürfen mit repräsentativen Prüffällen übernommen werden.

Auftragstermine und Workshop-Termine bleiben fachlich getrennt. Ein späterer gemeinsamer Kalender kann beide über definierte Schnittstellen darstellen.

## 9. Jährliche Bereinigung

Die Architektur berücksichtigt einen gemeinsamen Bereinigungsvertrag. Jedes Plugin beschreibt seine bereinigbaren Daten und zugehörigen Dateien sowie Ausschlussgründe. Core-Benutzer und Stammdaten werden nicht automatisch mit Vorgängen gelöscht.

Die erste tatsächliche Bereinigungsfunktion wird mit einem Fachplugin umgesetzt: Vorschau, expliziter Stichtag, Auswahl zulässiger abgeschlossener Vorgänge, berechtigte Bestätigung und Ergebnisprotokoll. Wiederholungen nach Teilfehlern müssen möglich sein. Eine jährliche Erinnerung oder Automatisierung kann später folgen; jährlich bereinigen bedeutet nicht automatisch, alle Daten nach genau 365 Tagen zu löschen. Backups besitzen eine getrennte Aufbewahrungsregel.

Qualifikationsnachweise können andere Aufbewahrungsregeln benötigen als Veranstaltungsanmeldungen. Vor ihrer Implementierung ist diese Trennung festzulegen.

## 10. Arbeitsauftrag für Codex im neuen Repository

Folgender Startauftrag kann zusammen mit diesem Dokument verwendet werden:

> Lies zuerst `doku/NeoFab2_Projektstart_Codex.md` und `doku/NeoFab2_Projektbeschreibung.md`. Baue NeoFab2 gemäß diesen Vorgaben. Implementiere zunächst ausschließlich die erste Ausbaustufe Core einschließlich Benutzerimport und minimalem Plugin-Vertrag. Verwende ein Testplugin zum Nachweis der Erweiterbarkeit; implementiere noch keine produktiven Fachplugins. Prüfe zuerst das Repository und vorhandene AGENTS.md-Anweisungen. Halte Architekturentscheidungen, den Umsetzungsstand und offene Entscheidungen im Repository fest. Arbeite in kleinen, überprüfbaren Schritten, prüfe Berechtigungen, Migrationen, Import und Plugin-Lifecycle mit aussagekräftigen Tests und dokumentiere Installation und Betrieb. Behalte die Skript-Bedienung und Dokumentationsweise gemäß Abschnitt 11 bei. Bei einer angeforderten Versionsänderung aktualisiere automatisch die Versionshistorie und bereite Commit-Titel und Commit-Beschreibung gemäß Abschnitt 12 vor; führe keinen Git-Commit oder Push aus. Verwende nur synthetische Testdaten. Ändere weder das alte NeoFab noch produktive Datenbanken. Produktivmigration, Veröffentlichung und Löschung sind nicht Teil dieses Auftrags. Melde den Core erst als abgeschlossen, wenn seine Abnahmekriterien erfüllt sind; benenne verbleibende Einschränkungen ausdrücklich.

Empfohlene Arbeitspakete für den Core:

1. Projektgerüst, dokumentierte Stack-/Datenbankentscheidung, Application Factory, Konfiguration, CI und erste Migration.
2. Benutzer, Authentifizierung, Rechte und Admin-Erstzugang.
3. Layout, Profil, Sprache, Einstellungen und Systemadministration.
4. Plugin-Vertrag, Testplugin und Lifecycle-Prüfungen.
5. Benachrichtigungen, minimale Hintergrundausführung und Audit-Logs.
6. Benutzerimport, Betriebsdokumentation und vollständige Core-Abnahme.

Bei Projektstart noch festzulegen: produktive Datenbank und Laufzeitumgebung, Registrierungsregeln, Zuordnung bisheriger Rollen, Behandlung gelöschter Benutzer und konkrete zum Semesterstart erforderliche Plugins. Dafür keine stillschweigenden produktiven Annahmen treffen; unabhängige Implementierungsschritte können dennoch vorbereitet werden.

## 11. Installationsskripte und Betriebsdokumentation beibehalten

Die bisherige Bedienungsweise ist eine ausdrückliche Anforderung. NeoFab2 behält die Verzeichnisse `script/` und `doku/` sowie die vertrauten Skriptnamen bei. Die zuvor vorgeschlagene Ablage unter `docs/PROJECT.md` entfällt zugunsten von `doku/NeoFab2_Projektbeschreibung.md`.

| Skript | Geforderte Aufgabe in NeoFab2 |
|---|---|
| `script/setupNeoFab` | Interaktive Basisinstallation mit verständlichen Vorgaben für Benutzer, Installationspfad und Admin-Zugang; virtuelle Python-Umgebung, Abhängigkeiten und explizite Migrationen; optionaler Teststart |
| `script/setupNeoFabService` | Einrichtung des Gunicorn-/systemd-Betriebs auf Basis der Installation; erforderliche Worker oder Timer ebenfalls einrichten und erklären |
| `script/upDateNeoFabService` | Kontrolliertes Update aus Git mit Dienststeuerung, Abhängigkeiten, expliziten Datenbankmigrationen, Neustart und Statusprüfung; Sicherung und Fehlerbehandlung dokumentieren |
| `script/resetAdminPassword` | Lokale Notfallwiederherstellung ohne funktionierende Webanmeldung: vorhandene Admin-Konten ermitteln, Konto auswählen und neues Passwort setzen |

Die Implementierung muss an Application Factory, neue Konfiguration und Modelle angepasst werden. Alte Skripte nicht ungeprüft kopieren. Passwort-Reset verwendet einen geprüften Core-Zugang und verdeckte Passworteingabe; Passwörter gehören nicht in Logs. Bestehende fest vorgegebene Notfallpasswörter sind keine zwingende Kompatibilitätsanforderung.

NeoFab2 erhält eigene Standardpfade und Dienstnamen, damit eine parallele Testinstallation NeoFab nicht überschreibt oder stoppt. Zielumgebung bleibt zunächst der bisherige Linux-Betriebsweg mit Debian, LXC/VM/Server und systemd; unterstützte Versionen werden beim Projektstart festgelegt und getestet.

Dokumentationsstil: deutschsprachige, schrittweise Anleitungen mit kopierbaren Befehlen, klar benannter Ausgangssituation, Ausführungsbenutzer, Installationspfaden, Standardwerten, erwarteten Ergebnissen und Hilfe bei Fehlern. `script/README.md` enthält den Schnellstart, `doku/SETUP.md` die ausführliche Anleitung; die Projekt-README verlinkt beide. Beispiele müssen die tatsächlich implementierten NeoFab2-Pfade und Dienste verwenden. Die bisherigen Dateien dienen als Referenz für Bedienung und Erklärung, nicht als unverändert gültige NeoFab2-Anleitung.

## 12. Versionsänderungen, Timeline und manuelle Commits

Diese Regel gilt für NeoFab2 und wird bei der Initialisierung zusätzlich in dessen `AGENTS.md` verankert, damit sie bei späteren Codex-Aufträgen berücksichtigt wird.

Wenn der Benutzer eine Versionsänderung anfordert, führt Codex im selben Arbeitsschritt Folgendes aus:

1. Die gewünschte Version an der zentralen Versionsquelle ändern und vorhandene Versionsangaben in Metadaten, Oberfläche und README konsistent nachführen. Ohne ausdrücklichen Versionsauftrag keine automatische Erhöhung bei jeder Bearbeitung. Anfangsversion und Versionsschema von NeoFab2 beim Projektstart festlegen; nicht ungefragt die NeoFab-Version fortsetzen.
2. `doku/Version_Timeline.md` automatisch ergänzen, neuester Eintrag zuerst, mit Version, Datum, betroffenem Core/Plugin, tatsächlich umgesetzten Änderungen, relevanten Migrations-/Betriebshinweisen und Ergebnis der ausgeführten Prüfungen. Geplante Funktionen nicht als fertig dokumentieren; nicht ausgeführte Prüfungen ausdrücklich kennzeichnen.
3. Einen kopierbaren Commit-Titel und eine passende Commit-Beschreibung direkt im Versionseintrag hinterlegen und in der Abschlussantwort darauf verweisen. Die Beschreibung fasst die Änderungen dieser Version einschließlich Dokumentation und Prüfungen zusammen; Geheimnisse und Benutzerdaten dürfen nicht enthalten sein.
4. Den tatsächlichen Commit dem Benutzer in GitHub Desktop überlassen. Codex führt weder `git commit` noch einen Push aus und meldet keinen Commit als erledigt. Titel und Beschreibung sind die Übergabe für den manuellen Versions-Commit.

Für separat angeforderte Plugin-Versionsänderungen wird das betroffene Plugin benannt und dessen Version aktualisiert. Eine Änderung aller anderen Plugin-Versionen ist dadurch nicht automatisch erforderlich. Die gemeinsame Timeline dokumentiert auch diese Änderungen.

Vorlage für einen Eintrag; Platzhalter vor Verwendung durch reale Angaben ersetzen:

```markdown
## Version <Version> – <YYYY-MM-DD>

Bereich: <Core / Distribution / Plugin-Kennung>

### Änderungen
- <Tatsächlich umgesetzte Änderung>

### Betrieb und Migration
- <Erforderliche Schritte oder: keine erforderlich>

### Prüfungen
- <Prüfung und tatsächliches Ergebnis>

### Commit für GitHub Desktop
Commit-Titel: <Version>: <kurze Beschreibung>

Commit-Beschreibung:
- <Änderung und Zweck>
- <Dokumentation, Migration und relevante Prüfungen>

Der Commit wird manuell in GitHub Desktop erstellt.
```

Die bisherige `doku/Version_Timeline.md` von NeoFab bleibt dessen historische Versionsliste. NeoFab2 erhält eine eigene Timeline. Das Erstellen dieser Planungsunterlagen ist keine Versionsänderung der Anwendung NeoFab.
