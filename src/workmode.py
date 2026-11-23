#!/usr/bin/env python3
import json
import os
import threading
import time
import urllib.error
from datetime import datetime

import jira

HOME = os.environ.get("FLOW_HOME") or os.path.expanduser("~/.flow")
CONFIG = os.path.join(HOME, "config.json")
STATE_FILE = os.environ.get("FLOW_WORKMODE_STATE") or os.path.join(HOME, "workmode.json")
LOG = os.environ.get("FLOW_WORKMODE_LOG") or os.path.join(HOME, "workmode.log")

AGENT, WAIT, HUMAN, PAUSED = "AgentWorking", "WaitingForHuman", "HumanWorking", "Paused"
HUMAN_VALUES = (HUMAN, PAUSED)
DEBOUNCE = 60
RECENT_STOP_H = 2
RATE = (30, 600)
MAX_FAILS = 3
HOLD = 3600
ACTION_MAX = 150

_lock = threading.Lock()
_pending = {}
_writes = []
_problems = {}
_notified = set()
on_problem = None



def enabled():
    try:
        with open(CONFIG) as f:
            return bool((json.load(f).get("workmode") or {}).get("enabled", False))
    except (OSError, ValueError, AttributeError):
        return False


def _load():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save(st):
    tmp = STATE_FILE + ".tmp"
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(st, f, ensure_ascii=False)
        os.replace(tmp, STATE_FILE)
    except OSError:
        pass


