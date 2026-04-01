# Raspberry Pi Setup voor Hand Tracker

## Stap 1: Project naar Raspberry Pi
```bash
git clone <je-repo> /home/pi/py-hand-tracker
cd /home/pi/py-hand-tracker
```

## Stap 2: Dependencies installeren
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Stap 3: Script uitvoerbaar maken
```bash
chmod +x run_handtracker.sh
```

## Stap 4: Autostart inschakelen (kies één methode)

### **Methode A: SystemD Service (aanbevolen)**
```bash
sudo nano /etc/systemd/system/handtracker.service
```

Plak dit in:
```ini
[Unit]
Description=Hand Tracker
After=graphical.target
Wants=graphical.target

[Service]
Type=simple
User=pi
Environment="DISPLAY=:0"
Environment="XAUTHORITY=/home/pi/.Xauthority"
ExecStart=/home/pi/py-hand-tracker/run_handtracker.sh
Restart=on-failure
RestartSec=10

[Install]
WantedBy=graphical.target
```

Opslaan (Ctrl+O, Enter, Ctrl+X) en activeren:
```bash
sudo systemctl daemon-reload
sudo systemctl enable handtracker.service
sudo systemctl start handtracker.service
```

Controleren of het werkt:
```bash
sudo systemctl status handtracker.service
```

### **Methode B: Autostart Desktop**
```bash
mkdir -p ~/.config/autostart
nano ~/.config/autostart/handtracker.desktop
```

Plak dit in:
```ini
[Desktop Entry]
Type=Application
Name=Hand Tracker
Exec=/home/pi/py-hand-tracker/run_handtracker.sh
Path=/home/pi/py-hand-tracker
Terminal=false
X-GNOME-Autostart-enabled=true
```

## Stap 5: Testen
Start de Raspberry Pi opnieuw op en het programma zou automatisch moeten starten!

Om handmatig te stoppen:
```bash
sudo systemctl stop handtracker.service
```

Om logs te zien:
```bash
sudo journalctl -u handtracker.service -f
```

## Nodig voor Camera
- USB webcam OF Pi Camera ingeschakeld in `raspi-config`
- Zorg dat `/dev/video0` beschikbaar is

## Problemen?
- Controleer of `daisy.png` en `background.png` in `/home/pi/py-hand-tracker/` liggen
- Controleer de logs: `sudo systemctl status handtracker.service`
