"""Check the fork's SQLite override using evaluated MSBuild items."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REPOBOT = "Repobot.SQLite.Unofficial"
SOURCEGEAR = "SourceGear.sqlite3"


@unittest.skipUnless(shutil.which("dotnet"), "the pinned .NET SDK is required")
class LegacySqliteProviderTests(unittest.TestCase):
    def evaluate(self, project_name, *references):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            shutil.copyfile(ROOT / "v2rayN/Directory.Build.targets", directory / "Directory.Build.targets")
            (directory / "Directory.Packages.props").write_text(
                f"""<Project>
  <PropertyGroup><ManagePackageVersionsCentrally>true</ManagePackageVersionsCentrally></PropertyGroup>
  <ItemGroup>
    <PackageVersion Include="{REPOBOT}" Version="9.0.0" />
    <PackageVersion Include="{SOURCEGEAR}" Version="9.0.1" />
  </ItemGroup>
</Project>""",
                encoding="utf-8",
            )
            items = "".join(f'<PackageReference Include="{name}" />' for name in references)
            project = directory / f"{project_name}.csproj"
            project.write_text(
                '<Project Sdk="Microsoft.NET.Sdk">'
                '<PropertyGroup><TargetFramework>net10.0</TargetFramework></PropertyGroup>'
                f"<ItemGroup>{items}</ItemGroup></Project>",
                encoding="utf-8",
            )
            run = subprocess.run(
                ["dotnet", "msbuild", str(project), "-nologo", "-getItem:PackageReference,PackageVersion"],
                cwd=ROOT,
                text=True,
                encoding="utf-8",
                capture_output=True,
                timeout=45,
            )
        self.assertEqual(0, run.returncode, run.stdout + run.stderr)
        evaluated = json.loads(run.stdout)["Items"]
        return [item["Identity"] for item in evaluated["PackageReference"]], evaluated["PackageVersion"]

    def test_replaces_the_upstream_provider_and_pins_a_single_version(self):
        for references in ((REPOBOT,), (REPOBOT, SOURCEGEAR)):
            with self.subTest(references=references):
                packages, versions = self.evaluate("ServiceLib", *references)
                self.assertEqual([SOURCEGEAR], packages)
                self.assertEqual(
                    ["3.53.4"],
                    [item["Version"] for item in versions if item["Identity"] == SOURCEGEAR],
                )

    def test_leaves_other_projects_and_other_provider_choices_alone(self):
        for project, provider, version in (("Other", REPOBOT, "9.0.0"), ("ServiceLib", SOURCEGEAR, "9.0.1")):
            with self.subTest(project=project, provider=provider):
                packages, versions = self.evaluate(project, provider)
                self.assertEqual([provider], packages)
                self.assertEqual([version], [item["Version"] for item in versions if item["Identity"] == provider])


if __name__ == "__main__":
    unittest.main()
