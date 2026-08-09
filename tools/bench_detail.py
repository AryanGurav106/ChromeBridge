"""Does the two-step path actually answer URL/media questions, and what does it cost?

Compares the two designs that were on the table for surfacing link targets and
image sources, on realistic tasks against live pages:

  A (shipped)  compact by default; when the answer needs a URL, re-read that ONE
               element with detail="full".
  B (rejected) every observation is detail="full", so a URL is always present.

For each task it verifies the path actually works — the target must be locatable
in the compact listing, and the scoped full read must contain the answer — and
then prices both designs over a task of OBS observations.

WHAT THIS DOES NOT MEASURE: whether a model *chooses* to escalate, and whether it
remembers to scope. That is a policy question about the agent, not a capability
question about the tool, and it needs a live benchmark with the extension loaded.
This harness answers "is the path there, is it signposted, and is it cheap" —
which is a precondition for that, not a substitute.

Run:  python tools/bench_detail.py [--obs 30]
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from _extract import extract  # noqa: E402

OUT = ROOT / "temp" / "dom_quality"

# needs="href"/"src" -> the answer requires detail="full".
# needs=None        -> a control task: answerable from the compact listing alone,
#                      so design B pays the premium for nothing.
TASKS = [
    dict(name="hn: URL behind a story",     url="https://news.ycombinator.com/",
         sel=".titleline a", needs="href"),
    dict(name="hn: click the comments link", url="https://news.ycombinator.com/",
         sel=".subline a[href^='item']", needs=None),
    dict(name="wikipedia: source of a photo", url="https://en.wikipedia.org/wiki/Main_Page",
         sel="#mp-tfa img, #mp-itn img, .mw-body-content img", needs="src"),
    dict(name="wikipedia: open a article link", url="https://en.wikipedia.org/wiki/Main_Page",
         sel="#mp-tfa a, #mp-itn a, .mw-body-content a", needs=None),
    dict(name="mdn: URL of a doc link",     url="https://developer.mozilla.org/en-US/docs/Web/HTML/Element/select",
         sel="main a[href*='/docs/'], article a[href*='/docs/']", needs="href"),
    dict(name="saucedemo: log in",          url="https://www.saucedemo.com/",
         sel="#login-button", needs=None),
    dict(name="bootstrap: fill an input",   url="https://getbootstrap.com/docs/5.3/forms/overview/",
         sel="input[type='email'], input[type='text']", needs=None),
]

PROBE = r"""
(function (sel) {
  // The collector injects mmids, so it has to run before anything can be found.
  const compact = _collectInteractivePage(false, null, 'compact');
  // Take the first VISIBLE match. An agent acts on what it can see, and a
  // selector will happily hand back a link inside a collapsed <details> — which
  // the collector correctly refuses to list (closed-details ghosts are excluded
  // via checkVisibility). Scoring that as a miss blames the collector for
  // obeying its own rule.
  const el = [...document.querySelectorAll(sel)].find(
      n => (n.checkVisibility ? n.checkVisibility({ checkVisibilityCSS: true }) : true)
           && n.getBoundingClientRect().width > 1);
  if (!el) return { found: false };
  const mmid = el.getAttribute('mmid');
  // Would the agent be able to LOCATE this from the compact listing? Either the
  // element is listed itself, or an ancestor it can scope to is.
  let locatable = compact.indexOf('mmid=' + mmid + ' ') !== -1;
  let anchor = mmid, n = el;
  while (!locatable && n && n.parentElement) {
    n = n.parentElement;
    const am = n.getAttribute && n.getAttribute('mmid');
    if (am && compact.indexOf('mmid=' + am + ' ') !== -1) { locatable = true; anchor = am; }
  }
  // A below-fold control is deliberately absent from the STRING listing (which is
  // viewport-scoped for token discipline) while remaining reachable through
  // `find`, which reads the structured set. Scoring those as "not locatable"
  // measures the wrong thing — the listing says "N elements are BELOW the
  // current viewport" and find() resolves them.
  const viaFind = _collectInteractivePage(true, null, 'compact').some(e => e.mmid === mmid);
  const scoped = _collectInteractivePage(false, anchor, 'full');
  const fullPage = _collectInteractivePage(false, null, 'full');
  return {
    found: true, mmid, anchor, locatable, viaFind,
    compact: compact.length, scoped: scoped.length, fullPage: fullPage.length,
    hasHatch: /^  - .*are NOT listed\./m.test(compact),
    scopedHasHref: /\shref="/.test(scoped),
    scopedHasSrc: /\ssrc="/.test(scoped),
  };
})
"""


async def one(ctx, task, fn):
    page = await ctx.new_page()
    rec = dict(task)
    try:
        # One retry: these are live sites and a single timeout should not silently
        # shrink the task set and move the headline ratio.
        for attempt in (1, 2):
            try:
                await page.goto(task["url"], wait_until="domcontentloaded", timeout=30000)
                break
            except Exception:
                if attempt == 2:
                    raise
                await page.wait_for_timeout(2000)
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        await page.wait_for_timeout(2200)
        rec.update(await page.evaluate(fn, task["sel"]))
    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {str(e).splitlines()[0][:60]}"
    finally:
        try:
            await page.close()
        except Exception:
            pass
    return rec


async def main(obs):
    src = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
    fn = "(function(){ " + extract("_collectInteractivePage", src, verify=True) + "\n; return " + PROBE.strip() + "; })()"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1366, "height": 900})
        await ctx.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        rows = await asyncio.gather(*[one(ctx, t, fn) for t in TASKS])
        await browser.close()

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "bench_detail.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")

    print(f"{'task':<34}{'locatable':>10}{'answered':>10}{'A (2-step)':>12}{'B (always)':>12}")
    print("-" * 78)
    a_tot = b_tot = 0
    ok_rows = []
    for r in rows:
        if r.get("error") or not r.get("found"):
            print(f"{r['name']:<34}   SKIP  {r.get('error', 'target not on page')[:30]}")
            continue
        ok_rows.append(r)
        needs = r["needs"]
        answered = (r["scopedHasHref"] if needs == "href"
                    else r["scopedHasSrc"] if needs == "src" else None)
        # A: obs compact reads, plus ONE scoped full read if the task needs a URL.
        a = obs * r["compact"] + (r["scoped"] if needs else 0)
        # B: every observation is a whole-page full read.
        b = obs * r["fullPage"]
        a_tot += a
        b_tot += b
        loc = 'yes' if r['locatable'] else ('find' if r.get('viaFind') else 'NO')
        print(f"{r['name']:<34}{loc:>10}"
              f"{('yes' if answered else '-' if answered is None else 'NO'):>10}"
              f"{a:>12,}{b:>12,}")

    if not ok_rows:
        print("\nno tasks completed")
        return
    print("-" * 78)
    print(f"{'TOTAL chars over ' + str(obs) + ' observations/task':<54}{a_tot:>12,}{b_tot:>12,}")
    print(f"\n  design B costs {b_tot / max(a_tot, 1):.2f}x design A "
          f"(~{(b_tot - a_tot) // 4:,} extra tokens across {len(ok_rows)} tasks)")
    bad = [r for r in ok_rows if not r["locatable"] and not r.get("viaFind")]
    viafind = [r for r in ok_rows if not r["locatable"] and r.get("viaFind")]
    print(f"  targets reachable: {len(ok_rows) - len(bad)}/{len(ok_rows)}"
          + (f"  ({len(viafind)} below the fold, reachable via find(): {[r['name'] for r in viafind]})" if viafind else "")
          + (f"  UNREACHABLE: {[r['name'] for r in bad]}" if bad else ""))
    need = [r for r in ok_rows if r["needs"]]
    got = [r for r in need if (r["scopedHasHref"] if r["needs"] == "href" else r["scopedHasSrc"])]
    print(f"  URL/media questions answered by the scoped read: {len(got)}/{len(need)}")
    nohatch = [r for r in ok_rows if not r["hasHatch"]]
    print(f"  compact read signposted the escape hatch: {len(ok_rows) - len(nohatch)}/{len(ok_rows)}"
          + (f"  (suppressed on {[r['name'] for r in nohatch]} — verify those pages have no links/media)" if nohatch else ""))
    print("\n  NOTE: this prices the PATH. Whether the agent chooses to escalate, and")
    print("  scopes it when it does, is a policy question needing a live agent run.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--obs", type=int, default=30, help="observations per task (default 30)")
    a = ap.parse_args()
    asyncio.run(main(a.obs))
