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


def snapshot(self_id):
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
            })
    queue.sort(key=lambda q: q.get("updatedAt") or "")
    return {"queue": queue, "working": working, "handledQuiet": quiet}


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
    ap.add_argument("--message-file", help="With --send: read the message from this UTF-8 file instead of stdin.")
    ap.add_argument("--messages", type=int, default=6, help="How many messages --last prints.")
    ap.add_argument("--interval", type=int, default=20, help="Seconds between checks in --watch.")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    self_id = a.self_id.strip()

    if a.mark or a.unmark or a.ignore or a.unignore:
        s = load_state()
        if a.mark:
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

    print(json.dumps(snapshot(self_id), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
