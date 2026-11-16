"""Does our listing change when only the COLOUR changes?

WHY THIS ONE FIRST. `docs/WEBPAGEBENCH.md` designs three measurements and this
is none of them -- it is the INSTRUMENT CHECK that has to pass before any of
them is believed. WebPageBench ships 12 `__theme_dark` variants whose task text
and success conditions are byte-identical to their canonical twin and which
differ only by `ui_variants: {"theme": "dark"}`. A representation built on what
the DOCUMENT DECLARES must produce the same listing for both. If dark mode moves
the number, the representation is reading presentation and every later result on
this benchmark is measuring the wrong thing.

It is also the cheapest real test of the project's own headline claim --
"works on any site at any stage, no site-specific code" -- because the two arms
are the same site at the same stage with one presentational variable moved.

WHAT IS COMPARED. The STRING listing, with refs normalised away: `mmid`s are
additive per document, so two loads of one page legitimately differ on them and
comparing them would measure the counter rather than the page. Everything else
-- tags, accessible names, values, state flags, structure, folding -- must
match.

THE DRIFT FLOOR IS NOT OPTIONAL. This is a live SPA with timers and fonts, so
two loads of the SAME arm can differ. The canonical arm is therefore rendered
TWICE and the canonical-vs-canonical difference is the floor; a dark-vs-light
difference only counts if it exceeds it. Block-structured A/B once produced
three "CLIFF" verdicts in this repo that were all run-order artefacts (#19), so
the arms are interleaved canonical / dark / canonical per pair.

Needs the site up:
    cd <WebPageBench>/site
    docker compose -f docker-compose.local.yml up -d     # serves :8080

Run:  python tools/measure_wpb_invariance.py --repo <path-to-WebPageBench>
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import difflib
import json
import os
import re
import sys
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _extract import extract as _shared_extract  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BG = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
# Extracted verbatim, as every browser suite does, so a disagreement with the
# shipped collector is a disagreement about the extractor and not about this.
COLLECT = _shared_extract("_collectInteractivePage", BG, verify=True)
TAG = (ROOT / "extension" / "listener_tag.js").read_text(encoding="utf-8")

HOST = "http://localhost:8080"
# A ref is additive per document, so two loads of one page differ on it
# legitimately. Normalising it is what makes the comparison about the PAGE.
_REF = re.compile(r"\b(?:ref_|mmid=['\"]?)\d+['\"]?")
# THE TWO ARMS ARE NECESSARILY DIFFERENT TRACKS, so the page url differs by the
# track id and nothing else. The first version of this probe did not normalise
# it and reported "the listing MOVES with the theme" on every pair -- 2 changed
# lines against a floor of 0, deterministic, which reads exactly like a real
# finding. It was the harness. Caught by printing the diff instead of trusting
# the count (#16), which is the rule this repo keeps paying for.
_TRACK = re.compile(r"/inv_[ld]_[A-Za-z0-9_]+/")


def _norm(listing: str) -> list[str]:
    out = []
    for line in (listing or "").splitlines():
        line = _TRACK.sub("/TRACK/", _REF.sub("ref_N", line)).rstrip()
        if not line:
            continue
        # The readiness banner is a timing fact, not a structural one; it names
        # millisecond ages that cannot match across two loads.
        if line.startswith("***"):
            continue
        out.append(line)
    return out


def _merge(base, upd):
    r = copy.deepcopy(base)
    for k, v in upd.items():
        r[k] = _merge(r[k], v) if k in r and isinstance(r[k], dict) and isinstance(v, dict) else copy.deepcopy(v)
    return r


def build_track_config(repo: Path, task_file: Path) -> dict:
    """A runnable track is config.json MERGED with a task file, not a task file.

    Learned by standing the site up: a track built from the task alone renders
    `State Not Found — не найден шаг state_id в конфиге`. The merge is theirs
    (`tests.py`); it is reimplemented here in stdlib so none of their code runs
    outside the container.
    """
    bench = repo / "tests" / "bench"
    base = json.loads((bench / "config.json").read_text(encoding="utf-8"))
    ext = base.pop("extends", None)
    if ext:
        p = (bench / ext).resolve()
        base = _merge(json.loads(p.read_text(encoding="utf-8")), base)
    merged = _merge(base, json.loads(task_file.read_text(encoding="utf-8")))
    merged["test_data"]["test_name"] = task_file.stem
    return merged


async def create_track(session, track_id: str, cfg: dict) -> bool:
    import urllib.request

    body, boundary = [], "----cbwpb"
    for k, v in (("name", track_id), ("track_id", track_id), ("delete_existing", "true")):
        body.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n")
    payload = json.dumps(cfg, ensure_ascii=False)
    body.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"cfg.json\"; "
        f"filename=\"cfg.json\"\r\nContent-Type: application/json\r\n\r\n{payload}\r\n"
    )
    body.append(f"--{boundary}--\r\n")
    data = "".join(body).encode("utf-8")
    req = urllib.request.Request(
        f"{HOST}/track/create", data=data,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8")).get("track_id") == track_id
    except Exception as e:
        print(f"    create_track failed: {e}")
        return False


async def listing_for(browser, track_id: str) -> tuple[list[str], str]:
    pg = await browser.new_page(viewport={"width": 1280, "height": 900})
    await pg.add_init_script(TAG)
    try:
        await pg.goto(f"{HOST}/{track_id}", wait_until="networkidle", timeout=30000)
        await pg.wait_for_timeout(2500)
        url = pg.url
        out = await pg.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(false); })()")
        return _norm(out), url
    finally:
        await pg.close()


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="path to a WebPageBench checkout")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    repo = Path(a.repo).resolve()
    tasks = repo / "tests" / "bench" / "tasks"
    if not tasks.is_dir():
        print(f"no task dir at {tasks}", file=sys.stderr)
        return 2

    pairs = []
    for v in sorted(tasks.glob("*__theme_dark.json")):
        c = tasks / v.name.replace("__theme_dark", "")
        if c.is_file():
            pairs.append((c, v))
    if a.limit:
        pairs = pairs[: a.limit]
    print(f"{len(pairs)} canonical/dark pair(s)\n")

    # The pair is only usable if the two really are identical but for the theme.
    bad = []
    for c, v in pairs:
        cd = json.loads(c.read_text(encoding="utf-8"))["test_data"]
        vd = json.loads(v.read_text(encoding="utf-8"))["test_data"]
        if cd.get("task") != vd.get("task") or cd.get("conditions") != vd.get("conditions"):
            bad.append(v.name)
    if bad:
        print(f"REFUSING: {len(bad)} pair(s) differ in task or conditions: {bad[:3]}")
        return 2
    print("precondition: task text and success conditions identical on all pairs  OK\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        rows, floor_hits = [], []
        for c, v in pairs:
            stem = c.stem[:38]
            ok = True
            for tid, cfg in ((f"inv_l_{c.stem[:24]}", build_track_config(repo, c)),
                             (f"inv_d_{v.stem[:24]}", build_track_config(repo, v))):
                ok = ok and await create_track(None, tid, cfg)
            if not ok:
                rows.append((stem, None, None, "track create failed")); continue

            lid, did = f"inv_l_{c.stem[:24]}", f"inv_d_{v.stem[:24]}"
            # INTERLEAVED light / dark / light, so run-order drift cannot align
            # with the arm and the floor is measured in the same window.
            l1, u1 = await listing_for(browser, lid)
            dk, u2 = await listing_for(browser, did)
            l2, _ = await listing_for(browser, lid)

            floor = sum(1 for _ in difflib.unified_diff(l1, l2, n=0) if _.startswith(("+", "-")) and not _.startswith(("+++", "---")))
            delta = sum(1 for _ in difflib.unified_diff(l1, dk, n=0) if _.startswith(("+", "-")) and not _.startswith(("+++", "---")))
            floor_hits.append(floor)
            rows.append((stem, len(l1), delta, floor))

        await browser.close()

    print(f"{'pair':40} {'rows':>5} {'dark-vs-light':>14} {'floor(l-vs-l)':>14}")
    worst = 0
    for stem, n, delta, floor in rows:
        if n is None:
            print(f"{stem:40} {'-':>5} {str(floor):>14}")
            continue
        worst = max(worst, delta - floor if isinstance(floor, int) else delta)
        print(f"{stem:40} {n:>5} {delta:>14} {floor:>14}")

    usable = [r for r in rows if r[1] is not None]
    print()
    if not usable:
        print("NO USABLE PAIRS — nothing was measured.")
        return 1
    tot_delta = sum(r[2] for r in usable)
    tot_floor = sum(r[3] for r in usable)
    print(f"{len(usable)} pair(s) measured. changed lines: dark-vs-light {tot_delta}, "
          f"same-arm floor {tot_floor}.")
    print(f"excess over floor, worst single pair: {worst}")
    print()
    if tot_delta <= tot_floor:
        print("VERDICT: the listing is INVARIANT to the theme within the drift floor.")
        print("         A colour-only change does not move the representation, which is")
        print("         what a structural representation must do and is the precondition")
        print("         for believing any other number from this benchmark.")
    else:
        print("VERDICT: the listing MOVES with the theme beyond the drift floor.")
        print("         The representation is reading presentation somewhere. Every other")
        print("         measurement on this benchmark is suspect until that is explained.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
