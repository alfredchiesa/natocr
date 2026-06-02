"""tests for the data models"""

from natocr.models import BoundingBox, OCRResult, TextElement


class TestBoundingBox:
    def test_bounds_returns_tuple(self):
        box = BoundingBox(x=1.0, y=2.0, width=3.0, height=4.0)
        assert box.bounds == (1.0, 2.0, 3.0, 4.0)


class TestTextElement:
    def test_defaults_confidence_to_none(self):
        elem = TextElement(text="hi", bounds=BoundingBox(0, 0, 1, 1))
        assert elem.confidence is None

    def test_stores_confidence(self):
        elem = TextElement(text="hi", bounds=BoundingBox(0, 0, 1, 1), confidence=0.9)
        assert elem.confidence == 0.9


class TestOCRResult:
    def test_post_init_defaults_elements_to_empty_list(self):
        result = OCRResult(text="hi")
        assert result.elements == []

    def test_post_init_keeps_provided_elements(self):
        elem = TextElement(text="hi", bounds=BoundingBox(0, 0, 1, 1))
        result = OCRResult(text="hi", elements=[elem])
        assert result.elements == [elem]

    def test_words_filters_whitespace_only(self):
        good = TextElement(text="hi", bounds=BoundingBox(0, 0, 1, 1))
        blank = TextElement(text="   ", bounds=BoundingBox(0, 0, 1, 1))
        result = OCRResult(text="hi", elements=[good, blank])
        assert result.words == [good]

    def test_lines_no_elements_with_text(self):
        result = OCRResult(text="just text")
        assert result.lines == ["just text"]

    def test_lines_no_elements_no_text(self):
        result = OCRResult(text="")
        assert result.lines == []

    def test_lines_groups_close_y_into_single_line(self):
        a = TextElement(text="hello", bounds=BoundingBox(x=0, y=0, width=10, height=10))
        b = TextElement(text="world", bounds=BoundingBox(x=20, y=1, width=10, height=10))
        result = OCRResult(text="ignored", elements=[a, b])
        assert result.lines == ["hello world"]

    def test_lines_splits_distant_y_into_multiple_lines(self):
        top = TextElement(text="top", bounds=BoundingBox(x=0, y=0, width=10, height=10))
        bottom = TextElement(
            text="bottom", bounds=BoundingBox(x=0, y=100, width=10, height=10)
        )
        # pass out of order to also exercise the (y, x) sort
        result = OCRResult(text="ignored", elements=[bottom, top])
        assert result.lines == ["top", "bottom"]
