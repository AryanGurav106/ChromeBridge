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

    # C20e: THE CHEAPER FORMAT MUST NAME WHAT IT DROPS.
    # `format="flat"` sold itself on size and on "you only need a single named
    # control". Measured live in eval 7: an agent chose flat TO REDUCE SIZE on a
    # grocery catalogue where ~40 cards carry an identically-named «Добавить»,
    # so its condition was satisfied and the advice was still wrong -- what it
    # then needed was the containment the tree states by indentation, and it
    # said so: "the cheaper format is the one that drops exactly the containment
    # relationship that disambiguates identical buttons."
    # #27 shipped the tree as default for precisely this ("a flat list cannot
    # express a row") and the escape hatch's own text never caught up. A trade
    # a parameter does not name is one the caller cannot weigh.
    _fmt = re.search(r'Field\(description="(\\"tree\\" \(default\).*?)"\)', _srv, re.S)
    _fmtdoc = _fmt.group(1) if _fmt else ""
    check("C20e format's own description names the trade flat makes -- that "
          "rows sharing one label lose the containment that separates them",
          bool(_fmtdoc) and "SHARE one label" in _fmtdoc
          and "UNIQUE on the page" in _fmtdoc,
          (_fmtdoc[-150:] if _fmtdoc else "(format description not found)"))

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
        _ms2 = _ms
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

    # C43: A STALE EXTENSION IS WORSE THAN A STALE SERVER, and had no read at
    # all. A `/mcp` reconnect fixes C22's case in a second; the loaded service
    # worker needs a HAND-RELOAD at chrome://extensions, and nothing anywhere
    # said so. Measured the day this was written: the observe->act submit
    # REFUSAL -- a guard on an irreversible action -- was committed at 13:22
    # while the running worker had started 23:33 the previous night, so it was
    # shipped, fixtured, documented CLOSED, and had never executed in a
    # browser. #43's rule is that a live pass is not optional; this is the read
    # that tells you whether you have had one.
    try:
        _ext_fresh = _ms2._ext_changed_since_worker(1)       # worker born 1s ago
        check("C43 CONTROL: a worker younger than every extension edit reports "
              "nothing — a notice that fired every run would be the noise #15 "
              "priced",
              _ext_fresh == [], f"reported {(_ext_fresh or [])[:4]}")
        _ext_old = _ms2._ext_changed_since_worker(10 ** 9)   # worker born in 1938
        check("C43b ...and a worker older than the files names them, so "
              "'shipped' and 'running' stop being the same word",
              isinstance(_ext_old, list)
              and "extension/background.js" in _ext_old,
              f"reported {(_ext_old or [])[:4]}")
        # THE AGE COMES FROM THE EXTENSION, so it can be absent or junk, and
        # "I could not see" must never render as "there is nothing to see"
        # (#77's structural root). None is the sentinel the caller reports as
        # UNKNOWN; an empty list would read as CLEAN.
        check("C43c an unreadable worker age reports UNKNOWN, never clean",
              all(_ms2._ext_changed_since_worker(_v) is None
                  for _v in (None, "", "soon", {})),
              "sentinel holds for None/''/'soon'/{}")
        _srv5 = read("mcp_server.py")
        check("C43d ...and sw_info actually CALLS it — #19/#30: the helper "
              "existing is not the same as it being wired",
              "_ext_changed_since_worker(" in _srv5.split("async def sw_info(")[1],
              "called inside sw_info")
        # BOTH SHAPES OF `out`. `sw_info` builds it as `res` itself when the
        # bridge returns a dict and `{"sw": res}` when it returns a string, so
        # reading one spelling finds the age on live traffic and nothing on the
        # other -- the string-contract class that kept `delta` dead for its
        # whole life (#30). Driven over the real extraction rather than grepped.
        import textwrap as _tw
        _sw_body = _srv5.split("async def sw_info(")[1].split("@mcp.tool()")[0]
        _ls = _sw_body.splitlines()
        _a = next(i for i, l in enumerate(_ls) if "_agesrc = out if" in l)
        _b = next(i for i, l in enumerate(_ls) if "_ext_changed_since_worker(_agesrc" in l)
        _frag = _tw.dedent("\n".join(_ls[_a:_b]))
        def _age_of(_out):
            _ns = {"out": _out, "json": __import__("json"), "_agesrc": {}}
            exec(_frag, _ns)
            return _ns["_agesrc"].get("ageSec")
        check("C43e the worker age is found in BOTH shapes sw_info can build — "
              "a dict result and a JSON string under 'sw'",
              _age_of({"ageSec": 42}) == 42
              and _age_of({"sw": '{"ageSec": 42}'}) == 42
              and _age_of({"sw": {"ageSec": 42}}) == 42,
              "dict / json-string / nested-dict all resolve")
        check("C43f CONTROL: junk under 'sw' yields no age, so it reports "
              "UNKNOWN rather than inventing a clean answer",
              _age_of({"sw": "not json"}) is None and _age_of({}) is None,
              "unparseable and absent both give None")
    except Exception as _e:
        check("C43 the extension-staleness probe runs", False,
              f"{type(_e).__name__}: {_e}")

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

    # ---- C47: docs/README.md ROUTES TO EVERY RESEARCH PAPER. Same class as
    # C28 one directory over, and it had already drifted further: 9 of 16
    # papers under docs/research/ had no row at all, so a reader hardening
    # record/replay was routed to FLOWS-CONCEPTUAL-BREAKS and never to
    # FLOW-FRAGILITY or FLOW-UNBREAKABLE, which are the two that rank the
    # failure modes and measure the ordinal witness. docs/README.md itself
    # calls research/ "one file per investigation" and the brief asks for
    # hierarchical documentation, so a paper nothing points at is a paper
    # nobody finds. Discovered from the FILESYSTEM, never from a list here,
    # for the same reason C28 is: a restated inventory is the thing that
    # drifts (PRINCIPLES 17).
    _papers = {f.name for f in (_Path(ROOT) / "docs" / "research").glob("*.md")}
    _docidx = read("docs/README.md")
    _routed = set(re.findall(r"research/([A-Za-z0-9\-\.]+\.md)", _docidx))
    _unrouted = sorted(_papers - _routed)
    # The firing demonstration. A completeness check whose "0 findings" has
    # never been shown to be reachable asserts that nothing is wrong while
    # being unable to say otherwise (PRINCIPLES 15, and #21's rule for
    # audit_patterns.py). Planting a name that cannot be in the index proves
    # the set difference is what decides it.
    _c47_fires = bool({"ZZ-PLANTED-NOT-IN-INDEX.md"} - _routed)

    # ---- C47c: THE "MOST RECENT WORK" POINTER NAMES THE MOST RECENT WORK.
    # That row read #76-#85 while the log ran to #94, so a new reader was
    # routed to a nine-entry-old view of the project by the one row whose
    # entire job is to be current. Found by hand in the same file as the nine
    # unrouted papers above -- two drift instances in one document, which is
    # what earns a check rather than another resolution to remember. Decidable:
    # the row claims to be the latest, so it must name the highest entry.
    _entries = [int(m) for m in re.findall(r"^(\d+)\.", read("CLAUDE.md"), re.M)]
    _head = max(_entries) if _entries else 0
    _catchup = next((l for l in _docidx.splitlines()
                     if l.startswith("| catching up on the most recent work")), "")
    _names_head = bool(_catchup) and str(_head) in _catchup
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

    check("C47 docs/README.md routes to every paper in docs/research/",
          not _unrouted,
          f"UNROUTED: {', '.join(_unrouted)}" if _unrouted
          else f"{len(_papers)} papers, all routed")

    check("C47b the route check FIRES on a paper the index does not name "
          "(a completeness check that cannot fire also asserts nothing is wrong)",
          _c47_fires,
          "planted name reported as unrouted" if _c47_fires
          else "PLANTED NAME WENT UNREPORTED — the set difference is not deciding this")

    check("C47c docs/README.md's catch-up row names the newest CLAUDE.md entry",
          _names_head,
          f"row does not mention #{_head}" if _catchup and not _names_head
          else ("catch-up row not found in docs/README.md" if not _catchup
                else f"names #{_head}"))

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

    # ---- C37: THE REF AND THE CONTEXT ARE TWO DIFFERENT UNITS -------------
    # The ref is the ATTRIBUTION unit (the element whose own text first contains
    # the whole match, #32) and the context is the nearest enclosing RECORD the
    # climb reached (#47). Both are right; printing them adjacent with nothing
    # saying so is what misleads.
    # Measured live in eval 7: a row read
    #   <div ref_1120 "Медный вензель…"@46> МЕДНЫЙ ВЕНЗЕЛЬ … | 4.5 | 430 | 689 ₽
    # and the agent took ref_1120 to own the 689 ₽. It scoped a read to it and
    # got one text node back -- a round trip for a string already on the line.
    check("C37 the located trailer says the ref owns the MATCH, not necessarily "
          "the whole context quoted beside it",
          "owns the MATCH" in _out and "belong to a sibling" in _out,
          _out.replace("\n", " ")[-220:])
    # CONTROL: the trailer is conditional (#13 -- a notation is explained only
    # when it appears), so a result with no located match must not carry it.
    class _FBP:
        connected = True

        async def call(self, op, **kw):
            return {"hits": [{"match": "whole", "context": "whole", "at": 0,
                              "tag": "p", "ref": "5"}],
                    "total": 1, "shown": 1, "scanned": 1}

    _ms.STATE["bridge"] = _FBP()
    _out2 = _aio.run(_sp(pattern="whole", tabId=1))
    check("C37b CONTROL: a match that fills its own element carries no such "
          "trailer, so the explanation appears only where the notation does",
          "owns the MATCH" not in _out2, _out2.replace("\n", " ")[:160])
    _ms.STATE["bridge"] = _FB()

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

    # ---- C36: A ROW WITH NO REF CANNOT BE ACTED ON, AND ONLY ONE SIBLING SAID SO
    # mmids come from the COLLECTOR, so nothing carries one until read_page has
    # run on this document (#32). `search_page` disclosed it; `query_elements`
    # never did -- while the listing's own aria-hidden note sends callers HERE
    # and promises "its refs act normally".
    # Measured live in eval 7: an agent followed that note, typed a destination,
    # queried the suggestion button that had just appeared, and got
    # `<button> "Дубай ОАЭ"` with NO ref. It spent a whole call running read_page
    # purely to make the collector stamp, then re-queried. Its words: "for a
    # suggestion list -- i.e. anything that appears in response to typing, which
    # is the normal case -- query_elements alone is a dead end, and nothing in
    # that note says so."
    _ms.STATE["bridge"] = _FBQ({"rows": [{"tag": "button", "text": "Дубай ОАЭ"}],
                                "total": 1})
    _out = _aio.run(_qe(selector=".opt", tabId=1))
    check("C36 query_elements says a ref-less row cannot be acted on yet, and "
          "names read_page as what stamps it",
          "NO ref" in _out and "read_page" in _out, _out.replace("\n", " ")[:170])
    # THE MIXED CASE IS THE COMMON ONE and an all-or-nothing guard is silent for
    # it: after one read_page the page's original elements carry refs and
    # anything rendered since does not. That is exactly what eval 7 hit.
    _ms.STATE["bridge"] = _FBQ({"rows": [{"ref": "9", "tag": "button", "text": "old"},
                                         {"tag": "button", "text": "new"}],
                                "total": 2})
    _out = _aio.run(_qe(selector="button", tabId=1))
    check("C36b ...and it fires when only SOME rows lack a ref, which is the "
          "shape a page gets after one read plus one interaction",
          "1 of these have NO ref" in _out, _out.replace("\n", " ")[:170])
    # CONTROL: every row stamped means nothing to say. Without this, a note that
    # always fires would pass C36 and be the noise #15 priced.
    _ms.STATE["bridge"] = _FBQ({"rows": [{"ref": "9", "tag": "button", "text": "x"}],
                                "total": 1})
    _out = _aio.run(_qe(selector="button", tabId=1))
    check("C36c CONTROL: rows that all carry refs get no such note",
          "NO ref" not in _out, _out.replace("\n", " ")[:120])
    # C19b: WHEN A CAUSE IS A CHECKABLE FACT, CHECK IT. "it is rendered by a
    # frame this query did not reach" sat fourth in a list of four, so the
    # headline still read as absence -- measured live on the jQuery UI slider
    # demo, where read_page surfaced the frame's controls as ordinary refs and
    # this tool, moments later on the same page, reported no match.
    # THE STUB RETURNED A STRING WHERE THE REAL OP RETURNS A DICT, and that is
    # why this check was GREEN over a feature that never ran. `b.call` hands
    # back `{"rows": [...], "total": N}`; the "N element(s) match" sentence is
    # built in Python AFTERWARDS. The production code regexed `str(result)` for
    # that sentence, so `_frames` was always 0 and the notice below has never
    # rendered since it shipped -- while this test fed it the sentence and
    # passed. #19's "test stubs that share your assumptions test nothing",
    # verbatim, found by driving the real tool against a real cross-origin
    # frame (it reported a partial count and warned about nothing).
    class _FBF(_FBQ):
        async def call(self, op, **kw):
            if op == "page_readiness":
                return ""
            if kw.get("selector") == "iframe, frame":
                return {"rows": [], "total": 2}
            return self.payload

    _ms.STATE["bridge"] = _FBF({"rows": [], "total": 0})
    _out = _aio.run(_qe(selector=".nope", tabId=1))
    check("C19b a miss on a page WITH frames leads with that, instead of "
          "burying it among causes that do not apply",
          "DID NOT LOOK INSIDE THEM" in _out
          and _out.index("frame(s)") < _out.index("No element matches"),
          _out.replace("\n", " ")[:150])
    # THE CONTROL. A page with no frames must not acquire the clause, or it
    # becomes the always-on note #15 priced -- and the cause stays in the list
    # there, because on a frameless page it is still a thing that can be true
    # of a frame the query could not see.
    _ms.STATE["bridge"] = _FBQ({"rows": [], "total": 0})
    _out = _aio.run(_qe(selector=".nope", tabId=1))
    check("C19c CONTROL: a frameless page does NOT get the frame clause",
          "DID NOT LOOK INSIDE THEM" not in _out
          and "rendered by a frame" in _out,
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

    # C38: _CLIMB_STOP and _FIELD_STOP answer ONE question -- "is this container
    # ever one thing's wrapper?" -- in two places, because `_searchTextPage` is
    # injected standalone and loses its closure. The duplication is forced; the
    # drift is not, and #21 records what it costs: the destructive wordlist
    # existed twice in one function, multilingual in one tier and English-only
    # in the other, so "Abbrechen" was rejected by one and accepted by the other.
    def _stopset(name):
        m = re.search(r"const " + name + r" = \{(.*?)\};", _bg, re.S)
        return set(re.findall(r"([A-Z]+)\s*:", m.group(1))) if m else set()
    _fs, _cs = _stopset("_FIELD_STOP"), _stopset("_CLIMB_STOP")
    check("C38 the climb's stop set and the field wrapper's are the same set "
          "(one concept, forced duplication, enforced equality)",
          bool(_fs) and _fs == _cs,
          f"only in _FIELD_STOP: {sorted(_fs - _cs)}; "
          f"only in _CLIMB_STOP: {sorted(_cs - _fs)}"
          if _fs != _cs else f"{len(_fs)} tags, agreed")

    # C39: THE FLOW RUNNER FILLS IN A tabId FOR EVERY STEP -- it has to, because
    # a flow may create a tab mid-run and everything after it belongs there
    # (#58) -- and `tabs_create_mcp` takes NO arguments. So a flow that opens
    # the way `instructions=` and browser_batch's own description BOTH teach
    # died on step 0 with "tabs_create_mcp() got an unexpected keyword argument
    # 'tabId'". Found by replaying a flow recorded on a real app; every offline
    # test builds its steps by hand, so nothing here could have caught it.
    # Driven rather than grepped (#19: the render is the untested link), with a
    # stub standing in for the real tool so no browser is touched.
    import asyncio as _aio
    import importlib.util as _ilu2
    _sp = _ilu2.spec_from_file_location(
        "_ms_tab", _Path(__file__).resolve().parents[1] / "mcp_server.py")
    _msm = _ilu2.module_from_spec(_sp)
    try:
        _sp.loader.exec_module(_msm)
        _seen = {}

        async def _no_tab():
            _seen["no_tab"] = True
            return "ok"

        async def _with_tab(tabId: int = 0):
            _seen["with_tab"] = tabId
            return "ok"

        _msm._BATCHABLE["__probe_no_tab"] = _no_tab
        _msm._BATCHABLE["__probe_with_tab"] = _with_tab
        _err = None
        try:
            _aio.run(_msm._flow_call("__probe_no_tab", {"tabId": 7}))
        except TypeError as e:
            _err = str(e)
        _aio.run(_msm._flow_call("__probe_with_tab", {"tabId": 7}))
    except Exception as e:  # pragma: no cover - import failure is the finding
        _err, _seen = f"probe could not run: {e}", {}
    check("C39 a flow step whose tool takes NO tabId still runs — the runner "
          "fills one in for every step and tabs_create_mcp accepts none",
          _err is None and _seen.get("no_tab") is True,
          _err or f"seen={_seen}")
    # THE CONTROL. "Always strip tabId" would satisfy C39 and break every other
    # step in every flow, since the runner's whole tab-threading contract (#58)
    # is that later steps run in the tab a create made.
    check("C39b CONTROL: ...and a tool that DOES take one still receives it",
          _seen.get("with_tab") == 7, f"seen={_seen}")

    # C40: EVERY BANNER MUST END `***\n`, OR _split_banner CANNOT PEEL IT.
    # `_BANNER_RE` is `\A((?:\*\*\*.*?\*\*\*\n)+)`, and a banner that does not
    # match is left as BODY text -- which means `_truncate` cuts it like any
    # other row and it gets glued onto the first listing line. #76/#77 fixed
    # exactly that for the scoped-read header, and the frozenFade sentence
    # reintroduced it hours later: an uninformed review demonstrated it by
    # running `_split_banner` on the real output. A grep for the newline would
    # pin the symptom; this drives the function that consumes it.
    # SCOPED TO `readinessNote`, because that is the function whose output is
    # fed to `_split_banner`. My first version scanned every `*** … ***`
    # literal in the file and flagged two false positives: `*** NOT DELIVERED
    # ***` is a deliberate INLINE suffix on a click result (note its leading
    # space) that never goes through the splitter, and a comment mentioning it.
    # A check that fires on correct code is worse than none.
    _bgt = read("extension/background.js")
    _rn_start = _bgt.index("async function readinessNote(")
    _rn_end = _bgt.index("\n}", _rn_start)
    _rn = _bgt[_rn_start:_rn_end]
    _opens = re.findall(r"`\*\*\* ", _rn)
    _closes = re.findall(r"\*\*\*(\\n)?`", _rn)
    _bad = sum(1 for c in _closes if not c)
    check("C40 every banner readinessNote returns ends with a newline, which is "
          "what _split_banner's regex requires in order to peel it",
          bool(_opens) and _closes and _bad == 0,
          f"{len(_opens)} opener(s), {len(_closes)} closer(s), "
          f"{_bad} missing the trailing newline")

    # ...and the consumer really does peel one, so C40 is pinned to behaviour
    # rather than to a character.
    _sb = getattr(_msm, "_split_banner", None)
    if _sb:
        _one = "*** A TEST BANNER ***\n"
        _two = "*** FIRST ***\n*** SECOND ***\n"
        _b1, _r1 = _sb(_one + "Current URL: /x")
        _b2, _r2 = _sb(_two + "Current URL: /x")
        check("C40b _split_banner peels a single banner AND two stacked ones, "
              "which is the shape a composed note has",
              _b1 == _one and _r1.startswith("Current URL")
              and _b2 == _two and _r2.startswith("Current URL"),
              f"one={_b1!r} two={_b2!r}")
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

    # MC3 — THE THREE OPTION-ROW COPIES. `_pickOptionPage`, `_countVisibleOptionsPage`
    # and `fillDropdown`'s sampleOptions each harvest option rows out of a popover,
    # and all three are injected separately so they lose their closure — the
    # duplication is FORCED and what was missing was enforcement (#21). They used
    # to reject any candidate whose text ran past 80 UTF-16 units, a chosen number
    # deciding whether an option could be picked at all; the replacement is the
    # structural question it was proxying for, and it has to stay one rule.
    _leaf = [l.strip() for l in _oc_lines
             if "rows = rows.filter(r => !rows.some(" in l]
    check("MC3 all three option-row harvests apply the SAME leaf rule, so a "
          "container cannot be offered as an option in one path and not another",
          len(_leaf) == 3 and len(set(_leaf)) == 1,
          f"{len(_leaf)} cop(ies), {len(set(_leaf))} distinct")
    check("MC3b ...and no copy still gates an option on a LENGTH — the number is "
          "gone from every one of them, not from the one that was reported",
          # CODE lines only. The three comments explaining the removal quote
          # the old gate verbatim, and a check that cannot tell a quotation from
          # the thing it quotes would fire on its own documentation.
          not [l for l in _oc_lines
               if "t.length > 80" in l and not l.lstrip().startswith("//")],
          "no length gate on option rows")

    # MC4 — THE PLACEHOLDER CLASS TEST, TWICE. `_phMarked` (the collector) and
    # `_triggerEvidencePage`'s local `marked` ask the same question about the same
    # element, and `_triggerEvidencePage` is injected separately so the duplication
    # is FORCED. They had drifted: the evidence copy kept the form `_phMarked`
    # carried BEFORE the utility-class exclusion, so a Tailwind `text-placeholder`
    # made it say "placeholder" while the collector read value="Ontario".
    # Reproduced live before fixing -- the two disagreed about the same element at
    # the same instant, three lines under a comment promising they were kept in
    # step. The cost is a false FAILED from fillDropdown on a pick that landed.
    _ph = {}
    for _i, _l in enumerate(_oc_lines):
        if "dup:phmarked" in _l:
            # the body is the token loop that follows the comment block
            _body = []
            for _j in range(_i + 1, min(_i + 24, len(_oc_lines))):
                _t = _oc_lines[_j].strip()
                if _t.startswith("//"):
                    continue
                _body.append(_t)
                if _t == "return false;":
                    break
            _ph[_i] = "\n".join(_body)
    check("MC4 both copies of the placeholder class test are identical, so the "
          "listing and the write-verification cannot disagree about one element",
          len(_ph) == 2 and len(set(_ph.values())) == 1,
          f"{len(_ph)} cop(ies), {len(set(_ph.values()))} distinct")
    check("MC4b ...and both carry the utility-class exclusion, which is the "
          "clause the drifted copy was missing",
          len(_ph) == 2 and all("-placeholder$/" in v for v in _ph.values()),
          "both exclude text-/bg-/border-placeholder")

    # OB8 — THE TWO SIGNATURE COPIES. `_collectInteractivePage` stamps and
    # `_rectForPage` compares, and both are injected separately so neither can
    # call the other: a free sibling identifier in an injected function throws a
    # ReferenceError that every try/catch swallows, which is the C11 class that
    # left three readiness signals dead in production for a release. The
    # duplication is FORCED; what was missing everywhere else was enforcement.
    # If these two drift, the guard compares a stamp against a different question
    # and reports a change on a settled page -- the false-positive direction that
    # makes a warning worth ignoring.
    _ob = {}
    for _i, _l in enumerate(_oc_lines):
        if "dup:obssig" in _l:
            _body = []
            for _j in range(_i + 1, min(_i + 30, len(_oc_lines))):
                _t = _oc_lines[_j].strip()
                if _t.startswith("//") or not _t:
                    continue
                _body.append(_t)
                if _t.startswith("};"):
                    break
            _ob[_i] = "\n".join(_body)
    check("OB8 both copies of the observe-to-act signature are identical, so the "
          "stamp and the comparison cannot ask different questions",
          len(_ob) == 2 and len(set(_ob.values())) == 1,
          f"{len(_ob)} cop(ies), {len(set(_ob.values()))} distinct")
    check("OB8b ...and neither compares GEOMETRY — a cookie banner, a lazy image "
          "and a re-sort that MOVES a node are all harmless, so a rect in the "
          "signature would fire on three cases where nothing is wrong",
          len(_ob) == 2 and not any("getBoundingClientRect" in v for v in _ob.values()),
          "no rect in the signature")

    # ---------------------------------------------------------------- C31 ---
    # THE BANNER'S PROTECTION IS POSITIONAL, AND NOTHING SAID SO UNTIL IT BROKE.
    # `_split_banner` matches ANCHORED, and `_truncate` leans on it to peel the
    # banner off before slicing. So any server-side line prepended AHEAD of a
    # banner does not merely reorder the output -- it makes the banner invisible
    # to both, and it is then truncated away as ordinary body text.
    #
    # MEASURED LIVE on ptable.com with the readiness signal plainly firing: a
    # read scoped with ref_id emitted NO banner at max_chars=300, 420 or 700,
    # and the banner reappeared only at 50000, sitting BELOW the scope header.
    # A scoped read is the documented way to reach deep into a page, so the
    # readiness signal was missing from exactly the reads that go deepest.
    sys.path.insert(0, str(ROOT))
    import importlib
    _ms = importlib.import_module("mcp_server")
    _BANNER = "*** THE DOM IS STILL CHANGING (last change 9ms ago) ***\n"
    _LISTING = "ref_1 | a \"Home\"\n"
    _hdr = "[scoped to the subtree of ref_5 — elements outside it are omitted]\n"
    _joined = _ms._prepend_to_listing(_BANNER + _LISTING, _hdr)
    check("C31 a server-side header line is inserted AFTER an extension banner, "
          "so the banner stays at position 0 where _split_banner and _truncate "
          "can both still find it",
          _joined.startswith(_BANNER) and _hdr in _joined
          and _ms._split_banner(_joined)[0] == _BANNER,
          repr(_joined[:90]))
    check("C31b CONTROL: with no banner present the header is simply first, so "
          "this did not become 'always leave a gap'",
          _ms._prepend_to_listing(_LISTING, _hdr) == _hdr + _LISTING)
    check("C31* ...and the rule provably fires on the concatenation that shipped",
          not _ms._split_banner(_hdr + _BANNER + _LISTING)[0],
          "naive prepend hides the banner from _split_banner")
    # The appended text block carries its own banner (get_dom_text prepends one),
    # describing the same page at the same instant as the listing's. Printing it
    # twice in one response leaves the reader asking which half each describes.
    _B1 = "*** THE DOM IS STILL CHANGING (x) ***\n"
    _B2 = "*** Minor DOM activity (y) ***\n"
    _L, _T = 'ref_1 | a "Home"\n', "page text\n"
    # SAME TIER, DIFFERENT COUNTER -- the shape exact equality could not fold.
    # The two banners are separate round trips milliseconds apart, so one reads
    # `45 change(s) ... 2 text` and the other `46 change(s) ... 3 text`; under
    # the old rule both printed, ~1,200 chars of identical-in-substance prose in
    # one response. Measured live in eval 7.
    _B2a = "*** Minor DOM activity (45 change(s) in the last 3000ms: 3 @class) ***\n"
    _B2b = "*** Minor DOM activity (46 change(s) in the last 3000ms: 4 @class) ***\n"
    _tick = _ms._merge_text_banner(_B2a + _L, _B2b + _T)
    check("C32d two readings of the SAME tier a few ms apart print once — a "
          "counter ticking between them is not a disagreement",
          _ms._split_banner(_tick[1])[0] == ""
          and _ms._split_banner(_tick[0])[0] == _B2a,
          repr((_tick[0][:46], _tick[1][:46])))
    # CONTROL: an UNRECOGNISED banner falls back to strict equality, so a tier
    # nobody taught _banner_tier is kept rather than silently folded into another.
    _BX = "*** SOMETHING NEW (1) ***\n"
    _BY = "*** SOMETHING NEW (2) ***\n"
    _unk = _ms._merge_text_banner(_BX + _L, _BY + _T)
    check("C32e CONTROL: an unknown banner keeps the strict behaviour, so a new "
          "tier is not folded into an existing one by accident",
          _ms._split_banner(_unk[1])[0] == _BY, repr(_unk[1][:46]))

    _same = _ms._merge_text_banner(_B2 + _L, _B2 + _T)
    _diff = _ms._merge_text_banner(_B2 + _L, _B1 + _T)
    _bare = _ms._merge_text_banner(_L, _B1 + _T)
    check("C32 an IDENTICAL banner on the appended text is stripped (the common "
          "duplicate, and the only case the strip was ever right for)",
          _ms._split_banner(_same[1])[0] == "" and _ms._split_banner(_same[0])[0] == _B2)
    check("C32b a DIFFERENT banner is KEPT — the two are separate round trips "
          "and the text probe runs after a hide-read-restore, so discarding it "
          "deleted a genuine warning while the surviving one asserted the "
          "listing was structurally current",
          _ms._split_banner(_diff[1])[0] == _B1)
    check("C32c a banner on the text when the LISTING has none is promoted to "
          "the front, where _truncate protects it instead of cutting it",
          _ms._split_banner(_bare[0])[0] == _B1
          and _ms._split_banner(_bare[1])[0] == "")
    # THE CALL SITE, not the helper. The defect being guarded was a call-site
    # defect: reverting line ~1400 to a naive `line + out` concatenation leaves
    # all 1268 checks green and silently restores the shipped bug, because C31
    # drives the helper directly and no test drives read_page with a ref_id.
    # #19 and #30 are explicit that this is where features die.
    _srv2 = read("mcp_server.py")
    check("C34 the scoped-read header goes through _prepend_to_listing, not a "
          "bare concatenation — C31 tests the helper and this tests the only "
          "place it matters",
          "_prepend_to_listing(" in _srv2
          and not re.search(r'=\s*f?"\[scoped to the subtree[^"]*"\s*\+\s*out', _srv2),
          "scope header is composed, not concatenated")

    # ---------------------------------------------------------------- C44 ---
    # A TIER MARKER MUST SURVIVE THE BRANCH IT IS EMITTED ON, and one did not.
    # `_BANNER_TIERS` is a hand-kept list in mcp_server.py restating the phrases
    # background.js leads a banner with -- the same cross-half string contract
    # C12 exists for, and the only one of them with no tripwire. Measured by
    # driving the real `readinessNote`, not by reading it: on a SCOPED read the
    # emitted banner is
    #     *** DOM STABLE IN THE SUBTREE YOU SCOPED TO, NETWORK BUSY. ...
    # so the marker `DOM STABLE, NETWORK BUSY` matched nothing, `_banner_tier`
    # fell back to the raw banner text, and the mutation counter defeated the
    # equality -- reinstating the duplicate-banner defect eval 7 measured, about
    # 1,200 characters of identical-in-substance prose in one response. A scoped
    # read is the documented way to go deep into a page, so that was the half
    # that mattered.
    #
    # THE RULE IS ABOUT INTERPOLATION, which is what makes it general rather
    # than a restatement of the list. A marker has to live in the run of text
    # between `*** ` and the template's FIRST `${...}`; anything after that
    # depends on which branch ran. Banners whose text carries no ticking value
    # (the frozen-fade and cross-origin-frame sentences) need no marker at all,
    # because exact equality already folds them -- so this asks only that every
    # marker in the list is reachable, not that every banner has one.
    _bgsrc = read("extension/background.js")
    _heads = [re.sub(r"\s+", " ", h).strip()
              for h in re.findall(r"`\*\*\* (.*?)(?:\$\{|`)", _bgsrc, re.S)]
    _unreach = [t for t in _ms._BANNER_TIERS
                if not any(t in h for h in _heads)]
    check("C44 every _BANNER_TIERS marker appears in the interpolation-free "
          "head of a banner the extension really emits — a marker split by a "
          "${...} matches only on the branch that leaves it intact, and the "
          "fallback is raw-string equality, which a counter defeats",
          not _unreach,
          f"unreachable: {_unreach}; heads: {[h[:40] for h in _heads if h]}")
    check("C44b CONTROL: the rule can fail — a marker that no emitted banner "
          "carries is reported, so this is not vacuously true of any list",
          bool([t for t in ("A TIER NOBODY EMITS",)
                if not any(t in h for h in _heads)]),
          "planted marker is detected as unreachable")
    check("C34* ...and the rule provably fires on the concatenation that shipped",
          bool(re.search(r'=\s*f?"\[scoped to the subtree of ref_\{x\} — y]\\n"\s*\+\s*out',
                         'out = f"[scoped to the subtree of ref_{x} — y]\\n" + out')))

    # ------------------------------------------------------- C33 / C34 / C35 ---
    # THE PARSE IS PART OF THE RULER, and for a year it was silently wrong.
    # Mind2Web serializes XML-style, so `<a/>`, `<i/>`, `<iframe/>` come back as
    # EMPTY elements. HTML has no self-closing syntax for a non-void element: the
    # slash is ignored and the tag OPENS. `bench_mind2web.py` excluded thirteen
    # labelled actions saying "the target element is absent from the saved
    # snapshot entirely" when every one of those ids was in the snapshot and was
    # lost in the PARSE -- a false sentence that hid a real input defect and
    # produced a second, pessimistic denominator (89.2%) printed beside the
    # headline. #73 found it; these pin the repair, the bound it exposed, and the
    # sentence. Driven here rather than in a browser suite because the repair is
    # a pure string transform and the credit rule is pure Python -- which is the
    # whole reason both were hoisted out of the benchmark (#30's lesson: a
    # function nested inside the tool is one a test can only reach by proxy).
    import _m2w_ruler as _mw

    _XML = ('<div><a href="/x" name="skip"/><h1 id="t">Balance Sheet</h1>'
            '<img src="i.png"/><iframe src="f"/><button id="after">Go</button></div>')
    _fixed = _mw.repair_serialization(_XML)
    check("C33 a self-closed non-void tag is reopened and closed, so it cannot "
          "adopt the markup that follows it",
          '<a href="/x" name="skip"></a>' in _fixed
          and '<iframe src="f"></iframe>' in _fixed
          and '<button id="after">Go</button>' in _fixed,
          repr(_fixed[:72]))
    check("C33b ...and a VOID element is left exactly as it was, because <img/> "
          "really is self-closing",
          '<img src="i.png"/>' in _fixed and "</img>" not in _fixed)
    check("C33c CONTROL: a document with nothing self-closed comes back "
          "byte-identical, so this is not 'rewrite the markup'",
          _mw.repair_serialization("<div><a href='/x'>hi</a><img src='i'></div>")
          == "<div><a href='/x'>hi</a><img src='i'></div>")
    # #13/#19: a repair that exists and is never applied is `detail="brief"`
    # shipping inert. The benchmark must feed the REPAIRED string to the page.
    _bm = read("tools/bench_mind2web.py")
    check("C33d ...and the benchmark actually renders the repaired string, not "
          "the stored one",
          re.search(r"html\s*=\s*repair_serialization\(s\[.html.\]\)", _bm)
          and re.search(r"set_content\(\s*html\b", _bm),
          "repair is wired into score_one")

    # C34: ONE CAP, BOTH DIRECTIONS. The descendant path was capped by area so a
    # page-sized container could not claim credit for its contents; the ancestor
    # path -- the direction where a false credit is structurally POSSIBLE, since
    # an ancestor is by construction at least as large as its target -- had no
    # bound at all. Measured on the corpus: the descendant cap has never fired
    # (0 of 173 targets reach 40% of the viewport) while the ancestor side
    # carried a <label> credited to an <a> holding 638 elements and 90% of the
    # viewport.
    _big = {"own": None, "area": 0.01, "descs": ["9"],
            "ancs": [{"mmid": "2", "area": 0.90}, {"mmid": "3", "area": 0.02}]}
    check("C34 an ancestor larger than the cap cannot stand in for its target",
          [r for r, _ in _mw.credit_refs(_big)] == ["3", "9"],
          f"{_mw.credit_refs(_big)}")
    check("C34b CONTROL: the same rule still credits a small ancestor, so this "
          "did not become 'never credit an ancestor'",
          _mw.credit_refs({"own": None, "area": 0.01, "descs": [],
                           "ancs": [{"mmid": "3", "area": 0.02}]})
          == [("3", "ancestor")])
    check("C34c the SAME constant bounds both directions — a page-sized TARGET "
          "still cannot be credited with its own contents",
          _mw.credit_refs({"own": None, "area": 0.95, "descs": ["9"], "ancs": []}) == []
          and _mw.credit_refs({"own": None, "area": 0.39, "descs": ["9"],
                               "ancs": []}) == [("9", "descendant")])
    # REFUSING A CREDIT IS NOT LOSING THE ROW, and reporting it as though it were
    # is how #73 computed "mirror the cap -> 165/173". Running it gives 166/173:
    # the one withdrawn credit falls through to the target's own <input>.
    check("C34d a refused ancestor falls through to a descendant credit rather "
          "than dropping the row",
          [v for _, v in _mw.credit_refs(_big)] == ["ancestor", "descendant"])
    check("C34e ...and `cap_withdrew` reports a CHANGED VERDICT, not merely the "
          "existence of an oversized ancestor (#73's own probe bug, which "
          "reported 8 where the truth was 1)",
          _mw.cap_withdrew(_big, {"2", "3", "9"})
          and not _mw.cap_withdrew({"own": "5", "area": 0.01, "descs": [],
                                    "ancs": [{"mmid": "2", "area": 0.9}]}, {"5", "2"}))

    # C35: THE SENTENCE ITSELF. The comment was the defect -- it asserted a fact
    # about the DATASET ("absent from the saved snapshot entirely") that was
    # false, and a reader who believed it had no reason to look further.
    check("C35 the benchmark no longer claims the excluded targets are absent "
          "from the snapshot, and no longer excludes them",
          "target_not_in_html" not in _bm
          and 'target_not_in_dom' in _bm
          and '"target_not_in_dom"' in _bm.split("SCORED = ")[1].split("\n")[0],
          "one denominator, all 186 actions")

    # C35 — THE CAP NOTICE NAMES THE RECOVERY THAT IS ALREADY IN THE RESPONSE.
    # Measured in eval 6: BOTH agents on a dense catalogue reported the capped
    # listing not containing the target while the `--- PAGE TEXT ---` block in
    # the SAME call did, and both said so unprompted. The notice offered find()
    # and a scoped read -- each another round trip -- and said nothing about the
    # text about to be appended below it.
    _srv3 = read("mcp_server.py")
    check("C35 a capped listing under filter=\"all\" points at the page text in "
          "the same response, before recommending another round trip",
          'OMITTED BUT ACTIONABLE" in out or "listing capped at" in out' in _srv3
          and "look there before spending a call" in _srv3,
          "cap notice names the appended text")
    check("C35b CONTROL: it is gated on the cap having FIRED, so an untruncated "
          "listing pays nothing for a notice it does not need",
          'if "OMITTED BUT ACTIONABLE" in out or "listing capped at" in out:' in _srv3,
          "gated on the cap")

    # C36 — A LONE SURROGATE KILLED THE SERVER PROCESS. A JS string is UTF-16 and
    # may legally hold an unpaired surrogate; Chromium preserves them in
    # `textContent` and `document.title`; `JSON.stringify` emits the escape and
    # Python's `json.loads` reconstructs it faithfully. Then everything
    # downstream refuses to encode it -- `TextContent.model_dump_json()` raises
    # `PydanticSerializationError` and the stdio server dies in its TaskGroup,
    # so the NEXT tools/call is never answered. One scrub at the single door
    # every message comes through, not at the ~21 bounded-string sites, because
    # none of those covers a page that simply CONTAINS one.
    import importlib.util as _ilu
    _bs = _ilu.spec_from_file_location(
        "_bsrv", os.path.join(ROOT, "core", "bridge", "server.py"))
    _bm2 = _ilu.module_from_spec(_bs)
    _bs.loader.exec_module(_bm2)
    _scrub = _bm2.ExtensionBridge._scrub_surrogates

    def _ser(x):
        try:
            __import__("json").dumps(x, ensure_ascii=False).encode("utf-8")
            return True
        except Exception:
            return False

    _dirty = {"result": "ab\ud83c", "nested": [{"t": "a\udc00b"}], "ok": "fine"}
    _clean = _scrub(_dirty)
    check("C41 an unpaired surrogate anywhere in a bridge message is replaced, "
          "so the result can be serialised instead of killing the process",
          _ser(_clean) and not _ser(_dirty)
          and "\ufffd" in _clean["result"]
          and "\ufffd" in _clean["nested"][0]["t"],
          repr(_clean))
    check("C41b ...and it REPLACES rather than drops, so no offset the caller "
          "already holds moves (the silent-shortening class, #22)",
          len(_clean["result"]) == len(_dirty["result"])
          # ...and it must have actually CHANGED, or "return the string
          # untouched" satisfies the length equality for free. Caught by
          # ablating the helper to the identity: this check passed.
          and _clean["result"] != _dirty["result"],
          f"{len(_dirty['result'])} -> {len(_clean['result'])}")
    # THE TWO CONTROLS. Without them "mangle every string" would pass C36.
    check("C41c CONTROL: a VALID astral pair survives byte-identical",
          _scrub("a\U0001F600b") == "a\U0001F600b"
          and _scrub({"k": "\U0001F1EF\U0001F1F5"})["k"] == "\U0001F1EF\U0001F1F5",
          "emoji intact")
    check("C41d CONTROL: non-Latin text survives byte-identical, including "
          "combining marks and CJK",
          _scrub("\u6771\u4eac \u0636\u0651 \uc0bc\uc131 \u0915\u093e") ==
          "\u6771\u4eac \u0636\u0651 \uc0bc\uc131 \u0915\u093e",
          "non-latin intact")
    # AND THE WIRING. #19/#30: the helper is not the caller. This is what catches
    # a third parse site being added without one, or the call being removed while
    # the helper stays and every check above still passes.
    _srv4 = read("core/bridge/server.py")
    _loads = [ln for ln in _srv4.splitlines() if "json.loads(" in ln]
    check("C41e every json.loads at the bridge ingress is scrubbed — the helper "
          "existing is not the same as it being called",
          len(_loads) >= 2 and all("_scrub_surrogates(" in ln for ln in _loads),
          " | ".join(x.strip()[:60] for x in _loads))

    # ---- C42: A DOCSTRING THAT SPELLS AN ESCAPE BECOMES IT -----------------
    # From Python 3.13 `compile()` refuses a docstring containing a lone
    # surrogate -- it encodes to UTF-8 while dedenting -- so a module with one
    # cannot be imported at all. `pyproject.toml` advertises >=3.10 and CI runs
    # the unit group on 3.10 AND 3.13 for exactly that reason, and the
    # _scrub_surrogates docstring (which is ABOUT lone surrogates, and spelled
    # one) killed every suite that imports mcp_server on the 3.13 leg for three
    # days while staying green on the 3.12 I develop on. A version-specific
    # break is invisible to the developer by construction; this makes it visible
    # on whatever version is running the suite.
    #
    # DOCSTRINGS ONLY, deliberately. An ordinary string constant holding a lone
    # surrogate compiles fine on every version, and C41's own dirty fixture is
    # one -- forbidding those would fail the test that proves the scrub works.
    import ast as _ast
    _lone = lambda t: any(0xD800 <= ord(c) <= 0xDFFF for c in t)
    _rt = _Path(ROOT)
    _roots = [_rt / "mcp_server.py", _rt / "config.py",
              _rt / "core", _rt / "tools"]
    _pys = []
    for _r in _roots:
        _pys.extend(sorted(_r.rglob("*.py")) if _r.is_dir() else [_r])
    _offenders, _scanned, _probed = [], 0, 0
    for _py in _pys:
        if "__pycache__" in _py.parts:
            continue
        try:
            _tree = _ast.parse(_py.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        _scanned += 1
        for _n in _ast.walk(_tree):
            if not isinstance(_n, (_ast.Module, _ast.ClassDef,
                                   _ast.FunctionDef, _ast.AsyncFunctionDef)):
                continue
            _d = _ast.get_docstring(_n, clean=False)
            if _d is None:
                continue
            _probed += 1
            if _lone(_d):
                _offenders.append(f"{_py.relative_to(_rt)}:{_n.lineno}")
    check("C42 no docstring in the project contains a lone UTF-16 surrogate — "
          "from 3.13 that is a compile error, so the module cannot be imported "
          "on a version pyproject.toml advertises",
          not _offenders and _scanned > 20 and _probed > 100,
          f"scanned={_scanned} files, {_probed} docstrings; offenders={_offenders}")
    # THE DETECTOR HAS TO BE SHOWN FIRING, or "0 offenders" is worth nothing
    # (#21's rule for audit_patterns.py). Planted in memory, never on disk, and
    # as the ESCAPE rather than the character -- that distinction IS the bug:
    # source text holding a real lone surrogate is refused by `ast.parse` on
    # every version, while source holding `\ud83d` inside a docstring compiles
    # on 3.12 and is refused from 3.13. So the control accepts EITHER outcome:
    # our scan finding it, or the compiler refusing it outright, which is the
    # stronger detection and is what the 3.13 CI leg does.
    _bs = chr(92)
    _planted_src = 'def f():\n    """talks about ' + _bs + 'ud83d for real"""\n'
    try:
        _pt = _ast.parse(_planted_src)
        _hit = [1 for _n in _ast.walk(_pt)
                if isinstance(_n, _ast.FunctionDef)
                and _lone(_ast.get_docstring(_n, clean=False) or "")]
        _how = f"our scan, {len(_hit)} hit(s)"
        _fired = len(_hit) == 1
    except UnicodeEncodeError:
        _how, _fired = "the compiler refused it (3.13+ behaviour)", True
    check("C42b CONTROL: a planted violation is caught — by this scan, or by "
          "the compiler refusing it — so the clean result above is evidence "
          "rather than an empty loop",
          _fired, f"caught by {_how}")

    # ---- C45: THE OTHER END OF THE SUPPORTED RANGE ------------------------
    # C42 catches what 3.13 refuses. This catches what 3.10 and 3.11 refuse: a
    # BACKSLASH inside an f-string's EXPRESSION part, which PEP 701 only made
    # legal in 3.12. `pyproject.toml` advertises >=3.10 and CI runs the unit
    # group on 3.10 AND 3.13 for exactly that, so a file with one does not
    # PARSE on the 3.10 leg -- the suite dies at import with
    # `SyntaxError: f-string expression part cannot include a backslash`.
    #
    # FOUND ON CI, NOT HERE, which is the whole reason this exists: the version
    # I develop on accepts it, so the construct is invisible locally in both
    # directions. Three sites when first run, and TWO OF THEM WERE WRITTEN THAT
    # HOUR by the author of C42 -- a check-message f-string interpolating
    # `'\"Buy\"' in _mv5`. A rule that lives only in prose is a rule a human
    # has to remember, and this one was forgotten by the person who had just
    # written the rule for the opposite version.
    #
    # EXACT, not a regex over source. `ast` gives the FormattedValue nodes and
    # `get_source_segment` gives each expression's own text, so a backslash in
    # the LITERAL part (which is legal at every version) cannot be mistaken for
    # one in the expression.
    _fstr = []
    for _py in _pys:
        if "__pycache__" in _py.parts:
            continue
        try:
            _src = _py.read_text(encoding="utf-8")
            _t = _ast.parse(_src)
        except (SyntaxError, UnicodeDecodeError):
            continue
        for _n in _ast.walk(_t):
            if isinstance(_n, _ast.FormattedValue):
                _seg = _ast.get_source_segment(_src, _n.value) or ""
                if "\\" in _seg:
                    _fstr.append(f"{_py.relative_to(_rt)}:{_n.lineno}")
    check("C45 no f-string in the project puts a backslash in its EXPRESSION "
          "part — legal only from 3.12, and pyproject.toml advertises >=3.10",
          not _fstr, f"offenders={_fstr}")
    # THE DETECTOR SHOWN FIRING -- AND THIS CONTROL ONCE BROKE EXACTLY THE WAY
    # THE CHECK ABOVE EXISTS TO PREVENT. The planted source is parsed with the
    # RUNNING interpreter, and on 3.10/3.11 that raises SyntaxError before any
    # of it is inspected -- uncaught, so the whole contracts suite died at this
    # line and CI's 3.10 leg reported `FAIL ... ? <- exit code 1` with no check
    # named. The comment that used to sit here even said the construct "would
    # not [parse] on 3.10" and then called ast.parse on it anyway. So the check
    # written to catch a 3.10-only breakage was itself a 3.10-only breakage, in
    # its own control, by the author who had just written the rule (#86's
    # lesson one layer deeper: a rule in prose is one a human has to remember,
    # and a rule in a check is one its own control can still violate).
    #
    # The fix is C42b's shape, which had this asymmetry right from the start:
    # on a version that REFUSES the construct, the refusal IS the detection,
    # and the control must report that rather than die of it.
    _planted_src = 'x = 1\ny = f"{chr(92) and \'a\\\\b\' in \'z\'}"\n'
    try:
        _planted_f = _ast.parse(_planted_src)
        _pf = [1 for _n in _ast.walk(_planted_f)
               if isinstance(_n, _ast.FormattedValue)
               and "\\" in (_ast.get_source_segment(_planted_src, _n.value) or "")]
        _pf_how = "our scan"
    except SyntaxError:
        _pf, _pf_how = [1], "the interpreter refusing to parse it"
    check("C45b CONTROL: the same scan fires on a planted backslash, so the "
          "clean result above is evidence rather than an empty loop",
          len(_pf) == 1, f"planted hits={len(_pf)}, caught by {_pf_how}")

    # ---- C46: AN imageId MUST NOT RESOLVE IN A SESSION THAT DID NOT MAKE IT --
    # `_store_image` used a module-level counter, so the Nth screenshot of EVERY
    # process was `img_N`. A recorded flow storing `img_2`, replayed in a session
    # that had taken two screenshots of anything, uploaded THAT session's second
    # capture and reported success. Reproduced with two module instances -- which
    # is what a server restart is, the registry being module state -- and a stub
    # bridge capturing the payload.
    #
    # CI STRUCTURALLY CANNOT CATCH IT, which is why a fixture has to: `run_flows`
    # takes no screenshots (they are observations, dropped at compile) so the
    # suite is always in the LOUD arm, while an MCP session where the agent has
    # been looking at the page is routinely in the silent one.
    _msA = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_msA)
    _msB = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_msB)
    _a1, _a2 = _msA._store_image(b"A-SHOT-1"), _msA._store_image(b"A-SHOT-2")
    _b1, _b2 = _msB._store_image(b"B-SHOT-1"), _msB._store_image(b"B-SHOT-2")
    check("C46 an id minted in one session does not resolve to a DIFFERENT "
          "image in another — content-addressed, so a stale id MISSES instead "
          "of uploading the wrong file silently",
          _msB.IMAGES.get(_a2) is None and _a2 != _b2,
          f"A2={_a2[:14]}… B2={_b2[:14]}… cross-resolves={_msB.IMAGES.get(_a2) is not None}")
    # NOT A CONTROL, and it was labelled one for ten minutes. It FAILS pre-fix
    # too (a counter gives the same bytes a new id every call), so it is a
    # second assertion about the new scheme rather than something that holds in
    # both arms. The ablation is what said so.
    check("C46c identical bytes share an id, so this is ADDRESSING and not just "
          "a longer counter — the same screenshot is the same screenshot",
          _msA._store_image(b"A-SHOT-1") == _a1 and _msB._store_image(b"A-SHOT-1") == _a1,
          "same bytes, same id, across two module instances")
    # THE ACTUAL CONTROL: an id minted in THIS session still resolves, and to
    # its own bytes. Without it, "never resolve anything" would satisfy C46
    # while deleting the feature.
    check("C46b CONTROL: an id minted in this session still resolves, to its "
          "own bytes — the fix must not be 'resolve nothing'",
          _msA.IMAGES.get(_a1) == b"A-SHOT-1" and _msB.IMAGES.get(_b2) == b"B-SHOT-2",
          "both sessions resolve their own ids correctly")

    print(f"\n{passed} passed, {failed} failed, {passed + failed} total checks")
    if failures:
        print("failing: " + ", ".join(failures))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
