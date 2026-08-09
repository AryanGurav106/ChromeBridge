"""Local WebSocket bridge between the Python agent and the Chrome extension.

Architecture: the Chrome extension's service worker connects as a client to
ws://127.0.0.1:<port>. The Python side issues requests
(`get_interactive_elements`, `click`, `enter_text`, `screenshot`, `navigate`,
...) keyed by a unique `id`; the extension processes them on the user's active
tab and replies. Each request is awaited as a Future, so the call site looks
synchronous (`result = await bridge.call("click", mmid="42")`).

The bridge is bound to 127.0.0.1 only and accepts at most one connected client
(the extension). A per-session token (printed at startup, read by the extension
from chrome.storage on install) gates the handshake so other local processes
cannot drive Chrome through this port.

This is the dev-friendly transport. The same protocol can later be moved behind
chrome.runtime.connectNative (no exposed TCP port) without touching call sites.
"""

import asyncio
import json
import secrets
import time
import uuid
from typing import Any, Awaitable, Callable, Optional

import websockets
from websockets.server import WebSocketServerProtocol

from core.utils.logger import Logger

logger = Logger()

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_REQUEST_TIMEOUT_SEC = 30.0


class ExtensionBridge:
    """One-extension WebSocket server with request/response correlation."""

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                 token: Optional[str] = None,
                 request_timeout: float = DEFAULT_REQUEST_TIMEOUT_SEC):
        self.host = host
        self.port = port
        self.token = token or secrets.token_urlsafe(16)
        self.request_timeout = request_timeout

        self._server: Optional[websockets.server.WebSocketServer] = None
        self._client: Optional[WebSocketServerProtocol] = None
        self._pending: dict[str, asyncio.Future] = {}
        self._connected_event = asyncio.Event()
        self._on_event: Optional[Callable[[dict], Awaitable[None]]] = None
        # Most recent op's WS round-trip duration; read by per-tool timing.
        self.last_call_ms: float = 0.0
        # Cumulative WS round-trip time since the bridge started; per-tool
        # timing subtracts before/after to get the bridge time inside a tool,
        # which is accurate even when a tool makes several bridge calls.
        self.total_bridge_ms: float = 0.0

    # ---- lifecycle --------------------------------------------------------
    async def start(self) -> None:
        self._server = await websockets.serve(
            self._handle, self.host, self.port, ping_interval=20, ping_timeout=20,
            max_size=64 * 1024 * 1024,  # 64MB — accommodate full-page screenshots
        )
        logger.info(f"Extension bridge listening on ws://{self.host}:{self.port} "
                    f"(token: {self.token})")

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(ConnectionError("bridge stopped"))
        self._pending.clear()

    async def wait_until_connected(self, timeout: float = 60.0) -> None:
        await asyncio.wait_for(self._connected_event.wait(), timeout=timeout)

    @property
    def connected(self) -> bool:
        if self._client is None:
            return False
        # websockets>=13 dropped .closed; .state may be an IntEnum. Be tolerant.
        try:
            state = getattr(self._client, "state", None)
            if state is not None:
                return getattr(state, "name", str(state)).upper() == "OPEN"
            return not self._client.closed  # legacy fallback
        except Exception:
            return True

    def set_event_handler(self, handler: Callable[[dict], Awaitable[None]]) -> None:
        """Register an async callback for unsolicited events from the extension
        (e.g. user clicked Cancel on the debugger bar, active tab changed)."""
        self._on_event = handler

    # ---- request / response ---------------------------------------------
    async def call(self, op: str, *, request_timeout: Optional[float] = None,
                   **params: Any) -> Any:
        """Issue an op to the extension and await its result.

        `request_timeout` overrides the default for THIS call. Needed because some
        ops are legitimately long: fill_form is a single op that can spend ~5s per
        combobox (open poll 1.2s -> trusted retry 1.2s -> search-type 1.0s -> settle
        -> verify 0.8s) plus up to 4s of submit settling. With the flat 30s default a
        10-dropdown form timed out on the PYTHON side while the extension kept going
        and submitted, so the model saw failure, retried, and DOUBLE-SUBMITTED.
        Keyword-only so it can never collide with an op's own params.
        """
        if not self.connected:
            raise ConnectionError("Chrome extension is not connected to the bridge.")
        timeout = request_timeout if request_timeout is not None else self.request_timeout
        req_id = uuid.uuid4().hex
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = fut
        payload = json.dumps({"id": req_id, "op": op, "params": params})
        t0 = time.monotonic()
        await self._client.send(payload)
        try:
            result = await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise TimeoutError(
                f"extension did not respond to {op} within {timeout:.0f}s. "
                "IMPORTANT: the extension may still be executing this op — for a "
                "mutating op (fill_form, click, computer) do NOT simply retry; "
                "re-observe with read_page/get_url first to see what actually "
                "landed, or you risk duplicating the action."
            )
        finally:
            # Record the most recent op's round-trip so callers (e.g. the per-
            # tool TimingTracker) can attribute extension/network time precisely.
            self.last_call_ms = (time.monotonic() - t0) * 1000.0
            self.total_bridge_ms += self.last_call_ms
            # Demoted to DEBUG: Windows console writes here (PowerShell + UTF-8
            # stream reconfigure) consistently added ~500ms to the call's wall
            # time, manifesting as a "ghost gap" between bridge's measured 30ms
            # and driver.click's measured 500-something. Run with LOG_LEVEL=DEBUG
            # to see per-op bridge timings; cumulative timing lives in
            # TimingTracker.bridge_ms anyway.
            logger.debug(f"[bridge] op={op} dt={self.last_call_ms:.0f}ms")
        return result

    # ---- connection handler ----------------------------------------------
    async def _handle(self, ws: WebSocketServerProtocol) -> None:
        # Handshake first: validate the token. Wrong token -> bounce immediately.
        try:
            hello_raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
            hello = json.loads(hello_raw)
            if hello.get("hello") != self.token:
                logger.warn("bridge handshake failed: bad token")
                await ws.close(code=1008, reason="bad token")
                return
        except Exception as e:
            # Quietly drop incomplete/aborted handshakes — usually a transient
            # MV3 service-worker respawn racing the old socket.
            logger.debug(f"bridge handshake aborted: {e}")
            try: await ws.close(code=1002, reason="handshake")
            except Exception: pass
            return

        # Newer-authenticated-wins: if an old client is still tracked, evict it.
        # MV3 service workers get evicted and respawn often; the prior socket is
        # usually a zombie. Aborting in-flight requests is the right move — they
        # would have hung waiting for a worker that no longer exists.
        if self._client is not None:
            old = self._client
            self._client = None
            for rid, fut in list(self._pending.items()):
                if not fut.done():
                    fut.set_exception(ConnectionError("extension reconnected; request aborted"))
            self._pending.clear()
            try: await old.close(code=1000, reason="replaced by newer connection")
            except Exception: pass
            logger.info("replaced an older extension connection with the new one")

        # Send welcome only after we've claimed the slot.
        try:
            await ws.send(json.dumps({"welcome": True, "server_time": time.time()}))
        except Exception as e:
            logger.warn(f"bridge welcome failed: {e}")
            try: await ws.close(code=1011, reason="welcome failed")
            except Exception: pass
            return

        self._client = ws
        self._connected_event.set()
        logger.info("Chrome extension connected to bridge")
        # Keep the MV3 service worker alive with periodic app-level pings.
        # Chrome evicts idle SWs in ~30s; protocol PING frames don't count, but
        # a JS-level WS message exchange does.
        keepalive_task = asyncio.create_task(self._keepalive_loop())
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except Exception as e:
                    logger.warn(f"bridge: malformed message: {e}")
                    continue
                await self._dispatch(msg)
        except websockets.ConnectionClosed:
            pass
        except Exception as e:
            logger.error(f"bridge: connection error: {e}")
        finally:
            keepalive_task.cancel()
            # Only clear global state if we're still the current client — a
            # newer connection may have taken over (newer-wins) and we must
            # not stomp on its reference.
            if self._client is ws:
                self._client = None
                self._connected_event.clear()
            logger.info("Chrome extension disconnected from bridge")

    async def _keepalive_loop(self) -> None:
        """Send a lightweight ping every 20s while the extension is connected.
        This keeps Chrome's MV3 service worker from being evicted for idleness."""
        try:
            while self.connected:
                await asyncio.sleep(20)
                if not self.connected:
                    return
                try:
                    await asyncio.wait_for(self.call("ping"), timeout=5.0)
                except Exception as e:
                    logger.debug(f"keepalive ping failed: {e}")
        except asyncio.CancelledError:
            pass

    async def _dispatch(self, msg: dict) -> None:
        # Either a response to one of our requests, or an unsolicited event.
        rid = msg.get("id")
        if rid and rid in self._pending:
            fut = self._pending.pop(rid)
            if msg.get("ok"):
                fut.set_result(msg.get("result"))
            else:
                fut.set_exception(RuntimeError(msg.get("error", "extension error")))
            return
        # Unsolicited event from the extension.
        if msg.get("event"):
            if self._on_event:
                try:
                    await self._on_event(msg)
                except Exception as e:
                    logger.error(f"bridge: event handler raised: {e}")
            return
        logger.warn(f"bridge: ignoring unmatched message {msg}")
