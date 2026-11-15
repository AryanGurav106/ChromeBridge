"""Out-of-sample element retention, measured on Mind2Web's labelled targets.

WHAT THIS ANSWERS THAT NOTHING ELSE DOES
----------------------------------------
`measure_retention.py` scores the 106-site corpus — the corpus the collector was
built against. It can only prove the absence of regressions. This scores pages
nobody involved has ever looked at, against targets a HUMAN labelled as the
element they actually clicked to complete a real task.

The question is narrow and the most important one in the system:

    when a person had to click something to get their task done,
    is that element in our listing, and can the agent pick it out?

Three numbers per action:

  recall        the labelled target appears in the structured listing — as
                itself, or as an ancestor/descendant we surfaced instead (an
                agent clicking the wrapping <a> of a labelled <span> succeeds,
                so scoring that as a miss would be dishonest). Both indirect
                paths are area-capped: see `_m2w_ruler.credit_refs`.
  exact         the target itself carries the ref, no ancestor/descendant credit
  findability   the REAL find() scorer, given the human's task description,
                ranks the target — MRR and top-3

Reported beside MindAct's published HTML-cleaning baseline of 94.7% target
recall. That is CONTEXT, not a head-to-head: their denominator rule is not known
to match ours and nothing here establishes that it does.

THE DENOMINATOR IS ALL 186 ACTIONS, and until #73 it was 173
-------------------------------------------------------------
Thirteen actions used to be excluded with the claim that "the target element is
absent from the saved snapshot entirely". That was FALSE — every one of the 13
ids is in the saved string, and they were lost in the PARSE, because Mind2Web
serializes XML-style and a self-closed `<iframe/>` or `<textarea/>` swallows the
rest of the document as text. `_m2w_ruler.repair_serialization` undoes that
before the page is rendered and all 186 targets now resolve, so the exclusion
and the two denominators it forced are both gone. `--no-repair` reproduces the
historical behaviour exactly, for comparison; it is not the honest arm.

HONEST LIMITS — do not quote a number from here without these
--------------------------------------------------------------
Mind2Web ships SERIALIZED HTML rendered fresh in a blank browser. That deletes:
  - handler tagging (no listeners are ever attached, so `listener_tag.js` finds
    nothing) — bare handler-bound divs are invisible HERE but found LIVE;
  - most external CSS, so visibility and geometry gates behave differently;
  - post-load framework rendering.
So this is the STRUCTURAL subset, and it is a LOWER BOUND on live behaviour.
Misses are triaged into `missed_invisible` (zero-area/hidden after render —
usually the missing-CSS artefact) and `missed_present` (the node rendered with
real geometry and we still dropped it). Only the second class is a real finding.

One more, measured rather than assumed: after the repair a median 99.8% of each
snapshot's recorded ids parse, worst 43.4%, because Mind2Web nests a frame's
whole document inside the `<iframe>` element and that is rawtext whatever the
slash does. No labelled target is among them — all 186 resolve to exactly one
node — so it bounds the LISTING, not the denominator.

Run:
    python tools/bench_mind2web.py                # all fetched shards
    python tools/bench_mind2web.py --limit 60
    python tools/bench_mind2web.py --baseline
    python tools/bench_mind2web.py --no-repair    # the pre-#73 arm, for comparison
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "temp" / "mind2web"
OUT = ROOT / "temp" / "mind2web"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _extract import extract  # noqa: E402
from _m2w_ruler import (CREDIT_AREA_CAP, cap_withdrew, credit_refs,  # noqa: E402
                        repair_serialization)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Every status that counts toward the denominator -- which is ALL of them except
# a harness error. `target_not_in_dom` is in here deliberately: excluding it is
# what produced a second denominator and a false sentence about the dataset.
SCORED = ("ok", "missed_present", "missed_invisible", "target_not_in_dom")

BG = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
COLLECT = extract("_collectInteractivePage", BG, verify=True)
TAG_JS = str(ROOT / "extension" / "listener_tag.js")

_spec = importlib.util.spec_from_file_location("ms", ROOT / "mcp_server.py")
ms = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ms)
_find = ms.find.fn if hasattr(ms.find, "fn") else ms.find

# Locate the labelled node, then ask three questions of it: did we tag it, did we
# tag an ancestor/descendant instead, and was it actually rendered at all.
PROBE = r"""
(bnid) => {
  const esc = String(bnid).replace(/"/g, '');
  const el = document.querySelector(`[backend_node_id="${esc}"]`);
  if (!el) return { found: false };
  const r = el.getBoundingClientRect();
  const cs = getComputedStyle(el);
  const rendered = r.width > 0 && r.height > 0 &&
                   cs.visibility !== 'hidden' && cs.display !== 'none';
  const own = el.getAttribute('mmid');
  // WALK THE WHOLE CHAIN, not just the nearest tagged ancestor. Stopping at the
  // first element that happens to carry an mmid scored real successes as misses:
  // on exploretock the labelled <svg> sits inside <span mmid=..> inside the
  // <button> that IS listed, and on discogs an <img> inside <span> inside the
  // listed <a>. The agent clicks the button/anchor and succeeds; calling that a
  // miss measures our probe, not the collector.
  //
  // Each one carries its own area fraction. THIS PROBE DECIDES NOTHING: the
  // credit rule is `_m2w_ruler.credit_refs`, in Python, so it can be driven by
  // a unit test and so the two benchmarks that use this probe cannot hold two
  // different versions of it (CLAUDE.md #21).
  const ancs = [];
  for (let n = el.parentElement; n; n = n.parentElement) {
    const m = n.getAttribute && n.getAttribute('mmid');
    if (m) {
      const b = n.getBoundingClientRect();
      ancs.push({ mmid: m, tag: n.tagName.toLowerCase(),
                  area: (b.width * b.height) / (innerWidth * innerHeight) });
    }
  }

  // ANY descendant, not the FIRST one. A <label> wrapping its <select> was
  // scored a miss because querySelector('[mmid]') returned a different child,
  // while the select itself WAS listed and acting on it does exactly what
  // clicking the label would.
  const ds = Array.from(el.querySelectorAll('[mmid]')).map(n=>n.getAttribute('mmid'));

  return {
    found: true, rendered, own, ancs, descs: ds,
    area: (r.width * r.height) / (innerWidth * innerHeight),
    tag: el.tagName.toLowerCase(),
    text: (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 80),
    w: Math.round(r.width), h: Math.round(r.height),
  };
}
"""


def load_samples(limit: int) -> list[dict]:
    rows: list[dict] = []
    for f in sorted(DATA.glob("samples_shard*.jsonl")):
        with f.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    # Round-robin by website so a limit does not silently become "one site".
    by_site: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_site[r.get("website") or "?"].append(r)
    out, i = [], 0
    while limit <= 0 or len(out) < limit:
        added = False
        for site in sorted(by_site):
            if i < len(by_site[site]):
                out.append(by_site[site][i])
                added = True
                if limit and len(out) >= limit:
                    break
        if not added:
            break
        i += 1
    return out


async def score_one(page, s: dict, repair: bool = True) -> dict:
    res: dict = {"website": s.get("website"), "domain": s.get("domain"),
                 "action_uid": s.get("action_uid"),
                 "task": (s.get("task") or "")[:90], "op": s.get("operation")}
    # THE PARSE IS PART OF THE RULER. An XML snapshot handed to an HTML parser
    # loses a target and clones others; see `_m2w_ruler` §1 for the measurement.
    html = repair_serialization(s["html"]) if repair else s["html"]
    await page.set_content(html, wait_until="domcontentloaded")
    await page.wait_for_timeout(120)

    structured = await page.evaluate(
        "(function(){ " + COLLECT + "; return _collectInteractivePage(true, null, 'full'); })()")
    listing = await page.evaluate(
        "(function(){ " + COLLECT + "; return _collectInteractivePage(false); })()")
    res["entries"] = len(structured)
    res["approx_tokens"] = round(len(listing or "") / 4)

    probe = await page.evaluate(PROBE, s.get("target_backend_node_id"))
    if not probe.get("found"):
        # NOT "absent from the snapshot" — that claim was false for all 13 of
        # the actions it used to exclude. With the repair in place this means
        # the id genuinely does not resolve, which is a defect to investigate
        # rather than a row to drop, so it is scored as a miss below.
        res["status"] = "target_not_in_dom"
        res["rendered"] = False
        res["exact"] = False
        res["recalled"] = False
        res["via"] = "none"
        return res

    listed = {str(e.get("mmid")) for e in structured}
    hit = next(((ref, via) for ref, via in credit_refs(probe) if ref in listed),
               (None, "none"))
    res["rendered"] = bool(probe.get("rendered"))
    res["exact"] = hit[1] == "own"
    res["recalled"] = hit[0] is not None
    res["via"] = hit[1]
    res["cap_withdrew"] = cap_withdrew(probe, listed)
    res["target_tag"] = probe.get("tag")
    res["target_text"] = probe.get("text")
    if not res["recalled"]:
        res["status"] = "missed_invisible" if not probe.get("rendered") else "missed_present"
    else:
        res["status"] = "ok"

    # Findability: the human's own task description as the query.
    if res["recalled"]:
        class FB:
            connected = True

            async def call(self, op, **kw):
                return structured

        ms.STATE["bridge"] = FB()
        want = hit[0]
        try:
            out = await _find(query=s.get("task") or "", tabId=1)
            refs = [ln.strip().split()[0].replace("ref_", "")
                    for ln in out.splitlines() if ln.strip().startswith("ref_")]
            rank = refs.index(want) + 1 if want in refs else 0
        except Exception:
            rank = 0
        res["rank"] = rank
        res["rr"] = round(1.0 / rank, 4) if rank else 0.0
    return res


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--baseline", action="store_true")
    ap.add_argument("--no-repair", dest="repair", action="store_false",
                    help="render the snapshots as they are stored — the pre-#73 "
                         "arm, which loses 13 targets in the parse and clones "
                         "nodes on 137 of 186 samples. For comparison only.")
    args = ap.parse_args()

    samples = load_samples(args.limit)
    if not samples:
        print("no samples — run tools/fetch_mind2web.py first")
        return 1
    sites = sorted({s.get("website") for s in samples})
    print(f"{len(samples)} labelled actions across {len(sites)} websites: {', '.join(sites)}")
    print("(none of these sites were used to build or tune the collector)")
    print("serialization repair: " + ("ON (XML self-closing undone before render)"
                                      if args.repair else
                                      "OFF  <- --no-repair: the pre-#73 arm, not the honest one") + "\n")

    t0 = time.time()
    rows = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 1600})
        await ctx.add_init_script(path=TAG_JS)
        page = await ctx.new_page()
        for i, s in enumerate(samples, 1):
            try:
                r = await score_one(page, s, repair=args.repair)
            except Exception as e:
                r = {"website": s.get("website"), "status": "error", "err": str(e)[:100]}
            rows.append(r)
            if i % 10 == 0 or i == len(samples):
                done = [x for x in rows if x.get("status") in SCORED]
                rec = sum(1 for x in done if x.get("recalled"))
                print(f"  [{i:>3}/{len(samples)}] recall so far "
                      f"{rec}/{len(done)} = {(rec/max(1,len(done))):.1%}")
        await browser.close()

    scored = [r for r in rows if r.get("status") in SCORED]
    if not scored:
        print("nothing scored")
        return 1
    rec = sum(1 for r in scored if r.get("recalled"))
    exact = sum(1 for r in scored if r.get("exact"))
    rendered = [r for r in scored if r.get("rendered")]
    rec_r = sum(1 for r in rendered if r.get("recalled"))
    rrs = [r.get("rr", 0.0) for r in scored if r.get("recalled")]
    status = Counter(r["status"] for r in rows)
    nodom = status.get("target_not_in_dom", 0)
    capped = [r for r in scored if r.get("cap_withdrew")]

    print(f"\n=== OUT-OF-SAMPLE (Mind2Web, {len(scored)} actions, {len(sites)} sites) ===")
    # ONE DENOMINATOR: every labelled action. The 13 that used to be dropped
    # here were dropped on a FALSE premise -- "the target element is absent from
    # the saved snapshot entirely" -- when every one of their ids is in the
    # snapshot and was lost in the parse. A target that still does not resolve
    # is a defect in this harness, not a row to excuse, so it is counted as a
    # miss and named in the status line. #22's rule applied to a ratio: a bound
    # nobody can see is indistinguishable from no bound.
    print(f"target recall            {rec}/{len(scored)} = {rec/len(scored):.1%}"
          f"   <- ALL labelled actions")
    if nodom:
        # Both figures, with which is which, because the second one is the
        # historical headline and it is the flattering one.
        # `rec` already excludes them: a row whose target never resolved is
        # never recalled, so the only thing that moves is the denominator.
        _res = len(scored) - nodom
        print(f"  ...of the {_res} whose target RESOLVED in the parsed DOM "
              f"{rec}/{_res} = {rec/max(1,_res):.1%}"
              f"   <- the pre-#73 headline; {nodom} action(s) excluded to get it")
    # The published MindAct figure is NOT known to use this denominator rule, and
    # nothing in this repo establishes that it does. Printed as context, flagged as
    # not-a-like-for-like, because an unqualified "vs 94.7%" is a comparison this
    # harness has not earned.
    print(f"  MindAct published baseline 94.7% — denominator rule NOT verified to "
          f"match; do not quote as a head-to-head")
    print(f"  ...of RENDERED targets {rec_r}/{len(rendered)} = "
          f"{rec_r/max(1,len(rendered)):.1%}   <- the number that reflects live behaviour")
    print(f"exact (no anc/desc credit) {exact}/{len(scored)} = {exact/len(scored):.1%}")
    print(f"via: {Counter(r.get('via') for r in scored).most_common()}")
    # Whether the bound fired, printed either way. A guard that is silent when it
    # does nothing is indistinguishable from one that is not there (#15).
    print(f"verdicts the {CREDIT_AREA_CAP:.0%}-of-viewport credit cap CHANGED: {len(capped)}"
          + ("   " + ", ".join(f"{r['website']}/{str(r.get('action_uid'))[:8]}"
                               for r in capped[:6]) if capped else
             "   (inert here — run --no-repair to see it fire: unrepaired, a\n     self-closed <a/> adopts half the page and claims one credit)"))
    print(f"findability (task as query)  MRR {statistics.fmean(rrs) if rrs else 0:.3f}   "
          f"top-3 {sum(1 for r in rrs if r >= 1/3)/max(1,len(rrs)):.1%}")
    print(f"median listing ~{statistics.median(r['approx_tokens'] for r in scored)} tokens, "
          f"{statistics.median(r['entries'] for r in scored)} entries")
    print(f"status: {dict(status)}")

    misses = [r for r in scored if r.get("status") == "missed_present"]
    if misses:
        print(f"\nREAL MISSES ({len(misses)}) — rendered with geometry and still dropped:")
        for r in misses[:12]:
            print(f"  {r['website']:<14} <{r.get('target_tag')}> {r.get('target_text','')[:52]!r}")
    if nodom:
        print(f"\nTARGET DID NOT RESOLVE ({nodom}) — counted as misses above. With the "
              f"repair ON this is a\nharness defect to investigate, not a dataset gap: "
              f"every id is in the saved string.")
        for r in [x for x in scored if x.get("status") == "target_not_in_dom"][:14]:
            print(f"  {r['website']:<14} {str(r.get('action_uid'))[:8]} {r.get('op')}")
    by_site = defaultdict(lambda: [0, 0])
    for r in scored:
        by_site[r["website"]][1] += 1
        if r.get("recalled"):
            by_site[r["website"]][0] += 1
    print("\nper-site recall: " + "  ".join(
        f"{k}={v[0]}/{v[1]}" for k, v in sorted(by_site.items())))

    payload = {"rows": rows, "sites": sites, "seconds": round(time.time() - t0, 1),
               # Which arm produced this, so a stored artifact cannot be read as
               # the other one. The two differ by ~1pp and by 13 actions.
               "repair": bool(args.repair), "n": len(scored),
               "recall": rec / len(scored), "recall_rendered": rec_r / max(1, len(rendered)),
               "exact": exact / len(scored)}
    (OUT / "bench_latest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if args.baseline:
        (OUT / "bench_baseline.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print("\nbaseline written -> temp/mind2web/bench_baseline.json")
    print(f"\n{round(time.time()-t0)}s  -> temp/mind2web/bench_latest.json")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
