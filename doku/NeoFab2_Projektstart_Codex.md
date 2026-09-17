# NeoFab2 – Projektstart für Codex

Stand: 17.09.2026. Übergabe aus dem bisherigen Repository NeoFab in das neu anzulegende Repository NeoFab2.

## Zweck und Verwendung

Diese Zusammenfassung ist keine technische Voraussetzung für das Anlegen eines Git-Repositories. Sie hält die getroffenen Entscheidungen unabhängig vom Chat fest und dient als Einstieg für die Umsetzung durch Codex.

Vorbereitete Unterlagen aus diesem Repository in das neue Repository übernehmen:

1. Diese Datei nach `doku/NeoFab2_Projektstart_Codex.md` kopieren.
2. Die [Projektbeschreibung](NeoFab2_Projektbeschreibung.md) nach `doku/NeoFab2_Projektbeschreibung.md` kopieren. Sie enthält den detaillierten Umfang und die Abnahmekriterien.
   Die [Funktionsmatrix](NeoFab2_Funktionsmatrix.md) ebenfalls nach `doku/NeoFab2_Funktionsmatrix.md` übernehmen; sie liefert Funktions-IDs, Zuordnungen, Quellanker und Prüfkriterien für die Arbeitspakete.
3. Die bisherigen `script/README.md`, `script/setupNeoFab`, `script/setupNeoFabService`, `script/upDateNeoFabService`, `script/resetAdminPassword` und `doku/SETUP.md` als Referenzen zugänglich machen, beispielsweise aus dem lokalen alten Checkout. Nicht ungeprüft als funktionsfähige NeoFab2-Skripte ausweisen.
4. Keine produktive Datenbank, Upload-Verzeichnisse, Konfigurationsgeheimnisse oder Benutzerexporte ins neue Repository kopieren. Referenzcode auf dem dokumentierten Quellstand lesen.

## Ausgangspunkt

- NeoFab 0.9.62, Quellstand `2673096675db2ccfb824abca0946607e87416819`.
- Flask, SQLAlchemy, Flask-Login, Jinja und Bootstrap; vorhandene Funktionen sind in der Projektbeschreibung erfasst.
- Bisher keine allgemeine Plugin-Architektur; Fachfunktionen sind eng mit Anwendungsstart, Modellen und Navigation verbunden.
- Neuer Aufbau mit Benutzerübernahme ist beschlossen. Alte Aufträge, Nachrichten, Termine und Dateien sind nicht zu migrieren.
- Semesterbeginn ist der Umstellungsanlass; Termin und bis dahin benötigter Funktionsumfang sind noch festzulegen.

## Getroffene Architekturentscheidungen

- Ein Repository `NeoFab2`, darin Core und eigene Plugins in getrennten Verzeichnissen.
- Zuerst ein ohne Fachplugins lauffähiger Core. Kein produktives Fachplugin vor dessen Abnahme.
- Gemeinsame Anwendung und Datenbank, Application Factory, explizite versionierte Migrationen und dokumentierter Plugin-Vertrag.
- Core: Benutzer, Anmeldung, Rechte, Oberfläche, Sprache, Einstellungen, technische Dienste, Plugin-Verwaltung und Benutzerimport.
- Erstes Fachplugin: Workshops/Schulungen mit Anmeldung und Teilnehmerinformationen.
- Weitere eigenständige Plugins: **3D-Druck, Plotten, Transferdruck, Beschaffung/Bestellung und CNC/Fräsen**. Gemeinsame Auftragsfunktionen liegen im späteren `orders`-Modul.
- Weitere mögliche Module: Lernmaterialien und Terminverwaltung; gemeinsame Kalenderanzeige später, fachliche Termine bleiben ihren Modulen zugeordnet.
- Transferdruck ist ein eigener Bereich; Verfahren und Erstumfang vor dessen Implementierung klären.
- Plugin-Deaktivierung erhält Daten und sperrt Seiten sowie Hintergrundaufgaben. Aktivierungsänderungen zunächst mit Neustart.
- Jährliche Bereinigung später mit Vorschau, Stichtag und Plugin-Regeln; keine automatische Löschung von Benutzern oder Stammdaten.

