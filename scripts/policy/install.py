"""Install, update, or remove the shared naming policy in a Git repository."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile

from generate_docs import render_document
from hooks import repository_root
from policy import PolicyError, load_policy


MANIFEST_NAME = "skill-architecture-policy.json"
START = "<!-- skill-architecture naming policy: start -->"
END = "<!-- skill-architecture naming policy: end -->"
REFERENCE = "詳しいコミット・PR・ブランチの命名規約は[policy/NAMING.md](policy/NAMING.md)を参照する。"
CLAUDE_HOOK_COMMAND = 'sh "${CLAUDE_PROJECT_DIR}/scripts/policy/agent-hook.sh"'
CODEX_HOOK_COMMAND = 'python3 -B "$(git rev-parse --show-toplevel)/scripts/policy/agent_hook.py" --codex'
CODEX_HOOK_COMMAND_WINDOWS = (
    'powershell.exe -NoProfile -Command "if (Get-Command python -ErrorAction SilentlyContinue) '
    '{ python -B (Join-Path (git rev-parse --show-toplevel) \'scripts/policy/agent_hook.py\') --codex } '
    'else { py -3 -B (Join-Path (git rev-parse --show-toplevel) \'scripts/policy/agent_hook.py\') --codex }"'
)
MANAGED_FILES = (
    "policy/shared.json", "policy/local.example.json", "policy/README.md",
    "scripts/policy/policy.py", "scripts/policy/rules.py", "scripts/policy/generate_docs.py",
    "scripts/policy/hooks.py", "scripts/policy/agent_hook.py", "scripts/policy/agent-hook.sh",
    "scripts/policy/validate.py",
    ".github/workflows/policy-check.yml",
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PolicyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=_json_object)
    except (OSError, UnicodeError, ValueError) as exc:
        raise PolicyError(f"{path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PolicyError(f"{path}: expected a JSON object")
    return value


def _git_path(root: Path, option: str) -> Path:
    result = subprocess.run(["git", "rev-parse", option], cwd=root,
                            text=True, encoding="utf-8", capture_output=True, check=False)
    if result.returncode:
        raise PolicyError(f"cannot resolve Git path {option}: {result.stderr.strip()}")
    path = Path(result.stdout.strip())
    return (root / path).resolve() if not path.is_absolute() else path.resolve()


def _active_hooks_dir(root: Path) -> Path:
    configured = subprocess.run(["git", "config", "--path", "--get", "core.hooksPath"], cwd=root,
                                text=True, encoding="utf-8", capture_output=True, check=False)
    if configured.returncode == 0:
        path = Path(configured.stdout.strip())
        return (root / path).resolve() if not path.is_absolute() else path.resolve()
    return _git_path(root, "--git-path hooks")


def _assert_managed_path(path: Path, roots: tuple[Path, ...]) -> None:
    if path.is_symlink():
        raise PolicyError(f"refusing to manage a symbolic link: {path}")
    resolved_parent = path.parent.resolve()
    if not any(resolved_parent == root or root in resolved_parent.parents for root in roots):
        raise PolicyError(f"managed path escapes the repository: {path}")


def _atomic_write(path: Path, data: bytes, mode: int | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(data)
    try:
        if mode is not None:
            temporary.chmod(mode)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _apply_changes(changes: list[tuple[Path, bytes | None, int | None]], roots: tuple[Path, ...]) -> None:
    """Apply a preflighted file plan and restore prior bytes if any write fails."""
    previous = []
    try:
        for path, content, mode in changes:
            _assert_managed_path(path, roots)
            if path.exists() and not path.is_file():
                raise PolicyError(f"refusing to replace a non-file: {path}")
            old = path.read_bytes() if path.exists() else None
            old_mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else None
            previous.append((path, old, old_mode))
            if content is None:
                if path.exists():
                    path.unlink()
            else:
                _atomic_write(path, content, mode)
    except Exception:
        for path, old, old_mode in reversed(previous):
            try:
                if old is None:
                    path.unlink(missing_ok=True)
                else:
                    _atomic_write(path, old, old_mode)
            except OSError:
                pass
        raise


def _block(newline: str) -> str:
    return newline.join((START, REFERENCE, END))


def _block_sha(block: str) -> str:
    return _sha(block.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8"))


def _agent_content(original: bytes | None, record: dict | None) -> tuple[bytes, dict]:
    created = original is None
    bom = b"\xef\xbb\xbf" if original is not None and original.startswith(b"\xef\xbb\xbf") else b""
    text = "" if original is None else original.decode("utf-8-sig")
    newline = "\r\n" if "\r\n" in text else "\n"
    existing_start = text.find(START)
    existing_end = text.find(END)
    if record is not None:
        if existing_start < 0 or existing_end < existing_start:
            raise PolicyError("AGENTS.md policy reference was changed or removed; preserving the file")
        previous_block = text[existing_start:existing_end + len(END)]
        if _block_sha(previous_block) != record["block_sha256"]:
            raise PolicyError("AGENTS.md policy reference was edited; preserving the file")
        block = _block(newline)
        updated = text[:existing_start] + block + text[existing_end + len(END):]
        metadata = {"block_sha256": _block_sha(block), "created_file": record["created_file"]}
        if record.get("preexisting"):
            metadata["preexisting"] = True
        return bom + updated.encode("utf-8"), metadata
    if existing_start >= 0 or existing_end >= 0:
        if existing_start >= 0 and existing_start < existing_end and text[existing_start:existing_end + len(END)] == _block(newline):
            block = _block(newline)
            return bom + text.encode("utf-8"), {"block_sha256": _block_sha(block), "created_file": False, "preexisting": True}
        raise PolicyError("AGENTS.md has an incomplete or unrelated policy marker")
    prefix = "" if not text else newline if text.endswith(newline) else newline * 2
    block = _block(newline)
    updated = text + prefix + block + newline
    return bom + updated.encode("utf-8"), {
        "block_sha256": _block_sha(block), "created_file": created,
        "prefix": prefix, "suffix": newline,
    }


def _agent_removal(original: bytes, record: dict) -> bytes:
    bom = b"\xef\xbb\xbf" if original.startswith(b"\xef\xbb\xbf") else b""
    text = original.decode("utf-8-sig")
    start = text.find(START)
    end = text.find(END, start + len(START)) if start >= 0 else -1
    if start < 0 or end < 0:
        raise PolicyError("AGENTS.md policy reference is missing; preserving all installed files")
    end += len(END)
    if _block_sha(text[start:end]) != record["block_sha256"]:
        raise PolicyError("AGENTS.md policy reference was edited; preserving all installed files")
    prefix = record.get("prefix", "")
    suffix = record.get("suffix", "")
    remove_start = start - len(prefix)
    if remove_start >= 0 and text[remove_start:start] == prefix and text[end:end + len(suffix)] == suffix:
        return bom + (text[:remove_start] + text[end + len(suffix):]).encode("utf-8")
    return bom + (text[:start] + text[end:]).encode("utf-8")


def _settings_bytes(original: bytes | None, entry: dict, operation: str,
                    *, installed: bool = False,
                    created_file: bool | None = None) -> tuple[bytes | None, bool, bool]:
    created = original is None if created_file is None else created_file
    settings = {} if original is None else _read_json_bytes(original, "Claude settings")
    hooks = settings.get("hooks", {})
    if not isinstance(hooks, dict):
        raise PolicyError("Claude settings hooks must be an object")
    pre_tool = hooks.get("PreToolUse", [])
    if not isinstance(pre_tool, list):
        raise PolicyError("Claude settings hooks.PreToolUse must be an array")
    for index, group in enumerate(pre_tool):
        if (not isinstance(group, dict) or not isinstance(group.get("hooks", []), list) or
                any(not isinstance(hook, dict) for hook in group.get("hooks", []))):
            raise PolicyError(f"Claude settings hooks.PreToolUse[{index}] is malformed; preserving settings")
    if operation == "install":
        exact = [group for group in pre_tool if isinstance(group, dict) and
                 any(isinstance(hook, dict) and hook.get("command") == CLAUDE_HOOK_COMMAND
                     for hook in group.get("hooks", []))]
        if exact:
            if entry in exact:
                return original, False, created
            raise PolicyError("Claude settings already contain a different policy hook; preserving settings")
        pre_tool.append(entry)
        hooks["PreToolUse"] = pre_tool
        settings["hooks"] = hooks
        return _dump_settings(settings, original), True, created
    if not installed:
        return original, False, created
    found = False
    filtered = []
    for group in pre_tool:
        if group == entry:
            found = True
            continue
        filtered.append(group)
    if not found:
        raise PolicyError("managed Claude hook was edited or removed; preserving installed files")
    hooks["PreToolUse"] = filtered
    if not filtered:
        hooks.pop("PreToolUse", None)
    if not hooks:
        settings.pop("hooks", None)
    else:
        settings["hooks"] = hooks
    if not settings and created:
        return None, True, created
    return _dump_settings(settings, original), True, created


def _dump_settings(settings: dict, original: bytes | None) -> bytes:
    bom = b"\xef\xbb\xbf" if original is not None and original.startswith(b"\xef\xbb\xbf") else b""
    return bom + (json.dumps(settings, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _read_json_bytes(content: bytes, label: str) -> dict:
    try:
        value = json.loads(content.decode("utf-8-sig"), object_pairs_hook=_json_object)
    except (UnicodeError, ValueError) as exc:
        raise PolicyError(f"{label}: {exc}") from exc
    if not isinstance(value, dict):
        raise PolicyError(f"{label}: expected an object")
    return value


def _agent_entry() -> dict:
    return {"matcher": "Bash", "hooks": [{
        "type": "command", "command": CLAUDE_HOOK_COMMAND,
        "timeout": 10, "onFailure": "block",
    }]}


def _codex_agent_entry() -> dict:
    return {"matcher": "^Bash$", "hooks": [{
        "type": "command", "command": CODEX_HOOK_COMMAND,
        "commandWindows": CODEX_HOOK_COMMAND_WINDOWS,
        "timeout": 10, "statusMessage": "Checking naming policy",
    }]}


def _codex_hooks_bytes(original: bytes | None, entry: dict, operation: str,
                       *, installed: bool = False,
                       created_file: bool | None = None) -> tuple[bytes | None, bool, bool]:
    created = original is None if created_file is None else created_file
    settings = {} if original is None else _read_json_bytes(original, "Codex hooks")
    hooks = settings.get("hooks", {})
    if not isinstance(hooks, dict):
        raise PolicyError("Codex hooks hooks must be an object")
    pre_tool = hooks.get("PreToolUse", [])
    if not isinstance(pre_tool, list):
        raise PolicyError("Codex hooks hooks.PreToolUse must be an array")
    for index, group in enumerate(pre_tool):
        if (not isinstance(group, dict) or not isinstance(group.get("hooks", []), list) or
                any(not isinstance(hook, dict) for hook in group.get("hooks", []))):
            raise PolicyError(f"Codex hooks PreToolUse[{index}] is malformed; preserving settings")
    if operation == "install":
        exact = [group for group in pre_tool if isinstance(group, dict) and
                 any(isinstance(hook, dict) and
                     (hook.get("command") == CODEX_HOOK_COMMAND or
                      hook.get("commandWindows") == CODEX_HOOK_COMMAND_WINDOWS)
                     for hook in group.get("hooks", []))]
        if exact:
            if entry in exact:
                return original, False, created
            raise PolicyError("Codex hooks already contain a different policy hook; preserving settings")
        pre_tool.append(entry)
        hooks["PreToolUse"] = pre_tool
        settings["hooks"] = hooks
        return _dump_settings(settings, original), True, created
    if not installed:
        return original, False, created
    found = False
    filtered = []
    for group in pre_tool:
        if group == entry:
            found = True
            continue
        filtered.append(group)
    if not found:
        raise PolicyError("managed Codex hook was edited or removed; preserving installed files")
    hooks["PreToolUse"] = filtered
    if not filtered:
        hooks.pop("PreToolUse", None)
    if not hooks:
        settings.pop("hooks", None)
    else:
        settings["hooks"] = hooks
    if not settings and created:
        return None, True, created
    return _dump_settings(settings, original), True, created


def _load_manifest(path: Path) -> dict | None:
    if not path.exists():
        return None
    manifest = _read_json(path)
    if manifest.get("format_version") != 1 or not isinstance(manifest.get("files"), dict):
        raise PolicyError(f"unrecognized install manifest: {path}")
    return manifest


def _install(root: Path, source: Path, *, claude: bool, codex: bool = False) -> None:
    git_dir = _git_path(root, "--git-dir")
    manifest_path = git_dir / MANIFEST_NAME
    _assert_managed_path(manifest_path, (root, git_dir))
    previous = _load_manifest(manifest_path)
    old_files = {} if previous is None else previous["files"]
    root_source = source.resolve()

    local_path = root / "policy" / "local.json"
    local_example = root_source / "policy" / "local.example.json"
    if local_path.exists():
        local_config = local_path
    else:
        local_config = local_example
    # Validate every input and generate the derived document before any write.
    naming = render_document(load_policy(root_source / "policy" / "shared.json", local_config)).encode("utf-8")
    source_files = {relative: (root_source / relative).read_bytes() for relative in MANAGED_FILES}
    source_files["policy/NAMING.md"] = naming
    plans: dict[Path, tuple[bytes | None, int | None]] = {}
    new_files = {}
    roots = (root, git_dir)
    for relative, content in source_files.items():
        target = root / Path(relative)
        _assert_managed_path(target, roots)
        old_record = old_files.get(relative)
        if target.exists():
            if not target.is_file():
                raise PolicyError(f"cannot install over a non-file: {target}")
            existing = target.read_bytes()
            digest = _sha(existing)
            if old_record is None and digest != _sha(content):
                raise PolicyError(f"cannot install: {target} already exists and is not managed; preserving it")
            if old_record is not None and digest not in {old_record["sha256"], _sha(content)}:
                raise PolicyError(f"managed file was edited: {target}; preserving it")
        plans[target] = (content, 0o644)
        new_files[relative] = {"sha256": _sha(content), "mode": 0o644}

    seeded = {} if previous is None else dict(previous.get("seeded_files", {}))
    if not local_path.exists():
        content = local_example.read_bytes()
        plans[local_path] = (content, 0o644)
        seeded["policy/local.json"] = {"sha256": _sha(content)}
    elif "policy/local.json" in seeded:
        old_hash = seeded["policy/local.json"]["sha256"]
        current_hash = _sha(local_path.read_bytes())
        if current_hash == old_hash:
            content = local_example.read_bytes()
            plans[local_path] = (content, 0o644)
            seeded["policy/local.json"] = {"sha256": _sha(content)}
        else:
            seeded.pop("policy/local.json")

    agents_path = root / "AGENTS.md"
    agents_original = agents_path.read_bytes() if agents_path.exists() else None
    agents_record = None if previous is None else previous.get("agents_reference")
    agents_content, agents_new_record = _agent_content(agents_original, agents_record)
    if agents_record is None or agents_content != agents_original:
        plans[agents_path] = (agents_content, 0o644)

    hook_record = None if previous is None else previous.get("git_hook")
    hook_dir = _active_hooks_dir(root)
    hook_path = hook_dir / "commit-msg"
    _assert_managed_path(hook_path, roots)
    if hook_record is not None and Path(hook_record["path"]).resolve() != hook_path:
        raise PolicyError("Git hooks path changed since installation; preserving hooks")
    backup_path = Path(hook_record["backup"]) if hook_record else hook_dir / "commit-msg.policy-original"
    _assert_managed_path(backup_path, roots)
    hook_content = (root_source / "scripts/policy/commit-msg").read_bytes()
    had_original = bool(hook_record and hook_record["had_original"])
    old_mode = hook_record.get("original_mode") if hook_record else None
    if hook_record:
        if not hook_path.is_file() or _sha(hook_path.read_bytes()) not in {hook_record["wrapper_sha256"], _sha(hook_content)}:
            raise PolicyError(f"managed Git hook was edited: {hook_path}; preserving it")
        if had_original and not backup_path.is_file():
            raise PolicyError(f"preserved Git hook backup is missing: {backup_path}")
    elif hook_path.exists():
        if not hook_path.is_file() or hook_path.is_symlink():
            raise PolicyError(f"cannot safely wrap existing Git hook: {hook_path}")
        if backup_path.exists():
            raise PolicyError(f"Git hook backup path already exists: {backup_path}")
        had_original = True
        old_mode = stat.S_IMODE(hook_path.stat().st_mode)
        plans[backup_path] = (hook_path.read_bytes(), old_mode)
    plans[hook_path] = (hook_content, 0o755)
    new_hook_record = {"path": str(hook_path), "backup": str(backup_path),
                       "had_original": had_original, "original_mode": old_mode,
                       "wrapper_sha256": _sha(hook_content)}

    agent_record_new = None if previous is None else previous.get("claude_hook")
    codex_record_new = None if previous is None else previous.get("codex_hook")
    if claude:
        entry = _agent_entry()
        settings_path = root / ".claude" / "settings.json"
        _assert_managed_path(settings_path, roots)
        settings_original = settings_path.read_bytes() if settings_path.exists() else None
        installed = False if agent_record_new is None else agent_record_new["installed"]
        settings_content, did_install, created = _settings_bytes(
            settings_original, entry, "install", installed=installed)
        if settings_content != settings_original:
            plans[settings_path] = (settings_content, 0o644)
        agent_record_new = {"path": str(settings_path.relative_to(root)), "entry": entry,
                            "installed": did_install or installed,
                            "created_file": created or bool(agent_record_new and agent_record_new.get("created_file"))}
    if codex:
        entry = _codex_agent_entry()
        hooks_path = root / ".codex" / "hooks.json"
        _assert_managed_path(hooks_path, roots)
        hooks_original = hooks_path.read_bytes() if hooks_path.exists() else None
        installed = False if codex_record_new is None else codex_record_new["installed"]
        hooks_content, did_install, created = _codex_hooks_bytes(
            hooks_original, entry, "install", installed=installed)
        if hooks_content != hooks_original:
            plans[hooks_path] = (hooks_content, 0o644)
        codex_record_new = {"path": str(hooks_path.relative_to(root)), "entry": entry,
                            "installed": did_install or installed,
                            "created_file": created or bool(codex_record_new and codex_record_new.get("created_file"))}

    new_manifest = {
        "format_version": 1, "files": new_files, "seeded_files": seeded,
        "agents_reference": agents_new_record, "git_hook": new_hook_record,
        "claude_hook": agent_record_new, "codex_hook": codex_record_new,
    }
    manifest_content = (json.dumps(new_manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    plans[manifest_path] = (manifest_content, 0o600)
    _apply_changes([(path, content, mode) for path, (content, mode) in plans.items()], roots)
    print(f"Installed naming policy in {root}")
    print("Updated common policy and generated policy/NAMING.md")
    print("Preserved local policy configuration in policy/local.json")
    if claude:
        print("Installed optional Claude Code PreToolUse hook")
    if codex:
        print("Installed optional Codex PreToolUse hook")


def _uninstall(root: Path) -> None:
    git_dir = _git_path(root, "--git-dir")
    manifest_path = git_dir / MANIFEST_NAME
    _assert_managed_path(manifest_path, (root, git_dir))
    manifest = _load_manifest(manifest_path)
    if manifest is None:
        print("Naming policy is not installed")
        return
    roots = (root, git_dir)
    changes = []
    for relative, record in manifest["files"].items():
        target = root / Path(relative)
        _assert_managed_path(target, roots)
        if not target.exists() or not target.is_file() or _sha(target.read_bytes()) != record["sha256"]:
            raise PolicyError(f"managed file was edited or removed: {target}; preserving installed policy")
        changes.append((target, None, None))

    for relative, record in manifest.get("seeded_files", {}).items():
        target = root / Path(relative)
        _assert_managed_path(target, roots)
        if target.is_file() and _sha(target.read_bytes()) == record["sha256"]:
            changes.append((target, None, None))

    agents_path = root / "AGENTS.md"
    agent_record = manifest.get("agents_reference")
    if agent_record and agents_path.exists():
        _assert_managed_path(agents_path, roots)
        updated = (agents_path.read_bytes() if agent_record.get("preexisting") else
                   _agent_removal(agents_path.read_bytes(), agent_record))
        if updated:
            changes.append((agents_path, updated, stat.S_IMODE(agents_path.stat().st_mode)))
        elif agent_record.get("created_file"):
            changes.append((agents_path, None, None))

    hook = manifest.get("git_hook")
    if hook:
        hook_path = Path(hook["path"])
        backup_path = Path(hook["backup"])
        _assert_managed_path(hook_path, roots)
        _assert_managed_path(backup_path, roots)
        if not hook_path.is_file() or _sha(hook_path.read_bytes()) != hook["wrapper_sha256"]:
            raise PolicyError(f"managed Git hook was edited or removed: {hook_path}; preserving installed policy")
        if hook["had_original"]:
            if not backup_path.is_file():
                raise PolicyError(f"original Git hook backup is missing: {backup_path}; preserving installed policy")
            changes.append((hook_path, backup_path.read_bytes(), hook.get("original_mode")))
            changes.append((backup_path, None, None))
        else:
            changes.append((hook_path, None, None))

    agent = manifest.get("claude_hook")
    if agent:
        settings_path = root / Path(agent["path"])
        _assert_managed_path(settings_path, roots)
        if settings_path.exists():
            settings_content, _, _ = _settings_bytes(
                settings_path.read_bytes(), agent["entry"], "uninstall",
                installed=agent["installed"], created_file=agent.get("created_file", False))
            if settings_content != settings_path.read_bytes():
                if settings_content is None and agent.get("created_file"):
                    changes.append((settings_path, None, None))
                elif settings_content is not None:
                    changes.append((settings_path, settings_content, stat.S_IMODE(settings_path.stat().st_mode)))

    codex_agent = manifest.get("codex_hook")
    if codex_agent:
        hooks_path = root / Path(codex_agent["path"])
        _assert_managed_path(hooks_path, roots)
        if hooks_path.exists():
            hooks_content, _, _ = _codex_hooks_bytes(
                hooks_path.read_bytes(), codex_agent["entry"], "uninstall",
                installed=codex_agent["installed"],
                created_file=codex_agent.get("created_file", False))
            if hooks_content != hooks_path.read_bytes():
                if hooks_content is None and codex_agent.get("created_file"):
                    changes.append((hooks_path, None, None))
                elif hooks_content is not None:
                    changes.append((hooks_path, hooks_content, stat.S_IMODE(hooks_path.stat().st_mode)))

    changes.append((manifest_path, None, None))
    _apply_changes(changes, roots)
    print(f"Uninstalled naming policy from {root}")
    print("Removed only managed policy files and references; kept user-owned policy/local.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd(), help="target Git repository")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--agent-hook", choices=("claude", "codex"), action="append",
                        help="optionally install an agent PreToolUse hook; repeat to install both")
    args = parser.parse_args(argv)
    try:
        root = repository_root(args.project.resolve())
        source = Path(__file__).resolve().parents[2]
        if args.uninstall:
            if args.agent_hook:
                raise PolicyError("--agent-hook cannot be combined with --uninstall")
            _uninstall(root)
        else:
            selected_hooks = set(args.agent_hook or ())
            _install(root, source, claude="claude" in selected_hooks,
                     codex="codex" in selected_hooks)
    except (PolicyError, OSError, UnicodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
