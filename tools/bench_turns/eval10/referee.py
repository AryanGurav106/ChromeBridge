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
    """Each scenario's interaction path, written from its prompt alone.

    REWRITTEN WHEN THE TASK SET WAS REPLACED, and that is the point: the first
    version still encoded the previous scenarios' sites, so it kept "confirming"
    two and failing three while measuring nothing about the new ones. A ruler
    that does not match the question answers a different one confidently.
    """
    tid = t["id"]
    await page.goto(t["start"], wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_timeout(1500)

    if tid in ("S4", "S5"):
        seq = re.search(r"begins ([\d,\s]+)\.", t["prompt"])
        if not seq:
            return False, "could not read the sequence out of the prompt"
        box = page.locator("input[name='q']").first
        await box.fill(seq.group(1).strip().rstrip("."))
        await box.press("Enter")
        await page.wait_for_timeout(2500)
        txt = await page.evaluate("document.body.innerText")
        return (_norm(t["answer"]) in _norm(txt)), "search -> results"

    if tid == "S1":
        # examples index -> Basic Initialisation -> Zero configuration -> ...
        # The intermediate section click is in the PROMPT and my first driver
        # skipped it, which read as the task being unreachable rather than as my
        # driver being wrong.
        try:
            await page.get_by_role("link", name=re.compile("Basic initialisation", re.I)).first.click(timeout=8000)
            await page.wait_for_timeout(1500)
        except Exception:
            pass
        await page.get_by_role("link", name=re.compile("Zero configuration", re.I)).first.click(timeout=15000)
        await page.wait_for_timeout(2500)
        try:
            await page.locator("select[name$='_length'], select.dt-input").first.select_option("25")
        except Exception:
            pass
        await page.wait_for_timeout(600)
        await page.locator("input[type='search'], .dt-search input").first.fill("Software Engineer")
        await page.wait_for_timeout(1500)
        txt = await page.evaluate("document.body.innerText")
        return (_norm(t["answer"]) in _norm(txt)), "filtered table"

    if tid == "S2":
        await page.get_by_role("link", name=re.compile(r"^\s*Mystery", re.I)).first.click()
        await page.wait_for_timeout(1800)
        try:
            await page.get_by_role("link", name=re.compile("next", re.I)).first.click()
            await page.wait_for_timeout(1800)
        except Exception:
            return False, "no page 2 in Mystery"
        # open the book the prompt names, then read its UPC from the table
        try:
            await page.get_by_role("link", name=re.compile("Silkworm", re.I)).first.click()
            await page.wait_for_timeout(1800)
        except Exception:
            return False, "target book not on page 2"
        txt = await page.evaluate("document.body.innerText")
        return (_norm(t["answer"]) in _norm(txt)), "book detail page"

    if tid == "S3":
        # home -> Sandbox -> Oscar Winning Films. Same omission as S1.
        try:
            await page.get_by_role("link", name=re.compile("Sandbox", re.I)).first.click(timeout=8000)
            await page.wait_for_timeout(1500)
        except Exception:
            pass
        await page.get_by_role("link", name=re.compile("Oscar", re.I)).first.click(timeout=15000)
        await page.wait_for_timeout(2000)
        for yr in ("2010", "2013"):
            try:
                await page.get_by_role("link", name=re.compile(rf"^\s*{yr}\s*$")).first.click()
                await page.wait_for_timeout(2500)   # the table arrives by AJAX
            except Exception:
                return False, f"year link {yr} unreachable"
        txt = await page.evaluate("document.body.innerText")
        return (_norm(t["answer"]) in _norm(txt)), "2013 table loaded"

    return False, "no driver written for this id"


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
