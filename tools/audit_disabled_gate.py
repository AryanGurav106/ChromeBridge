"""Is there a DECLARED link between a disabled button and the fields it gates?

`docs/OPEN.md` 4i asks the listing to answer what `fill_form` answers when a
submit fails: enumerate the `(required)`/`(unselected)` fields that are still
empty. `fill_form`'s scope rule is explicit and already measured -- "the dialog,
or the submit button's OWN form, is the only honest scope ... with neither, we
have no scope and offer no list" -- so porting it means binding to `btn.form`,
HTML's own form-owner answer.

This asks the corpus whether that binding is ever available, and what the
disabled buttons that DO occur actually are. Both halves matter: a note that
cannot bind is a feature that never fires, and a note on a pagination arrow at
page 1 is wrong, because nothing is blocking it and nothing can unblock it.

SELF-TEST FIRST. A detector that reports 0 is worth nothing until it has been
seen to fire (#21's rule for `audit_patterns.py`), and the headline here IS a
zero. `--self-test` runs it against markup that plainly has the shape.

Usage:
    python tools/audit_disabled_gate.py --self-test
    python tools/audit_disabled_gate.py [N]      # N frozen sites, default all
"""
import asyncio, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FROZEN = ROOT / "temp" / "frozen"

PROBE = r"""(function(){
  var o = {dis:0, declaredSubmit:0, form:0, ctrls:0, desc:0, fset:0, none:0,
           reqEmpty:0, sawReq:false, names:[]};
  // Does the PAGE hold the fact a blocker note would carry -- a field that
  // DECLARES itself required and is empty? Counted independently of the
  // buttons, so "no scope" and "no fact" stay distinguishable.
  document.querySelectorAll('input,select,textarea,[role=combobox]').forEach(function(f){
    var r = f.getBoundingClientRect(); if (r.width === 0 && r.height === 0) return;
    if (!(f.hasAttribute('required') || f.getAttribute('aria-required') === 'true')) return;
    o.sawReq = true;
    var v = (f.value !== undefined ? f.value : (f.innerText || ''));
    if (!String(v || '').trim()) o.reqEmpty++;
  });
  document.querySelectorAll('button,input[type=submit],input[type=button],[role=button]').forEach(function(el){
    var r = el.getBoundingClientRect(); if (r.width === 0 && r.height === 0) return;
    var cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return;
    if (!(el.disabled === true || el.getAttribute('aria-disabled') === 'true')) return;
    o.dis++;
    var t = (el.getAttribute('type') || '').toLowerCase();
    var f = el.form || (el.closest && el.closest('form')) || null;
    // HTML's own declaration of "this button submits a form" -- type=submit, or
    // the implicit submit inside a <form>. The same thing #24's submit picker
    // reads, and deliberately not a wordlist over the button's label.
    if (t === 'submit' || (el.tagName === 'BUTTON' && !t && f)) o.declaredSubmit++;
    var hit = false;
    if (f) { o.form++; hit = true; }
    if (el.getAttribute('aria-controls')) { o.ctrls++; hit = true; }
    if (el.getAttribute('aria-describedby')) { o.desc++; hit = true; }
    if (el.closest && el.closest('fieldset')) { o.fset++; hit = true; }
    if (!hit) o.none++;
    if (o.names.length < 3) o.names.push((((el.innerText || el.value || '').trim()) || '<no name>').slice(0, 28));
  });
  return o;
})()"""

SELFTEST_HTML = """<form id=f>
  <input id=a required>
  <input id=b required value="x">
  <select id=c required><option value="">pick</option><option value=1>one</option></select>
  <button id=go type=submit disabled>Place order</button>
</form>
<button id=pager disabled aria-controls="t">&laquo;</button>"""


async def _eval(pg):
    return await pg.evaluate(PROBE)


async def self_test():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        pg = await (await b.new_context(viewport={"width": 1280, "height": 900})).new_page()
        await pg.set_content(SELFTEST_HTML)
        r = await _eval(pg)
        await b.close()
    print("against markup that plainly has the shape:", json.dumps(r, ensure_ascii=False))
    ok = r["reqEmpty"] >= 2 and r["form"] == 1 and r["dis"] == 2 and r["declaredSubmit"] == 1
    print("SELF-TEST:", "FIRES — the probe is sound, so its zeros mean something"
          if ok else "*** BROKEN — do not believe any zero it reports ***")
    return 0 if ok else 1


async def corpus(limit):
    from playwright.async_api import async_playwright
    hars = sorted(FROZEN.glob("*.har"))[:limit]
    if not hars:
        print(f"no frozen corpus at {FROZEN} — rebuild with tools/freeze_corpus.py")
        return 1
    T = dict(sites=0, dis=0, sub=0, form=0, ctrls=0, desc=0, fset=0, none=0,
             reqEmpty=0, sitesWithReq=0)
    ex = []
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        for h in hars:
            ctx = await b.new_context(viewport={"width": 1280, "height": 900})
            try:
                await ctx.route_from_har(h, not_found="abort", update=False)
                pg = await ctx.new_page()
                d = json.loads(h.read_text(encoding="utf-8", errors="replace"))
                url = next(e["request"]["url"] for e in d["log"]["entries"]
                           if e.get("response", {}).get("content", {}).get("mimeType", "").startswith("text/html"))
                await pg.goto(url, wait_until="domcontentloaded", timeout=25000)
                await pg.wait_for_timeout(1200)
                r = await _eval(pg)
                T["sites"] += 1
                T["dis"] += r["dis"]; T["sub"] += r["declaredSubmit"]
                for k in ("form", "ctrls", "desc", "fset", "none", "reqEmpty"):
                    T[k] += r[k]
                if r["sawReq"]:
                    T["sitesWithReq"] += 1
                if r["dis"]:
                    ex.append((h.stem, r["dis"], r["declaredSubmit"], r["names"]))
            except Exception:
                pass
            finally:
                try:
                    await ctx.close()
                except Exception:
                    pass
        await b.close()
    print(f"sites replayed: {T['sites']}")
    print(f"visible DISABLED buttons: {T['dis']}")
    print(f"  a DECLARED submit (the only population a blocker note could be right about): {T['sub']}")
    print(f"  a declared association to the fields it gates:")
    print(f"     form owner (what fill_form binds to) {T['form']}")
    print(f"     aria-controls                        {T['ctrls']}")
    print(f"     aria-describedby                     {T['desc']}")
    print(f"     <fieldset>                           {T['fset']}")
    print(f"     NONE OF THESE                        {T['none']}")
    print(f"the fact a note would carry: {T['reqEmpty']} required-and-empty field(s), "
          f"on {T['sitesWithReq']}/{T['sites']} sites")
    print("\nwhat the disabled buttons actually ARE:")
    for s, d, sub, n in ex[:20]:
        print(f"   {s:<20} {d:<3} declared-submit={sub}  {n}")
    return 0


def main():
    args = [a for a in sys.argv[1:]]
    if "--self-test" in args:
        sys.exit(asyncio.run(self_test()))
    lim = int(args[0]) if args and args[0].isdigit() else 10 ** 6
    sys.exit(asyncio.run(corpus(lim)))


if __name__ == "__main__":
    main()
