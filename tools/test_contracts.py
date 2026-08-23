"""test_contracts.py — assert the constants duplicated across process boundaries agree.

Run:  .venv\\Scripts\\python.exe tools\\test_contracts.py

ChromeBridge spans three processes that cannot import each other: the Python MCP
server, the extension's service worker, and the side panel. Four values therefore
exist in more than one file, kept in sync by nothing but a comment:

    PORT_RANGE_SPAN   core/bridge/server.py, extension/background.js, extension/panel.js
    PROTOCOL_VERSION  core/bridge/server.py, extension/background.js
    version           extension/manifest.json, pyproject.toml, SERVER_VERSION in server.py

Each mismatch fails in a way that looks like something else:

  - a narrower span in the extension strands every session the server places on a
    port the extension never probes; the panel just says it cannot reach the bridge.
  - a PROTOCOL_VERSION skew closes every connection with 4001 — which is the
    mechanism working correctly, reporting a bug that is ours, not the user's.
  - a version skew is cosmetic but it is what a human reads first when diagnosing
    the other two, so a wrong one sends them down the wrong path.

Parsed out of the source text rather than imported, because two of the three files
are JavaScript. That is deliberate: the point is to compare what each process will
actually load, not what a Python-side constant says they should.
"""

import json
import os
import re
import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _extract import code_mask, extract as _shared_extract  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

passed = 0
failed = 0
failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {name}" + (f"  - {detail}" if detail else ""))
    else:
        failed += 1
        failures.append(name)
        print(f"  FAIL  {name}" + (f"  - {detail}" if detail else ""))


def read(rel: str) -> str:
    with open(os.path.join(ROOT, rel), "r", encoding="utf-8") as fh:
        return fh.read()


def grab(rel: str, pattern: str) -> str | None:
    """First capture group of `pattern` in `rel`, or None."""
    m = re.search(pattern, read(rel), re.M)
    return m.group(1) if m else None


