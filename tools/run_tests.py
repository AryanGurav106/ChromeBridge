#!/usr/bin/env python
"""Run every ChromeBridge test suite as one set, and exit non-zero if any fail.

WHY THIS EXISTS
---------------
There are 13 suites and until now they were invoked by hand, one file at a
time, from a list that lived only in CLAUDE.md. `extension/background.js` is
443 KB and every suite in `tools/` exists to pin one class of regression in it,
so "run them all" is the single most valuable command in the repo and it did
not exist. Nothing stopped a change landing green because the person making it
ran the three suites they remembered.

WHAT IT DOES NOT DO
-------------------
It does not own, wrap, or normalise the suites. Each one keeps its own output
format and its own exit code; this runner only discovers them, runs them,
reports them and aggregates. **The process exit code is the source of truth.**
Where a suite's exit code is known to be wrong, that is recorded as an explicit,
named override below rather than silently patched here or in the suite.

GROUPS
------
Discovery is by source inspection, not by a hardcoded list, so a suite added
later is picked up with no edit here:

  unit     - no browser, no network, no extension. Pure Python or pure Node.
  browser  - drives headless Chromium through Playwright.

Both groups are CI-safe: every suite is offline (the browser ones serve their
own fixtures from `file://`, `page.route` interception, or an ephemeral local
HTTP server) and headless. The distinction matters because the `browser` group
needs `pip install playwright` plus a downloaded Chromium, neither of which
comes from `requirements.txt`. When those are absent the group is SKIPPED with
a reason rather than failed -- a developer without Playwright still gets a
useful run, while CI passes `--strict` so a skip there is a failure.

No `test_*` suite requires the live Chrome extension or the WebSocket bridge.
The scripts that do -- `tools/diag_*.py`, `tools/audit_*.py`,
`tools/bench_*.py`, `tools/measure_*.py` -- are live probes and benchmarks,
not pass/fail suites, and are deliberately not discovered.

USAGE
-----
    python tools/run_tests.py                  # everything
    python tools/run_tests.py --group unit     # no browser needed
    python tools/run_tests.py --only find,truncate
    python tools/run_tests.py --skip pixels
    python tools/run_tests.py --quiet          # summary table only
    python tools/run_tests.py --verbose        # stream each suite's full log
    python tools/run_tests.py --list           # inventory, run nothing
    python tools/run_tests.py --strict         # a SKIP is a failure (CI)

Suites run sequentially. They are fast (~60s for all 13) and several bind
local ports or a shared temp directory, so parallelism would buy little and
would interleave the output this runner exists to keep readable.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"

DEFAULT_TIMEOUT = 300  # seconds per suite; slowest observed is ~7s


# ---------------------------------------------------------------------------
# Per-suite overrides.
#
# Everything else is derived from the filesystem. Only facts that CANNOT be
# derived belong here, and each one names the observed behaviour it exists for.
# ---------------------------------------------------------------------------
OVERRIDES: dict[str, dict] = {
    "gaps": {
        # test_gaps.py is an INVENTORY, not a pass/fail suite: it ends with
        # `asyncio.run(main())` and no sys.exit, so it returns 0 even when it
        # reports MISSED probes. CLAUDE.md's invariant for it is "48 checks,
        # 0 MISS". Without this guard a regression that turned four probes
        # MISSED would land green. Not fixed in the suite -- runners do not
        # edit the tests they run -- so the guard is declared here, visibly.
        "fail_if": re.compile(r"\b([1-9]\d*) MISSED\b"),
        "fail_if_why": "reported MISSED probes (the suite itself always exits 0)",
        "warn_if": re.compile(r"\b([1-9]\d*) PARTIAL\b"),
        "warn_if_why": "reported PARTIAL probes",
        # It writes its results JSON to temp/dom_audit/ without creating the
        # directory. temp/ is gitignored, so on a fresh clone (i.e. every CI
        # run) that is a FileNotFoundError after all 48 probes have passed.
        "needs_dirs": ["temp/dom_audit"],
    },
}


@dataclass
class Suite:
    name: str                      # short name: "find", "gaps", "ops"
    path: Path
    runner: str                    # "python" | "node"
    group: str                     # "unit" | "browser"
    fail_if: re.Pattern | None = None
    fail_if_why: str = ""
    warn_if: re.Pattern | None = None
    warn_if_why: str = ""
    needs_dirs: list[str] = field(default_factory=list)

    @property
    def rel(self) -> str:
        try:
            return self.path.relative_to(ROOT).as_posix()
        except ValueError:      # a suite outside the repo (only ever a test rig)
            return self.path.as_posix()


@dataclass
class Result:
    suite: Suite
    status: str                    # PASS | FAIL | SKIP
    seconds: float = 0.0
    code: int | None = None
    output: str = ""
    summary: str = ""              # e.g. "67/67"
    reason: str = ""               # why it failed or was skipped
    warning: str = ""


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------
_PLAYWRIGHT_IMPORT = re.compile(r"^\s*(?:from|import)\s+playwright\b", re.M)
_JS_BROWSER = re.compile(r"require\(['\"](?:playwright|puppeteer)", re.M)


def discover(root: Path | None = None) -> list[Suite]:
    """Find every suite in tools/ and classify it by what it needs to run."""
    root = root if root is not None else TOOLS   # late-bound, so TOOLS stays overridable
    suites: list[Suite] = []

    for path in sorted(root.glob("test_*.py")):
        src = path.read_text(encoding="utf-8", errors="replace")
        group = "browser" if _PLAYWRIGHT_IMPORT.search(src) else "unit"
        suites.append(Suite(name=path.stem[len("test_"):], path=path,
                            runner="python", group=group))

    for path in sorted(root.glob("test_*.js")):
        src = path.read_text(encoding="utf-8", errors="replace")
        group = "browser" if _JS_BROWSER.search(src) else "unit"
        suites.append(Suite(name=path.stem[len("test_"):], path=path,
                            runner="node", group=group))

    for s in suites:
        ov = OVERRIDES.get(s.name)
        if ov:
            s.fail_if = ov.get("fail_if")
            s.fail_if_why = ov.get("fail_if_why", "")
            s.warn_if = ov.get("warn_if")
            s.warn_if_why = ov.get("warn_if_why", "")
            s.needs_dirs = list(ov.get("needs_dirs", []))

    suites.sort(key=lambda s: (s.group != "unit", s.name))
    return suites


# ---------------------------------------------------------------------------
# Reading a suite's own summary line
#
# Every suite prints its own tally in its own words. We scan from the END so
# that a suite printing a running total more than once (test_truncate prints
# "12/12" after its sync half and the cumulative "15/15" after its async half)
# is read at its final, complete figure.
# ---------------------------------------------------------------------------
_SUMMARY_PATTERNS = [
    # "67/67 generality checks passed."   "11/11 checks passed."
    (re.compile(r"\b(\d+)/(\d+)\b[^\n]*\bpassed\b"),
     lambda m: (int(m.group(1)), int(m.group(2)))),
    # "89 passed, 0 failed, 89 total checks"
    (re.compile(r"\b(\d+) passed,\s*(\d+) failed\b"),
     lambda m: (int(m.group(1)), int(m.group(1)) + int(m.group(2)))),
    # "14 passed, 8 not-applicable (gate off), 22 total checks" — the permissions
    # suite's armed-off form, which matched NOTHING and so contributed zero while
    # still reporting PASS. The project total silently dropped by 22 and only the
    # CLAUDE.md drift note caught it, one digit at a time. Same class as a tool
    # count that stays 31 while a tool is swapped out (#63).
    (re.compile(r"\b(\d+) passed,[^\n]*?\b(\d+) total checks\b"),
     lambda m: (int(m.group(1)), int(m.group(2)))),
    # "0 MISSED, 0 PARTIAL, 48 CAPTURED"
    (re.compile(r"\b(\d+) MISSED,\s*(\d+) PARTIAL,\s*(\d+) CAPTURED\b"),
     lambda m: (int(m.group(3)),
                int(m.group(1)) + int(m.group(2)) + int(m.group(3)))),
]


def parse_summary(output: str) -> str:
    for line in reversed([ln for ln in output.splitlines() if ln.strip()]):
        for pattern, extract in _SUMMARY_PATTERNS:
            m = pattern.search(line)
            if m:
                good, total = extract(m)
                return f"{good}/{total}"
    # A SUITE THAT PASSES AND REPORTS NO COUNT IS NOT A SUITE THAT RAN. The
    # permissions suite did exactly that for a whole session when its armed-off
    # summary matched no pattern: PASS, zero checks, total quietly 22 lower.
    return "?"


# ---------------------------------------------------------------------------
# Failure excerpts -- surface the failing lines, never the whole log
# ---------------------------------------------------------------------------
_FAIL_LINE = re.compile(r"^\s*(FAIL|MISS(?:ED)?|ERROR)\b|\bMISSED\b|^\s*E\s{3}")
_MAX_FAIL_LINES = 25
_MAX_TRACEBACK_LINES = 40
_MAX_TAIL_LINES = 30


def excerpt(output: str) -> str:
    """The lines a reader needs to know WHAT broke, bounded."""
    lines = output.splitlines()
    picked: list[str] = []

    hits = [ln for ln in lines if _FAIL_LINE.search(ln)]
    if hits:
        picked.extend(hits[:_MAX_FAIL_LINES])
        if len(hits) > _MAX_FAIL_LINES:
            picked.append(f"... {len(hits) - _MAX_FAIL_LINES} more failing line(s) not shown")

    tb_start = None
    for i, ln in enumerate(lines):
        if "Traceback (most recent call last)" in ln:
            tb_start = i
    if tb_start is not None:
        tb = lines[tb_start:]
        if len(tb) > _MAX_TRACEBACK_LINES:
            tb = [f"... traceback truncated to its last {_MAX_TRACEBACK_LINES} lines"] + \
                 tb[-_MAX_TRACEBACK_LINES:]
        if picked:
            picked.append("")
        picked.extend(tb)

    if not picked:
        tail = [ln for ln in lines if ln.strip()][-_MAX_TAIL_LINES:]
        picked = ["(no FAIL/traceback lines matched; last output follows)"] + tail

    return "\n".join(picked)


# ---------------------------------------------------------------------------
# Environment probes
# ---------------------------------------------------------------------------
_PLAYWRIGHT_PROBE = (
    "import os, sys\n"
    "from playwright.sync_api import sync_playwright\n"
    "p = sync_playwright().start()\n"
    "exe = p.chromium.executable_path\n"
    "p.stop()\n"
    "sys.exit(0 if os.path.exists(exe) else 3)\n"
)

_browser_cache: tuple[bool, str] | None = None


def browser_available() -> tuple[bool, str]:
    """Can the browser group actually run here? Cached; probed at most once."""
    global _browser_cache
    if _browser_cache is not None:
        return _browser_cache

    if os.environ.get("CHROMEBRIDGE_SKIP_BROWSER"):
        _browser_cache = (False, "CHROMEBRIDGE_SKIP_BROWSER is set")
        return _browser_cache

    try:
        proc = subprocess.run([sys.executable, "-c", _PLAYWRIGHT_PROBE],
                              cwd=str(ROOT), capture_output=True, timeout=120)
    except (subprocess.TimeoutExpired, OSError) as exc:
        _browser_cache = (False, f"Playwright probe failed: {exc}")
        return _browser_cache

    if proc.returncode == 0:
        _browser_cache = (True, "")
    elif proc.returncode == 3:
        _browser_cache = (False, "Chromium is not downloaded "
                                 "(run: python -m playwright install chromium)")
    else:
        err = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        detail = err[-1] if err else f"exit {proc.returncode}"
        if "ModuleNotFoundError" in "\n".join(err):
            detail = "playwright is not installed (run: pip install playwright)"
        _browser_cache = (False, detail)
    return _browser_cache


def node_available() -> tuple[str | None, str]:
    node = os.environ.get("NODE") or shutil.which("node")
    if not node:
        return None, "node is not on PATH"
    return node, ""


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------
def child_env() -> dict:
    env = dict(os.environ)
    # Several suites print Japanese, Arabic and box-drawing characters. When
    # their stdout is a pipe rather than a console, the Windows default cp1252
    # either mangles them or raises. The suites that reconfigure their own
    # stdout are unaffected; this makes the rest behave the same.
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def run_suite(suite: Suite, timeout: int, verbose: bool) -> Result:
    if suite.runner == "node":
        node, why = node_available()
        if not node:
            return Result(suite, "SKIP", reason=why)
        cmd = [node, str(suite.path)]
    else:
        cmd = [sys.executable, str(suite.path)]

    if suite.group == "browser":
        ok, why = browser_available()
        if not ok:
            return Result(suite, "SKIP", reason=why)

    for d in suite.needs_dirs:
        (ROOT / d).mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    chunks: list[str] = []
    timed_out = False
    try:
        proc = subprocess.Popen(cmd, cwd=str(ROOT), env=child_env(),
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        assert proc.stdout is not None

        # The read loop below blocks on the pipe, so a suite that hangs while
        # printing NOTHING (a browser that never launches, a socket that never
        # accepts) would never reach a deadline check inside it. The watchdog
        # is what actually bounds the run; killing the child closes the pipe
        # and releases the loop.
        def _kill_on_timeout() -> None:
            nonlocal timed_out
            timed_out = True
            try:
                proc.kill()
            except OSError:
                pass

        watchdog = threading.Timer(timeout, _kill_on_timeout)
        watchdog.daemon = True
        watchdog.start()
        try:
            for raw in proc.stdout:
                text = raw.decode("utf-8", "replace")
                chunks.append(text)
                if verbose:
                    sys.stdout.write("    " + text.rstrip("\r\n") + "\n")
                    sys.stdout.flush()
            code = proc.wait(timeout=30)
        finally:
            watchdog.cancel()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Result(suite, "FAIL", time.monotonic() - started, None,
                      "".join(chunks), reason=f"could not run: {exc}")

    elapsed = time.monotonic() - started
    output = "".join(chunks)
    result = Result(suite, "PASS", elapsed, code, output, parse_summary(output))

    if timed_out:
        result.status, result.reason = "FAIL", f"timed out after {timeout}s"
        return result

    # The exit code is the source of truth ...
    if code != 0:
        result.status, result.reason = "FAIL", f"exit code {code}"
        return result

    # ... except where a suite is known not to have one, in which case the
    # override that says so is declared in OVERRIDES with its evidence.
    if suite.fail_if:
        m = suite.fail_if.search(output)
        if m:
            result.status = "FAIL"
            result.reason = f"{suite.fail_if_why}: {m.group(0)}"
            return result
    if suite.warn_if:
        m = suite.warn_if.search(output)
        if m:
            result.warning = f"{suite.warn_if_why}: {m.group(0)}"

    return result


# ---------------------------------------------------------------------------
# Selection + reporting
# ---------------------------------------------------------------------------
def normalise(token: str) -> str:
    t = token.strip().lower()
    for suffix in (".py", ".js"):
        if t.endswith(suffix):
            t = t[: -len(suffix)]
    if t.startswith("test_"):
        t = t[len("test_"):]
    return t


def select(suites: list[Suite], only: str | None, skip: str | None,
           group: str) -> tuple[list[Suite], list[str]]:
    chosen = suites
    unknown: list[str] = []
    known = {s.name for s in suites}

    if group != "all":
        chosen = [s for s in chosen if s.group == group]

    if only:
        wanted = [normalise(t) for t in only.split(",") if t.strip()]
        unknown += [w for w in wanted if w not in known]
        chosen = [s for s in chosen if s.name in wanted]

    if skip:
        dropped = [normalise(t) for t in skip.split(",") if t.strip()]
        unknown += [d for d in dropped if d not in known]
        chosen = [s for s in chosen if s.name not in dropped]

    return chosen, unknown


def print_table(results: list[Result], stream=sys.stdout) -> None:
    width = max([len(r.suite.name) for r in results] + [6])
    print("", file=stream)
    print("  {:<{w}}  {:<7}  {:<7}  {:>7}  {}".format(
        "SUITE", "GROUP", "STATUS", "TIME", "CHECKS", w=width), file=stream)
    print("  " + "-" * (width + 40), file=stream)
    for r in results:
        detail = r.summary
        if r.status == "SKIP":
            detail = f"skipped: {r.reason}"
        elif r.status == "FAIL":
            detail = f"{r.summary or '-'}  <- {r.reason}"
        elif r.warning:
            detail = f"{r.summary or '-'}  (warning: {r.warning})"
        print("  {:<{w}}  {:<7}  {:<7}  {:>6.1f}s  {}".format(
            r.suite.name, r.suite.group, r.status, r.seconds, detail, w=width),
            file=stream)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="run_tests.py",
        description="Run every ChromeBridge test suite; exit non-zero if any fail.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
               "  python tools/run_tests.py --group unit\n"
               "  python tools/run_tests.py --only find,truncate\n"
               "  python tools/run_tests.py --quiet --strict\n")
    ap.add_argument("--only", metavar="A,B",
                    help="run only these suites (short names, e.g. find,truncate)")
    ap.add_argument("--skip", metavar="A,B", help="run everything except these")
    ap.add_argument("--group", choices=("all", "unit", "browser"), default="all",
                    help="'unit' needs no browser; 'browser' drives headless Chromium")
    ap.add_argument("--skip-browser", action="store_true",
                    help="shorthand for --group unit")
    ap.add_argument("-q", "--quiet", action="store_true",
                    help="print only the summary table and the total")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="stream each suite's full output as it runs")
    ap.add_argument("--strict", action="store_true",
                    help="treat a SKIPPED suite as a failure (use this in CI)")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, metavar="SEC",
                    help=f"per-suite timeout in seconds (default {DEFAULT_TIMEOUT})")
    ap.add_argument("--list", action="store_true",
                    help="print the suite inventory and exit")
    args = ap.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    suites = discover()
    if not suites:
        print(f"No suites found in {TOOLS}", file=sys.stderr)
        return 2

    group = "unit" if args.skip_browser else args.group
    chosen, unknown = select(suites, args.only, args.skip, group)

    if unknown:
        print(f"Unknown suite name(s): {', '.join(sorted(set(unknown)))}",
              file=sys.stderr)
        print(f"Known: {', '.join(s.name for s in suites)}", file=sys.stderr)
        return 2

    if args.list:
        width = max(len(s.name) for s in suites)
        print(f"{len(suites)} suite(s) in {TOOLS.relative_to(ROOT).as_posix()}/:\n")
        for s in suites:
            note = ""
            if s.fail_if:
                note = f"  [exit code unreliable -- guarded on: {s.fail_if_why}]"
            print(f"  {s.name:<{width}}  {s.group:<7}  {s.runner:<6}  {s.rel}{note}")
        print("\n  unit    = no browser, no network, no extension")
        print("  browser = headless Chromium via Playwright "
              "(pip install playwright && python -m playwright install chromium)")
        return 0

    if not chosen:
        print("No suites selected.", file=sys.stderr)
        return 2

    if not args.quiet:
        print(f"Running {len(chosen)} of {len(suites)} suite(s) from {ROOT}")

    results: list[Result] = []
    started = time.monotonic()
    for suite in chosen:
        if not args.quiet:
            print(f"\n>>> {suite.name}  ({suite.group}, {suite.rel})", flush=True)
        result = run_suite(suite, args.timeout, args.verbose and not args.quiet)
        results.append(result)
        if not args.quiet:
            if result.status == "SKIP":
                print(f"    SKIP  {result.reason}", flush=True)
            elif result.status == "PASS":
                extra = f"  (warning: {result.warning})" if result.warning else ""
                print(f"    PASS  {result.summary or 'ok'}  "
                      f"({result.seconds:.1f}s){extra}", flush=True)
            else:
                print(f"    FAIL  {result.reason}  ({result.seconds:.1f}s)",
                      flush=True)
    total_time = time.monotonic() - started

    failures = [r for r in results if r.status == "FAIL"]
    skips = [r for r in results if r.status == "SKIP"]

    if failures and not args.verbose:
        for r in failures:
            print(f"\n{'=' * 70}")
            print(f"FAILED: {r.suite.name}  ({r.suite.rel})  -- {r.reason}")
            print("=" * 70)
            print(excerpt(r.output))

    print_table(results)

    passed = [r for r in results if r.status == "PASS"]
    checks = 0
    for r in results:
        if r.summary and "/" in r.summary:
            try:
                checks += int(r.summary.split("/")[1])
            except ValueError:
                pass

    print("")
    print(f"  {len(passed)} passed, {len(failures)} failed, {len(skips)} skipped "
          f"of {len(results)} suite(s); {checks} checks; {total_time:.1f}s")

    # DOC DRIFT IS SELF-DETECTING NOW, because this is the only thing that knows
    # the true count. CLAUDE.md states the total in two places and it had gone
    # stale three times over (502 in the docs against 475, 498 and then 532 in
    # reality) — the file's own guidance says "quote counts from --list and a real
    # run, not from memory", which is advice a human has to remember to follow. An
    # attempt to fix it by hand also silently no-opped, because the sed pattern
    # matched nothing and said so to nobody. A whole-suite run is the moment the
    # answer is known, so it is the right moment to notice. Advisory, never a
    # failure: the count is documentation, not behaviour, and a wrong number in a
    # comment must not break someone's build.
    # `--group` DEFAULTS TO "all", which is truthy — so the first version of this
    # gate (`not args.group`) never ran, and the notice stayed silent against a
    # deliberately wrong count. Caught by planting 999 in the doc and watching
    # nothing happen, not by reading the condition.
    if args.group in (None, "all") and not getattr(args, "only", None) \
            and not getattr(args, "skip", None) and not args.skip_browser:
        # THE COUNT NOW LIVES IN THREE FILES, so scanning one is the drift this
        # check was written to end, one file over. README.md is the front door
        # and tools/README.md says of its own tables that `--list` "cannot drift
        # the way the tables below can" — both had the number, and both were
        # wrong (344 against 1038) while this notice reported CLAUDE.md as clean.
        # Same pattern, same advisory handling, no second spelling (#21).
        for _doc in ("README.md", "tools/README.md"):
            try:
                _t = (ROOT / _doc).read_text(encoding="utf-8")
                # Anchored on "suite" appearing shortly before, not on one
                # spelling of the separator: the two files write it as
                # "19 suites, 1038 checks" and "of 19 suite(s); 1038 checks",
                # and a pattern fitting one silently skipped the other — which
                # is the failure mode of the check directly below this.
                _st = {int(m.group(1).replace(",", ""))
                       for m in re.finditer(r"([\d,]+) checks", _t)
                       if "suite" in _t[max(0, m.start() - 40):m.start()]}
                if _st and checks and _st != {checks}:
                    print(f"  note: {_doc} says "
                          f"{'/'.join(str(x) for x in sorted(_st))} checks, this run"
                          f" counted {checks}")
            except Exception:
                pass
        try:
            _md = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
            # THE SUITE COUNT IS NOT PART OF THE PATTERN. This read `17 suites,
            # (\d+) checks` and CLAUDE.md has said 18 since the batch suite landed,
            # so it matched NOTHING and reported NOTHING for every run since — the
            # exact silent no-op #30 wrote this check to end, reappearing inside the
            # check itself. A detector that cannot fire is worth less than none,
            # because it is also a claim that nothing is wrong. Hence the second
            # branch: if the anchor is gone, say so instead of passing quietly.
            _stated = {int(m) for m in re.findall(r"\d+ suites, (\d+) checks", _md)}
            if not _stated:
                print("  note: CLAUDE.md has no 'N suites, M checks' line any more —"
                      " this drift check is inert until one is restored")
            elif checks and _stated != {checks}:
                print(f"  note: CLAUDE.md says {'/'.join(str(s) for s in sorted(_stated))}"
                      f" checks, this run counted {checks} — update the two"
                      f" current-state lines (the per-section 'Suites: N checks'"
                      f" figures are history and stay as they are)")
        except Exception:
            pass

    if skips:
        print(f"  skipped: {', '.join(r.suite.name for r in skips)}")
        if args.strict:
            print("  --strict: a skipped suite is a failure")
    for r in results:
        if r.warning:
            print(f"  warning: {r.suite.name}: {r.warning}")

    if failures:
        print(f"  FAILED: {', '.join(r.suite.name for r in failures)}")
        return 1
    if skips and args.strict:
        return 1
    # "ALL GREEN" over zero passing suites would be the runner's own version of
    # the failure mode half these suites exist to prevent: a confident report
    # about something that never happened.
    print("  ALL GREEN" if passed else "  NOTHING RAN (every selected suite was skipped)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
