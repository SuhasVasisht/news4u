"""OS-owned lock: survives orphaned children, releases on exit/reboot, no stale PID files."""
import fcntl
import os
from pathlib import Path
import subprocess
import sys
from threading import Thread

from lib.publisher_logging import open_log, record

root = Path(__file__).resolve().parent.parent
log, redact = open_log(root)
lock_path = root / "data/publisher.lock"
lock_path.parent.mkdir(parents=True, exist_ok=True)
with log, lock_path.open("a+") as lock:
    record(log, redact, f"run_start pid={os.getpid()} command={' '.join(sys.argv[1:])}")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        record(log, redact, "run_blocked reason=publisher_lock Another publisher/build/deploy is active; retry after it finishes.")
        sys.exit(1)
    os.set_inheritable(lock.fileno(), True)
    os.environ["NEWS_PUBLISHER_LOCK_FD"] = str(lock.fileno())
    # Never unlink a flock file: another process could otherwise lock a new inode.
    os.environ["PYTHONUNBUFFERED"] = "1"
    process = subprocess.Popen(sys.argv[1:], pass_fds=(lock.fileno(),), stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, errors="replace", bufsize=1)
    def drain():
        for line in process.stdout:
            record(log, redact, line)
    reader = Thread(target=drain, daemon=True)
    reader.start()
    code = process.wait()
    # A crashed supervisor can leave a stage holding the stdout pipe and lock.
    # Do not wait forever for that orphan's EOF; the OS still owns its lock.
    reader.join(timeout=1)

    record(log, redact, f"run_end pid={os.getpid()} exit={code}")
    sys.exit(code if code >= 0 else 128 - code)
