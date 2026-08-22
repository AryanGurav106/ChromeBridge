"""Static audit of every pattern-match in the collector, classified by how it fails.

WHY THIS EXISTS
---------------
Pattern matching is where this project breaks, and it breaks QUIETLY. Three
separate incidents, all the same shape — a matcher that reads as general and
measures as narrow, failing with no error and no missing-result signal:

  * the ablation study found three `/[a-z0-9]/i` gates discarding EVERY
    CJK/Cyrillic/Arabic label, and four page scans blind to shadow DOM;
  * the submit picker's destructive wordlist listed 削除 / キャンセル / 삭제 /
    удалить behind a trailing `\\b`, which is an ASCII-only boundary — so every
    non-Latin entry was dead code while the comment claimed multilingual cover;
  * 1,304 fields on 66% of the corpus were truncated with no marker, hiding
    216,719 characters in a form indistinguishable from a short value.

Grepping found none of these until someone already suspected them. So this
enumerates EVERY regex literal and string-membership test in the extension and
the server, classifies each by the failure mode it is vulnerable to, and prints
them for review. It cannot decide correctness — a regex over a CSS class name is
fine, the same regex over page text is a locale bug — so the output is a review
queue, not a verdict, and each finding is dispositioned in AUDIT_PATTERNS.md.

CATEGORIES
  ascii-on-text     ASCII-only class or \\b against content that may be any script.
                    The highest-severity class: silently excludes most of the web.
  wordlist          an alternation of natural-language words. Fine as a BOOSTER
                    or a last-resort tier, a locale bug as a sole gate.
  framework-name    a library's class/attribute convention (cm-, ant-, Mui, v-).
                    Fine as a booster; load-bearing means the page must use that
                    library to be seen at all.
  class-substring   matching on CSS class text, which is author-controlled and
                    unstandardised, but at least not language-dependent.
  html-regex        a regex applied to markup rather than to the DOM.
  url-host          hardcoded hosts or URL shapes.

Run:  python tools/audit_patterns.py            # summary + review queue
      python tools/audit_patterns.py --cat ascii-on-text
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = ["extension/background.js", "extension/listener_tag.js",
         "extension/sidepanel.js", "mcp_server.py"]

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# A JS regex literal, avoiding division and comments. Deliberately conservative:
# it is better to miss an exotic literal than to fill the queue with `a / b`.
JS_RE = re.compile(r"(?<![\w)\]])/(?![/*])((?:\\.|\[(?:\\.|[^\]\\])*\]|[^/\\\n])+)/([gimsuy]*)")
PY_RE = re.compile(r"""re\.(?:compile|match|search|findall|sub|split)\(\s*r?["']([^"']+)["']""")

ASCII_CLASS = re.compile(r"\[(?:\^?)(?:a-z|A-Z|a-zA-Z|A-Za-z)[^\]]*\]|\\w|\\b")
# A word-ish alternation: three or more runs of letters separated by |
WORDLIST = re.compile(r"(?:[A-Za-zÀ-ɏ]{2,}\|){2,}[A-Za-zÀ-ɏ]{2,}")
FRAMEWORKS = re.compile(
    r"\b(cm-|CodeMirror|monaco|ace_|ant-|Mui|mat-|v-|ng-|chakra|select2|choices__|"
    r"slick|swiper|tox-|ql-|ProseMirror|lexical|tiptap|rc-|el-|p-|sl-|md-|dx-|k-|"
    r"bp[35]-|oxd-|rz-|primevue|vuetify|bootstrap|tailwind)", re.I)
CLASS_SUB = re.compile(r"class(?:Name)?\s*(?:\*|\^|\$)?=|\[class\*=|className")
URLHOST = re.compile(r"https?://|\.com\b|\.org\b|localhost|127\.0\.0\.1")

# Contexts that mean the subject is page TEXT (any script) rather than a class
# name, an attribute name, a URL or a key code.
TEXTY = re.compile(
    r"innerText|textContent|\btxt\b|\blabel\b|\bname\b|\bvalue\b|placeholder|"
    r"ariaLabel|aria-label|heading|caption|alt\b|title\b|query|\bq\b|\bterm\b", re.I)
NOT_TEXTY = re.compile(
    r"className|getAttribute\(['\"](?:class|id|data-|style)|selector|\bsel\b|"
    r"\burl\b|href|\bsrc\b|tagName|nodeName|key(?:Code)?|mmid|\bcss\b|font|"
    r"style\.|\bpath\b|\bfile\b|\bmime\b", re.I)


def classify(pat: str, line: str) -> list[str]:
    cats = []
    texty = bool(TEXTY.search(line)) and not NOT_TEXTY.search(line)
    if ASCII_CLASS.search(pat) and texty:
        cats.append("ascii-on-text")
    if WORDLIST.search(pat):
        cats.append("wordlist")
    if FRAMEWORKS.search(pat):
        cats.append("framework-name")
    if CLASS_SUB.search(line) or CLASS_SUB.search(pat):
        cats.append("class-substring")
    if URLHOST.search(pat):
        cats.append("url-host")
    if re.search(r"<\w+|</\w+|&[a-z]+;", pat):
        cats.append("html-regex")
    return cats or ["other"]


def scan() -> list[dict]:
    out = []
    for rel in FILES:
        p = ROOT / rel
        if not p.exists():
            continue
        src = p.read_text(encoding="utf-8")
        lines = src.split("\n")
        rx = PY_RE if rel.endswith(".py") else JS_RE
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("#") or stripped.startswith("*"):
                continue
            for m in rx.finditer(line):
                pat = m.group(1)
                if len(pat) < 2:
                    continue
                out.append({"file": rel, "line": i, "pat": pat,
                            "cats": classify(pat, line), "src": stripped})
    return out


# The three patterns this audit exists because of, in their PRE-FIX form. A
# detector that reports "0 findings" is worth nothing until it has been shown to
# fire, and every one of these passed a code review before it was measured. If a
# future edit to classify() stops flagging them, the audit is lying, not clean.
REGRESSION_CORPUS = [
    ("ascii-on-text", r"[a-z0-9]",
     "if (!/[a-z0-9]/i.test(txt)) return '';   // ablation: killed every CJK label"),
    ("ascii-on-text", r"^(cancel|close|delete|削除)\b",
     r"if (/^(cancel|close|delete|削除)\b/i.test(txt)) return false;  // \b is ASCII-only"),
    ("wordlist", r"^(submit|save|confirm|continue)\b",
     r"const submitWords = /^(submit|save|confirm|continue)\b/i;  // English-only gate"),
]


def self_test() -> bool:
    ok = True
    print("detector self-test (historical bugs must be flagged):")
    for want, pat, line in REGRESSION_CORPUS:
        cats = classify(pat, line)
        hit = want in cats
        ok = ok and hit
        print(f"  {'PASS' if hit else 'FAIL'}  {want:<14} /{pat[:44]}/  -> {','.join(cats)}")
    print()
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cat", default=None)
    ap.add_argument("--full", action="store_true", help="print every finding")
    args = ap.parse_args()

    if not self_test():
        print("*** classify() no longer catches known bugs — findings"
              " below are NOT trustworthy ***" + chr(10))
    found = scan()
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for f in found:
        for c in f["cats"]:
            by_cat[c].append(f)

    print(f"{len(found)} pattern-matching sites across {len(FILES)} files\n")
    print(f"{'category':<18}{'count':>7}   risk")
    RISK = {
        "ascii-on-text": "HIGH   excludes non-Latin content silently",
        "wordlist":      "MED    locale-dependent; must not be a sole gate",
        "framework-name": "MED    site must use that library to be seen",
        "class-substring": "LOW    author-controlled but language-neutral",
        "html-regex":    "MED    parsing markup with a regex",
        "url-host":      "LOW    check it is not site-specific behaviour",
        "other":         "-      structural / key codes / formatting",
    }
    for c in ("ascii-on-text", "wordlist", "framework-name", "html-regex",
              "class-substring", "url-host", "other"):
        if by_cat.get(c):
            print(f"{c:<18}{len(by_cat[c]):>7}   {RISK[c]}")

    # EVERY risky category is listed, not three of them. framework-name and
    # class-substring were counted in the table above and never printed, so the
    # three sites in them could not be reviewed from this tool's output at all —
    # a category you cannot read is a category nobody audits. "other" stays behind
    # --cat/--full because it is 209 structural/formatting patterns.
    show = [args.cat] if args.cat else [
        "ascii-on-text", "wordlist", "framework-name", "html-regex",
        "class-substring", "url-host",
    ]
    for c in show:
        rows = by_cat.get(c) or []
        if not rows:
            continue
        print(f"\n{'='*74}\n{c.upper()} — {len(rows)} site(s)\n{'='*74}")
        for r in rows if (args.full or args.cat) else rows[:40]:
            print(f"\n{r['file']}:{r['line']}")
            print(f"  /{r['pat'][:120]}/")
            print(f"  {r['src'][:150]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
