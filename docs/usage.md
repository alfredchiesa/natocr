# Usage

## Basics

Create an `OCR` and call `recognize()`. It returns an
[`OCRResult`](api.md#natocr.OCRResult):

```python
from natocr import OCR

ocr = OCR()                    # defaults to english
result = ocr.recognize("invoice.png")

print(result.text)
```

```text
Invoice #1042 Total $58.20 Thank you!
```

## Confidence scores and bounding boxes

Beyond the flat `.text`, you get a per-detection breakdown with bounding boxes
and (on macOS) confidence scores:

```python
result = ocr.recognize("receipt.png")

print(result.confidence)          # average confidence, or None if unavailable

for element in result.elements:
    box = element.bounds.bounds   # (x, y, width, height) in pixels
    print(f"{element.text!r} @ {box} conf={element.confidence}")
```

```text
0.93
'Acme Coffee' @ (24.0, 18.0, 180.0, 32.0) conf=0.97
'Latte' @ (24.0, 70.0, 96.0, 28.0) conf=0.95
'$4.50' @ (220.0, 70.0, 80.0, 28.0) conf=0.88
```

!!! note
    Windows Runtime OCR doesn't report confidence, so `confidence` is `None`
    there.

## Lines and words

Convenience views group the result by reading order:

```python
result.lines      # ['Acme Coffee', 'Latte $4.50']  - elements grouped into lines
result.words      # list of TextElement with non-empty text
```

## Detection language

Pick a recognition language, and inspect what the current platform supports:

```python
ocr = OCR(language="fr")
print(ocr.platform)               # 'darwin' or 'win32'
print(ocr.supported_languages)    # ['en-US', 'fr-FR', 'de-DE', ...]
```

## Supported languages

The set of recognizable languages is decided by the OS, not by natocr, so the
source of truth is always:

```python
OCR().supported_languages
```

It returns BCP-47 tags (e.g. `en-US`, `zh-Hans`) for whatever the current
machine supports. If that live query ever fails, natocr falls back to a curated
hardcoded set (`COMMON_LANGUAGES` in `natocr/macos.py` and `natocr/windows.py`),
listed below.

### macOS (Vision)

Vision ships a fixed set per OS version, queried live from the framework. As of
macOS 15, the accurate recognizer supports (this is also natocr's hardcoded
`COMMON_LANGUAGES` fallback):

| | | | |
| --- | --- | --- | --- |
| `en-US` English | `fr-FR` French | `it-IT` Italian | `de-DE` German |
| `es-ES` Spanish | `pt-BR` Portuguese | `ru-RU` Russian | `uk-UA` Ukrainian |
| `ko-KR` Korean | `ja-JP` Japanese | `zh-Hans` Chinese (Simplified) | `zh-Hant` Chinese (Traditional) |
| `yue-Hans` Cantonese (Simplified) | `yue-Hant` Cantonese (Traditional) | `th-TH` Thai | `vi-VT` Vietnamese |
| `ar-SA` Arabic | `ars-SA` Najdi Arabic | | |

The exact list grows with newer macOS releases, so prefer the runtime query
above over hard-coding it.

### Windows (Windows Runtime OCR)

Windows recognizes any language that has an **OCR language pack** installed, so
the list is machine-specific. natocr's hardcoded `COMMON_LANGUAGES` fallback
covers the common packs:

| | | | |
| --- | --- | --- | --- |
| `en-US` English (US) | `en-GB` English (UK) | `fr-FR` French | `de-DE` German |
| `es-ES` Spanish | `it-IT` Italian | `pt-BR` Portuguese | `nl-NL` Dutch |
| `ru-RU` Russian | `ja-JP` Japanese | `ko-KR` Korean | `zh-Hans-CN` Chinese (Simplified) |
| `zh-Hant-TW` Chinese (Traditional) | | | |

List what's actually installed (Windows PowerShell):

```powershell
[Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages
```

See which packs are available, then install one (PowerShell as Administrator):

```powershell
# list all installable OCR packs
Get-WindowsCapability -Online | Where-Object { $_.Name -like 'Language.OCR*' }

# install, e.g. French
Get-WindowsCapability -Online |
  Where-Object { $_.Name -like 'Language.OCR*fr-FR*' } |
  Add-WindowsCapability -Online
```

## Accepted inputs

`recognize()` accepts more than file paths - hand it whatever you already have
in memory:

```python
from PIL import Image
import numpy as np

ocr.recognize("page.png")              # a file path
ocr.recognize(Image.open("page.png"))  # a PIL image
ocr.recognize(np.array(image))         # a numpy array (e.g. from OpenCV)
ocr.recognize(open("page.png", "rb").read())  # raw image bytes
```

| Input type | Example |
| --- | --- |
| `str` (file path) | `ocr.recognize("page.png")` |
| `PIL.Image.Image` | `ocr.recognize(Image.open("page.png"))` |
| `numpy.ndarray` | `ocr.recognize(np.array(image))` |
| `bytes` (encoded image) | `ocr.recognize(data)` |

## Supported file formats

Images are decoded with [Pillow](https://python-pillow.org/), so any raster
format Pillow can open works as an input file or byte string.

| Format | Extensions | Notes |
| --- | --- | --- |
| PNG | `.png` | recommended - lossless |
| JPEG | `.jpg`, `.jpeg` | great for photos of documents |
| TIFF | `.tif`, `.tiff` | common for scans |
| BMP | `.bmp` | uncompressed bitmap |
| GIF | `.gif` | first frame is used |
| WebP | `.webp` | modern lossy/lossless |
| PPM/PGM | `.ppm`, `.pgm` | netpbm bitmaps |

!!! note
    PDFs and other multi-page documents aren't decoded directly - rasterize a
    page to one of the formats above first (e.g. with `pdf2image` or `pymupdf`).

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

### Test layout

| File | Covers |
| --- | --- |
| `tests/test_models.py` | data models (`BoundingBox`, `TextElement`, `OCRResult`) |
| `tests/test_ocr.py` | the `OCR` facade and platform detection in `core.py` |
| `tests/test_macos.py` | the macOS Vision backend (Vision mocked) |
| `tests/test_windows.py` | the Windows Runtime backend (winrt mocked) |
| `tests/test_integration_macos.py` | real Vision end-to-end (runs on macOS, skips elsewhere) |
| `tests/test_package.py` | public exports and version |
