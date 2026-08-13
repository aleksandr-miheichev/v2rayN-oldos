#!/usr/bin/env python3
"""Validate GitHub workflow files before they cost a CI round-trip.

Two defect classes this fork has actually shipped and paid for:

  1. YAML that does not parse -- a ${{ }} expression inside an unquoted flow
     mapping ends the mapping at the expression's first closing brace;
  2. embedded bash that does not parse -- quoting mistakes and heredoc slips
     survive careless review because nothing executes the script until a
     runner does.

Both are caught here in under a second. PowerShell steps are skipped: this
repository validates only what runs through bash on the runners.

A check that cannot measure must fail rather than pass silently -- a missing
interpreter once turned a whole verification step into a no-op warning, so an
absent bash or PyYAML is reported as a failure, not skipped.

Usage:
  lint-workflows.py                    validate every .github/workflows/*.yml
  lint-workflows.py FILE...            validate the given files
  lint-workflows.py --hook             PostToolUse mode: read the tool-call
                                       JSON from stdin, validate the edited
                                       file if it is a workflow, exit 2 with
                                       findings on stderr so the model sees
                                       them and fixes the file before pushing
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

# The default shell on these runners is not bash, and a `shell:` of any of
# these is not bash either; there is nothing for this linter to execute.
NON_BASH_SHELLS = {"pwsh", "powershell", "cmd", "python"}


def check_file(path: str) -> list[str]:
    findings: list[str] = []
    try:
        text = open(path, encoding="utf-8").read()
    except OSError as exc:
        return [f"{path}: cannot read: {exc}"]

    try:
        import yaml
    except ImportError:
        return [f"{path}: PyYAML is not installed, nothing was validated"]

    try:
        doc = yaml.safe_load(text)
    except Exception as exc:
        return [f"{path}: YAML does not parse: {exc}"]
    if not isinstance(doc, dict):
        return [f"{path}: parses to {type(doc).__name__}, expected a mapping"]

    bash = shutil.which("bash")
    checked = 0
    for job_name, job in (doc.get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        runs_on = str(job.get("runs-on", ""))
        for index, step in enumerate(job.get("steps") or []):
            if not isinstance(step, dict):
                continue
            script = step.get("run")
            if not isinstance(script, str):
                continue
            shell = step.get("shell")
            if shell in NON_BASH_SHELLS:
                continue
            if shell is None and "windows" in runs_on.lower():
                continue

            label = f"{path}: job '{job_name}' step {index + 1} ({step.get('name', 'unnamed')})"
            if bash is None:
                return findings + [f"{label}: bash is not on PATH, embedded scripts were NOT verified"]

            # bash reads the file itself, so the newline style must be Unix
            # regardless of what this machine would write by default.
            handle = tempfile.NamedTemporaryFile(
                "w", suffix=".sh", encoding="utf-8", newline="\n", delete=False)
            try:
                handle.write(script)
                handle.close()
                result = subprocess.run(
                    ["bash", "-n", handle.name], capture_output=True, text=True)
                if result.returncode != 0:
                    detail = (result.stderr or "").replace(handle.name, "<step script>").strip()
                    findings.append(f"{label}: bash cannot parse the script:\n  {detail}")
                checked += 1
            finally:
                os.unlink(handle.name)

    if not findings:
        print(f"OK  {path}  ({checked} bash steps parse)")
    return findings


def hook_mode() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception as exc:
        # Never return 0 here. A payload this hook cannot read means it is
        # validating nothing at all, and silence would hide that forever --
        # exactly how a no-op check once passed every macOS binary. Exit 1 is
        # visible without blocking the edit.
        sys.stderr.write(f"lint-workflows: cannot read the tool payload, nothing was validated: {exc}\n")
        return 1
    if payload.get("tool_name") not in ("Edit", "MultiEdit", "Write"):
        return 0
    file_path = ((payload.get("tool_input") or {}).get("file_path") or "").replace("\\", "/")
    if "/.github/workflows/" not in file_path or not file_path.endswith((".yml", ".yaml")):
        return 0
    if not os.path.exists(file_path):
        return 0

    findings = check_file(file_path)
    if findings:
        sys.stderr.write(
            "The edited workflow would fail on GitHub before any job runs:\n"
            + "\n".join(findings)
            + "\nFix the file before pushing; a broken workflow costs a CI round-trip.\n")
        return 2
    return 0


def main() -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args = sys.argv[1:]
    if args == ["--hook"]:
        return hook_mode()

    paths = args or sorted(glob.glob(".github/workflows/*.yml")
                           + sorted(glob.glob(".github/workflows/*.yaml")))
    if not paths:
        print("no workflow files found", file=sys.stderr)
        return 1

    all_findings: list[str] = []
    for path in paths:
        all_findings.extend(check_file(path))

    if all_findings:
        print("\n".join(all_findings), file=sys.stderr)
        return 1
    print(f"{len(paths)} workflow files are clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
