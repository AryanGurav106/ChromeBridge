"""CLI: run the Browser Agent against the user's real Chrome via the extension.

Usage:
  python run_extension.py "Open my gmail and tell me the subject of the latest email"
  python run_extension.py --port 8765 --token <hex> "..."
  python run_extension.py            # interactive REPL

First-time setup is printed at startup: load the extension/ folder as an
unpacked extension in chrome://extensions (Developer mode), open its side
panel, paste the token, then your tasks run on the active Chrome tab.
"""

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from core.utils.model_profiles import apply_profile, describe_active, AVAILABLE  # noqa: E402
from extension_harness import ExtensionAgentHarness  # noqa: E402


async def _inspect_only(args):
    """No-LLM diagnostic dump: connects to the extension, captures URL,
    interactive elements list (formatted + raw), full page text, runs keyword
    sweeps, and writes everything to temp/inspect_<ts>/. Then exits."""
    import json as _j
    import time as _t
    from extension_harness import ExtensionAgentHarness as _H
    async with _H(host=args.host, port=args.port, token=args.token) as h:
        drv = h.driver
        out_dir = os.path.join(drv.job_dir, f"inspect_{int(_t.time())}")
        os.makedirs(out_dir, exist_ok=True)

        url      = await drv.get_url()
        elements = await drv.get_interactive_elements()
        raw      = await drv.list_interactive_elements_raw()
        text     = await drv.get_dom_text()

        # Filter-effectiveness audit: count things by section/role/tag so we
        # can see at a glance what kind of page this is and where the listing
        # budget is going. Empirically driven noise filtering.
        from collections import Counter as _C
        sec_count = _C(e.get("section") or "(none)" for e in raw)
        tag_count = _C(e.get("tag") for e in raw)
        role_count = _C(e.get("role") or "(none)" for e in raw)
        unlabeled = sum(1 for e in raw if not (e.get("label") or "").strip())
        tiny = sum(1 for e in raw if (e.get("w") or 0) < 12 and (e.get("h") or 0) < 12)
        occluded = sum(1 for e in raw if e.get("clickable") is False)
        active_count = sum(1 for e in raw if e.get("active"))
        # default keyword list also drives the deep inspect.
        kw_default = ["investor updates", "data room", "dataroom", "investor", "updates"]
        kws_for_deep = [k.strip() for k in (args.kw.split(",") if args.kw else kw_default) if k.strip()]
        deep     = await drv.deep_inspect(kws_for_deep)

        # save
        with open(os.path.join(out_dir, "url.txt"), "w", encoding="utf-8") as f: f.write(url)
        with open(os.path.join(out_dir, "elements.txt"), "w", encoding="utf-8") as f: f.write(elements)
        with open(os.path.join(out_dir, "raw.json"), "w", encoding="utf-8") as f: _j.dump(raw, f, indent=2)
        with open(os.path.join(out_dir, "text.txt"), "w", encoding="utf-8") as f: f.write(text)
        with open(os.path.join(out_dir, "deep.json"), "w", encoding="utf-8") as f: _j.dump(deep, f, indent=2)

        # default keywords are the ones the agent was trying to find;
        # caller can pass more via --kw "foo,bar".
        kws = ["investor", "investor updates", "data room", "dataroom", "updates"]
        if args.kw:
            kws = [k.strip() for k in args.kw.split(",") if k.strip()]

        print("\n========= INSPECTION DUMP =========")
        print(f"saved under: {out_dir}")
        print("\n--- URL ---")
        print(url)

        print("\n--- KEYWORD SWEEP ---")
        for kw in kws:
            lk = kw.lower()
            in_elems = lk in elements.lower()
            in_text  = lk in text.lower()
            in_raw_labels = [e for e in raw if lk in (e.get("label") or "").lower()]
            print(f"  {kw!r}:  /elements={in_elems}  /text={in_text}  raw_label_matches={len(in_raw_labels)}")
            for e in in_raw_labels[:5]:
                print(f"      raw mmid={e.get('mmid')} {e.get('tag')} "
                      f"label={e.get('label')!r} "
                      f"box=({e.get('x')},{e.get('y')},{e.get('w')},{e.get('h')}) "
                      f"clickable={e.get('clickable')}")

        print("\n--- /elements (full, formatted; first 80 lines) ---")
        for ln in elements.splitlines()[:80]:
            print(ln)
        if len(elements.splitlines()) > 80:
            print(f"... ({len(elements.splitlines())} lines total; see elements.txt)")

        print("\n--- /raw (structured, first 30 of "
              f"{len(raw)}) ---")
        for e in raw[:30]:
            print(f"  mmid={e.get('mmid')} {e.get('tag')} "
                  f"label={(e.get('label') or '')[:50]!r} "
                  f"box=({e.get('x')},{e.get('y')},{e.get('w')},{e.get('h')}) "
                  f"clickable={e.get('clickable')}")

        # Text near each keyword to see if it's visually present but
        # not interactive (i.e. a label without an associated clickable).
        print("\n--- /text snippets around keywords ---")
        low = text.lower()
        for kw in kws:
            pos = low.find(kw.lower())
            if pos >= 0:
                start = max(0, pos - 80)
                end = min(len(text), pos + 80 + len(kw))
                snippet = text[start:end].replace("\n", " \\n ")
                print(f"  {kw!r} @ char {pos}: ...{snippet}...")
            else:
                print(f"  {kw!r}: NOT FOUND in page text")

        print("\n--- DEEP INSPECT: viewport + global counts ---")
        print(f"  viewport: {deep.get('viewport')}    scroll: {deep.get('scroll')}")
        print(f"  counts:   {deep.get('counts')}")

        print(f"\n--- DEEP INSPECT: label matches ({len(deep.get('labelMatches', []))}) ---")
        for m in (deep.get("labelMatches") or [])[:40]:
            v = m.get("verdict", {})
            print(f"  [{m.get('tag')}] text={m.get('text')!r}  rect={m.get('rect')}  "
                  f"role={m.get('role')!r}  href={m.get('href')!r}  "
                  f"cursor={m.get('cursor')!r}  vis={m.get('visibility')}/{m.get('display')}/op{m.get('opacity')}  "
                  f"verdict=interactive:{v.get('isInteractive')} visible:{v.get('visible')} "
                  f"inVP:{v.get('inViewport')} clickable:{v.get('clickable')}")
            ca = m.get("clickAncestor")
            if ca:
                v2 = ca.get("verdict", {})
                print(f"     ^ clickAncestor [{ca.get('tag')}] depth={ca.get('depth')}  "
                      f"role={ca.get('role')!r} href={ca.get('href')!r}  "
                      f"cursor={ca.get('cursor')!r}  rect={ca.get('rect')}  "
                      f"verdict=interactive:{v2.get('isInteractive')} visible:{v2.get('visible')} "
                      f"inVP:{v2.get('inViewport')} clickable:{v2.get('clickable')}")
            else:
                print(f"     ^ NO clickable ancestor within 8 levels")

        # Top candidate-interactive elements (regardless of pass/fail) — first 25.
        cands = deep.get("allCandidates") or []
        print(f"\n--- DEEP INSPECT: candidate-interactive elements (first 25 of {len(cands)}) ---")
        for c in cands[:25]:
            v = c.get("verdict", {})
            print(f"  [{c.get('tag')}] text={c.get('text')!r}  rect={c.get('rect')}  "
                  f"cursor={c.get('cursor')!r}  "
                  f"verdict=interactive:{v.get('isInteractive')} visible:{v.get('visible')} "
                  f"inVP:{v.get('inViewport')} clickable:{v.get('clickable')}")

        print("\n--- LISTING NOISE AUDIT (post-filter) ---")
        print(f"  raw elements returned: {len(raw)}  | listing chars: {len(elements)}  | DOM text chars: {len(text)}")
        print(f"  by section:  {dict(sec_count.most_common(10))}")
        print(f"  by tag:      {dict(tag_count.most_common(10))}")
        print(f"  by role:     {dict(role_count.most_common(8))}")
        print(f"  unlabeled:   {unlabeled}   (form fields exempted — these are mystery elements)")
        print(f"  sub-12px:    {tiny}        (likely decoration that slipped through)")
        print(f"  occluded:    {occluded}    (overlay-blocked — agent should dismiss overlay)")
        print(f"  marked active/selected/current: {active_count}")

        print("\n========= END INSPECTION =========\n")


