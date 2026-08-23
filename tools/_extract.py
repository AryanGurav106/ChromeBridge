"""Pull one function's source out of extension/background.js, reliably.

Every harness in this directory runs the REAL page-side code by slicing it out of
background.js and handing it to page.evaluate. They all did that by counting
braces from the function header — which counts braces inside COMMENTS, STRINGS
and REGEX LITERALS too.

That is a silent failure. A single `{` in a prose comment ("innerText emits
`function greet() {`") makes the slice run past the end of the function and drag
in whatever follows, and the test then dies inside unrelated code with an error
like `ReferenceError: chrome is not defined` — pointing at the wrong file, the
wrong function, and the wrong bug. It cost a debugging cycle before it was
recognised as an extraction artefact rather than a collector defect.

This scanner skips comments, strings, template literals and regex literals, so
only real code braces count. `verify=True` additionally parses the result with
Node so a bad slice fails loudly, here, with a useful message.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

_REGEX_PRECEDERS = set("(,=:[!&|?{};+-*%~^<>\n")
_KEYWORD_PRECEDERS = ("return", "typeof", "case", "in", "of", "delete", "void", "instanceof", "new", "do", "else")


def _regex_allowed(src: str, i: int) -> bool:
    """Is the '/' at src[i] the start of a regex literal rather than division?"""
    j = i - 1
    while j >= 0 and src[j] in " \t":
        j -= 1
    if j < 0:
        return True
    if src[j] in _REGEX_PRECEDERS:
        return True
    k = j
    while k >= 0 and (src[k].isalpha() or src[k] == "_"):
        k -= 1
    return src[k + 1:j + 1] in _KEYWORD_PRECEDERS


def extract(name: str, src: str, verify: bool = False) -> str:
    marker = f"function {name}("
    i = src.index(marker)
    # KEEP A LEADING `async`. The slice started at "function", so an async function
    # came back without its modifier and every `await` inside it became a syntax
    # error — which made async page functions untestable by every suite that uses
    # this helper, and looked like a bug in the function rather than in the slicer.
    # Found when the WebMCP probes (_pageToolsPage / _callPageToolPage) could not be
    # extracted at all.
    _pre = src.rfind("async", max(0, i - 6), i)
    if _pre != -1 and src[_pre + len("async"):i].strip() == "":
        i = _pre
    j = src.index("{", i) + 1
    depth = 1
    n = len(src)
    while depth and j < n:
        c = src[j]
        two = src[j:j + 2]
        if two == "//":
            j = src.find("\n", j)
            if j < 0:
                break
            continue
        if two == "/*":
            j = src.find("*/", j)
            if j < 0:
                break
            j += 2
            continue
        if c in "'\"`":
            q, j = c, j + 1
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == q:
                    j += 1
                    break
                # `${...}` in a template literal is real code, but nothing in
                # this codebase nests braces inside one, so skipping the whole
                # literal stays correct and keeps the scanner simple.
                j += 1
            continue
        if c == "/" and _regex_allowed(src, j):
            j += 1
            in_class = False
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == "[":
                    in_class = True
                elif src[j] == "]":
                    in_class = False
                elif src[j] == "/" and not in_class:
                    j += 1
                    break
                elif src[j] == "\n":
                    break          # not a regex after all; bail rather than run away
                j += 1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        j += 1
    out = src[i:j]
    if depth:
        raise ValueError(f"extract({name!r}): unbalanced braces — reached end of file")
    if verify:
        check_parses(out, name)
    return out


def check_parses(code: str, name: str = "") -> None:
    """Parse the slice with Node so a bad extraction fails here, not in the page."""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write("(function(){\n" + code + "\n})\n")
        path = f.name
    try:
        r = subprocess.run(["node", "--check", path], capture_output=True, text=True)
        if r.returncode != 0:
            raise ValueError(f"extract({name!r}) produced unparsable JS:\n{r.stderr[:400]}")
    except FileNotFoundError:
        pass          # node not installed — skip verification rather than fail the suite
    finally:
        Path(path).unlink(missing_ok=True)


def live_mask(src: str) -> bytearray:
    """One byte per character: 1 where the character is LIVE, 0 only inside a comment.

    `code_mask` answers "is this executable syntax", which is the right question
    for the pattern auditor (a legend sentence must not be reported as a regex).
    It is the WRONG question for asking whether a signature still exists, because
    a hardcoded CSS selector — `'.CodeMirror, .cm-editor, .monaco-editor'` — lives
    in a string literal and IS the signature. Masking strings out reported eight
    of ten ablation entries as deleted when only two were.

    So: strings and regex literals count, comments do not. The distinction that
    matters here is live-vs-dead, not code-vs-data.
    """
    mask = bytearray(b"\x01") * len(src)
    for j, live in enumerate(code_mask(src, strings_are_code=True)):
        mask[j] = live
    return mask


def code_mask(src: str, strings_are_code: bool = False) -> bytearray:
    """One byte per character: 1 where it is real JS CODE, 0 in a comment or string.

    With `strings_are_code=True` only comments are masked out — see `live_mask`,
    which is the caller that wants that and explains why.

    Lifted out of `extract`'s scanner so `audit_patterns.py` can share it instead of
    approximating with "does the line START with //". That approximation produced two
    standing false positives every run — a TRAILING comment (`codeEditor, //
    CodeMirror/Monaco/Ace host` was reported as a framework-name regex `/ CodeMirror/`)
    and a user-facing legend string (`L.push(`... / <select> — a DROPDOWN ...`)` was
    reported as an html-regex). A pattern auditor whose risky categories are a third
    noise costs review attention on every run, which is how a real finding gets
    skimmed past.

    Regex LITERALS count as code, because they are exactly what the auditor is
    looking for. Template-literal `${...}` interpolations are treated as string,
    matching `extract`'s own simplification (nothing here nests braces in one).
    """
    n = len(src)
    mask = bytearray(b"\x01") * n
    j = 0
    while j < n:
        c = src[j]
        two = src[j:j + 2]
        if two == "//":
            end = src.find("\n", j)
            if end < 0:
                end = n
            for k in range(j, end):
                mask[k] = 0
            j = end
            continue
        if two == "/*":
            end = src.find("*/", j)
            end = n if end < 0 else end + 2
            for k in range(j, end):
                mask[k] = 0
            j = end
            continue
        if c in "'\"`":
            q = c
            k = j + 1
            while k < n:
                if src[k] == "\\":
                    k += 2
                    continue
                if src[k] == q:
                    k += 1
                    break
                k += 1
            if not strings_are_code:
                for x in range(j, min(k, n)):
                    mask[x] = 0
            j = k
            continue
        if c == "/" and _regex_allowed(src, j):
            k = j + 1
            in_class = False
            while k < n:
                if src[k] == "\\":
                    k += 2
                    continue
                if src[k] == "[":
                    in_class = True
                elif src[k] == "]":
                    in_class = False
                elif src[k] == "/" and not in_class:
                    k += 1
                    break
                elif src[k] == "\n":
                    break
                k += 1
            j = k          # regex literals stay marked as code
            continue
        j += 1
    return mask
