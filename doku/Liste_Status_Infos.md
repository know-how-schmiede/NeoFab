# NeoFab: Statusaenderungen und E-Mail-Ereignisse

Stand: NeoFab 0.9.35

Dieses Dokument beschreibt die im aktuellen Programmcode hinterlegten Statuswerte,
automatischen Statusaenderungen und Ereignisse, bei denen NeoFab eine E-Mail
versendet oder zu versenden versucht.

## Allgemeine Hinweise

- Die sichtbaren Bezeichnungen und Farben der Auftrags- und
  3D-Druckauftragsstatus koennen unter **Systemeinstellungen >
  Status-Meldungen** angepasst werden.
- Die internen Statuscodes und die nachfolgend beschriebenen Automatiken werden
  dadurch nicht veraendert.
- Automatische E-Mails werden nur versendet, wenn SMTP vollstaendig eingerichtet
  ist.
- Die unter **Systemeinstellungen > E-Mail > E-Mail-Aktionen** aufgefuehrten
  Ereignisse koennen einzeln aktiviert oder deaktiviert werden.
- Benutzer koennen im eigenen Profil **Status-E-Mails empfangen** deaktivieren.
  Diese Einstellung betrifft Auftragsstatus- und Plakat-E-Mails, nicht jedoch
  Aktivierungs-, Passwort-Reset-, Begruessungs-, neue-Auftrags- oder
  Mitteilungs-E-Mails.

## 1. Auftragsstatus

| Interner Status | Anzeige | Bedeutung |
| --- | --- | --- |
| `new` | Neu | Der Auftrag wurde angelegt oder besitzt noch keine begonnene Bearbeitung. |
| `in_progress` | In Bearbeitung | Die Bearbeitung des Auftrags wurde begonnen. |
| `on_hold` | Pausiert | Der Auftrag wurde manuell pausiert. |
| `completed` | Abgeschlossen | Der Auftrag ist abgeschlossen. |
| `cancelled` | Storniert | Der Auftrag wurde storniert. |

Jeder neue Auftrag wird mit dem Status `new` angelegt.

### Manuelle Statusaenderungen

- Administratoren koennen den Auftragsstatus in der Auftragsansicht auf jeden
  gueltigen Auftragsstatus setzen.
- Ein Auftrag kann durch einen Administrator oder durch den Besitzer des
  Auftrags storniert werden.
- Bereits abgeschlossene oder bereits stornierte Auftraege koennen ueber die
  Stornieren-Funktion nicht erneut storniert werden.
- Der Status `on_hold` wird nur manuell gesetzt. Es gibt keine automatische
  Regel, die einen Auftrag pausiert.

### Status-E-Mails bei manueller Aenderung

- Wechsel auf `in_progress`: E-Mail-Aktion **Auftrag in Bearbeitung**.
- Wechsel auf `completed`: E-Mail-Aktion **Auftrag abgeschlossen**.
- Wechsel auf `new` oder `on_hold`: keine E-Mail.
- Wechsel auf `cancelled`: Im Programm wird eine allgemeine
  Statusaenderungs-E-Mail aufgerufen. Fuer den dabei verwendeten Aktionsschluessel
  `order_status_changed` existiert in der aktuellen E-Mail-Konfiguration jedoch
  kein aktiver Schalter. Daher wird aktuell keine Stornierungs-E-Mail versendet.

Empfaenger der wirksamen Auftragsstatus-E-Mails:

- Administratoren,
- Besitzer des Auftrags,
- E-Mail-Adressen der zugeordneten Kostenstelle.

Bei Administratoren und beim Auftragsbesitzer wird die Profileinstellung
**Status-E-Mails empfangen** beruecksichtigt. Adressen der Kostenstelle werden
davon nicht beeinflusst.

## 2. Automatische Statusaenderungen bei 3D-Druckauftraegen

### Status eines 3D-Druckauftrags

| Interner Status | Anzeige |
| --- | --- |
| `upload` | Hochgeladen |
| `preparation` | Druckvorbereitung |
| `started` | Druck gestartet |
| `error` | Fehler |
| `finished` | Druck beendet |
| `cancelled` | Abgebrochen |

