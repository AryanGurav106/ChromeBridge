"""Audit of the NON-REGEX pattern surface, classified by how each site fails.

WHY THIS EXISTS
---------------
`audit_patterns.py` sees regex literals only. #71 measured that at ~26% of the
real pattern surface: the rest is `.includes(...)`, `.indexOf(...)`,
`.startsWith(...)`, `classList.contains(...)`, `x === 'literal'`,
`getAttribute('data-...')`, `.toLowerCase()` / `.normalize()` comparisons,
`.slice(0, N)` and bare numeric comparisons. #71 found real defects in exactly
that surface (a handler property invisible to every tool, a surrogate-pair cut
emitting invalid UTF-16, an ASCII-only `\\d` silently disabling a fold guard),
so it is classified here.

THE FILE LIST IS NOT RESTATED. It is imported from `audit_patterns.FILES`, so
the two auditors cannot drift apart (that list once said `sidepanel.js` for its
whole life and scanned three files while printing four).

FAILURE MODES (a site may carry several)
  ascii-on-text       ASCII-only class / \\b / charCode<128 gating text
  english-wordlist    a natural-language word compared against page text
  framework-name      a library's class/attribute convention
  class-substring     matching author-chosen class text
  fixed-threshold     a chosen number gating a decision (length, px, fraction)
  latin-digit         \\d / [0-9] / charCode 48..57 where any script's digits occur
  surrogate-unsafe    UTF-16 unit slicing of text with no surrogate guard
  locale-dependent    toLocale*Case / localeCompare with no locale
  exact-role-string   `role` compared as one raw string (ARIA says: token list)
  attr-vs-property    reads an `on*` ATTRIBUTE where the handler PROPERTY also counts
  data-attr           a page-author `data-*` attribute read as a signal
  benign-css-value    compares a computed-style / CSS keyword
  benign-spec-list    compares tag names, ARIA roles/attrs, input types, events
  benign-structural   no content judgement (empty tests, own markers, variable arg)

It cannot decide correctness -- a class test on the page's OWN marker is fine and
the same test on an author's class is a defect -- so the output is a review queue.
Verdicts live in docs/research/PATTERN-SURFACE-2026-11.md.

Run:  python tools/audit_pattern_surface.py              # counts + risky queue
      python tools/audit_pattern_surface.py --mode surrogate-unsafe
      python tools/audit_pattern_surface.py --md          # markdown listing
      python tools/audit_pattern_surface.py --self-test   # plants the old bugs
"""

from __future__ import annotations

import argparse
import io
import re
import sys
import tokenize
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _extract import code_mask  # noqa: E402
import audit_patterns as AP  # noqa: E402  (FILES, JS_RE, PY_RE, FRAMEWORKS, ...)

ROOT = AP.ROOT
FILES = AP.FILES  # imported, never restated

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BENIGN = {"benign-css-value", "benign-spec-list", "benign-structural"}
MODES = ["ascii-on-text", "english-wordlist", "framework-name", "class-substring",
         "fixed-threshold", "latin-digit", "surrogate-unsafe", "locale-dependent",
         "exact-role-string", "attr-vs-property", "data-attr",
         "benign-css-value", "benign-spec-list", "benign-structural"]

# ----------------------------------------------------------------- vocabularies
HTML_TAGS = set("""a abbr address area article aside audio b base bdi bdo blockquote body br button
canvas caption cite code col colgroup data datalist dd del details dfn dialog div dl dt em embed
fieldset figcaption figure footer form h1 h2 h3 h4 h5 h6 head header hgroup hr html i iframe img
input ins kbd label legend li link main map mark menu meta meter nav noscript object ol optgroup
option output p picture pre progress q rp rt ruby s samp script search section select slot small
source span strong style sub summary sup svg table tbody td template textarea tfoot th thead time
title tr track u ul var video wbr math g path rect circle text tspan use""".split())
ARIA_ROLES = set("""alert alertdialog application article banner button cell checkbox columnheader
combobox complementary contentinfo definition dialog directory document feed figure form generic grid
gridcell group heading img link list listbox listitem log main marquee math menu menubar menuitem
menuitemcheckbox menuitemradio meter navigation none note option presentation progressbar radio
radiogroup region row rowgroup rowheader scrollbar search searchbox separator slider spinbutton status
switch tab table tablist tabpanel term textbox timer toolbar tooltip tree treegrid treeitem""".split())
CSS_WORDS = set("""none block inline flex grid contents fixed absolute sticky relative static hidden
visible auto pointer collapse scroll clip inherit initial transparent normal nowrap pre wrap center
left right top bottom opacity transform ltr rtl text default move crosshair""".split())
INPUT_TYPES = set("""text password checkbox radio submit reset button image file hidden email url tel
number search date time datetime-local month week color range""".split())
EVENTS = set("""click pointerdown pointerup mousedown mouseup keydown keyup keypress input change
focus blur submit scroll load""".split())
SPEC_MISC = set("true false on off yes no null undefined _blank _top _self _parent top bottom "
                "ArrowDown ArrowUp ArrowLeft ArrowRight Enter Escape Tab Space Backspace Delete "
                "Home End PageUp PageDown Shift Control Alt Meta".split())