def audit(**rec):
    rec["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    try:
        fd = os.open(LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _ts(s):
    try:
        return datetime.fromisoformat(s).timestamp()
    except (TypeError, ValueError):
        return 0.0


def _clip(text, n=ACTION_MAX):
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"



def _label(r):
    return _clip(r.get("title") or os.path.basename(r.get("cwd") or "") or "session", 50)


def target(rows, now):
    running = [r for r in rows if r["state"] == "running"]
    if running:
        r = max(running, key=lambda x: _ts(x["last_ts"]))
        return AGENT, _clip(f"Agent: pracuje v session „{_label(r)}“."), _ts(r["last_ts"])
    waiting = [r for r in rows if r["state"] == "waiting"]
    if waiting:
        r = max(waiting, key=lambda x: _ts(x["last_ts"]))
        what = "povolit akci agenta" if r.get("notification") == "permission_prompt" else "odpovědět agentovi"
        return WAIT, _clip(f"Developer: {what} v session „{_label(r)}“."), 0.0
    done = [r for r in rows if r["state"] == "idle" and r.get("last_event") == "Stop"
            and now - _ts(r["last_ts"]) < RECENT_STOP_H * 3600]
    if done:
        r = max(done, key=lambda x: _ts(x["last_ts"]))
        return WAIT, _clip(f"Developer: zkontrolovat výsledek běhu agenta a rozhodnout o dalším kroku (session „{_label(r)}“)."), 0.0
    return None


def decide(tgt, cur, st, now):
    cm, ca = cur.get("mode"), (cur.get("action") or "")
    if cur.get("category") == "done":
        return ("clear", "tiket je hotový") if (cm or ca) else (None, "hotový tiket, pole jsou prázdná")
    if tgt is None:
        return None, "sessions nic spolehlivého neříkají"
    mode, action, resume = tgt
    if cm in HUMAN_VALUES:
        seen = st.get("human_seen") or {}
        since = seen.get("at", now) if seen.get("mode") == cm else now
        if not (mode == AGENT and resume > since):
            return None, f"{cm} nastavil člověk, nepřepisuji"
        return (mode, action), "skutečné obnovení práce po lidské hodnotě"
    if cm == mode and ca:
        return None, "beze změny"
    return (mode, action), "změna stavu"



def _problem(key, msg):
    _problems[key] = msg
    if key not in _notified:
        _notified.add(key)
        if on_problem:
            try:
                on_problem(key, msg)
            except Exception:
                pass


def _rate_ok(now):
    _writes[:] = [t for t in _writes if now - t < RATE[1]]
    return len(_writes) < RATE[0]


def tick(rows, tickets=None, now=None, dry=False):
    now = time.time() if now is None else now
    out = []
    if not dry and not enabled():
        return out
    with _lock:
        ids = jira.wm_ids()
        if ids is None:
            return out
        if not ids:
            if not dry:
                _problem("*", "V Jiře chybí pole WorkMode a/nebo NextAction (nebo mají jiný typ).")
            return [{"key": "*", "result": "chybí pole"}]
        _problems.pop("*", None)
        by_key = {}
        for r in rows:
            if r.get("ticket"):
                by_key.setdefault(r["ticket"], []).append(r)
        state = _load()
        dirty = False
        for key, trs in sorted(by_key.items()):
            st = state.setdefault(key, {})
            if st.get("hold_until", 0) > now:
                continue
            tgt = target(trs, now)
            cached = ((tickets or {}).get(key) or {})
            cm = (cached.get("workmode") or {})
            if tgt is None and cached.get("category") != "done":
                _pending.pop(key, None)
                continue
            if tgt is not None:
                p = _pending.get(key)
                if not p or p[0] != tgt[0]:
                    _pending[key] = (tgt[0], now)
                    continue
                if now - p[1] < DEBOUNCE:
                    continue
            if cached.get("category") == "done" and not (cm.get("mode") or cm.get("action")):
                continue
            try:
                cur = jira.wm_read(key)
            except Exception as e:
                out.append({"key": key, "result": f"čtení selhalo ({type(e).__name__})"})
                continue
            if cur["mode"] in HUMAN_VALUES and (st.get("human_seen") or {}).get("mode") != cur["mode"]:
                st["human_seen"] = {"mode": cur["mode"], "at": now}
                dirty = True
            elif cur["mode"] not in HUMAN_VALUES and st.get("human_seen"):
                st.pop("human_seen")
                dirty = True
            write, why = decide(tgt, cur, st, now)
            if write is None:
                if "člověk" in why:
                    out.append({"key": key, "result": "ponecháno", "why": why})
                continue
            mode, action = (None, None) if write == "clear" else write
            rec = {"key": key, "from": cur["mode"], "to": mode, "action": action, "why": why}
            if dry:
                out.append(dict(rec, result="plán"))
                continue
            opts = jira.wm_options(cur.get("type") or cached.get("type"))
            if not opts:
                msg = f"Typ „{cur.get('type')}“ nemá pole WorkMode / NextAction na obrazovce."
                _problem(key, msg)
                audit(**rec, result="chyba", error=msg)
                st["hold_until"] = now + HOLD
                dirty = True
                out.append(dict(rec, result="chyba", error=msg))
                continue
            if mode is not None and mode not in opts["options"]:
                msg = f"Hodnota {mode} není mezi povolenými: {', '.join(opts['options'])}."
                _problem(key, msg)
                audit(**rec, result="chyba", error=msg)
                st["hold_until"] = now + HOLD
                dirty = True
                out.append(dict(rec, result="chyba", error=msg))
                continue
            if not _rate_ok(now):
                audit(**rec, result="limit")
                out.append(dict(rec, result="limit"))
                break
            try:
                jira.wm_write(key, opts, mode, action)
            except Exception as e:
                code = e.code if isinstance(e, urllib.error.HTTPError) else None
                st["fails"] = st.get("fails", 0) + 1
                refused = code is not None and 400 <= code < 500
                st["hold_until"] = now + (HOLD if refused or st["fails"] >= MAX_FAILS else 300 * 2 ** st["fails"])
                msg = f"Zápis do Jiry selhal ({'HTTP ' + str(code) if code else type(e).__name__})."
                _problem(key, msg)
                audit(**rec, result="chyba", error=msg)
                dirty = True
                out.append(dict(rec, result="chyba", error=msg))
                continue
            _writes.append(now)
            _problems.pop(key, None)
            _notified.discard(key)
            st.pop("fails", None)
            st["wrote"] = {"mode": mode, "action": action, "at": now}
            dirty = True
            audit(**rec, result="ok")
            out.append(dict(rec, result="zapsáno"))
        if dirty:
            _save(state)
    return out


def public():
    ids = jira.wm_ids()
    return {"enabled": enabled(), "ready": None if ids is None else bool(ids), "problems": dict(_problems)}
