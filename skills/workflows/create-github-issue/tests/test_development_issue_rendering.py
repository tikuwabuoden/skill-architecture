from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


WORKFLOW_ROOT = Path(__file__).parents[1]
SKILLS_ROOT = Path(__file__).parents[3]
SCRIPT = SKILLS_ROOT / "capabilities" / "render-markdown" / "scripts" / "render_markdown.py"
FORMAT_ROOT = WORKFLOW_ROOT / "assets" / "development-issue"
SCHEMA = FORMAT_ROOT / "schema.json"
TEMPLATE = FORMAT_ROOT / "template.md"


def valid_issue() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "title": "検索結果に開発Issueの詳細を表示する",
        "background": ["利用者は検索結果から次の作業を判断できない"],
        "goal": "検索結果に実装へ必要な情報を表示する",
        "acceptanceCriteria": [
            "検索結果に対象の概要が表示される",
            "既存の検索条件とURLが維持される",
        ],
        "scope": ["検索結果の表示データと画面を変更する"],
        "outOfScope": ["検索方式の変更は扱わない"],
        "verification": ["既存テストと表示確認を実行する"],
        "dependencies": ["検索APIのレスポンス契約"],
        "risks": ["古いレスポンスでは情報が表示されない可能性がある"],
    }


class DevelopmentIssueRenderingTest(unittest.TestCase):
    def render(
        self, issue: object
    ) -> tuple[subprocess.CompletedProcess[bytes], Path, tempfile.TemporaryDirectory[str]]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        output_path = root / "issue.md"
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--schema",
                str(SCHEMA),
                "--template",
                str(TEMPLATE),
                "--data",
                "-",
                "--output",
                str(output_path),
            ],
            input=json.dumps(issue, ensure_ascii=False).encode("utf-8"),
            cwd=root,
            capture_output=True,
            check=False,
        )
        self.assertEqual(set(root.iterdir()), {output_path} if result.returncode == 0 else set())
        return result, output_path, temporary

    def test_workflow_resources_render_complete_issue(self) -> None:
        result, output_path, temporary = self.render(valid_issue())
        self.addCleanup(temporary.cleanup)

        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8"))
        markdown = output_path.read_text(encoding="utf-8")
        self.assertTrue(markdown.startswith("## Background\n\n"))
        self.assertNotRegex(markdown, r"(?m)^# ")
        self.assertNotIn("# 検索結果に開発Issueの詳細を表示する\n", markdown)
        self.assertIn("## Background\n\n- 利用者は検索結果から次の作業を判断できない", markdown)
        self.assertIn("## Acceptance criteria\n\n- [ ] 検索結果に対象の概要が表示される", markdown)
        self.assertIn("## Dependencies\n\n- 検索APIのレスポンス契約", markdown)
        self.assertIn("## Risks\n\n- 古いレスポンスでは情報が表示されない可能性がある", markdown)
        self.assertNotIn(b"\r\n", output_path.read_bytes())

    def test_optional_lists_render_empty_state(self) -> None:
        issue = valid_issue()
        issue["dependencies"] = []
        issue["risks"] = []
        result, output_path, temporary = self.render(issue)
        self.addCleanup(temporary.cleanup)

        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8"))
        markdown = output_path.read_text(encoding="utf-8")
        self.assertIn("## Dependencies\n\n- None identified", markdown)
        self.assertIn("## Risks\n\n- None identified", markdown)

    def test_schema_rejects_missing_acceptance_criteria(self) -> None:
        issue = valid_issue()
        del issue["acceptanceCriteria"]
        result, output_path, temporary = self.render(issue)
        self.addCleanup(temporary.cleanup)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "data: missing keys: acceptanceCriteria",
            result.stderr.decode("utf-8"),
        )
        self.assertFalse(output_path.exists())

    def test_schema_rejects_markdown_code_fence_in_goal(self) -> None:
        issue = valid_issue()
        issue["goal"] = "```unsafe```"
        result, output_path, temporary = self.render(issue)
        self.addCleanup(temporary.cleanup)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("data.goal: does not match required pattern", result.stderr.decode("utf-8"))
        self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main()
