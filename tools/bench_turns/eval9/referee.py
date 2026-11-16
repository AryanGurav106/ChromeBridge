# -*- coding: utf-8 -*-
"""Re-derive ground truth INDEPENDENTLY of the task author, with a deterministic
headless browser and no model anywhere in the path.

The author verified its own answers, which is exactly the circularity this
removes: #16's rule is that a result which flatters the design gets re-derived
before it is believed, and a task author confirming its own key is that shape.
Where this disagrees with the author, the task is DROPPED rather than
adjudicated — an ambiguous task is worse than no task (eval 3 dropped two on
the same rule).
"""
import asyncio, json, pathlib, re, sys
from playwright.async_api import async_playwright

HERE = pathlib.Path(__file__).resolve().parent


def _norm(s):
    # Compare on what a reader sees: collapse whitespace, fold case, and treat
    # the dash family as one character. NOT a fuzzy match -- the answer must
    # still appear verbatim modulo those three.
    s = (s or "").replace(" ", " ")
    s = re.sub(r"[‐-―−]", "-", s)
    # MULTIPLICATION SIGN -> x, and the narrow spaces scientific sites use.
    # NIST writes 1.674 x 10^-27 with U+00D7 and U+2009/U+202F, so a key typed
    # in ASCII fails against a page that is correct. The task AUTHOR flagged
    # this BEFORE the referee ran, which is what makes adding it fixing the
    # instrument rather than tuning it: a normalisation added after seeing
    # which task it rescues is how a referee stops being independent.
    s = s.replace("\u00d7", "x").replace("\u2009", " ").replace("\u202f", " ")
    return re.sub(r"\s+", " ", s).strip().casefold()


async def main():
    tasks = json.loads((HERE / "tasks.json").read_text(encoding="utf-8"))
    rows = []
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        ctx = await b.new_context(viewport={"width": 1280, "height": 900},
                                  locale="en-US")
        for t in tasks:
            url = t.get("verified_from") or t["start"]
            ok, why = False, ""
            try:
                pg = await ctx.new_page()
                await pg.goto(url, wait_until="domcontentloaded", timeout=45000)
                await pg.wait_for_timeout(2500)
                txt = _norm(await pg.evaluate(
                    "document.body ? document.body.innerText : ''"))
                # CHECK `onpage`, NOT `answer`. A task may legitimately ask for
                # a NORMALISED form -- "report the date as YYYY-MM-DD" -- and
                # then the answer is a reformatting that by construction does
                # not appear verbatim. My first referee tested `answer` and
                # dropped three tasks for that reason, which is a flaw in the
                # instrument, not in the tasks: debian.org renders "July 6th,
                # 2019" and the key said 2019-07-06. So the author now supplies
                # BOTH -- `onpage` exactly as rendered, `answer` as the thing to
                # report -- and the referee confirms the half it can.
                need = t.get("onpage") or t["answer"]
                ok = _norm(need) in txt
                why = "found on the page" if ok else "NOT present in rendered text"
                await pg.close()
            except Exception as e:                                   # noqa: BLE001
                why = f"could not load: {type(e).__name__}: {str(e)[:90]}"
            rows.append({"id": t["id"], "answer": t["answer"],
                         "onpage": t.get("onpage") or t["answer"], "url": url,
                         "confirmed": ok, "why": why})
            print(f"  {t['id']:<4} {'CONFIRM' if ok else 'DROP   '}  "
                  f"{(t.get('onpage') or t['answer'])[:34]!r:<38} {why}")
        await b.close()
    (HERE / "ground_truth.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    n = sum(1 for r in rows if r["confirmed"])
    print(f"\n{n}/{len(rows)} task(s) confirmed independently; "
          f"{len(rows) - n} dropped")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
