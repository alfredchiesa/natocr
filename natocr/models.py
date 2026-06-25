"""
data models for ocr results
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class BoundingBox:
    """Pixel-space bounding box for a piece of detected text.

    The origin is the top-left of the image, with ``y`` growing downward.

    Attributes:
        x: left edge, in pixels.
        y: top edge, in pixels.
        width: box width, in pixels.
        height: box height, in pixels.
    """

    x: float
    y: float
    width: float
    height: float

    @property
    def bounds(self) -> Tuple[float, float, float, float]:
        """The box as an ``(x, y, width, height)`` tuple."""
        return (self.x, self.y, self.width, self.height)


@dataclass
class TextElement:
    """A single detected piece of text with its location.

    Attributes:
        text: the recognized string.
        bounds: where it was found in the image.
        confidence: recognition confidence in ``0.0..1.0``, or ``None`` when the
            backend doesn't report one (Windows OCR doesn't).
    """

    text: str
    bounds: BoundingBox
    confidence: Optional[float] = None


@dataclass
class TextLine:
    """A run of detected text grouped into one line.

    The structured cousin of [`OCRResult.lines`][natocr.OCRResult.lines] - same
    grouping, but each line keeps its elements, an aggregated confidence, and
    the box that wraps them. Also the shape
    [`OCRResult.paragraphs`][natocr.OCRResult.paragraphs] returns.

    Attributes:
        text: the line's text, its elements joined left-to-right.
        elements: the detections that make up the line.
        confidence: mean confidence across the elements that report one, or
            ``None`` when none do (Windows OCR doesn't).
        bounds: the box enclosing every element in the line.
    """

    text: str
    elements: List[TextElement]
    confidence: Optional[float]
    bounds: BoundingBox


def _mean_confidence(elements: List[TextElement]) -> Optional[float]:
    """average of the confidences that exist, or none if there aren't any"""
    scores = [e.confidence for e in elements if e.confidence is not None]
    return sum(scores) / len(scores) if scores else None


def _union_bounds(elements: List[TextElement]) -> BoundingBox:
    """smallest box that wraps every element"""
    left = min(e.bounds.x for e in elements)
    top = min(e.bounds.y for e in elements)
    right = max(e.bounds.x + e.bounds.width for e in elements)
    bottom = max(e.bounds.y + e.bounds.height for e in elements)
    return BoundingBox(x=left, y=top, width=right - left, height=bottom - top)


@dataclass
class OCRResult:
    """Everything an OCR pass found in one image.

    Attributes:
        text: all detected text joined into a single string.
        confidence: average confidence across detections, or ``None`` if the
            backend doesn't report confidence.
        elements: per-detection breakdown with text, bounds, and confidence.
    """

    text: str
    confidence: Optional[float] = None
    elements: List[TextElement] = None

    def __post_init__(self):
        # default the mutable elements list when none was passed
        if self.elements is None:
            self.elements = []

    @property
    def words(self) -> List[TextElement]:
        """The elements that contain non-whitespace text."""
        return [elem for elem in self.elements if elem.text.strip()]

    def _group_lines(self) -> List[List[TextElement]]:
        """group elements into lines by vertical proximity, in reading order"""
        groups = []
        current_line = []
        current_y = None

        for elem in sorted(self.elements, key=lambda e: (e.bounds.y, e.bounds.x)):
            if (
                current_y is None
                or abs(elem.bounds.y - current_y) < elem.bounds.height * 0.5
            ):
                current_line.append(elem)
                current_y = elem.bounds.y
            else:
                if current_line:
                    groups.append(current_line)
                current_line = [elem]
                current_y = elem.bounds.y

        if current_line:
            groups.append(current_line)

        return groups

    @property
    def lines(self) -> List[str]:
        """Detected text grouped into lines by vertical position.

        Elements whose ``y`` are close together are treated as one line and
        joined left-to-right. Falls back to ``[text]`` (or ``[]``) when there
        are no elements.
        """
        if not self.elements:
            return [self.text] if self.text else []
        return [" ".join(e.text for e in group) for group in self._group_lines()]

    @property
    def text_lines(self) -> List[TextLine]:
        """Detected lines as [TextLine][natocr.TextLine] objects.

        Same grouping as [lines][natocr.OCRResult.lines], but each line carries
        its elements, an aggregated confidence (mean over the elements that
        report one), and the box that wraps them. Empty when there are no
        positioned elements.
        """
        return [
            TextLine(
                text=" ".join(e.text for e in group),
                elements=group,
                confidence=_mean_confidence(group),
                bounds=_union_bounds(group),
            )
            for group in self._group_lines()
        ]

    @property
    def paragraphs(self) -> List[TextLine]:
        """Lines merged into paragraphs by the vertical gaps between them.

        Walks the lines top-to-bottom and starts a new paragraph whenever the
        gap to the next line is more than ~1.5x the line's height. Each
        paragraph comes back in the same [TextLine][natocr.TextLine] shape - its
        ``text`` is the member lines joined by newlines, with ``confidence`` and
        ``bounds`` aggregated across all of their elements.
        """
        lines = self.text_lines
        if not lines:
            return []

        # break on a big vertical gap, otherwise keep stacking lines
        groups = [[lines[0]]]
        for prev, line in zip(lines, lines[1:]):
            gap = line.bounds.y - (prev.bounds.y + prev.bounds.height)
            if gap > prev.bounds.height * 1.5:
                groups.append([line])
            else:
                groups[-1].append(line)

        paragraphs = []
        for group in groups:
            elements = [e for line in group for e in line.elements]
            paragraphs.append(
                TextLine(
                    text="\n".join(line.text for line in group),
                    elements=elements,
                    confidence=_mean_confidence(elements),
                    bounds=_union_bounds(elements),
                )
            )
        return paragraphs

    def filter(
        self, min_confidence: float, *, drop_unknown: bool = False
    ) -> "OCRResult":
        """A copy keeping only elements at or above ``min_confidence``.

        Args:
            min_confidence: lowest confidence to keep, in ``0.0..1.0``.
            drop_unknown: what to do with elements that have no confidence
                (Windows OCR never reports one). ``False`` (the default) keeps
                them, since they can't be judged; ``True`` drops them.

        Returns:
            A new [OCRResult][natocr.OCRResult] holding the surviving elements,
            with ``text`` and ``confidence`` recomputed from them.
        """
        kept = []
        for elem in self.elements:
            if elem.confidence is None:
                if not drop_unknown:
                    kept.append(elem)
            elif elem.confidence >= min_confidence:
                kept.append(elem)

        return OCRResult(
            text=" ".join(e.text for e in kept),
            confidence=_mean_confidence(kept),
            elements=kept,
        )
