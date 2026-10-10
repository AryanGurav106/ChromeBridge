"""Local WebSocket bridge between the Python agent and the Chrome extension.

Architecture: the Chrome extension's service worker connects as a client to
ws://127.0.0.1:<port>. The Python side issues requests
(`get_interactive_elements`, `click`, `enter_text`, `screenshot`, `navigate`,
...) keyed by a unique `id`; the extension processes them on the user's active
tab and replies. Each request is awaited as a Future, so the call site looks
synchronous (`result = await bridge.call("click", mmid="42")`).

The bridge is bound to 127.0.0.1 only and accepts at most one connected client
(the extension). A shared token (from BRIDGE_TOKEN, pasted once into the
extension's side panel) gates the handshake so other local processes cannot
drive Chrome through this port.

This is the dev-friendly transport. The same protocol can later be moved behind
chrome.runtime.connectNative (no exposed TCP port) without touching call sites.
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Awaitable, Callable, Optional

# The modern (asyncio) websockets API. The legacy `websockets.server.
# WebSocketServerProtocol` path this used to import is deprecated since 14.0 and
# scheduled for removal, and requirements.txt has no upper bound — so a routine
# `pip install` on a fresh machine is what would have broken the build.
from websockets.asyncio.server import Server, ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from core.utils.logger import Logger

logger = Logger()

# The asyncio websockets server narrates "server listening on ...", "server
# closing", "server closed" at INFO — a less informative duplicate of the line
# start() emits, on the same stderr stream a user reads to diagnose a failed
# connection. Keep its warnings and errors, drop the narration.
logging.getLogger("websockets.server").setLevel(logging.WARNING)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

# Port 8765 is a single bind but every Claude Code session defaults to it, so a
# second project opened at the same time used to die with OSError before it
# served a single tool. start() walks DEFAULT_PORT .. DEFAULT_PORT+PORT_RANGE_SPAN-1
# and takes the first free one.
#
# KEEP IN SYNC WITH THE EXTENSION: the extension probes the SAME span when it
# looks for a server, so widening or narrowing it here silently strands sessions
# on ports the extension will never try.
PORT_RANGE_SPAN = 10

# Wire-protocol version, exchanged in the handshake (see _handle). The extension
# is installed by hand ("Load unpacked"), so a stale extension against a newer
# server is the NORMAL condition, not an edge case — without this it showed up as
# mysterious per-op failures long after the connection looked healthy. Bump this
# whenever an op's request/response shape changes incompatibly.
PROTOCOL_VERSION = 1

# Reported to the extension in the welcome frame, purely so a human debugging a
# mismatch can see both halves' versions. Mirrors extension/manifest.json.
SERVER_VERSION = "0.1.0"

DEFAULT_REQUEST_TIMEOUT_SEC = 30.0


class ExtensionBridge:
    """One-extension WebSocket server with request/response correlation."""

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                 token: Optional[str] = None,
                 request_timeout: float = DEFAULT_REQUEST_TIMEOUT_SEC):
        self.host = host
        # The port we START looking at. start() overwrites self.port with the one
        # actually bound, so every reader (log lines, user-facing "not connected"
        # text) reports reality rather than the constant.
        self.requested_port = port
        self.port = port
        if not token or not str(token).strip():
            # This used to fall back to secrets.token_urlsafe(16), which meant an
            # unset BRIDGE_TOKEN produced a DIFFERENT random token on every launch:
            # the extension got close code 1008 forever while the only copy of the
            # correct token scrolled past in a stderr line nobody reads. Refusing
            # here makes that failure impossible to reach.
            raise ValueError(
                "ExtensionBridge requires a shared token. Set BRIDGE_TOKEN in .env "
                "(mcp_server.py generates and persists one for you if it is empty) "
                "and paste the same value into the extension's side panel."
            )
        self.token = str(token).strip()
        self.request_timeout = request_timeout

        self._server: Optional[Server] = None
        self._client: Optional[ServerConnection] = None
        self._pending: dict[str, asyncio.Future] = {}
        self._connected_event = asyncio.Event()
        self._on_event: Optional[Callable[[dict], Awaitable[None]]] = None
        # Handshake facts about the currently connected extension. First thing to
        # check when ops misbehave after an extension update.
        self.client_version: Optional[str] = None
        self.client_name: Optional[str] = None
        # Most recent op's WS round-trip duration; read by per-tool timing.
        self.timeouts: list = []
        self.last_call_ms: float = 0.0
        # Cumulative WS round-trip time since the bridge started; per-tool
        # timing subtracts before/after to get the bridge time inside a tool,
        # which is accurate even when a tool makes several bridge calls.
        self.total_bridge_ms: float = 0.0

    # ---- lifecycle --------------------------------------------------------
    async def start(self) -> None:
        """Bind the first free port in [requested_port, requested_port+SPAN).

        Raises OSError naming the whole range if every one of them is taken —
        the old single-bind OSError said only "address in use" and killed the
        session's entire tool surface with no hint that a second Claude Code
        window was the cause.
        """
        first = self.requested_port
        last = first + PORT_RANGE_SPAN - 1
        last_err: Optional[OSError] = None
        for candidate in range(first, last + 1):
            try:
                self._server = await serve(
                    self._handle, self.host, candidate,
                    ping_interval=20, ping_timeout=20,
                    max_size=64 * 1024 * 1024,  # 64MB — accommodate full-page screenshots
                )
            except OSError as e:
                last_err = e
                logger.debug(f"port {candidate} unavailable ({e}); trying the next one")
                continue
            self.port = candidate
            if candidate != first:
                logger.info(f"port {first} was busy; using {candidate} instead "
                            f"(another ChromeBridge session is probably running)")
            logger.info(f"Extension bridge listening on ws://{self.host}:{self.port} "
                        f"(protocol {PROTOCOL_VERSION}, token: {self.token})")
            return
        raise OSError(
            f"all {PORT_RANGE_SPAN} bridge ports {first}-{last} on {self.host} are in "
            f"use (last error: {last_err}). Close some ChromeBridge sessions, or set "
            f"BRIDGE_PORT in .env to a different starting port — note the extension "
            f"probes the same {PORT_RANGE_SPAN}-port span, so it must be moved too."
        )

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
            # LEAVE A TRACE. Three stalls were observed in one session and none
            # reproduced, so there is nothing to fix -- but "it hung once" is
            # not evidence and an intermittent that leaves no record cannot be
            # diagnosed on the next occurrence either. sw_info reports this, so
            # the next one arrives with its op, its age and how many came
            # before it instead of a memory.
            self.timeouts.append({"op": op, "after_s": round(timeout, 1),
                                  "ts": time.time()})
            del self.timeouts[:-10]
            # NAME THE RECOVERY THAT WAS SEEN TO WORK, and only that one.
            # Observed live: ops that INJECT into the page (read_page,
            # fill_form, computer, javascript_tool) all hung together, while
            # get_url, sw_info and navigate kept answering in milliseconds --
            # the signature of a blocked page main thread rather than a dead
            # extension, which the old wording could not distinguish. Steering
            # the reader to `read_page` first is the one thing that cannot
            # work in that state, because read_page is one of the ops that is
            # stuck. navigate recovered the tab on the spot. #33's rule: the
            # advice has to be a recovery that has been verified, not a
            # plausible one (and no cause is asserted here that was not seen).
            raise TimeoutError(
                f"extension did not respond to {op} within {timeout:.0f}s. "
                "IMPORTANT: the extension may still be executing this op — for a "
                "mutating op (fill_form, click, computer) do NOT simply retry; "
                "re-observe FIRST to see what actually landed, or you risk "
                "duplicating the action. Use get_url or sw_info to re-observe, "
                "NOT read_page: if the page's own main thread is blocked (a "
                "modal dialog, or a script loop) then every op that injects "
                "into the page is stuck too, while get_url/sw_info/navigate "
                "still answer. The two causes need DIFFERENT answers and there "
                "is a tool that tells them apart: dismiss_dialog reports "
                "no_dialog when none is open, and clears the page when one is. "
                "A script loop is the other case, and navigating the tab clears "
                "that one."
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
    async def _handle(self, ws: ServerConnection) -> None:
        # Handshake, in this order:
        #   {"hello": <token>, "protocol": 1, "client": ..., "version": ...}
        #   -> {"welcome": true, "server_time": <t>, "protocol": 1, "version": ...}
        # Token is checked FIRST: an unauthenticated peer learns nothing about the
        # protocol version it failed to match.
        try:
            hello_raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
            hello = json.loads(hello_raw)
            if not isinstance(hello, dict):
                raise ValueError("hello frame is not an object")
        except Exception as e:
            # Quietly drop incomplete/aborted handshakes — usually a transient
            # MV3 service-worker respawn racing the old socket.
            logger.debug(f"bridge handshake aborted: {e}")
            try: await ws.close(code=1002, reason="handshake")
            except Exception: pass
            return

        if hello.get("hello") != self.token:
            logger.warn("bridge handshake failed: bad token")
            try: await ws.close(code=1008, reason="bad token")
            except Exception: pass
            return

        # A hello with NO `protocol` field is a pre-versioning extension; report it
        # as client=0 rather than as a malformed frame, because that is exactly the
        # case this check exists for.
        client_protocol = hello.get("protocol", 0)
        client_version = str(hello.get("version") or "unknown")
        client_name = str(hello.get("client") or "unknown")
        if client_protocol != PROTOCOL_VERSION:
            reason = f"protocol mismatch (server={PROTOCOL_VERSION}, client={client_protocol})"
            logger.warn(
                f"bridge handshake rejected: {reason}. The extension (version "
                f"{client_version}) is out of step with mcp_server.py — reload it at "
                "chrome://extensions (Load unpacked / the reload arrow) from this repo."
            )
            try: await ws.close(code=4001, reason=reason)
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
            await ws.send(json.dumps({
                "welcome": True,
                "server_time": time.time(),
                "protocol": PROTOCOL_VERSION,
                "version": SERVER_VERSION,
            }))
        except Exception as e:
            logger.warn(f"bridge welcome failed: {e}")
            try: await ws.close(code=1011, reason="welcome failed")
            except Exception: pass
            return

        self._client = ws
        self.client_version = client_version
        self.client_name = client_name
        self._connected_event.set()
        # Version first in the line: when an op starts failing after a hand-reload
        # of the extension, this is the fact you want without re-running anything.
        logger.info(f"Chrome extension connected to bridge on port {self.port} "
                    f"(client={client_name} version={client_version} "
                    f"protocol={client_protocol}; server version={SERVER_VERSION})")
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
        except ConnectionClosed:
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
                self.client_version = None
                self.client_name = None
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
