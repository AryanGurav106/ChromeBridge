"""Every hardcoded NUMBER the collector compares against, enumerated mechanically.

WHY THIS EXISTS
---------------
#28's lesson was that reading the code to find its own weak spots does not work:
a hand-written audit named three container rules that could delete an element and
missed three more, and two separate static reviews missed the same three. What
found them was `grep -o` over the call sites.

"No chosen number gates whether an element EXISTS" is now true. But plenty of
chosen numbers still decide PROMINENCE — which is allowed, and is exactly the
category that drifts silently, because a threshold tuned on one corpus is invisible
to the next. `tools/audit_patterns.py` does this for regexes and wordlists; this
does it for magic numbers, so both families have a mechanical inventory instead of
a paragraph someone wrote from memory.

It cannot decide correctness. `0.25 * vw * vh` for "is this canvas the app" is a
judgement; `=== 3` for `Node.TEXT_NODE` is the DOM spec; `1e3` in a timeout is a
duration. So the output is a review queue, classified by the SUBJECT of the
comparison, and the summary states how many are viewport fractions and pixel
counts — the two kinds that encode an assumption about a page nobody has seen.

Run:  python tools/audit_thresholds_static.py
      python tools/audit_thresholds_static.py --kind viewport-fraction
      python tools/audit_thresholds_static.py --full
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _extract import code_mask  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TARGET = "extension/background.js"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# A numeric literal on either side of a comparison, or one used as a scale factor
# against a viewport dimension. Deliberately narrow: a bare number in an argument
# list is not a threshold, it is a parameter.
CMP = re.compile(
    r"(?:[<>]=?|===?|!==?)\s*(-?\d+(?:\.\d+)?(?:e-?\d+)?)"
    r"|(-?\d+(?:\.\d+)?(?:e-?\d+)?)\s*(?:[<>]=?|===?|!==?)"
    r"|(-?\d*\.?\d+)\s*\*\s*(?:vw|vh|pvw|pvh)")

# Comparisons whose SUBJECT is fixed by a spec or by the platform, not chosen.
SPEC_SUBJECT = re.compile(
    r"nodeType|\.length\s*[<>=!]|keyCode|which\b|button\b|clickCount|"
    r"status\b|readyState|PROTOCOL_VERSION|charCodeAt|codePointAt|"
    r"indexOf|lastIndexOf|\.size\s*[<>=!]|depth|d\s*>\s*\d|"
    r"searchParams|slice|substr|split", re.I)
VIEWPORT = re.compile(r"\bv?[wh]\b|\bpv[wh]\b|innerWidth|innerHeight|clientWidth|clientHeight")
PIXELS = re.compile(
    r"getBoundingClientRect|\brect\b|\br\.(?:width|height|top|left|bottom|right)|"
    r"\.width\b|\.height\b|offset(?:Width|Height|Top|Left)|scroll(?:Top|Height|Width)|"
    # ENTRY-FIELD geometry. The collector's own entries carry x/y/w/h, so
    # `Math.abs(h.w - e.w) <= 8` is a pixel comparison with none of the words
    # above in it — and the self-test caught this classifying
    # same-box-wrapper-collapse as "other", which would have let a pixel
    # threshold gating existence pass unreported.
    r"\b[A-Za-z_$][\w$]*\.(?:x|y|w|h)\b|Math\.abs", re.I)
# `ts\b` (no leading boundary) matched inside `removedHosts`, so
# shadow-host-collapse was classified as a DURATION and skipped entirely. A
# substring match on an identifier is the same defect this whole audit family
# exists to find, in the auditor itself.
TIME = re.compile(
    r"setTimeout|setInterval|Date\.now|\bts\b|elapsed|timeout|\bms\b|sleep|poll", re.I)
COUNT = re.compile(r"count|\bn\b|\blen\b|members|entries|rows|cells|kids|children", re.I)


def kind_of(line: str) -> str:
    if TIME.search(line):
        return "duration"
    if VIEWPORT.search(line) and re.search(r"\*\s*(?:vw|vh|pvw|pvh)|(?:vw|vh|pvw|pvh)\s*\*", line):
        return "viewport-fraction"
    if PIXELS.search(line):
        return "pixel-count"
    if SPEC_SUBJECT.search(line):
        return "spec-or-index"
    if COUNT.search(line):
        return "element-count"
    return "other"


RISK = {
    "viewport-fraction": "HIGH   encodes an assumption about page layout",
    "pixel-count":       "HIGH   a page nobody has seen may render at any size",
    "element-count":     "MED    tuned on one corpus; drifts silently",
    "duration":          "LOW    a wait, not a judgement about the page",
    "spec-or-index":     "-      fixed by a spec or by the platform",
    "other":             "-      review",
}


def scan() -> list[dict]:
    src = (ROOT / TARGET).read_text(encoding="utf-8")
    mask = code_mask(src)
    lines = src.split("\n")
    out, base = [], 0
    for i, line in enumerate(lines, 1):
        start = base
        base += len(line) + 1
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("*"):
            continue
        for m in CMP.finditer(line):
            if not mask[start + m.start()]:
                continue
            num = next((g for g in m.groups() if g), None)
            if num is None:
                continue
            # 0 and 1 are almost always emptiness or identity tests, not thresholds.
            try:
                if abs(float(num)) in (0.0, 1.0):
                    continue
            except ValueError:
                continue
            out.append({"line": i, "num": num, "kind": kind_of(line), "src": stripped[:150]})
    return out


# The rules permitted to remove an element, kept in step with test_ledger's L10c.
# A line that both compares against a chosen number AND calls _drop with a rule
# outside this set is a threshold gating EXISTENCE — the thing #28 established must
# never happen. Two members legitimately involve a rect: not-visible is whether the
# page renders it at all, outside-viewport is the caller's own viewport.
SPEC_DELETES = {
    "not-connected", "not-visible", "checkVisibility-false", "aria-hidden",
    "inert", "outside-viewport", "not-interactive", "contenteditable-non-root",
    "inside-editor-host", "canvas-measure-failed", "iframe-contents-listed-instead",
}
DROP_CALL = re.compile(r"""_drop(?:Mmids)?\(\s*[^,]+,\s*['"]([a-z:-]+)['"]""")


def gating_existence(found: list[dict]) -> list[dict]:
    """Threshold sites whose own line deletes under a rule outside the permitted set."""
    bad = []
    for f in found:
        if f["kind"] not in ("viewport-fraction", "pixel-count", "element-count"):
            continue
        for m in DROP_CALL.finditer(f["src"]):
            if m.group(1) not in SPEC_DELETES:
                bad.append(dict(f, rule=m.group(1)))
    return bad


# The five container rules in their PRE-#28 form, when they still deleted. A
# detector that reports "0 findings" is worth nothing until it has been shown to
# fire — audit_patterns.py carries the same self-test for the same reason, and #28
# happened precisely because a hand audit reported a clean-looking three.
REGRESSION_CORPUS = [
    ("parent-child-dedup",
     "if (cursorOnly && parentStrong && parentEntry.w * parentEntry.h <= 0.15 * vw * vh)"
     " return _drop(el, 'parent-child-dedup');"),
    ("delegation-root",
     "if (contained >= 8 && (e.h >= vh * 0.5)) _dropMmids(drop, 'delegation-root');"),
    ("container-suppression",
     "if (n < 3) continue; if (be.h >= vh * 1.2) _dropMmids(drop, 'container-suppression');"),
    ("same-box-wrapper-collapse",
     "if (Math.abs(h.w - e.w) <= 8) _dropMmids(drop, 'same-box-wrapper-collapse');"),
    ("shadow-host-collapse",
     "if (Math.abs(h.x - e.x) <= 4) _dropMmids(removedHosts, 'shadow-host-collapse');"),
]


def self_test() -> bool:
    print("detector self-test (the five pre-#28 container deletes must be flagged):")
    ok = True
    for rule, src in REGRESSION_CORPUS:
        rows = [{"line": 0, "num": "8", "kind": kind_of(src), "src": src}]
        hit = gating_existence(rows)
        got = bool(hit) and hit[0]["rule"] == rule
        ok = ok and got
        print(f"  {'PASS' if got else 'FAIL'}  {rule:26} kind={rows[0]['kind']}")
    print()
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind")
    ap.add_argument("--full", action="store_true")
    args = ap.parse_args()

    if not self_test():
        print("The detector cannot see the rules it exists to catch — fix it before")
        print("trusting the clean report below.\n")
    found = scan()
    by = defaultdict(list)
    for f in found:
        by[f["kind"]].append(f)

    print(f"{len(found)} hardcoded thresholds in {TARGET}\n")
    print(f"{'kind':<18}{'count':>7}   risk")
    for k in ("viewport-fraction", "pixel-count", "element-count", "duration",
              "spec-or-index", "other"):
        if by.get(k):
            print(f"{k:<18}{len(by[k]):>7}   {RISK[k]}")

    judgement = len(by["viewport-fraction"]) + len(by["pixel-count"]) + len(by["element-count"])
    print(f"\n{judgement} of {len(found)} are JUDGEMENTS about a page's layout or size.")
    _bad = gating_existence(found)
    if _bad:
        print("FAIL: a chosen number GATES EXISTENCE on these lines —")
        for b in _bad:
            print(f"  {TARGET}:{b['line']}  [{b['num']}] deletes as '{b['rule']}'")
            print(f"    {b['src']}")
    else:
        print("None of them gates existence: no line combines a chosen number with a")
        print("delete outside the permitted set. Checked MECHANICALLY — #28's three")
        print("missed container rules were missed by two separate static reviews.")

    show = [args.kind] if args.kind else ["viewport-fraction", "pixel-count"]
    for k in show:
        rows = by.get(k) or []
        if not rows:
            continue
        print(f"\n{'=' * 74}\n{k.upper()} — {len(rows)} site(s)\n{'=' * 74}")
        for r in (rows if (args.full or args.kind) else rows[:24]):
            print(f"\n{TARGET}:{r['line']}  [{r['num']}]")
            print(f"  {r['src']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
