"""Exercise sync's workflow review decisions with local Git histories."""

import os
import tempfile
from pathlib import Path

from test_webapi_release import ShellFixture, git, workflow_step

WORKFLOW = Path(".github/workflows/build-WebAPI.yml")
CONTAINER = """name: WebAPI
jobs:
  container:
    runs-on: ubuntu-24.04
    steps:
      - uses: docker/setup-buildx-action@v4
      - uses: docker/build-push-action@v7
        with:
          push: false
"""
EXPLICIT = CONTAINER.replace("          push: false\n", "          outputs: type=cacheonly\n          push: false\n")


class WorkflowReviewTests(ShellFixture):
    def setup_repository(
        self, incoming=EXPLICIT, *, reviewed=None, extra_workflow=False, executable=False, rebase_conflict=False
    ):
        repo = Path(tempfile.mkdtemp(dir=self.work))
        git(repo, "init", "--quiet", "-b", "master")
        git(repo, "config", "user.email", "test@example.invalid")
        git(repo, "config", "user.name", "Fixture")
        (repo / WORKFLOW).parent.mkdir(parents=True)
        (repo / WORKFLOW).write_text(CONTAINER, encoding="utf-8", newline="\n")
        git(repo, "add", str(WORKFLOW))
        git(repo, "commit", "--quiet", "-m", "reviewed mirror")
        git(repo, "update-ref", "refs/remotes/origin/master", "HEAD")

        git(repo, "checkout", "--quiet", "-b", "incoming")
        if incoming is None:
            (repo / WORKFLOW).unlink()
        else:
            (repo / WORKFLOW).write_text(incoming, encoding="utf-8", newline="\n")
        (repo / "product.txt").write_text("incoming code\n", encoding="utf-8")
        if extra_workflow:
            (repo / WORKFLOW.parent / "other.yml").write_text("name: Additional workflow\n", encoding="utf-8")
        git(repo, "add", ".")
        if executable:
            (repo / WORKFLOW).chmod(0o755)
            git(repo, "update-index", "--chmod=+x", str(WORKFLOW))
        git(repo, "commit", "--quiet", "-m", "upstream batch")
        git(repo, "update-ref", "refs/remotes/upstream/master", "HEAD")

        git(repo, "checkout", "--quiet", "-b", "patches", "master")
        if reviewed is not None:
            (repo / WORKFLOW).write_text(reviewed, encoding="utf-8", newline="\n")
        if rebase_conflict:
            (repo / "product.txt").write_text("conflicting fork code\n", encoding="utf-8")
        (repo / "fork.txt").write_text("reviewed fork tweak\n", encoding="utf-8")
        git(repo, "add", ".")
        git(repo, "commit", "--quiet", "-m", "fork changes")
        git(repo, "update-ref", "refs/remotes/origin/patches", "HEAD")

        bin_dir = repo / ".git/bin"
        bin_dir.mkdir()
        gh = bin_dir / "gh"
        gh.write_text(
            '#!/usr/bin/env bash\n'
            'printf "%s\\n" "$*" >> "$GH_LOG"\n'
            'if [[ "$1 $2" == "issue list" ]]; then printf "%s\\n" "${EXISTING_ISSUE:-null}"; fi\n',
            encoding="utf-8",
            newline="\n",
        )
        gh.chmod(0o755)
        return repo

    def run_step(self, repo, *, name=None, step_id=None, **overrides):
        temp = repo / ".git"
        script = workflow_step("sync-upstream.yml", "sync", name=name, step_id=step_id)
        output = temp / "actions-output"
        output.write_text("", encoding="utf-8")
        env = {
            "GITHUB_OUTPUT": str(output),
            "GITHUB_STEP_SUMMARY": str(temp / "actions-summary"),
            "GITHUB_RUN_ID": "789",
            "RUNNER_TEMP": str(temp),
            "PATCH_BRANCH": "patches",
            "PRODUCT_BRANCH": "oldos",
            "GH_LOG": str(temp / "gh.log"),
            "PATH": str(temp / "bin") + os.pathsep + os.environ["PATH"],
            **overrides,
        }
        result = self.shell(script, env, repo)
        return result, dict(line.split("=", 1) for line in output.read_text().splitlines())

    def rebase_and_check(self, repo, *, conflict="false", **gate_env):
        result, outputs = self.run_step(repo, step_id="rebase")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual({"conflict": conflict}, outputs)
        return self.run_step(repo, step_id="gate", REBASE_CONFLICT=outputs["conflict"], **gate_env)

    def test_explicit_cache_only_allows_source_sync_without_filing_an_issue(self):
        repo = self.setup_repository(reviewed=EXPLICIT)
        gate, values = self.rebase_and_check(repo)
        self.assertEqual(0, gate.returncode, gate.stdout + gate.stderr)
        self.assertEqual({"review": "false", "defer_mirror": "true"}, values)
        self.assertFalse((repo / ".git/gh.log").exists())
        self.assertIn("mirror", (repo / ".git/actions-summary").read_text())

        mirror, _ = self.run_step(repo, name="Update the mirror branch", DEFER_MIRROR="true")
        self.assertEqual(0, mirror.returncode, mirror.stdout + mirror.stderr)
        self.assertEqual(git(repo, "rev-parse", "master"), git(repo, "rev-parse", "origin/master"))

        guard, _ = self.run_step(repo, name="Verify rebased workflow content")
        self.assertEqual(0, guard.returncode, guard.stdout + guard.stderr)
        self.assertEqual("incoming code\n", (repo / "product.txt").read_text())

        close, _ = self.run_step(repo, name="Close resolved sync issues", DEFER_MIRROR="true", EXISTING_ISSUE="49")
        self.assertEqual(0, close.returncode, close.stdout + close.stderr)
        calls = (repo / ".git/gh.log").read_text()
        self.assertIn("issue close 49", calls)
        self.assertIn("last reviewed", calls)
        self.assertNotIn("issue create", calls)

    def test_upstream_workflow_delta_already_published_on_patches_needs_no_issue(self):
        updated = EXPLICIT.replace("docker/setup-buildx-action@v4", "docker/setup-buildx-action@v5")
        repo = self.setup_repository(incoming=updated, reviewed=updated)
        gate, values = self.rebase_and_check(repo)
        self.assertEqual(0, gate.returncode, gate.stdout + gate.stderr)
        self.assertEqual({"review": "false", "defer_mirror": "true"}, values)
        self.assertFalse((repo / ".git/gh.log").exists())

    def test_guard_rejects_new_workflow_content_after_the_gate(self):
        repo = self.setup_repository(reviewed=EXPLICIT)
        gate, values = self.rebase_and_check(repo)
        self.assertEqual(0, gate.returncode, gate.stdout + gate.stderr)
        self.assertEqual("true", values["defer_mirror"])

        (repo / WORKFLOW).write_text(CONTAINER, encoding="utf-8", newline="\n")
        git(repo, "commit", "--quiet", "-am", "unexpected new workflow after review")
        guard, _ = self.run_step(repo, name="Verify rebased workflow content")
        self.assertNotEqual(0, guard.returncode, guard.stdout + guard.stderr)
        self.assertIn(str(WORKFLOW), (repo / ".git/sync-failure.txt").read_text())

    def test_effective_workflow_changes_require_review(self):
        cases = (
            {},
            {"incoming": EXPLICIT.replace("push: false", "push: true")},
            {"incoming": EXPLICIT.replace("build-push-action@v7", "build-push-action@v8")},
            {"incoming": None},
            {"reviewed": EXPLICIT, "extra_workflow": True},
            {"reviewed": EXPLICIT, "executable": True},
        )
        for case in cases:
            with self.subTest(case=case):
                repo = self.setup_repository(**case)
                gate, values = self.rebase_and_check(repo)
                self.assertEqual(1, gate.returncode, gate.stdout + gate.stderr)
                self.assertEqual({"review": "true"}, values)
                self.assertIn("issue create", (repo / ".git/gh.log").read_text())

    def test_reverted_upstream_workflow_still_requires_review_when_the_fork_changes(self):
        repo = self.setup_repository(reviewed=EXPLICIT)
        gate, values = self.rebase_and_check(repo)
        self.assertEqual(0, gate.returncode, gate.stdout + gate.stderr)
        self.assertEqual("true", values["defer_mirror"])
        git(repo, "update-ref", "refs/remotes/origin/patches", "HEAD")

        git(repo, "switch", "--quiet", "incoming")
        (repo / WORKFLOW).write_text(CONTAINER, encoding="utf-8", newline="\n")
        git(repo, "commit", "--quiet", "-am", "revert upstream workflow to the held mirror")
        git(repo, "update-ref", "refs/remotes/upstream/master", "HEAD")
        git(repo, "switch", "--quiet", "patches")

        gate, values = self.rebase_and_check(repo)
        self.assertEqual(1, gate.returncode, gate.stdout + gate.stderr)
        self.assertEqual({"review": "true"}, values)
        self.assertIn("issue create", (repo / ".git/gh.log").read_text())

    def test_workflow_change_with_a_conflict_uses_the_existing_review_issue(self):
        repo = self.setup_repository(reviewed=EXPLICIT, rebase_conflict=True)
        gate, values = self.rebase_and_check(repo, conflict="true", EXISTING_ISSUE="49")
        self.assertEqual(0, gate.returncode, gate.stdout + gate.stderr)
        self.assertEqual({"review": "true"}, values)
        self.assertIn("Issue #49 is already waiting", gate.stdout)
        self.assertNotIn("issue create", (repo / ".git/gh.log").read_text())
        self.assertEqual(git(repo, "rev-parse", "HEAD"), git(repo, "rev-parse", "origin/patches"))

    def test_code_only_batches_still_use_the_ordinary_sync_path(self):
        for conflict in ("false", "true"):
            with self.subTest(conflict=conflict):
                repo = self.setup_repository(incoming=CONTAINER, rebase_conflict=conflict == "true")
                gate, values = self.rebase_and_check(repo, conflict=conflict)
                self.assertEqual(0, gate.returncode, gate.stdout + gate.stderr)
                self.assertEqual({"review": "false"}, values)
                self.assertFalse((repo / ".git/gh.log").exists())
