# Vendored microdot

Source: <https://github.com/miguelgrinberg/microdot>
Pinned version: **2.3.3** (same as Debian trixie's `python3-microdot 2.3.3-1`)
License: MIT (see `LICENSE`)

## Why vendored

Debian 11 bullseye does not ship `python3-microdot` in apt, which previously
forced the `go-web-ui` Debian package to be trixie-only. Bundling microdot
under `ModulineWebUI/_vendor/microdot/` lets us drop the `python3-microdot`
line from `Depends` in `.github/workflows/build-package.yml`, so a single
architecture-independent `.deb` resolves on bullseye, bookworm and trixie
once `apt.gocontroll.com` is in the controller's sources list.

`ModulineWebUI/__init__.py` prepends this directory's parent (`_vendor/`)
to `sys.path` so regular `from microdot import …` statements throughout
the codebase resolve here without further modification.

## Trim

We bundle only the modules our app actually imports (and their transitive
deps inside microdot itself):

| File          | Size  | Why                                                  |
|---------------|-------|------------------------------------------------------|
| `__init__.py` | 145 B | Re-exports the public API (`Microdot`, `Request`, …) |
| `microdot.py` | 58 KB | The framework core                                   |
| `session.py`  | 5.3 KB | `from microdot.session import Session, with_session` |
| `helpers.py`  | 232 B | `wraps` decorator (used by `session.py`)             |
| `multipart.py`| 10 KB | Imported via docstring reference / form-data path    |

`asgi.py`, `auth.py`, `cors.py`, `csrf.py`, `jinja.py`, `login.py`,
`sse.py`, `test_client.py`, `utemplate.py`, `websocket.py`, `wsgi.py` are
deliberately **not** vendored — re-add them here if a feature ever needs
them, and document the reason.

## Updating

When microdot is upgraded:

1. Pick the same version Debian trixie ships (so M1/L4/HMI1 controllers
   that were apt-installing `python3-microdot` see no behavioural change).
2. Replace the five files above plus `LICENSE`. Keep this `VENDORED.md`
   updated.
3. Bump the `go-web-ui` minor version — vendored-dep changes are not
   patch-level.
