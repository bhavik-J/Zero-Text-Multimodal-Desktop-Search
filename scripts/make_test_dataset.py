#!/usr/bin/env python3
"""Build a labelled *real-photo* test library for PixelIndex.

    python scripts/make_test_dataset.py --out data/testset

Mixes three sources into one messy folder tree, the way a real "second brain"
folder looks:

* **COCO 2017 val** (``detection-datasets/coco`` on the HF Hub, CC-BY photos):
  everyday scenes, each labelled with the objects in it → category queries.
* **Flickr8k test** (``jxie/flickr8k``): 1,000 photos with 5 human captions
  each → "describe it and find it" retrieval.
* **Synthetic screenshots** from ``make_chaos_dataset.py``: lecture slides,
  code, memes, charts, UI → OCR / text-in-image queries.

Exact copies and near duplicates (resize, re-encode, crop, brightness) of the
real photos are planted. ``ground_truth.json`` uses the same format as the
chaos dataset (``files`` + ``duplicate_pairs``) plus ``source``,
``categories`` (COCO) and ``captions`` (Flickr), so both
``scripts/eval_dedup.py`` and ``scripts/eval_test_dataset.py`` can score it.

Downloads ~540 MB of parquet files once into ``data/raw/`` (git-ignored).
"""

from __future__ import annotations

import argparse
import io
import json
import random
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import make_chaos_dataset as chaos  # noqa: E402  (reuse near_dup + generator)

SOURCES = {
    "coco": ("detection-datasets/coco", "data/val-00001-of-00002-7af5414a3b178949.parquet"),
    "flickr": ("jxie/flickr8k", "data/test-00000-of-00001-42a2661d12c73e48.parquet"),
}

# COCO-2017 detection categories in the contiguous 0..79 order used by the HF export.
COCO_NAMES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
    "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog",
    "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella",
    "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite",
    "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket", "bottle",
    "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch", "potted plant",
    "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote", "keyboard", "cell phone",
    "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase", "scissors",
    "teddy bear", "hair drier", "toothbrush",
]

PHOTO_FOLDERS = [
    "Camera Roll", "Camera Roll/2024", "Camera Roll/2025", "WhatsApp Images",
    "WhatsApp Images/Sent", "Downloads", "Desktop/random", "Pictures/Trip",
    "Pictures/Family", "Phone Backup/DCIM/Camera", "Telegram Desktop", "untitled folder",
]


def photo_name(rng: random.Random, ext: str) -> str:
    """A believable, content-free camera / messaging-app filename."""
    y, m, d = rng.randint(2019, 2026), rng.randint(1, 12), rng.randint(1, 28)
    hh, mm, ss = rng.randint(0, 23), rng.randint(0, 59), rng.randint(0, 59)
    return rng.choice([
        f"IMG_{rng.randint(1000, 9999)}.{ext}",
        f"IMG_{y}{m:02d}{d:02d}_{hh:02d}{mm:02d}{ss:02d}.{ext}",
        f"PXL_{y}{m:02d}{d:02d}_{hh:02d}{mm:02d}{ss:02d}{rng.randint(100, 999)}.{ext}",
        f"WhatsApp Image {y}-{m:02d}-{d:02d} at {hh:02d}.{mm:02d}.{ss:02d}.{ext}",
        f"photo_{y}-{m:02d}-{d:02d}_{hh:02d}-{mm:02d}-{ss:02d}.{ext}",
        f"DSC{rng.randint(1000, 9999)}.{ext}",
        f"download ({rng.randint(1, 60)}).{ext}",
        f"{rng.randint(10**14, 10**15 - 1)}.{ext}",
    ])


def fetch(source: str, raw_dir: Path) -> Path:
    """Download one parquet shard into ``raw_dir`` (cached)."""
    dest = raw_dir / f"{source}.parquet"
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    from huggingface_hub import hf_hub_download

    repo, filename = SOURCES[source]
    print(f"downloading {repo}/{filename} …", file=sys.stderr)
    raw_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(hf_hub_download(repo, filename, repo_type="dataset"), dest)
    return dest


def load_rows(path: Path, n: int, rng: random.Random) -> list[dict]:
    import pyarrow.parquet as pq

    table = pq.read_table(path)
    idx = sorted(rng.sample(range(table.num_rows), min(n, table.num_rows)))
    return table.take(idx).to_pylist()


