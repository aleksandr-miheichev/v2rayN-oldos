#!/usr/bin/env bash
# Install the same exact SDK as CI, including inside native package containers.
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
sdk_version="$(jq -er '.sdk.version | strings' "$repo_root/global.json")"
if [[ ! "$sdk_version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "global.json must pin an exact stable SDK version" >&2
    exit 1
fi
install_dir="${FORK_DOTNET_ROOT:-"$HOME/.dotnet"}"
installer="$(mktemp)"
trap 'rm -f "$installer"' EXIT
curl -fsSL https://dot.net/v1/dotnet-install.sh -o "$installer"
bash "$installer" --version "$sdk_version" --install-dir "$install_dir" --no-path
install_dir="$(cd "$install_dir" && pwd)"
actual_version="$(cd "$repo_root" && "$install_dir/dotnet" --version)"
if [[ "$actual_version" != "$sdk_version" ]]; then
    echo "Expected SDK $sdk_version, got $actual_version" >&2
    exit 1
fi
echo "Package SDK: $actual_version"
