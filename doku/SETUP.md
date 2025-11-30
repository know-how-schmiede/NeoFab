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
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
```

### 2. Repository klonen
```
git clone https://github.com/<dein-github-user>/neofab.git
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
pip install -r requirements.txt
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