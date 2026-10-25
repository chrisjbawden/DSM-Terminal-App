#!/var/packages/dsm-terminal/target/bin/python-runtime

import json
import os
import sys
from urllib.parse import parse_qs

LOG_PATH = "/var/packages/dsm-terminal/var/logs/terminal.log"


def send_json(payload):
    sys.stdout.write("Content-Type: application/json\r\nCache-Control: no-store\r\n\r\n")
    sys.stdout.write(json.dumps(payload) + "\n")


def read_tail(count):
    try:
        with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as handle:
            return handle.readlines()[-count:]
    except FileNotFoundError:
        return []


def main():
    action = parse_qs(os.environ.get("QUERY_STRING", "")).get("action", ["tail"])[0]
    if action == "download":
        sys.stdout.write("Content-Type: text/plain; charset=utf-8\r\n")
        sys.stdout.write("Content-Disposition: attachment; filename=terminal.log\r\nCache-Control: no-store\r\n\r\n")
        try:
            with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as handle:
                sys.stdout.write(handle.read())
        except FileNotFoundError:
            pass
        return 0
    send_json({"ok": True, "lines": [line.rstrip("\n") for line in reversed(read_tail(20))]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
