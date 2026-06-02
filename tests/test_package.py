"""tests for the package's public surface"""

import natocr


def test_version_exposed():
    assert natocr.__version__ == "1.3.2"


def test_public_exports():
    for name in ("OCR", "OCRResult", "TextElement", "BoundingBox"):
        assert hasattr(natocr, name)
