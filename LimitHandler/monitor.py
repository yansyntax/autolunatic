#!/usr/bin/env python3
import os, subprocess, time, json, requests
from pathlib import Path
from datetime import datetime

# ================= CONFIG =================
SERVICES = {
    "vmess": "/etc/lunatic/vmess",
    "vless": "/etc/lunatic/vless",
    "trojan": "/etc/lunatic/trojan",
    "ssh": "/etc/lunatic/ssh"
}

XRAY_CONFIG = "/etc/xray/config.json"
XRAY_LOG = "/var/log/xray/access.log"
TELEGRAM = "/etc/lunatic/telegram.json"

CHECK_INTERVAL = 3

# ================= UTIL =================
def run(cmd):
    subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def load_json(path):
    try:
        return json.load(open(path))
    except:
        return {}

# ================= TELEGRAM =================
def send(title, user, service, info="", ips=None):
    try:
        conf = load_json(TELEGRAM)
        key = conf.get("monitor", {}).get("bot_key")
        chat = conf.get("monitor", {}).get("chat_id")

        if not key or not chat:
            return

        ip_text = ""
        if ips:
            ip_text = "\n🌐 IP : " + ", ".join(ips)

        msg = f"""
<b>━━━━━━━━━━━━━━━━━━</b>
<b>{title}</b>
<b>━━━━━━━━━━━━━━━━━━</b>

👤 User    : <code>{user}</code>
📡 Service : <b>{service.upper()}</b>{ip_text}

💥 Action  : <b>KILLED + DELETED</b>
📊 Info    : <b>{info}</b>

⏰ Time    : {datetime.now().strftime('%d %b %Y %H:%M:%S')}
<b>━━━━━━━━━━━━━━━━━━</b>
"""

        requests.post(
            f"https://api.telegram.org/bot{key}/sendMessage",
            data={"chat_id": chat, "text": msg, "parse_mode": "HTML"},
            timeout=5
        )
    except:
        pass

# ================= GET USER IP =================
def get_ips(user):
    ips = set()

    if os.path.exists(XRAY_LOG):
        with open(XRAY_LOG) as f:
            for line in f:
                if user in line:
                    try:
                        ip = line.split()[2].split(":")[0].replace("tcp://","")
                        ips.add(ip)
                    except:
                        pass

    return list(ips)

# ================= FORCE DC =================
def force_dc(user, service):
    ips = get_ips(user)

    # block sementara
    for ip in ips:
        run(f"iptables -I INPUT -s {ip} -j DROP")
        run(f"iptables -I OUTPUT -d {ip} -j DROP")

    run(f"pkill -9 -f {user}")

    # restart service biar auto kick
    if service == "ssh":
        run("systemctl restart ssh")
        run("systemctl restart sshd")
        run("systemctl restart dropbear")
        run("systemctl restart ws")
    else:
        run("systemctl restart xray")

    # unblock (delay dikit)
    for ip in ips:
        run(f"iptables -D INPUT -s {ip} -j DROP")
        run(f"iptables -D OUTPUT -d {ip} -j DROP")

    return ips

# ================= DELETE USER =================
def delete_user(user, service):
    base = SERVICES[service]

    # XRAY CLEAN
    if service in ["vmess","vless","trojan"]:
        run(f"jq '(.inbounds[].settings.clients) |= map(select(.email != \"{user}\" and .password != \"{user}\"))' {XRAY_CONFIG} > /tmp/xray.json && mv /tmp/xray.json {XRAY_CONFIG}")

    # SSH CLEAN
    if service == "ssh":
        run(f"userdel -r {user}")

    # FILE CLEAN
    paths = [
        f"{base}/ip/{user}",
        f"{base}/detail/{user}.txt",
        f"{base}/quota/usage/{user}",
        f"{base}/quota/used/{user}",
        f"{base}/quota/today/{user}",
        f"{base}/quota/last/{user}",
    ]

    for p in paths:
        run(f"rm -f {p}")

# ================= CHECK =================
def check():
    for service, base in SERVICES.items():

        ip_dir = Path(f"{base}/ip")
        usage_dir = Path(f"{base}/quota/usage")
        used_dir = Path(f"{base}/quota/used")

        if not ip_dir.exists():
            continue

        for file in ip_dir.iterdir():
            user = file.name

            try:
                limit_ip = int(file.read_text())
            except:
                continue

            ips = get_ips(user)

            # ================= MULTI LOGIN =================
            if limit_ip > 0 and len(ips) > limit_ip:
                force_dc(user, service)
                delete_user(user, service)

                send("🚨 MULTI LOGIN DETECTED", user, service, f"{len(ips)}/{limit_ip}", ips)
                continue

            # ================= QUOTA =================
            if usage_dir.exists() and (usage_dir/user).exists():
                try:
                    quota = int((usage_dir/user).read_text())
                    used = int((used_dir/user).read_text())
                except:
                    continue

                if quota > 0 and used >= quota:
                    force_dc(user, service)
                    delete_user(user, service)

                    send("🔥 QUOTA EXCEEDED", user, service, f"{used}/{quota}", ips)

# ================= MAIN =================
if __name__ == "__main__":
    while True:
        check()
        time.sleep(CHECK_INTERVAL)