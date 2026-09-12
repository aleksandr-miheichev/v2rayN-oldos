#!/usr/bin/env bash
# Apply this fork's patches to submodule sources during the build.
#
# Some fixes belong in a repository this fork does not own. The GlobalHotKeys
# submodule is pinned to a commit whose P/Invoke declares a non-nullable
# parameter that the caller legitimately passes null to, which makes every
# consumer build emit CS8625. The fix has been proposed upstream; until it is
# merged, carrying it as a patch keeps the change reviewable in one file and
# avoids forking another repository over one character.
#
# Layout: scripts/fork/patches/<path/to/target>/*.patch, where the directory
# mirrors the path of the tree the patch applies to.
#
# A patch that is already present is skipped rather than treated as an error,
# so the build keeps working the moment upstream merges the fix and the
# submodule pointer moves. A patch that neither applies nor is already present
# is fatal: the code underneath moved and the patch has to be revisited rather
# than silently doing nothing.
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
PATCH_ROOT="${REPO_ROOT}/scripts/fork/patches"

if [[ ! -d "$PATCH_ROOT" ]]; then
    echo "No patch directory, nothing to do."
    exit 0
fi

applied=0
present=0

while IFS= read -r -d '' patch; do
    relative="${patch#"$PATCH_ROOT"/}"
    target_dir="${REPO_ROOT}/$(dirname -- "$relative")"
    name="$(basename -- "$patch")"

    if [[ ! -d "$target_dir" ]]; then
        echo "::error::patch ${name} targets ${target_dir}, which does not exist"
        echo "The submodule is probably not checked out; use submodules: recursive."
        exit 1
    fi

    if git -C "$target_dir" apply --check -- "$patch" 2>/dev/null; then
        git -C "$target_dir" apply -- "$patch"
        echo "applied       $(dirname -- "$relative") <- ${name}"
        applied=$((applied + 1))
    elif git -C "$target_dir" apply --reverse --check -- "$patch" 2>/dev/null; then
        echo "already there $(dirname -- "$relative") <- ${name}"
        present=$((present + 1))
    else
        echo "::error::${name} neither applies to $(dirname -- "$relative") nor is already present"
        echo "The code underneath changed. Regenerate the patch, or delete it if the"
        echo "fix reached upstream in a different shape."
        exit 1
    fi
done < <(find "$PATCH_ROOT" -type f -name '*.patch' -print0)

echo "Patches applied: ${applied}; already present upstream: ${present}"
