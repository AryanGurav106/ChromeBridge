"""One-off live diagnostic for Boxsy's 'Decision Time' dropdown.

Requires: Chrome open with the extension loaded, the Boxsy tab ACTIVE with the
Add-Investor modal open. The user's run_extension.py must be stopped (single-
client bridge); the extension auto-reconnects to this script's server.

Does: finds the decision-time trigger -> clicks it (synthetic, same as
fillDropdown step 1) -> dumps every option-ish element + popover container the
collector can see -> Escape to close. NO submission, NO data entry.
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


async def main():
    bridge = ExtensionBridge(host="127.0.0.1", port=8765, token=os.environ["BRIDGE_TOKEN"])
    await bridge.start()
    print("bridge up — waiting for the extension to (re)connect ...")
    await bridge.wait_until_connected(timeout=90)
    drv = ExtensionDriver(bridge, job_id="diag_decision")
    print(await drv.get_url())

    def _txt(e):
        return (str(e.get('name', '')) + str(e.get('text', '')) + str(e.get('label', ''))).lower()

    raw = await drv.list_interactive_elements_raw()
    trig = [e for e in raw if 'decision' in _txt(e)]

    if not trig:
        # modal not open — open it: "Add investor" button -> "Add investor" menu option
        print("modal not open; opening it ...")
        btn = [e for e in raw if 'add investor' in _txt(e)]
        if not btn:
            print("NO 'Add investor' button on the active tab either — wrong page?")
            await bridge.stop()
            return
        print("opening menu:", json.dumps({k: btn[0].get(k) for k in ('mmid', 'tag', 'name', 'text')}, ensure_ascii=False))
        print(await drv.click(f"[mmid='{btn[0]['mmid']}']"))
        await asyncio.sleep(1.0)
        raw = await drv.list_interactive_elements_raw()
        opt = [e for e in raw if 'add investor' in _txt(e) and (e.get('role') or '').startswith('menuitem')]
        if not opt:
            opt = [e for e in raw if 'add investor' in _txt(e) and e.get('mmid') != btn[0]['mmid']]
        if opt:
            print("clicking menu option:", json.dumps({k: opt[0].get(k) for k in ('mmid', 'tag', 'role', 'name', 'text')}, ensure_ascii=False))
            print(await drv.click(f"[mmid='{opt[0]['mmid']}']"))
            await asyncio.sleep(1.5)
        raw = await drv.list_interactive_elements_raw()
        trig = [e for e in raw if 'decision' in _txt(e)]

    if not trig:
        print("STILL no decision-time trigger — dumping what's visible:")
        for e in raw[:30]:
            print("  ", json.dumps({k: e.get(k) for k in ('mmid', 'tag', 'role', 'name', 'text')}, ensure_ascii=False))
        await bridge.stop()
        return
    t = trig[0]
    print("TRIGGER:", json.dumps(t, ensure_ascii=False))
    sel = f"[mmid='{t['mmid']}']"

    print("\n-- clicking trigger (synthetic) --")
    print(await drv.click(sel))
    await asyncio.sleep(1.2)

    raw2 = await drv.list_interactive_elements_raw()
    opts = [e for e in raw2 if (e.get('role') or '') in ('option', 'menuitem', 'menuitemradio', 'menuitemcheckbox', 'treeitem')]
    print(f"\nOPTION-ROLE elements visible: {len(opts)}")
    for o in opts[:12]:
        print("  ", json.dumps({k: o.get(k) for k in ('mmid', 'tag', 'role', 'name', 'text', 'label', 'x', 'y', 'w', 'h', 'clickable')}, ensure_ascii=False))

    month = [e for e in raw2 if 'month' in (str(e.get('name', '')) + str(e.get('text', '')) + str(e.get('label', ''))).lower()]
    print(f"\nelements containing 'month': {len(month)}")
    for o in month[:12]:
        print("  ", json.dumps({k: o.get(k) for k in ('mmid', 'tag', 'role', 'name', 'text', 'label', 'x', 'y', 'w', 'h', 'clickable')}, ensure_ascii=False))

    async def trigger_state(label):
        r = await drv.list_interactive_elements_raw()
        m = [e for e in r if e.get('mmid') == t['mmid']]
        print(f"\nTRIGGER {label}:",
              json.dumps({k: m[0].get(k) for k in ('mmid', 'text', 'label', 'value', 'unselected', 'collapsed')}, ensure_ascii=False) if m
              else "(not in listing)")
        return m[0] if m else None

    async def reopen_if_closed():
        r = await drv.list_interactive_elements_raw()
        if not [e for e in r if (e.get('role') or '') == 'option' and 'month' in _txt(e)]:
            print("  popover closed — reopening trigger ...")
            print(" ", await drv.click(sel))
            await asyncio.sleep(1.0)

    pick = next((o for o in opts if '1-3' in (o.get('name') or '')), opts[1] if len(opts) > 1 else opts[0]) if opts else None
    if pick:
        psel = f"[mmid='{pick['mmid']}']"

        print(f"\n== ATTEMPT 1: synthetic click on option {pick['name']} ({psel}) ==")
        print(await drv.click(psel))
        await asyncio.sleep(1.0)
        st = await trigger_state("after synthetic option click")
        synthetic_ok = st is not None and '1-3' in (str(st.get('text', '')) + str(st.get('value', '')) + str(st.get('label', '')))
        print("SYNTHETIC PICK REGISTERED:", synthetic_ok)

        if not synthetic_ok:
            await reopen_if_closed()
            # re-find the option (mmids may have changed after reopen)
            r = await drv.list_interactive_elements_raw()
            opt2 = [e for e in r if (e.get('role') or '') == 'option' and '1-3' in _txt(e)]
            if opt2:
                psel2 = f"[mmid='{opt2[0]['mmid']}']"
                print(f"\n== ATTEMPT 2: TRUSTED (CDP) click on option ({psel2}) box({opt2[0].get('x')},{opt2[0].get('y')},{opt2[0].get('w')},{opt2[0].get('h')}) ==")
                print(await drv.click(psel2, trusted=True))
                await asyncio.sleep(1.0)
                st2 = await trigger_state("after TRUSTED option click")
                trusted_ok = st2 is not None and '1-3' in (str(st2.get('text', '')) + str(st2.get('value', '')) + str(st2.get('label', '')))
                print("TRUSTED PICK REGISTERED:", trusted_ok)
            else:
                print("could not re-find the 1-3 months option after reopen")

    print("\n-- Escape to close (cleanup) --")
    print(await drv.press_keys("Escape"))
    await asyncio.sleep(0.4)
    await trigger_state("FINAL")
    await bridge.stop()
    print("done.")


asyncio.run(main())