async def _run(args):
    if args.inspect:
        await _inspect_only(args)
        return
    async with ExtensionAgentHarness(
        host=args.host, port=args.port, token=args.token,
        request_limit=args.request_limit, vault_ns=args.vault_ns,
        keep_history=not args.no_history,
    ) as h:
        # In one-shot mode, only the single task closes the bridge. Most users
        # want a persistent session — pass no task arg to get the REPL below.
        if args.task and not args.stay:
            answer = await h.run_task(" ".join(args.task))
            print("\n=== ANSWER ===\n" + str(answer) + "\n")
            return

        # Persistent / REPL mode: the bridge + extension connection stays alive
        # across as many tasks as you want. The connection only drops if you
        # quit, the terminal closes, or you reload the extension.
        print("\n" + "─" * 60)
        print(" Ready. Extension stays connected across tasks.")
        print(" Type a task and press Enter. 'quit' or Ctrl-D to exit.")
        print("─" * 60)

        # Run the initial task first if one was passed alongside --stay.
        if args.task:
            ans = await h.run_task(" ".join(args.task))
            print("\n=== ANSWER ===\n" + str(ans) + "\n")

        print("Slash commands (no LLM cost): /url  /elements  /text  /raw  /tab  /help")

        loop = asyncio.get_event_loop()
        while True:
            try:
                line = await loop.run_in_executor(None, lambda: input("agent> "))
            except EOFError:
                print()
                break
            except KeyboardInterrupt:
                print("\n(Ctrl-C — type 'quit' to exit cleanly so the extension detaches properly)")
                continue
            line = (line or "").strip()
            if not line:
                continue
            if line.lower() in ("exit", "quit", ":q"):
                break
            if line.startswith("/"):
                try:
                    await _handle_slash(h, line)
                except Exception as e:
                    print(f"\n=== ERROR ===\n{e}\n")
                continue
            try:
                ans = await h.run_task(line)
                print("\n=== ANSWER ===\n" + str(ans) + "\n")
            except Exception as e:
                print(f"\n=== ERROR ===\n{e}\n")


