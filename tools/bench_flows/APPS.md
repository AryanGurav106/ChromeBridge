# The eight apps

Named by an agent told only to describe short public browser interactions —
no knowledge that any feature was under test, and no sight of PREREG.md. It
fetched every URL live and confirmed each control in the real markup rather
than describing a page from memory; it flagged the two cases where a control
is JS-generated and therefore absent from a static fetch.

| # | slug | origin | shape |
|---|---|---|---|
| 1 | `ev-httpbin-pizza-form` | `https://httpbin.org` | form, many field types |
| 2 | `ev-arxiv-advanced-search` | `https://arxiv.org` | search-and-filter |
| 3 | `ev-datatables-zero-config` | `https://datatables.net` | data table |
| 4 | `ev-todomvc-react` | `https://todomvc.com` | SPA, hash routing |
| 5 | `ev-jawiki-tokyo-tower` | `https://ja.wikipedia.org` | non-Latin interface |
| 6 | `ev-bootstrap-modal-demo` | `https://getbootstrap.com` | dialog / modal |
| 7 | `ev-apg-select-only-combobox` | `https://www.w3.org` | ARIA combobox (not `<select>`) |
| 8 | `ev-python-docs-controlflow` | `https://docs.python.org` | docs, in-page nav |

Nothing here mutates shared state: httpbin echoes a POST back to the caller,
TodoMVC keeps state in localStorage, and the other six are read-only.

Full step briefs and the per-app CHECK are in `briefs.json`.
