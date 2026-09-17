# NeoFab → NeoFab2: Funktionsbestand und Umsetzungszuordnung

Stand: 17.09.2026. Referenz: NeoFab 0.9.62, Git-Stand `2673096675db2ccfb824abca0946607e87416819`.

Diese Matrix ergänzt die [Projektbeschreibung](NeoFab2_Projektbeschreibung.md) und den [Projektstart für Codex](NeoFab2_Projektstart_Codex.md). Sie inventarisiert die im Quellcode und in der Dokumentation erkennbaren Funktionsbereiche. Sie ist kein Nachweis einer Laufzeitprüfung und keine Zusage, sämtliche Bestandsfunktionen bereits in der ersten NeoFab2-Version zu liefern.

## Verwendung durch Codex

1. Vor einem Arbeitspaket die betroffenen IDs auswählen und die genannten Quellstellen im alten Repository lesen. Die Quellverweise unten beziehen sich auf NeoFab, nicht auf noch vorhandene Dateien in NeoFab2.
2. Die Zuordnung als Zielarchitektur verwenden. Mit **Vorschlag** gekennzeichnete Modulgrenzen vor ihrer Implementierung dokumentiert entscheiden; die bestehende Core-Abgrenzung nicht stillschweigend erweitern.
3. Vor Implementierung den Erstumfang festlegen. Nicht eingeplante Bestandsfunktionen ausdrücklich als zurückgestellt erfassen, statt sie unbemerkt wegzulassen.
4. Im Umsetzungsnachweis am Dateiende je bearbeiteter ID Zielpfad, Status und tatsächliche Prüfergebnisse ergänzen. Die stabilen IDs auch in Arbeitspaketen und Tests verwenden.
5. Fertig bedeutet implementiert und gegen die relevanten Prüfkriterien geprüft. Reine Datei- oder Menüexistenz genügt nicht. Ein Abweichungsentscheid enthält Grund und Auswirkungen.
6. Zuerst nur die Core-Ausbaustufe aus der Projektbeschreibung umsetzen. Diese Bestandsliste ist kein Auftrag, alle Plugins gleichzeitig zu bauen.

**Initialstatus:** Alle NeoFab2-Zuordnungen in dieser Datei sind geplant, nicht implementiert oder abgenommen. Spätere Statusänderungen stehen im Umsetzungsnachweis. Neue Funktionen sind getrennt vom NeoFab-Bestand aufgeführt.

## Zielbereiche und Abhängigkeiten

| Ziel | Verantwortung und Abhängigkeit |
|---|---|
| Core | Benutzer, Rechte, Systemkonfiguration, gemeinsame Oberfläche und Plugin-Lifecycle; lauffähig ohne Fachplugins |
| Core-Dienst | Technischer Dienst innerhalb der Core-Ausbaustufe, keine eigenständige Fachanwendung; zum Beispiel Versand, Dateien, Zeit, Logs |
| Plugin `orders` | Gemeinsame Auftragsbasis; benötigt Core |
| Plugins `printing3d`, `plotting`, `procurement`, `milling`, `transfer_printing` | Eigenständige Fachplugins; benötigen Core und `orders`, keine pauschalen gegenseitigen Abhängigkeiten |
| Plugin `workshops` | Veranstaltungen und Teilnehmer; benötigt Core, nicht `orders` |
| Plugin `order_appointments` – Vorschlag | Auftragsbezogene Terminabstimmung; benötigt `orders`, unabhängig von Workshops |
| Plugin `learning` – Vorschlag | Lernvideos, Playlists und Unterlagen; benötigt Core, nicht Workshops |
| Plugin `announcements` – Vorschlag | Redaktionelle Mitteilungen und deren Gelesen-Status; benötigt Core; technische Systemmeldungen bleiben im Core |
| Betrieb/Entwicklung | Installationsskripte, Dokumentation, Versionspflege und Prüfwerkzeuge |

Ein gemeinsamer technischer Dienst besitzt keine fachlichen Rechteentscheidungen: zum Beispiel entscheidet das jeweilige Plugin, wer einen Anhang lesen darf und an wen eine Status-E-Mail geht. Der Core darf keine aktiven Fertigungsplugins voraussetzen.

## A. Benutzer und Zugang

