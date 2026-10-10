"""Acme Ops — a deliberately hostile fake SaaS, for testing recorded flows.

    python tools/saas_playground.py          # http://127.0.0.1:8787

Stdlib only, one file, in-memory state. It exists because the flow recorder was
verified against a third-party marketing page, which cannot be broken
reproducibly: "break the frontend and confirm the flow FAILS" was being done by
hand with javascript_tool, and a falsifier you improvise is not a falsifier.

WHAT IT IS BUILT TO BREAK. Every one of these is a shape that defeats some
record-and-replay tool, and several defeat ours if we got them wrong:

  * EVERY id, class and DOM order token is REGENERATED ON EVERY LOAD. A CSS
    selector or an XPath recorded on one visit is meaningless on the next, by
    construction. This is the one that separates a descriptor built from
    declarations (#28) from the DOM paths Midscene and Chrome's Recorder store.
  * Controlled inputs RE-RENDER THE WHOLE FORM on every keystroke, replacing
    the nodes. That is fix #5's React case, which orphans mmids mid-form, and
    it is why fill_form batches its writes into one script.
  * A custom combobox with role-less options in a portal, plus a decoy hidden
    listbox the trigger's aria-controls points at. That is the rc-select/antd
    shape #29 had to rewrite the option picker for.
  * A modal that marks the rest of the document aria-hidden, which is what made
    the first recorded flow non-idempotent.
  * Two buttons with the SAME accessible name in different landmarks, and a
    table whose rows are identical except by position -- the ambiguity and
    ordinal paths.
  * A <select> whose first option is a sentinel (value="-1"), the older-web
    shape #25 found running Amazon's buy box.

  CHAOS, which is the point: /api/chaos toggles drift ON PURPose, so a
  falsifier run is scripted and repeatable instead of improvised.
      rename     the primary button's label changes
      reorder    table rows are reversed
      insert     a row is inserted ABOVE the others (shifts every ordinal)
      remove     a control disappears
      slow       responses stall, to exercise the readiness banner (#15)
      expire     the session dies after the next request, so a flow mid-way
                 through suddenly gets the LOGIN page back. A flow must fail
                 honestly here, not assert against the wrong document -- the
                 single most realistic way a real suite goes wrong overnight.
      paginate   projects split across pages of 2. Ordinals shift, and the
                 RENDERED row count stops matching the declared total (#35/Q8).
      depends    Plan is disabled until a Region is chosen, so fill_form's
                 field ORDER decides whether the write lands at all (#24/#27's
                 demoqa City case, which ~6 agents reported)
      ja         labels render in Japanese, because the whole descriptor design
                 rests on the accessible name and the corpus that validated it
                 is mostly Latin (#25: the sample cannot measure itself)
      formwide   a keystroke re-renders the WHOLE form, destroying sibling
                 fields -- harsher than React, and the shape that exposed
                 fill_form verifying each field at write time rather than
                 after the whole batch

Credentials are seeded HERE, in the fixture, and are not anyone's secret:
    ada@acme.test / demo-pass-1234
"""
from __future__ import annotations

import json
import random
import re
import string
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST, PORT = "127.0.0.1", 8787
USER = {"email": "ada@acme.test", "password": "demo-pass-1234", "name": "Ada Lovelace"}

STATE_LOCK = threading.Lock()


def seed_projects():
    return [
        {"id": 1, "name": "atlas-api", "region": "eu-west-1", "plan": "team", "status": "running"},
        {"id": 2, "name": "beacon-web", "region": "us-east-1", "plan": "free", "status": "running"},
        {"id": 3, "name": "cinder-jobs", "region": "ap-south-1", "plan": "team", "status": "paused"},
        {"id": 4, "name": "delta-cache", "region": "eu-west-1", "plan": "enterprise", "status": "running"},
    ]


STATE = {"projects": seed_projects(), "next_id": 5, "chaos": set(), "sessions": set()}

REGIONS = ["us-east-1", "eu-west-1", "ap-south-1", "sa-east-1"]
PAGE_SIZE = 2

