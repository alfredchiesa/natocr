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
pip install natocr[macos]      # on macOS
pip install natocr[windows]    # on Windows
```

## Quick start

```python
from natocr import OCR

ocr = OCR()                    # defaults to english
result = ocr.recognize("invoice.png")

print(result.text)
```

```text
Invoice #1042 Total $58.20 Thank you!
```

## Next steps

- **[Usage](usage.md)** - confidence scores, bounding boxes, languages,
  accepted input types, supported file formats, and how to run the tests.
- **[API Reference](api.md)** - the full `OCR` / `OCRResult` / `TextElement` /
  `BoundingBox` reference, generated from the source.