| ID | Aktuell in NeoFab | Ziel in NeoFab2 | Quellbezug | Prüfkriterium / Umsetzungshinweis |
|---|---|---|---|---|
| U01 | Anmeldung, Abmeldung und Passwort-Hashing | Core | APP: `login`, `logout`; MODELS: `User` | Gültige und ungültige Anmeldung prüfen; keine Klartextpasswörter speichern |
| U02 | Registrierung mit konfigurierbarer Domain-Beschränkung | Core | APP: `register`; CONFIG | Zulässige und abgelehnte Domains sowie deaktivierte Registrierung prüfen |
| U03 | Optionale E-Mail-Aktivierung und Aktivierungslinks | Core + Versanddienst | APP: `activate_user`, `create_user_activation_token`; MODELS: `UserActivationToken` | Abgelaufene und verbrauchte Tokens zurückweisen; Kontostatus beachten |
| U04 | Passwort vergessen / Self-Service-Reset | Core + Versanddienst | APP: `password_reset_request`, `password_reset_confirm`; MODELS: `UserPasswordResetToken` | Tokenablauf und Einmalnutzung prüfen; vorhandene Sitzungen nach definierter Regel behandeln |
| U05 | Benutzer anlegen, bearbeiten, aktivieren, deaktivieren und löschen | Core | ADMIN: `admin_user_*`; MODELS: `User` | Zugriff nur mit Recht; deaktivierte Konten bleiben gesperrt; Löschwirkung auf spätere Plugins definieren |
| U06 | Rollen und rollenbasierter Zugriff | Core; fachliche Rechte durch Plugins | AUTH: `roles_required`; MODELS: `User.role` | Direkte HTTP-Zugriffe ebenso schützen wie Navigation; alte Rollen explizit zuordnen |
| U07 | Profilfelder, Sprache und helles/dunkles Erscheinungsbild | Core | APP: `profile`; MODELS: `User`; UI | Speichern und erneutes Laden prüfen; fachliche Profilfelder als Erweiterungen abgrenzen |
| U08 | Inaktivitätszeitlimit und Sitzungsverhalten | Core | AUTH: `register_session_timeout` | Timeout beendet Zugriff zuverlässig; Konfiguration und Sonderfälle prüfen |
| U09 | Benutzerimport und -export im Admin-Bereich | Core; Altimport gesonderter Ablauf | ADMIN: `admin_user_import`, `admin_user_export` | Format und Zugriffsrechte dokumentieren; vorhandener Export ist nicht ungeprüft ein vollständiger Migrationsvertrag |
| U10 | E-Mail-Empfängerfavoriten pro Benutzer | Core-Dienst für persönliche Empfängerpräferenzen | MODELS: `UserEmailFavorite`; APP: `save_user_email_favorites`, `profile` | Nur eigene Favoriten verwalten; Versandberechtigung entsteht nicht durch einen Favoriten |
| U11 | Benutzerbezogene Abholzeiten und Kontaktinformationen | Plugin `orders`, an Benutzer gebundene Einstellungen | MODELS: `User.pickup_*`; NOTIFY: `_append_completion_pickup_info` | In fachlichen Abholinformationen verfügbar, keine Pflichtfelder des schlanken Cores |

## B. Oberfläche, System und technische Dienste

