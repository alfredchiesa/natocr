"""tests for the data models"""

import pytest

from natocr.models import BoundingBox, OCRResult, TextElement, TextLine


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


class TestTextLines:
    def test_aggregates_text_confidence_and_bounds_per_line(self):
        a = TextElement(
            text="hello", bounds=BoundingBox(0, 0, 10, 10), confidence=0.8
        )
        b = TextElement(
            text="world", bounds=BoundingBox(20, 1, 10, 10), confidence=0.6
        )
        result = OCRResult(text="ignored", elements=[a, b])
        lines = result.text_lines
        assert len(lines) == 1
        line = lines[0]
        assert isinstance(line, TextLine)
        assert line.text == "hello world"
        assert line.confidence == pytest.approx(0.7)  # mean of 0.8 and 0.6
        # union box wraps both elements
        assert line.bounds.bounds == (0, 0, 30, 11)
        assert line.elements == [a, b]

    def test_confidence_ignores_missing_scores(self):
        scored = TextElement(text="a", bounds=BoundingBox(0, 0, 10, 10), confidence=0.9)
        unscored = TextElement(text="b", bounds=BoundingBox(12, 0, 10, 10))
        result = OCRResult(text="ignored", elements=[scored, unscored])
        # only the scored element counts toward the mean
        assert result.text_lines[0].confidence == pytest.approx(0.9)

    def test_confidence_none_when_no_scores(self):
        elem = TextElement(text="a", bounds=BoundingBox(0, 0, 10, 10))
        result = OCRResult(text="ignored", elements=[elem])
        assert result.text_lines[0].confidence is None

    def test_empty_without_elements(self):
        assert OCRResult(text="just text").text_lines == []


class TestParagraphs:
    def test_groups_lines_by_vertical_gap(self):
        # two stacked lines, then a big gap, then a third line
        l1 = TextElement(text="one", bounds=BoundingBox(0, 0, 10, 10), confidence=0.9)
        l2 = TextElement(text="two", bounds=BoundingBox(0, 12, 10, 10), confidence=0.7)
        l3 = TextElement(text="far", bounds=BoundingBox(0, 100, 10, 10), confidence=0.5)
        result = OCRResult(text="ignored", elements=[l1, l2, l3])
        paras = result.paragraphs
        assert len(paras) == 2
        # first paragraph stacks the two close lines, newline-joined
        assert paras[0].text == "one\ntwo"
        assert paras[0].confidence == pytest.approx(0.8)  # mean of 0.9 and 0.7
        assert paras[1].text == "far"

    def test_empty_without_elements(self):
        assert OCRResult(text="just text").paragraphs == []


class TestFilter:
    def _result(self):
        high = TextElement(text="hi", bounds=BoundingBox(0, 0, 10, 10), confidence=0.9)
        low = TextElement(text="lo", bounds=BoundingBox(0, 20, 10, 10), confidence=0.4)
        unknown = TextElement(text="??", bounds=BoundingBox(0, 40, 10, 10))
        return OCRResult(text="ignored", elements=[high, low, unknown]), high, unknown

    def test_drops_below_threshold_keeps_unknown_by_default(self):
        result, high, unknown = self._result()
        out = result.filter(0.5)
        # low (0.4) drops; high (0.9) and the unscored one stay
        assert out.elements == [high, unknown]
        assert out.text == "hi ??"
        assert out.confidence == pytest.approx(0.9)  # unknown ignored in the mean

    def test_drop_unknown_removes_unscored_elements(self):
        result, high, _ = self._result()
        out = result.filter(0.5, drop_unknown=True)
        assert out.elements == [high]

    def test_returns_new_result_without_mutating(self):
        result, _, _ = self._result()
        out = result.filter(0.5)
        assert out is not result
        assert len(result.elements) == 3  # original untouched