# Same page, another script. The descriptor's identity slot is the accessible
# name, and every number behind it came from a mostly-Latin corpus.
JA = {
    "Work email": "\u30e1\u30fc\u30eb\u30a2\u30c9\u30ec\u30b9",
    "Password": "\u30d1\u30b9\u30ef\u30fc\u30c9",
    "Sign in": "\u30ed\u30b0\u30a4\u30f3",
    "Projects": "\u30d7\u30ed\u30b8\u30a7\u30af\u30c8",
    "New project": "\u65b0\u3057\u3044\u30d7\u30ed\u30b8\u30a7\u30af\u30c8",
    "Project name": "\u30d7\u30ed\u30b8\u30a7\u30af\u30c8\u540d",
    "Region": "\u30ea\u30fc\u30b8\u30e7\u30f3",
    "Plan": "\u30d7\u30e9\u30f3",
    "Create project": "\u4f5c\u6210",
    "Cancel": "\u30ad\u30e3\u30f3\u30bb\u30eb",
    "Members": "\u30e1\u30f3\u30d0\u30fc",
    "Settings": "\u8a2d\u5b9a",
    "Sign out": "\u30ed\u30b0\u30a2\u30a6\u30c8",
    "Manage": "\u7ba1\u7406",
}


def T(en):
    """Translate when the `ja` chaos flag is on. Identity otherwise."""
    return JA.get(en, en) if chaos("ja") else en
PLANS = [("-1", "Select a plan"), ("free", "Free"), ("team", "Team"),
         ("enterprise", "Enterprise")]


def rid(n=8):
    """A fresh identifier every single time. Nothing here is stable across loads."""
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def chaos(flag): return flag in STATE["chaos"]


# ---------------------------------------------------------------------------
# markup
# ---------------------------------------------------------------------------
CSS = """
*{box-sizing:border-box}
body{margin:0;background:#0b0b0d;color:#e8e8ea;font:14px/1.5 ui-sans-serif,system-ui,-apple-system,sans-serif}
a{color:inherit;text-decoration:none}
.wrap{max-width:980px;margin:0 auto;padding:28px 20px 80px}
header{border-bottom:1px solid #1e1e22;background:#111113}
.bar{max-width:980px;margin:0 auto;padding:12px 20px;display:flex;align-items:center;gap:18px}
.brand{font-weight:650;letter-spacing:-.02em}
.bar nav{display:flex;gap:14px;margin-left:12px;font-size:13px;color:#9a9aa2}
.bar nav a[aria-current=page]{color:#fff}
.bar .right{margin-left:auto;display:flex;gap:10px;align-items:center}
h1{font-size:26px;letter-spacing:-.03em;margin:22px 0 4px}
.sub{color:#9a9aa2;margin:0 0 22px}
.card{background:#141417;border:1px solid #232329;border-radius:12px;padding:18px}
label{display:block;font-size:12.5px;color:#b9b9c0;margin:14px 0 6px}
input[type=text],input[type=email],input[type=password],select,textarea{
 width:100%;padding:9px 11px;background:#0e0e11;border:1px solid #2a2a31;border-radius:8px;color:#e8e8ea;font:inherit}
input:disabled,select:disabled{opacity:.5}
button{font:inherit;padding:9px 14px;border-radius:8px;border:1px solid #2a2a31;background:#1b1b20;color:#e8e8ea;cursor:pointer}
button.primary{background:#e8e8ea;color:#111;border-color:#e8e8ea;font-weight:600}
button.danger{border-color:#5a2222;color:#ff9b9b}
table{width:100%;border-collapse:collapse;margin-top:8px}
th,td{text-align:left;padding:10px 8px;border-bottom:1px solid #1e1e22;font-size:13.5px}
th{color:#9a9aa2;font-weight:500;font-size:12px}
.pill{font-size:11.5px;padding:2px 8px;border-radius:999px;border:1px solid #2a2a31;color:#b9b9c0}
.row{display:flex;gap:10px;align-items:center}
.muted{color:#9a9aa2;font-size:12.5px}
.err{color:#ff9b9b;font-size:13px;margin-top:10px}
.combo{position:relative}
.combo .trigger{width:100%;text-align:left;display:flex;justify-content:space-between}
.pop{position:absolute;z-index:40;top:calc(100% + 6px);left:0;right:0;background:#17171b;
 border:1px solid #2a2a31;border-radius:10px;padding:5px;box-shadow:0 20px 50px -20px #000}
.pop div[data-opt]{padding:7px 9px;border-radius:7px;cursor:pointer}
.pop div[data-opt]:hover{background:#232329}
.backdrop{position:fixed;inset:0;background:rgba(0,0,0,.6);display:grid;place-items:center;z-index:60}
/* A class rule outranks the UA stylesheet's [hidden]{display:none}, so without
   this the modal is ALWAYS painted and covers the page. ChromeBridge read that
   correctly -- it listed the modal's fields and nothing behind them -- which is
   how the fixture bug surfaced. */
.backdrop[hidden]{display:none}
.modal{width:440px;background:#141417;border:1px solid #232329;border-radius:14px;padding:20px}
.flash{background:#13231a;border:1px solid #1f4030;color:#9fe6bb;padding:10px 12px;border-radius:9px;margin-bottom:16px;font-size:13px}
"""