| ID | Aktuell in NeoFab | Ziel in NeoFab2 | Quellbezug | Prüfkriterium / Umsetzungshinweis |
|---|---|---|---|---|
| S01 | Startseite, Navigation, Admin-Einstieg und Infoseite | Core; Plugin-Beiträge | APP: `landing`, `info`; UI: `base.html`; ADMIN: `admin_panel` | Oberfläche ohne Fachplugins nutzbar; nur zugängliche aktive Plugins anzeigen |
| S02 | Deutsch, Englisch, Französisch und Fallback | Core-Dienst + Plugin-Übersetzungen | I18N; APP: `inject_globals`; `i18n/` | Fehlende Schlüssel führen zu definiertem Fallback; Plugins besitzen eigene Übersetzungen |
| S03 | UTC-/Lokalzeitbehandlung, Datumsformatierung und Dashboard-Uhr | Core-Dienst | TIME; APP: `format_local_datetime`; UI | Zeitzone in Oberfläche, E-Mails und Exporten konsistent; Sommerzeitfälle prüfen |
| S04 | Systemeinstellungen einschließlich Import/Export | Core; fachliche Einstellungen in Plugins | CONFIG; ADMIN: `admin_settings`, `admin_settings_import`, `admin_settings_export` | Geheimnisse gesondert behandeln; unbekannte oder ungültige Werte validieren |
| S05 | SMTP-Konfiguration und Testversand | Core-Dienst | CONFIG; ADMIN: `admin_settings`; NOTIFY: `_send_message` | Erfolg und Fehler sichtbar; keine Zugangsdaten protokollieren |
| S06 | Willkommens-, Aktivierungs- und Reset-E-Mails | Core + Versanddienst | NOTIFY: `send_user_welcome_notification`, `send_user_activation_notification`, `send_password_reset_notification` | Sprache und Kontostatus berücksichtigen; technischer Versandfehler nachvollziehbar |
| S07 | Steuerung fachlicher E-Mails und Benutzerpräferenzen | Core-Dienst für Versand/Präferenzen; Inhalte und Auslöser in Plugins | CONFIG: `EMAIL_ACTION_DEFS`; NOTIFY; MODELS: `User.status_email_enabled` | Keine globale Abschaltung versehentlich als Verbot notwendiger Kontowiederherstellung interpretieren; Kategorien klar definieren |
| S08 | Impressum und Datenschutz als konfigurierbare Markdown-Inhalte | Core | APP: `imprint`, `privacy`; `legal_markdown.py`; CONFIG | Inhalte sicher rendern und öffentlich erreichbar halten |
| S09 | Aktivitäts-/Audit-Logs, Anzeige, Löschen und zeitgesteuerte Bereinigung | Core-Dienst; fachliche Ereignisse durch Plugins | AUDIT; ADMIN: `admin_logs`, `admin_log_delete`; CONFIG | Berechtigungen, Aufbewahrung und verständliche Ereignisse prüfen; Geheimnisse ausschließen |
| S10 | Dateiablage, Downloads, Größenlimits und grundlegende Vorschauen | Core-Dateidienst + fachliche Plugin-Regeln | APP: Upload-/Download-Routen, `handle_request_entity_too_large`, `save_image_thumbnail` | Pfad- und Zugriffsprüfung; Grenzen serverseitig erzwingen; Dateitypen je Plugin festlegen |
| S11 | PDF-Erzeugung und Ersatzdarstellung bei fehlenden Möglichkeiten | Technischer Exportdienst bei Bedarf; Inhalte in Plugins | APP: `render_pdf_with_template`, `_build_text_rows_pdf`, `_build_order_pdf` | Fehlende Renderer verständlich behandeln; keinen auftragsabhängigen Core erzeugen |
| S12 | Anwendungsversionsanzeige | Core | `neofab/version.py`; APP: `show_version`; UI | Eine zentrale Versionsquelle; Core-/Plugin-Versionen unterscheidbar |

## C. Gemeinsame Auftragsfunktionen

