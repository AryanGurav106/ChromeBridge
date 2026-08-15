"""Unit suite for _detectSubmitPage — the submit picker, which had NO test.

WHY THIS EXISTS
---------------
`fill_form(submit=True)` decides which button to press by running this function.
It is the one place where the tool takes an irreversible action on the user's
behalf, and it was the largest untested function in the project: a wrong pick
does not fail loudly, it presses the wrong button.

The audit that produced this file found the picker's two wordlists were both
broken in the same way, and broken INVISIBLY:

  A trailing `\\b` is an ASCII-only boundary. JS `\\w` is [A-Za-z0-9_], so `\\b`
  after a CJK or Hangul alternative demands a boundary that can never exist:

      /^(cancel|…|削除|キャンセル|삭제)\\b/i.test('削除')   ===   false

  Every non-Latin word in the destructive list was dead code. The list's own
  comment claimed multilingual coverage, and the German entries passed only
  because they happen to end in ASCII letters. This is the same failure mode the
  ablation study found in the `/[a-z0-9]/i` gates — a signature that reads as
  generality and measures as English-only — reintroduced in a different shape.

  The submit list had no non-English words at all, so on any non-English form
  without an explicit type="submit" the keyword tier was a guaranteed no-op.

WHAT IT DOES NOW — and why there is no wordlist left
Fixing the lists made them longer, not sound: any wordlist is a guess about
languages nobody enumerated, and a wrong guess here clicks "Delete account".
So the picker consults NO words. It answers only when the document declares
which button submits the form (type="submit", or HTML's implicit submit inside
a real <form>), and refuses — naming the candidates — when zero or several do.
The agent has the listing and the task; it picks with submit_ref.

The cost, stated plainly: a div-form with no declared submit no longer
auto-submits at all, and a page that marks a destructive button as its own
type="submit" will be honoured. The first is a refusal the agent can act on;
the second is what the page says, and no structural signal contradicts it.

Run:  python tools/test_submit.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _extract import extract  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BG = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
DETECT = extract("_detectSubmitPage", BG, verify=True)

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  - {detail}" if detail else ""))


def scope(*buttons, host="form"):
    """A field plus buttons inside `host`.

    host="form"          real <form>  -> tiers 1 and 1b are live
    host="div role=form" div-form     -> tier 1b cannot fire (it requires a
                                          <form> ancestor), so the keyword tier
                                          is the ONLY thing that can answer.
    """
    return (f"<!DOCTYPE html><meta charset=utf-8><body><{host} id=host>"
            f"<input id=f name=q>{''.join(buttons)}</{host.split()[0]}></body>")


async def pick(page, html):
    """Return the label _detectSubmitPage chooses, or None."""
    await page.set_content(html)
    await page.wait_for_timeout(30)
    return await page.evaluate(
        "(function(){ " + DETECT + ";\n"
        "  const r = _detectSubmitPage('#f');\n"
        "  return r ? r.label : null; })()")


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1100, "height": 800})
        DIV = "div role=form"

        # --- the only two things that count as evidence ------------------------
        got = await pick(page, scope("<button type=button>Speichern</button>",
                                     "<button type=submit>Weiter</button>"))
        check("S1 an explicit type=submit is the answer",
              got == "Weiter", f"picked {got!r}")

        got = await pick(page, scope("<button>Weiter</button>"))
        check("S2 a typeless <button> in a real <form> is HTML's implicit submit",
              got == "Weiter", f"picked {got!r}")

        # --- and language is now structurally irrelevant -----------------------
        # The point of deleting the wordlists: these used to depend on whether
        # someone had put the word in a list. Now they cannot, because no word is
        # consulted at all. S3 covers scripts the old list did and did not have.
        for name, label in [("S3a Japanese", "送信"), ("S3b Korean", "저장"),
                            ("S3c Russian", "Сохранить"), ("S3d Sinhala", "යොමු කරන්න"),
                            ("S3e Amharic", "አስገባ")]:
            got = await pick(page, scope(f"<button type=submit>{label}</button>"))
            check(f"{name}: the declared submit is used whatever language it is in",
                  got == label, f"picked {got!r}")

        # --- refusals: the tool must decline rather than guess -----------------
        got = await pick(page, scope("<button type=button>Speichern</button>",
                                     "<button type=button>Abbrechen</button>", host=DIV))
        check("S4 a div-form with NO declared submit is refused, not guessed",
              got is None, f"picked {got!r}")

        got = await pick(page, scope("<button type=button>අවලංගු කරන්න</button>", host=DIV))
        check("S5 ...including a SOLE button — one button is not evidence of intent",
              got is None, f"picked {got!r}")

        # Two declared submits is the case that used to be decided by a wordlist:
        # "Save changes" vs "Delete account", resolved by geometry plus a word list.
        # Now it is a refusal that NAMES both, so the agent chooses with submit_ref.
        await page.set_content(scope("<button type=submit>Save changes</button>",
                                     "<button type=submit>Delete account</button>"))
        await page.wait_for_timeout(30)
        amb = await page.evaluate(
            "(function(){ " + DETECT + ";\n"
            "  const r = _detectSubmitPage('#f');\n"
            "  return r ? {mmid: r.mmid || null, ambiguous: r.ambiguous || null,"
            "             hidden: r.hidden || 0} : null; })()")
        check("S6 two declared submits are REFUSED rather than chosen between",
              amb is not None and not amb.get("mmid"),
              f"got {amb!r}")
        _labels = sorted((x.get("label") or "") for x in (amb.get("ambiguous") or []))
        check("S7 ...and the refusal names both, so the agent can pick one",
              _labels == ["Delete account", "Save changes"],
              f"options={(amb or {}).get('ambiguous')!r}")
        # A LABEL IS NOT ENOUGH TO ACT ON. GitHub's advanced search has two submits
        # labelled byte-identically; "pass submit_ref for the one you mean" between
        # two copies of "Search" is circular. Every candidate carries its ref.
        # Each candidate must expose a `mmid` FIELD — identical labels made the old
        # label-only message circular ("pass submit_ref for the one you mean" between
        # two copies of "Search"). In a bare fixture the collector has not run, so the
        # value is null; what matters is that the shape carries the ref.
        check("S7b ...and each candidate carries a ref field, not just a label",
              all("mmid" in x for x in (amb.get("ambiguous") or [])),
              f"{amb.get('ambiguous')!r}")

        # --- no word can change the outcome any more ---------------------------
        # The old suite needed rows for 'Address'/'Deleted items'/'Undelete' because
        # a substring could flip the verdict. Nothing here reads the label, so one
        # check that the label is inert is the whole story.
        outcomes = []
        for label in ["Save", "Address book", "Deleted items", "Undelete",
                      "Delete account", "削除", "Абракадабра"]:
            outcomes.append(await pick(page, scope(f"<button type=submit>{label}</button>")))
        check("S8 the label never changes WHETHER a declared submit is used",
              outcomes == ["Save", "Address book", "Deleted items", "Undelete",
                           "Delete account", "削除", "Абракадабра"],
              f"got {outcomes!r}")

        # --- and the source carries no wordlist to drift back in ---------------
        check("S9 the picker's source contains no natural-language wordlist",
              not any(w in DETECT.lower() for w in
                      ("cancel|", "submit|save", "speichern", "abbrechen", "annuler",
                       "削除", "삭제", "удалить")),
              "a wordlist reappeared in _detectSubmitPage")

        # S10: HTML lets a button submit a form it is not inside (`form="id"`) —
        # the standard modal-footer pattern. Querying only within the scope refused
        # a form whose document plainly declares its submit.
        await page.set_content(
            "<!DOCTYPE html><meta charset=utf-8><body>"
            "<form id=theform><input id=f name=q></form>"
            "<div class=modal-footer><button type=submit form=theform>Save</button></div>"
            "</body>")
        await page.wait_for_timeout(30)
        got = await page.evaluate(
            "(function(){ " + DETECT + ";\n"
            "  const r = _detectSubmitPage('#f');\n"
            "  return r ? r.label : null; })()")
        check("S10 a button associated by form=\"id\" from OUTSIDE the form counts",
              got == "Save", f"picked {got!r}")

        # S11: two submits that produce an IDENTICAL submission (same label, no
        # name/value/formaction divergence) are interchangeable per HTML — GitHub's
        # advanced search. Refusing there asked the agent to choose between two
        # copies of the same string. Structural equivalence, not a semantic guess.
        got = await pick(page, scope("<button type=submit>Search</button>",
                                     "<button type=submit>Search</button>"))
        check("S11 structurally interchangeable submits are collapsed, not refused",
              got == "Search", f"picked {got!r}")

        # ...but a divergence that CHANGES the submission must still refuse.
        await page.set_content(scope("<button type=submit>Search</button>",
                                     "<button type=submit formaction='/elsewhere'>Search</button>"))
        await page.wait_for_timeout(30)
        _r = await page.evaluate(
            "(function(){ " + DETECT + ";\n"
            "  const r = _detectSubmitPage('#f');\n"
            "  return r ? {mmid: r.mmid || null, n: (r.ambiguous || []).length} : null; })()")
        check("S11b ...while a differing formaction still refuses (different submission)",
              bool(_r) and not _r.get("mmid") and _r.get("n") == 2, f"got {_r!r}")

        # S12: a declared-but-hidden submit (Google's 0x0 btnK) must not be clicked,
        # and must not be reported as "nothing declares itself the submit" either.
        await page.set_content(scope(
            "<button type=submit style='display:none'>Google Search</button>"))
        await page.wait_for_timeout(30)
        _h = await page.evaluate(
            "(function(){ " + DETECT + ";\n"
            "  const r = _detectSubmitPage('#f');\n"
            "  return r ? {mmid: r.mmid || null, hidden: r.hidden || 0} : null; })()")
        check("S12 a HIDDEN declared submit is not clicked, but IS counted",
              bool(_h) and not _h.get("mmid") and _h.get("hidden") == 1, f"got {_h!r}")

        await browser.close()

    passed = sum(1 for r in results if r)
    print(f"\n{passed}/{len(results)} submit-picker checks passed.")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
