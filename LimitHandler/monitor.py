#!/usr/bin/env python3
import os
import subprocess
import time
import requests
import threading
from pathlib import Path
from datetime import datetime

# ================= CONFIG =================
TRIAL_DB = "/etc/lunatic/triall/triall.db"

SERVICES = {
    "trojan": "/etc/lunatic/trojan",
    "vmess": "/etc/lunatic/vmess",
    "vless": "/etc/lunatic/vless",
    "ssh": "/etc/lunatic/ssh"
}

XRAY_CONFIG = "/etc/xray/config.json"
XRAY_ACCESS_LOG = "/var/log/xray/access.log"

BOT_KEY = "/etc/lunatic/bot/notif/key"
CHAT_ID = "/etc/lunatic/bot/notif/id"

CHECK_INTERVAL = 1

# ================= TELEGRAM =================
def send(title, user, service, extra="", ips=None):
    try:
        key = Path(BOT_KEY).read_text().strip()
        chat = Path(CHAT_ID).read_text().strip()

        ip_text = ""
        if ips:
            ip_text = "\n🌐 IP : " + ", ".join(ips)

        msg = f"""
<b>━━━━━━━━━━━━━━</b>
<b>{title}</b>
<b>━━━━━━━━━━━━━━</b>

👤 User : <code>{user}</code>
📡 Service : <b>{service.upper()}</b>{ip_text}

💥 Status : <b>{extra}</b>

⏰ Time : {datetime.now().strftime('%d %b %Y %H:%M:%S')}
<b>━━━━━━━━━━━━━━</b>
"""
        requests.post(
            f"https://api.telegram.org/bot{key}/sendMessage",
            data={"chat_id": chat, "text": msg, "parse_mode": "HTML"},
            timeout=5
        )
    except:
        pass

# ================= GET IP =================
def get_user_ips(user):
    ips = set()
    if os.path.exists(XRAY_ACCESS_LOG):
        with open(XRAY_ACCESS_LOG) as f:
            for line in f:
                if user in line:
                    try:
                        ip = line.split()[2].split(":")[0].replace("tcp://","")
                        ips.add(ip)
                    except:
                        pass
    return list(ips)

