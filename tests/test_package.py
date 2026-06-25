"""tests for the package's public surface"""

import os
import re

import natocr


def test_version_exposed():
    # don't pin an exact value - semantic-release bumps it on each release
    assert isinstance(natocr.__version__, str)
    assert re.match(r"^\d+\.\d+\.\d+", natocr.__version__)


def test_public_exports():
    for name in ("OCR", "OCRResult", "TextElement", "TextLine", "BoundingBox"):
        assert hasattr(natocr, name)


def test_ships_py_typed_marker():
    # pep 561 marker so downstream type checkers trust our hints
    marker = os.path.join(os.path.dirname(natocr.__file__), "py.typed")
    assert os.path.isfile(marker)
