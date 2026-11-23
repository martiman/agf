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

HERE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
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


DESC = {"type": "doc", "version": 1, "content": [
    head("Problém"), para("Limit řidiče se vyhodnocuje jinak než v Dispečeru a řidič vidí jiné číslo."),
    head("Kde to je"), para("src/pages/DriverPage.vue:42 počítá limit z objemu."), head("Očekávané chování"), para("Limit se počítá jako v Dispečeru."),
    {"type": "bulletList", "content": [
        {"type": "listItem", "content": [para("AC-1: Když je objem 8 000 a limit 10 000, pak se zobrazí ok; při 12 000 se zobrazí upozornění.")]},
        {"type": "listItem", "content": [para("AC-2: Pokud řidič nemá oprávnění, nezobrazí se tlačítko Uložit.")]}]}]}

JIRA = {"status": "TO DO", "writes": [], "updated": "2026-11-18T10:00:00.000+0100", "labels": []}


class FakeJira(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj, code=200):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _issue_fields(self):
        cat = {"TO DO": "new", "REFINED": "new"}.get(JIRA["status"], "indeterminate")
        return {"summary": "Limit řidiče", "status": {"name": JIRA["status"], "statusCategory": {"key": cat}},
                "issuetype": {"name": "Story"}, "assignee": {"displayName": "Tester"}, "updated": JIRA["updated"],
                "parent": None, "labels": JIRA["labels"]}

    def do_GET(self):
        path = self.path.split("?")[0]
        if path.endswith("/search/jql"):
            return self._send({"issues": [{"key": "APS-1", "fields": self._issue_fields()}], "isLast": True})
        if path == "/rest/api/3/issue/APS-1":
            return self._send({"fields": {"description": DESC, "customfield_10606": None}, "changelog": {"histories": [], "total": 0}})
        if path.endswith("/transitions"):
            return self._send({"transitions": [{"id": "11", "name": "To Do", "to": {"name": "TO DO"}},
                                               {"id": "81", "name": "Schválit AC", "to": {"name": "REFINED"}}]})
        if path.endswith("/statuses"):
            return self._send([{"statuses": [{"name": "TO DO"}, {"name": "REFINED"}, {"name": "In Progress"}]}])
        if path.endswith("/myself"):
            return self._send({"displayName": "Tester"})
        self._send({}, 404)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        path = self.path.split("?")[0]
        JIRA["writes"].append((path, body))
        if path.endswith("/transitions"):
            JIRA["status"] = "REFINED"
            JIRA["updated"] = "2026-11-18T12:00:00.000+0100"
            return self._send({}, 204)
        if path.endswith("/comment"):
            return self._send({"id": "1"}, 201)
        self._send({}, 404)


jp = free_port()
fake = ThreadingHTTPServer(("127.0.0.1", jp), FakeJira)
threading.Thread(target=fake.serve_forever, daemon=True).start()

dp = free_port()
log = os.path.join(tempfile.mkdtemp(), "approve.log")
env = dict(os.environ, JIRA_BASE_URL=f"http://127.0.0.1:{jp}", JIRA_EMAIL="t@example.test", JIRA_API_TOKEN="dummy",
           FLOW_APPROVE_LOG=log, FLOW_PORT=str(dp))
srv = subprocess.Popen([sys.executable, os.path.join(HERE, "dashboard.py"), "--port", str(dp)], env=env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, cwd=HERE)
base = f"http://127.0.0.1:{dp}"
for _ in range(50):
    try:
        urllib.request.urlopen(base + "/api/state?hours=1", timeout=1)
        break
    except Exception:
        time.sleep(0.2)


def post(body, token, origin=True):
    h = {"Content-Type": "application/json"}
    if origin:
        h["Origin"] = base
    if token:
        h["X-Flow-Launch"] = token
    req = urllib.request.Request(base + "/api/approve", data=json.dumps(body).encode(), headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


try:
    page = urllib.request.urlopen(base + "/v2/", timeout=5).read().decode()
    token = re.search(r'name="flow-token" content="([^"]+)"', page).group(1)
    state = json.load(urllib.request.urlopen(base + "/api/state?hours=1", timeout=20))
    check("/api/state exposes the approval switch", state["approve"], {"enabled": True, "refined_exists": True})

    check("no Origin: refused", post({"key": "APS-1", "dry": True}, token, origin=False)[0], 403)
    check("no token: refused", post({"key": "APS-1", "dry": True}, None)[0], 403)
    check("wrong token: refused", post({"key": "APS-1", "dry": True}, "x" * 20)[0], 403)
    check("nothing was written by refused calls", JIRA["writes"], [])

    st, res = post({"key": "APS-1", "dry": True}, token)
    plan = res.get("plan", {})
    check("the plan comes from the FAKE Jira (its ticket, not a real one)", (plan.get("summary"), plan.get("assignee")), ("Limit řidiče", "Tester"))
    check("dry run: 200 with the plan, nothing written", (st, plan.get("transition", {}).get("to"), len(plan.get("criteria", [])), JIRA["writes"]), (200, "REFINED", 2, []))

    check("execute without confirm: refused, nothing written", (post({"key": "APS-1", "fingerprint": plan["fingerprint"]}, token)[0], JIRA["writes"]), (400, []))
    check("execute with a stale fingerprint: refused, nothing written", (post({"key": "APS-1", "fingerprint": "0" * 16, "confirm": True}, token)[0], JIRA["writes"]), (409, []))

    st, res = post({"key": "APS-1", "fingerprint": plan["fingerprint"], "confirm": True}, token)
    check("execute: 200, ticket is now REFINED", (st, res.get("ok"), res.get("to")), (200, True, "REFINED"))
    check("Jira received exactly one write: the transition with the right id",
          JIRA["writes"], [("/rest/api/3/issue/APS-1/transitions", {"transition": {"id": "81"}})])
    st, res = post({"key": "APS-1", "dry": True}, token)
    check("a repeat is refused: already approved (409)", (st, "už jsou schválená" in res.get("error", "")), (409, True))
    check("Jira received nothing more", len(JIRA["writes"]), 1)
    rec = [json.loads(x) for x in open(log)]
    check("the approval is in the audit log", (rec[-1]["result"], rec[-1]["key"], rec[-1]["to"]), ("ok", "APS-1", "REFINED"))
finally:
    srv.terminate()
    srv.wait(timeout=5)
    fake.shutdown()

print("\n" + ("ALL PASSED" if not fails else f"{fails} FAILED"))
sys.exit(1 if fails else 0)
