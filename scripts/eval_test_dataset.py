#!/usr/bin/env python3
"""Score PixelIndex on the labelled test library from ``make_test_dataset.py``.

    python scripts/make_test_dataset.py                      # build data/testset (once)
    python scripts/eval_test_dataset.py --index              # index it + evaluate → docs/EVALUATION.md

Measures, with the real CLIP encoder:

1. **Caption → photo** (Flickr8k): each human caption is a text query; recall@1/5/10
   of its photo among *all* indexed images, and among the Flickr photos only
   (the standard Flickr8k text→image protocol, for comparison with papers).
2. **Object queries** (COCO): ``"a photo of a {object}"`` for every object with ≥ 20
   photos; precision@10 / @50 against COCO's labels.
3. **Text inside images** (synthetic slides, memes, charts…): OCR keyword query
   through the real hybrid search; is the image in the top 10?
4. **Find similar**: query with a photo, is its planted near duplicate in the top 5?
5. **Duplicate detection**: ``/duplicates`` groups vs the planted pairs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
import statistics
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("VS_MODELS_DIR", str(ROOT / "data" / "models"))

STOP = set("the a an and of in on at to with for from by is are this that it its as be".split())


def configure(data_dir: Path, precision: str, ocr: str) -> None:
    os.environ["SEARCH_DATA_DIR"] = str(data_dir)
    os.environ["VS_ONNX_PRECISION"] = precision
    os.environ["VS_EMBED_BACKEND"] = "onnx"
    os.environ["VS_OCR_ENGINE"] = ocr


def build_index(dataset: Path) -> float:
    from app.db.schema import get_db, init_db
    from app.indexer.worker import IndexWorker

    init_db()
    with get_db() as conn:
        row = conn.execute("SELECT folder_id FROM watched_folders WHERE path = ?", (str(dataset),)).fetchone()
        fid = row["folder_id"] if row else conn.execute(
            "INSERT INTO watched_folders (path) VALUES (?)", (str(dataset),)).lastrowid
    last = [0.0]

    def progress(p) -> None:
        if time.time() - last[0] > 15:
            last[0] = time.time()
            print(f"  indexing… {p.embedded}/{p.total_files} ({p.images_per_sec} img/s)", file=sys.stderr)

    t0 = time.time()
    asyncio.run(IndexWorker(progress).start([fid]))
    return time.time() - t0


def recall_at(ranks: list[int], k: int) -> float:
    return round(sum(r <= k for r in ranks) / len(ranks), 4)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", type=Path, default=ROOT / "data" / "testset")
    ap.add_argument("--data-dir", type=Path, default=ROOT / "data" / "testset_index")
    ap.add_argument("--index", action="store_true", help="index --dataset into --data-dir first (incremental)")
    ap.add_argument("--precision", default="fp32", choices=["fp32", "fp16", "int8"])
    ap.add_argument("--ocr", default="auto")
    ap.add_argument("--min-photos", type=int, default=20, help="COCO objects need this many photos")
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "EVALUATION.md")
    a = ap.parse_args(argv)

    dataset = a.dataset.resolve()
    configure(a.data_dir.resolve(), a.precision, a.ocr)
    gt = json.loads((dataset / "ground_truth.json").read_text())
    index_s = build_index(dataset) if a.index else None

    from app.db.schema import get_db
    from app.db.vectors import load_vectors
    from app.embeddings import get_encoder

    enc = get_encoder()
    ids, mat = load_vectors(model=enc.name)
    assert len(ids), f"no '{enc.name}' vectors in {a.data_dir} — run with --index"
    with get_db() as conn:
        path_of = {r["image_id"]: str(Path(r["file_path"]).relative_to(dataset))
                   for r in conn.execute("SELECT image_id, file_path FROM images WHERE status='COMPLETED'")}
    rel = [path_of[int(i)] for i in ids]
    row_of = {p: i for i, p in enumerate(rel)}
    meta = [gt["files"].get(p, {}) for p in rel]
    # every file's "content id": duplicates share their source's id
    content = [m.get("dup_of", p) for p, m in zip(rel, meta)]
    report: dict = {"model": enc.name, "n_indexed": len(ids), "n_files": gt["n"],
                    "index_seconds": round(index_s, 1) if index_s else None}

    def rank_of(scores: np.ndarray, target: str) -> int:
        """1-based rank of the best-scoring file showing ``target``'s content."""
        order = np.argsort(-scores)
        for r, j in enumerate(order, start=1):
            if content[j] == target:
                return r
        return len(order) + 1

    # 1. caption → photo (Flickr8k) ------------------------------------------------
    t0 = time.time()
    fl = [i for i, m in enumerate(meta) if m.get("source") == "flickr" and "dup_of" not in m]
    queries = [(rel[i], c) for i in fl for c in meta[i]["captions"]]
    qv = np.concatenate([enc.encode_texts([c for _, c in queries[s:s + 64]]) for s in range(0, len(queries), 64)])
    sims = qv @ mat.T
    ranks_all = [rank_of(sims[q], target) for q, (target, _) in enumerate(queries)]
    fl_cols = np.array(fl)
    ranks_fl = []
    for q, (target, _) in enumerate(queries):
        s = sims[q, fl_cols]
        ranks_fl.append(int((s > s[list(fl_cols).index(row_of[target])]).sum()) + 1)
    examples = []
    rng = random.Random(0)
    for q in rng.sample(range(len(queries)), 6):
        top = int(np.argmax(sims[q]))
        examples.append({"caption": queries[q][1], "rank": ranks_all[q],
                         "top_hit": rel[top], "top_hit_caption": (meta[top].get("captions") or [meta[top].get("category")])[0]})
    report["captions"] = {
        "queries": len(queries), "photos": len(fl),
        "all_library": {f"R@{k}": recall_at(ranks_all, k) for k in (1, 5, 10)} | {"median_rank": statistics.median(ranks_all)},
        "flickr_only": {f"R@{k}": recall_at(ranks_fl, k) for k in (1, 5, 10)} | {"median_rank": statistics.median(ranks_fl)},
        "examples": examples, "seconds": round(time.time() - t0, 1)}
    print("captions", report["captions"]["all_library"], file=sys.stderr)

    # 2. COCO object queries --------------------------------------------------------
    coco_rows = [i for i, m in enumerate(meta) if m.get("source") == "coco"]
    counts: dict[str, int] = {}
    for i in coco_rows:
        if "dup_of" not in meta[i]:
            for c in meta[i]["categories"]:
                counts[c] = counts.get(c, 0) + 1
    objects = sorted(c for c, n in counts.items() if n >= a.min_photos)
    tv = enc.encode_texts([f"a photo of a {o}" for o in objects])
    per_obj = []
    # Flickr photos have no object labels (yet are full of people and dogs), so
    # they are left out here: a Flickr hit would be scored wrong even when correct.
    labelled = np.array([m.get("source") != "flickr" for m in meta])
    for o, v in zip(objects, tv):
        s = mat @ v
        s[~labelled] = -np.inf
        order = np.argsort(-s)
        hit = [o in meta[j].get("categories", []) for j in order[:50]]
        per_obj.append({"object": o, "photos": counts[o], "P@10": sum(hit[:10]) / 10, "P@50": sum(hit) / 50})
    per_obj.sort(key=lambda r: -r["P@10"])
    report["objects"] = {"n_objects": len(objects),
                         "mean_P@10": round(float(np.mean([r["P@10"] for r in per_obj])), 4),
                         "mean_P@50": round(float(np.mean([r["P@50"] for r in per_obj])), 4),
                         "per_object": per_obj}
    print("objects", report["objects"]["mean_P@10"], file=sys.stderr)

    # 3. text inside images (real hybrid search, OCR only) ---------------------------
    from app.search.hybrid import hybrid_search
    from app.search.schemas import SearchRequest

    ocr_rows = [i for i, m in enumerate(meta) if m.get("source") == "synthetic" and len(m.get("text", "")) > 12
                and "dup_of" not in m]
    hits, tried, ocr_examples = 0, 0, []
    for i in rng.sample(ocr_rows, min(80, len(ocr_rows))):
        words = [w for w in re.findall(r"[A-Za-z]{4,}", meta[i]["text"]) if w.lower() not in STOP]
        if len(words) < 2:
            continue
        start = rng.randrange(len(words) - 1)
        q = " ".join(words[start:start + 2])
        res = hybrid_search(SearchRequest(ocr=q, k=10))
        top = [content[row_of[str(Path(h["file_path"]).relative_to(dataset))]] for h in res["results"]]
        ok = rel[i] in top
        hits += ok
        tried += 1
        if len(ocr_examples) < 6:
            ocr_examples.append({"query": q, "category": meta[i]["category"], "found_in_top10": ok})
    with get_db() as conn:
        words_found = conn.execute("SELECT COALESCE(SUM(word_count),0) n FROM image_ocr").fetchone()["n"]
    report["ocr"] = {"queries": tried, "top10_hit_rate": round(hits / max(tried, 1), 4),
                     "ocr_words_indexed": words_found, "examples": ocr_examples}
    print("ocr", report["ocr"]["top10_hit_rate"], file=sys.stderr)

    # 4. find similar → planted near duplicate ---------------------------------------
    near = [p for p in gt["duplicate_pairs"] if p["kind"] == "near" and p["a"] in row_of and p["b"] in row_of]
    sim_ranks = []
    for p in near:
        qa, qb = row_of[p["a"]], row_of[p["b"]]
        s = mat @ mat[qa]
        s[qa] = -np.inf
        sim_ranks.append(int((s > s[qb]).sum()) + 1)
    report["similar"] = {"pairs": len(near), "dup_in_top1": recall_at(sim_ranks, 1),
                         "dup_in_top5": recall_at(sim_ranks, 5)}

    # 5. duplicate detection --------------------------------------------------------
    from app.dedup.service import find_duplicates
    from eval_dedup import evaluate

    t0 = time.time()
    payload = find_duplicates()
    d = evaluate(payload, gt, dataset)
    report["dedup"] = {k: v for k, v in d.items() if not isinstance(v, list)} | {"seconds": round(time.time() - t0, 1)}
    print("dedup", report["dedup"].get("recall"), file=sys.stderr)

    write_report(report, a)
    (a.out.with_suffix(".json")).write_text(json.dumps(report, indent=1))
    print(f"wrote {a.out}", file=sys.stderr)


