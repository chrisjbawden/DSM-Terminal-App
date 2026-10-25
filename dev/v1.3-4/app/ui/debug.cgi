#!/var/packages/dsm-terminal/target/bin/python-runtime

import json
import os
import sys
import time

TMP_DIR = "/tmp/dsm-terminal-pty"
LOG_FILE = os.path.join(TMP_DIR, "frontend-debug.log")


def respond(payload):
    sys.stdout.write("Content-Type: application/json\r\n")
    sys.stdout.write("Cache-Control: no-store\r\n\r\n")
    sys.stdout.write(json.dumps(payload))


def main():
    os.makedirs(TMP_DIR, exist_ok=True)
    length = int(os.environ.get("CONTENT_LENGTH", "0") or "0")
    raw = sys.stdin.read(length) if length > 0 else ""
    payload = json.loads(raw) if raw else {}
    line = {
        "ts": int(time.time() * 1000),
        "event": payload.get("event"),
        "data": payload.get("data"),
    }
    with open(LOG_FILE, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, ensure_ascii=True) + "\n")
    respond({"ok": True})


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        respond({"ok": False, "error": str(exc)})
