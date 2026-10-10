from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "policy"))
from install import MANIFEST_NAME, _active_hooks_dir, _install, _uninstall
from policy import PolicyError


class PolicyInstallTest(unittest.TestCase):
    def setUp(self):
        if not shutil.which("git"):
            self.skipTest("Git is required for installer tests")
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        injected = {key: value for key, value in os.environ.items() if key == "GIT_CONFIG_COUNT" or
                    key.startswith("GIT_CONFIG_KEY_") or key.startswith("GIT_CONFIG_VALUE_")}
        for key in injected:
            os.environ.pop(key, None)
        self.addCleanup(os.environ.update, injected)
        self.root = Path(temporary.name) / "project"
        self.root.mkdir()
        self.git("init", "--quiet")
        self.git("config", "user.name", "Install Test")
        self.git("config", "user.email", "install@example.invalid")
        self.git("switch", "-c", "main")

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, text=True,
                              encoding="utf-8", capture_output=True, check=True)

    @property
    def manifest_path(self):
        result = self.git("rev-parse", "--git-dir").stdout.strip()
        git_dir = Path(result)
        if not git_dir.is_absolute():
            git_dir = self.root / git_dir
        return git_dir / MANIFEST_NAME

    def install(self, *, claude=False):
        _install(self.root, ROOT, claude=claude)

    def test_install_generates_documents_and_adds_only_a_managed_agent_reference(self):
        original = "# Project rules\n\nKeep existing guidance.\n"
        (self.root / "AGENTS.md").write_text(original, encoding="utf-8")
        self.install()
        agents = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertTrue(agents.startswith(original))
        self.assertIn("policy/NAMING.md", agents)
        self.assertTrue((self.root / "policy" / "NAMING.md").is_file())
        self.assertTrue((self.root / "scripts" / "policy" / "validate.py").is_file())
        self.assertTrue((self.root / ".github" / "workflows" / "policy-check.yml").is_file())
        self.assertTrue((self.root / "policy" / "local.json").is_file())
        self.assertTrue(self.manifest_path.is_file())

    def test_existing_git_hook_runs_after_install_and_is_restored_on_uninstall(self):
        hook_dir = _active_hooks_dir(self.root)
        hook_dir.mkdir(parents=True, exist_ok=True)
        existing = hook_dir / "commit-msg"
        original = b"#!/bin/sh\nprintf existing >> \"$HOOK_MARKER\"\n"
        existing.write_bytes(original)
        existing.chmod(0o755)
        original_mode = existing.stat().st_mode & 0o777
        self.install()
        backup = hook_dir / "commit-msg.policy-original"
        self.assertEqual(backup.read_bytes(), original)
        self.assertIn(b"hooks.py", existing.read_bytes())
        _uninstall(self.root)
        self.assertEqual(existing.read_bytes(), original)
        self.assertEqual(existing.stat().st_mode & 0o777, original_mode)
        self.assertFalse(backup.exists())
        self.assertFalse(self.manifest_path.exists())

    def test_install_is_idempotent_and_keeps_local_configuration(self):
        self.install()
        local = self.root / "policy" / "local.json"
        local.write_text('{"schema_version": 1, "scope": {"allowed": ["custom"]}}\n', encoding="utf-8")
        self.install()
        self.assertEqual(local.read_text(encoding="utf-8"),
                         '{"schema_version": 1, "scope": {"allowed": ["custom"]}}\n')
        naming = (self.root / "policy" / "NAMING.md").read_text(encoding="utf-8")
        self.assertIn("`custom`", naming)
        self.assertEqual((self.root / "AGENTS.md").read_text(encoding="utf-8").count("skill-architecture naming policy: start"), 1)

    def test_update_accepts_user_changes_outside_managed_agents_block(self):
        self.install()
        agents = self.root / "AGENTS.md"
        content = agents.read_text(encoding="utf-8") + "\nExtra user guidance.\n"
        agents.write_text(content, encoding="utf-8")
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        from install import START, END, _block_sha
        block_start = content.find(START)
        block_end = content.find(END, block_start) + len(END)
        self.assertEqual(_block_sha(content[block_start:block_end]),
                         manifest["agents_reference"]["block_sha256"])
        self.install()
        self.assertEqual(agents.read_text(encoding="utf-8"), content)

    def test_uninstall_preserves_user_local_policy_and_restores_agents(self):
        original = "Follow these project-specific rules.\n"
        (self.root / "AGENTS.md").write_text(original, encoding="utf-8")
        self.install()
        local = self.root / "policy" / "local.json"
        local.write_text('{"schema_version": 1, "guidance": ["user-owned"]}\n', encoding="utf-8")
        _uninstall(self.root)
        self.assertEqual((self.root / "AGENTS.md").read_text(encoding="utf-8"), original)
        self.assertTrue(local.is_file())
        self.assertEqual(local.read_text(encoding="utf-8"), '{"schema_version": 1, "guidance": ["user-owned"]}\n')
        self.assertFalse((self.root / "policy" / "shared.json").exists())
        self.assertFalse(self.manifest_path.exists())

    def test_uninstall_removes_only_unchanged_seed_configuration(self):
        self.install()
        local = self.root / "policy" / "local.json"
        self.assertTrue(local.is_file())
        _uninstall(self.root)
        self.assertFalse(local.exists())

    def test_uninstall_refuses_user_modified_managed_files_without_partial_removal(self):
        self.install()
        owned = self.root / "scripts" / "policy" / "rules.py"
        owned.write_text("# user's change\n", encoding="utf-8")
        with self.assertRaisesRegex(PolicyError, "managed file was edited"):
            _uninstall(self.root)
        self.assertTrue((self.root / "policy" / "shared.json").is_file())
        self.assertTrue(self.manifest_path.is_file())
        self.assertEqual(owned.read_text(encoding="utf-8"), "# user's change\n")

    def test_update_refuses_user_modified_managed_files(self):
        self.install()
        workflow = self.root / ".github" / "workflows" / "policy-check.yml"
        workflow.write_text("# customized workflow\n", encoding="utf-8")
        with self.assertRaisesRegex(PolicyError, "managed file was edited"):
            self.install()
        self.assertEqual(workflow.read_text(encoding="utf-8"), "# customized workflow\n")

    def test_preexisting_file_conflict_stops_before_any_install_changes(self):
        workflow = self.root / ".github" / "workflows" / "policy-check.yml"
        workflow.parent.mkdir(parents=True)
        workflow.write_text("user workflow\n", encoding="utf-8")
        original_agents = "User rules\n"
        (self.root / "AGENTS.md").write_text(original_agents, encoding="utf-8")
        with self.assertRaisesRegex(PolicyError, "not managed"):
            self.install()
        self.assertEqual((self.root / "AGENTS.md").read_text(encoding="utf-8"), original_agents)
        self.assertFalse((self.root / "policy" / "shared.json").exists())
        self.assertFalse(self.manifest_path.exists())

    def test_optional_claude_hook_merges_and_uninstalls_without_losing_other_settings(self):
        settings_path = self.root / ".claude" / "settings.json"
        settings_path.parent.mkdir()
        original = {
            "model": "custom-model",
            "hooks": {"PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "custom-check"}]}]},
        }
        settings_path.write_text(json.dumps(original), encoding="utf-8")
        self.install(claude=True)
        installed = json.loads(settings_path.read_text(encoding="utf-8"))
        groups = installed["hooks"]["PreToolUse"]
        self.assertEqual(groups[0], original["hooks"]["PreToolUse"][0])
        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[1]["matcher"], "Bash")
        _uninstall(self.root)
        self.assertEqual(json.loads(settings_path.read_text(encoding="utf-8")), original)

    def test_claude_hook_is_opt_in(self):
        self.install()
        self.assertFalse((self.root / ".claude" / "settings.json").exists())
        _uninstall(self.root)

    def test_malformed_claude_settings_are_protected(self):
        settings_path = self.root / ".claude" / "settings.json"
        settings_path.parent.mkdir()
        settings_path.write_text("{invalid", encoding="utf-8")
        with self.assertRaisesRegex(PolicyError, "Claude settings"):
            self.install(claude=True)
        self.assertEqual(settings_path.read_text(encoding="utf-8"), "{invalid")
        self.assertFalse(self.manifest_path.exists())

    def test_user_preexisting_agent_reference_is_not_removed_on_uninstall(self):
        from install import _block
        original = "# Existing\n\n" + _block("\n") + "\n"
        (self.root / "AGENTS.md").write_text(original, encoding="utf-8")
        self.install()
        _uninstall(self.root)
        self.assertEqual((self.root / "AGENTS.md").read_text(encoding="utf-8"), original)

    def test_install_refuses_a_git_hooks_path_outside_repo_and_git_dir(self):
        outside = self.root.parent / "shared-hooks"
        outside.mkdir()
        self.git("config", "core.hooksPath", str(outside))
        with self.assertRaisesRegex(PolicyError, "escapes the repository"):
            self.install()
        self.assertFalse(self.manifest_path.exists())
        self.assertFalse((self.root / "policy" / "shared.json").exists())


if __name__ == "__main__":
    unittest.main()
