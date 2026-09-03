#!/usr/bin/env bash
# ==============================================================================
# Delta BTC Options Bot — Google Cloud Always Free VM (e2-micro) Setup Script
# ==============================================================================
set -e

echo "=== 1. Updating system packages ==="
sudo apt-get update -y
sudo apt-get install -y python3 python3-pip python3-venv git curl ufw

APP_DIR="/opt/delta-bot"
REPO_URL="https://github.com/ankushrane2024/delta-bot.git"

echo "=== 2. Setting up project directory ==="
if [ -d "$APP_DIR" ]; then
    echo "Directory $APP_DIR exists. Pulling latest code..."
    cd "$APP_DIR"
    sudo git pull origin main
else
    echo "Cloning repository to $APP_DIR..."
    sudo git clone "$REPO_URL" "$APP_DIR"
    cd "$APP_DIR"
fi

echo "=== 3. Setting up Python virtual environment ==="
sudo python3 -m venv "$APP_DIR/venv"
sudo "$APP_DIR/venv/bin/pip" install --upgrade pip
sudo "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"

# Add swap space (1GB) so e2-micro (1GB RAM) never encounters Out-Of-Memory during builds
if [ ! -f /swapfile ]; then
    echo "=== Creating 1GB swapfile for e2-micro stability ==="
    sudo fallocate -l 1G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
fi

# Ensure permissions
sudo chown -R $USER:$USER "$APP_DIR"

echo "=== 4. Configuring systemd auto-restart service ==="
SERVICE_FILE="/etc/systemd/system/delta-bot.service"

sudo bash -c "cat <<EOF > $SERVICE_FILE
[Unit]
Description=Delta BTC Options Bot Service
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/python main.py
Restart=always
RestartSec=5
StandardOutput=append:$APP_DIR/trading_bot.log
StandardError=append:$APP_DIR/errors.log
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF"

sudo systemctl daemon-reload
sudo systemctl enable delta-bot
sudo systemctl restart delta-bot

echo "=== 5. Checking service status ==="
sleep 2
sudo systemctl status delta-bot --no-pager

EXT_IP=$(curl -s https://api.ipify.org || echo "YOUR_VM_EXTERNAL_IP")

echo ""
echo "=========================================================================="
echo " SUCCESS: Delta BTC Options Bot is running on Google Cloud Compute Engine!"
echo "=========================================================================="
echo " Dashboard URL: http://$EXT_IP:5000"
echo " Bot Status:    sudo systemctl status delta-bot"
echo " Bot Logs:      sudo journalctl -u delta-bot -f"
echo " Restart Bot:   sudo systemctl restart delta-bot"
echo " Stop Bot:      sudo systemctl stop delta-bot"
echo "=========================================================================="
echo " IMPORTANT: Add this static IP to Delta Exchange API Whitelist: $EXT_IP"
echo "=========================================================================="
