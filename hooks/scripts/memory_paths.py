#!/usr/bin/env python3
"""oh-my-kiro memory paths — shared storage-location helper for the memory payload.

Resolves the per-project memory root under ~/.kiro/memories/projects/. The
folder name embeds a hash of the absolute project path so two projects that
share a basename never collide. Resolving never creates anything — callers
create on write via ensure_memory_root(). Pure stdlib, tolerant, never crashes.
"""

import hashlib
import os
import re
from pathlib import Path

MEMORY_INDEX = "MEMORY.md"


def base_dir(project_dir=None):
    """First available of the argument, KIRO_PROJECT_DIR, cwd — made absolute."""
    raw = project_dir or os.environ.get("KIRO_PROJECT_DIR") or os.getcwd()
    return os.path.abspath(str(raw))


def slugify(name):
    """Lowercase name; collapse every non-[a-z0-9] run to '-'; empty -> 'project'."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "project"


def project_key(base):
    """Stable '<slug>-<hash16>' folder name for an absolute base directory."""
    digest = hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]
    return "%s-%s" % (slugify(os.path.basename(base)), digest)


def resolve_memory_root(project_dir=None):
    """Return the per-project memory root path. Never creates anything."""
    base = base_dir(project_dir)
    root = Path.home() / ".kiro" / "memories" / "projects" / project_key(base) / "memory"
    return root


def ensure_memory_root(project_dir=None):
    """Resolve and create the memory root (parents included). The ONLY
    create-on-write entry point."""
    root = resolve_memory_root(project_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


if __name__ == "__main__":
    print(resolve_memory_root())
