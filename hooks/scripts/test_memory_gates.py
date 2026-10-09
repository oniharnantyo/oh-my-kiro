#!/usr/bin/env python3
"""oh-my-kiro memory hook gate tests — exercises both memory hooks as real
subprocesses against throwaway project dirs and throwaway HOMEs, so no test
ever touches the real ~/.kiro. Stdlib unittest only; run from anywhere:

  python3 hooks/scripts/test_memory_gates.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from memory_paths import resolve_memory_root  # noqa: E402

TURN_HOOK = os.path.join(HERE, "memory_turn_hook.py")
EXTRACT_HOOK = os.path.join(HERE, "memory_extract_hook.py")
HOOK_TIMEOUT = 30
SHIM_TIMEOUT = 15
LONG_PROMPT = "please remember that I prefer tabs over spaces in python files"
SESSION_ID = "12345678-90ab-4cde-8f01-234567890abc"


class HookCase(unittest.TestCase):
    """Shared fixtures: a throwaway project dir + throwaway HOME per test."""

    def temp_dir(self, prefix):
        path = tempfile.mkdtemp(prefix=prefix)
        self.addCleanup(shutil.rmtree, path, True)
        return path

    def make_world(self, with_root=True):
        """(project, home, memory root) — root resolved exactly the way the
        hooks resolve it, i.e. with HOME pointed at the throwaway home."""
        project = self.temp_dir("omk-mem-proj-")
        home = self.temp_dir("omk-mem-home-")
        root = self.root_for(project, home)
        if with_root:
            os.makedirs(root, exist_ok=True)
        return project, home, root

    def root_for(self, project, home):
        old = os.environ.get("HOME")
        os.environ["HOME"] = home
        try:
            return resolve_memory_root(project_dir=project)
        finally:
            if old is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old

    def run_hook(self, script, project, home, stdin_text="", extra_env=None):
        env = dict(os.environ)
        env["KIRO_PROJECT_DIR"] = project
        env["HOME"] = home
        env.pop("OMK_MEMORY_EXTRACTOR", None)
        env.pop("USER_PROMPT", None)
        env.update(extra_env or {})
        return subprocess.run(
            [sys.executable, script],
            input=stdin_text,
            capture_output=True,
            text=True,
            env=env,
            timeout=HOOK_TIMEOUT,
        )

    def write(self, root, name, text):
        with open(os.path.join(root, name), "w") as f:
            f.write(text)

    def read(self, root, name):
        with open(os.path.join(root, name)) as f:
            return f.read()

    def backdate(self, path, seconds):
        stamp = time.time() - seconds
        os.utime(path, (stamp, stamp))

    def ready_root(self, root):
        """Stamp a root so every extract-hook gate passes."""
        self.write(root, ".user-prose", "1")
        self.write(root, ".turn-start", str(int(time.time())))
        index = os.path.join(root, "MEMORY.md")
        with open(index, "w") as f:
            f.write("# Memory index\n")
        self.backdate(index, 60)

    def make_shim(self, project):
        """Fake kiro-cli: appends argv + env to $OMK_SHIM_LOG, then ---END---."""
        shim = os.path.join(project, "fake-kiro-cli.sh")
        log = os.path.join(project, "shim-calls.log")
        with open(shim, "w") as f:
            f.write("#!/bin/sh\n")
            f.write("{\n")
            f.write("  printf 'ARGV:'\n")
            f.write("  printf ' [%s]' \"$@\"\n")
            f.write("  printf '\\nENV\\n'\n")
            f.write("  env\n")
            f.write("  echo '---END---'\n")
            f.write("} >> \"$OMK_SHIM_LOG\"\n")
        os.chmod(shim, 0o755)
        return shim, log

    def shim_log(self, log_path):
        """Shim output once it finished, polling briefly for the detached
        child; "" when the shim never ran."""
        deadline = time.time() + SHIM_TIMEOUT
        text = ""
        while time.time() < deadline:
            try:
                with open(log_path) as f:
                    text = f.read()
            except OSError:
                text = ""
            if "---END---" in text:
                return text
            time.sleep(0.05)
        return text

    def shim_silence(self, log_path):
        """Shim output after a short settle window — long enough for a buggy
        hook to have spawned, short enough to keep the suite fast. "" means
        the shim never ran."""
        time.sleep(2)
        try:
            with open(log_path) as f:
                return f.read()
        except OSError:
            return ""

    def fake_session(self, home, session_id=SESSION_ID):
        """A transcript under the throwaway HOME's sessions tree."""
        sessions = os.path.join(home, ".kiro", "sessions", "abc123")
        transcript = os.path.join(sessions, "sess_%s" % session_id, "messages.jsonl")
        os.makedirs(os.path.dirname(transcript), exist_ok=True)
        with open(transcript, "w") as f:
            f.write('{"type": "user", "text": "%s"}\n' % LONG_PROMPT)
        return transcript


