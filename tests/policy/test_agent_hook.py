from __future__ import annotations

import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "policy"))
from agent_hook import handle_input


class ClaudePreToolUseTest(unittest.TestCase):
    def setUp(self):
        if not shutil.which("git"):
            self.skipTest("Git is required for agent-hook integration tests")
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "repo"
        self.root.mkdir()
        self.git("init", "--quiet")
        (self.root / "policy").mkdir()
        for name in ("shared.json", "local.json"):
            shutil.copyfile(ROOT / "policy" / name, self.root / "policy" / name)
        target = self.root / "scripts" / "policy"
        target.mkdir(parents=True)
        for name in ("policy.py", "rules.py", "hooks.py", "agent_hook.py"):
            shutil.copyfile(ROOT / "scripts" / "policy" / name, target / name)
        self.git("switch", "-c", "feat/123-add-feature")

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, text=True,
                              encoding="utf-8", capture_output=True, check=True)

    def request(self, command, *, tool="Bash", cwd=None):
        payload = {"tool_name": tool, "tool_input": {"command": command, "timeout": 5},
                   "cwd": str(cwd or self.root), "session_id": "test-session"}
        return payload, handle_input(payload)

    def test_unrelated_tools_and_commands_pass_through(self):
        outside = self.root.parent
        for tool, command, cwd in (
            ("Read", "ignored", self.root),
            ("Bash", "python -c 'print(1)'", outside),
            ("Bash", "echo 'unmatched", outside),
            ("Bash", "git status --short", self.root),
        ):
            with self.subTest(tool=tool, command=command):
                self.assertEqual(self.request(command, tool=tool, cwd=cwd)[1], (None, None))

    def test_branch_creation_commands_are_validated_and_left_unchanged(self):
        for command in (
            "git switch -c chore/no-issue-update-dependencies",
            "git switch --create feat/456-new-feature main",
            "git checkout -b fix/789-correct-error origin/main",
        ):
            with self.subTest(command=command):
                self.assertEqual(self.request(command)[1], (None, None))

    def test_invalid_branch_name_is_denied_with_actionable_reason(self):
        response, reason = self.request("git switch -c feature/add-login")[1]
        self.assertIn("invalid branch name", reason)
        output = response["hookSpecificOutput"]
        self.assertEqual(output["permissionDecision"], "deny")
        self.assertIn("policy/NAMING.md", output["permissionDecisionReason"])

    def test_missing_or_unsupported_branch_arguments_are_denied(self):
        for command in ("git switch -c", "git switch -c feat/123-valid extra args"):
            with self.subTest(command=command):
                response, reason = self.request(command)[1]
                self.assertIsNotNone(response)
                self.assertIn("supported forms", reason)

    def test_shell_compound_branch_creation_is_denied(self):
        response, reason = self.request("git switch -c feat/123-add-feature && echo done")[1]
        self.assertEqual(response["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("compound", reason)

    def test_pr_title_and_body_are_completed_in_updated_input(self):
        command = 'gh pr create --title "feat(implement-feature): 機能を追加" --body "本文\n\nSee #999" --head feat/123-add-feature --draft'
        payload, (response, reason) = self.request(command)
        self.assertIsNone(reason)
        updated_input = response["hookSpecificOutput"]["updatedInput"]
        self.assertEqual(updated_input["timeout"], 5)
        self.assertEqual(payload["tool_input"]["command"], command)
        updated = shlex.split(updated_input["command"])
        self.assertEqual(updated[updated.index("--title") + 1],
                         "feat(implement-feature): 機能を追加 (#123)")
        body = updated[updated.index("--body") + 1]
        self.assertEqual(body, "本文\n\nSee #999\n\nRefs #123")
        self.assertIn("--draft", updated)

    def test_matching_issue_references_are_idempotent(self):
        command = 'gh pr create --title "feat: summary (#123)" --body "Refs #123"'
        self.assertEqual(self.request(command)[1], (None, None))

    def test_mismatching_title_issue_is_denied_without_changing_body_file(self):
        body_file = self.root / "body.md"
        body_file.write_text("existing", encoding="utf-8")
        command = f'gh pr create -t "feat: summary (#124)" -F "{body_file}"'
        response, reason = self.request(command)[1]
        self.assertEqual(response["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("branch references #123", reason)
        self.assertEqual(body_file.read_text(encoding="utf-8"), "existing")

    def test_pr_body_file_is_updated_without_losing_other_issue_references(self):
        body_file = self.root / "body with spaces.md"
        original = "Details\n\nRefs #99\n"
        body_file.write_text(original, encoding="utf-8", newline="")
        command = f'gh pr create --title="fix(implement-feature): 修正" --body-file="{body_file.name}"'
        response, reason = self.request(command)[1]
        self.assertIsNone(reason)
        self.assertEqual(body_file.read_text(encoding="utf-8"), original + "\nRefs #123")
        updated = response["hookSpecificOutput"]["updatedInput"]["command"]
        self.assertEqual(shlex.split(updated)[0:2], ["gh", "pr"])

    def test_pr_using_no_issue_branch_is_not_modified(self):
        self.git("switch", "-c", "chore/no-issue-update-dependencies")
        command = 'gh pr create -t "chore: update" -b "Details #99"'
        self.assertEqual(self.request(command)[1], (None, None))

    def test_missing_title_body_and_unsupported_arguments_are_rejected(self):
        commands = (
            "gh pr create --fill --body details",
            "gh pr create --title title",
            "gh pr create --title title --body details --json title",
            "gh pr create --title title --body-file -",
        )
        for command in commands:
            with self.subTest(command=command):
                response, _ = self.request(command)[1]
                self.assertEqual(response["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_invalid_tool_input_is_left_alone_for_non_target_command(self):
        self.assertEqual(handle_input({"tool_name": "Bash", "tool_input": {"command": "ls"}}), (None, None))

    def test_main_emits_valid_claude_json_and_no_diagnostic_stdout(self):
        script = self.root / "scripts" / "policy" / "agent_hook.py"
        request = {"tool_name": "Bash", "tool_input": {"command": "git switch -c invalid"},
                   "cwd": str(self.root)}
        result = subprocess.run([sys.executable, "-B", str(script)], input=json.dumps(request),
                                text=True, encoding="utf-8", capture_output=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")


if __name__ == "__main__":
    unittest.main()
