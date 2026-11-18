# -*- coding: utf-8 -*-
"""Re-derive each scenario's answer by DRIVING it, not by fetching a result URL.

WHY THIS IS NOT OPTIONAL HERE. The task author verified every answer with curl
against the calculators' own result URLs. That checks the arithmetic and leaves
the thing this eval is about -- the multi-step interaction -- entirely
unchecked, and it means the scenario might be solvable by CONSTRUCTING that URL
rather than driving the form, which is the shortcut eval 9 had to exclude a
whole pair for (its Amendment 5).

So this referee starts at the scenario's own `start` URL, drives the form, and
only then looks for the answer. A scenario it cannot reach that way is DROPPED
rather than adjudicated -- eval 3 dropped two on the same rule, and an ambiguous
scenario is worse than no scenario.

It is deliberately NOT the thing under test: plain Playwright, no ChromeBridge,
no extension, no model.

Run:  python tools/bench_turns/eval10/referee.py
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent


def _norm(s: str) -> str:
    s = (s or "").replace(" ", " ")
    s = re.sub(r"[‐-―−]", "-", s)
    return re.sub(r"\s+", " ", s).strip().casefold()


async def drive(page, t) -> tuple[bool, str]:
    """Each scenario's interaction path, written from its prompt alone."""
    tid = t["id"]
    await page.goto(t["start"], wait_until="domcontentloaded", timeout=40000)
    await page.wait_for_timeout(1500)

    if tid in ("S4", "S5"):
        seq = re.search(r"begins ([\d,\s]+)\.", t["prompt"])
        if not seq:
            return False, "could not read the sequence out of the prompt"
        q = seq.group(1).strip().rstrip(".")
        box = page.locator("input[name='q']").first
        await box.fill(q)
        await box.press("Enter")
        await page.wait_for_timeout(2500)
        txt = await page.evaluate("document.body.innerText")
        return (_norm(t["answer"]) in _norm(txt)), "search results"

    if tid == "S3":
        # The sun page: search the city, then set month and year.
        box = page.locator("input[type='search'], input[name='query'], input#query").first
        try:
            await box.fill("Reykjavik")
            await box.press("Enter")
            await page.wait_for_timeout(2500)
        except Exception as e:                                    # noqa: BLE001
            return False, f"city search unreachable: {str(e)[:60]}"
        txt = await page.evaluate("document.body.innerText")
        return (_norm(t["answer"]) in _norm(txt)), "after city search (month/year not yet set)"

    # S1/S2: reach the calculator from the HOME page, which is the step the
    # author's curl could not check.
    link = page.locator("a[href*='/date/']").first
    try:
        await link.click()
        await page.wait_for_timeout(2000)
    except Exception as e:                                        # noqa: BLE001
        return False, f"no date-calculator link reachable from home: {str(e)[:60]}"
    txt = await page.evaluate("document.body.innerText")
    return False, f"reached {page.url} — form not driven, answer not confirmed"


async def main() -> int:
    tasks = json.loads((HERE / "tasks.json").read_text(encoding="utf-8"))
    from playwright.async_api import async_playwright

    out = []
    async with async_playwright() as p:
        br = await p.chromium.launch(headless=True)
        ctx = await br.new_context(viewport={"width": 1280, "height": 900},
                                   locale="en-US")
        for t in tasks:
            page = await ctx.new_page()
            try:
                ok, why = await drive(page, t)
            except Exception as e:                                # noqa: BLE001
                ok, why = False, f"threw: {str(e)[:80]}"
            await page.close()
            out.append({"id": t["id"], "answer": t["answer"],
                        "confirmed": ok, "why": why})
            print(f"  {t['id']}  {'CONFIRMED' if ok else 'NOT CONFIRMED'}  {why}")
        await br.close()

    (HERE / "ground_truth.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    good = [r for r in out if r["confirmed"]]
    print(f"\n{len(good)}/{len(out)} scenario(s) confirmed by DRIVING them.")
    print("A scenario this could not reach is DROPPED, not adjudicated.")
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
