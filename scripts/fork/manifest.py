#!/usr/bin/env python3
"""Record and compare everything that shapes a release but leaves no commit behind.

Release notes for this fork are generated from upstream commits. That is
accurate for source changes and completely blind to everything else: a NuGet
package resolving to a different version, a new .NET SDK patch, a rebuilt
native library, or a core binary downloaded from an external repository at
packaging time. Those are precisely the changes that broke older systems
before, and none of them appear in `git log`.

  build  writes a manifest describing the real inputs of a build
  diff   compares two manifests and renders the differences as Markdown

The release workflow appends the rendered diff to the commit-derived changelog,
so a release always states what changed, whether or not a commit caused it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ELF_MAGIC = b"\x7fELF"
GLIBC_RE = re.compile(rb"GLIBC_(\d+)\.(\d+)")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_elf(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(4) == ELF_MAGIC
    except OSError:
        return False


def glibc_baseline(path: Path) -> str | None:
    """Highest GLIBC_x.y symbol version the binary requires.

    readelf is preferred because it reads the version-requirements section
    proper. The raw byte scan is a fallback for environments without binutils:
    those version strings live in .dynstr, so finding them is strong evidence,
    though it cannot distinguish a requirement from an unrelated string.
    """
    versions: list[tuple[int, int]] = []
    try:
        out = subprocess.run(
            ["readelf", "--version-info", str(path)],
            capture_output=True,
            check=False,
        ).stdout
        versions = [(int(a), int(b)) for a, b in GLIBC_RE.findall(out)]
    except FileNotFoundError:
        versions = [(int(a), int(b)) for a, b in GLIBC_RE.findall(path.read_bytes())]
    if not versions:
        return None
    major, minor = max(versions)
    return f"{major}.{minor}"


def collect_native(root: Path) -> dict[str, dict[str, str]]:
    native: dict[str, dict[str, str]] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or not is_elf(path):
            continue
        entry = {"sha256": sha256(path)}
        baseline = glibc_baseline(path)
        if baseline:
            entry["glibc"] = baseline
        native[str(path.relative_to(root)).replace("\\", "/")] = entry
    return native


def collect_packages(assets: Path) -> dict[str, str]:
    """Every resolved NuGet package, direct and transitive, from project.assets.json."""
    data = json.loads(assets.read_text(encoding="utf-8"))
    packages: dict[str, str] = {}
    for key, value in (data.get("libraries") or {}).items():
        if value.get("type") != "package" or "/" not in key:
            continue
        name, version = key.rsplit("/", 1)
        packages[name] = version
    return dict(sorted(packages.items()))


def cmd_build(args: argparse.Namespace) -> int:
    manifest: dict[str, object] = {
        "schema": 1,
        "version": args.version,
        "commit": args.commit,
        "upstream_commit": args.upstream_commit,
        "dotnet_sdk": args.dotnet_sdk,
    }
    if args.assets:
        manifest["packages"] = collect_packages(Path(args.assets))
    if args.package_root:
        manifest["native"] = collect_native(Path(args.package_root))

    Path(args.output).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    native = manifest.get("native") or {}
    packages = manifest.get("packages") or {}
    print(f"manifest written to {args.output}: {len(packages)} packages, {len(native)} binaries")
    return 0


def diff_mapping(old: dict, new: dict) -> tuple[list, list, list]:
    added = [(k, new[k]) for k in new if k not in old]
    removed = [(k, old[k]) for k in old if k not in new]
    changed = [(k, old[k], new[k]) for k in new if k in old and old[k] != new[k]]
    return sorted(added), sorted(removed), sorted(changed)


def render(old: dict, new: dict) -> str:
    lines: list[str] = []

    for label, key in (("SDK", "dotnet_sdk"),):
        if old.get(key) != new.get(key) and new.get(key):
            lines.append(f"- .NET {label}: `{old.get(key) or 'unknown'}` → `{new.get(key)}`")

    added, removed, changed = diff_mapping(old.get("packages") or {}, new.get("packages") or {})
    for name, was, now in changed:
        lines.append(f"- Dependency `{name}`: `{was}` → `{now}`")
    for name, version in added:
        lines.append(f"- Dependency `{name}` added at `{version}`")
    for name, version in removed:
        lines.append(f"- Dependency `{name}` removed (was `{version}`)")

    old_native = old.get("native") or {}
    new_native = new.get("native") or {}
    n_added, n_removed, n_changed = diff_mapping(old_native, new_native)

    # An ABI baseline move is the single most important thing this fork tracks,
    # so it is called out separately instead of being buried among file hashes.
    for name, was, now in n_changed:
        if was.get("glibc") != now.get("glibc"):
            lines.append(
                f"- **ABI baseline of `{name}`: GLIBC_{was.get('glibc') or '?'} "
                f"→ GLIBC_{now.get('glibc') or '?'}**"
            )

    rebuilt = [n for n, was, now in n_changed if was.get("glibc") == now.get("glibc")]
    if rebuilt:
        shown = ", ".join(f"`{n}`" for n in rebuilt[:8])
        more = f" and {len(rebuilt) - 8} more" if len(rebuilt) > 8 else ""
        lines.append(f"- Rebuilt native binaries: {shown}{more}")
    if n_added:
        lines.append(f"- New native binaries: {', '.join(f'`{n}`' for n, _ in n_added[:8])}")
    if n_removed:
        lines.append(f"- Removed native binaries: {', '.join(f'`{n}`' for n, _ in n_removed[:8])}")

    if not lines:
        return ""
    return "### Changes not visible in the commit history\n\n" + "\n".join(lines) + "\n"


def cmd_diff(args: argparse.Namespace) -> int:
    old_path = Path(args.old)
    old = json.loads(old_path.read_text(encoding="utf-8")) if old_path.is_file() else {}
    new = json.loads(Path(args.new).read_text(encoding="utf-8"))
    body = render(old, new)
    if args.output:
        Path(args.output).write_text(body, encoding="utf-8")
    else:
        sys.stdout.write(body)
    return 0


def main() -> int:
    # The rendered Markdown contains arrows; without this it dies on any console
    # whose default encoding is not UTF-8.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="write a manifest of this build's inputs")
    build.add_argument("--output", required=True)
    build.add_argument("--assets", help="path to project.assets.json")
    build.add_argument("--package-root", help="unpacked package tree to scan for binaries")
    build.add_argument("--version", default="")
    build.add_argument("--commit", default="")
    build.add_argument("--upstream-commit", default="")
    build.add_argument("--dotnet-sdk", default="")
    build.set_defaults(func=cmd_build)

    diff = sub.add_parser("diff", help="render the differences between two manifests")
    diff.add_argument("old", help="previous manifest (missing file is treated as empty)")
    diff.add_argument("new")
    diff.add_argument("--output")
    diff.set_defaults(func=cmd_diff)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
