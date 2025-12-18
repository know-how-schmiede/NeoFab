# Interner Mailserver – Admin-Dokumentation

Diese Dokumentation beschreibt Installation, Betrieb und Wartung
des internen Mailservers für **NeoFab**, **PrintFleet** und **Thunderbird**.

Der Server ist **ausschließlich für das lokale Netzwerk** gedacht
und stellt eine realistische, aber bewusst einfache Mailumgebung bereit.

---

## 1. Überblick

**Ziel**
- Interner SMTP- und IMAP-Mailserver
- Kein Versand ins Internet
- Keine TLS-/Zertifikatsverwaltung
- Fokus: Funktionalität & Nachvollziehbarkeit

**Einsatz**
- NeoFab (Status-Mails, Benachrichtigungen)
- PrintFleet (Systemmeldungen)
- Thunderbird (Test- und Admin-Postfächer)

---

## 2. Systemumgebung

| Komponente | Wert |
|-----------|------|
| Virtualisierung | Proxmox |
| Typ | LXC-Container |
| Betriebssystem | Debian 12 / 13 |
| Hostname | `mail.neofab.local` |
| IP-Adresse | z. B. `192.168.1.50` |
| Mail-Domain | `neofab.local` |

---

## 3. Verwendete Software

| Dienst | Aufgabe |
|------|--------|
| Postfix | SMTP (Mailversand) |
| Dovecot | IMAP (Mailabruf) |

---

## 4. Wichtige Ports

| Port | Dienst | Zweck |
|----|------|-----|
| 25 | SMTP | Mailversand |
| 143 | IMAP | Mailabruf |

> **Hinweis:**  
> Keine Verschlüsselung – ausschließlich für vertrauenswürdige LANs!

---

## 5. Benutzer & Mailboxen

Für jede Mailadresse existiert **ein Linux-Benutzer**.

### Beispiele

| Benutzer | Mailadresse |
|-------|-------------|
| info | info@neofab.local |
| printfleet | printfleet@neofab.local |

### Benutzer anlegen

```bash
adduser info
adduser printfleet
```

Die Mailbox (Maildir) wird automatisch erzeugt.

## 6. Postfix – Kerneinstellungen

Datei:

```swift
/etc/postfix/main.cf
```

Zentrale Parameter:

```ini
myhostname = mail.neofab.local
mydomain = neofab.local
myorigin = $mydomain

mynetworks = 127.0.0.0/8, 192.168.1.0/24
inet_protocols = ipv4
relayhost =
```

Erklärung:

- Nur Clients aus dem LAN dürfen Mails versenden
- Kein Weiterleiten ins Internet

## 7. Dovecot – Kerneinstellungen

Mailbox-Format:

```ini
mail_location = maildir:~/Maildir
```

Authentifizierung:

```ini
systemctl status postfix
systemctl status dovecot
```

Neustart:

```bash
systemctl restart postfix
systemctl restart dovecot
```

## 9. Logs & Fehlersuche

Wichtige Logdatei:

```bash
/var/log/mail.log
```

Live mitlesen:

```bash
tail -f /var/log/mail.log
```

Typische Fehler:

- falscher Benutzer / Passwort
- falsche IP nicht in mynetworks
- Dienst nicht gestartet

## 10. Backup-Hinweise

Relevante Verzeichnisse:

```text
/etc/postfix/
/etc/dovecot/
/home/*/Maildir/
```

empfohlen:
- Regelmäßiges Backup der Maildirs
- Snapshot des Containers vor Updates

## 11. Sicherheitshinweis

⚠️ Nicht für den Internetbetrieb geeignet!

Kein:
- TLS
- Spamfilter
- Virenschutz
- DKIM / SPF / DMARC

Nur für interne Entwicklungs- & Testsysteme.