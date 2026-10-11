from __future__ import annotations

from pathlib import Path
import sys
import unittest
import copy


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "policy"))
from policy import PolicyError, load_policy
from rules import complete_commit_message, complete_pr_body, complete_subject, extract_branch_issue, validate_branch, validate_subject


POLICY = load_policy(ROOT / "policy" / "shared.json", ROOT / "policy" / "local.json")


class NamingRulesTest(unittest.TestCase):
    def test_completion_uses_configured_issue_reference_templates(self):
        policy = copy.deepcopy(POLICY)
        policy["issue_reference"] = {
            "subject_suffix": " [issue:{issue}]",
            "pr_body_line": "Issue: #{issue}",
        }
        subject = "feat(implement-feature): 機能を追加"
        completed = complete_subject(subject, "123", policy)
        self.assertEqual(completed, subject + " [issue:123]")
        self.assertEqual(validate_subject(completed, policy).group("issue"), "123")
        self.assertEqual(complete_subject(completed, "123", policy), completed)
        self.assertEqual(complete_pr_body("Details", "123", policy), "Details\n\nIssue: #123")

    def test_subject_valid_forms(self):
        cases = (
            ("feat(implement-feature): 機能を追加 (#123)", True),
            ("fix!: issueなしの修正", True),
            ("docs: 文書を更新．", False),
        )
        for subject, valid in cases:
            with self.subTest(subject=subject):
                if valid:
                    validate_subject(subject, POLICY)
                else:
                    with self.assertRaises(PolicyError):
                        validate_subject(subject, POLICY)

    def test_subject_rejects_invalid_type_scope_breaking_summary_and_issue(self):
        cases = (
            "Feat: 不正な大文字",
            "feat(unknown): 不正なscope",
            "feat(): 空のscope",
            "feat: ",
            "feat: summary.",
            "feat: summary。",
            "feat: summary\n2行目",
            "feat: summary (#0)",
            "feat: summary (#abc)",
        )
        for subject in cases:
            with self.subTest(subject=subject), self.assertRaises(PolicyError):
                validate_subject(subject, POLICY)

    def test_branch_names_and_permanent_exceptions(self):
        self.assertEqual(validate_branch("feat/123-add-login", POLICY).group("issue"), "123")
        self.assertEqual(validate_branch("chore/no-issue-update-dependencies", POLICY).group("no_issue"), "no-issue")
        self.assertIsNone(validate_branch("main", POLICY))
        self.assertIsNone(validate_branch("master", POLICY))
        for branch in ("feat/0-add-login", "feat/123-Add-login", "feat/no-issue-Bad", "main/sub"):
            with self.subTest(branch=branch), self.assertRaises(PolicyError):
                validate_branch(branch, POLICY)

    def test_branch_exception_can_be_disabled_for_source_branches(self):
        with self.assertRaises(PolicyError):
            validate_branch("main", POLICY, allow_permanent=False)

    def test_issue_extraction_does_not_validate_unrecognized_branch_names(self):
        self.assertEqual(extract_branch_issue("feat/123-add-login", POLICY), "123")
        for branch in ("main", "chore/no-issue-update-dependencies",
                       "feature/3-install-shared-policy", "feat/0-add-login", "feat/123-Add-login"):
            with self.subTest(branch=branch):
                self.assertIsNone(extract_branch_issue(branch, POLICY))

    def test_issue_extraction_uses_the_configured_branch_format(self):
        policy = copy.deepcopy(POLICY)
        policy["branch_pattern"] = policy["branch_pattern"].replace("/", "__")
        self.assertEqual(extract_branch_issue("feat__123-add-login", policy), "123")
        self.assertIsNone(extract_branch_issue("feat/123-add-login", policy))

    def test_issue_extraction_respects_permanent_branch_exceptions(self):
        policy = copy.deepcopy(POLICY)
        policy["permanent_branches"].append("feat/123-add-login")
        self.assertIsNone(extract_branch_issue("feat/123-add-login", policy))

    def test_subject_completion_and_rerun_are_idempotent(self):
        subject = "feat(implement-feature): 機能を追加"
        completed = complete_subject(subject, "123", POLICY)
        self.assertEqual(completed, subject + " (#123)")
        self.assertEqual(complete_subject(completed, "123", POLICY), completed)

    def test_matching_existing_issue_is_preserved(self):
        subject = "feat(implement-feature): 機能を追加 (#123)"
        self.assertEqual(complete_subject(subject, "123", POLICY), subject)
        self.assertEqual(validate_subject(subject, POLICY).group("issue"), "123")

    def test_mismatching_existing_issue_is_rejected(self):
        with self.assertRaisesRegex(PolicyError, "references #124.*#123"):
            complete_subject("feat: 機能を追加 (#124)", "123", POLICY)

    def test_no_issue_branch_does_not_add_or_remove_reference(self):
        subject = "feat: 機能を追加"
        self.assertEqual(complete_subject(subject, None, POLICY), subject)
        referenced = subject + " (#124)"
        self.assertEqual(complete_subject(referenced, None, POLICY), referenced)

    def test_invalid_issue_inputs_are_rejected(self):
        for number in ("", "0", "01", "-1", "abc"):
            with self.subTest(number=number), self.assertRaises(PolicyError):
                complete_subject("feat: summary", number, POLICY)

    def test_pr_body_preserves_other_references_and_is_idempotent(self):
        body = "# Detail\n\nRefs #99\nSee #101"
        completed = complete_pr_body(body, "123", POLICY)
        self.assertTrue(completed.startswith(body + "\n\n"))
        self.assertIn("Refs #99", completed)
        self.assertIn("See #101", completed)
        self.assertTrue(completed.endswith("Refs #123"))
        self.assertEqual(complete_pr_body(completed, "123", POLICY), completed)

    def test_pr_body_reference_at_eof_is_not_duplicated(self):
        for body in ("Refs #123", "detail\nRefs #123\n", "Refs #123\n\n"):
            with self.subTest(body=body):
                self.assertEqual(complete_pr_body(body, "123", POLICY), body)

    def test_no_issue_leaves_pr_body_byte_for_byte_unchanged(self):
        body = "Text\r\n\r\nCloses #99"
        self.assertEqual(complete_pr_body(body, None, POLICY), body)

    def test_commit_message_completion_preserves_body_and_line_endings(self):
        for newline in ("\n", "\r\n", "\r"):
            with self.subTest(newline=repr(newline)):
                message = "feat(implement-feature): 機能を追加" + newline + newline + "Details #99"
                result = complete_commit_message(message, "123", POLICY)
                self.assertTrue(result.startswith("feat(implement-feature): 機能を追加 (#123)" + newline))
                self.assertTrue(result.endswith(newline + "Details #99"))
                self.assertEqual(complete_commit_message(result, "123", POLICY), result)

    def test_commit_message_without_issue_keeps_original_bytes(self):
        message = "feat: summary\r\n\r\nbody\r\n"
        self.assertEqual(complete_commit_message(message, None, POLICY), message)

    def test_completion_rejects_invalid_subject(self):
        with self.assertRaises(PolicyError):
            complete_commit_message("feat(scope): summary", "123", POLICY)


if __name__ == "__main__":
    unittest.main()
