#!/usr/bin/env bash
# Guard against the exact regression this fork exists to prevent.
#
# Upstream builds became uninstallable on Ubuntu 22.04, Debian 12 and RHEL 9
# because a dependency update silently raised the native SQLite library's ABI
# baseline to GLIBC_2.38 and added the DT_RELR relative-relocation tag, which
# older dynamic loaders reject outright. Not a single source file changed, so
# nothing in the build caught it.
#
# This script inspects every ELF file in a staged package tree and fails when
# any of them requires a newer glibc than the baseline this fork promises.
set -euo pipefail

usage() {
    echo "usage: $0 <directory> [max-glibc]" >&2
    exit 2
}

ROOT="${1:-}"
[[ -n "$ROOT" && -d "$ROOT" ]] || usage
MAX="${2:-2.34}"

command -v readelf >/dev/null 2>&1 || {
    echo "readelf is required (install binutils)" >&2
    exit 2
}

# Returns the greater of two dotted versions.
max_version() { printf '%s\n%s\n' "$1" "$2" | sort -V | tail -n1; }

worst="0.0"
worst_file=""
scanned=0
offenders=()
relr_users=()

is_elf() {
    [[ "$(head -c 4 -- "$1" 2>/dev/null | od -An -tx1 | tr -d ' \n')" == "7f454c46" ]]
}

while IFS= read -r -d '' f; do
    is_elf "$f" || continue
    scanned=$((scanned + 1))

    info="$(readelf --version-info -- "$f" 2>/dev/null || true)"

    # GLIBC_ABI_DT_RELR is a blocker on its own: a loader older than glibc 2.36
    # aborts with "GLIBC_ABI_DT_RELR not found" no matter what the symbol
    # versions say.
    if grep -q 'GLIBC_ABI_DT_RELR' <<<"$info"; then
        relr_users+=("$f")
    fi

    needed="$(grep -o 'GLIBC_[0-9][0-9]*\.[0-9][0-9]*' <<<"$info" |
        sed 's/^GLIBC_//' | sort -V | tail -n1 || true)"
    [[ -n "$needed" ]] || continue

    if [[ "$(max_version "$worst" "$needed")" == "$needed" && "$needed" != "$worst" ]]; then
        worst="$needed"
        worst_file="$f"
    fi

    if [[ "$(max_version "$MAX" "$needed")" == "$needed" && "$needed" != "$MAX" ]]; then
        offenders+=("GLIBC_${needed}  ${f#"$ROOT"/}")
    fi
done < <(find "$ROOT" -type f -print0)

echo "Scanned ${scanned} ELF files under ${ROOT}"
echo "Baseline promised by this fork: GLIBC_${MAX}"
echo "Highest requirement found:      GLIBC_${worst}${worst_file:+  (${worst_file#"$ROOT"/})}"

status=0

if ((${#offenders[@]})); then
    status=1
    echo
    echo "FAIL: binaries requiring a glibc newer than the baseline:"
    printf '  %s\n' "${offenders[@]}"
fi

if ((${#relr_users[@]})); then
    status=1
    echo
    echo "FAIL: binaries referencing GLIBC_ABI_DT_RELR (rejected by loaders older than glibc 2.36):"
    printf '  %s\n' "${relr_users[@]#"$ROOT"/}"
fi

if ((status != 0)); then
    echo
    echo "This is the failure mode that made upstream releases unusable on the"
    echo "systems this fork targets. Do not relax the baseline to make it pass:"
    echo "find the dependency that raised it and pin or replace it instead."
fi

((scanned > 0)) || {
    echo "FAIL: no ELF files found, the package tree is probably wrong" >&2
    status=1
}

exit "$status"
