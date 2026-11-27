#!/usr/bin/env python3
"""Queue helper for the T3 Code session manager skill.

Lists T3 Code threads that finished and wait on the user (oldest first),
keeps per-computer bookkeeping (handled / ignored), relays a message read
from stdin, and can watch for newly finished threads.

Standard library only. Works on Windows, macOS and Linux.
"""
import argparse
import datetime as dt
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

LIVE = {"queued", "preparing", "starting", "running"}
FINISHED = {"completed": "done", "idle": "done", "failed": "error",
            "cancelled": "stopped", "interrupted": "stopped", "rolled_back": "stopped"}

STATE = Path.home() / ".claude" / "t3-session-manager" / "state.json"
WAKE = STATE.parent / "wake.json"
WAKE_LOG = STATE.parent / "wake.log"
WAKE_TEXT = ("[t3-session-manager wake] A thread may have finished. Rebuild the queue and report "
             "what is new. (Automatic message from the wake watcher on this computer, not typed by the user.)")


def t3_home() -> Path:
    env = os.environ.get("T3CODE_HOME", "").strip()
    return Path(env).expanduser() if env else Path.home() / ".t3"


def t3_cmd() -> list:
    home = t3_home() / "bin"
    for name in ("t3.cmd", "t3.exe", "t3"):
        p = home / name
        if p.exists():
            return [str(p)]
    found = shutil.which("t3")
    if found:
        return [found]
    sys.exit(json.dumps({"error": "t3 command not found. In T3 Code, use Settings > About to add t3 to PATH."}))


def run_t3(args, stdin_text=None):
    r = subprocess.run(t3_cmd() + args, input=(stdin_text.encode("utf-8") if stdin_text is not None else None),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")


def t3_json(args):
    code, out, err = run_t3(args + ["--json"])
    if code != 0:
        raise RuntimeError((err or out).strip()[:400])
    return json.loads(out)


def project_ids():
    db = t3_home() / "userdata" / "statev2.sqlite"
    con = sqlite3.connect("file:" + db.as_posix() + "?mode=ro", uri=True)
    try:
        rows = con.execute("select project_id, title from projection_projects where deleted_at is null").fetchall()
    finally:
        con.close()
    return rows


def load_state():
    try:
        s = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        s = {}
    s.setdefault("handled", {})
    s.setdefault("ignored", [])
    return s


def save_state(s):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, STATE)


def parse_time(s):
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def fingerprint(t):
    return f"{t.get('latestRunId')}|{t.get('status')}"


