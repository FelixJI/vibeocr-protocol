// Fail-closed construction tests for the typed MinerU 4 configuration entry
// (ocr.mineru-config.v1), mirroring tests/contracts/v2/test_mineru_config.py.
using System.Text.Json;
using System.Text.Json.Nodes;
using VibeOCR.Contracts.HttpV2;
using VibeOCR.Runtime.Client;
using Xunit;

namespace VibeOCR.Runtime.Client.Tests;

public sealed class MineruConfigSelectionTests
{
    private static readonly string[] Capabilities =
    [
        "ocr.recognition.v2",
        "ocr.mineru-config.v1",
    ];

    private static JsonElement Catalog() => JsonDocument.Parse("""
        {
          "default_tier": "basic",
          "tiers": [
            {"id": "flash", "availability": "ready", "reason_code": null},
            {"id": "basic", "availability": "ready", "reason_code": null},
            {"id": "standard", "availability": "preparation_required",
             "reason_code": "MINERU_TIER_PREPARATION_REQUIRED"},
            {"id": "advanced", "availability": "unavailable",
             "reason_code": "MINERU_TIER_UNAVAILABLE"}
          ],
          "languages": ["ch", "en"]
        }
        """).RootElement.Clone();

    [Fact]
    public void BuildReturnsMineruSelectionFromCapabilityAndCatalog()
    {
        var selection = MineruConfigSelection.Build(
            new MineruConfig { Tier = MineruTier.Basic },
            Capabilities,
            Catalog());

        Assert.Equal("MinerU", selection.PipelineId);
        Assert.Equal(1, selection.OptionsVersion);
        Assert.Empty(selection.Options);
        Assert.Null(selection.Engine);
        Assert.Equal(MineruTier.Basic, selection.Mineru!.Tier);
        Assert.Equal(MineruOcrMode.Auto, selection.Mineru.OcrMode);
        Assert.Equal("all", selection.Mineru.PageRange);
        Assert.Equal("ch", selection.Mineru.Language);

        string json = HttpV2Json.Serialize(selection, typeof(PipelineSelection));
        Assert.Contains("\"tier\":\"basic\"", json);
        Assert.Contains("\"ocr_mode\":\"auto\"", json);
        Assert.Contains("\"page_range\":\"all\"", json);
        Assert.Contains("\"language\":\"ch\"", json);
    }

    [Fact]
    public void MissingCapabilityOrCatalogFailsClosedWithConfigUnavailable()
    {
        var config = new MineruConfig { Tier = MineruTier.Basic };
        var exception = Assert.Throws<MineruConfigException>(
            () => MineruConfigSelection.Build(
                config, ["ocr.recognition.v2"], Catalog()));
        Assert.Equal(HttpV2ErrorCode.MineruConfigUnavailable, exception.Code);

        exception = Assert.Throws<MineruConfigException>(
            () => MineruConfigSelection.Build(config, null, Catalog()));
        Assert.Equal(HttpV2ErrorCode.MineruConfigUnavailable, exception.Code);

        exception = Assert.Throws<MineruConfigException>(
            () => MineruConfigSelection.Build(config, Capabilities, null));
        Assert.Equal(HttpV2ErrorCode.MineruConfigUnavailable, exception.Code);

        exception = Assert.Throws<MineruConfigException>(
            () => MineruConfigSelection.Build(
                config, Capabilities, JsonDocument.Parse("\"x\"").RootElement));
        Assert.Equal(HttpV2ErrorCode.MineruConfigUnavailable, exception.Code);
    }

    [Theory]
    [InlineData("""{"default_tier": "basic", "languages": ["ch"]}""")]
    [InlineData("""{"tiers": [], "default_tier": "basic", "languages": ["ch"]}""")]
    [InlineData("""{"default_tier": "ultra", "tiers": [{"id": "basic", "availability": "ready", "reason_code": null}], "languages": ["ch"]}""")]
    [InlineData("""{"default_tier": "basic", "tiers": [{"id": "ultra", "availability": "ready", "reason_code": null}], "languages": ["ch"]}""")]
    [InlineData("""{"default_tier": "standard", "tiers": [{"id": "basic", "availability": "ready", "reason_code": null}], "languages": ["ch"]}""")]
    [InlineData("""{"default_tier": "basic", "tiers": [{"id": "basic", "availability": "ready", "reason_code": null}, {"id": "basic", "availability": "ready", "reason_code": null}], "languages": ["ch"]}""")]
    [InlineData("""{"default_tier": "basic", "tiers": [{"id": "basic", "availability": "partial", "reason_code": null}], "languages": ["ch"]}""")]
    [InlineData("""{"default_tier": "basic", "tiers": [{"id": "basic", "availability": "ready", "reason_code": ""}], "languages": ["ch"]}""")]
    [InlineData("""{"default_tier": "basic", "tiers": [{"id": "basic", "availability": "ready"}], "languages": ["ch"]}""")]
    [InlineData("""{"default_tier": "basic", "tiers": [{"id": "basic", "availability": "ready", "reason_code": null}], "languages": []}""")]
    [InlineData("""{"default_tier": "basic", "tiers": [{"id": "basic", "availability": "ready", "reason_code": null}], "languages": ["ch", "ch"]}""")]
    public void MalformedCatalogsFailClosedWithConfigUnavailable(string json)
    {
        var exception = Assert.Throws<MineruConfigException>(
            () => MineruConfigSelection.Build(
                new MineruConfig { Tier = MineruTier.Basic },
                Capabilities,
                JsonDocument.Parse(json).RootElement));
        Assert.Equal(HttpV2ErrorCode.MineruConfigUnavailable, exception.Code);
    }