async def _handle_slash(h, line: str) -> None:
    """Direct extension queries — no agent, no LLM call. Cheap, fast inspection."""
    cmd, _, _ = line.partition(" ")
    cmd = cmd.lower()
    drv = h.driver
    if cmd in ("/help", "/?"):
        print(
            "Slash commands (no LLM, free):\n"
            "  /tab        currently active tab (url + title)\n"
            "  /url        same as /tab\n"
            "  /elements   structured listing of visible interactive elements\n"
            "  /text       full visible page text\n"
            "  /raw        structured element list as JSON (with boxes)\n"
            "  /reset      clear carried-over message history for next task\n"
            "  /history    show how many messages are carried into next task\n"
            "  /save NAME  save the LAST successful task as a replayable recipe\n"
            "  /recipes    list saved recipes\n"
            "  /run NAME   replay a saved recipe (no LLM — near-instant)\n"
            "  /help       this message\n"
        )
        return
    if cmd == "/save":
        name = line.partition(" ")[2].strip()
        if not name:
            print("Usage: /save <name>   (saves the last completed task)"); return
        print(h.save_last_as_recipe(name)); return
    if cmd == "/recipes":
        items = h.list_recipes()
        if not items: print("No recipes saved yet. After a successful task, use: /save <name>")
        else:
            print(f"{len(items)} recipe(s):")
            for r in items:
                print(f"  {r['name']:<24}  steps={r['steps']:<3}  task={r.get('task','')[:60]!r}")
        return
    if cmd == "/run":
        name = line.partition(" ")[2].strip()
        if not name:
            print("Usage: /run <name>"); return
        out = await h.run_recipe(name)
        print(out); return
    if cmd == "/reset":
        h.reset_history()
        print("Message history cleared. Next task starts fresh.")
        return
    if cmd == "/history":
        print(f"Carrying {len(h._history)} messages of context into the next task "
              f"(keep_history={h.keep_history}). Use /reset to clear.")
        return
    if cmd in ("/url", "/tab"):
        print(await drv.get_url())
        return
    if cmd == "/elements":
        out = await drv.get_interactive_elements()
        path = os.path.join(drv.job_dir, "manual_elements.txt")
        try:
            with open(path, "w", encoding="utf-8") as f: f.write(out)
            print(f"\n(saved full output to {path})\n")
        except Exception: pass
        print(out)
        return
    if cmd == "/text":
        out = await drv.get_dom_text()
        path = os.path.join(drv.job_dir, "manual_text.txt")
        try:
            with open(path, "w", encoding="utf-8") as f: f.write(out)
            print(f"\n(saved full output to {path})\n")
        except Exception: pass
        print(out[:4000] + ("\n... [truncated]" if len(out) > 4000 else ""))
        return
    if cmd == "/raw":
        raw = await drv.list_interactive_elements_raw()
        import json as _j
        path = os.path.join(drv.job_dir, "manual_raw.json")
        try:
            with open(path, "w", encoding="utf-8") as f: _j.dump(raw, f, indent=2)
            print(f"\n(saved {len(raw)} elements to {path})\n")
        except Exception: pass
        for e in raw[:30]:
            print(f"  mmid={e.get('mmid')} {e.get('tag')} \"{e.get('label','')}\" "
                  f"box=({e.get('x')},{e.get('y')},{e.get('w')},{e.get('h')}) "
                  f"clickable={e.get('clickable')}")
        if len(raw) > 30:
            print(f"  ... and {len(raw)-30} more (see {path})")
        return
    print(f"Unknown slash command: {cmd}. Try /help.")


