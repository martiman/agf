#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import time
import urllib.request

OUT =os.path.join(os.environ.get("FLOW_HOME") or os.path.expanduser("~/.flow"), "events.jsonl")
MAX_BYTES = 2 * 1024 * 1024
KEEP_DAYS = 60


def rotate():
    try:
        if os.path.getsize(OUT) > MAX_BYTES:
            os.rename(OUT, OUT.replace(".jsonl", time.strftime("-%Y%m%d-%H%M%S.jsonl")))
    except OSError:
        pass
    base = os.path.dirname(OUT)
    cutoff = time.time() - KEEP_DAYS * 86400
    try:
        for name in os.listdir(base):
            if name.startswith("events-") and name.endswith(".jsonl"):
                p = os.path.join(base, name)
                if os.path.getmtime(p) < cutoff:
                    os.remove(p)
    except OSError:
        pass


def ping():
    try:
        with open(os.path.join(os.environ.get("FLOW_HOME") or os.path.expanduser("~/.flow"), "secret")) as f:
            secret = f.read().strip()
        port = os.environ.get("FLOW_PORT", "8765")
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/ping", data=b"", method="POST",
            headers={"X-Flow-Secret": secret},
        )
        urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=0.7).read()
    except Exception:
        pass


def branch(cwd):
    try:
        r = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=2,
        )
        return r.stdout.strip() or None
    except Exception:
        return None


def main():
    try:
        d = json.load(sys.stdin)
    except Exception:
        return
    cwd = d.get("cwd") or ""
    rec = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "ms": int(time.time() * 1000),
        "event": d.get("hook_event_name"),
        "session_id": d.get("session_id"),
        "cwd": cwd,
        "branch": branch(cwd) if cwd else None,
        "permission_mode": d.get("permission_mode"),
    }
    if d.get("hook_event_name") == "Notification":
        rec["notification_type"] = d.get("notification_type")
        rec["message"] = (d.get("message") or "")[:120]
    for k in ("source", "reason", "stop_hook_active"):
        if k in d:
            rec[k] = d[k]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    rotate()
    with open(OUT, "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    ping()


try:
    main()
except Exception:
    pass
sys.exit(0)
