# natocr

**natocr** (*native ocr*) is a small Python wrapper around the OCR engines that 
already ship with macOS and Windows: Vision framework on macOS and Windows 
Runtime OCR on Windows.

These built-in engines are generally faster, more efficient, and more accurate 
than third-party alternatives like Tesseract. **natocr** makes reaching for them 
painless via one clean Python API instead of wrangling with Objective-C bridges 
or WinRT async plumbing.

## Notable Updates

- **v2.0.0** (2026-06-25) - batch & async support: [`recognize_many()`](#batch-and-async) plus awaitable [`arecognize()`](#batch-and-async) / [`arecognize_many()`](#batch-and-async) for concurrent, non-blocking OCR
- **v1.6.1** (2026-06-04) - animated PNG and multi-image HEIF support
- **v1.6.0** (2026-06-04) - multi-page documents and DjVu support
- **v1.5.0** (2026-06-04) - JPEG 2000, JPEG XL, and JPEG XR / HD Photo support
- **v1.4.0** (2026-06-04) - HEIC / HEIF (iPhone photo) support

## Install

```bash
pip install natocr

# for JPEG XL, JPEG XR & DjVu support
pip install natocr[extras]
```

The right native backend (Vision on macOS, Windows Runtime OCR on Windows) is
pulled in automatically for your platform - no OS-specific install command to
pick.

natocr ships a `py.typed` marker, so the public API is fully typed - mypy,
pyright, and your editor pick up the hints with no stubs needed.

## Quick start

```python
from natocr import OCR

ocr = OCR()                    # defaults to english
pages = ocr.recognize("invoice.png")   # one OCRResult per page

print(pages[0].text)
```

```text
Invoice #1042 Total $58.20 Thank you!
```

`recognize()` always returns a `list` of `OCRResult` - one per page. Most images
are a single page, so you'll often just read `pages[0]`; multi-page/multi-frame
inputs (DjVu, TIFF, GIF, animated PNG, multi-image HEIC/HEIF) give one result per
frame (see [Multi-page documents](#multi-page-documents)).

### Confidence Scores and Bounding Boxes

Beyond the flat `.text`, each `OCRResult` carries a per-detection breakdown with
bounding boxes and (*on macOS*) confidence scores:

```python
page = ocr.recognize("receipt.png")[0]   # first (often only) page

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

### Lines and Words

There's also convenience views for grouping a page by reading order:

```python
page.lines      # ['Acme Coffee', 'Latte $4.50']  - elements grouped into lines
page.words      # list of TextElement with non-empty text
```

Want the confidence and bounds for each line (not just the text)? `text_lines`
gives you the same grouping as [`TextLine`](https://alfredchiesa.github.io/natocr/api/#natocr.TextLine)
objects, and `paragraphs` merges lines into blocks by their vertical gaps - both
aggregate confidence across their elements:

```python
for line in page.text_lines:
    print(line.text, line.confidence, line.bounds.bounds)

for para in page.paragraphs:   # lines joined by newlines, confidence averaged
    print(para.confidence, para.text)
```

### Filtering by Confidence

Drop the low-confidence noise with `filter()` - it hands back a new `OCRResult`
keeping only detections at or above the threshold:

```python
clean = page.filter(0.8)       # only elements >= 0.8 confidence
print(clean.text)
```

Elements without a confidence score (Windows OCR doesn't report one) are kept by
default since they can't be judged - pass `drop_unknown=True` to drop them too.

### Detection Language

Pick a different recognition language, and inspect what the current platform
supports:

```python
ocr = OCR(language="fr")
print(ocr.platform)               # 'darwin' or 'win32'
print(ocr.supported_languages)    # ['en-US', 'fr-FR', 'de-DE', ...]
```

The supported set is decided by the OS and queried live, so
`supported_languages` always reflects the current machine. On macOS it's
Vision's built-in set for your macOS version; on Windows it's whatever OCR
language packs are installed. See the [Usage guide](https://alfredchiesa.github.io/natocr/usage/#supported-languages)
for the full list and how to add Windows language packs.

### Alternative Inputs

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

### Batch and async

`recognize()` handles one input at a time. For bulk jobs, `recognize_many()`
runs many inputs concurrently with bounded parallelism. The native engines
release the GIL while recognizing, so this gives real throughput instead of
plodding through the list one by one:

```python
paths = ["page1.png", "page2.png", "page3.png"]

results = ocr.recognize_many(paths, max_concurrency=4)
for pages in results:          # one entry per input, in the same order
    print(pages[0].text)       # each entry is a list of pages, like recognize()
```

`recognize_many()` accepts the same input types as `recognize()` (paths, PIL
images, numpy arrays, bytes - mix and match), preserves input order, and
defaults `max_concurrency` to the CPU count.

There are also awaitable variants so OCR never blocks your event loop - drop
them straight into FastAPI or any async server:

```python
result = await ocr.arecognize("page.png")          # one input
results = await ocr.arecognize_many(paths)          # many, concurrently
```

`arecognize()` / `arecognize_many()` offload the blocking native call to a
worker thread, so the calling coroutine stays responsive.

## Supported File Types

Images are decoded with [Pillow](https://python-pillow.org/), so any raster
format Pillow can open works as an input file or byte string. HEIC/HEIF decoding
(and AVIF) is provided by the bundled [pillow-heif](https://github.com/bigcat88/pillow_heif),
so iPhone photos work with no extra setup. JPEG XL, JPEG XR, and DjVu need extra
decoders - install them with `pip install natocr[extras]` (see
[Optional formats](#optional-formats-jpeg-xl-jpeg-xr-djvu) below).

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

### Optional formats (JPEG XL, JPEG XR, DjVu)

These are optional because their decoders are extra dependencies. Install them
with:

```bash
pip install natocr[extras]
```

That pulls in [pillow-jxl-plugin](https://github.com/inflation/pillow-jxl-plugin)
for `.jxl`, [imagecodecs](https://github.com/cgohlke/imagecodecs) for
`.jxr`/`.wdp`/`.hdp`, and [python-djvulibre](https://pypi.org/project/djvulibre-python/)
for `.djvu`/`.djv`. Once installed they decode through the same `recognize()`
call as every other format - no extra code. Without the extra, the rest of the
formats above (including JPEG 2000) keep working unchanged.

**DjVu also needs the system `djvulibre` library** that python-djvulibre builds
against:

```bash
brew install djvulibre         # macOS
sudo apt install libdjvulibre-dev   # Debian/Ubuntu
```

On Windows, install [DjVuLibre](https://djvu.sourceforge.net/) so its DLLs land
on `PATH` (the wheel links against it).

> [!NOTE]
> Support degrades gracefully: if `natocr[extras]` or the `djvulibre` library
> isn't present, DjVu just isn't registered and opening a `.djvu` raises Pillow's
> usual `UnidentifiedImageError`. Every other format keeps working - nothing else
> breaks.

### Multi-page documents

`recognize()` reads **every page** and returns one `OCRResult` per page, in
order. The formats that can carry more than one frame/page are **DjVu**,
**multi-page TIFF**, **animated GIF**, **animated PNG**, and **multi-image
HEIC/HEIF**:

```python
for i, page in enumerate(ocr.recognize("scan.djvu"), start=1):
    print(f"--- page {i} ---")
    print(page.text)
```

Single-page inputs (PNG, JPEG, ...) come back as a one-element list, so the same
loop works for everything - or just grab `recognize(...)[0]`.

In addition to file paths, `recognize()` accepts these in-memory types:

| Input type | Example |
| --- | --- |
| `str` (file path) | `ocr.recognize("page.png")` |
| `PIL.Image.Image` | `ocr.recognize(Image.open("page.png"))` |
| `numpy.ndarray` | `ocr.recognize(np.array(image))` |
| `bytes` (encoded image) | `ocr.recognize(data)` |

> [!NOTE]
> Only DjVu, TIFF, GIF, animated PNG, and multi-image HEIC/HEIF carry multiple
> pages here. PDFs aren't decoded directly - rasterize a page to one of the
> formats above first (e.g. with `pdf2image` or `pymupdf`).

## Testing

Install the dev dependencies (in a virtualenv), then run the suite. The tests
mock the native macOS Vision and Windows Runtime backends, so they run anywhere
without those frameworks installed.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Run everything with coverage (coverage is wired up in `pyproject.toml`, so plain
`pytest` already reports it):

```bash
pytest
```

Other handy invocations:

```bash
# run a single test file
pytest tests/test_models.py

# run one test by name
pytest -k test_lines_groups_close_y_into_single_line

# verbose output
pytest -v
```

Coverage reports land in the terminal, in `htmlcov/index.html`, and in
`coverage.xml`.
