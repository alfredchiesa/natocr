# natocr

**natocr** (*native ocr*) is a small Python wrapper around the OCR engines that
already ship with macOS and Windows: the Vision framework on macOS and Windows
Runtime OCR on Windows.

These built-in engines are generally faster, more efficient, and more accurate
than third-party alternatives like Tesseract. **natocr** makes reaching for them
painless via one clean Python API instead of wrangling with Objective-C bridges
or WinRT async plumbing.

## Install

```bash
pip install natocr
```

Add the `extras` group for **JPEG XL** / **XR** / **HD** and **DjVu** decoding (see
[supported file formats](usage.md#supported-file-formats)):

```bash
pip install natocr[extras]
```

## Quick start

```python
from natocr import OCR

ocr = OCR()
pages = ocr.recognize("invoice.png")

print(pages[0].text)
```

```text
Invoice #1042 Total $58.20 Thank you!
```

`recognize()` always returns a `list` - one [`OCRResult`](api.md#natocr.OCRResult)
per page. Most images are a single page, so reach for `pages[0]`; see
[Multi-page documents](usage.md#multi-page-documents) for DjVu / TIFF / GIF.

### Bounding Boxes

```python
page = ocr.recognize("receipt.png")[0]

for element in page.elements:
    box = element.bounds.bounds
    print(f"{element.text!r} @ {box} conf={element.confidence}")
```

```text
'Acme Coffee' @ (24.0, 18.0, 180.0, 32.0) conf=0.97
'Latte' @ (24.0, 70.0, 96.0, 28.0) conf=0.95
'$4.50' @ (220.0, 70.0, 80.0, 28.0) conf=0.88
```

### Confidence Scores

On macOS you can view the confidence score of the total detections or per 
individual detection. This is not currently available on windows.

```python
page = ocr.recognize("drivers-license.jpg")[0]

# avg confidence, or None if unavailable
print(f"Overall confidence: {page.confidence}")
```

```text
Overall confidence: 0.93
```

## Next steps

- **[Usage](usage.md)** - confidence scores, bounding boxes, languages,
  accepted input types, supported file formats, and how to run the tests.
- **[API Reference](api.md)** - the full `OCR` / `OCRResult` / `TextElement` /
  `BoundingBox` reference, generated from the source.
