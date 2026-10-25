#!/var/packages/dsm-terminal/target/bin/python-runtime

import errno
import json
import os
import socket
import sys
import traceback
import subprocess


TMP_DIR = "/tmp/dsm-terminal-pty"
LOG_FILE = os.path.join(TMP_DIR, "pty-cgi.log")
SOCKET_PATH = os.path.join(TMP_DIR, "pty.sock")


def ensure_log_dir() -> None:
    try:
        os.makedirs(TMP_DIR, mode=0o777, exist_ok=True)
    except OSError:
        pass
    try:
        os.chmod(TMP_DIR, 0o777)
    except OSError:
        pass


def log_error(message: str) -> None:
    ensure_log_dir()
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as handle:
            handle.write(message)
            if not message.endswith("\n"):
                handle.write("\n")
    except OSError:
        pass


def send_json(payload) -> None:
    sys.stdout.write("Content-Type: application/json\r\n")
    sys.stdout.write("Cache-Control: no-store\r\n\r\n")
    sys.stdout.write(json.dumps(payload))
    sys.stdout.write("\n")
    sys.stdout.flush()


def read_body() -> bytes:
    length_raw = os.environ.get("CONTENT_LENGTH", "0")
    try:
        length = int(length_raw)
    except ValueError:
        length = 0
    return sys.stdin.buffer.read(length) if length > 0 else b""


def resolve_user() -> str:
    remote_user = os.environ.get("REMOTE_USER", "").strip()
    if remote_user:
        return remote_user
    try:
        env = os.environ.copy()
        result = subprocess.run(
            ["/usr/syno/synoman/webman/modules/authenticate.cgi"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            text=True,
        )
        authenticated = result.stdout.strip().splitlines()
        if authenticated:
            return authenticated[0].strip()
    except Exception:
        pass
    return "dsm-session" if os.environ.get("HTTP_COOKIE") else "unknown"


def main() -> int:
    body = read_body()
    try:
        request = json.loads(body.decode("utf-8"))
        request["client"] = {
            "user": resolve_user(),
            "ip": os.environ.get("REMOTE_ADDR", "unknown") or "unknown",
        }
        body = json.dumps(request).encode("utf-8")
    except (TypeError, ValueError):
        pass

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(SOCKET_PATH)
    except OSError as exc:
        if exc.errno in (errno.ENOENT, errno.ECONNREFUSED):
            send_json({"ok": False, "error": "PTY service is not running"})
            return 0
        if exc.errno == errno.EACCES:
            send_json({"ok": False, "error": "PTY service socket permission denied"})
            return 0
        raise

    try:
        sock.sendall(body)
        sock.shutdown(socket.SHUT_WR)
        response = bytearray()
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            response.extend(chunk)
    finally:
        sock.close()

    if not response:
        send_json({"ok": False, "error": "PTY service did not return a response"})
        return 0

    sys.stdout.write("Content-Type: application/json\r\n")
    sys.stdout.write("Cache-Control: no-store\r\n\r\n")
    sys.stdout.flush()
    sys.stdout.buffer.write(response)
    if not response.endswith(b"\n"):
        sys.stdout.buffer.write(b"\n")
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    ensure_log_dir()
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        log_error(traceback.format_exc())
        send_json({"ok": False, "error": "PTY CGI bridge failed"})
        raise SystemExit(0)
