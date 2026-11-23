#!/usr/bin/env python3
import glob
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
fails = []


def load(lang):
    d = {}
    for f in glob.glob(os.path.join(ROOT, "web/v2/app/i18n", lang, "*.js")):
        src = open(f, encoding="utf-8").read()
        for m in re.finditer(r'^\s*"([^"]+)":\s*(.+?),?\s*$', src, re.M):
            d[m.group(1)] = m.group(2)
    return d


cs, en = load("cs"), load("en")
used = {}
for f in glob.glob(os.path.join(ROOT, "src/*.py")):
    if f.endswith("msg.py"):
        continue
    for m in re.finditer(r'\bk\(\s*"([\w.\-]+)"([^)]*)\)', open(f, encoding="utf-8").read()):
        used.setdefault(m.group(1), set()).update(re.findall(r"(\w+)\s*=", m.group(2)))
for key, params in sorted(used.items()):
    if key not in cs:
        fails.append("missing in cs: " + key)
    if key not in en:
        fails.append("missing in en: " + key)
    for lang, d in (("cs", cs), ("en", en)):
        if key in d:
            have = set(re.findall(r"\{(\w+)\}", d[key]))
            if have != params and not d[key].lstrip().startswith("{"):
                fails.append(f"{lang}: {key} uses {sorted(have)} but the server sends {sorted(params)}")
for f in fails:
    print("FAIL", f)
print(f"{len(used)} server keys checked")
print("ALL PASSED" if not fails else f"{len(fails)} FAILED")
sys.exit(1 if fails else 0)
