"""Fetch a bounded slice of Mind2Web as an EXTERNAL held-out benchmark.

WHY MIND2WEB, AND WHY IT COUNTS AS HELD-OUT
-------------------------------------------
Every number this project has ever produced came from its own 106-site corpus —
the same corpus the collector was tuned against. That measures absence of
regression, not generalization, and the distinction is not academic: an
architecture review this week found three of seven confident criticisms were
simply wrong, and only out-of-sample data would have caught that before acting.

Mind2Web is real human demonstrations over 137 websites with, for each action, a
LABELLED target element. Our collector has never seen any of it — so even the
train split is fully out-of-sample *for us*. "Held out" is relative to what YOU
tuned on, not to the dataset's own split names.

WHY A RANGE DOWNLOAD
--------------------
The JSON shards are ~590 MB each (11 of them) and the multimodal parquet variant
is ~296 MB/shard because it embeds screenshots we do not need. We need
`raw_html` plus the target's `backend_node_id`, nothing else. So: HTTP Range for
the first N MB, then scan out the complete top-level objects and discard the
truncated tail. ~60 MB gives a usable sample and costs seconds, not minutes.

WHAT THIS CANNOT MEASURE — read before quoting a number
-------------------------------------------------------
Mind2Web ships SERIALIZED HTML, not a live page. Rendering it in a fresh browser
loses:
  - `listener_tag.js` handler tagging (no real listeners are ever attached), so
    bare handler-bound divs are invisible here but ARE found live;
  - external CSS in many cases, so geometry and visibility gates behave
    differently from the original page;
  - anything a framework would have rendered after load.
This therefore measures the STRUCTURAL subset of the collector's behaviour. A
target missed here is not automatically a live defect — but a target missed here
that SHOULD be reachable from static markup is a real finding, and the whole
point is that it comes from pages nobody tuned against.

Run:
    python tools/fetch_mind2web.py                 # ~60MB slice -> temp/mind2web/
    python tools/fetch_mind2web.py --mb 120
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "temp" / "mind2web"
URL = ("https://huggingface.co/datasets/osunlp/Mind2Web/resolve/main/"
       "data/train/train_{shard}.json")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def complete_objects(text: str):
    """Yield complete top-level JSON objects from a truncated `[{...},{...},...` blob.

    A naive brace count is wrong: `raw_html` is full of braces and quotes, so the
    scanner has to track string state and escapes. Anything after the last
    balanced object is discarded rather than guessed at.
    """
    i = text.find("[")
    if i == -1:
        return
    depth = 0
    start = None
    in_str = False
    esc = False
    for j in range(i + 1, len(text)):
        c = text[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            if depth == 0:
                start = j
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0 and start is not None:
                yield text[start:j + 1]
                start = None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mb", type=int, default=60, help="megabytes to range-download")
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--max-actions", type=int, default=400)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    url = URL.format(shard=args.shard)
    nbytes = args.mb * 1024 * 1024
    print(f"range-downloading first {args.mb} MB of shard {args.shard}")
    t0 = time.time()
    req = urllib.request.Request(url, headers={"Range": f"bytes=0-{nbytes}"})
    blob = urllib.request.urlopen(req, timeout=300).read().decode("utf-8", "replace")
    print(f"  got {len(blob)/1024/1024:.1f} MB in {time.time()-t0:.0f}s")

    samples = []
    tasks = 0
    for raw in complete_objects(blob):
        try:
            rec = json.loads(raw)
        except Exception:
            continue
        tasks += 1
        task = rec.get("confirmed_task") or ""
        for act in rec.get("actions") or []:
            pos = act.get("pos_candidates") or []
            html = act.get("raw_html") or act.get("cleaned_html") or ""
            if not pos or not html:
                continue
            # pos_candidates entries carry the labelled target's backend_node_id;
            # attributes is a JSON string in this dataset.
            cand = pos[0]
            attrs = cand.get("attributes")
            if isinstance(attrs, str):
                try:
                    attrs = json.loads(attrs)
                except Exception:
                    attrs = {}
            samples.append({
                # MindAct's OWN cleaning output, kept so the head-to-head compares
                # against THEIR baseline rather than my reimplementation of it.
                "cleaned_html": act.get("cleaned_html") or "",
                "annotation_id": rec.get("annotation_id"),
                "action_uid": act.get("action_uid"),
                "website": rec.get("website"),
                "domain": rec.get("domain"),
                "subdomain": rec.get("subdomain"),
                "task": task,
                "operation": (act.get("operation") or {}).get("op"),
                "target_backend_node_id": cand.get("backend_node_id"),
                "target_tag": cand.get("tag"),
                "target_attrs": attrs or {},
                "html": html,
            })
            if len(samples) >= args.max_actions:
                break
        if len(samples) >= args.max_actions:
            break

    dest = OUT / f"samples_shard{args.shard}.jsonl"
    with dest.open("w", encoding="utf-8") as fh:
        for s in samples:
            fh.write(json.dumps(s, ensure_ascii=False) + "\n")

    sites = sorted({s["website"] for s in samples})
    doms = sorted({s["domain"] for s in samples if s.get("domain")})
    print(f"\n{len(samples)} labelled actions from {tasks} tasks")
    print(f"websites ({len(sites)}): {', '.join(sites[:18])}{' …' if len(sites) > 18 else ''}")
    print(f"domains  ({len(doms)}): {', '.join(doms)}")
    print(f"-> {dest}  ({dest.stat().st_size/1024/1024:.1f} MB)")
    return 0 if samples else 1


if __name__ == "__main__":
    sys.exit(main())
