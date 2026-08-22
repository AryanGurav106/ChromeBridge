"""Lint suite for the failure modes that keep coming back in pattern matching.

Three incidents, one shape: a matcher that reads as general and measures as
narrow, failing with no error and no missing-result signal.

  1  `/[a-z0-9]/i` gates discarded every CJK / Cyrillic / Arabic label. Found by
     ablation, not by review.
  2  The destructive wordlist listed 削除 / キャンセル / 삭제 / удалить behind a
     trailing `\\b` — an ASCII-only boundary, so every non-Latin entry was dead
     code while the comment above it claimed multilingual coverage.
  3  The SAME concept was spelled two ways ("is this button destructive?") in two
     tiers of one function, so 'Abbrechen' was rejected by one and accepted by
     the other. The placeholder-word question had FOUR copies.

Each of those survived reading. What catches them is a rule a machine can check,
so this file is rules, not examples:

  P1  no regex may put `\\b` next to a non-ASCII alternative  — bug 2, mechanically
  P2  one concept, one spelling: every definition tagged `i18n:<concept>` must be
      byte-identical to its siblings                          — bug 3, mechanically
  P3  the pattern auditor still fires on all three historical bugs, so its "0
      findings" means something                               — bug 1, by proxy
  P4  no ASCII-only character class gates page text           — bug 1, directly

P2 exists because the duplication is FORCED: these functions are injected into
the page with chrome.scripting and lose their closure, so a shared constant is
not available to them. The copies are deliberate; the drift was not.

Run:  python tools/test_patterns.py
"""

from __future__ import annotations

import importlib.util
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_spec = importlib.util.spec_from_file_location("ap", ROOT / "tools" / "audit_patterns.py")
ap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ap)

FILES = ["extension/background.js", "extension/listener_tag.js", "mcp_server.py"]
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  - {detail}" if detail else ""))