| ID | Aktuell in NeoFab | Ziel in NeoFab2 | Quellbezug | Prüfkriterium / Umsetzungshinweis |
|---|---|---|---|---|
| O01 | Auftrag anlegen und ändern, Besitzer, Titel, Beschreibung und Status | Plugin `orders` | MODELS: `Order`; APP: `new_order`, `order_detail` | Besitzer-/Mitarbeiterrechte prüfen; Stammdaten der Fertigung nicht in den Basiskopf einbauen |
| O02 | Projektinformationen, öffentliche Nutzungsfreigaben und Beschreibungen | Plugin `orders` | MODELS: `Order`; APP: `new_order`, `order_detail` | Bestehende Feldbedeutung sichten; Freigaben explizit speichern und korrekt anzeigen |
| O03 | Kategorien, konfigurierbare Reiter und Bearbeiterrollen | Plugin `orders` + Fachplugin-Registrierung | MODELS: `OrderCategory`; APP: `get_visible_order_tabs`, `can_manage_order_category` | Kategorien und aktive Plugins zuordnen; deaktivierte Plugins nicht nur im Menü verbergen |
| O04 | Benutzerbezogene Kategorie-Bearbeitungsrechte | Core-Rechteprüfung + Regeln in `orders`/Fachplugin | MODELS: `UserOrderCategoryPermission`; APP: `can_view_order` | Fachliche Berechtigungen explizit abbilden; keine unkontrollierte Übernahme alter Kategorie-IDs |
| O05 | Auftragsbereiche, Import/Export und persönliche Bereichsfilter | Plugin `orders` | MODELS: `OrderArea`, `UserOrderAreaPreference`; ADMIN: `admin_area_import`, `admin_area_export` | Bereichsverwaltung und persönliche Auswahl prüfen; nicht mit allgemeiner Mandantenfähigkeit gleichsetzen |
| O06 | Stabile Auftragsnummern und administrativer Sequenzreset | Plugin `orders` | SCHEMA: `reserve_next_order_id`, `reset_order_id_sequence`; ADMIN: `admin_orders_delete_all` | Nummern unter Parallelzugriff eindeutig; Reset nur bei erfüllten Voraussetzungen |
| O07 | Dashboard-Suche, kombinierte Filter, Sortierung, Pagination und Spaltenauswahl | Plugin `orders`; Core stellt Oberfläche bereit | APP: `dashboard`; CONFIG: `DASHBOARD_COLUMN_DEFS`; UI | Such-/Filterzustand bleibt erhalten; nur berechtigte Aufträge sichtbar |
| O08 | Nachrichten je Auftrag, Gelesen-Status und Aktualisierung von Nachrichtenfragmenten | Plugin `orders` + Versanddienst | MODELS: `OrderMessage`, `OrderReadStatus`; APP: `order_messages_fragment`, `order_detail` | Verlauf, ungelesene Nachrichten und Versandregeln pro Benutzer prüfen |
| O09 | Projektbilder, Dokumentationsdateien und Videos mit Notizen | Plugin `orders` + Dateidienst | MODELS: `OrderImage`, `OrderVideo`, `OrderFile`; APP: `order_detail` | Allgemeine Dokumentation von druckspezifischen Modelldaten trennen; bisherige Videoformate und 200-MB-Grenze bewusst bestätigen oder ändern |
| O10 | Statuswechsel und Stornierung, Statusbeschriftungen | Plugin `orders`; spezifische Regeln in Fachplugins | APP: `order_detail`; `status_messages.py`; NOTIFY: `send_order_status_change_notification` | Zulässige Übergänge und Auslöser definieren; ungültige Wechsel zurückweisen |
| O11 | Archivieren, einzelne Aufträge mit Dateien löschen und Gesamtbereinigung | Plugin `orders` + Datei-/Bereinigungsdienste | ADMIN: `admin_order_archive`, `admin_order_delete`, `admin_orders_delete_all` | Abhängige Daten und Dateien konsistent behandeln; Fehlerwiederaufnahme und Rechte prüfen |
| O12 | Auftrags-PDF mit Projektdaten und Fachinformationen | Plugin `orders` + Beiträge der Fachplugins | APP: `build_order_context`, `admin_order_pdf`; `doku/pdf_template.html` | Export enthält nur zugängliche Daten; deaktivierte Fachmodule geregelt behandeln |
| O13 | Kostenstellenverwaltung, Import/Export und Kostenstellen-PDF | Zunächst Plugin `orders`; späterer eigenständiger Finanzbereich nur bei Bedarf | MODELS: `CostCenter`; ADMIN: `admin_cost_center_*` | Fachplugins liefern Kostenpositionen über Schnittstelle; Summen gegen Beispiele prüfen |
| O14 | Allgemeine Arbeitsaufträge mit Maschine, Materialnotiz, Kosten und Dauer | Plugin `orders` als gemeinsame Basis; CNC-spezifische Ausprägung in `milling` | MODELS: `OrderWorkJob`; APP: `order_detail` | Tatsächlich nutzbaren Bestand sichten; kein vollständiges CNC-System aus dem Datenmodell ableiten |

## D. Fachplugins für Fertigung und Beschaffung

