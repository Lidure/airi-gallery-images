import json
import re
import subprocess
from pathlib import Path


ALGORITHM = "dhash64-nn-white-v1"
IMAGE_SUFFIXES = {".bmp", ".gif", ".jpeg", ".jpg", ".jfif", ".png", ".tif", ".tiff", ".webp"}
HASH_RE = re.compile(r"^[0-9a-f]{16}$")


def gallery_images() -> list[str]:
    output = subprocess.check_output(
        [
            "git",
            "-c",
            "core.quotePath=false",
            "ls-tree",
            "-r",
            "--name-only",
            "HEAD",
            "--",
            "gallery",
        ],
        text=True,
    )
    paths: list[str] = []
    for raw in output.splitlines():
        path = raw.strip()
        parts = path.split("/")
        if len(parts) != 3 or parts[0] != "gallery":
            continue
        name = parts[-1]
        if name.startswith(".airi-renumber-"):
            continue
        if Path(name).suffix.lower() not in IMAGE_SUFFIXES:
            continue
        paths.append(path)
    return sorted(paths)


def load_manifest() -> dict:
    return json.loads(Path("gallery/gallery_index.json").read_text(encoding="utf-8"))


def test_gallery_images_include_unicode_category_paths():
    paths = gallery_images()
    assert "gallery/airi图片/5150.jpg" in paths


def test_gallery_index_exactly_covers_repository_images():
    expected = set(gallery_images())
    manifest = load_manifest()
    actual = set((manifest.get("files") or {}).keys())

    missing = sorted(expected - actual)
    stale = sorted(actual - expected)
    assert actual == expected, (
        f"manifest coverage mismatch: expected={len(expected)} actual={len(actual)} "
        f"missing={len(missing)} stale={len(stale)} "
        f"missing_sample={missing[:8]} stale_sample={stale[:8]}"
    )


def test_gallery_index_keeps_algorithm_hash_shape_and_global_max_index():
    manifest = load_manifest()
    files = manifest.get("files") or {}

    assert manifest.get("version") == 1
    assert manifest.get("algorithm") == ALGORITHM

    bad_hashes = [
        path
        for path, entry in files.items()
        if not isinstance(entry, dict)
        or not HASH_RE.fullmatch(str(entry.get("perceptual_hash", "")).lower())
    ]
    assert not bad_hashes, f"invalid perceptual hashes: {bad_hashes[:8]}"

    numeric_stems = [
        int(Path(path).stem)
        for path in gallery_images()
        if Path(path).stem.isdigit()
    ]
    expected_max = max(numeric_stems, default=0)
    assert manifest.get("max_index") == expected_max