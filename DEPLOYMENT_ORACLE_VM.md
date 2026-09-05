# Complete Deployment Guide: Delta BTC Options Bot on Oracle Cloud Free Tier VM

**Target Environment:**
- **Cloud Provider:** Oracle Cloud Infrastructure (OCI) Free Tier
- **Region:** Mumbai (`ap-mumbai-1`)
- **Compute Shape:** `VM.Standard.E2.1.Micro` (AMD 1 OCPU, 1 GB RAM) or `VM.Standard.A1.Flex` (Ampere ARM 1–4 OCPU, 6–24 GB RAM)
- **Operating System:** Ubuntu 22.04 LTS (x86_64 / aarch64)

---

## 1. Architectural Changes: Render.com vs Oracle Cloud VM

| Feature | Render.com Setup | Oracle Cloud Standalone VM | Benefit / Impact |
| :--- | :--- | :--- | :--- |
| **Process Supervision** | Render web service container | `systemd` daemon (`delta-bot.service`) | Native Linux daemon with `Restart=always`, `RestartSec=5` |
| **Crash Alerting** | None (Render dashboard only) | `watchdog.py` via `ExecStopPost` | Instant Telegram alert upon abnormal exit or crash |
| **Health Monitoring** | Inactivity sleep after 15m | Periodic Telegram Heartbeat + Loopback Ping | Active memory & status reports without instance sleeps |
| **Storage Durability** | Ephemeral container disk | Dedicated persistent block volume | Local database (`bot_state.json`, `active_positions.json`) is permanently durable across reboots |
| **Offsite Backup** | GitHub Gist / JSONBlob fallback | Dual local disk + offsite GitHub Gist | Full disaster recovery redundancy preserved |
| **Outbound IP** | Dynamic shared NAT IP | **Reserved Static Public IPv4** | Delta Exchange API IP Whitelist never drifts or breaks |
| **Default Trading Mode** | Forced `PAPER` if `RENDER=true` | Strict fail-safe fallback: Defaults to `PAPER` unless explicitly set to `LIVE` | Eliminates risk of accidental live execution |

---

## 2. Pre-Deployment Configuration in Oracle Cloud Console

