# CLAUDE.md

Guidance for Claude Code (and other AI coding agents) when working in this repository.

## What this is

`go-web-ui` is a Python web application that runs on GOcontroll Moduline embedded controllers. It exposes a browser UI on port 5000 (default, configurable) so integrators can configure network interfaces, manage systemd services, read/clear diagnostic trouble codes, browse module pinout, edit module configuration, and toggle whether the hardware driver should drive each module slot. The server uses Microdot (async micro-framework) with simple session-based auth backed by a SHA-256 passkey.

It is one of three tightly coupled packages on the controller; understanding the boundaries matters:

| Package | Responsibility | Key persisted artifact |
|---|---|---|
| `go-modules` | Scan SPI bus, identify modules, flash firmware, write `modules.json` | `/lib/firmware/gocontroll/modules.json` |
| `go-hardware-driver` | Read `modules.json` and run the per-slot module driver loop (100 Hz) | `/dev/shm/gocontroll/slot{N}/...` |
| `go-web-ui` (this repo) | Browser-based config editor + status view | reads/writes `modules.json` |

This UI is a strict consumer of the `modules.json` schema owned by `go-modules`. The authoritative schema lives in the `GOcontroll-Architecture` repo under `modules/configuration.md`.

## Build / package

The package is a `Architecture: all` Debian package — pure Python, no compiled artifacts. Files end up at:

- `/usr/lib/python3/dist-packages/ModulineWebUI/` — the package source tree.
- `/usr/bin/go-web-ui` — a tiny shim that imports and calls `ModulineWebUI.__main__.execute_script`.
- `/usr/bin/go-print-dtcs` — companion DTC-print helper, imports `ModulineWebUI.diag.print_errors`.
- `/usr/lib/systemd/system/go-web-ui.service` — systemd unit.
- `/etc/go_webui.conf` — INI-style config (listen address/port, pass-hash, service blacklist, optional SSL).

CI (`.github/workflows/build-package.yml`) triggers on `v*` tags, constructs the `.deb` manually with `dpkg-deb`, publishes a GitHub Release, and dispatches an index rebuild to the GOcontroll apt repo. The tag drives the package version — keep `README.md` Changelog, `ModulineWebUI.__version__`, and the tag in sync. The CI also `sed`-patches `__version__` from the tag at build time so the .deb's Version, the apt index, and the runtime constant cannot drift apart for tagged releases.

For ad-hoc on-controller testing, replace the installed source tree with a fresh copy:

```sh
systemctl stop go-web-ui
rm -rf /usr/lib/python3/dist-packages/ModulineWebUI
cp -r ./ModulineWebUI /usr/lib/python3/dist-packages/ModulineWebUI
systemctl start go-web-ui
```

