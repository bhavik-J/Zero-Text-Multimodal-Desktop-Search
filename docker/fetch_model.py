"""Download the CLIP ONNX weights into the image at build time (layer is cached).

Mirrors backend/app/embeddings/download.py but runs without the app package, so
code changes do not invalidate this ~600 MB layer.
"""
import os
import shutil
import sys
from pathlib import Path

from huggingface_hub import hf_hub_download

REPO = os.environ.get("VS_ONNX_REPO", "Xenova/clip-vit-base-patch32")
PRECISIONS = {
    "fp32": ("vision_model.onnx", "text_model.onnx"),
    "fp16": ("vision_model_fp16.onnx", "text_model_fp16.onnx"),
    "int8": ("vision_model_quantized.onnx", "text_model_quantized.onnx"),
}
precisions = sys.argv[1:] or ["fp32"]
dest = Path(os.environ.get("VS_MODELS_DIR", "/models")) / REPO.replace("/", "__")
dest.mkdir(parents=True, exist_ok=True)
files = ["tokenizer.json", "preprocessor_config.json", "config.json"]
for p in precisions:
    files += [f"onnx/{f}" for f in PRECISIONS[p]]
for rel in files:
    target = dest / Path(rel).name
    if not target.exists():
        print("downloading", rel, flush=True)
        shutil.copyfile(hf_hub_download(REPO, rel), target)
print("model ready in", dest)