def main() -> int:
    findings = ap.scan()

    # ---- P1: \b beside a non-ASCII alternative --------------------------------
    # JS \w is [A-Za-z0-9_]. `\b` after 削除 asks for a boundary between two
    # non-word characters, which never exists, so the alternative can never match.
    # ONE implementation, used for both the scan and its control. The first
    # version of this rule could not fire at all: the character class excluded
    # `)`, and in the pattern that actually shipped the `\b` sits AFTER the
    # closing paren of the alternation — `…|削除)\b` — so nothing ever matched
    # and P1 passed by being blind. The control below is what exposed that, which
    # is the whole argument for having one.
    def _p1(pat: str) -> list[str]:
        if "\\b" not in pat or not any(ord(c) > 127 for c in pat):
            return []
        out = []
        # the last alternative, then any closing parens, then a literal \b
        for m in re.finditer(r"([^|()\[\]/\\]{1,40})\)*\\b", pat):
            tail = m.group(1)
            if tail and ord(tail[-1]) > 127:
                out.append(tail)
        return out

    bad = [(f["file"], f["line"], t[-12:])
           for f in findings for t in _p1(f["pat"])]
    check("P1 no regex puts \\b next to a non-ASCII alternative (it can never match)",
          not bad, "; ".join(f"{a}:{b} …{c!r}" for a, b, c in bad[:4]))
    check("P1* ...and the rule provably fires on the pattern that actually shipped",
          bool(_p1(r"^(cancel|close|delete|削除|삭제)\b")) and not _p1(r"^(cancel|delete)\b"),
          "fires on the shipped list, silent on its ASCII-only form")

    # ---- P2: one concept, one spelling ----------------------------------------
    tagged: dict[str, list[tuple[str, int, str]]] = defaultdict(list)
    TAG = re.compile(r"i18n:([a-z_]+)")
    for rel in FILES:
        src = (ROOT / rel).read_text(encoding="utf-8")
        lines = src.split("\n")
        for i, line in enumerate(lines):
            m = TAG.search(line)
            if not m:
                continue
            # The definition is the next line that is not a comment.
            for j in range(i + 1, min(i + 25, len(lines))):
                nxt = lines[j].strip()
                if nxt.startswith("//"):
                    continue
                tagged[m.group(1)].append((rel, j + 1, nxt))
                break
    # A concept tagged i18n: and then DELETED leaves its tombstone comments behind,
    # and that is the outcome we WANT — a deleted wordlist cannot drift. The rule is
    # about live copies of one definition diverging, so a concept counts as live
    # only where a definition actually names it. Anchoring on "the next non-comment
    # line" alone was wrong: after a tombstone that line is whatever code follows,
    # so two unrelated statements were compared as if they were two spellings of the
    # wordlist and P2 failed on a concept with no code left at all.
    _KEYWORDS = {"placeholder": "_phWord", "destructive": "DESTRUCTIVE", "submit": "submitWords"}

    for concept, sites in sorted(tagged.items()):
        needle = _KEYWORDS.get(concept, concept)
        live = [x for x in sites if needle in x[2] and "=" in x[2]]
        if not live:
            check(f"P2 i18n:{concept} was DELETED — no wordlist left to drift",
                  True, f"{len(sites)} tombstone comment(s), 0 live definitions")
            continue
        bodies = {x[2] for x in live}
        check(f"P2 i18n:{concept} has ONE spelling across its {len(live)} copies",
              len(bodies) == 1,
              f"{len(bodies)} distinct at " + ", ".join(f"{a}:{b}" for a, b, _ in live))
    check("P2* every tagged concept was actually located in the source",
          bool(tagged), f"concepts={sorted(tagged)}")
    # The corresponding control for P2: the comparison must reject two copies
    # that differ by a single alternative, which is exactly how DESTRUCTIVE drifted.
    _a = "const D = /^(cancel|close|delete)/i;"
    _b = "const D = /^(cancel|close|delete|remove)/i;"
    check("P2** ...and the comparison would REJECT two copies differing by one word",
          len({_a, _b}) == 2 and len({_a, _a}) == 1)

    # ---- P3: the auditor still detects the bugs it was built for --------------
    check("P3 the pattern auditor still fires on all three historical bugs",
          ap.self_test(), "see self-test output above")

    # ---- P4: no ASCII-only class gating page text -----------------------------
    ascii_text = [f for f in findings if "ascii-on-text" in f["cats"]]
    check("P4 no ASCII-only character class gates page text",
          not ascii_text,
          "; ".join(f"{f['file']}:{f['line']} /{f['pat'][:30]}/" for f in ascii_text[:4]))

    # ---- P5: the auditor's risky categories must not be part noise -------------
    # It used to decide "is this code" by asking whether the LINE STARTS with //,
    # which left two permanent false positives in the categories a human is meant
    # to read: a TRAILING comment (`codeEditor, // CodeMirror/Monaco/Ace host`
    # reported as a framework-name regex) and a user-facing legend string
    # (`- role=combobox / <select> ...` reported as an html-regex). Two of nine
    # risky hits being noise is how a real finding gets skimmed past — the same
    # failure mode as an always-on warning (#15). It shares `_extract.code_mask`
    # with every browser suite now, so there is one definition of "is this code".
    from _extract import code_mask  # noqa: PLC0415

    src = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
    mask = code_mask(src)
    offs, base = [], 0
    for line in src.split("\n"):
        offs.append(base)
        base += len(line) + 1
    inert = []
    for f in findings:
        if f["file"] != "extension/background.js":
            continue
        ln = f["line"] - 1
        if ln >= len(offs):
            continue
        # The auditor's RECORDED column, not a search for the pattern text: a
        # search finds the first occurrence on the line, which can land inside a
        # CSS selector string (`[class*="placeholder"]`) while the real match is
        # the regex further along. That mislocation made this check report a
        # genuine finding as noise.
        at = f.get("col")
        if at is None:
            continue
        if not mask[offs[ln] + at]:
            inert.append(f)
    check("P5 no reported pattern lies inside a comment or a string",
          not inert,
          "; ".join(f"{f['file']}:{f['line']} /{f['pat'][:34]}/" for f in inert[:4])
          or f"{len(findings)} findings, all in code")
    # NEGATIVE CONTROL, because P1's first version could not fire at all: the mask
    # must actually mark a known comment and a known legend string as non-code.
    _c = src.find("// CodeMirror/Monaco/Ace host")
    _s = src.find("- role=combobox / <select>")
    check("P5* ...and the mask provably marks a trailing comment and a legend"
          " string as non-code",
          _c > 0 and _s > 0 and not mask[_c + 4] and not mask[_s + 4],
          f"comment@{_c} code={bool(mask[_c + 4]) if _c > 0 else '?'}"
          f"  string@{_s} code={bool(mask[_s + 4]) if _s > 0 else '?'}")

    # ---- P6: no chosen NUMBER gates existence either ---------------------------
    # audit_patterns covers regexes and wordlists; magic numbers are the other half
    # of the same family, and #28 was five container rules deleting on thresholds
    # nobody had enumerated (8 contained controls, 25% of the viewport, 3
    # descendants, 12 residual characters, 4px, a name-length richness score). This
    # asserts mechanically what L10c asserts at runtime: no line combines a chosen
    # number with a delete outside the permitted set.
    from audit_thresholds_static import (  # noqa: PLC0415
        gating_existence, scan as scan_nums, self_test as num_self_test,
    )

    _rows = scan_nums()
    _bad = gating_existence(_rows)
    check("P6 no chosen number gates whether an element EXISTS",
          not _bad,
          "; ".join(f"bg.js:{b['line']} [{b['num']}] deletes as '{b['rule']}'"
                    for b in _bad[:3])
          or f"{len(_rows)} thresholds, "
             f"{sum(1 for r in _rows if r['kind'] in ('viewport-fraction', 'pixel-count', 'element-count'))}"
             f" of them layout judgements, none deleting")
    # And the detector must be shown to fire, because it found two of its own
    # classifier bugs the first time it was asked to: `ts\\b` matched inside
    # `removedHosts` so shadow-host-collapse was filed as a DURATION, and
    # entry-field geometry (`h.w`, `e.x`) was not recognised as pixels at all.
    check("P6* ...and the detector provably flags all five pre-#28 container deletes",
          num_self_test(),
          "see self-test output above")

    passed = sum(1 for r in results if r)
    print(f"\n{passed}/{len(results)} pattern-lint checks passed.")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
