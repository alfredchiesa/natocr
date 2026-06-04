"""real macos vision integration tests.

these talk to the actual vision framework instead of mocking it, so they only
run on a mac with the macos extra installed. everything is skipped otherwise -
the mocked unit tests in test_macos.py cover the cross-platform logic.
"""

import sys

import pytest
from PIL import Image, ImageDraw, ImageFont

from natocr import macos

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin" or not macos.VISION_AVAILABLE,
    reason="requires macOS with the vision framework installed",
)


@pytest.fixture
def ocr():
    from natocr import OCR

    return OCR()


def render(text):
    """render text onto a white image so vision has something clean to read"""
    img = Image.new("RGB", (520, 90), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 40)
    except OSError:
        pytest.skip("Arial not available to render a reliable sample")
    draw.text((12, 25), text, fill="black", font=font)
    return img


def test_supported_languages_is_real(ocr):
    # the live list straight from vision
    langs = ocr.supported_languages
    assert langs, "vision should report at least one language"
    assert "en-US" in langs
    # all bcp-47 tags, no bare short codes
    assert all("-" in tag for tag in langs)


def test_recognizes_rendered_text(ocr):
    # full round-trip: render some text and read it back (single page -> [0])
    result = ocr.recognize(render("Hello natocr 123"))[0]

    assert "natocr" in result.text.lower()
    # macos reports real confidence per detection
    assert result.confidence is not None and result.confidence > 0.5
    assert result.elements
    box = result.elements[0].bounds
    assert box.width > 0 and box.height > 0


def test_recognizes_french():
    from natocr import OCR

    # french engine on french text
    result = OCR(language="fr").recognize(render("Bonjour le monde"))[0]

    assert "bonjour" in result.text.lower()
    assert result.confidence is not None and result.confidence > 0.5


def test_recognizes_spanish():
    from natocr import OCR

    # café has an accent, so this also exercises non-ascii recognition
    result = OCR(language="es").recognize(render("Hola mundo café"))[0]

    text = result.text.lower()
    assert "hola" in text and "café" in text
    assert result.confidence is not None and result.confidence > 0.5
