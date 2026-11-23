#!/usr/bin/env python3
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), "src")
fails = 0


def check(name, got, want=True):
    global fails
    ok = got == want
    fails += 0 if ok else 1
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def para(t):
    return {"type": "paragraph", "content": [{"type": "text", "text": t}]}


def head(t):
    return {"type": "heading", "attrs": {"level": 3}, "content": [{"type": "text", "text": t}]}


QTEXT = "Kde držet otisky vzorků? Návrh: Jira jako sdílené úložiště, lokální soubor ve scratch jen jako cache, a to i při opakovaném spuštění stejného běhu na stejných datech."
DESC = {"type": "doc", "version": 1, "content": [
    head("Problém"), para("Skill načítá celý soubor a stojí zbytečný kontext při každém spuštění."),
    head("Kde to je"), para("SKILL.md:1"), head("Očekávané chování"),
    {"type": "bulletList", "content": [{"type": "listItem", "content": [para("AC-1: Soubor má do 100 řádků, pak se zobrazí stručný přehled.")]}]},
    head("Otevřené otázky"), {"type": "bulletList", "content": [{"type": "listItem", "content": [para(QTEXT)]}]}]}

J = {"writes": [], "comments": [{"body": {"type": "doc", "content": [para("Rozhodnutí D-2 · dřívější")]}}], "fail": False, "descwrites": 0}


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj, code=200):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path.endswith("/search/jql"):
            return self._send({"issues": [{"key": "APS-1", "fields": {
                "summary": "Skill", "status": {"name": "TO DO", "statusCategory": {"key": "new"}}, "issuetype": {"name": "Story"},
                "assignee": None, "updated": "2026-11-18T10:00:00.000+0100", "labels": []}}], "isLast": True})
        if path == "/rest/api/3/issue/APS-1":
            return self._send({"fields": {"description": DESC, "customfield_10606": None}, "changelog": {"histories": [], "total": 0}})
        if path.endswith("/comment"):
            return self._send({"comments": J["comments"]})
        if path.endswith("/field"):
            return self._send([])
        if path.endswith("/myself"):
            return self._send({"displayName": "Tester"})
        self._send({}, 404)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        if J["fail"]:
            return self._send({"errorMessages": ["boom"]}, 500)
        J["writes"].append((self.path.split("?")[0], body))
        self._send({"id": "9"}, 201)

    def do_PUT(self):
        J["descwrites"] += 1
        self._send({}, 204)


jp = free_port()
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", jp), Fake).serve_forever, daemon=True).start()
home = tempfile.mkdtemp()
dp = free_port()
env = dict(os.environ, JIRA_BASE_URL=f"http://127.0.0.1:{jp}", JIRA_EMAIL="t@example.test", JIRA_API_TOKEN="dummy",
           FLOW_HOME=home, FLOW_REFINE_DIR=os.path.join(home, "refine"))
srv = subprocess.Popen([sys.executable, os.path.join(SRC, "dashboard.py"), "--port", str(dp)], env=env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, cwd=SRC)
base = f"http://127.0.0.1:{dp}"
for _ in range(50):
    try:
        urllib.request.urlopen(base + "/api/state?hours=1", timeout=1)
        break
    except Exception:
        time.sleep(0.2)


def post(action, body, token, origin=True):
    h = {"Content-Type": "application/json"}
    if origin:
        h["Origin"] = base
    if token:
        h["X-Flow-Launch"] = token
    req = urllib.request.Request(base + "/api/refine/" + action, data=json.dumps(body).encode(), headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


try:
    token = re.search(r'name="flow-token" content="([^"]+)"', urllib.request.urlopen(base + "/v2/", timeout=5).read().decode()).group(1)
    st = json.load(urllib.request.urlopen(base + "/api/ticket?key=APS-1", timeout=20))
    spec = st["jira"]["ticket"]["ac"]["spec"]
    check("the open question of the description is exposed to the page", spec["questions"], [QTEXT])

    check("import without a token: refused", post("import", {"key": "APS-1"}, None)[0], 403)
    check("import without Origin: refused", post("import", {"key": "APS-1"}, token, origin=False)[0], 403)
    s, r = post("import", {"key": "APS-1"}, token)
    q = r["record"]["questions"][0]
    check("import: one question, the proposal is the recommended option, nothing written to Jira",
          (s, r["imported"], q["text"], q["options"][0]["recommended"], q["options"][0]["label"].startswith("Přijmout návrh: Jira"), J["writes"]),
          (200, 1, "Kde držet otisky vzorků?", True, True, []))
    check("import: marked as taken over from Jira", (q["source"], q["src_text"]), ("jira", QTEXT))
    s, r = post("import", {"key": "APS-1"}, token)
    check("a second import adds nothing", (s, r["imported"], len(r["record"]["questions"])), (200, 0, 1))

    check("posting before an answer: nothing to post", post("post-decision", {"key": "APS-1"}, token)[0], 400)
    s, r = post("answer", {"key": "APS-1", "answers": {"Q1": {"choice": q["options"][0]["label"], "text": "Jira je zdroj pravdy."}}}, token)
    check("answered", (s, r["record"]["questions"][0]["answer"]["choice"] is not None), (200, True))

    check("post without a token: refused, nothing written", (post("post-decision", {"key": "APS-1"}, None)[0], J["writes"]), (403, []))
    J["fail"] = True
    s, r = post("post-decision", {"key": "APS-1"}, token)
    rec = json.loads(open(os.path.join(home, "refine", "APS-1.json")).read())
    check("a failed write is reported and the question is NOT marked as written", (s, "posted_at" in rec["questions"][0]), (502, False))
    J["fail"] = False
    time.sleep(5.2)
    s, r = post("post-decision", {"key": "APS-1"}, token)
    check("post: 200, one comment", (s, r["posted"], len(J["writes"])), (200, 1, 1))
    path, body = J["writes"][0]
    text = " ".join(p["content"][0]["text"] for p in body["body"]["content"])
    check("it goes to the comment endpoint of the ticket", path, "/rest/api/3/issue/APS-1/comment")
    check("numbering continues after the highest existing D-n (D-2 -> D-3)", "Rozhodnutí D-3" in text, True)
    check("comment has the question, the choice and the source",
          all(x in text for x in ("Kde držet otisky vzorků?", "Jira je zdroj pravdy.", "Zdroj: dashboard")), True)
    check("a long proposal is written in full, not cut like the option label", "ve scratch jen jako cache, a to i při opakovaném spuštění stejného běhu na stejných datech." in text, True)
    check("every line is its own paragraph", len(body["body"]["content"]) >= 4, True)
    check("the description is NEVER edited", J["descwrites"], 0)
    check("it says the question stays in the description", r["still_in_description"], True)
    rec = json.loads(open(os.path.join(home, "refine", "APS-1.json")).read())
    check("question marked as written (and nobody has to say 'pokračuj')",
          (rec["questions"][0]["posted_as"], rec["questions"][0]["consumed"]), ("D-3", True))
    time.sleep(5.2)
    s, r = post("post-decision", {"key": "APS-1"}, token)
    check("a second post has nothing to write", (s, len(J["writes"])), (400, 1))
finally:
    srv.terminate()
    srv.wait(timeout=5)

print("\n" + ("ALL PASSED" if not fails else f"{fails} FAILED"))
sys.exit(1 if fails else 0)
