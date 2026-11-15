#!/usr/bin/env python3
"""Turn the raw recording into the final MP4: drop spinner waits listed in cuts.json.

    python scripts/cut_demo.py docs/demo/video
"""
import json
import subprocess
import sys
from pathlib import Path

d = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/demo/video")
cuts = json.loads((d / "cuts.json").read_text()) if (d / "cuts.json").exists() else []
keep = "+".join(f"between(t,{a:.2f},{b:.2f})" for a, b in cuts) or "0"
vf = f"select='not({keep})',setpts=N/FRAME_RATE/TB,fps=30,format=yuv420p"
out = d / "pixelindex-demo.mp4"
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(d / "pixelindex-demo.webm"), "-vf", vf,
                "-an", "-c:v", "libx264", "-preset", "slow", "-crf", "23", "-movflags", "+faststart", str(out)], check=True)
print(out, f"removed {sum(b - a for a, b in cuts):.1f}s")