### Step 2.1: Launch Compute Instance
1. Log in to the [Oracle Cloud Console](https://cloud.oracle.com).
2. Ensure your region is set to **Mumbai** (`ap-mumbai-1`).
3. Navigate to **Compute → Instances → Create Instance**.
4. Configure the following:
   - **Name:** `delta-bot-vm`
   - **Image:** `Canonical Ubuntu 22.04` (Minimal or standard)
   - **Shape:** 
     - Choice A: `Specialty and legacy → VM.Standard.E2.1.Micro` (Always Free Eligible)
     - Choice B: `Ampere → VM.Standard.A1.Flex` (1-2 OCPUs, 6-12 GB RAM, Always Free Eligible)
   - **Networking:** Select default VCN and public subnet.
   - **SSH Keys:** Paste your public SSH key (`~/.ssh/id_rsa.pub` on Linux/Mac, or PuTTY key).

### Step 2.2: Assign a Reserved Static Public IP
By default, ephemeral public IPs change on instance reboot. To maintain permanent Delta Exchange API whitelist authorization:
1. In the OCI Console, navigate to **Networking → IP Management → Reserved Public IPs**.
2. Click **Reserve Public IP Address**:
   - Scope: Regional (`ap-mumbai-1`)
   - Name: `delta-bot-static-ip`
3. Once reserved, open your VM's details page → Click **Attached VNICs** → Click the primary VNIC.
4. Under **IPv4 Addresses**, click the three-dots menu on the primary private IP → **Edit**.
5. Change Public IP Type to **No Public IP** and click **Update** (releases ephemeral IP).
6. Click **Edit** again → Change Public IP Type to **Reserved Public IP** → Select `delta-bot-static-ip` → Click **Update**.
7. Note down your static IP (e.g. `140.238.xxx.xxx`).

### Step 2.3: Configure VCN Security List (Firewall)
Oracle Cloud Virtual Cloud Networks (VCN) drop all incoming traffic by default unless explicitly allowed:
1. In OCI Console, navigate to **Networking → Virtual Cloud Networks**.
2. Click your VCN → Click **Security Lists** → Click **Default Security List for your VCN**.
3. Click **Add Ingress Rules**:
   - **Stateless:** Unchecked
   - **Source Type:** CIDR
   - **Source CIDR:**
     - *Recommended (Secure):* `<YOUR_HOME_OR_OFFICE_PUBLIC_IP>/32` (prevents malicious internet scanners from accessing port 5000)
     - *Alternative:* `0.0.0.0/0` (if you plan to access from multiple locations or use an SSH tunnel)
   - **IP Protocol:** TCP
   - **Source Port Range:** All
   - **Destination Port Range:** `5000`
   - **Description:** `Delta Bot Web Dashboard`
4. Ensure Port `22` (SSH) is already open in the ingress list.

---

## 3. Delta Exchange API Key IP Whitelisting

1. Log in to [Delta Exchange India](https://india.delta.exchange) (or Global).
2. Go to **Settings → API Keys**.
3. Create a new API Key or edit your existing key:
   - **Permissions:** Trading & Read
   - **IP Whitelist / Trusted IPs:** Enter your Oracle VM's **Reserved Static Public IP**.
4. Save the key and keep your `DELTA_API_KEY` and `DELTA_API_SECRET` ready.

---

## 4. Server Terminal Execution (Step-by-Step)

### Step 4.1: Connect via SSH
```bash
ssh -i /path/to/your_private_key ubuntu@<ORACLE_VM_STATIC_IP>
```

### Step 4.2: Prepare Directory and Clone Repository
```bash
# Create application directory with correct ownership
sudo mkdir -p /opt/delta-bot
sudo chown -R ubuntu:ubuntu /opt/delta-bot

# Clone repository into /opt/delta-bot
git clone https://github.com/ankushrane2024/delta-bot.git /opt/delta-bot
cd /opt/delta-bot
```

### Step 4.3: Configure Environment Variables (`.env`)
```bash
cp .env.example .env
nano .env
```
Ensure you enter your parameters:
```ini
# Delta Exchange Credentials
DELTA_API_KEY=your_real_api_key
DELTA_API_SECRET=your_real_api_secret

# Mode: strictly set to PAPER for initial verification
BOT_MODE=PAPER

# Web Dashboard & Port
PORT=5000

# Telegram Credentials
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
TELEGRAM_CHAT_ID=987654321

# Watchdog & Heartbeat
ENABLE_TELEGRAM_HEARTBEAT=true
HEARTBEAT_INTERVAL_MINS=60

# Offsite Secondary Backup (Optional, Recommended)
GITHUB_PAT=ghp_yourPersonalAccessToken
GITHUB_GIST_ID=
```
Save with `Ctrl+O`, Enter, then `Ctrl+X`. Secure file permissions:
```bash
chmod 600 .env
```

### Step 4.4: Run Automated Installation Script
The included setup script handles swap creation, system dependencies, Python virtualenv, firewall rules, and systemd registration:
```bash
chmod +x setup_oracle_vm.sh
./setup_oracle_vm.sh
```

---

## 5. Mandatory Pre-Flight Verification (Run in PAPER Mode)

Before starting the daemon or switching to LIVE mode, verify the environment:

### 1. Test Isolation & REST Connectivity:
```bash
/opt/delta-bot/venv/bin/python test_demo_account_isolation.py
```
*Expected result:* Tests pass cleanly with zero import errors and successful Delta Exchange connection tests.

### 2. Test Watchdog Health Checker:
```bash
/opt/delta-bot/venv/bin/python watchdog.py --check
```

---

## 6. Service Supervision & Management Commands

### Start the Service:
```bash
sudo systemctl start delta-bot
```

### Check Service Status:
```bash
sudo systemctl status delta-bot
```
*Expected status:* `active (running)` with process PID and systemd timer.

### View Live Logs via journalctl:
```bash
# Stream live logs with IST timestamps
sudo journalctl -u delta-bot -f

# View the last 100 log lines
sudo journalctl -u delta-bot -n 100 --no-pager
```

### Telegram Verification:
Check your Telegram chat. You should receive:
```
🚀 Bot Started in PAPER mode | Capital: $50000.0
```

### Stop / Restart Commands:
```bash
# Restart bot (e.g. after code pull or .env edit)
sudo systemctl restart delta-bot

# Stop bot
sudo systemctl stop delta-bot
```
> [!NOTE]
> When you run `sudo systemctl restart delta-bot` or `sudo systemctl stop delta-bot`, `watchdog.py` detects that `$SERVICE_RESULT=success` (clean exit) and will **NOT** spam your Telegram with a crash alert. Crash alerts are only triggered if the process dies abnormally.

---

## 7. Accessing the Web Dashboard Securely

### Option A: Direct Web Browser Access (If Port 5000 Ingress is Open)
Visit:
```
http://<ORACLE_VM_STATIC_IP>:5000
```

### Option B: Encrypted SSH Tunnel (Recommended / Most Secure)
If you want to keep Port 5000 closed to the public internet to protect against port scanners:
1. On your local machine (Mac / Linux / Windows PowerShell), run:
   ```bash
   ssh -N -L 5000:localhost:5000 -i /path/to/your_private_key ubuntu@<ORACLE_VM_STATIC_IP>
   ```
2. Open your local web browser and navigate to:
   ```
   http://localhost:5000
   ```
   All traffic between your browser and the Oracle VM is encrypted over the SSH tunnel, and no public port 5000 needs to be open!

---

## 8. Switching to LIVE Trading

Once you have verified PAPER mode performance for a cycle:
1. Edit `/opt/delta-bot/.env`:
   ```bash
   nano /opt/delta-bot/.env
   ```
2. Change:
   ```ini
   BOT_MODE=LIVE
   ```
3. Restart the service:
   ```bash
   sudo systemctl restart delta-bot
   ```
4. Verify via Telegram:
   ```
   🚀 Bot Started in LIVE mode | Capital: $...
   ```
5. Confirm via Telegram command `/status` or web dashboard.
