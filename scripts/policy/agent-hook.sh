#!/bin/sh

set -eu

project_root=${CLAUDE_PROJECT_DIR:?Claude Code did not provide CLAUDE_PROJECT_DIR}
if command -v python3 >/dev/null 2>&1 && \
        python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 10))' >/dev/null 2>&1; then
    python_command=python3
elif command -v python >/dev/null 2>&1 && \
        python -c 'import sys; raise SystemExit(sys.version_info < (3, 10))' >/dev/null 2>&1; then
    python_command=python
else
    echo "policy hook: Python 3.10 or newer is required on PATH" >&2
    exit 1
fi
exec "$python_command" -B "$project_root/scripts/policy/agent_hook.py"
