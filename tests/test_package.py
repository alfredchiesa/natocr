"""tests for the package's public surface"""

import re

import natocr


def test_version_exposed():
    # don't pin an exact value - semantic-release bumps it on each release
    assert isinstance(natocr.__version__, str)
    assert re.match(r"^\d+\.\d+\.\d+", natocr.__version__)


def test_public_exports():
    for name in ("OCR", "OCRResult", "TextElement", "BoundingBox"):
        assert hasattr(natocr, name)
