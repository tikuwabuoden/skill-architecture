from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "policy"))
from hooks import load_repository_policy
from policy import PolicyError
from validate import validate_commit_range, validate_pull_request


POLICY = load_repository_policy(ROOT)


class PullRequestValidationTest(unittest.TestCase):
    def test_pr_requires_matching_title_and_body_reference_for_numbered_branch(self):
        validate_pull_request("feat(implement-feature): feature (#123)", "Detail\n\nRefs #123", "feat/123-add-feature", POLICY)
        cases = (
            ("feat(implement-feature): feature", "Refs #123", "must end in"),
            ("feat(implement-feature): feature (#124)", "Refs #123", "references #124"),
            ("feat(implement-feature): feature (#123)", "Detail #1234", "line containing"),
            ("invalid", "Refs #123", "invalid subject"),
            ("feat(unknown): feature (#123)", "Refs #123", "not in the configured allowed list"),
        )
        for title, body, message in cases:
            with self.subTest(title=title, body=body), self.assertRaisesRegex(PolicyError, message):
                validate_pull_request(title, body, "feat/123-add-feature", POLICY)

    def test_no_issue_and_permanent_branches_do_not_require_references(self):
        validate_pull_request("chore: update", "Refs #99", "chore/no-issue-update-dependencies", POLICY)
        validate_pull_request("docs: update", "", "main", POLICY)

    def test_pr_does_not_reject_branches_outside_the_naming_convention(self):
        for branch in ("feature/3-install-shared-policy", "feature/x", "feat/123-Add-feature"):
            with self.subTest(branch=branch):
                validate_pull_request("feat: x", "", branch, POLICY)
                with self.assertRaisesRegex(PolicyError, "invalid subject"):
                    validate_pull_request("invalid", "", branch, POLICY)

    def test_pr_requires_the_source_branch_to_be_available(self):
        with self.assertRaisesRegex(PolicyError, "source branch is unavailable"):
            validate_pull_request("feat: x", "", "", POLICY)

    def test_pr_does_not_replace_other_body_references(self):
        validate_pull_request("feat(implement-feature): x (#123)",
                              "Refs #99\n\nRefs #123\n", "feat/123-add-feature", POLICY)


class CommitRangeValidationTest(unittest.TestCase):
    def setUp(self):
        if not shutil.which("git"):
            self.skipTest("Git is required for commit-range validation tests")
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "repo"
        self.root.mkdir()
        self.git("init", "--quiet")
        self.git("config", "user.name", "Policy Test")
        self.git("config", "user.email", "policy@example.invalid")
        self.git("config", "i18n.commitEncoding", "UTF-8")
        (self.root / "policy").mkdir()
        for name in ("shared.json", "local.json"):
            shutil.copyfile(ROOT / "policy" / name, self.root / "policy" / name)
        self.git("switch", "-c", "main")
        (self.root / "base.txt").write_text("base\n", encoding="utf-8")
        self.git("add", "base.txt")
        self.git("commit", "--message", "docs: base")
        self.base = self.git("rev-parse", "HEAD").stdout.strip()

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, text=True,
                              encoding="utf-8", capture_output=True, check=True)

    def commit(self, subject):
        name = "commit-" + str(len(list(self.root.glob("commit-*.txt")))) + ".txt"
        (self.root / name).write_text("change\n", encoding="utf-8")
        self.git("add", name)
        self.git("commit", "--message", subject)

    def test_validates_each_commit_since_base_without_requiring_branch_issue_match(self):
        self.git("switch", "-c", "feat/123-new-feature")
        self.commit("feat(implement-feature): add feature (#123)")
        self.commit("test(implement-feature): exercise behavior")
        head = self.git("rev-parse", "HEAD").stdout.strip()
        self.assertEqual(validate_commit_range(self.root, self.base, head,
                                               load_repository_policy(self.root)), 2)

    def test_ci_cli_accepts_nonconforming_branch_and_still_validates_pr_and_commits(self):
        self.git("switch", "-c", "feature/3-install-shared-policy")
        self.commit("feat: add feature")
        environment = os.environ.copy()
        environment.update({
            "POLICY_PR_BRANCH": "feature/3-install-shared-policy",
            "POLICY_PR_TITLE": "feat: add feature",
            "POLICY_PR_BODY": "",
            "POLICY_BASE_SHA": self.base,
            "POLICY_HEAD_SHA": self.git("rev-parse", "HEAD").stdout.strip(),
        })
        command = [sys.executable, "-B", str(ROOT / "scripts" / "policy" / "validate.py"), "pull-request"]
        result = subprocess.run(command, cwd=self.root, env=environment,
                                text=True, encoding="utf-8", capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Validated PR metadata and 1 commit(s).", result.stdout)

        environment["POLICY_PR_TITLE"] = "invalid"
        result = subprocess.run(command, cwd=self.root, env=environment,
                                text=True, encoding="utf-8", capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("invalid subject", result.stderr)

        environment["POLICY_PR_TITLE"] = "feat: add feature"
        self.commit("not conventional")
        environment["POLICY_HEAD_SHA"] = self.git("rev-parse", "HEAD").stdout.strip()
        result = subprocess.run(command, cwd=self.root, env=environment,
                                text=True, encoding="utf-8", capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("invalid subject", result.stderr)

    def test_invalid_commit_is_rejected_with_its_position(self):
        self.git("switch", "-c", "chore/no-issue-changes")
        self.commit("chore: good")
        self.commit("not conventional")
        head = self.git("rev-parse", "HEAD").stdout.strip()
        with self.assertRaisesRegex(PolicyError, "commit 1 has an invalid subject"):
            validate_commit_range(self.root, self.base, head,
                                   load_repository_policy(self.root))

    def test_missing_commit_and_invalid_sha_are_reported(self):
        with self.assertRaisesRegex(PolicyError, "full Git commit SHA"):
            validate_commit_range(self.root, "main", "HEAD", load_repository_policy(self.root))
        with self.assertRaisesRegex(PolicyError, "unavailable"):
            validate_commit_range(self.root, self.base, "0" * 40, load_repository_policy(self.root))


if __name__ == "__main__":
    unittest.main()