def main():
    p = argparse.ArgumentParser(description="Run the Browser Agent against the user's real Chrome (via extension).")
    p.add_argument("task", nargs="*", help="Natural-language task. Omit for interactive mode.")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--token", default=os.getenv("BRIDGE_TOKEN"),
                   help="Pin a specific token instead of auto-generating one. "
                        "Falls back to the BRIDGE_TOKEN env var (set it in .env to "
                        "paste the token into the extension only once, ever).")
    p.add_argument("--request-limit", type=int, default=40)
    p.add_argument("--vault-ns", default="default")
    p.add_argument("--stay", action="store_true",
                   help="After the initial task, stay in the REPL with the extension still connected, "
                        "instead of exiting and disconnecting.")
    p.add_argument("--inspect", action="store_true",
                   help="Diagnostic dump only: capture URL + interactive elements + page text + raw "
                        "structured elements + keyword sweep, save to temp/, print to stdout, then exit. "
                        "No LLM calls.")
    p.add_argument("--kw", default=None,
                   help="Comma-separated keywords for the --inspect sweep (default: investor, data room, ...).")
    p.add_argument("--no-history", action="store_true",
                   help="Don't carry the previous task's messages into the next REPL task.")
    p.add_argument("--model", default=os.getenv("MODEL_PROFILE"),
                   help=f"Model profile to use. One of: {', '.join(AVAILABLE)}. "
                        f"Default uses the AGENTIC_BROWSER_TEXT_* env vars as-is.")
    args = p.parse_args()
    if args.model:
        try:
            used = apply_profile(args.model)
            print(f"[model] profile={used}   {describe_active()}")
        except Exception as e:
            print(f"[model] failed to apply profile {args.model!r}: {e}", file=sys.stderr); sys.exit(2)
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        print("\nInterrupted.")


if __name__ == "__main__":
    main()
