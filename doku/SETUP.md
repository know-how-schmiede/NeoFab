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
  --timeout 120 \
  --graceful-timeout 30 \
  --keep-alive 5 \
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

### Gunicorn-Performance-Einstellungen in bestehendem System nachpflegen

Wenn NeoFab bereits als systemd-Dienst laeuft, kann die bestehende Unit direkt angepasst werden:

```bash
sudo systemctl edit --full neofab
```

In der `ExecStart=`-Zeile sollten die bewaehrten Gunicorn-Parameter gesetzt sein:

```txt
ExecStart=/home/neofab/projects/neofab/.venv/bin/gunicorn \
  --worker-class gthread \
  --workers 2 \
  --threads 4 \
  --timeout 120 \
  --graceful-timeout 30 \
  --keep-alive 5 \
  --access-logfile - \
  --error-logfile - \
  --log-level info \
  -b 0.0.0.0:8080 app:app
```

Danach systemd neu laden und NeoFab neu starten:

```bash
sudo systemctl daemon-reload
sudo systemctl restart neofab
sudo systemctl status neofab
```

Die aktiven Startparameter koennen mit folgendem Befehl kontrolliert werden:

```bash
systemctl cat neofab
```

### Git-Fehler beim Update durch gesetzte Datei-Rechte beheben

Wenn `script/upDateNeoFabService` beim `git pull` mit einer Meldung wie dieser abbricht:

```txt
error: Your local changes to the following files would be overwritten by merge:
        script/setupNeoFab
        script/upDateNeoFabService
Please commit your changes or stash them before you merge.
Aborting
```

dann zuerst pruefen, ob es nur Datei-Rechte sind oder echte Inhaltsaenderungen:

```bash
cd /home/neofab/projects/neofab
sudo -u neofab git status --short
sudo -u neofab git diff --summary -- script/setupNeoFab script/setupNeoFabService script/upDateNeoFabService script/resetAdminPassword
sudo -u neofab git diff -- script/setupNeoFab script/setupNeoFabService script/upDateNeoFabService script/resetAdminPassword
```

Wenn `git diff --summary` nur `mode change` zeigt und der normale `git diff` keinen Inhalt ausgibt, handelt es sich nur um Datei-Rechte. Dann kann Git angewiesen werden, Datei-Rechte nicht als Aenderung zu behandeln:

```bash
cd /home/neofab/projects/neofab
sudo -u neofab git config core.fileMode false
sudo -u neofab git restore --staged --worktree script/setupNeoFab script/setupNeoFabService script/upDateNeoFabService script/resetAdminPassword
```

Falls die Scripte ausfuehrbar bleiben sollen, die Rechte danach setzen. Durch `core.fileMode false` blockieren diese Rechte das naechste Update nicht mehr:

```bash
sudo chmod +x /home/neofab/projects/neofab/script/setupNeoFab
sudo chmod +x /home/neofab/projects/neofab/script/setupNeoFabService
sudo chmod +x /home/neofab/projects/neofab/script/upDateNeoFabService
sudo chmod +x /home/neofab/projects/neofab/script/resetAdminPassword
```

Danach das Update erneut starten:

```bash
sudo bash /home/neofab/projects/neofab/script/upDateNeoFabService
```

Wenn der normale `git diff` Inhalt zeigt, nicht blind `git restore` ausfuehren. Dann zuerst die lokalen Aenderungen sichern oder bewusst verwerfen:

```bash
cd /home/neofab/projects/neofab
sudo -u neofab git diff -- script/setupNeoFab script/setupNeoFabService script/upDateNeoFabService script/resetAdminPassword > /tmp/neofab-local-script-changes.patch
```

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
