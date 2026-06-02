# Usage

## Running the tests

The test suite mocks the native macOS Vision and Windows Runtime backends, so it
runs on any platform without those frameworks installed.

Set up a virtualenv and install the dev extras:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Run the full suite (coverage is configured in `pyproject.toml`, so it runs by
default):

```bash
pytest
```

Targeted runs:

```bash
pytest tests/test_ocr.py     # one file
pytest -k convert            # match tests by name
pytest -v                    # verbose
```

Coverage output is printed to the terminal and written to `htmlcov/index.html`
and `coverage.xml`.

## Test layout

| File | Covers |
| --- | --- |
| `tests/test_models.py` | data models (`BoundingBox`, `TextElement`, `OCRResult`) |
| `tests/test_ocr.py` | the `OCR` facade and platform detection in `core.py` |
| `tests/test_macos.py` | the macOS Vision backend (Vision mocked) |
| `tests/test_windows.py` | the Windows Runtime backend (winrt mocked) |
| `tests/test_package.py` | public exports and version |
