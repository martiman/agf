#!/usr/bin/env python3
import json
import os
import socket
import sys
import tempfile
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TMP = tempfile.mkdtemp()


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


OPTS = {"AgentWorking": "1", "WaitingForHuman": "2", "HumanWorking": "3", "Paused": "4"}
J = {"issues": {}, "writes": [], "put_status": 200, "fields": True, "reads": 0}


def reset():
    J["issues"] = {"APS-1": {"mode": None, "action": None, "type": "Story", "cat": "indeterminate"},
                   "APS-2": {"mode": None, "action": None, "type": "Story", "cat": "indeterminate"}}
    J["writes"].clear()
    J.update(put_status=200, fields=True, reads=0)


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
        if path == "/rest/api/3/field":
            if not J["fields"]:
                return self._send([{"id": "customfield_1", "name": "Something", "schema": {"type": "string"}}])
            return self._send([{"id": "customfield_11045", "name": "WorkMode", "schema": {"type": "option"}},
                               {"id": "customfield_11046", "name": "NextAction", "schema": {"type": "string"}}])
        if path.endswith("/issue/createmeta/APS/issuetypes"):
            return self._send({"issueTypes": [{"id": "10417", "name": "Story"}]})
        if path.endswith("/issuetypes/10417"):
            return self._send({"fields": [
                {"fieldId": "customfield_11045", "allowedValues": [{"value": k, "id": v} for k, v in OPTS.items()]},
                {"fieldId": "customfield_11046"}]})
        if path.startswith("/rest/api/3/issue/APS-"):
            J["reads"] += 1
            i = J["issues"][path.rsplit("/", 1)[1]]
            return self._send({"fields": {"customfield_11045": {"value": i["mode"]} if i["mode"] else None,
                                          "customfield_11046": i["action"], "updated": "x", "issuetype": {"name": i["type"]},
                                          "status": {"statusCategory": {"key": i["cat"]}}}})
        self._send({}, 404)

    def do_PUT(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        key = self.path.rsplit("/", 1)[1]
        if J["put_status"] != 200:
            return self._send({"errorMessages": ["no"]}, J["put_status"])
        J["writes"].append((key, body))
        f = body["fields"]
        m = f["customfield_11045"]
        J["issues"][key]["mode"] = next((k for k, v in OPTS.items() if v == m["id"]), None) if m else None
        J["issues"][key]["action"] = f["customfield_11046"]
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()


port = free_port()
srv = ThreadingHTTPServer(("127.0.0.1", port), Fake)
threading.Thread(target=srv.serve_forever, daemon=True).start()
os.environ.update(JIRA_BASE_URL=f"http://127.0.0.1:{port}", JIRA_EMAIL="t@example.test", JIRA_API_TOKEN="dummy",
                  FLOW_HOME=TMP, FLOW_WORKMODE_STATE=os.path.join(TMP, "wm.json"), FLOW_WORKMODE_LOG=os.path.join(TMP, "wm.log"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import jira
import workmode as w

fails = 0


def check(name, got, want=True):
    global fails
    ok = got == want
    fails += 0 if ok else 1
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))


def row(ticket, state, last_event, at, title="Zadání", notification=None):
    return {"ticket": ticket, "state": state, "last_event": last_event, "notification": notification, "title": title,
            "cwd": "/x", "last_ts": datetime.fromtimestamp(at, timezone.utc).isoformat()}


def enable(on=True):
    with open(os.path.join(TMP, "config.json"), "w") as f:
        json.dump({"workmode": {"enabled": on}}, f)


def fresh():
    reset()
    w._pending.clear(); w._writes.clear(); w._problems.clear(); w._notified.clear()
    for p in (w.STATE_FILE, w.LOG):
        if os.path.exists(p):
            os.remove(p)
    jira._wm.update(at=0.0, ids=None)
    jira._wm_opts.clear()


T0 = 1_800_000_000.0
enable()

fresh()
rows = [row("APS-1", "running", "UserPromptSubmit", T0)]
check("start: first pass only remembers (debounce, no write)", (w.tick(rows, now=T0 + 5), J["writes"]), ([], []))
r = w.tick(rows, now=T0 + 70)
check("start: written after the debounce", [x["result"] for x in r], ["zapsáno"])
check("start: ONE request carries BOTH fields with the real ids and the real option id",
      J["writes"], [("APS-1", {"fields": {"customfield_11045": {"id": "1"}, "customfield_11046": "Agent: pracuje v session „Zadání“."}})])
check("start: mode and action are in Jira now", (J["issues"]["APS-1"]["mode"], J["issues"]["APS-1"]["action"].startswith("Agent:")), ("AgentWorking", True))
w.tick(rows, now=T0 + 140)
check("a repeated pass writes nothing (no change)", len(J["writes"]), 1)

rows = [row("APS-1", "waiting", "Notification", T0 + 200, notification="idle_prompt")]
w.tick(rows, now=T0 + 205)
w.tick(rows, now=T0 + 270)
check("question: WaitingForHuman with the concrete action", (J["issues"]["APS-1"]["mode"], J["issues"]["APS-1"]["action"]),
      ("WaitingForHuman", "Developer: odpovědět agentovi v session „Zadání“."))
check("question: still one write per change", len(J["writes"]), 2)
rows = [row("APS-1", "waiting", "Notification", T0 + 300, notification="permission_prompt")]
w.tick(rows, now=T0 + 305); w.tick(rows, now=T0 + 370)
check("same mode, action already there: nothing rewritten", len(J["writes"]), 2)

rows = [row("APS-1", "idle", "SessionStart", T0 + 400)]
w.tick(rows, now=T0 + 405); w.tick(rows, now=T0 + 470)
check("a just-opened session says nothing: no write", len(J["writes"]), 2)

rows = [row("APS-2", "idle", "Stop", T0 + 500, title="Hotovo")]
w.tick(rows, now=T0 + 505); w.tick(rows, now=T0 + 570)
check("review: finished run -> WaitingForHuman, check the result",
      (J["issues"]["APS-2"]["mode"], "zkontrolovat výsledek" in J["issues"]["APS-2"]["action"]), ("WaitingForHuman", True))
fresh(); J["issues"]["APS-2"]["mode"] = None
rows = [row("APS-2", "idle", "Stop", T0 - 3 * 3600)]
w.tick(rows, now=T0); w.tick(rows, now=T0 + 70)
check("a finished run older than 2 h is not announced", J["writes"], [])

fresh(); J["issues"]["APS-1"].update(mode="Paused", action="Developer: čeká na PO.")
rows = [row("APS-1", "running", "UserPromptSubmit", T0 - 100)]
w.tick(rows, now=T0); w.tick(rows, now=T0 + 70)
check("Paused set by a human is not overwritten by an older prompt", (J["writes"], J["issues"]["APS-1"]["mode"]), ([], "Paused"))
rows = [row("APS-1", "waiting", "Notification", T0 + 200)]
w.tick(rows, now=T0 + 205); w.tick(rows, now=T0 + 270)
check("Paused is not overwritten by a waiting session either", J["writes"], [])
rows = [row("APS-1", "running", "UserPromptSubmit", T0 + 300)]
w.tick(rows, now=T0 + 305); w.tick(rows, now=T0 + 370)
check("a prompt submitted AFTER the human value = a real resume: AgentWorking", J["issues"]["APS-1"]["mode"], "AgentWorking")
fresh(); J["issues"]["APS-1"].update(mode="HumanWorking", action="Developer: implementuje.")
rows = [row("APS-1", "idle", "Stop", T0)]
w.tick(rows, now=T0 + 1); w.tick(rows, now=T0 + 70)
check("HumanWorking is not replaced by 'check the result'", (J["writes"], J["issues"]["APS-1"]["mode"]), ([], "HumanWorking"))

check("the code can only target AgentWorking or WaitingForHuman",
      {w.target([row("K", s, e, T0, notification=n)], T0 + 1)[0] for s, e, n in
       [("running", "UserPromptSubmit", None), ("waiting", "Notification", "idle_prompt"), ("waiting", "Notification", "permission_prompt"),
        ("idle", "Stop", None)]}, {"AgentWorking", "WaitingForHuman"})
check("closed / suspect / unknown sessions say nothing",
      [w.target([row("K", s, "SessionEnd", T0)], T0 + 1) for s in ("closed", "suspect", "unknown")], [None, None, None])

fresh(); J["issues"]["APS-1"].update(mode="WaitingForHuman", action="Reviewer: zkontrolovat PR.", cat="done")
tickets = {"APS-1": {"category": "done", "workmode": {"mode": "WaitingForHuman", "action": "x"}, "type": "Story"}}
rows = [row("APS-1", "idle", "SessionEnd", T0)]
w.tick(rows, tickets, now=T0)
check("Done: both fields cleared in one request", (J["writes"], J["issues"]["APS-1"]["mode"]),
      ([("APS-1", {"fields": {"customfield_11045": None, "customfield_11046": None}})], None))

fresh(); J["put_status"] = 403
rows = [row("APS-1", "running", "UserPromptSubmit", T0)]
w.tick(rows, now=T0 + 1); r = w.tick(rows, now=T0 + 70)
check("refused write: reported as an error", [x["result"] for x in r], ["chyba"])
check("refused write: visible in public()", "APS-1" in w.public()["problems"], True)
before = J["reads"]
J["put_status"] = 200
for k in range(5):
    w.tick(rows, now=T0 + 100 + k * 100)
check("refused write: NOT retried (hold), Jira not even read", (J["writes"], J["reads"]), ([], before))
rec = [json.loads(x) for x in open(w.LOG)]
check("refused write: in the audit log", (rec[-1]["result"], rec[-1]["key"]), ("chyba", "APS-1"))
w.tick(rows, now=T0 + 100 + w.HOLD + 100); w.tick(rows, now=T0 + 100 + w.HOLD + 200)
check("after the hold the ticket is tried again", len(J["writes"]), 1)

fresh(); J["fields"] = False
r = w.tick(rows, now=T0 + 1); r = w.tick(rows, now=T0 + 70)
check("fields missing: no write, message names them", (J["writes"], "WorkMode" in w.public()["problems"].get("*", "")), ([], True))

fresh(); enable(False)
w.tick([row("APS-1", "running", "UserPromptSubmit", T0)], now=T0 + 1); w.tick([row("APS-1", "running", "UserPromptSubmit", T0)], now=T0 + 70)
check("switched off: no Jira call at all", (J["writes"], J["reads"]), ([], 0))
enable(True); fresh()
w.tick([row(None, "running", "UserPromptSubmit", T0)], now=T0 + 1); w.tick([row(None, "running", "UserPromptSubmit", T0)], now=T0 + 70)
check("session without a ticket: nothing touched", J["writes"], [])
rows = [row("APS-1", "running", "UserPromptSubmit", T0)]
w.tick(rows, now=T0 + 1); w.tick(rows, now=T0 + 70)
check("only the ticket of the session is touched", [k for k, _ in J["writes"]], ["APS-1"])

fresh()
rows = [row("APS-1", "running", "UserPromptSubmit", T0)]
w.tick(rows, now=T0 + 1, dry=True); r = w.tick(rows, now=T0 + 70, dry=True)
check("dry run: plan without a write", ([x["result"] for x in r], J["writes"]), (["plán"], []))

fresh(); w.RATE = (1, 600)
J["issues"]["APS-3"] = {"mode": None, "action": None, "type": "Story", "cat": "indeterminate"}
rows = [row("APS-1", "running", "UserPromptSubmit", T0), row("APS-3", "running", "UserPromptSubmit", T0)]
w.tick(rows, now=T0 + 1); w.tick(rows, now=T0 + 70)
check("rate limit: only one write goes through", len(J["writes"]), 1)
w.RATE = (30, 600)

check("the action text is capped", len(w._clip("x" * 400)), w.ACTION_MAX)

srv.shutdown()
print("\n" + ("ALL PASSED" if not fails else f"{fails} FAILED"))
sys.exit(1 if fails else 0)