SPEC_ALL = HTML_TAGS | ARIA_ROLES | CSS_WORDS | INPUT_TYPES | EVENTS | SPEC_MISC

# classifiers over the SUBJECT (receiver + args) text
S_TAGROLE = re.compile(r"tagName|nodeName|localName|\btagL\b|\btag\b|\brole\b|\bkind\b|\bRole\b|\.type\b|\btype\b", re.I)
S_CLASS = re.compile(r"className|classList|\bcls\w*\b|\bclasses\b|\bcn\b")
S_CSS = re.compile(r"getComputedStyle|\.style\b|\bcs\b|\bcss\b|\bdisplay\b|\bposition\b|\boverflow|"
                   r"\bcursor\b|\bvisibility\b|pointerEvents|\btransition|\bpos\b|\bdsp\b")
S_URL = re.compile(r"href|\bsrc\b|\burl\b|location|\borigin\b|\bhost|\bpath\b|\bfile\b|\bmime\b|\bsel(ector)?\b", re.I)
S_ATTR = re.compile(r"getAttribute|hasAttribute|\.attributes\b|dataset|\battr\w*\b", re.I)
S_TEXT = re.compile(r"innerText|textContent|\.label\b|\.text\b|\btxt\b|\.title\b|placeholder|"
                    r"aria-label|heading|caption|\bmsg\b|\bquery\b|\bterm\b|\blab\b|\bstr\b|"
                    r"\bphrase\b|\blabel\w*\b|\btext\w*\b|\bwant\w*\b|\bhint\b|\.value\b|\bvalue\b|"
                    r"\bpick\.text|\bopt\w*\.text|\bname\b(?!\s*===\s*['\"](?:value|checked|selected|href|src))", re.I)
# the project's OWN protocol vocabulary (op names, states, message kinds): not page text
S_PROTO = re.compile(r"\.(op|kind|state|reason|action|status|phase|level)\b|\bmsg\.|\bnote\.|\bst\.name\b|"
                     r"^name$|^action$|\bname\s*$", re.I)
S_KEY = re.compile(r"\.key\b|\.code\b|\bkey\b|\bevent\b")
OWN_MARKER = re.compile(r"__ab|\bab[-_]|data-ab|mmid|__mmid|chromebridge|cb-", re.I)

GUARD = re.compile(r"surrogate|0xD8|0xDC|\\uD[89AB]|isHigh|codePointAt|Array\.from\(|\[\.\.\.|"
                   r"markCut|\bclip\(|_cut\(|\bclipText\b|\[\.\.\.\w+\]", re.I)
ARRAYISH = re.compile(r"\.sort\(\)\s*$|\.(?:filter|map|split)\([^)]*\)\s*$|\b(els|hs|ks|_?tbls|toks|fields|arr|out|rows|lines|parts|list|items|els|nodes|kids|children|members|hits|"
                      r"opts|options|cands|candidates|refs|ids|entries|keys|vals|results|tabs|steps|"
                      r"checks|log|buf|q|stack|queue|mmids|matches|sample)\w*\b", re.I)

# ---------------------------------------------------------------- site records
class Site:
    __slots__ = ("file", "line", "kind", "snippet", "modes", "note")

    def __init__(self, file, line, kind, snippet, modes, note=""):
        self.file, self.line, self.kind = file, line, kind
        self.snippet, self.modes, self.note = snippet, modes, note

    @property
    def risky(self):
        return any(m not in BENIGN for m in self.modes)


def blank_py(src: str) -> str:
    """Blank comments and docstrings in Python source, keep offsets."""
    out = list(src)
    lines = src.splitlines(keepends=True)
    starts = [0]
    for l in lines:
        starts.append(starts[-1] + len(l))

    def off(pos):
        return starts[pos[0] - 1] + pos[1]
    try:
        prev = None
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                a, b = off(tok.start), off(tok.end)
                for k in range(a, b):
                    if out[k] != "\n":
                        out[k] = " "
            elif tok.type == tokenize.STRING and prev in (None, tokenize.NEWLINE, tokenize.INDENT,
                                                          tokenize.DEDENT, tokenize.NL):
                a, b = off(tok.start), off(tok.end)
                for k in range(a, b):
                    if out[k] != "\n":
                        out[k] = " "
            if tok.type not in (tokenize.NL, tokenize.COMMENT):
                prev = tok.type
            elif tok.type == tokenize.NL and prev is None:
                pass
    except (tokenize.TokenError, IndentationError):
        pass
    return "".join(out)


