#!/usr/bin/env python3
"""queue.py - queue helper for the session-manager skill (macOS/Linux; also runs on Windows).

Reads Claude Code's own session records (~/.claude/sessions/*.json) and, when present,
the switchboard plugin's status reports (~/.claude/switchboard/reports/*.json). Prints JSON.
Standard library only.

  Queue:   python3 queue.py --self <local_id of the manager session>
  Handled: python3 queue.py --mark <local_id>     (run BEFORE relaying, or on skip)
           python3 queue.py --unmark <local_id>   (undo a mark, e.g. when the relay failed)
  Ignore:  python3 queue.py --ignore <local_id>   (never queue it again) / --unignore <local_id>
  Watch:   python3 queue.py --self <id> --watch   (print "READY: title | kind | id" whenever a
                                                   session newly enters the queue)
  Testing: --only <local_id>,<local_id>  and  --state-file <path>
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude"
SESSIONS_DIR = CLAUDE_DIR / "sessions"
REPORTS_DIR = CLAUDE_DIR / "switchboard" / "reports"
DEFAULT_STATE = CLAUDE_DIR / "session-manager" / "state.json"


def now_ms():
    return int(time.time() * 1000)


def to_ms(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0
    if 0 < v < 1e12:  # seconds, not milliseconds
        return int(v * 1000)
    return int(v)


def local_id(h):
    return h if h.startswith("local_") else "local_" + h


def pid_alive(pid):
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel32.CloseHandle(handle)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def read_state(path):
    state = {"handled": {}, "ignored": []}
    j = read_json(path)
    if isinstance(j, dict):
        if isinstance(j.get("handled"), dict):
            state["handled"] = {k: int(v) for k, v in j["handled"].items()}
        if isinstance(j.get("ignored"), list):
            state["ignored"] = [x for x in j["ignored"] if x]
    return state


def save_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def get_queue(self_id, only, state_path):
    state = read_state(state_path)
    now = now_ms()
    queue, working, handled_quiet = [], [], 0
    for f in sorted(SESSIONS_DIR.glob("*.json")) if SESSIONS_DIR.is_dir() else []:
        r = read_json(f)
        if not isinstance(r, dict) or not r.get("hostSessionId"):
            continue
        if "desktop" not in str(r.get("entrypoint", "")):
            continue
        if not pid_alive(r.get("pid")):
            continue
        sid = local_id(str(r["hostSessionId"]))
        if sid == self_id:
            continue
        if only and sid not in only:
            continue
        if sid in state["ignored"]:
            continue

        title = str(r.get("name") or "") or Path(str(r.get("cwd", ""))).name
        updated = to_ms(r.get("statusUpdatedAt"))

        rep = None
        if r.get("sessionId"):
            rep = read_json(REPORTS_DIR / (str(r["sessionId"]) + ".json"))
            if not isinstance(rep, dict):
                rep = None

        status = str(r.get("status", ""))
        if status in ("busy", "shell"):
            working.append(title)
            continue
        if status not in ("idle", "waiting"):
            continue
        if sid in state["handled"] and updated <= state["handled"][sid]:
            handled_quiet += 1
            continue

        kind = "done"
        if status == "waiting":
            kind = "approval"
        elif rep and rep.get("turnError"):
            kind = "error"
        elif rep and rep.get("question"):
            kind = "question"

        queue.append({
            "id": sid,
            "title": title,
            "kind": kind,
            "waitedMin": round((now - updated) / 60000) if updated > 0 else 0,
            "since": updated,
            "cwd": str(r.get("cwd", "")),
            "question": rep.get("question") if rep else None,
            "approval": rep.get("approval") if rep else None,
            "error": rep.get("turnError") if rep else None,
        })
    queue.sort(key=lambda q: q["since"])
    return {"queue": queue, "working": working, "handledQuiet": handled_quiet}


def emit(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2), flush=True)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Queue helper for the session-manager skill.")
    p.add_argument("--self", dest="self_id", default="")
    p.add_argument("--mark", default="")
    p.add_argument("--unmark", default="")
    p.add_argument("--ignore", default="")
    p.add_argument("--unignore", default="")
    p.add_argument("--only", default="")
    p.add_argument("--state-file", default=str(DEFAULT_STATE))
    p.add_argument("--watch", action="store_true")
    p.add_argument("--interval", type=int, default=20)
    a = p.parse_args()

    state_path = Path(a.state_file).expanduser()
    only = [x.strip() for x in a.only.split(",") if x.strip()]

    if a.mark or a.unmark or a.ignore or a.unignore:
        state = read_state(state_path)
        if a.mark:
            state["handled"][a.mark] = now_ms()
            save_state(state_path, state)
            emit({"ok": True, "marked": a.mark})
        elif a.unmark:
            state["handled"].pop(a.unmark, None)
            save_state(state_path, state)
            emit({"ok": True, "unmarked": a.unmark})
        elif a.ignore:
            if a.ignore not in state["ignored"]:
                state["ignored"].append(a.ignore)
            save_state(state_path, state)
            emit({"ok": True, "ignored": a.ignore})
        else:
            state["ignored"] = [x for x in state["ignored"] if x != a.unignore]
            save_state(state_path, state)
            emit({"ok": True, "unignored": a.unignore})
        return

    if a.watch:
        # Sessions already waiting when the watch starts are not reported again.
        try:
            seen = {q["id"] for q in get_queue(a.self_id, only, state_path)["queue"]}
        except Exception:
            seen = set()
        while True:
            time.sleep(a.interval)
            try:
                current = get_queue(a.self_id, only, state_path)["queue"]
                for q in current:
                    if q["id"] not in seen:
                        print("READY: %s | %s | %s" % (q["title"], q["kind"], q["id"]), flush=True)
                seen = {q["id"] for q in current}
            except Exception as e:  # keep watching after a bad read
                print("WATCH-ERROR: %s" % e, flush=True)

    emit(get_queue(a.self_id, only, state_path))


if __name__ == "__main__":
    main()
