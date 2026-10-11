"""Dump the current listing — what does the collector see right now?"""
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
    drv = ExtensionDriver(bridge, job_id="diag_dump")
    print(await drv.get_url())
    raw = await drv.list_interactive_elements_raw()
    print(f"{len(raw)} elements")
    for e in raw:
        sec = e.get('section') or ''
        if sec in ('dialog',) or (e.get('role') or '') in ('dialog', 'combobox', 'option', 'listbox', 'menuitem') \
           or 'add record' in (str(e.get('name','')) + str(e.get('text','')) + str(e.get('label',''))).lower():
            print(" ", json.dumps({k: e.get(k) for k in ('mmid','tag','role','name','text','label','value','section','disabled','unselected','collapsed','x','y')}, ensure_ascii=False))
    await bridge.stop()


asyncio.run(main())
