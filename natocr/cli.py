"""
command line interface - `natocr scan.png` straight from the shell

the cli's dependencies (typer + rich) live in an optional extra so
library-only installs stay lean: pip install 'natocr[cli]'
"""

import glob
import html
import io
import json
import os
import sys
from enum import Enum
from typing import List, Optional, Tuple

from PIL import Image, ImageSequence

from . import __version__
from .core import OCR
from .models import OCRResult

# the natocr command is always installed, so point users at the extra
# instead of tracebacking when typer/rich aren't there
try:
    import typer
    from rich.console import Console
    from rich.progress import track
    from rich.table import Table
except ImportError:
    typer = None


class OutputFormat(str, Enum):
    text = "text"
    json = "json"
    hocr = "hocr"
    pdf = "pdf"
    table = "table"


# output extension per format, used when writing into a directory
_EXTENSIONS = {
    "text": ".txt",
    "json": ".json",
    "hocr": ".hocr",
    "pdf": ".pdf",
    "table": ".txt",
}


def _expand_inputs(patterns: List[str]) -> List[str]:
    """resolve args to concrete paths, expanding globs the shell didn't"""
    paths = []
    for pattern in patterns:
        if pattern == "-" or os.path.exists(pattern):
            paths.append(pattern)
            continue
        matches = sorted(glob.glob(pattern, recursive=True))
        if not matches:
            raise FileNotFoundError(pattern)
        paths.extend(matches)
    return paths


def _load_pages(path: str) -> List[Image.Image]:
    """explode an input into standalone rgb page images"""
    if path == "-":
        image = Image.open(io.BytesIO(sys.stdin.buffer.read()))
    else:
        image = Image.open(path)
    # iterator frames share one underlying image, so convert() copies each
    # page out before the next seek clobbers it
    return [frame.convert("RGB") for frame in ImageSequence.Iterator(image)]


def _derived_name(path: str, fmt: str) -> str:
    """output filename for a given input when writing into a directory"""
    stem = "stdin" if path == "-" else os.path.splitext(os.path.basename(path))[0]
    return stem + _EXTENSIONS[fmt]


def _stdout_is_tty() -> bool:
    try:
        return sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def _render_text(results: List[OCRResult]) -> str:
    # form feed between pages, same convention tesseract uses
    return "\f".join(result.text for result in results) + "\n"


def _render_json(path: str, language: str, results: List[OCRResult]) -> str:
    # one compact json object per input (ndjson), stable shape for jq
    document = {
        "file": path,
        "language": language,
        "pages": [
            {
                "text": result.text,
                "confidence": result.confidence,
                "lines": result.lines,
                "elements": [
                    {
                        "text": element.text,
                        "confidence": element.confidence,
                        "bounds": {
                            "x": element.bounds.x,
                            "y": element.bounds.y,
                            "width": element.bounds.width,
                            "height": element.bounds.height,
                        },
                    }
                    for element in result.elements
                ],
            }
            for result in results
        ],
    }
    return json.dumps(document, ensure_ascii=False) + "\n"


def _hocr_bbox(bounds) -> str:
    return (
        f"bbox {int(bounds.x)} {int(bounds.y)} "
        f"{int(bounds.x + bounds.width)} {int(bounds.y + bounds.height)}"
    )


