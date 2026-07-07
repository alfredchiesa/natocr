"""tests for the natocr command line interface in cli.py"""

import io
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from PIL import Image
from typer.testing import CliRunner

from natocr import __version__, cli
from natocr.models import BoundingBox, OCRResult, TextElement

# click 8.2 dropped mix_stderr and separates stderr by default; 8.1 needs it
try:
    runner = CliRunner(mix_stderr=False)
except TypeError:
    runner = CliRunner()


def _forced_terminal_console(*args, **kwargs):
    """a rich console that believes it's on a tty, for the pretty paths"""
    from rich.console import Console

    kwargs["force_terminal"] = True
    return Console(*args, **kwargs)


def _stderr(result):
    """captured stderr, falling back to combined output on odd click builds"""
    try:
        return result.stderr
    except ValueError:
        return result.output


def _result():
    """a small two-word page with bounds and confidences"""
    return OCRResult(
        text="hello world",
        confidence=0.9,
        elements=[
            TextElement("hello", BoundingBox(10.0, 10.0, 50.0, 12.0), 0.95),
            TextElement("world", BoundingBox(70.0, 10.0, 50.0, 12.0), 0.85),
        ],
    )


class FakeOCR:
    """stand-in for the real OCR facade - no native backend needed"""

    supported_languages = ["en-US", "fr-FR"]
    platform = "darwin"

    def __init__(self, language="en"):
        self.language = language
        self.calls = []

    def recognize(self, image):
        self.calls.append(image)
        return [_result()]


@pytest.fixture
def fake_ocr(monkeypatch):
    """patch cli.OCR with the fake; returns the list of created instances"""
    created = []

    def factory(language="en"):
        ocr = FakeOCR(language)
        created.append(ocr)
        return ocr

    monkeypatch.setattr(cli, "OCR", factory)
    return created


@pytest.fixture
def png(tmp_path):
    path = tmp_path / "scan.png"
    Image.new("RGB", (200, 100), "white").save(path)
    return str(path)


class TestArguments:
    def test_no_inputs_is_a_usage_error(self, fake_ocr):
        result = runner.invoke(cli.app, [])
        assert result.exit_code == 2
        assert "at least one image" in _stderr(result)

    def test_version_prints_and_exits_zero(self):
        result = runner.invoke(cli.app, ["--version"])
        assert result.exit_code == 0
        assert result.output.strip() == f"natocr {__version__}"

    def test_unknown_format_is_rejected(self, fake_ocr, png):
        result = runner.invoke(cli.app, [png, "--format", "yaml"])
        assert result.exit_code == 2

    def test_min_confidence_out_of_range_is_rejected(self, fake_ocr, png):
        result = runner.invoke(cli.app, [png, "--min-confidence", "1.5"])
        assert result.exit_code == 2

    def test_missing_file_is_a_usage_error(self, fake_ocr):
        result = runner.invoke(cli.app, ["nope.png"])
        assert result.exit_code == 2
        assert "nope.png" in _stderr(result)

    def test_help_shows_examples(self):
        result = runner.invoke(cli.app, ["--help"])
        assert result.exit_code == 0
        assert "examples" in result.output


class TestTextOutput:
    def test_prints_recognized_text(self, fake_ocr, png):
        result = runner.invoke(cli.app, [png])
        assert result.exit_code == 0
        assert result.output == "hello world\n"

    def test_language_is_forwarded(self, fake_ocr, png):
        runner.invoke(cli.app, [png, "--lang", "fr"])
        assert fake_ocr[0].language == "fr"

    def test_multipage_input_joins_pages_with_form_feed(self, fake_ocr, tmp_path):
        path = tmp_path / "doc.tiff"
        Image.new("RGB", (20, 15), "white").save(
            path,
            save_all=True,
            append_images=[Image.new("RGB", (20, 15), "black")],
        )
        result = runner.invoke(cli.app, [str(path)])
        assert result.exit_code == 0
        assert result.output == "hello world\fhello world\n"
        # one recognize call per page
        assert len(fake_ocr[0].calls) == 2

    def test_multiple_inputs_are_streamed_in_order(self, fake_ocr, png):
        result = runner.invoke(cli.app, [png, png])
        assert result.exit_code == 0
        assert result.output == "hello world\nhello world\n"


class TestJsonOutput:
    def test_shape(self, fake_ocr, png):
        result = runner.invoke(cli.app, [png, "-f", "json"])
        assert result.exit_code == 0
        document = json.loads(result.output)
        assert document["file"] == png
        assert document["language"] == "en"
        page = document["pages"][0]
        assert page["text"] == "hello world"
        assert page["confidence"] == 0.9
        assert page["lines"] == ["hello world"]
        assert page["elements"][0] == {
            "text": "hello",
            "confidence": 0.95,
            "bounds": {"x": 10.0, "y": 10.0, "width": 50.0, "height": 12.0},
        }

    def test_multiple_inputs_emit_one_json_line_each(self, fake_ocr, png):
        result = runner.invoke(cli.app, [png, png, "-f", "json"])
        assert result.exit_code == 0
        lines = result.output.splitlines()
        assert len(lines) == 2
        assert all(json.loads(line)["file"] == png for line in lines)

    def test_min_confidence_filters_elements(self, fake_ocr, png):
        result = runner.invoke(cli.app, [png, "-f", "json", "--min-confidence", "0.9"])
        assert result.exit_code == 0
        page = json.loads(result.output)["pages"][0]
        assert page["text"] == "hello"
        assert [e["text"] for e in page["elements"]] == ["hello"]