def blank_js(src: str) -> str:
    m = code_mask(src, strings_are_code=True)
    return "".join(c if (m[i] or c == "\n") else " " for i, c in enumerate(src))


def lit_strings(s: str) -> list[str]:
    return [a or b for a, b in re.findall(r"'((?:\\.|[^'\\\n])*)'|\"((?:\\.|[^\"\\\n])*)\"", s)]


def balanced_args(code: str, i: int) -> tuple[str, int]:
    """code[i] == '('. Return (inner text, index after ')')."""
    depth, j, n = 0, i, len(code)
    q = None
    while j < n:
        c = code[j]
        if q:
            if c == "\\":
                j += 2
                continue
            if c == q:
                q = None
        elif c in "'\"`":
            q = c
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                return code[i + 1:j], j + 1
        j += 1
    return code[i + 1:i + 80], i + 80


def receiver_before(code: str, dot: int) -> str:
    """The expression immediately left of code[dot] == '.'."""
    j = dot
    while j > 0:
        c = code[j - 1]
        if c in ")]}":
            depth, k = 0, j - 1
            while k >= 0:
                if code[k] in ")]}":
                    depth += 1
                elif code[k] in "([{":
                    depth -= 1
                    if depth == 0:
                        break
                k -= 1
            j = k
        elif c.isalnum() or c in "_$.?'\"" or c == "!":
            j -= 1
        else:
            break
        if dot - j > 160:
            break
    return code[j:dot]


def is_alpha_word(s: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z\- ]{2,}", s))


def classify_membership(subj: str, lits: list[str], ctx: str) -> tuple[list[str], str]:
    """A test of `subj` against literals. Returns (modes, note)."""
    words = [l for l in lits if is_alpha_word(l)]
    nonword = [l for l in lits if l and not is_alpha_word(l)]
    isclass = bool(S_CLASS.search(subj))
    iscss = bool(S_CSS.search(subj))
    istag = bool(S_TAGROLE.search(subj))
    isurl = bool(S_URL.search(subj))
    isattr = bool(S_ATTR.search(subj))
    istext = bool(S_TEXT.search(subj))
    iskey = bool(S_KEY.search(subj))
    if S_PROTO.search(subj.strip()) and not S_TEXT.search(subj.replace("name", "")):
        return ["benign-structural"], "own protocol vocabulary"
    modes = []
    notes = []
    if any(OWN_MARKER.search(l) for l in lits):
        return ["benign-structural"], "own marker"
    if isclass:
        if words or nonword:
            if any(AP.FRAMEWORKS.search(l) for l in lits):
                modes.append("framework-name")
            else:
                modes.append("class-substring")
        else:
            modes.append("benign-structural")
        return modes, "class text"
    if isattr and any(l.startswith("data-") for l in lits):
        if any(AP.FRAMEWORKS.search(l) for l in lits) or any(
                re.search(r"radix|headless|popper|floating|state|testid|mui|ant|chakra", l, re.I) for l in lits):
            return ["framework-name", "data-attr"], "page-author data-* attribute"
        return ["data-attr"], "page-author data-* attribute"
    if isattr and re.search(r"['\"]role['\"]", subj):
        istag = True
    if not words:
        return ["benign-structural"], "no word literal"
    allspec = all((w in SPEC_ALL) or w.lower() in SPEC_ALL for w in words)
    if iscss and allspec:
        return ["benign-css-value"], "css keyword"
    if (istag or iskey or isurl) and not istext:
        return (["benign-spec-list"] if allspec or istag else ["benign-structural"]), "tag/role/type/key"
    if allspec and not istext:
        return ["benign-spec-list"], "spec vocabulary"
    if istext:
        return ["english-wordlist"], "word literal against text-like subject"
    return ["benign-structural"], "subject not text-like"


def numeric_site(kind, line, code_line):
    return None