    [Fact]
    public void TierAvailabilityMapsToStableErrorCodes()
    {
        var exception = Assert.Throws<MineruConfigException>(
            () => MineruConfigSelection.Build(
                new MineruConfig { Tier = MineruTier.Advanced },
                Capabilities,
                Catalog()));
        Assert.Equal(HttpV2ErrorCode.MineruTierUnavailable, exception.Code);

        exception = Assert.Throws<MineruConfigException>(
            () => MineruConfigSelection.Build(
                new MineruConfig { Tier = MineruTier.Standard },
                Capabilities,
                Catalog()));
        Assert.Equal(HttpV2ErrorCode.MineruTierPreparationRequired, exception.Code);

        JsonElement catalog = Catalog();
        // Remove flash from tiers; requesting it now fails closed.
        var rewritten = JsonSerializer.SerializeToNode(catalog)!;
        var tiers = (JsonArray)rewritten["tiers"]!;
        foreach (JsonNode? node in tiers.ToList())
        {
            if (node!["id"]!.GetValue<string>() == "flash")
            {
                tiers.Remove(node);
            }
        }
        exception = Assert.Throws<MineruConfigException>(
            () => MineruConfigSelection.Build(
                new MineruConfig { Tier = MineruTier.Flash },
                Capabilities,
                JsonSerializer.SerializeToElement(rewritten)));
        Assert.Equal(HttpV2ErrorCode.MineruTierUnavailable, exception.Code);
    }

    [Fact]
    public void LanguageOutsideTheCatalogFailsClosedWithValidationError()
    {
        var exception = Assert.Throws<MineruConfigException>(
            () => MineruConfigSelection.Build(
                new MineruConfig { Tier = MineruTier.Basic, Language = "jp" },
                Capabilities,
                Catalog()));
        Assert.Equal(HttpV2ErrorCode.ValidationError, exception.Code);
    }

    [Theory]
    [InlineData("all\n")]
    [InlineData("0")]
    [InlineData("r0")]
    [InlineData("01")]
    [InlineData(" 1")]
    [InlineData("1, 2")]
    [InlineData("1,")]
    [InlineData("all,1")]
    [InlineData("1-")]
    [InlineData("")]
    public void InvalidPageRangesFailClosedBeforeAnyRequest(string pageRange)
    {
        var exception = Assert.Throws<MineruConfigException>(
            () => MineruConfigSelection.Build(
                new MineruConfig { Tier = MineruTier.Basic, PageRange = pageRange },
                Capabilities,
                Catalog()));
        Assert.Equal(HttpV2ErrorCode.ValidationError, exception.Code);
    }

    [Theory]
    [InlineData("all")]
    [InlineData("1")]
    [InlineData("r1")]
    [InlineData("1-5")]
    [InlineData("1-5,8")]
    [InlineData("r3-r1")]
    [InlineData("10-20,30,r5")]
    public void CanonicalPageRangesAreAccepted(string pageRange)
    {
        var selection = MineruConfigSelection.Build(
            new MineruConfig { Tier = MineruTier.Basic, PageRange = pageRange },
            Capabilities,
            Catalog());
        Assert.Equal(pageRange, selection.Mineru!.PageRange);
    }

    [Fact]
    public void InvalidLanguagesFailClosedWithValidationError()
    {
        var exception = Assert.Throws<MineruConfigException>(
            () => MineruConfigSelection.Build(
                new MineruConfig { Tier = MineruTier.Basic, Language = " ch" },
                Capabilities,
                Catalog()));
        Assert.Equal(HttpV2ErrorCode.ValidationError, exception.Code);

        exception = Assert.Throws<MineruConfigException>(
            () => MineruConfigSelection.Build(
                new MineruConfig { Tier = MineruTier.Basic, Language = "" },
                Capabilities,
                Catalog()));
        Assert.Equal(HttpV2ErrorCode.ValidationError, exception.Code);
    }

    [Fact]
    public void FutureOptionalResponseFieldsAreIgnored()
    {
        var catalog = JsonSerializer.SerializeToNode(Catalog())!;
        catalog["future_hint"] = 1;
        catalog["tiers"]![1]!["future_hint"] = "supported";
        var selection = MineruConfigSelection.Build(
            new MineruConfig { Tier = MineruTier.Basic }, Capabilities,
            JsonSerializer.SerializeToElement(catalog));
        Assert.Equal(MineruTier.Basic, selection.Mineru!.Tier);
    }

    [Theory]
    [InlineData("default_tier")]
    [InlineData("id")]
    [InlineData("availability")]
    public void WrongCatalogFieldTypesHaveStableErrors(string field)
    {
        var catalog = JsonSerializer.SerializeToNode(Catalog())!;
        if (field == "default_tier")
            catalog[field] = 1;
        else
            catalog["tiers"]![1]![field] = 1;
        var exception = Assert.Throws<MineruConfigException>(
            () => MineruConfigSelection.Build(
                new MineruConfig { Tier = MineruTier.Basic }, Capabilities,
                JsonSerializer.SerializeToElement(catalog)));
        Assert.Equal(HttpV2ErrorCode.MineruConfigUnavailable, exception.Code);
    }

    [Fact]
    public void InvalidOcrModeCannotProduceARequest()
    {
        var exception = Assert.Throws<MineruConfigException>(
            () => MineruConfigSelection.Build(
                new MineruConfig { Tier = MineruTier.Basic, OcrMode = (MineruOcrMode)999 },
                Capabilities, Catalog()));
        Assert.Equal(HttpV2ErrorCode.ValidationError, exception.Code);
    }

    [Fact]
    public void NullConfigIsRejected()
    {
        Assert.Throws<ArgumentNullException>(
            () => MineruConfigSelection.Build(null!, Capabilities, Catalog()));
    }
}
