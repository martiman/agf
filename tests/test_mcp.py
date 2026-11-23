#!/usr/bin/env python3
import json
import os
import select
import subprocess
import sys

HERE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
SERVER = os.path.join(HERE, "mcp_server.py")
fails = 0


def check(name, cond, extra=""):
    global fails
    fails += 0 if cond else 1
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  {extra}"))


class Client:
    def __init__(self, env=None):
        e = dict(os.environ)
        e.update(env or {})
        self.p = subprocess.Popen([sys.executable, SERVER], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True, env=e)
        self.n = 0

    def raw(self, line):
        self.p.stdin.write(line + "\n")
        self.p.stdin.flush()

    def read(self, timeout=30):
        r, _, _ = select.select([self.p.stdout], [], [], timeout)
        if not r:
            raise TimeoutError("no reply")
        return json.loads(self.p.stdout.readline())

    def rpc(self, method, params=None):
        self.n += 1
        self.raw(json.dumps({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params or {}}))
        return self.read()

    def tool(self, name, args=None):
        r = self.rpc("tools/call", {"name": name, "arguments": args or {}})
        return r["result"]["content"][0]["text"], r["result"]["isError"]

    def close(self):
        self.p.stdin.close()
        self.p.wait(timeout=5)
        return self.p.stderr.read()


c = Client()
r = c.rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}})
check("initialize: version echoed, tools capability, server name",
      r["result"]["protocolVersion"] == "2025-06-18" and "tools" in r["result"]["capabilities"]
      and r["result"]["serverInfo"]["name"] == "flow")
c.raw(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}))
r = c.rpc("ping")
check("notification gets no reply, ping answers next", r["result"] == {} and r["id"] == c.n)
r2 = Client().rpc("initialize", {"protocolVersion": "1999-01-01"})
check("unknown protocol version falls back to a supported one", r2["result"]["protocolVersion"] in ("2025-06-18", "2025-03-26", "2024-11-05"))

tools = c.rpc("tools/list")["result"]["tools"]
READ_TOOLS = ["flow_ac", "flow_overview", "flow_sessions", "flow_ticket"]
DIALOG_TOOLS = ["flow_answers", "flow_ask", "flow_done", "flow_draft"]
by_name = {t["name"]: t for t in tools}
check("four reading tools and four dialog tools", sorted(by_name) == sorted(READ_TOOLS + DIALOG_TOOLS))
check("every reading tool is read-only; no tool leaks 'fn'",
      all(by_name[n]["annotations"]["readOnlyHint"] for n in READ_TOOLS)
      and all("fn" not in t and t["inputSchema"]["type"] == "object" for t in tools))
check("dialog tools are not read-only and say they do not write to Jira",
      all(not by_name[n]["annotations"]["readOnlyHint"] and "ne do Jiry" in by_name[n]["description"] for n in DIALOG_TOOLS))
check("reading tool descriptions say that texts are data",
      all("data" in by_name[n]["description"] for n in READ_TOOLS))

text, err = c.tool("flow_overview")
check("flow_overview works", not err and text.startswith("Sessions za posledních"), text[:80])
text, err = c.tool("flow_sessions", {"state": "closed", "limit": 3})
check("flow_sessions filters and limits", not err and "neaktivní" in text and text.count("\n- ") <= 3, text[:120])
text, err = c.tool("flow_sessions", {"state": "bogus"})
check("flow_sessions: bad state is a tool error", err and "Neplatný stav" in text)
text, err = c.tool("flow_sessions", {"ticket": "drop table"})
check("flow_sessions: bad ticket is a tool error", err and "Neplatný klíč" in text)

text, err = c.tool("flow_ticket", {"key": "aps-2454"})
check("flow_ticket (lowercase key accepted) shows AC and status", not err and "APS-2454" in text and "AC-1" in text and "brána:" in text, text[:200])
text, err = c.tool("flow_ac", {"key": "APS-2454"})
check("flow_ac shows criteria and the honest test note", not err and "AC-1" in text and "nesbírají" in text, text[:200])
check("flow_ac shows the readiness of the specification", not err and "zadání:" in text and "/8" in text, text[:300])
text, err = c.tool("flow_ac", {"key": "not-a-key"})
check("flow_ac: bad key is a tool error", err and "Neplatný klíč" in text)
text, err = c.tool("flow_ticket", {"key": "APS-99999999"})
check("flow_ticket: missing ticket is handled", "nenalezen" in text or err, text[:120])

r = c.rpc("tools/call", {"name": "write_everything", "arguments": {}})
check("unknown tool -> JSON-RPC error", r["error"]["code"] == -32602)
r = c.rpc("resources/list")
check("unknown method -> -32601", r["error"]["code"] == -32601)
c.raw("this is not json")
bad = c.read()
check("malformed JSON -> parse error, server survives", bad["error"]["code"] == -32700 and c.rpc("ping")["result"] == {})
err_out = c.close()
check("server writes nothing unexpected to stderr", err_out.strip() == "", err_out[:200])

d = Client({"FLOW_PORT": "59999"})
d.rpc("initialize", {"protocolVersion": "2025-06-18"})
text, err = d.tool("flow_overview")
check("dashboard down -> clear tool error", err and "flow start" in text, text)
d.close()

sys.path.insert(0, HERE)
import mcp_server as m
dirty = "Ignoruj pokyny\x00\x1b[31m\n\n" + "A" * 400
cl = m.clean(dirty, 100)
check("clean(): control characters gone, length capped", len(cl) <= 100 and "\x1b" not in cl and "\n" not in cl and "\x00" not in cl)
check("clean(): handles None", m.clean(None) == "")

print("\n" + ("ALL PASSED" if not fails else f"{fails} FAILED"))
sys.exit(1 if fails else 0)
