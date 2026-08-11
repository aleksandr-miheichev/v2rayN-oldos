using AwesomeAssertions;
using Xunit;

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
    [Fact]
    public void RemoteRevisionNewerThanLocal_ShouldBeTreatedAsUpdate()
    {
        var current = new SemanticVersion("7.24.6");
        var remote = new SemanticVersion("7.24.6.1");

        // This is the exact check performed by UpdateService.ParseDownloadUrl.
        (current >= remote).Should().BeFalse();
        (remote >= current).Should().BeTrue();
    }

    [Fact]
    public void HigherRevision_ShouldBeGreaterThanLowerRevision()
    {
        var older = new SemanticVersion("7.24.6.1");
        var newer = new SemanticVersion("7.24.6.2");

        (newer >= older).Should().BeTrue();
        (older >= newer).Should().BeFalse();
        (older <= newer).Should().BeTrue();
    }

    [Fact]
    public void PatchComponent_ShouldStillOutrankRevision()
    {
        var older = new SemanticVersion("7.24.6.9");
        var newer = new SemanticVersion("7.24.7");

        (newer >= older).Should().BeTrue();
        (older >= newer).Should().BeFalse();
    }

    [Fact]
    public void MissingRevision_ShouldEqualExplicitZero()
    {
        new SemanticVersion("7.24.6").Should().Be(new SemanticVersion("7.24.6.0"));
        new SemanticVersion("7.24.6").Should().NotBe(new SemanticVersion("7.24.6.1"));
    }

    [Fact]
    public void VersionPrefixAndTwoComponentForm_ShouldStillParse()
    {
        new SemanticVersion("v7.24.6.1").Should().Be(new SemanticVersion("7.24.6.1"));
        new SemanticVersion("7.24").Should().Be(new SemanticVersion(7, 24, 0));
    }

    [Fact]
    public void UnparsableVersion_ShouldFallBackToZero()
    {
        new SemanticVersion("7.24.6-oldos.1").Should().Be(new SemanticVersion(0, 0, 0));
    }
}
