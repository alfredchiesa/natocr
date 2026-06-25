"""
windows implementation using windows runtime ocr
"""

import io
from typing import List, Optional

from PIL import Image

try:
    import asyncio

    import winrt.windows.foundation as foundation
    import winrt.windows.graphics.imaging as imaging
    import winrt.windows.media.ocr as ocr
    import winrt.windows.storage.streams as streams

    WINDOWS_OCR_AVAILABLE = True
except ImportError:
    WINDOWS_OCR_AVAILABLE = False

from .models import BoundingBox, OCRResult, TextElement

# curated fallback if the engine's live query fails - common windows ocr packs
# (bcp-47 tags). actual availability depends on which packs are installed.
COMMON_LANGUAGES = [
    "en-US",
    "en-GB",
    "fr-FR",
    "de-DE",
    "es-ES",
    "it-IT",
    "pt-BR",
    "nl-NL",
    "ru-RU",
    "ja-JP",
    "ko-KR",
    "zh-Hans-CN",
    "zh-Hant-TW",
]


class WindowsOCR:
    """windows ocr implementation using windows runtime ocr"""

    def __init__(self, language: str = "en"):
        """
        initialize windows ocr

        args:
            language: language code for text recognition
        """
        if not WINDOWS_OCR_AVAILABLE:
            raise ImportError("windows runtime ocr not available")

        self.language = language
        self._setup_engine()

    def _setup_engine(self):
        """setup windows ocr engine"""
        # create ocr engine with specified language
        self.engine = ocr.OcrEngine.try_create_from_language(
            ocr.Language(self.language)
        )

        if not self.engine:
            # fallback to default language if specified not available
            self.engine = ocr.OcrEngine.try_create_from_user_profile_languages()

        if not self.engine:
            raise RuntimeError("could not create ocr engine")

    def recognize(self, image: Image.Image) -> OCRResult:
        """
        perform ocr on pil image

        args:
            image: pil image to process

        returns:
            OCRResult with detected text and metadata
        """
        # run async recognition
        return asyncio.run(self._recognize_async(image))

    async def _recognize_async(self, image: Image.Image) -> OCRResult:
        """async ocr recognition"""
        # convert pil image to windows bitmap
        bitmap = await self._pil_to_bitmap(image)

        # perform ocr
        result = await self.engine.recognize_async(bitmap)

        # process results
        return self._process_result(result, image.size)

    async def _pil_to_bitmap(self, image: Image.Image):
        """convert pil image to windows bitmap"""
        # convert to rgb if needed
        if image.mode != "RGB":
            image = image.convert("RGB")

        # save to bytes
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        image_data = buffer.getvalue()

        # create in-memory random access stream
        stream = streams.InMemoryRandomAccessStream()
        writer = streams.DataWriter(stream)
        writer.write_bytes(image_data)
        await writer.store_async()
        await writer.flush_async()
        stream.seek(0)

        # create bitmap decoder
        decoder = await imaging.BitmapDecoder.create_async(stream)
        bitmap = await decoder.get_software_bitmap_async()

        return bitmap

    def _process_result(self, result, image_size) -> OCRResult:
        """process windows ocr result into ocr result"""
        elements = []
        full_text_parts = []

        for line in result.lines:
            line_text = line.text
            if line_text.strip():
                # word rect when we have one, else the line rect
                source = line.words[0] if line.words else line
                bbox = source.bounding_rect

                # convert to pixel coordinates
                x = bbox.x
                y = bbox.y
                width = bbox.width
                height = bbox.height

                # winrt ocr doesn't expose confidence today, so this is None in
                # practice - but grab it best-effort in case a build ever does
                confidence = getattr(source, "confidence", None)

                # create bounding box and text element
                bounds = BoundingBox(x=x, y=y, width=width, height=height)
                element = TextElement(
                    text=line_text, bounds=bounds, confidence=confidence
                )
                elements.append(element)

                # accumulate text
                full_text_parts.append(line_text)

        # join text parts
        full_text = " ".join(full_text_parts)

        # mean of whatever confidences exist (none today), mirroring macos
        scores = [e.confidence for e in elements if e.confidence is not None]
        avg_confidence = sum(scores) / len(scores) if scores else None

        return OCRResult(
            text=full_text,
            confidence=avg_confidence,
            elements=elements,
        )

    @property
    def supported_languages(self) -> List[str]:
        """Language codes with an OCR pack installed on this machine.

        Queried live from the engine, so it reflects whatever Windows OCR
        language packs are installed (returned as BCP-47 tags like ``en-US``).
        Falls back to the curated
        [`COMMON_LANGUAGES`][natocr.windows.COMMON_LANGUAGES] set if the query
        fails.
        """
        # the set depends on installed ocr language packs, so ask the engine
        try:
            languages = self.engine.available_recognizer_languages
            return [lang.language_tag for lang in languages]
        except Exception:
            return list(COMMON_LANGUAGES)
