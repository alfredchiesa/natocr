import sys
from typing import List

from .models import OCRResult


class OCR:
    def __init__(self, language: str = "en"):
        self.language = language
        self._backend = None
        self._initialize_backend()  # should init based on the os

    def _initialize_backend(self):
        if sys.platform == "darwin":
            pass
        elif sys.platform == "win32":
            pass
        else:
            raise RuntimeError(f"unsupported platform: {sys.platform}")

    def recognize(self, image) -> OCRResult:
        pass

    @property
    def supported_languages(self) -> List[str]:
        pass

    @property
    def platform(self) -> str:
        pass
