"""test_contracts.py — assert the constants duplicated across process boundaries agree.

Run:  .venv\\Scripts\\python.exe tools\\test_contracts.py

ChromeBridge spans three processes that cannot import each other: the Python MCP
server, the extension's service worker, and the side panel. Four values therefore
exist in more than one file, kept in sync by nothing but a comment:

    PORT_RANGE_SPAN   core/bridge/server.py, extension/background.js, extension/panel.js
    PROTOCOL_VERSION  core/bridge/server.py, extension/background.js
    version           extension/manifest.json, pyproject.toml, SERVER_VERSION in server.py

Each mismatch fails in a way that looks like something else:

  - a narrower span in the extension strands every session the server places on a
    port the extension never probes; the panel just says it cannot reach the bridge.
  - a PROTOCOL_VERSION skew closes every connection with 4001 — which is the
    mechanism working correctly, reporting a bug that is ours, not the user's.
  - a version skew is cosmetic but it is what a human reads first when diagnosing
    the other two, so a wrong one sends them down the wrong path.

Parsed out of the source text rather than imported, because two of the three files
are JavaScript. That is deliberate: the point is to compare what each process will
actually load, not what a Python-side constant says they should.
"""

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

passed = 0
failed = 0
failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {name}" + (f"  - {detail}" if detail else ""))
    else:
        failed += 1
        failures.append(name)
        print(f"  FAIL  {name}" + (f"  - {detail}" if detail else ""))


def read(rel: str) -> str:
    with open(os.path.join(ROOT, rel), "r", encoding="utf-8") as fh:
        return fh.read()


def grab(rel: str, pattern: str) -> str | None:
    """First capture group of `pattern` in `rel`, or None."""
    m = re.search(pattern, read(rel), re.M)
    return m.group(1) if m else None


def main() -> int:
    # ---- PORT_RANGE_SPAN ---------------------------------------------------
    spans = {
        "core/bridge/server.py": grab("core/bridge/server.py", r"^PORT_RANGE_SPAN\s*=\s*(\d+)"),
        "extension/background.js": grab("extension/background.js", r"^const PORT_RANGE_SPAN\s*=\s*(\d+)"),
        "extension/panel.js": grab("extension/panel.js", r"^const PORT_RANGE_SPAN\s*=\s*(\d+)"),
    }
    for path, val in spans.items():
        check(f"C1 PORT_RANGE_SPAN is present in {path}", val is not None,
              "not found — did the constant get renamed?" if val is None else f"= {val}")
    if all(v is not None for v in spans.values()):
        check("C2 all three PORT_RANGE_SPAN values agree",
              len(set(spans.values())) == 1, ", ".join(f"{k.split('/')[-1]}={v}" for k, v in spans.items()))

    # ---- PROTOCOL_VERSION --------------------------------------------------
    protos = {
        "core/bridge/server.py": grab("core/bridge/server.py", r"^PROTOCOL_VERSION\s*=\s*(\d+)"),
        "extension/background.js": grab("extension/background.js", r"^const PROTOCOL_VERSION\s*=\s*(\d+)"),
    }
    for path, val in protos.items():
        check(f"C3 PROTOCOL_VERSION is present in {path}", val is not None,
              "not found" if val is None else f"= {val}")
    if all(v is not None for v in protos.values()):
        check("C4 server and extension PROTOCOL_VERSION agree "
              "(a skew closes every connection with 4001)",
              len(set(protos.values())) == 1,
              ", ".join(f"{k.split('/')[-1]}={v}" for k, v in protos.items()))

    # ---- version -----------------------------------------------------------
    manifest = json.loads(read("extension/manifest.json"))
    versions = {
        "extension/manifest.json": manifest.get("version"),
        "pyproject.toml": grab("pyproject.toml", r'^version\s*=\s*"([^"]+)"'),
        "core/bridge/server.py": grab("core/bridge/server.py", r'^SERVER_VERSION\s*=\s*"([^"]+)"'),
    }
    for path, val in versions.items():
        check(f"C5 version is present in {path}", bool(val),
              "not found" if not val else f"= {val}")
    if all(versions.values()):
        check("C6 manifest, pyproject and SERVER_VERSION agree",
              len(set(versions.values())) == 1,
              ", ".join(f"{k.split('/')[-1]}={v}" for k, v in versions.items()))

    # ---- the handshake field names both sides spell out --------------------
    # The wire contract is four keys. A rename on one side is a 4001 storm at
    # best and a silent mis-parse at worst, so assert both halves still say them.
    sw = read("extension/background.js")
    py = read("core/bridge/server.py")
    for key in ("hello", "protocol", "client", "version"):
        check(f"C7 hello key '{key}' appears in both halves",
              f'"{key}"' in sw or f"'{key}'" in sw or f"{key}:" in sw,
              "extension side")
    check("C8 server reads the same hello keys",
          all(f'"{k}"' in py or f"'{k}'" in py for k in ("hello", "protocol")),
          "server side")
    check("C9 protocol-mismatch close code 4001 is used by BOTH halves "
          "(the panel must recognise what the server sends)",
          "4001" in py and "4001" in read("extension/panel.js"))

    # C10: a tool parameter must not be NARROWER than the way clients call it.
    # `call_page_tool(args=...)` was declared `Optional[str]`, which looks right and
    # fails on first use: an MCP client handed '{"instrument":"..."}' parses it into
    # an object before validation, so the natural call is rejected with a pydantic
    # string_type error that mentions nothing about tools. The extension already
    # accepted either shape (test_ops.js pins that); only the server schema was
    # narrow. Checked statically because the failure is in the SIGNATURE, which is
    # what a client sees, not in any code path a runtime call would reach.
    _srv = read("mcp_server.py")   # NOT `py`, which is core/bridge/server.py
    check("C10 call_page_tool accepts args as an object OR a string, and normalises",
          "Optional[Union[str, dict]]" in _srv
          and "json.dumps(args, ensure_ascii=False)" in _srv,
          "args annotation is Optional[Union[str, dict]] with a json.dumps fallback")

    print(f"\n{passed} passed, {failed} failed, {passed + failed} total checks")
    if failures:
        print("failing: " + ", ".join(failures))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
