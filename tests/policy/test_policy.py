from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "policy"))
from policy import PolicyError, load_policy
from generate_docs import render_document


SCRIPT = ROOT / "scripts" / "policy" / "generate_docs.py"
SHARED = ROOT / "policy" / "shared.json"
LOCAL = ROOT / "policy" / "local.json"


class PolicyTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.shared = self.root / "shared.json"
        self.local = self.root / "local.json"
        self.config = json.loads(SHARED.read_text(encoding="utf-8"))
        self.write(self.shared, self.config)

    @staticmethod
    def write(path, value):
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def effective(self, local):
        self.write(self.local, local)
        return load_policy(self.shared, self.local)

    def run_cli(self, *arguments):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--shared", str(self.shared), *arguments],
            cwd=self.root, capture_output=True,
        )

    def test_defaults_without_local_configuration(self):
        policy = load_policy(self.shared)
        self.assertEqual(policy["scope"], {"allowed": None, "required": False, "required_for_types": []})
        self.assertEqual(policy["permanent_branches"], ["main", "master"])
        self.assertEqual(policy["guidance"], [])

    def test_partial_scope_override_preserves_shared_defaults(self):
        policy = self.effective({"schema_version": 1, "scope": {"allowed": ["auth"]}})
        self.assertEqual(policy["scope"], {"allowed": ["auth"], "required": False, "required_for_types": []})

    def test_local_lists_replace_defaults_and_can_be_empty(self):
        policy = self.effective({"schema_version": 1, "permanent_branches": [], "guidance": []})
        self.assertEqual(policy["permanent_branches"], [])
        self.assertEqual(policy["guidance"], [])

    def test_loading_does_not_modify_inputs(self):
        self.write(self.local, {"schema_version": 1, "scope": {"required": True}})
        before = [path.read_bytes() for path in (self.shared, self.local)]
        load_policy(self.shared, self.local)
        self.assertEqual(before, [path.read_bytes() for path in (self.shared, self.local)])

    def test_explicit_missing_local_configuration_is_an_error(self):
        with self.assertRaisesRegex(PolicyError, "local.json"):
            load_policy(self.shared, self.local)

    def test_invalid_local_settings(self):
        invalid = [
            {"types": []},
            {"scope": {"require": True}},
            {"scope": {"required": "false"}},
            {"scope": {"required_for_types": ["unknown"]}},
            {"scope": {"allowed": "auth"}},
            {"scope": {"allowed": ["auth", "auth"]}},
            {"scope": {"allowed": ["bad scope"]}},
            {"scope": {"allowed": ["bad(scope)"]}},
            {"scope": {"allowed": [42]}},
            {"scope": {"allowed": [], "required": True}},
            {"scope": {"allowed": [], "required_for_types": ["feat"]}},
            {"permanent_branches": ["main", "main"]},
            {"guidance": ["first\nsecond"]},
            {"guidance": [""]},
        ]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(PolicyError):
                self.effective({"schema_version": 1, **value})

    def test_version_is_required_and_must_be_supported_integer(self):
        for value in ({}, {"schema_version": 2}, {"schema_version": True}, {"schema_version": 1.0}):
            with self.subTest(value=value), self.assertRaises(PolicyError):
                self.effective(value)

    def test_duplicate_json_keys_are_rejected(self):
        self.local.write_text('{"schema_version": 1, "scope": {}, "scope": {}}', encoding="utf-8")
        with self.assertRaisesRegex(PolicyError, "duplicate JSON key"):
            load_policy(self.shared, self.local)

    def test_malformed_json_has_path_diagnostic(self):
        self.local.write_text('{', encoding="utf-8")
        with self.assertRaisesRegex(PolicyError, "local.json"):
            load_policy(self.shared, self.local)

    def test_utf8_bom_is_accepted(self):
        self.local.write_text('{"schema_version": 1}', encoding="utf-8-sig")
        self.assertEqual(load_policy(self.shared, self.local)["scope"]["allowed"], None)

    def test_invalid_shared_settings(self):
        invalid = [
            {"schema_version": 2},
            {"types": []},
            {"types": [{"name": "Feat", "description": "機能"}]},
            {"types": [self.config["types"][0]] * 2},
            {"summary_forbidden_endings": [".", "."]},
            {"issue_reference": {"subject_suffix": " (#{issue})", "pr_body_line": "Closes #{issue}"}},
            {"issue_reference": {"subject_suffix": " (#{issue}) ", "pr_body_line": "Refs #{issue}"}},
            {"branch_pattern": "(?P<type>{types})"},
            {"branch_pattern": "^(?P<type>{types})[$"},
            {"branch_pattern": "^(?P<type>{types})$"},
            {"subject_pattern": "^[a-z]+$"},
            {"defaults": {"scope": {}, "permanent_branches": []}},
        ]
        for change in invalid:
            with self.subTest(change=change):
                self.write(self.shared, {**copy.deepcopy(self.config), **change})
                with self.assertRaises(PolicyError):
                    load_policy(self.shared)

    def test_generated_document_uses_effective_settings(self):
        policy = self.effective({
            "schema_version": 1,
            "scope": {"allowed": ["auth", "api"], "required_for_types": ["feat", "fix"]},
            "permanent_branches": ["develop"], "guidance": ["責務に合わせて選ぶ。"],
        })
        document = render_document(policy)
        for text in ("許可一覧: `auth`、`api`", "`feat`、`fix`で必須", "例外: `develop`", "責務に合わせて選ぶ。"):
            self.assertIn(text, document)
        self.assertNotIn("`master`", document)

    def test_generated_document_uses_changed_shared_type_and_punctuation(self):
        self.config["types"] = [{"name": "custom", "description": "独自の変更"}]
        self.config["summary_forbidden_endings"] = ["。"]
        self.write(self.shared, self.config)
        document = render_document(load_policy(self.shared))
        self.assertIn("`custom`: 独自の変更", document)
        self.assertIn("(?P<type>(?:custom))", document)
        self.assertNotIn("`feat`", document)
        self.assertIn("使えない文字: `。`", document)

    def test_generated_document_uses_configured_issue_reference_templates(self):
        self.config["issue_reference"] = {
            "subject_suffix": " [issue:{issue}]",
            "pr_body_line": "Issue: #{issue}",
        }
        self.write(self.shared, self.config)
        document = render_document(load_policy(self.shared))
        self.assertIn("件名・タイトル末尾: ` [issue:<issue番号>]`", document)
        self.assertIn("PR本文の参照行: `Issue: #<issue番号>`", document)

    def test_optional_and_required_scopes_are_documented(self):
        cases = [
            ({"allowed": []}, "scopeの指定不可"),
            ({"required": True}, "すべてのtypeで必須"),
            ({}, "省略可能"),
        ]
        for scope, text in cases:
            with self.subTest(scope=scope):
                self.assertIn(text, render_document(self.effective({"schema_version": 1, "scope": scope})))

    def test_checked_in_document_is_current(self):
        self.assertEqual((ROOT / "policy" / "NAMING.md").read_bytes(),
                         render_document(load_policy(SHARED, LOCAL)).encode("utf-8"))

    def test_repository_allowed_scopes_match_skill_directory_names(self):
        directories = sorted(path.parent.name for path in (ROOT / "skills").glob("*/*/SKILL.md"))
        self.assertEqual(sorted(load_policy(SHARED, LOCAL)["scope"]["allowed"]), directories)

    def test_example_configuration_is_valid(self):
        policy = load_policy(SHARED, ROOT / "policy" / "local.example.json")
        self.assertEqual(policy["scope"]["required_for_types"], ["feat", "fix"])

    def test_cli_generation_is_deterministic_and_check_is_read_only(self):
        output = self.root / "命名規約.md"
        args = ["--output", str(output)]
        self.assertEqual(self.run_cli(*args).returncode, 0)
        before = output.read_bytes()
        self.assertEqual(self.run_cli(*args).returncode, 0)
        self.assertEqual(output.read_bytes(), before)
        self.assertNotIn(b"\r\n", before)
        self.assertEqual(self.run_cli(*args, "--check").returncode, 0)
        self.assertEqual(output.read_bytes(), before)
        output.write_bytes(b"manual edit")
        result = self.run_cli(*args, "--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn(b"out of date", result.stderr)
        self.assertEqual(output.read_bytes(), b"manual edit")

    def test_cli_error_preserves_existing_output(self):
        output = self.root / "NAMING.md"
        output.write_bytes(b"existing document")
        self.write(self.local, {"schema_version": 1, "scope": {"required": "false"}})
        result = self.run_cli("--local", str(self.local), "--output", str(output))
        self.assertEqual(result.returncode, 1)
        self.assertIn(b"local.scope.required", result.stderr)
        self.assertNotIn(b"Traceback", result.stderr)
        self.assertEqual(output.read_bytes(), b"existing document")

    def test_cli_stdout_is_utf8(self):
        result = self.run_cli("--output", "-")
        self.assertEqual(result.returncode, 0)
        self.assertIn("命名規約", result.stdout.decode("utf-8"))

    def test_cli_uses_explicit_local_settings_from_another_directory(self):
        self.write(self.local, {
            "schema_version": 1, "scope": {"allowed": ["auth"], "required": True},
            "permanent_branches": ["develop"],
        })
        result = self.run_cli("--local", str(self.local), "--output", "-")
        self.assertEqual(result.returncode, 0)
        document = result.stdout.decode("utf-8")
        self.assertIn("許可一覧: `auth`", document)
        self.assertIn("すべてのtypeで必須", document)
        self.assertIn("例外: `develop`", document)

    def test_cli_does_not_overwrite_configuration_inputs(self):
        self.write(self.local, {"schema_version": 1})
        for path in (self.shared, self.local):
            before = path.read_bytes()
            result = self.run_cli("--local", str(self.local), "--output", str(path))
            self.assertEqual(result.returncode, 1)
            self.assertEqual(path.read_bytes(), before)

    def test_check_requires_existing_file_output(self):
        for output in ("-", str(self.root / "missing.md")):
            with self.subTest(output=output):
                self.assertEqual(self.run_cli("--output", output, "--check").returncode, 1)


if __name__ == "__main__":
    unittest.main()