| ID | Aktuell in NeoFab | Ziel in NeoFab2 | Quellbezug | Prüfkriterium / Umsetzungshinweis |
|---|---|---|---|---|
| D01 | 3D-Modell-Uploads, Mengen, Material-/Farbzuordnung und Dateiverwaltung | Plugin `printing3d` | MODELS: `OrderFile`; APP: `order_detail`, `set_file_color` | Fachmetadaten im Plugin; Dateien nur mit Berechtigung lesbar und änderbar |
| D02 | STL-/3MF-Viewer, Anzeigeoptionen und Modell-Thumbnails | Plugin `printing3d` | APP: `order_file_preview`, `generate_stl_thumbnails`; UI und `neofab/static/` | Repräsentative STL-/3MF-Dateien und fehlerhafte Dateien prüfen; verfügbare Anzeigeoptionen dokumentieren |
| D03 | Druckaufträge, G-Code-Dateien, Maschinenzuordnung, Zeiten und Druckstatus | Plugin `printing3d` | MODELS: `OrderPrintJob`; APP: Aktionen `upload_print_job`, `update_print_job`, `delete_print_job` | Druckstatus und Auftragstatus getrennt modellieren; Zugriffe und Löschverhalten prüfen |
| D04 | G-Code-Analyse für Druckdauer, Filamentlänge/-gewicht und Ergänzung fehlender Werte | Plugin `printing3d` | APP: `extract_gcode_metadata`, `apply_gcode_metadata_to_job`; `doku/GCode_Druckparameter_Automatik.md` | Mehrere Slicer-Kommentare und fehlende Daten prüfen; manuelle Eingaben nicht unbeabsichtigt überschreiben |
| D05 | Druckerprofile, Materialien, Filamente und Farben einschließlich Import/Export | Plugin `printing3d` | MODELS: `PrinterProfile`, `Material`, `FilamentMaterial`, `Color`; ADMIN: zugehörige CRUD-/Import-/Export-Routen | Fachliche Stammdaten und aktive Referenzen prüfen; Materialkatalog nicht vorsorglich in Core verschieben |
| D06 | 3D-Druck-Kosten aus Maschine, Material, Menge, Zeit und Rüstkosten | Plugin `printing3d`; Kostenschnittstelle zu `orders` | MODELS: `OrderPrintJob`; APP: `order_detail`; `doku/Kostenermittlung_3D_Druck.md` | Bekannte Rechenbeispiele, Einheiten und Rundung prüfen |
| D07 | Druckstatus-Zusammenfassungen und automatische Auftragsstatus-Anpassung | Plugin `printing3d`; Dashboard-Beitrag zu `orders` | APP: `sync_3d_order_status_from_print_jobs`, `dashboard` | Gemischte laufende, fertige und fehlgeschlagene Drucke korrekt zusammenfassen |
| P01 | JPG-/PNG-/PDF-Plakate, Bemerkung, Anzahl und gewünschtes Druckdatum | Plugin `plotting` | MODELS: `OrderPosterFile`; APP: Aktionen `upload_poster_file`, `update_poster_file` | Mehrere Plakate je Auftrag und sichere Dateioperationen prüfen |
| P02 | Bild- und PDF-Vorschauen mit Ersatzvorschau | Plugin `plotting` + technischer Vorschaudienst | APP: `save_poster_thumbnail`, `poster_file_thumbnail` | Erste PDF-Seite bei vorhandenem Renderer; verständlicher Fallback bei fehlender Unterstützung |
| P03 | Papiere, Plottertypen, Standardpapier und Import/Export | Plugin `plotting` | MODELS: `PlotterPaper`, `PlotterType`; ADMIN: `admin_plotter_*` | Standardpapier und in Nutzung befindliche Stammdaten konsistent behandeln |
| P04 | Formate, Deckungsgradanalyse und Plakatkosten | Plugin `plotting` | `neofab/plotter_utils.py`; APP: `analyze_poster_coverage`; `doku/Plakat_Kostenermittlung.md` | Papier-, Tinten-, Maschinen-, Wartungs-, Mengen- und Rüstkosten gegen Referenzfälle prüfen |
| P05 | Als gedruckt markieren, Auftragsstatus und E-Mail dazu | Plugin `plotting` + Versanddienst | APP: `mark_poster_printed`-Aktion, `sync_plotter_order_status_from_posters`; NOTIFY: `send_poster_printed_notification` | Teilfertige und vollständig fertige Aufträge korrekt behandeln |
| B01 | Beschaffungsartikel mit Lieferant, Link, Beschreibung, Menge, Preis und Positionsnummer | Plugin `procurement` | MODELS: `OrderProcurementArticle`; APP: Artikelaktionen, `ensure_procurement_article_position_numbers` | Positionen, Mengen und Preisangaben validieren; stabile Reihenfolge |
| B02 | Notizanhänge für Artikel | Plugin `procurement` + Dateidienst | APP: `download_procurement_article_note_file`, Artikelaktionen | Unterstützte Dokumenttypen und Rechte prüfen; Austausch/Löschung räumt zugehörige Datei auf |
| B03 | Bestellt-/Geliefert-Status und automatische Auftragsstatus-Aktualisierung | Plugin `procurement` | APP: `sync_procurement_order_status_from_articles`, Artikelstatusaktionen | Gemischte Artikelstatus und vollständige Lieferung prüfen |
| B04 | Artikelliste per E-Mail an ausgewählte Empfänger | Plugin `procurement` + Versand-/Favoritendienst | APP: Aktion `send_procurement_article_list`; NOTIFY: `send_procurement_article_list_email` | Inhalt, berechtigte Empfängerauswahl und Versandfehler prüfen |
| F01 | CNC/Fräsen als Auftragskategorie mit allgemeinem Arbeitsablauf | Plugin `milling` | MODELS: `OrderCategory`, `OrderWorkJob`; APP: Kategorien/Reiter | Vor Umsetzung benötigte Maschinen-, Datei-, Status- und Kostenfunktionen bestimmen; Bestand nicht als vollständigen Fräsworkflow ausweisen |

