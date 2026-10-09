#!/usr/bin/env python3
"""oh-my-kiro memory hooks — stamp every user turn for the auto-capture gate.

Runs on UserPromptSubmit. Writes two tiny stamp files into the project's
memory root (see memory_paths.py): .turn-start (epoch seconds of this turn)
and .user-prose ("1" when the prompt had >= 3 words of real prose, else "0").
The Stop-side extract hook (memory_extract_hook.py) reads them to decide
whether to spawn a memory-extractor sidecall. Tolerant by design: any failure
exits 0 silently so it can never block a session.
"""

import json
import os
import sys
import time

STAMP_TURN_START = ".turn-start"
STAMP_USER_PROSE = ".user-prose"
MIN_PROSE_WORDS = 3


def prompt_text():
    """USER_PROMPT env wins; else tolerate stdin JSON in snake/camelCase."""
    value = os.environ.get("USER_PROMPT")
    if isinstance(value, str) and value.strip():
        return value
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        return ""
    if not isinstance(data, dict):
        return ""
    for key in ("user_prompt", "userPrompt", "prompt", "content"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def write_stamp(root, name, text):
    try:
        with open(os.path.join(root, name), "w") as f:
            f.write(text)
    except Exception:
        pass


def main():
    try:
        from memory_paths import ensure_memory_root

        text = prompt_text()
        root = ensure_memory_root()
        write_stamp(root, STAMP_TURN_START, str(int(time.time())))
        has_prose = "1" if len(text.split()) >= MIN_PROSE_WORDS else "0"
        write_stamp(root, STAMP_USER_PROSE, has_prose)
    except Exception:
        pass  # never block the session on a stamping failure
    sys.exit(0)


if __name__ == "__main__":
    main()
