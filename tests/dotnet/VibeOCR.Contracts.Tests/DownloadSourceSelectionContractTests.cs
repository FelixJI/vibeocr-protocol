// Cross-language contract tests for the runtime.download-sources.v1 extension.
//
// They prove the handwritten HttpV2 mirror and the generated Wire/Host
// bindings agree with the Python-side golden payloads in
// runtime_contracts/golden/golden.json (see
// tests/contracts/v2/test_download_source_selection.py).
using System.Text.Json;
using System.Text.Json.Nodes;
using VibeOCR.Contracts.HttpV2;
using Wire = VibeOCR.Runtime.Contracts.Generated.Wire;
using Xunit;
using Host = VibeOCR.Runtime.Contracts.Generated.Host;

namespace VibeOCR.Contracts.Tests;

public sealed class DownloadSourceSelectionContractTests
{
    private static readonly string V2Directory = FindV2Directory();

    [Fact]
    public void DownloadSourceCatalogGoldenRoundTripsThroughGeneratedWireBinding()
    {
        JsonElement fixture = LoadGolden().RootElement.GetProperty("download_source_catalog");

        var catalog = JsonSerializer.Deserialize<Wire.DownloadSourceCatalog>(fixture.GetRawText())!;
        Assert.Equal(4, catalog.Sources.Count);
        Assert.Equal(Wire.DownloadSourceKind.PackageIndex, catalog.Sources[0].Kind);
        Assert.Equal("pypi-official", catalog.Sources[0].Id);
        Assert.Equal("https://pypi.org/simple", catalog.Sources[0].Endpoint);
        Assert.Equal(Wire.DownloadSourceKind.PackageIndex, catalog.Sources[1].Kind);
        Assert.Equal(Wire.DownloadSourceKind.ModelRegistry, catalog.Sources[2].Kind);
        Assert.Equal(Wire.DownloadSourceKind.ModelRegistry, catalog.Sources[3].Kind);
        Assert.Equal("hf-mirror", catalog.Sources[3].Id);

        AssertDeepRoundTrip(
            fixture,
            json => JsonSerializer.Deserialize<Wire.DownloadSourceCatalog>(json)!,
            value => JsonSerializer.Serialize(value, value.GetType()));
    }

    [Fact]
    public void SettingsSelectionRoundTripsThroughHttpV2Mirror()
    {
        JsonElement fixture = LoadGolden().RootElement.GetProperty("download_source_selection");

        string[] selection = JsonSerializer.Deserialize<string[]>(fixture.GetRawText())!;
        var snapshot = new HttpV2.SettingsSnapshot
        {
            Residency = new SettingsResidency(),
            Extra = new Dictionary<string, JsonElement>(),
            DownloadSourceIds = selection,
        };

        var node = JsonNode.Parse(
            HttpV2Json.Serialize(snapshot, typeof(HttpV2.SettingsSnapshot)))!;
        Assert.True(JsonNode.DeepEquals(JsonNode.Parse(fixture.GetRawText()), node!["download_source_ids"]));
    }

    [Fact]
    public void OmittingDownloadSourceIdsKeepsLegacyWireShape()
    {
        const string legacyJson = """
            {"schema_version": 2, "residency": {"default_ttl_seconds": 300, "pipelines": []}, "extra": {}}
            """;
        var snapshot = HttpV2Json.Deserialize<HttpV2.SettingsSnapshot>(legacyJson)!;
        Assert.Null(snapshot.DownloadSourceIds);

        var roundTrip = JsonNode.Parse(
            HttpV2Json.Serialize(snapshot, typeof(HttpV2.SettingsSnapshot)))!;
        Assert.Null(roundTrip["download_source_ids"]);
    }

    [Fact]
    public void GeneratedSourceEnumsRejectNonWireValues()
    {
        Assert.Equal(
            Wire.DownloadSourceKind.PackageIndex,
            JsonSerializer.Deserialize<Wire.DownloadSourceKind>("\"package_index\""));
        Assert.Equal(
            Wire.DownloadSourceKind.ModelRegistry,
            JsonSerializer.Deserialize<Wire.DownloadSourceKind>("\"model_registry\""));
        Assert.Throws<JsonException>(
            () => JsonSerializer.Deserialize<Wire.DownloadSourceKind>("\"package-index\""));
        Assert.Throws<JsonException>(
            () => JsonSerializer.Deserialize<Wire.DownloadSourceKind>("0"));
    }

