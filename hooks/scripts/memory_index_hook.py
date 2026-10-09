#!/usr/bin/env python3
"""oh-my-kiro memory hooks — recall the project's persistent memory index.

Prints the project's MEMORY.md (under ~/.kiro/memories/projects/) into agent
context at session start so preferences, feedback, and project context survive
across conversations. Tolerant by design: any failure prints nothing and the
hook always exits 0 so it can never block a session.
"""

import sys
import time

EXTRACTION_MARKER = ".last-extraction"
SECONDS_PER_DAY = 86400


def days_since_last_extraction(root):
    """Days since the last auto-capture, or None when it has never run."""
    try:
        with open(root / EXTRACTION_MARKER) as f:
            tokens = f.read().split()
        epoch = int(tokens[0])
    except Exception:
        return None
    return max(0, (int(time.time()) - epoch) // SECONDS_PER_DAY)


def print_memory_index():
    from memory_paths import MEMORY_INDEX, resolve_memory_root

    root = resolve_memory_root()
    index = root / MEMORY_INDEX
    with open(index) as f:
        contents = f.read()
    print(
        "Contents of %s (persistent memory that survives across conversations):"
        % index
    )
    print(contents)
    days = days_since_last_extraction(root)
    if days is None:
        print("Auto-capture has not run for this project yet.")
    else:
        print("Memory last updated %d day(s) ago by auto-capture." % days)


def main():
    try:
        print_memory_index()
    except Exception:
        pass  # never block the session on a missing or broken memory index
    sys.exit(0)


if __name__ == "__main__":
    main()