def scan_source(src: str, rel: str) -> list[Site]:
    py = rel.endswith(".py")
    code = blank_py(src) if py else blank_js(src)
    lines_off = [0]
    for l in src.split("\n"):
        lines_off.append(lines_off[-1] + len(l) + 1)

    def lineno(pos):
        lo, hi = 0, len(lines_off) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if lines_off[mid] <= pos:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1
    src_lines = src.split("\n")
    sites: list[Site] = []

    def add(pos, kind, modes, note=""):
        ln = lineno(pos)
        sites.append(Site(rel, ln, kind, src_lines[ln - 1].strip()[:200], modes, note))

    def pre_ctx(pos, n=420):
        return code[max(0, pos - n):pos]

    # ---- method-call sites -------------------------------------------------
    if py:
        call_re = re.compile(r"\.(startswith|endswith|find|index|lower|casefold|upper|isascii|isalpha|"
                             r"isalnum|isdigit|encode|translate|normalize)\(")
    else:
        call_re = re.compile(r"\.(includes|indexOf|lastIndexOf|startsWith|endsWith|has|contains|slice|"
                             r"substring|substr|split|charAt|charCodeAt|codePointAt|normalize|"
                             r"toLowerCase|toUpperCase|toLocaleLowerCase|toLocaleUpperCase|"
                             r"localeCompare|toLocaleString|getAttribute|hasAttribute)\(")
    for m in call_re.finditer(code):
        meth = m.group(1)
        dot = m.start()
        recv = receiver_before(code, dot)
        args, end = balanced_args(code, m.end() - 1)
        lits = lit_strings(src[m.end():end]) if args else []
        subj = recv + " " + args
        ctx = pre_ctx(dot)
        if meth in ("toLocaleLowerCase", "toLocaleUpperCase", "toLocaleString", "localeCompare"):
            if not args.strip():
                add(dot, meth, ["locale-dependent"], "no locale argument")
            else:
                add(dot, meth, ["benign-structural"], "explicit locale")
            continue
        if meth in ("includes", "indexOf", "lastIndexOf", "startsWith", "endsWith", "has", "contains",
                    "startswith", "endswith", "find", "index"):
            if meth == "has" and not lits and not S_TEXT.search(subj):
                continue  # Set/Map membership of a variable: nothing to judge
            modes, note = classify_membership(subj, lits, ctx)
            if meth in ("includes", "indexOf", "has") and recv.strip().startswith("["):
                # array-literal receiver: the words are IN the receiver
                rl = lit_strings(recv)
                modes, note = classify_membership(args, rl, ctx)
            add(dot, meth, modes, note)
            continue
        if meth in ("getAttribute", "hasAttribute"):
            if not lits:
                continue
            a = lits[0]
            if a == "role":
                add(dot, meth + "(role)", ["exact-role-string"],
                    "role read as one raw string unless split/tokenised nearby") if not re.search(
                    r"split\(|_roleHit|_roleTokens|\.trim\(\)\.split|toLowerCase\(\)\.split",
                    src_lines[lineno(dot) - 1]) else add(dot, meth + "(role)", ["benign-spec-list"], "tokenised")
            elif a.startswith("data-"):
                if OWN_MARKER.search(a):
                    add(dot, meth, ["benign-structural"], "own marker")
                else:
                    fw = bool(re.search(r"radix|headless|popper|floating|state|testid|mui|ant|chakra", a, re.I))
                    add(dot, meth, (["framework-name", "data-attr"] if fw else ["data-attr"]),
                        "page-author data-* attribute")
            elif re.fullmatch(r"on[a-z]+", a):
                # F1 (#71): an `on*` attribute read where the handler PROPERTY also counts
                near = code[max(0, dot - 300):end + 300]
                if re.search(r"_hasHandlerProp|\.on" + a[2:] + r"\b|__abClickBound|ACTIVATION", near):
                    add(dot, meth, ["benign-spec-list"], "handler property also read")
                else:
                    add(dot, meth, ["attr-vs-property"], "attribute read with no handler-property read nearby")
            continue
        if meth in ("slice", "substring", "substr", "charAt"):
            if py:
                continue
            nums = re.findall(r"\b(\d+)\b", args)
            two = "," in args
            if ARRAYISH.search(recv):
                continue                      # an array slice, not a string cut
            texty = bool(S_TEXT.search(recv)) or bool(re.search(
                r"trim\(\)|\.replace\(|String\(|\.toString\(\)|\|\|\s*''\)|\b(?:em|desc|nm|host|url|u|raw|_ra|msg|err)\b", recv))
            if not two and meth != "charAt":
                continue  # prefix/suffix strip after a literal test
            if not texty:
                continue
            if re.search(r"toISOString|toString\(36\)|random", recv):
                continue                      # ASCII by construction
            if re.match(r"\s*(?:===|!==)\s*['\"]", code[end:end + 12]):
                continue                      # compared to an ASCII literal prefix
            guarded = bool(GUARD.search(src[max(0, src.rfind("\n", 0, dot - 300)):dot + 200]))
            n_lit = bool(nums) and int(nums[-1]) >= 2 and two and args.strip().startswith("0")
            modes = []
            if not guarded:
                modes.append("surrogate-unsafe")
            if n_lit:
                modes.append("fixed-threshold")
            if modes:
                add(dot, meth, modes, "UTF-16 unit cut" + (", numeric bound" if n_lit else ""))
            continue
        if meth == "split" and re.fullmatch(r"''|\"\"", args.strip()):
            add(dot, "split('')", ["surrogate-unsafe"], "splits into UTF-16 units")
            continue
        if meth in ("charCodeAt", "codePointAt"):
            near = src_lines[lineno(dot) - 1]
            if re.search(r"[<>]=?\s*(128|127|0x7f|0x80|255|256)\b", near, re.I):
                add(dot, meth, ["ascii-on-text"], "code unit bound as 'is ASCII'")
            if re.search(r"\b(48|57|0x30|0x39)\b", near):
                add(dot, meth, ["latin-digit"], "code 48..57")
            continue
        if meth in ("toLowerCase", "toUpperCase", "lower", "upper", "casefold"):
            # a case fold DIRECTLY compared to / searched for an English literal
            tail = code[end:end + 60]
            head = code[max(0, dot - 80):dot]
            cmp1 = re.match(r"\s*\)?\s*(?:\.trim\(\)\s*)?(?:===|!==|==|!=)\s*['\"]([^'\"\n]*)['\"]", tail)
            cmp2 = re.match(r"\s*(?:\.strip\(\)\s*)?(?:\.(?:startswith|endswith)\(|in\s*[\(\[{])\s*['\"]([^'\"\n]*)['\"]", tail)
            cmp3 = re.match(r"\s*\.(?:includes|indexOf|startsWith|endsWith)\(\s*['\"]([^'\"\n]*)['\"]", tail)
            cmp4 = re.search(r"['\"]([^'\"\n]*)['\"]\s*(?:===|!==|==|!=|in)\s*$", head)
            lit = next((c.group(1) for c in (cmp1, cmp2, cmp3, cmp4) if c), None)
            if lit and is_alpha_word(lit) and lit not in SPEC_ALL and S_TEXT.search(recv) \
                    and not S_TAGROLE.search(recv) and not S_CSS.search(recv) and not S_PROTO.search(recv):
                add(dot, meth, ["english-wordlist"], "folded text compared to English literal")
            continue
        if meth in ("isascii", "encode") and py:
            if meth == "isascii" or re.search(r"['\"]ascii['\"]", args):
                add(dot, meth, ["ascii-on-text"], "ASCII gate")
            continue
        if meth == "normalize" and not py:
            continue

    # ---- CSS SELECTOR strings: querySelector(All)/matches/closest ------------
    # `[class*="fa-"]` is a class-substring test spelled as a selector, and the
    # first version of this auditor could not see it because the argument is a
    # string, not a method call on a text value.
    if not py:
        for m in re.finditer(r"\.(querySelectorAll|querySelector|matches|closest)\(", code):
            args, end = balanced_args(code, m.end() - 1)
            for sel in lit_strings(src[m.end():end]):
                modes, note = [], ""
                for cm in re.finditer(r"\[class\s*([*^$~|]?)=\s*[\"']?([^\]\"']*)", sel):
                    val = cm.group(2)
                    if OWN_MARKER.search(val):
                        continue
                    fw = bool(AP.FRAMEWORKS.search(val)) or bool(re.fullmatch(
                        r"(fa|bi|icon|lucide|ph|ri|ti|mdi|bx|octicon|tabler|la|gg|ant|mui|v|el|md|p|sl|rc)-?", val.strip("-_ ")+"-"))
                    modes.append("framework-name" if fw else "class-substring")
                    note = f"[class{cm.group(1)}={val!r}] attribute selector"
                for dm in re.finditer(r"\[(data-[\w-]+)", sel):
                    if OWN_MARKER.search(dm.group(1)):
                        continue
                    fw = bool(re.search(r"radix|headless|popper|floating|state|testid|mui|ant|chakra|value|placeholder", dm.group(1), re.I))
                    modes += (["framework-name", "data-attr"] if fw else ["data-attr"])
                    note = note or f"[{dm.group(1)}] attribute selector"
                for km in re.finditer(r"(?<![\w\]\)-])\.(?!__ab)([A-Za-z_][\w-]*)", sel):
                    if OWN_MARKER.search(km.group(1)):
                        continue
                    fw = bool(AP.FRAMEWORKS.search(km.group(1) + "-"))
                    modes.append("framework-name" if fw else "class-substring")
                    note = note or f".{km.group(1)} class selector"
                if modes:
                    add(m.start(), "selector", sorted(set(modes)), note)
                elif re.search(r"\[role\s*=|\[aria-|\binput\b|\bbutton\b|\ba\[|\bselect\b|\btextarea\b|\[type=|\[href|\[tabindex|\[contenteditable|\[onclick|\[for=|\[popover|\[open|\[inert", sel):
                    add(m.start(), "selector", ["benign-spec-list"], "tag/role/aria/type selector")
    # ---- equality against a string literal ---------------------------------
    eq = re.compile(r"(?P<lhs>[\w$.\]\)]+(?:\([^()\n]{0,40}\))?)\s*(?:===|!==|==|!=)\s*(?P<lit>'(?:\\.|[^'\\\n])*'|\"(?:\\.|[^\"\\\n])*\")")
    eq2 = re.compile(r"(?P<lit>'(?:\\.|[^'\\\n])*'|\"(?:\\.|[^\"\\\n])*\")\s*(?:===|!==|==|!=)\s*(?P<lhs>[\w$.\]\)]+)")
    for rx in (eq, eq2):
        for m in rx.finditer(code):
            lit = m.group("lit")[1:-1]
            lhs = m.group("lhs")
            if not lit or not is_alpha_word(lit):
                continue
            if re.search(r"getAttribute\(['\"]role|\.role\b|\brole\b", lhs):
                if lit in ARIA_ROLES or True:
                    add(m.start(), "== role", ["exact-role-string"],
                        "raw string equality on role (ARIA: ASCII-insensitive token list)")
                continue
            modes, note = classify_membership(lhs, [lit], pre_ctx(m.start()))
            if modes == ["benign-structural"]:
                continue  # equality on a variable of unknown provenance: nothing to say
            add(m.start(), "==", modes, note)

    # ---- numeric thresholds -------------------------------------------------
    num = re.compile(r"(?P<lhs>\.length|[A-Za-z_$][\w$]*(?:Width|Height|width|height|Top|Left|area|Area|"
                     r"top|left|right|bottom)\b|\binner(?:Width|Height)\b|len\([^()]{1,40}\))\s*"
                     r"(?P<op>>=|<=|>|<)\s*(?P<n>\d+(?:\.\d+)?)")
    for m in num.finditer(code):
        n = float(m.group("n"))
        lhs = m.group("lhs")
        if n <= 1 and "length" in lhs.lower() or n == 0:
            continue
        if n <= 1 and "length" not in lhs.lower() and "len(" not in lhs:
            pass
        add(m.start(), "numeric", ["fixed-threshold"], f"{lhs.strip()} {m.group('op')} {m.group('n')}")
    for m in re.finditer(r"\binner(?:Width|Height)\s*\*\s*0?\.\d+|0?\.\d+\s*\*\s*inner(?:Width|Height)", code):
        add(m.start(), "viewport-fraction", ["fixed-threshold"], "fraction of viewport")

    # ---- word/Set literal DEFINITIONS --------------------------------------
    if py:
        arr = re.compile(r"[\[({]\s*((?:'(?:\\.|[^'\\\n])*'|\"(?:\\.|[^\"\\\n])*\")\s*,\s*){2,}"
                         r"(?:'(?:\\.|[^'\\\n])*'|\"(?:\\.|[^\"\\\n])*\")\s*[\])}]")
    else:
        arr = re.compile(r"[\[({]\s*((?:'(?:\\.|[^'\\\n])*'|\"(?:\\.|[^\"\\\n])*\")\s*,\s*){2,}"
                         r"(?:'(?:\\.|[^'\\\n])*'|\"(?:\\.|[^\"\\\n])*\")\s*[\])}]")
    for m in arr.finditer(code):
        ls = lit_strings(m.group(0))
        words = [l for l in ls if is_alpha_word(l)]
        if len(words) < 3:
            continue
        head = src[max(0, m.start() - 60):m.start()]
        if all(w in SPEC_ALL or w.lower() in SPEC_ALL for w in words):
            add(m.start(), "list", ["benign-spec-list"], "all entries are tag/role/CSS/event vocabulary")
        elif any(AP.FRAMEWORKS.search(w) for w in words):
            add(m.start(), "list", ["framework-name"], "library names")
        elif re.search(r"(role|tag|type|attr|key|css|display|style|prop|event|mime|ext|FIELDS|KINDS|OBSERVES|"
                       r"ACTIVATION|for\s*\(?\s*(?:const|let)?\s*\w+\s+(?:of|in)\s*$|^.*\bfor\s+\w+\s+in\s*$)",
                       head, re.I):
            add(m.start(), "list", ["benign-spec-list"], "named for a spec property")
        else:
            add(m.start(), "list", ["english-wordlist"], "list of word literals")

    # ---- regex literals: only the modes audit_patterns does not have --------
    if not py:
        for m in AP.JS_RE.finditer(code):
            pat, flags = m.group(1), m.group(2)
            ln = src_lines[lineno(m.start()) - 1]
            texty = bool(AP.TEXTY.search(ln)) and not AP.NOT_TEXTY.search(ln)
            modes = []
            if re.search(r"(?<!\\)\\d|\[[^\]]*0-9[^\]]*\]", pat) and "p{Nd}" not in pat:
                if not re.search(r"selector|href|\burl\b|\bid\b|mmid|px|rect|width|height|css|style\.", ln, re.I):
                    modes.append("latin-digit")
            # #21: \b beside a NON-ASCII alternative can never match
            if re.search(r"[^\x00-\x7f]\)?\\b|\\b\(?[^\x00-\x7f]", pat):
                modes.append("ascii-on-text")
            if AP.WORDLIST.search(pat) and texty:
                modes.append("english-wordlist")
            if re.search(r"\[(?:\^?)(?:a-z|A-Z|a-zA-Z|A-Za-z)", pat) and texty and "u" not in flags:
                modes.append("ascii-on-text")
            if modes:
                add(m.start(), "regex", sorted(set(modes)), "regex literal")
    else:
        for m in re.finditer(r"""re\.(?:compile|match|search|findall|sub|split|fullmatch)\(\s*r?["']([^"']+)["']""", code):
            pat = m.group(1)
            modes = []
            if re.search(r"\[[^\]]*0-9[^\]]*\]", pat):
                modes.append("latin-digit")
            if re.search(r"\[(?:\^?)(?:a-z|A-Z|a-zA-Z|A-Za-z)", pat):
                modes.append("ascii-on-text")
            if AP.WORDLIST.search(pat):
                modes.append("english-wordlist")
            if modes:
                add(m.start(), "regex", modes, "regex literal")
        for m in re.finditer(r"re\.ASCII|string\.ascii_\w+", code):
            add(m.start(), "ascii", ["ascii-on-text"], "ASCII flag/constant")

    # de-duplicate (a site may be reached by two detectors on one line+kind)
    seen, out = set(), []
    for s in sites:
        key = (s.file, s.line, s.kind, tuple(s.modes))
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def scan_all() -> list[Site]:
    missing = [f for f in FILES if not (ROOT / f).exists()]
    if missing:
        raise SystemExit(f"FILES names paths that do not exist: {missing}")
    out = []
    for rel in FILES:
        out += scan_source((ROOT / rel).read_text(encoding="utf-8"), rel)
    return out


