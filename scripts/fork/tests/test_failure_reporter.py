"""Replay the watchdog's executable steps without contacting GitHub."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import unittest

from test_webapi_release import ShellFixture, workflow_step


FAKE_GH = r'''
gh() {
  local endpoint file filter='' title='' label='' body=''
  case "$1 $2" in
    'label create') return 0 ;;
    'issue list') cat "$FIXTURE_DIR/issues.json"; return ;;
    'issue create')
      shift 2
      while (($#)); do
        case "$1" in
          --title) title="$2"; shift 2 ;;
          --label) label="$2"; shift 2 ;;
          --body-file) body="$2"; shift 2 ;;
          *) echo "Unexpected issue argument: $1" >&2; return 99 ;;
        esac
      done
      jq -n --arg title "$title" --arg label "$label" --rawfile body "$body" \
        '{title: $title, label: $label, body: $body}' > "$FIXTURE_DIR/created.json"
      return ;;
    'run list') file="$FIXTURE_DIR/sweep.json"; shift 2 ;;
    api\ *)
      endpoint="$2"
      shift 2
      case "$endpoint" in
        repos/*/actions/runs/*/jobs\?*) file="$FIXTURE_DIR/jobs.json" ;;
        repos/*/actions/runs/*) file="$FIXTURE_DIR/run-${endpoint##*/}.json" ;;
        repos/*/check-runs/*/annotations*) file="$FIXTURE_DIR/annotations.json" ;;
        *) echo "Unexpected API endpoint: $endpoint" >&2; return 99 ;;
      esac ;;
    *) echo "Unexpected gh command: $*" >&2; return 99 ;;
  esac
  [[ -f "$file" ]] || return 1
  while (($#)); do
    case "$1" in
      --jq) filter="$2"; shift 2 ;;
      *) shift ;;
    esac
  done
  if [[ -n "$filter" ]]; then jq -r "$filter" "$file"; else cat "$file"; fi
}
'''


class FailureReporter(ShellFixture):
    def setUp(self) -> None:
        super().setUp()
        self.run_id = 41330972322
        self.run = {
            "name": "build v2rayN.WebAPI", "event": "push", "head_branch": "patches",
            "path": ".github/workflows/build-WebAPI.yml", "conclusion": "failure",
            "head_sha": "49c1458b9d24b1fccf9e0cd0007869002043f3f0",
            "html_url": f"https://github.com/example/fork/actions/runs/{self.run_id}",
            "run_started_at": "2026-11-01T17:00:00Z", "updated_at": "2026-11-01T17:10:00Z",
            "pull_requests": [],
        }
        self.jobs = {"jobs": [{
            "id": 100, "name": "Backend, ServiceLib, package smoke", "conclusion": "failure",
            "html_url": "https://github.com/example/fork/actions/runs/1/job/100",
            "steps": [{"name": "Check patch whitespace", "conclusion": "failure"}],
        }]}
        self.annotations = [{"annotation_level": "failure", "message": "Process completed with exit code 128."}]
        self.issues = []

    def write_json(self, name: str, value: object) -> None:
        (self.work / name).write_text(json.dumps(value), encoding="utf-8")

    def report(self, runs: str | None = None) -> dict | None:
        self.write_json(f"run-{self.run_id}.json", self.run)
        self.write_json("jobs.json", self.jobs)
        self.write_json("annotations.json", self.annotations)
        self.write_json("issues.json", self.issues)
        created = self.work / "created.json"
        created.unlink(missing_ok=True)
        result = self.shell(FAKE_GH + workflow_step(
            "report-failure.yml", "report", name="Open an issue for each failure"), {
                "FIXTURE_DIR": self.work.as_posix(), "GH_REPO": "example/fork",
                "RUNS": runs or str(self.run_id),
            })
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(created.read_text(encoding="utf-8")) if created.exists() else None

    def test_patch_push_failure_reports_ci_without_claiming_a_release(self) -> None:
        issue = self.report()
        self.assertEqual(issue["label"], "ci-check-failure")
        self.assertTrue(issue["title"].startswith("CI check failed:"))
        self.assertIn("Check patch whitespace", issue["body"])
        self.assertIn("exit code 128", issue["body"])
        self.assertIn("does not publish a release", issue["body"])
        self.assertNotIn("this release was not published", issue["body"])
        self.assertNotIn("gh workflow run", issue["body"])
        self.assertNotIn("once the release completes", issue["body"])

    def test_development_classification_uses_the_workflow_path(self) -> None:
        self.run["name"] = "Renamed API checks"
        self.assertEqual(self.report()["label"], "ci-check-failure")

    def test_release_wrapper_retains_its_release_report(self) -> None:
        self.run.update(name="release v2rayN.WebAPI", event="workflow_dispatch",
                        head_branch="7.25.6.42", path=".github/workflows/release-WebAPI.yml")
        issue = self.report()
        self.assertEqual(issue["label"], "release-failure")
        self.assertTrue(issue["title"].startswith("Release blocked:"))
        self.assertIn("once the release completes", issue["body"])

    def test_platform_release_retains_the_exact_rebuild_command(self) -> None:
        self.run.update(name="release Linux", event="workflow_dispatch",
                        head_branch="7.25.6.42", path=".github/workflows/build-linux.yml")
        issue = self.report()
        self.assertEqual(issue["label"], "release-failure")
        self.assertIn("gh workflow run build-linux.yml --repo example/fork --ref refs/tags/7.25.6.42", issue["body"])

    def test_pull_request_report_keeps_its_existing_route(self) -> None:
        self.run.update(event="pull_request", pull_requests=[{"number": 12}])
        issue = self.report()
        self.assertEqual(issue["label"], "pr-check-failure")
        self.assertTrue(issue["title"].startswith("PR check failed:"))
        self.assertIn("| Pull request | #12 |", issue["body"])

    def test_other_push_workflows_are_not_reclassified(self) -> None:
        self.run.update(name="auto release", path=".github/workflows/auto-release.yml")
        self.assertEqual(self.report()["label"], "release-failure")

    def test_missing_workflow_identity_is_still_reported(self) -> None:
        self.run.update(name=None, path=None)
        issue = self.report()
        self.assertEqual(issue["label"], "release-failure")
        self.assertIn("GitHub did not record which workflow", issue["body"])

    def test_open_and_closed_existing_reports_prevent_duplicates(self) -> None:
        for state in ("open", "closed"):
            with self.subTest(state=state):
                self.issues = [{"number": 40, "state": state,
                                "title": f"Release blocked: old title (run #{self.run_id})"}]
                self.assertIsNone(self.report())

    def test_an_unreadable_run_does_not_hide_the_next_failure(self) -> None:
        self.assertIsNotNone(self.report(f"999 {self.run_id}"))

    def test_manual_cancellation_is_not_reported(self) -> None:
        self.run["conclusion"] = "cancelled"
        self.jobs["jobs"][0]["conclusion"] = "cancelled"
        self.annotations = [{"message": "The run was canceled by @maintainer."}]
        self.assertIsNone(self.report())

    def test_timeout_cancellation_remains_a_ci_report(self) -> None:
        self.run["conclusion"] = "cancelled"
        self.jobs["jobs"][0]["conclusion"] = "cancelled"
        self.annotations = [{"message": "The job has exceeded the maximum execution time of 6h0m0s"}]
        issue = self.report()
        self.assertEqual(issue["label"], "ci-check-failure")
        self.assertIn("exceeded the maximum execution time", issue["body"])
        self.assertNotIn("this release was not published", issue["body"])

    def test_startup_failure_does_not_get_release_recovery_instructions(self) -> None:
        self.run["conclusion"] = "startup_failure"
        self.jobs = {"jobs": []}
        issue = self.report()
        self.assertEqual(issue["label"], "ci-check-failure")
        self.assertIn("GitHub could not start", issue["body"])
        self.assertNotIn("once the release completes", issue["body"])

    def test_collection_keeps_development_checks_and_excludes_mirror_pushes(self) -> None:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.write_json("sweep.json", [
            {"databaseId": self.run_id, "conclusion": "failure", "updatedAt": now,
             "name": self.run["name"], "headBranch": "patches", "event": "push"},
            {"databaseId": 999, "conclusion": "failure", "updatedAt": now,
             "name": "release Linux", "headBranch": "master", "event": "push"},
        ])
        for event in ("schedule", "workflow_run"):
            with self.subTest(event=event):
                output = self.work / "output"
                output.unlink(missing_ok=True)
                result = self.shell(FAKE_GH + workflow_step("report-failure.yml", "report", step_id="collect"), {
                    "FIXTURE_DIR": self.work.as_posix(), "GH_REPO": "example/fork",
                    "EVENT": event, "GITHUB_OUTPUT": output.as_posix(),
                    "TRIGGER_RUN": str(self.run_id), "TRIGGER_CONCLUSION": "failure",
                    "TRIGGER_EVENT": "push", "TRIGGER_BRANCH": "patches",
                })
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(output.read_text().strip(), f"runs={self.run_id}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