Der Status eines 3D-Druckauftrags wird beim Hochladen oder Bearbeiten durch
Administrator beziehungsweise berechtigten Mitarbeiter ausgewaehlt.

Beim Wechsel auf `started` wird der Startzeitpunkt auf den aktuellen Zeitpunkt
gesetzt.

### Auswirkung auf den uebergeordneten Auftrag

- Beim ersten vorhandenen 3D-Druckauftrag wechselt ein Auftrag von `new` auf
  `in_progress`.
- Sind alle vorhandenen 3D-Druckauftraege `finished`, wechselt der Auftrag auf
  `completed`.
- Wird bei einem abgeschlossenen Auftrag mindestens ein Druckauftrag wieder auf
  einen anderen Status als `finished` gesetzt oder ein fertiger Druckauftrag
  entfernt, wechselt der Auftrag auf `in_progress`.
- Ein manuell pausierter Auftrag bleibt `on_hold`, solange nicht alle
  Druckauftraege `finished` sind. Sind alle beendet, wechselt er auf
  `completed`.
- Ein stornierter Auftrag wird durch Druckauftragsstatus nicht automatisch
  veraendert.
- Ohne vorhandene 3D-Druckauftraege erfolgt keine automatische Aenderung.

Wenn diese Automatik den Auftrag auf `in_progress` oder `completed` setzt, wird
die dazugehoerige Auftragsstatus-E-Mail versendet, sofern die jeweilige
E-Mail-Aktion aktiviert ist.

Eine Aenderung des 3D-Druckauftragsstatus selbst erzeugt keine separate E-Mail.

## 3. Automatische Statusaenderungen bei Plotter-Auftraegen

### Plakatstatus

| Interner Status | Anzeige |
| --- | --- |
| `open` | Offen |
| `printed` | Gedruckt |

Ein neu hochgeladenes Plakat beginnt mit `open`. Administratoren und
berechtigte Mitarbeiter koennen es auf `printed` setzen.

### Auswirkung auf den uebergeordneten Auftrag

- Alle vorhandenen Plakate sind `open`: Auftrag wird `new`.
- Mindestens ein Plakat ist `printed`, aber nicht alle: Auftrag wird
  `in_progress`.
- Alle vorhandenen Plakate sind `printed`: Auftrag wird `completed`.
- Ohne vorhandene Plakate erfolgt keine automatische Aenderung.
- Ein stornierter Auftrag wird durch Plakatstatus nicht automatisch veraendert.

Die Synchronisation erfolgt beim Hochladen, Bearbeiten, als gedruckt Markieren
und Loeschen eines Plakats.

### E-Mails bei Plakaten

Beim erstmaligen Setzen eines Plakats auf `printed` wird die E-Mail-Aktion
**Plakat gedruckt** ausgefuehrt.

Empfaenger:

- Administratoren,
- Besitzer des Auftrags,
- E-Mail-Adressen der zugeordneten Kostenstelle.

Bei Administratoren und beim Auftragsbesitzer wird die Profileinstellung
**Status-E-Mails empfangen** beruecksichtigt.

Wenn das Markieren zugleich den uebergeordneten Auftrag auf `in_progress` oder
`completed` setzt, kann zusaetzlich eine Auftragsstatus-E-Mail versendet werden.
Ein Klick auf **Gedruckt** kann daher zwei unterschiedliche E-Mails ausloesen.

Beim Loeschen eines Plakats wird der Auftragsstatus ebenfalls neu berechnet.
Eine dadurch entstehende Statusaenderung versendet aktuell jedoch keine
Auftragsstatus-E-Mail.

## 4. Automatische Statusaenderungen bei Beschaffungen

### Status eines Beschaffungsartikels

| Interner Status | Anzeige |
| --- | --- |
| `open` | Offen |
| `ordered` | Bestellt |
| `delivered` | Geliefert |

Ein neu angelegter Artikel beginnt mit `open`. Administratoren und berechtigte
Mitarbeiter koennen ihn auf `ordered` und danach auf `delivered` setzen.

