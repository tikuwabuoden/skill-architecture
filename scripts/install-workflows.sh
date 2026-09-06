#!/bin/sh

set -eu

case "$(uname -s)" in
    Darwin|Linux) ;;
    *)
        echo "This installer supports macOS and Linux. Use install-workflows.ps1 on Windows." >&2
        exit 1
        ;;
esac

usage() {
    cat <<'EOF'
Usage: ./scripts/install-workflows.sh [--destination PATH] [--uninstall]
EOF
}

script_dir=$(CDPATH= cd -P "$(dirname "$0")" && pwd -P)
repository_root=$(dirname "$script_dir")
workflow_root="$repository_root/skills/workflows"
destination=${HOME:?HOME is not set}/.agents/skills
uninstall=false

while [ "$#" -gt 0 ]; do
    case "$1" in
        --destination)
            if [ "$#" -lt 2 ]; then
                echo "--destination requires a path." >&2
                exit 2
            fi
            destination=$2
            shift 2
            ;;
        --uninstall)
            uninstall=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

workflow_count=0
for source in "$workflow_root"/*; do
    if [ -d "$source" ] && [ -f "$source/SKILL.md" ]; then
        workflow_count=$((workflow_count + 1))
    fi
done

if [ "$workflow_count" -eq 0 ]; then
    echo "No Workflow Skills found under $workflow_root" >&2
    exit 1
fi

# Check every destination before changing any link.
for source in "$workflow_root"/*; do
    if [ ! -d "$source" ] || [ ! -f "$source/SKILL.md" ]; then
        continue
    fi

    name=$(basename "$source")
    link=$destination/$name
    if [ ! -e "$link" ] && [ ! -L "$link" ]; then
        continue
    fi
    if [ ! -L "$link" ]; then
        echo "Cannot manage $name: $link already exists and is not a symbolic link." >&2
        exit 1
    fi

    existing_target=$(readlink "$link")
    case "$existing_target" in
        /*) ;;
        *) existing_target=$(dirname "$link")/$existing_target ;;
    esac
    if [ ! -d "$existing_target" ]; then
        echo "Cannot manage $name: $link points to missing target $existing_target." >&2
        exit 1
    fi

    existing_target=$(CDPATH= cd -P "$existing_target" && pwd -P)
    source=$(CDPATH= cd -P "$source" && pwd -P)
    if [ "$existing_target" != "$source" ]; then
        echo "Cannot manage $name: $link points to $existing_target." >&2
        exit 1
    fi
done

if [ "$uninstall" = true ]; then
    for source in "$workflow_root"/*; do
        if [ ! -d "$source" ] || [ ! -f "$source/SKILL.md" ]; then
            continue
        fi

        name=$(basename "$source")
        link=$destination/$name
        if [ ! -L "$link" ]; then
            echo "Not installed: $name"
            continue
        fi

        rm "$link"
        echo "Uninstalled: $name"
    done
    exit 0
fi

mkdir -p "$destination"
for source in "$workflow_root"/*; do
    if [ ! -d "$source" ] || [ ! -f "$source/SKILL.md" ]; then
        continue
    fi

    name=$(basename "$source")
    link=$destination/$name
    if [ -L "$link" ]; then
        echo "Already installed: $name"
        continue
    fi

    source=$(CDPATH= cd -P "$source" && pwd -P)
    ln -s "$source" "$link"
    echo "Installed: $name -> $source"
done
