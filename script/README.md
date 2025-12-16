# NeoFab Setup-Skripte (Debian 13, LXC/VM/Server)

## Wohin kopieren?
- Empfohlener Pfad: `/home/neofab/projects/neofab/script`
- Wenn du das gesamte Repository klonst, liegen die Skripte automatisch dort. Kein separates Kopieren nötig.

## Schnellstart (als root im Debian-Container)
```bash
# Repo (falls noch nicht vorhanden) nach /home/neofab/projects/neofab holen
adduser neofab               # falls Benutzer noch nicht existiert
sudo -u neofab mkdir -p /home/neofab/projects
sudo -u neofab git clone https://github.com/Know-How-Schmiede/neofab.git /home/neofab/projects/neofab

# Ausführbar machen
chmod +x /home/neofab/projects/neofab/script/setupNeoFab
chmod +x /home/neofab/projects/neofab/script/setupNeoFabService

# Basis-Setup & Test-Run (interaktiv, startet Server optional im Terminal)
sudo bash /home/neofab/projects/neofab/script/setupNeoFab

# Wenn alles passt: als Service (Gunicorn + systemd) einrichten
sudo bash /home/neofab/projects/neofab/script/setupNeoFabService
```

## Hinweis
- Beide Skripte müssen als `root`/`sudo` laufen (legen Benutzer an, installieren Pakete, schreiben systemd-Unit).
- `setupNeoFab` fragt dich nach User/Installationspfad/Admin-Zugang und kann den Dev-Server direkt im Terminal starten.
- `setupNeoFabService` setzt auf der Basisinstallation auf und erstellt den systemd-Dienst (`/etc/systemd/system/<name>.service`).