# ---------------------------------------------------------------------- self test
PLANTED = [
    # (name, filename, source, mode that MUST fire)
    ("#21 \\b beside a CJK alternative", "x.js",
     "if (/^(cancel|delete|削除|삭제)\\b/i.test(label.textContent)) bad();", "ascii-on-text"),
    ("#21 english destructive wordlist (array receiver)", "x.js",
     "if (['cancel','delete','remove'].includes(label.toLowerCase())) bad();", "english-wordlist"),
    ("#21 folded text vs English literal", "x.js",
     "if (label.toLowerCase() === 'submit') go();", "english-wordlist"),
    ("#24 placeholder wordlist regex", "x.js",
     "if (/select|choose|pick/i.test(el.textContent)) ph();", "english-wordlist"),
    ("#37 per-field cap, surrogate-unsafe", "x.js",
     "const f = (label) => label.slice(0, 60);", "surrogate-unsafe"),
    ("#37 per-field cap, numeric", "x.js",
     "const f = (label) => label.slice(0, 60);", "fixed-threshold"),
    ("#71 F3 fold-label back-off by code unit", "x.js",
     "const cut = (txt) => txt.substring(0, k);", "surrogate-unsafe"),
    ("#71 F4 ASCII-only digit test", "x.js",
     "const isNum = /^\\d+$/.test(text);", "latin-digit"),
    ("#71 locale-dependent fold", "x.js",
     "const k = text.toLocaleLowerCase();", "locale-dependent"),
    ("#71 F5 role as one raw string", "x.js",
     "if (el.getAttribute('role') === 'button') ok();", "exact-role-string"),
    ("#71 F1 onclick ATTRIBUTE only", "x.js",
     "if (el.hasAttribute('onclick')) ctl();", "attr-vs-property"),
    ("#29 state class decides selection", "x.js",
     "if (el.className.includes('selected')) cur();", "class-substring"),
    ("#29 library class convention", "x.js",
     "if (el.className.includes('ant-select')) combo();", "framework-name"),
    ("#28 pixel/length threshold", "x.js",
     "if (label.length > 60) drop();", "fixed-threshold"),
    ("viewport-fraction threshold", "x.js",
     "if (r.width > innerWidth * 0.25) big();", "fixed-threshold"),
    ("class substring spelled as a selector", "x.js",
     "const ic = el.querySelectorAll('[class*=\"fa-\"]');", "framework-name"),
    ("author class selector", "x.js",
     "const c = el.closest('.dropdown-menu');", "class-substring"),
    ("page-author data-* signal", "x.js",
     "const s = el.getAttribute('data-state');", "data-attr"),
    ("ASCII code-unit gate", "x.js",
     "if (s.charCodeAt(0) < 128) ascii();", "ascii-on-text"),
    ("py: english word against text", "x.py",
     "if 'select' in label.lower():\n    pass\nif label.lower().startswith('choose'):\n    pass", "english-wordlist"),
    ("py: ASCII gate", "x.py",
     "ok = text.encode('ascii', 'ignore')", "ascii-on-text"),
    ("py: latin-digit regex", "x.py",
     "import re\nm = re.search(r'[0-9]+', text)", "latin-digit"),
]
CONTROLS = [
    # (name, file, source, mode that must NOT fire)
    ("aria/role selector is benign", "x.js",
     "const c = el.querySelectorAll('[role=\"option\"],[aria-selected]');", "class-substring"),
    ("tag list is benign", "x.js", "if (['a','button','input'].includes(tagL)) ok();", "english-wordlist"),
    ("css keyword is benign", "x.js", "if (cs.position === 'fixed') ok();", "english-wordlist"),
    ("own marker class is benign", "x.js", "if (el.classList.contains('__ab_highlight__')) ok();", "class-substring"),
    ("surrogate-guarded slice is not flagged", "x.js",
     "const f = (label) => Array.from(label).slice(0, 60).join('');", "surrogate-unsafe"),
    ("handler property read nearby is fine", "x.js",
     "if (el.hasAttribute('onclick') || el.onclick) ctl();", "attr-vs-property"),
    ("tokenised role is fine", "x.js",
     "const r = (el.getAttribute('role')||'').trim().split(/\\s+/)[0];", "exact-role-string"),
    ("\\p{Nd} is not latin-digit", "x.js", "const n = /^\\p{Nd}+$/u.test(text);", "latin-digit"),
    ("explicit locale is fine", "x.js", "const k = text.toLocaleLowerCase('en');", "locale-dependent"),
]


