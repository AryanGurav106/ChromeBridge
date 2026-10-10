"""A recorded flow must never carry a password.

`record_flow` stores the values a step typed, and flow files are tests, so they
live in git. Recording a login therefore wrote the user's password in plaintext
into a file whose entire purpose is to be committed and shared — and #31
removed exactly this leak from the other end, where `read_page` printed
`type=password` values into the listing and every tool downstream assumed a
listing was safe to carry. The recorder undid that. This closes it.

WHAT IS SECRET IS DECLARED, NOT GUESSED. `<input type="password">` is HTML's
own enum, the same declaration #31 reads and the same kind #24's submit picker
answers from. No entropy heuristic, no name wordlist ("pass", "pwd", "secret"),
because a wordlist here fails in both directions at once: it would miss a field
called `kennwort` and redact one called `password_hint`.

TWO PATHS CARRY A TYPED VALUE, and both are covered by declarations:

  form_input / fill_form   the step NAMES the field, so its recorded descriptor
                           carries the type. Exact.
  computer(action="type")  names nothing — it goes to whatever has FOCUS. The
                           answer is in the recording itself: focus was
                           established by the last step that named a ref, which
                           is #43's rule for the batch guard, reused rather than
                           re-derived. A `type` following a click on a password
                           field is redacted; following a click on a text field
                           it is not (FS5/FS5b).

WHAT IS STORED INSTEAD is a placeholder naming an environment variable, so the
flow file says WHICH secret it needs without containing it. Replay reads the
variable and REFUSES, naming it, when it is unset — it never substitutes an
empty string, because a login that silently submits a blank password is a
failure that looks like a bad credential rather than a missing one.
"""
from __future__ import annotations

import os
import re
from typing import Optional

# Explicit and greppable. A plain string rather than a dict so the flow file's
# value slot keeps one type, and a prefix no page value realistically collides
# with — and only values the recorder itself wrote are ever read back as one.
PREFIX = "${CHROMEBRIDGE_SECRET:"
SUFFIX = "}"
ENV_PREFIX = "CB_SECRET_"


def is_secret(target: dict) -> bool:
    """Does this step's target declare itself a password field?"""
    t = target or {}
    desc = t.get("full") or t.get("desc") or {}
    return (desc.get("type") or "").strip().lower() == "password"


def _slug(s: str) -> str:
    """Uppercase ASCII identifier, or '' when nothing survives.

    AN ASCII ALLOWLIST IS CORRECT HERE AND IS WRONG THREE FILES OVER, which is
    worth saying because this is the shape #32 shipped as a bug and #49
    reproduced. A FILENAME may contain any script, so an allowlist built from
    `\\w` turns a Japanese flow name into a row of dashes — that one strips only
    what a filesystem forbids. An ENVIRONMENT VARIABLE NAME is `[A-Za-z_][A-Za-z0-9_]*`
    by POSIX; a name outside that cannot be exported by a shell at all. So the
    constraint is the standard's, not a guess about what matters — and the
    caller below falls back to the field's POSITION when a non-Latin label
    leaves nothing, rather than emitting an empty name.
    """
    return re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9]+", "_", s or "")).strip("_").upper()


def env_name(flow_name: str, target: dict, path: str) -> str:
    """CB_SECRET_<FLOW>_<FIELD> — says which secret, never what it is."""
    desc = (target or {}).get("full") or (target or {}).get("desc") or {}
    field = _slug(desc.get("name") or "")
    if not field:
        # A label in a script with no ASCII at all, or no label. Position is
        # stable within one flow file and is the only thing left that is.
        field = _slug(path) or "FIELD"
    flow = _slug(flow_name) or "FLOW"
    return f"{ENV_PREFIX}{flow}_{field}"


def placeholder(name: str) -> str:
    return f"{PREFIX}{name}{SUFFIX}"


def named(value) -> Optional[str]:
    """The env var this value stands for, or None if it is an ordinary value."""
    if isinstance(value, str) and value.startswith(PREFIX) and value.endswith(SUFFIX):
        return value[len(PREFIX):-len(SUFFIX)]
    return None


def resolve(obj):
    """Substitute every placeholder in a step's input. -> (input, missing names).

    Walks the structure rather than knowing where values live, so it covers
    form_input's `value`, fill_form's `fields[].value` and computer's `text`
    without a third list of field locations to keep in sync (#21).
    """
    missing: list = []

    def walk(v):
        if isinstance(v, str):
            name = named(v)
            if name is None:
                return v
            got = os.environ.get(name)
            if got is None or got == "":
                missing.append(name)
                return v
            return got
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        return v

    return walk(obj), missing


def missing_message(names: list) -> str:
    uniq = sorted(set(names))
    plural = "s" if len(uniq) > 1 else ""
    return (
        f"this step needs secret{plural} that are not set: {', '.join(uniq)}. "
        f"The flow records WHICH secret a password field needs, never the value "
        f"— export the variable{plural} and run it again. Refusing rather than "
        f"typing an empty string, because a blank password submits and then "
        f"looks like a wrong credential instead of a missing one."
    )
