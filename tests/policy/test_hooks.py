from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class CommitHookTest(unittest.TestCase):
    def setUp(self):
        if not shutil.which("git") or not shutil.which("python"):
            self.skipTest("Git and Python are required for commit-hook integration tests")
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "repository"
        self.root.mkdir()
        self.run_git("init", "--quiet")
        self.run_git("config", "user.name", "Policy Test")
        self.run_git("config", "user.email", "policy@example.invalid")
        self.run_git("config", "i18n.commitEncoding", "UTF-8")
        self.run_git("config", "i18n.logOutputEncoding", "UTF-8")
        (self.root / "policy").mkdir()
        shutil.copyfile(ROOT / "policy" / "shared.json", self.root / "policy" / "shared.json")
        shutil.copyfile(ROOT / "policy" / "local.json", self.root / "policy" / "local.json")
        (self.root / "scripts" / "policy").mkdir(parents=True)
        for name in ("policy.py", "rules.py", "hooks.py", "commit-msg"):
            shutil.copyfile(ROOT / "scripts" / "policy" / name, self.root / "scripts" / "policy" / name)
        hooks = Path(self.run_git("rev-parse", "--git-path", "hooks").stdout.strip())
        if not hooks.is_absolute():
            hooks = self.root / hooks
        self.hooks = hooks
        self.hooks.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.root / "scripts" / "policy" / "commit-msg", self.hooks / "commit-msg")
        (self.hooks / "commit-msg").chmod(0o755)

    def run_git(self, *args, check=True):
        result = subprocess.run(["git", *args], cwd=getattr(self, "root", None),
                                 text=True, encoding="utf-8", errors="replace", capture_output=True)
        if check and result.returncode:
            self.fail(f"git {' '.join(args)} failed: {result.stderr}")
        return result

    def prepare_commit(self, branch="feat/123-add-feature"):
        self.run_git("switch", "-c", branch)
        (self.root / "file.txt").write_text("content\n", encoding="utf-8")
        self.run_git("add", "file.txt")

    def test_git_commit_completes_subject_and_preserves_body(self):
        self.prepare_commit()
        message = self.root / "message.txt"
        message.write_bytes("feat(implement-feature): 機能を追加\n\n本文に別issue #999\n".encode("utf-8"))
        self.run_git("commit", "--file", str(message))
        subject = self.run_git("log", "-1", "--format=%s").stdout.strip()
        body = self.run_git("log", "-1", "--format=%b").stdout
        self.assertEqual(subject, "feat(implement-feature): 機能を追加 (#123)")
        self.assertEqual(body.rstrip("\n"), "本文に別issue #999")

    def test_git_commit_is_idempotent_and_does_not_duplicate_matching_issue(self):
        self.prepare_commit()
        message = self.root / "message.txt"
        original = "feat: 機能を追加 (#123)\n\n本文\n"
        message.write_text(original, encoding="utf-8", newline="")
        self.run_git("commit", "--file", str(message))
        self.assertEqual(self.run_git("log", "-1", "--format=%s").stdout.strip(),
                         "feat: 機能を追加 (#123)")

    def test_conflicting_issue_rejects_commit_without_changing_message(self):
        self.prepare_commit()
        message = self.root / "message.txt"
        original = "feat: 機能を追加 (#124)\n\n本文\n"
        message.write_text(original, encoding="utf-8", newline="")
        result = self.run_git("commit", "--file", str(message), check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("branch references #123", result.stderr)
        self.assertEqual(message.read_text(encoding="utf-8"), original)
        self.assertEqual(self.run_git("rev-list", "--count", "HEAD", check=False).returncode, 128)

    def test_invalid_subject_rejects_commit(self):
        self.prepare_commit()
        message = self.root / "message.txt"
        original = "invalid message\n\nbody\n"
        message.write_text(original, encoding="utf-8", newline="")
        result = self.run_git("commit", "--file", str(message), check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid subject", result.stderr)
        self.assertEqual(message.read_text(encoding="utf-8"), original)

    def test_no_issue_branch_does_not_append_reference(self):
        self.prepare_commit("chore/no-issue-update-readme")
        message = self.root / "message.txt"
        original = "chore: 依存関係を更新\n\n詳細\n"
        message.write_text(original, encoding="utf-8", newline="")
        self.run_git("commit", "--file", str(message))
        self.assertEqual(message.read_text(encoding="utf-8"), original)

    def test_existing_hook_runs_before_policy_hook(self):
        original_hook = self.hooks / "commit-msg.policy-original"
        marker = self.root / "previous-hook-ran"
        original_hook.write_text(
            "#!/bin/sh\nprintf ran > '" + str(marker).replace("'", "'\"'\"'") + "'\n",
            encoding="utf-8",
        )
        original_hook.chmod(0o755)
        self.prepare_commit()
        message = self.root / "message.txt"
        message.write_text("feat: 機能を追加", encoding="utf-8")
        self.run_git("commit", "--file", str(message))
        self.assertEqual(marker.read_text(encoding="utf-8"), "ran")


if __name__ == "__main__":
    unittest.main()
