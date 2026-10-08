#!/usr/bin/env python3
"""oh-my-kiro team hooks — reminders and dispatch logging for the team skill.

Reads the Kiro hook event JSON on stdin. All modes only act when a team run is
active (.team/state.json in the project root) and never block the session:
every mode exits 0 and swallows its own errors.

Modes (passed as argv[1] from hooks/team-state.json):
  session-start  print goal + progress so a restarted session can resume
  prompt-submit  same reminder mid-session, with open task IDs
  pre-tool-use   append one DISPATCH line to .team/log.md
  post-tool-use  append one COMPLETE line (extracted worker STATUS) to .team/log.md
  stop           append a session-end line; warn when the run ended with open tasks
"""

import json
import os
import re
import sys
from datetime import datetime

LOG_NAME = "log.md"
STATE_NAME = "state.json"
LOG_MAX_BYTES = 512 * 1024


def payload():
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        data = {}
    return data if isinstance(data, dict) else {}


def first(data, *keys):
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return None


def project_dir(data):
    return (
        os.environ.get("KIRO_PROJECT_DIR")
        or first(data, "cwd", "project_dir", "projectDir")
        or os.getcwd()
    )


def team_dir(data):
    return os.path.join(project_dir(data), ".team")


def load_state(data):
    try:
        with open(os.path.join(team_dir(data), STATE_NAME)) as f:
            state = json.load(f)
        return state if isinstance(state, dict) else None
    except Exception:
        return None


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def append_log(data, line):
    try:
        os.makedirs(team_dir(data), exist_ok=True)
        path = os.path.join(team_dir(data), LOG_NAME)
        try:
            if os.path.getsize(path) > LOG_MAX_BYTES:
                os.replace(path, path + ".1")
        except OSError:
            pass
        with open(path, "a") as f:
            f.write(line.rstrip("\n") + "\n")
    except Exception:
        pass


def split_progress(state):
    tasks = state.get("tasks") or []
    done = [t for t in tasks if t.get("status") == "done"]
    open_tasks = [t for t in tasks if t.get("status") != "done"]
    return done, open_tasks, len(tasks)


def tool_input(data):
    value = first(data, "tool_input", "toolInput", "input", "tool_args", "args")
    return value if isinstance(value, dict) else {}


def worker_of(data):
    ti = tool_input(data)
    for key in ("subagent_type", "agent_type", "agent", "agent_name",
                "agentName", "worker", "name"):
        value = ti.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    tool_name = first(data, "tool_name", "toolName")
    return tool_name if isinstance(tool_name, str) and tool_name else "agent"


def response_text(data):
    for key in ("tool_response", "toolResponse", "response", "result",
                "output", "tool_output", "toolOutput"):
        value = data.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            return value
        try:
            return json.dumps(value)
        except Exception:
            return str(value)
    return ""


def task_label(task):
    label = "#%s (%s) %s" % (
        task.get("id", "?"),
        task.get("owner", "?"),
        task.get("title", ""),
    )
    return label.strip()


def reminder(state):
    goal = state.get("goal") or "(no goal recorded)"
    done, open_tasks, total = split_progress(state)
    lines = [
        "[oh-my-kiro team] Active team run — %s" % goal,
        "Progress: %d/%d tasks done." % (len(done), total),
    ]
    if open_tasks:
        lines.append("Open: %s" % "; ".join(task_label(t) for t in open_tasks))
    lines.append(
        "Continue the team workflow (skills/team) from .team/state.json — "
        "do not re-plan; dispatch history is in .team/log.md."
    )
    return "\n".join(lines)


def log_tail(data, n=10):
    try:
        with open(os.path.join(team_dir(data), LOG_NAME)) as f:
            lines = [line.rstrip("\n") for line in f if line.strip()]
        return lines[-n:]
    except Exception:
        return []


def on_session_start(data):
    state = load_state(data)
    if state is None or state.get("status") != "active":
        return
    print(reminder(state))
    if first(data, "source", "reason") in ("compact", "clear"):
        tail = log_tail(data)
        if tail:
            print("Recent dispatch log (last %d lines of .team/log.md):" % len(tail))
            for line in tail:
                print(line)


def on_prompt_submit(data):
    on_session_start(data)


def on_pre_tool_use(data):
    if load_state(data) is None:
        return
    ti = tool_input(data)
    label = first(ti, "description", "task")
    if not label:
        prompt = str(ti.get("prompt") or "").strip()
        label = prompt.splitlines()[0][:120] if prompt else "(no description)"
    append_log(data, "- [%s] DISPATCH %s — %s" % (now(), worker_of(data), label))


def on_post_tool_use(data):
    if load_state(data) is None:
        return
    match = re.search(r"STATUS:\s*(DONE|BLOCKED)", response_text(data) or "")
    status = match.group(1) if match else "no STATUS line found"
    append_log(data, "- [%s] COMPLETE %s — %s" % (now(), worker_of(data), status))


def on_stop(data):
    state = load_state(data)
    if state is None or state.get("status") != "active":
        return
    done, open_tasks, total = split_progress(state)
    if open_tasks:
        append_log(
            data,
            "- [%s] SESSION_END — %d/%d done, %d open" % (now(), len(done), total, len(open_tasks)),
        )
        print(
            "[oh-my-kiro team] Session ended with %d/%d task(s) still open. "
            "Next session resumes from .team/state.json — finish the open tasks, "
            "then run team-verify before shutdown." % (len(done), total)
        )
    else:
        append_log(data, "- [%s] SESSION_END — %d/%d done" % (now(), len(done), total))
        print(
            "[oh-my-kiro team] All %d task(s) done. Run team-verify (one verifier "
            "worker with fresh evidence), then mark state done and write the handoff." % total
        )


def main():
    data = payload()
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    handlers = {
        "session-start": on_session_start,
        "prompt-submit": on_prompt_submit,
        "pre-tool-use": on_pre_tool_use,
        "post-tool-use": on_post_tool_use,
        "stop": on_stop,
    }
    handler = handlers.get(mode)
    if handler is None:
        return
    try:
        handler(data)
    except Exception as exc:  # never block the session, but leave a trace
        print("team_hook: %r" % exc, file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()
