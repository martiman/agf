#!/usr/bin/env python3
import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone

EVENTS = os.path.join(os.environ.get("FLOW_HOME") or os.path.expanduser("~/.flow"), "events.jsonl")
PROJECTS = os.path.expanduser("~/.claude/projects")
KEY = re.compile(r"APS-\d+", re.I)


def parse_ts(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")


_title_cache = {}


def title_of(session_id):
    import time
    hit = _title_cache.get(session_id)
    now = time.time()
    if hit and now - hit[0] < (120 if hit[1] else 30):
        return hit[1]
    title = _scan_title(session_id)
    saved = _saved_titles()
    if title:
        if saved.get(session_id) != title:
            saved[session_id] = title
            _save_titles(saved)
    else:
        title = saved.get(session_id)
    _title_cache[session_id] = (now, title)
    return title


TITLES_FILE = os.path.join(os.environ.get("FLOW_HOME") or os.path.expanduser("~/.flow"), "titles.json")
_saved = None


def _saved_titles():
    global _saved
    if _saved is None:
        try:
            with open(TITLES_FILE) as f:
                _saved = json.load(f)
        except (OSError, ValueError):
            _saved = {}
    return _saved


def _save_titles(d):
    try:
        tmp = TITLES_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(d, f, ensure_ascii=False)
        os.replace(tmp, TITLES_FILE)
    except OSError:
        pass


def _scan_title(session_id):
    for path in glob.glob(f"{PROJECTS}/*/{session_id}.jsonl"):
        title = None
        try:
            with open(path, errors="ignore") as f:
                for line in f:
                    if '"custom-title"' in line:
                        try:
                            d = json.loads(line)
                        except ValueError:
                            continue
                        if d.get("type") == "custom-title":
                            title = d.get("customTitle") or title
        except OSError:
            pass
        return title
    return None


def ticket_of(*sources):
    for s in sources:
        m = KEY.search(s or "")
        if m:
            return m.group(0).upper()
    return None


def load(hours):
    sessions = {}
    now = datetime.now(timezone.utc)
    files = sorted(glob.glob(os.path.join(os.environ.get("FLOW_HOME") or os.path.expanduser("~/.flow"), "events-*.jsonl"))) + [EVENTS]
    for path in files:
        if not os.path.exists(path):
            continue
        with open(path) as f:
            for line in f:
                try:
                    e = json.loads(line)
                    ts = parse_ts(e["ts"])
                except (ValueError, KeyError):
                    continue
                if (now - ts).total_seconds() > hours * 3600:
                    continue
                sid = e.get("session_id")
                if not sid:
                    continue
                key = e.get("ms") or int(ts.timestamp() * 1000)
                s = sessions.setdefault(sid, {"session_id": sid, "events": 0, "_key": 0})
                s["events"] += 1
                s["cwd"] = e.get("cwd") or s.get("cwd")
                s["branch"] = e.get("branch") or s.get("branch")
                if key >= s["_key"]:
                    s["_key"] = key
                    s["last_event"], s["last_ts"] = e["event"], ts
                    s["notification"] = e.get("notification_type") if e["event"] == "Notification" else None
    for s in sessions.values():
        del s["_key"]
    return sessions, now


def classify(s, now, stale_min):
    ev = s["last_event"]
    if ev == "UserPromptSubmit":
        state = "running"
    elif ev == "SessionStart":
        state = "idle"
    elif ev == "Notification":
        state = "waiting"
    elif ev == "Stop":
        state = "idle"
    elif ev == "SessionEnd":
        state = "closed"
    else:
        state = "unknown"
    age = (now - s["last_ts"]).total_seconds() / 60
    if state in ("running", "waiting") and age > stale_min:
        state = "suspect"
    s["state"], s["age_min"] = state, round(age, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--stale-min", type=float, default=10)
    ap.add_argument("--hours", type=float, default=48)
    a = ap.parse_args()
    if not os.path.exists(EVENTS):
        sys.exit("no events yet")
    sessions, now = load(a.hours)
    rows = []
    for s in sessions.values():
        classify(s, now, a.stale_min)
        s["title"] = title_of(s["session_id"])
        s["ticket"] = ticket_of(s.get("branch"), s.get("cwd"), s.get("title"))
        s["last_ts"] = s["last_ts"].isoformat()
        rows.append(s)
    order = {"waiting": 0, "suspect": 1, "running": 2, "idle": 3, "closed": 4, "unknown": 5}
    rows.sort(key=lambda r: (order[r["state"]], r["age_min"]))
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
        return
    print(f"{'state':8} {'age':>7}  {'ticket':9} {'session':8}  {'branch':22} title / folder")
    for r in rows:
        where = (r["title"] or os.path.basename(r.get("cwd") or "") or "-")[:50]
        print(f"{r['state']:8} {str(r['age_min']) + 'm':>7}  {(r['ticket'] or '-'):9} "
              f"{r['session_id'][:8]}  {(r.get('branch') or '-')[:22]:22} {where}")


APP_SESSIONS = os.path.expanduser("~/Library/Application Support/Claude/claude-code-sessions")
_app = {"at": 0.0, "map": {}}


def app_links():
    import time
    if time.time() - _app["at"] < 60:
        return _app["map"]
    m = {}
    for p in glob.glob(APP_SESSIONS + "/*/*/local_*.json"):
        try:
            with open(p) as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        if d.get("cliSessionId") and d.get("sessionId") and not d.get("isArchived"):
            m[d["cliSessionId"]] = d["sessionId"]
    _app["at"], _app["map"] = time.time(), m
    return m


def snapshot(hours=48, stale_min=10):
    if not os.path.exists(EVENTS):
        return []
    sessions, now = load(hours)
    rows = []
    links = app_links()
    for s in sessions.values():
        classify(s, now, stale_min)
        s["app_link"] = ("claude://claude.ai/epitaxy/" + links[s["session_id"]]) if s["session_id"] in links else None
        s["title"] = title_of(s["session_id"])
        s["ticket"] = ticket_of(s.get("branch"), s.get("cwd"), s.get("title"))
        s["last_ts"] = s["last_ts"].isoformat()
        rows.append(s)
    return rows


if __name__ == "__main__":
    main()