## E. Termine, Mitteilungen und Lernmaterialien

| ID | Aktuell in NeoFab | Ziel in NeoFab2 | Quellbezug | Prüfkriterium / Umsetzungshinweis |
|---|---|---|---|---|
| T01 | Terminanfrage zu einem Auftrag mit Nachricht | Plugin `order_appointments` – Vorschlag | MODELS: `OrderAppointmentRequest`; APP: Aktion `request_appointment` | Nur berechtigte Auftragsbeteiligte; kein Workshop-Modell daraus ableiten |
| T02 | Vorschläge mit Dauer, Auswahl, Ablehnung aller Vorschläge und Bestätigung | Plugin `order_appointments` – Vorschlag | APP: `appointment_detail`, Aktion `select_appointment_time`; MODELS: `OrderAppointmentRequest` | Zustandswechsel, geänderte Vorschläge und notwendige erneute Bestätigung prüfen |
| T03 | Terminliste, Wochenkalender und mehrere Termine im Dashboard | Plugin `order_appointments`; Beitrag zu `orders` | APP: `appointments`, `dashboard`; UI: `appointments.html` | Bestätigte und zusätzlich offene Vorschläge gleichzeitig korrekt anzeigen |
| T04 | Terminbenachrichtigungen und Kalenderanhang | Plugin `order_appointments` + Versanddienst | NOTIFY: `send_appointment_proposal_notification`, `send_appointment_confirmation_notification` | Empfänger, Zeitangaben und Kalenderdaten prüfen |
| A01 | Mitteilungen erstellen, bearbeiten, löschen, importieren und exportieren | Plugin `announcements` – Vorschlag | MODELS: `Announcement`; APP: `announcement_update`, `dashboard`; ADMIN: `admin_announcement_*` | Sichtbarkeit, redaktionelle Rechte und definierte Anzeigepunkte prüfen |
| A02 | Mitteilungen als gelesen markieren, wichtige Mitteilungen per E-Mail | Plugin `announcements` + Versanddienst | MODELS: `AnnouncementRead`; APP: `mark_announcement_read`-Aktion; NOTIFY: `send_announcement_attention_notification` | Gelesen-Status je Benutzer; Empfänger und Wiederholungsregeln prüfen |
| L01 | Trainingsvideos/YouTube-Einbindung und PDF-Unterlagen | Plugin `learning` – Vorschlag | MODELS: `TrainingVideo`; APP: `tutorials`, `tutorial_pdf`, `extract_youtube_id` | Linkvalidierung, Anzeige und Downloadrechte prüfen; keine Teilnahmeverwaltung unterstellen |
| L02 | Playlists, Sortierung, Videoverwaltung und Videoimport/-export | Plugin `learning` – Vorschlag | MODELS: `TrainingPlaylist`; ADMIN: `admin_training_*` | Zuordnungen und Reihenfolge bleiben konsistent; Importformat dokumentieren |

