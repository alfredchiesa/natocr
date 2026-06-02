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

    @property
    def lines(self) -> List[str]:
        """Detected text grouped into lines by vertical position.

        Elements whose ``y`` are close together are treated as one line and
        joined left-to-right. Falls back to ``[text]`` (or ``[]``) when there
        are no elements.
        """
        if not self.elements:
            return [self.text] if self.text else []

        # group elements by approximate y-coordinate for line detection
        lines = []
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
                    line_text = " ".join(elem.text for elem in current_line)
                    lines.append(line_text)
                current_line = [elem]
                current_y = elem.bounds.y

        if current_line:
            line_text = " ".join(elem.text for elem in current_line)
            lines.append(line_text)

        return lines
