using System.Text.Json;
using VibeOCR.Contracts.HttpV2;
using VibeOCR.Runtime.Contracts.Generated;

namespace VibeOCR.Runtime.Client;

/// <summary>
/// Stable, judgeable preload-plan failure, carrying the protocol error code
/// the caller branches on. Thrown before any network request is attempted.
/// </summary>
public sealed class RecognitionPreloadException : Exception
{
    public RecognitionPreloadException(HttpV2ErrorCode code, string message)
        : base(message)
    {
        Code = code;
    }

    public HttpV2ErrorCode Code { get; }
}

/// <summary>
/// Deterministic legacy projection for one explicit preload request. Feed
/// <c>Pipelines</c> and <c>RecognitionModes</c> into the generic transport's
/// preload call; the server validates that both fields agree.
/// </summary>
public sealed record RecognitionPreloadPlan(
    IReadOnlyList<string> Pipelines,
    IReadOnlyList<string> RecognitionModes);

/// <summary>
/// Explicit recognition-mode preload plan entry
/// (<c>ocr.recognition-modes.v1</c>). A pure counterpart of the Python
/// <c>vibeocr.runtime_client.recognition_preload</c> helper: it validates the
/// requested modes against the *runtime-declared* lifecycle catalog the caller
/// already fetched and fails closed without any network request. It does not
/// replace server-side validation, and the new constants of this package are
/// never used as evidence for what an older runtime supports.
/// </summary>
public static class RecognitionPreload
{
    private static readonly HashSet<string> WireIds =
    [
        "rapid_text",
        "windows_text",
        "paddle_text",
        "paddle_structure",
        "paddle_document_vl",
        "mineru_document",
        "paddle_table",
        "paddle_formula",
    ];

    /// <summary>Builds a preload request plan guarded by the runtime
    /// lifecycle catalog.</summary>
    public static RecognitionPreloadPlan Build(
        IEnumerable<string> recognitionModes,
        IEnumerable<string>? capabilities,
        JsonElement? recognitionModeCatalog)
    {
        ArgumentNullException.ThrowIfNull(recognitionModes);

        List<string> modes = [];
        foreach (string raw in recognitionModes)
        {
            if (!WireIds.Contains(raw))
            {
                throw new RecognitionPreloadException(
                    HttpV2ErrorCode.RecognitionModeUnknown,
                    $"Unknown recognition mode id '{raw}'.");
            }
            if (!modes.Contains(raw, StringComparer.Ordinal))
            {
                modes.Add(raw);
            }
        }
        if (modes.Count == 0)
        {
            throw new RecognitionPreloadException(
                HttpV2ErrorCode.ValidationError,
                "preload requires at least one recognition mode.");
        }

        if (capabilities is null
            || !capabilities.Contains(
                RuntimeProtocol.OCR_RECOGNITION_MODES_V1,
                StringComparer.Ordinal))
        {
            throw new RecognitionPreloadException(
                HttpV2ErrorCode.RecognitionModeLifecycleUnsupported,
                $"The runtime does not advertise "
                    + $"{RuntimeProtocol.OCR_RECOGNITION_MODES_V1}; refusing to "
                    + "preload without the runtime-declared lifecycle catalog.");
        }
        if (recognitionModeCatalog is not { } catalog
            || catalog.ValueKind is not JsonValueKind.Object)
        {
            throw new RecognitionPreloadException(
                HttpV2ErrorCode.RecognitionModeLifecycleUnsupported,
                $"The runtime advertises "
                    + $"{RuntimeProtocol.OCR_RECOGNITION_MODES_V1} but the caller "
                    + "did not provide its recognition_mode_catalog.");
        }

        Dictionary<string, bool> support = ReadDeclaredSupport(catalog);
        foreach (string mode in modes)
        {
            bool listed = support.TryGetValue(mode, out bool declared);
            if (!listed || !declared)
            {
                throw new RecognitionPreloadException(
                    HttpV2ErrorCode.RecognitionModeLifecycleUnsupported,
                    listed
                        ? $"The runtime declares that recognition mode '{mode}' "
                            + "does not support preload."
                        : $"The recognition mode '{mode}' is not listed by the "
                            + "recognition_mode_catalog.");
            }
        }

        List<string> pipelines = [];
        foreach (string mode in modes)
        {
            string pipeline = ProjectToPipeline(mode);
            if (!pipelines.Contains(pipeline, StringComparer.Ordinal))
            {
                pipelines.Add(pipeline);
            }
        }
        return new RecognitionPreloadPlan(pipelines, modes);
    }

    private static string ProjectToPipeline(string mode) => mode switch
    {
        "rapid_text" or "windows_text" or "paddle_text" => "OCR",
        "paddle_structure" => "PP-StructureV3",
        "paddle_document_vl" => "PaddleOCR-VL",
        "mineru_document" => "MinerU",
        "paddle_table" => "TABLE_RECOGNITION",
        "paddle_formula" => "FORMULA_RECOGNITION",
        _ => throw new RecognitionPreloadException(
            HttpV2ErrorCode.RecognitionModeUnknown,
            $"Unknown recognition mode id '{mode}'."),
    };

    /// <summary>
    /// Maps listed mode ids to their runtime-declared preload support,
    /// tolerating unknown future response fields and mode kinds; only the
    /// known supports_preload boolean is read.
    /// </summary>
    private static Dictionary<string, bool> ReadDeclaredSupport(
        JsonElement catalog)
    {
        if (!catalog.TryGetProperty("modes", out JsonElement modesElement)
            || modesElement.ValueKind is not JsonValueKind.Array
            || modesElement.GetArrayLength() == 0)
        {
            throw MalformedCatalog("modes must be a non-empty array.");
        }
        var support = new Dictionary<string, bool>();
        foreach (JsonElement descriptor in modesElement.EnumerateArray())
        {
            if (descriptor.ValueKind is not JsonValueKind.Object)
            {
                throw MalformedCatalog("mode descriptors must be objects.");
            }
            if (!descriptor.TryGetProperty("id", out JsonElement idElement)
                || idElement.ValueKind is not JsonValueKind.String
                || string.IsNullOrEmpty(idElement.GetString()))
            {
                throw MalformedCatalog("mode descriptors must carry a string id.");
            }
            string id = idElement.GetString()!;
            if (!descriptor.TryGetProperty("lifecycle", out JsonElement lifecycle)
                || lifecycle.ValueKind is not JsonValueKind.Object
                || !lifecycle.TryGetProperty(
                    "supports_preload", out JsonElement supportsPreload)
                || !lifecycle.TryGetProperty("kind", out _))
            {
                throw MalformedCatalog(
                    $"mode '{id}' must carry a lifecycle object with kind and "
                    + "supports_preload.");
            }
            if (supportsPreload.ValueKind is not JsonValueKind.True
                and not JsonValueKind.False)
            {
                throw MalformedCatalog(
                    $"mode '{id}' lifecycle supports_preload must be a boolean.");
            }
            if (support.ContainsKey(id))
            {
                throw MalformedCatalog($"duplicate mode id '{id}'.");
            }
            support[id] = supportsPreload.ValueKind is JsonValueKind.True;
        }
        return support;
    }

    private static RecognitionPreloadException MalformedCatalog(string reason) =>
        new(
            HttpV2ErrorCode.RecognitionModeLifecycleUnsupported,
            "The recognition_mode_catalog is malformed: " + reason);
}
