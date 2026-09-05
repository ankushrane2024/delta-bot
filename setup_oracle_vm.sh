#!/usr/bin/env bash
# ==============================================================================
# Delta BTC Options Bot — Oracle Cloud Free Tier VM (Ubuntu 22.04) Setup Script
# ==============================================================================
# Region: Mumbai (ap-mumbai-1) or any OCI region
# Target OS: Ubuntu 22.04 LTS (x86_64 or aarch64 Ampere A1)
# ==============================================================================
set -e

# Colors for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}====================================================================${NC}"
echo -e "${BLUE} Delta BTC Options Bot — Oracle Cloud VM Automated Installer        ${NC}"
echo -e "${BLUE}====================================================================${NC}"

# 1. Identify Target Directory & Current User
APP_DIR="/opt/delta-bot"
CURRENT_USER=$(whoami)

if [ "$CURRENT_USER" = "root" ]; then
    echo -e "${YELLOW}Warning: Running as root. If you have an 'ubuntu' user, running as 'ubuntu' with sudo is recommended.${NC}"
fi

# 2. System Package Updates & Prerequisites
echo -e "\n${GREEN}=== 1. Updating APT repository and installing system packages ===${NC}"
sudo apt-get update -y
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    build-essential \
    git \
    curl \
    ufw \
    iptables-persistent

# 3. Swapfile Configuration (Crucial for 1GB RAM Micro Instances)
echo -e "\n${GREEN}=== 2. Configuring 2GB swap space for memory stability ===${NC}"
if [ ! -f /swapfile ]; then
    echo "Creating 2GB swapfile..."
    sudo fallocate -l 2G /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=2048
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    # Optimize swappiness for low-RAM VMs
    sudo sysctl vm.swappiness=20
    sudo sysctl vm.vfs_cache_pressure=50
    echo 'vm.swappiness=20' | sudo tee -a /etc/sysctl.conf
    echo 'vm.vfs_cache_pressure=50' | sudo tee -a /etc/sysctl.conf
    echo "Swapfile created and activated successfully."
else
    echo "Swapfile already exists. Skipping."
fi

# 4. Working Directory & Permissions
echo -e "\n${GREEN}=== 3. Verifying application directory permissions ===${NC}"
if [ ! -d "$APP_DIR" ]; then
    echo "Creating $APP_DIR..."
    sudo mkdir -p "$APP_DIR"
fi
sudo chown -R "$CURRENT_USER:$CURRENT_USER" "$APP_DIR"

# 5. Python Virtual Environment Setup
echo -e "\n${GREEN}=== 4. Setting up Python virtual environment and dependencies ===${NC}"
if [ ! -d "$APP_DIR/venv" ]; then
    echo "Creating virtual environment at $APP_DIR/venv..."
    python3 -m venv "$APP_DIR/venv"
fi

"$APP_DIR/venv/bin/pip" install --upgrade pip setuptools wheel
if [ -f "$APP_DIR/requirements.txt" ]; then
    echo "Installing Python dependencies from requirements.txt..."
    "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"
else
    echo -e "${RED}Error: requirements.txt not found in $APP_DIR!${NC}"
    exit 1
fi

# 6. Firewall & Oracle Ubuntu iptables Configuration
echo -e "\n${GREEN}=== 5. Configuring Ubuntu firewall & Oracle iptables rules ===${NC}"
# Oracle Cloud Ubuntu images include default iptables rules that reject input on ports not in the rule chain.
# Insert rule allowing port 5000 before any REJECT rule
sudo iptables -I INPUT 5 -p tcp --dport 5000 -m state --state NEW,ESTABLISHED -j ACCEPT || true
sudo netfilter-persistent save || true

# UFW rules
sudo ufw allow 22/tcp comment 'SSH' || true
sudo ufw allow 5000/tcp comment 'Delta Bot Dashboard' || true
sudo ufw --force enable || true

# 7. Setup Environment File
echo -e "\n${GREEN}=== 6. Checking environment configuration (.env) ===${NC}"
if [ ! -f "$APP_DIR/.env" ]; then
    if [ -f "$APP_DIR/.env.example" ]; then
        echo "Creating .env from .env.example..."
        cp "$APP_DIR/.env.example" "$APP_DIR/.env"
        echo -e "${YELLOW}Notice: Default .env created. Please edit $APP_DIR/.env with your real API credentials!${NC}"
    else
        touch "$APP_DIR/.env"
    fi
fi
chmod 600 "$APP_DIR/.env"

# 8. Install & Register systemd Service
echo -e "\n${GREEN}=== 7. Registering delta-bot systemd supervisor service ===${NC}"
SERVICE_DEST="/etc/systemd/system/delta-bot.service"

sudo bash -c "cat <<EOF > $SERVICE_DEST
[Unit]
Description=Delta BTC Options Bot Service
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/python main.py
ExecStopPost=$APP_DIR/venv/bin/python $APP_DIR/watchdog.py --on-stop
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
EnvironmentFile=-$APP_DIR/.env
Environment=PYTHONUNBUFFERED=1
TimeoutStopSec=20

[Install]
WantedBy=multi-user.target
EOF"

sudo systemctl daemon-reload
sudo systemctl enable delta-bot

# 9. Public IP Discovery & Next Steps
EXT_IP=$(curl -s --max-time 5 https://api.ipify.org || echo "YOUR_VM_PUBLIC_IP")

echo ""
echo -e "${GREEN}====================================================================${NC}"
echo -e "${GREEN} SUCCESS: Delta BTC Options Bot setup completed successfully!        ${NC}"
echo -e "${GREEN}====================================================================${NC}"
echo -e " VM Public IP:      ${YELLOW}$EXT_IP${NC}"
echo -e " App Directory:     $APP_DIR"
echo -e " Python Virtualenv: $APP_DIR/venv"
echo -e " Service Name:      delta-bot.service"
echo -e " Web Dashboard:     http://$EXT_IP:5000"
echo -e "===================================================================="
echo -e "${YELLOW}IMPORTANT DEPLOYMENT STEPS TO COMPLETE BEFORE STARTING:${NC}"
echo -e " 1. Configure your credentials:"
echo -e "    ${BLUE}nano $APP_DIR/.env${NC}"
echo -e "    (Set DELTA_API_KEY, DELTA_API_SECRET, TELEGRAM_BOT_TOKEN, BOT_MODE=PAPER)"
echo -e ""
echo -e " 2. Whitelist this Static Public IP in Delta Exchange API settings:"
echo -e "    ${YELLOW}$EXT_IP${NC}"
echo -e ""
echo -e " 3. Run mandatory pre-flight test suite in PAPER mode:"
echo -e "    ${BLUE}$APP_DIR/venv/bin/python test_demo_account_isolation.py${NC}"
echo -e ""
echo -e " 4. Start the supervised service:"
echo -e "    ${BLUE}sudo systemctl start delta-bot${NC}"
echo -e ""
echo -e " 5. Monitor logs in real time:"
echo -e "    ${BLUE}sudo journalctl -u delta-bot -f${NC}"
echo -e "===================================================================="