def _render_hocr(
    name: str,
    language: str,
    pages: List[Tuple[OCRResult, Tuple[int, int]]],
) -> str:
    """render results as an hocr document (xhtml with layout metadata)"""
    lang = html.escape(language, quote=True)
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"'
        ' "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">',
        f'<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="{lang}" lang="{lang}">',
        " <head>",
        f"  <title>{html.escape(name)}</title>",
        '  <meta http-equiv="Content-Type" content="text/html;charset=utf-8"/>',
        f'  <meta name="ocr-system" content="natocr {__version__}"/>',
        '  <meta name="ocr-capabilities" content="ocr_page ocr_line ocrx_word"/>',
        " </head>",
        " <body>",
    ]
    for pageno, (result, (width, height)) in enumerate(pages, start=1):
        title = (
            f"image &quot;{html.escape(name, quote=True)}&quot;; "
            f"bbox 0 0 {width} {height}; ppageno {pageno - 1}"
        )
        out.append(f'  <div class="ocr_page" id="page_{pageno}" title="{title}">')
        word_no = 0
        for line_no, line in enumerate(result.text_lines, start=1):
            out.append(
                f'   <span class="ocr_line" id="line_{pageno}_{line_no}"'
                f' title="{_hocr_bbox(line.bounds)}">'
            )
            for element in line.elements:
                word_no += 1
                title = _hocr_bbox(element.bounds)
                if element.confidence is not None:
                    title += f"; x_wconf {round(element.confidence * 100)}"
                out.append(
                    f'    <span class="ocrx_word" id="word_{pageno}_{word_no}"'
                    f' title="{title}">{html.escape(element.text)}</span>'
                )
            out.append("   </span>")
        out.append("  </div>")
    out.extend([" </body>", "</html>", ""])
    return "\n".join(out)


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _pdf_text_layer(result: OCRResult, page_height: float) -> str:
    """invisible text overlay (render mode 3) so the pdf is searchable"""
    parts = ["BT", "3 Tr"]
    for element in result.words:
        box = element.bounds
        size = max(box.height, 1.0)
        # helvetica averages roughly half the point size per glyph; stretch
        # the run horizontally so it spans the detected box
        natural_width = 0.5 * size * max(len(element.text), 1)
        scale = 100.0 * box.width / natural_width
        # pdf origin is bottom-left; ours is top-left
        baseline = page_height - box.y - box.height
        text = _pdf_escape(element.text).encode("latin-1", "replace").decode("latin-1")
        parts.append(f"/F1 {size:.2f} Tf")
        parts.append(f"{scale:.2f} Tz")
        parts.append(f"1 0 0 1 {box.x:.2f} {baseline:.2f} Tm")
        parts.append(f"({text}) Tj")
    parts.append("ET")
    return "\n".join(parts)


def _render_pdf(pages: List[Tuple[Image.Image, OCRResult]]) -> bytes:
    """build a searchable pdf: each page image with its invisible text layer"""
    # fixed object layout: 1 catalog, 2 page tree, 3 font, then an image,
    # content stream, and page object per page
    total = 3 + 3 * len(pages)
    bodies = {}

    kids = " ".join(f"{6 + 3 * i} 0 R" for i in range(len(pages)))
    bodies[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    bodies[2] = f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode()
    bodies[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"

    for i, (image, result) in enumerate(pages):
        width, height = image.size
        jpeg = io.BytesIO()
        image.save(jpeg, format="JPEG", quality=85)
        data = jpeg.getvalue()
        bodies[4 + 3 * i] = (
            f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height}"
            f" /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode"
            f" /Length {len(data)} >>\nstream\n".encode()
            + data
            + b"\nendstream"
        )
        content = (
            f"q\n{width} 0 0 {height} 0 0 cm\n/Im0 Do\nQ\n"
            + _pdf_text_layer(result, height)
        ).encode("latin-1", "replace")
        bodies[5 + 3 * i] = (
            f"<< /Length {len(content)} >>\nstream\n".encode()
            + content
            + b"\nendstream"
        )
        bodies[6 + 3 * i] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}]"
            f" /Resources << /XObject << /Im0 {4 + 3 * i} 0 R >>"
            f" /Font << /F1 3 0 R >> >> /Contents {5 + 3 * i} 0 R >>"
        ).encode()

    buf = io.BytesIO()
    buf.write(b"%PDF-1.4\n")
    offsets = {}
    for num in range(1, total + 1):
        offsets[num] = buf.tell()
        buf.write(f"{num} 0 obj\n".encode())
        buf.write(bodies[num])
        buf.write(b"\nendobj\n")
    xref = buf.tell()
    buf.write(f"xref\n0 {total + 1}\n".encode())
    buf.write(b"0000000000 65535 f \n")
    for num in range(1, total + 1):
        buf.write(f"{offsets[num]:010d} 00000 n \n".encode())
    buf.write(
        f"trailer\n<< /Size {total + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n".encode()
    )
    return buf.getvalue()