class TurnHookTests(HookCase):
    def prose_flag(self, root):
        turn_start = int(self.read(root, ".turn-start").strip())
        self.assertLess(abs(int(time.time()) - turn_start), 120)
        return self.read(root, ".user-prose").strip()

    def test_long_env_prompt_marks_prose(self):
        project, home, root = self.make_world()
        proc = self.run_hook(
            TURN_HOOK, project, home, extra_env={"USER_PROMPT": LONG_PROMPT}
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(self.prose_flag(root), "1")

    def test_short_prompt_marks_no_prose(self):
        project, home, root = self.make_world()
        proc = self.run_hook(
            TURN_HOOK, project, home, extra_env={"USER_PROMPT": "go on"}
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(self.prose_flag(root), "0")

    def test_exactly_three_words_counts_as_prose(self):
        project, home, root = self.make_world()
        proc = self.run_hook(
            TURN_HOOK,
            project,
            home,
            extra_env={"USER_PROMPT": "remember the tab rule"},
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(self.prose_flag(root), "1")

    def test_missing_env_and_empty_stdin_is_no_prose(self):
        project, home, root = self.make_world()
        proc = self.run_hook(TURN_HOOK, project, home)
        self.assertEqual(proc.returncode, 0)
        # Both stamps must exist even with nothing to record.
        self.assertEqual(self.prose_flag(root), "0")

    def test_unparseable_stdin_is_no_prose(self):
        project, home, root = self.make_world()
        proc = self.run_hook(TURN_HOOK, project, home, stdin_text="{{{not json")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(self.prose_flag(root), "0")

    def test_camelcase_stdin_key_honored(self):
        project, home, root = self.make_world()
        proc = self.run_hook(
            TURN_HOOK,
            project,
            home,
            stdin_text=json.dumps({"userPrompt": LONG_PROMPT}),
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(self.prose_flag(root), "1")

    def test_snake_case_stdin_key_honored(self):
        project, home, root = self.make_world()
        proc = self.run_hook(
            TURN_HOOK,
            project,
            home,
            stdin_text=json.dumps({"user_prompt": LONG_PROMPT}),
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(self.prose_flag(root), "1")


class ExtractHookGateTests(HookCase):
    def spawn_setup(self, project, home):
        shim, shim_log = self.make_shim(project)
        return {
            "OMK_KIRO_CLI": shim,
            "OMK_SHIM_LOG": shim_log,
        }

    def assert_blocked(self, proc, root, shim_log):
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(self.shim_silence(shim_log), "")  # shim never ran
        self.assertFalse(os.path.exists(os.path.join(root, ".extract.log")))

    def test_gate_recursion_sentinel_blocks(self):
        project, home, root = self.make_world()
        self.ready_root(root)
        extra = self.spawn_setup(project, home)
        extra["OMK_MEMORY_EXTRACTOR"] = "1"
        proc = self.run_hook(EXTRACT_HOOK, project, home, extra_env=extra)
        self.assert_blocked(proc, root, extra["OMK_SHIM_LOG"])

    def test_gate_missing_root_blocks(self):
        project, home, root = self.make_world(with_root=False)
        extra = self.spawn_setup(project, home)
        proc = self.run_hook(EXTRACT_HOOK, project, home, extra_env=extra)
        self.assert_blocked(proc, root, extra["OMK_SHIM_LOG"])

    def test_gate_no_prose_blocks(self):
        project, home, root = self.make_world()
        self.write(root, ".user-prose", "0")
        self.write(root, ".turn-start", str(int(time.time())))
        extra = self.spawn_setup(project, home)
        proc = self.run_hook(EXTRACT_HOOK, project, home, extra_env=extra)
        self.assert_blocked(proc, root, extra["OMK_SHIM_LOG"])

    def test_gate_stand_down_blocks(self):
        project, home, root = self.make_world()
        self.write(root, ".user-prose", "1")
        # Turn started 120 s ago; MEMORY.md was written just now, so the main
        # agent already saved this turn.
        self.write(root, ".turn-start", str(int(time.time()) - 120))
        with open(os.path.join(root, "MEMORY.md"), "w") as f:
            f.write("# Memory index\n")
        extra = self.spawn_setup(project, home)
        proc = self.run_hook(EXTRACT_HOOK, project, home, extra_env=extra)
        self.assert_blocked(proc, root, extra["OMK_SHIM_LOG"])

    def test_gate_missing_turn_start_blocks(self):
        project, home, root = self.make_world()
        self.write(root, ".user-prose", "1")
        extra = self.spawn_setup(project, home)
        proc = self.run_hook(EXTRACT_HOOK, project, home, extra_env=extra)
        self.assert_blocked(proc, root, extra["OMK_SHIM_LOG"])

    def test_gate_fresh_lock_blocks(self):
        project, home, root = self.make_world()
        self.ready_root(root)
        self.write(root, ".extract.lock", "%d %d" % (os.getpid(), int(time.time())))
        extra = self.spawn_setup(project, home)
        proc = self.run_hook(EXTRACT_HOOK, project, home, extra_env=extra)
        self.assert_blocked(proc, root, extra["OMK_SHIM_LOG"])


class ExtractHookSpawnTests(HookCase):
    def assert_spawned(self, proc, root, shim_log, transcript):
        self.assertEqual(proc.returncode, 0)
        calls = self.shim_log(shim_log)
        self.assertEqual(calls.count("ARGV:"), 1, calls)
        for expected in (
            "--agent",
            "memory-extractor",
            "--trust-tools=fs_read,fs_write",
            "--no-interactive",
            transcript,
            str(root),
            ".last-extraction",
        ):
            self.assertIn(expected, calls, calls)
        self.assertIn("OMK_MEMORY_EXTRACTOR=1", calls, calls)
        lock = self.read(root, ".extract.lock").split()
        self.assertEqual(len(lock), 2)
        self.assertLess(abs(int(time.time()) - int(lock[1])), 120)
        self.assertTrue(os.path.exists(os.path.join(root, ".extract.log")))

    def spawn_case(self, with_root=True):
        project, home, root = self.make_world()
        if with_root:
            self.ready_root(root)
        transcript = self.fake_session(home)
        shim, shim_log = self.make_shim(project)
        extra = {"OMK_KIRO_CLI": shim, "OMK_SHIM_LOG": shim_log}
        stdin_text = json.dumps({"sessionId": SESSION_ID})
        proc = self.run_hook(
            EXTRACT_HOOK, project, home, stdin_text=stdin_text, extra_env=extra
        )
        return proc, root, shim_log, transcript

    def test_all_gates_pass_spawns_extractor(self):
        proc, root, shim_log, transcript = self.spawn_case()
        self.assert_spawned(proc, root, shim_log, transcript)

    def test_stale_lock_does_not_block_spawn(self):
        project, home, root = self.make_world()
        self.ready_root(root)
        self.write(
            root, ".extract.lock", "%d %d" % (999999, int(time.time()) - 700)
        )
        transcript = self.fake_session(home)
        shim, shim_log = self.make_shim(project)
        extra = {"OMK_KIRO_CLI": shim, "OMK_SHIM_LOG": shim_log}
        proc = self.run_hook(
            EXTRACT_HOOK,
            project,
            home,
            stdin_text=json.dumps({"sessionId": SESSION_ID}),
            extra_env=extra,
        )
        self.assert_spawned(proc, root, shim_log, transcript)


if __name__ == "__main__":
    unittest.main(verbosity=2)