def shell(title, body, user=None, current="", overlay=""):
    nav = ""
    if user:
        items = [("/projects", T("Projects")), ("/members", T("Members")),
                 ("/report", "Report"), ("/settings", T("Settings"))]
        nav = "".join(
            f'<a href="{h}" class="{rid()}"{" aria-current=page" if h == current else ""}>{t}</a>'
            for h, t in items)
    right = (f'<span class="muted">{user["email"]}</span>'
             f'<form method="post" action="/logout" style="margin:0">'
             f'<button class="{rid()}">{T("Sign out")}</button></form>') if user else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} · Acme Ops</title><style>{CSS}</style></head><body>
<header><div class="bar"><span class="brand">Acme Ops</span><nav>{nav}</nav>
<div class="right">{right}</div></div></header>
<div class="wrap">{body}</div>
{overlay}
<script>{JS.replace("__FORMWIDE__", "true" if chaos("formwide") else "false")}</script></body></html>"""


# Controlled inputs: every keystroke REPLACES the field's wrapper, which orphans
# any handle held on the old node. That is fix #5's React case reproduced
# without React, and it is the single most useful hostile behaviour here.
JS = """
window.__FORMWIDE = __FORMWIDE__;
document.addEventListener('input', function (e) {
  var f = e.target.closest('[data-controlled]');
  if (!f) return;
  // Rebuild THIS FIELD's wrapper only. The node identity changes under the
  // caller -- which is the React case fix #5 exists for -- while sibling
  // fields are left alone, because React re-renders once at the end of the
  // tick and does not destroy a field you are not typing into.
  //
  // An earlier version used f.parentElement, i.e. the whole <form>, so typing
  // into field 2 wiped field 1. That is a HARSHER shape than React, and it is
  // worth having on purpose rather than by accident: FORMWIDE below.
  var v = e.target.value;
  var scope = window.__FORMWIDE ? (f.closest('form') || f) : f;
  scope.innerHTML = scope.innerHTML;
  var n = scope.querySelector('[name="' + e.target.name + '"]');
  if (n) { n.value = v; n.focus();
           try { n.setSelectionRange(v.length, v.length); } catch (_) {} }
});
document.addEventListener('click', function (e) {
  var t = e.target.closest('[data-combo-trigger]');
  if (t) {
    var box = t.closest('.combo'), pop = box.querySelector('.pop');
    var open = pop.hasAttribute('hidden');
    pop.toggleAttribute('hidden', !open);
    t.setAttribute('aria-expanded', open ? 'true' : 'false');
    return;
  }
  var o = e.target.closest('[data-opt]');
  if (o) {
    // `depends`: Plan stays disabled until a Region is chosen. fill_form's
    // field ORDER then decides whether the write lands at all -- the demoqa
    // City case (#24/#27) that ~6 live agents reported, made reproducible.
    var frm = o.closest('form');
    if (frm) { var sel = frm.querySelector('select[name=plan]');
               if (sel) sel.disabled = false; }
    var box2 = o.closest('.combo');
    box2.querySelector('[data-combo-trigger] span').textContent = o.textContent;
    box2.querySelector('input[type=hidden]').value = o.getAttribute('data-opt');
    var p = box2.querySelector('.pop');
    p.setAttribute('hidden', '');
    box2.querySelector('[data-combo-trigger]').setAttribute('aria-expanded', 'false');
    return;
  }
  var op = e.target.closest('[data-open-modal]');
  if (op) { document.getElementById(op.getAttribute('data-open-modal')).hidden = false;
            document.querySelector('.wrap').setAttribute('aria-hidden', 'true'); return; }
  var cl = e.target.closest('[data-close-modal]');
  if (cl) { cl.closest('.backdrop').hidden = true;
            document.querySelector('.wrap').removeAttribute('aria-hidden'); return; }
});
"""


def field(label, name, type_="text", placeholder="", value="", required=False):
    """A properly associated label whose `for` matches a PER-LOAD id.

    The ids churn on every load (that is the point), but within one load the
    association is real -- otherwise every field falls back to its POST key
    and the fixture stops resembling an app anyone would ship. One deliberately
    unlabelled field lives on the members page, so the (post-key) path is still
    exercised somewhere.
    """
    i = rid()
    req = " required" if required else ""
    ph = f' placeholder="{placeholder}"' if placeholder else ""
    val = f' value="{value}"' if value else ""
    return (f'<div data-controlled><label for="{i}">{label}</label>'
            f'<input id="{i}" type="{type_}" name="{name}"{ph}{val}{req}></div>')


def combo(name, value, options, label):
    """A custom combobox with role-less options in a portal-ish popover, and a
    DECOY hidden listbox that aria-controls points at — the rc-select/antd
    shape #29 rewrote the option picker for."""
    decoy, pop = rid(), rid()
    shown = next((t for v, t in options if v == value), "Select a region")
    opts = "".join(f'<div data-opt="{v}" class="{rid()}">{t}</div>' for v, t in options)
    return f"""<label>{label}</label>
<div class="combo">
  <button type="button" class="trigger {rid()}" data-combo-trigger aria-expanded="false"
          aria-controls="{decoy}" aria-label="{label}"><span>{shown}</span><span>⌄</span></button>
  <ul id="{decoy}" role="listbox" hidden style="display:none"></ul>
  <div class="pop {pop}" hidden>{opts}</div>
  <input type="hidden" name="{name}" value="{value}">
</div>"""


