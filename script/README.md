# NeoFab Setup-Skripte (Debian 13, LXC/VM/Server)

## Wohin kopieren?

- Empfohlener Pfad: `/home/neofab/projects/neofab/script`
- Wenn du das gesamte Repository klonst, liegen die Skripte automatisch dort. Kein separates Kopieren nötig.

## Schnellstart (als root im Debian-Container)

Ausgangs-Situation:
Neu erstellter LXC-Container mit Debain13 auf einem Proxmox-Server (8.4.14) (Stand Ende Dezember 2025)

in der Konsole des Servers (Proxmox-Oberfläche)angemeldet:

```bash
# Sudo installieren und weitere Vorbereitungen für Installation
apt install sudo -y
sudo apt update -y
sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip git

# Repo (falls noch nicht vorhanden) nach /home/neofab/projects/neofab holen
adduser neofab               # falls Benutzer noch nicht existiert
sudo -u neofab mkdir -p /home/neofab/projects
sudo -u neofab git clone https://github.com/Know-How-Schmiede/neofab.git /home/neofab/projects/neofab

# Ausführbar machen
chmod +x /home/neofab/projects/neofab/script/setupNeoFab
chmod +x /home/neofab/projects/neofab/script/setupNeoFabService
chmod +x /home/neofab/projects/neofab/script/upDateNeoFabService

# Basis-Setup & Test-Run (interaktiv, startet Server optional im Terminal)
sudo bash /home/neofab/projects/neofab/script/setupNeoFab

# Wenn alles passt: als Service (Gunicorn + systemd) einrichten
sudo bash /home/neofab/projects/neofab/script/setupNeoFabService

# Update NeoFab als Service
sudo bash /home/neofab/projects/neofab/script/upDateNeoFabService
```

## Hinweis

- Alle drei Skripte müssen als `root`/`sudo` laufen (legen Benutzer an, installieren Pakete, schreiben systemd-Unit).
- `setupNeoFab` fragt dich nach User/Installationspfad/Admin-Zugang und kann den Dev-Server direkt im Terminal starten.
- `setupNeoFabService` setzt auf der Basisinstallation auf und erstellt den systemd-Dienst (`/etc/systemd/system/<name>.service`).
- `upDateNeoFabService` stopt den systemd-Dienst, holt sich den aktuellen Stand auf Git von NeoFab, installiert neue Abhängigkeiten und startet den Dienst neu.