# ================= IPTABLES =================
def drop_ip(ip):
    if subprocess.call(["iptables","-C","INPUT","-s",ip,"-j","DROP"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0:
        subprocess.run(["iptables","-I","INPUT","-s",ip,"-j","DROP"])
        subprocess.run(["iptables","-I","OUTPUT","-d",ip,"-j","DROP"])

def unblock_ip(ip):
    time.sleep(10)
    subprocess.run(["iptables","-D","INPUT","-s",ip,"-j","DROP"], stderr=subprocess.DEVNULL)
    subprocess.run(["iptables","-D","OUTPUT","-d",ip,"-j","DROP"], stderr=subprocess.DEVNULL)

# ================= FORCE KILL =================
def force_kill(user, service):
    ips = get_user_ips(user)

    for ip in ips:
        drop_ip(ip)
        threading.Thread(target=unblock_ip, args=(ip,)).start()

    subprocess.run(["pkill","-9","-f",user], stdout=subprocess.DEVNULL)

    if service == "ssh":
        subprocess.run(["systemctl","restart","ssh"], stdout=subprocess.DEVNULL)
    else:
        subprocess.run(["systemctl","restart","xray"], stdout=subprocess.DEVNULL)

    return ips

# ================= CLEAN FILE =================
def delete_files(user):
    for f in Path("/var/www/html").glob(f"*{user}*"):
        try: f.unlink()
        except: pass

# ================= REMOVE USER =================
def remove_user(user, service):
    base = SERVICES.get(service, "")

    if service in ["trojan","vmess","vless"]:
        for sub in ["ip","detail"]:
            path = Path(f"{base}/{sub}")
            if path.exists():
                for f in path.glob(f"*{user}*"):
                    try: f.unlink()
                    except: pass

        for sub in ["usage","used","today","last"]:
            path = Path(f"{base}/quota/{sub}")
            if path.exists():
                for f in path.glob(user):
                    try: f.unlink()
                    except: pass

    delete_files(user)

    db = f"{base}/{service}.db"
    if os.path.exists(db):
        subprocess.run(["sed","-i",f"/^### {user}/d",db])

    if service == "ssh":
        subprocess.run(["userdel","-f",user], stdout=subprocess.DEVNULL)

# ================= UPDATE TRAFFIC =================
def update_usage():
    try:
        stats = subprocess.check_output(
            ["xray","api","statsquery","--server=127.0.0.1:10085"],
            stderr=subprocess.DEVNULL
        ).decode()
    except:
        return

    for proto in ["vless","vmess","trojan"]:
        base = Path(f"/etc/lunatic/{proto}/quota")
        (base/"used").mkdir(parents=True, exist_ok=True)
        (base/"today").mkdir(parents=True, exist_ok=True)
        (base/"last").mkdir(parents=True, exist_ok=True)

        try:
            users = subprocess.check_output([
                "jq","-r",
                f'.inbounds[] | select(.protocol=="{proto}") | .settings.clients[]?.email',
                XRAY_CONFIG
            ]).decode().split()
        except:
            continue

        for user in set(users):
            try:
                up = subprocess.getoutput(f"echo '{stats}' | jq -r '.stat[] | select(.name==\"user>>>{user}>>>traffic>>>uplink\") | .value'")
                down = subprocess.getoutput(f"echo '{stats}' | jq -r '.stat[] | select(.name==\"user>>>{user}>>>traffic>>>downlink\") | .value'")

                up = int(up) if up.isdigit() else 0
                down = int(down) if down.isdigit() else 0

                now = up + down

                last_file = base/"last"/user
                last = int(last_file.read_text()) if last_file.exists() else 0

                today = now - last
                if today < 0:
                    today = 0

                (base/"used"/user).write_text(str(now))
                (base/"today"/user).write_text(str(today))

            except:
                continue

# ================= MULTI LOGIN =================
def check_autokill():
    for service, base in SERVICES.items():
        ipdir = Path(f"{base}/ip")
        if not ipdir.exists():
            continue

        for file in ipdir.iterdir():
            try:
                user = file.name
                limit = int(file.read_text())
                if limit == 0:
                    continue

                ips = get_user_ips(user)

                if len(ips) > limit:
                    force_kill(user, service)
                    remove_user(user, service)
                    send("🚨 MULTI LOGIN", user, service, f"{len(ips)}/{limit}", ips)
            except:
                continue

# ================= QUOTA =================
def check_quota():
    for proto in ["vless","vmess","trojan"]:
        usage = Path(f"/etc/lunatic/{proto}/quota/usage")
        used = Path(f"/etc/lunatic/{proto}/quota/used")

        if not usage.exists():
            continue

        for f in usage.glob("*"):
            user = f.name
            try:
                limit = int(f.read_text())
                used_val = int((used/user).read_text())
            except:
                continue

            if limit > 0 and used_val >= limit:
                ips = force_kill(user, proto)
                remove_user(user, proto)
                send("🔥 QUOTA EXCEEDED", user, proto, f"{used_val}/{limit}", ips)

# ================= EXPIRED =================
def parse_date(text):
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except:
            continue
    return None

def check_expired():
    now = datetime.now()

    for service, base in SERVICES.items():
        db = Path(f"{base}/{service}.db")
        if not db.exists():
            continue

        new_lines = []

        for line in db.read_text().splitlines():
            if not line.startswith("###"):
                continue

            parts = line.split()
            user = parts[1]
            exp = parse_date(" ".join(parts[2:]))

            if not exp:
                continue

            if now >= exp:
                ips = force_kill(user, service)
                remove_user(user, service)
                send("⛔ EXPIRED", user, service, "DELETED", ips)
            else:
                new_lines.append(line)

        db.write_text("\n".join(new_lines) + "\n")

# ================= TRIAL =================
def check_trial():
    if not os.path.exists(TRIAL_DB):
        return

    now = datetime.now()
    new_lines = []

    with open(TRIAL_DB) as f:
        for line in f:
            if not line.startswith("#trial#"):
                continue

            try:
                parts = line.strip().split()
                service = parts[1]
                user = parts[2]
                limit = int(parts[3])
                exp = datetime.strptime(" ".join(parts[4:6]), "%Y-%m-%d %H:%M")
            except:
                continue

            ips = get_user_ips(user)

            if now >= exp:
                force_kill(user, service)
                remove_user(user, service)
                send("⛔ TRIAL EXPIRED", user, service, "DELETED", ips)
                continue

            if limit > 0 and len(ips) > limit:
                force_kill(user, service)
                remove_user(user, service)
                send("🚨 TRIAL MULTI LOGIN", user, service, f"{len(ips)}/{limit}", ips)
                continue

            new_lines.append(line)

    with open(TRIAL_DB, "w") as f:
        f.writelines(new_lines)

# ================= MAIN =================
if __name__ == "__main__":
    while True:
        update_usage()
        check_autokill()
        check_quota()
        check_expired()
        check_trial()
        time.sleep(CHECK_INTERVAL)