def login_page(error=""):
    btn = "Log in" if chaos("rename") else T("Sign in")
    return shell("Sign in", f"""
<h1>Sign in</h1><p class="sub">Acme Ops console</p>
<div class="card" style="max-width:420px">
<form method="post" action="/login" class="{rid()}">
  {field(T("Work email"), "email", "email", "you@company.com", required=True)}
  {field(T("Password"), "password", "password", "••••••••", required=True)}
  <label class="row" style="margin-top:14px"><input type="checkbox" name="remember"
     style="width:auto"> <span>Keep me signed in</span></label>
  <div style="margin-top:18px"><button type="submit" class="primary {rid()}">{btn}</button></div>
  {f'<div class="err">{error}</div>' if error else ''}
</form>
<p class="muted" style="margin-top:16px">Demo credentials: ada@acme.test / demo-pass-1234</p>
</div>""")


def projects_page(user, flash=""):
    rows = list(STATE["projects"])
    if chaos("reorder"):
        rows = list(reversed(rows))
    if chaos("insert"):
        rows = [{"id": 0, "name": "aaa-injected", "region": "us-east-1",
                 "plan": "free", "status": "running"}] + rows
    page_note = ""
    if chaos("paginate"):
        total = len(rows)
        rows = rows[:PAGE_SIZE]
        # The DECLARED total and the RENDERED count now disagree, which is the
        # case #35 built the query_elements caveat for. aria-rowcount is how a
        # grid states it; this table states it and renders fewer.
        page_note = f' aria-rowcount="{total}"'
    trs = "".join(f"""<tr class="{rid()}">
  <td><a href="/projects/{p['id']}" class="{rid()}">{p['name']}</a></td>
  <td class="muted">{p['region']}</td><td><span class="pill">{p['plan']}</span></td>
  <td class="muted">{p['status']}</td>
  <td style="text-align:right"><button class="{rid()}" name="manage">{T("Manage")}</button></td>
</tr>""" for p in rows)
    newbtn = "" if chaos("remove") else (
        f'<button class="primary {rid()}" data-open-modal="newproj">{T("New project")}</button>')
    return shell("Projects", f"""
{f'<div class="flash">{flash}</div>' if flash else ''}
<h1>{T("Projects")}</h1><p class="sub">{len(rows)} project(s) in this workspace</p>
<div class="card">
  <div class="row" style="justify-content:space-between;margin-bottom:6px">
    <input type="text" placeholder="Filter projects" style="max-width:260px" class="{rid()}">
    {newbtn}
  </div>
  <table{page_note}><thead><tr><th>Name</th><th>Region</th><th>Plan</th><th>Status</th><th></th></tr></thead>
  <tbody>{trs}</tbody></table>
</div>

""", user, "/projects", overlay=f"""<div class="backdrop" id="newproj" hidden>
 <div class="modal" role="dialog" aria-modal="true" aria-label="{T("New project")}">
  <h2 style="margin:0 0 4px;font-size:18px">{T("New project")}</h2>
  <p class="muted" style="margin:0 0 6px">Create a project in this workspace.</p>
  <form method="post" action="/projects/new" class="{rid()}">
    {field(T("Project name"), "name", "text", "my-service", required=True)}
    {combo("region", "", [(r, r) for r in REGIONS], T("Region"))}
    <label>{T("Plan")}</label>
    <select name="plan" class="{rid()}"{" disabled" if chaos("depends") else ""}>
      {''.join(f'<option value="{v}">{t}</option>' for v, t in PLANS)}
    </select>
    <div class="row" style="margin-top:20px;justify-content:flex-end">
      <button type="button" data-close-modal class="{rid()}">{T("Cancel")}</button>
      <button type="submit" class="primary {rid()}">{T("Create project")}</button>
    </div>
  </form>
 </div>
</div>""")


