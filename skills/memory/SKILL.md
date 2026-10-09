---
name: memory
description: Save, recall, and forget persistent cross-session memories for this project. Use when the user says remember this, remember that, keep in mind, don't forget, recall what we said about, what do you remember about, or forget that; when they run /memory save, /memory forget, or /memory show; or when they state a preference, correction, or project fact that should survive the session. Writes one-fact markdown files plus a MEMORY.md index under the per-project memory store. Do not trigger for facts the repository already records or for ephemeral task state.
license: MIT
metadata:
  author: oniharnantyo
  version: 0.1.0
---

# Memory — Persistent Project Recall

Save, recall, and forget facts that should survive the session. Memories live
per project under `~/.kiro/memories/projects/<slug>-<hash16>/memory/`, derived
from the absolute project path by `hooks/scripts/memory_paths.py`. The format
contract lives in the `memory` steering doc (`steering/memory.md`) — follow it
exactly.

## Syntax

- `/memory save <fact>` — or the user saying "remember this/that ..." in any phrasing
- `/memory forget <topic>` — remove the matching memories
- `/memory show [topic]` — print the index and/or matching memory files

## Saving

Write the memory file **now** — no confirmation round-trip, even when the fact
looks minor. The user asked; saving is not a proposal.

1. Pick the best-fitting type — `user` (who they are, preferences), `feedback`
   (corrections, how they want work done), `project` (decisions, constraints,
   goals), or `reference` (pointers to material outside the repo).
2. Write one markdown file per the steering contract — frontmatter `name`
   (kebab-case slug, identical to the filename stem), `description` (one-line
   when-it's-relevant summary), `metadata.type` — with the fact in the body and
   `[[name]]` links to related memories.
3. Append exactly one index line to `MEMORY.md`:
   `- [Title](file.md) — hook`. Create the index and the memory directory
   (`ensure_memory_root()` in hooks/scripts/memory_paths.py) if missing.

**Never save what the repository already records** — code structure, git
history, fix recipes, steering docs — nor ephemeral task state. If a matching
memory already exists, update that file instead of creating a duplicate.

## Forgetting

Find the memory file(s) matching the topic — by index line, `name`, or body
content — delete each file, and remove its line from `MEMORY.md`. Forgetting
means gone — no tombstones, no "archived" copies.

## Showing

Print the `MEMORY.md` index; for a named topic, also print the matching memory
file bodies. Showing is read-only — it never writes.
