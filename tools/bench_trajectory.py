"""TOKENS-TO-COMPLETION: what a representation costs over a WHOLE task.

WHY THIS EXISTS
---------------
Every other measurement in this project scores ONE observation. That is the wrong
unit for the questions now open:

  - dropping `box()` makes each read smaller but might cost an extra read;
  - a region index makes the first read much smaller and adds a round trip;
  - folding makes a read smaller but can hide the one row the task needed.

Per-read tokens flatter all three. Per-read answerability damns all three. The
question is what the agent spends to finish the task, so that is what this
measures: walk a labelled multi-step trajectory and sum the observation cost of
the reads a representation forces.

WHAT MAKES IT HONEST
--------------------
Reachability is scored on the **string listing** — the surface the agent actually
acts on — not on the structured array. Those differ: the string listing is
viewport-scoped and capped at 150 entries, so a target can be in `structured`
(which is what `bench_mind2web.py` scores) and still be absent from what the
agent was shown. A ref counts as reachable if it appears anywhere the agent can
act on it, including inside a folded group row and including the PROBABLY
DECORATION tier, because both are explicitly actionable by ref.

`recall_structured` is also reported, unchanged in definition, so this ruler can
be checked against `bench_mind2web.py` on the old question before it is trusted
on the new one. A new ruler that disagrees with the old one about the old
measurement is broken, not insightful.

HONEST LIMITS — do not quote a number from here without these
--------------------------------------------------------------
  - It is a LOWER BOUND. It assumes the agent walks the human's gold path, so it
    cannot see "the representation misled the agent into a different action".
    Only a live fan-out sees that.
  - It inherits every Mind2Web limitation already documented in CLAUDE.md #18:
    serialized HTML rendered in a blank browser, so no handler tagging, most
    external CSS gone, no post-load framework rendering. Structural subset only.
  - Task count is small. Report n, always; widen with tools/fetch_mind2web.py.
  - Tokens are `len(text)/4`, the same approximation the rest of the suite uses.
    Fine for comparing representations, not a billing figure.

Run:
    python tools/bench_trajectory.py                     # all policies
    python tools/bench_trajectory.py --policies current
    python tools/bench_trajectory.py --limit-tasks 6     # smoke
    python tools/bench_trajectory.py --baseline
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
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _extract import extract  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BG = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
COLLECT = extract("_collectInteractivePage", BG, verify=True)
TAG_JS = str(ROOT / "extension" / "listener_tag.js")

# Reuse the sibling benchmark's target probe rather than restating it. Its
# ancestor/descendant credit rules were corrected twice on measured evidence
# (CLAUDE.md #18: walking the WHOLE ancestor chain, and ANY descendant capped by
# area), and a second copy here would drift away from them silently.
_spec = importlib.util.spec_from_file_location("bm", ROOT / "tools" / "bench_mind2web.py")
bm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bm)
PROBE = bm.PROBE


# REPRESENTATION POLICIES. Each names the collector arguments that produce the
# agent-facing string. New presentation work adds an entry here; the engine below
# never needs to know what changed. `reads` is how many observations the policy
# forces to make one target actionable — a flat listing is always 1, a region
# index is 1 plus an expansion when the target is not already named in the index.
# Args are spelled out to match what the op router actually sends
# (`case "get_interactive_elements"`: structured, scopeMmid, detail, ledger).
# Passing fewer positionals and letting them default is how a benchmark drifts
# away from the shipped path — the same class of gap as CLAUDE.md #19's untested
# router, where `detail="brief"` never reached the collector.
POLICIES: dict[str, dict] = {
    # The shipped default, whatever it currently is.
    "current": {"args": "false, null, 'compact', false", "reads": 1},
    # TREE: the same entries, re-shaped. Serialization only — it consumes the
    # structured array the collector already returns, so refs, AccName, visibility
    # and every flag are identical and the ONLY variable is the shape. That is the
    # comparison worth making; adding text nodes at the same time would confound it.
    # Same 6th positional the op router will send. Identical population to
    # `current` -- post viewport-filter, post entry-cap -- so the only variable is
    # the shape.
    "tree": {"args": "false, null, 'compact', false, false, 'tree'", "reads": 1},
}


# An mmid is digits, or `f<frameId>:<n>` for a cross-origin frame. Matching a
# looser alphabet made the fold pattern harvest the literal word "ref" out of
# the phrase `shown as ref:"label"` — harmless here, but a ref set that contains
# things that are not refs is the wrong foundation for a reachability metric.
_MMID = r"(?:f\d+:\d+|\d+)"
_REF_LINE = re.compile(r"ref_(" + _MMID + r")")
_REF_FOLD = re.compile(r"(?:^|\s)(" + _MMID + r"):\"")
_REF_ICON = re.compile(r"(?:^|\s)(" + _MMID + r")@\(")
_REF_BARE = re.compile(r"(?:^|\s)(" + _MMID + r")(?=\s|$)")


def listing_refs(text: str) -> set[str]:
    """Every ref the agent can act on, in every form the serializer emits.

    Five shapes, all actionable and all easy to miss:
      ref_52 | a "post" ...                        an ordinary row
      ... shown as ref:"label" ...: 398:"list"     a shape/record fold
      ... reading order): 232@(24,57)              an unlabelled-icon fold
      ... ordered top-to-bottom; refs: 556 593     a per-row-label fold
      9 generic-no-label (ref_17 ref_23)           the PROBABLY DECORATION tier

    Counting only the first shape would score every folded row as unreachable and
    make folding look catastrophic, which is exactly backwards.
    """
    if not text:
        return set()
    refs: set[str] = set(_REF_LINE.findall(text))
    refs |= set(_REF_FOLD.findall(text))
    refs |= set(_REF_ICON.findall(text))
    for line in text.splitlines():
        # `refs: 556 593 667` — bare integers, only on lines that announce them,
        # so ordinary prose containing a number is not mistaken for a ref.
        if "refs:" in line:
            refs |= set(_REF_BARE.findall(line.split("refs:", 1)[1]))
    return {r for r in refs if r}


def load_tasks(limit_tasks: int, limit_steps: int) -> list[list[dict]]:
    """Group actions into gold-path trajectories, preserving on-disk order.

    Verified on the fetched shards: `annotation_id` groups actions into one task
    and its rows are contiguous within a shard, so file order IS step order.
    There is no explicit step index in the data, which is why order must be
    preserved rather than reconstructed.
    """
    tasks: dict[str, list[dict]] = defaultdict(list)
    order: list[str] = []
    for f in sorted(DATA.glob("samples_shard*.jsonl")):
        with f.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                a = d.get("annotation_id") or "?"
                if a not in tasks:
                    order.append(a)
                tasks[a].append(d)
    out = [tasks[a] for a in order if len(tasks[a]) >= 2]
    if limit_steps:
        out = [t[:limit_steps] for t in out]
    # Widest site coverage first, so a --limit-tasks smoke run is not one site.
    out.sort(key=lambda t: (t[0].get("website") or "", len(t)))
    if limit_tasks:
        seen: dict[str, int] = Counter()
        picked = []
        for t in out:
            site = t[0].get("website") or "?"
            if seen[site] < max(1, limit_tasks // 8):
                picked.append(t)
                seen[site] += 1
            if len(picked) >= limit_tasks:
                break
        out = picked or out[:limit_tasks]
    return out


async def score_step(page, s: dict, policy: dict) -> dict:
    """One action: cost of the observation(s), and whether the target was in them."""
    r: dict = {"website": s.get("website"), "action_uid": s.get("action_uid"),
               "op": s.get("operation")}
    await page.set_content(s["html"], wait_until="domcontentloaded")
    await page.wait_for_timeout(120)

    structured = await page.evaluate(
        "(function(){ " + COLLECT + "; return _collectInteractivePage(true, null, 'full'); })()")
    listing = await page.evaluate(
        "(function(){ " + COLLECT + "; return _collectInteractivePage(" + policy["args"] + "); })()")
    listing = listing if isinstance(listing, str) else ""
    r["base_tokens"] = round(len(listing) / 4)
    r["reads"] = policy["reads"]
    r["entries"] = len(structured or [])

    probe = await page.evaluate(PROBE, s.get("target_backend_node_id"))
    if not probe.get("found"):
        r["status"] = "target_not_in_html"
        r["tokens"] = r["base_tokens"] * r["reads"]
        return r

    by_mmid = {str(e.get("mmid")): e for e in (structured or [])}
    credited = [x for x in ([probe.get("own")] + (probe.get("ancs") or [])
                            + (probe.get("descs") or [])) if x]
    # Same credit rule as bench_mind2web: the target itself, any ancestor, or any
    # (area-capped) descendant we surfaced instead.
    in_structured = [c for c in credited if c in by_mmid]
    shown = listing_refs(listing)
    in_listing = [c for c in in_structured if c in shown]

    r["rendered"] = bool(probe.get("rendered"))
    r["recall_structured"] = bool(in_structured)
    r["reachable"] = bool(in_listing)
    r["target_tag"] = probe.get("tag")
    r["target_text"] = probe.get("text")

    # WHY IS IT NOT SHOWN? The first version of this metric scored every
    # collected-but-unlisted target as a failure, which conflates three very
    # different situations and is not how the tool behaves. The listing is
    # viewport-scoped and capped at 150 entries, and in BOTH of those cases it
    # says so and names the recovery — so the honest cost is an extra
    # observation, not an unreachable target. Charging them as failures would
    # also have flattered any change that merely made the listing bigger, which
    # is the exact failure mode CLAUDE.md #16 says to re-derive before believing.
    if r["reachable"]:
        r["status"] = "ok"
    elif in_structured:
        ent = by_mmid[in_structured[0]]
        # ORDER MATTERS, and getting it wrong hid a real result. Classifying on
        # `offscreen` FIRST reported 43 steps as below_viewport after collection
        # had started keeping offscreen controls — which is impossible, and was
        # this classifier mislabelling elements the 150-entry CAP had removed
        # from a listing that would otherwise have carried them. An element can
        # be both offscreen and past the cap; the cap is then the filter that
        # actually removed it, and the recovery is a scoped read, not a scroll.
        if "listing capped at" in listing:
            r["status"] = "over_cap"
            r["reads"] += 1
        elif ent.get("offscreen"):
            # The listing says what is off-viewport, and now also WHICH REGIONS hold
            # it, so there are two recoveries with very different prices: scroll and
            # re-read the whole page, or read one region by ref. Charge the cheaper
            # one the agent can actually reach, because charging a full re-read
            # would price a capability the tool no longer forces.
            r["status"] = "below_viewport"
            r["reads"] += 1
            r["recovery"] = "rescan"
            best = None
            for anc in (probe.get("ancs") or [])[:6]:
                if anc not in by_mmid and anc != in_structured[0]:
                    pass
                try:
                    sub = await page.evaluate(
                        "(function(){ " + COLLECT + "; return _collectInteractivePage("
                        + policy["args"].replace("null", "'" + str(anc) + "'", 1) + "); })()")
                except Exception:
                    continue
                if not isinstance(sub, str) or not sub:
                    continue
                # Only counts if the target is actually reachable in that scoped read
                # — a region that does not contain it is not a recovery.
                if any(c in listing_refs(sub) for c in in_structured):
                    n = round(len(sub) / 4)
                    if best is None or n < best:
                        best = n
            if best is not None and best < r["base_tokens"]:
                r["recovery"] = "scoped"
                r["scoped_tokens"] = best
        else:
            # On-screen, collected, and cut by the char budget.
            r["status"] = "over_cap"
            r["reads"] += 1
    else:
        r["status"] = "missed_invisible" if not probe.get("rendered") else "missed_present"
    # Recoverable with an extra read, as opposed to absent from the observation
    # entirely at any budget.
    r["recoverable"] = r["status"] in ("ok", "below_viewport", "over_cap")
    # An extra read costs another observation. A forced RESCAN is charged at the
    # size of the listing it re-reads; a SCOPED recovery is charged at the measured
    # size of that scoped read, which is the whole point of naming the regions.
    r["tokens"] = r["base_tokens"] * r["reads"]
    if r.get("recovery") == "scoped":
        r["tokens"] = r["base_tokens"] + r["scoped_tokens"]
    return r


async def run_policy(page, tasks: list[list[dict]], name: str, policy: dict) -> dict:
    per_task, steps = [], []
    for ti, t in enumerate(tasks, 1):
        tok = rd = 0
        ok_steps = 0
        first_bad = None
        for si, s in enumerate(t):
            try:
                r = await score_step(page, s, policy)
            except Exception as e:
                r = {"status": "error", "err": str(e)[:120], "tokens": 0, "reads": 0,
                     "website": s.get("website")}
            r["task_i"], r["step_i"] = ti, si
            steps.append(r)
            tok += r.get("tokens") or 0
            rd += r.get("reads") or 0
            if r.get("reachable"):
                ok_steps += 1
            # A task is broken only by a target no budget reaches. A scroll or a
            # scoped read is a cost, already charged in tokens and reads above.
            if first_bad is None and not r.get("recoverable", True) \
                    and r.get("status") != "target_not_in_html":
                first_bad = si
        scoreable = [x for x in t]
        per_task.append({"website": t[0].get("website"), "steps": len(scoreable),
                         "tokens": tok, "reads": rd, "reachable_steps": ok_steps,
                         "complete": first_bad is None,
                         "first_unreachable_step": first_bad,
                         "task": (t[0].get("task") or "")[:70]})
        print(f"  [{name}] task {ti}/{len(tasks)} {t[0].get('website'):<14} "
              f"{len(scoreable)} steps  {tok:>6} tok  {ok_steps}/{len(scoreable)} reachable")
    return {"policy": name, "tasks": per_task, "steps": steps}


def report(res: dict) -> dict:
    name = res["policy"]
    tasks, steps = res["tasks"], res["steps"]
    scored = [s for s in steps if s.get("status") in
              ("ok", "below_viewport", "over_cap", "missed_present", "missed_invisible")]
    if not scored or not tasks:
        print(f"\n[{name}] nothing scored")
        return {}
    reach = sum(1 for s in scored if s.get("reachable"))
    recov = sum(1 for s in scored if s.get("recoverable"))
    rec = sum(1 for s in scored if s.get("recall_structured"))
    toks = [t["tokens"] for t in tasks]
    summary = {
        "policy": name,
        "tasks": len(tasks),
        "steps": len(scored),
        "median_tokens_per_task": int(statistics.median(toks)),
        "mean_tokens_per_task": int(statistics.fmean(toks)),
        "total_tokens": sum(toks),
        "total_reads": sum(t["reads"] for t in tasks),
        "step_reachable_first_read": reach / len(scored),
        "step_recoverable": recov / len(scored),
        "recall_structured": rec / len(scored),
        "task_complete": sum(1 for t in tasks if t["complete"]) / len(tasks),
    }
    print(f"\n=== {name} — {len(tasks)} tasks, {len(scored)} steps ===")
    print(f"tokens to completion   median {summary['median_tokens_per_task']:>7}"
          f"   mean {summary['mean_tokens_per_task']:>7}"
          f"   total {summary['total_tokens']:>8}")
    print(f"reads (incl. forced re-reads)     {summary['total_reads']}")
    print(f"reachable on the FIRST read       {reach}/{len(scored)} = "
          f"{summary['step_reachable_first_read']:.1%}   <- the agent-facing number")
    print(f"recoverable with an extra read    {recov}/{len(scored)} = "
          f"{summary['step_recoverable']:.1%}")
    print(f"recall_structured (bench_mind2web definition)  {rec}/{len(scored)} = "
          f"{summary['recall_structured']:.1%}   <- cross-check")
    print(f"tasks completable end-to-end      {summary['task_complete']:.1%}")
    print(f"status: {dict(Counter(s['status'] for s in steps))}")
    rec = Counter(s.get("recovery") for s in scored if s.get("recovery"))
    if rec:
        # A "scoped" recovery means the region index let the agent read ONE container
        # by ref instead of re-listing the page after a scroll.
        print(f"off-viewport recovery: {dict(rec)}")
    # THE POPULATION NO SINGLE-OBSERVATION METRIC CAN SEE: collected, and not in
    # the listing the agent read. Split by cause, because the two have opposite
    # fixes — `below_viewport` is the deliberate viewport scoping (a scroll), and
    # `over_cap` is the 150-entry cap biting (a scoped read, or a representation
    # that fits more in the same budget, which is what this overhaul is for).
    for cause in ("below_viewport", "over_cap"):
        gap = [s for s in scored if s.get("status") == cause]
        if not gap:
            continue
        print(f"\n{cause.upper()} ({len(gap)} steps) — collected, absent from the "
              f"first listing:")
        for s in gap[:8]:
            print(f"  {s.get('website'):<14} <{s.get('target_tag')}> "
                  f"{(s.get('target_text') or '')[:48]!r}")
    return summary


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--policies", default="", help="comma-separated subset of " + ",".join(POLICIES))
    ap.add_argument("--limit-tasks", type=int, default=0)
    ap.add_argument("--limit-steps", type=int, default=0)
    ap.add_argument("--baseline", action="store_true")
    args = ap.parse_args()

    want = [p.strip() for p in args.policies.split(",") if p.strip()] or list(POLICIES)
    bad = [p for p in want if p not in POLICIES]
    if bad:
        print(f"unknown policy: {bad}; have {list(POLICIES)}")
        return 1

    tasks = load_tasks(args.limit_tasks, args.limit_steps)
    if not tasks:
        print("no multi-step tasks — run tools/fetch_mind2web.py first")
        return 1
    sites = sorted({t[0].get("website") for t in tasks})
    nsteps = sum(len(t) for t in tasks)
    print(f"{len(tasks)} multi-step tasks, {nsteps} actions, {len(sites)} sites: "
          f"{', '.join(sites)}")
    print(f"steps per task: min {min(len(t) for t in tasks)} "
          f"median {int(statistics.median(len(t) for t in tasks))} "
          f"max {max(len(t) for t in tasks)}")
    print("(none of these sites were used to build or tune the collector)\n")

    t0 = time.time()
    out = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 1600})
        await ctx.add_init_script(path=TAG_JS)
        page = await ctx.new_page()
        for name in want:
            out[name] = await run_policy(page, tasks, name, POLICIES[name])
        await browser.close()

    summaries = [s for s in (report(out[n]) for n in want) if s]
    if len(summaries) > 1:
        base = summaries[0]
        print(f"\n=== RELATIVE TO {base['policy']} ===")
        for s in summaries[1:]:
            dt = (s["total_tokens"] - base["total_tokens"]) / max(1, base["total_tokens"])
            print(f"{s['policy']:<18} tokens {dt:+.1%}   reads "
                  f"{s['total_reads'] - base['total_reads']:+d}   "
                  f"first-read {s['step_reachable_first_read'] - base['step_reachable_first_read']:+.1%}   "
                  f"task-complete {s['task_complete'] - base['task_complete']:+.1%}")

    payload = {"summaries": summaries, "sites": sites, "tasks": len(tasks),
               "actions": nsteps, "seconds": round(time.time() - t0, 1),
               "detail": {n: out[n]["tasks"] for n in want}}
    (DATA / "trajectory_latest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if args.baseline:
        (DATA / "trajectory_baseline.json").write_text(json.dumps(payload, indent=2),
                                                       encoding="utf-8")
        print("\nbaseline written -> temp/mind2web/trajectory_baseline.json")
    print(f"\n{round(time.time()-t0)}s  -> temp/mind2web/trajectory_latest.json")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
