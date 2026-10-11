"""Replay recorded flows headlessly, in CI. The thing that makes them a suite.

    python tools/run_flows.py                      # every flow in flows/
    python tools/run_flows.py checkout --headed    # one, visibly
    python tools/run_flows.py --vars '{"project_name":"ci-run"}'

Until this existed, a flow only ran when a human drove it through an MCP
session, which is the opposite of a regression suite: #49 shipped with "no
headless/CI runner" as a stated gap, and a test nobody can run on a commit is
a demo.

HOW IT DIFFERS FROM EVERY OTHER SUITE HERE. The browser suites inject page
functions directly and never cross the two boundaries that decide whether the
code runs at all (#30). This one drives the WHOLE stack -- a real Chrome, the
real unpacked extension, the real WebSocket bridge, the real op router, the
real MCP tool functions -- so it exercises exactly the links that have shipped
broken behind green fixtures: `detail="brief"` (#19), `delta` (#30), the
recording wrapper that refused every batch (#49).

THE PERMISSION GATE IS NOT BYPASSED, it is granted. Flows name an origin, and
the gate's rule is that a grant comes from a human clicking in extension UI
(background.js never writes `bridge_permissions`). Here the profile is a
throwaway created and destroyed by this script, and the grant is written into
ITS storage before the run -- which is the same thing a human does in the
panel, for a browser that exists for twelve seconds. It cannot reach the
user's own Chrome: the profile is empty and the bridge is on a port outside
the default 8765-8774 span, so the extension the user has loaded never sees it.

EXIT CODE is the point: 0 when every flow passed, 1 otherwise, so this belongs
in CI next to run_tests.py.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import re
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.bridge.server import ExtensionBridge  # noqa: E402
from core.flows.model import load as flow_load  # noqa: E402
from core.flows.runner import PASSED, start as flow_start  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

EXT = ROOT / "extension"
FLOWS = ROOT / "flows"
PORT = 8901          # outside the default span, on purpose -- see the docstring


def _load_server():
    """The REAL mcp_server, tools and all.

    Imported rather than reimplemented: the flow runner calls MCP tool
    functions, and a CI harness that called the bridge directly would be
    testing a path no agent uses (#19's standing warning, and the reason
    measure_retention imports the real find() scorer).
    """
    spec = importlib.util.spec_from_file_location("ms_flows", ROOT / "mcp_server.py")
    ms = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ms)
    return ms


async def _grant(ctx, ext_id: str, origins: list, token: str) -> None:
    page = await ctx.new_page()
    await page.goto(f"chrome-extension://{ext_id}/panel.html")
    await page.wait_for_timeout(200)
    now = int(time.time() * 1000)
    await page.evaluate(
        "s => chrome.storage.local.set(s)",
        {"bridge_host": "127.0.0.1", "bridge_port": PORT,
         # Without the TOKEN the extension has nothing to handshake with and
         # the wait below times out with no hint that a credential is missing
         # -- which is the #17 first-run bug in miniature.
         "bridge_token": token,
         "bridge_permissions": {"origins": {o: {"granted": now} for o in origins}}},
    )
    await page.close()


def _origins(flows: list) -> list:
    """Every origin the selected flows navigate to, from the flows themselves."""
    out = set()
    for f in flows:
        if f.origin:
            out.add(f.origin)
        for st in f.steps:
            u = (st.input or {}).get("url")
            if isinstance(u, str):
                m = re.match(r"^(https?://[^/]+)", u)
                if m:
                    out.add(m.group(1))
        for v in (f.require or {}).values():
            if isinstance(v, str):
                m = re.match(r"^(https?://[^/]+)", v)
                if m:
                    out.add(m.group(1))
    return sorted(out)


def _fixture_secret_names(flows) -> list:
    """Every ${CHROMEBRIDGE_SECRET:NAME} a LOCAL-FIXTURE flow references."""
    out, pre = [], "${CHROMEBRIDGE_SECRET:"
    for f in flows:
        blob = json.dumps([s_.to_json() for s_ in f.steps], default=str)
        if "127.0.0.1:8787" not in (f.origin or "") and "127.0.0.1:8787" not in blob:
            continue
        for frag in blob.split(pre)[1:]:
            out.append(frag.split("}")[0])
    return sorted(set(out))


def _pg_reset(chaos: str = "") -> None:
    """Seed state, then flags. ORDER IS THE POINT: /api/reset clears chaos."""
    import urllib.request as _u
    try:
        _u.urlopen(_u.Request("http://127.0.0.1:8787/api/reset", method="POST"), timeout=2)
    except Exception:
        return
    flags = [f.strip() for f in (chaos or "").split(",") if f.strip()]
    if not flags:
        return
    try:
        _u.urlopen(_u.Request("http://127.0.0.1:8787/api/chaos", method="POST",
                              data=json.dumps({"flags": flags}).encode(),
                              headers={"Content-Type": "application/json"}), timeout=2)
    except Exception as exc:
        print(f"  could not set chaos flags: {exc}")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("flow", nargs="*", help="flow names; default every flows/*.flow.json")
    ap.add_argument("--headed", action="store_true", help="show the browser")
    ap.add_argument("--vars", default="", help="JSON overrides applied to every flow")
    ap.add_argument("--playground", action="store_true",
                    help="start tools/saas_playground.py for the run and stop it after")
    ap.add_argument("--local-only", action="store_true",
                    help="skip flows that touch a non-loopback origin; what CI wants, "
                         "because a suite that needs the public internet fails for "
                         "reasons that are not the code's")
    ap.add_argument("--chaos", default="",
                    help="comma-separated saas_playground chaos flags to set AFTER "
                         "the reset (needs --playground). Use it to script a "
                         "falsifier, or to prove a fix end to end: --chaos badge "
                         "renames a nav link without touching its href.")
    ap.add_argument("--check-only", action="store_true",
                    help="load and validate every flow WITHOUT a browser. CI can "
                         "only REPLAY the local-fixture flows -- the rest need the "
                         "public internet and would fail for reasons that are not "
                         "the code's -- so nothing was checking that they still "
                         "PARSE. A format change (the expect shape grew lists, the "
                         "on_fail enum lost a value) can orphan a recorded file "
                         "silently, and the only signal would be a SKIP line that "
                         "looks identical to a healthy skip.")
    ap.add_argument("--token", default="")
    args = ap.parse_args()

    paths = ([FLOWS / (n if n.endswith(".flow.json") else n + ".flow.json")
              for n in args.flow] if args.flow
             else sorted(FLOWS.glob("*.flow.json")))
    missing = [p for p in paths if not p.exists()]
    if missing:
        print("no such flow: " + ", ".join(p.name for p in missing))
        return 1
    if not paths:
        print("no flows to run")
        return 0

    if args.check_only:
        bad, ok = [], 0
        for pth in paths:
            try:
                f = flow_load(pth)
            except Exception as exc:
                bad.append(f"  BAD   {pth.name}: {type(exc).__name__}: {exc}")
                continue
            # Beyond "it parses": a step that NAMES a ref must carry a descriptor
            # for it, or the file is a recording of nothing. That is the shape a
            # compile bug would leave behind, and it loads fine.
            holes = [i for i, st in enumerate(f.steps)
                     if st.targets and any(not (t or {}).get("desc")
                                           for t in st.targets.values())]
            if holes:
                bad.append(f"  BAD   {pth.name}: step(s) {holes} name a target with no descriptor")
                continue
            ok += 1
            print(f"  OK    {f.name:<32} {len(f.steps)} step(s), "
                  f"{sum(1 for s_ in f.steps if s_.expect)} asserted")
        for line in bad:
            print(line)
        print(f"\n  {ok}/{len(paths)} flow file(s) valid")
        return 0 if not bad else 1

    # THE PLAYWRIGHT GATE BELONGS BELOW --check-only, NOT ABOVE IT. It used to
    # run first, so `--check-only` -- which opens no browser and exists
    # precisely so a machine without one can still validate every file --
    # printed a SKIP and returned 0. Measured on a fresh clone with no
    # playwright: zero files checked, exit 0, and a line that reads exactly
    # like a healthy skip. That is the failure this flag's own docstring
    # describes, in the flag itself, and CI could never see it because CI
    # installs playwright.
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("SKIP run_flows: playwright is a TEST-only dependency and is not "
              "installed. Install it or run with --headed under a real Chrome. "
              "(--check-only needs no browser and runs without it.)")
        return 0

    flows = [flow_load(p) for p in paths]
    if args.local_only:
        keep, skipped = [], []
        for f, pth in zip(flows, paths):
            ext = [o for o in _origins([f])
                   if not re.match(r"^https?://(127\.0\.0\.1|localhost|\[::1\])\b", o)]
            (skipped if ext else keep).append((f, pth, ext))
        for f, _pth, ext in skipped:
            print(f"  SKIP  {f.name:<28} needs {', '.join(ext)}")
        flows = [f for f, _p, _e in keep]
        paths = [p_ for _f, p_, _e in keep]
        if not flows:
            print("\n  no local flows to run")
            return 0
    overrides = json.loads(args.vars) if args.vars else None
    origins = _origins(flows)
    token = args.token or ("ciflows-" + os.urandom(8).hex())

    pg = None
    if args.playground:
        import subprocess
        # STDERR IS KEPT, because a fixture that dies on startup -- port 8787
        # already in use is the common one -- took its reason to /dev/null with
        # it and the run then failed three layers away.
        pg = subprocess.Popen([sys.executable, str(ROOT / "tools" / "saas_playground.py")],
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        import urllib.request
        # AND THE WAIT IS NOT BEST-EFFORT. This loop tried for ~5s and then fell
        # through whether or not anything was listening, so when the fixture was
        # slow on a cold CI runner the flows ran against NOTHING and the failure
        # read as `ChromeBridge cannot act on about:blank` and `NAVIGATION DID
        # NOT COMMIT` -- both true, neither the cause. Measured: that is exactly
        # how a CI run failed, and the log said nothing about the server.
        up, waited = False, 0.0
        while waited < 30.0:
            if pg.poll() is not None:
                break
            try:
                urllib.request.urlopen("http://127.0.0.1:8787/api/state", timeout=0.5)
                up = True
                break
            except Exception:
                await asyncio.sleep(0.2)
                waited += 0.2
        if not up:
            err = ""
            if pg.poll() is not None:
                try:
                    # THE LAST LINE, not the last 400 characters: a traceback's
                    # tail sliced by length lands mid-frame, and the one line
                    # that names the fault (`OSError: [Errno 48] Address
                    # already in use`) is the last one.
                    _raw = (pg.stderr.read() or b"").decode("utf-8", "replace")
                    _lines = [l.strip() for l in _raw.splitlines() if l.strip()]
                    err = _lines[-1][:300] if _lines else ""
                except Exception:
                    pass
            print(f"FAIL: the fixture app never answered on 127.0.0.1:8787 after "
                  f"{waited:.0f}s"
                  + (f" — it exited with code {pg.returncode}" if pg.poll() is not None
                     else " — it is still running but not serving")
                  + ". Nothing was replayed. The usual cause is port 8787 already "
                    "being in use by an earlier run."
                  + (f"\n  its stderr: {err}" if err else ""))
            pg.terminate()
            return 1
        if waited > 2:
            print(f"  fixture app came up after {waited:.1f}s")
        # A known starting state, or the flow's own precondition is measuring
        # whatever the last run left behind.
        _pg_reset(args.chaos)
        if args.chaos:
            print(f"  chaos: {args.chaos}")
        # THE FIXTURE'S OWN SEEDED CREDENTIAL, for every flow that asks for one.
        # Derived from the flows being run rather than named one at a time: the
        # secret's env name is built from the flow name, so a hardcoded list
        # goes stale the moment a second fixture flow is recorded -- which is
        # what #42 deleted `_OBSERVES` for. Only flows pointed AT the fixture
        # are seeded, since nothing else here could be this password.
        for _name in _fixture_secret_names(flows):
            os.environ.setdefault(_name, "demo-pass-1234")

    ms = _load_server()
    bridge = ExtensionBridge(host="127.0.0.1", port=PORT, token=token)
    await bridge.start()
    # The server's own tools talk to whatever _bridge() returns, so point it at
    # the bridge this script owns rather than letting it start a second one.
    ms.STATE["bridge"] = bridge

    results = []
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir="",
            headless=False,
            args=([f"--disable-extensions-except={EXT}", f"--load-extension={EXT}"]
                  + ([] if args.headed else ["--headless=new"])),
            viewport={"width": 1280, "height": 900},
        )
        try:
            sw = (ctx.service_workers[0] if ctx.service_workers
                  else await ctx.wait_for_event("serviceworker", timeout=20000))
            ext_id = sw.url.split("/")[2]
            await _grant(ctx, ext_id, origins, token)
            try:
                await bridge.wait_until_connected(timeout=30)
            except Exception:
                print("FAIL: the extension never connected to the bridge on "
                      f"127.0.0.1:{PORT}. The throwaway profile was seeded with "
                      "host, port and token, so this is the extension failing to "
                      "load or the handshake being refused -- run with --headed "
                      "and open the side panel to see which.")
                return 1

            tab = await ms.tabs_create_mcp()
            tab_id = int(json.loads(tab)["tabId"]) if tab.strip().startswith("{") \
                else int(re.search(r'"tabId":\s*(\d+)', tab).group(1))

            for flow, path in zip(flows, paths):
                # A FIXTURE RESET PER FLOW, not per run. Resetting once meant
                # the first mutating flow poisoned every flow after it:
                # acme-create-project adds a project, so acme-nav-badge's
                # recorded `4 rows` met 5 and failed at step 1 -- which is #54's
                # "a mutating flow is not re-runnable in place" one level up,
                # between flows rather than between runs. Each flow gets the
                # state it was recorded against, which is what a per-test
                # fixture means.
                if args.playground:
                    _pg_reset(args.chaos)
                t0 = time.time()
                try:
                    res = await flow_start(flow, tab_id, ms._flow_call,
                                           ms._flow_entries, overrides=overrides,
                                           viewport_fn=ms._flow_viewport)
                except Exception as exc:
                    res = {"status": "failed", "flow": flow.name, "at": 0,
                           "of": len(flow.steps), "reason": f"{type(exc).__name__}: {exc}",
                           "log": [], "patches": [], "candidates": [],
                           "seconds": round(time.time() - t0, 2)}
                results.append(res)
                mark = "PASS" if res["status"] == PASSED else "FAIL"
                print(f"  {mark}  {flow.name:<28} {res['at']}/{res['of']} step(s) "
                      f"in {res['seconds']}s")
                for d in (res.get("drifted") or []):
                    # A pass that matched on a different key than it recorded is
                    # still a pass, and still news: the page's labels moved.
                    # SAME SENTENCE AS mcp_server's run_flow renderer. Two
                    # renderers for one result object had drifted to "; matched"
                    # and " — matched" (#21: one concept, two spellings), so a
                    # reader grepping for the phrase found it under one only.
                    print(f"        step {d['step']} {d['name']}: name "
                          f"{(d.get('was') or {}).get('name')!r} is gone; matched "
                          f"href={(d.get('alt') or {}).get('href')!r}")
                if res["status"] != PASSED:
                    print(f"        {res['reason']}")
        finally:
            await ctx.close()
            await bridge.stop()
            if pg is not None:
                pg.terminate()

    ok = sum(1 for r in results if r["status"] == PASSED)
    print(f"\n  {ok}/{len(results)} flow(s) passed")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