### Auswirkung auf den uebergeordneten Auftrag

- Alle vorhandenen Artikel sind `open`: Beschaffungsauftrag wird `new`.
- Mindestens ein Artikel ist `ordered` oder `delivered`: Beschaffungsauftrag
  wird `in_progress`.
- Alle vorhandenen Artikel sind `delivered`: Beschaffungsauftrag wird
  `completed`.
- Ohne vorhandene Artikel erfolgt keine automatische Aenderung.
- Ein stornierter Auftrag wird durch Artikelstatus nicht automatisch
  veraendert.

Die Synchronisation erfolgt beim Anlegen, Bearbeiten, als bestellt Markieren,
als geliefert Markieren und Loeschen eines Artikels.

**Aktueller E-Mail-Stand:** Die automatische Statusaenderung eines
Beschaffungsauftrags ruft derzeit keine Auftragsstatus-E-Mail auf. Das gilt auch
fuer den Wechsel auf `in_progress` durch **Bestellt** und auf `completed` durch
**Geliefert**.

## 5. Benutzerkontostatus

| Zustand | Technische Merkmale | Wirkung |
| --- | --- | --- |
| Aktiv | `is_active = true`, kein Loeschzeitpunkt | Anmeldung ist moeglich. |
| Deaktiviert | `is_active = false`, kein Loeschzeitpunkt | Anmeldung ist gesperrt; das Konto bleibt erhalten. |
| Geloescht | `is_active = false`, Loeschzeitpunkt gesetzt | Soft-Delete; Anmeldung ist gesperrt und das Konto bleibt fuer bestehende Beziehungen erhalten. |

Statusaenderungen:

- Aktivierung ueber einen gueltigen Aktivierungslink setzt das Konto auf aktiv.
- Administratoren koennen Konten aktivieren oder deaktivieren.
- Administratoren koennen Konten per Soft-Delete als geloescht markieren.
- Der eigene angemeldete Benutzer und der letzte aktive Administrator duerfen
  nicht deaktiviert oder geloescht werden.
- Ein bereits geloeschtes Konto kann ueber die normale Aktivieren-Funktion nicht
  reaktiviert werden.

Fuer Aktivieren, Deaktivieren oder Loeschen eines bestehenden Kontos wird keine
Status-E-Mail versendet.

## 6. Lese- und Hinweisstatus

### Auftraege

NeoFab speichert pro Benutzer den Zeitpunkt, zu dem ein Auftrag zuletzt
geoeffnet wurde. Neue Nachrichten nach diesem Zeitpunkt werden in der
Auftragsliste als ungelesene Kommunikation angezeigt.

Das Oeffnen eines Auftrags aktualisiert diesen Lesezeitpunkt. Dabei wird keine
E-Mail versendet.

### Mitteilungen

Mitteilungen koennen folgende Prioritaeten besitzen:

- Information,
- Hinweis,
- Wichtig,
- Warnung,
- Achtung eMail.

Benutzer koennen eine Mitteilung als gelesen markieren. Wird eine Mitteilung
bearbeitet, werden die bisherigen Lesemarkierungen entfernt, sodass sie wieder
als ungelesen erscheint.

Nur beim Erstellen einer neuen Mitteilung mit der Prioritaet **Achtung eMail**
wird eine E-Mail an alle aktiven, nicht geloeschten Benutzer versendet. Eine
spaetere Bearbeitung oder Umstellung einer bestehenden Mitteilung auf diese
Prioritaet versendet keine E-Mail.

## 7. Interner Datei-Vorschaustatus

Bei hochgeladenen 3D-Modellen fuehrt NeoFab intern einen Vorschaustatus:

| Status | Bedeutung |
| --- | --- |
| `ok` | Die Vorschau wurde erfolgreich erzeugt. |
| `unsupported` | Fuer den Dateityp wird keine Vorschau erzeugt. |
| `missing` | Die Quelldatei fehlt. |
| `failed` | Die Vorschauerzeugung ist fehlgeschlagen. |

Diese Werte sind technische Verarbeitungsinformationen. Sie aendern keinen
Auftragsstatus und versenden keine E-Mail.

