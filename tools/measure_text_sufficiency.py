"""Does the TEXT surface carry what a task needs? The other half of #OPEN 12.

`measure_sufficiency.py` prices the listing of CONTROLS: given the target is on
the page, can the listing distinguish it (DS | reachable = 0.933). It says
NOTHING about prose, tables or page data, which reach an agent through
`get_page_text`, `search_page` and `query_elements` -- and the source paper's
single largest finding is that TEXT dominates the minimal failure set. Eval 4
then found a silent column misalignment in exactly that half that no presence
or sufficiency number would have caught.

THE LABELS. Eval 4 is 20 tasks written by an author told only to write varied
two-hop browser tasks, with no knowledge that any toolset was under test, and
each answer re-derived by an independent referee driving headless Chromium.
`ground_truth.json`'s `require_all` is therefore a blind (page, required value)
label set -- the thing a prose-sufficiency metric needs and the frozen corpus
does not have.

THE PAGES are harvested MECHANICALLY from both arms' transcripts (every url
either agent navigated to), never transcribed. Amendment 6 of that eval exists
because a hand-copied value broke the ruler once already.

WHAT THIS CANNOT ANSWER, stated before the number:
  * It is an UPPER bound on the tool and a LOWER bound on the task. A value
    present in the text does not mean an agent finds it; a value absent from
    one page may be on another the agent would have reached.
  * These are LIVE pages, not HARs. A site that changed since the eval reads as
    a miss that is really drift. Re-running is the only control, and the script
    prints per-page so a drifted site is visible rather than averaged in.
  * It prices `get_page_text` ONLY. `search_page` and `query_elements` can
    reach things this misses; that is a separate arm and is not run here.

  python tools/measure_text_sufficiency.py [--n 20]

=============================================================================
RESULT: THIS DESIGN CANNOT MEASURE WHAT IT WAS BUILT FOR. Kept, with the
reason, because the next person will have the same idea.

Run on 4 tasks it reported 2/5 values carried, and BOTH misses are artefacts
of the design rather than failures of the text surface:
  * T3 needs "Please select the Paymeny Method." -- a validation message that
    does not exist until the form is submitted.
  * T4 needs "29.0 km" -- a cell in a result set that does not exist until the
    search is run.

The confound is total and checkable in one line: `tasks.md` records
`Interactions needed` per task, and **0 of 22 tasks need zero**. Seven need
one, nine need two, six need three or more. They were written that way on
purpose -- a two-hop task is what makes a good turn-count eval -- and that is
exactly what makes the label set useless here. A static load of the urls an
agent visited cannot contain a value the agent produced BY INTERACTING, so
this probe measures how many eval tasks are two-hop, which is 100%, and tells
you nothing about `get_page_text`.

Reporting the 0.400 as a sufficiency number would have been the flattering
version of a broken ruler (#16, #48), and the misses would have looked like
tool failures.

WHAT WOULD ACTUALLY MEASURE IT, and the answer is pleasingly close to home:
separating "the text surface failed to carry it" from "the value did not exist
yet" requires REPLAYING the interaction and then reading the text. That is
precisely what a recorded flow does. So the path runs through `run_flow`:
record each eval task once, replay to the step before the answer, and ask the
text surface there. The labels already exist (`ground_truth.json`, blind
author, independent referee); what is missing is 20 recordings and a harness
that stops a replay at step N.

Until then the prose/table half of OPEN item 12 stays OPEN, and the control
half's 0.933 must not be quoted as if it covered it.
=============================================================================
"""
import argparse, asyncio, json, re, sys
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
E4 = ROOT / "tools" / "bench_turns" / "eval4"
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(E4))
from _extract import extract as _extract_fn            # noqa: E402
from score import score, D as SUBDIR                   # noqa: E402

BG = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
TEXT_FN = _extract_fn("_domTextPage", BG, verify=True)
VIEWPORT = {"width": 1280, "height": 1600}


def urls_for(task):
    """Every url either arm navigated to, from the TRANSCRIPTS."""
    out = []
    for line in (E4 / "runs.tsv").read_text().strip().splitlines()[1:]:
        _o, t, _arm, aid = line.split("\t")
        if t != task:
            continue
        f = Path(SUBDIR) / f"agent-{aid}.jsonl"
        if not f.exists():
            continue
        for ln in f.open(encoding="utf-8", errors="replace"):
            for m in re.finditer(r'"url"\s*:\s*"(https?://[^"]{4,300})"', ln):
                u = m.group(1)
                if u not in out:
                    out.append(u)
    return out


async def text_of(browser, url):
    ctx = await browser.new_context(viewport=VIEWPORT)
    try:
        page = await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        try:
            await page.wait_for_load_state("networkidle", timeout=6000)
        except Exception:
            pass
        await page.wait_for_timeout(900)
        r = await page.evaluate("(function(){ " + TEXT_FN
                                + "; return _domTextPage(null,null); })()")
        if isinstance(r, dict):
            r = r.get("text") or json.dumps(r, ensure_ascii=False)
        return str(r or "")
    except Exception as e:
        return f"__ERROR__ {e}"
    finally:
        await ctx.close()


def norm(s):
    return re.sub(r"\s+", " ", str(s)).replace("−", "-").lower()


async def main(n):
    gt = json.load(open(E4 / "ground_truth.json"))["gt"]
    rows, carried, total = [], 0, 0
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        for task in sorted(gt, key=lambda x: int(x[1:]))[:n]:
            need = gt[task].get("require_all") or []
            if not need:
                continue
            urls = urls_for(task)[:6]
            blob = ""
            errs = 0
            for u in urls:
                t = await text_of(b, u)
                if t.startswith("__ERROR__"):
                    errs += 1
                    continue
                blob += "\n" + t
            nb = norm(blob)
            hit = [v for v in need if norm(v) in nb]
            total += len(need)
            carried += len(hit)
            rows.append((task, len(hit), len(need), len(urls), errs,
                         [v for v in need if norm(v) not in nb]))
            print(f"  {task:<5} {len(hit)}/{len(need)} values carried  "
                  f"({len(urls)} page(s), {errs} unreachable)"
                  + (f"  MISSING={rows[-1][5]}" if rows[-1][5] else ""))
        await b.close()

    full = sum(1 for r in rows if r[1] == r[2])
    print(f"\ntasks fully carried: {full}/{len(rows)}")
    print(f"values carried: {carried}/{total} = {carried/total:.3f}" if total else "")
    print("\nNOT A SUCCESS RATE. This is an UPPER bound on get_page_text and a")
    print("LOWER bound on the task: a value present does not mean an agent finds")
    print("it, and a value absent here may be reachable by search_page or")
    print("query_elements, which are a separate arm and were not run.")
    print("Pages are LIVE, not frozen -- a site that changed since the eval reads")
    print("as a miss. Per-task lines above are printed so drift is visible rather")
    print("than averaged in.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    asyncio.run(main(ap.parse_args().n))
