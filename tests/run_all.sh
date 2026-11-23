#!/bin/bash
# Run every test suite of agenticflow (no network, the e2e test uses a mock Jira). Exit 1 if any fails.
cd "$(dirname "$0")" || exit 1
rc=0
for t in test_*.py; do
  printf '%-24s' "$t"
  out="$(/usr/bin/python3 "$t" 2>&1)"; code=$?
  if [ $code -eq 0 ]; then echo "ok  ($(echo "$out" | tail -1))"; else echo "FAIL"; echo "$out" | tail -15; rc=1; fi
done
if command -v node >/dev/null 2>&1; then
  for t in test_*.mjs; do
    printf '%-24s' "$t"
    out="$(node "$t" 2>&1)"; code=$?
    if [ $code -eq 0 ]; then echo "ok  ($(echo "$out" | tail -1))"; else echo "FAIL"; echo "$out" | tail -15; rc=1; fi
  done
else
  echo "(node not found: the .mjs tests were skipped)"
fi
exit $rc
