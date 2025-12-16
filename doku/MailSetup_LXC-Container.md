# 📧 NeoFab – Interner Test-Mailserver (LXC)

Dieser Repository beschreibt den Aufbau eines **internen Mailservers** für **NeoFab** zur Entwicklung und zum Testen von E-Mail-Funktionen.  
Der Server läuft **ausschließlich im lokalen Netzwerk** und stellt eine realistische Mailumgebung für **NeoFab, PrintFleet und Thunderbird** bereit.

---

## 🎯 Zielsetzung

- Eigene Test-Mailadresse: `info@neofab.de`
- Versand & Empfang **nur im LAN**
- Nutzung mit **Thunderbird (IMAP/SMTP)**
- Anbindung von **NeoFab** für Mailtests
- **Kein externer Mailverkehr**
- Kein Produktivbetrieb

---

## 🧱 Architektur

| Komponente | Beschreibung |
|-----------|-------------|
| Virtualisierung | Proxmox LXC (unprivileged) |
| Betriebssystem | Ubuntu 24.04 LTS |
| SMTP | Postfix |
| IMAP | Dovecot |
| Mailformat | Maildir |
| TLS | Self-signed |
| Netzwerk | LAN only |



NeoFab / Dev-PC ──┐
├── SMTP / IMAP ──▶ mail.neofab.de (LXC)
Thunderbird ─────┘


---

## 🌐 Namensauflösung (intern)

Kein öffentliches DNS erforderlich.

**Hosts-Eintrag (Client & Dev-PC):**
```text
192.168.1.50   mail.neofab.de

📦 Installation (Kurzfassung)
apt update && apt upgrade -y
apt install postfix dovecot-core dovecot-imapd mailutils -y

Mailbenutzer anlegen
adduser info


➡️ Mailadresse: info@neofab.de

✉️ Postfix (SMTP)
myhostname = mail.neofab.de
mydomain = neofab.de
myorigin = $mydomain

inet_interfaces = all
mydestination = $myhostname, localhost.$mydomain, localhost, $mydomain

mynetworks = 127.0.0.0/8, 192.168.1.0/24
home_mailbox = Maildir/

smtpd_recipient_restrictions =
    permit_mynetworks,
    reject


✔ Nur LAN
✔ Kein Open Relay

📥 Dovecot (IMAP)
mail_location = maildir:~/Maildir


Authentifizierung über Linux-User (info).

🔐 TLS (Self-Signed)
openssl req -new -x509 -days 3650 -nodes \
  -out /etc/ssl/certs/mail.pem \
  -keyout /etc/ssl/private/mail.key


TLS ist für SMTP & IMAP aktiv.
⚠️ Zertifikatswarnungen in Thunderbird sind normal.

▶️ Dienste starten
systemctl restart postfix dovecot
systemctl enable postfix dovecot

🧪 Test
echo "Testmail NeoFab" | mail -s "Mailtest" info@neofab.de


Logs:

tail -f /var/log/mail.log

---

## 🦅 Thunderbird-Setup
### IMAP
```
Server: mail.neofab.de
Port: 993
SSL/TLS
Benutzer: info
```

### SMTP
```
Server: mail.neofab.de
Port: 587
STARTTLS
Benutzer: info
```

---

## ⚙️ NeoFab SMTP-Konfiguration
```
SMTP_HOST = mail.neofab.de
SMTP_PORT = 587
SMTP_USER = info
SMTP_PASSWORD = ********
SMTP_TLS = true
```

---

## 🔒 Sicherheit

- kein Internet-Routing
- nur LAN-Zugriff
- kein Open Relay
- ideal für Tests & Entwicklung

Optional:
```
ufw allow from 192.168.1.0/24 to any port 25,587,993
ufw enable
```

---

## 🚀 Erweiterungsmöglichkeiten

- SMTP-Relay (z. B. Uni-Mailserver)
- echte Domain-DNS
- Let’s Encrypt
- DKIM / SPF
- Trennung Test / Produktion

---

## ⚠️ Hinweis

Dieser Mailserver ist nicht für den Produktivbetrieb gedacht.
Er dient ausschließlich der Entwicklung, dem Testen und der Schulung.

---

## 📄 Lizenz

MIT (oder projektspezifisch anpassen)

---

## ✨ Kontext

Dieses Setup ist Teil des NeoFab / MakerSpace / Know-How-Schmiede-Ökosystems
zur Entwicklung von digitalen Werkzeugen rund um 3D-Druck & Projektverwaltung.