"""OS-owned lock: survives orphaned children, releases on exit/reboot, no stale PID files."""
import fcntl
import os
from pathlib import Path
import subprocess
import sys

lock_path = Path(__file__).resolve().parent.parent / "data/publisher.lock"
lock_path.parent.mkdir(parents=True, exist_ok=True)
with lock_path.open("a+") as lock:
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit("Another publisher/build/deploy is active; retry after it finishes.")
    os.set_inheritable(lock.fileno(), True)
    os.environ["NEWS_PUBLISHER_LOCK_FD"] = str(lock.fileno())
    # Never unlink a flock file: another process could otherwise lock a new inode.
    result = subprocess.run(sys.argv[1:], pass_fds=(lock.fileno(),))
    sys.exit(result.returncode if result.returncode >= 0 else 128 - result.returncode)
