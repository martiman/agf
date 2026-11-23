#!/usr/bin/env python3
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
ROOT = os.path.dirname(HERE)
fails = 0


def check(name, got, want=True):
    global fails
    ok = got == want
    fails += 0 if ok else 1
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))


own = []
for d, _, files in os.walk(os.path.join(ROOT, "web", "v2")):
    own += [os.path.join(d, f) for f in files if f.endswith((".js", ".html", ".css"))]
check("the page has source files", len(own) >= 8)
check("no v-html anywhere in our code (untrusted Jira and agent text must stay escaped)", [p for p in own if "v-html" in open(p).read() or "innerHTML" in open(p).read()], [])
check("no eval / Function() in our code", [p for p in own if re.search(r"\beval\(|new Function\(", open(p).read())], [])
ext = [(os.path.basename(p), m) for p in own for m in re.findall(r"https?://[^\s\"'`)]+", open(p).read()) if not m.startswith(("http://127.0.0.1", "http://localhost"))]
check("our code loads nothing from the internet", ext, [])
idx = open(os.path.join(ROOT, "web", "v2", "index.html")).read()
srcs = re.findall(r'(?:src|href)="([^"]+)"', idx)
check("index.html refers only to local files", [s for s in srcs if not s.startswith("/")], [])
check("every file it refers to exists", [s for s in srcs if not os.path.isfile(os.path.join(ROOT, "web", s.lstrip("/")))], [])
check("the vendored Vue and Ant Design are there", all(os.path.getsize(os.path.join(ROOT, "web", "vendor", f)) > 100000 for f in ("vue.global.prod.js", "antd.min.js")))

with socket.socket() as s:
    s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
env = dict(os.environ, FLOW_HOME=tempfile.mkdtemp(), JIRA_EMAIL="", JIRA_API_TOKEN="")
srv = subprocess.Popen([sys.executable, os.path.join(ROOT, "src", "dashboard.py"), "--port", str(port)], env=env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=os.path.join(ROOT, "src"))
base = f"http://127.0.0.1:{port}"
for _ in range(50):
    try:
        urllib.request.urlopen(base + "/api/state?hours=1", timeout=1); break
    except Exception:
        time.sleep(0.2)


def get(path):
    import http.client
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    c.request("GET", path)
    r = c.getresponse(); body = r.read()
    return r.status, r.getheader("Content-Security-Policy") or "", body


try:
    st, csp, body = get("/v2/")
    check("the page is served with a real token (not the placeholder)", (st, b"__LAUNCH_TOKEN__" in body, b'name="flow-token" content="' in body), (200, False, True))
    check("only the v2 page may use 'unsafe-eval'", "'unsafe-eval'" in csp and  "'unsafe-eval'" not in get("/api/state?hours=1")[1], True)
    for p in ("/v2/../src/dashboard.py", "/vendor/../dashboard.html", "/v2/%2e%2e/src/dashboard.py", "/v2/app/", "/v2/app/missing.js", "/vendor/", "/v2/app/../../src/hook.py"):
        check("static route refuses " + p, get(p)[0], 404)
    check("a vendored file is served", get("/vendor/vue.global.prod.js")[0], 200)
    st, _, _ = get("/")
    import http.client
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5); c.request("GET", "/"); r = c.getresponse(); r.read()
    check("/ redirects to the new page", (r.status, r.getheader("Location")), (302, "/v2/"))
    check("the old page and its script are gone", (get("/legacy")[0], get("/refine.js")[0]), (404, 404))
    check("the old page files are deleted", [f for f in ("dashboard.html", "refine.js") if os.path.exists(os.path.join(ROOT, "web", f))], [])
finally:
    srv.terminate(); srv.wait(timeout=5)

print("\n" + ("ALL PASSED" if not fails else f"{fails} FAILED"))
sys.exit(1 if fails else 0)
