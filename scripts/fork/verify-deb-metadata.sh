#!/usr/bin/env bash
# Reject mislabeled packages before they enter the release pipeline.
set -euo pipefail

fail() {
    echo "::error::$*" >&2
    exit 1
}

[[ $# -eq 2 ]] || fail "Usage: $0 <release-version> <package-directory>"
expected_version="${1#v}"
package_dir="$2"
[[ "$expected_version" =~ ^(0|[1-9][0-9]*)(\.(0|[1-9][0-9]*)){3}$ ]] \
    || fail "Expected an exact four-component release version, got '$1'."
[[ -d "$package_dir" ]] || fail "Package directory not found: $package_dir"

# Check the entire upload inventory, including unexpected nested packages.
inventory="$(find "$package_dir" -type f -name '*.deb' -printf '%P\n' | LC_ALL=C sort)"
[[ "$inventory" == $'v2rayN-linux-64.deb\nv2rayN-linux-arm64.deb' ]] \
    || fail "Expected exactly v2rayN-linux-64.deb and v2rayN-linux-arm64.deb; found: $inventory"

for target in 64:amd64 arm64:arm64; do
    IFS=: read -r asset_arch expected_arch <<< "$target"
    package="$package_dir/v2rayN-linux-$asset_arch.deb"
    actual_version="$(dpkg-deb --field "$package" Version)"
    [[ "$actual_version" == "$expected_version" ]] \
        || fail "Version mismatch in $package: expected $expected_version, got '$actual_version'."
    actual_arch="$(dpkg-deb --field "$package" Architecture)"
    [[ "$actual_arch" == "$expected_arch" ]] \
        || fail "Architecture mismatch in $package: expected $expected_arch, got '$actual_arch'."
    actual_name="$(dpkg-deb --field "$package" Package)"
    [[ "$actual_name" == v2rayn ]] \
        || fail "Package mismatch in $package: expected v2rayn, got '$actual_name'."
    echo "Verified $(basename "$package"): $actual_name $actual_version ($actual_arch)"
done
