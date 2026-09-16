#!/usr/bin/env python3
"""Validate structured data and render a deterministic Markdown template."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn


TAG = re.compile(r"{{(.*?)}}", re.DOTALL)
PATH = re.compile(r"(?:this|@[a-z]+|[A-Za-z][A-Za-z0-9_-]*)(?:\.[A-Za-z][A-Za-z0-9_-]*)*")


class RenderError(ValueError):
    """Raised when data, schema, or template input is invalid."""


@dataclass(frozen=True)
class Node:
    kind: str
    value: str = ""
    children: tuple["Node", ...] = ()
    alternative: tuple["Node", ...] = ()


@dataclass(frozen=True)
class Context:
    value: object
    index: int | None = None


def _object_without_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise RenderError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path | None, source: str, label: str) -> object:
    try:
        if source == "-":
            raw_text = sys.stdin.buffer.read().decode("utf-8")
        else:
            assert path is not None
            raw_text = path.read_text(encoding="utf-8")
        return json.loads(raw_text, object_pairs_hook=_object_without_duplicate_keys)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RenderError(f"cannot read {label}: {exc}") from exc


def _same_json_value(left: object, right: object) -> bool:
    return type(left) is type(right) and left == right


def _matches_type(value: object, expected: str) -> bool:
    checks = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }
    return checks.get(expected, False)


def validate_schema_definition(schema: object, location: str = "schema") -> dict[str, object]:
    if not isinstance(schema, dict):
        raise RenderError(f"{location}: expected an object")
    supported = {
        "$schema",
        "title",
        "description",
        "type",
        "const",
        "enum",
        "anyOf",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "minItems",
        "minLength",
        "pattern",
    }
    unknown = sorted(set(schema) - supported)
    if unknown:
        raise RenderError(f"{location}: unsupported keywords: {', '.join(unknown)}")

    schema_type = schema.get("type")
    valid_types = {"object", "array", "string", "integer", "number", "boolean", "null"}
    if schema_type is not None and schema_type not in valid_types:
        raise RenderError(f"{location}.type: unsupported JSON type")
    if "anyOf" in schema:
        choices = schema["anyOf"]
        if not isinstance(choices, list) or not choices:
            raise RenderError(f"{location}.anyOf: expected a non-empty array")
        for index, choice in enumerate(choices):
            validate_schema_definition(choice, f"{location}.anyOf[{index}]")
    if "properties" in schema:
        properties = schema["properties"]
        if not isinstance(properties, dict):
            raise RenderError(f"{location}.properties: expected an object")
        for name, child in properties.items():
            validate_schema_definition(child, f"{location}.properties.{name}")
    if "required" in schema:
        required = schema["required"]
        if not isinstance(required, list) or any(not isinstance(item, str) for item in required):
            raise RenderError(f"{location}.required: expected an array of strings")
        if len(required) != len(set(required)):
            raise RenderError(f"{location}.required: duplicate property names")
    if "additionalProperties" in schema and not isinstance(schema["additionalProperties"], bool):
        raise RenderError(f"{location}.additionalProperties: expected a boolean")
    if "items" in schema:
        validate_schema_definition(schema["items"], f"{location}.items")
    for keyword in ("minItems", "minLength"):
        if keyword in schema:
            value = schema[keyword]
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise RenderError(f"{location}.{keyword}: expected a non-negative integer")
    if "pattern" in schema:
        pattern = schema["pattern"]
        if not isinstance(pattern, str):
            raise RenderError(f"{location}.pattern: expected a string")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise RenderError(f"{location}.pattern: invalid regular expression: {exc}") from exc
    if "enum" in schema and (not isinstance(schema["enum"], list) or not schema["enum"]):
        raise RenderError(f"{location}.enum: expected a non-empty array")
    return schema


def validate(value: object, schema: dict[str, object], location: str = "data") -> None:
    if "anyOf" in schema:
        errors: list[str] = []
        choices = schema["anyOf"]
        assert isinstance(choices, list)
        for choice in choices:
            assert isinstance(choice, dict)
            try:
                validate(value, choice, location)
                break
            except RenderError as exc:
                errors.append(str(exc))
        else:
            raise RenderError(f"{location}: does not match any allowed schema ({'; '.join(errors)})")

    schema_type = schema.get("type")
    if isinstance(schema_type, str) and not _matches_type(value, schema_type):
        raise RenderError(f"{location}: expected type {schema_type}")
    if "const" in schema and not _same_json_value(value, schema["const"]):
        raise RenderError(f"{location}: expected constant {schema['const']!r}")
    enum = schema.get("enum")
    if isinstance(enum, list) and not any(_same_json_value(value, item) for item in enum):
        raise RenderError(f"{location}: value is not in enum")

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            properties = {}
        required = schema.get("required", [])
        if not isinstance(required, list):
            required = []
        missing = sorted(set(required) - set(value))
        if missing:
            raise RenderError(f"{location}: missing keys: {', '.join(missing)}")
        if schema.get("additionalProperties") is False:
            unknown = sorted(set(value) - set(properties))
            if unknown:
                raise RenderError(f"{location}: unknown keys: {', '.join(unknown)}")
        for name, child_value in value.items():
            child_schema = properties.get(name)
            if isinstance(child_schema, dict):
                validate(child_value, child_schema, f"{location}.{name}")
    if isinstance(value, list):
        minimum = schema.get("minItems")
        if isinstance(minimum, int) and len(value) < minimum:
            raise RenderError(f"{location}: expected at least {minimum} item(s)")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                validate(item, item_schema, f"{location}[{index}]")
    if isinstance(value, str):
        minimum = schema.get("minLength")
        if isinstance(minimum, int) and len(value) < minimum:
            raise RenderError(f"{location}: expected at least {minimum} character(s)")
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.search(pattern, value) is None:
            raise RenderError(f"{location}: does not match required pattern")


def parse_template(template: str) -> tuple[Node, ...]:
    normalized = template.replace("\r\n", "\n").replace("\r", "\n")
    without_tags = TAG.sub("", normalized)
    if "{{" in without_tags or "}}" in without_tags:
        raise RenderError("template: unmatched braces")

    def parse_from(position: int, stops: set[str]) -> tuple[list[Node], int, str | None]:
        nodes: list[Node] = []
        while True:
            match = TAG.search(normalized, position)
            if match is None:
                nodes.append(Node("text", normalized[position:]))
                return nodes, len(normalized), None
            nodes.append(Node("text", normalized[position : match.start()]))
            tag = match.group(1).strip()
            if tag in stops:
                return nodes, match.end(), tag
            if tag.startswith("#each ") or tag.startswith("#if "):
                kind, path = tag[1:].split(maxsplit=1)
                if PATH.fullmatch(path) is None:
                    raise RenderError(f"template: invalid path: {path}")
                alternate_tag = "#empty" if kind == "each" else "#else"
                close_tag = f"/{kind}"
                children, next_position, stop = parse_from(match.end(), {alternate_tag, close_tag})
                alternative: list[Node] = []
                if stop == alternate_tag:
                    alternative, next_position, stop = parse_from(next_position, {close_tag})
                if stop != close_tag:
                    raise RenderError(f"template: missing {{{{{close_tag}}}}}")
                nodes.append(Node(kind, path, tuple(children), tuple(alternative)))
                position = next_position
                continue
            if tag.startswith("#") or tag.startswith("/"):
                raise RenderError(f"template: unexpected tag: {{{{{tag}}}}}")
            if PATH.fullmatch(tag) is None:
                raise RenderError(f"template: invalid tag: {{{{{tag}}}}}")
            nodes.append(Node("value", tag))
            position = match.end()

    nodes, _, stop = parse_from(0, set())
    if stop is not None:
        raise RenderError(f"template: unexpected tag: {{{{{stop}}}}}")
    return tuple(nodes)


def resolve(path: str, context: Context) -> object:
    parts = path.split(".")
    first = parts.pop(0)
    if first == "this":
        value = context.value
    elif first == "@index":
        value = context.index
    elif first == "@number":
        value = None if context.index is None else context.index + 1
    elif isinstance(context.value, dict) and first in context.value:
        value = context.value[first]
    else:
        raise RenderError(f"template: unknown path: {path}")
    for part in parts:
        if not isinstance(value, dict) or part not in value:
            raise RenderError(f"template: unknown path: {path}")
        value = value[part]
    return value


def render_nodes(nodes: tuple[Node, ...], context: Context) -> str:
    output: list[str] = []
    for node in nodes:
        if node.kind == "text":
            output.append(node.value)
        elif node.kind == "value":
            value = resolve(node.value, context)
            if value is None or isinstance(value, (dict, list)):
                raise RenderError(f"template: path is not a scalar: {node.value}")
            output.append("true" if value is True else "false" if value is False else str(value))
        elif node.kind == "each":
            value = resolve(node.value, context)
            if not isinstance(value, list):
                raise RenderError(f"template: #each path is not an array: {node.value}")
            if value:
                for index, item in enumerate(value):
                    output.append(render_nodes(node.children, Context(item, index)))
            else:
                output.append(render_nodes(node.alternative, context))
        elif node.kind == "if":
            value = resolve(node.value, context)
            branch = node.children if value else node.alternative
            output.append(render_nodes(branch, context))
        else:  # pragma: no cover
            raise RenderError(f"template: unsupported node: {node.kind}")
    return "".join(output)


def _fail(message: str) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate JSON data and render a deterministic Markdown template."
    )
    parser.add_argument("--schema", required=True, type=Path)
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--data", required=True, help="JSON data path or '-' for stdin")
    parser.add_argument("--output", required=True, help="Markdown path or '-' for stdout")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    schema_path = args.schema.resolve()
    template_path = args.template.resolve()
    try:
        schema = validate_schema_definition(load_json(schema_path, str(schema_path), "schema"))
        data_path = None if args.data == "-" else Path(args.data).resolve()
        data = load_json(data_path, args.data, "JSON data")
        validate(data, schema)
        template = template_path.read_text(encoding="utf-8")
        result = render_nodes(parse_template(template), Context(data)).rstrip("\n") + "\n"
    except (OSError, UnicodeError) as exc:
        _fail(f"cannot read template {template_path}: {exc}")
    except RenderError as exc:
        _fail(str(exc))

    if args.output == "-":
        sys.stdout.buffer.write(result.encode("utf-8"))
        return 0

    output_path = Path(args.output).resolve()
    if output_path.exists() and not args.overwrite:
        _fail(f"output already exists: {output_path}; pass --overwrite to replace it")
    if not output_path.parent.is_dir():
        _fail(f"output directory does not exist: {output_path.parent}")
    try:
        with output_path.open("w", encoding="utf-8", newline="\n") as output_file:
            output_file.write(result)
    except OSError as exc:
        _fail(f"cannot write output file {output_path}: {exc}")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
