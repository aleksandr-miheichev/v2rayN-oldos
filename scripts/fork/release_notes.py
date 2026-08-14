#!/usr/bin/env python3
"""Build release notes from the commits that actually landed.

Upstream's own release descriptions are terse, so this fork derives its notes
from the commit history instead. Upstream does not use Conventional Commits --
subjects look like "Set tun \"route only\" to true (#9933)" or "up 7.24.6" --
so commits are grouped by matching the subject against the project's real
vocabulary rather than by a "type:" prefix.

Commits carry the pull request number of the upstream repository, which is
turned into a link so every line is traceable back to its discussion.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys

UPSTREAM = "https://github.com/2dust/v2rayN"

# Ordered: the first pattern that matches wins, so the specific ones come first
# and the catch-all is last. Anything genuinely uninteresting is dropped.
GROUPS: list[tuple[str, str]] = [
    (r"^\s*revert\b", "Reverted"),
    (r"\b(tun|tproxy|route|routing|rule[- ]?set|geoip|geosite|sniff)\b", "Routing and TUN"),
    (r"\b(dns|doh|doq|dot|resolver)\b", "DNS"),
    (r"\b(xray|sing-?box|mihomo|core|reality|vless|vmess|hysteria|tuic|wireguard|shadowsocks|trojan)\b",
     "Protocols and cores"),
    (r"\b(ui|gui|theme|window|icon|tray|layout|font|dark mode|avalonia)\b", "User interface"),
    (r"\b(i18n|l10n|translat|locale|language|resx)\b", "Translations"),
    (r"\b(subscription|profile|server|group|import|export|share|qr)\b", "Profiles and subscriptions"),
    (r"\b(deps?|dependenc|bump|nuget|package version)\b", "Dependencies"),
    (r"\b(ci|workflow|build|package|release|installer|deb|rpm|dmg|winget)\b", "Build and packaging"),
    (r"\b(fix|bug|crash|error|issue|regression|leak)\b", "Fixes"),
    (r".*", "Other changes"),
]

SKIP = re.compile(r"^\s*(up\s+\d|merge branch|merge pull request|update readme)", re.IGNORECASE)

PR_RE = re.compile(r"\(#(\d+)\)")


def run(args: list[str]) -> str:
    result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", check=True)
    return result.stdout


def collect(since: str, until: str) -> list[tuple[str, str]]:
    """(sha, subject) pairs of what is new on the release side.

    The symmetric range with --cherry-pick matters: the hourly sync rebases the
    fork's patch stack, which rewrites every one of its SHAs, and a plain
    A..B range would then relist the entire stack as "new" in the next
    release. Patch-id comparison drops those rebased duplicates.
    """
    out = run(["git", "log", "--no-merges", "--right-only", "--cherry-pick",
               "--pretty=format:%H\t%s", f"{since}...{until}"])
    pairs = []
    for line in out.splitlines():
        if "\t" in line:
            sha, subject = line.split("\t", 1)
            if subject.strip():
                pairs.append((sha, subject.strip()))
    return pairs


def fork_commit_set(upstream_ref: str, until: str) -> set[str]:
    out = run(["git", "rev-list", f"{upstream_ref}..{until}"])
    return set(out.split())


def classify(subject: str) -> str:
    for pattern, group in GROUPS:
        if re.search(pattern, subject, re.IGNORECASE):
            return group
    return "Other changes"


def linkify(subject: str, upstream: str) -> str:
    return PR_RE.sub(lambda m: f"([#{m.group(1)}]({upstream}/pull/{m.group(1)}))", subject)


# Commits written by this fork do follow Conventional Commits; capitalising
# them would turn "i18n(ru): ..." into "I18n(ru): ...".
CONVENTIONAL_RE = re.compile(r"^[a-z]+(\([^)]*\))?!?: ")


def upper_first(subject: str) -> str:
    if CONVENTIONAL_RE.match(subject):
        return subject
    return subject[:1].upper() + subject[1:]


def render(pairs: list[tuple[str, str]], upstream: str, fork_set: set[str] | None) -> str:
    """Upstream changes grouped by topic; the fork's own commits do not appear.

    The reader of a release page wants to know what changed in the
    application, which means upstream's commits. The fork's CI and packaging
    commits are dropped outright: the "what differs" compare link in the
    release boilerplate already discloses the fork's changes in full.
    """
    buckets: dict[str, list[str]] = {}
    for sha, subject in pairs:
        if SKIP.match(subject):
            continue
        if fork_set is not None and sha in fork_set:
            continue
        buckets.setdefault(classify(subject), []).append(linkify(subject, upstream))

    order = []
    for _, group in GROUPS:
        if group in buckets and group not in order:
            order.append(group)

    lines: list[str] = []
    for group in order:
        lines.append(f"### {group}")
        lines.append("")
        for subject in buckets[group]:
            lines.append(f"- {upper_first(subject)}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n" if lines else ""


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="since", required=True, help="previous release tag or commit")
    parser.add_argument("--to", dest="until", default="HEAD")
    parser.add_argument("--upstream", default=UPSTREAM)
    parser.add_argument("--upstream-ref",
                        help="ref of upstream's master; commits not reachable from it "
                             "are the fork's own and are folded into a maintenance block")
    parser.add_argument("--output")
    args = parser.parse_args()

    pairs = collect(args.since, args.until)
    fork_set = fork_commit_set(args.upstream_ref, args.until) if args.upstream_ref else None
    body = render(pairs, args.upstream, fork_set)
    if not body:
        body = "No source changes since the previous release.\n"

    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(body)
    else:
        sys.stdout.write(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
