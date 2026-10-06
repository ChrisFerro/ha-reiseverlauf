"""Bundled TrueType font, so umlauts, Ø and dashes render on every system."""

from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

FONT_PATH = Path(__file__).parent / "DejaVuSans.ttf"


@lru_cache(maxsize=32)
def load_font(size: int) -> ImageFont.FreeTypeFont:
    """Return the bundled font in `size` pixels."""
    return ImageFont.truetype(FONT_PATH, max(size, 1))
