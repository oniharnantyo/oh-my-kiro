---
name: setup
description: Set up oh-my-kiro on this machine — install the team worker agents, team-state hooks, and team steering into a Kiro scope, and pick the model for each executor tier. Use when the user asks to set up oh-my-kiro, install/configure the team agents or hooks, initialize the power, or change which models the executors use.
license: MIT
metadata:
  author: oniharnantyo
  version: 0.1.0
---

# Setup — install agents, hooks, and steering

Installs the oh-my-kiro payload (worker agents, team-state + bash-guard hooks, team
steering) into a Kiro configuration scope, with a model chosen per executor tier.

**Setup is required before the first team run** — the `team` skill dispatches the
installed worker agents by name, so nothing works until this has run at least once.

**Ask before you install.** This skill must gather the answers below and get user
confirmation before running the installer — never install silently.

## Scope frequency (tell the user)

| Scope | Setup runs | Why |
| --- | --- | --- |
| **Project** (`.kiro/`) | **Once per project** | Agents are created inside that project's `.kiro/agents/` — every new project needs setup run again |
| **Global** (`~/.kiro/`) | **Once per machine** | Agents live in `~/.kiro/agents/` and serve every project |

Recommend global when the user works across many projects; recommend project when the
team config should live with the repo or stay workspace-specific.

## Step 1 — Locate the power root

The installer lives beside this skill: `<power-root>/skills/setup/scripts/install.py`.

1. Resolve this SKILL.md's absolute path; the script is at `scripts/install.py` in the
   same directory.
2. If the path can't be resolved that way, search for it:
   - `~/.kiro/powers/**/skills/setup/scripts/install.py`
   - the current workspace: `**/skills/setup/scripts/install.py` where the parent chain
     contains a `plugin.json` with `"name": "oh-my-kiro"`.
3. Verify with `python3 <script> --help` (exits 0 and prints usage).

## Step 2 — Ask the scope question

**First detect whether the power is installed inside the current project.** If the
power root is inside the workspace (e.g. `<project>/powers/oh-my-kiro/` or any path
under the current working directory), the power is project-installed: **use
`--scope project` and do not ask about global.**

Otherwise (the power lives in a global location such as `~/.kiro/powers/`), ask the
user:

> Where should oh-my-kiro install its agents, hooks, and steering?
>
> 1. **Project** — `.kiro/` in this workspace only (agents are created per project, so
>    **each new project needs setup run again**; can be committed with the repo)
> 2. **Global** — `~/.kiro/` for all projects on this machine (**run once**; agents and
>    hooks apply everywhere, including the bash guard)

## Step 3 — Ask the preset question

Fetch **https://kiro.dev/docs/models.md** to confirm current model names, then ask
which cost preset to use:

> Which model preset should the team use?
>
> | Preset | low (executor-low) | medium (planner, verifier, executor-medium) | high (executor-high, debugger, critic) |
> | --- | --- | --- | --- |
> | **cheap** | `qwen3-coder-next` (0.05x) | `minimax-m2.5` (0.25x) | `glm-5` (0.5x) |
> | **medium** (default) | `minimax-m2.5` (0.25x) | `claude-haiku-4.5` (0.4x) | `claude-sonnet-5.5` (1.3x) |
> | **premium** | `claude-haiku-4.5` (0.4x) | `claude-sonnet-5.5` (1.3x) | `claude-opus-5.5` (2.0x) |
> | **openai** | `gpt-5.6-luna` (0.6x) | `gpt-5.6-terra` (2.2x) | `gpt-5.6-terra` (2.2x) |
>
> - **cheap** — open-weight models throughout; best for high-volume or cost-sensitive runs.
> - **medium** — cheap for trivial work, Haiku for scoped work, Sonnet 5.5 for structural work.
> - **premium** — Haiku as the floor, Sonnet 5.5 for scoped work, Opus 5.5 for structural work.
> - **openai** — GPT-5.6 models throughout: Luna for light work, Terra for the rest.

If the user wants a custom mix instead of a preset, accept per-tier overrides
(`--model-low`, `--model-medium`, `--model-high`) or any model IDs they name.

**On reasoning effort:** Kiro agent configs have no effort field — effort is a
session/model setting, not an agent setting. If the user asks for per-tier effort,
explain this and point them at `/effort` or `chat.modelDefaults` in
`~/.kiro/settings/cli.json` (see https://kiro.dev/docs/models/effort.md).

## Step 4 — Confirm and install

1. Show the exact plan and ask for confirmation:
   - power root, scope, target directory (`<cwd>/.kiro` or `~/.kiro`)
   - the chosen preset and the three resolved models
   - what gets written: `agents/*.md` (7 agents), `steering/team.md`,
     `hooks/*.json` + `hooks/scripts/*` (team state + bash guard)
2. Run a dry run first: `python3 <script> --scope <scope> --preset <preset> --dry-run`
3. On confirmation, run it for real (drop `--dry-run`).

```bash
# project scope, medium preset (default)
python3 <power-root>/skills/setup/scripts/install.py \
  --scope project \
  --preset medium

# other presets
python3 <power-root>/skills/setup/scripts/install.py --scope project --preset cheap
python3 <power-root>/skills/setup/scripts/install.py --scope project --preset premium
python3 <power-root>/skills/setup/scripts/install.py --scope project --preset openai
```

The installer:

- copies the 7 worker agents to `<target>/.kiro/agents/` and injects the preset
  `model:` into each agent's frontmatter,
- copies `steering/team.md` to `<target>/.kiro/steering/`,
- copies the hook JSON files and scripts to `<target>/.kiro/hooks/`, rewriting the
  script path in hook commands for the scope (`.kiro/hooks/scripts/...` for project,
  `~/.kiro/hooks/scripts/...` for global).

Useful flags: `--target <dir>` to install elsewhere, `--power-root <dir>` if the script
can't infer it, `--dry-run` to preview.

## Step 5 — Verify and report

1. Confirm the files exist:
   ```bash
   ls <target>/.kiro/agents/ <target>/.kiro/steering/ <target>/.kiro/hooks/
   ```
2. Smoke-test the hooks:
   ```bash
   echo '{}' | python3 <target>/.kiro/hooks/scripts/team_hook.py session-start
   echo '{"tool_input":{"command":"git push --force"}}' | python3 <target>/.kiro/hooks/scripts/guard_hook.py; echo "exit=$? (expect 2)"
   ```
3. Report to the user: scope, target, per-tier models, files written, and that a new
   Kiro session is needed for agents/hooks to load. Mention the `team` skill is now
   ready: `team 3:executor-medium "<task>"`.
4. If the scope was **project**, remind the user that setup runs **once per project** —
   a different project needs it run again there. If **global**, note it is installed
   once for every project on this machine.

## Changing presets later

Re-run this skill (or the installer directly with a new `--preset`) — the installer
overwrites the copied agents with the new models. Nothing else changes.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `does not look like the oh-my-kiro power root` | Pass `--power-root <dir>` pointing at the directory containing `plugin.json` |
| Agents don't appear in the agent picker | New session required; confirm files landed in `.kiro/agents/` and that the workspace is trusted |
| Hooks don't fire | Confirm `.kiro/hooks/*.json` exist and `python3` is on PATH; hook commands run from the project root |
| Workers stall on permission prompts | Executor agents pre-approve standard commands; for custom setups add the workers to `toolsSettings.subagent.trustedAgents` of the orchestrating agent |

## References

- [Creating custom agents](https://kiro.dev/docs/custom-agents/creating.md)
- [Hooks](https://kiro.dev/docs/hooks.md)
- [Models](https://kiro.dev/docs/models.md)