class TestTableOutput:
    def test_renders_a_rich_table(self, fake_ocr, png):
        result = runner.invoke(cli.app, [png, "-f", "table"])
        assert result.exit_code == 0
        assert "hello world" in result.output
        assert "0.90" in result.output
        # rich draws box borders around the table
        assert "─" in result.output

    def test_table_written_to_file(self, fake_ocr, png, tmp_path):
        out = tmp_path / "result.txt"
        result = runner.invoke(cli.app, [png, "-f", "table", "-o", str(out)])
        assert result.exit_code == 0
        assert "hello world" in out.read_text(encoding="utf-8")

    def test_table_shows_text_even_without_positioned_elements(self, monkeypatch, png):
        class BareOCR(FakeOCR):
            def recognize(self, image):
                return [OCRResult(text="just text", confidence=None)]

        monkeypatch.setattr(cli, "OCR", BareOCR)
        result = runner.invoke(cli.app, [png, "-f", "table"])
        assert result.exit_code == 0
        assert "just text" in result.output


class TestHocrOutput:
    def test_is_wellformed_xml_with_expected_classes(self, fake_ocr, png):
        result = runner.invoke(cli.app, [png, "-f", "hocr"])
        assert result.exit_code == 0
        root = ET.fromstring(result.output)
        assert root.tag == "{http://www.w3.org/1999/xhtml}html"
        assert 'class="ocr_page"' in result.output
        assert 'class="ocr_line"' in result.output
        assert 'class="ocrx_word"' in result.output

    def test_page_title_carries_image_and_bbox(self, fake_ocr, png):
        result = runner.invoke(cli.app, [png, "-f", "hocr"])
        # the fixture png is 200x100
        assert "bbox 0 0 200 100" in result.output
        assert "ppageno 0" in result.output

    def test_words_carry_bbox_and_confidence(self, fake_ocr, png):
        result = runner.invoke(cli.app, [png, "-f", "hocr"])
        assert 'title="bbox 10 10 60 22; x_wconf 95">hello</span>' in result.output
        assert "x_wconf 85" in result.output

    def test_multiple_inputs_without_output_dir_is_an_error(self, fake_ocr, png):
        result = runner.invoke(cli.app, [png, png, "-f", "hocr"])
        assert result.exit_code == 2


class TestPdfOutput:
    def test_writes_a_searchable_pdf(self, fake_ocr, png, tmp_path):
        out = tmp_path / "scan.pdf"
        result = runner.invoke(cli.app, [png, "-f", "pdf", "-o", str(out)])
        assert result.exit_code == 0
        data = out.read_bytes()
        assert data.startswith(b"%PDF-1.4")
        assert data.rstrip().endswith(b"%%EOF")
        # jpeg-compressed page image plus the invisible text layer
        assert b"/DCTDecode" in data
        assert b"(hello) Tj" in data
        assert b"3 Tr" in data

    def test_stdout_pipe_is_allowed(self, fake_ocr, png):
        result = runner.invoke(cli.app, [png, "-f", "pdf"])
        assert result.exit_code == 0
        assert result.stdout_bytes.startswith(b"%PDF-1.4")

    def test_stdout_tty_is_refused(self, fake_ocr, png, monkeypatch):
        monkeypatch.setattr(cli, "_stdout_is_tty", lambda: True)
        result = runner.invoke(cli.app, [png, "-f", "pdf"])
        assert result.exit_code == 2
        assert "refusing" in _stderr(result)

    def test_multipage_pdf_has_one_page_object_per_page(self, fake_ocr, tmp_path):
        path = tmp_path / "doc.tiff"
        Image.new("RGB", (20, 15), "white").save(
            path,
            save_all=True,
            append_images=[Image.new("RGB", (20, 15), "black")],
        )
        out = tmp_path / "doc.pdf"
        result = runner.invoke(cli.app, [str(path), "-f", "pdf", "-o", str(out)])
        assert result.exit_code == 0
        data = out.read_bytes()
        assert data.count(b"/Type /Page ") == 2
        assert b"/Count 2" in data


