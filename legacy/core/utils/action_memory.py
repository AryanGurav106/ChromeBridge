"""Per-task episodic action memory (Reflexion-lite self-correction).

The Browser Agent runs as a single pydantic-ai loop, so its message history
already carries prior tool results. What it lacks is a *deterministic* signal
when it starts repeating itself — re-clicking a dead element or re-observing an
unchanged page. This tiny memory counts action signatures within one task and
produces escalating guidance so the agent breaks the loop instead of burning
steps. It is created fresh per task (one per BA_Deps).
"""


class ActionMemory:
    def __init__(self):
        self.counts: dict[str, int] = {}

    def record(self, signature: str) -> int:
        """Record an attempt of `signature`; return how many times it's been seen."""
        self.counts[signature] = self.counts.get(signature, 0) + 1
        return self.counts[signature]

    def click_note(self, selector: str, count: int, had_effect: bool) -> str:
        """Escalating guidance for repeated clicks on the same selector."""
        if count >= 3:
            return (
                f"\nSTOP: you have clicked {selector} {count} times — this is a loop. "
                "Do NOT click it again. Get a fresh DOM (get_interactive_elements), use "
                "analyze_screen to see what's actually there, pick a DIFFERENT mmid, or "
                "conclude the task with what you know."
            )
        if count == 2 and not had_effect:
            return (
                f"\nNote: you have now clicked {selector} twice with no detectable effect. "
                "Don't repeat it — re-check the element or try a different one."
            )
        return ""

    def observe_note(self, tool: str, count: int) -> str:
        """Escalating guidance for repeated observation calls."""
        if count >= 3:
            return (
                f"\nSTOP: you have called {tool} {count} times. Re-observing is not making "
                "progress (the page may be unchanged). Take a concrete action now "
                "(click/type/navigate) or give your final answer."
            )
        return ""
