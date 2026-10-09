#!/usr/bin/env python3
"""oh-my-kiro setup installer — copy team agents, hooks, and steering into a Kiro scope.

Invoked by the `setup` skill after the user answers the scope, preset, and memory
questions.

Usage:
  python3 install.py --scope project|global [--preset cheap|medium|premium]
                      [--model-low MODEL] [--model-medium MODEL] [--model-high MODEL]
                      [--memory on|off] [--auto-capture on|off]
                      [--target DIR] [--power-root DIR] [--dry-run]

Model presets by credit cost (verified against `kiro-cli chat --list-models`
and https://kiro.dev/docs/models.md):

  cheap:
     low:    qwen3-coder-next     0.05x
     medium: minimax-m2.5         0.25x
     high:   glm-5                0.50x
  medium:
     low:    minimax-m2.5         0.25x
     medium: claude-haiku-4.5     0.40x
     high:   claude-sonnet-5.5    1.30x
  premium:
     low:    claude-haiku-4.5     0.40x
     medium: claude-sonnet-5.5    1.30x
     high:   claude-opus-5.5      2.00x
  openai:
     low:    gpt-5.6-luna         0.60x
     medium: gpt-5.6-terra        2.20x
     high:   gpt-5.6-terra        2.20x

Tier -> worker mapping:
  low     executor-low
  medium  executor-medium, verifier
  high    planner, executor-high, debugger, critic

Copies:
  agents/*.md           -> <target>/.kiro/agents/          (each gets its preset `model:`)
  steering/team.md      -> <target>/.kiro/steering/team.md
  hooks/*.json + scripts-> <target>/.kiro/hooks/           (command paths rewritten per scope;
                                                            dev-only scripts excluded)

With --memory on, also the memory payload:
  steering/memory.md     -> <target>/.kiro/steering/memory.md
  hooks/memory-index.json + scripts -> <target>/.kiro/hooks/  (paths rewritten per scope)
  (the /memory skill is NOT copied — it is provided by the installed power itself;
   stale per-scope copies from older installs are pruned on every run)

With --auto-capture on (--memory on is required), additionally:
  hooks/memory-turn.json, hooks/memory-extract.json + scripts -> <target>/.kiro/hooks/
  agents/memory-extractor.md -> <target>/.kiro/agents/      (frontmatter kept verbatim)

Re-running with different answers removes the memory files the new answers no
longer select, so the target always matches the last run. With auto-capture on,
`kiro-cli chat --list-models` is checked for `qwen3-coder-next`; a missing model is
a visible warning, never an install failure.

Project scope: --target defaults to the current directory.
Global scope:  --target defaults to the home directory.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

# Which tier each worker agent maps to.
TIER_AGENTS = {
    "executor-low": "low",
    "executor-medium": "medium",
    "verifier": "medium",
    "planner": "high",
    "executor-high": "high",
    "debugger": "high",
    "critic": "high",
}

# Preset -> tier -> model. Values verified against `kiro-cli chat --list-models`.
PRESETS = {
    "cheap": {
        "low": "qwen3-coder-next",       # 0.05x
        "medium": "minimax-m2.5",        # 0.25x
        "high": "glm-5",                 # 0.50x
    },
    "medium": {
        "low": "minimax-m2.5",           # 0.25x
        "medium": "claude-haiku-4.5",    # 0.40x
        "high": "claude-sonnet-5.5",     # 1.30x
    },
    "premium": {
        "low": "claude-haiku-4.5",       # 0.40x
        "medium": "claude-sonnet-5.5",   # 1.30x
        "high": "claude-opus-5.5",       # 2.00x
    },
    "openai": {
        "low": "gpt-5.6-luna",           # 0.60x
        "medium": "gpt-5.6-terra",       # 2.20x
        "high": "gpt-5.6-terra",         # 2.20x
    },
}

DEFAULT_PRESET = "medium"

# Opt-in memory payload, installed only via --memory on / --auto-capture on.
# The generic agents/hooks copy loops exclude these by name (team installs must
# never pick them up); copy_memory() copies them per the flags instead, and
# prune_memory() removes them on reinstall. agents/memory-extractor.md is copied
# verbatim — its `model: qwen3-coder-next` frontmatter must never be rewritten.
MEMORY_HOOKS_ALWAYS = ["memory-index.json"]
MEMORY_HOOKS_AUTO = ["memory-turn.json", "memory-extract.json"]
MEMORY_SCRIPTS_ALWAYS = ["memory_index_hook.py", "memory_paths.py"]
MEMORY_SCRIPTS_AUTO = ["memory_turn_hook.py", "memory_extract_hook.py"]
MEMORY_AGENT = "memory-extractor.md"
MEMORY_MODEL = "qwen3-coder-next"
MEMORY_HOOK_JSON_SET = set(MEMORY_HOOKS_ALWAYS) | set(MEMORY_HOOKS_AUTO)
MEMORY_SCRIPT_SET = set(MEMORY_SCRIPTS_ALWAYS) | set(MEMORY_SCRIPTS_AUTO)
MEMORY_AGENT_SET = {MEMORY_AGENT}

# Literal memory target paths (relative to <target>/.kiro) pruned on reinstall.
# Filename lists only — no globs, so team payload files can never match.
MEMORY_TARGETS_ALWAYS = [
    "hooks/memory-index.json",
    "hooks/scripts/memory_index_hook.py",
    "hooks/scripts/memory_paths.py",
    "steering/memory.md",
]
# The /memory skill is power-provided and never copied into a scope; this is a
# legacy-cleanup target, pruned on every run like DEV_TARGETS.
MEMORY_TARGET_SKILL_DIR = "skills/memory"
MEMORY_TARGETS_AUTO = [
    "hooks/memory-turn.json",
    "hooks/memory-extract.json",
    "hooks/scripts/memory_turn_hook.py",
    "hooks/scripts/memory_extract_hook.py",
    "agents/memory-extractor.md",
]

# Repo-only dev files that never ship into a Kiro scope: skipped by the scripts
# copy loop and pruned on every reinstall, whatever the memory flags say.
DEV_SCRIPTS = {"test_memory_gates.py"}
DEV_TARGETS = ["hooks/scripts/test_memory_gates.py"]


def power_root(explicit):
    if explicit:
        return os.path.abspath(os.path.expanduser(explicit))
    # script lives at <power>/skills/setup/scripts/install.py
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, "..", "..", ".."))


def target_dir(scope, explicit):
    if explicit:
        return os.path.abspath(os.path.expanduser(explicit))
    return os.path.expanduser("~") if scope == "global" else os.getcwd()


def hook_prefix(scope):
    """Command prefix hooks use to reach their scripts, valid from any project root."""
    return "~/.kiro/hooks/scripts" if scope == "global" else ".kiro/hooks/scripts"


def agents_of_tier(tier):
    return sorted(name for name, t in TIER_AGENTS.items() if t == tier)


def copy_agents(root, target, models, dry_run):
    src = os.path.join(root, "agents")
    dst = os.path.join(target, ".kiro", "agents")
    if not os.path.isdir(src):
        return [], "agents/ not found in power root"
    copied = []
    for name in sorted(os.listdir(src)):
        if not name.endswith(".md") or name in MEMORY_AGENT_SET:
            continue
        text = open(os.path.join(src, name)).read()
        stem = name[:-3]
        tier = TIER_AGENTS.get(stem)
        if tier:
            text = set_frontmatter_model(text, models[tier])
        if not dry_run:
            os.makedirs(dst, exist_ok=True)
            with open(os.path.join(dst, name), "w") as f:
                f.write(text)
        copied.append(name)
    return copied, None


def set_frontmatter_model(text, model):
    """Insert or replace `model:` in the YAML frontmatter (keeps other fields)."""
    m = re.match(r"\A---\n(.*?)\n---\n(.*)\Z", text, re.S)
    if not m:
        return text
    fm, body = m.group(1), m.group(2)
    if re.search(r"^model:.*$", fm, re.M):
        fm = re.sub(r"^model:.*$", "model: %s" % model, fm, flags=re.M)
    else:
        fm = fm + "\nmodel: %s" % model
    return "---\n%s\n---\n%s" % (fm, body)


def copy_steering(root, target, dry_run):
    src = os.path.join(root, "steering", "team.md")
    if not os.path.isfile(src):
        return [], "steering/team.md not found in power root"
    dst = os.path.join(target, ".kiro", "steering", "team.md")
    if not dry_run:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
    return ["team.md"], None


def write_hook_json(src, dst, prefix, dry_run):
    """Copy one hook JSON file, rewriting its script path prefix for the scope."""
    data = json.load(open(src))
    for hook in data.get("hooks", []):
        action = hook.get("action", {})
        if action.get("type") == "command" and "command" in action:
            action["command"] = re.sub(
                r"(?:\.kiro|~/.kiro)/hooks/scripts/",
                prefix + "/",
                action["command"],
            )
    if not dry_run:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")


def copy_hooks(root, target, scope, dry_run):
    src_hooks = os.path.join(root, "hooks")
    dst_hooks = os.path.join(target, ".kiro", "hooks")
    if not os.path.isdir(src_hooks):
        return [], "hooks/ not found in power root"
    copied = []
    prefix = hook_prefix(scope)
    for name in sorted(os.listdir(src_hooks)):
        path = os.path.join(src_hooks, name)
        if name.endswith(".json") and name not in MEMORY_HOOK_JSON_SET:
            write_hook_json(path, os.path.join(dst_hooks, name), prefix, dry_run)
            copied.append(name)
    src_scripts = os.path.join(src_hooks, "scripts")
    if os.path.isdir(src_scripts):
        dst_scripts = os.path.join(dst_hooks, "scripts")
        if not dry_run:
            os.makedirs(dst_scripts, exist_ok=True)
            for name in sorted(os.listdir(src_scripts)):
                if (name in MEMORY_SCRIPT_SET or name in DEV_SCRIPTS
                        or not os.path.isfile(os.path.join(src_scripts, name))):
                    continue
                shutil.copyfile(os.path.join(src_scripts, name),
                                os.path.join(dst_scripts, name))
                os.chmod(os.path.join(dst_scripts, name), 0o755)
        copied.append("scripts/")
    return copied, None


def copy_memory(root, target, scope, capture_on, dry_run):
    """Copy the opt-in memory payload (always set, plus auto-capture when on).

    Returns (memory_items, capture_items, missing) report lists; missing names
    payload files absent from the power root (warned about, never fatal).
    """
    kiro = os.path.join(target, ".kiro")
    prefix = hook_prefix(scope)

    def entry(rel):
        src = os.path.join(root, *rel.split("/"))
        return (rel, src, os.path.join(kiro, *rel.split("/")))

    plan = [("memory", *entry("steering/memory.md"))]
    plan += [("memory", *entry(os.path.join("hooks", name)))
             for name in MEMORY_HOOKS_ALWAYS]
    plan += [("memory", *entry(os.path.join("hooks", "scripts", name)))
             for name in MEMORY_SCRIPTS_ALWAYS]
    if capture_on:
        plan.append(("capture", *entry("agents/" + MEMORY_AGENT)))
        plan += [("capture", *entry(os.path.join("hooks", name)))
                 for name in MEMORY_HOOKS_AUTO]
        plan += [("capture", *entry(os.path.join("hooks", "scripts", name)))
                 for name in MEMORY_SCRIPTS_AUTO]

    memory_items, capture_items, missing = [], [], []
    for tag, rel, src, dst in plan:
        if not os.path.isfile(src):
            missing.append(rel)
            continue
        if rel.endswith(".json"):
            write_hook_json(src, dst, prefix, dry_run)
        elif not dry_run:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
            if rel.startswith("hooks/scripts/"):
                os.chmod(dst, 0o755)
        (memory_items if tag == "memory" else capture_items).append(rel)
    return memory_items, capture_items, missing


def prune_memory(target, memory_on, capture_on, dry_run):
    """Remove memory payload files the current answers no longer install, so a
    re-run leaves the target exactly matching the flags, plus files that are
    never part of any install (dev-only scripts; the power-provided /memory
    skill) under any flags. Literal filename lists only — team payload files are
    never touched. Returns the removed (or, in a dry run, removable) paths
    relative to <target>/.kiro."""
    if memory_on and capture_on:
        doomed = []
    elif memory_on:
        doomed = list(MEMORY_TARGETS_AUTO)
    else:
        doomed = list(MEMORY_TARGETS_ALWAYS) + list(MEMORY_TARGETS_AUTO)
    # Never-installed files are stale the moment they exist, so they always go.
    doomed += [MEMORY_TARGET_SKILL_DIR] + DEV_TARGETS
    removed = []
    for rel in doomed:
        path = os.path.join(target, ".kiro", *rel.split("/"))
        if os.path.isdir(path) and not os.path.islink(path):
            if not dry_run:
                shutil.rmtree(path)
            removed.append(rel + "/")
        elif os.path.lexists(path):
            if not dry_run:
                os.remove(path)
            removed.append(rel)
    return removed


def check_capture_model(timeout=20):
    """Best-effort check that the auto-capture sidecall model is available.

    Returns a warning string, or None when `qwen3-coder-next` shows up in
    `kiro-cli chat --list-models`. Never raises, never fails the install.
    """
    try:
        proc = subprocess.run(["kiro-cli", "chat", "--list-models"],
                              capture_output=True, text=True, errors="replace",
                              timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return _capture_model_unavailable("could not run `kiro-cli chat --list-models` (%s)" % exc)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        suffix = ": %s" % detail[-1] if detail else ""
        return _capture_model_unavailable("`kiro-cli chat --list-models` failed with "
                                          "exit %s%s" % (proc.returncode, suffix))
    if MEMORY_MODEL not in (proc.stdout + proc.stderr):
        return ("warning: model '%s' not in kiro-cli chat --list-models — extraction "
                "sidecalls will silently fall back to your account default (possibly "
                "at a much higher cost)" % MEMORY_MODEL)
    return None


def _capture_model_unavailable(detail):
    return ("warning: %s — cannot verify that '%s' is available; extraction sidecalls "
            "may silently fall back to your account default (possibly at a much higher "
            "cost)" % (detail, MEMORY_MODEL))


def resolve_models(args):
    """Preset first, then per-tier overrides."""
    models = dict(PRESETS[args.preset])
    overrides = {
        "low": args.model_low,
        "medium": args.model_medium,
        "high": args.model_high,
    }
    for tier, value in overrides.items():
        if value:
            models[tier] = value
    return models


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scope", choices=["project", "global"], required=True)
    ap.add_argument("--preset", choices=sorted(PRESETS), default=DEFAULT_PRESET,
                    help="model preset by cost (default: %(default)s)")
    ap.add_argument("--model-low", help="override the low-tier model")
    ap.add_argument("--model-medium", help="override the medium-tier model")
    ap.add_argument("--model-high", help="override the high-tier model")
    ap.add_argument("--memory", choices=["on", "off"], default="off",
                    help="install the persistent-memory payload (default: %(default)s)")
    ap.add_argument("--auto-capture", choices=["on", "off"], default="off",
                    help="with --memory on: add the Stop-hook auto-capture sidecall "
                         "and the memory-extractor agent (default: %(default)s)")
    ap.add_argument("--target")
    ap.add_argument("--power-root")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    memory_on = args.memory == "on"
    capture_on = args.auto_capture == "on"
    if capture_on and not memory_on:
        ap.error("--auto-capture on requires --memory on")

    root = power_root(args.power_root)
    target = target_dir(args.scope, args.target)
    models = resolve_models(args)

    if not os.path.isfile(os.path.join(root, "plugin.json")):
        print("error: %s does not look like the oh-my-kiro power root" % root,
              file=sys.stderr)
        return 1

    print("oh-my-kiro setup")
    print("  power root : %s" % root)
    print("  scope      : %s" % args.scope)
    print("  target     : %s" % target)
    print("  preset     : %s" % args.preset)
    if memory_on:
        print("  memory     : on%s" % (", auto-capture on" if capture_on else ""))
    for tier in ("low", "medium", "high"):
        print("  %-6s : %-20s (%s)" % (tier, models[tier], ", ".join(agents_of_tier(tier))))
    if args.dry_run:
        print("  (dry run — nothing written)")

    removed = prune_memory(target, memory_on, capture_on, args.dry_run)

    results = []
    agents, err = copy_agents(root, target, models, args.dry_run)
    results.append(("agents", agents, err))
    steering, err = copy_steering(root, target, args.dry_run)
    results.append(("steering", steering, err))
    hooks, err = copy_hooks(root, target, args.scope, args.dry_run)
    results.append(("hooks", hooks, err))
    if memory_on:
        memory_items, capture_items, missing = copy_memory(
            root, target, args.scope, capture_on, args.dry_run)
    else:
        memory_items, capture_items, missing = [], [], []

    failed = False
    for label, items, err in results:
        if err:
            print("  %-8s FAILED: %s" % (label, err))
            failed = True
        else:
            print("  %-8s %s" % (label, ", ".join(items)))
    if removed:
        print("  %-8s %s" % ("removed", ", ".join(removed)))
    if memory_on:
        print("  %-8s %s" % ("memory", ", ".join(memory_items)))
        if capture_on:
            print("  %-8s %s" % ("capture", ", ".join(capture_items)))
        print("  %-8s %s" % ("note",
              "memories are stored per project under ~/.kiro/memories/"))
    if missing:
        print("  warning: memory payload missing from power root: %s"
              % ", ".join(missing))
    if capture_on:
        warning = check_capture_model()
        if warning:
            print(warning)

    if failed:
        return 1
    print("done. Restart or open a new Kiro session to pick up agents, hooks, and steering.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
