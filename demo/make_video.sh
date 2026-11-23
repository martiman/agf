#!/bin/bash
# Fresh demo state, then record. Usage: demo/make_video.sh [approve|launch] [en [cc|mute]]
cd "$(dirname "$0")" || exit 1
[ "$2" = "en" ] && export DEMO_LANG=en
./stop_demo.sh >/dev/null; sleep 1; ./start_demo.sh >/dev/null
PATH="/opt/homebrew/bin:$PATH" node record.mjs "${1:-approve}" $2 $3
