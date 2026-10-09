#!/usr/bin/env python3
"""oh-my-kiro memory hooks — spawn the background memory-extractor sidecall.

Runs on Stop. A gate chain decides whether this turn produced material worth
capturing; any failed gate means no spawn and an immediate exit 0:

  1. OMK_MEMORY_EXTRACTOR is set -> we ARE the sidecall; never recurse (the
     nested kiro-cli inherits this hook's environment).
  2. memory root exists          -> nothing stamped for this project yet (the
     turn hook creates the root on its first stamp).
  3. .user-prose == "1"          -> the prompt had >= 3 words of real prose.
  4. stand-down                  -> some *.md in the root is newer than
     .turn-start, so the main agent already saved this turn; a missing or
     unparseable .turn-start also skips (conservative).
  5. .extract.lock fresh         -> its epoch is younger than 600 s, so an
     extraction is already running; a stale or unreadable lock proceeds.

On pass, resolve the session transcript (stdin session_id, else the newest
~/.kiro/sessions/*/sess_*/messages.jsonl by mtime), write .extract.lock, then
spawn `kiro-cli chat --agent memory-extractor ...` fully detached, logging
stdout+stderr to .extract.log. The sidecall (agents/memory-extractor.md)
writes .last-extraction and removes the lock when it finishes.
"""

import glob
import json
import os
import subprocess
import sys
import time

STAMP_TURN_START = ".turn-start"
STAMP_USER_PROSE = ".user-prose"
STAMP_LAST_EXTRACTION = ".last-extraction"
LOCK_NAME = ".extract.lock"
LOG_NAME = ".extract.log"
LOCK_STALE_SECONDS = 600
SPAWN_PROMPT = (
    "Extract session memories. Transcript JSONL: %s. Memory root: %s. "
    "Last-extraction stamp: %s. Read your agent instructions and follow "
    "them exactly."
)


def payload():
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def first_str(data, *keys):
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def project_dir():
    return os.environ.get("KIRO_PROJECT_DIR") or os.getcwd()


def read_stamp(root, name):
    """Stripped file contents, or "" when missing/unreadable."""
    try:
        with open(os.path.join(root, name)) as f:
            return f.read().strip()
    except Exception:
        return ""


def main_agent_saved_this_turn(root):
    """Stand-down gate: True when a *.md is newer than .turn-start (or the
    stamp is missing/unparseable — conservative skip)."""
    turn_start = read_stamp(root, STAMP_TURN_START)
    try:
        turn_start = int(turn_start.split()[0]) if turn_start else None
    except (ValueError, IndexError):
        turn_start = None
    if turn_start is None:
        return True
    try:
        for name in os.listdir(root):
            if not name.endswith(".md"):
                continue
            try:
                if os.path.getmtime(os.path.join(root, name)) > turn_start:
                    return True
            except OSError:
                continue
    except OSError:
        return True  # cannot inspect the root -> conservative skip
    return False


def extraction_running(root):
    """Lock gate: True when .extract.lock holds an epoch younger than 600 s.
    Missing or unparseable counts as stale -> proceed."""
    tokens = read_stamp(root, LOCK_NAME).split()
    if not tokens:
        return False
    try:
        epoch = int(tokens[-1])  # '<pid> <epoch>' — last token is the epoch
    except ValueError:
        return False
    return (time.time() - epoch) < LOCK_STALE_SECONDS


def glob_transcripts(stem):
    try:
        pattern = os.path.join(
            os.path.expanduser("~"), ".kiro", "sessions", "*", stem,
            "messages.jsonl",
        )
        return glob.glob(pattern)
    except Exception:
        return []


def newest(paths):
    def mtime(path):
        try:
            return os.path.getmtime(path)
        except OSError:
            return 0

    return max(paths, key=mtime) if paths else None


def resolve_transcript(data):
    """Exact session_id match first, else the newest transcript anywhere."""
    session_id = first_str(data, "session_id", "sessionId")
    if session_id:
        matches = glob_transcripts("sess_%s" % session_id)
        matches += glob_transcripts(session_id)
        found = newest(matches)
        if found:
            return found
    return newest(glob_transcripts("sess_*"))


def write_lock(root):
    try:
        with open(os.path.join(root, LOCK_NAME), "w") as f:
            f.write("%d %d" % (os.getpid(), int(time.time())))
    except Exception:
        pass


def spawn_extractor(transcript, root):
    # Test seam: OMK_KIRO_CLI points the spawn at a fake kiro-cli binary so
    # tests can observe argv/env without a real CLI install.
    kiro_bin = os.environ.get("OMK_KIRO_CLI", "kiro-cli")
    log_path = os.path.join(root, LOG_NAME)
    try:
        with open(log_path, "w") as log:
            subprocess.Popen(
                [
                    kiro_bin,
                    "chat",
                    "--agent",
                    "memory-extractor",
                    "--trust-tools=fs_read,fs_write",
                    "--no-interactive",
                    SPAWN_PROMPT % (transcript, root, os.path.join(root, STAMP_LAST_EXTRACTION)),
                ],
                env=dict(os.environ, OMK_MEMORY_EXTRACTOR="1"),
                cwd=project_dir(),
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
    except Exception:
        try:  # no sidecall will clean the lock up -> let it expire now
            os.remove(os.path.join(root, LOCK_NAME))
        except OSError:
            pass


def run():
    if "OMK_MEMORY_EXTRACTOR" in os.environ:
        return
    from memory_paths import resolve_memory_root

    data = payload()
    root = resolve_memory_root()
    if not root.is_dir():
        return
    if read_stamp(root, STAMP_USER_PROSE) != "1":
        return
    if main_agent_saved_this_turn(root):
        return
    if extraction_running(root):
        return
    transcript = resolve_transcript(data)
    if not transcript:
        return
    write_lock(root)
    spawn_extractor(str(transcript), root)


def main():
    try:
        run()
    except Exception:
        pass  # never block the session on a failed extraction attempt
    sys.exit(0)


if __name__ == "__main__":
    main()
