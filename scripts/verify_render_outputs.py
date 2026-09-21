#!/usr/bin/env python3
"""Fail when a required mechanical PNG is missing, blank, or near-uniform."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageStat


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "mechanical" / "generated"
REQUIRED = (
    "render_top.png",
    "render_end.png",
    "render_side.png",
    "render_iso.png",
    "render_j1_closeup.png",
    "render_j2_closeup.png",
)
BACKGROUND = (245, 245, 245)


def check(path: Path) -> tuple[int, int, float]:
    with Image.open(path) as source:
        image = source.convert("RGB")
    if image.size != (1200, 900):
        raise ValueError(f"unexpected image size {image.size}")
    content = image.crop((0, 35, image.width, image.height))
    foreground = sum(pixel != BACKGROUND for pixel in content.getdata())
    minimum = int(content.width * content.height * 0.01)
    colors = content.getcolors(maxcolors=1_000_000)
    unique = len(colors or [])
    deviation = sum(ImageStat.Stat(content).stddev) / 3.0
    if foreground < minimum:
        raise ValueError(f"only {foreground} foreground pixels; expected at least {minimum}")
    if unique < 5 or deviation < 4.0:
        raise ValueError(f"near-uniform image: {unique} colors, deviation {deviation:.2f}")
    return foreground, unique, deviation


def main() -> int:
    failed = False
    for filename in REQUIRED:
        path = OUTPUT / filename
        try:
            if not path.is_file():
                raise ValueError("file is missing")
            foreground, unique, deviation = check(path)
            print(
                f"{filename}: PASS; foreground={foreground}, "
                f"colors={unique}, deviation={deviation:.2f}"
            )
        except (OSError, ValueError) as exc:
            failed = True
            print(f"{filename}: FAIL; {exc}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
