"""
data models for ocr results
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class BoundingBox:
    """bounding box coordinates for detected text"""

    x: float
    y: float
    width: float
    height: float

    @property
    def bounds(self) -> Tuple[float, float, float, float]:
        """return bounds as (x, y, width, height) tuple"""
        return (self.x, self.y, self.width, self.height)


@dataclass
class TextElement:
    """individual text element with bounding box and confidence"""

    text: str
    bounds: BoundingBox
    confidence: Optional[float] = None


@dataclass
class OCRResult:
    """complete ocr result containing all detected text"""

    text: str
    confidence: Optional[float] = None
    elements: List[TextElement] = None

    def __post_init__(self):
        """initialize elements list if not provided"""
        if self.elements is None:
            self.elements = []

    @property
    def words(self) -> List[TextElement]:
        """get all word-level elements"""
        return [elem for elem in self.elements if elem.text.strip()]

    @property
    def lines(self) -> List[str]:
        """get text organized by lines (simplified)"""
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
