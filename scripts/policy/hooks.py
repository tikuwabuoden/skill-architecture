"""Entrypoints called by Git and optional agent hooks."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

from policy import PolicyError, load_policy
from rules import complete_commit_message, validate_branch


def repository_root(cwd: Path | None = None) -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], cwd=cwd,
        text=True, encoding="utf-8", capture_output=True, check=False,
    )
    if result.returncode:
        raise PolicyError("not inside a Git repository")
    return Path(result.stdout.strip()).resolve()


def load_repository_policy(root: Path) -> dict:
    shared = root / "policy" / "shared.json"
    local = root / "policy" / "local.json"
    return load_policy(shared, local if local.is_file() else None)


def branch_issue(root: Path, policy: dict, *, allow_permanent: bool = True) -> str | None:
    result = subprocess.run(
        ["git", "symbolic-ref", "--quiet", "--short", "HEAD"], cwd=root,
        text=True, encoding="utf-8", capture_output=True, check=False,
    )
    if result.returncode:
        raise PolicyError("cannot read the current branch (detached HEAD)")
    match = validate_branch(result.stdout.strip(), policy, allow_permanent=allow_permanent)
    return match.group("issue") if match is not None else None


def process_commit_message(message_path: Path, root: Path) -> str:
    policy = load_repository_policy(root)
    issue = branch_issue(root, policy)
    try:
        original = message_path.read_bytes()
        message = original.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise PolicyError(f"cannot read commit message {message_path}: {exc}") from exc
    updated = complete_commit_message(message, issue, policy)
    if updated.encode("utf-8") != original:
        try:
            message_path.write_bytes(updated.encode("utf-8"))
        except OSError as exc:
            raise PolicyError(f"cannot update commit message {message_path}: {exc}") from exc
    return updated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    commit = subparsers.add_parser("commit-msg")
    commit.add_argument("message_file", type=Path)
    branch = subparsers.add_parser("check-branch")
    branch.add_argument("branch_name")
    branch.add_argument("--source", action="store_true", help="disallow permanent-branch exceptions")
    args = parser.parse_args(argv)
    try:
        root = repository_root()
        policy = load_repository_policy(root)
        if args.command == "commit-msg":
            process_commit_message(args.message_file, root)
        else:
            validate_branch(args.branch_name, policy, allow_permanent=not args.source)
    except (PolicyError, OSError) as exc:
        print(f"policy hook: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
