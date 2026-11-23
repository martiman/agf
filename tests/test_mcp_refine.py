#!/usr/bin/env python3
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
TMP = tempfile.mkdtemp(prefix="flow-mcp-refine-")
env = dict(os.environ, FLOW_REFINE_DIR=TMP)
sys.path.insert(0, HERE)
os.environ["FLOW_REFINE_DIR"] = TMP
import refine

p = subprocess.Popen(["/usr/bin/python3", os.path.join(HERE, "mcp_server.py")], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE, text=True, env=env)
fails, nid = 0, 0


def rpc(method, params=None):
    global nid
    nid += 1
    p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": nid, "method": method, "params": params or {}}) + "\n")
    p.stdin.flush()
    return json.loads(p.stdout.readline())["result"]


def call(name, args):
    res = rpc("tools/call", {"name": name, "arguments": args})
    return res["content"][0]["text"], res["isError"]


def check(name, cond, extra=""):
    global fails
    fails += 0 if cond else 1
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else "  " + str(extra)[:300]))


try:
    init = rpc("initialize", {"protocolVersion": "2025-06-18"})
    check("instructions mention the mailbox", "schránky" in init["instructions"])
    tools = {t["name"]: t for t in rpc("tools/list")["tools"]}
    check("8 tools: 4 reading + 4 dialog", len(tools) == 8 and all(n in tools for n in ("flow_ask", "flow_answers", "flow_draft", "flow_done")), list(tools))
    check("dialog tools are not read-only, reading tools are", not tools["flow_ask"]["annotations"]["readOnlyHint"] and tools["flow_ac"]["annotations"]["readOnlyHint"])
    check("dialog tool descriptions say: not Jira", all("ne do Jiry" in tools[n]["description"] for n in ("flow_ask", "flow_answers", "flow_draft", "flow_done")))

    txt, err = call("flow_ask", {"key": "APS-9100", "questions": [
        {"text": "Z objemu, nebo z počtu?", "why": "Limit.vue:40", "options": [{"label": "z objemu", "recommended": True}, {"label": "z počtu"}]},
        {"text": "I v mobilní aplikaci?"}]})
    check("flow_ask publishes and tells the agent to stop", not err and "SKONČETE TAH" in txt and "Q1, Q2" in txt, txt)
    txt, err = call("flow_ask", {"key": "aps-1", "questions": [{"text": "x"}]})
    check("bad key is an error the agent sees", err and "Neplatný klíč" in txt, txt)
    txt, err = call("flow_ask", {"key": "APS-9100", "questions": []})
    check("empty questions are an error", err)

    txt, err = call("flow_answers", {"key": "APS-9100"})
    check("no answers yet", not err and "Žádné nové odpovědi" in txt and "neodpověděl na 2" in txt, txt)
    refine.answer("APS-9100", {"Q1": {"choice": "z objemu"}, "Q2": {"defer": True}})
    txt, err = call("flow_answers", {"key": "APS-9100"})
    check("answers are returned with the defer note", "z objemu" in txt and "ODLOŽENO" in txt and "flow_draft" in txt, txt)
    txt, _ = call("flow_answers", {"key": "APS-9100"})
    check("answers are returned only once", "Žádné nové odpovědi" in txt, txt)

    txt, err = call("flow_draft", {"key": "APS-9100", "problem": "P", "where": "W", "expected": "E",
                                   "ac": [{"text": "Limit 10 000: 8 000 = ok, 12 000 = přes.", "from": "Q1"}, {"text": "Mobil jen zobrazuje."}],
                                   "decisions": [{"q": "Q1", "choice": "z objemu"}], "unresolved": ["Mobil: odloženo"]})
    check("flow_draft stores v1 and forbids writing to Jira yet", not err and "v1" in txt and "NEZAPISUJTE" in txt, txt)
    txt, err = call("flow_done", {"key": "APS-9100"})
    check("flow_done refused before approval", err and "schválený" in txt, txt)
    refine.edit_ac("APS-9100", {"2": "Mobil jen zobrazuje, nepočítá."}); refine.approve("APS-9100")
    txt, err = call("flow_answers", {"key": "APS-9100"})
    check("after approval the agent gets the approved draft incl. the human's edit",
          "SCHVÁLENÝ NÁVRH" in txt and "nepočítá" in txt and "upraveno uživatelem" in txt and "flow_done" in txt, txt)
    txt, err = call("flow_done", {"key": "APS-9100", "note": "pole AC + komentář D-1"})
    check("flow_done after approval", not err and "zapsaný" in txt, txt)
    txt, _ = call("flow_answers", {"key": "APS-9100"})
    check("written state is reported", "zapsaný do Jiry" in txt, txt)
    check("no stderr noise", p.poll() is None)
finally:
    p.stdin.close(); p.terminate()
    shutil.rmtree(TMP, ignore_errors=True)

print("\n" + ("ALL PASSED" if not fails else f"{fails} FAILED"))
sys.exit(1 if fails else 0)