def self_test() -> int:
    bad = 0
    for name, fn, src, mode in PLANTED:
        got = {m for s in scan_source(src, fn) for m in s.modes}
        ok = mode in got
        bad += not ok
        print(f"  {'FIRES ' if ok else 'MISSED'}  {name}  [{mode}]" + ("" if ok else f"  got={sorted(got)}"))
    for name, fn, src, mode in CONTROLS:
        got = {m for s in scan_source(src, fn) for m in s.modes}
        ok = mode not in got
        bad += not ok
        print(f"  {'quiet ' if ok else 'NOISY '}  control: {name}  [{mode}]" + ("" if ok else f"  got={sorted(got)}"))
    # the corpus itself must not be empty: a detector scanning nothing is silent too
    n = len(scan_all())
    if n < 300:
        print(f"  MISSED  corpus scan returned only {n} sites")
        bad += 1
    else:
        print(f"  ok      corpus scan returned {n} sites")
    print(f"\n{'SELF-TEST FAILED' if bad else 'self-test passed'}: {len(PLANTED)} planted, "
          f"{len(CONTROLS)} controls, {bad} failure(s)")
    return 1 if bad else 0


def report(sites, mode_filter=None, md=False):
    by_file = defaultdict(Counter)
    by_mode = Counter()
    distinct_risky = 0
    for s in sites:
        for m in s.modes:
            by_file[s.file][m] += 1
            by_mode[m] += 1
        distinct_risky += s.risky
    print(f"{len(sites)} non-regex-surface sites across {len(FILES)} files "
          f"({distinct_risky} carry at least one risky mode)\n")
    print(f"{'mode':<20}{'sites':>7}")
    for m in MODES:
        print(f"{m:<20}{by_mode[m]:>7}")
    print()
    print(f"{'file':<28}" + "".join(f"{m[:9]:>10}" for m in MODES if m not in BENIGN) + f"{'risky':>8}")
    for f in FILES:
        c = by_file[f]
        risky = sum(1 for s in sites if s.file == f and s.risky)
        print(f"{f:<28}" + "".join(f"{c[m]:>10}" for m in MODES if m not in BENIGN) + f"{risky:>8}")
    print()
    for s in sites:
        if mode_filter and mode_filter not in s.modes:
            continue
        if not mode_filter and not s.risky:
            continue
        if md:
            print(f"- `{s.file}:{s.line}` **{','.join(m for m in s.modes if m not in BENIGN) or '-'}** "
                  f"({s.note}) `{s.snippet.replace('`', chr(39))}`")
        else:
            print(f"{s.file}:{s.line}  [{','.join(s.modes)}]  {s.note}\n    {s.snippet}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode")
    ap.add_argument("--md", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(self_test())
    report(scan_all(), a.mode, a.md)


if __name__ == "__main__":
    main()