def project_page(user, p):
    return shell(p["name"], f"""
<h1>{p['name']}</h1><p class="sub">{p['region']} · {p['plan']} · {p['status']}</p>
<div class="card">
  <form method="post" action="/projects/{p['id']}/save" class="{rid()}">
    {field("Display name", "name", "text", value=p["name"])}
    {combo("region", p["region"], [(r, r) for r in REGIONS], T("Region"))}
    <label>{T("Plan")}</label>
    <select name="plan" class="{rid()}">
      {''.join(f'<option value="{v}"{" selected" if v == p["plan"] else ""}>{t}</option>' for v, t in PLANS)}
    </select>
    <div style="margin-top:18px"><button type="submit" class="primary {rid()}">Save changes</button></div>
  </form>
</div>
<div class="card" style="margin-top:16px;border-color:#3a2020">
  <strong>Danger zone</strong>
  <p class="muted" style="margin:6px 0 12px">Deleting a project cannot be undone.</p>
  <form method="post" action="/projects/{p['id']}/delete" style="margin:0">
    <button class="danger {rid()}">Delete project</button></form>
</div>""", user, "/projects")


def report_page(user):
    """Two shapes that each made a pass disagree with another pass (#48).

    The DIALOG is a FULL-VIEWPORT opacity:0 overlay — what a consent
    library leaves behind after a fade-out. It must dominate the viewport and
    sit over its centre, or it passes no modality test and the fixture is
    VACUOUS: the first version was 320x120 in a corner, and an ablation of the
    fix produced byte-identical output because neither arm could reach the
    code under test. Being opacity:0 with an unremarkable display/visibility,
    the modal pass's old hand-rolled test kept it while the collector's
    checkVisibility({opacityProperty:true}) had already dropped it. That is how a Rijksmuseum cookie <aside> raised the MODAL banner and
    suppressed 32 elements that were perfectly visible.

    The TABLE's first row carries a colspan=2, so counting cell ELEMENTS gives
    3 while the renderer expands to 4. The hint advertised `155x11` for a table
    it rendered as `155x28`.
    """
    rows = "".join(
        f'<tr><td>{d}</td><td>{a}</td><td>{b}</td><td>{c}</td></tr>'
        for d, a, b, c in [("2026-10-01", "12", "4", "0.33"),
                           ("2026-10-02", "18", "9", "0.50"),
                           ("2026-10-03", "7", "1", "0.14")])
    return shell("Report", f"""
<h1>Report</h1><p class="sub">Three days, four columns, one colspan</p>
<div class="card">
  <table id="metrics">
    <thead>
      <tr><th>Day</th><th colspan="2">Requests</th><th>Ratio</th></tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
</div>""", user, "/report", overlay=f"""
<aside role="dialog" aria-label="Cookie notice" class="{rid()}"
       style="position:fixed;inset:0;opacity:0;pointer-events:none;
              background:rgba(10,10,12,.86);display:flex;align-items:center;
              justify-content:center">
  <div style="background:#141417;border:1px solid #232329;border-radius:12px;
              padding:24px;width:320px">
    <p class="muted" style="margin:0 0 10px">We use cookies.</p>
    <button class="{rid()}">Accept</button>
  </div>
</aside>""")