def write_report(r: dict, a) -> None:
    c, o = r["captions"], r["objects"]
    lines = [
        "# Evaluation on real photos",
        "",
        f"Generated by `python scripts/eval_test_dataset.py` · model `{r['model']}` · "
        f"{r['n_indexed']} images indexed"
        + (f" in {r['index_seconds']} s" if r["index_seconds"] else "") + ".",
        "",
        "Test library (`python scripts/make_test_dataset.py`): real photos from "
        "[COCO 2017 val](https://huggingface.co/datasets/detection-datasets/coco) (object labels) and "
        "[Flickr8k test](https://huggingface.co/datasets/jxie/flickr8k) (5 human captions each), "
        "synthetic slides / memes / code / charts for text-in-image search, and planted exact + near "
        "duplicates, all shuffled into messy camera-roll folders with meaningless file names.",
        "",
        "## 1. Describe it, find it (Flickr8k captions → photo)",
        "",
        f"{c['queries']} caption queries for {c['photos']} photos. Rank of the right photo:",
        "",
        "| searched among | R@1 | R@5 | R@10 | median rank |",
        "|---|---:|---:|---:|---:|",
        f"| whole library ({r['n_indexed']} images) | {c['all_library']['R@1']:.1%} | {c['all_library']['R@5']:.1%} "
        f"| {c['all_library']['R@10']:.1%} | {c['all_library']['median_rank']} |",
        f"| Flickr photos only (standard protocol) | {c['flickr_only']['R@1']:.1%} | {c['flickr_only']['R@5']:.1%} "
        f"| {c['flickr_only']['R@10']:.1%} | {c['flickr_only']['median_rank']} |",
        "",
        "Examples:",
        "",
        "| caption | rank | top hit's own caption |",
        "|---|---:|---|",
        *[f"| {e['caption']} | {e['rank']} | {e['top_hit_caption']} |" for e in c["examples"]],
        "",
        "## 2. Object queries (COCO labels)",
        "",
        f"`\"a photo of a {{object}}\"` for the {o['n_objects']} objects with ≥ {a.min_photos} photos, searched "
        f"over the COCO photos and screenshots (Flickr photos are unlabelled, so they are left out). **Mean precision@10 = {o['mean_P@10']:.1%}**, precision@50 = {o['mean_P@50']:.1%}.",
        "",
        "| object | photos | P@10 | P@50 |",
        "|---|---:|---:|---:|",
        *[f"| {x['object']} | {x['photos']} | {x['P@10']:.0%} | {x['P@50']:.0%} |" for x in o["per_object"]],
        "",
        "## 3. Text inside images (OCR)",
        "",
        f"{r['ocr']['queries']} two-word queries taken from the text drawn on synthetic slides, memes, charts and "
        f"screenshots, run through the real hybrid search (OCR mode). "
        f"**Found in the top 10: {r['ocr']['top10_hit_rate']:.1%}** "
        f"({r['ocr']['ocr_words_indexed']} OCR words indexed).",
        "",
        "| query | kind | found |",
        "|---|---|---|",
        *[f"| {e['query']} | {e['category']} | {'✅' if e['found_in_top10'] else '❌'} |" for e in r["ocr"]["examples"]],
        "",
        "## 4. Find similar",
        "",
        f"For {r['similar']['pairs']} planted near duplicates (resized, re-encoded, cropped or brightened), "
        f"querying with the original photo puts the copy at **rank 1 in {r['similar']['dup_in_top1']:.1%}** "
        f"and in the top 5 in {r['similar']['dup_in_top5']:.1%} of cases.",
        "",
        "## 5. Duplicate detection",
        "",
        "```json",
        json.dumps(r["dedup"], indent=1),
        "```",
        "",
    ]
    a.out.write_text("\n".join(lines))


if __name__ == "__main__":
    main()
