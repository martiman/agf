#!/usr/bin/env python3
import argparse
import hmac
import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
WEB = os.path.join(os.path.dirname(HERE), "web")
HOME = os.environ.get("FLOW_HOME") or os.path.expanduser("~/.flow")
import jira
import workmode
import refine
import status
import ideas
import msg as _m
import appsessions
import approve

PORT = 8765
WORKSPACE = next((p for p in (os.path.expanduser("~/dev/trafinoil"),) if os.path.isdir(p)), "")
CONFIG = os.path.join(HOME, "config.json")
LAUNCH_LOG = os.path.join(HOME, "launch.log")
TOKEN_FILE = os.path.join(HOME, "page.token")


def _page_token():
    try:
        with open(TOKEN_FILE) as f:
            t = f.read().strip()
        if len(t) >= 16:
            return t
    except OSError:
        pass
    t = secrets.token_urlsafe(16)
    fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(t)
    return t


LAUNCH_TOKEN = _page_token()
ACTIONS = {
    "ticket-refine": "Použij skill ticket-refine na {key}.",
    "deliver": "Použij skill deliver na {key}.",
    "check": "Použij skill check na {key}.",
    "bp-update": "Použij skill bp-update na {key}.",
    "ac-check": ("Proveď nezávislou kontrolu akceptačních kritérií tiketu {key}. Postup: přečti tiket v Jiře (pouze čtení), "
                 "pak spusť jednoho subagenta s čistým kontextem a předej mu jen text zadání a číslovaná AC, bez své analýzy. "
                 "Zeptej se ho, které AC je netestovatelné, které hraniční případy chybí, které dvě AC si odporují a jaké "
                 "zjevné čtení zadání není pokryté. Výsledek vypiš česky po jednotlivých AC (AC-n: nález, návrh úpravy). "
                 "Nic nezapisuj do Jiry ani do kódu."),
}
TITLE_LABEL = {"ticket-refine": "refine", "deliver": "deliver", "check": "check", "bp-update": "BP update", "ac-check": "kontrola AC"}


def session_title(action, key, where):
    return " · ".join([key, TITLE_LABEL[action]] + ([where] if where else []))


LAUNCH_KEY_RE = re.compile(r"^APS-\d+$")
LAUNCH_WHERE = {"", "tris", "aps_team_git"}
_launch = {"last": 0.0, "recent": []}


def launch_cfg():
    try:
        with open(CONFIG) as f:
            d = json.load(f).get("launch") or {}
    except (OSError, ValueError, AttributeError):
        d = {}
    return {"enabled": bool(d.get("enabled")), "method": d.get("method") if d.get("method") in ("app", "terminal") else "app",
            "prompts": ACTIONS}


def build_launch(action, key, where):
    if action not in ACTIONS:
        raise _m.KValueError("unknown action", "srv.launch.bad_action")
    if not isinstance(key, str) or not LAUNCH_KEY_RE.match(key):
        raise _m.KValueError("bad ticket key", "srv.launch.bad_key")
    if where not in LAUNCH_WHERE:
        raise _m.KValueError("bad folder", "srv.launch.bad_folder")
    folder = os.path.join(WORKSPACE, where) if (WORKSPACE and where) else WORKSPACE
    if not folder or not os.path.isdir(folder):
        raise _m.KValueError("folder not found", "srv.launch.no_folder")
    title = session_title(action, key, where)
    return folder, (f"{title}\n\n{ACTIONS[action].format(key=key)}\n\n"
                    f"Jako první krok, pokud k tomu máš nástroj, nastav název této session přesně na „{title}“. Pak pokračuj.")


