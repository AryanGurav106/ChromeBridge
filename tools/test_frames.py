"""Cross-origin iframe geometry — the last untested cluster.

Audit findings A1/A15/A16 all live here, the blast radius is payment and consent flows
(Stripe Elements, TCF CMPs), and it was written off as "runtime-only, Playwright can't
exercise chrome.* APIs". That is true of `collectCrossFrames` itself, but NOT of the part
that actually broke: the GEOMETRY. Two local HTTP servers on different ports are two real
origins, so the frames really are cross-origin and the maths can be checked exactly.

What this pins:
  - `_frameShellsPage` finds cross-origin shells and skips same-origin/hidden/tiny ones.
  - frame-local coords + shell offset == the element's true top-document position, which is
    what CDP trusted input needs.
  - shells re-measure correctly after a scroll (the stale-offset bug).
  - identically-sized sibling frames stay distinguishable by src — the Stripe expiry/CVC
    case where matching by size clicked the wrong field even with zero scrolling.

Run:  python tools/test_frames.py
"""

import asyncio
import http.server
import socket
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import threading
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _extract import extract as _shared_extract  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BG = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")


def extract(name: str) -> str:
    """Delegates to tools/_extract, which skips comments/strings/regexes.

    The brace counter this replaced also counted braces inside comments, so one
    `{` in prose silently sliced in the wrong amount of code and the failure
    surfaced somewhere unrelated.
    """
    return _shared_extract(name, BG, verify=True)


SHELLS = extract("_frameShellsPage")
COLLECT = extract("_collectInteractivePage")

CHILD = """<!DOCTYPE html><meta charset="utf-8"><body style="margin:0">
<button id="b" style="position:absolute;left:20px;top:12px;width:100px;height:30px">Field {n}</button>
</body>"""


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def serve(port: int, pages: dict):
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = pages.get(self.path, pages.get("/", "")).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


async def main():
    p_child, p_parent = free_port(), free_port()
    child_pages = {f"/f{i}.html": CHILD.replace("{n}", str(i)) for i in (1, 2, 3)}
    # Three cross-origin frames. f2 and f3 are IDENTICALLY SIZED siblings — the Stripe
    # expiry/CVC shape that broke size-based shell matching. f4 is same-origin (must be
    # skipped by _frameShellsPage), f5 is a tracking-pixel-sized frame (also skipped).
    parent = f"""<!DOCTYPE html><meta charset="utf-8"><body style="margin:0">
      <div style="height:80px"></div>
      <iframe src="http://127.0.0.1:{p_child}/f1.html" style="position:absolute;left:40px;top:100px;width:300px;height:60px;border:0"></iframe>
      <iframe src="http://127.0.0.1:{p_child}/f2.html" style="position:absolute;left:40px;top:200px;width:150px;height:60px;border:0"></iframe>
      <iframe src="http://127.0.0.1:{p_child}/f3.html" style="position:absolute;left:220px;top:200px;width:150px;height:60px;border:0"></iframe>
      <iframe srcdoc="<button>same origin</button>" style="position:absolute;left:40px;top:300px;width:200px;height:60px;border:0"></iframe>
      <iframe src="http://127.0.0.1:{p_child}/f1.html" style="position:absolute;left:40px;top:400px;width:10px;height:10px;border:0"></iframe>
      <div style="height:1600px"></div>
    </body>"""
    s1 = serve(p_child, child_pages)
    s2 = serve(p_parent, {"/": parent})

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 900, "height": 700})
            await page.goto(f"http://127.0.0.1:{p_parent}/")
            await page.wait_for_timeout(400)

            async def shells():
                return await page.evaluate("(function(){ " + SHELLS + "; return _frameShellsPage(); })()")

            sh = await shells()
            check("finds exactly the 3 real cross-origin shells (same-origin + tiny skipped)",
                  len(sh) == 3, f"got {len(sh)}: {[(s['w'], s['h']) for s in sh]}")
            check("shells carry src (identity, not just geometry)",
                  all(s.get("src") for s in sh), str([s.get("src", "")[-9:] for s in sh]))

            same_size = [s for s in sh if s["w"] == 150 and s["h"] == 60]
            check("the two identically-sized siblings are present and distinguishable by src",
                  len(same_size) == 2 and same_size[0]["src"] != same_size[1]["src"],
                  f"srcs={[s['src'][-8:] for s in same_size]}")

            # THE CORE ASSERTION: frame-local coords + shell offset == true top-doc position.
            for i, name in ((1, "f1.html"), (2, "f2.html"), (3, "f3.html")):
                frame = next(f for f in page.frames if f.url.endswith(name))
                raw = await frame.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(true); })()")
                ent = next((e for e in raw if (e.get("text") or "").startswith("Field")), None)
                shell = next(s for s in sh if s["src"].endswith(name))
                truth = await (await frame.query_selector("#b")).bounding_box()  # top-doc CSS px
                ok = ent is not None and abs(ent["x"] + shell["x"] - truth["x"]) <= 2 \
                                     and abs(ent["y"] + shell["y"] - truth["y"]) <= 2
                check(f"{name}: frame-local + shell offset == true top-document position",
                      ok,
                      f"computed=({ent['x'] + shell['x']},{ent['y'] + shell['y']}) truth=({round(truth['x'])},{round(truth['y'])})"
                      if ent else "element entry missing from in-frame collection")

            # SCROLL: the offsets cached at collection time go stale; re-measuring must track.
            before = {s["src"]: s["y"] for s in sh}
            await page.evaluate("window.scrollTo(0, 250)")
            await page.wait_for_timeout(150)
            after = await shells()
            moved = all(abs((before[s["src"]] - s["y"]) - 250) <= 2 for s in after)
            check("after scrolling 250px, re-measured shells move by exactly 250px",
                  moved, f"deltas={[before[s['src']] - s['y'] for s in after]}")

            frame = next(f for f in page.frames if f.url.endswith("f3.html"))
            raw = await frame.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(true); })()")
            ent = next(e for e in raw if (e.get("text") or "").startswith("Field"))
            shell_now = next(s for s in after if s["src"].endswith("f3.html"))
            shell_stale = next(s for s in sh if s["src"].endswith("f3.html"))
            truth = await (await frame.query_selector("#b")).bounding_box()
            check("f3 after scroll: RE-MEASURED offset is correct",
                  abs(ent["y"] + shell_now["y"] - truth["y"]) <= 2,
                  f"computed={ent['y'] + shell_now['y']} truth={round(truth['y'])}")
            check("f3 after scroll: STALE cached offset would have been wrong (bug reproduced)",
                  abs(ent["y"] + shell_stale["y"] - truth["y"]) > 100,
                  f"stale={ent['y'] + shell_stale['y']} truth={round(truth['y'])}")

            await browser.close()
    finally:
        s1.shutdown()
        s2.shutdown()

    passed = sum(1 for r in results if r)
    print(f"\n{passed}/{len(results)} cross-origin frame checks passed.")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
