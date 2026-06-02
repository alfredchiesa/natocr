"""tests for the macos vision backend, with vision symbols mocked out"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PIL import Image

from natocr import macos
from natocr.macos import MacOSOCR


# fake vision observation objects used by _process_observations / recognize
class FakeCandidate:
    def __init__(self, text, conf):
        self._text = text
        self._conf = conf

    def string(self):
        return self._text

    def confidence(self):
        return self._conf


class FakeObservation:
    def __init__(self, text, conf, x, y, w, h):
        self._cand = FakeCandidate(text, conf)
        self._bbox = SimpleNamespace(
            origin=SimpleNamespace(x=x, y=y),
            size=SimpleNamespace(width=w, height=h),
        )

    def topCandidates_(self, n):
        return [self._cand]

    def boundingBox(self):
        return self._bbox


@pytest.fixture
def vision(monkeypatch):
    """flip VISION_AVAILABLE on and stub the request type"""
    monkeypatch.setattr(macos, "VISION_AVAILABLE", True)
    request_cls = MagicMock()
    request_cls.RecognitionLevelAccurate = "accurate"
    # symbols don't exist when vision failed to import, so raising=False
    monkeypatch.setattr(macos, "VNRecognizeTextRequest", request_cls, raising=False)
    return request_cls


@pytest.fixture
def backend(vision):
    return MacOSOCR(language="en")


class TestInit:
    def test_raises_without_vision(self, monkeypatch):
        monkeypatch.setattr(macos, "VISION_AVAILABLE", False)
        with pytest.raises(ImportError, match="vision framework not available"):
            MacOSOCR()

    def test_configures_request(self, vision):
        ocr = MacOSOCR(language="fr")
        assert ocr.language == "fr"
        assert ocr.request.recognitionLanguages == ["fr"]
        assert ocr.request.recognitionLevel == "accurate"
        assert ocr.request.usesLanguageCorrection is True


class TestSupportedLanguages:
    def test_returns_common_languages(self, backend):
        langs = backend.supported_languages
        assert "en" in langs
        assert "ja" in langs


class TestPilToNsdata:
    def test_rgb_image(self, backend, monkeypatch):
        ns = MagicMock()
        monkeypatch.setattr(macos, "NSData", ns, raising=False)
        backend._pil_to_nsdata(Image.new("RGB", (4, 4)))
        assert ns.dataWithBytes_length_.called

    def test_converts_non_rgb(self, backend, monkeypatch):
        ns = MagicMock()
        monkeypatch.setattr(macos, "NSData", ns, raising=False)
        # "L" mode exercises the convert-to-rgb branch
        backend._pil_to_nsdata(Image.new("L", (4, 4)))
        assert ns.dataWithBytes_length_.called


class TestProcessObservations:
    def test_builds_elements_and_average_confidence(self, backend):
        obs = [
            FakeObservation("hi", 0.9, x=0.1, y=0.2, w=0.3, h=0.4),
            FakeObservation("   ", 0.1, x=0, y=0, w=0, h=0),  # skipped: blank
        ]
        result = backend._process_observations(obs, image_size=(100, 200))
        assert result.text == "hi"
        assert result.confidence == pytest.approx(0.9)
        assert len(result.elements) == 1
        elem = result.elements[0]
        assert elem.bounds.x == pytest.approx(10.0)
        assert elem.bounds.y == pytest.approx(80.0)  # y is flipped
        assert elem.bounds.width == pytest.approx(30.0)
        assert elem.bounds.height == pytest.approx(80.0)

    def test_all_blank_gives_none_confidence(self, backend):
        result = backend._process_observations(
            [FakeObservation("  ", 0.5, 0, 0, 0, 0)], image_size=(10, 10)
        )
        assert result.text == ""
        assert result.confidence is None
        assert result.elements == []


class TestRecognize:
    def _patch_handler(self, monkeypatch, success=True, error=None):
        handler = MagicMock()
        handler.performRequests_error_.return_value = (success, error)
        handler_cls = MagicMock()
        handler_cls.alloc.return_value.initWithData_options_.return_value = handler
        monkeypatch.setattr(macos, "VNImageRequestHandler", handler_cls, raising=False)
        monkeypatch.setattr(macos, "NSData", MagicMock(), raising=False)
        return handler

    def test_returns_processed_result(self, backend, monkeypatch):
        self._patch_handler(monkeypatch, success=True)
        backend.request.results.return_value = [
            FakeObservation("hello", 0.8, 0.0, 0.0, 1.0, 1.0)
        ]
        result = backend.recognize(Image.new("RGB", (10, 10)))
        assert result.text == "hello"

    def test_failure_raises(self, backend, monkeypatch):
        self._patch_handler(monkeypatch, success=False, error="boom")
        with pytest.raises(RuntimeError, match="vision framework error"):
            backend.recognize(Image.new("RGB", (10, 10)))

    def test_no_observations_returns_empty(self, backend, monkeypatch):
        self._patch_handler(monkeypatch, success=True)
        backend.request.results.return_value = None
        result = backend.recognize(Image.new("RGB", (10, 10)))
        assert result.text == ""
        assert result.elements == []