def members_page(user):
    people = [("Ada Lovelace", "ada@acme.test", "Owner"),
              ("Grace Hopper", "grace@acme.test", "Admin"),
              ("Alan Turing", "alan@acme.test", "Member")]
    trs = "".join(f'<tr class="{rid()}"><td>{n}</td><td class="muted">{e}</td>'
                  f'<td><span class="pill">{r}</span></td>'
                  f'<td style="text-align:right"><button class="{rid()}">Remove</button></td></tr>'
                  for n, e, r in people)
    return shell("Members", f"""
<h1>Members</h1><p class="sub">{len(people)} people</p>
<div class="card">
  <input type="text" name="invite" placeholder="" style="max-width:260px;margin-bottom:10px" class="{rid()}">
  <table{page_note}><thead><tr><th>Name</th><th>Email</th><th>Role</th><th></th></tr>
</thead><tbody>{trs}</tbody></table></div>""", user, "/members")


def settings_page(user):
    # Two "Save" buttons in different landmarks: the ambiguity case.
    return shell("Settings", f"""
<h1>Settings</h1><p class="sub">Workspace preferences</p>
<section class="card" aria-label="Profile">
  <strong>Profile</strong>
  {field("Full name", "fullname", "text", value=user["name"])}
  <div style="margin-top:14px"><button class="primary {rid()}">Save</button></div>
</section>
<section class="card" style="margin-top:16px" aria-label="Notifications">
  <strong>Notifications</strong>
  <label class="row" style="margin-top:10px"><input type="checkbox" style="width:auto" checked>
    <span>Email me about incidents</span></label>
  <label class="row"><input type="checkbox" style="width:auto">
    <span>Weekly digest</span></label>
  <div style="margin-top:14px"><button class="primary {rid()}">Save</button></div>
</section>""", user, "/settings")


