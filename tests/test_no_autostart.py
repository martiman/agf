#!/usr/bin/env python3
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), "src")
fails = 0


def check(name, got, want=True):
    global fails
    ok = got == want
    fails += 0 if ok else 1
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))


def src(name):
    with open(os.path.join(SRC, name)) as f:
        return f.read()


dash = src("dashboard.py")
check("open_session is called exactly once, inside the /api/launch handler",
      [m.start() for m in re.finditer(r"\bopen_session\(", dash)].__len__(), 2)
call = dash.index("res = open_session(")
check("that call sits in Handler._launch", dash.rfind("def _launch", 0, call) > dash.rfind("def ", 0, dash.rfind("def _launch", 0, call)) - 1 and
      dash.rfind("def _launch", 0, call) > dash.rfind("\n    def ", 0, dash.rfind("def _launch", 0, call)) - 1)
for name in ("workmode.py", "refine.py", "approve.py", "status.py", "jira.py", "mcp_server.py", "mcp_refine.py", "ac.py", "spec.py"):
    t = src(name)
    check(f"{name} cannot start processes", not re.search(r"\b(subprocess|os\.system|os\.exec|os\.spawn|Popen)\b", t))
    check(f"{name} knows nothing about the launch endpoint" + ("" if name == "status.py" else " or claude:// links"),
          "open_session" not in t and (name == "status.py" or "claude://" not in t))
check("the POST /launch route is the only caller of _launch", len(re.findall(r"self\._launch\(\)", dash)), 1)
v2 = os.path.join(os.path.dirname(HERE), "web", "v2", "app")
callers = sorted(os.path.relpath(os.path.join(d, f), v2) for d, _, fs in os.walk(v2) for f in fs if f.endswith(".js") and "launchApi(" in open(os.path.join(d, f)).read())
check("the page calls the launch API only from the launch dialog (only components/LaunchModal.js calls it)", callers, ["components/LaunchModal.js"])
check("that dialog really starts a session only in its click handler (go), the dry run is only a preview",
      open(os.path.join(v2, "components", "LaunchModal.js")).read().count("launchApi(") == 2 and "launchApi(props.act, false, method, where.value)" in open(os.path.join(v2, "components", "LaunchModal.js")).read())

home = tempfile.mkdtemp()
with socket.socket() as s:
    s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
env = dict(os.environ, FLOW_HOME=home, JIRA_EMAIL="", JIRA_API_TOKEN="")
srv = subprocess.Popen([sys.executable, os.path.join(SRC, "dashboard.py"), "--port", str(port)], env=env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=SRC)
base = f"http://127.0.0.1:{port}"
for _ in range(50):
    try:
        urllib.request.urlopen(base + "/api/state?hours=1", timeout=1); break
    except Exception:
        time.sleep(0.2)


def post(headers, body):
    req = urllib.request.Request(base + "/api/launch", data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


try:
    page = urllib.request.urlopen(base + "/v2/", timeout=5).read().decode()
    token = re.search(r'name="flow-token" content="([^"]+)"', page).group(1)
    body = {"action": "deliver", "key": "APS-1", "where": ""}
    J = {"Content-Type": "application/json"}
    check("no Origin: refused", post(J, body)[0], 403)
    check("foreign Origin: refused", post(dict(J, Origin="http://evil.test", **{"X-Flow-Launch": token}), body)[0], 403)
    check("right page, but launching is OFF (default): refused", post(dict(J, Origin=base, **{"X-Flow-Launch": token}), body)[0], 403)
    check("a GET never launches", urllib.request.urlopen(base + "/api/workmode", timeout=10).status, 200)
    check("nothing was written to the launch log", os.path.exists(os.path.join(home, "launch.log")), False)
finally:
    srv.terminate(); srv.wait(timeout=5)

print("\n" + ("ALL PASSED" if not fails else f"{fails} FAILED"))
sys.exit(1 if fails else 0)
