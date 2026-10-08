---
inclusion: auto
name: team
description: Active oh-my-kiro team run reminder. Load when the user asks about team progress, resuming a team run, or what tasks are open.
---

# Active team run

If a `.team/state.json` file exists in the project root with `"status": "active"`, a
parallel team run is in progress (started by the `team` skill, installed with this
power).

When that file exists:

- **Resume, don't re-plan.** Read `.team/state.json` for the goal and task list, and
  `.team/log.md` for the dispatch history. Continue the team workflow from where it
  stopped — never re-decompose work that is already recorded.
- **Keep owners pre-assigned.** Workers cannot claim tasks; every task's `owner` was
  set during team-plan.
- **Mark progress as it happens.** Update each task's `status` to `done` in
  `.team/state.json` as its worker returns, and dispatch verification only after all
  tasks are done.
- **Verify separately.** Never self-approve worker output; dispatch a fresh verifier
  pass (see the `team` skill's Phase 3).
- **Finish cleanly.** Set `"status": "done"`, write a handoff doc in
  `.team/handoffs/`, and report per-task outcomes with `file:line` evidence.

The full pipeline lives in the `team` skill: `skills/team/SKILL.md`.
