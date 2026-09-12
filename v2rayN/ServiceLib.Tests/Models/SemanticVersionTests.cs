namespace ServiceLib.Tests.Models;

/// <summary>
/// Covers the four-component version comparison this fork relies on.
/// Fork releases are tagged "&lt;upstream version&gt;.&lt;fork build&gt;" (e.g. 7.24.6.3),
/// so the revision component must take part in the comparison. Without it
/// UpdateService.ParseDownloadUrl evaluates "current >= remote" as true and the
/// update is silently never offered.
/// </summary>
public class SemanticVersionTests
{
    [Test]
    public async Task RemoteRevisionNewerThanLocal_ShouldBeTreatedAsUpdate()
    {
        var current = new SemanticVersion("7.24.6");
        var remote = new SemanticVersion("7.24.6.1");

        // This is the exact check performed by UpdateService.ParseDownloadUrl.
        await (current >= remote).Should().BeFalse();
        await (remote >= current).Should().BeTrue();
    }

    [Test]
    public async Task HigherRevision_ShouldBeGreaterThanLowerRevision()
    {
        var older = new SemanticVersion("7.24.6.1");
        var newer = new SemanticVersion("7.24.6.2");

        await (newer >= older).Should().BeTrue();
        await (older >= newer).Should().BeFalse();
        await (older <= newer).Should().BeTrue();
    }

    [Test]
    public async Task PatchComponent_ShouldStillOutrankRevision()
    {
        var older = new SemanticVersion("7.24.6.9");
        var newer = new SemanticVersion("7.24.7");

        await (newer >= older).Should().BeTrue();
        await (older >= newer).Should().BeFalse();
    }

    [Test]
    public async Task MissingRevision_ShouldEqualExplicitZero()
    {
        await new SemanticVersion("7.24.6").Should().BeEqualTo(new SemanticVersion("7.24.6.0"));
        await new SemanticVersion("7.24.6").Should().NotBeEqualTo(new SemanticVersion("7.24.6.1"));
    }

    [Test]
    public async Task VersionPrefixAndTwoComponentForm_ShouldStillParse()
    {
        await new SemanticVersion("v7.24.6.1").Should().BeEqualTo(new SemanticVersion("7.24.6.1"));
        await new SemanticVersion("7.24").Should().BeEqualTo(new SemanticVersion(7, 24, 0));
    }

    [Test]
    public async Task UnparsableVersion_ShouldFallBackToZero()
    {
        // No dash in the input: a "-label" suffix parses as a pre-release and
        // survives the fallback, so it would not compare equal to 0.0.0.
        await new SemanticVersion("7.24.x").Should().BeEqualTo(new SemanticVersion(0, 0, 0));

        // The fallback does not reset the revision: it stays zero only because
        // the revision is parsed after every other component.
        await new SemanticVersion("7.24.x.5").Should().BeEqualTo(new SemanticVersion(0, 0, 0));
    }

    [Test]
    public async Task Revision_ShouldBeComparedBeforePrereleaseLabel()
    {
        var prerelease = new SemanticVersion("7.24.6.1-beta");

        await (prerelease > new SemanticVersion("7.24.6")).Should().BeTrue();
        await (prerelease < new SemanticVersion("7.24.6.1")).Should().BeTrue();
    }

    [Test]
    public async Task OwnVersion_ShouldKeepTheRevisionComponent()
    {
        // UpdateService.ParseDownloadUrl takes the running version from here. Cut
        // to three components, every fork build looks older than its own release
        // tag and the update it already runs is offered forever.
        var assemblyVersion = typeof(Utils).Assembly.GetName().Version!.ToString();

        await Utils.GetVersionInfo().Should().BeEqualTo(assemblyVersion);
    }
}