def snapshot(self_id, remote_file=None):
    state = load_state()
    now = dt.datetime.now(dt.timezone.utc)
    queue, working, quiet = [], [], []
    for pid, ptitle in project_ids():
        try:
            threads = t3_json(["thread", "list", "--project", pid])
        except Exception:
            continue
        for t in threads:
            tid = t["threadId"]
            if tid == self_id or tid in state["ignored"]:
                continue
            if t.get("latestRunId") is None:        # never ran in T3 Code (imported history)
                continue
            if t.get("settled") or t.get("snoozed"):  # put away by the user
                continue
            status = t.get("status")
            title = t.get("title") or "(untitled)"
            if status in LIVE:
                working.append(title)
                continue
            kind = FINISHED.get(status)
            detail = None
            if status == "waiting":
                try:
                    detail = t3_json(["thread", "show", tid, "--messages", "0"])["thread"]
                except Exception:
                    detail = {}
                if (detail or {}).get("pendingRequestCount", 0) > 0:
                    kind = "needs-you"
                else:
                    working.append(title)
                    continue
            if kind is None:
                kind = status or "unknown"
            if state["handled"].get(tid) == fingerprint(t):
                quiet.append(title)
                continue
            upd = parse_time(t.get("updatedAt", ""))
            queue.append({
                "id": tid,
                "title": title,
                "project": ptitle,
                "kind": kind,
                "status": status,
                "provider": t.get("providerInstanceId"),
                "model": t.get("model"),
                "waitedMin": max(0, int((now - upd).total_seconds() // 60)) if upd else None,
                "updatedAt": t.get("updatedAt"),
                "_run": t.get("latestRunId"),
            })
    for q in queue:
        q.update({"machine": "this machine", "environmentId": None, "threadId": q["id"],
                  "fp": f"{q.pop('_run', None)}|{q['status']}"})
    if remote_file:
        add_remote(remote_file, state, now, queue, working, quiet)
    queue.sort(key=lambda q: q.get("updatedAt") or "")
    return {"queue": queue, "working": working, "handledQuiet": quiet}


def add_remote(remote_file, state, now, queue, working, quiet):
    """Merge thread lists from linked machines, fetched by the agent with T3's own
    t3_thread_list tool and saved as JSON:
    [{"environmentId": "...", "label": "...", "threads": [<t3_thread_list items>]}, ...]"""
    blocks = json.loads(Path(remote_file).read_text(encoding="utf-8-sig"))
    if isinstance(blocks, dict):
        blocks = [blocks]
    for b in blocks:
        env = b.get("environmentId")
        label = b.get("label") or env
        for t in b.get("threads", []):
            tid = t.get("threadId")
            if not env or not tid:
                continue
            key = f"{env}/{tid}"
            if key in state["ignored"] or t.get("latestRunId") is None:
                continue
            if t.get("settled") or t.get("snoozed"):
                continue
            status = t.get("status")
            title = t.get("title") or "(untitled)"
            if status in LIVE:
                working.append(f"{title} ({label})")
                continue
            kind = "waiting" if status == "waiting" else FINISHED.get(status, status or "unknown")
            if state["handled"].get(key) == fingerprint(t):
                quiet.append(f"{title} ({label})")
                continue
            upd = parse_time(t.get("updatedAt", ""))
            queue.append({
                "id": key, "machine": label, "environmentId": env, "threadId": tid,
                "title": title, "project": t.get("projectId"), "kind": kind, "status": status,
                "provider": t.get("providerInstanceId"), "model": t.get("model"),
                "waitedMin": max(0, int((now - upd).total_seconds() // 60)) if upd else None,
                "updatedAt": t.get("updatedAt"), "fp": fingerprint(t),
            })


# ---------------------------------------------------------------- wake watcher
# The T3 desktop app logs a "set-notification-badge" call each time a thread on any
# connected machine finishes or needs the user. The watcher follows that local log
# line and sends the manager thread a wake message, so the manager reports on its own.
# It spends no model tokens and asks T3 for nothing until the badge changes.

def pid_alive(pid):
    if not pid:
        return False
    if os.name == "nt":
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(h)
        return bool(ok) and code.value == 259
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def t3_is_foreground():
    """Windows only: True when a T3 Code window has focus. Focusing T3 clears the badge,
    which must not wake the manager."""
    if os.name != "nt":
        return False
    import ctypes
    from ctypes import wintypes
    u, k = ctypes.windll.user32, ctypes.windll.kernel32
    pid = wintypes.DWORD()
    u.GetWindowThreadProcessId(u.GetForegroundWindow(), ctypes.byref(pid))
    h = k.OpenProcess(0x1000, False, pid.value)
    if not h:
        return False
    buf = ctypes.create_unicode_buffer(520)
    size = wintypes.DWORD(520)
    k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
    k.CloseHandle(h)
    return "t3 code" in buf.value.lower()


def wlog(msg):
    try:
        WAKE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(WAKE_LOG, "a", encoding="utf-8") as fh:
            fh.write(dt.datetime.now().strftime("%m-%d %H:%M:%S ") + msg + "\n")
    except Exception:
        pass


def manager_state(tid):
    try:
        return t3_json(["thread", "show", tid, "--messages", "0"])["thread"]
    except Exception as e:
        return None if "no longer available" in str(e) or "not found" in str(e).lower() else {}


def wake_watch(manager, debounce=8, min_gap=30, self_quiet=25):
    log = t3_home() / "userdata" / "logs" / "desktop.trace.ndjson"
    pos = log.stat().st_size if log.exists() else 0
    pending, last_ping, ping_runs, last_check = None, 0.0, None, time.time()
    wlog(f"watching for {manager}")
    while True:
        time.sleep(1)
        now = time.time()
        try:
            size = log.stat().st_size
        except OSError:
            continue
        if size < pos:                       # log rotated
            pos = 0
        if size > pos:
            with open(log, "rb") as fh:
                fh.seek(pos)
                chunk = fh.read(size - pos)
            pos = size
            if b"set-notification-badge" in chunk and not t3_is_foreground():
                pending = pending or now
        if now - last_check > 300:
            last_check = now
            th = manager_state(manager)
            if th is None or (th or {}).get("archived"):
                wlog("manager thread is gone or archived; stopping")
                return
        if not pending or now - pending < debounce or now - last_ping < min_gap:
            continue
        pending = None
        th = manager_state(manager)
        if th is None or th.get("archived"):
            wlog("manager thread is gone or archived; stopping")
            return
        if not th:
            continue
        runs = th.get("runCount")
        if ping_runs is not None and runs == ping_runs:
            continue                         # the last wake is still waiting to run
        if th.get("status") not in LIVE:
            upd = parse_time(th.get("updatedAt", ""))
            if upd and (dt.datetime.now(dt.timezone.utc) - upd).total_seconds() < self_quiet:
                continue                     # the badge moved because the manager itself just answered
        code, out, err = run_t3(["thread", "send", manager, "-"], stdin_text=WAKE_TEXT)
        last_ping, ping_runs = now, runs
        wlog("wake sent" if code == 0 else "wake failed: " + (err or out).strip()[:200])


def start_wake(manager):
    try:
        cur = json.loads(WAKE.read_text(encoding="utf-8"))
    except Exception:
        cur = {}
    if pid_alive(cur.get("pid")):
        if cur.get("manager") == manager:
            return {"wake": "already running", "pid": cur["pid"]}
        stop_wake()
    args = [sys.executable, str(Path(__file__).resolve()), "--wake-watch", "--self", manager]
    kw = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "close_fds": True}
    if os.name == "nt":
        flags = 0x00000008 | 0x00000200      # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        try:                                 # also leave the agent's job, so it outlives the agent process
            p = subprocess.Popen(args, creationflags=flags | 0x01000000, **kw)
        except OSError:
            p = subprocess.Popen(args, creationflags=flags, **kw)
    else:
        p = subprocess.Popen(args, start_new_session=True, **kw)
    WAKE.parent.mkdir(parents=True, exist_ok=True)
    WAKE.write_text(json.dumps({"pid": p.pid, "manager": manager}), encoding="utf-8")
    return {"wake": "started", "pid": p.pid}


def stop_wake():
    try:
        cur = json.loads(WAKE.read_text(encoding="utf-8"))
    except Exception:
        return {"wake": "not running"}
    if pid_alive(cur.get("pid")):
        import signal
        os.kill(int(cur["pid"]), signal.SIGTERM)
    WAKE.unlink(missing_ok=True)
    return {"wake": "stopped"}


def thread_fingerprint(tid):
    t = t3_json(["thread", "show", tid, "--messages", "0"])["thread"]
    return fingerprint(t), t.get("title")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--self", dest="self_id", default=os.environ.get("T3CODE_THREAD_ID", ""),
                    help="This manager's own thread id (defaults to $T3CODE_THREAD_ID).")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--mark", metavar="ID", help="Hide a thread until it produces new work.")
    g.add_argument("--unmark", metavar="ID")
    g.add_argument("--ignore", metavar="ID", help="Never show this thread again.")
    g.add_argument("--unignore", metavar="ID")
    g.add_argument("--send", metavar="ID", help="Mark the thread, then send it the message read from stdin.")
    g.add_argument("--last", metavar="ID", help="Print the thread's latest messages.")
    g.add_argument("--watch", action="store_true", help="Print READY lines as threads newly finish.")
    g.add_argument("--start-wake", action="store_true",
                   help="Start the background wake watcher for this manager thread (one per computer).")
    g.add_argument("--stop-wake", action="store_true", help="Stop the wake watcher.")
    g.add_argument("--wake-status", action="store_true", help="Show whether the wake watcher runs.")
    g.add_argument("--wake-watch", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--message-file", help="With --send: read the message from this UTF-8 file instead of stdin.")
    ap.add_argument("--remote", metavar="FILE",
                    help="Also queue threads from linked machines: a JSON file of t3_thread_list results per environment.")
    ap.add_argument("--fp", help="With --mark on another machine's thread: the queue item's fp.")
    ap.add_argument("--messages", type=int, default=6, help="How many messages --last prints.")
    ap.add_argument("--interval", type=int, default=20, help="Seconds between checks in --watch.")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    self_id = a.self_id.strip()

    if a.wake_watch:
        wake_watch(self_id)
        return
    if a.start_wake:
        if not self_id or self_id == "none":
            sys.exit(json.dumps({"error": "no manager thread id: run inside a T3 Code thread or pass --self"}))
        print(json.dumps(start_wake(self_id)))
        return
    if a.stop_wake:
        print(json.dumps(stop_wake()))
        return
    if a.wake_status:
        try:
            cur = json.loads(WAKE.read_text(encoding="utf-8"))
        except Exception:
            cur = {}
        print(json.dumps({"running": pid_alive(cur.get("pid")), **cur}))
        return

    if a.mark or a.unmark or a.ignore or a.unignore:
        s = load_state()
        if a.mark and "/" in a.mark:           # a thread on a linked machine: env/thread
            if not a.fp:
                sys.exit(json.dumps({"error": "--mark on another machine needs --fp (the queue item's fp)"}))
            s["handled"][a.mark] = a.fp
            msg = {"marked": a.mark}
        elif a.mark:
            fp, title = thread_fingerprint(a.mark)
            s["handled"][a.mark] = fp
            msg = {"marked": a.mark, "title": title}
        elif a.unmark:
            s["handled"].pop(a.unmark, None)
            msg = {"unmarked": a.unmark}
        elif a.ignore:
            if a.ignore not in s["ignored"]:
                s["ignored"].append(a.ignore)
            msg = {"ignored": a.ignore}
        else:
            s["ignored"] = [x for x in s["ignored"] if x != a.unignore]
            msg = {"unignored": a.unignore}
        save_state(s)
        print(json.dumps(msg, ensure_ascii=False))
        return

    if a.last:
        data = t3_json(["thread", "show", a.last, "--messages", str(a.messages)])
        th = data["thread"]
        out = {"title": th.get("title"), "status": th.get("status"),
               "pendingRequestCount": th.get("pendingRequestCount"),
               "messages": [{"role": m.get("role"), "text": m.get("text")} for m in data.get("messages", [])]}
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return

    if a.send:
        if a.send == self_id:
            sys.exit(json.dumps({"error": "refusing to send to the manager's own thread"}))
        if a.message_file:
            text = Path(a.message_file).read_text(encoding="utf-8-sig").strip()
        else:
            text = sys.stdin.buffer.read().decode("utf-8", "replace").strip()
        if not text:
            sys.exit(json.dumps({"error": "no message on stdin"}))
        s = load_state()
        fp, title = thread_fingerprint(a.send)
        s["handled"][a.send] = fp            # mark first, so a fast reply is not hidden
        save_state(s)
        code, out, err = run_t3(["thread", "send", a.send, "-"], stdin_text=text)
        if code != 0:
            s = load_state()
            s["handled"].pop(a.send, None)   # did not go through: put it back
            save_state(s)
            print(json.dumps({"sent": False, "title": title, "error": (err or out).strip()[:400]}, ensure_ascii=False))
            sys.exit(1)
        print(json.dumps({"sent": True, "title": title, "result": out.strip()[:400]}, ensure_ascii=False))
        return

    if a.watch:
        seen = {q["id"] + "|" + (q.get("updatedAt") or "") for q in snapshot(self_id)["queue"]}
        print("WATCHING", flush=True)
        while True:
            time.sleep(max(5, a.interval))
            try:
                snap = snapshot(self_id)
            except Exception as e:
                print("WARN: " + str(e)[:200], flush=True)
                continue
            for q in snap["queue"]:
                key = q["id"] + "|" + (q.get("updatedAt") or "")
                if key not in seen:
                    seen.add(key)
                    print(f"READY: {q['title']} | {q['kind']} | {q['id']}", flush=True)

    snap = snapshot(self_id, a.remote)
    # "new": queue items not reported before (or with new work since), recorded as reported now.
    s = load_state()
    ann = s.setdefault("announced", {})
    snap["new"] = [q for q in snap["queue"] if ann.get(q["id"]) != q.get("fp")]
    for q in snap["new"]:
        ann[q["id"]] = q.get("fp")
    save_state(s)
    print(json.dumps(snap, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
