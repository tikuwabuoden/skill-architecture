"""Read-only command line validation used by CI and local smoke checks."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys

from hooks import load_repository_policy, repository_root
from policy import PolicyError
from rules import complete_pr_body, complete_subject, validate_branch, validate_subject


def validate_pull_request(title: str, body: str, branch_name: str, policy: dict) -> None:
    """Validate PR fields against policy and its source branch; never mutate them."""
    branch = validate_branch(branch_name, policy)
    match = validate_subject(title, policy)
    branch_issue = branch.group("issue") if branch is not None else None
    title_issue = match.group("issue")
    if branch_issue is not None and title_issue != branch_issue:
        if title_issue is None:
            raise PolicyError(f"PR title must end in (#{branch_issue}) for source branch {branch_name!r}")
        raise PolicyError(f"PR title references #{title_issue} but source branch references #{branch_issue}")
    if branch_issue is not None and complete_pr_body(body, branch_issue, policy) != body:
        reference = policy["issue_reference"]["pr_body_line"].replace("{issue}", branch_issue)
        raise PolicyError(f"PR body must include a line containing {reference!r}")


def validate_commit_range(root: Path, base_sha: str, head_sha: str, policy: dict) -> int:
    """Validate subjects for every commit reachable from head but not base."""
    for label, value in (("base", base_sha), ("head", head_sha)):
        if not re.fullmatch(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})", value):
            raise PolicyError(f"{label} must be a full Git commit SHA")
        check = subprocess.run(["git", "cat-file", "-e", f"{value}^{{commit}}"], cwd=root,
                               capture_output=True, check=False)
        if check.returncode:
            raise PolicyError(f"{label} commit is unavailable after checkout: {value}")
    result = subprocess.run(["git", "log", "--format=%s%x00", f"{base_sha}..{head_sha}"],
                            cwd=root, text=True, encoding="utf-8", capture_output=True, check=False)
    if result.returncode:
        raise PolicyError(f"cannot read commits in {base_sha}..{head_sha}: {result.stderr.strip()}")
    subjects = [record.lstrip("\r\n") for record in result.stdout.split("\x00") if record.strip()]
    for index, subject in enumerate(subjects, start=1):
        try:
            validate_subject(subject, policy)
        except PolicyError as exc:
            raise PolicyError(f"commit {index} has an invalid subject: {exc}") from exc
    return len(subjects)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subject = subparsers.add_parser("subject")
    subject.add_argument("value")
    subject.add_argument("--issue")
    branch = subparsers.add_parser("branch")
    branch.add_argument("value")
    branch.add_argument("--source", action="store_true")
    pull_request = subparsers.add_parser("pull-request")
    pull_request.add_argument("--title-env", default="POLICY_PR_TITLE")
    pull_request.add_argument("--body-env", default="POLICY_PR_BODY")
    pull_request.add_argument("--branch-env", default="POLICY_PR_BRANCH")
    pull_request.add_argument("--base-env", default="POLICY_BASE_SHA")
    pull_request.add_argument("--head-env", default="POLICY_HEAD_SHA")
    args = parser.parse_args(argv)
    try:
        root = repository_root()
        policy = load_repository_policy(root)
        if args.command == "subject":
            validate_subject(args.value, policy)
            if args.issue is not None:
                if complete_subject(args.value, args.issue, policy) != args.value:
                    raise PolicyError(f"subject must reference #{args.issue}")
        elif args.command == "branch":
            validate_branch(args.value, policy, allow_permanent=not args.source)
        else:
            title = os.environ.get(args.title_env, "")
            body = os.environ.get(args.body_env, "")
            branch_name = os.environ.get(args.branch_env, "")
            validate_pull_request(title, body, branch_name, policy)
            count = validate_commit_range(root, os.environ.get(args.base_env, ""),
                                          os.environ.get(args.head_env, ""), policy)
            print(f"Validated PR metadata and {count} commit(s).")
    except (PolicyError, OSError) as exc:
        print(f"policy: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
