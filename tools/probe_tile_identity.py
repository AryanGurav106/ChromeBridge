import asyncio, sys, json
from pathlib import Path
from playwright.async_api import async_playwright
ROOT = Path("/Users/aryangurav/Desktop/ChromeBridge")
sys.path.insert(0, str(ROOT / "tools"))
from _extract import extract
BG = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
COLLECT = extract("_collectInteractivePage", BG, verify=True)

# Four plausible ways a periodic-table tile declares itself. The question is
# which of them leave the element with the SYMBOL as its only identity while a
# human reads the full name off the page.
HTML = """<body><div id=t style='display:grid'>
 <!-- A: symbol only, full name nowhere -->
 <div id=a onclick='void 0' style='width:60px;height:60px'><span>36</span><em>Kr</em></div>
 <!-- B: symbol visible, full name in a title -->
 <div id=b onclick='void 0' title='Krypton' style='width:60px;height:60px'><span>36</span><em>Kr</em></div>
 <!-- C: symbol visible, full name in a visible small label (ptable's real shape) -->
 <div id=c onclick='void 0' style='width:60px;height:60px'><span>36</span><em>Kr</em><small>Krypton</small></div>
 <!-- D: symbol visible, full name aria-label -->
 <div id=d onclick='void 0' aria-label='Krypton' style='width:60px;height:60px'><span>36</span><em>Kr</em></div>
</div></body>"""

async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        ctx = await b.new_context(viewport={"width":1280,"height":900})
        await ctx.add_init_script(path=str(ROOT/"extension"/"listener_tag.js"))
        p = await ctx.new_page()
        await p.goto("about:blank"); await p.set_content(HTML); await p.wait_for_timeout(150)
        raw = await p.evaluate("(function(){ "+COLLECT+"; return _collectInteractivePage(true); })()")
        ids = {}
        for e in raw:
            i = await p.evaluate("(m)=>{const x=document.querySelector(`[mmid='${m}']`);return x?x.id:null;}", e.get("mmid"))
            if i: ids[i] = {"name": e.get("name"), "label": e.get("label"), "text": e.get("text")}
        print(json.dumps(ids, ensure_ascii=False, indent=1))
        print("\nDoes any tile carry 'Krypton' anywhere in its identity?")
        for k in "abcd":
            v = ids.get(k)
            blob = json.dumps(v, ensure_ascii=False) if v else ""
            print(f"  {k}: listed={bool(v)}  carries 'Krypton'={'Krypton' in blob}")
        await b.close()
asyncio.run(main())
