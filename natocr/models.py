from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class BoundingBox:
    x: float
    y: float
    width: float
    height: float

    @property
    def bounds(self) -> Tuple[float, float, float, float]:
        return (self.x, self.y, self.width, self.height)


@dataclass
class TextElement:
    text: str
    bounds: BoundingBox
    confidence: Optional[float] = None


@dataclass
class OCRResult:
    text: str
    confidence: Optional[float] = None
    elements: List[TextElement] = None
