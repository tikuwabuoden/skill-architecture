#!/bin/sh

set -eu

script_dir=$(CDPATH= cd -P "$(dirname "$0")" && pwd -P)
repository_root=$(dirname "$script_dir")
installer=$repository_root/scripts/policy/install.py

if command -v python3 >/dev/null 2>&1 && \
        python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 10))' >/dev/null 2>&1; then
    exec python3 -B "$installer" "$@"
elif command -v python >/dev/null 2>&1 && \
        python -c 'import sys; raise SystemExit(sys.version_info < (3, 10))' >/dev/null 2>&1; then
    exec python -B "$installer" "$@"
fi

echo "Policy installer requires Python 3.10 or newer on PATH." >&2
exit 1
