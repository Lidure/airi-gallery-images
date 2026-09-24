from pathlib import Path

from PIL import Image

from scripts.rebuild_gallery_index import build_manifest_payload, perceptual_hash


ALGORITHM = "dhash64-nn-white-v1"


def test_perceptual_hash_matches_plugin_bit_order(tmp_path: Path):
    image_path = tmp_path / "pattern.png"
    image = Image.new("RGB", (9, 8), (0, 0, 0))
    pixels = image.load()
    for row in range(8):
        pixels[0, row] = (255, 255, 255)
    image.save(image_path)

    assert perceptual_hash(image_path) == "8080808080808080"


def test_perceptual_hash_composites_transparency_over_white(tmp_path: Path):
    image_path = tmp_path / "transparent.png"
    image = Image.new("RGBA", (9, 8), (0, 0, 0, 0))
    pixels = image.load()
    for row in range(8):
        pixels[0, row] = (0, 0, 0, 255)
    image.save(image_path)

    assert perceptual_hash(image_path) == "0000000000000000"


def test_build_manifest_preserves_unknown_metadata_and_replaces_files():
    existing = {
        "version": 1,
        "algorithm": ALGORITHM,
        "max_index": 999,
        "future_field": {"keep": True},
        "files": {"gallery/old/999.png": {"perceptual_hash": "ffffffffffffffff"}},
    }
    hashes = {
        "gallery/airi/1.png": "1111111111111111",
        "gallery/Bang/5687.jpg": "2222222222222222",
    }

    rebuilt = build_manifest_payload(existing, hashes)

    assert rebuilt["future_field"] == {"keep": True}
    assert rebuilt["version"] == 1
    assert rebuilt["algorithm"] == ALGORITHM
    assert rebuilt["max_index"] == 5687
    assert rebuilt["files"] == {
        "gallery/Bang/5687.jpg": {"perceptual_hash": "2222222222222222"},
        "gallery/airi/1.png": {"perceptual_hash": "1111111111111111"},
    }
