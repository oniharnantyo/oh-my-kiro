---
name: setup
description: Set up oh-my-kiro on this machine — install the team worker agents, team-state hooks, and team steering into a Kiro scope, pick the model for each executor tier, and opt in to the persistent-memory system. Use when the user asks to set up oh-my-kiro, install/configure the team agents or hooks, initialize the power, change which models the executors use, enable or disable the memory or auto-capture features, or refresh/update an existing installation after a power update.
license: MIT
metadata:
  author: oniharnantyo
  version: 0.1.0
---

# Setup — install agents, hooks, and steering

Installs the oh-my-kiro payload (worker agents, team-state + bash-guard hooks, team
steering, and optionally the persistent-memory system) into a Kiro configuration
scope, with a model chosen per executor tier.

**Setup is required before the first team run** — the `team` skill dispatches the
installed worker agents by name, so nothing works until this has run at least once.

**Ask before you install.** This skill must gather the answers below and get user
confirmation before running the installer — never install silently.

**Always inspect before installing.** Every invocation starts by checking the
candidate scopes for an existing oh-my-kiro install (Step 2) — re-running setup is
also how a power update reaches already-set-up projects.

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

## Step 2 — Inspect any existing install (always, before asking anything)

Re-running setup is how a power update reaches scopes that were set up earlier — and
the most common gap is a project whose `.kiro/` predates the current payload (e.g.
set up before the memory system existed). On **every** invocation, check both
candidate scopes first:

1. **Existence.** Project: `./.kiro/` containing any of `agents/`, `hooks/`,
   `steering/`. Global: `~/.kiro/` containing the payload (`steering/team.md`,
   `hooks/team-state.json`, worker agents).
2. **Drift.** For each installed scope, compare against the power's current payload
   (`diff -q <target>/.kiro/<path> <power-root>/<path>`). Verbatim-copied files
   (hook scripts, `steering/*.md`, `skills/memory/SKILL.md`) diff directly. Two
   file kinds carry install-time rewrites — ignore those lines or they will always
   look drifted: agent frontmatter `model:` (injected per preset) and hook
   `command:` paths (`~/.kiro/...` in global scope, `.kiro/...` in project scope).
3. **Installed models.** Read `model:` from the installed agents to learn the
   current tier models (low: `executor-low.md`; medium: `executor-medium.md` and
   `verifier.md`; high: `planner.md`, `executor-high.md`, `debugger.md`, `critic.md`).

Report the verdict, then shape the rest of the flow:

