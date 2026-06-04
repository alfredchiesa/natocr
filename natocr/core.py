"""
main ocr class with platform detection and delegation
"""

import io
import os
import sys
import tempfile
from typing import List, Union

import numpy as np
import pillow_heif
from PIL import Image, ImageFile, ImageSequence

from .macos import MacOSOCR
from .models import OCRResult
from .windows import WindowsOCR

# teach pillow to decode heic/heif so Image.open handles iphone photos too.
# this also registers .avif (libheif decodes both), so avif works for free.
pillow_heif.register_heif_opener()

# jpeg 2000 (.jp2 etc) is decoded by pillow natively, no setup needed.

# jpeg xl support is optional (pip install natocr[extras]); just importing the
# plugin registers a .jxl opener with pillow, same idea as pillow-heif above.
try:
    import pillow_jxl  # noqa: F401
except ImportError:
    pass

# jpeg xr / hd photo has no pillow plugin, so wire up a tiny opener backed by
# imagecodecs when it's available (also part of the optional extras group).
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

# djvu (scanned documents) has no pillow plugin either, so wire up a multi-page
# opener backed by python-djvulibre when it's available (optional extras group).
# needs the djvulibre system library too - see the docs.
try:
    import djvu.decode

    class _DjVuImageFile(ImageFile.ImageFile):
        format = "DJVU"
        format_description = "DjVu scanned document"

        def _open(self):
            # djvulibre reads pages lazily from the source file, so it has to stay
            # readable while we render. open from the real path when we have one,
            # else spill the bytes to a temp file (also avoids windows file locks).
            tmp = None
            if getattr(self, "filename", None):
                path = self.filename
            else:
                fd, path = tempfile.mkstemp(suffix=".djvu")
                os.write(fd, self.fp.read())
                os.close(fd)
                tmp = path
            try:
                context = djvu.decode.Context()
                document = context.new_document(djvu.decode.FileURI(path))
                document.decoding_job.wait()
                # render every page up front to rgb bytes, then we no longer need
                # the file. matches the eager jpeg xr opener above.
                fmt = djvu.decode.PixelFormatRgb()
                fmt.rows_top_to_bottom = 1
                fmt.y_top_to_bottom = 1
                self._frames = []
                for page in document.pages:
                    job = page.decode(wait=True)
                    width, height = job.size
                    rect = (0, 0, width, height)
                    raw = job.render(
                        djvu.decode.RENDER_COLOR, rect, rect, fmt, row_alignment=1
                    )
                    self._frames.append(((width, height), bytes(raw)))
            finally:
                if tmp is not None:
                    os.unlink(tmp)
            self._frame = 0
            self._load_frame()

        def _load_frame(self):
            # hand pillow the already-decoded page as a single raw rgb tile
            size, raw = self._frames[self._frame]
            self._size = size
            self._mode = "RGB"
            self.fp = io.BytesIO(raw)
            self.tile = [("raw", (0, 0) + size, 0, ("RGB", 0, 1))]

        @property
        def n_frames(self):
            return len(self._frames)

        @property
        def is_animated(self):
            return len(self._frames) > 1

        def seek(self, frame):
            if not 0 <= frame < len(self._frames):
                raise EOFError("no such page")
            self._frame = frame
            self._load_frame()

        def tell(self):
            return self._frame

    def _accept_djvu(prefix):
        return prefix[:8] == b"AT&TFORM"

    Image.register_open(_DjVuImageFile.format, _DjVuImageFile, _accept_djvu)
    Image.register_extensions(_DjVuImageFile.format, [".djvu", ".djv"])
    Image.register_mime(_DjVuImageFile.format, "image/vnd.djvu")
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
        for page in ocr.recognize("invoice.png"):
            print(page.text)
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
                    "macos dependencies not installed. install with: pip install natocr"
                )
        elif sys.platform == "win32":
            try:
                self._backend = WindowsOCR(self.language)
            except ImportError:
                raise RuntimeError(
                    "windows dependencies not installed. install with: pip install natocr"
                )
        else:
            raise RuntimeError(f"unsupported platform: {sys.platform}")

    def recognize(
        self, image: Union[str, Image.Image, np.ndarray, bytes]
    ) -> List[OCRResult]:
        """Recognize text on every page of an image or document.

        Reads each page in order and returns one result per page. Single-page
        inputs (a PNG, a JPEG, ...) come back as a one-element list, so you can
        always iterate the result. Multi-page formats - DjVu, multi-page TIFF,
        and animated GIF - give one [OCRResult][natocr.OCRResult] per page.

        Args:
            image: what to read. One of: a file path (``str``), a
                ``PIL.Image.Image``, a ``numpy.ndarray``, or raw encoded image
                ``bytes``.

        Returns:
            One [OCRResult][natocr.OCRResult] per page, in page order. At least
            one element for any valid input.

        Raises:
            ValueError: if ``image`` isn't one of the supported types.
        """
        # convert input to pil image for consistent processing
        pil_image = self._convert_to_pil(image)

        # ImageSequence.Iterator walks frames/pages for any multi-frame format;
        # single-page inputs simply yield one frame
        return [
            self._backend.recognize(page)
            for page in ImageSequence.Iterator(pil_image)
        ]

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
