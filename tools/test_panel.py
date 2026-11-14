"""The side panel, rendered under Playwright with chrome.* stubbed.

WHY THIS SUITE EXISTS
---------------------
The panel is the only surface in this project with no automated coverage, and it
is where every grant, every pause and now every steering note is produced. A
syntax check says nothing about a listener bound to an id that does not exist, a
render that throws on first paint, or a button that silently does nothing.
CLAUDE.md already names this technique — "render it under Playwright with chrome.*
stubbed" — as the way to iterate on the panel without a load-unpacked cycle; it
had just never been turned into a test.

It opened with the STEERING composer because that is what it was written for, and
three of its first assertions were wrong about the PROBE rather than the product:
`.steer-state` is `text-transform: uppercase`, so inner_text() returns WAITING,
and a closed <details> yields empty inner_text() for everything inside it. Both
are recorded here because the next person writing a panel check will hit them.

WHAT IS FAKED
-------------
`chrome.runtime`, `chrome.storage` and `chrome.tabs`. The stub mimics the one
behaviour that matters: background.js is the only writer of `bridge_steer`, and
the panel learns about a state change through storage.onChanged — so the stub
writes storage and fires the listener rather than answering the panel directly.

Run:  python tools/test_panel.py
"""
import asyncio, json, sys
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
STUB = """
window.__sent = [];
window.__storage = {};
window.__listeners = [];
window.chrome = {
  runtime: {
    sendMessage: async (msg) => {
      window.__sent.push(msg);
      if (msg.kind === "get_status") return { status: { connected: true, since: Date.now() } };
      if (msg.kind === "steer") {
        const note = { id: "id-" + window.__sent.length, text: msg.text, ts: Date.now(), state: "sent" };
        const cur = window.__storage.bridge_steer || [];
        cur.push(note);
        window.__storage.bridge_steer = cur;
        // mimic the service worker's storage write landing back here
        setTimeout(() => window.__listeners.forEach(f =>
          f({ bridge_steer: { newValue: cur } }, "local")), 0);
        return { ok: true, note, connected: true };
      }
      if (msg.kind === "clear_steer") { window.__storage.bridge_steer = []; return { ok: true }; }
      return { ok: true };
    },
    onMessage: { addListener: () => {} },
  },
  storage: {
    local: {
      get: async (keys) => {
        const out = {};
        for (const k of (Array.isArray(keys) ? keys : [keys])) if (k in window.__storage) out[k] = window.__storage[k];
        return out;
      },
      set: async (o) => { Object.assign(window.__storage, o); },
      remove: async () => {},
    },
    onChanged: { addListener: (f) => window.__listeners.push(f) },
  },
  tabs: { onActivated: { addListener: () => {} }, onUpdated: { addListener: () => {} },
          query: async () => [{ id: 1, url: "https://example.test/x", active: true }] },
};
"""

async def main():
    fails = []
    TOTAL = [0]
    def check(name, ok, detail=""):
        TOTAL[0] += 1
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  - {detail}" if detail else ""))
        if not ok: fails.append(name)

    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        await pg.add_init_script(STUB)
        await pg.goto((ROOT / "extension" / "panel.html").as_uri())
        await pg.wait_for_timeout(400)

        check("PN1 the panel renders with no page error", not errors, "; ".join(errors[:2]))
        check("PN2 the Steer card exists", await pg.locator("details[data-fold='steer']").count() == 1)
        check("PN3 composer + send button are present",
              await pg.locator("#steer_text").count() == 1 and await pg.locator("#steer_send").count() == 1)
        check("PN4 the limit is stated up front, not hidden",
              "next browser action" in (await pg.locator("#steer_when").text_content()))
        check("PN5 the note list starts hidden", await pg.locator("#steer_list").is_hidden())
        check("PN6 Clear is hidden while there is nothing to clear",
              await pg.locator("#clear_steer").is_hidden())

        # open the card and send one
        await pg.locator("details[data-fold='steer'] summary").click()
        await pg.fill("#steer_text", "the filter is in the left sidebar")
        await pg.click("#steer_send")
        await pg.wait_for_timeout(300)

        sent = await pg.evaluate("window.__sent.filter(m => m.kind === 'steer')")
        check("PN7 clicking Send hands the text to the worker",
              len(sent) == 1 and sent[0]["text"] == "the filter is in the left sidebar", json.dumps(sent))
        check("PN8 the composer is cleared", (await pg.input_value("#steer_text")) == "")
        check("PN9 the note appears in the list with its state",
              await pg.locator("#steer_list li").count() == 1
              and "waiting" in (await pg.locator(".steer-state").first.inner_text()).lower(),
              await pg.locator("#steer_list").inner_text())
        check("PN10 Clear appears once there is something to clear",
              await pg.locator("#clear_steer").is_visible())

        # Enter sends; Shift+Enter must not.
        await pg.fill("#steer_text", "second note")
        await pg.press("#steer_text", "Enter")
        await pg.wait_for_timeout(250)
        n_after_enter = len(await pg.evaluate("window.__sent.filter(m => m.kind === 'steer')"))
        check("PN11 Enter sends", n_after_enter == 2, f"n={n_after_enter}")

        await pg.fill("#steer_text", "a draft")
        await pg.press("#steer_text", "Shift+Enter")
        await pg.wait_for_timeout(250)
        n_after_shift = len(await pg.evaluate("window.__sent.filter(m => m.kind === 'steer')"))
        check("PN12 CONTROL: Shift+Enter does NOT send (it is a newline)",
              n_after_shift == 2, f"n={n_after_shift}")
        check("PN12b ...and the draft is still in the box",
              "a draft" in (await pg.input_value("#steer_text")))

        # an empty send must do nothing
        await pg.fill("#steer_text", "   ")
        await pg.click("#steer_send")
        await pg.wait_for_timeout(200)
        n_blank = len(await pg.evaluate("window.__sent.filter(m => m.kind === 'steer')"))
        check("PN13 CONTROL: a blank note is not sent", n_blank == 2, f"n={n_blank}")

        # a delivered note must read differently from a waiting one
        await pg.evaluate("""() => {
          const cur = window.__storage.bridge_steer;
          cur[0].state = 'delivered'; cur[0].delivered_ts = Date.now();
          window.__listeners.forEach(f => f({ bridge_steer: { newValue: cur } }, 'local'));
        }""")
        await pg.wait_for_timeout(200)
        txt = await pg.locator("#steer_list").inner_text()
        check("PN14 an acknowledged note reads 'delivered', not 'waiting'",
              "delivered" in txt.lower() and "waiting" in txt.lower(), txt.replace("\n", " | "))

        check("PN15 still no page errors after driving it", not errors, "; ".join(errors[:2]))
        await b.close()

    print(f"\n{TOTAL[0] - len(fails)}/{TOTAL[0]} panel checks passed."
          + (f"  FAILED: {', '.join(fails)}" if fails else ""))
    return 1 if fails else 0

sys.exit(asyncio.run(main()))
