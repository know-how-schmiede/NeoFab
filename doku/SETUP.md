# Setup und Installation NeoFab
## PowerShell (Windows PC)
### 1. Repository klonen
```bash
git clone https://github.com/know-how-schmiede/neofab.git
cd neofab
```

### 2. Virtuelle Umgebung erstellen
```
python -m venv .venv
```

### 3. Virtuelle Umgebung aktivieren
```
.\.venv\Scripts\Activate.ps1
```
Kann das Script nicht ausgeführt werden, da Script Ausführen deaktiviert:
Lösung 1 - beim Beenden der Shell ist ales wieder verschwunden
```
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
.\.venv\Scripts\Activate
```
Lösung 2 - dauerhaft für deinen Benutzer
```
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\.venv\Scripts\Activate
```

### 4. Abhängigkeiten installieren
```
pip install -r requirements.txt
```

### 5. Flask-App starten (Development)
```
$env:FLASK_APP="run.py"
flask run
```
Optional: Debug-Modus aktivieren
```
$env:FLASK_DEBUG="1"
flask run
```

## Debian 13 (LXC-Container, VM oder Server)
### 1. Grundpakete installieren
```
apt install sudo
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git

adduser neofab
su - neofab
mkdir -p ~/projects/neofab

cd projects/neofab
```

### 2. Repository klonen
```
git clone https://github.com/Know-How-Schmiede/neofab.git
cd neofab
```

### 3. Virtuelle Umgebung erstellen
```
python3 -m venv .venv
```

### 4. Virtuelle Umgebung aktivieren
```
source .venv/bin/activate
```

### 5. Abhängigkeiten installieren
```
pip install -r neofab/requirements.txt
```

### 6. Environment-Variablen setzen (temporär)
```
export FLASK_APP=run.py
export FLASK_ENV=development
```

### 7. Datenbank migrieren
```
flask db upgrade
```

### 8. Development-Server starten
```
flask run --host=0.0.0.0 --port=5000
```

NeoFab ist dann erreichbar unter:
```
http://<container-ip>:5000
```

## Optional: Systemdienst (Production) – Debian 13
### Gunicorn installieren
```
pip install gunicorn
```

### Systemd-Dienst anlegen
Datei erstellen:
```
sudo nano /etc/systemd/system/neofab.service
```
Inhalt anpassen:
```
[Unit]
Description=NeoFab Service
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/home/neofab/neofab
Environment="FLASK_APP=run.py"
Environment="FLASK_ENV=production"
ExecStart=/home/neofab/neofab/.venv/bin/gunicorn -b 0.0.0.0:5000 run:app

[Install]
WantedBy=multi-user.target
```
Dienst aktivieren:
```
sudo systemctl daemon-reload
sudo systemctl enable --now neofab
```

## 🚀 Starten
### Windows PowerShell
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```
### Debian 13 / Linux
```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 app.py
```

## App zum ersten Mal mit DB starten
im Projekt-Ordner:
### Windows PowerShell
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Datenbank erzeugen
flask --app app init-db

# App starten
flask --app app run
```

### Debian / Linux
```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

flask --app app init-db
### flask --app app run ### -> Flask hört nur auf localhost !!!
flask --app app run --host=0.0.0.0 --port=8080
```

## CLI-Kommandos
### Version anzeigen
```
flask --app app version
```
### Admin erstellen
```
flask --app app create-admin
```
### Datenbank neu erstellen
Zuvor die alte Datenbank löschen:
```
flask --app app init-db
```


# neues Setup für Debian 13 LXC-Container unter Proxmox
Verhinderung Fehler bei PDF-Export
```
apt install sudo -y
```

```
sudo apt update -y
```

```
sudo apt upgrade -y
```

```
sudo apt install -y python3 python3-venv python3-pip git
```

```
sudo apt update -y
```

```
sudo apt upgrade -y
```

```
sudo apt install -y \
    pkg-config \
    libcairo2-dev \
    python3-dev \
    build-essential \
    meson \
    ninja-build \
    libffi-dev
```

```
adduser neofab
```

```
su - neofab
```

```
mkdir -p ~/projects/neofab
```

```
cd projects/neofab
```

```
git clone https://github.com/Know-How-Schmiede/neofab.git
```

```
cd neofab
```

```
python3 -m venv .venv
```

```
source .venv/bin/activate
```

```
pip install -r neofab/requirements.txt
```

```
export FLASK_APP=run.py
```

```
cd neofab
```

```
flask --app app version
```

```
flask --app app init-db
```

```
flask --app app create-admin
```

```
flask --app app run --host=0.0.0.0 --port=8080
```