# ---------------------------------------------------------------------------
class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # quiet
        pass

    # -- helpers ----------------------------------------------------------
    def _send(self, body, code=200, ctype="text/html; charset=utf-8", cookie=None):
        raw = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(raw)

    def _redirect(self, to, cookie=None):
        self.send_response(303)
        self.send_header("Location", to)
        self.send_header("Content-Length", "0")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()

    def _session(self):
        m = re.search(r"sid=([a-z0-9]+)", self.headers.get("Cookie") or "")
        ok = bool(m and m.group(1) in STATE["sessions"])
        if ok and chaos("expire"):
            # THE REALISTIC OVERNIGHT FAILURE. The session dies mid-flow, so
            # every later step gets the LOGIN page back with a 200 and the
            # right url. A flow must fail honestly here; the dangerous outcome
            # is asserting against a document it never asked for, which is
            # exactly what the navigate redirect defect used to hide.
            with STATE_LOCK:
                STATE["sessions"].discard(m.group(1))
            return None
        return USER if ok else None

    def _form(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n).decode("utf-8")
        return {k: v[0] for k, v in urllib.parse.parse_qs(raw, keep_blank_values=True).items()}

    # -- routes -----------------------------------------------------------
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if chaos("slow"):
            import time
            time.sleep(1.5)
        if path == "/api/state":
            return self._send(json.dumps({
                "projects": STATE["projects"], "chaos": sorted(STATE["chaos"])}),
                ctype="application/json")
        user = self._session()
        if path == "/logout":
            # GET as well as POST. A recorded flow establishes its own starting
            # state by navigating (CAPTURE.md), and it cannot POST -- so without
            # this, any flow that begins at the login page is unreplayable the
            # moment you are already signed in. That is the precondition gap:
            # flows have postconditions and no pre-conditions, and this makes
            # the state reachable rather than pretending the gap is closed.
            with STATE_LOCK:
                STATE["sessions"].clear()
            return self._redirect("/login", cookie="sid=; Path=/; Max-Age=0")
        if path in ("/", "/login"):
            return self._send(login_page()) if not user else self._redirect("/projects")
        if not user:
            return self._redirect("/login")
        if path == "/projects":
            return self._send(projects_page(user))
        m = re.fullmatch(r"/projects/(\d+)", path)
        if m:
            p = next((x for x in STATE["projects"] if x["id"] == int(m.group(1))), None)
            return self._send(project_page(user, p)) if p else self._send(
                shell("Not found", "<h1>404</h1><p class='sub'>No such project.</p>", user), 404)
        if path == "/report":
            return self._send(report_page(user))
        if path == "/members":
            return self._send(members_page(user))
        if path == "/settings":
            return self._send(settings_page(user))
        return self._send(shell("Not found", "<h1>404</h1>", user), 404)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/chaos":
            f = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or "{}")
            with STATE_LOCK:
                STATE["chaos"] = set(f.get("flags") or [])
            return self._send(json.dumps({"chaos": sorted(STATE["chaos"])}),
                              ctype="application/json")
        if path == "/api/reset":
            with STATE_LOCK:
                STATE["projects"], STATE["next_id"], STATE["chaos"] = seed_projects(), 5, set()
            return self._send(json.dumps({"ok": True}), ctype="application/json")

        form = self._form()
        if path == "/login":
            if form.get("email") == USER["email"] and form.get("password") == USER["password"]:
                sid = rid(16)
                STATE["sessions"].add(sid)
                return self._redirect("/projects", cookie=f"sid={sid}; Path=/")
            return self._send(login_page("That email and password do not match."), 401)
        if path == "/logout":
            STATE["sessions"].clear()
            return self._redirect("/login", cookie="sid=; Path=/; Max-Age=0")

        if not self._session():
            return self._redirect("/login")
        if path == "/projects/new":
            name = (form.get("name") or "").strip()
            plan = form.get("plan") or "-1"
            if not name or plan == "-1":
                return self._send(projects_page(self._session(),
                                  "Project not created: a name and a plan are required."), 400)
            with STATE_LOCK:
                STATE["projects"].append({
                    "id": STATE["next_id"], "name": name,
                    "region": form.get("region") or "us-east-1",
                    "plan": plan, "status": "running"})
                STATE["next_id"] += 1
            return self._redirect("/projects")
        m = re.fullmatch(r"/projects/(\d+)/(save|delete)", path)
        if m:
            pid, what = int(m.group(1)), m.group(2)
            with STATE_LOCK:
                if what == "delete":
                    STATE["projects"] = [x for x in STATE["projects"] if x["id"] != pid]
                    return self._redirect("/projects")
                for x in STATE["projects"]:
                    if x["id"] == pid:
                        x["name"] = form.get("name") or x["name"]
                        x["region"] = form.get("region") or x["region"]
                        if form.get("plan") and form["plan"] != "-1":
                            x["plan"] = form["plan"]
            return self._redirect(f"/projects/{pid}")
        return self._send(shell("Not found", "<h1>404</h1>", self._session()), 404)


def main():
    srv = ThreadingHTTPServer((HOST, PORT), H)
    print(f"Acme Ops on http://{HOST}:{PORT}  (ada@acme.test / demo-pass-1234)")
    print("  chaos:  curl -XPOST http://127.0.0.1:8787/api/chaos "
          "-d '{\"flags\":[\"rename\"]}'   flags: rename reorder insert remove slow")
    print("  reset:  curl -XPOST http://127.0.0.1:8787/api/reset")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
