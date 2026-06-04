"""
main ocr class with platform detection and delegation
"""

import io
import sys
from typing import List, Union

import numpy as np
import pillow_heif
from PIL import Image, ImageFile

from .macos import MacOSOCR
from .models import OCRResult
from .windows import WindowsOCR

# teach pillow to decode heic/heif so Image.open handles iphone photos too
pillow_heif.register_heif_opener()

# jpeg 2000 (.jp2 etc) is decoded by pillow natively, no setup needed.

# jpeg xl support is optional (pip install natocr[formats]); just importing the
# plugin registers a .jxl opener with pillow, same idea as pillow-heif above.
try:
    import pillow_jxl  # noqa: F401
except ImportError:
    pass

# jpeg xr / hd photo has no pillow plugin, so wire up a tiny opener backed by
# imagecodecs when it's available (also part of the optional formats extra).
try:
    import imagecodecs

    class _JpegXRImageFile(ImageFile.ImageFile):
        format = "JPEGXR"
        format_description = "JPEG XR / HD Photo"

        def _open(self):
            arr = imagecodecs.jpegxr_decode(self.fp.read())
            if arr.ndim == 2:  # grayscale comes back without a channel axis
                arr = arr[:, :, None]
            height, width, channels = arr.shape
            mode = {1: "L", 2: "LA", 3: "RGB", 4: "RGBA"}[channels]
            self._size = (width, height)
            self._mode = mode
            # hand pillow the already-decoded pixels as a single raw tile
            self.fp = io.BytesIO(np.ascontiguousarray(arr).tobytes())
            self.tile = [("raw", (0, 0, width, height), 0, (mode, 0, 1))]

    def _accept_jpegxr(prefix):
        return prefix[:4] == b"II\xbc\x01"

    Image.register_open(_JpegXRImageFile.format, _JpegXRImageFile, _accept_jpegxr)
    Image.register_extensions(_JpegXRImageFile.format, [".jxr", ".wdp", ".hdp"])
    Image.register_mime(_JpegXRImageFile.format, "image/jxr")
except ImportError:
    pass


class OCR:
    """Run OCR using the operating system's native engine.

    Picks the right backend for the current platform - the Vision framework on
    macOS, Windows Runtime OCR on Windows - and gives you one API over both.

    Example:
        ```python
        from natocr import OCR

        ocr = OCR()                       # english by default
        result = ocr.recognize("invoice.png")
        print(result.text)
        ```

    Args:
        language: language code for text recognition (default: ``"en"``).

    Raises:
        RuntimeError: on an unsupported platform, or when the platform's native
            OCR dependencies aren't installed.
    """

    def __init__(self, language: str = "en"):
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
        """Recognize text in an image.

        Args:
            image: what to read. One of: a file path (``str``), a
                ``PIL.Image.Image``, a ``numpy.ndarray``, or raw encoded image
                ``bytes``.

        Returns:
            An [OCRResult][natocr.OCRResult] with the detected text and
            per-element metadata.

        Raises:
            ValueError: if ``image`` isn't one of the supported types.
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
        """Language codes the current platform's backend supports."""
        return self._backend.supported_languages if self._backend else []

    @property
    def platform(self) -> str:
        """The current platform identifier (e.g. ``"darwin"`` or ``"win32"``)."""
        return sys.platform