def open_session(method, folder, prompt, dry):
    if method == "app":
        url = "claude://code/new?q=" + quote(prompt, safe="") + "&folder=" + quote(folder, safe="")
        if not dry:
            subprocess.run(["open", url], check=True, timeout=10)
        return {"method": "app", "url": url if dry else None}
    path_dirs = os.path.expanduser("~/.local/bin") + ":/opt/homebrew/bin:/usr/local/bin:" + os.environ.get("PATH", "")
    claude = shutil.which("claude", path=path_dirs)
    if not claude:
        raise _m.KValueError("claude CLI not found", "srv.launch.no_cli")
    script = "#!/bin/bash\ncd %s || exit 1\nexec %s %s\n" % (shlex.quote(folder), shlex.quote(claude), shlex.quote(prompt))
    if dry:
        return {"method": "terminal", "script": script}
    d = os.path.join(HOME, "launch")
    os.makedirs(d, exist_ok=True)
    for old in os.listdir(d):
        p = os.path.join(d, old)
        if old.endswith(".command") and time.time() - os.path.getmtime(p) > 86400:
            os.remove(p)
    p = os.path.join(d, "%d.command" % int(time.time() * 1000))
    with open(p, "w") as f:
        f.write(script)
    os.chmod(p, 0o700)
    subprocess.run(["open", "-a", "Terminal", p], check=True, timeout=10)
    return {"method": "terminal", "url": None}


def launch_guard(action, key, where):
    now = time.time()
    _launch["recent"] = [t for t in _launch["recent"] if now - t[0] < 600]
    if now - _launch["last"] < 3:
        raise _m.KPermissionError("příliš rychle za sebou, zkuste to za chvíli", "srv.launch.too_fast")
    if len(_launch["recent"]) >= 6:
        raise _m.KPermissionError("limit 6 spuštění za 10 minut", "srv.launch.limit")
    if any(t[1:] == (action, key, where) and now - t[0] < 60 for t in _launch["recent"]):
        raise _m.KPermissionError("stejné spuštění už proběhlo před chvílí", "srv.launch.dup")
    _launch["last"] = now
    _launch["recent"].append((now, action, key, where))


