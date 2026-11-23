#!/usr/bin/env python3
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

import msg as _m

TTL_OK = 120
TTL_FAIL = 30
KEY_RE = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")
ENV_FILE = os.path.join(os.environ.get("FLOW_HOME") or os.path.expanduser("~/.flow"), "jira.env")


def _env_file():
    vals = {}
    try:
        with open(ENV_FILE) as f:
            for line in f:
                if "=" in line and not line.lstrip().startswith("#"):
                    k, v = line.strip().split("=", 1)
                    vals[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return vals


BASE = (os.environ.get("JIRA_BASE_URL") or _env_file().get("JIRA_BASE_URL") or "").rstrip("/")

_cache = {}


def _creds():
    if not BASE:
        return None, None
    email, token = os.environ.get("JIRA_EMAIL"), os.environ.get("JIRA_API_TOKEN")
    if email and token:
        return email, token
    vals = _env_file()
    return vals.get("JIRA_EMAIL"), vals.get("JIRA_API_TOKEN")


def _parent(p):
    if not isinstance(p, dict) or not p.get("key"):
        return None
    pf = p.get("fields") or {}
    st = pf.get("status") or {}
    return {
        "key": p["key"],
        "summary": pf.get("summary"),
        "type": (pf.get("issuetype") or {}).get("name"),
        "status": st.get("name"),
        "category": (st.get("statusCategory") or {}).get("key"),
    }


def _wm_param():
    ids = _wm["ids"]
    return ("," + ids["mode"] + "," + ids["action"]) if ids else ""


def _wm_values(f):
    ids = _wm["ids"]
    if not ids:
        return None
    return {"mode": (f.get(ids["mode"]) or {}).get("value"), "action": f.get(ids["action"])}


def _fetch(keys, email, token):
    out = {}
    for i in range(0, len(keys), 100):
        out.update(_fetch_chunk(keys[i:i + 100], email, token))
    return out


def _fetch_chunk(keys, email, token):
    import base64
    jql = "key in (" + ",".join(keys) + ")"
    qs = urllib.parse.urlencode({
        "jql": jql, "maxResults": 100,
        "fields": "summary,status,issuetype,assignee,updated,parent,labels" + _wm_param(),
    })
    auth = base64.b64encode(f"{email}:{token}".encode()).decode()
    req = urllib.request.Request(
        f"{BASE}/rest/api/3/search/jql?{qs}",
        headers={"Authorization": f"Basic {auth}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=8) as r:
        data = json.load(r)
    out = {}
    for issue in data.get("issues", []):
        f = issue.get("fields", {})
        st = f.get("status") or {}
        out[issue["key"]] = {
            "status": st.get("name"),
            "category": (st.get("statusCategory") or {}).get("key"),
            "summary": f.get("summary"),
            "type": (f.get("issuetype") or {}).get("name"),
            "assignee": (f.get("assignee") or {}).get("displayName"),
            "url": f"{BASE}/browse/{issue['key']}",
            "updated": f.get("updated"),
            "parent": _parent(f.get("parent")),
            "labels": f.get("labels") or [],
            "workmode": _wm_values(f),
        }
    _add_ac(out, email, token)
    return out



_detail_cache = {}


def _get(path, params, email, token):
    import base64
    auth = base64.b64encode(f"{email}:{token}".encode()).decode()
    req = urllib.request.Request(
        f"{BASE}{path}?{urllib.parse.urlencode(params)}",
        headers={"Authorization": f"Basic {auth}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.load(r)


def _ac_for(key, t, email, token):
    import ac
    cfg = ac.config()
    hit = _detail_cache.get(key)
    if hit and hit[0] == t.get("updated"):
        return hit[1]
    try:
        d = _get(f"/rest/api/3/issue/{key}",
                 {"fields": f"description,{cfg['ac_field']}", "expand": "changelog"}, email, token)
        cl = d.get("changelog") or {}
        histories = list(cl.get("histories", []))
        total = cl.get("total", len(histories))
        while len(histories) < total:
            page = _get(f"/rest/api/3/issue/{key}/changelog", {"startAt": len(histories), "maxResults": 100}, email, token)
            vals = page.get("values", [])
            if not vals:
                break
            histories += vals
        f = d.get("fields", {})
        res = ac.analyze(f.get(cfg["ac_field"]), f.get("description"), histories, t.get("status"), cfg)
        try:
            import spec
            res["spec"] = spec.lint(f.get("description"), res, t.get("type"), t.get("labels"))
        except Exception:
            res["spec"] = None
    except urllib.error.HTTPError as e:
        return {"gate": "unknown", "reason": f"HTTP {e.code}", "criteria": [], "total": 0, "ticked": 0}
    except Exception as e:
        return {"gate": "unknown", "reason": type(e).__name__, "criteria": [], "total": 0, "ticked": 0}
    _detail_cache[key] = (t.get("updated"), res)
    return res



_desc_cache = {}
DESC_MAX = 60000


def _segs(node, out, marks=()):
    t = node.get("type")
    if t == "text":
        m = {x.get("type"): x for x in node.get("marks") or []}
        href = (m.get("link") or {}).get("attrs", {}).get("href")
        seg = {"t": node.get("text", "")}
        if "strong" in m:
            seg["b"] = 1
        if "code" in m:
            seg["c"] = 1
        if href and href.startswith(("http://", "https://")):
            seg["href"] = href
        out.append(seg)
    elif t == "hardBreak":
        out.append({"t": "\n"})
    elif t in ("mention", "emoji", "status", "inlineCard"):
        a = node.get("attrs") or {}
        txt = a.get("text") or a.get("shortName") or a.get("url") or ""
        if txt:
            out.append({"t": txt})
    else:
        for c in node.get("content", []) or []:
            if isinstance(c, dict):
                _segs(c, out)


def adf_blocks(adf):
    out = []

    def inl(n):
        segs = []
        _segs(n, segs)
        return segs

    def walk(n, depth=0, ordered=None):
        if not isinstance(n, dict):
            return
        t = n.get("type")
        if t == "paragraph":
            segs = inl(n)
            if any(x["t"].strip() for x in segs):
                out.append({"k": "p", "text": segs, "depth": depth})
        elif t == "heading":
            out.append({"k": "h", "level": (n.get("attrs") or {}).get("level", 3), "text": inl(n)})
        elif t in ("bulletList", "orderedList", "taskList"):
            for i, c in enumerate(n.get("content", []) or []):
                walk(c, depth, (i + 1) if t == "orderedList" else None)
        elif t in ("listItem", "taskItem"):
            first, rest = True, []
            for c in n.get("content", []) or []:
                if first and c.get("type") in ("paragraph", None):
                    item = {"k": "li", "text": inl(c), "depth": depth}
                    if ordered:
                        item["n"] = ordered
                    if t == "taskItem":
                        item["done"] = (n.get("attrs") or {}).get("state") == "DONE"
                        item["task"] = 1
                    out.append(item)
                    first = False
                else:
                    rest.append(c)
            if t == "taskItem" and first:
                out.append({"k": "li", "text": inl(n), "depth": depth, "task": 1,
                            "done": (n.get("attrs") or {}).get("state") == "DONE"})
            for c in rest:
                walk(c, depth + 1)
        elif t == "codeBlock":
            out.append({"k": "code", "text": [{"t": "".join(x["t"] for x in inl(n))}]})
        elif t == "blockquote":
            for c in n.get("content", []) or []:
                if c.get("type") == "paragraph":
                    out.append({"k": "quote", "text": inl(c)})
                else:
                    walk(c, depth)
        elif t == "rule":
            out.append({"k": "rule"})
        elif t == "table":
            for row in n.get("content", []) or []:
                cells = [" ".join(x["t"] for x in inl(c)).strip() for c in row.get("content", []) or []]
                out.append({"k": "p", "text": [{"t": " | ".join(cells)}], "depth": depth})
        else:
            for c in n.get("content", []) or []:
                walk(c, depth, ordered)

    walk(adf)
    size = 0
    for i, b in enumerate(out):
        size += sum(len(x["t"]) for x in b.get("text", []))
        if size > DESC_MAX:
            return out[:i + 1], True
    return out, False


def description(key, force=False):
    email, token = _creds()
    if not (email and token):
        return {"error": "chybí JIRA_EMAIL / JIRA_API_TOKEN", "error_k": _m.k("srv.jira.no_creds")}
    try:
        d = _get(f"/rest/api/3/issue/{key}", {"fields": "description,updated"}, email, token)
    except urllib.error.HTTPError as e:
        return {"error": f"Jira odpověděla HTTP {e.code}", "error_k": _m.k("srv.jira.http", code=e.code)}
    except Exception as e:
        return {"error": f"Jira nedostupná ({type(e).__name__})", "error_k": _m.k("srv.jira.down", error=type(e).__name__)}
    f = d.get("fields") or {}
    hit = _desc_cache.get(key)
    if hit and hit[0] == f.get("updated") and not force:
        return hit[1]
    adf = f.get("description")
    blocks, cut = adf_blocks(adf) if isinstance(adf, dict) else ([], False)
    res = {"key": key, "blocks": blocks, "truncated": cut, "updated": f.get("updated")}
    _desc_cache[key] = (f.get("updated"), res)
    while len(_desc_cache) > 20:
        _desc_cache.pop(next(iter(_desc_cache)))
    return res


def _add_ac(tickets, email, token):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {k: ex.submit(_ac_for, k, t, email, token) for k, t in tickets.items()}
        for k, fut in futures.items():
            tickets[k]["ac"] = fut.result()


def info(keys, force=False):
    keys = sorted({k for k in keys if k and KEY_RE.match(k)})
    email, token = _creds()
    if not (email and token):
        return {"enabled": False, "reason": "chybí JIRA_EMAIL / JIRA_API_TOKEN", "reason_k": _m.k("srv.jira.no_creds"), "tickets": {}}
    wm_ids()
    if not keys:
        return {"enabled": True, "reason": None, "tickets": {}, "fetched": time.time()}
    now = time.time()
    c = _cache.get(tuple(keys)) or {"key": None, "at": 0.0, "value": None}
    ttl = TTL_OK if (c["value"] and c["value"].get("enabled") and not c["value"].get("reason")) else TTL_FAIL
    if not force and c["key"] == keys and now - c["at"] < ttl and c["value"] is not None:
        return c["value"]
    try:
        value = {"enabled": True, "reason": None, "tickets": _fetch(keys, email, token), "fetched": now}
    except urllib.error.HTTPError as e:
        value = {"enabled": True, "reason": f"Jira odpověděla HTTP {e.code}", "reason_k": _m.k("srv.jira.http", code=e.code), "tickets": {}, "fetched": now}
    except Exception as e:
        value = {"enabled": True, "reason": f"Jira nedostupná ({type(e).__name__})", "reason_k": _m.k("srv.jira.down", error=type(e).__name__), "tickets": {}, "fetched": now}
    c.update(key=keys, at=now, value=value)
    _cache[tuple(keys)] = c
    while len(_cache) > 8:
        _cache.pop(next(iter(_cache)))
    return value



SPRINT_JQL = ('project = APS AND sprint in openSprints() '
              'AND issuetype in (Story, Bug, Task, Subtask) ORDER BY key')
_TYPES = "issuetype in (Story, Bug, Task, Subtask)"
BACKLOG_JQL = f"project = APS AND sprint is EMPTY AND statusCategory != Done AND {_TYPES} ORDER BY key"
_scopes = {}
SCOPE_RE = re.compile(r"^(open|backlog|sprint:\d{1,6})$")


def scope_jql(scope):
    if scope == "open":
        return SPRINT_JQL
    if scope == "backlog":
        return BACKLOG_JQL
    if SCOPE_RE.match(scope or "") and scope.startswith("sprint:"):
        return f"project = APS AND sprint = {int(scope.split(':')[1])} AND {_TYPES} ORDER BY key"
    raise ValueError("bad scope")


def scope_keys(scope="open", force=False):
    jql = scope_jql(scope)
    slot = _scopes.setdefault(scope, {"at": 0.0, "keys": []})
    now = time.time()
    if not force and slot["keys"] and now - slot["at"] < TTL_OK:
        return slot["keys"]
    email, token = _creds()
    if not (email and token):
        return []
    keys, tok = [], None
    try:
        for _ in range(5):
            params = {"jql": jql, "maxResults": 100, "fields": "summary"}
            if tok:
                params["nextPageToken"] = tok
            d = _get("/rest/api/3/search/jql", params, email, token)
            keys += [i["key"] for i in d.get("issues", []) if KEY_RE.match(i.get("key", ""))]
            tok = d.get("nextPageToken")
            if not tok or d.get("isLast"):
                break
    except Exception:
        return slot["keys"]
    slot.update(at=now, keys=keys)
    return keys


def sprint_keys(force=False):
    return scope_keys("open", force)


_sprints = {"at": 0.0, "list": []}


def sprints():
    now = time.time()
    if _sprints["list"] and now - _sprints["at"] < 600:
        return _sprints["list"]
    email, token = _creds()
    if not (email and token):
        return []
    try:
        boards = _get("/rest/agile/1.0/board", {"projectKeyOrId": "APS"}, email, token).get("values", [])
        b = next((x for x in boards if (x.get("location") or {}).get("projectKey") == "APS" and x.get("type") in ("simple", "scrum")), None)
        if not b:
            return _sprints["list"]
        vals = _get(f"/rest/agile/1.0/board/{b['id']}/sprint", {"state": "active,future", "maxResults": 50}, email, token).get("values", [])
    except Exception:
        return _sprints["list"]
    _sprints.update(at=now, list=[{"id": v["id"], "name": v.get("name"), "state": v.get("state")} for v in vals])
    return _sprints["list"]



_me = {"at": 0.0, "name": None}


def me():
    now = time.time()
    if _me["name"] and now - _me["at"] < 3600:
        return _me["name"]
    email, token = _creds()
    if not (email and token):
        return None
    try:
        name = _get("/rest/api/3/myself", {}, email, token).get("displayName")
    except Exception:
        return _me["name"]
    _me.update(at=now, name=name)
    return name



def _send(method, path, body=None):
    import base64
    email, token = _creds()
    if not (email and token):
        raise RuntimeError("Jira není nastavená (JIRA_BASE_URL / JIRA_EMAIL / JIRA_API_TOKEN)")
    auth = base64.b64encode(f"{email}:{token}".encode()).decode()
    req = urllib.request.Request(
        f"{BASE}{path}", method=method, data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Basic {auth}", "Accept": "application/json", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        raw = r.read()
    return json.loads(raw) if raw else {}


def transitions(key):
    return _send("GET", f"/rest/api/3/issue/{key}/transitions").get("transitions", [])


def do_transition(key, transition_id):
    _send("POST", f"/rest/api/3/issue/{key}/transitions", {"transition": {"id": str(transition_id)}})


def add_comment(key, text):
    paras = [{"type": "paragraph", "content": [{"type": "text", "text": ln}]} for ln in str(text).split("\n") if ln.strip()]
    _send("POST", f"/rest/api/3/issue/{key}/comment", {"body": {"type": "doc", "version": 1, "content": paras or [
        {"type": "paragraph", "content": [{"type": "text", "text": "-"}]}]}})


def next_decision_no(key):
    email, token = _creds()
    d = _get(f"/rest/api/3/issue/{key}/comment", {"maxResults": 100}, email, token)
    best = 0
    for c in d.get("comments", []):
        def walk(n):
            if isinstance(n, dict):
                yield n.get("text") or ""
                for ch in n.get("content") or []:
                    yield from walk(ch)
        for m in re.finditer(r"Rozhodnutí D-(\d+)", " ".join(walk(c.get("body")))):
            best = max(best, int(m.group(1)))
    return best + 1


def invalidate(key=None):
    _cache.clear()
    if key:
        _detail_cache.pop(key, None)


_statuses = {"at": 0.0, "names": None}


def status_names(project="APS"):
    now = time.time()
    if _statuses["names"] is not None and now - _statuses["at"] < 600:
        return _statuses["names"]
    email, token = _creds()
    if not (email and token):
        return None
    try:
        data = _get(f"/rest/api/3/project/{project}/statuses", {}, email, token)
        names = {s["name"] for it in data for s in it.get("statuses", [])}
    except Exception:
        return _statuses["names"]
    _statuses.update(at=now, names=names)
    return names



WM_NAMES = ("workmode", "nextaction")
_wm = {"at": 0.0, "ids": None}
_wm_opts = {}


def wm_ids(force=False):
    now = time.time()
    if not force and _wm["ids"] is not None and now - _wm["at"] < 600:
        return _wm["ids"]
    email, token = _creds()
    if not (email and token):
        return None
    try:
        fields = _get("/rest/api/3/field", {}, email, token)
    except Exception:
        return _wm["ids"]
    found = {}
    for f in fields:
        n = re.sub(r"\s+", "", f.get("name", "")).lower()
        t = (f.get("schema") or {}).get("type")
        if n == WM_NAMES[0] and t == "option":
            found["mode"] = f["id"]
        elif n == WM_NAMES[1] and t == "string":
            found["action"] = f["id"]
    ids = found if len(found) == 2 else {}
    _wm.update(at=now, ids=ids)
    return ids


def wm_options(issue_type, project="APS"):
    ids = wm_ids()
    if not ids:
        return None
    now = time.time()
    hit = _wm_opts.get(issue_type)
    if hit and now - hit[0] < 600:
        return hit[1]
    email, token = _creds()
    try:
        types = _get(f"/rest/api/3/issue/createmeta/{project}/issuetypes", {}, email, token)
        tid = next((t["id"] for t in types.get("issueTypes", types.get("values", [])) if t.get("name") == issue_type), None)
        if not tid:
            raise KeyError(issue_type)
        meta = _get(f"/rest/api/3/issue/createmeta/{project}/issuetypes/{tid}", {}, email, token)
        by_id = {f["fieldId"]: f for f in meta.get("fields", meta.get("values", []))}
    except Exception:
        return hit[1] if hit else None
    m, a = by_id.get(ids["mode"]), by_id.get(ids["action"])
    res = None
    if m and a:
        res = {"mode": ids["mode"], "action": ids["action"],
               "options": {o["value"]: o["id"] for o in m.get("allowedValues", [])}}
    _wm_opts[issue_type] = (now, res)
    return res


def wm_read(key):
    ids = wm_ids()
    if not ids:
        raise RuntimeError("pole WorkMode / NextAction v Jiře nejsou")
    email, token = _creds()
    d = _get(f"/rest/api/3/issue/{key}", {"fields": f"{ids['mode']},{ids['action']},updated,status,issuetype"}, email, token)
    f = d.get("fields", {})
    return {"mode": (f.get(ids["mode"]) or {}).get("value"), "action": f.get(ids["action"]),
            "updated": f.get("updated"), "type": (f.get("issuetype") or {}).get("name"),
            "category": ((f.get("status") or {}).get("statusCategory") or {}).get("key")}


def wm_write(key, opts, mode, action):
    body = {opts["mode"]: None if mode is None else {"id": opts["options"][mode]},
            opts["action"]: None if mode is None else action}
    _send("PUT", f"/rest/api/3/issue/{key}", {"fields": body})
    invalidate(key)
