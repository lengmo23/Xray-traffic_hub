#!/bin/bash
while getopts "e:t:" opt; do
  case $opt in
    e) SERVER_URL="$OPTARG" ;;
    t) SECRET_TOKEN="$OPTARG" ;;
    ?) echo "Invalid option -$OPTARG" >&2; exit 1 ;;
  esac
done

if [ -z "$SERVER_URL" ] || [ -z "$SECRET_TOKEN" ]; then
    echo "‚ùå Error: Missing arguments. -e <URL> -t <Token> required."
    exit 1
fi

echo "Ì†ΩÌ Installing Xray Traffic Agent..."
if [ -f /etc/debian_version ]; then apt update && apt install -y python3 python3-requests; fi
if [ -f /etc/redhat-release ]; then yum install -y python3 python3-requests; fi

cat << PYEOF > /opt/traffic_agent.py
#!/usr/bin/python3
import json, subprocess, sys, requests, time
from datetime import datetime

SERVER_URL = "${SERVER_URL}"
SECRET_TOKEN = "${SECRET_TOKEN}"
TOOL = "/usr/local/bin/xray"
XRAY_API = "127.0.0.1:8080"

def get_xray_data(reset=False):
    cmd = [TOOL, "api", "statsquery", "--server="+XRAY_API, "--pattern", "user>>>"]
    if reset: cmd.append("-reset")
    try: return subprocess.check_output(cmd).decode("utf-8")
    except: return "{}"

def parse_traffic(raw):
    traffic = {}
    try: data = json.loads(raw)
    except: return {}
    for item in data.get("stat", []):
        parts = item["name"].split(">>>")
        if len(parts) < 4 or parts[0] != "user": continue
        uid, metric, direct = parts[1], parts[2], parts[3]
        if metric != "traffic": continue
        val = int(item.get("value", "0"))
        if uid not in traffic: traffic[uid] = {"up":0, "down":0}
        if direct == "uplink": traffic[uid]["up"] += val
        elif direct == "downlink": traffic[uid]["down"] += val
    return traffic

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "reset_only":
        get_xray_data(reset=True)
        sys.exit(0)

    while True:
        today = datetime.now().strftime("%Y-%m-%d")
        raw = get_xray_data(reset=False)
        stats = parse_traffic(raw)
        if stats:
            try: requests.post(SERVER_URL, json={"token":SECRET_TOKEN, "date":today, "data":stats}, timeout=5)
            except: pass
        time.sleep(10)
PYEOF

chmod +x /opt/traffic_agent.py

cat << 'SYSEOF' > /etc/systemd/system/traffic_agent.service
[Unit]
Description=Xray Real-time Agent
After=network.target
[Service]
ExecStart=/usr/bin/python3 /opt/traffic_agent.py
Restart=always
[Install]
WantedBy=multi-user.target
SYSEOF

systemctl daemon-reload
systemctl enable traffic_agent
systemctl restart traffic_agent
(crontab -l 2>/dev/null | grep -v "traffic_agent.py"; echo "59 23 * * * /usr/bin/python3 /opt/traffic_agent.py reset_only >> /var/log/traffic_reset.log 2>&1") | crontab -
echo "∫Ä‚úÖ Installed successfully!"
