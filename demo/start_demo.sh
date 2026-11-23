#!/bin/bash
# Starts the demo: a fake Jira + a SEPARATE dashboard (own data folder, port 8799, launching on). Nothing real is touched.
# Usage: demo/start_demo.sh   (stop: demo/stop_demo.sh)
cd "$(dirname "$0")" || exit 1
D=/tmp/agf-demo; mkdir -p $D/flow; rm -rf $D/flow/*
echo '{"launch": {"enabled": true, "method": "app"}}' > $D/flow/config.json
/usr/bin/python3 seed_events.py $D/flow/events.jsonl
FLOW_HOME=$D/flow JIRA_BASE_URL=http://127.0.0.1:8798 JIRA_EMAIL=demo@example.test JIRA_API_TOKEN=demo FLOW_PORT=8799 \
  nohup /usr/bin/python3 ../src/dashboard.py --port 8799 > $D/dashboard.log 2>&1 &
echo $! > $D/dashboard.pid
nohup /usr/bin/python3 mock_jira.py 8798 > $D/jira.log 2>&1 &
echo $! > $D/jira.pid
sleep 2; echo "demo: http://127.0.0.1:8799/v2/"
