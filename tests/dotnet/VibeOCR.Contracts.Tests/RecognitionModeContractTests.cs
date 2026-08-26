using System.Text.Json;
using VibeOCR.Contracts.HttpV2;
using Xunit;

namespace VibeOCR.Contracts.Tests;

public sealed class RecognitionModeContractTests
{
    [Fact]
    public void RecognitionModeUsesStableWireIds()
    {
        Assert.Equal(
            "\"rapid_text\"",
            JsonSerializer.Serialize(RecognitionMode.RapidText));
        Assert.Equal(
            RecognitionMode.PaddleDocumentVl,
            JsonSerializer.Deserialize<RecognitionMode>("\"paddle_document_vl\""));
    }

    [Fact]
    public void LegacyPipelineSpecDoesNotInventRecognitionMode()
    {
        var json = HttpV2Json.Serialize(new PipelineSpec
        {
            Name = "OCR",
            TtlSeconds = 120,
        });

        Assert.DoesNotContain("recognition_mode", json, StringComparison.Ordinal);
    }

    [Fact]
    public void ResidencyEntryNamesModeAndConcreteResource()
    {
        var value = new ResidencyEntry
        {
            Pipeline = "OCR",
            RecognitionMode = RecognitionMode.PaddleText,
            ResourceKind = RecognitionResourceKind.Model,
            ResourceId = "paddleocr.text.server-v5",
            Kind = ResidencyKind.Pinned,
        };

        var json = HttpV2Json.Serialize(value);
        var parsed = HttpV2Json.Deserialize<ResidencyEntry>(json)!;

        Assert.Equal(RecognitionMode.PaddleText, parsed.RecognitionMode);
        Assert.Equal(RecognitionResourceKind.Model, parsed.ResourceKind);
        Assert.Equal("paddleocr.text.server-v5", parsed.ResourceId);
    }
}
