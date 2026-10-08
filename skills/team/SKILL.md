---
name: team
description: Parallel subagent team executor (inspired by oh-my-claudecode's team skill). Use when the user explicitly asks to run a team of subagents or workers in parallel, uses "team N:agent-type" phrasing (e.g. "team 3:executor fix all TypeScript errors"), or asks to fan one goal out across planner/executor/verifier workers on a shared task list. Do not trigger for ordinary tasks a single agent can do directly.
license: MIT
metadata:
  author: oniharnantyo
  version: 0.1.0
---

# Team — Parallel Subagent Executor

Spawn N coordinated subagents working a shared task list, then verify their work with a
fresh pass. Pipeline: **team-plan → team-exec → team-verify → team-fix (loop) → report**.

## Prerequisite — setup is mandatory

The pipeline dispatches **installed worker agents** by name; without them there is
nothing to dispatch. Before the first team run:

1. **Check for the worker agents** — `planner.md`, `executor-low.md`,
   `executor-medium.md`, `executor-high.md`, `debugger.md`, `verifier.md`,
   `critic.md` — in either location:
   - project: `.kiro/agents/` in this workspace
   - global: `~/.kiro/agents/`
2. **If missing, run the `setup` skill now** (it asks for scope and executor models,
   then installs the agents, hooks, and steering). Do not start the pipeline without
   it — tell the user setup is required and run it first.

### Scope frequency

| Scope | Setup runs | Why |
| --- | --- | --- |
| **Project** (`.kiro/`) | **Once per project** | Agents are created inside that project's `.kiro/agents/` — a new project needs setup run again there |
| **Global** (`~/.kiro/`) | **Once per machine** | Agents live in `~/.kiro/agents/` and serve every project |

If the user runs teams across many projects, recommend global scope — it is a
one-time install. Project scope is the right choice when the team config should be
committed with the repo or kept workspace-specific.

## Syntax

- `team 3:executor-medium "fix all TypeScript errors"` — 3 medium-tier executor workers in parallel
- `team "small task"` — you decompose and pick the default team (executors + 1 verifier)
- Worker types: `planner`, `debugger`, `verifier`, `critic`, and `executor` in three complexity tiers — `executor-low`, `executor-medium`, `executor-high`
- Cap the team at **5** workers. Broadcasts are expensive; more workers ≠ faster.

## Worker roster

| Worker | Purpose |
| --- | --- |
| `planner` | Goal → file-scoped tasks with owners; writes no code |
| `executor-low` | Trivial one-edit tasks |
| `executor-medium` | Scoped multi-file tasks (default tier) |
| `executor-high` | Complex structural tasks |
| `debugger` | Root cause + minimal fix in the fix loop |
| `verifier` | PASS/FAIL verdict from fresh evidence |
| `critic` | Adversarial gate on plans/diffs |

Each worker is a Kiro custom agent installed by setup, carrying its role prompt,
tools, and pre-approved permissions (executors may write and run test/build commands;
planner, verifier, and critic are read-only). Dispatch them **by name**.

## Rules of the runtime (why the protocol looks like this)

- Kiro sub-agents are **ephemeral and stateless**: they run with isolated context and no
  memory of your conversation. Every dispatch must be fully self-contained — the agent
  carries the role, so pass the task details, context, and the output contract.
- There is **no atomic task claiming**: workers cannot grab work. You pre-assign owners.
- Parallelism comes from dispatching **all independent workers together** — state the
  full task graph up front and ask for independent tasks to run in parallel.
  Sequential dispatches when tasks are independent are a bug.
- **Sub-agents share the session's permission configuration.** The installed agents
  pre-approve standard read/write/test commands; if workers still stall on approval
  prompts, pre-approve the relevant commands in the session's permissions rules.
- Never put secrets in worker prompts. Pass file pointers (`src/x.ts:40-80`), not file dumps.

## Phase 0 — Initialize the team workspace

Create the shared state at `.team/` in the project root:

```bash
mkdir -p .team/handoffs && python3 - <<'PY'
import json, datetime
tasks = [
    {"id": "1", "title": "Fix null handling in src/a.ts", "owner": "executor-medium", "status": "pending"},
    {"id": "2", "title": "Fix imports in src/b.ts", "owner": "executor-low", "status": "pending"},
]
json.dump({"goal": "<the user's goal>", "status": "active",
           "created": datetime.datetime.now().isoformat(timespec="seconds"),
           "tasks": tasks}, open(".team/state.json", "w"), indent=2)
PY
```

Task IDs are strings ("1", "2", ...). Schema: `{goal, status: active|done, created, tasks: [{id, title, owner, status}]}`.

## Phase 1 — team-plan

Decompose the goal into **file-scoped subtasks**:

- One file cluster per task; **two tasks must never edit the same file** (workers race).
- 3–6 tasks is the sweet spot; give each task verifiable acceptance criteria
  (a test that can pass, a build that can go green, a grep that can hit).
- Pre-assign each task an `owner` type. For a large goal, dispatch the `planner`
  sub-agent first to produce the decomposition, review it, then continue.
- Pick the executor tier by task complexity: a single obvious edit in one file →
  `executor-low`; a scoped multi-file change with clear criteria → `executor-medium`;
  structural, cross-cutting, or invariant-sensitive work → `executor-high`. When torn
  between two tiers, take the higher one — under-thinking structural work costs more
  rework than over-thinking simple work costs tokens.
- Write the plan into `.team/state.json` (snippet above). Suggest the user add
  `.team/` to `.gitignore`.

## Phase 2 — team-exec (parallel dispatch)

Dispatch all workers **in one batch** — state the full task graph up front and ask for
independent tasks to run in parallel (sub-agents run concurrently with isolated context;
with workflows enabled the main agent may use background delegation instead).

Dispatch **by agent name**, e.g. "run these in parallel: `executor-medium` on task 1,
`executor-low` on task 2". Each dispatch needs:

1. The task (title, files, acceptance criteria).
2. Context the worker can't discover cheaply: conventions found, related tests, gotchas.
3. The output contract (below).

**Worker output contract** (put this verbatim in every dispatch):

> End your final message with exactly `STATUS: DONE` or `STATUS: BLOCKED`, then
> **Changes Made** (each with `file:line` references and one-line rationale),
> **Verification** (the actual build/test commands run and their fresh output),
> and a 1–2 sentence **Summary**.

While workers run, the team-state hooks (installed by setup) log every
dispatch/completion to `.team/log.md` automatically; consult it if you lose track after
a compaction.

As each worker returns, mark its task done:

```bash
python3 - <<'PY'
import json
d = json.load(open(".team/state.json"))
for t in d["tasks"]:
    if t["id"] == "<task-id>":
        t["status"] = "done"
json.dump(d, open(".team/state.json", "w"), indent=2)
PY
```

If a worker returns `STATUS: BLOCKED`, do not re-dispatch the same prompt blindly —
read its blocker, adjust the task, or route it to `debugger` in the fix loop.

## Phase 3 — team-verify

After all tasks are done, dispatch **one** `verifier` sub-agent with the acceptance
criteria and how to check them. Verification is a separate pass — **never
self-approve work from your own context**. Accept only `PASS` / `FAIL` /
`INCOMPLETE` with fresh evidence (test output, build exit code, diagnostics).

## Phase 4 — team-fix (loop)

On `FAIL`: dispatch `debugger` (root cause, minimal fix) and/or the same
`executor-<tier>` that owned the failed item, then re-verify. **Max 3 loops**, then
report honestly what still fails and why. A red report is better than a false green one.

## Phase 5 — shutdown

1. Mark the run finished:

```bash
python3 - <<'PY'
import json
d = json.load(open(".team/state.json"))
d["status"] = "done"
json.dump(d, open(".team/state.json", "w"), indent=2)
PY
```

2. Write a handoff doc at `.team/handoffs/<date>-<slug>.md` — 10–20 lines:
   decisions made, rejected alternatives, risks left behind.
3. Final report to the user: per-task outcome with `file:line` evidence, the
   verification result, and any open items.

## Supporting Kiro hooks (installed by the setup skill)

| Trigger | Team support |
| --- | --- |
| `SessionStart` | If `.team/state.json` is active, injects the goal + progress so a restarted session resumes instead of re-planning |
| `UserPromptSubmit` | Same reminder mid-session, with open task IDs |
| `PreToolUse` (subagent tools) | Logs every dispatch (worker type + task) to `.team/log.md` |
| `PostToolUse` (subagent tools) | Logs every worker completion to `.team/log.md` |
| `Stop` | Appends a session-end summary; flags runs that ended with open tasks |

A separate always-on `PreToolUse` (shell tools) guard blocks clearly destructive
commands (`rm -rf /` or `~`, force push, disk wipes). See the power README for how to
disable it.

## Known gotchas (carried over from upstream)

- **Setup first** — project scope needs it once per project; global scope once per machine.
- Pre-assign owners — no atomic claiming.
- Stateless workers → self-contained dispatches (task + context + contract).
- Cap workers at 5; broadcasts are expensive.
- Secrets never go into worker prompts.
- Task IDs are strings.
