#!/var/packages/dsm-terminal/target/bin/python-runtime

import json
import shutil
import subprocess
import sys


def send_json(payload) -> None:
    sys.stdout.write("Content-Type: application/json\r\n")
    sys.stdout.write("Cache-Control: no-store\r\n\r\n")
    sys.stdout.write(json.dumps(payload))
    sys.stdout.write("\n")


def main() -> int:
    sudo_bin = shutil.which("sudo") or "/usr/bin/sudo"
    try:
        result = subprocess.run(
            [sudo_bin, "-n", "true"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except FileNotFoundError:
        send_json({"ok": True, "enabled": False, "available": False})
        return 0

    send_json({
        "ok": True,
        "enabled": result.returncode == 0,
        "available": True,
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
