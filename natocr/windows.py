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
        total_confidence = 0.0
        valid_lines = 0

        for line in result.lines:
            line_text = line.text
            if line_text.strip():
                # get line bounding box
                bbox = line.words[0].bounding_rect if line.words else line.bounding_rect

                # convert to pixel coordinates
                x = bbox.x
                y = bbox.y
                width = bbox.width
                height = bbox.height

                # create bounding box and text element
                bounds = BoundingBox(x=x, y=y, width=width, height=height)
                element = TextElement(text=line_text, bounds=bounds, confidence=None)
                elements.append(element)

                # accumulate text
                full_text_parts.append(line_text)
                valid_lines += 1

        # join text parts
        full_text = " ".join(full_text_parts)

        return OCRResult(
            text=full_text,
            confidence=None,  # windows ocr doesn't provide confidence scores
            elements=elements,
        )

    @property
    def supported_languages(self) -> List[str]:
        """get list of supported languages"""
        # get available languages from ocr engine
        try:
            languages = self.engine.available_recognizer_languages
            return [lang.language_tag for lang in languages]
        except Exception:
            # fallback to common languages
            return [
                "en",
                "es",
                "fr",
                "de",
                "it",
                "pt",
                "ru",
                "ja",
                "ko",
                "zh-Hans",
                "zh-Hant",
                "ar",
                "hi",
                "th",
                "vi",
                "tr",
                "pl",
                "nl",
                "sv",
                "da",
                "no",
                "fi",
            ]