## 8. Aktiv-Status von Stammdaten

Folgende Stammdaten besitzen einen Aktiv-/Inaktiv-Zustand:

- Auftragskategorien,
- Kostenstellen,
- Druckerprofile,
- Filamentmaterialien,
- Trainings-Playlists.

Inaktive Eintraege bleiben grundsaetzlich in der Datenbank und bei bestehenden
Zuordnungen erhalten, werden aber bei der normalen Neuauswahl nicht mehr oder
nur eingeschraenkt angeboten. Das Aktivieren oder Deaktivieren dieser
Stammdaten versendet keine E-Mail und aendert keinen Auftragsstatus.

## 9. Vollstaendige Liste der E-Mail-Ereignisse

| Ereignis | Ausloeser | Empfaenger | Konfigurierbarer Aktionsschalter |
| --- | --- | --- | --- |
| Aktivierungslink | Registrierung mit erforderlicher Aktivierung, neuer Admin mit erforderlicher Aktivierung oder manueller Neuversand durch Admin | Betroffener Benutzer | Nein |
| Passwort-Reset | Reset-Anforderung fuer ein aktives, nicht geloeschtes Konto | Betroffener Benutzer | Nein |
| Begruessungs-E-Mail | Konto wird ohne Aktivierung direkt angelegt, neues Konto wird aktiviert oder ein neues Konto wird importiert | Neuer Benutzer und Administratoren | `user_welcome` |
| Neuer Auftrag | Ein Auftrag wurde erfolgreich erstellt | Administratoren und Auftragsbesitzer | `new_order` |
| Auftrag in Bearbeitung | Wirksamer manueller oder angebundener automatischer Wechsel auf `in_progress` | Administratoren, Auftragsbesitzer und Kostenstelle | `order_in_progress` |
| Auftrag abgeschlossen | Wirksamer manueller oder angebundener automatischer Wechsel auf `completed` | Administratoren, Auftragsbesitzer und Kostenstelle | `order_completed` |
| Plakat gedruckt | Ein Plakat wird erstmals auf `printed` gesetzt | Administratoren, Auftragsbesitzer und Kostenstelle | `poster_printed` |
| Achtung-eMail-Mitteilung | Neue Mitteilung wird mit Prioritaet `attention_email` erstellt | Alle aktiven, nicht geloeschten Benutzer | `announcement_attention_email` |
| Test-E-Mail | Administrator startet den SMTP-Test in den Systemeinstellungen | Manuell eingetragene Testadresse | Nein |

### Ereignisse ohne E-Mail

- Auftragsstatus `new` oder `on_hold`,
- derzeit auch Auftragsstatus `cancelled`,
- Statusaenderung eines einzelnen 3D-Druckauftrags ohne resultierenden
  Auftragswechsel auf `in_progress` oder `completed`,
- Statusaenderungen von Beschaffungsartikeln und daraus automatisch entstehende
  Auftragsstatusaenderungen,
- Rueckstufung eines Plotter-Auftrags durch Loeschen eines Plakats,
- Benutzer aktivieren, deaktivieren oder loeschen,
- Lese-/Ungelesen-Markierungen,
- Aktiv-/Inaktiv-Zustand von Stammdaten,
- Datei-Vorschaustatus.

## 10. Voraussetzungen fuer den E-Mail-Versand

Eine E-Mail wird nur tatsaechlich versendet, wenn:

1. SMTP-Host, SMTP-Port und Absenderadresse gespeichert sind,
2. bei konfigurierbaren Ereignissen die E-Mail-Aktion aktiv ist,
3. mindestens ein gueltiger Empfaenger vorhanden ist,
4. bei Status- und Plakat-E-Mails der jeweilige Benutzer den Empfang von
   Status-E-Mails nicht deaktiviert hat,
5. die Verbindung zum SMTP-Server und gegebenenfalls die Anmeldung erfolgreich
   sind.

Fehlgeschlagene oder uebersprungene Versandversuche verhindern die eigentliche
Statusaenderung nicht. Erfolgreich versendete System-E-Mails werden im
Audit-Log protokolliert.
