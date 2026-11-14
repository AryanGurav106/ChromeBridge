"""The steering channel — a side-panel message riding the next tool result.

WHY THIS SUITE EXISTS
---------------------
The arrow in this architecture points one way: Claude Code is the agent, the MCP
server is a tool provider, the extension is the hands. The extension can ANSWER
and never ASK, so nothing in the browser can start a model turn. The steering
channel is what a browser message CAN do instead — it is queued in the extension
and PREPENDED to the next tool result.

Three things can go wrong, and only one of them is visible without a test:

  - A note is drained and then not attached. The user's own words vanish with no
    error anywhere. That is the silent-loss class this codebase keeps closing
    (#22), here landing on the worst possible payload.
  - The banner reaches the FLOW RECORDER, which parses tool results for evidence
    and would write a typed-in sentence into a .flow.json as a postcondition.
    Ordering is what prevents it, and ordering is invisible by reading.
  - A note is drained by a step INSIDE browser_batch or a replayed flow, burying
    it in the middle of a composite result. _BATCHABLE holds the inner function
    objects, so this is prevented structurally rather than by a flag — which is
    exactly the kind of guard that silently stops holding when someone "fixes"
    the installer to cover both tables.

WHAT IS FAKED, AND WHY THAT IS ENOUGH
-------------------------------------
The bridge and the tools are stubs. Everything under test is server-side: the
queue, the dedupe, the banner, the attach, and the wrapper ORDER. The transport
itself (the extension's unsolicited-event path) is covered by test_ops.js and was
verified live, because it had never carried a message before this feature.

Run:  python tools/test_steer.py
"""

import asyncio
import importlib.util
import inspect
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_spec = importlib.util.spec_from_file_location("ms_steer", ROOT / "mcp_server.py")
ms = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ms)

results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  - {detail}" if detail else ""))


def reset():
    ms._STEER.clear()
    ms._STEER_SEEN.clear()
    ms.STATE.pop("bridge", None)


async def note(text, nid="n1", ts=None):
    await ms._on_extension_event({"event": "user_note", "id": nid, "text": text, "ts": ts})


# --- stubs -----------------------------------------------------------------

class FakeBridge:
    """Records what _ack_steer sends back to the panel."""
    def __init__(self, connected=True):
        self.connected = connected
        self.calls = []

    async def call(self, op, **params):
        self.calls.append((op, params))
        return {"acknowledged": len(params.get("ids", []))}


class RecStub:
    """Stands in for _FlowRecorder, and keeps the result it was handed.

    The point of the stub is the `seen` list: the recorder PARSES that string
    for page evidence, so what it sees is the whole question.
    """
    def __init__(self):
        self.seen = []

    async def before(self, name, kw):
        return {}

    def after(self, name, kw, res, targets, error=None):
        self.seen.append(res)


