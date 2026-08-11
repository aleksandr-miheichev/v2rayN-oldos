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


def collect(rev_range: str) -> list[str]:
    out = run(["git", "log", "--no-merges", "--pretty=format:%s", rev_range])
    return [line.strip() for line in out.splitlines() if line.strip()]


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


def render(subjects: list[str], upstream: str) -> str:
    buckets: dict[str, list[str]] = {}
    for subject in subjects:
        if SKIP.match(subject):
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
    parser.add_argument("--output")
    args = parser.parse_args()

    subjects = collect(f"{args.since}..{args.until}")
    body = render(subjects, args.upstream)
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
