# Setup und Installation NeoFab

## PowerShell (Windows PC)

### 1. Repository klonen

```bash
git clone https://github.com/know-how-schmiede/neofab.git
cd neofab
```

### 2. Virtuelle Umgebung erstellen

```bash
python -m venv .venv
```

### 3. Virtuelle Umgebung aktivieren

```bash
.\.venv\Scripts\Activate.ps1
```

Kann das Script nicht ausgeführt werden, da Script Ausführen deaktiviert:
Lösung 1 - beim Beenden der Shell ist ales wieder verschwunden

```bash
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
.\.venv\Scripts\Activate
```

Lösung 2 - dauerhaft für deinen Benutzer

```bash
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\.venv\Scripts\Activate
```

### 4. Abhängigkeiten installieren

```bash
pip install -r requirements.txt
```

### 5. Flask-App starten (Development)

```bash
$env:FLASK_APP="run.py"
flask run
```

Optional: Debug-Modus aktivieren

```bash
$env:FLASK_DEBUG="1"
flask run
```

## Debian 13 (LXC-Container, VM oder Server)

### 1. Grundpakete installieren

Anmelden als root-User

```bash
apt install sudo
sudo apt update -y
sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip git
sudo apt install -y build-essential pkg-config libcairo2-dev python3-dev cmake

adduser neofab
su - neofab
mkdir -p ~/projects/neofab

cd projects/neofab
```

### 2. Repository klonen

```bash
git clone https://github.com/Know-How-Schmiede/neofab.git
cd neofab
```

### 3. Virtuelle Umgebung erstellen

```bash
python3 -m venv .venv
```

### 4. Virtuelle Umgebung aktivieren

```bash
source .venv/bin/activate
```

### 5. Abhängigkeiten installieren

```bash
pip install --upgrade pip setuptools wheel
pip install -r neofab/requirements.txt
```

### 6. Environment-Variablen setzen (temporär)

```bash
export FLASK_APP=run.py
export FLASK_ENV=development
```

### 7. Datenbank migrieren

```bash
flask db upgrade
```

### 8. Development-Server starten

```bash
flask run --host=0.0.0.0 --port=5000
```

NeoFab ist dann erreichbar unter:

```bash
http://<container-ip>:5000
```

## Optional: Systemdienst (Production) – Debian 13

### Gunicorn installieren

```bash
pip install gunicorn
```

### Systemd-Dienst anlegen

auf User root wechseln
Datei erstellen:

```bash
sudo nano /etc/systemd/system/neofab.service
```

Inhalt anpassen:

```txt
[Unit]
Description=NeoFab Service
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/home/neofab/neofab
Environment="FLASK_APP=run.py"
Environment="FLASK_ENV=production"
Environment="NEOFAB_LOG_LEVEL=INFO"
ExecStart=/home/neofab/neofab/.venv/bin/gunicorn \
  --worker-class gthread \
  --workers 2 \
  --threads 4 \
  --timeout 90 \
  --graceful-timeout 30 \
  --keep-alive 2 \
  --access-logfile - \
  --error-logfile - \
  --log-level info \
  -b 0.0.0.0:5000 run:app

[Install]
WantedBy=multi-user.target
```

Dienst aktivieren:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now neofab
```

## 🚀 Starten

### Windows PowerShell

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

### Debian 13 / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 app.py
```

## App zum ersten Mal mit DB starten

im Projekt-Ordner:

### Windows PowerShell

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Datenbank erzeugen

```bash
flask --app app init-db
```

## App starten

```bash
flask --app app run
```

### Debian / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

flask --app app init-db
### flask --app app run ### -> Flask hört nur auf localhost !!!
flask --app app run --host=0.0.0.0 --port=8080
```

## CLI-Kommandos

### Version anzeigen

```bash
flask --app app version
```

### Admin erstellen

```bash
flask --app app create-admin
```

### Datenbank neu erstellen

Zuvor die alte Datenbank löschen:

```bash
flask --app app init-db
```

# neues Setup für Debian 13 LXC-Container unter Proxmox

Verhinderung Fehler bei PDF-Export

```bash
apt install sudo -y
```

```bash
sudo apt update -y
```

```bash
sudo apt upgrade -y
```

```bash
sudo apt install -y python3 python3-venv python3-pip git
```

```bash
sudo apt update -y
```

```bash
sudo apt upgrade -y
```

```bash
sudo apt install -y \
    pkg-config \
    libcairo2-dev \
    python3-dev \
    build-essential \
    meson \
    ninja-build \
    libffi-dev
```

```bash
adduser neofab
```

```bash
su - neofab
```

```bash
mkdir -p ~/projects/neofab
```

```bash
cd projects/neofab
```

```bash
git clone https://github.com/Know-How-Schmiede/neofab.git
```

```bash
cd neofab
```

```bash
python3 -m venv .venv
```

```bash
source .venv/bin/activate
```

```bash
pip install -r neofab/requirements.txt
```

```bash
export FLASK_APP=run.py
```

```bash
cd neofab
```

```bash
flask --app app version
```

```bash
flask --app app init-db
```

```bash
flask --app app create-admin
```

```bash
flask --app app run --host=0.0.0.0 --port=8080
```
