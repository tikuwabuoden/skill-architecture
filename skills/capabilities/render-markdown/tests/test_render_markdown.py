from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).parents[1]
SCRIPT = SKILL_ROOT / "scripts" / "render_markdown.py"


def generic_schema() -> dict[str, object]:
    line = {"type": "string", "minLength": 1, "pattern": r"^(?!.*[\r\n])(?=.*\S).+$"}
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["title", "items", "note"],
        "properties": {
            "title": line,
            "items": {"type": "array", "items": line},
            "note": {"anyOf": [{"type": "null"}, line]},
        },
    }


TEMPLATE = """# {{ title }}

{{#each items}}- {{ @number }}. {{ this }}
{{#empty}}- なし
{{/each}}
{{#if note}}{{ note }}
{{#else}}注記なし
{{/if}}
"""


class RenderMarkdownTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.schema = self.root / "schema.json"
        self.template = self.root / "template.md"
        self.schema.write_text(json.dumps(generic_schema()), encoding="utf-8")
        self.template.write_text(TEMPLATE, encoding="utf-8")

    def run_renderer(
        self,
        document: object,
        *,
        schema: Path | None = None,
        template: Path | None = None,
        output: str = "result.md",
        overwrite: bool = False,
    ) -> tuple[subprocess.CompletedProcess[bytes], Path]:
        output_path = self.root / output if output != "-" else Path("-")
        command = [
            sys.executable,
            str(SCRIPT),
            "--schema",
            str(schema or self.schema),
            "--template",
            str(template or self.template),
            "--data",
            "-",
            "--output",
            str(output_path),
        ]
        if overwrite:
            command.append("--overwrite")
        return subprocess.run(
            command,
            input=json.dumps(document, ensure_ascii=False).encode("utf-8"),
            capture_output=True,
            check=False,
            cwd=self.root,
        ), output_path

    def test_renders_generic_template_blocks(self) -> None:
        result, output_path = self.run_renderer(
            {"title": "更新情報", "items": ["追加", "修正"], "note": None}
        )

        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8"))
        self.assertEqual(
            output_path.read_text(encoding="utf-8"),
            "# 更新情報\n\n- 1. 追加\n- 2. 修正\n\n注記なし\n",
        )
        self.assertNotIn(b"\r\n", output_path.read_bytes())

    def test_renders_empty_and_present_branches(self) -> None:
        result, output_path = self.run_renderer(
            {"title": "更新情報", "items": [], "note": "破壊的変更なし"}
        )

        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8"))
        markdown = output_path.read_text(encoding="utf-8")
        self.assertIn("- なし\n", markdown)
        self.assertTrue(markdown.endswith("破壊的変更なし\n"))

    def test_accepts_data_from_stdin_and_writes_utf8_to_stdout(self) -> None:
        data = json.dumps(
            {"title": "更新情報", "items": ["追加"], "note": None}, ensure_ascii=False
        ).encode("utf-8")
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--schema",
                str(self.schema),
                "--template",
                str(self.template),
                "--data",
                "-",
                "--output",
                "-",
            ],
            input=data,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8"))
        self.assertTrue(result.stdout.startswith("# 更新情報\n".encode("utf-8")))
        self.assertNotIn(b"\r\n", result.stdout)

    def test_rejects_missing_and_unknown_data_keys(self) -> None:
        result, output_path = self.run_renderer({"title": "更新情報", "extra": []})

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing keys: items, note", result.stderr.decode("utf-8"))
        self.assertFalse(output_path.exists())

    def test_rejects_data_that_violates_schema_pattern(self) -> None:
        result, output_path = self.run_renderer(
            {"title": "更新情報\n", "items": [], "note": None}
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("data.title: does not match required pattern", result.stderr.decode("utf-8"))
        self.assertFalse(output_path.exists())

    def test_rejects_unsupported_schema_keyword(self) -> None:
        schema = generic_schema()
        schema["definitions"] = {}
        self.schema.write_text(json.dumps(schema), encoding="utf-8")
        result, output_path = self.run_renderer(
            {"title": "更新情報", "items": [], "note": None}
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsupported keywords: definitions", result.stderr.decode("utf-8"))
        self.assertFalse(output_path.exists())

    def test_rejects_unknown_template_path(self) -> None:
        self.template.write_text("# {{ unknown }}\n", encoding="utf-8")
        result, output_path = self.run_renderer(
            {"title": "更新情報", "items": [], "note": None}
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("template: unknown path: unknown", result.stderr.decode("utf-8"))
        self.assertFalse(output_path.exists())

    def test_rejects_unclosed_template_block(self) -> None:
        self.template.write_text("{{#each items}}{{ this }}", encoding="utf-8")
        result, output_path = self.run_renderer(
            {"title": "更新情報", "items": [], "note": None}
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("template: missing {{/each}}", result.stderr.decode("utf-8"))
        self.assertFalse(output_path.exists())

    def test_rejects_duplicate_json_keys(self) -> None:
        output_path = self.root / "result.md"
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--schema",
                str(self.schema),
                "--template",
                str(self.template),
                "--data",
                "-",
                "--output",
                str(output_path),
            ],
            input=b'{"title":"a","title":"b"}',
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate JSON key: title", result.stderr.decode("utf-8"))
        self.assertFalse(output_path.exists())

    def test_rejects_file_input(self) -> None:
        result = subprocess.run(
            [
                sys.executable, str(SCRIPT),
                "--schema", str(self.schema),
                "--template", str(self.template),
                "--data", str(self.root / "data.json"),
                "--output", str(self.root / "result.md"),
            ],
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid choice", result.stderr.decode("utf-8"))
        self.assertEqual(set(self.root.iterdir()), {self.schema, self.template})

    def test_leaves_no_intermediate_files_on_success_or_failure(self) -> None:
        for document in (
            {"title": "更新情報", "items": [], "note": None},
            {"title": "更新情報"},
        ):
            with self.subTest(document=document):
                result, _ = self.run_renderer(document, output="-")
                self.assertEqual(result.returncode == 0, "items" in document)
                self.assertEqual(set(self.root.iterdir()), {self.schema, self.template})

    def test_refuses_to_replace_existing_output_without_flag(self) -> None:
        document = {"title": "更新情報", "items": [], "note": None}
        result, output_path = self.run_renderer(document)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8"))
        original = output_path.read_bytes()

        refused, _ = self.run_renderer(document)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("output already exists", refused.stderr.decode("utf-8"))
        self.assertEqual(output_path.read_bytes(), original)

        document["title"] = "変更後"
        replaced, _ = self.run_renderer(document, overwrite=True)
        self.assertEqual(replaced.returncode, 0, replaced.stderr.decode("utf-8"))
        self.assertTrue(output_path.read_bytes().startswith("# 変更後\n".encode("utf-8")))


if __name__ == "__main__":
    unittest.main()