def unique_path(out: Path, folder: str, name: str, taken: set[str]) -> str:
    rel = f"{folder}/{name}"
    stem, ext = rel.rsplit(".", 1)
    i = 1
    while rel in taken:
        rel = f"{stem} ({i}).{ext}"
        i += 1
    taken.add(rel)
    (out / rel).parent.mkdir(parents=True, exist_ok=True)
    return rel


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "testset")
    ap.add_argument("--raw-dir", type=Path, default=ROOT / "data" / "raw")
    ap.add_argument("--coco", type=int, default=1500, help="COCO photos (max 2476)")
    ap.add_argument("--flickr", type=int, default=1000, help="Flickr8k photos (max 1000)")
    ap.add_argument("--screenshots", type=int, default=600, help="synthetic slides/memes/code/…")
    ap.add_argument("--exact-frac", type=float, default=0.04, help="exact copies, fraction of photos")
    ap.add_argument("--near-frac", type=float, default=0.04, help="near duplicates, fraction of photos")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--clean", action="store_true", help="delete --out first")
    a = ap.parse_args(argv)

    out: Path = a.out.resolve()
    if a.clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(a.seed)
    files: dict[str, dict] = {}
    pairs: list[dict] = []
    taken: set[str] = set()

    # 1. synthetic screenshots (OCR-heavy) under screenshots/
    if a.screenshots > 0:
        shots = out / "screenshots"
        chaos.main(["--out", str(shots), "--n", str(a.screenshots), "--seed", str(a.seed), "--clean",
                    "--exact-frac", "0.03", "--near-frac", "0.03"])
        gt = json.loads((shots / "ground_truth.json").read_text())
        (shots / "ground_truth.json").unlink()
        for rel, meta in gt["files"].items():
            files[f"screenshots/{rel}"] = {"source": "synthetic", **meta,
                                           **({"dup_of": f"screenshots/{meta['dup_of']}"} if "dup_of" in meta else {})}
        for pr in gt["duplicate_pairs"]:
            pairs.append({**pr, "a": f"screenshots/{pr['a']}", "b": f"screenshots/{pr['b']}"})

    # 2. real photos
    photos: list[str] = []
    for source, n in (("coco", a.coco), ("flickr", a.flickr)):
        if n <= 0:
            continue
        rows = load_rows(fetch(source, a.raw_dir), n, rng)
        for row in rows:
            data = row["image"]["bytes"]
            ext = "jpg"
            rel = unique_path(out, rng.choice(PHOTO_FOLDERS), photo_name(rng, ext), taken)
            (out / rel).write_bytes(data)
            meta: dict = {"source": source, "category": f"photo_{source}"}
            if source == "coco":
                meta["categories"] = sorted({COCO_NAMES[c] for c in row["objects"]["category"] if 0 <= c < 80})
                meta["coco_image_id"] = row["image_id"]
            else:
                meta["captions"] = [row[f"caption_{i}"].strip() for i in range(5)]
            files[rel] = meta
            photos.append(rel)
        print(f"{source}: {len(rows)} photos", file=sys.stderr)

    # 3. planted duplicates of real photos
    from PIL import Image

    n_exact, n_near = round(len(photos) * a.exact_frac), round(len(photos) * a.near_frac)
    for src in rng.sample(photos, min(n_exact, len(photos))):
        rel = unique_path(out, rng.choice(PHOTO_FOLDERS),
                          rng.choice([f"Copy of {Path(src).name}", photo_name(rng, "jpg")]), taken)
        shutil.copyfile(out / src, out / rel)
        files[rel] = {**files[src], "dup_of": src, "dup_kind": "exact"}
        pairs.append({"a": src, "b": rel, "kind": "exact"})
    for src in rng.sample(photos, min(n_near, len(photos))):
        img = Image.open(out / src).convert("RGB")
        dup, transform = chaos.near_dup(img, rng)
        ext = rng.choice(["jpg", "jpg", "png", "webp"])
        rel = unique_path(out, rng.choice(PHOTO_FOLDERS), photo_name(rng, ext), taken)
        (out / rel).write_bytes(chaos.encode(dup, ext, rng))
        files[rel] = {**files[src], "dup_of": src, "dup_kind": "near", "transform": transform}
        pairs.append({"a": src, "b": rel, "kind": "near", "transform": transform})

    counts: dict[str, int] = {}
    for meta in files.values():
        counts[meta["category"]] = counts.get(meta["category"], 0) + 1
    gt = {"seed": a.seed, "n": len(files), "categories": counts, "files": files, "duplicate_pairs": pairs,
          "sources": {k: f"https://huggingface.co/datasets/{v[0]}" for k, v in SOURCES.items()}}
    (out / "ground_truth.json").write_text(json.dumps(gt, indent=1))
    print(json.dumps({"out": str(out), "files": len(files), "categories": counts,
                      "exact_pairs": sum(p["kind"] == "exact" for p in pairs),
                      "near_pairs": sum(p["kind"] == "near" for p in pairs)}, indent=1))


if __name__ == "__main__":
    main()
