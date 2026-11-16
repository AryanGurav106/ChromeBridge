"""Create the eval-7 tracks on a running WebPageBench, and record what was made.

EVAL 6 DID NOT KEEP ITS GENERATOR, which is #48's own lesson ("a result nobody
can re-derive is an anecdote with a p-value") landing on the eval that followed
it. This one is in the repo.

A track is the benchmark's base `config.json` with ONE task file's `test_data`
merged over it, POSTed as a multipart upload to `/track/create`. The server then
serves that task's app at `/<track_id>` and records its business events against
that track alone, so each (task, arm) cell is independent state.

Needs the benchmark running (docker compose, localhost:8080) and a checkout of
ai-forever/WebPageBench for `config.json` and `tests/bench/tasks/`.

Run:  python tools/bench_turns/eval7/make_tracks.py --repo <path-to-checkout>
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOST = "http://localhost:8080"

# Chosen for CONDITION COUNT (the resolution of eval 7's primary metric) and
# spread across all six app families. Base files only: the `__date_native_input`
# / `__theme_dark` variants are #79's control-swap arms and would confound this.
TASKS = [
    ("rail2p",   "rail_book_to_cart_2_passengers.json"),
    ("railpay",  "rail_book_and_pay_2_passengers.json"),
    ("hoteldxb", "hotel_search_scenario_dubai.json"),
    ("hotel2rm", "hotel_search_scenario_two_rooms.json"),
    ("shop3",    "ecommerce_basket_three_products.json"),
    ("filespdf", "files_download_pdf.json"),
    ("booksexp", "digital_books_author_expensive_basket.json"),
    ("grocat",   "grocery_basket_category_named_product.json"),
]
ARMS = ("cb", "cic")


def _post_multipart(url: str, fields: dict, fname: str, blob: bytes) -> str:
    b = uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        parts.append(f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n")
    head = "".join(parts) + (
        f"--{b}\r\nContent-Disposition: form-data; name=\"{fname}\"; "
        f"filename=\"{fname}\"\r\nContent-Type: application/json\r\n\r\n")
    body = head.encode() + blob + f"\r\n--{b}--\r\n".encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="path to a WebPageBench checkout")
    ap.add_argument("--host", default=HOST)
    a = ap.parse_args()
    repo = Path(a.repo)
    base_p = repo / "tests" / "bench" / "config.json"
    tdir = repo / "tests" / "bench" / "tasks"
    if not base_p.exists() or not tdir.is_dir():
        print(f"not a WebPageBench checkout: {repo}", file=sys.stderr)
        return 2

    base = json.loads(base_p.read_text(encoding="utf-8"))
    rows = []
    for key, fname in TASKS:
        task = json.loads((tdir / fname).read_text(encoding="utf-8"))
        conds = task["test_data"].get("conditions", []) or []
        for arm in ARMS:
            tid = f"e7_{arm}_{key}"
            cfg = json.loads(json.dumps(base))          # deep copy per track
            cfg["test_data"].update(task["test_data"])  # task wins on conflict
            blob = json.dumps(cfg, ensure_ascii=False).encode("utf-8")
            try:
                res = _post_multipart(
                    a.host + "/track/create",
                    {"track_id": tid, "delete_existing": "true"},
                    "config.json", blob)
                ok = tid in res
            except Exception as e:                       # noqa: BLE001
                res, ok = str(e)[:120], False
            rows.append({"key": key, "arm": arm, "track": tid, "task_file": fname,
                         "task": task["test_data"].get("task", ""),
                         "n_conditions": len(conds), "conditions": conds,
                         "created": bool(ok), "server": res[:120]})
            print(f"{'ok ' if ok else 'FAIL'} {tid:24} {len(conds):>2} cond  {fname}")

    (HERE / "tracks.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    made = sum(1 for r in rows if r["created"])
    print(f"\n{made}/{len(rows)} track(s) created; "
          f"{sum(r['n_conditions'] for r in rows if r['arm'] == 'cb')} conditions per arm")
    return 0 if made == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
