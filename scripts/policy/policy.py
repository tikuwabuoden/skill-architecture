"""Load the shared naming policy and a separately owned repository configuration."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path


class PolicyError(ValueError):
    """An invalid configuration, with a location suitable for user diagnostics."""


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise PolicyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"),
                           object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, ValueError) as exc:
        raise PolicyError(f"{path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PolicyError(f"{path}: expected a JSON object")
    return value


def _keys(value: object, allowed: set[str], required: set[str], label: str) -> dict:
    if not isinstance(value, dict):
        raise PolicyError(f"{label}: expected an object")
    unknown = value.keys() - allowed
    missing = required - value.keys()
    if unknown or missing:
        raise PolicyError(f"{label}: unknown keys {sorted(unknown)}, missing keys {sorted(missing)}")
    return value


def _strings(value: object, label: str) -> list[str]:
    if not isinstance(value, list):
        raise PolicyError(f"{label}: expected an array")
    if any(not isinstance(item, str) or not item.strip() or
           ("\n" in item or "\r" in item) for item in value):
        raise PolicyError(f"{label}: expected nonempty single-line strings")
    if len(value) != len(set(value)):
        raise PolicyError(f"{label}: duplicate values")
    return value


def _version(value: object, label: str) -> None:
    if type(value) is not int or value != 1:
        raise PolicyError(f"{label}: schema_version must be the integer 1")


def _scope(value: object, type_names: list[str], label: str, *, partial: bool) -> dict:
    fields = {"allowed", "required", "required_for_types"}
    scope = _keys(value, fields, set() if partial else fields, label)
    if "allowed" in scope and scope["allowed"] is not None:
        names = _strings(scope["allowed"], f"{label}.allowed")
        if any(not re.fullmatch(r"[^()\s:!]+", name) for name in names):
            raise PolicyError(f"{label}.allowed: names cannot contain whitespace, parentheses, : or !")
    if "required" in scope and type(scope["required"]) is not bool:
        raise PolicyError(f"{label}.required: expected a boolean")
    if "required_for_types" in scope:
        required = _strings(scope["required_for_types"], f"{label}.required_for_types")
        if set(required) - set(type_names):
            raise PolicyError(f"{label}.required_for_types: unknown type")
    return scope


def compile_pattern(pattern: str, type_names: list[str]) -> re.Pattern:
    """Expand only the type placeholder; retain regex quantifiers verbatim."""
    return re.compile(pattern.replace("{types}", "(?:" + "|".join(map(re.escape, type_names)) + ")"))


def load_policy(shared_path: Path, local_path: Path | None = None) -> dict:
    """Return validated effective settings without modifying either input file.

    Local lists replace defaults. Local scope fields override individually.
    Only scope, permanent branches and human guidance are locally configurable.
    An explicitly supplied missing local file is an error, never a fallback.
    """
    fields = {"schema_version", "types", "subject_pattern", "branch_pattern", "issue_reference",
              "summary_forbidden_endings", "defaults"}
    shared = _keys(_read(shared_path), fields, fields, "shared")
    _version(shared["schema_version"], "shared")
    types = shared["types"]
    if not isinstance(types, list) or not types:
        raise PolicyError("shared.types: expected a nonempty array")
    type_names = []
    for index, entry in enumerate(types):
        label = f"shared.types[{index}]"
        entry = _keys(entry, {"name", "description"}, {"name", "description"}, label)
        name = entry["name"]
        if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", name):
            raise PolicyError(f"{label}.name: expected a lowercase type name")
        _strings([entry["description"]], f"{label}.description")
        type_names.append(name)
    if len(type_names) != len(set(type_names)):
        raise PolicyError("shared.types: duplicate names")
    groups = {
        "subject_pattern": {"type", "scope", "breaking", "summary", "issue"},
        "branch_pattern": {"type", "issue", "no_issue", "description"},
    }
    for field, expected_groups in groups.items():
        pattern = shared[field]
        if not isinstance(pattern, str) or pattern.count("{types}") != 1:
            raise PolicyError(f"shared.{field}: expected one {{types}} placeholder")
        if not pattern.startswith("^") or not pattern.endswith("$"):
            raise PolicyError(f"shared.{field}: expected an anchored pattern")
        try:
            compiled = compile_pattern(pattern, type_names)
        except re.error as exc:
            raise PolicyError(f"shared.{field}: invalid regex: {exc}") from exc
        if set(compiled.groupindex) != expected_groups:
            raise PolicyError(f"shared.{field}: expected named groups {sorted(expected_groups)}")
    _strings(shared["summary_forbidden_endings"], "shared.summary_forbidden_endings")
    issue_reference = _keys(shared["issue_reference"], {"subject_suffix", "pr_body_line"},
                             {"subject_suffix", "pr_body_line"}, "shared.issue_reference")
    for field in ("subject_suffix", "pr_body_line"):
        value = issue_reference[field]
        if (not isinstance(value, str) or value.count("{issue}") != 1 or
                "\r" in value or "\n" in value):
            raise PolicyError(f"shared.issue_reference.{field}: expected one {{issue}} placeholder on one line")
    sample_suffix = issue_reference["subject_suffix"].replace("{issue}", "123")
    first_type = type_names[0]
    defaults = _keys(shared["defaults"], {"scope", "permanent_branches"},
                     {"scope", "permanent_branches"}, "shared.defaults")
    default_scope = _scope(defaults["scope"], type_names, "shared.defaults.scope", partial=False)
    sample_scope = ""
    scope_required = (default_scope["required"] or
                      first_type in default_scope["required_for_types"])
    if scope_required:
        allowed = default_scope["allowed"]
        if allowed == []:
            raise PolicyError("shared.defaults.scope: a required scope needs at least one allowed name")
        sample_scope = f"({allowed[0] if allowed else 'sample'})"
    sample_subject = f"{first_type}{sample_scope}: summary{sample_suffix}"
    subject_pattern = compile_pattern(shared["subject_pattern"], type_names)
    if not subject_pattern.fullmatch(sample_subject):
        raise PolicyError("shared.subject_pattern must accept the configured issue suffix")
    sample_body_line = issue_reference["pr_body_line"].replace("{issue}", "123")
    if re.search(r"\b(?:close[sd]?|fix(?:es|ed)?|resolve[sd]?)\b", sample_body_line, re.IGNORECASE):
        raise PolicyError("shared.issue_reference.pr_body_line must not close issues automatically")
    _strings(defaults["permanent_branches"], "shared.defaults.permanent_branches")
    local = {} if local_path is None else _read(local_path)
    if local_path is not None:
        _keys(local, {"schema_version", "scope", "permanent_branches", "guidance"},
              {"schema_version"}, "local")
        _version(local["schema_version"], "local")
    if "scope" in local:
        _scope(local["scope"], type_names, "local.scope", partial=True)
    for field in ("permanent_branches", "guidance"):
        if field in local:
            _strings(local[field], f"local.{field}")
    effective = copy.deepcopy(shared)
    effective.pop("defaults")
    effective["scope"] = copy.deepcopy(defaults["scope"])
    effective["scope"].update(local.get("scope", {}))
    effective["permanent_branches"] = copy.deepcopy(
        local.get("permanent_branches", defaults["permanent_branches"]))
    effective["guidance"] = copy.deepcopy(local.get("guidance", []))
    if effective["scope"]["allowed"] == [] and (
        effective["scope"]["required"] or effective["scope"]["required_for_types"]
    ):
        raise PolicyError("local.scope: a required scope needs at least one allowed name")
    return effective
