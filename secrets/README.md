# `secrets/`

**Nothing in the live product reads this directory.** `local_secrets.json` is
read only by `legacy/` — the retired pydantic-ai loop, which does not even
import any more (see the README's `legacy/` section). `config.py` still
declares the path because `legacy/` imports it.

**Flow secrets are environment variables, not this file.** A password typed
during `record_flow` is written into the flow as
`${CHROMEBRIDGE_SECRET:CB_SECRET_<FLOW>_<FIELD>}` and resolved from the
environment at replay, so the value never touches the repo:

```bash
export CB_SECRET_ACME_CREATE_PROJECT_PASSWORD='…'
```

`run_flow` refuses and names the variable when it is unset, rather than typing
an empty string — a blank password submits, and then looks like a wrong
credential instead of a missing one.
