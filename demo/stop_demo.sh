#!/bin/bash
for port in 8799 8798; do
  for pid in $(lsof -nP -iTCP:$port -sTCP:LISTEN -t 2>/dev/null); do kill "$pid" 2>/dev/null; done
done
rm -f /tmp/agf-demo/dashboard.pid /tmp/agf-demo/jira.pid
echo stopped