## F. Installation, Wartung und Entwicklung

| ID | Aktuell in NeoFab | Ziel in NeoFab2 | Quellbezug | Prüfkriterium / Umsetzungshinweis |
|---|---|---|---|---|
| X01 | Interaktive Basisinstallation mit optionalem Teststart | Betrieb, bereits Core-Lieferumfang | `script/setupNeoFab`, `script/README.md` | Vertraute Fragen/Vorgaben; eigene NeoFab2-Pfade; Installation auf sauberer Testumgebung |
| X02 | Gunicorn-/systemd-Service einrichten | Betrieb, bereits Core-Lieferumfang | `script/setupNeoFabService` | Start, Stop und Neustart prüfen; erforderliche Worker/Timer dokumentieren |
| X03 | Aktualisierung aus Git, Abhängigkeiten und Service-Neustart | Betrieb, bereits Core-Lieferumfang | `script/upDateNeoFabService` | Explizite Migrationen und Sicherung integrieren; Updatefehler dürfen nicht als Erfolg gemeldet werden |
| X04 | Admin-Passwort lokal wiederherstellen | Betrieb/Core-Wiederherstellungszugang | `script/resetAdminPassword` | Admin-Auswahl und verdeckte Passworteingabe; ohne Webanmeldung nutzbar; keine Passwortprotokollierung |
| X05 | Deutsche Schritt-für-Schritt-Anleitungen, Schnellstart und Fachbeschreibungen | Betrieb/Entwicklung; Dokumentation je Plugin | `script/README.md`, `doku/SETUP.md`, fachliche Dateien unter `doku/` | Befehle, Benutzer, Pfade, Standardwerte und Ergebnisprüfung stimmen mit Implementierung überein |
| X06 | Versionsquelle, README-Versionsangaben und Versionshistorie | Betrieb/Entwicklung + Core-Anzeige | `neofab/version.py`, `README*.md`, `doku/Version_Timeline.md` | Angeforderte Version konsistent aktualisieren; neue Historie für NeoFab2; Commit-Titel/-Beschreibung liefern, Commit manuell in GitHub Desktop |
| X07 | Schema-Ergänzungen und initiale Datenanlage | Core-Migrationen und pluginbezogene Migrationen | APP: `ensure_*`, `init_db`, `init_stammdaten`; SCHEMA | Bestehenden Mechanismus durch explizite versionierte Migrationen ersetzen; keine Schemaänderung bei Seitenaufrufen |
| X08 | Administrativer Design-Smoke-Test | Entwicklungs-/Prüfwerkzeug, bei Bedarf | ADMIN: `admin_design_smoke_test`; UI: `admin_design_smoke_test.html` | Gemeinsame UI und Plugin-Komponenten prüfbar; kein Pflichtbestandteil produktiver Fachnavigation |

## G. Neue Anforderungen ohne entsprechenden vollständigen NeoFab-Bestand

| ID | Neu für NeoFab2 | Ziel und Abhängigkeit | Nachweis für die spätere Umsetzung |
|---|---|---|---|
| N01 | Plugin-Registrierung, API-Versionen, Abhängigkeiten und Aktivierung | Core; Testplugin zuerst | Core ohne Fachplugins; Deaktivierung sperrt direkte Zugriffe und Aufgaben; keine Datenlöschung |
| N02 | Workshops/Schulungen mit Veröffentlichung und Teilnehmeranmeldung | Plugin `workshops`; nur Core | Rechte für eigene/alle Veranstaltungen, Kapazitätsprüfung unter Parallelzugriff, An-/Abmeldung und Änderungs-/Absageinformationen |
| N03 | Transferdruck | Plugin `transfer_printing`; Core + `orders` | Verfahren, Artikel/Trägermaterial, Motive, Mengen, Status und Kosten vor Umsetzung spezifizieren; nicht vom Plotter-Plugin abhängig machen |
| N04 | Gezielte einmalige Benutzerübernahme aus NeoFab | Core-Importwerkzeug | Lesende Quelle; wiederholbarer Import; Hash-Kompatibilität prüfen; keine Übernahme alter Aufträge, Dateien oder Sitzungen |
| N05 | Persistente Versandaufträge mit Wiederholungen und minimale Hintergrundausführung | Core-Dienst | SMTP-Fehler, Neustart und Wiederholungen prüfen; keine Zusage exakt einmaliger SMTP-Zustellung |
| N06 | Gemeinsame jährliche Bereinigung über Plugin-Grenzen | Core-Vertrag + Löschregeln der Plugins, tatsächliche Bereinigung später | Vorschau/Stichtag, berechtigte Bestätigung, zugehörige Dateien, Fehlerwiederaufnahme; Benutzer/Stammdaten getrennt |
| N07 | Gemeinsame Kalenderanzeige verschiedener Fachbereiche | Spätere Erweiterung, Grenze noch offen | Auftrags- und Workshop-Termine bleiben getrennte Fachmodelle; noch kein Auftrag für ein allgemeines Kalenderplugin |
| N08 | Wartelisten, Erinnerungen, Serientermine und Qualifikationsnachweise | Spätere Erweiterung von `workshops` | Erstumfang separat vereinbaren; Aufbewahrung von Qualifikationen unabhängig von Veranstaltungsdaten regeln |