- **Fresh install** — nothing found: continue with the questions below.
- **Installed and current** — say so ("oh-my-kiro is already installed here:
  low=X, medium=Y, high=Z, memory on/off") and ask whether to change anything
  (preset, memory, auto-capture) or leave it as is.
- **Installed but missing or drifted files** — name the gap explicitly ("set up
  with an older power: the current power adds `hooks/memory-index.json` and
  `steering/memory.md`, updates `hooks/scripts/team_hook.py`") and recommend a
  refresh. **On refresh, preserve the installed models** by passing them as
  explicit `--model-low/--model-medium/--model-high` overrides (from the `model:`
  lines read above), unless the user explicitly asks to change preset — a bare
  re-run applies the requested preset to every worker agent, silently rewriting
  models (and preset tables move as Kiro's model lineup changes).

## Step 3 — Ask the scope question

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

## Step 4 — Ask the preset question

Fetch **https://kiro.dev/docs/models.md** to confirm current model names, then ask
which cost preset to use:

> Which model preset should the team use?
>
> | Preset | low (executor-low) | medium (verifier, executor-medium) | high (planner, executor-high, debugger, critic) |
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

## Step 5 — Ask the memory questions

oh-my-kiro has an opt-in persistent-memory system (memories are stored per project
under `~/.kiro/memories/`). Ask these after the preset question, defaulting to
**no** when the user is indifferent:

> **Enable persistent memory?** Each project gets its memory index injected at
> session start (a steering file plus a session-start hook) so preferences,
> feedback, and project context survive across conversations. The `/memory`
> skill for reading and editing it comes from the power itself — nothing to
> install per project.

> *(only if yes)* **Enable background auto-capture?** Adds a Stop hook that makes
> one cheap background model call per turn (`minimax-m2.1`) to extract durable
> facts, plus a `memory-extractor` agent that performs the extraction.

Map the answers to installer flags and spell out the consequences:

| Answer | Flags | What the user gets |
| --- | --- | --- |
| No memory (default) | *(omit the memory flags)* | Nothing extra; re-running setup **removes** any memory files a previous install added |
| Memory yes | `--memory on` | `steering/memory.md` and the session-start recall hook (`hooks/memory-index.json` + its scripts). The `/memory` skill is **not** copied — the installed power provides it on demand |
| Auto-capture yes | `--memory on --auto-capture on` | Additionally the Stop-hook sidecall (`hooks/memory-turn.json`, `hooks/memory-extract.json` + their scripts) and the `memory-extractor` agent |

`--auto-capture on` requires `--memory on` (the installer rejects it otherwise).
Before installing with auto-capture, the installer runs `kiro-cli chat
--list-models` and prints a visible warning if `minimax-m2.1` is missing —
extraction sidecalls would then silently fall back to the account default model,
possibly at a much higher cost. If it cannot run the check at all it says so.
Relay either warning to the user before they confirm.

## Step 6 — Confirm and install

1. Show the exact plan and ask for confirmation:
   - power root, scope, target directory (`<cwd>/.kiro` or `~/.kiro`)
   - the chosen preset and the three resolved models
   - the memory answers (persistent memory / auto-capture — default: no)
   - whether this is a fresh install or a refresh of an existing one (Step 2), and
     what will be added, updated, or removed by it
   - what gets written: `agents/*.md` (7 agents), `steering/team.md`,
     `hooks/*.json` + `hooks/scripts/*` (team state + bash guard); with
     `--memory on`, additionally the memory payload listed above
2. Run a dry run first (include the memory flags when the user opted in):
   `python3 <script> --scope <scope> --preset <preset> --dry-run`
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

# with persistent memory and background auto-capture
python3 <power-root>/skills/setup/scripts/install.py \
  --scope project \
  --preset medium \
  --memory on --auto-capture on

# refresh an existing install, keeping its current models (discovered in Step 2)
python3 <power-root>/skills/setup/scripts/install.py \
  --scope project \
  --model-low <installed-low> --model-medium <installed-medium> --model-high <installed-high> \
  --memory on --auto-capture on
```

The installer:

- copies the 7 worker agents to `<target>/.kiro/agents/` and injects the preset
  `model:` into each agent's frontmatter,
- copies `steering/team.md` to `<target>/.kiro/steering/`,
- copies the hook JSON files and scripts to `<target>/.kiro/hooks/`, rewriting the
  script path in hook commands for the scope (`.kiro/hooks/scripts/...` for project,
  `~/.kiro/hooks/scripts/...` for global),
- with `--memory on`, additionally copies `steering/memory.md` and the
  session-start hook (`hooks/memory-index.json` + its scripts, paths rewritten
  for the scope), and prints where memories live. The `/memory` skill is **not**
  copied — the installed power provides it on demand; a stale `skills/memory/`
  copy from an older install is pruned on every run,
- with `--auto-capture on` (which requires `--memory on`), additionally copies the
  Stop-hook sidecall hooks (`memory-turn.json`, `memory-extract.json` + their
  scripts) and the `memory-extractor` agent verbatim,
- removes memory payload files that the current flags no longer select, so a
  re-run leaves the target exactly matching the last answers (team files are
  never touched).

Useful flags: `--target <dir>` to install elsewhere, `--power-root <dir>` if the script
can't infer it, `--dry-run` to preview.

## Step 7 — Verify and report

1. Confirm the files exist:
   ```bash
   ls <target>/.kiro/agents/ <target>/.kiro/steering/ <target>/.kiro/hooks/
   ```
   With `--memory on`, also confirm the memory hook scripts under
   `<target>/.kiro/hooks/scripts/` (`memory_index_hook.py`, plus
   `memory_turn_hook.py` and `memory_extract_hook.py` with auto-capture), and
   that `<target>/.kiro/skills/memory/` is absent — the skill is power-provided.
2. Smoke-test the hooks:
   ```bash
   echo '{}' | python3 <target>/.kiro/hooks/scripts/team_hook.py session-start
   echo '{"tool_input":{"command":"git push --force"}}' | python3 <target>/.kiro/hooks/scripts/guard_hook.py; echo "exit=$? (expect 2)"
   ```
3. Report to the user: scope, target, per-tier models, files written (including
   the memory payload when enabled, and where memories live:
   `~/.kiro/memories/`), and that a new Kiro session is needed for agents/hooks
   to load. Mention the `team` skill is now ready:
   `team 3:executor-medium "<task>"`.
4. If the scope was **project**, remind the user that setup runs **once per project** —
   a different project needs it run again there. If **global**, note it is installed
   once for every project on this machine.

## Changing presets or memory later

Re-run this skill (or the installer directly with new flags) — the installer
overwrites the copied agents with the new models, and the memory flags update the
install in place: `--memory on --auto-capture off` removes just the auto-capture
files, and `--memory off` (the default) removes the whole memory payload. Nothing
else changes.

After **updating the power itself** (Check-for-updates, or a repo reinstall), re-run
this skill in each installed scope — Step 2's inspection reports exactly what the
new power adds or drifts, and a refresh preserves the installed models unless you
deliberately change the preset.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `does not look like the oh-my-kiro power root` | Pass `--power-root <dir>` pointing at the directory containing `plugin.json` |
| Agents don't appear in the agent picker | New session required; confirm files landed in `.kiro/agents/` and that the workspace is trusted |
| Hooks don't fire | Confirm `.kiro/hooks/*.json` exist and `python3` is on PATH; hook commands run from the project root |
| Memory index not injected at session start | The recall hook isn't installed in that scope — installing the power ships skills only; hooks, steering, and agents come from setup. Re-run setup with `--memory on` |
| `/memory` skill doesn't appear | The skill is provided by the power, not setup — confirm the oh-my-kiro power is installed and start a new session |
| Workers stall on permission prompts | Executor agents pre-approve standard commands; for custom setups add the workers to `toolsSettings.subagent.trustedAgents` of the orchestrating agent |

## References

- [Creating custom agents](https://kiro.dev/docs/custom-agents/creating.md)
- [Hooks](https://kiro.dev/docs/hooks.md)
- [Models](https://kiro.dev/docs/models.md)
