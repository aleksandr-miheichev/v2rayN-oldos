"""Exercise the sync workflow's cache-only exception with local Git histories."""

import os
import shutil
import tempfile
from pathlib import Path

from test_webapi_release import ROOT, ShellFixture, git, workflow_step

WORKFLOW = Path(".github/workflows/build-WebAPI.yml")
HELPER = Path("scripts/fork/check-cache-only-workflow.py")
CONTAINER = """name: WebAPI
jobs:
  container:
    runs-on: ubuntu-24.04
    steps:
      - uses: docker/setup-buildx-action@v4
      - name: Build API container (no push)
        uses: docker/build-push-action@v7
        env:
          DOCKER_BUILD_RECORD_UPLOAD: false
        with:
          context: .
          file: ./v2rayN/v2rayN.WebAPI/Containerfile
          platforms: ${{ matrix.platform }}
          tags: v2rayn-webapi:ci
          build-args: |
            RID=${{ matrix.rid }}
            WEB_VERSION=${{ needs.identity.outputs.version }}
            WEB_REPOSITORY=${{ github.repository }}
            WEB_COMMIT=${{ github.sha }}
            WEB_BUILD_DATE=${{ needs.identity.outputs.build_date }}
          push: false

  release-assets:
    runs-on: ubuntu-24.04
"""
EXPLICIT = CONTAINER.replace("          push: false\n", "          outputs: type=cacheonly\n          push: false\n")


class WorkflowReviewTests(ShellFixture):
    def setup_repository(self, incoming=EXPLICIT, *, mirror=CONTAINER, reviewed=None, extra_workflow=False, executable=False):
        repo = Path(tempfile.mkdtemp(dir=self.work))
        git(repo, "init", "--quiet", "-b", "master")
        git(repo, "config", "user.email", "test@example.invalid")
        git(repo, "config", "user.name", "Fixture")
        (repo / WORKFLOW).parent.mkdir(parents=True)
        (repo / WORKFLOW).write_text(mirror, encoding="utf-8", newline="\n")
        git(repo, "add", str(WORKFLOW))
        git(repo, "commit", "--quiet", "-m", "reviewed mirror")
        git(repo, "update-ref", "refs/remotes/origin/master", "HEAD")

        git(repo, "checkout", "--quiet", "-b", "incoming")
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
        if (ROOT / HELPER).exists():
            (repo / HELPER).parent.mkdir(parents=True)
            shutil.copyfile(ROOT / HELPER, repo / HELPER)
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

    def test_explicit_cache_only_allows_source_sync_without_filing_an_issue(self):
        repo = self.setup_repository(reviewed=EXPLICIT)
        gate, values = self.run_step(repo, step_id="gate")
        self.assertEqual(0, gate.returncode, gate.stdout + gate.stderr)
        self.assertEqual({"review": "false", "cache_only": "true"}, values)
        self.assertFalse((repo / ".git/gh.log").exists())
        self.assertIn("mirror", (repo / ".git/actions-summary").read_text())

        mirror, _ = self.run_step(repo, name="Update the mirror branch", CACHE_ONLY="true")
        self.assertEqual(0, mirror.returncode, mirror.stdout + mirror.stderr)
        git(repo, "diff", "--exit-code", "master", "origin/master")

        replay, result = self.run_step(repo, step_id="rebase")
        self.assertEqual(0, replay.returncode, replay.stdout + replay.stderr)
        self.assertEqual({"conflict": "false"}, result)
        guard, _ = self.run_step(repo, name="Verify rebased workflow content")
        self.assertEqual(0, guard.returncode, guard.stdout + guard.stderr)
        self.assertEqual("incoming code\n", (repo / "product.txt").read_text())

        close, _ = self.run_step(repo, name="Close resolved sync issues", CACHE_ONLY="true", EXISTING_ISSUE="47")
        self.assertEqual(0, close.returncode, close.stdout + close.stderr)
        calls = (repo / ".git/gh.log").read_text()
        self.assertIn("issue close 47", calls)
        self.assertIn("last reviewed", calls)
        self.assertNotIn("issue create", calls)

    def test_cache_only_rebase_rejects_a_workflow_that_is_not_already_reviewed(self):
        repo = self.setup_repository()
        gate, decision = self.run_step(repo, step_id="gate")
        self.assertEqual(0, gate.returncode, gate.stdout + gate.stderr)
        self.assertEqual("true", decision["cache_only"])

        replay, result = self.run_step(repo, step_id="rebase")
        self.assertEqual(0, replay.returncode, replay.stdout + replay.stderr)
        self.assertEqual({"conflict": "false"}, result)
        guard, _ = self.run_step(repo, name="Verify rebased workflow content")
        self.assertNotEqual(0, guard.returncode, guard.stdout + guard.stderr)
        self.assertIn("build-WebAPI.yml", (repo / ".git/sync-failure.txt").read_text())

    def test_other_workflow_changes_open_the_existing_review_issue(self):
        cases = (
            {"incoming": EXPLICIT.replace("push: false", "push: true")},
            {"incoming": EXPLICIT.replace("build-push-action@v7", "build-push-action@v8")},
            {"extra_workflow": True},
            {"executable": True},
            {
                "mirror": CONTAINER.replace("          push: false", "          load: true\n          push: false"),
                "incoming": EXPLICIT.replace("          push: false", "          load: true\n          push: false"),
            },
            {
                "mirror": CONTAINER.replace("  container:", "  other:"),
                "incoming": EXPLICIT.replace("  container:", "  other:"),
            },
        )
        for case in cases:
            with self.subTest(case=case):
                repo = self.setup_repository(**case)
                result, values = self.run_step(repo, step_id="gate")
                self.assertEqual(1, result.returncode, result.stdout + result.stderr)
                self.assertEqual({"review": "true"}, values)
                self.assertIn("issue create", (repo / ".git/gh.log").read_text())

    def test_code_changes_still_follow_the_ordinary_sync_path(self):
        repo = self.setup_repository(incoming=CONTAINER)
        gate, values = self.run_step(repo, step_id="gate")
        self.assertEqual(0, gate.returncode, gate.stdout + gate.stderr)
        self.assertEqual({"review": "false"}, values)
        self.assertFalse((repo / ".git/gh.log").exists())
