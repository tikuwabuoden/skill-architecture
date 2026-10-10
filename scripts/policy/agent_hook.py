"""Claude Code PreToolUse adapter for the documented initial Bash command set."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

from hooks import load_repository_policy
from policy import PolicyError
from rules import complete_pr_body, complete_subject, validate_branch


class UnsupportedCommand(PolicyError):
    """A target operation whose inputs cannot be edited without guessing."""


def _tokens(command: str) -> list[str]:
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|<>")
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
    except ValueError as exc:
        raise UnsupportedCommand(f"cannot parse command quoting: {exc}") from exc
    return tokens


def _executable(token: str, name: str) -> bool:
    return Path(token.replace("\\", "/")).name.lower() in {name, name + ".exe"}


def _head_branch(value: str, cwd: Path) -> str:
    if value:
        if value.count(":") > 1:
            raise UnsupportedCommand("--head must be BRANCH or OWNER:BRANCH")
        branch = value.rsplit(":", 1)[-1]
        if not branch:
            raise UnsupportedCommand("--head must include a branch name")
        return branch
    result = subprocess.run(["git", "symbolic-ref", "--quiet", "--short", "HEAD"],
                            cwd=cwd, text=True, encoding="utf-8", capture_output=True)
    if result.returncode:
        raise UnsupportedCommand("cannot determine the PR source branch from a detached HEAD")
    return result.stdout.strip()


def _git_branch(tokens: list[str], policy: dict) -> bool:
    if len(tokens) < 2 or not _executable(tokens[0], "git"):
        return False
    operation = tokens[1]
    if operation == "switch":
        flags = {"-c", "--create"}
    elif operation == "checkout":
        flags = {"-b", "--branch"}
    else:
        return False
    if len(tokens) < 3 or tokens[2] not in flags:
        return False
    if len(tokens) not in (4, 5):
        raise UnsupportedCommand("supported forms are git switch -c NAME [START_POINT] and git checkout -b NAME [START_POINT]")
    validate_branch(tokens[3], policy)
    return True


def _pr_args(tokens: list[str]) -> dict[str, tuple[int, int | None, str]]:
    """Map option names to (option token, value token, current value)."""
    values = {}
    aliases = {
        "--title": "title", "-t": "title", "--body": "body", "-b": "body",
        "--body-file": "body-file", "-F": "body-file", "--head": "head", "-H": "head",
    }
    values_with_args = set(aliases) | {
        "--base", "-B", "--assignee", "-a", "--reviewer", "-r", "--label", "-l",
        "--milestone", "-m", "--project",
    }
    flags = {"--draft", "--no-maintainer-edit", "--web", "--dry-run", "--help"}
    i = 3
    while i < len(tokens):
        token = tokens[i]
        if token in flags:
            i += 1
            continue
        key, equals, inline_value = token.partition("=")
        if key not in values_with_args:
            raise UnsupportedCommand(f"unsupported gh pr create argument: {token}")
        if equals:
            if key not in aliases:
                raise UnsupportedCommand(f"inline form is unsupported for {key}")
            canonical = aliases[key]
            if canonical in values:
                raise UnsupportedCommand(f"{key} was specified more than once")
            values[canonical] = (i, None, inline_value)
            i += 1
            continue
        if i + 1 >= len(tokens):
            raise UnsupportedCommand(f"{key} requires a value")
        canonical = aliases.get(key)
        if canonical:
            if canonical in values:
                raise UnsupportedCommand(f"{key} was specified more than once")
            values[canonical] = (i, i + 1, tokens[i + 1])
        i += 2
    return values


def _replace(tokens: list[str], value: tuple[int, int | None, str], updated: str) -> None:
    option_index, value_index, previous = value
    if updated == previous:
        return
    if value_index is None:
        prefix = tokens[option_index].split("=", 1)[0] + "="
        tokens[option_index] = prefix + updated
    else:
        tokens[value_index] = updated


def _gh_pr(tokens: list[str], policy: dict, cwd: Path) -> tuple[bool, bool]:
    if len(tokens) < 3 or not (_executable(tokens[0], "gh") and tokens[1:3] == ["pr", "create"]):
        return False, False
    values = _pr_args(tokens)
    if "title" not in values:
        raise UnsupportedCommand("gh pr create needs an explicit --title/-t; --fill and prompts are unsupported")
    if ("body" in values) == ("body-file" in values):
        raise UnsupportedCommand("gh pr create needs exactly one explicit --body/-b or --body-file/-F")
    branch_name = _head_branch(values.get("head", (0, None, ""))[2], cwd)
    branch = validate_branch(branch_name, policy, allow_permanent=False)
    issue = branch.group("issue")
    title = complete_subject(values["title"][2], issue, policy)
    body_file = None
    if "body-file" in values:
        raw_path = values["body-file"][2]
        if raw_path in {"", "-"}:
            raise UnsupportedCommand("--body-file must point to a readable file; stdin is unsupported")
        body_file = Path(raw_path)
        if not body_file.is_absolute():
            body_file = cwd / body_file
        try:
            original_body = body_file.read_bytes().decode("utf-8")
        except (OSError, UnicodeError) as exc:
            raise UnsupportedCommand(f"cannot read --body-file {raw_path!r}: {exc}") from exc
        updated_body = complete_pr_body(original_body, issue, policy)
    else:
        original_body = values["body"][2]
        updated_body = complete_pr_body(original_body, issue, policy)
    if issue is not None:
        _replace(tokens, values["title"], title)
        if "body" in values:
            _replace(tokens, values["body"], updated_body)
        else:
            if updated_body != original_body:
                try:
                    body_file.write_bytes(updated_body.encode("utf-8"))
                except OSError as exc:
                    raise UnsupportedCommand(f"cannot update --body-file: {exc}") from exc
    return True, title != values["title"][2] or updated_body != original_body


def handle_input(payload: object) -> tuple[dict | None, str | None]:
    """Return a Claude PreToolUse response and a diagnostic, if one is needed."""
    if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
        return None, None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict) or not isinstance(tool_input.get("command"), str):
        return None, None
    command = tool_input["command"]
    try:
        try:
            tokens = _tokens(command)
        except UnsupportedCommand:
            targeted = re.match(r"\s*(?:git\s+(?:switch\s+(?:-c|--create)|checkout\s+(?:-b|--branch))|gh\s+pr\s+create)(?:\s|$)", command)
            if targeted:
                raise
            return None, None
        if not tokens:
            return None, None
        if not (_is_git_branch_target(tokens) or _is_pr_target(tokens)):
            return None, None
        if any(token in {";", "&", "&&", "|", "||", "<", "<<", ">", ">>", "<<<"}
               for token in tokens):
            raise UnsupportedCommand("compound commands and shell redirection are not supported")
        if any("$" in token or "`" in token for token in tokens):
            raise UnsupportedCommand("shell expansion is not supported")
        cwd = Path(payload.get("cwd") or os.getcwd()).resolve()
        from hooks import repository_root
        root = repository_root(cwd)
        policy = load_repository_policy(root)
        if _git_branch(tokens, policy):
            return None, None
        is_pr, changed = _gh_pr(tokens, policy, cwd)
        if is_pr and changed:
            updated = dict(tool_input)
            updated["command"] = shlex.join(tokens)
            return {"hookSpecificOutput": {
                "hookEventName": "PreToolUse", "updatedInput": updated,
            }}, None
        return None, None
    except (PolicyError, OSError, ValueError) as exc:
        return {"hookSpecificOutput": {
            "hookEventName": "PreToolUse", "permissionDecision": "deny",
            "permissionDecisionReason": str(exc),
        }}, str(exc)


def _is_git_branch_target(tokens: list[str]) -> bool:
    return (len(tokens) >= 3 and _executable(tokens[0], "git") and
            ((tokens[1] == "switch" and tokens[2] in {"-c", "--create"}) or
             (tokens[1] == "checkout" and tokens[2] in {"-b", "--branch"})))


def _is_pr_target(tokens: list[str]) -> bool:
    return len(tokens) >= 3 and _executable(tokens[0], "gh") and tokens[1:3] == ["pr", "create"]


def main() -> int:
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse", "permissionDecision": "deny",
            "permissionDecisionReason": f"invalid hook JSON: {exc}",
        }}))
        return 0
    response, diagnostic = handle_input(payload)
    if response is not None:
        print(json.dumps(response, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