## Verbindliche Arbeitsweise

Die ausführliche Projektbeschreibung ist die Spezifikation. Bei der Initialisierung werden folgende dauerhafte Regeln in der neuen `AGENTS.md` festgehalten:

- Zunächst ausschließlich den Core mit Testplugin implementieren und anhand seiner Abnahmekriterien prüfen.
- Altes NeoFab und produktive Daten unverändert lassen; keine Produktivmigration oder Löschung ohne gesonderten Auftrag.
- Die Verzeichnisse `doku/` und `script/` beibehalten.
- Bedienungsweise der Installations-, Service-, Update- und Notfall-Passwort-Reset-Skripte erhalten und technisch an NeoFab2 anpassen. Eigene NeoFab2-Pfade und Dienstnamen verwenden.
- Deutschsprachige Anleitungen mit konkreten kopierbaren Befehlen, Ausführungsbenutzer, Standardwerten, Ergebnisprüfung und Fehlerhilfe schreiben. Schnellstart in `script/README.md`, Details in `doku/SETUP.md`.
- Bei angeforderter Versionsänderung automatisch Versionsangaben und `doku/Version_Timeline.md` gemeinsam aktualisieren. Dort Datum, tatsächliche Änderungen, Prüfungen, Betriebs-/Migrationshinweise sowie kopierbaren Commit-Titel und Commit-Beschreibung angeben.
- **Kein automatischer Git-Commit und kein Push.** Der Benutzer erstellt den Versions-Commit manuell in GitHub Desktop mit den bereitgestellten Texten.
- Ohne Versionsauftrag keine Versionsanhebung. NeoFab2 erhält eine eigene Timeline und eine beim Projektstart festgelegte Anfangsversion.
- Den Fortschritt nachvollziehbar dokumentieren; geplante oder ungeprüfte Funktionen nicht als fertig melden.
- Vor jedem Arbeitspaket `doku/NeoFab2_Funktionsmatrix.md` lesen, die betroffenen IDs referenzieren und anschließend den Umsetzungsnachweis mit Zielpfaden, Status, Prüfergebnissen und bewussten Abweichungen fortführen. Neue Modulvorschläge vor Implementierung entscheiden.

## Erster Umsetzungsauftrag

> Lies `doku/NeoFab2_Projektstart_Codex.md` und `doku/NeoFab2_Projektbeschreibung.md` sowie vorhandene Repository-Anweisungen. Setze zuerst ausschließlich den Core von NeoFab2 um. Übernimm die dauerhaften Arbeitsregeln in die AGENTS.md des neuen Repositories. Beginne mit Projektgerüst, Application Factory, Konfiguration, expliziten Migrationen und dokumentierten Technologieentscheidungen. Implementiere anschließend Benutzerverwaltung, Rechte, Oberfläche, gemeinsame Dienste, Plugin-Vertrag mit Testplugin und Benutzerimport. Behalte die vertrauten Installations- und Wartungsskripte samt deutschsprachiger Dokumentationsweise bei. Prüfe die Core-Abnahmekriterien. Erstelle noch keine produktiven Fachplugins, ändere das alte NeoFab nicht und führe keinen Git-Commit oder Push aus. Beachte bei einer angeforderten Versionsänderung den Timeline- und Commit-Text-Ablauf aus der Projektbeschreibung.

## Noch zu entscheiden

- Unterstützte Laufzeitversionen und produktive Datenbank; bisheriger Betriebsweg Debian auf LXC/VM/Server mit systemd bleibt Planungsbasis.
- Anfangsversion und Versionsschema von NeoFab2.
- Registrierung, Zuordnung alter Rollen, Behandlung gelöschter Benutzer und Konflikte beim Import.
- Konkreter Umstellungstermin und priorisierte Plugins nach Workshops.
- Optionale Übernahme von Stammdaten jeweils vor Umsetzung des betroffenen Plugins.

Die Erstellung dieser Übergabe startet noch keine Implementierung, Versionsänderung oder Migration. Nach Anlage des neuen Repositories kann der oben formulierte Auftrag dort verwendet werden.
