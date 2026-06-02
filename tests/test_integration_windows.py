"""real windows runtime ocr integration tests.

these talk to the actual Windows.Media.Ocr engine instead of mocking it, so they
only run on windows with the windows extra installed and at least one OCR
language pack present. everything is skipped otherwise - the mocked unit tests in
test_windows.py cover the cross-platform logic.

mirrors test_integration_macos.py. note: windows ocr does not report confidence,
so those assertions differ (confidence is always None).
"""

import sys

import pytest
from PIL import Image, ImageDraw, ImageFont

from natocr import windows

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" or not windows.WINDOWS_OCR_AVAILABLE,
    reason="requires Windows with the runtime OCR available (natocr[windows])",
)


@pytest.fixture
def ocr():
    from natocr import OCR

    return OCR()


def render(text):
    """render text onto a white image so the engine has something clean to read"""
    img = Image.new("RGB", (520, 90), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("C:\\Windows\\Fonts\\arial.ttf", 40)
    except OSError:
        pytest.skip("Arial not available to render a reliable sample")
    draw.text((12, 25), text, fill="black", font=font)
    return img


def test_supported_languages_is_real(ocr):
    # whatever ocr packs are installed on this box
    langs = ocr.supported_languages
    assert langs, "the engine should report at least one installed language"
    # all bcp-47 tags, no bare short codes
    assert all("-" in tag for tag in langs)


def test_recognizes_rendered_text(ocr):
    # full round-trip: render some text and read it back
    result = ocr.recognize(render("Hello natocr 123"))

    assert "natocr" in result.text.lower()
    # windows ocr doesn't expose confidence
    assert result.confidence is None
    assert result.elements
    box = result.elements[0].bounds
    assert box.width > 0 and box.height > 0


def test_recognizes_french():
    from natocr import OCR

    # if the fr pack isn't installed the engine falls back to a default one,
    # which still reads latin script fine
    result = OCR(language="fr").recognize(render("Bonjour le monde"))

    assert "bonjour" in result.text.lower()


def test_recognizes_spanish():
    from natocr import OCR

    # spanish text; plain ascii words so it passes whatever pack is active
    result = OCR(language="es").recognize(render("Hola mundo café"))

    text = result.text.lower()
    assert "hola" in text and "mundo" in text
