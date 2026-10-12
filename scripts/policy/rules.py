"""Shared naming validation and issue-reference completion."""

from __future__ import annotations

import re
from dataclasses import dataclass

from policy import PolicyError, compile_pattern


@dataclass(frozen=True)
class SubjectMatch:
    """Match groups after the issue suffix has been separated unambiguously."""

    base_match: re.Match
    issue: str | None

    def group(self, name: str):
        return self.issue if name == "issue" else self.base_match.group(name)

    def groupdict(self) -> dict:
        groups = self.base_match.groupdict()
        groups["issue"] = self.issue
        return groups


def _suffix_match(subject: str, template: str) -> re.Match | None:
    before, after = template.split("{issue}")
    candidate = re.compile(re.escape(before) + r"(?P<raw>[^()\r\n]*)" +
                           re.escape(after) + r"$").search(subject)
    if candidate is None:
        return None
    issue = candidate.group("raw")
    if not re.fullmatch(r"[1-9][0-9]*", issue):
        raise PolicyError("an issue suffix must contain a positive integer")
    return candidate


def validate_branch(name: str, policy: dict, *, allow_permanent: bool = True):
    """Return a branch match; return None for an explicitly exempt permanent branch."""
    if name in policy["permanent_branches"] and allow_permanent:
        return None
    match = compile_pattern(policy["branch_pattern"],
                            [entry["name"] for entry in policy["types"]]).fullmatch(name)
    if not match:
        raise PolicyError(f"invalid branch name {name!r}; see policy/NAMING.md")
    return match


def extract_branch_issue(name: str, policy: dict) -> str | None:
    """Read an issue from the configured branch format without rejecting other names."""
    if name in policy["permanent_branches"]:
        return None
    match = compile_pattern(policy["branch_pattern"],
                            [entry["name"] for entry in policy["types"]]).fullmatch(name)
    return match.group("issue") if match is not None else None


def validate_subject(subject: str, policy: dict) -> SubjectMatch:
    """Validate the syntax and configured scope rules for one subject line."""
    if "\n" in subject or "\r" in subject:
        raise PolicyError("subject must contain exactly one line")
    issue = None
    base_subject = subject
    issue_suffix = _suffix_match(subject, policy["issue_reference"]["subject_suffix"])
    if issue_suffix is not None:
        issue = issue_suffix.group("raw")
        base_subject = subject[:issue_suffix.start()]
    match = compile_pattern(policy["subject_pattern"],
                            [entry["name"] for entry in policy["types"]]).fullmatch(base_subject)
    if not match:
        raise PolicyError(f"invalid subject {subject!r}; see policy/NAMING.md")
    groups = match.groupdict()
    scope = groups["scope"]
    settings = policy["scope"]
    if scope is None and (settings["required"] or groups["type"] in settings["required_for_types"]):
        raise PolicyError(f"scope is required for type {groups['type']!r}")
    if scope is not None and settings["allowed"] is not None and scope not in settings["allowed"]:
        raise PolicyError(f"scope {scope!r} is not in the configured allowed list")
    summary = groups["summary"]
    if any(summary.endswith(suffix) for suffix in policy["summary_forbidden_endings"]):
        raise PolicyError("summary ends with a forbidden punctuation mark")
    return SubjectMatch(match, issue)


def complete_subject(subject: str, issue_number: str | None, policy: dict) -> str:
    """Add the branch issue to a subject, preserving a matching existing suffix."""
    match = validate_subject(subject, policy)
    existing = match.group("issue")
    if issue_number is not None:
        if not re.fullmatch(r"[1-9][0-9]*", issue_number):
            raise PolicyError("issue number must be a positive integer")
        if existing is not None and existing != issue_number:
            raise PolicyError(f"subject references #{existing} but the branch references #{issue_number}")
        if existing is None:
            subject = subject + policy["issue_reference"]["subject_suffix"].replace("{issue}", issue_number)
            validate_subject(subject, policy)
    return subject


def complete_pr_body(body: str, issue_number: str | None, policy: dict) -> str:
    """Append one non-closing issue reference, without editing existing body text."""
    if issue_number is None:
        return body
    if not re.fullmatch(r"[1-9][0-9]*", issue_number):
        raise PolicyError("issue number must be a positive integer")
    reference = policy["issue_reference"]["pr_body_line"].replace("{issue}", issue_number)
    if re.search(re.escape(reference) + r"(?![0-9])", body):
        return body
    if not body:
        return reference
    separator = "" if body.endswith("\n\n") else "\n" if body.endswith("\n") else "\n\n"
    return f"{body}{separator}{reference}"


def complete_commit_message(message: str, issue_number: str | None, policy: dict) -> str:
    """Complete only the commit subject; preserve body, comments, and line endings."""
    match = re.match(r"([^\r\n]*)(\r\n|\n|\r|$)", message)
    assert match is not None
    subject, newline = match.groups()
    completed = complete_subject(subject, issue_number, policy)
    return completed + newline + message[match.end():]