def main() -> int:
    # ---- PORT_RANGE_SPAN ---------------------------------------------------
    spans = {
        "core/bridge/server.py": grab("core/bridge/server.py", r"^PORT_RANGE_SPAN\s*=\s*(\d+)"),
        "extension/background.js": grab("extension/background.js", r"^const PORT_RANGE_SPAN\s*=\s*(\d+)"),
        "extension/panel.js": grab("extension/panel.js", r"^const PORT_RANGE_SPAN\s*=\s*(\d+)"),
    }
    for path, val in spans.items():
        check(f"C1 PORT_RANGE_SPAN is present in {path}", val is not None,
              "not found — did the constant get renamed?" if val is None else f"= {val}")
    if all(v is not None for v in spans.values()):
        check("C2 all three PORT_RANGE_SPAN values agree",
              len(set(spans.values())) == 1, ", ".join(f"{k.split('/')[-1]}={v}" for k, v in spans.items()))

    # ---- PROTOCOL_VERSION --------------------------------------------------
    protos = {
        "core/bridge/server.py": grab("core/bridge/server.py", r"^PROTOCOL_VERSION\s*=\s*(\d+)"),
        "extension/background.js": grab("extension/background.js", r"^const PROTOCOL_VERSION\s*=\s*(\d+)"),
    }
    for path, val in protos.items():
        check(f"C3 PROTOCOL_VERSION is present in {path}", val is not None,
              "not found" if val is None else f"= {val}")
    if all(v is not None for v in protos.values()):
        check("C4 server and extension PROTOCOL_VERSION agree "
              "(a skew closes every connection with 4001)",
              len(set(protos.values())) == 1,
              ", ".join(f"{k.split('/')[-1]}={v}" for k, v in protos.items()))

    # ---- version -----------------------------------------------------------
    manifest = json.loads(read("extension/manifest.json"))
    versions = {
        "extension/manifest.json": manifest.get("version"),
        "pyproject.toml": grab("pyproject.toml", r'^version\s*=\s*"([^"]+)"'),
        "core/bridge/server.py": grab("core/bridge/server.py", r'^SERVER_VERSION\s*=\s*"([^"]+)"'),
    }
    for path, val in versions.items():
        check(f"C5 version is present in {path}", bool(val),
              "not found" if not val else f"= {val}")
    if all(versions.values()):
        check("C6 manifest, pyproject and SERVER_VERSION agree",
              len(set(versions.values())) == 1,
              ", ".join(f"{k.split('/')[-1]}={v}" for k, v in versions.items()))

    # ---- the handshake field names both sides spell out --------------------
    # The wire contract is four keys. A rename on one side is a 4001 storm at
    # best and a silent mis-parse at worst, so assert both halves still say them.
    sw = read("extension/background.js")
    py = read("core/bridge/server.py")
    for key in ("hello", "protocol", "client", "version"):
        check(f"C7 hello key '{key}' appears in both halves",
              f'"{key}"' in sw or f"'{key}'" in sw or f"{key}:" in sw,
              "extension side")
    check("C8 server reads the same hello keys",
          all(f'"{k}"' in py or f"'{k}'" in py for k in ("hello", "protocol")),
          "server side")
    check("C9 protocol-mismatch close code 4001 is used by BOTH halves "
          "(the panel must recognise what the server sends)",
          "4001" in py and "4001" in read("extension/panel.js"))

    # C10: a tool parameter must not be NARROWER than the way clients call it.
    # `call_page_tool(args=...)` was declared `Optional[str]`, which looks right and
    # fails on first use: an MCP client handed '{"instrument":"..."}' parses it into
    # an object before validation, so the natural call is rejected with a pydantic
    # string_type error that mentions nothing about tools. The extension already
    # accepted either shape (test_ops.js pins that); only the server schema was
    # narrow. Checked statically because the failure is in the SIGNATURE, which is
    # what a client sees, not in any code path a runtime call would reach.
    _srv = read("mcp_server.py")   # NOT `py`, which is core/bridge/server.py
    check("C10 call_page_tool accepts args as an object OR a string, and normalises",
          "Optional[Union[str, dict]]" in _srv
          and "json.dumps(args, ensure_ascii=False)" in _srv,
          "args annotation is Optional[Union[str, dict]] with a json.dumps fallback")

    # ------------------------------------------------------------------
    # C11: THE INJECTION BOUNDARY. `runInTab(tabId, fn)` hands `fn` to
    # chrome.scripting.executeScript({func}), which stringifies THAT FUNCTION AND
    # NOTHING ELSE. So any identifier in `fn` that resolves to a top-level sibling
    # is a free variable that does not exist in the page: the call throws
    # ReferenceError, and because these functions are written defensively the throw
    # lands in a try/catch and the result is a plausible-looking zero.
    #
    # This is the most expensive failure shape in the project, because it is silent
    # in BOTH directions. `_readinessPage` called two top-level helpers, so its
    # three DOM signals (images-loading, aria-busy, progressbar) returned 0 on every
    # page for as long as they existed, and read_page emitted no readiness banner on
    # a page that plainly held an aria-busy region and a visible progressbar — while
    # tools/test_readiness.py reported 10/10, because it PREPENDED the helpers before
    # injecting and so tested an environment production never has.
    #
    # Checked mechanically rather than by reading: the same class was documented in
    # CLAUDE.md #25, a page-context copy was already in the codebase at the
    # `dup:deepall` site, and it still recurred. A comment is not a guard.
    _bg = read("extension/background.js")

    def _code_only(s):
        # THE MASK MUST BE COMPUTED FOR THE STRING BEING MASKED. The first version
        # closed over one mask built from the whole file and applied it to each
        # extracted slice, so the indices referred to unrelated offsets: comments
        # were treated as code and code as comment, and the check reported a free
        # reference in a function that had none. Which is this very bug class — a
        # helper reading state that is not in scope for its input — caught by
        # reproducing the check standalone rather than by reading it.
        m = code_mask(s)
        return "".join(c if m[i] else " " for i, c in enumerate(s))

    _bg_code = _code_only(_bg)
    _toplevel = set(re.findall(r"^function\s+([A-Za-z_$][\w$]*)", _bg_code, re.M))
    _injected = set(re.findall(r"runInTab\(\s*[^,]+,\s*([A-Za-z_$][\w$]*)", _bg_code))
    _bad = []
    for _fn in sorted(_injected):
        if _fn not in _toplevel:
            continue                      # a parameter or local; nothing to check
        try:
            _src = _shared_extract(_fn, _bg, verify=False)
        except Exception as e:
            _bad.append(f"{_fn}: could not extract ({type(e).__name__})")
            continue
        _body = _code_only(_src)
        # Names DECLARED inside the function are fine however they are spelled.
        _local = set(re.findall(r"(?:const|let|var|function)\s+([A-Za-z_$][\w$]*)", _body))
        for _ref in sorted(set(re.findall(r"\b([A-Za-z_$][\w$]*)\s*\(", _body))):
            if _ref in _toplevel and _ref != _fn and _ref not in _local:
                _bad.append(f"{_fn} calls top-level {_ref}()")
    # C12: THE LISTING'S BOUNDARY LINE IS A CROSS-PROCESS STRING CONTRACT. The
    # server splits a listing into preamble and rows by looking for the line that
    # introduces the actionable rows. It searched for "Act on an element" while the
    # extension emits "Act on a row by its ref_N:", so `_content_rows` never started
    # collecting, returned [], and the guard that stores a baseline never ran —
    # read_page(delta=true) reported "first read of this tab" forever and the whole
    # feature was dead. It failed SAFE (honest notice, full listing), which is
    # exactly why no test and no agent caught it.
    check("C12 the server's listing-boundary marker is a prefix of the line the "
          "extension actually emits",
          (lambda m: bool(m) and m.group(1) in _bg)(
              re.search(r'^_ACT_LINE\s*=\s*"([^"]+)"', _srv, re.M)),
          (lambda m: (f"server={m.group(1)!r} present in background.js"
                      if m and m.group(1) in _bg else
                      f"server={m.group(1)!r} NOT emitted by the extension" if m
                      else "_ACT_LINE not found in mcp_server.py"))(
              re.search(r'^_ACT_LINE\s*=\s*"([^"]+)"', _srv, re.M)))

    check("C11 every function injected via runInTab is self-contained "
          "(executeScript stringifies only that function)",
          not _bad,
          f"{len(_injected)} injected function(s) checked"
          + (f" — FREE REFERENCES: {'; '.join(_bad[:6])}" if _bad else ", all self-contained"))

    print(f"\n{passed} passed, {failed} failed, {passed + failed} total checks")
    if failures:
        print("failing: " + ", ".join(failures))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
