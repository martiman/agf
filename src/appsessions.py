#!/usr/bin/env python3
import glob
import json
import os
import re
import shutil
import time

import msg as _m

HOME = os.environ.get("FLOW_HOME") or os.path.expanduser("~/.flow")
ROOT = os.environ.get("FLOW_APP_SESSIONS") or os.path.expanduser("~/Library/Application Support/Claude/claude-code-sessions")
BACKUP = os.path.join(HOME, "app-sessions-backup")
LOG = os.path.join(HOME, "archive.log")
ID_RE = re.compile(r"^local_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
BUSY_MIN = 30
MAX_IDS = 200


def _files():
    return glob.glob(ROOT + "/*/*/local_*.json")


def _find(sid):
    if not ID_RE.match(sid or ""):
        return None
    hits = glob.glob(os.path.join(ROOT, "*", "*", sid + ".json"))
    return hits[0] if len(hits) == 1 else None


KEY_RE = re.compile(r"\bAPS-\d+\b", re.I)
_info_cache = {}
FINISHED = ("Done", "DECLINED", "ACCEPTED")


def _text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _clean(t, n):
    t = re.sub(r"\s+", " ", t or "").strip()
    return t if len(t) <= n else t[:n - 1].rstrip() + "…"


def _is_prompt(t):
    t = (t or "").lstrip()
    return bool(t) and not t.startswith(("<", "Caveat:", "[Request interrupted"))


def transcript_info(cli):
    paths = [p for p in _data_paths(cli) if p.endswith(".jsonl") and os.path.isfile(p)]
    if not paths:
        return {}
    path = paths[0]
    st = os.stat(path)
    key = (st.st_mtime, st.st_size)
    hit = _info_cache.get(path)
    if hit and hit[0] == key:
        return hit[1]
    first = branch = last = None
    try:
        with open(path, "rb") as f:
            for i, line in enumerate(f):
                if i > 600 or (first and branch):
                    break
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if d.get("type") != "user" or d.get("isSidechain") or d.get("isMeta"):
                    continue
                branch = branch or d.get("gitBranch")
                t = _text_of((d.get("message") or {}).get("content"))
                if not first and _is_prompt(t):
                    first = _clean(t, 260)
                elif not first and "<command-name>" in t:
                    nm = re.search(r"<command-name>(.*?)</command-name>", t, re.S)
                    ar = re.search(r"<command-args>(.*?)</command-args>", t, re.S)
                    if nm and nm.group(1).strip() not in ("/clear", "/compact", "/model"):
                        first = _clean(nm.group(1) + " " + (ar.group(1) if ar else ""), 260)
        with open(path, "rb") as f:
            f.seek(max(0, st.st_size - 400000))
            tail = f.read().splitlines()
        for line in reversed(tail):
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("type") == "assistant" and not d.get("isSidechain"):
                t = _text_of((d.get("message") or {}).get("content"))
                if t.strip():
                    last = _clean(t, 260)
                    break
    except OSError:
        return {}
    info = {"first_prompt": first, "last_reply": last, "branch": branch}
    _info_cache[path] = (key, info)
    while len(_info_cache) > 400:
        _info_cache.pop(next(iter(_info_cache)))
    return info


def ticket_of(row):
    for src in (row.get("title"), row.get("first_prompt")):
        m = KEY_RE.search(src or "")
        if m:
            return m.group(0).upper()
    return None


def _r(action, reason, key, **params):
    return {"action": action, "reason": reason, "reason_k": _m.k(key, **params)}


def _w(sid, why, key, **params):
    return {"id": sid, "why": why, "why_k": _m.k(key, **params)}


def recommend(row, ticket_status=None):
    age_d = (row.get("age_min") or 0) / 1440
    days = "%d dní" % age_d
    tk, turns = row.get("ticket"), row.get("turns") or 0
    if row.get("archived"):
        return _r("keep", "Už je archivovaná.", "srv.rec.archived")
    if row.get("busy"):
        return _r("keep", "Aktivní nebo běží právě teď.", "srv.rec.busy")
    if not row.get("first_prompt") and not row.get("last_reply") and age_d >= 14:
        return _r("delete", "Přepis konverzace už neexistuje, v aplikaci zbyl jen prázdný záznam.", "srv.rec.no_transcript")
    if turns <= 1 and age_d >= 14:
        return _r("delete", "Prázdná session (%d tahů), %s bez aktivity." % (turns, days), "srv.rec.empty", n=turns, days=int(age_d))
    if tk and ticket_status in FINISHED:
        return _r("archive", "Tiket %s je %s." % (tk, ticket_status), "srv.rec.ticket_done", ticket=tk, status=ticket_status)
    if tk and ticket_status:
        if age_d >= 30:
            return _r("review", "Tiket %s je pořád otevřený (%s), ale session leží %s." % (tk, ticket_status, days), "srv.rec.ticket_idle", ticket=tk, status=ticket_status, days=int(age_d))
        return _r("keep", "Rozdělaná práce na %s (%s)." % (tk, ticket_status), "srv.rec.ticket_wip", ticket=tk, status=ticket_status)
    if age_d >= 30:
        big = turns >= 40
        if big:
            return _r("review", "Velká session (%d tahů), %s bez aktivity. Zkontrolujte, jestli v ní není hodnotná práce." % (turns, days), "srv.rec.big", turns=turns, days=int(age_d))
        return _r("archive", "Bez tiketu, %s bez aktivity." % days, "srv.rec.no_ticket", days=int(age_d))
    return _r("keep", "Čerstvá session (%s)." % days, "srv.rec.fresh", n=int(age_d))


def listing(known_cli_ids=(), busy_cli_ids=()):
    now = time.time() * 1000
    known, busy, out = set(known_cli_ids), set(busy_cli_ids), []
    for p in _files():
        try:
            with open(p) as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        sid = d.get("sessionId")
        if not sid or not ID_RE.match(sid):
            continue
        last = d.get("lastActivityAt") or d.get("createdAt") or 0
        age_min = max(0, (now - last) / 60000) if last else None
        cli = d.get("cliSessionId")
        out.append({
            "id": sid, "cli_id": cli, "title": d.get("title") or "", "cwd": d.get("cwd") or "",
            "archived": bool(d.get("isArchived")), "last": last, "age_min": age_min, "turns": d.get("completedTurns") or 0,
            "in_agf": cli in known, "busy": cli in busy or (age_min is not None and age_min < BUSY_MIN),
        })
        out[-1].update(transcript_info(cli))
        out[-1]["ticket"] = ticket_of(out[-1])
    out.sort(key=lambda r: r["last"] or 0, reverse=True)
    return out


def _log(**rec):
    rec["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    try:
        os.makedirs(HOME, exist_ok=True)
        with open(LOG, "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _write(path, d):
    tmp = path + ".agf-tmp"
    mode = os.stat(path).st_mode & 0o777
    with open(tmp, "w") as f:
        json.dump(d, f, ensure_ascii=False, separators=(",", ":"))
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def set_archived(ids, archived, busy_cli_ids=(), dry=False):
    if not isinstance(ids, list) or not ids or len(ids) > MAX_IDS or not all(isinstance(i, str) for i in ids):
        raise _m.KValueError("ids: 1 až %d položek" % MAX_IDS, "srv.ids", max=MAX_IDS)
    busy, done, skipped = set(busy_cli_ids), [], []
    stamp = time.strftime("%Y%m%d-%H%M%S")
    bdir = os.path.join(BACKUP, stamp)
    for sid in dict.fromkeys(ids):
        p = _find(sid)
        if not p:
            skipped.append(_w(sid, "session nenalezena", "srv.why.not_found"))
            continue
        try:
            with open(p) as f:
                d = json.load(f)
        except (OSError, ValueError):
            skipped.append(_w(sid, "metadata nejdou přečíst", "srv.why.unreadable"))
            continue
        if bool(d.get("isArchived")) == archived:
            skipped.append((_w(sid, "už je archivovaná", "srv.why.already_archived") if archived else _w(sid, "není archivovaná", "srv.why.not_archived")))
            continue
        last = d.get("lastActivityAt") or d.get("createdAt") or 0
        if archived and (d.get("cliSessionId") in busy or (last and (time.time() * 1000 - last) < BUSY_MIN * 60000)):
            skipped.append(_w(sid, "session je aktivní (posledních %d min)" % BUSY_MIN, "srv.why.active", n=BUSY_MIN))
            continue
        if not dry:
            try:
                os.makedirs(bdir, exist_ok=True)
                shutil.copy2(p, os.path.join(bdir, sid + ".json"))
                d["isArchived"] = archived
                _write(p, d)
                with open(p) as f:
                    if bool(json.load(f).get("isArchived")) != archived:
                        raise OSError("zápis se nepotvrdil")
            except (OSError, ValueError) as e:
                skipped.append(_w(sid, "zápis selhal: %s" % e, "srv.why.write_failed", error=str(e)))
                continue
            _log(action="archive" if archived else "restore", id=sid, title=d.get("title"), backup=bdir)
        done.append(sid)
    return {"done": done, "skipped": skipped, "dry": dry, "backup": bdir if done and not dry else None}


CLAUDE = os.environ.get("FLOW_CLAUDE_HOME") or os.path.expanduser("~/.claude")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _size(path):
    if os.path.islink(path):
        return 0
    if os.path.isfile(path):
        return os.path.getsize(path)
    total = 0
    for dp, _, fs in os.walk(path):
        for f in fs:
            fp = os.path.join(dp, f)
            if not os.path.islink(fp):
                total += os.path.getsize(fp)
    return total


def _data_paths(cli):
    if not UUID_RE.match(cli or ""):
        return []
    pats = [f"projects/*/{cli}.jsonl", f"projects/*/{cli}", f"file-history/{cli}", f"session-env/{cli}", f"todos/{cli}-*.json"]
    out = []
    for pat in pats:
        for p in glob.glob(os.path.join(CLAUDE, pat)):
            real = os.path.realpath(os.path.dirname(p))
            if os.path.islink(p) or not real.startswith(os.path.realpath(CLAUDE) + os.sep):
                continue
            out.append(p)
    return out


def delete_sessions(ids, busy_cli_ids=(), dry=False):
    if not isinstance(ids, list) or not ids or len(ids) > MAX_IDS or not all(isinstance(i, str) for i in ids):
        raise _m.KValueError("ids: 1 až %d položek" % MAX_IDS, "srv.ids", max=MAX_IDS)
    busy, done, skipped, total = set(busy_cli_ids), [], [], 0
    for sid in dict.fromkeys(ids):
        p = _find(sid)
        if not p:
            skipped.append(_w(sid, "session nenalezena", "srv.why.not_found"))
            continue
        try:
            with open(p) as f:
                d = json.load(f)
        except (OSError, ValueError):
            skipped.append(_w(sid, "metadata nejdou přečíst", "srv.why.unreadable"))
            continue
        last = d.get("lastActivityAt") or d.get("createdAt") or 0
        if d.get("cliSessionId") in busy or (last and (time.time() * 1000 - last) < BUSY_MIN * 60000):
            skipped.append(_w(sid, "session je aktivní (posledních %d min)" % BUSY_MIN, "srv.why.active", n=BUSY_MIN))
            continue
        paths = _data_paths(d.get("cliSessionId"))
        size = _size(p) + sum(_size(x) for x in paths)
        if not dry:
            try:
                for x in paths:
                    shutil.rmtree(x) if os.path.isdir(x) else os.remove(x)
                os.remove(p)
            except OSError as e:
                skipped.append(_w(sid, "mazání selhalo: %s" % e, "srv.why.delete_failed", error=str(e)))
                continue
            _log(action="delete", id=sid, title=d.get("title"), removed=[os.path.relpath(x, CLAUDE) for x in paths], bytes=size)
        total += size
        done.append(sid)
    return {"done": done, "skipped": skipped, "bytes": total, "dry": dry}
