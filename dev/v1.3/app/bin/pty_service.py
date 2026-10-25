#!/var/packages/dsm-terminal/target/bin/python-runtime

import argparse
import base64
import errno
import fcntl
import json
import os
import pty
import selectors
import signal
import socket
import struct
import sys
import threading
import time
import traceback
import tty

DEBUG_DIR = "/tmp/dsm-terminal-pty"
STREAM_LOG = os.path.join(DEBUG_DIR, "stream-debug.log")
DEBUG_STREAM = False


def log_stream(event: str, sid: str, data: bytes) -> None:
    if not DEBUG_STREAM:
        return
    try:
        os.makedirs(DEBUG_DIR, exist_ok=True)
        with open(STREAM_LOG, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "ts": int(time.time() * 1000),
                "event": event,
                "sid": sid,
                "len": len(data),
                "data_b64": base64.b64encode(data).decode("ascii"),
            }))
            handle.write("\n")
    except Exception:
        pass


def set_nonblocking(fd: int) -> None:
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)


class PtySession:
    def __init__(self, sid: str, home_dir: str, shell: str, cols: int, rows: int) -> None:
        self.sid = sid
        self.home_dir = home_dir
        self.shell = shell
        self.cols = cols
        self.rows = rows
        self.master_fd = -1
        self.pid = -1
        self.closed = False
        self.lock = threading.Lock()
        self.buffer = bytearray()
        self.start_seq = 0
        self.max_buffer = 512 * 1024
        self.last_used = time.time()
        self._spawn()

    def _spawn(self) -> None:
        pid, master_fd = pty.fork()
        if pid == 0:
            env = os.environ.copy()
            env["TERM"] = env.get("TERM", "xterm-256color")
            env["HOME"] = self.home_dir
            env["SHELL"] = self.shell
            env["USER"] = env.get("USER", "dsm-terminal")
            os.chdir(self.home_dir)
            os.execvpe(self.shell, [self.shell, "-i"], env)

        self.pid = pid
        self.master_fd = master_fd
        set_nonblocking(self.master_fd)
        self.resize(self.cols, self.rows)

    def resize(self, cols: int, rows: int) -> None:
        self.cols = max(20, cols)
        self.rows = max(8, rows)
        winsz = struct.pack("HHHH", self.rows, self.cols, 0, 0)
        fcntl.ioctl(self.master_fd, tty.TIOCSWINSZ, winsz)

    def append_output(self, data: bytes) -> None:
        log_stream("pty:read", self.sid, data)
        with self.lock:
            self.buffer.extend(data)
            if len(self.buffer) > self.max_buffer:
                excess = len(self.buffer) - self.max_buffer
                del self.buffer[:excess]
                self.start_seq += excess
            self.last_used = time.time()

    def read_from(self, cursor: int):
        with self.lock:
            if cursor < self.start_seq:
                cursor = self.start_seq
            offset = cursor - self.start_seq
            data = bytes(self.buffer[offset:])
            next_cursor = self.start_seq + len(self.buffer)
            self.last_used = time.time()
            return data, next_cursor

    def write(self, data: bytes) -> None:
        if self.closed:
            return
        log_stream("pty:write", self.sid, data)
        os.write(self.master_fd, data)
        with self.lock:
            self.last_used = time.time()

    def terminate(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            os.close(self.master_fd)
        except OSError:
            pass
        try:
            os.kill(self.pid, signal.SIGHUP)
        except OSError:
            pass


class PtyServer:
    def __init__(self, socket_path: str, home_dir: str, pidfile: str) -> None:
        self.socket_path = socket_path
        self.home_dir = home_dir
        self.pidfile = pidfile
        self.shell = os.environ.get("SHELL", "/bin/sh")
        self.sessions = {}
        self.selector = selectors.DefaultSelector()
        self.server = None
        self.running = True
        self.session_counter = 0

    def next_sid(self) -> str:
        self.session_counter += 1
        return f"s{int(time.time())}-{os.getpid()}-{self.session_counter}"

    def serve(self) -> None:
        os.makedirs(os.path.dirname(self.socket_path), exist_ok=True)
        os.makedirs(self.home_dir, exist_ok=True)
        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass

        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(self.socket_path)
        os.chmod(self.socket_path, 0o666)
        self.server.listen(16)
        self.server.setblocking(False)
        self.selector.register(self.server, selectors.EVENT_READ, self._accept)
        with open(self.pidfile, "w", encoding="utf-8") as handle:
            handle.write(str(os.getpid()))

        print(f"PTY service ready on {self.socket_path}", file=sys.stderr, flush=True)
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        while self.running:
            for key, _mask in self.selector.select(timeout=0.2):
                callback = key.data
                callback(key.fileobj)
            self._reap_sessions()

        self._shutdown()

    def _handle_signal(self, _signum, _frame) -> None:
        self.running = False

    def _accept(self, sock) -> None:
        conn, _addr = sock.accept()
        conn.settimeout(2)
        try:
            raw = conn.recv(1024 * 1024)
            request = json.loads(raw.decode("utf-8"))
            response = self._handle_request(request)
        except Exception as exc:
            response = {"ok": False, "error": str(exc)}
        conn.sendall(json.dumps(response).encode("utf-8"))
        conn.close()

    def _handle_request(self, request):
        action = request.get("action")
        if action == "ping":
            return {"ok": True, "status": "ready"}

        if action == "create":
            cols = int(request.get("cols", 80))
            rows = int(request.get("rows", 24))
            sid = self.next_sid()
            session_home = os.path.join(self.home_dir, sid)
            os.makedirs(session_home, exist_ok=True)
            session = PtySession(sid, session_home, self.shell, cols, rows)
            self.sessions[sid] = session
            return {"ok": True, "sid": sid, "cursor": 0}

        sid = request.get("sid")
        session = self.sessions.get(sid)
        if not session:
            # A closed PTY is removed during the reap pass.  A browser can
            # still have one poll in flight at that point, so report a read
            # of a missing session as a normal closed session.  This is
            # especially common when more than one DSM window is open and
            # their polling/close requests interleave.
            if action == "read":
                return {
                    "ok": True,
                    "closed": True,
                    "cursor": int(request.get("cursor", 0)),
                    "data": "",
                }
            return {"ok": False, "error": "Session not found"}

        if action == "read":
            cursor = int(request.get("cursor", 0))
            data, next_cursor = session.read_from(cursor)
            return {
                "ok": True,
                "closed": session.closed,
                "cursor": next_cursor,
                "data": base64.b64encode(data).decode("ascii"),
            }

        if action == "write":
            data = base64.b64decode(request.get("data", ""))
            session.write(data)
            return {"ok": True}

        if action == "resize":
            cols = int(request.get("cols", 80))
            rows = int(request.get("rows", 24))
            session.resize(cols, rows)
            return {"ok": True}

        if action == "close":
            session.terminate()
            self.sessions.pop(sid, None)
            return {"ok": True}

        return {"ok": False, "error": "Unsupported action"}

    def _reap_sessions(self) -> None:
        for sid in list(self.sessions):
            session = self.sessions[sid]
            if session.closed:
                self.sessions.pop(sid, None)
                continue
            try:
                data = os.read(session.master_fd, 8192)
                if data:
                    session.append_output(data)
                    continue
                session.closed = True
            except BlockingIOError:
                pass
            except OSError as exc:
                if exc.errno not in (errno.EIO, errno.EBADF):
                    raise
                session.closed = True
            try:
                pid, _status = os.waitpid(session.pid, os.WNOHANG)
                if pid == session.pid:
                    session.closed = True
            except ChildProcessError:
                session.closed = True

    def _shutdown(self) -> None:
        for session in list(self.sessions.values()):
            session.terminate()
        self.sessions.clear()
        if self.server:
            self.selector.unregister(self.server)
            self.server.close()
        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass
        try:
            os.unlink(self.pidfile)
        except FileNotFoundError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", required=True)
    parser.add_argument("--home", required=True)
    parser.add_argument("--pidfile", required=True)
    args = parser.parse_args()

    print("PTY service starting", file=sys.stderr, flush=True)
    server = PtyServer(args.socket, args.home, args.pidfile)
    try:
        server.serve()
    except Exception:
        traceback.print_exc()
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
