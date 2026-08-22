"""Information retention per token — the north-star metric, as a number.

THE PROBLEM THIS SOLVES
-----------------------
Every heuristic in the collector was tuned by anecdote inside measured
guardrails: recall, ambiguity and token cost were reported SEPARATELY, with no
exchange rate between them. So "is this threshold right?" had no answer, and
"did change N+1 help?" required launching live agents and reading transcripts.

This turns the project's stated north star — represent a page in the LOWEST
dimension with the HIGHEST information retention — into a single curve you can
regress against: retention plotted against tokens, per detail level.

WHAT IS MEASURED
----------------
Ground truth is derived from the DOM INDEPENDENTLY of the collector, so the
metric cannot be satisfied by the collector agreeing with itself. For a sample
of elements a user could plausibly ask about, we record a descriptor (how a
person would refer to it) and a KEY FACT (the thing an agent would need):

    link      -> href            input/textarea -> value
    checkbox  -> checked state   image          -> src
    button    -> accessible name select         -> selected option

Three components, all in [0,1]:

  presence      the element appears in the listing at all
  answerability its key fact appears in the listing (this is the metric that
                catches SILENT OMISSION — the class that produced "compact has
                no href", "media has no src", "no ref-addressable code block")
  findability   the real find() scorer, fed the descriptor as a query, ranks the
                target in its top 3 (mean reciprocal rank also reported)

Cost is the listing size. Tokens are approximated as chars/4 and labelled as
such — the ratio is what matters for comparing two builds, and a real tokenizer
would add a dependency for no change in ordering.

HONEST LIMITS
-------------
- Ground truth is DOM-derived, so it inherits the DOM's blind spots: it cannot
  see canvas-drawn or pixel-only content, and it will not ask about things no
  DOM query can find. It measures omission against what IS in the DOM.
- Sites flagged unstable by `freeze_corpus.py --verify` will jitter slightly.
- This is a DEV-SET metric. The corpus was used to build the collector, so a
  high score here proves the absence of regressions, NOT generalization. For
  that you need held-out sites; see --holdout.

Run:
    python tools/measure_retention.py                 # frozen corpus, all levels
    python tools/measure_retention.py --limit 10
    python tools/measure_retention.py --live          # bypass recordings
    python tools/measure_retention.py --holdout 0.3   # report dev/held-out split
    python tools/measure_retention.py --baseline      # write the frontier file
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
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
FROZEN = ROOT / "temp" / "frozen"
OUT = ROOT / "temp" / "retention"
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

# The real find() scorer, imported rather than reimplemented — a reimplementation
# would drift from the thing being measured, which is the whole failure mode this
# suite exists to catch.
_spec = importlib.util.spec_from_file_location("ms", ROOT / "mcp_server.py")
ms = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ms)
_find = ms.find.fn if hasattr(ms.find, "fn") else ms.find


# --------------------------------------------------------------------------
# Ground truth, derived from the DOM independently of the collector.
# --------------------------------------------------------------------------
GROUND_TRUTH = r"""
(function () {
  const vw = innerWidth, vh = innerHeight;
  const vis = (el) => {
    try {
      const r = el.getBoundingClientRect();
      if (r.width < 8 || r.height < 8) return false;
      if (r.bottom <= 0 || r.top >= vh || r.right <= 0 || r.left >= vw) return false;
      const cs = getComputedStyle(el);
      if (cs.visibility === 'hidden' || cs.display === 'none') return false;
      if (parseFloat(cs.opacity || '1') === 0) return false;
      return true;
    } catch (e) { return false; }
  };
  const txt = (el) => (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
  const items = [];
  const push = (el, kind, descriptor, factName, fact) => {
    if (!descriptor || !fact) return;
    if (String(descriptor).length < 2 || String(descriptor).length > 90) return;
    items.push({ kind, descriptor: String(descriptor).slice(0, 90),
                 factName, fact: String(fact).slice(0, 300) });
  };

  for (const a of document.querySelectorAll('a[href]')) {
    if (!vis(a)) continue;
    const h = a.getAttribute('href') || '';
    if (!h || h.startsWith('javascript:') || h === '#') continue;
    push(a, 'link', txt(a) || a.getAttribute('aria-label'), 'href', h);
  }
  for (const el of document.querySelectorAll('input,textarea')) {
    if (!vis(el)) continue;
    const t = (el.getAttribute('type') || 'text').toLowerCase();
    const lbl = (el.labels && el.labels[0] ? el.labels[0].innerText : '') ||
                el.getAttribute('aria-label') || el.getAttribute('name') ||
                el.getAttribute('placeholder') || '';
    if (t === 'checkbox' || t === 'radio') {
      push(el, 'checkbox', lbl, 'checked', el.checked ? 'true' : '');
    } else if (t !== 'hidden' && el.value) {
      push(el, 'field', lbl, 'value', el.value);
    }
  }
  for (const b of document.querySelectorAll('button,[role="button"]')) {
    if (!vis(b)) continue;
    push(b, 'button', txt(b) || b.getAttribute('aria-label'), 'name',
         txt(b) || b.getAttribute('aria-label'));
  }
  for (const im of document.querySelectorAll('img')) {
    if (!vis(im)) continue;
    const r = im.getBoundingClientRect();
    if (r.width < 24 || r.height < 24) continue;
    push(im, 'image', im.getAttribute('alt') || im.getAttribute('title'), 'src',
         im.currentSrc || im.getAttribute('src') || '');
  }
  for (const s of document.querySelectorAll('select')) {
    if (!vis(s)) continue;
    const o = s.options && s.options[s.selectedIndex];
    const lbl = (s.labels && s.labels[0] ? s.labels[0].innerText : '') ||
                s.getAttribute('aria-label') || s.getAttribute('name') || '';
    if (o) push(s, 'select', lbl, 'value', o.text);
  }
  // Deduplicate on (descriptor, fact) so a repeated nav link is one question.
  const seen = new Set(), uniq = [];
  for (const it of items) {
    const k = it.kind + '|' + it.descriptor + '|' + it.fact;
    if (seen.has(k)) continue;
    seen.add(k); uniq.push(it);
  }
  return uniq;
})()
"""


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().casefold()


def _fact_present(listing: str, kind: str, fact: str) -> bool:
    """Is the key fact recoverable from the listing text?

    URLs are compared on their distinctive tail: listings legitimately resolve
    relative hrefs to absolute and may clip long query strings, so a raw
    substring test would score a correct answer as a miss.
    """
    L = listing.casefold()
    f = _norm(fact)
    if not f:
        return False
    if kind in ("link", "image"):
        tail = re.split(r"[?#]", str(fact))[0].rstrip("/").split("/")[-1].casefold()
        return bool(tail) and tail in L
    return f[:60] in L


async def measure_page(page, name: str) -> dict:
    truth = await page.evaluate(GROUND_TRUTH)
    if not truth:
        return {"name": name, "skipped": "no ground truth"}

    # FORMAT MATTERS AND WAS BEING LEFT UNSET. `format` is the 6th positional of
    # _collectInteractivePage and TREEFMT is `format === 'tree'`, so omitting it
    # measured the FLAT listing -- while the shipped default has been "tree" since
    # CLAUDE.md #27. Every corpus token figure this tool produced described a
    # surface the agent no longer receives by default. Both are measured now, and
    # the default one is what `approx_tokens` reports; `flat_tokens` keeps the
    # older series comparable and prices the format choice on real pages.
    levels = {}
    for level in ("compact", "brief", "full"):
        async def _listing(fmt: str) -> str:
            return await page.evaluate(
                "(function(){ " + COLLECT + "; return _collectInteractivePage("
                "false, null, '" + level + "', false, false, '" + fmt + "'); })()") or ""
        tree_listing, flat_listing = await _listing("tree"), await _listing("flat")
        structured = await page.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(true, null, '"
            + level + "'); })()")
        levels[level] = {"listing": tree_listing, "flat": flat_listing,
                         "structured": structured or []}

    # Cap the question set so one enormous page cannot dominate the corpus mean.
    sample = truth[:60]
    res: dict = {"name": name, "questions": len(sample)}

    for level, data in levels.items():
        listing, structured = data["listing"], data["structured"]
        hay = " ".join(
            " ".join(str(e.get(k) or "") for k in
                     ("name", "label", "value", "placeholder", "text", "near"))
            for e in structured).casefold()

        present = sum(1 for q in sample if _norm(q["descriptor"])[:40] in hay)
        answerable = sum(1 for q in sample if _fact_present(listing, q["kind"], q["fact"]))
        res[level] = {
            "chars": len(listing),
            "approx_tokens": round(len(listing) / 4),
            "flat_tokens": round(len(data["flat"]) / 4),
            "entries": len(structured),
            "presence": round(present / len(sample), 4),
            "answerability": round(answerable / len(sample), 4),
        }

    # Findability uses the REAL scorer over the full structured listing.
    class FB:
        connected = True

        def __init__(self, entries):
            self.entries = entries

        async def call(self, op, **kw):
            return self.entries

    ms.STATE["bridge"] = FB(levels["full"]["structured"])
    ranks = []
    for q in sample[:20]:                      # scorer calls are the slow part
        try:
            out = await _find(query=q["descriptor"], tabId=1)
        except Exception:
            ranks.append(0.0)
            continue
        refs = [ln.strip().split()[0] for ln in out.splitlines() if ln.strip().startswith("ref_")]
        hit = 0.0
        for i, r in enumerate(refs[:10], 1):
            mm = r.replace("ref_", "")
            e = next((x for x in levels["full"]["structured"] if str(x.get("mmid")) == mm), None)
            if e and _norm(q["descriptor"])[:30] in _norm(
                    " ".join(str(e.get(k) or "") for k in ("name", "label", "text", "value"))):
                hit = 1.0 / i
                break
        ranks.append(hit)
    res["findability"] = {
        "mrr": round(statistics.fmean(ranks), 4) if ranks else 0.0,
        "top3": round(sum(1 for r in ranks if r >= 1 / 3) / len(ranks), 4) if ranks else 0.0,
        "n": len(ranks),
    }
    return res


async def run_site(browser, name: str, url: str, live: bool) -> dict:
    ctx = await browser.new_context(viewport=VIEWPORT)
    try:
        await ctx.add_init_script(path=TAG_JS)
        if not live:
            har = FROZEN / f"{name}.har"
            if not har.exists():
                return {"name": name, "skipped": "no recording"}
            await ctx.route_from_har(str(har), not_found="abort")
        page = await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=40000)
        try:
            await page.wait_for_load_state("networkidle", timeout=6000)
        except Exception:
            pass
        await page.wait_for_timeout(900)
        return await measure_page(page, name)
    except Exception as e:
        return {"name": name, "skipped": str(e)[:120]}
    finally:
        await ctx.close()


def load_sites() -> list[tuple[str, str]]:
    src = (ROOT / "tools" / "capture_listings.py").read_text(encoding="utf-8")
    body = src[src.index("SITES = ["):src.index("\nOUT = ")]
    return re.findall(r'\(\s*"([a-z_0-9]+)"\s*,\s*"(https?://[^"]+)"', body)


def summarise(rows: list[dict], label: str) -> dict:
    scored = [r for r in rows if "compact" in r]
    if not scored:
        print(f"\n{label}: no sites scored")
        return {}
    out = {"label": label, "sites": len(scored)}
    print(f"\n=== {label} ({len(scored)} sites) ===")
    print(f"{'level':<9} {'tree~':>8} {'flat~':>8} {'entries':>8} {'presence':>9} {'answerable':>11}")
    for level in ("compact", "brief", "full"):
        tok = statistics.median(r[level]["approx_tokens"] for r in scored)
        flat = statistics.median(r[level].get("flat_tokens", 0) for r in scored)
        ent = statistics.median(r[level]["entries"] for r in scored)
        pres = statistics.fmean(r[level]["presence"] for r in scored)
        ans = statistics.fmean(r[level]["answerability"] for r in scored)
        out[level] = {"median_tokens": tok, "median_flat_tokens": flat,
                      "median_entries": ent,
                      "presence": round(pres, 4), "answerability": round(ans, 4),
                      "retention": round((pres + ans) / 2, 4)}
        print(f"{level:<9} {tok:>8} {flat:>8} {ent:>8} {pres:>9.3f} {ans:>11.3f}")
    mrr = statistics.fmean(r["findability"]["mrr"] for r in scored if "findability" in r)
    top3 = statistics.fmean(r["findability"]["top3"] for r in scored if "findability" in r)
    out["findability"] = {"mrr": round(mrr, 4), "top3": round(top3, 4)}
    print(f"findability (full):  MRR {mrr:.3f}   top-3 {top3:.3f}")
    r_c, r_f = out["compact"], out["full"]
    ret_c = (r_c["presence"] + r_c["answerability"] + mrr) / 3
    ret_f = (r_f["presence"] + r_f["answerability"] + mrr) / 3
    out["retention_per_ktoken"] = {
        "compact": round(ret_c / max(1, r_c["median_tokens"]) * 1000, 4),
        "full": round(ret_f / max(1, r_f["median_tokens"]) * 1000, 4)}
    print(f"RETENTION  compact {ret_c:.3f} @ ~{r_c['median_tokens']} tok   "
          f"full {ret_f:.3f} @ ~{r_f['median_tokens']} tok")
    return out


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", default="")
    ap.add_argument("--live", action="store_true", help="ignore recordings, hit the network")
    ap.add_argument("--holdout", type=float, default=0.0,
                    help="fraction of sites reported separately as held-out (deterministic split)")
    ap.add_argument("--baseline", action="store_true", help="write temp/retention/baseline.json")
    args = ap.parse_args()

    sites = load_sites()
    if args.only:
        want = {s.strip() for s in args.only.split(",")}
        sites = [s for s in sites if s[0] in want]
    if args.limit:
        sites = sites[: args.limit]

    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    rows = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for i, (name, url) in enumerate(sites, 1):
            r = await run_site(browser, name, url, args.live)
            rows.append(r)
            if "skipped" in r:
                print(f"  [{i:>3}/{len(sites)}] skip {name:<24} {r['skipped']}")
            else:
                c, f = r["compact"], r["full"]
                print(f"  [{i:>3}/{len(sites)}] ok   {name:<24} "
                      f"tok {c['approx_tokens']:>5}/{f['approx_tokens']:<5} "
                      f"pres {c['presence']:.2f}  ans {c['answerability']:.2f}->{f['answerability']:.2f}")
        await browser.close()

    if args.holdout > 0:
        # Deterministic split on site name, so the held-out set is stable across
        # runs and cannot be reshuffled until a number looks good.
        held = {n for n, _ in sites if (hash(n) % 100) < args.holdout * 100}
        dev = summarise([r for r in rows if r["name"] not in held], "DEV")
        ho = summarise([r for r in rows if r["name"] in held], "HELD-OUT")
        summary = {"dev": dev, "holdout": ho}
    else:
        summary = {"all": summarise(rows, "CORPUS")}

    payload = {"sites": rows, "summary": summary, "seconds": round(time.time() - t0, 1),
               "mode": "live" if args.live else "frozen"}
    (OUT / "latest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if args.baseline:
        (OUT / "baseline.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print("\nbaseline written -> temp/retention/baseline.json")
    print(f"\n{round(time.time() - t0)}s   -> temp/retention/latest.json")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
