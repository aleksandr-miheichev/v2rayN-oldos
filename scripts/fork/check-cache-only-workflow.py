"""Recognize the explicit cache-only default for the upstream WebAPI build."""

import re
import subprocess
import sys

WORKFLOW = ".github/workflows/build-WebAPI.yml"
# Match the setup action with its default docker-container driver and the exact
# inputs of the build without push, load, or another exporter.
BUILD_STEP = b"""      - uses: docker/setup-buildx-action@v4
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
"""
EXPLICIT_EXPORT = BUILD_STEP.replace(b"          push: false\n", b"          outputs: type=cacheonly\n          push: false\n")


def git(*args):
    return subprocess.check_output(("git", *args))


def is_cache_only_change(mirror, upstream):
    for ref in (mirror, upstream):
        if not git("ls-tree", ref, "--", WORKFLOW).startswith(b"100644 blob "):
            return False

    before = git("show", f"{mirror}:{WORKFLOW}")
    after = git("show", f"{upstream}:{WORKFLOW}")
    header = b"\njobs:\n"
    if before.count(header) != 1 or before.count(BUILD_STEP) != 1:
        return False

    jobs = re.split(rb"(?m)^\S", before.split(header, 1)[1], maxsplit=1)[0]
    container = re.split(rb"(?m)^  container:\n", jobs)
    if len(container) != 2:
        return False

    job = re.split(rb"(?m)^  \S", container[1], maxsplit=1)[0]
    return job.rstrip(b"\n").endswith(BUILD_STEP.rstrip(b"\n")) and after == before.replace(BUILD_STEP, EXPLICIT_EXPORT, 1)


if __name__ == "__main__":
    sys.exit(0 if is_cache_only_change(*sys.argv[1:]) else 1)
