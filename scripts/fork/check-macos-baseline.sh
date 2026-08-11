#!/usr/bin/env bash
# macOS counterpart of check-abi-baseline.sh.
#
# A Mach-O binary carries the oldest macOS it is willing to run on in its
# LC_BUILD_VERSION (or the older LC_VERSION_MIN_MACOSX) load command. If any
# shipped binary declares a newer minimum than this fork promises, the
# application refuses to launch on the systems it exists for -- which is
# exactly what happened upstream when the native SQLite library was built on a
# newer toolchain without an explicit deployment target.
#
# This is a metadata check, so it is meaningful even on a machine newer than
# the promised floor. The companion runtime check lives in verify-macos.yml.
set -euo pipefail

usage() {
    echo "usage: $0 <directory> [max-min-macos]" >&2
    exit 2
}

ROOT="${1:-}"
[[ -n "$ROOT" && -d "$ROOT" ]] || usage
MAX="${2:-14.0}"

command -v otool >/dev/null 2>&1 || {
    echo "otool is required (install the Xcode command line tools)" >&2
    exit 2
}

# Sorts two dotted versions and returns the greater one.
max_version() { printf '%s\n%s\n' "$1" "$2" | sort -V | tail -n1; }

scanned=0
worst="0.0"
worst_file=""
offenders=()

while IFS= read -r -d '' f; do
    file -b -- "$f" | grep -q 'Mach-O' || continue
    scanned=$((scanned + 1))

    # Universal binaries report one load command block per architecture, so
    # every value is collected and the highest one wins.
    while read -r declared; do
        [[ -n "$declared" ]] || continue
        if [[ "$(max_version "$worst" "$declared")" == "$declared" && "$declared" != "$worst" ]]; then
            worst="$declared"
            worst_file="$f"
        fi
        if [[ "$(max_version "$MAX" "$declared")" == "$declared" && "$declared" != "$MAX" ]]; then
            offenders+=("macOS ${declared}  ${f#"$ROOT"/}")
        fi
    done < <(otool -l -- "$f" 2>/dev/null | awk '
        $1 == "cmd" && ($2 == "LC_BUILD_VERSION" || $2 == "LC_VERSION_MIN_MACOSX") { want = 1; next }
        want && ($1 == "minos" || $1 == "version") { print $2; want = 0 }
    ')
done < <(find "$ROOT" -type f -print0)

echo "Scanned ${scanned} Mach-O files under ${ROOT}"
echo "Oldest macOS this fork promises: ${MAX}"
echo "Highest minimum found:           ${worst}${worst_file:+  (${worst_file#"$ROOT"/})}"

status=0
if ((${#offenders[@]})); then
    status=1
    echo
    echo "FAIL: binaries that refuse to run on macOS ${MAX}:"
    printf '  %s\n' "${offenders[@]}"
    echo
    echo "Do not raise the promised floor to make this pass: find the dependency"
    echo "that was built without a deployment target and pin or replace it."
fi

((scanned > 0)) || {
    echo "FAIL: no Mach-O files found, the bundle path is probably wrong" >&2
    status=1
}

exit "$status"
