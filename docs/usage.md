# Usage

## Basics

Create an `OCR` and call `recognize()`. It returns a `list` of
[`OCRResult`](api.md#natocr.OCRResult) - one per page. Most images are a single
page, so you'll usually read `pages[0]`:

```python
from natocr import OCR

ocr = OCR()                    # defaults to english
pages = ocr.recognize("invoice.png")

print(pages[0].text)
```

```text
Invoice #1042 Total $58.20 Thank you!
```

Multi-page/multi-frame inputs (DjVu, TIFF, GIF, animated PNG, multi-image
HEIC/HEIF) give one result per frame - see
[Multi-page documents](#multi-page-documents).

## Confidence scores and bounding boxes

Beyond the flat `.text`, each page gives a per-detection breakdown with bounding
boxes and (on macOS) confidence scores:

```python
page = ocr.recognize("receipt.png")[0]

print(page.confidence)            # average confidence, or None if unavailable

for element in page.elements:
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

Convenience views group a page by reading order:

```python
page.lines      # ['Acme Coffee', 'Latte $4.50']  - elements grouped into lines
page.words      # list of TextElement with non-empty text
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
| `ar-SA` Arabic | `ars-SA` Najdi Arabic | | |
| `en-US` English | `fr-FR` French | `it-IT` Italian | `de-DE` German |
| `es-ES` Spanish | `pt-BR` Portuguese | `ru-RU` Russian | `uk-UA` Ukrainian |
| `ko-KR` Korean | `ja-JP` Japanese | `zh-Hans` Chinese (Simplified) | `zh-Hant` Chinese (Traditional) |
| `yue-Hans` Cantonese (Simplified) | `yue-Hant` Cantonese (Traditional) | `th-TH` Thai | `vi-VT` Vietnamese |

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
format Pillow can open works as an input file or byte string. HEIC/HEIF decoding
(and AVIF) is provided by the bundled [pillow-heif](https://github.com/bigcat88/pillow_heif),
so iPhone photos work with no extra setup. JPEG XL, JPEG XR, and DjVu need extra
decoders from the optional `extras` group (see [JPEG XL and JPEG XR](#jpeg-xl-and-jpeg-xr)
and [DjVu](#djvu) below).

| Format | Extensions | Notes |
| --- | --- | --- |
| AVIF | `.avif` | AV1-based, decoded via the bundled pillow-heif |
| BMP | `.bmp` | uncompressed bitmap |
| DjVu | `.djvu`, `.djv` | scanned documents; **multi-page** (needs `natocr[extras]` + the djvulibre system library) |
| GIF | `.gif` | **multi-frame** - one result per frame |
| HEIC/HEIF | `.heic`, `.heif`, `.hif` | iPhone photos and screenshots; **multi-image** containers give one result per image |
| JPEG | `.jpg`, `.jpeg` | great for photos of documents |
| JPEG 2000 | `.jp2`, `.j2k`, `.jpf`, `.jpx` | wavelet-based, decoded natively by Pillow |
| JPEG XL | `.jxl` | modern successor to JPEG (needs `natocr[extras]`) |
| JPEG XR / HD Photo | `.jxr`, `.wdp`, `.hdp` | Microsoft HD Photo (needs `natocr[extras]`) |
| PCX | `.pcx` | legacy PC Paintbrush, common in old scan archives |
| PNG | `.png` | recommended - lossless; **animated PNG** gives one result per frame |
| PPM/PGM | `.ppm`, `.pgm` | netpbm bitmaps |
| TIFF | `.tif`, `.tiff` | common for scans; **multi-page** |
| WebP | `.webp` | modern lossy/lossless |

!!! note
    Multi-page DjVu, TIFF, GIF, animated PNG, and multi-image HEIC/HEIF are read
    frame-by-frame by [`recognize()`](#multi-page-documents). PDFs aren't decoded
    directly - rasterize a page to one of the formats above first (e.g. with
    `pdf2image` or `pymupdf`).

### JPEG 2000

JPEG 2000 (`.jp2`, `.j2k`, `.jpf`, `.jpx`) is decoded by Pillow itself, so it
works out of the box with no extra dependencies.

### JPEG XL and JPEG XR

These two are optional because their decoders are extra dependencies. Install
the `extras` group to enable them:

```bash
pip install natocr[extras]
```

That pulls in
[pillow-jxl-plugin](https://github.com/inflation/pillow-jxl-plugin) for `.jxl`
and [imagecodecs](https://github.com/cgohlke/imagecodecs) for
`.jxr`/`.wdp`/`.hdp`. Once installed, both decode through the same `recognize()`
call as every other format - no extra code:

```python
ocr.recognize("scan.jxl")              # JPEG XL
ocr.recognize("photo.jxr")             # JPEG XR / HD Photo
```

!!! note
    Without the `extras` group, the rest of the formats above (including
    JPEG 2000) keep working unchanged - only `.jxl` and `.jxr`/`.wdp`/`.hdp`
    require it.

### DjVu

DjVu (`.djvu`, `.djv`) is a format built for scanned text documents. Its decoder,
[python-djvulibre](https://pypi.org/project/djvulibre-python/), is part of the
`extras` group:

```bash
pip install natocr[extras]
```

It also needs the system **djvulibre** library it builds against - this is the
library python-djvulibre links to, and it isn't installable with `pip`:

```bash
brew install djvulibre             # macOS
sudo apt install libdjvulibre-dev  # Debian/Ubuntu
```

On Windows, install [DjVuLibre](https://djvu.sourceforge.net/) so its DLLs are on
`PATH`. Once set up, DjVu decodes through the same `recognize()` call as any other
format. Because DjVu is usually multi-page, see
[Multi-page documents](#multi-page-documents) below.

!!! note "Graceful fallback"
    If `natocr[extras]` or the `djvulibre` library isn't installed, DjVu simply
    isn't registered - opening a `.djvu` raises Pillow's usual
    `UnidentifiedImageError`, and every other format keeps working. Nothing else
    breaks.

## Multi-page documents

`recognize()` reads **every page** and returns one
[`OCRResult`](api.md#natocr.OCRResult) per page, in order. The formats that can
carry more than one frame/page are **DjVu**, **multi-page TIFF**, **animated
GIF**, **animated PNG**, and **multi-image HEIC/HEIF**:

```python
ocr = OCR()

for i, page in enumerate(ocr.recognize("scan.djvu"), start=1):
    print(f"--- page {i} ---")
    print(page.text)
```

Single-page inputs (PNG, JPEG, ...) return a one-element list, so the same loop
works for everything - or just grab `recognize(...)[0]`.

!!! note
    Only DjVu, TIFF, GIF, animated PNG, and multi-image HEIC/HEIF carry multiple
    pages here. PDFs aren't decoded directly - rasterize a page to one of the
    supported formats first (e.g. with `pdf2image` or `pymupdf`).

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
