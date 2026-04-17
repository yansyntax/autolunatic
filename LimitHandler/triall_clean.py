#!/usr/bin/env python3

import json, os, time, subprocess
from datetime import datetime

# ===============================
# PATH
# ===============================
FILES = {
    "zivpn": "/etc/lunatic/triall/ziv-triall.json",
    "vmess": "/etc/lunatic/vmess/vme-triall.json",
    "vless": "/etc/lunatic/triall/vle-triall.json",
    "trojan": "/etc/lunatic/triall/tro-triall.json",
    "ssh": "/etc/lunatic/triall/ssh-triall.json"
}

XRAY = "/etc/xray/config.json"
ZIV_DB = "/etc/zivpn/users.db"
ZIV_CFG = "/etc/zivpn/config.json"

TELE_JSON = "/etc/lunatic/telegram.json"

# ===============================
# UTIL
# ===============================
def run(cmd):
    subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def now():
    return int(time.time())

def parse(t):
    try:
        return int(datetime.strptime(t, "%Y-%m-%d %H:%M:%S").timestamp())
    except:
        return 0

def load(path):
    if not os.path.exists(path): return []
    try:
        return json.load(open(path))
    except:
        return []

def save(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

# ===============================
# TELEGRAM (PAKE JSON BARU)
# ===============================
def notif(msg):
    try:
        data = load(TELE_JSON)
        key = data.get("main", {}).get("bot_key", "")
        chat = data.get("main", {}).get("chat_id", "")

        if not key or not chat:
            return

        run(f"curl -s -X POST https://api.telegram.org/bot{key}/sendMessage "
            f"-d chat_id={chat} -d parse_mode=HTML -d text=\"{msg}\"")
    except:
        pass

# ===============================
# XRAY CLEAN
# ===============================
def clean_xray(user):
    if not os.path.exists(XRAY): return

    data = load(XRAY)

    for i in data.get("inbounds", []):
        if "clients" in i.get("settings", {}):
            i["settings"]["clients"] = [
                c for c in i["settings"]["clients"]
                if c.get("email") != user and c.get("password") != user
            ]

    save(XRAY, data)

# ===============================
# TROJAN CLEAN
# ===============================
def clean_trojan(password):
    if not os.path.exists(XRAY): return
    data = load(XRAY)

    for i in data.get("inbounds", []):
        if i.get("protocol") == "trojan":
            i["settings"]["clients"] = [
                c for c in i["settings"]["clients"]
                if c.get("password") != password
            ]

    save(XRAY, data)

# ===============================
# ZIVPN CLEAN
# ===============================
def clean_zivpn(user):
    if os.path.exists(ZIV_DB):
        lines = open(ZIV_DB).readlines()
        open(ZIV_DB, "w").writelines([l for l in lines if not l.startswith(user + ":")])

    if os.path.exists(ZIV_CFG):
        data = load(ZIV_CFG)
        if "auth" in data:
            data["auth"]["config"] = [x for x in data["auth"]["config"] if x != user]
            save(ZIV_CFG, data)

# ===============================
# SSH CLEAN + FORCE DC
# ===============================
def clean_ssh(user):
    run(f"pkill -u {user}")
    run(f"userdel -r {user}")

    base = "/etc/lunatic/triall"
    run(f"rm -f {base}/ip/{user}")
    run(f"rm -f {base}/detail/{user}.txt")

# ===============================
# FILESYSTEM CLEAN
# ===============================
def clean_files(user, proto):
    paths = [
        f"/etc/lunatic/{proto}/ip/{user}",
        f"/etc/lunatic/{proto}/quota/usage/{user}",
        f"/etc/lunatic/{proto}/quota/used/{user}",
        f"/etc/lunatic/{proto}/quota/today/{user}",
        f"/etc/lunatic/{proto}/quota/last/{user}",
        f"/etc/lunatic/{proto}/detail/{user}.txt",
    ]

    for p in paths:
        run(f"rm -f {p}")

# ===============================
# MAIN
# ===============================
deleted = []
restart_xray = False
restart_ssh = False
restart_ziv = False

for proto, path in FILES.items():
    data = load(path)
    new = []

    for u in data:
        exp = parse(u.get("expired", ""))

        if exp and exp < now():

            name = u.get("username") or u.get("password")

            # ===== CLEAN
            if proto == "zivpn":
                clean_zivpn(u["password"])
                restart_ziv = True

            elif proto == "ssh":
                clean_ssh(name)
                restart_ssh = True

            elif proto == "trojan":
                clean_trojan(name)
                restart_xray = True

            else:
                clean_xray(name)
                restart_xray = True

            clean_files(name, proto)
            deleted.append(f"{name} ({proto})")

        else:
            new.append(u)

    save(path, new)

# ===============================
# RESTART SERVICE (AUTO DC)
# ===============================
if restart_xray:
    run("systemctl restart xray")

if restart_ziv:
    run("systemctl restart zivpn")

if restart_ssh:
    run("systemctl restart ssh")
    run("systemctl restart sshd")
    run("systemctl restart dropbear")
    run("systemctl restart ws")

# ===============================
# NOTIF (VERSI GANTENG)
# ===============================
if deleted:
    msg = "<b>🧹 AUTO TRIAL CLEANER</b>\n"
    msg += "━━━━━━━━━━━━━━━━━━\n\n"
    msg += "<b>Expired Account Removed:</b>\n\n"

    for x in deleted:
        msg += f"• <code>{x}</code>\n"

    msg += "\n━━━━━━━━━━━━━━━━━━\n"
    msg += "<b>Status :</b> CLEAN ✓\n"
    msg += f"<b>Time :</b> <code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>"

    notif(msg)