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
FORMAT_ROOT = WORKFLOW_ROOT / "assets" / "implementation-plan"
SCHEMA = FORMAT_ROOT / "schema.json"
TEMPLATE = FORMAT_ROOT / "template.md"


def valid_plan() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "title": "機能実装計画",
        "behavior": ["リリース履歴を確認できる"],
        "outOfScope": [],
        "approach": ["既存の静的生成を維持する"],
        "implementationUnits": [
            {
                "name": "リリースデータ",
                "outcome": "検証済みのリリース情報を保持できる",
                "changes": ["リリーススキーマを追加する"],
                "dependsOn": [],
                "verification": ["正しいデータを読み込めることを確認する"],
            },
            {
                "name": "履歴表示",
                "outcome": "OSSごとのリリース履歴を表示できる",
                "changes": ["詳細ページへ履歴を追加する"],
                "dependsOn": ["リリースデータ"],
                "verification": ["新しい順に表示されることを確認する"],
            },
        ],
        "responsibilities": ["データ取得と表示を分離する"],
        "flowDiagram": {
            "type": "mermaid",
            "source": "flowchart TD\n  A[取得] --> B[表示]",
        },
        "interfaceImpacts": [],
        "constraints": ["既存URLを維持する"],
        "verification": ["型検査とビルドを実行する"],
        "risks": [],
    }


class ImplementationPlanRenderingTest(unittest.TestCase):
    def render(self, plan: object) -> tuple[subprocess.CompletedProcess[bytes], Path, tempfile.TemporaryDirectory[str]]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        output_path = root / "plan.md"
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
            input=json.dumps(plan, ensure_ascii=False).encode("utf-8"),
            cwd=root,
            capture_output=True,
            check=False,
        )
        self.assertEqual(set(root.iterdir()), {output_path} if result.returncode == 0 else set())
        return result, output_path, temporary

    def test_workflow_resources_render_complete_plan(self) -> None:
        result, output_path, temporary = self.render(valid_plan())
        self.addCleanup(temporary.cleanup)

        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8"))
        markdown = output_path.read_text(encoding="utf-8")
        self.assertIn("# 機能実装計画\n", markdown)
        self.assertIn("### 1. リリースデータ\n", markdown)
        self.assertIn("### 2. 履歴表示\n", markdown)
        self.assertIn("#### 前提となる単位\n\n- なし", markdown)
        self.assertIn("```mermaid\nflowchart TD\n  A[取得] --> B[表示]\n```", markdown)
        self.assertNotIn(b"\r\n", output_path.read_bytes())

    def test_workflow_schema_rejects_incomplete_unit(self) -> None:
        plan = valid_plan()
        unit = plan["implementationUnits"][0]  # type: ignore[index]
        del unit["verification"]  # type: ignore[index]
        result, output_path, temporary = self.render(plan)
        self.addCleanup(temporary.cleanup)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "data.implementationUnits[0]: missing keys: verification",
            result.stderr.decode("utf-8"),
        )
        self.assertFalse(output_path.exists())

    def test_workflow_schema_rejects_code_fence_in_diagram(self) -> None:
        plan = valid_plan()
        plan["flowDiagram"] = {"type": "mermaid", "source": "```mermaid\nA --> B\n```"}
        result, output_path, temporary = self.render(plan)
        self.addCleanup(temporary.cleanup)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("data.flowDiagram", result.stderr.decode("utf-8"))
        self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main()
