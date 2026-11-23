#!/usr/bin/env python3
import json
import os
import secrets
import time

import msg as _m

HOME = os.environ.get("FLOW_HOME") or os.path.expanduser("~/.flow")
FILE = os.path.join(HOME, "ideas.json")
MAX_IDEAS, MAX_TEXT, MAX_CTX = 1000, 2000, 1500


def load():
    try:
        with open(FILE) as f:
            d = json.load(f)
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _save(items):
    os.makedirs(HOME, exist_ok=True)
    tmp = FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    os.replace(tmp, FILE)


def _s(v, n):
    return v.strip()[:n] if isinstance(v, str) else ""


def _source(src):
    src = src if isinstance(src, dict) else {}
    return {k: _s(src.get(k), 300) for k in ("session_id", "title", "cwd", "ticket")} | {"last": src.get("last") if isinstance(src.get("last"), (int, float)) else None}


def add(text, context="", source=None, dedupe=True):
    text = _s(text, MAX_TEXT)
    if not text:
        raise _m.KValueError("text nápadu je prázdný", "srv.ideas.empty")
    items = load()
    src = _source(source)
    if dedupe and src["session_id"]:
        for it in items:
            if (it.get("source") or {}).get("session_id") == src["session_id"]:
                return it, False
    if len(items) >= MAX_IDEAS:
        raise _m.KValueError("příliš mnoho nápadů (max %d)" % MAX_IDEAS, "srv.ideas.too_many", max=MAX_IDEAS)
    idea = {"id": secrets.token_hex(6), "text": text, "context": _s(context, MAX_CTX), "source": src, "status": "open", "created": int(time.time() * 1000)}
    items.append(idea)
    _save(items)
    return idea, True


def update(idea_id, text=None, status=None):
    items = load()
    for it in items:
        if it.get("id") == idea_id:
            if text is not None:
                t = _s(text, MAX_TEXT)
                if not t:
                    raise _m.KValueError("text nápadu je prázdný", "srv.ideas.empty")
                it["text"] = t
            if status is not None:
                if status not in ("open", "done"):
                    raise _m.KValueError("bad status", "srv.ideas.bad_status")
                it["status"] = status
                it["done_at"] = int(time.time() * 1000) if status == "done" else None
            _save(items)
            return it
    raise _m.KValueError("nápad nenalezen", "srv.ideas.not_found")


def delete(idea_id):
    items = load()
    rest = [i for i in items if i.get("id") != idea_id]
    if len(rest) == len(items):
        raise _m.KValueError("nápad nenalezen", "srv.ideas.not_found")
    _save(rest)
