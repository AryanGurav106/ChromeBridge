"""Command-line runner for the standalone Browser Agent.

Examples:
    python run.py "Go to wikipedia.org and tell me today's featured article"
    python run.py --url https://news.ycombinator.com "Summarize the top 3 stories"
    python run.py --headless "What is the title of example.com?"
    python run.py            # interactive REPL: type tasks one per line

The agent drives a LOCAL Chromium/Chrome window via Playwright.
"""

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv
load_dotenv()

from core.utils.model_profiles import apply_profile, describe_active, AVAILABLE  # noqa: E402
from harness import BrowserAgentHarness  # noqa: E402


async def _run_once(args):
    async with BrowserAgentHarness(
        start_url=args.url,
        headless=args.headless,
        show_overlay=not args.no_overlay,
        take_screenshots=not args.no_screenshots,
        record_video=args.record_video,
        vault_ns=args.vault_ns,
        user_data_dir=args.profile,
    ) as h:
        if args.task:
            answer = await h.run_task(" ".join(args.task))
            print("\n=== ANSWER ===\n" + str(answer) + "\n")
        else:
            # Interactive REPL — reuses the same browser session across tasks.
            print("Interactive mode. Type a task and press Enter (Ctrl-C or 'exit' to quit).")
            loop = asyncio.get_event_loop()
            while True:
                try:
                    task = await loop.run_in_executor(None, sys.stdin.readline)
                except (EOFError, KeyboardInterrupt):
                    break
                task = (task or "").strip()
                if not task or task.lower() in ("exit", "quit"):
                    break
                answer = await h.run_task(task)
                print("\n=== ANSWER ===\n" + str(answer) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Run the standalone Browser Agent on a local browser.")
    parser.add_argument("task", nargs="*", help="Natural-language task. Omit for interactive mode.")
    parser.add_argument("--url", default="https://google.com", help="Starting URL (default: https://google.com)")
    parser.add_argument("--headless", action="store_true", help="Run the browser headless")
    parser.add_argument("--no-overlay", action="store_true", help="Disable the on-page status overlay")
    parser.add_argument("--no-screenshots", action="store_true", help="Disable screenshot capture")
    parser.add_argument("--record-video", action="store_true", help="Record a video of the session")
    parser.add_argument("--vault-ns", default="default", help="Namespace in secrets/local_secrets.json for credentials")
    parser.add_argument("--profile", default=None,
                        help="Path to a persistent Chrome profile dir to reuse logins "
                             "(defaults to BROWSER_STORAGE_DIR env var, else a throwaway profile)")
    parser.add_argument("--model", default=os.getenv("MODEL_PROFILE"),
                        help=f"Model profile. One of: {', '.join(AVAILABLE)}. "
                             "Default uses AGENTIC_BROWSER_TEXT_* env vars as-is.")
    args = parser.parse_args()
    if args.model:
        try:
            used = apply_profile(args.model)
            print(f"[model] profile={used}   {describe_active()}")
        except Exception as e:
            print(f"[model] failed: {e}", file=sys.stderr); sys.exit(2)

    try:
        asyncio.run(_run_once(args))
    except KeyboardInterrupt:
        print("\nInterrupted.")


if __name__ == "__main__":
    main()
