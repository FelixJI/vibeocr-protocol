using System.Text.Json;
using System.Text.RegularExpressions;
using VibeOCR.Contracts.HttpV2;
using VibeOCR.Runtime.Contracts.Generated;

namespace VibeOCR.Runtime.Client;

/// <summary>
/// Stable, judgeable construction failure for the typed MinerU 4
/// configuration entry; carrying the protocol error code the caller branches
/// on. Thrown before any network request is attempted.
/// </summary>
public sealed class MineruConfigException : Exception
{
    public MineruConfigException(HttpV2ErrorCode code, string message)
        : base(message)
    {
        Code = code;
    }

    public HttpV2ErrorCode Code { get; }
}

/// <summary>
/// Explicit MinerU 4 configuration construction entry
/// (<c>ocr.mineru-config.v1</c>). A pure counterpart of the Python
/// <c>vibeocr.runtime_client.mineru_config</c> helper: it validates the typed
/// config plus the caller-fetched capabilities and catalog fail-closed and
/// returns a ready <see cref="PipelineSelection"/> without issuing any
/// network request. It does not replace server-side validation, and it never
/// falls back to legacy options or the flash tier.
/// </summary>
public static partial class MineruConfigSelection
{
    private static readonly HashSet<string> TierIds =
    [
        "flash",
        "basic",
        "standard",
        "advanced",
    ];

    private static readonly HashSet<string> Availabilities =
    [
        "ready",
        "preparation_required",
        "unavailable",
    ];

    /// <summary>Builds a kind=mineru_parse selection guarded by the
    /// capability and catalog the caller already fetched from health.</summary>
    public static PipelineSelection Build(
        MineruConfig config,
        IEnumerable<string>? capabilities,
        JsonElement? mineruConfigCatalog)
    {
        ArgumentNullException.ThrowIfNull(config);
        ValidateConfig(config);

        if (capabilities is null
            || !capabilities.Contains(
                RuntimeProtocol.OCR_MINERU_CONFIG_V1,
                StringComparer.Ordinal))
        {
            throw new MineruConfigException(
                HttpV2ErrorCode.MineruConfigUnavailable,
                $"The runtime does not advertise {RuntimeProtocol.OCR_MINERU_CONFIG_V1}; "
                    + "refusing to send the typed mineru config without falling "
                    + "back to legacy options or the flash tier.");
        }
        if (mineruConfigCatalog is not { } catalog
            || catalog.ValueKind is not JsonValueKind.Object)
        {
            throw new MineruConfigException(
                HttpV2ErrorCode.MineruConfigUnavailable,
                $"The runtime advertises {RuntimeProtocol.OCR_MINERU_CONFIG_V1} "
                    + "but the caller did not provide its mineru_config_catalog.");
        }

        Dictionary<string, JsonElement> tiers = ValidateCatalog(catalog);
        if (!tiers.TryGetValue(
                ToWireTier(config.Tier),
                out JsonElement descriptor))
        {
            throw new MineruConfigException(
                HttpV2ErrorCode.MineruTierUnavailable,
                $"The mineru tier '{ToWireTier(config.Tier)}' is not listed by "
                    + "the mineru_config_catalog.");
        }
        string availability = descriptor.GetProperty("availability").GetString()!;
        if (availability == "unavailable")
        {
            throw new MineruConfigException(
                HttpV2ErrorCode.MineruTierUnavailable,
                $"The mineru tier '{ToWireTier(config.Tier)}' cannot run in this runtime.");
        }
        if (availability == "preparation_required")
        {
            throw new MineruConfigException(
                HttpV2ErrorCode.MineruTierPreparationRequired,
                $"The mineru tier '{ToWireTier(config.Tier)}' requires user "
                    + "preparation before use.");
        }
        foreach (JsonElement language in catalog.GetProperty("languages").EnumerateArray())
        {
            if (language.GetString() == config.Language)
            {
                return new PipelineSelection
                {
                    PipelineId = "MinerU",
                    Options = new Dictionary<string, JsonElement>(),
                    Mineru = config,
                };
            }
        }
        throw new MineruConfigException(
            HttpV2ErrorCode.ValidationError,
            $"The mineru language '{config.Language}' is not listed by the "
                + "mineru_config_catalog.");
    }

    [GeneratedRegex(
        "^(all|r?[1-9][0-9]*(-r?[1-9][0-9]*)?(,r?[1-9][0-9]*(-r?[1-9][0-9]*)?)*)$")]
    private static partial Regex PageRangeRegex();

    private static void ValidateConfig(MineruConfig config)
    {
        if (string.IsNullOrEmpty(config.Language)
            || config.Language.Trim() != config.Language)
        {
            throw new MineruConfigException(
                HttpV2ErrorCode.ValidationError,
                "mineru language must be a non-empty language id without "
                    + "surrounding whitespace.");
        }
        if (string.IsNullOrEmpty(config.PageRange)
            || !PageRangeRegex().IsMatch(config.PageRange))
        {
            throw new MineruConfigException(
                HttpV2ErrorCode.ValidationError,
                "mineru page_range must be 'all' or a comma-separated list of "
                    + "positive/reverse page indexes and closed ranges.");
        }
    }

