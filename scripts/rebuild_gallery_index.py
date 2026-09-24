from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Iterable, Mapping

from PIL import Image, ImageOps


ALGORITHM = "dhash64-nn-white-v1"
IMAGE_SUFFIXES = {
    ".bmp",
    ".gif",
    ".jpeg",
    ".jpg",
    ".jfif",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}


def iter_gallery_images(gallery_root: Path | str = Path("gallery")) -> list[Path]:
    """Return supported direct children of gallery/<category>/ in stable order."""
    root = Path(gallery_root)
    paths: list[Path] = []
    for category in sorted(root.iterdir(), key=lambda item: item.name):
        if not category.is_dir():
            continue
        for path in sorted(category.iterdir(), key=lambda item: item.name):
            if not path.is_file():
                continue
            if path.name.startswith(".airi-renumber-"):
                continue
            if path.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            paths.append(path)
    return paths


def perceptual_hash(path: Path | str) -> str:
    """Compute the exact dhash64-nn-white-v1 used by the Gallery plugin."""
    image_path = Path(path)
    with Image.open(image_path) as image:
        safe = ImageOps.exif_transpose(image)
        rgba = safe.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        normalized = Image.alpha_composite(background, rgba).convert("RGB")
        resized = normalized.resize((9, 8), Image.Resampling.NEAREST).convert("L")
        row_major = list(resized.getdata())

    value = 0
    for row in range(8):
        base = row * 9
        for col in range(8):
            value <<= 1
            if row_major[base + col] > row_major[base + col + 1]:
                value |= 1
    return f"{value:016x}"


def _numeric_max_index(paths: Iterable[str]) -> int:
    maximum = 0
    for raw_path in paths:
        stem = Path(raw_path).stem
        if stem.isdigit():
            maximum = max(maximum, int(stem))
    return maximum


def build_manifest_payload(
    existing: Mapping[str, object],
    hashes: Mapping[str, str],
) -> dict[str, object]:
    """Replace the full files map while preserving compatible top-level metadata."""
    if not isinstance(existing, Mapping):
        raise ValueError("existing manifest must be an object")

    version = existing.get("version", 1)
    if version != 1:
        raise ValueError(f"unsupported manifest version: {version!r}")

    algorithm = str(existing.get("algorithm", "") or "").strip()
    if algorithm and algorithm != ALGORITHM:
        raise ValueError(f"incompatible manifest algorithm: {algorithm!r}")

    files: dict[str, dict[str, str]] = {}
    for path in sorted(hashes):
        digest = str(hashes[path]).strip().lower()
        if len(digest) != 16 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ValueError(f"invalid perceptual hash for {path}: {digest!r}")
        files[path] = {"perceptual_hash": digest}

    rebuilt = dict(existing)
    rebuilt["version"] = 1
    rebuilt["algorithm"] = ALGORITHM
    rebuilt["max_index"] = _numeric_max_index(files)
    rebuilt["files"] = files
    return rebuilt


def _hash_one(path: str) -> tuple[str, str]:
    return path, perceptual_hash(path)


def rebuild_index(
    gallery_root: Path,
    manifest_path: Path,
    *,
    workers: int | None = None,
) -> dict[str, object]:
    existing = json.loads(manifest_path.read_text(encoding="utf-8"))
    images = iter_gallery_images(gallery_root)
    if not images:
        raise ValueError("no Gallery images found; refusing to replace the manifest")

    path_strings = [path.as_posix() for path in images]
    worker_count = workers or min(4, max(1, os.cpu_count() or 1))
    hashes: dict[str, str] = {}

    print(f"Hashing {len(path_strings)} Gallery images with {worker_count} worker(s)…", flush=True)
    with ProcessPoolExecutor(max_workers=worker_count) as executor:
        for index, (path, digest) in enumerate(
            executor.map(_hash_one, path_strings, chunksize=8),
            start=1,
        ):
            hashes[path] = digest
            if index % 250 == 0 or index == len(path_strings):
                print(f"  hashed {index}/{len(path_strings)}", flush=True)

    if len(hashes) != len(path_strings):
        raise RuntimeError(
            f"hash count mismatch: expected {len(path_strings)}, got {len(hashes)}"
        )

    rebuilt = build_manifest_payload(existing, hashes)
    categories = {path.split("/")[1] for path in hashes}

    temporary = manifest_path.with_name(f"{manifest_path.name}.tmp")
    temporary.write_text(
        json.dumps(rebuilt, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    temporary.replace(manifest_path)

    print(
        "Rebuilt Gallery index: "
        f"{len(categories)} categories, {len(hashes)} images, "
        f"max_index={rebuilt['max_index']}",
        flush=True,
    )
    return rebuilt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebuild gallery/gallery_index.json from every repository image."
    )
    parser.add_argument("--gallery-root", default="gallery")
    parser.add_argument("--manifest", default="gallery/gallery_index.json")
    parser.add_argument("--workers", type=int, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.workers is not None and args.workers < 1:
        raise SystemExit("--workers must be at least 1")
    rebuild_index(
        Path(args.gallery_root),
        Path(args.manifest),
        workers=args.workers,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
