"""Exercise the DEB and RPM drivers without installing build dependencies."""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PACKAGERS = ("package-debian.sh", "package-rhel.sh")

DRIVER = r"""
detect_environment() { HOST_ARCH=x86_64; }
install_dependencies() { :; }
prepare_workspace() { PROJECT="$PWD/fixture.csproj"; }
resolve_version() { :; }
prepare_cross_rpm_tools() { :; }
prepare_dotnet_sdk() { :; }
print_summary() { :; }

download_nuget_packages() {
    NUGET_CACHE_DIR="$PWD/prebuilt"
    mkdir "$NUGET_CACHE_DIR"
    printf '%s\n' 'download prebuilt feed'
}
dotnet() { printf 'dotnet %s\n' "$*"; }
package_binary() { printf 'package %s\n' "$2"; }

main --arch "$1"
"""


class LinuxPackagingTests(unittest.TestCase):
    def run_driver(self, script, arch):
        source, entry_point = (ROOT / script).read_text(encoding="utf-8").rstrip().rsplit("\n", 1)
        self.assertEqual('main "$@"', entry_point)
        with tempfile.TemporaryDirectory() as workdir:
            run = subprocess.run(
                ["bash", "-s", "--", arch],
                cwd=workdir,
                input=source + "\n" + DRIVER,
                text=True,
                capture_output=True,
                timeout=15,
            )
        self.assertEqual(0, run.returncode, run.stdout + run.stderr)
        return run.stdout.splitlines()

    def test_all_targets_use_the_fork_release_architectures_and_standard_restore(self):
        for script in PACKAGERS:
            with self.subTest(script=script):
                lines = self.run_driver(script, "all")
                self.assertEqual(
                    ["package linux-x64", "package linux-arm64"],
                    [line for line in lines if line.startswith("package ")],
                )
                self.assertNotIn("download prebuilt feed", lines)
                publishes = [line for line in lines if line.startswith("dotnet publish ")]
                self.assertEqual(2, len(publishes))
                self.assertTrue(all(" --source " not in line and " --no-restore" not in line for line in publishes))

    def test_explicit_riscv_target_uses_the_prebuilt_feed(self):
        for script in PACKAGERS:
            with self.subTest(script=script):
                lines = self.run_driver(script, "riscv64")
                self.assertEqual(
                    ["package linux-riscv64"],
                    [line for line in lines if line.startswith("package ")],
                )
                self.assertEqual(1, lines.count("download prebuilt feed"))
                restores = [line for line in lines if line.startswith("dotnet restore ")]
                self.assertEqual(1, len(restores))
                self.assertIn("/prebuilt", restores[0])


if __name__ == "__main__":
    unittest.main()
