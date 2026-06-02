"""
main ocr class with platform detection and delegation
"""

import io
import sys
from typing import List, Union

import numpy as np
from PIL import Image

from .macos import MacOSOCR
from .models import OCRResult
from .windows import WindowsOCR


class OCR:
    """main ocr class that delegates to platform-specific implementations"""

    def __init__(self, language: str = "en"):
        """
        initialize ocr with specified language

        args:
            language: language code for text recognition (default: "en")
        """
        self.language = language
        self._backend = None
        self._initialize_backend()

    def _initialize_backend(self):
        """initialize platform-specific ocr backend"""
        if sys.platform == "darwin":
            try:
                self._backend = MacOSOCR(self.language)
            except ImportError:
                raise RuntimeError(
                    "macos dependencies not installed. install with: pip install natocr[macos]"
                )
        elif sys.platform == "win32":
            try:
                self._backend = WindowsOCR(self.language)
            except ImportError:
                raise RuntimeError(
                    "windows dependencies not installed. install with: pip install natocr[windows]"
                )
        else:
            raise RuntimeError(f"unsupported platform: {sys.platform}")

    def recognize(self, image: Union[str, Image.Image, np.ndarray, bytes]) -> OCRResult:
        """
        perform ocr on the provided image

        args:
            image: image to process - can be file path, pil image, numpy array, or bytes

        returns:
            OCRResult containing detected text and metadata
        """
        # convert input to pil image for consistent processing
        pil_image = self._convert_to_pil(image)

        # delegate to platform-specific implementation
        return self._backend.recognize(pil_image)

    def _convert_to_pil(
        self, image: Union[str, Image.Image, np.ndarray, bytes]
    ) -> Image.Image:
        """convert various image formats to pil image"""
        if isinstance(image, str):
            # file path
            return Image.open(image)
        elif isinstance(image, Image.Image):
            # already a pil image
            return image
        elif isinstance(image, np.ndarray):
            # numpy array
            return Image.fromarray(image)
        elif isinstance(image, bytes):
            # raw bytes
            return Image.open(io.BytesIO(image))
        else:
            raise ValueError(f"unsupported image type: {type(image)}")

    @property
    def supported_languages(self) -> List[str]:
        """get list of supported languages for current platform"""
        return self._backend.supported_languages if self._backend else []

    @property
    def platform(self) -> str:
        """get current platform name"""
        return sys.platform
