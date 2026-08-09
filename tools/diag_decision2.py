"""Replicate the exact live failure: fill_form with ONLY the decision-time field.

Opens the Add-Investor modal if needed, then calls fill_form([{selector, value}])
exactly like the agent does, and dumps the result + trigger state after.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from core.bridge.server import ExtensionBridge
from core.bridge.driver import ExtensionDriver


def _txt(e):
    return (str(e.get('name', '')) + str(e.get('text', '')) + str(e.get('label', ''))).lower()


async def main():
    bridge = ExtensionBridge(host="127.0.0.1", port=8765, token=os.environ["BRIDGE_TOKEN"])
    await bridge.start()
    print("bridge up — waiting for the extension to (re)connect ...")
    await bridge.wait_until_connected(timeout=90)
    drv = ExtensionDriver(bridge, job_id="diag_decision2")
    print(await drv.get_url())

    raw = await drv.list_interactive_elements_raw()
    trig = [e for e in raw if 'decision' in _txt(e)]

    if not trig:
        print("modal not open; opening it ...")
        btn = [e for e in raw if 'add investor' in _txt(e)]
        if not btn:
            print("NO 'Add investor' button — wrong page?")
            await bridge.stop()
            return
        print(await drv.click(f"[mmid='{btn[0]['mmid']}']"))
        await asyncio.sleep(1.0)
        raw = await drv.list_interactive_elements_raw()
        opt = [e for e in raw if 'add investor' in _txt(e) and (e.get('role') or '').startswith('menuitem')]
        if opt:
            print(await drv.click(f"[mmid='{opt[0]['mmid']}']"))
        for _ in range(8):  # poll up to ~6s for the modal to finish rendering
            await asyncio.sleep(0.75)
            raw = await drv.list_interactive_elements_raw()
            trig = [e for e in raw if 'decision' in _txt(e)]
            if trig:
                break

    if not trig:
        print("STILL no decision-time trigger — aborting")
        await bridge.stop()
        return

    t = trig[0]
    sel = f"[mmid='{t['mmid']}']"
    print("TRIGGER:", json.dumps({k: t.get(k) for k in ('mmid', 'text', 'label', 'value', 'unselected', 'collapsed')}, ensure_ascii=False))

    print(f"\n== fill_form([{{selector: {sel}, value: '1-3 months'}}]) — the agent's exact path ==")
    res = await drv.fill_form([{"selector": sel, "value": "1-3 months"}])
    print("RESULT:", res)

    await asyncio.sleep(0.8)
    raw2 = await drv.list_interactive_elements_raw()
    m = [e for e in raw2 if e.get('mmid') == t['mmid']]
    print("\nTRIGGER AFTER fill_form:",
          json.dumps({k: m[0].get(k) for k in ('mmid', 'text', 'label', 'value', 'unselected', 'collapsed')}, ensure_ascii=False) if m
          else "(not in listing — modal may have closed!)")
    dlg = [e for e in raw2 if (e.get('role') or '') == 'dialog']
    print("dialog still open:", bool(dlg))

    await bridge.stop()
    print("done.")


asyncio.run(main())
