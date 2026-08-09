"""Per-task timing tracker.

Records the wall-clock time spent in each tool call (and within that, how much
was the WS bridge round-trip to the extension vs. extension/page work). At
end-of-task we print a breakdown so we can see whether the latency budget is
going to: (a) LLM thinking, (b) the bridge / Chrome work, or (c) Python/agent
framework overhead.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class _Call:
    name: str
    start: float
    end: float = 0.0
    bridge_ms: float = 0.0


@dataclass
class TimingTracker:
    task_name: str = ""
    task_start: float = 0.0
    task_end: float = 0.0
    calls: list[_Call] = field(default_factory=list)
    requests: Optional[int] = None
    total_tokens: Optional[int] = None
    request_tokens: Optional[int] = None
    response_tokens: Optional[int] = None

    # ------- lifecycle ----------------------------------------------------
    def start_task(self, name: str) -> None:
        self.task_name = name
        self.task_start = time.monotonic()
        self.task_end = 0.0
        self.calls.clear()
        self.requests = self.total_tokens = self.request_tokens = self.response_tokens = None

    def end_task(self) -> None:
        self.task_end = time.monotonic()

    # ------- per-tool measurement ----------------------------------------
    def begin(self, name: str) -> int:
        self.calls.append(_Call(name=name, start=time.monotonic()))
        return len(self.calls) - 1

    def end(self, idx: int, bridge_ms: float = 0.0) -> None:
        c = self.calls[idx]
        c.end = time.monotonic()
        c.bridge_ms = bridge_ms

    # ------- usage (from pydantic-ai RunResult) --------------------------
    def set_usage(self, requests: Optional[int], total: Optional[int],
                   req: Optional[int], resp: Optional[int]) -> None:
        self.requests, self.total_tokens, self.request_tokens, self.response_tokens = \
            requests, total, req, resp

    # ------- report -------------------------------------------------------
    def summary(self) -> str:
        total_ms = max((self.task_end - self.task_start) * 1000.0, 1.0)
        tool_ms = sum((c.end - c.start) * 1000.0 for c in self.calls if c.end)
        bridge_ms = sum(c.bridge_ms for c in self.calls)
        nontool_ms = max(total_ms - tool_ms, 0.0)  # LLM thinking + framework

        pct = lambda v: f"{v / total_ms * 100:5.1f}%"
        lines = []
        lines.append("")
        lines.append("=" * 64)
        lines.append(f" TIMING  task: {self.task_name!r}")
        lines.append("=" * 64)
        lines.append(f"  TOTAL                 {total_ms:8.0f} ms  ({pct(total_ms)})")
        lines.append(f"  LLM + framework       {nontool_ms:8.0f} ms  ({pct(nontool_ms)})")
        lines.append(f"  Tools (sum)           {tool_ms:8.0f} ms  ({pct(tool_ms)})")
        lines.append(f"    of which bridge WS  {bridge_ms:8.0f} ms  ({pct(bridge_ms)})")
        lines.append(f"    extension/page work {tool_ms - bridge_ms:8.0f} ms")
        if self.requests is not None:
            lines.append(f"  LLM requests          {self.requests}")
        if self.total_tokens is not None:
            req_t = self.request_tokens or 0
            resp_t = self.response_tokens or 0
            lines.append(f"  Tokens (req/resp/tot) {req_t} / {resp_t} / {self.total_tokens}")
        lines.append("")
        if self.calls:
            lines.append(f"  {len(self.calls)} tool calls (slowest first):")
            grouped: dict[str, list[_Call]] = {}
            for c in self.calls:
                grouped.setdefault(c.name, []).append(c)
            ordered = sorted(
                grouped.items(),
                key=lambda kv: -sum((c.end - c.start) for c in kv[1] if c.end),
            )
            for name, group in ordered:
                gtotal = sum((c.end - c.start) * 1000.0 for c in group if c.end)
                gbridge = sum(c.bridge_ms for c in group)
                gmax = max(((c.end - c.start) * 1000.0 for c in group if c.end), default=0.0)
                lines.append(
                    f"    {name:32s}  x{len(group):<2d}  "
                    f"total {gtotal:7.0f} ms (bridge {gbridge:6.0f}) "
                    f"max {gmax:6.0f} ms"
                )
        lines.append("=" * 64)
        return "\n".join(lines)
