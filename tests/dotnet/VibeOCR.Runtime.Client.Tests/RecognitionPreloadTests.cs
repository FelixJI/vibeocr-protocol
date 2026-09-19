// Fail-closed plan tests for the explicit recognition-mode preload entry
// (ocr.recognition-modes.v1), mirroring
// tests/contracts/v2/test_recognition_preload.py.
using System.Text.Json;
using VibeOCR.Contracts.HttpV2;
using VibeOCR.Runtime.Client;
using Xunit;

namespace VibeOCR.Runtime.Client.Tests;

public sealed class RecognitionPreloadTests
{
    private static readonly string[] Capabilities =
    [
        "ocr.recognition.v2",
        "ocr.recognition-modes.v1",
    ];

    private static JsonElement Catalog(bool mineruSupportsPreload = true) =>
        JsonDocument.Parse($$$"""
            {
              "modes": [
                {"id": "paddle_text", "family": "text", "pipeline_id": "OCR",
                 "engine": "paddleocr", "provisioning": "advanced_component",
                 "availability": "preparation_required", "reason_code": null,
                 "required_component": "paddleocr-cpu", "supported_options": [],
                 "lifecycle": {"kind": "model_residency", "supports_preload": true,
                  "supports_ttl": true, "supports_pinning": true,
                  "supports_release": true}},
                {"id": "paddle_table", "family": "specialized",
                 "pipeline_id": "TABLE_RECOGNITION", "engine": null,
                 "provisioning": "advanced_component",
                 "availability": "preparation_required",
                 "reason_code": "runtime_component_missing",
                 "required_component": "paddleocr-cpu", "supported_options": [],
                 "lifecycle": {"kind": "model_residency", "supports_preload": true,
                  "supports_ttl": true, "supports_pinning": true,
                  "supports_release": true}},
                {"id": "mineru_document", "family": "document",
                 "pipeline_id": "MinerU", "engine": null,
                 "provisioning": "advanced_component",
                 "availability": "preparation_required",
                 "reason_code": "runtime_component_missing",
                 "required_component": "mineru-cpu", "supported_options": [],
                 "lifecycle": {"kind": "process_keep_alive",
                  "supports_preload": {{{mineruSupportsPreload.ToString().ToLowerInvariant()}}},
                  "supports_ttl": true, "supports_pinning": false,
                  "supports_release": true}}
              ]
            }
            """).RootElement.Clone();

    [Fact]
    public void BuildProjectsMineruPreloadToTheFrozenRequestShape()
    {
        RecognitionPreloadPlan plan = RecognitionPreload.Build(
            ["mineru_document"], Capabilities, Catalog());

        Assert.Equal(["MinerU"], plan.Pipelines);
        Assert.Equal(["mineru_document"], plan.RecognitionModes);
    }

    [Fact]
    public void BuildDeduplicatesModesAndPipelinesInRequestOrder()
    {
        RecognitionPreloadPlan plan = RecognitionPreload.Build(
            ["paddle_table", "mineru_document", "paddle_text", "paddle_table"],
            Capabilities,
            Catalog());

        Assert.Equal(
            ["TABLE_RECOGNITION", "MinerU", "OCR"],
            plan.Pipelines);
        Assert.Equal(
            ["paddle_table", "mineru_document", "paddle_text"],
            plan.RecognitionModes);
    }

    [Fact]
    public void MissingCapabilityOrCatalogFailsClosedWithLifecycleUnsupported()
    {
        var exception = Assert.Throws<RecognitionPreloadException>(
            () => RecognitionPreload.Build(
                ["mineru_document"], ["ocr.recognition.v2"], Catalog()));
        Assert.Equal(
            HttpV2ErrorCode.RecognitionModeLifecycleUnsupported,
            exception.Code);

        exception = Assert.Throws<RecognitionPreloadException>(
            () => RecognitionPreload.Build(["mineru_document"], null, Catalog()));
        Assert.Equal(
            HttpV2ErrorCode.RecognitionModeLifecycleUnsupported,
            exception.Code);

        exception = Assert.Throws<RecognitionPreloadException>(
            () => RecognitionPreload.Build(
                ["mineru_document"], Capabilities, null));
        Assert.Equal(
            HttpV2ErrorCode.RecognitionModeLifecycleUnsupported,
            exception.Code);
    }

    [Fact]
    public void OldRuntimeDeclarationKeepsExplicitRejection()
    {
        // A pre-2.8.1 runtime declares mineru_document without preload
        // support; the guard rejects on that runtime's own declaration
        // instead of letting this package's new constants speak for it.
        var exception = Assert.Throws<RecognitionPreloadException>(
            () => RecognitionPreload.Build(
                ["mineru_document"], Capabilities, Catalog(false)));
        Assert.Equal(
            HttpV2ErrorCode.RecognitionModeLifecycleUnsupported,
            exception.Code);
    }