def _render(path, fmt, language, images, results):
    if fmt == "text":
        return _render_text(results)
    if fmt == "json":
        return _render_json(path, language, results)
    if fmt == "hocr":
        sizes = [image.size for image in images]
        return _render_hocr(path, language, list(zip(results, sizes)))
    return _render_pdf(list(zip(images, results)))


def main() -> int:
    """console script entry point"""
    if typer is None:
        print(
            "natocr: the command line interface needs the optional cli extra - "
            "install it with: pip install 'natocr[cli]'",
            file=sys.stderr,
        )
        return 1
    return app()


if typer is not None:

    app = typer.Typer(
        rich_markup_mode="rich",
        context_settings={"help_option_names": ["-h", "--help"]},
    )

    _EXAMPLES = """\
[bold]examples:[/bold]

  natocr scan.png                          print the recognized text

  natocr scan.png -f json | jq -r '.pages[].text'

  natocr photo.jpg -l fr                   recognize french text

  natocr 'scans/*.tiff' -f pdf -o out/     searchable pdfs, one per input

  cat scan.png | natocr -                  read the image from stdin

  natocr --list-languages                  languages this machine supports
"""

    def _version_callback(value: Optional[bool]) -> None:
        if value:
            typer.echo(f"natocr {__version__}")
            raise typer.Exit()

    def _fmt_confidence(confidence: Optional[float]) -> str:
        return f"{confidence:.2f}" if confidence is not None else "-"

    def _build_table(path: str, results: List[OCRResult]) -> Table:
        pages = "page" if len(results) == 1 else "pages"
        table = Table(
            title=f"{path} - {len(results)} {pages}",
            title_style="bold",
            header_style="bold cyan",
        )
        table.add_column("page", justify="right", style="dim", no_wrap=True)
        table.add_column("text")
        table.add_column("conf", justify="right", style="green")
        table.add_column("bounds (x, y, w, h)", style="dim")
        for pageno, result in enumerate(results, start=1):
            lines = result.text_lines
            if not lines and result.text:
                # elements without positions still get their text shown
                table.add_row(
                    str(pageno),
                    result.text,
                    _fmt_confidence(result.confidence),
                    "-",
                )
            for line in lines:
                bounds = line.bounds
                table.add_row(
                    str(pageno),
                    line.text,
                    _fmt_confidence(line.confidence),
                    f"({bounds.x:.0f}, {bounds.y:.0f},"
                    f" {bounds.width:.0f}, {bounds.height:.0f})",
                )
        return table

    def _emit_table(
        path: str, results: List[OCRResult], destination: Optional[str]
    ) -> None:
        table = _build_table(path, results)
        if destination is None:
            Console().print(table)
        else:
            with open(destination, "w", encoding="utf-8") as fh:
                Console(file=fh, width=120).print(table)

    def _emit(payload, destination: Optional[str]) -> None:
        if destination is None:
            # typer.echo writes bytes to the binary stream, str as text
            typer.echo(payload, nl=False)
        elif isinstance(payload, bytes):
            with open(destination, "wb") as fh:
                fh.write(payload)
        else:
            with open(destination, "w", encoding="utf-8") as fh:
                fh.write(payload)

    def _print_languages(ocr: OCR) -> None:
        console = Console()
        if not console.is_terminal:
            # plain lines when piped so grep and friends stay happy
            for language in ocr.supported_languages:
                typer.echo(language)
            return
        table = Table(
            title=f"supported languages ({ocr.platform})",
            title_style="bold",
            header_style="bold cyan",
        )
        table.add_column("#", justify="right", style="dim")
        table.add_column("language", style="cyan")
        for i, language in enumerate(ocr.supported_languages, start=1):
            table.add_row(str(i), language)
        console.print(table)

    @app.command(epilog=_EXAMPLES)
    def run(
        inputs: Optional[List[str]] = typer.Argument(
            None,
            metavar="[IMAGE]...",
            help="image files, glob patterns, or - for stdin",
        ),
        lang: str = typer.Option(
            "en", "--lang", "-l", help="recognition language"
        ),
        fmt: OutputFormat = typer.Option(
            OutputFormat.text, "--format", "-f", help="output format"
        ),
        output: Optional[str] = typer.Option(
            None,
            "--output",
            "-o",
            metavar="PATH",
            help="output file, or a directory when there are multiple inputs",
        ),
        min_confidence: Optional[float] = typer.Option(
            None,
            "--min-confidence",
            min=0.0,
            max=1.0,
            metavar="N",
            help="drop detections below this confidence (0.0-1.0)",
        ),
        list_languages: bool = typer.Option(
            False,
            "--list-languages",
            help="print the languages the current platform supports and exit",
        ),
        version: Optional[bool] = typer.Option(
            None,
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="print the version and exit",
        ),
    ) -> None:
        """ocr images with the operating system's native engine"""
        # soft_wrap keeps long paths in error messages on one line
        err = Console(stderr=True, soft_wrap=True)

        if not inputs and not list_languages:
            err.print("[red]error:[/red] at least one image (or -) is required")
            raise typer.Exit(2)

        try:
            ocr = OCR(language=lang)
        except RuntimeError as exc:
            err.print(f"[red]error:[/red] {exc}")
            raise typer.Exit(1)

        if list_languages:
            _print_languages(ocr)
            raise typer.Exit()

        try:
            paths = _expand_inputs(inputs)
        except FileNotFoundError as exc:
            err.print(f"[red]error:[/red] no such file or glob match: {exc.args[0]}")
            raise typer.Exit(2)

        # -o is a directory when there are several inputs (or it already is
        # one), otherwise a plain file path; no -o streams to stdout
        output_dir = output_file = None
        if output:
            if len(paths) > 1 or os.path.isdir(output):
                output_dir = output
                try:
                    os.makedirs(output_dir, exist_ok=True)
                except (FileExistsError, NotADirectoryError):
                    err.print(f"[red]error:[/red] not a directory: {output}")
                    raise typer.Exit(2)
            else:
                output_file = output
        else:
            if len(paths) > 1 and fmt in (OutputFormat.hocr, OutputFormat.pdf):
                err.print(
                    f"[red]error:[/red] --format {fmt.value} with multiple"
                    " inputs needs --output DIR"
                )
                raise typer.Exit(2)
            if fmt is OutputFormat.pdf and _stdout_is_tty():
                err.print(
                    "[red]error:[/red] refusing to write pdf binary to a"
                    " terminal - pipe it or use -o"
                )
                raise typer.Exit(2)

        # progress lives on stderr and only for multi-file runs writing to
        # files, so stdout streams stay clean for pipes
        iterator = paths
        if output_dir and len(paths) > 1 and err.is_terminal:
            iterator = track(
                paths, description="recognizing", console=err, transient=True
            )

        failed = False
        for path in iterator:
            try:
                images = _load_pages(path)
                results = [ocr.recognize(image)[0] for image in images]
            except (OSError, ValueError) as exc:
                # report and keep going so one bad file doesn't sink the batch
                err.print(f"[red]error:[/red] {path}: {exc}")
                failed = True
                continue
            if min_confidence is not None:
                results = [result.filter(min_confidence) for result in results]
            if output_dir:
                destination = os.path.join(output_dir, _derived_name(path, fmt.value))
            else:
                destination = output_file
            if fmt is OutputFormat.table:
                _emit_table(path, results, destination)
            else:
                _emit(_render(path, fmt.value, lang, images, results), destination)

        if failed:
            raise typer.Exit(1)


if __name__ == "__main__":
    sys.exit(main())
