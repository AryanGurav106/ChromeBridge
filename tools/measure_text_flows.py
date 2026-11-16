"""TEXT sufficiency, measured through the flow recorder. `OPEN.md` item 12's open half.

WHY THIS EXISTS, AND WHY THE OBVIOUS PROBE COULD NOT
----------------------------------------------------
`measure_sufficiency.py` prices the listing of CONTROLS: given the target is on
the page, does the listing distinguish it (DS | reachable = 0.933). It says
nothing about prose or table data, and the source paper (arXiv:2605.29397,
Table 3) measures TEXT as the single largest contributor to the minimal failure
set -- 30.5 / 59.5 coverage drop when ablated, against 4.8-13.6 for any control
type.

`measure_text_sufficiency.py` is the design that was tried and REFUTED: it
loads the urls an eval agent visited and looks for the answer. It cannot work,
and its own docstring says why -- `tasks.md` records `Interactions needed` per
task and 0 of 22 need zero, so a static load of a url can never contain a value
the agent produced BY INTERACTING. It measures how many eval tasks are two-hop,
which is 100%.

The separation that design lacks is between "the text surface failed to carry
it" and "the value did not exist yet", and a RECORDED FLOW is exactly the thing
that provides it: `run_flow(stop_after=N)` replays to step N and stops with the
page in the state that step left it -- a validation message, a filtered table,
a created row -- which a fresh navigate to the same url cannot reproduce.

WHAT IS MEASURED, as the paper's ablation rather than as a success rate
----------------------------------------------------------------------
The paper ablates an element type from the representation and measures the
coverage drop. Our analogue is exact and costs nothing to run, because
`read_page`'s own `filter` parameter IS the ablation:

    read_page(filter="all")          controls + page text   <- the default
    read_page(filter="interactive")  controls ONLY          <- TEXT ABLATED

So, per required value, in the state a flow left behind:

    TEXT-DEPENDENT   the controls-only listing does not carry it
    CARRIED          some text surface does
    LOST             no surface does

  text_dependence = TEXT-DEPENDENT / scored          (our Table-3 "Text" row)
  TS              = CARRIED / TEXT-DEPENDENT         (quote this one)

Each of `read_page(filter="all")`, `get_page_text`, `search_page` and
`query_elements` is scored separately, so the answer says WHICH tool carries
the text surface rather than asserting that "the text surface" does.

WHERE THE LABELS COME FROM -- the whole non-circularity argument
----------------------------------------------------------------
A ground truth derived from the thing being measured is worthless, and this
probe has three defences, in the same shape `measure_sufficiency.py` uses:

(a) THE VALUES ARE READ BY PLAYWRIGHT, NOT BY US. Every required value and
    every table association is computed by `page.evaluate` in the browser,
    through Playwright's own CDP session. No ChromeBridge code runs in that
    path -- not the collector, not `_domTextPage`, not the op router. If our
    text surface and Chrome's rendering disagree, the probe sides with Chrome.

(b) THE QUESTIONS ARE GENERATED, NOT AUTHORED. Nobody writes a task. Every
    visible leaf text block that contains no control, and every (row key,
    column key) -> cell triple of every visible table, becomes an item. I do
    not get to choose which values count, which is what would otherwise let me
    pick the ones we handle well.

(c) THE RECORDED ASSERTIONS ARE NOT THE LABELS. A flow's `expect` blocks were
    written by whoever recorded it USING THESE TOOLS, so scoring against them
    would be asking whether `search_page` finds what `search_page` found. They
    are never read here. The flows are used only to reach a state.

What (a)-(c) still cannot remove: I chose which flows to record against the
fixture, and the fixture is one app. See LIMITS.

WHAT THIS CANNOT ANSWER -- before the number, not after it
-----------------------------------------------------------
  * CARRIED means the value is in the output. It does not mean a model finds
    it, reads it correctly, or asks the right tool. This is necessary, not
    sufficient -- the same bound `SUFFICIENCY.md` puts on DS.
  * `query_elements` is scored with a GENERATED selector (the element's own tag
    path), which is an UPPER bound: an agent has to guess the selector, and
    #39's census exists because agents often cannot.
  * The association test for a table is "can a reader recover the value from
    the row key and the column key". A line carrying both is scored paired.
    That is weaker than a human reading a grid and stronger than presence.
  * The fixture corpus is `tools/saas_playground.py`, which I did not write but
    did select states from. The `ev-*` corpus is real third-party pages
    recorded by agents who had no idea this measurement would exist; it is the
    better sample and the one that drifts.

Run:
    python tools/measure_text_flows.py --record          # record the fixture flows
    python tools/measure_text_flows.py --measure         # score them
    python tools/measure_text_flows.py --measure --replicates 2   # drift floor
    python tools/measure_text_flows.py --measure --corpus ev      # live sites
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.bridge.server import ExtensionBridge  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

EXT = ROOT / "extension"
FLOWS = ROOT / "flows"
PORT = 8904            # outside the default 8765-8774 span AND outside run_flows' 8901
PG = "http://127.0.0.1:8787"
STATE_DIR = None        # set from --out; every arm's raw output lands here

# A state is read only once it has stopped changing. #70's recency window is
# 3000ms wide, so a read taken sooner carries a banner that is TRUE and
# consumes budget; and reading a page that is still painting measures the
# collector's timing rather than the text surface. This is the one wall-clock
# constant here and it is the window's own width, not a guess.
SETTLE_S = 3.4


# ---------------------------------------------------------------------------
# normalisation -- one spelling, used by every comparison in this file
# ---------------------------------------------------------------------------
def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", str(s or ""))


def norm_line(s: str) -> str:
    """Collapse intra-line whitespace, KEEP newlines. For association tests."""
    s = _nfc(s).replace(" ", " ").replace("​", "")
    s = re.sub(r"[ \t　]+", " ", s)
    return "\n".join(l.strip() for l in s.split("\n"))


def norm_flat(s: str) -> str:
    """Collapse ALL whitespace. For presence tests."""
    return re.sub(r"\s+", " ", norm_line(s)).strip()


# ---------------------------------------------------------------------------
# THE INDEPENDENT GROUND TRUTH. Runs in the page under PLAYWRIGHT's own CDP
# session -- no part of ChromeBridge is involved, which is defence (a).
#
# Two generators, both mechanical:
#   blocks  every visible LEAF text block holding no control and inside none
#   cells   every (row key, column key, value) of every visible table, with
#           colspan/rowspan expanded, so the question "what is <col> for <row>"
#           is the table's own structure rather than something I wrote
# ---------------------------------------------------------------------------
SWEEP_JS = r"""
() => {
  const INTER = 'a,button,input,select,textarea,summary,option,[role=button],'
    + '[role=link],[role=checkbox],[role=radio],[role=textbox],[role=combobox],'
    + '[role=option],[role=menuitem],[role=menuitemcheckbox],[role=menuitemradio],'
    + '[role=tab],[role=switch],[role=slider],[role=spinbutton],[role=searchbox],'
    + '[contenteditable],[tabindex],[onclick]';
  const vis = el => {
    try { return el.checkVisibility({opacityProperty:true, visibilityProperty:true}); }
    catch (_) { return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length); }
  };
  const txt = el => (el.innerText || el.textContent || '');
  // A STRUCTURAL selector for one element, so the `query_elements` arm can be
  // asked without anyone authoring a selector. It is an UPPER bound on that
  // tool by construction -- a real agent has to guess this one.
  const sel = el => {
    const parts = [];
    let n = el;
    while (n && n.nodeType === 1 && n.tagName !== 'BODY' && parts.length < 12) {
      const t = n.tagName.toLowerCase();
      let i = 1, s = n;
      while ((s = s.previousElementSibling)) if (s.tagName === n.tagName) i++;
      parts.unshift(t + ':nth-of-type(' + i + ')');
      n = n.parentElement;
    }
    return 'body > ' + parts.join(' > ');
  };

  // ---- table triples -------------------------------------------------
  const cells = [];
  let ti = -1;
  for (const t of document.querySelectorAll('table')) {
    ti++;
    if (!vis(t)) continue;
    // Expand the grid the way HTML defines it: colSpan widens a cell across
    // columns, rowSpan carries it down. Counting cell ELEMENTS instead is the
    // defect #51 fixed in our own hint, so the ruler must not repeat it.
    const grid = [];
    const pending = {};           // col -> {rows left, text, isHeader}
    for (const tr of t.rows) {
      const row = [];
      let c = 0;
      const put = (v) => { while (row[c] !== undefined) c++; row[c] = v; };
      for (const td of tr.cells) {
        while (row[c] !== undefined) c++;
        const v = {text: txt(td).trim(), th: td.tagName === 'TH', el: td};
        for (let k = 0; k < (td.colSpan || 1); k++) {
          row[c + k] = v;
          if ((td.rowSpan || 1) > 1) pending[c + k] = {left: (td.rowSpan || 1) - 1, v};
        }
        c += (td.colSpan || 1);
      }
      for (const k of Object.keys(pending)) {
        const i = +k;
        if (row[i] === undefined && pending[k].left > 0) { row[i] = pending[k].v; pending[k].left--; }
      }
      grid.push(row);
    }
    if (grid.length < 2) continue;
    // Header = the LAST row of <thead>, or the first all-<th> row.
    let hdr = -1;
    const thead = t.tHead;
    if (thead && thead.rows.length) {
      hdr = Array.prototype.indexOf.call(t.rows, thead.rows[thead.rows.length - 1]);
    } else {
      for (let i = 0; i < grid.length; i++) {
        const r = grid[i].filter(Boolean);
        if (r.length && r.every(x => x.th)) { hdr = i; break; }
      }
    }
    if (hdr < 0) continue;
    const head = grid[hdr].map(x => (x ? x.text : ''));
    for (let i = hdr + 1; i < grid.length; i++) {
      const row = grid[i];
      if (!row || !row.filter(Boolean).length) continue;
      const key = (row.find(Boolean) || {}).text || '';
      if (!key) continue;
      for (let j = 0; j < row.length; j++) {
        if (!row[j] || row[j].th) continue;
        const val = row[j].text;
        if (!val || val === key) continue;
        cells.push({table: ti, row: i, col: j, rowKey: key,
                    colKey: head[j] || '', value: val, sel: sel(row[j].el),
                    rowSel: sel(t.rows[i])});
      }
    }
  }

  // ---- prose blocks ---------------------------------------------------
  // A LEAF block: holds its own text, holds no control, sits inside no
  // control, and has no descendant that also qualifies (so a wrapper does not
  // swallow three paragraphs into one item).
  const blocks = [];
  const cand = [];
  const all = document.body ? document.body.querySelectorAll('*') : [];
  for (const el of all) {
    if (el.closest('table')) continue;                 // tables are the other sweep
    // ...and nor is a WRAPPER of one. A `.card` holding nothing but a <table>
    // has no deeper candidate, so the leaf rule kept it and its text was the
    // whole grid flattened -- scoring the same data twice, once as rows and
    // once as a blob that any surface carries because it is just a long
    // string. Found by reading the item list, not by reading the rule.
    if (el.querySelector('table')) continue;
    if (['SCRIPT','STYLE','NOSCRIPT','TEMPLATE','HEAD'].includes(el.tagName)) continue;
    if (!vis(el)) continue;
    if (el.closest(INTER)) continue;
    if (el.querySelector(INTER)) continue;
    const d = getComputedStyle(el).display;
    if (d === 'inline' || d === 'none' || d === 'contents') continue;
    const s = txt(el).trim();
    if (!s) continue;
    cand.push({el, s});
  }
  for (const c of cand) {
    if (cand.some(o => o !== c && c.el.contains(o.el))) continue;   // not a leaf
    blocks.push({tag: c.el.tagName.toLowerCase(), text: c.s, sel: sel(c.el)});
  }

  return {url: location.href, title: document.title,
          innerText: document.body ? document.body.innerText : '',
          cells, blocks};
}
"""


def load_server():
    spec = importlib.util.spec_from_file_location("ms_textflows", ROOT / "mcp_server.py")
    ms = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ms)
    return ms


class Stack:
    """Real Chrome + the unpacked extension + the bridge + the real MCP tools.

    Same shape as `run_flows.py` and for its reason: every other probe injects
    page functions directly and never crosses the two boundaries where features
    ship inert (#19/#30). A text-sufficiency number taken by calling
    `_domTextPage` in Playwright would not be measuring the tool.
    """

    def __init__(self, origins, headed=False):
        self.origins = list(origins)
        self.headed = headed
        self.token = "txtflows-" + os.urandom(8).hex()

    async def __aenter__(self):
        from playwright.async_api import async_playwright
        self.ms = load_server()
        self.bridge = ExtensionBridge(host="127.0.0.1", port=PORT, token=self.token)
        await self.bridge.start()
        self.ms.STATE["bridge"] = self.bridge
        self._pw = async_playwright()
        p = await self._pw.__aenter__()
        self.ctx = await p.chromium.launch_persistent_context(
            user_data_dir="", headless=False,
            args=([f"--disable-extensions-except={EXT}", f"--load-extension={EXT}"]
                  + ([] if self.headed else ["--headless=new"])),
            viewport={"width": 1280, "height": 900})
        sw = (self.ctx.service_workers[0] if self.ctx.service_workers
              else await self.ctx.wait_for_event("serviceworker", timeout=20000))
        ext_id = sw.url.split("/")[2]
        pg = await self.ctx.new_page()
        await pg.goto(f"chrome-extension://{ext_id}/panel.html")
        await pg.wait_for_timeout(200)
        now = int(time.time() * 1000)
        await pg.evaluate("s => chrome.storage.local.set(s)",
                          {"bridge_host": "127.0.0.1", "bridge_port": PORT,
                           "bridge_token": self.token,
                           "bridge_permissions":
                               {"origins": {o: {"granted": now} for o in self.origins}}})
        await pg.close()
        await self.bridge.wait_until_connected(timeout=30)
        tab = await self.ms.tabs_create_mcp()
        self.tab = int(re.search(r'"tabId":\s*(\d+)', tab).group(1))
        self.B = self.ms._BATCHABLE
        return self

    async def __aexit__(self, *a):
        try:
            await self.ctx.close()
        finally:
            await self.bridge.stop()
            await self._pw.__aexit__(*a)

    async def page_for(self, url: str):
        """The PLAYWRIGHT handle on the tab the flow ran in -- the ground-truth
        channel. Matched on url; the panel and about:blank are excluded."""
        best = None
        for p in self.ctx.pages:
            if p.url.startswith("chrome-extension://") or p.url == "about:blank":
                continue
            if url and p.url == url:
                best = p
            elif best is None:
                best = p
        return best

    async def sweep(self, url: str):
        p = await self.page_for(url)
        if p is None:
            return None
        return await p.evaluate(SWEEP_JS)


# ---------------------------------------------------------------------------
# the fixture flows -- recorded, not hand-written
# ---------------------------------------------------------------------------
def ref_for(listing: str, pattern: str):
    """A ref whose row matches `pattern`. Handles a FOLD line too: a folded
    member carries its ref as `123:"label"`, and #55 records a probe that read
    only `ref_N |` rows and concluded a page had four controls when it had
    thirty."""
    rx = re.compile(pattern)
    for line in listing.split("\n"):
        if not rx.search(line):
            continue
        m = re.search(r"\bref_(\d+)\b", line)
        if m:
            return m.group(1)
        for mm in re.finditer(r"(\d+):\"([^\"]*)\"", line):
            if rx.search(mm.group(2)):
                return mm.group(1)
    return None


async def _refs(S, *patterns):
    listing = await S.B["read_page"](tabId=S.tab, filter="interactive")
    out = []
    for p in patterns:
        r = ref_for(listing, p)
        if not r:
            raise RuntimeError(f"no ref matching {p!r} in:\n{listing[:1800]}")
        out.append(r)
    return out


async def _login(S, email="ada@acme.test"):
    """Addressed BY REF, deliberately, and the first version of this was not.

    `fill_form` takes a CSS selector as well, and a selector is the ref-free way
    to address a form (#48). But the recorder builds a step's `targets` from
    REFS only, and `secrets.is_secret` reads the declared `type` out of that
    descriptor -- so a selector-addressed `input[type=password]` has no target,
    is never tested, and its value is written into the flow file VERBATIM.
    Measured: the first recording of these seven flows put `demo-pass-1234` in
    plaintext in all seven, in files whose whole purpose is to be committed.
    Reported rather than worked around in `core/flows/secrets.py`, which is
    outside this probe's scope.
    """
    await S.B["navigate"](url=PG + "/logout", tabId=S.tab)
    await asyncio.sleep(0.8)
    em, pw = await _refs(S, r'name="Work email"', r'name="Password"')
    r = await S.B["fill_form"](
        fields=[{"ref": em, "value": email},
                {"ref": pw, "value": "demo-pass-1234"}],
        submit=True, tabId=S.tab)
    await asyncio.sleep(1.0)
    return r


async def _click_named(S, pattern):
    listing = await S.B["read_page"](tabId=S.tab, filter="interactive")
    ref = ref_for(listing, pattern)
    if not ref:
        raise RuntimeError(f"no ref matching {pattern!r} in:\n{listing[:1500]}")
    out = await S.B["computer"](action="left_click", ref=ref, tabId=S.tab)
    await asyncio.sleep(1.0)
    return out


async def record_fixture_flows(S, only=None):
    """Drive each happy path through the WRAPPED registry, exactly as an agent
    would, and let the recorder compile it.

    The postconditions deliberately assert URLS and COUNTS and never the prose
    values this probe later sweeps for: a flow that asserted the sentence would
    make the measurement circular, and the recorder would then be the thing
    deciding whether the text surface carries it.
    """
    import urllib.request as U

    def reset():
        U.urlopen(U.Request(PG + "/api/reset", method="POST"), timeout=5).read()

    def chaos(flags):
        U.urlopen(U.Request(PG + "/api/chaos", method="POST",
                            data=json.dumps({"flags": flags}).encode(),
                            headers={"Content-Type": "application/json"}),
                  timeout=5).read()

    # ---- each recipe leaves the page in a state a fresh navigate cannot make
    # The modal is in the DOM at all times, inside a `[hidden]` backdrop, so
    # `[role=dialog]` counts 1 whether it is open or shut and an assertion on
    # it is HOLLOW -- #57's warning, earned on the first take of these
    # recordings. `.backdrop:not([hidden])` is the page's own declaration of
    # which state it is in.
    OPEN_MODAL = ".backdrop:not([hidden]) [role=dialog]"

    async def validation(S):
        await _login(S)
        await S.B["query_elements"](selector="table tbody tr", tabId=S.tab)   # 4
        await _click_named(S, r'"New project"')
        await S.B["query_elements"](selector=OPEN_MODAL, tabId=S.tab)         # 1
        name_ref, = await _refs(S, r'name="Project name"')
        await S.B["fill_form"](fields=[{"ref": name_ref, "value": "zz-no-plan"}],
                               submit=True, tabId=S.tab)
        await asyncio.sleep(1.2)
        await S.B["get_url"](tabId=S.tab)
        await S.B["query_elements"](selector=".flash", tabId=S.tab)           # 1 now
        await S.B["query_elements"](selector="table tbody tr", tabId=S.tab)   # still 4

    async def login_error(S):
        await S.B["navigate"](url=PG + "/logout", tabId=S.tab)
        await asyncio.sleep(0.8)
        await S.B["query_elements"](selector="form", tabId=S.tab)
        em, pw = await _refs(S, r'name="Work email"', r'name="Password"')
        await S.B["fill_form"](
            fields=[{"ref": em, "value": "ada@wrong.test"},
                    {"ref": pw, "value": "demo-pass-1234"}],
            submit=True, tabId=S.tab)
        await asyncio.sleep(1.2)
        await S.B["query_elements"](selector=".err", tabId=S.tab)             # 1 now

    async def new_project(S):
        await _login(S)
        await S.B["query_elements"](selector="table tbody tr", tabId=S.tab)   # 4
        await _click_named(S, r'"New project"')
        await S.B["query_elements"](selector=OPEN_MODAL, tabId=S.tab)
        # The Plan <label> carries no `for`, so the select has no accessible
        # name and the listing shows its POST key -- `(post-key)`, #41. Matching
        # on the tag is what the page actually declares here.
        nm, rg, pl = await _refs(S, r'name="Project name"', r'name="Region"',
                                 r'\| select\b')
        await S.B["fill_form"](
            fields=[{"ref": nm, "value": "zz-probe-svc"},
                    {"ref": rg, "value": "sa-east-1"},
                    {"ref": pl, "value": "Enterprise"}],
            submit=True, tabId=S.tab)
        await asyncio.sleep(1.2)
        await S.B["query_elements"](selector="table tbody tr", tabId=S.tab)   # 5
        await S.B["get_url"](tabId=S.tab)

    async def modal(S):
        await _login(S)
        await S.B["query_elements"](selector=OPEN_MODAL, tabId=S.tab)         # 0
        await _click_named(S, r'"New project"')
        await S.B["query_elements"](selector=OPEN_MODAL, tabId=S.tab)         # 1
        await S.B["query_elements"](selector="#newproj label", tabId=S.tab)

    async def report(S):
        await _login(S)
        await S.B["query_elements"](selector="#metrics", tabId=S.tab)
        await _click_named(S, r'a "Report"')
        await S.B["get_url"](tabId=S.tab)
        await S.B["query_elements"](selector="#metrics tbody tr", tabId=S.tab)

    async def members(S):
        await _login(S)
        await _click_named(S, r'a "Members"')
        await S.B["get_url"](tabId=S.tab)
        await S.B["query_elements"](selector="table tbody tr", tabId=S.tab)

    async def detail(S):
        await _login(S)
        await _click_named(S, r'"cinder-jobs"')
        await S.B["get_url"](tabId=S.tab)
        await S.B["query_elements"](selector="button.danger", tabId=S.tab)

    for nm, fn in [("txt-pg-validation", validation),
                   ("txt-pg-login-error", login_error),
                   ("txt-pg-new-project", new_project),
                   ("txt-pg-modal", modal),
                   ("txt-pg-report", report),
                   ("txt-pg-members", members),
                   ("txt-pg-detail", detail)]:
        if only and nm not in only:
            continue
        reset()
        chaos([])
        print(f"\n--- recording {nm}")
        print(await S.ms.record_flow(action="start", name=nm))
        try:
            await fn(S)
        except Exception as exc:
            print(f"  ABORT {type(exc).__name__}: {exc}")
            print(await S.ms.record_flow(action="cancel"))
            continue
        print(await S.ms.record_flow(action="stop", name=nm))


# ---------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------
def carried(value: str, out: str) -> bool:
    return norm_flat(value) in norm_flat(out)


def paired(row_key: str, value: str, out: str) -> bool:
    """Can a reader recover this cell from its row key? True when some LINE of
    the output holds both. `search_page` marks the page's own cell boundaries
    with ` | ` on one line, `get_page_text` keeps a table row on one line, and
    a flattened run of cells keeps neither -- which is #14's complaint (8
    headers and ZERO data rows) and what the test is for."""
    rk, v = norm_flat(row_key), norm_flat(value)
    if not rk or not v:
        return False
    for line in norm_line(out).split("\n"):
        f = norm_flat(line)
        if rk in f and v in f:
            return True
    return False


def state_sig(sw) -> str:
    """Identity of a page STATE, so the same state reached from two flows (or
    from two stop points) is one item and not two. Mechanical, so it is not me
    choosing which states count."""
    body = json.dumps([sw["url"],
                       sorted(b["text"] for b in sw["blocks"]),
                       sorted(f'{c["rowKey"]}|{c["colKey"]}|{c["value"]}'
                              for c in sw["cells"])], ensure_ascii=False)
    return hashlib.sha1(body.encode("utf-8")).hexdigest()[:12]


async def read_arms(S):
    """Every whole-page surface, on ONE page state, with no action between
    them, which is R3's requirement that a variant be measured on the same page
    LOAD rather than on a later one."""
    t = S.tab
    # THE ABLATION. `filter="interactive"` is `read_page` with its text
    # removed -- the paper's Table-3 row, available as a parameter.
    li = await S.B["read_page"](tabId=t, filter="interactive")
    arms = {
        "listing_interactive": li,
        "read_page_all": await S.B["read_page"](tabId=t, filter="all"),
        "get_page_text": await S.B["get_page_text"](tabId=t),
    }
    # The data-table hint names each table's ref and tells the caller to read
    # it scoped. Following that advice IS the arm; the refs come from the
    # listing itself, so nothing here authors a selector.
    refs, scoped = [], []
    m = re.search(r"data table\(s\) on this page:(.*)", li)
    if m:
        refs = re.findall(r"ref_(\d+)", m.group(1))
    for r in refs[:12]:
        try:
            scoped.append(await S.B["read_page"](tabId=t, ref_id=r, filter="all"))
        except Exception as exc:
            scoped.append(f"__ERROR__ {type(exc).__name__}: {exc}")
    arms["scoped_tables"] = "\n".join(scoped)
    arms["_table_refs"] = ",".join(refs)
    return arms


def search_hits(res: str):
    """How many matches `search_page` reported. -1 when it could not be read.

    NOT `startswith("No match")`. The miss path prepends the readiness note
    (#39 routes a miss through `page_readiness`), so the sentence is never at
    the front and a prefix test reports EVERY miss as a hit. My first version
    did exactly that and scored the random-nonce control as found on 8 states
    out of 8 -- the flattering direction, caught by the control rather than by
    reading, which is the only reason it is not in the number.
    """
    s = str(res or "")
    if s.startswith("__ERROR__"):
        return -1
    m = re.search(r"(\d+)\s+match\(es\) for ", s)
    if m:
        return int(m.group(1))
    if re.search(r'No match for "', s):
        return 0
    return -1


def row_present(values, out: str) -> bool:
    """COVERAGE: is every cell value of this row somewhere in the output?

    This is the headline test for a row, and NOT a same-line test. My first
    version required all the values on ONE line, and 44 of the 54 rows it
    scored LOST have a cell whose own text spans several lines (an APG keyboard
    table with a <ul> in a cell, a Wikipedia broadcast table with footnote
    runs) -- unrecoverable by construction, so the ruler was manufacturing a
    third of its own damning result. Association is a real and separate
    question and is measured separately below, over the rows where it is
    decidable.
    """
    vals = [norm_flat(v) for v in values if norm_flat(v)]
    if not vals:
        return False
    flat = norm_flat(out)
    return all(v in flat for v in vals)


def row_ordered(values, out: str) -> bool:
    """WEAK ASSOCIATION: the values appear in document order, one after the
    other, somewhere in the output."""
    vals = [norm_flat(v) for v in values if norm_flat(v)]
    if not vals:
        return False
    flat = norm_flat(out)
    i = 0
    for v in vals:
        j = flat.find(v, i)
        if j < 0:
            return False
        i = j + len(v)
    return True


def row_oneline(values, out: str) -> bool:
    """STRONG ASSOCIATION: one LINE carries the whole row, in order.

    Only meaningful for a row whose every cell is itself single-line, so it is
    reported over that subset and never over all rows (`single_line` below).
    """
    vals = [norm_flat(v) for v in values if norm_flat(v)]
    if not vals:
        return False
    for line in norm_line(out).split("\n"):
        f = norm_flat(line)
        i, ok = 0, True
        for v in vals:
            j = f.find(v, i)
            if j < 0:
                ok = False
                break
            i = j + len(v)
        if ok:
            return True
    return False


def rows_of(sweep):
    """Table rows as ORDERED value sequences, grouped by (table, row)."""
    by = defaultdict(list)
    for c in sweep["cells"]:
        by[(c["table"], c["row"])].append(c)
    out = []
    for k in sorted(by):
        cs = sorted(by[k], key=lambda c: c["col"])
        # The ROW KEY leads. The sweep drops the cell whose text IS the key
        # (it is reported as `rowKey`), and leaving it out of the recovery
        # sequence tests a weaker thing than a reader asks: "the row for
        # atlas-api" has to start with atlas-api.
        seen, vals = set(), [cs[0]["rowKey"]]
        for c in cs:                      # a colspan repeats one cell; count once
            if c["col"] in seen:
                continue
            seen.add(c["col"])
            vals.append(c["value"])
        out.append({"table": k[0], "row": k[1], "row_key": cs[0]["rowKey"],
                    "values": vals,
                    # THE <tr>, not the first <td>. Asking query_elements for
                    # one cell and then testing whether the whole row came back
                    # scores the tool on a question nobody asked it, and it
                    # read as a 0.778 arm until the selector was looked at.
                    "sel": cs[0].get("rowSel") or cs[0].get("sel", ""),
                    "cols": [c["colKey"] for c in cs]})
    return out


async def score_state(S, sweep, arms, state_id, flow, stop_after):
    """One item per required value. Two mechanical kinds, no thresholds:

      block  a visible leaf text block holding no control -> its whole text
      row    a table data row -> its cell values, in order

    `search_page` and `query_elements` cost a round trip each and are asked for
    EVERY item, not only the ones the cheap arms missed: asking only where it
    could change the verdict would make the per-tool column a different
    population from the headline (#22's numerator/denominator rule).
    """
    items = []
    for b in sweep["blocks"]:
        items.append({"kind": "block", "value": b["text"], "values": [b["text"]],
                      "row_key": "", "tag": b["tag"], "sel": b.get("sel", "")})
    for r in rows_of(sweep):
        items.append({"kind": "row", "value": " | ".join(r["values"]),
                      "values": r["values"], "row_key": r["row_key"],
                      "tag": "tr", "sel": r["sel"], "cols": r["cols"]})

    out = []
    for it in items:
        if not [v for v in it["values"] if norm_flat(v)]:
            continue
        rec = dict(it)
        rec.update(state=state_id, flow=flow, stop_after=stop_after,
                   url=sweep["url"], len=len(norm_flat(it["value"])),
                   single_line=all("\n" not in v for v in it["values"]))

        def has(blob):
            return (row_present(it["values"], blob) if it["kind"] == "row"
                    else carried(it["value"], blob))

        rec["in_listing"] = has(arms["listing_interactive"])
        rec["in_read_all"] = has(arms["read_page_all"])
        rec["in_text"] = has(arms["get_page_text"])
        if it["kind"] == "row":
            for nm, blob in (("text", arms["get_page_text"]),
                             ("read_all", arms["read_page_all"]),
                             ("scoped", arms["scoped_tables"])):
                rec[f"ordered_{nm}"] = row_ordered(it["values"], blob)
                rec[f"oneline_{nm}"] = row_oneline(it["values"], blob)
            # THE ARM #26 BUILT FOR TABLES, and `OPEN.md` item 12 says it was
            # never priced: the listing names each data table's ref and says to
            # read it with read_page(ref_id=…, filter="all"), which renders the
            # cells as aligned columns under their header. A whole-page text
            # read is not that tool, so scoring tables without it would price
            # the fallback and call it the feature.
            rec["in_scoped"] = row_present(it["values"], arms["scoped_tables"])
        # search_page is asked for the ROW KEY on a table row -- an agent
        # greps for the thing it knows, and the question is whether the hit's
        # CONTEXT then carries the rest of the row.
        probe = it["row_key"] if it["kind"] == "row" else it["value"]
        try:
            sres = await S.B["search_page"](pattern=probe, tabId=S.tab, regex=False,
                                            context_chars=240, max_results=5)
        except Exception as exc:
            sres = f"__ERROR__ {type(exc).__name__}: {exc}"
        rec["search_hits"] = search_hits(sres)
        rec["in_search"] = (rec["search_hits"] > 0) and has(sres)
        try:
            qres = await S.B["query_elements"](selector=it["sel"], tabId=S.tab,
                                               include_text=True, max_results=5)
        except Exception as exc:
            qres = f"__ERROR__ {type(exc).__name__}: {exc}"
        rec["in_query"] = has(qres)
        rec["carried"] = bool(rec["in_read_all"] or rec["in_text"]
                              or rec["in_search"] or rec["in_query"]
                              or rec.get("in_scoped"))
        out.append(rec)
    return out


# ---------------------------------------------------------------------------
def summarise(items, label):
    scored = list(items)
    if not scored:
        print(f"\n=== {label}: nothing scored")
        return {}
    dep = [i for i in scored if not i["in_listing"]]
    car = [i for i in dep if i["carried"]]
    lost = [i for i in dep if not i["carried"]]
    print(f"\n=== {label}")
    print(f"  distinct page states     {len({i['state'] for i in scored})}")
    print(f"  required values scored   {len(scored)}  "
          f"({sum(1 for i in scored if i['kind']=='block')} prose, "
          f"{sum(1 for i in scored if i['kind']=='row')} table rows)")
    print(f"  TEXT-DEPENDENT           {len(dep)}/{len(scored)} = "
          f"{len(dep)/len(scored):.3f}   <- the controls-only listing does NOT carry them")
    if dep:
        print(f"  TS (carried by any arm)  {len(car)}/{len(dep)} = {len(car)/len(dep):.3f}")
        print(f"  LOST                     {len(lost)}")
        for arm, nm in (("in_read_all", "read_page(all)"),
                        ("in_text", "get_page_text"),
                        ("in_search", "search_page"),
                        ("in_query", "query_elements")):
            n = sum(1 for i in dep if i.get(arm))
            print(f"    {nm:<16} {n:>4}/{len(dep)} = {n/len(dep):.3f}")
    trows = [i for i in scored if i["kind"] == "row"]
    if trows:
        print(f"  TABLE ROWS ({len(trows)}):")
        n = sum(1 for i in trows if i.get("in_scoped"))
        print(f"    read_page(ref_id=table, filter=all)  {n}/{len(trows)} = "
              f"{n/len(trows):.3f}   <- the tool the hint points at")
        sl = [i for i in trows if i.get("single_line")]
        for nm in ("text", "read_all", "scoped"):
            o = sum(1 for i in trows if i.get(f"ordered_{nm}"))
            print(f"    ordered in {nm:<9} {o}/{len(trows)} = {o/len(trows):.3f}", end="")
            if sl:
                l1 = sum(1 for i in sl if i.get(f"oneline_{nm}"))
                print(f"   |  one line, single-line cells only: "
                      f"{l1}/{len(sl)} = {l1/len(sl):.3f}")
            else:
                print()
    for kind in ("block", "row"):
        k = [i for i in scored if i["kind"] == kind]
        kd = [i for i in k if not i["in_listing"]]
        if k:
            print(f"  {kind:<6} {len(k):>4} item(s); text-dependent {len(kd)} "
                  f"({len(kd)/len(k):.3f}); carried "
                  f"{sum(1 for i in kd if i['carried'])}/{len(kd)}")
    if lost:
        print("  lost values (first 15):")
        for i in lost[:15]:
            print(f"    [{i['flow']}@{i['stop_after']} {i['kind']}] "
                  f"{norm_flat(i['value'])[:90]!r}")
    return {"scored": len(scored), "dep": len(dep), "carried": len(car),
            "lost": len(lost),
            "ts": (len(car) / len(dep)) if dep else None,
            "text_dependence": len(dep) / len(scored)}


# ---------------------------------------------------------------------------
# controls
# ---------------------------------------------------------------------------
async def run_controls(S, sweep, arms):
    """Falsifiers. A matcher that says yes to everything, and a tool that is
    not actually being driven, both read as a perfect score."""
    res = {}
    nonce = "zz-" + hashlib.sha1(str(time.time()).encode()).hexdigest()[:10]
    res["nonce_in_text"] = carried(nonce, arms["get_page_text"])
    res["nonce_in_read_all"] = carried(nonce, arms["read_page_all"])
    try:
        sres = await S.B["search_page"](pattern=nonce, tabId=S.tab, regex=False)
        res["nonce_in_search"] = search_hits(sres) > 0
        res["nonce_search_readable"] = search_hits(sres) >= 0
    except Exception as exc:
        res["nonce_in_search"] = f"__ERROR__ {exc}"
        res["nonce_search_readable"] = False
    # The ablation must be a SUBSET: anything the controls-only listing carries
    # has to be in the full one, or `filter` is not what this probe thinks.
    vals = [b["text"] for b in sweep["blocks"]][:40]
    res["ablation_subset"] = all(
        (not carried(v, arms["listing_interactive"])) or carried(v, arms["read_page_all"])
        for v in vals)
    # Vacuity: a state with no required values at all would score 1.000.
    res["values_present"] = len(sweep["blocks"]) + len(sweep["cells"])
    return res



# ---------------------------------------------------------------------------
# replay + measure
# ---------------------------------------------------------------------------
def flows_for(corpus: str, only):
    names = sorted(p.stem.replace(".flow", "") for p in FLOWS.glob("*.flow.json"))
    if only:
        return [n for n in names if n in set(only)]
    if corpus == "fixture":
        return [n for n in names if n.startswith("txt-pg-")]
    if corpus == "ev":
        # The eight `ev-*` recordings come from #63/#64's bench_flows rounds:
        # eight agents, eight real third-party apps, told to record a flow and
        # told nothing about any text measurement. That is the closest thing
        # here to a blind sample of post-interaction states, and it is the only
        # corpus with real page SIZE -- the thing that makes a budget bite.
        # `todomvc-add-items` joins them (#56, same shape, public site).
        # The `crm-*` flows are deliberately absent: they point at a private
        # staging host that is excluded from git (#67) and is nobody's to reach.
        return [n for n in names
                if n.startswith("ev-") or n == "todomvc-add-items"]
    if corpus == "all":
        return [n for n in names if n.startswith("txt-pg-")
                or n.startswith("ev-") or n == "todomvc-add-items"]
    raise SystemExit(f"unknown corpus {corpus!r}")


async def measure(S, names, replicate=0, limit_states=None, quiet=False):
    """Replay each flow to EVERY step index and score the state it leaves.

    Stopping at every step rather than at one I picked is deliberate: choosing
    the stop point is choosing the sample, and #25's rule is that an ablation
    measures the code against the sample and cannot measure the sample. States
    that repeat (the login landing, reached by six flows) are deduped by their
    own content hash, so the denominator counts DISTINCT states.
    """
    rows, seen, controls, failures = [], {}, [], []
    for name in names:
        path = FLOWS / f"{name}.flow.json"
        try:
            flow = S.ms._flow_load(path)
        except Exception as exc:
            failures.append((name, -1, f"load: {exc}"))
            continue
        fixture = (flow.origin or "").startswith(PG)
        for stop in range(len(flow.steps)):
            # A RESET PER REPLAY, not per flow and not per run. `run_flows.py`
            # moved from per-run to per-flow because one mutating flow poisoned
            # every flow after it (#54, one level up); a stop_after sweep runs
            # the SAME mutating flow many times, so the level goes up again.
            # Measured: without this, `txt-pg-new-project` left a fifth project
            # behind and `txt-pg-validation` then failed its own recorded
            # `4 rows` on every one of its three stop points -- 0 of its states
            # were ever scored, in silence except for a REPLAY FAILURES line.
            if fixture:
                try:
                    import urllib.request as U
                    U.urlopen(U.Request(PG + "/api/reset", method="POST"), timeout=5).read()
                except Exception as exc:
                    failures.append((name, stop, f"fixture reset failed: {exc}"))
                    continue
            try:
                res = await S.ms._flow_start(
                    S.ms._flow_load(path), S.tab, S.ms._flow_call, S.ms._flow_entries,
                    viewport_fn=S.ms._flow_viewport, stop_after=stop)
            except Exception as exc:
                failures.append((name, stop, f"{type(exc).__name__}: {exc}"))
                continue
            if res.get("status") not in ("stopped_early", "passed"):
                failures.append((name, stop, f"{res.get('status')}: {res.get('reason','')[:140]}"))
                continue
            await asyncio.sleep(SETTLE_S)
            try:
                url = json.loads(await S.B["get_url"](tabId=S.tab)).get("url", "")
            except Exception:
                url = ""
            sw = await S.sweep(url)
            if not sw:
                failures.append((name, stop, "no playwright page for the tab"))
                continue
            sig = state_sig(sw)
            if sig in seen:
                if not quiet:
                    print(f"  {name}@{stop:<2} same state as {seen[sig]} — deduped")
                continue
            seen[sig] = f"{name}@{stop}"
            arms = await read_arms(S)
            # EVERY ARM, VERBATIM, ON DISK. A claim about what a surface
            # carries is checkable only against what it actually printed, and
            # three of this probe's own defects were found by reading these
            # rather than by reading the code.
            if STATE_DIR:
                STATE_DIR.mkdir(parents=True, exist_ok=True)
                (STATE_DIR / f"{sig}.txt").write_text(
                    f"### {name}@{stop}  {url}\n"
                    + "".join(f"\n===== {k} =====\n{v}\n" for k, v in arms.items())
                    + f"\n===== PLAYWRIGHT innerText (GROUND TRUTH) =====\n{sw['innerText']}\n",
                    encoding="utf-8")
            controls.append({"state": sig, "where": f"{name}@{stop}",
                             **await run_controls(S, sw, arms)})
            got = await score_state(S, sw, arms, sig, name, stop)
            rows.extend(got)
            if not quiet:
                print(f"  {name}@{stop:<2} {url[:64]:<64} "
                      f"{len(sw['blocks'])} block(s) {len(sw['cells'])} cell(s) "
                      f"-> {len(got)} value(s)")
            if limit_states and len(seen) >= limit_states:
                return rows, controls, failures
    return rows, controls, failures


async def amain():
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", action="store_true", help="record the fixture flows")
    ap.add_argument("--measure", action="store_true")
    ap.add_argument("--corpus", default="fixture", choices=["fixture", "ev", "all"])
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--replicates", type=int, default=1,
                    help="replay the WHOLE corpus N times; the drift floor is "
                         "the disagreement between replicates on identical code")
    ap.add_argument("--limit-states", type=int, default=None)
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "temp" / "text_flows"))
    args = ap.parse_args()
    if not (args.record or args.measure):
        ap.error("pass --record and/or --measure")

    names = flows_for(args.corpus, args.only) if args.measure else []
    origins = {PG}
    for n in names:
        try:
            f = S_load = None
            import json as _j
            d = _j.loads((FLOWS / f"{n}.flow.json").read_text(encoding="utf-8"))
            if d.get("origin"):
                origins.add(d["origin"])
            for st in d.get("steps", []):
                u = (st.get("input") or {}).get("url")
                m = re.match(r"^(https?://[^/]+)", u) if isinstance(u, str) else None
                if m:
                    origins.add(m.group(1))
        except Exception:
            pass
    # The fixture's own seeded credential, the same derivation run_flows uses.
    for n in names + ["txt-pg-validation", "txt-pg-new-project", "txt-pg-modal",
                      "txt-pg-report", "txt-pg-members", "txt-pg-detail",
                      "txt-pg-login-error"]:
        slug = re.sub(r"[^A-Z0-9]+", "_", n.upper())
        for fld in ("PASSWORD",):
            os.environ.setdefault(f"CB_SECRET_{slug}_{fld}", "demo-pass-1234")

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    global STATE_DIR
    STATE_DIR = outdir / "states"

    async with Stack(sorted(origins), headed=args.headed) as S:
        if args.record:
            await record_fixture_flows(S, only=set(args.only) if args.only else None)
        if not args.measure:
            return 0
        reps = []
        for rep in range(args.replicates):
            print(f"\n######## replicate {rep + 1}/{args.replicates}")
            # A KNOWN STARTING STATE per replicate, or replicate 2 measures
            # whatever replicate 1 left behind -- the between-run version of
            # the per-flow reset run_flows needed (#54, one level up).
            try:
                import urllib.request as U
                U.urlopen(U.Request(PG + "/api/reset", method="POST"), timeout=5).read()
            except Exception as exc:
                print(f"  (fixture reset failed: {exc})")
            rows, controls, failures = await measure(
                S, names, replicate=rep, limit_states=args.limit_states)
            reps.append((rows, controls, failures))

    for rep, (rows, controls, failures) in enumerate(reps):
        summarise(rows, f"replicate {rep + 1} — corpus {args.corpus}")
        bad = [c for c in controls
               if c["nonce_in_text"] or c["nonce_in_read_all"]
               or c["nonce_in_search"] is True or not c["ablation_subset"]
               or not c["values_present"] or not c["nonce_search_readable"]]
        print(f"  CONTROLS: {len(controls)} state(s), {len(bad)} violation(s)"
              + ("" if not bad else "  <-- A CONTROL FAILED, do not quote the number"))
        for b in bad[:6]:
            print(f"    {b}")
        if failures:
            print(f"  REPLAY FAILURES: {len(failures)}")
            for f in failures[:12]:
                print(f"    {f[0]}@{f[1]}: {f[2]}")

    if len(reps) > 1:
        def key(r):
            return (r["state"], r["kind"], norm_flat(r["value"]), r["row_key"])
        a = {key(r): r for r in reps[0][0]}
        b = {key(r): r for r in reps[1][0]}
        both = set(a) & set(b)
        fields = ["in_listing", "in_read_all", "in_text", "in_search", "in_query",
                  "carried", "paired_text"]
        dis = {f: sum(1 for k in both if a[k].get(f) != b[k].get(f)) for f in fields}
        print(f"\n=== DRIFT FLOOR (same code, two replicates)")
        print(f"  values in both replicates: {len(both)}  "
              f"(rep1 {len(a)}, rep2 {len(b)})")
        for f, n in dis.items():
            print(f"    {f:<14} {n:>4} disagreement(s) = "
                  f"{(n / len(both) * 100 if both else 0):.2f}%")

    (outdir / "rows.json").write_text(
        json.dumps([r for rep in reps for r in rep[0]], ensure_ascii=False, indent=1),
        encoding="utf-8")
    print(f"\n  rows -> {outdir / 'rows.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(amain()))