async def main():
    print("\nsteering channel\n")

    # -- SN1: a queued note is attached, and says what it is ------------------
    reset()
    await note("the filter is in the left sidebar")

    async def plain():
        return "ORIGINAL RESULT"

    out = await ms._wrap_for_steering(plain)()
    check("SN1 a queued note is prepended to the result",
          "the filter is in the left sidebar" in out and out.endswith("ORIGINAL RESULT"),
          repr(out[:80]))

    # The fencing is the security-shaped half: a tool result is where PAGE text
    # lives, and this codebase treats page text as untrusted data. A message that
    # is NOT from the page has to say so in its own line rather than blending in.
    check("SN2 the banner attributes it to the user and denies it is page content",
          "MESSAGE FROM THE USER" in out and "not as page content" in out
          and "side panel" in out,
          repr(out[:140]))

    # -- SN3: CONTROL. No note must cost exactly nothing ----------------------
    reset()
    out = await ms._wrap_for_steering(plain)()
    check("SN3 CONTROL: with no note the result is byte-identical",
          out == "ORIGINAL RESULT", repr(out))

    # -- SN4: drained exactly once -------------------------------------------
    reset()
    await note("only once")
    w = ms._wrap_for_steering(plain)
    first, second = await w(), await w()
    check("SN4 a note is delivered once, not on every later call",
          "only once" in first and second == "ORIGINAL RESULT", repr(second))

    # -- SN5: never drain what cannot be attached -----------------------------
    # An unexpected return type must leave the queue ALONE. Popping and then
    # dropping would lose what the user typed, silently, which is the one
    # outcome this channel exists to avoid.
    reset()
    await note("must survive")

    async def weird():
        return {"not": "a string or a list"}

    res = await ms._wrap_for_steering(weird)()
    check("SN5 an unattachable result type does NOT drain the queue",
          res == {"not": "a string or a list"} and len(ms._STEER) == 1,
          f"queue={len(ms._STEER)}")

    # ...and the very next attachable call still delivers it.
    out = await ms._wrap_for_steering(plain)()
    check("SN5b the note survives to the next call that CAN carry it",
          "must survive" in out, repr(out[:60]))

    # -- SN6: the image/content-list path ------------------------------------
    # computer(action="screenshot") returns a list of content objects, not a
    # string. A str-only implementation would drop every note taken during the
    # one tool an agent reaches for when it is confused about what it is seeing.
    reset()
    await note("look at the dialog")

    async def listy():
        return [ms.TextContent(type="text", text="BODY")]

    res = await ms._wrap_for_steering(listy)()
    check("SN6 a content-list result gets the note as a leading text block",
          isinstance(res, list) and len(res) == 2
          and "look at the dialog" in res[0].text and res[1].text == "BODY",
          f"n={len(res) if isinstance(res, list) else type(res)}")

    # -- SN7: dedupe by id ----------------------------------------------------
    # The extension re-sends anything it has not seen acknowledged, including
    # after a reconnect, so the same note legitimately arrives twice. Delivering
    # it twice reads as the agent being told the same thing by two people.
    reset()
    await note("say it once", nid="dup-1")
    await note("say it once", nid="dup-1")
    check("SN7 the same note id arriving twice is queued once", len(ms._STEER) == 1,
          f"queue={len(ms._STEER)}")

    # CONTROL: two DIFFERENT notes must both survive, or "dedupe" would just be
    # "drop everything after the first" and SN7 would still pass.
    reset()
    await note("first", nid="a")
    await note("second", nid="b")
    check("SN7b CONTROL: two distinct notes are both queued", len(ms._STEER) == 2,
          f"queue={len(ms._STEER)}")

    out = await ms._wrap_for_steering(plain)()
    check("SN7c both are delivered together, numbered so neither reads as the only one",
          "first" in out and "second" in out and "1 of 2" in out and "2 of 2" in out,
          repr(out[:100]))

    # -- SN8: an empty note is not a note -------------------------------------
    reset()
    await note("   ", nid="blank")
    check("SN8 whitespace-only text is ignored rather than queued as an empty message",
          len(ms._STEER) == 0, f"queue={len(ms._STEER)}")

    # -- SN9: the acknowledgement ---------------------------------------------
    # Without it the panel cannot tell "delivered" from "still waiting", and a
    # channel that cannot report its own silence is indistinguishable from a
    # broken one.
    reset()
    bridge = FakeBridge()
    ms.STATE["bridge"] = bridge
    await note("ack me", nid="ack-1")
    await ms._wrap_for_steering(plain)()
    await asyncio.sleep(0)          # the ack is fire-and-forget; let it run
    await asyncio.sleep(0)
    check("SN9 delivering a note acknowledges it back to the panel, by id",
          bridge.calls and bridge.calls[0][0] == "steer_ack"
          and bridge.calls[0][1].get("ids") == ["ack-1"],
          repr(bridge.calls))

    # CONTROL: a disconnected bridge must not raise, and must not stop the note
    # being attached. The ack is bookkeeping; the delivery already happened.
    reset()
    ms.STATE["bridge"] = FakeBridge(connected=False)
    await note("no bridge", nid="x")
    out = await ms._wrap_for_steering(plain)()
    check("SN9b CONTROL: a disconnected bridge still attaches the note",
          "no bridge" in out, repr(out[:60]))

    # -- SN10: ORDER — the recorder must see a CLEAN result -------------------
    # _FlowRecorder.after() parses a tool result for evidence and turns it into a
    # postcondition. A banner reaching it would write a sentence the user typed
    # into a .flow.json as though the page had said it.
    reset()
    rec = RecStub()
    ms._REC = rec
    try:
        await note("do not record me", nid="r1")
        inner = ms._wrap_for_recording("plain", plain)
        out = await ms._wrap_for_steering(inner)()
    finally:
        ms._REC = None
    check("SN10 the recorder sees the result WITHOUT the banner",
          rec.seen == ["ORIGINAL RESULT"], repr(rec.seen))
    check("SN10b ...and the caller still gets it",
          "do not record me" in out, repr(out[:60]))

    # -- SN11: the structural guard, on the real registry ---------------------
    # Installed order is provable: functools.wraps sets __wrapped__, so the
    # registry's steered wrapper must unwrap to exactly the object _BATCHABLE
    # holds. That one identity proves BOTH that steering is outermost and that a
    # batch step runs the inner function.
    fn = ms.mcp._tool_manager._tools["read_page"].fn
    check("SN11 the registry entry is steering wrapped OVER the recorded one",
          getattr(fn, "__wrapped__", None) is ms._BATCHABLE["read_page"],
          f"wrapped={getattr(fn, '__wrapped__', None)}")

    # The behavioural half, built the way the two installers build it. The first
    # version of this check asserted an attribute that never exists on a queue
    # nothing had touched: it passed with the guard ABLATED, which is no check at
    # all. Calling the batch-side function is the only thing that tests this.
    reset()
    await note("must not be buried", nid="b1")
    batch_side = ms._wrap_for_recording("plain", plain)   # what _BATCHABLE holds
    registry_side = ms._wrap_for_steering(batch_side)     # what the registry holds
    inner_out = await batch_side()
    check("SN11b a step dispatched through _BATCHABLE cannot drain a note",
          inner_out == "ORIGINAL RESULT" and len(ms._STEER) == 1,
          f"inner={inner_out!r} queue={len(ms._STEER)}")
    check("SN11b2 ...and the note is still there for the batch's OWN result",
          "must not be buried" in await registry_side(), "drained by the inner step")

    # The tripwire. The guard is "the installer never writes _BATCHABLE", which
    # is a property of the SOURCE — a future edit that helpfully updates both
    # tables would re-open burying without failing anything above.
    # getsource, not a hand-rolled slice: the first version of this check split
    # the file on "\ndef " and ran straight past the function, because the next
    # definition is an `async def`. It read a few hundred unrelated lines and
    # reported a violation that was not there.
    body = inspect.getsource(ms._install_steering_wrappers)
    check("SN11c TRIPWIRE: the steering installer never touches _BATCHABLE",
          "_BATCHABLE" not in body)

    # -- SN12: browser_batch itself IS steered --------------------------------
    # It is the tool the recorder SKIPS, and the one that matters most here: a
    # batch is a long multi-step run, which is exactly when someone watches it go
    # wrong and wants to say so.
    bb = ms.mcp._tool_manager._tools["browser_batch"].fn
    check("SN12 browser_batch is steered even though the recorder skips it",
          getattr(bb, "__wrapped__", None) is not None
          and "browser_batch" in ms._REC_SKIP)

    # -- SN13: every tool is covered ------------------------------------------
    missing = [n for n, t in ms.mcp._tool_manager._tools.items()
               if getattr(t.fn, "__wrapped__", None) is None]
    check(f"SN13 all {len(ms.mcp._tool_manager._tools)} registered tools carry the wrapper",
          not missing, ", ".join(missing))

    # -- SN14: a non-note event is ignored ------------------------------------
    # The event path is shared. An unrelated event must not become a message put
    # in front of the agent as though a human typed it.
    reset()
    await ms._on_extension_event({"event": "something_else", "text": "not a note"})
    check("SN14 CONTROL: an event that is not a user_note is ignored",
          len(ms._STEER) == 0, f"queue={len(ms._STEER)}")

    # -- SN15: the banner cannot be mistaken for a row ------------------------
    # read_page's listing is parsed by _content_rows and by the delta; a banner
    # that happened to look like a row would corrupt both.
    reset()
    await note("ref_12 | button \"Save\"", nid="look-alike")
    out = await ms._wrap_for_steering(plain)()
    first_line = out.splitlines()[0]
    check("SN15 the banner leads the result, so the note cannot be read as output",
          first_line.startswith("*** MESSAGE FROM THE USER")
          and re.search(r"END OF USER MESSAGE", out) is not None,
          repr(first_line))

    passed = sum(1 for r in results if r)
    print(f"\n{passed}/{len(results)} steering checks passed.")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