For host-side development (lints, quick sanity checks; no hardware integration), a virtualenv with editable install works:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install --editable ".[dev]"
go-web-ui --passkey test
```

## Runtime architecture

### Entry point

`ModulineWebUI/__main__.py:execute_script()` parses CLI flags, layers in `/etc/go_webui.conf`, sets the passkey hash, generates / reads SSL cert and key (or runs HTTP if not configured), and starts the Microdot app from `app.py`. The shim binary at `/usr/bin/go-web-ui` calls this function.

### Modules

| File | Role |
|---|---|
| `app.py` | Microdot app construction, session setup, login/logout, static-file routes, `auth` decorator |
| `go_webui.py` | CLI args, logging, SSL bootstrap, server start (`app.run`) |
| `controller.py` | All `/api/...` routes for system info, modules, faults, app config, env parameters |
| `can.py`, `wifi.py`, `wwan.py`, `ethernet.py`, `diag.py` | Per-feature `/api/...` routes |
| `conf.py` | Read/write `/etc/go_webui.conf` (INI-style) |
| `handlers/service.py` | Wraps systemd via `subprocess`; respects `service_blacklist` from config |
| `handlers/modules.py` | Reads/writes `modules.json`, holds `MODULE_SCHEMAS` (the UI form schema) and `MODULE_TYPE_NAMES` (article-prefix → display name) |
| `handlers/parameters.py` | `/etc/gocontroll/config.json` + `parameters.js` (env vars for downstream apps) |
| `handlers/bluetooth.py` | Bluetooth helpers |
| `static/*.html` | One page per top-level nav item |
| `js/*.js` | Vanilla JS, no build step; fetches the JSON APIs above |
| `style/*.css` | Plain CSS, no preprocessor |
| `data/module_pinning.json`, `data/controller_pinning.json` | Pin-out tables generated from `GOcontroll-Architecture` |
| `scripts/generate_module_pinning.py`, `scripts/generate_controller_pinning.py` | Generators that consume the markdown in `GOcontroll-Architecture/modules/` |
| `_vendor/` | Bundled Microdot + dependencies (so the package runs on a stock Python without pip on the controller) |

### Auth model

The user logs in with a passkey (default "Moduline"); the SHA-256 hash is stored in `/etc/go_webui.conf`. Successful login mints a random token, stored both in the session and in an in-memory `tokens` list (`app.py`). Tokens are lost on restart — every login session is therefore tied to a single server lifetime. Every `/api/...` route is wrapped in `@with_session @auth` which redirects to `/` if the session token is unknown.

There is no CSRF protection beyond the auth wrapper. Endpoints that mutate state (`/api/save_module_config`, `/api/set_module_enabled`, etc.) accept JSON bodies and rely on the session cookie + same-origin policy.

### Path traversal

Static routes (`/static/`, `/style/`, `/js/`, `/assets/`) refuse paths containing `..`. Don't add new file-serving endpoints without that check.

## `modules.json` flow

The Modules page is the most schema-coupled part of this UI:

1. The Modules page (`static/modules.html` + `js/modules.js`) fetches `/api/get_modules`, which returns one entry per slot enriched with display-friendly fields (`module_name`, `article`, `recognised`, `enabled`).
2. Clicking a slot opens a per-module panel with two tabs:
   - **Pinout** — fetches `/api/get_module_pinning?article=…&slot=…`, rendered from `data/module_pinning.json` (auto-generated from `pinning.md`).
   - **Configuration** — fetches `/api/get_module_config?slot=…`, returns the slot's `module` + `channels` plus the matching `schema` entry from `MODULE_SCHEMAS`. The JS uses the schema to render the form; on Save it POSTs `/api/save_module_config`. A separate `Hardware driver` toggle at the top of the Configuration tab POSTs `/api/set_module_enabled` immediately and is independent of the dirty-state machinery.

### Adding a new module type

1. Add an entry to `MODULE_TYPE_NAMES[<6-digit prefix>]` in `handlers/modules.py` with the human-readable name (no integration-context labels — name the module after what it *is*, not who uses it; e.g. "IR Communication Module", not "Anleg IR Module").
2. Add an entry to `MODULE_SCHEMAS[<module_type>]` with `channel_count`, `module_fields`, and `channel_fields`. Field types supported by the JS renderer: `enum`, `int`, `string`, `freq_pairs`, `bool_array`. See existing entries for shape. Labels and value-labels must mirror what Node-RED uses where applicable, for cross-tool consistency.
3. Regenerate `data/module_pinning.json` from the updated `GOcontroll-Architecture/modules/pinning.md` using `scripts/generate_module_pinning.py`.
4. Ensure `go-modules` (`ModuleType` enum + `from_firmware()` mapping + defaults) and `go-hardware-driver` (registry + per-module C file) recognise the new `module_type` string. The three packages must agree.

### `READ_ONLY_SLOT_KEYS`

Detection-derived fields (`slot`, `module_type`, `article_number`, `hardware_version`, `firmware_version`, `firmware`, `manufacturer`, `qr_front`, `qr_back`) are written by `go-modules` and are *never* mutated by the UI. `save_module_config` filters these out on save. Don't add user-editable forms that touch these.

### `enabled` flag

Per-slot `enabled` boolean controls whether `go-hardware-driver` touches the module. The UI exposes this in the Configuration tab via `/api/set_module_enabled`. Missing key in the JSON defaults to `true` for backwards compatibility (modules.json files written by `go-modules` < 3.2.0 don't have the key). The toggle saves immediately and shows a hint that the driver must be restarted to pick up the change — the driver only re-reads `modules.json` at startup.

## Configuration files the UI reads / writes

| Path | Direction | Notes |
|---|---|---|
| `/etc/go_webui.conf` | r/w | INI-ish (parsed line-by-line in `conf.py`). Stores pass-hash, listen address/port, service blacklist, SSL paths. |
| `/lib/firmware/gocontroll/modules.json` | r/w | Owned by `go-modules`; UI mutates only the user-editable subset. |
| `/etc/gocontroll/config.json` | r/w | Application configuration (Configuration tab). |
| `/etc/gocontroll/parameters.js` | r/w | Env vars exposed to downstream apps. |
| `/usr/mem-diag/*` | r/w | DTC store; UI lists files and clears them on user request. |
| `/usr/mem-sim/MODEL_*` | r | Simulink model versions. |
| `/etc/image-info` | r | Build metadata of the rootfs image. |
| `/sys/firmware/devicetree/base/{hardware,platform}` | r | Controller identification (used for slot-prefix detection and home-page info). |

When adding a new endpoint that touches a system file, document it here and follow the existing pattern: open, parse, return JSON; never shell out unless there is no library alternative.

## Conventions / gotchas

- **No build step.** JS and CSS are served as-is; HTML is hand-written. Don't introduce a bundler / minifier — the controller's Python interpreter is the only runtime.
- **`_vendor/` is intentional.** Microdot and its dependencies are vendored so the controller doesn't need `pip` at install time. Don't replace with a `Depends:` on system packages.
- **Avoid third-party runtime dependencies.** The Debian control file uses base-system packages only (`python3`, `python3-jwt`, `python3-netifaces`, `python3-setuptools`). Anything else has to be vendored or skipped.
- **Vanilla JS, ES2020-ish, no frameworks.** The age of the controller's browser surface is not the constraint — it's auditability. Keep the JS readable and avoid heavy abstractions.
- **Atomic writes for shared state.** When mutating files that other processes read (`modules.json`, `parameters.js`), write `path.tmp` and `os.replace()` — see `save_module_config` and `set_module_enabled` for the pattern.
- **Never trust path inputs.** Static routes refuse `..`. API routes accept JSON only; never echo user input back as HTML.
- **Schema mismatches with `go-modules` are foreseeable.** Old `modules.json` files in the field may lack fields that the UI expects. Backfill defaults at read time (see how `enabled` and `name` are handled); never crash because a key is missing.
- **Save semantics on the Configuration tab.** Editable fields participate in the dirty-state mechanism (yellow vs. green per field; "Save" button writes the whole `module`/`channels` block). The driver-enable toggle bypasses this — it writes a single key, immediately, with its own feedback. Don't tangle the two flows.

## Related architecture documentation

The authoritative module schemas live in the `GOcontroll-Architecture` repo under `modules/`:

- `configuration.md` — `modules.json` JSON schema and runtime contract
- `naming.md` — article-number format + module-type enumeration
- `pinning.md` — per-module pin assignments per controller slot (source for `data/module_pinning.json`)
- `spi.md` — module SPI protocol reference
- `input-6ch.md`, `input-10ch.md`, `input-4-20ma.md`, `bridge-2ch.md`, `output-6ch.md`, `output-10ch.md`, `ir-communication.md` — per-module specs (the values, labels, and defaults used by `MODULE_SCHEMAS` must mirror these documents).

When the architecture documents change (new module type, new field, renamed enum value), update `handlers/modules.py` and regenerate `data/module_pinning.json` in the same change.
