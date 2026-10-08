#!/usr/bin/env python3
"""oh-my-kiro bash guard — block clearly destructive shell commands.

Reads the Kiro hook event JSON on stdin. On a destructive-pattern match it
exits 2 with a stderr reason, which Kiro turns into a blocked tool call for
PreToolUse hooks. Unexpected errors never break the session (stderr trace,
exit 0). Set "enabled": false on the bash-guard hook to disable.
"""

import json
import re
import sys

# label, regex — conservative on purpose: a missed exotic is better than a
# false positive blocking legitimate work. Recursive/forced deletes are only
# blocked when targeted at absolute paths outside any project (/, ~, $HOME).
DENY_RULES = [
    ("recursive/forced delete at / or ~",
     r"\brm\s+(-[a-zA-Z]+\s+)*-[a-zA-Z]*[rf][a-zA-Z]*\s+(--\s+)?(?:/[\S]*|~/?[\S]*|\$HOME[\S]*)"),
    ("force push",
     r"\bgit\s+push\b[^;&|<>]*(--force\b|--force-with-lease\b|\s-f\b)"),
    ("system power/reboot command",
     r"(?<!npm run )(?<!npx )(?<!make )\b(shutdown|reboot|halt|poweroff)\b"),
    ("disk destruction",
     r"\bmkfs\b|\bdd\b[^;&|<>]*of=/dev/|\bdiskutil\s+erase"),
    ("SQL DROP statement",
     r"\bdrop\s+(table|database|schema)\b"),
    ("world-writable chmod at /",
     r"\bchmod\s+-R\s+777\s+/(?:\s|$)"),
    ("shell history wipe",
     r"\bhistory\s+-c\b|\brm\b[^;&|<>]*\s\.?(bash_)?history\b"),
]


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


def bash_command(data):
    ti = first(data, "tool_input", "toolInput", "input", "tool_args", "args")
    if not isinstance(ti, dict):
        ti = {}
    command = first(ti, "command", "cmd", "script")
    return command if isinstance(command, str) else ""


def main():
    data = payload()
    command = bash_command(data)
    if not command.strip():
        sys.exit(0)
    try:
        for label, pattern in DENY_RULES:
            if re.search(pattern, command, re.IGNORECASE):
                sys.stderr.write(
                    "oh-my-kiro guard: blocked %s — command: %s\n"
                    % (label, command.strip()[:200])
                )
                sys.exit(2)
    except Exception as exc:  # never break the session, but leave a trace
        print("guard_hook: %r" % exc, file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()
