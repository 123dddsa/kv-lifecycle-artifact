#!/usr/bin/env python3
"""Package an anonymous artifact and fail if internal paths leak.

Usage:
    python scripts/package_artifact.py [--out PATH]

The archive excludes VCS/venv/cache directories and scans every text file for
known local-path or username markers. Exit code 1 on a leak.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDE_DIRS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    ".venv",
    "dist",
    "build",
    "node_modules",
}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".zip"}
LEAK_MARKERS = (
    "<DRIVE>\Users\\",
    "<MOUNT>/<USER_HOME>/",
    "\\Users\\",
)


def iter_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
        if path.suffix in EXCLUDE_SUFFIXES:
            continue
        files.append(path)
    return sorted(files)


def is_text(path: Path) -> bool:
    try:
        path.read_text(encoding="utf-8")
        return True
    except UnicodeDecodeError:
        return False


def scan_leaks(files: list[Path]) -> list[str]:
    leaks: list[str] = []
    for path in files:
        if path == Path(__file__).resolve():
            continue  # this script contains the marker list itself
        if not is_text(path):
            continue
        text = path.read_text(encoding="utf-8")
        for marker in LEAK_MARKERS:
            if marker in text:
                leaks.append(f"{path.relative_to(ROOT)}: {marker!r}")
    return leaks


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        default=str(ROOT.parent / "kvc_lifecycle_artifact_20261117.zip"),
    )
    args = parser.parse_args()
    out = Path(args.out)
    files = iter_files()
    leaks = scan_leaks(files)
    if leaks:
        print("LEAKS FOUND:")
        for item in leaks:
            print(f"  {item}")
        return 1

    manifest = {
        "name": "kvc-lifecycle",
        "version": "0.8.0",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "files": [
            {"path": str(path.relative_to(ROOT)), "sha256": sha256(path)}
            for path in files
        ],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, arcname=str(Path("kvc-lifecycle") / path.relative_to(ROOT)))
        archive.writestr("kvc-lifecycle/ARTIFACT_MANIFEST.json", json.dumps(manifest, indent=2))

    print(f"wrote {out} ({out.stat().st_size} bytes, {len(files)} files)")
    print(f"sha256 {sha256(out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

