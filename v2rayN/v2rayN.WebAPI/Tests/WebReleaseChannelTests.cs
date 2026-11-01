using System.Reflection;
using v2rayN.WebAPI.Services;

namespace v2rayN.WebAPI.Tests;

public class WebReleaseChannelTests
{
    [Test]
    public async Task CanonicalThreeAndFourPartReleaseTagsAreAcceptedAndOtherIdentitiesAreIgnored()
    {
        foreach (var tag in new[] { "0.0.0", "7.25.3", "0.0.0.0", "7.25.3.1", "7.25.3.10" })
        {
            var accepted = WebReleaseChannel.TryParseReleaseTag(tag, out var version);
            await accepted.Should().BeTrue();
            await version.Should().BeEqualTo(tag);
        }

        foreach (var legacy in new[]
        {
            "web-v7.25.3-web.1", "7.25.3-web.1", "7.25.3-dev", "7.25.3.1-dev", "v7.25.3", "v7.25.3.1",
            "7.25", "7.25.3.1.1", "07.25.3", "7.025.3", "7.25.03", "7.25.3.01", "", null,
        })
        {
            var parsed = WebReleaseChannel.TryParseReleaseTag(legacy, out var parsedVersion);
            await parsed.Should().BeFalse();
            await parsedVersion.Should().BeEqualTo(string.Empty);
        }
    }

    [Test]
    public async Task ReleaseIndexUrlIsBuiltFromTheBuildRepository()
    {
        await WebReleaseChannel.BuildReleaseIndexUrl(WebReleaseChannel.DefaultRepository)
            .Should().BeEqualTo("https://api.github.com/repos/aleksandr-miheichev/v2rayN-oldos/releases?per_page=100");
        await WebBuildIdentity.Current.Repository.Should().BeEqualTo("aleksandr-miheichev/v2rayN-oldos");
        await typeof(WebReleaseChannel).Assembly.GetCustomAttributes<AssemblyMetadataAttribute>()
            .Single(attribute => attribute.Key == "WebRepository").Value.Should().BeEqualTo("aleksandr-miheichev/v2rayN-oldos");
        await WebReleaseChannel.BuildReleaseIndexUrl("2dust/v2rayN")
            .Should().BeEqualTo("https://api.github.com/repos/2dust/v2rayN/releases?per_page=100");

        var rejected = false;
        try { _ = WebReleaseChannel.BuildReleaseIndexUrl("2dust/v2rayN/../../evil"); }
        catch (ArgumentException) { rejected = true; }
        await rejected.Should().BeTrue();
        await WebReleaseChannel.IsValidRepository("community-fork/v2rayN").Should().BeTrue();
        await WebReleaseChannel.IsValidRepository("not-a-repository").Should().BeFalse();
    }

    [Test]
    public async Task AssemblyVersionsTrackTheWebBuildIdentityWithoutDevelopmentSuffixes()
    {
        var assembly = typeof(WebReleaseChannel).Assembly;
        var buildVersion = assembly.GetCustomAttributes<AssemblyMetadataAttribute>()
            .Single(attribute => attribute.Key == "WebVersion").Value!;
        var numeric = Version.Parse(buildVersion.Split('-', 2)[0]);
        var expected = new Version(numeric.Major, numeric.Minor, numeric.Build, Math.Max(numeric.Revision, 0));

        await assembly.GetName().Version.Should().BeEqualTo(expected);
        await assembly.GetCustomAttribute<AssemblyFileVersionAttribute>()!.Version.Should().BeEqualTo(expected.ToString());
        await assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()!.InformationalVersion.Split('+', 2)[0]
            .Should().BeEqualTo(buildVersion);
    }

    [Test]
    public async Task TrustedAssetUrlsMustUseTheBuildRepositoryTagAndAsset()
    {
        var repository = "aleksandr-miheichev/v2rayN-oldos";
        var tag = "7.25.3.2";
        var asset = "v2rayN-linux-64-WebAPI-update.zip";
        var trusted = $"https://github.com/{repository}/releases/download/{tag}/{asset}";

        await WebReleaseChannel.IsTrustedAssetUrl(trusted, repository, tag, asset).Should().BeTrue();
        // A build must not accept the same asset from another repository.
        await WebReleaseChannel.IsTrustedAssetUrl(trusted.Replace(repository, "another-owner/v2rayN", StringComparison.Ordinal),
            repository, tag, asset).Should().BeFalse();
        await WebReleaseChannel.IsTrustedAssetUrl("http://github.com/2dust/v2rayN/releases/download/7.25.3/" + asset,
            repository, tag, asset).Should().BeFalse();
        await WebReleaseChannel.IsTrustedAssetUrl("https://example.com/2dust/v2rayN/releases/download/7.25.3/" + asset,
            repository, tag, asset).Should().BeFalse();
        await WebReleaseChannel.IsTrustedAssetUrl(trusted, repository, "7.25.4", asset).Should().BeFalse();
        await WebReleaseChannel.IsTrustedAssetUrl(trusted, repository, tag, "WebAPI-update.json").Should().BeFalse();
        await WebReleaseChannel.IsTrustedAssetUrl("https://github.com/2dust/v2rayN/releases/download/7.25.3/sub/" + asset,
            repository, tag, asset).Should().BeFalse();
        await WebReleaseChannel.IsTrustedAssetUrl(null, repository, tag, asset).Should().BeFalse();
    }

