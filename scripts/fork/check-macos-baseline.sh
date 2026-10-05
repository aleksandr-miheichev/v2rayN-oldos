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
    echo "usage: $0 <directory> [max-min-macos] [helper-prefix]" >&2
    exit 2
}

ROOT="${1:-}"
[[ -n "$ROOT" && -d "$ROOT" ]] || usage
MAX="${2:-13.6}"
# Binaries under this relative prefix are helper processes (bundled cores),
# not code loaded into our process. Their declared floor is reported but not
# fatal: Go binaries routinely declare a far newer minimum than they need,
# and whether they actually start is proven by executing them, which the
# workflow does in a separate step.
HELPERS="${3:-}"

command -v otool >/dev/null 2>&1 || {
    echo "otool is required (install the Xcode command line tools)" >&2
    exit 2
}

# Sorts two dotted versions and returns the greater one.
max_version() { printf '%s\n%s\n' "$1" "$2" | sort -V | tail -n1; }

scanned=0
measured=0
worst="0.0"
worst_file=""
offenders=()
helper_offenders=()
silent=()

while IFS= read -r -d '' f; do
    file -b -- "$f" | grep -q 'Mach-O' || continue
    scanned=$((scanned + 1))

    # Universal binaries report one load command block per architecture, so
    # every value is collected and the highest one wins.
    found_for_file=0
    while read -r declared; do
        [[ -n "$declared" ]] || continue
        found_for_file=1
        measured=$((measured + 1))
        if [[ "$(max_version "$worst" "$declared")" == "$declared" && "$declared" != "$worst" ]]; then
            worst="$declared"
            worst_file="$f"
        fi
        if [[ "$(max_version "$MAX" "$declared")" == "$declared" && "$declared" != "$MAX" ]]; then
            rel="${f#"$ROOT"/}"
            if [[ -n "$HELPERS" && "$rel" == "$HELPERS"* ]]; then
                helper_offenders+=("macOS ${declared}  ${rel}")
            else
                offenders+=("macOS ${declared}  ${rel}")
            fi
        fi
    # No "--" here: BSD otool does not understand it as an end-of-options
    # marker and fails, which silently emptied this whole check once.
    done < <(otool -l "$f" 2>/dev/null | awk '
        $1 == "cmd" && ($2 == "LC_BUILD_VERSION" || $2 == "LC_VERSION_MIN_MACOSX") { want = 1; next }
        want && ($1 == "minos" || $1 == "version") { print $2; want = 0 }
    ')

    ((found_for_file)) || silent+=("${f#"$ROOT"/}")
done < <(find "$ROOT" -type f -print0)

echo "Scanned ${scanned} Mach-O files under ${ROOT}, read ${measured} deployment targets"
echo "Oldest macOS this fork promises: ${MAX}"
echo "Highest minimum found:           ${worst}${worst_file:+  (${worst_file#"$ROOT"/})}"

status=0

# A check that measures nothing passes everything. That is worse than having no
# check at all, and it is exactly what happened when otool was invoked with an
# argument it did not understand.
if ((scanned > 0 && measured == 0)); then
    echo
    echo "FAIL: not a single deployment target could be read, so nothing was actually verified."
    echo "Check that otool works here; do not treat this as a pass."
    status=1
fi

if ((${#silent[@]})); then
    echo
    echo "Note: ${#silent[@]} binaries declare no deployment target (normal for some object kinds):"
    printf '  %s\n' "${silent[@]:0:5}"
fi
if ((${#helper_offenders[@]})); then
    echo
    echo "WARNING: helper processes declaring a newer floor than macOS ${MAX}:"
    printf '  %s\n' "${helper_offenders[@]}"
    echo "Not fatal by itself; the workflow proves whether they start by running them."
fi
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
