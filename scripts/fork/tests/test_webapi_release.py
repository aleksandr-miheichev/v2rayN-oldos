"""Execute WebAPI workflow guards against local release and Git fixtures."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[3]
BASH = shutil.which("bash") if os.name != "nt" else r"C:\Program Files\Git\bin\bash.exe"
DESKTOP = (
    "manifest.json", "v2rayN-public-key.asc",
    "v2rayN-linux-64.deb",
)
WEB = (
    "v2rayN-linux-64-WebAPI.zip", "v2rayN-linux-64-WebAPI-update.zip",
    "v2rayN-linux-arm64-WebAPI.zip", "v2rayN-linux-arm64-WebAPI-update.zip",
    "v2rayN-windows-64-WebAPI.zip", "v2rayN-windows-64-WebAPI-update.zip",
    "v2rayN-windows-arm64-WebAPI.zip", "v2rayN-windows-arm64-WebAPI-update.zip",
    "WebAPI-update.json",
)
GH_STUB = r'''
import json, os, pathlib, subprocess, sys
sys.stdout.reconfigure(newline="\n")
root = pathlib.Path(os.environ["GH_FIXTURE"])
args = sys.argv[1:]
releases = json.loads((root / "releases.json").read_text())
if args[:2] == ["release", "list"]:
    result = releases
elif args[:2] == ["release", "view"]:
    result = next(r for r in releases if r["tagName"] == args[2])
    if ".assets" in args:
        counter = root / "asset-reads"
        count = int(counter.read_text()) + 1 if counter.exists() else 1
        counter.write_text(str(count))
        if count > 1 and (root / "second-assets.json").exists():
            result = dict(result, assets=json.loads((root / "second-assets.json").read_text()))
else:
    raise SystemExit("Unexpected gh operation: " + repr(args))
if "--jq" in args:
    query = args[args.index("--jq") + 1]
    process = subprocess.run(["jq", "-r", query], input=json.dumps(result), text=True, capture_output=True)
    sys.stdout.write(process.stdout)
    sys.stderr.write(process.stderr)
    raise SystemExit(process.returncode)
print(json.dumps(result))
'''


def workflow_step(workflow: str, job: str, *, name: str | None = None, step_id: str | None = None) -> str:
    document = yaml.safe_load((ROOT / ".github/workflows" / workflow).read_text(encoding="utf-8"))
    steps = document["jobs"].get(job, {}).get("steps", [])
    for step in steps:
        if (name and step.get("name") == name) or (step_id and step.get("id") == step_id):
            return step["run"]
    raise AssertionError(f"Missing executable guard in {workflow}, job {job}: {name or step_id}")


def git(directory: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "core.autocrlf=false", "-c", "user.name=Release fixture",
         "-c", "user.email=fixture@example.invalid", "-C", str(directory), *args],
        check=True, capture_output=True, text=True,
    )


def catalog(names: tuple[str, ...]) -> str:
    return "\n".join(names) + "\n"


def assets(names: tuple[str, ...], *, recent: bool = False) -> list[dict[str, str]]:
    date = "2099-01-01T00:00:00Z" if recent else "2020-01-01T00:00:00Z"
    result = []
    for name in names:
        result.append({"name": name, "updatedAt": date})
        if name not in ("manifest.json", "v2rayN-public-key.asc"):
            result.append({"name": name + ".sig", "updatedAt": date})
    return result


class ShellFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="webapi-release-")
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name)

    def shell(self, script: str, env: dict[str, str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        path = self.work / "step.sh"
        path.write_text(script, encoding="utf-8", newline="\n")
        return subprocess.run(
            [BASH, "--noprofile", "--norc", "-eo", "pipefail", path.as_posix()],
            cwd=cwd or self.work, env=dict(os.environ, **env),
            capture_output=True, text=True, timeout=120,
        )

class WorkflowGuards(ShellFixture):
    def test_four_component_build_identity_preserves_the_release_version(self) -> None:
        script = workflow_step("build-WebAPI.yml", "identity", step_id="resolve")
        output = self.work / "output"
        result = self.shell(script, {"RELEASE_TAG": "7.25.6.42", "GITHUB_OUTPUT": output.as_posix()})
        self.assertEqual(result.returncode, 0, result.stderr)
        values = dict(line.split("=", 1) for line in output.read_text().splitlines())
        self.assertEqual(values["version"], "7.25.6.42")
        self.assertEqual(values["tag"], "7.25.6.42")
        self.assertEqual(values["release"], "true")

    def test_malformed_official_tags_cannot_enter_the_release_path(self) -> None:
        script = workflow_step("build-WebAPI.yml", "identity", step_id="resolve")
        for tag in ("v7.25.6.42", "7.25.6.042", "7.25.6.42.1", "7.25.6.42-dev"):
            with self.subTest(tag=tag):
                result = self.shell(script, {"RELEASE_TAG": tag, "GITHUB_OUTPUT": (self.work / "output").as_posix()})
                self.assertNotEqual(result.returncode, 0)

    def test_development_build_remains_non_releasing(self) -> None:
        script = workflow_step("build-WebAPI.yml", "identity", step_id="resolve")
        output = self.work / "output"
        result = self.shell(script, {"RELEASE_TAG": "", "GITHUB_OUTPUT": output.as_posix()})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("release=false", output.read_text().splitlines())

    def test_release_source_must_match_its_tag(self) -> None:
        script = workflow_step("release-WebAPI.yml", "source", name="Validate release source")
        for ref_type, ref_name, expected in (("tag", "7.25.6.42", 0), ("branch", "oldos", 1), ("tag", "7.25.6.41", 1)):
            with self.subTest(ref_type=ref_type, ref_name=ref_name):
                result = self.shell(script, {"RELEASE_TAG": "7.25.6.42", "RELEASE_REF_TYPE": ref_type, "RELEASE_REF_NAME": ref_name})
                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)


class FinalizerContract(ShellFixture):
    def setUp(self) -> None:
        super().setUp()
        self.origin = self.work / "origin"
        self.origin.mkdir()
        git(self.origin, "init", "--quiet")
        self.list_path = self.origin / "scripts/fork/expected-release-assets.txt"
        self.list_path.parent.mkdir(parents=True)
        for tag, text in (("7.25.6.1", catalog(DESKTOP)), ("7.25.6.2", catalog(DESKTOP + WEB)),
                          ("7.25.6.3", "# Empty contract\n")):
            self.list_path.write_text(text, encoding="utf-8", newline="\n")
            git(self.origin, "add", ".")
            git(self.origin, "commit", "--quiet", "-m", "fixture")
            git(self.origin, "tag", tag)
        git(self.origin, "rm", "--quiet", "scripts/fork/expected-release-assets.txt")
        git(self.origin, "commit", "--quiet", "-m", "missing contract")
        git(self.origin, "tag", "7.25.6.4")
        self.repo = self.work / "checkout"
        subprocess.run(["git", "clone", "--quiet", str(self.origin), str(self.repo)], check=True, capture_output=True)
        git(self.repo, "checkout", "--quiet", "7.25.6.2")
        self.bin = self.work / "bin"
        self.bin.mkdir()
        (self.work / "gh.py").write_text(GH_STUB, encoding="utf-8", newline="\n")
        for name, body in (("gh", '#!/bin/sh\nexec "$GH_PYTHON" "$GH_SCRIPT" "$@"\n'),
                           ("sleep", "#!/bin/sh\nexit 0\n")):
            path = self.bin / name
            path.write_text(body, encoding="utf-8", newline="\n")
            path.chmod(0o755)

    def pick(self, tag: str, present: list[dict[str, str]], second: list[dict[str, str]] | None = None):
        release = {"tagName": tag, "isPrerelease": True, "isDraft": False, "assets": present}
        (self.work / "releases.json").write_text(json.dumps([release]), encoding="utf-8")
        if second is not None:
            (self.work / "second-assets.json").write_text(json.dumps(second), encoding="utf-8")
        output = self.work / "output"
        output.write_text("", encoding="utf-8")
        script = workflow_step("finalize-release.yml", "finalize", step_id="pick").replace("${{ inputs.tag }}", tag)
        prefix = 'if command -v cygpath >/dev/null 2>&1; then GH_BIN="$(cygpath -u "$GH_BIN")"; fi\nexport PATH="$GH_BIN:$PATH"\n'
        result = self.shell(prefix + script, {
            "GH_FIXTURE": self.work.as_posix(), "GH_PYTHON": Path(sys.executable).as_posix(),
            "GH_SCRIPT": (self.work / "gh.py").as_posix(), "GH_BIN": self.bin.as_posix(),
            "GITHUB_OUTPUT": output.as_posix(), "SETTLE_MINUTES": "0",
        }, self.repo)
        values = dict(line.split("=", 1) for line in output.read_text().splitlines() if "=" in line)
        return result, values

    def test_old_release_uses_its_tagged_desktop_contract(self) -> None:
        result, values = self.pick("7.25.6.1", assets(DESKTOP))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(values.get("ready"), "true", result.stdout)

    def test_new_release_waits_for_webapi_assets(self) -> None:
        result, values = self.pick("7.25.6.2", assets(DESKTOP))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(values.get("ready"), "false", result.stdout)

    def test_new_release_waits_for_the_manifest_signature(self) -> None:
        present = [a for a in assets(DESKTOP + WEB) if a["name"] != "WebAPI-update.json.sig"]
        result, values = self.pick("7.25.6.2", present)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(values.get("ready"), "false", result.stdout)

    def test_complete_new_release_is_ready(self) -> None:
        result, values = self.pick("7.25.6.2", assets(DESKTOP + WEB))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(values.get("ready"), "true", result.stdout)

    def test_empty_contract_fails_closed(self) -> None:
        result, _ = self.pick("7.25.6.3", assets(DESKTOP + WEB))
        self.assertNotEqual(result.returncode, 0, result.stdout)

    def test_missing_contract_fails_closed(self) -> None:
        result, _ = self.pick("7.25.6.4", assets(DESKTOP + WEB))
        self.assertNotEqual(result.returncode, 0, result.stdout)

    def test_unknown_tag_fails_closed(self) -> None:
        result, _ = self.pick("7.25.6.9", assets(DESKTOP + WEB))
        self.assertNotEqual(result.returncode, 0, result.stdout)

    def test_settle_recheck_retains_the_tagged_signature_contract(self) -> None:
        second = [a for a in assets(DESKTOP + WEB) if a["name"] != "WebAPI-update.json.sig"]
        result, values = self.pick("7.25.6.2", assets(DESKTOP + WEB, recent=True), second)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(values.get("ready"), "false", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
