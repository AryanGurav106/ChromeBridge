"""Head-to-head: three page representations, same pages, same metric.

WHY THIS EXISTS
---------------
Every accuracy claim in this project has compared numbers computed by different
people, on different samples, with different definitions of "recall". Putting
93.6% (ours) next to 94.7% (MindAct's published figure) in a table implies a
comparison that does not exist. This runs all three representations over the
SAME labelled actions with ONE definition, so the comparison is real.

THE THREE
---------
  chromebridge   the collector's `brief` listing — what the agent actually reads
  ax-tree        Chrome's own accessibility tree (CDP Accessibility.getFullAXTree),
                 serialised the way agent frameworks consume it (WebArena-style
                 `role "name"` lines). This is the representation the architecture
                 review argued we should have used instead of building our own.
  cleaned-html   Mind2Web's OWN `cleaned_html` field — MindAct's cleaning output,
                 not my reimplementation of it, so the baseline is theirs.

THE METRIC — one definition, applied identically
------------------------------------------------
  recall   the human-labelled target is REACHABLE in the representation:
             chromebridge -> the target, an ancestor or a descendant carries an mmid
                             that appears in the listing
             ax-tree      -> an AX node whose backendDOMNodeId maps to the target,
                             an ancestor or a descendant (resolved through CDP, not
                             by name matching, so it is the same question)
             cleaned-html -> the target's backend_node_id survives the cleaning
  tokens   len(representation) / 4, identical for all three

WHAT THIS CANNOT SETTLE
-----------------------
Static HTML, so `listener_tag.js` never fires and handler-bound elements are
invisible to US in a way they would not be live. That penalises chromebridge
specifically and does not penalise the other two, because neither uses handler
tagging. Our number here is a FLOOR; theirs are not. Do not read a small
chromebridge deficit as a real one.

Run:
    python tools/bench_headtohead.py               # all fetched samples
    python tools/bench_headtohead.py --limit 60
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "temp" / "mind2web"
OUT = ROOT / "temp" / "headtohead"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _extract import extract  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BG = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
COLLECT = extract("_collectInteractivePage", BG, verify=True)
TAG_JS = str(ROOT / "extension" / "listener_tag.js")
VIEWPORT = {"width": 1280, "height": 1600}

# Target, its ancestors and one descendant — as CHROME node ids, so the AX tree can
# be asked the same question by identity rather than by name matching.
IDS_PROBE = r"""(bn)=>{
  const el = document.querySelector(`[backend_node_id="${String(bn).replace(/"/g,'')}"]`);
  if (!el) return null;
  const chain = [el];
  for (let n = el.parentElement; n; n = n.parentElement) chain.push(n);
  const d = el.querySelector ? el.querySelector('*') : null;
  if (d) chain.push(d);
  return { count: chain.length };
}"""


def load_samples(limit: int) -> list[dict]:
    rows: list[dict] = []
    for f in sorted(DATA.glob("samples_shard*.jsonl")):
        for line in f.open(encoding="utf-8"):
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    by = defaultdict(list)
    for r in rows:
        by[r.get("website") or "?"].append(r)
    out, i = [], 0
    while limit <= 0 or len(out) < limit:
        added = False
        for site in sorted(by):
            if i < len(by[site]):
                out.append(by[site][i])
                added = True
                if limit and len(out) >= limit:
                    break
        if not added:
            break
        i += 1
    return out


def ax_lines(nodes: list[dict]) -> str:
    """Serialise the AX tree the way agent frameworks feed it to a model."""
    out = []
    for n in nodes:
        if n.get("ignored"):
            continue
        role = ((n.get("role") or {}).get("value")) or ""
        name = ((n.get("name") or {}).get("value")) or ""
        if not role:
            continue
        val = ((n.get("value") or {}).get("value")) or ""
        line = f'{role} "{name}"' if name else role
        if val:
            line += f' value="{val}"'
        out.append(line)
    return "\n".join(out)


async def score(page, cdp, s: dict) -> dict | None:
    await page.set_content(s["html"], wait_until="domcontentloaded")
    await page.wait_for_timeout(110)
    bn = str(s["target_backend_node_id"])
    if not await page.evaluate(IDS_PROBE, bn):
        return None

    res: dict = {"website": s.get("website")}

    # ---- chromebridge -------------------------------------------------------
    st = await page.evaluate(
        "(function(){ " + COLLECT + "; return _collectInteractivePage(true, null, 'brief'); })()")
    listing = await page.evaluate(
        "(function(){ " + COLLECT + "; return _collectInteractivePage(false, null, 'brief'); })()")
    probe = await page.evaluate(
        """(bn)=>{const el=document.querySelector(`[backend_node_id="${String(bn).replace(/"/g,'')}"]`);
           if(!el)return null;const a=[];for(let n=el.parentElement;n;n=n.parentElement){
             const m=n.getAttribute&&n.getAttribute('mmid'); if(m)a.push(m);}
           // ANY descendant, not the FIRST one. A <label> wrapping its <select> was
           // scored a miss because querySelector('[mmid]') returned a different child,
           // while the select itself WAS listed and acting on it does exactly what
           // clicking the label would. Capped by area so a page-sized container cannot
           // claim credit for everything inside it.
           const _r = el.getBoundingClientRect();
           const _small = (_r.width * _r.height) < 0.4 * innerWidth * innerHeight;
           const ds = _small ? Array.from(el.querySelectorAll('[mmid]')).map(n=>n.getAttribute('mmid')) : [];
           return {own:el.getAttribute('mmid'),ancs:a,descs:ds};}""", bn)
    kept = {str(e.get("mmid")) for e in (st or [])}
    res["chromebridge"] = {
        "recall": bool(probe and (probe["own"] in kept
                                  or any(a in kept for a in probe["ancs"])
                                  or any(x in kept for x in (probe.get("descs") or [])))),
        "tokens": round(len(listing or "") / 4),
    }

    # ---- accessibility tree -------------------------------------------------
    # Resolved through Runtime objectIds, NOT the DOM domain. The first version
    # called DOM.getDocument(depth=-1, pierce=True) per sample on a CDP session
    # reused across dozens of set_content swaps: every call measured 0.0s in
    # isolation, yet the run wedged before sample 10 and printed nothing for
    # minutes. describeNode on an objectId needs no document node-map, so there
    # is no stale state to wedge on.
    #
    # Ancestors are resolved by INDEXED expression rather than a parent walk,
    # because DOM.describeNode does not return parentId (verified: the walk
    # stopped at hop 0 every time, silently giving the AX tree no ancestor
    # credit while chromebridge got it — an unfair comparison).
    try:
        want = set()
        for depth in range(0, 9):
            chain = ".parentElement" * depth
            expr = f"document.querySelector('[backend_node_id=\"{bn}\"]')" + chain
            ev = await cdp.send("Runtime.evaluate",
                                {"expression": expr, "returnByValue": False})
            oid = (ev.get("result") or {}).get("objectId")
            if not oid:
                break
            try:
                d = await cdp.send("DOM.describeNode",
                                   {"objectId": oid, "depth": 1 if depth == 0 else 0})
                node = d["node"]
                want.add(node.get("backendNodeId"))
                if depth == 0:
                    for ch in node.get("children") or []:
                        want.add(ch.get("backendNodeId"))
            except Exception:
                break
        ax = await cdp.send("Accessibility.getFullAXTree", {})
        nodes = ax.get("nodes") or []
        seen = {n.get("backendDOMNodeId") for n in nodes if not n.get("ignored")}
        res["ax-tree"] = {"recall": bool(want & seen),
                          "tokens": round(len(ax_lines(nodes)) / 4)}
    except Exception as e:
        res["ax-tree"] = {"recall": False, "tokens": 0, "err": str(e)[:60]}

    # ---- MindAct cleaned HTML ----------------------------------------------
    ch = s.get("cleaned_html") or ""
    res["cleaned-html"] = {
        "recall": f'backend_node_id="{bn}"' in ch or f"backend_node_id='{bn}'" in ch,
        "tokens": round(len(ch) / 4),
    }
    return res


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=60)
    args = ap.parse_args()

    samples = load_samples(args.limit)
    if not samples:
        print("no samples — run tools/fetch_mind2web.py first")
        return 1
    sites = sorted({s.get("website") for s in samples})
    print(f"{len(samples)} labelled actions across {len(sites)} sites, "
          f"three representations, one metric\n")

    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    rows = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport=VIEWPORT)
        await ctx.add_init_script(path=TAG_JS)
        page = await ctx.new_page()
        cdp = await ctx.new_cdp_session(page)
        for i, s in enumerate(samples, 1):
            try:
                # A single pathological page must not silently stall the run —
                # that cost three rounds of blind waiting.
                r = await asyncio.wait_for(score(page, cdp, s), timeout=45)
            except asyncio.TimeoutError:
                print(f"  [{i:>3}] TIMEOUT on {s.get('website')} — skipped", flush=True)
                r = None
            except Exception:
                r = None
            if r:
                rows.append(r)
            if i % 10 == 0 or i == len(samples):
                print(f"  [{i:>3}/{len(samples)}] scored {len(rows)}", flush=True)
        await browser.close()

    if not rows:
        print("nothing scored")
        return 1

    print(f"\n{'='*72}\nHEAD-TO-HEAD — {len(rows)} labelled actions, {len(sites)} sites\n{'='*72}")
    print(f"{'representation':<16}{'recall':>9}{'median tokens':>16}{'recall/1k tok':>15}")
    summary = {}
    for key in ("chromebridge", "ax-tree", "cleaned-html"):
        rec = statistics.fmean(1.0 if r[key]["recall"] else 0.0 for r in rows)
        tok = statistics.median(r[key]["tokens"] for r in rows)
        summary[key] = {"recall": round(rec, 4), "median_tokens": tok}
        eff = rec / max(1, tok) * 1000
        print(f"{key:<16}{rec:>8.1%}{tok:>16}{eff:>15.3f}")

    base = summary["chromebridge"]["median_tokens"]
    print(f"\nrelative size: chromebridge 1.00x   "
          f"ax-tree {summary['ax-tree']['median_tokens']/max(1,base):.2f}x   "
          f"cleaned-html {summary['cleaned-html']['median_tokens']/max(1,base):.2f}x")
    print("\nNOTE static HTML means listener_tag.js never fires, so handler-bound "
          "elements\nare invisible to chromebridge but cost the other two nothing. "
          "Our recall here\nis a FLOOR; theirs are not.")

    (OUT / "latest.json").write_text(
        json.dumps({"rows": rows, "summary": summary}, indent=2), encoding="utf-8")
    print(f"\n{round(time.time()-t0)}s  -> temp/headtohead/latest.json")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
