#!/usr/bin/env python3
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))
os.environ["FLOW_HOME"] = tempfile.mkdtemp(prefix="flow-title-")
import dashboard as d

fails = 0


def check(name, got, want=True):
    global fails
    ok = got == want
    fails += 0 if ok else 1
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))


check("every action has a title label", sorted(d.TITLE_LABEL), sorted(d.ACTIONS))
check("title without repo", d.session_title("ticket-refine", "APS-2616", ""), "APS-2616 · refine")
check("title with repo", d.session_title("deliver", "APS-2616", "tris"), "APS-2616 · deliver · tris")
for a in d.ACTIONS:
    for w in ("", "tris"):
        if not d.WORKSPACE or not os.path.isdir(os.path.join(d.WORKSPACE, w)):
            continue
        folder, prompt = d.build_launch(a, "APS-1", w)
        t = d.session_title(a, "APS-1", w)
        check(f"{a}/{w or '-'}: prompt starts with the title, never with '/'", prompt.startswith(t + "\n") and not prompt.startswith("/"))
        check(f"{a}/{w or '-'}: prompt asks to set the same title", f"„{t}“" in prompt)
print("\n" + ("ALL PASSED" if not fails else f"{fails} FAILED"))
sys.exit(1 if fails else 0)
