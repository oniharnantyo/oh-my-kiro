#!/usr/bin/env python3
"""oh-my-kiro setup installer — copy team agents, hooks, and steering into a Kiro scope.

Invoked by the `setup` skill after the user answers the scope and preset questions.

Usage:
  python3 install.py --scope project|global [--preset cheap|medium|premium]
                      [--model-low MODEL] [--model-medium MODEL] [--model-high MODEL]
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
  hooks/*.json + scripts-> <target>/.kiro/hooks/           (command paths rewritten per scope)

Project scope: --target defaults to the current directory.
Global scope:  --target defaults to the home directory.
"""

import argparse
import json
import os
import re
import shutil
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
        if not name.endswith(".md"):
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


def copy_hooks(root, target, scope, dry_run):
    src_hooks = os.path.join(root, "hooks")
    dst_hooks = os.path.join(target, ".kiro", "hooks")
    if not os.path.isdir(src_hooks):
        return [], "hooks/ not found in power root"
    copied = []
    prefix = hook_prefix(scope)
    for name in sorted(os.listdir(src_hooks)):
        path = os.path.join(src_hooks, name)
        if name.endswith(".json"):
            data = json.load(open(path))
            for hook in data.get("hooks", []):
                action = hook.get("action", {})
                if action.get("type") == "command" and "command" in action:
                    action["command"] = re.sub(
                        r"(?:\.kiro|~/.kiro)/hooks/scripts/",
                        prefix + "/",
                        action["command"],
                    )
            if not dry_run:
                os.makedirs(dst_hooks, exist_ok=True)
                with open(os.path.join(dst_hooks, name), "w") as f:
                    json.dump(data, f, indent=2)
                    f.write("\n")
            copied.append(name)
    src_scripts = os.path.join(src_hooks, "scripts")
    if os.path.isdir(src_scripts):
        dst_scripts = os.path.join(dst_hooks, "scripts")
        if not dry_run:
            os.makedirs(dst_scripts, exist_ok=True)
            for name in sorted(os.listdir(src_scripts)):
                shutil.copyfile(os.path.join(src_scripts, name),
                                os.path.join(dst_scripts, name))
                os.chmod(os.path.join(dst_scripts, name), 0o755)
        copied.append("scripts/")
    return copied, None


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
    ap.add_argument("--target")
    ap.add_argument("--power-root")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

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
    for tier in ("low", "medium", "high"):
        print("  %-6s : %-20s (%s)" % (tier, models[tier], ", ".join(agents_of_tier(tier))))
    if args.dry_run:
        print("  (dry run — nothing written)")

    results = []
    agents, err = copy_agents(root, target, models, args.dry_run)
    results.append(("agents", agents, err))
    steering, err = copy_steering(root, target, args.dry_run)
    results.append(("steering", steering, err))
    hooks, err = copy_hooks(root, target, args.scope, args.dry_run)
    results.append(("hooks", hooks, err))

    failed = False
    for label, items, err in results:
        if err:
            print("  %-8s FAILED: %s" % (label, err))
            failed = True
        else:
            print("  %-8s %s" % (label, ", ".join(items)))

    if failed:
        return 1
    print("done. Restart or open a new Kiro session to pick up agents, hooks, and steering.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
