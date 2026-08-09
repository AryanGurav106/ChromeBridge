"""fill_form on the decision-time combobox (currently '1-3 months') -> '6-12 months'.
This is the agent's exact code path that failed live ('Filled 0/1')."""
import asyncio, json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv; load_dotenv()
from core.bridge.server import ExtensionBridge
from core.bridge.driver import ExtensionDriver


async def main():
    bridge = ExtensionBridge(host="127.0.0.1", port=8765, token=os.environ["BRIDGE_TOKEN"])
    await bridge.start()
    await bridge.wait_until_connected(timeout=90)
    drv = ExtensionDriver(bridge, job_id="diag_fillform")
    print(await drv.get_url())

    raw = await drv.list_interactive_elements_raw()
    # find the decision-time combobox: prefer the 'Select decision time...' label,
    # else the combobox currently showing a months value
    trig = [e for e in raw if 'decision' in (str(e.get('text','')) + str(e.get('label',''))).lower()]
    if not trig:
        trig = [e for e in raw if (e.get('role') or '') == 'combobox' and 'month' in str(e.get('text','')).lower()]
    if not trig:
        print("no decision-time combobox found; aborting")
        await bridge.stop()
        return
    t = trig[0]
    sel = f"[mmid='{t['mmid']}']"
    print("TRIGGER BEFORE:", json.dumps({k: t.get(k) for k in ('mmid','text','value','unselected','collapsed')}, ensure_ascii=False))

    target = "6-12 months" if "6-12" not in str(t.get('text','')) else "3-6 months"
    print(f"\n== fill_form([{{selector: {sel}, value: '{target}'}}]) ==")
    res = await drv.fill_form([{"selector": sel, "value": target}])
    print("RESULT:", res)

    await asyncio.sleep(0.8)
    raw2 = await drv.list_interactive_elements_raw()
    m = [e for e in raw2 if e.get('mmid') == t['mmid']]
    print("\nTRIGGER AFTER:",
          json.dumps({k: m[0].get(k) for k in ('mmid','text','value','unselected','collapsed')}, ensure_ascii=False) if m
          else "(not in listing — modal closed?!)")
    dlg = [e for e in raw2 if (e.get('role') or '') == 'dialog']
    print("dialog still open:", bool(dlg))
    await bridge.stop()
    print("done.")


asyncio.run(main())