    [Fact]
    public void UnknownAndUnlistedModesFailClosed()
    {
        var exception = Assert.Throws<RecognitionPreloadException>(
            () => RecognitionPreload.Build(
                ["turbo_text"], Capabilities, Catalog()));
        Assert.Equal(HttpV2ErrorCode.RecognitionModeUnknown, exception.Code);

        JsonElement withoutMineru = JsonDocument.Parse("""
            {"modes": [{"id": "paddle_text",
              "lifecycle": {"kind": "model_residency",
               "supports_preload": true, "supports_ttl": true,
               "supports_pinning": true, "supports_release": true}}]}
            """).RootElement;
        exception = Assert.Throws<RecognitionPreloadException>(
            () => RecognitionPreload.Build(
                ["mineru_document"], Capabilities, withoutMineru));
        Assert.Equal(
            HttpV2ErrorCode.RecognitionModeLifecycleUnsupported,
            exception.Code);

        exception = Assert.Throws<RecognitionPreloadException>(
            () => RecognitionPreload.Build([], Capabilities, Catalog()));
        Assert.Equal(HttpV2ErrorCode.ValidationError, exception.Code);
    }

    [Theory]
    [InlineData("""{"modes": []}""")]
    [InlineData("""{}""")]
    [InlineData("""{"modes": [{"id": "mineru_document"}]}""")]
    [InlineData("""{"modes": [{"lifecycle": {"supports_preload": true}}]}""")]
    [InlineData("""{"modes": [{"id": "mineru_document", "lifecycle": {"kind": "process_keep_alive"}}]}""")]
    [InlineData("""{"modes": [{"id": "mineru_document", "lifecycle": {"kind": "process_keep_alive", "supports_preload": "yes"}}]}""")]
    [InlineData("""{"modes": [{"id": "mineru_document", "lifecycle": {"kind": "process_keep_alive", "supports_preload": true}}, {"id": "mineru_document", "lifecycle": {"kind": "process_keep_alive", "supports_preload": true}}]}""")]
    public void MalformedCatalogsFailClosedWithLifecycleUnsupported(string json)
    {
        var exception = Assert.Throws<RecognitionPreloadException>(
            () => RecognitionPreload.Build(
                ["mineru_document"],
                Capabilities,
                JsonDocument.Parse(json).RootElement));
        Assert.Equal(
            HttpV2ErrorCode.RecognitionModeLifecycleUnsupported,
            exception.Code);
    }

    [Fact]
    public void FutureOptionalResponseFieldsStayCompatible()
    {
        JsonElement catalog = JsonDocument.Parse("""
            {"future_hint": {"value": 1}, "modes": [
              {"id": "mineru_document", "future_hint": ["supported"],
               "lifecycle": {"kind": "process_keep_alive",
                "supports_preload": true, "supports_ttl": true,
                "supports_pinning": false, "supports_release": true,
                "future_hint": 7}}]}
            """).RootElement;
        RecognitionPreloadPlan plan = RecognitionPreload.Build(
            ["mineru_document"],
            Capabilities.Append("future.feature.v3"),
            catalog);
        Assert.Equal(["MinerU"], plan.Pipelines);
    }

    [Fact]
    public void PreparationRejectsBeforeAndBuildsAfterRefreshedCatalog()
    {
        // The typed MinerU helper keeps rejecting a preparation-required
        // tier; after the caller preloads and re-reads the refreshed tier
        // catalog, the same typed request constructs.
        JsonElement before = MineruTierCatalog("preparation_required");
        var configException = Assert.Throws<MineruConfigException>(
            () => MineruConfigSelection.Build(
                new MineruConfig { Tier = MineruTier.Standard },
                Capabilities.Append("ocr.mineru-config.v1"),
                before));
        Assert.Equal(
            HttpV2ErrorCode.MineruTierPreparationRequired,
            configException.Code);

        RecognitionPreloadPlan plan = RecognitionPreload.Build(
            ["mineru_document"], Capabilities, Catalog());
        Assert.Equal(["mineru_document"], plan.RecognitionModes);

        PipelineSelection selection = MineruConfigSelection.Build(
            new MineruConfig { Tier = MineruTier.Standard },
            Capabilities.Append("ocr.mineru-config.v1"),
            MineruTierCatalog("ready"));
        Assert.Equal(MineruTier.Standard, selection.Mineru!.Tier);
    }

    private static JsonElement MineruTierCatalog(string standardAvailability) =>
        JsonDocument.Parse($$"""
            {
              "default_tier": "basic",
              "tiers": [
                {"id": "flash", "availability": "ready", "reason_code": null},
                {"id": "basic", "availability": "ready", "reason_code": null},
                {"id": "standard", "availability": "{{standardAvailability}}",
                 "reason_code": null},
                {"id": "advanced", "availability": "unavailable",
                 "reason_code": "MINERU_TIER_UNAVAILABLE"}
              ],
              "languages": ["ch", "en"]
            }
            """).RootElement.Clone();
}