def launch_audit(**rec):
    rec["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    try:
        with open(LAUNCH_LOG, "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


SECRET_FILE = os.path.join(HOME, "secret")
NOTIFY_OFF = os.path.join(HOME, "notify.off")

_post_last = {}
cond = threading.Condition()
version = 0
check_lock = threading.Lock()
seen = {}


def read_secret():
    try:
        with open(SECRET_FILE) as f:
            return f.read().strip()
    except OSError:
        return ""


def notify(row):
    if os.path.exists(NOTIFY_OFF):
        return
    where = row.get("title") or os.path.basename(row.get("cwd") or "") or "session"
    msg = "".join(ch for ch in where if ch.isprintable())[:80] + " – potřebuje vaše schválení"
    script = ["on run argv", "display notification (item 1 of argv) with title (item 2 of argv)", "end run"]
    cmd = ["osascript"] + [x for line in script for x in ("-e", line)] + [msg, "Claude čeká na vás"]
    try:
        subprocess.run(cmd, timeout=5, capture_output=True)
    except Exception:
        pass


def notify_text(msg, title):
    if os.path.exists(NOTIFY_OFF):
        return
    msg = "".join(ch for ch in msg if ch.isprintable())[:120]
    script = ["on run argv", "display notification (item 1 of argv) with title (item 2 of argv)", "end run"]
    try:
        subprocess.run(["osascript"] + [x for line in script for x in ("-e", line)] + [msg, title], timeout=5, capture_output=True)
    except Exception:
        pass


seen_refine = {}


def refine_changes(first=False):
    for key, s in refine.summaries().items():
        sig = None
        if s["stage"] == "questions" and s["pending"]:
            sig = ("q", s["round"], s["pending"])
        elif s["stage"] == "draft":
            sig = ("d", s["version"])
        if sig and not first and seen_refine.get(key) != sig:
            notify_text(f"{key}: agent se ptá ({s['pending']} otázek)" if sig[0] == "q" else f"{key}: návrh zadání čeká na schválení",
                        "Zadání tiketu")
        seen_refine[key] = sig


def check_changes(first=False):
    with check_lock:
        for r in status.snapshot():
            cur = (r["state"], r["last_ts"])
            if not first and r["state"] == "waiting" and seen.get(r["session_id"]) != cur:
                notify(r)
            seen[r["session_id"]] = cur
        refine_changes(first)


def workmode_tick(dry=False):
    try:
        rows = [r for r in status.snapshot(48, 10) if r.get("ticket")]
        keys = {r["ticket"] for r in rows}
        tickets = jira.info(keys).get("tickets", {}) if keys else {}
        return workmode.tick(rows, tickets, dry=dry)
    except Exception as e:
        print("workmode:", type(e).__name__, e, flush=True)
        return []


def workmode_loop():
    while True:
        time.sleep(30)
        if workmode.enabled():
            workmode_tick()
            jira.invalidate()


class Handler(BaseHTTPRequestHandler):
    def _headers(self, code, ctype, length=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        if length is not None:
            self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self' 'unsafe-inline'" +
                         (" 'unsafe-eval'" if getattr(self, "_allow_eval", False) else "") + "; connect-src 'self'")

    def _send(self, code, body, ctype):
        data = body if isinstance(body, bytes) else body.encode()
        self._headers(code, ctype, len(data))
        self.end_headers()
        self.wfile.write(data)

    def _host_ok(self):
        return (self.headers.get("Host") or "").split(":")[0] in ("127.0.0.1", "localhost")

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, "forbidden", "text/plain")
        url = urlparse(self.path)
        if url.path == "/":
            self.send_response(302)
            self.send_header("Location", "/v2/")
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if url.path == "/api/state":
            q = parse_qs(url.query)
            try:
                hours = min(max(float(q.get("hours", ["48"])[0]), 1), 720)
                stale = min(max(float(q.get("stale", ["10"])[0]), 1), 240)
            except ValueError:
                return self._send(400, "bad query", "text/plain")
            force = q.get("refresh", ["0"])[0] == "1"
            rows = status.snapshot(hours, stale)
            keys = {r.get("ticket") for r in rows}
            sprint, sprints = [], []
            scope = q.get("scope", ["open"])[0]
            if not jira.SCOPE_RE.match(scope):
                return self._send(400, "bad scope", "text/plain")
            if q.get("sprint", ["0"])[0] == "1":
                sprint = jira.scope_keys(scope, force=force)
                sprints = jira.sprints()
                keys |= set(sprint)
            rf = refine.summaries()
            keys |= set(rf)
            jira_info = jira.info(keys, force=force)
            return self._send(200, json.dumps({"sessions": rows, "jira": jira_info, "sprint": sprint, "sprints": sprints, "scope": scope,
                                               "jira_base": jira.BASE, "workspace": WORKSPACE,
                                               "launch": launch_cfg(), "approve": approve.cfg(), "workmode": workmode.public(), "me": jira.me(), "refine": rf},
                                              ensure_ascii=False),
                              "application/json; charset=utf-8")
        if url.path == "/api/refine":
            key = (parse_qs(url.query).get("key", [""])[0] or "").upper()
            try:
                refine.valid_key(key)
            except refine.RefineError as e:
                return self._json(400, {"error": str(e), "error_k": e.mk})
            rec = refine.load(key)
            return self._json(200, {"record": rec, "checks": refine.draft_checks(rec) if rec else []})
        if url.path == "/api/ticket":
            q = parse_qs(url.query)
            key = (q.get("key", [""])[0] or "").upper()
            if not jira.KEY_RE.match(key):
                return self._send(400, "bad key", "text/plain")
            try:
                hours = min(max(float(q.get("hours", ["168"])[0]), 1), 720)
            except ValueError:
                return self._send(400, "bad query", "text/plain")
            info = jira.info([key], force=q.get("refresh", ["0"])[0] == "1")
            rows = [r for r in status.snapshot(hours, 10) if r.get("ticket") == key]
            body = {"key": key, "sessions": rows,
                    "jira": {"enabled": info.get("enabled"), "reason": info.get("reason"), "reason_k": info.get("reason_k"),
                             "ticket": (info.get("tickets") or {}).get(key)}}
            return self._send(200, json.dumps(body, ensure_ascii=False), "application/json; charset=utf-8")
        if url.path == "/api/app-sessions":
            rows = status.snapshot(24 * 365, 10)
            known = [r["session_id"] for r in rows]
            busy = [r["session_id"] for r in rows if r["state"] in ("running", "waiting")]
            rows_app = appsessions.listing(known, busy)
            keys = sorted({r["ticket"] for r in rows_app if r.get("ticket") and not r["archived"]})
            tk = (jira.info(keys).get("tickets") or {}) if keys else {}
            for r in rows_app:
                r["ticket_status"] = (tk.get(r["ticket"]) or {}).get("status") if r.get("ticket") else None
                r["rec"] = appsessions.recommend(r, r["ticket_status"])
            return self._json(200, {"sessions": rows_app})
        if url.path == "/api/ideas":
            return self._json(200, {"ideas": ideas.load()})
        if url.path == "/api/description":
            q = parse_qs(url.query)
            key = (q.get("key", [""])[0] or "").upper()
            if not jira.KEY_RE.match(key):
                return self._send(400, "bad key", "text/plain")
            return self._json(200, jira.description(key, force=q.get("refresh", ["0"])[0] == "1"))
        if url.path in ("/v2", "/v2/") or url.path.startswith(("/v2/", "/vendor/")):
            return self._static(url.path)
        if url.path == "/api/workmode":
            return self._json(200, {"status": workmode.public(), "plan": workmode_tick(dry=True)})
        if url.path == "/events":
            return self._events()
        self._send(404, "not found", "text/plain")

    STATIC_TYPES = {".js": "application/javascript; charset=utf-8", ".mjs": "application/javascript; charset=utf-8",
                    ".css": "text/css; charset=utf-8", ".html": "text/html; charset=utf-8",
                    ".svg": "image/svg+xml"}

    def _static(self, path):
        rel = "v2/index.html" if path in ("/v2", "/v2/") else path.lstrip("/")
        top = rel.split("/", 1)[0]
        full = os.path.realpath(os.path.join(WEB, rel))
        root = os.path.realpath(os.path.join(WEB, top)) + os.sep
        ctype = self.STATIC_TYPES.get(os.path.splitext(full)[1].lower())
        if top not in ("v2", "vendor") or not full.startswith(root) or not ctype or not os.path.isfile(full):
            return self._send(404, "not found", "text/plain")
        with open(full, "rb") as f:
            data = f.read()
        if rel == "v2/index.html":
            data = data.replace(b"__LAUNCH_TOKEN__", LAUNCH_TOKEN.encode())
            self._allow_eval = True
        return self._send(200, data, ctype)

    def _events(self):
        global version
        self._headers(200, "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        with cond:
            last = version
        try:
            self.wfile.write(b"retry: 3000\n\n")
            self.wfile.flush()
            while True:
                with cond:
                    cond.wait_for(lambda: version != last, timeout=15)
                    changed, last = version != last, version
                self.wfile.write(b"data: tick\n\n" if changed else b": heartbeat\n\n")
                self.wfile.flush()
        except OSError:
            pass

    def do_POST(self):
        global version
        if not self._host_ok():
            return self._send(403, "forbidden", "text/plain")
        if urlparse(self.path).path == "/api/launch":
            return self._launch()
        if urlparse(self.path).path == "/api/approve":
            return self._approve()
        if urlparse(self.path).path == "/api/app-sessions":
            return self._app_sessions_post()
        if urlparse(self.path).path == "/api/ideas":
            return self._ideas_post()
        if urlparse(self.path).path.startswith("/api/refine/"):
            return self._refine_post(urlparse(self.path).path.rsplit("/", 1)[1])
        if urlparse(self.path).path != "/ping":
            return self._send(404, "not found", "text/plain")
        secret = read_secret()
        given = self.headers.get("X-Flow-Secret") or ""
        if not secret or not hmac.compare_digest(secret.encode(), given.encode()):
            return self._send(403, "forbidden", "text/plain")
        try:
            self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 1024))
        except (ValueError, OSError):
            pass
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()
        threading.Thread(target=self._after_ping, daemon=True).start()

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    @staticmethod
    def _guard_json(code, text):
        keys = {"bad origin": "srv.guard.origin", "bad token": "srv.guard.token", "json only": "srv.guard.json", "too large": "srv.guard.too_large"}
        return {"error": text, "error_k": _m.k(keys[text])} if text in keys else {"error": text}

    def _page_guard(self):
        port = self.server.server_address[1]
        if (self.headers.get("Origin") or "") not in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
            return "bad origin"
        if not hmac.compare_digest((self.headers.get("X-Flow-Launch") or "").encode(), LAUNCH_TOKEN.encode()):
            return "bad token"
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            return "json only"
        return None

    def _refine_post(self, action):
        bad = self._page_guard()
        if bad:
            return self._json(403, {"error": bad})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n > 16384:
                return self._json(413, {"error": "too large"})
            body = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(body, dict):
                raise refine.RefineError("Tělo musí být objekt.", _m.k("refine.srv.body_object"))
            key = refine.valid_key(body.get("key"))
            if action == "answer":
                rec = refine.answer(key, body.get("answers"))
            elif action == "edit":
                rec = refine.edit_ac(key, body.get("ac"))
            elif action == "approve-draft":
                rec = refine.approve(key)
            elif action == "discard":
                return self._json(200, {"ok": refine.discard(key)})
            elif action == "import":
                t = (jira.info([key], force=True).get("tickets") or {}).get(key) or {}
                texts = (((t.get("ac") or {}).get("spec") or {}).get("questions")) or []
                rec, new = refine.import_jira(key, texts)
                if not new:
                    return self._json(200, {"ok": True, "imported": 0, "record": rec, "checks": refine.draft_checks(rec) if rec else []})
                launch_audit(action="refine-import", key=key, result=f"ok {len(new)}")
                threading.Thread(target=Handler._after_ping, daemon=True).start()
                return self._json(200, {"ok": True, "imported": len(new), "record": rec, "checks": refine.draft_checks(rec)})
            elif action == "post-decision":
                return self._post_decisions(key, body.get("ids"))
            else:
                return self._json(404, {"error": "unknown action"})
        except (refine.RefineError, ValueError, TypeError) as e:
            return self._json(400, {"error": str(e), "error_k": getattr(e, "mk", None)})
        launch_audit(action="refine-" + action, key=key, result="ok")
        threading.Thread(target=Handler._after_ping, daemon=True).start()
        return self._json(200, {"ok": True, "record": rec, "checks": refine.draft_checks(rec)})

    def _post_decisions(self, key, ids):
        rec = refine.load(key)
        if not rec:
            return self._json(404, {"error": "K tiketu není žádná schránka.", "error_k": _m.k("refine.srv.no_mailbox")})
        todo = [q for q in refine.postable(rec) if ids is None or q["id"] in ids]
        if not todo:
            return self._json(400, {"error": "Nic k zapsání: žádná zodpovězená otázka bez zápisu.", "error_k": _m.k("refine.srv.nothing_to_post")})
        now = time.time()
        if now - _post_last.get(key, 0) < 5:
            return self._json(429, {"error": "příliš rychle za sebou, zkuste to za chvíli", "error_k": _m.k("refine.srv.too_fast")})
        _post_last[key] = now
        try:
            n = jira.next_decision_no(key)
            who = jira.me() or "člověk"
            day = time.strftime("%Y-%m-%d")
            lines = []
            for i, q in enumerate(todo):
                a = q["answer"]
                opt = next((o for o in q.get("options", []) if o["label"] == a.get("choice")), None)
                choice = opt["note"] if opt and opt.get("note") and opt["label"].startswith("Přijmout návrh") else a.get("choice")
                if choice is not a.get("choice"):
                    choice = "Přijmout návrh: " + choice
                lines += [f"Rozhodnutí D-{n + i} · {day} · {who}", "Otázka: " + q["text"],
                          "Volba: " + " · ".join(x for x in (choice, a.get("text")) if x),
                          "Zdroj: dashboard (dialog s agentem)", ""]
            jira.add_comment(key, "\n".join(lines))
        except Exception as e:
            launch_audit(action="refine-post-decision", key=key, result="failed: " + type(e).__name__)
            return self._json(502, {"error": "Komentář se do Jiry nepodařilo zapsat (" + type(e).__name__ + "). Nic se neoznačilo jako zapsané.",
                                    "error_k": _m.k("refine.srv.comment_failed", error=type(e).__name__)})
        rec = refine.mark_posted(key, {q["id"] for q in todo}, f"D-{n}")
        jira.invalidate(key)
        launch_audit(action="refine-post-decision", key=key, result=f"ok D-{n}..D-{n + len(todo) - 1}")
        threading.Thread(target=Handler._after_ping, daemon=True).start()
        return self._json(200, {"ok": True, "posted": len(todo), "first": n,
                                "still_in_description": any(q.get("source") == "jira" for q in todo),
                                "record": rec, "checks": refine.draft_checks(rec)})

    def _approve(self):
        bad = self._page_guard()
        if bad:
            return self._json(415 if bad == "json only" else 403, {"error": bad})
        if not approve.cfg()["enabled"]:
            return self._json(403, {"error": "Schvalování z dashboardu je vypnuté.", "hint": "zapněte příkazem: flow approve on",
                                              "error_k": _m.k("approve.srv.off"), "hint_k": _m.k("approve.srv.off_hint")})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n > 4096:
                return self._json(413, {"error": "too large"})
            body = json.loads(self.rfile.read(n) or b"{}")
            key = body.get("key")
            if body.get("dry") is True:
                return self._json(200, {"ok": True, "plan": approve.plan(key)})
            res = approve.execute(key, body.get("fingerprint"), body.get("confirm"), str(body.get("reason") or "")[:500])
        except approve.ApproveError as e:
            return self._json(e.status, {"error": str(e), "error_k": e.mk})
        except (ValueError, TypeError, AttributeError):
            return self._json(400, {"error": "bad request"})
        threading.Thread(target=Handler._after_ping, daemon=True).start()
        return self._json(200, res)

    def _launch(self):
        port = self.server.server_address[1]
        origin = self.headers.get("Origin") or ""
        if origin not in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
            return self._json(403, {"error": "bad origin", "error_k": _m.k("srv.guard.origin")})
        if not hmac.compare_digest((self.headers.get("X-Flow-Launch") or "").encode(), LAUNCH_TOKEN.encode()):
            return self._json(403, {"error": "bad token", "error_k": _m.k("srv.guard.token")})
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            return self._json(415, {"error": "json only", "error_k": _m.k("srv.guard.json")})
        cfg = launch_cfg()
        if not cfg["enabled"]:
            return self._json(403, {"error": "launch disabled", "error_k": _m.k("srv.launch.off"),
                                    "hint": "zapněte příkazem: flow launch on", "hint_k": _m.k("srv.launch.off_hint")})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n > 1024:
                return self._json(413, self._guard_json(413, "too large"))
            body = json.loads(self.rfile.read(n) or b"{}")
            action, key, where = body.get("action"), body.get("key"), body.get("where") or ""
            dry = body.get("dry") is True
            method = body.get("method") or cfg["method"]
            if method not in ("app", "terminal"):
                raise _m.KValueError("bad method", "srv.launch.bad_method")
            folder, prompt = build_launch(action, key, where)
        except (ValueError, TypeError, AttributeError) as e:
            return self._json(400, _m.err(e))
        try:
            if not dry:
                launch_guard(action, key, where)
            res = open_session(method, folder, prompt, dry)
        except PermissionError as e:
            launch_audit(action=action, key=key, where=where, method=method, result="refused: " + str(e))
            return self._json(429, _m.err(e))
        except (ValueError, subprocess.SubprocessError, OSError) as e:
            launch_audit(action=action, key=key, where=where, method=method, result="failed: " + str(e))
            return self._json(500, {"error": str(e)})
        launch_audit(action=action, key=key, where=where, method=method, dry=dry, result="ok")
        return self._json(200, {"ok": True, "dry": dry, "folder": folder, "prompt": prompt, **res})

    def _ideas_post(self):
        err = self._page_guard()
        if err:
            return self._json(403, self._guard_json(403, err))
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n > 200000:
                return self._json(413, self._guard_json(413, "too large"))
            b = json.loads(self.rfile.read(n) or b"{}")
            act = b.get("action")
            if act == "add":
                idea, created = ideas.add(b.get("text"), b.get("context", ""), b.get("source"), dedupe=b.get("dedupe") is True)
                res = {"idea": idea, "created": created}
            elif act == "add_many":
                items = b.get("items")
                if not isinstance(items, list) or not items or len(items) > 200:
                    raise _m.KValueError("items: 1 až 200 položek", "srv.ideas.items")
                made = [ideas.add(i.get("text"), i.get("context", ""), i.get("source"), dedupe=True)[1] for i in items]
                res = {"created": sum(made), "already": len(made) - sum(made)}
            elif act == "update":
                res = {"idea": ideas.update(b.get("id"), b.get("text"), b.get("status"))}
            elif act == "delete":
                ideas.delete(b.get("id"))
                res = {}
            else:
                raise _m.KValueError("bad action", "srv.guard.bad_action")
        except (ValueError, TypeError, AttributeError) as e:
            return self._json(400, _m.err(e))
        return self._json(200, {"ok": True, **res})

    def _app_sessions_post(self):
        err = self._page_guard()
        if err:
            return self._json(403, self._guard_json(403, err))
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n > 20000:
                return self._json(413, self._guard_json(413, "too large"))
            body = json.loads(self.rfile.read(n) or b"{}")
            action = body.get("action")
            if action not in ("archive", "restore", "delete"):
                raise _m.KValueError("bad action", "srv.guard.bad_action")
            rows = status.snapshot(24 * 365, 10)
            busy = [r["session_id"] for r in rows if r["state"] in ("running", "waiting")]
            if action == "delete":
                res = appsessions.delete_sessions(body.get("ids"), busy, dry=body.get("dry") is True)
            else:
                res = appsessions.set_archived(body.get("ids"), action == "archive", busy, dry=body.get("dry") is True)
        except (ValueError, TypeError, AttributeError) as e:
            return self._json(400, _m.err(e))
        return self._json(200, {"ok": True, **res})

    @staticmethod
    def _after_ping():
        global version
        try:
            check_changes()
            if workmode.enabled():
                workmode_tick()
        finally:
            with cond:
                version += 1
                cond.notify_all()

    def log_message(self, *a):
        pass


class Server(ThreadingHTTPServer):
    daemon_threads = True


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=PORT)
    a = ap.parse_args()
    refine.prune()
    workmode.on_problem = lambda key, msg: notify_text(f"{key}: {msg}", "WorkMode v Jiře")
    threading.Thread(target=workmode_loop, daemon=True).start()
    check_changes(first=True)
    srv = Server(("127.0.0.1", a.port), Handler)
    print(f"dashboard on http://127.0.0.1:{a.port}", flush=True)
    srv.serve_forever()
