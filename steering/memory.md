---
inclusion: auto
name: memory
description: Persistent memory contract for this power. Load when the user asks to remember, recall, or forget something across sessions, or when writing to or cleaning up the per-project memory store.
---

# Persistent memory

Memories are per-project markdown files stored under
`~/.kiro/memories/projects/<slug>-<hash16>/memory/` — the `<slug>-<hash16>`
folder is derived from the absolute project path by
`hooks/scripts/memory_paths.py`, so two projects sharing a basename never
collide. `MEMORY.md` in that folder is the index.

## Format

- **One fact per file.** Each memory file's frontmatter carries
  - `name` — a kebab-case slug, identical to the filename stem;
  - `description` — one line saying when the memory is relevant;
  - `metadata.type` — exactly one of `user`, `feedback`, `project`, `reference`.
- The body is the fact itself, plus whatever is needed to act on it. Link
  related memories in the body with `[[name]]`.
- **`MEMORY.md` is index-only** — one line per memory,
  `- [Title](file.md) — hook`, where the hook says when the memory matters.
  Never store memory content in the index.

## What not to save

Anything this repository already records — code structure, git history, fix
recipes, steering docs — and ephemeral task state. Memory is for what survives
leaving the repo.

## Staleness

Memories reflect the moment they were written. Before acting on a memory that
names a file, flag, command, or path, verify it still exists and still applies.
A memory the repo has contradicted is updated or deleted — never silently
ignored.

## Saving and forgetting

- When the user asks to remember something, save immediately — no confirmation
  round-trip.
- Update the existing memory file instead of creating a near-duplicate.
- On "forget X", remove the memory file and its `MEMORY.md` index line.

The `/memory` skill (`skills/memory/SKILL.md`) implements this contract.
