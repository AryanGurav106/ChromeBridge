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
import shutil
import subprocess
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

    # C13: THE COLLECTOR'S DEFAULT FORMAT MUST BE THE PRODUCT'S DEFAULT FORMAT.
    # `read_page(format="tree")` is the shipped default, but the collector read
    # `format === 'tree'`, so an OMITTED format silently produced the FLAT listing —
    # a parameter whose omission changes the output and cannot fail. It has cost four
    # measurements and fixtures so far: #29's corpus token figures all described the
    # flat listing while the tree was shipping, and RG10 (twice) plus TB12 passed
    # against empty sets this session because they read a flat listing while checking
    # a tree-only property. Same shape as the injection boundary C11 guards: silent,
    # unfailable, and only findable by noticing the output was about something else.
    # Omission now means the default; `'flat'` is the thing a caller must ask for.
    _srv_fmt = re.search(r'\]\s*=\s*"(tree|flat)",\s*geometry', _srv)
    _coll_default_is_tree = "const TREEFMT = format !== 'flat';" in _bg
    check("C13 an omitted format gives the collector the same default the tool "
          "advertises, so a caller that omits it cannot get the other format",
          bool(_srv_fmt) and _srv_fmt.group(1) == "tree" and _coll_default_is_tree,
          f"server default={_srv_fmt.group(1) if _srv_fmt else 'NOT FOUND'!r}, "
          f"collector treats omitted as tree={_coll_default_is_tree}")

    # C14: A FIXTURE THAT SILENTLY LOADS NOTHING. Playwright's add_init_script only
    # affects documents created AFTER the call, and page.set_content reuses the
    # existing about:blank — so `add_init_script(listener_tag.js)` immediately
    # followed by `set_content` runs the tagger on nothing, and every check on that
    # page tests an untagged document while staying green. Found while adding S14:
    # the attachShadow wrap read as broken when it was the harness that was, and the
    # audit then found ELEVEN fixture pages across two suites in that state, some
    # predating this change. Same class as #29's three vacuous fixtures, and the
    # reason that lesson is now a test rather than a paragraph.
    _fx_bad = []
    _tools_dir = _Path(ROOT) / "tools"
    for _f in sorted(_tools_dir.glob("test_*.py")):
        _txt = _f.read_text(encoding="utf-8")
        for _m in re.finditer(r"await (\w+)\.add_init_script\([^\n]*listener_tag\.js[^\n]*\)\n"
                              r"(?P<rest>(?:[ \t]*#[^\n]*\n)*)[ \t]*await (\w+)\.(\w+)\(", _txt):
            if _m.group(1) == _m.group(3) and _m.group(4) == "set_content":
                _fx_bad.append(f"{_f.name}:{_txt[:_m.start()].count(chr(10)) + 1} ({_m.group(1)})")
    check("C14 no fixture injects listener_tag.js and then calls set_content without "
          "a navigation (the init script would never run)",
          not _fx_bad,
          f"{len(_fx_bad)} vacuous fixture page(s)"
          + (f": {'; '.join(_fx_bad[:6])}" if _fx_bad else " — all fixtures navigate first"))

    # C15: A NOTE MAY NOT PICK A CAUSE FOR THE READER. Three separate incidents now
    # share one shape — #14's stale-ref message asserting "a navigation invalidated
    # your refs" (BBC hit it with no navigation), #23's cross-extension message
    # asserting a recovery was impossible that an agent had just performed, and the
    # aria-hidden note concluding "most likely a CLOSED menu/panel" while its own
    # output listed an open role=menu. Each read as considered rather than guessed,
    # which is what makes the class expensive.
    # The rule the codebase already states: an explanatory note gives the FACT and
    # enumerates causes; it never selects one. This flags the hedged-assertion
    # vocabulary inside emitted strings, which is how all three were phrased.
    # SCOPE IS LOAD-BEARING, AND IT WAS TOO NARROW. This scanned only
    # background.js, while mcp_server.py and core/flows/*.py now emit a great
    # deal of agent-facing prose — the resolver's refusals, the precondition
    # message, the count-grew note, find's miss path. A tripwire that covers
    # part of a surface also asserts the rest is fine, which is #66's finding:
    # audit_patterns.py printed "253 sites across 4 files" while scanning three,
    # and had never looked at panel.js or core/flows at all.
    _NOTE_FILES = ["extension/background.js", "mcp_server.py",
                   "core/flows/runner.py", "core/flows/recorder.py",
                   "core/flows/descriptor.py"]
    def _scan_hedges(_label, _src, _mask, _out):
        for _m in re.finditer(
                r"[`\"'][^`\"'\n]{0,400}?(most likely|probably|this is because|usually means)"
                r"[^`\"'\n]{0,400}?[`\"']", _src, re.I):
            # Only STRING literals matter — prose in a comment is the reasoning,
            # not output.
            if _mask[_m.start()]:
                continue
            # THE WINDOW MUST SPAN THE WHOLE MESSAGE, not one literal. These notes
            # are built by concatenating several string chunks, so the hedge and
            # the words that justify it routinely sit in different literals — the
            # first version matched only the chunk containing "probably" and
            # flagged a note whose very next line says "heuristic".
            _seg = _src[max(0, _m.start() - 200):_m.end() + 400]
            # An enumeration is the sanctioned form: naming several causes is not
            # picking one.
            if re.search(r"\(a\)|\(b\)|either|or a |one of|each do it|which applies",
                         _seg, re.I):
                continue
            # ...and so is a note that DECLARES itself a judgement. "PROBABLY
            # DECORATION — a size/shape/label heuristic (never a spec rule) judged
            # them non-content" is the honest form this rule exists to encourage,
            # not a violation of it: the hedge is the category name and the note
            # says what made the guess. Flagging it would push the codebase toward
            # removing the word rather than the guess.
            if re.search(r"heuristic|never a spec rule", _seg, re.I):
                continue
            _out.append(f"{_label}:{_src[:_m.start()].count(chr(10)) + 1}")

    _note_bad = []
    for _nf in _NOTE_FILES:
        _nsrc = read(_nf)
        _scan_hedges(_nf.split("/")[-1], _nsrc, code_mask(_nsrc), _note_bad)

    check("C15 no emitted note asserts a single cause it cannot know "
          "(state the fact, enumerate the causes)",
          not _note_bad,
          f"{len(_note_bad)} hedged assertion(s)"
          + (f": {'; '.join(_note_bad[:6])}" if _note_bad
             else f" — {len(_NOTE_FILES)} files scanned, all notes enumerate or state facts"))

    # AND THE DETECTOR MUST BE SHOWN TO FIRE on the NEW files, not only on the
    # one it was written against — a scan that silently matches nothing in
    # core/flows would look identical to one that found them clean.
    _planted = 'raise Unresolved("the element is gone, this is because the page navigated")'
    _pb = []
    _scan_hedges("planted", _planted, code_mask(_planted), _pb)
    check("C15b ...and the scanner provably fires on a planted hedge in the "
          "python emitted-string shape (not just background.js's template literals)",
          len(_pb) == 1, f"{len(_pb)} hit(s) on the planted violation")

    # C16 scans the EXTENSION specifically — op names are its vocabulary. (C15
    # above now scans five files and no longer leaves a module-level
    # `_notes_src` behind, so this names its own source.)
    _notes_src = read("extension/background.js")

    # C16: AN AGENT-FACING MESSAGE MAY ONLY NAME TOOLS THE AGENT HAS. The extension
    # speaks in OP names (`get_dom_fields`, `get_interactive_elements`); the agent has
    # MCP TOOL names (`read_page`, `find`). They are different vocabularies and only
    # the server knows the mapping, so an op name in a message is an instruction the
    # reader cannot follow. Found live: fill_form's submit result said "re-observe with
    # get_dom_fields", which is not a tool — the agent had to guess `read_page`.
    # Ops that ARE also tool names (navigate, computer, fill_form…) are fine.
    _ops = set(re.findall(r'case\s+"([a-z_0-9]+)"\s*:', _notes_src))
    _tools = set(re.findall(r"^async def ([a-z_0-9]+)\(", read("mcp_server.py"), re.M))
    # TWO NARROWINGS, both because the first version flagged 38 sites of ordinary
    # English. `click` and `screenshot` are op names AND normal words, so "nothing was
    # clicked" and "take a screenshot" tripped it — and telling the codebase to stop
    # using those words is worse than the bug. So:
    #   - only SNAKE_CASE ops (an underscore makes it unambiguously an identifier;
    #     a single English word cannot be separated from prose mechanically), and
    #   - only in an INSTRUCTION context ("re-observe with X", "call X"), which is
    #     what makes it a direction the reader cannot follow rather than a mention.
    # `get_dom_fields` — the live leak — satisfies both, which is the test.
    # SCAN THE SOURCE, NOT STRING LITERALS. The first version windowed on quoted
    # regions and its planted-leak control DID NOT FIRE — the real message is a
    # TEMPLATE literal carrying `${...}` and embedded quotes, so the window either
    # terminated early or started on a delimiter the mask calls code. A tripwire that
    # cannot catch the bug it was written for is worth nothing (#21), and only the
    # control showed it. The instruction phrasing is distinctive enough to scan for
    # directly; the one thing to exclude is a `//` comment, where naming an op is
    # discussion rather than output.
    # THE NAME NEED NOT BE A REAL OP. `get_dom_fields` — the live leak — is not a
    # router case, not a tool, not anything: a phantom. Deriving the candidate set from
    # `case "…"` therefore could NOT catch it, and the planted control said so twice
    # before I stopped assuming and read what the string actually contained. The
    # invariant is about what the READER can act on: an instruction naming a
    # snake_case identifier that is not an MCP tool, whatever it is internally.
    # THREE REFERENCE SHAPES, because the messages use all three and only checking one
    # is how this stayed open. A survey found ZERO bad `name` / name( references — the
    # forms I looked at first — while the live leak was a BARE name after "with", which
    # neither shape matches. Checking all three also guards the case nobody has hit yet:
    # RENAMING a tool silently invalidates every message that names the old one, and
    # `read_page(ledger=true)` / `computer(action="scroll_to")` appear in a lot of them.
    # Restricted to snake_case: `click` and `screenshot` are tool-ish words AND ordinary
    # English, and no mechanical rule separates "take a screenshot" from a reference.
    _NAME = r"([a-z][a-z0-9]*_[a-z0-9_]+)"
    _leaks = []
    for _pat in (re.compile(r"(?:re-observe with|observe with|call|invoke|use)\s+`?" + _NAME + r"\b", re.I),
                 re.compile(r"`" + _NAME + r"`"),
                 re.compile(r"\b" + _NAME + r"\(")):
        for _m in _pat.finditer(_notes_src):
            _ls = _notes_src.rfind("\n", 0, _m.start()) + 1
            if "//" in _notes_src[_ls:_m.start()] or _m.group(1) in _tools:
                continue
            _hit = f"background.js:{_notes_src[:_m.start()].count(chr(10)) + 1} ({_m.group(1)})"
            if _hit not in _leaks:
                _leaks.append(_hit)
    check("C16 no agent-facing message names an internal op that is not an MCP tool",
          not _leaks,
          f"{len(_leaks)} leak(s)" + (f": {'; '.join(_leaks[:5])}" if _leaks
                                      else f" — every instruction names a real tool"))

    # C20: THE SERVER'S OWN INSTRUCTIONS ARE AGENT-FACING TEXT, so C16's rule
    # applies to them with more force, not less: they are read ONCE, before the
    # agent calls anything, and nothing later corrects them. They also name tools
    # explicitly, in a `select:` line whose whole purpose is to be pasted into a
    # ToolSearch call — so a renamed tool turns that line into a request for a
    # phantom, and the agent discovers it by having the call fail.
    #
    # The second half pins WHY the field exists. #45 added it because transcript
    # mining measured 1.24 ToolSearch calls per run (21.8% of turns in the
    # unconfounded group) against a competitor that ships instructions saying to
    # batch them into one. An `instructions=` that survives but loses that sentence
    # is the field still being set and the cost being paid again, which is exactly
    # the silent-no-op shape #30 and #39 both record.
    _srv = read("mcp_server.py")
    _ins_m = re.search(r'FastMCP\([^)]*instructions\s*=\s*(\w+)', _srv)
    _ins = ""
    if _ins_m:
        _lit = re.search(r'^' + _ins_m.group(1) + r'\s*=\s*"""\\?\n(.*?)"""',
                         _srv, re.S | re.M)
        _ins = _lit.group(1) if _lit else ""
    check("C20 the server declares non-empty MCP instructions",
          len(_ins) > 200,
          f"{len(_ins)} chars"
          + ("" if len(_ins) > 200 else " — the only channel read BEFORE the first call"))

    _named = set(re.findall(r"mcp__chromebridge__([a-z_0-9]+)", _ins))
    _ins_bad = sorted(n for n in _named if n not in _tools)
    check("C20b every tool the instructions name is a real tool",
          not _ins_bad,
          f"{len(_named)} named"
          + (f" — PHANTOM: {', '.join(_ins_bad)}" if _ins_bad else ", all resolve"))

    check("C20c the instructions still say to batch ToolSearch into one call",
          "ToolSearch" in _ins and "SINGLE" in _ins.upper(),
          "the measured 21.8%-of-turns sink is still addressed"
          if "ToolSearch" in _ins else "the ToolSearch guidance is GONE")

    # C20d: THE ONE-TURN START LIVES IN THE TOOL DESCRIPTION, NOT ONLY IN
    # `instructions=`. The two channels arrive on different schedules and under
    # different caches, which is the real reason to use both:
    #   - `instructions=` is delivered when the server's tools come into play
    #     (a subagent that loads a chromebridge tool gets it as an addedBlocks
    #     attachment; one that loads none gets nothing).
    #   - a tool DESCRIPTION travels with the schema -- and a schema already
    #     loaded in a parent session is CACHED, so a `/mcp` reconnect did not
    #     refresh it for a subagent spawned afterwards. Measured by reading the
    #     old text back out of that subagent's transcript.
    # NOTE the justification first recorded here was wrong and is corrected in
    # #46: it claimed `instructions=` reaches a subagent zero times, on a scan of
    # 512 transcripts that all PREDATED the field existing. The conclusion (put it
    # in both) survived; the evidence for it did not.
    _bb = re.search(r"async def browser_batch\(.*?\n    \"\"\"(.*?)\"\"\"",
                    _srv, re.S)
    _bbdoc = _bb.group(1) if _bb else ""
    check("C20d the one-turn start is in browser_batch's DESCRIPTION, "
          "not only in the server instructions",
          "START IN ONE TURN" in _bbdoc and "tabs_create_mcp" in _bbdoc,
          "in both channels, which cache and arrive differently"
          if "START IN ONE TURN" in _bbdoc else
          "MISSING from the only channel a subagent reads")

    # C22: A STALE SERVER IS INVISIBLE FROM INSIDE, so it has to be reported.
    # The MCP server is a long-lived stdio process that imports mcp_server.py
    # and core/* ONCE, at connect time; editing them changes nothing until the
    # client reconnects, and the running process answers NORMALLY the whole
    # time. #59 learned that by inspecting a saved artefact (a flow file
    # silently missing a field the newer recorder writes) at a cost of three
    # reconnects, and #61 paid three more. Driven, not grepped -- the helper is
    # at module level precisely so this can call it (#30 found `_content_rows`
    # untestable for its whole life because it was nested inside its tool).
    import importlib.util as _ilu, os as _os, time as _time
    _spec = _ilu.spec_from_file_location("_ms_stale", _Path(__file__).resolve().parents[1] / "mcp_server.py")
    _ms = _ilu.module_from_spec(_spec)
    try:
        _spec.loader.exec_module(_ms)
        _fresh = _ms._changed_since_start()
        check("C22 CONTROL: a server importing the code on disk reports NOTHING "
              "stale — a notice that fired every run would be the noise #15 priced",
              _fresh == [], f"reported {_fresh[:4]}")
        _victim = _Path(__file__).resolve().parents[1] / "core" / "flows" / "runner.py"
        _was = _victim.stat().st_mtime
        try:
            _os.utime(_victim, (_time.time(), _time.time()))
            _after = _ms._changed_since_start()
            check("C22b ...and an edit AFTER the import is named, so the one "
                  "failure mode nothing else can see becomes a read",
                  "core/flows/runner.py" in _after, f"reported {_after[:4]}")
        finally:
            _os.utime(_victim, (_was, _was))
    except Exception as _e:
        check("C22 the staleness probe runs", False, f"{type(_e).__name__}: {_e}")

    # C23: NO AGENT-FACING json.dumps MAY ESCAPE NON-ASCII. Four times now:
    # #11(d) fixed `find`, #42 fixed `query_elements`, and #63 found `get_url`
    # printing a Japanese title as \uXXXX -- in a function I had edited two
    # hours earlier, with the rule written in `_q`'s docstring 600 lines above
    # it. A rule living in prose is a rule a human has to remember; this is the
    # tripwire that should have existed after the first one.
    _ms = (_Path(__file__).resolve().parents[1] / "mcp_server.py").read_text(encoding="utf-8")
    _bare = []
    for _m in re.finditer(r"json\.dumps\(", _ms):
        _seg = _ms[_m.start(): _m.start() + 220]
        _line = _ms[:_m.start()].count("\n") + 1
        if "ensure_ascii" in _seg.split("\n")[0] or "ensure_ascii" in _seg[:120]:
            continue
        _bare.append(_line)
    check("C23 every json.dumps in mcp_server.py passes ensure_ascii=False — "
          "escaping non-Latin text to \\uXXXX has shipped four times",
          not _bare, f"bare json.dumps at line(s) {_bare[:8]}" if _bare
          else f"all {_ms.count('json.dumps(')} call(s) explicit")

    # C24: A COUNT IS NOT AN INVENTORY. I inserted a module-level helper
    # between `@mcp.tool()` and `async def sw_info(`, so the decorator bound to
    # the HELPER: `_changed_since_start` became a public tool and `sw_info`
    # vanished from the surface -- while the total stayed at 31, so the
    # over-the-wire count smoke test that CLAUDE.md calls "the only way to
    # catch a tool that fails to register" passed. A swap is invisible to a
    # count. Found only because the MCP client announced the change.
    #
    # The invariant is that a decorated name is never private, which catches
    # the general case (a decorator that drifted onto the wrong function) and
    # names the offender instead of reporting a number that looks right.
    _bad_tool = []
    for _m in re.finditer(r"@mcp\.tool\(\)\s*\n\s*(?:async\s+)?def\s+(\w+)", _ms):
        if _m.group(1).startswith("_"):
            _bad_tool.append(_m.group(1))
    _decorated = re.findall(r"@mcp\.tool\(\)\s*\n\s*(?:async\s+)?def\s+(\w+)", _ms)
    check("C24 no @mcp.tool() is bound to a PRIVATE function — a helper that "
          "lands between the decorator and its tool swaps them, and the tool "
          "count stays identical",
          not _bad_tool, f"PUBLISHED AS TOOLS: {_bad_tool}" if _bad_tool
          else f"{len(_decorated)} decorated, none private")
    check("C24b ...and the tools CLAUDE.md names as diagnostics are still "
          "registered, because a swap removes one as silently as it adds one",
          {"sw_info", "debug_targets", "get_url"} <= set(_decorated),
          f"missing: {sorted({'sw_info', 'debug_targets', 'get_url'} - set(_decorated))}")

    # ---- C27/C27b: THE README'S TOOL TABLE IS THE FRONT DOOR, and it had drifted
    # by SEVEN tools — it advertised 24 while the server served 31, with the whole
    # flow feature absent from a table it should have been in for six entries.
    # Same failure as C16 (an agent-facing message naming a tool that does not
    # exist) and C20b (the instructions naming one), one audience over: a reader
    # deciding whether this project does what they need. Both directions matter —
    # a MISSING tool is a capability nobody discovers (#26: a capability the agent
    # cannot find is not a capability), and a PHANTOM one is a promise the clone
    # will not keep.
    _rd = read("README.md")
    # ANCHORED ON THE HEADING, not on a sentence. The first version sliced
    # between the literal "| **Tabs** |" and "Three of those are" — both of
    # which moved the first time the README was restructured, and the check
    # then reported "the slice is empty" rather than anything about tools. A
    # tripwire that a reasonable rewording disarms is the silent-no-op shape
    # #30 and #39 both record; a section heading is the stable landmark.
    _m = re.search(r"^## What Claude gets\s*$(.*?)^## ", _rd, re.S | re.M)
    _tbl = _m.group(1) if _m else ""
    # Tool names only: the table also back-ticks PARAMETERS (`ref_id`, `detail`)
    # and literal values (`back`, `forward`), which are not tools and must not be
    # reported as phantoms.
    _tbl_named = set(re.findall(r"`([a-z_0-9]+)`", _tbl)) & (set(_decorated) | {"__none__"})
    _tbl_missing = sorted(set(_decorated) - _tbl_named)
    check("C27 the README's tool section names every registered tool",
          bool(_tbl) and not _tbl_missing,
          ("the table markers moved — the slice is empty" if not _tbl
           else f"NOT IN THE README: {', '.join(_tbl_missing)}"))
    # A backticked name in that table is legitimately one of three things: a
    # tool, a PARAMETER of one (`ref_id`, `max_chars`, `detail`), or a literal
    # value a parameter takes (`back`, `forward`). Only the first two can be
    # enumerated mechanically — from the tool SIGNATURES, which is a
    # declaration rather than a list someone maintains — so anything else is
    # reported, and the literals are matched by being a default IN a signature.
    # Deciding "tool or parameter?" by whether the name contains an underscore
    # was the first version and it flagged `ref_id` and `max_chars`: a shape
    # heuristic standing in for a fact that is right there in the source (#27).
    _sig_words = set()
    for _m in re.finditer(r"^async def [a-z_0-9]+\((.*?)\)\s*->", _srv, re.S | re.M):
        _sig_words |= set(re.findall(r"([a-z_0-9]+)", _m.group(1)))
    _tbl_phantom = sorted(set(re.findall(r"`([a-z_0-9]+)`", _tbl))
                          - set(_decorated) - _sig_words)
    check("C27b ...and names no tool that does not exist",
          not _tbl_phantom,
          f"PHANTOM: {', '.join(_tbl_phantom)}" if _tbl_phantom else "")
    # Tolerates markup around the number (`**31 MCP tools.**`), because bolding
    # a figure is not a contract change.
    _claimed = re.search(r"\*{0,2}(\d+)\*{0,2} MCP tools", _rd)
    check("C27c ...and the count it states is the count it serves",
          bool(_claimed) and int(_claimed.group(1)) == len(_decorated),
          f"README says {_claimed.group(1) if _claimed else '?'}, "
          f"server registers {len(_decorated)}")

    # ---- C28: tools/README.md DOCUMENTS EVERY SUITE. That file says of its own
    # tables, in its own words, that `--list` "cannot drift the way the tables
    # below can" — and they had: five suites (batch, contracts, flows, patterns,
    # submit) existed with no row, and the sample run still printed 14 suites /
    # 344 checks against 19 / 1038. Knowing a table drifts and leaving it
    # unchecked is the same posture as a detector that cannot fire (#30/#39).
    # Suite discovery here mirrors run_tests.py's: the filesystem, not a list.
    _suites = {f.stem[len("test_"):] for f in (_Path(ROOT) / "tools").glob("test_*.py")}
    _suites |= {f.stem[len("test_"):] for f in (_Path(ROOT) / "tools").glob("test_*.js")}
    _tr = read("tools/README.md")
    _documented = set(re.findall(r"^\| `([a-z_0-9]+)` \|", _tr, re.M))
    _undoc = sorted(_suites - _documented)
    # ---- C29: NO PRIVATE ORIGIN IN A TRACKED FILE. The flow files recorded
    # against a private staging app are excluded from git on purpose, and the
    # EVAL RESULTS table carried its hostname anyway — three rows of it, in a
    # file nobody thought of as secret-bearing. (This comment named the host
    # when it was written, and the check caught ITSELF on the first run, which
    # is the firing demonstration it needed.) Exclusion protects the artefact
    # you remembered; a check
    # protects the one you did not. Reads the exclude list rather than
    # restating it (#21), so adding a pattern there extends this automatically.
    # READS BOTH SOURCES, and that is load-bearing. The patterns used to live
    # ONLY in .git/info/exclude, which is per-clone and never travels — so the
    # protection existed on exactly one machine, and a collaborator recording
    # against the same app got none of it. They are now in .gitignore as well,
    # which IS version controlled. If this check kept reading only the exclude
    # file it would find no patterns on a fresh clone, derive no hosts, and pass
    # having checked nothing — a detector that cannot fire, which also asserts
    # that nothing is wrong (PRINCIPLES #15, and the exact shape of the drift
    # check in #30 and the --check-only flag in #67).
    _hosts = set()
    _pat_lines = []
    for _src in (_Path(ROOT) / ".git" / "info" / "exclude",
                 _Path(ROOT) / ".gitignore"):
        if _src.exists():
            _pat_lines += _src.read_text(encoding="utf-8").splitlines()
    if True:
        for _ln in _pat_lines:
            _ln = _ln.strip()
            if not _ln or _ln.startswith("#"):
                continue
            if not _ln.startswith("flows/"):   # .gitignore holds unrelated patterns
                continue
            # flows/crm-*.flow.json -> the origin of each excluded flow
            for _fp in sorted((_Path(ROOT)).glob(_ln)):
                try:
                    _o = json.loads(_fp.read_text(encoding="utf-8")).get("origin") or ""
                except Exception:
                    continue
                _h = re.sub(r"^https?://", "", _o).split("/")[0]
                if _h and not _h.startswith("127.") and "localhost" not in _h:
                    _hosts.add(_h)
    _leaks = []
    if _hosts:
        _tracked = subprocess.run(["git", "ls-files"], capture_output=True,
                                  text=True, cwd=str(ROOT)).stdout.split()
        for _rel in _tracked:
            _f = _Path(ROOT) / _rel
            try:
                _txt = _f.read_text(encoding="utf-8")
            except Exception:
                continue
            for _h in _hosts:
                if _h in _txt:
                    _leaks.append(f"{_rel}:{_h}")
    # IT IS INERT ON EVERY MACHINE THAT DOES NOT HOLD THE PRIVATE FLOWS, AND
    # THAT INCLUDES CI. The patterns now travel (.gitignore), but the HOSTS are
    # read out of the excluded flow FILES, which are gitignored and therefore
    # absent from every clone — so a fresh checkout derives zero hosts, scans
    # nothing, and passes. The named failure mode moved one step later rather
    # than being removed.
    #
    # It is NOT fixed by committing a hash of the host: a hash in a public repo
    # confirms a guess cheaply, which trades real privacy for detection on the
    # one machine that already has the better protection. And CI genuinely
    # cannot detect a hostname it is not allowed to know.
    #
    # So the honest shape is: this check protects the RECORDING MACHINE, where
    # a leak can originate, and it must SAY when it is not protecting anything.
    # `C29b` enforces that it is live wherever excluded flows exist, and the
    # INERT detail below is written so `run_tests.py` surfaces it as a warning
    # rather than letting a developer on a fresh clone believe they are covered.
    _inert = not _hosts
    check("C29 no origin of a deliberately-excluded flow appears in a tracked file",
          not _leaks,
          "; ".join(sorted(set(_leaks))[:6]) if _leaks
          else (f"{len(_hosts)} excluded origin(s) checked against the tracked tree"
                if _hosts else
                "C29 INERT: no excluded flow files on this checkout, so zero "
                "origins were derived and NOTHING was scanned. This check "
                "protects the machine that records against a private app; it "
                "cannot protect a clone, because CI is not allowed to know the "
                "hostname it would be looking for."))

    # C29b: WHEREVER THE EXCLUDED FLOWS EXIST, THE CHECK MUST BE LIVE. Without
    # this, the inert state above is indistinguishable from a working one on the
    # machine where a leak can actually originate — and "passes having checked
    # nothing" is the exact failure PRINCIPLES #15 names. The pattern list is
    # read from the same two sources as above, never restated (#21).
    _declared = [l.strip() for l in _pat_lines
                 if l.strip().startswith("flows/") and not l.strip().startswith("#")]
    _present = [f for pat in _declared for f in _Path(ROOT).glob(pat)]
    check("C29b the leak check is LIVE wherever excluded flows exist "
          "(inert is only acceptable when there is genuinely nothing to scan)",
          (not _present) or bool(_hosts),
          f"{len(_present)} excluded flow file(s) present, "
          f"{len(_hosts)} origin(s) derived"
          + ("  -> files exist but NO origin was derived: the derivation is broken"
             if _present and not _hosts else ""))

    check("C28 tools/README.md has a row for every suite on disk",
          not _undoc,
          f"UNDOCUMENTED: {', '.join(_undoc)}" if _undoc
          else f"{len(_suites)} suites, all documented")

    check("C11 every function injected via runInTab is self-contained "
          "(executeScript stringifies only that function)",
          not _bad,
          f"{len(_injected)} injected function(s) checked"
          + (f" — FREE REFERENCES: {'; '.join(_bad[:6])}" if _bad else ", all self-contained"))

    # C17: A FIELD THE EXTENSION COMPUTES AND THE SERVER DOES NOT PRINT IS NOT
    # SHIPPED. Same class as C12 and as #19's "the op router is the untested link":
    # `_searchTextPage` locates each match inside the window it quotes, and for as
    # long as the renderer dropped that number, two matches inside one element came
    # back byte-identical and a live agent read them as one position reported twice.
    # Checked against the real renderer with a hand-built hit, because the defect is
    # entirely in the formatting and a browser is not needed to see it.
    import asyncio as _aio
    sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
    import mcp_server as _ms

    class _FB:
        connected = True

        async def call(self, op, **kw):
            return {"hits": [
                {"match": "SIGQUIT", "context": "SIGQUIT 3 3 SIGUSR1 10 30",
                 "at": 0, "tag": "pre", "ref": "12"},
                {"match": "SIGUSR1", "context": "SIGQUIT 3 3 SIGUSR1 10 30",
                 "at": 12, "tag": "pre", "ref": "12"},
            ], "total": 2, "shown": 2, "scanned": 9}

    _ms.STATE["bridge"] = _FB()
    _sp = _ms.search_page.fn if hasattr(_ms.search_page, "fn") else _ms.search_page
    _out = _aio.run(_sp(pattern="SIGQUIT|SIGUSR1", tabId=1, regex=True))
    _rows = [ln for ln in _out.splitlines() if ln.strip().startswith("<pre")]
    check("C17 two matches quoted from the same window are distinguishable in the "
          "rendered output",
          len(_rows) == 2 and _rows[0] != _rows[1]
          and '"SIGQUIT"@0' in _out and '"SIGUSR1"@12' in _out,
          f"{len(_rows)} row(s); identical={_rows[0] == _rows[1] if len(_rows) == 2 else 'n/a'}")

    # C30/C30b: THE SERVER'S ROW PATTERNS MUST MATCH THE ROW THE EXTENSION EMITS IN
    # THE DEFAULT FORMAT. C12 guards the boundary line that introduces the rows; this
    # guards the rows themselves, and the defect was the same shape one line down.
    # `format` defaults to "tree" (C13, right above) and the tree formatter writes
    # `pad + row`, where pad is the node's depth — but `_ROW_LINE`, `_line_ident` and
    # find's prefix strip were all anchored at `^ref_` with no tolerance for that
    # indent. Consequences, all measured on the DEFAULT format:
    #   * truncation lost elements in silence — a 40-row listing at max_chars=1200
    #     printed 8 rows and no residual clause at all (rule 5), while the flat
    #     listing of the same rows said "32 more element(s) not shown";
    #   * the #13 legend-eviction fallback keys off the same pattern, so a listing
    #     whose legend fills the budget returned ZERO rows where flat returned 6;
    #   * `_line_ident` kept the mmid as part of the identity, so an ordinary
    #     re-render that renumbers refs reported every row as both ADDED and GONE —
    #     precisely the trap that function's docstring exists to prevent.
    # Built from what background.js really does rather than from a row typed here:
    # the indent is confirmed by the `pad + ` push, and the prefix by the formatter's
    # own `ref_${e.mmid} | ` template.
    _emits_pad = bool(re.search(r"out\.push\(\s*pad\s*\+", _bg))
    _emits_ref = bool(re.search(r"return\s*`ref_\$\{e\.mmid\}\s*\|\s*", _bg))
    _indented = '  ref_42 | a "Headline" href="/x"'
    check("C30 the server's row pattern matches an INDENTED row, which is what the "
          "default tree format emits",
          _emits_pad and _emits_ref
          and bool(_ms._ROW_LINE.match(_indented))
          and _ms._line_ident(_indented) == 'a "Headline" href="/x"',
          f"extension indents={_emits_pad} emits ref_={_emits_ref}; "
          f"_ROW_LINE={bool(_ms._ROW_LINE.match(_indented))}; "
          f"_line_ident={_ms._line_ident(_indented)!r}")

    # C30b: find reuses the collector's own rendered row (`line`) so the two tools
    # cannot drift — then stripped a `mmid=N | ` prefix the collector has not written
    # since the listing moved to ref_N, printing the ref and the tag TWICE:
    #     ref_12  [a]  ref_12 | a "Login" href="/login"
    # NO fixture ever set `line`, so that whole path was unreachable from the suite
    # and shipped inert behind 51 green find checks. This one sets it.
    class _FBL:
        connected = True

        async def call(self, op, **kw):
            if op == "get_interactive_elements" and not kw.get("structured"):
                return ""
            return [dict(mmid="12", tag="a", role=None, label="Login", name="Login",
                         value="", placeholder="", text="", near="", w=100, h=20, y=0,
                         line='ref_12 | a "Login" href="/login"')]

    _ms.STATE["bridge"] = _FBL()
    _f = _ms.find.fn if hasattr(_ms.find, "fn") else _ms.find
    _row = [ln for ln in _aio.run(_f(query="login", tabId=1)).splitlines()
            if "ref_12" in ln]
    check("C30b find strips the ref prefix the collector actually writes, so a "
          "reused row does not print the ref and the tag twice",
          len(_row) == 1 and _row[0].count("ref_12") == 1
          and _row[0].count("[a]") == 1 and ' | a "Login"' not in _row[0],
          _row[0].strip() if _row else "no row")

    # C18/C19: query_elements' two silences. An element with NO text rendered
    # IDENTICALLY to a text-extraction failure (live on nginx, whose <h1> really is
    # empty because the visible heading is an <h2>) — correct, indistinguishable, and
    # it cost a third batch to confirm another way. And a zero-result asserted
    # "nothing on the page has that shape right now", a fact about the PAGE that a
    # query of the rendered document at one instant cannot establish.
    class _FBQ:
        connected = True

        def __init__(self, payload):
            self.payload = payload

        async def call(self, op, **kw):
            if op == "page_readiness":
                return ""
            return self.payload

    _qe = _ms.query_elements.fn if hasattr(_ms.query_elements, "fn") else _ms.query_elements

    _ms.STATE["bridge"] = _FBQ({"rows": [{"ref": "9", "tag": "h1", "text": ""}],
                                "total": 1})
    _out = _aio.run(_qe(selector="h1", tabId=1))
    check("C18 an element with no text SAYS so, instead of rendering like a failed read",
          "(no text)" in _out, _out.replace("\n", " ")[:120])

    _ms.STATE["bridge"] = _FBQ({"rows": [], "total": 0})
    _out = _aio.run(_qe(selector=".nope", tabId=1))
    check("C19 a zero-result states the MISS and enumerates causes, rather than "
          "asserting a fact about the page it cannot establish",
          "has that shape right now" not in _out and "Causes" in _out,
          _out.replace("\n", " ")[:140])

    # ---- C21: fill_form's batched write must not trust a held reference ----
    # The batched text pass CLEARS each field and dispatches `input` before
    # writing the real value. An app that re-renders synchronously on input
    # replaces the node right there, so the held `el` is detached: the write
    # lands on an orphan and the read-back reads that same orphan and reports
    # SUCCESS while the page stays empty. Measured live on
    # tools/saas_playground.py -- detachedAfterClear=true, readback filled,
    # live value "" -- i.e. the #10/#11/#12 family reached through the
    # VERIFICATION step, which is why #24's read-back rule did not catch it.
    #
    # This lives in a contract check rather than a fixture because the batched
    # write is INLINE in the op router's `case "fill_form"` and cannot be
    # sliced out by _extract -- #19's "the op router is the untested link",
    # literally. A source-shape tripwire is weaker than a behavioural test and
    # is what is available here.
    _bg = open(os.path.join(ROOT, "extension", "background.js"),
               encoding="utf-8").read()
    _i = _bg.find("Batched text-input pass")
    _j = _bg.find("Non-text fields one-by-one", _i + 1) if _i > 0 else -1
    # Bounded by the NEXT section's marker, not by a character count: a magic
    # window silently stops covering the end of the pass the moment the code
    # grows, which is how a tripwire stops tripping (#39).
    _seg = _bg[_i:_j] if _i > 0 and _j > _i else ""
    check("C21 fill_form's batched write RE-RESOLVES after the clear-dispatch, "
          "instead of writing to and reading back from a node the app may have "
          "already replaced",
          bool(_seg) and "if (!node.isConnected) node = q(j.selector)" in _seg,
          "re-resolve after clear not found in the batched pass")
    check("C21b ...and the read-back is taken from the LIVE document, not from "
          "the node the write happened to land on",
          bool(_seg) and "node.isConnected ? node : (q(j.selector)" in _seg
          and "'value' in live" in _seg,
          "live read-back not found in the batched pass")

    # ---- C26: --check-only VALIDATES WITHOUT A BROWSER, which is the whole
    # reason it exists. The playwright import used to run before the flag was
    # read, so on a machine with no playwright the flag printed a SKIP and
    # returned 0 — zero files checked, exit 0, and a line indistinguishable
    # from a healthy skip. That is precisely the failure the flag's own help
    # text describes, in the flag itself, and CI could never see it because CI
    # installs playwright. Measured on a fresh clone before the fix.
    #
    # Driven as a SUBPROCESS with playwright hidden, rather than asserted from
    # the source: the invariant is what the caller gets, not where an import
    # sits (#15 — test the function the caller actually reaches).
    import textwrap
    _blocker = _Path(ROOT) / "temp" / "_noplaywright"
    try:
        _blocker.mkdir(parents=True, exist_ok=True)
        # A package directory that shadows the real one and refuses to import.
        (_blocker / "playwright").mkdir(exist_ok=True)
        (_blocker / "playwright" / "__init__.py").write_text(
            "raise ImportError('hidden for C26')\n", encoding="utf-8")
        _env = dict(os.environ)
        _env["PYTHONPATH"] = str(_blocker) + os.pathsep + _env.get("PYTHONPATH", "")
        _r = subprocess.run([sys.executable, str(_Path(ROOT) / "tools" / "run_flows.py"),
                             "--check-only"],
                            capture_output=True, text=True, timeout=120, env=_env,
                            cwd=str(ROOT))
        _out = (_r.stdout or "") + (_r.stderr or "")
        check("C26 --check-only validates every flow with NO playwright installed",
              _r.returncode == 0 and "flow file(s) valid" in _out
              and "SKIP run_flows" not in _out,
              textwrap.shorten(_out.strip().replace("\n", " | "), 200))
        _r2 = subprocess.run([sys.executable, str(_Path(ROOT) / "tools" / "run_flows.py"),
                              "--local-only"],
                             capture_output=True, text=True, timeout=120, env=_env,
                             cwd=str(ROOT))
        _out2 = (_r2.stdout or "") + (_r2.stderr or "")
        check("C26b CONTROL: a real REPLAY still skips with a reason, so the "
              "fix did not make a browserless run pretend it replayed",
              "SKIP run_flows" in _out2 and "flow file(s) valid" not in _out2,
              textwrap.shorten(_out2.strip().replace("\n", " | "), 200))
    except Exception as _e:
        check("C26 --check-only validates every flow with NO playwright installed",
              False, f"{type(_e).__name__}: {_e}")
    finally:
        shutil.rmtree(_blocker, ignore_errors=True)

    # ---- OC5/OC6: `onclick` and case folding have ONE spelling each ----------
    # `onclick` is two attributes with one name: the CONTENT attribute, which
    # hasAttribute sees, and the IDL attribute, which `el.onclick = fn` sets
    # without touching the markup. listener_tag.js cannot see the second either —
    # it wraps addEventListener, and a property assignment never calls it. So an
    # element declaring only a property handler existed for no tool, and ten
    # separate sites asked the question the narrow way. Rule 17: a concept spelled
    # two ways drifts, and here the drift is a whole class of control going
    # missing. Neither term subsumes the other — under a strict CSP an inline
    # handler attribute is never compiled, so hasAttribute is true while the
    # property is null.
    _oc_src = read("extension/background.js")
    _oc_lines = _oc_src.split("\n")
    _oc_bad = []
    for _i, _l in enumerate(_oc_lines):
        if "hasAttribute('onclick')" not in _l:
            continue
        # The two spellings routinely straddle a line break in these long boolean
        # chains, so the window is the line plus its neighbours rather than the
        # line alone — a per-line rule would flag correct code and teach the
        # reader to ignore it.
        _win = "\n".join(_oc_lines[max(0, _i - 1):_i + 3])
        if "_hasHandlerProp(" not in _win:
            _oc_bad.append(_i + 1)
    check("OC5 every site reading the onclick ATTRIBUTE reads the handler "
          "PROPERTY beside it",
          not _oc_bad,
          f"{len(_oc_bad)} site(s) at line(s) {_oc_bad[:6]}" if _oc_bad
          else f"{sum(1 for l in _oc_lines if 'hasAttribute(' + chr(39) + 'onclick' + chr(39) + ')' in l)} site(s), all paired")
    # The detector must be shown to fire, or "0 findings" is worth nothing.
    check("OC5* ...and the rule provably fires on a site that reads only the "
          "attribute",
          "_hasHandlerProp(" not in "if (el.hasAttribute('onclick')) return true;")

    # OC7/OC8: the property check is DERIVED from listener_tag.js, not restated.
    # Two passes answering "did the page wire this up?" with two different lists
    # is #21's one-concept-two-spellings, and #18 measured exactly that asymmetry
    # (isInteractive accepting a handler-bound div while keepForFind did not) at
    # 60% of a whole accuracy gap. Asking only about `onclick` here would have
    # said: bound with addEventListener('pointerdown') = a control, assigned to
    # onpointerdown = not a control — and the pointer half is the half that
    # matters, because Radix/HeadlessUI/MUI gate on pointerdown rather than click,
    # which is the entire reason fix #1 exists.
    _hp = {l.strip() for l in _oc_lines if "const _hasHandlerProp" in l}
    _hp_n = sum(1 for l in _oc_lines if "const _hasHandlerProp" in l)
    check("OC7 every injected copy of _hasHandlerProp is byte-identical (the "
          "closure is lost on injection, so the duplication is forced — the "
          "drift is not)",
          len(_hp) == 1 and _hp_n >= 4, f"{_hp_n} copies, {len(_hp)} distinct")
    _tag_src = read("extension/listener_tag.js")
    _act = re.search(r"const ACTIVATION = new Set\(\[([^\]]*)\]\)", _tag_src)
    _want_props = ({"on" + s for s in re.findall(r"'([a-z]+)'", _act.group(1))}
                   if _act else set())
    _have_props = set(re.findall(r"'(on[a-z]+)'", next(iter(_hp)))) if _hp else set()
    check("OC8 the properties it checks are exactly `on` + listener_tag.js's "
          "ACTIVATION set, so the two files cannot disagree about what an "
          "activation handler is",
          bool(_want_props) and _have_props == _want_props,
          f"only in background.js: {sorted(_have_props - _want_props)}; "
          f"only in listener_tag.js: {sorted(_want_props - _have_props)}"
          if _have_props != _want_props else f"{len(_want_props)} events, agreed")
    # OC6: `toLocaleLowerCase()` is SPECIFIED to use the host default locale, so
    # the same page and the same request can give different answers on different
    # machines. MEASURED AND THE SCARY VERSION DID NOT REPRODUCE: the audit
    # reported that a Turkish-locale Chrome could select no option containing a
    # capital I; `'INDIA'.toLocaleLowerCase('tr-TR')` really is 'ındıa', but the
    # NO-ARGUMENT form returns 'india' with the ICU default locale set to tr-TR —
    # checked in headless Chromium via Emulation.setLocaleOverride, with
    # --lang=tr-TR, with LANG/LC_ALL, and in bare Node (V8 13.6). So this is a
    # latent API hazard rather than an observed defect, and a source rule is the
    # ONLY thing that can pin it: no behavioural fixture can make V8 exhibit it.
    _oc_mask = code_mask(_oc_src)
    _loc = [_oc_src[:m.start()].count("\n") + 1
            for m in re.finditer(r"toLocale(?:Lower|Upper)Case", _oc_src)
            if _oc_mask[m.start()]]
    check("OC6 no locale-dependent case conversion in the extension, so a match "
          "cannot depend on the user's OS", not _loc,
          f"{len(_loc)} site(s) at line(s) {_loc[:6]}" if _loc else "clean")
    check("OC6* ...and the rule provably fires on the call that shipped",
          bool(re.search(r"toLocale(?:Lower|Upper)Case",
                         "x.normalize('NFC').toLocaleLowerCase()")))

    # ---- FX1: the fold that ACTS and the fold that RANKS are one rule ---------
    # mcp_server.py's `_fold` and the extension's `norm` answer the same question
    # in two LANGUAGES, so P2's byte-identity cannot reach across and the only
    # checkable property is behaviour: two strings that are the same option on one
    # side must be the same option on the other. Neither file is imported — `_fold`
    # is sliced out and exec'd, `norm` is sliced out and run in node — because
    # importing mcp_server runs its module body.
    _FXC = ["İstanbul", "istanbul", "Istanbul", "ISTANBUL", "İzmir", "izmir",
            "Ankara", "México", "Mexico", "Café", "Cafe", "Ελλάδα", "ελλαδα",
            "Tiếng Việt", "Tieng Viet", "Åland", "aland", "ПРИМЕР", "пример",
            "ハス", "バス", "パス", "ビール", "ピール", "ヒール",
            "क", "का", "किताब", "कताब", "한국어", "검색", "٣٨٢", "382",
            # The three KNOWN divergences, included rather than excluded: an
            # exclusion list quietly grows, while asserting the exact set makes a
            # FOURTH divergence a failure. casefold() applies FULL case folding
            # and toLowerCase does not (ß, the ﬁ ligature), so JS merges FEWER —
            # a miss on an exotic spelling, never a wrong option. And Python
            # filters on canonical combining class while JS has no such API and
            # filters on category Mn, so JS drops the handful of ccc-0 Mn marks
            # (Thai U+0E31) that Python keeps, and merges MORE for those scripts.
            "Straße", "strasse", "ﬁle", "file", "กัน", "กน"]
    _FX_KNOWN = {frozenset({"Straße", "strasse"}), frozenset({"ﬁle", "file"}),
                 frozenset({"กัน", "กน"})}
    try:
        import unicodedata as _ud
        _srv_src = read("mcp_server.py")
        _m = re.search(r"^_KANA_VOICING = .*?^def _fold\(x: str\) -> str:.*?^(?=\S)",
                       _srv_src, re.S | re.M)
        _ns = {"unicodedata": _ud}
        exec(compile(_m.group(0), "<_fold>", "exec"), _ns)  # noqa: S102
        _norms = {l.strip() for l in _oc_lines if "const norm = (s)" in l}
        assert len(_norms) == 1, f"{len(_norms)} distinct norm copies"
        _js = ("const c = " + json.dumps(_FXC, ensure_ascii=False) + ";"
               + _norms.pop() + "console.log(JSON.stringify(c.map(norm)));")
        _jsr = json.loads(subprocess.run(["node", "-e", _js], capture_output=True,
                                         text=True, check=True, timeout=60).stdout)
        _pyr = [re.sub(r"\s+", " ", _ns["_fold"](s)).strip() for s in _FXC]

        def _merge(vals):
            g: dict = {}
            for s, v in zip(_FXC, vals):
                g.setdefault(v, []).append(s)
            return {frozenset(v) for v in g.values() if len(v) > 1}

        _mj, _mp = _merge(_jsr), _merge(_pyr)
        _fx_diff = _mj ^ _mp
        check("FX1 the extension's fold and mcp_server's _fold merge the same "
              "strings, bar the three documented divergences",
              _fx_diff == _FX_KNOWN,
              f"js={len(_mj)} py={len(_mp)}; unexpected="
              + ("; ".join(sorted(str(sorted(s)) for s in (_fx_diff - _FX_KNOWN)))
                 or "none")
              + ("; no longer diverging: "
                 + "; ".join(sorted(str(sorted(s)) for s in (_FX_KNOWN - _fx_diff)))
                 if _FX_KNOWN - _fx_diff else ""))
        # Kana voicing and a Devanagari matra are the two shapes where dropping a
        # mark changes the WORD rather than its strictness. If this ever merges,
        # a request for one option lands on another under ok:true.
        _pairs = [("ハス", "バス"), ("ハス", "パス"), ("バス", "パス"),
                  ("ビール", "ピール"), ("ヒール", "ビール"),
                  ("क", "का"), ("किताब", "कताब")]
        _bad = [(a, b) for a, b in _pairs if _jsr[_FXC.index(a)] == _jsr[_FXC.index(b)]]
        check("FX1b ...and neither side merges a voiced kana with its plain form, "
              "or a matra with its bare consonant", not _bad, f"merged={_bad}")
    except Exception as _e:  # noqa: BLE001
        check("FX1 the extension's fold and mcp_server's _fold merge the same "
              "strings", False, f"{type(_e).__name__}: {_e}")

    # ---- MC1/MC2: a `dup:` tag must tell the truth ---------------------------
    # `i18n:` tags are enforced by P2; `dup:` tags were enforced by nothing, and
    # one of them was a lie. `markCutLite` sat under `dup:markcut` claiming to be
    # a copy of markCut while doing a raw `t.slice(0, n)` with no surrogate guard —
    # and it had NO CALL SITES in any file, so no live run could ever have caught
    # it. It is deleted; these two keep the remaining copies honest.
    _dup: dict = {}
    for _i, _l in enumerate(_oc_lines):
        _m2 = re.search(r"dup:([a-z]+)", _l)
        if _m2:
            _dup.setdefault(_m2.group(1), []).append(_i)
    _mc_bad, _mc_live = [], 0
    for _i in _dup.get("markcut", []):
        _win = "\n".join(_oc_lines[_i:_i + 14])
        if "…(+" not in _win:
            continue      # a tombstone: a deleted copy cannot drift (P2's rule)
        _mc_live += 1
        if not re.search(r"0xD800|clip\(|markCut\(", _win):
            _mc_bad.append(_i + 1)
    check("MC1 every live dup:markcut copy is surrogate-safe, so an emoji at the "
          "cut cannot become a lone surrogate",
          not _mc_bad and _mc_live >= 2,
          f"{_mc_live} live cop(ies), unguarded at {_mc_bad}" if _mc_bad
          else f"{_mc_live} live copies, all guarded")
    check("MC1* ...and the rule provably fires on markCutLite's body as it shipped",
          not re.search(r"0xD800|clip\(|markCut\(",
                        "let cut = t.slice(0, n);\nreturn cut + '…(+' + n + ')';"))
    _mc2 = [k for k, v in _dup.items() if len(v) < 2]
    check("MC2 no dup: tag claims a duplication that no longer exists",
          not _mc2, f"singletons={_mc2}" if _mc2
          else ", ".join(f"{k}x{len(v)}" for k, v in sorted(_dup.items())))

    print(f"\n{passed} passed, {failed} failed, {passed + failed} total checks")
    if failures:
        print("failing: " + ", ".join(failures))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
