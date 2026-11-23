#!/usr/bin/env python3
import json
import os
import sys
from datetime import datetime, timedelta

now = datetime.now().astimezone()


def ev(mins_ago, event, sid, branch, cwd, **kw):
    return dict({"ts": (now - timedelta(minutes=mins_ago)).strftime("%Y-%m-%dT%H:%M:%S%z"), "event": event, "session_id": sid, "cwd": cwd,
                 "branch": branch, "permission_mode": "default"}, **kw)


TRIS, API = "/Users/demo/trafinoil/tris", "/Users/demo/trafinoil/aps_team_git"
rows = [
    ev(30, "SessionStart", "00000000-0000-4000-8000-000000000001", "feature/APS-9005-paging", API, source="startup"),
    ev(29, "UserPromptSubmit", "00000000-0000-4000-8000-000000000001", "feature/APS-9005-paging", API),
    ev(4, "UserPromptSubmit", "00000000-0000-4000-8000-000000000001", "feature/APS-9005-paging", API),
    ev(50, "SessionStart", "00000000-0000-4000-8000-000000000002", "feature/APS-9004-route-filter", TRIS, source="startup"),
    ev(49, "UserPromptSubmit", "00000000-0000-4000-8000-000000000002", "feature/APS-9004-route-filter", TRIS),
    ev(12, "Notification", "00000000-0000-4000-8000-000000000002", "feature/APS-9004-route-filter", TRIS, notification_type="permission_prompt", message="Claude needs your permission"),
    ev(120, "SessionStart", "00000000-0000-4000-8000-000000000003", "dev", TRIS, source="startup"),
    ev(119, "UserPromptSubmit", "00000000-0000-4000-8000-000000000003", "dev", TRIS),
    ev(90, "Stop", "00000000-0000-4000-8000-000000000003", "dev", TRIS),
]
if os.environ.get("DEMO_LANG") == "en":
    rows += [
        ev(25, "SessionStart", "00000000-0000-4000-8000-000000000004", "feature/APS-9012-map-clusters", TRIS, source="startup"),
        ev(24, "UserPromptSubmit", "00000000-0000-4000-8000-000000000004", "feature/APS-9012-map-clusters", TRIS),
        ev(1, "UserPromptSubmit", "00000000-0000-4000-8000-000000000004", "feature/APS-9012-map-clusters", TRIS),
        ev(70, "SessionStart", "00000000-0000-4000-8000-000000000005", "feature/APS-9008-export-region", API, source="startup"),
        ev(69, "UserPromptSubmit", "00000000-0000-4000-8000-000000000005", "feature/APS-9008-export-region", API),
        ev(22, "Stop", "00000000-0000-4000-8000-000000000005", "feature/APS-9008-export-region", API),
    ]
with open(sys.argv[1], "w") as f:
    for r in rows:
        f.write(json.dumps(r) + "\n")