    [Test]
    public async Task RuntimeIdentifiersMapToSupportedArchiveNames()
    {
        await WebUpdatePackageStager.ArtifactArch("linux-x64").Should().BeEqualTo("64");
        await WebUpdatePackageStager.ArtifactArch("linux-arm64").Should().BeEqualTo("arm64");
        await WebUpdatePackageStager.FullInstallAssetName("linux-x64").Should().BeEqualTo("v2rayN-linux-64-WebAPI.zip");
        await WebUpdatePackageStager.FullInstallAssetName("linux-arm64").Should().BeEqualTo("v2rayN-linux-arm64-WebAPI.zip");
        await WebUpdatePackageStager.AppOnlyAssetName("linux-x64").Should().BeEqualTo("v2rayN-linux-64-WebAPI-update.zip");
        await WebUpdatePackageStager.AppOnlyAssetName("linux-arm64").Should().BeEqualTo("v2rayN-linux-arm64-WebAPI-update.zip");
        await WebUpdatePackageStager.ArtifactArch("win-x64").Should().BeEqualTo("64");
        await WebUpdatePackageStager.FullInstallAssetName("win-x64").Should().BeEqualTo("v2rayN-windows-64-WebAPI.zip");
        await WebUpdatePackageStager.AppOnlyAssetName("win-x64").Should().BeEqualTo("v2rayN-windows-64-WebAPI-update.zip");
        await WebUpdatePackageStager.ArtifactArch("linux-riscv64").Should().BeNull();
        await WebUpdatePackageStager.FullInstallAssetName("linux-riscv64").Should().BeNull();
        await WebUpdatePackageStager.AppOnlyAssetName("linux-riscv64").Should().BeNull();
        await WebUpdatePackageStager.ArtifactArch("linux-loongarch64").Should().BeNull();
        await WebUpdatePackageStager.FullInstallAssetName("linux-loongarch64").Should().BeNull();
        await WebUpdatePackageStager.AppOnlyAssetName("linux-loongarch64").Should().BeNull();
        await WebUpdatePackageStager.ArtifactArch("win-arm64").Should().BeEqualTo("arm64");
        await WebUpdatePackageStager.FullInstallAssetName("win-arm64").Should().BeEqualTo("v2rayN-windows-arm64-WebAPI.zip");
        await WebUpdatePackageStager.AppOnlyAssetName("win-arm64").Should().BeEqualTo("v2rayN-windows-arm64-WebAPI-update.zip");
        await WebUpdatePackageStager.IsSupportedRid("linux-riscv64").Should().BeTrue();
        await WebUpdatePackageStager.IsSupportedRid("linux-loongarch64").Should().BeTrue();
        await WebUpdatePackageStager.IsSupportedRid("win-arm64").Should().BeTrue();
        await WebUpdatePackageStager.IsSupportedRid("linux-unknown64").Should().BeFalse();
        await WebUpdatePackageStager.FullInstallAssetName("linux-unknown64").Should().BeNull();
        await WebUpdatePackageStager.AppOnlyAssetName(null).Should().BeNull();
    }

    [Test]
    public async Task FourPartReleaseUpdatesRequireANewerRevision()
    {
        await WebUpdatePackageStager.IsUpdateAvailable("7.25.3.1", "7.25.3.2", allowPrerelease: false).Should().BeTrue();
        await WebUpdatePackageStager.IsUpdateAvailable("7.25.3.9", "7.25.3.10", allowPrerelease: false).Should().BeTrue();
        await WebUpdatePackageStager.IsUpdateAvailable("7.25.3.2", "7.25.3.1", allowPrerelease: true).Should().BeFalse();
        await WebUpdatePackageStager.IsUpdateAvailable("7.25.3.2", "7.25.3.2", allowPrerelease: false).Should().BeFalse();
        await WebUpdatePackageStager.IsUpdateAvailable("7.25.3.2", "7.25.3.2", allowPrerelease: true).Should().BeFalse();
        await WebUpdatePackageStager.IsUpdateAvailable("7.25.3.2-dev.1", "7.25.3.2", allowPrerelease: false).Should().BeTrue();
    }

    [Test]
    public async Task OfficialVersionsCompareGreaterThanDevAndLegacyIdentities()
    {
        await WebUpdatePackageStager.IsUpdateAvailable("7.25.2", "7.25.3", allowPrerelease: false).Should().BeTrue();
        await WebUpdatePackageStager.IsUpdateAvailable("7.25.3", "7.25.3", allowPrerelease: false).Should().BeFalse();
        await WebUpdatePackageStager.IsUpdateAvailable("7.25.3", "7.25.2", allowPrerelease: false).Should().BeFalse();
        await WebUpdatePackageStager.IsUpdateAvailable("0.0.0-dev", "7.25.3", allowPrerelease: false).Should().BeTrue();
        await WebUpdatePackageStager.IsUpdateAvailable("7.25.2-web.9", "7.25.3", allowPrerelease: false).Should().BeTrue();
    }
}
