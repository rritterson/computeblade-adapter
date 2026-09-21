#!/usr/bin/env python3
"""Fetch and authenticate pinned official Compute Blade reference CAD."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DIR = ROOT / "mechanical" / "reference"
UPSTREAM_COMMIT = "9c7e472f4fb5c74401d17cdc7a766254d78a32c6"
RAW_ROOT = f"https://raw.githubusercontent.com/uptime-lab/compute-blade/{UPSTREAM_COMMIT}"


@dataclass(frozen=True)
class Reference:
    name: str
    upstream_path: str
    sha256: str

    @property
    def url(self) -> str:
        return f"{RAW_ROOT}/{self.upstream_path.replace(' ', '%20')}"


REFERENCES = (
    Reference(
        "compute_blade_dev.step",
        "models/blade/v1.0-mk4/v1.0_mk4_DEV.step",
        "acc700e5cb5c6bf44ff2b0cfbfd24ef290b3ee56614e1380c0137468647d8067",
    ),
    Reference(
        "bladerunner_19in_half_body.stl",
        "models/bladerunner/19-inch/half body.stl",
        "5718b81325380055abcc9a4fd7d0dbaf881af87f03f2604858a9e5f57475dbfd",
    ),
    Reference(
        "bladerunner_19in_left_bracket.stl",
        "models/bladerunner/19-inch/left bracket.stl",
        "46e6f71310190d1bed5f0ba9bb952c10fda15dcfa626f6e4844b7b702e91b41c",
    ),
    Reference(
        "bladerunner_19in_right_bracket.stl",
        "models/bladerunner/19-inch/right bracket.stl",
        "f47f89b6606106f285bd30a76ebce8001b48d3db288d38fe323909a3442d5701",
    ),
)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-dir",
        type=Path,
        help="copy already-downloaded files from this directory instead of the network",
    )
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    for reference in REFERENCES:
        target = REFERENCE_DIR / reference.name
        if not target.exists() and not args.check_only:
            if args.source_dir:
                aliases = {
                    "bladerunner_19in_half_body.stl": "bladerunner_half_body.stl",
                    "bladerunner_19in_left_bracket.stl": "bladerunner_left_bracket.stl",
                    "bladerunner_19in_right_bracket.stl": "bladerunner_right_bracket.stl",
                }
                source = args.source_dir / aliases.get(reference.name, reference.name)
                shutil.copyfile(source, target)
            else:
                print(f"Fetching {reference.url}")
                urllib.request.urlretrieve(reference.url, target)
        if not target.exists():
            errors.append(f"missing {target.relative_to(ROOT)}")
            continue
        actual = digest(target)
        status = "OK" if actual == reference.sha256 else "HASH MISMATCH"
        print(f"{status:13} {reference.name}  sha256={actual}")
        if actual != reference.sha256:
            errors.append(f"SHA-256 mismatch for {reference.name}")

    if errors:
        print("Reference CAD validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(f"Pinned upstream commit: {UPSTREAM_COMMIT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