    [Fact]
    public void CapabilityDescriptorCarriesOptionalSourceCatalog()
    {
        var catalog = new Wire.DownloadSourceCatalog
        {
            Sources =
            [
                new Wire.DownloadSourceDescriptor
                {
                    Kind = Wire.DownloadSourceKind.ModelRegistry,
                    Id = "hf-mirror",
                    Endpoint = "https://hf-mirror.com",
                },
            ],
        };
        var descriptor = new Wire.CapabilityDescriptor
        {
            Name = "runtime.download-sources.v1",
            Lifecycle = "active",
            IntroducedIn = "2.7.0",
            DeprecatedIn = null,
            SunsetAt = null,
            Replacement = null,
            DownloadSourceCatalog = catalog,
        };

        string json = JsonSerializer.Serialize(descriptor);
        Assert.Contains("\"download_source_catalog\"", json);
        Assert.Contains("\"hf-mirror\"", json);

        var parsed = JsonSerializer.Deserialize<Wire.CapabilityDescriptor>(json)!;
        Assert.Equal("hf-mirror", parsed.DownloadSourceCatalog!.Sources[0].Id);

        string legacyJson = """
            {"name": "ocr.recognition.v2", "lifecycle": "active", "introduced_in": "2.0.0",
             "deprecated_in": null, "sunset_at": null, "replacement": null}
            """;
        var legacy = JsonSerializer.Deserialize<Wire.CapabilityDescriptor>(legacyJson)!;
        Assert.Null(legacy.DownloadSourceCatalog);
    }

    [Fact]
    public void GeneratedHostRequestCarriesOptionalSelection()
    {
        var request = new Host.RuntimeHostRequest
        {
            ProtocolVersion = 2,
            Operation = Host.RuntimeHostOperation.Ensure,
            ProductRoot = "C:/VibeOCR",
            ComponentLock = "C:/VibeOCR/component-lock.json",
            RuntimeManifest = "C:/VibeOCR/backend/runtime-manifest.json",
            DownloadSourceIds = ["pypi-tuna", "hf-mirror"],
        };

        string json = JsonSerializer.Serialize(request);
        Assert.Contains("\"download_source_ids\"", json);

        var parsed = JsonSerializer.Deserialize<Host.RuntimeHostRequest>(json)!;
        Assert.Equal(["pypi-tuna", "hf-mirror"], parsed.DownloadSourceIds);

        const string legacyJson = """
            {"protocol_version": 2, "operation": "ensure", "product_root": "C:/VibeOCR",
             "component_lock": "C:/VibeOCR/component-lock.json",
             "runtime_manifest": "C:/VibeOCR/backend/runtime-manifest.json"}
            """;
        var legacy = JsonSerializer.Deserialize<Host.RuntimeHostRequest>(legacyJson)!;
        Assert.Null(legacy.DownloadSourceIds);
    }

    private static JsonDocument LoadGolden()
    {
        string path = Path.Combine(V2Directory, "golden", "golden.json");
        return JsonDocument.Parse(File.ReadAllText(path));
    }

    private static string FindV2Directory()
    {
        foreach (string? seed in new[]
                 {
                     Environment.GetEnvironmentVariable("VIBEOCR_REPOSITORY_ROOT"),
                     Directory.GetCurrentDirectory(),
                     AppContext.BaseDirectory,
                 })
        {
            DirectoryInfo? directory = string.IsNullOrWhiteSpace(seed) ? null : new(seed);
            while (directory is not null)
            {
                string candidate = Path.Combine(
                    directory.FullName,
                    "packages",
                    "vibeocr-contracts-py",
                    "src",
                    "vibeocr",
                    "runtime_contracts");
                if (File.Exists(Path.Combine(candidate, "errors.json")))
                {
                    return candidate;
                }

                directory = directory.Parent;
            }
        }

        throw new DirectoryNotFoundException(
            "Could not locate vibeocr/runtime_contracts from test output.");
    }

    private static void AssertDeepRoundTrip(
        JsonElement expected,
        Func<string, object> deserialize,
        Func<object, string> serialize)
    {
        object value = deserialize(expected.GetRawText());
        JsonNode expectedNode = JsonNode.Parse(expected.GetRawText())!;
        JsonNode actualNode = JsonNode.Parse(serialize(value))!;
        Assert.True(JsonNode.DeepEquals(expectedNode, actualNode),
            $"round-trip mismatch for {value.GetType().Name}:\n" +
            $"expected: {expectedNode}\nactual:   {actualNode}");
    }
}
