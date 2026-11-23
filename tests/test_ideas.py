#!/usr/bin/env python3
import os
import sys
import tempfile

os.environ["FLOW_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import ideas

fails = 0


def check(name, got, want=True):
    global fails
    ok = got == want
    fails += 0 if ok else 1
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))


src = {"session_id": "local_1", "title": "T", "cwd": "/x/r", "last": 1}
i1, c1 = ideas.add("  první nápad ", "kontext", src, dedupe=True)
check("added and trimmed", (c1, i1["text"], i1["status"]), (True, "první nápad", "open"))
i2, c2 = ideas.add("druhý", "", src, dedupe=True)
check("second idea from the same session is deduped", (c2, i2["id"]), (False, i1["id"]))
i3, c3 = ideas.add("druhý", "", src, dedupe=False)
check("manual add is not deduped", c3)
check("list", len(ideas.load()), 2)
check("update text", ideas.update(i1["id"], text="změna")["text"], "změna")
check("done", ideas.update(i1["id"], status="done")["status"], "done")
for bad in (lambda: ideas.add("   "), lambda: ideas.update(i1["id"], status="x"), lambda: ideas.update("nope", text="a"), lambda: ideas.delete("nope")):
    try:
        bad(); check("refused", False)
    except ValueError:
        check("refused", True)
ideas.delete(i1["id"])
check("deleted", [i["id"] for i in ideas.load()], [i3["id"]])
check("long text is cut", len(ideas.add("x" * 5000)[0]["text"]), ideas.MAX_TEXT)
print("ALL PASSED" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
