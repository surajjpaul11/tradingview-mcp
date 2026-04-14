#!/usr/bin/env python3
"""SessionStart hook: emit /loop instructions for each active loop in loops.json.

Reads loops.json + loops.state.json (last-run timestamps) from CWD and emits
additionalContext telling Claude which /loop commands to start. Loops whose
last run is within `interval` are skipped so a quick restart doesn't re-fire
them immediately.
"""
import json
import os
import re
import sys
import time
from pathlib import Path

WORKSPACE = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
LOOPS_FILE = WORKSPACE / "loops.json"
STATE_FILE = WORKSPACE / "loops.state.json"


def parse_interval(s: str) -> int:
    m = re.fullmatch(r"(\d+)\s*([smhd])", s.strip().lower())
    if not m:
        return 0
    n, unit = int(m.group(1)), m.group(2)
    return n * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]


def main() -> None:
    if not LOOPS_FILE.exists():
        sys.exit(0)

    try:
        loops = json.loads(LOOPS_FILE.read_text())
    except json.JSONDecodeError as e:
        print(f"restore_loops: loops.json parse error: {e}", file=sys.stderr)
        sys.exit(0)

    try:
        state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    except json.JSONDecodeError:
        state = {}

    now = int(time.time())
    lines: list[str] = []
    seen: set[str] = set()

    for loop in loops:
        if not isinstance(loop, dict) or not loop.get("enabled", True):
            continue
        loop_id = loop.get("id")
        interval = loop.get("interval")
        prompt = loop.get("prompt")
        if not (loop_id and interval and prompt):
            continue
        if loop_id in seen:
            continue
        seen.add(loop_id)

        last = state.get(loop_id, {}).get("last_run", 0)
        interval_s = parse_interval(interval)
        if interval_s and now - last < interval_s:
            remaining = interval_s - (now - last)
            lines.append(
                f"- [{loop_id}] last ran {now - last}s ago; next due in ~{remaining}s "
                f"(interval {interval}). Prompt: {prompt}"
            )
        else:
            lines.append(f"- [{loop_id}] /loop {interval} {prompt}")

    if not lines:
        sys.exit(0)

    body = (
        "Active loops configured in loops.json — restart them now by invoking "
        "each `/loop` below (skip entries marked 'next due in ~Ns', they ran "
        "recently). After starting each loop, update loops.state.json with the "
        "new last_run timestamp.\n\n" + "\n".join(lines)
    )

    out = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": body}}
    print(json.dumps(out))


if __name__ == "__main__":
    main()
