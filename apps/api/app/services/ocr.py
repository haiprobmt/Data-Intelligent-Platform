from dataclasses import dataclass


@dataclass(frozen=True)
class OcrExtractionResult:
    text: str
    provider: str
    pages: list[dict]
    confidence: float | None = None


class OcrProvider:
    def extract(self, file_path: str) -> OcrExtractionResult:
        raise NotImplementedError


class NoopOcrProvider(OcrProvider):
    def extract(self, file_path: str) -> OcrExtractionResult:
        return OcrExtractionResult(text="", provider="none", pages=[], confidence=None)


def get_ocr_provider() -> OcrProvider:
    return NoopOcrProvider()