class TestOutputRouting:
    def test_output_file(self, fake_ocr, png, tmp_path):
        out = tmp_path / "result.txt"
        result = runner.invoke(cli.app, [png, "-o", str(out)])
        assert result.exit_code == 0
        assert out.read_text(encoding="utf-8") == "hello world\n"

    def test_output_existing_dir_derives_the_name(self, fake_ocr, png, tmp_path):
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        result = runner.invoke(cli.app, [png, "-o", str(out_dir)])
        assert result.exit_code == 0
        assert (out_dir / "scan.txt").read_text(encoding="utf-8") == "hello world\n"

    def test_output_dir_is_created_for_multiple_inputs(self, fake_ocr, tmp_path):
        for name in ("a.png", "b.png"):
            Image.new("RGB", (10, 10), "white").save(tmp_path / name)
        out_dir = tmp_path / "results"
        args = [str(tmp_path / "a.png"), str(tmp_path / "b.png")]
        result = runner.invoke(cli.app, [*args, "-f", "json", "-o", str(out_dir)])
        assert result.exit_code == 0
        assert (out_dir / "a.json").exists()
        assert (out_dir / "b.json").exists()

    def test_output_pointing_at_a_file_with_multiple_inputs_errors(
        self, fake_ocr, png, tmp_path
    ):
        clash = tmp_path / "clash"
        clash.write_text("already a file")
        result = runner.invoke(cli.app, [png, png, "-o", str(clash)])
        assert result.exit_code == 2
        assert "not a directory" in _stderr(result)


class TestGlobInputs:
    def test_pattern_expands_sorted(self, fake_ocr, tmp_path):
        for name in ("b.png", "a.png"):
            Image.new("RGB", (10, 10), "white").save(tmp_path / name)
        result = runner.invoke(cli.app, [str(tmp_path / "*.png"), "-f", "json"])
        assert result.exit_code == 0
        files = [json.loads(line)["file"] for line in result.output.splitlines()]
        assert files == [str(tmp_path / "a.png"), str(tmp_path / "b.png")]

    def test_unmatched_pattern_is_a_usage_error(self, fake_ocr, tmp_path):
        result = runner.invoke(cli.app, [str(tmp_path / "*.bmp")])
        assert result.exit_code == 2


class TestStdinInput:
    def test_dash_reads_image_bytes_from_stdin(self, fake_ocr):
        buf = io.BytesIO()
        Image.new("RGB", (10, 10), "white").save(buf, format="PNG")
        result = runner.invoke(cli.app, ["-", "-f", "json"], input=buf.getvalue())
        assert result.exit_code == 0
        assert json.loads(result.output)["file"] == "-"


class TestErrors:
    def test_bad_file_reports_and_batch_continues(self, fake_ocr, png, tmp_path):
        bad = tmp_path / "bad.png"
        bad.write_text("not an image")
        result = runner.invoke(cli.app, [str(bad), png])
        assert result.exit_code == 1
        assert "bad.png" in _stderr(result)
        # the good file still made it through
        assert result.output.endswith("hello world\n")

    def test_backend_init_failure_exits_one(self, monkeypatch, png):
        def boom(language="en"):
            raise RuntimeError("unsupported platform: linux")

        monkeypatch.setattr(cli, "OCR", boom)
        result = runner.invoke(cli.app, [png])
        assert result.exit_code == 1
        assert "unsupported platform" in _stderr(result)


class TestListLanguages:
    def test_prints_plain_lines_when_piped(self, fake_ocr):
        # the runner's stdout isn't a terminal, so output is grep-friendly
        result = runner.invoke(cli.app, ["--list-languages"])
        assert result.exit_code == 0
        assert result.output == "en-US\nfr-FR\n"

    def test_renders_a_table_on_a_terminal(self, fake_ocr, monkeypatch):
        monkeypatch.setattr(cli, "Console", _forced_terminal_console)
        result = runner.invoke(cli.app, ["--list-languages"])
        assert result.exit_code == 0
        # rich may wrap the title, so check the parts and the table borders
        assert "languages" in result.output
        assert "en-US" in result.output
        assert "─" in result.output


class TestProgress:
    def test_multi_file_dir_output_shows_progress_on_stderr(
        self, fake_ocr, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(cli, "Console", _forced_terminal_console)
        for name in ("a.png", "b.png"):
            Image.new("RGB", (10, 10), "white").save(tmp_path / name)
        out_dir = tmp_path / "results"
        args = [str(tmp_path / "a.png"), str(tmp_path / "b.png")]
        result = runner.invoke(cli.app, [*args, "-o", str(out_dir)])
        assert result.exit_code == 0
        # the outputs landed despite the progress bar on stderr
        assert (out_dir / "a.txt").exists()
        assert (out_dir / "b.txt").exists()


class TestOptionalDependencyGuard:
    def test_main_without_typer_points_at_the_cli_extra(self, monkeypatch, capsys):
        monkeypatch.setattr(cli, "typer", None)
        assert cli.main() == 1
        assert "natocr[cli]" in capsys.readouterr().err

    def test_main_dispatches_to_the_typer_app(self, monkeypatch):
        calls = []
        monkeypatch.setattr(cli, "app", lambda: calls.append(True) or 0)
        assert cli.main() == 0
        assert calls == [True]


class TestModuleEntryPoint:
    def test_python_dash_m_natocr_runs(self):
        # --version exits before any backend is touched, so this is safe anywhere
        proc = subprocess.run(
            [sys.executable, "-m", "natocr", "--version"],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        assert proc.returncode == 0
        assert proc.stdout.strip() == f"natocr {__version__}"