## Migrationsregeln

- **Funktionen übernehmen bedeutet nicht Bestandsdaten übernehmen.** Alte Aufträge, Nachrichten, Termine, Mitteilungen, Lernmaterialien und Auftragsdateien gehören nicht zur zugesagten Benutzerübernahme.
- Nur Benutzer werden gemäß Importvertrag übernommen. Fachliche Benutzerpräferenzen und Berechtigungen benötigen eine explizite Zuordnung; alte Tokens und Sitzungen werden verworfen.
- Stammdaten wie Drucker, Papiere oder Kostenstellen können später nach gesonderter Entscheidung importiert werden. Ihre Datenübernahme ist nicht durch diese Matrix beauftragt.
- Bewährte Berechnungen und Validierungen dürfen nach Prüfung wiederverwendet werden. Direkte Importe aus dem alten monolithischen `app.py` sind keine dauerhafte NeoFab2-Schnittstelle.
- Deaktivierung, Archivierung, Löschung und jährliche Bereinigung sind unterschiedliche Vorgänge. Ein Plugin-Ausbau darf vorhandene Daten nicht stillschweigend löschen.

## Quellverzeichnis für Codex

Die Kürzel beziehen sich auf den oben genannten Git-Stand. Funktions- und Modellnamen sind als Suchanker angegeben, damit spätere Zeilenverschiebungen die Verweise nicht entwerten.

| Kürzel | Pfad im bisherigen Repository |
|---|---|
| APP | `neofab/app.py` |
| MODELS | `neofab/models.py` |
| ADMIN | `neofab/routes/admin.py` |
| AUTH | `neofab/auth_utils.py` |
| CONFIG | `neofab/config.py` |
| NOTIFY | `neofab/notifications.py` |
| SCHEMA | `neofab/schema_utils.py` |
| TIME | `neofab/time_utils.py` |
| I18N | `neofab/i18n_utils.py` |
| AUDIT | `neofab/audit_logs.py` |
| UI | `neofab/templates/` und `neofab/static/` |

## Umsetzungsnachweis – während der Entwicklung fortführen

Zulässige Statuswerte: **geplant**, **in Arbeit**, **implementiert**, **geprüft**, **zurückgestellt**, **entfällt nach Entscheidung**. Eine ID kann mehrere Teilnachweise erhalten, wenn Core und Plugin beteiligt sind. Für die gesamte ID gilt „geprüft“ erst nach Prüfung aller eingeplanten Teile; ausgenommene Teile ausdrücklich nennen.

| Funktions-ID | Status | Zielpfad / Arbeitspaket | Prüfung und Ergebnis | Abweichung / offene Punkte |
|---|---|---|---|---|
| Noch keine Einträge | Alle IDs geplant | – | Keine NeoFab2-Laufzeitprüfung erfolgt | Erstumfang pro Arbeitspaket festlegen |

Bei jeder abgeschlossenen Umsetzung diesen Nachweis aktualisieren. Versionsänderungen zusätzlich gemäß Projektbeschreibung in `doku/Version_Timeline.md` dokumentieren, einschließlich Commit-Titel und Commit-Beschreibung für den manuellen Commit. Diese Matrix allein ersetzt weder Tests noch die Versionshistorie.