    private static Dictionary<string, JsonElement> ValidateCatalog(
        JsonElement catalog)
    {
        foreach (string property in catalog.EnumerateObject()
                     .Select(property => property.Name))
        {
            if (property is not ("default_tier" or "tiers" or "languages"))
            {
                throw MalformedCatalog($"unknown catalog key '{property}'.");
            }
        }
        foreach (string required in new[] { "default_tier", "tiers", "languages" })
        {
            if (!catalog.TryGetProperty(required, out _))
            {
                throw MalformedCatalog($"missing catalog key '{required}'.");
            }
        }

        string defaultTier = catalog.GetProperty("default_tier").GetString()!;
        if (!TierIds.Contains(defaultTier))
        {
            throw MalformedCatalog(
                $"default_tier '{defaultTier}' is not a stable tier id.");
        }

        JsonElement tiersElement = catalog.GetProperty("tiers");
        if (tiersElement.ValueKind is not JsonValueKind.Array
            || tiersElement.GetArrayLength() == 0)
        {
            throw MalformedCatalog("tiers must be a non-empty array.");
        }
        var tiers = new Dictionary<string, JsonElement>();
        foreach (JsonElement descriptor in tiersElement.EnumerateArray())
        {
            if (descriptor.ValueKind is not JsonValueKind.Object)
            {
                throw MalformedCatalog("tier descriptors must be objects.");
            }
            foreach (string property in descriptor.EnumerateObject()
                         .Select(property => property.Name))
            {
                if (property is not ("id" or "availability" or "reason_code"))
                {
                    throw MalformedCatalog(
                        $"unknown tier descriptor key '{property}'.");
                }
            }
            foreach (string required in new[] { "id", "availability", "reason_code" })
            {
                if (!descriptor.TryGetProperty(required, out _))
                {
                    throw MalformedCatalog(
                        $"tier descriptor is missing '{required}'.");
                }
            }
            string id = descriptor.GetProperty("id").GetString()!;
            if (!TierIds.Contains(id))
            {
                throw MalformedCatalog($"unknown tier id '{id}'.");
            }
            if (tiers.ContainsKey(id))
            {
                throw MalformedCatalog($"duplicate tier id '{id}'.");
            }
            string availability = descriptor.GetProperty("availability").GetString()!;
            if (!Availabilities.Contains(availability))
            {
                throw MalformedCatalog(
                    $"tier '{id}' has an unknown availability '{availability}'.");
            }
            JsonElement reason = descriptor.GetProperty("reason_code");
            if (reason.ValueKind is JsonValueKind.String
                && string.IsNullOrEmpty(reason.GetString()))
            {
                throw MalformedCatalog(
                    $"tier '{id}' reason_code must be null or a non-empty string.");
            }
            if (reason.ValueKind is not (JsonValueKind.String or JsonValueKind.Null))
            {
                throw MalformedCatalog(
                    $"tier '{id}' reason_code must be a string or null.");
            }
            tiers[id] = descriptor;
        }
        if (!tiers.ContainsKey(defaultTier))
        {
            throw MalformedCatalog(
                $"default_tier '{defaultTier}' is not listed in tiers.");
        }

        JsonElement languages = catalog.GetProperty("languages");
        if (languages.ValueKind is not JsonValueKind.Array
            || languages.GetArrayLength() == 0)
        {
            throw MalformedCatalog("languages must be a non-empty array.");
        }
        var seenLanguages = new HashSet<string>(StringComparer.Ordinal);
        foreach (JsonElement language in languages.EnumerateArray())
        {
            string? id = language.ValueKind is JsonValueKind.String
                ? language.GetString()
                : null;
            if (string.IsNullOrEmpty(id))
            {
                throw MalformedCatalog(
                    "languages must be non-empty strings.");
            }
            if (!seenLanguages.Add(id))
            {
                throw MalformedCatalog($"duplicate language id '{id}'.");
            }
        }
        return tiers;
    }

    private static MineruConfigException MalformedCatalog(string reason) =>
        new(
            HttpV2ErrorCode.MineruConfigUnavailable,
            "The mineru_config_catalog is malformed: " + reason);

    private static string ToWireTier(MineruTier tier) => tier switch
    {
        MineruTier.Flash => "flash",
        MineruTier.Basic => "basic",
        MineruTier.Standard => "standard",
        MineruTier.Advanced => "advanced",
        _ => throw new MineruConfigException(
            HttpV2ErrorCode.ValidationError,
            $"Unknown mineru tier '{tier}'."),
    };
}
