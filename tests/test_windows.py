"""tests for the windows runtime ocr backend, with winrt mocked out"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image

from natocr import windows
from natocr.windows import WindowsOCR


def make_line(text, rects):
    """build a fake ocr line; rects -> word bounding_rects, [] means no words"""
    words = [SimpleNamespace(bounding_rect=r) for r in rects]
    return SimpleNamespace(
        text=text,
        words=words,
        bounding_rect=SimpleNamespace(x=9, y=9, width=9, height=9),
    )


@pytest.fixture
def winrt(monkeypatch):
    """flip availability on and stub the winrt ocr module"""
    monkeypatch.setattr(windows, "WINDOWS_OCR_AVAILABLE", True)
    ocr_mod = MagicMock()
    # winrt symbols are absent when the import failed, so raising=False
    monkeypatch.setattr(windows, "ocr", ocr_mod, raising=False)
    return ocr_mod


@pytest.fixture
def backend(winrt):
    return WindowsOCR(language="en")


class TestInit:
    def test_raises_without_winrt(self, monkeypatch):
        monkeypatch.setattr(windows, "WINDOWS_OCR_AVAILABLE", False)
        with pytest.raises(ImportError, match="windows runtime ocr not available"):
            WindowsOCR()

    def test_creates_engine_from_language(self, winrt):
        ocr = WindowsOCR(language="en")
        assert ocr.engine is winrt.OcrEngine.try_create_from_language.return_value

    def test_falls_back_to_user_profile(self, winrt):
        winrt.OcrEngine.try_create_from_language.return_value = None
        fallback = MagicMock()
        winrt.OcrEngine.try_create_from_user_profile_languages.return_value = fallback
        ocr = WindowsOCR()
        assert ocr.engine is fallback

    def test_raises_when_no_engine(self, winrt):
        winrt.OcrEngine.try_create_from_language.return_value = None
        winrt.OcrEngine.try_create_from_user_profile_languages.return_value = None
        with pytest.raises(RuntimeError, match="could not create ocr engine"):
            WindowsOCR()


class TestSupportedLanguages:
    def test_lists_engine_languages(self, backend):
        backend.engine.available_recognizer_languages = [
            SimpleNamespace(language_tag="en-US"),
            SimpleNamespace(language_tag="fr-FR"),
        ]
        assert backend.supported_languages == ["en-US", "fr-FR"]

    def test_falls_back_to_common_set_on_error(self, backend):
        class RaisingEngine:
            @property
            def available_recognizer_languages(self):
                raise RuntimeError("nope")

        backend.engine = RaisingEngine()
        assert backend.supported_languages == windows.COMMON_LANGUAGES


class TestProcessResult:
    def test_uses_word_rect_and_skips_blank_and_wordless(self, backend):
        result = SimpleNamespace(
            lines=[
                make_line("hello", [SimpleNamespace(x=1, y=2, width=3, height=4)]),
                make_line("   ", [SimpleNamespace(x=0, y=0, width=0, height=0)]),
                make_line("tail", []),  # no words -> uses line.bounding_rect
            ]
        )
        out = backend._process_result(result, image_size=(50, 50))
        assert out.text == "hello tail"
        assert out.confidence is None
        assert len(out.elements) == 2
        # first element pulled its box from the word rect
        assert out.elements[0].bounds.bounds == (1, 2, 3, 4)
        # third line had no words, so it used the line rect
        assert out.elements[1].bounds.bounds == (9, 9, 9, 9)


class TestRecognize:
    def test_runs_async_chain(self, backend, monkeypatch):
        # stub the winrt stream/imaging plumbing used by _pil_to_bitmap
        writer = MagicMock()
        writer.store_async = AsyncMock()
        writer.flush_async = AsyncMock()
        streams = MagicMock()
        streams.DataWriter.return_value = writer
        monkeypatch.setattr(windows, "streams", streams, raising=False)

        decoder = MagicMock()
        decoder.get_software_bitmap_async = AsyncMock(return_value="bitmap")
        imaging = MagicMock()
        imaging.BitmapDecoder.create_async = AsyncMock(return_value=decoder)
        monkeypatch.setattr(windows, "imaging", imaging, raising=False)

        fake_result = SimpleNamespace(
            lines=[make_line("done", [SimpleNamespace(x=0, y=0, width=1, height=1)])]
        )
        backend.engine.recognize_async = AsyncMock(return_value=fake_result)

        # non-rgb input also exercises the convert branch in _pil_to_bitmap
        out = backend.recognize(Image.new("L", (8, 8)))
        assert out.text == "done"
        backend.engine.recognize_async.assert_awaited_once()
