# Command line

natocr ships an optional CLI so you can OCR straight from the shell - no Python
required. Its dependencies ([typer](https://typer.tiangolo.com/) and
[rich](https://rich.readthedocs.io/)) live in the `cli` extra to keep
library-only installs lean:

```bash
pip install 'natocr[cli]'
```

That gives you a `natocr` command (and a matching `python -m natocr`):

```bash
natocr scan.png
```

```text
Invoice #1042 Total $58.20 Thank you!
```

The synopsis:

```text
natocr [OPTIONS] [IMAGE]...

  -l, --lang TEXT                  recognition language (default: en)
  -f, --format [text|json|hocr|pdf|table]
                                   output format (default: text)
  -o, --output PATH                output file, or a directory when there
                                   are multiple inputs
  --min-confidence N               drop detections below this confidence
  --list-languages                 print the supported languages and exit
  --version                        print the version and exit
```

!!! note
    The `natocr` command itself is always installed with the package (Python
    entry points can't be conditional). Without the `cli` extra it just prints
    a one-line pointer to `pip install 'natocr[cli]'` instead of a traceback.

## Inputs

Pass one or more image files in any
[supported format](usage.md#supported-file-formats). Glob patterns are expanded
too (quote them so your shell doesn't get there first), and `-` reads raw image
bytes from stdin. This works the same on macOS and Windows - handy on Windows,
where the shell doesn't expand globs for you:

```bash
natocr page1.png page2.png              # several files
natocr 'scans/**/*.tiff'                # glob, including ** recursion
cat scan.png | natocr -                 # from a pipe
```

Multi-page inputs (TIFF, DjVu, GIF, animated PNG, multi-image HEIC/HEIF) are
read page by page, exactly like [`recognize()`](usage.md#multi-page-documents).

If one file in a batch fails to decode, natocr reports it on stderr, keeps
going, and exits non-zero at the end - one bad scan doesn't sink the run.
Batches writing to a directory also get a progress bar on stderr, so stdout
stays clean for pipes.

## Output formats

### `text` (default)

Plain recognized text on stdout. Pages of a multi-page input are separated by a
form feed (`\f`), the same convention tesseract uses:

```bash
natocr scan.png
natocr scan.png | grep -i total
```

### `table`

A colorized table for humans - one row per detected line with its confidence
and bounding box, one table per input:

```bash
natocr receipt.png -f table
```

```text
                receipt.png - 1 page
┏━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┓
┃ page ┃ text          ┃ conf ┃ bounds (x, y, w, h) ┃
┡━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━╇━━━━━━━━━━━━━━━━━━━━━┩
│    1 │ Cosmos Coffee │ 0.97 │ (24, 18, 180, 32)   │
│    1 │ Sagano $4.50  │ 0.92 │ (24, 70, 276, 28)   │
└──────┴───────────────┴──────┴─────────────────────┘
```

### `json`

One compact JSON object per input, newline-delimited (NDJSON), so the shape is
identical whether you pass one file or a thousand - pipe it straight into `jq`:

```bash
natocr scan.png -f json | jq .
natocr '*.png' -f json | jq -r '.pages[].text'
```

Each object carries the file name, language, and per-page text, line grouping,
confidences, and pixel bounding boxes:

```json
{
  "file": "scan.png",
  "language": "en",
  "pages": [
    {
      "text": "Cosmos Coffee Sagano $4.50",
      "confidence": 0.93,
      "lines": ["Cosmos Coffee", "Sagano $4.50"],
      "elements": [
        {
          "text": "Cosmos Coffee",
          "confidence": 0.97,
          "bounds": {"x": 24.0, "y": 18.0, "width": 180.0, "height": 32.0}
        }
      ]
    }
  ]
}
```

### `hocr`

[hOCR](https://kba.github.io/hocr-spec/) is the standard XHTML interchange
format for OCR layout - each word keeps its bounding box and confidence, so
downstream tools (PDF assemblers, layout analyzers, editors like hocr-tools)
can consume it:

```bash
natocr scan.png -f hocr -o scan.hocr
```

### `pdf`

A searchable PDF: each page embeds the original image with an invisible text
layer laid over it, so the output looks like the scan but supports text
selection, copy, and search - the same trick tesseract's PDF output uses:

```bash
natocr scan.png -f pdf -o scan.pdf
natocr 'scans/*.png' -f pdf -o out/     # one pdf per input
```

PDF is binary, so writing it to an interactive terminal is refused - pipe it or
use `-o`.

## Choosing where output goes

Without `-o/--output` everything streams to stdout. With it:

```bash
natocr scan.png -o scan.txt             # single input: a file path
natocr '*.png' -f json -o results/      # multiple inputs: a directory
```

For a directory, each output is named after its input with the format's
extension (`.txt`, `.json`, `.hocr`, `.pdf`) - `scan.png` becomes `scan.txt`,
and stdin becomes `stdin.txt`. The directory is created if it doesn't exist.

!!! note
    `hocr` and `pdf` produce one document per input, so multiple inputs
    require `-o DIR`. `text`, `table`, and `json` stream fine either way.

## Language

`-l/--lang` picks the recognition language (default `en`), and
`--list-languages` prints what the current machine supports - the same live
query as [`supported_languages`](usage.md#supported-languages). On a terminal
it renders as a table; piped, it's plain lines for `grep`:

```bash
natocr menu.jpg --lang fr
natocr --list-languages
natocr --list-languages | grep zh
```

## Filtering by confidence

`--min-confidence` drops detections below a threshold before rendering, the
CLI face of [`OCRResult.filter()`](usage.md#filtering-by-confidence):

```bash
natocr blurry.jpg --min-confidence 0.8
```

!!! note
    Windows Runtime OCR doesn't report confidence, so on Windows detections
    have no score and are kept regardless (they can't be judged).

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | every input processed successfully |
| `1` | at least one input failed (unreadable file, backend error, missing `cli` extra) |
| `2` | usage error (bad flag, unmatched glob, missing `-o` for binary output) |
