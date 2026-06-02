"""
macos implementation using vision framework
"""

import io
from typing import List

from PIL import Image

try:
    from Foundation import NSData
    from Vision import VNImageRequestHandler, VNRecognizeTextRequest

    VISION_AVAILABLE = True
except ImportError:
    VISION_AVAILABLE = False

from .models import BoundingBox, OCRResult, TextElement


class MacOSOCR:
    """macos ocr implementation using vision framework"""

    def __init__(self, language: str = "en"):
        """
        initialize macos ocr

        args:
            language: language code for text recognition
        """
        if not VISION_AVAILABLE:
            raise ImportError("vision framework not available")

        self.language = language
        self._setup_request()

    def _setup_request(self):
        """setup vision text recognition request"""
        self.request = VNRecognizeTextRequest()
        self.request.recognitionLanguages = [self.language]
        self.request.recognitionLevel = VNRecognizeTextRequest.RecognitionLevelAccurate
        self.request.usesLanguageCorrection = True

    def recognize(self, image: Image.Image) -> OCRResult:
        """
        perform ocr on pil image

        args:
            image: pil image to process

        returns:
            OCRResult with detected text and metadata
        """
        # convert pil image to nsdata for vision framework
        ns_image_data = self._pil_to_nsdata(image)

        # create image request handler
        handler = VNImageRequestHandler.alloc().initWithData_options_(ns_image_data, {})

        # perform text recognition
        success, error = handler.performRequests_error_([self.request], None)

        if not success:
            raise RuntimeError(f"vision framework error: {error}")

        # extract results
        observations = self.request.results()
        if not observations:
            return OCRResult(text="", confidence=None, elements=[])

        # process observations into structured result
        return self._process_observations(observations, image.size)

    def _pil_to_nsdata(self, image: Image.Image) -> NSData:
        """convert pil image to nsdata for vision framework"""
        # convert to rgb if needed
        if image.mode != "RGB":
            image = image.convert("RGB")

        # save to bytes
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        image_data = buffer.getvalue()

        # create nsdata
        return NSData.dataWithBytes_length_(image_data, len(image_data))

    def _process_observations(self, observations, image_size) -> OCRResult:
        """process vision observations into ocr result"""
        elements = []
        full_text_parts = []
        total_confidence = 0.0
        valid_observations = 0

        for observation in observations:
            # get recognized text
            text = observation.topCandidates_(1)[0].string()
            confidence = observation.topCandidates_(1)[0].confidence()

            if text.strip():
                # get bounding box
                bbox = observation.boundingBox()

                # convert normalized coordinates to pixel coordinates
                x = bbox.origin.x * image_size[0]
                y = (1.0 - bbox.origin.y - bbox.size.height) * image_size[1]  # flip y
                width = bbox.size.width * image_size[0]
                height = bbox.size.height * image_size[1]

                # create bounding box and text element
                bounds = BoundingBox(x=x, y=y, width=width, height=height)
                element = TextElement(text=text, bounds=bounds, confidence=confidence)
                elements.append(element)

                # accumulate text and confidence
                full_text_parts.append(text)
                total_confidence += confidence
                valid_observations += 1

        # calculate average confidence
        avg_confidence = (
            total_confidence / valid_observations if valid_observations > 0 else None
        )

        # join text parts
        full_text = " ".join(full_text_parts)

        return OCRResult(text=full_text, confidence=avg_confidence, elements=elements)

    @property
    def supported_languages(self) -> List[str]:
        """get list of supported languages"""
        # vision framework supports many languages, return common ones
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
