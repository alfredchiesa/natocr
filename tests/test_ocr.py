"""tests for the platform-detecting OCR facade in core.py"""

import io
from unittest.mock import MagicMock

import numpy as np
import pytest
from PIL import Image

from natocr import core
from natocr.core import OCR


@pytest.fixture
def mock_backend(monkeypatch):
    """build an OCR on darwin with a mocked macos backend"""
    backend = MagicMock()
    monkeypatch.setattr(core, "MacOSOCR", MagicMock(return_value=backend))
    # only patch sys.platform while constructing OCR, then restore it. leaving it
    # patched to darwin leaks into pytest's tmp_path fixture, whose get_user_id()
    # then skips its win32 guard and calls os.getuid() - which blows up on windows.
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(core.sys, "platform", "darwin")
        ocr = OCR()
    return ocr, backend


class TestBackendSelection:
    def test_darwin_uses_macos_backend(self, monkeypatch):
        macos = MagicMock()
        monkeypatch.setattr(core.sys, "platform", "darwin")
        monkeypatch.setattr(core, "MacOSOCR", macos)
        ocr = OCR(language="fr")
        macos.assert_called_once_with("fr")
        assert ocr._backend is macos.return_value

    def test_darwin_import_error_becomes_runtime_error(self, monkeypatch):
        monkeypatch.setattr(core.sys, "platform", "darwin")
        monkeypatch.setattr(core, "MacOSOCR", MagicMock(side_effect=ImportError))
        with pytest.raises(RuntimeError, match="macos dependencies"):
            OCR()

    def test_win32_uses_windows_backend(self, monkeypatch):
        win = MagicMock()
        monkeypatch.setattr(core.sys, "platform", "win32")
        monkeypatch.setattr(core, "WindowsOCR", win)
        ocr = OCR()
        win.assert_called_once_with("en")
        assert ocr._backend is win.return_value

    def test_win32_import_error_becomes_runtime_error(self, monkeypatch):
        monkeypatch.setattr(core.sys, "platform", "win32")
        monkeypatch.setattr(core, "WindowsOCR", MagicMock(side_effect=ImportError))
        with pytest.raises(RuntimeError, match="windows dependencies"):
            OCR()

    def test_unsupported_platform_raises(self, monkeypatch):
        monkeypatch.setattr(core.sys, "platform", "linux")
        with pytest.raises(RuntimeError, match="unsupported platform"):
            OCR()


class TestRecognize:
    def test_converts_then_delegates(self, mock_backend):
        ocr, backend = mock_backend
        sentinel = object()
        backend.recognize.return_value = sentinel
        img = Image.new("RGB", (4, 4))
        assert ocr.recognize(img) is sentinel
        backend.recognize.assert_called_once_with(img)


class TestConvertToPil:
    def test_pil_image_passthrough(self, mock_backend):
        ocr, _ = mock_backend
        img = Image.new("RGB", (2, 2))
        assert ocr._convert_to_pil(img) is img

    def test_numpy_array(self, mock_backend):
        ocr, _ = mock_backend
        arr = np.zeros((3, 3, 3), dtype=np.uint8)
        out = ocr._convert_to_pil(arr)
        assert isinstance(out, Image.Image)
        assert out.size == (3, 3)

    def test_bytes(self, mock_backend):
        ocr, _ = mock_backend
        buf = io.BytesIO()
        Image.new("RGB", (5, 5)).save(buf, format="PNG")
        out = ocr._convert_to_pil(buf.getvalue())
        assert isinstance(out, Image.Image)
        assert out.size == (5, 5)

    def test_str_path(self, mock_backend, tmp_path):
        ocr, _ = mock_backend
        path = tmp_path / "img.png"
        Image.new("RGB", (6, 6)).save(path)
        out = ocr._convert_to_pil(str(path))
        assert isinstance(out, Image.Image)
        assert out.size == (6, 6)

    def test_heif_bytes(self, mock_backend):
        ocr, _ = mock_backend
        buf = io.BytesIO()
        Image.new("RGB", (5, 5)).save(buf, format="HEIF")
        out = ocr._convert_to_pil(buf.getvalue())
        assert isinstance(out, Image.Image)
        assert out.size == (5, 5)

    def test_heic_path(self, mock_backend, tmp_path):
        ocr, _ = mock_backend
        path = tmp_path / "img.heic"
        Image.new("RGB", (6, 6)).save(path)
        out = ocr._convert_to_pil(str(path))
        assert isinstance(out, Image.Image)
        assert out.size == (6, 6)

    def test_jpeg2000_bytes(self, mock_backend):
        ocr, _ = mock_backend
        buf = io.BytesIO()
        Image.new("RGB", (5, 5)).save(buf, format="JPEG2000")
        out = ocr._convert_to_pil(buf.getvalue())
        assert isinstance(out, Image.Image)
        assert out.size == (5, 5)

    def test_jxl_bytes(self, mock_backend):
        pytest.importorskip("pillow_jxl")
        ocr, _ = mock_backend
        buf = io.BytesIO()
        Image.new("RGB", (5, 5)).save(buf, format="JXL")
        out = ocr._convert_to_pil(buf.getvalue())
        assert isinstance(out, Image.Image)
        assert out.size == (5, 5)

    def test_jxr_path(self, mock_backend, tmp_path):
        imagecodecs = pytest.importorskip("imagecodecs")
        ocr, _ = mock_backend
        arr = np.zeros((6, 6, 3), dtype=np.uint8)
        path = tmp_path / "img.jxr"
        path.write_bytes(imagecodecs.jpegxr_encode(arr))
        out = ocr._convert_to_pil(str(path))
        assert isinstance(out, Image.Image)
        assert out.size == (6, 6)

    def test_jxr_bytes(self, mock_backend):
        imagecodecs = pytest.importorskip("imagecodecs")
        ocr, _ = mock_backend
        arr = np.zeros((5, 7, 3), dtype=np.uint8)
        out = ocr._convert_to_pil(imagecodecs.jpegxr_encode(arr))
        assert isinstance(out, Image.Image)
        assert out.size == (7, 5)

    def test_unsupported_type_raises(self, mock_backend):
        ocr, _ = mock_backend
        with pytest.raises(ValueError, match="unsupported image type"):
            ocr._convert_to_pil(123)


class TestProperties:
    def test_supported_languages_delegates_to_backend(self, mock_backend):
        ocr, backend = mock_backend
        backend.supported_languages = ["en", "fr"]
        assert ocr.supported_languages == ["en", "fr"]

    def test_supported_languages_empty_without_backend(self, mock_backend):
        ocr, _ = mock_backend
        ocr._backend = None
        assert ocr.supported_languages == []

    def test_platform_property(self, mock_backend, monkeypatch):
        ocr, _ = mock_backend
        monkeypatch.setattr(core.sys, "platform", "darwin")
        assert ocr.platform == "darwin"
