"""
natocr - native ocr library using platform-specific frameworks

this package provides ocr functionality using native frameworks:
- macos: vision framework
- windows: windows runtime ocr
"""

from .core import OCR
from .models import BoundingBox, OCRResult, TextElement

__version__ = "2.0.1"
__author__ = "alfredchiesa"
__email__ = "alfred.personal@icloud.com"

__all__ = [
    "OCR",
    "OCRResult",
    "TextElement",
    "BoundingBox",
]
