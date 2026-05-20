"""ModulineWebUI package bootstrap.

The upstream `microdot` web framework is vendored under `_vendor/microdot/`
because Debian 11 (bullseye) — still the rootfs on legacy Moduline IV
controllers — does not ship `python3-microdot` in apt. Inserting `_vendor/`
ahead of the system locations on `sys.path` lets the regular
`from microdot import ...` statements throughout this package resolve
against the bundled copy on every supported Debian release, so we can drop
the `python3-microdot` Depends line in `debian/control` and ship a single
`go-web-ui_X.Y.Z_all.deb` that installs cleanly on bullseye, bookworm and
trixie alike.
"""

import os
import sys

# Runtime version. Source of truth for what `/api/get_webui_version` returns
# (and therefore what the UI footer shows). The CI workflow substitutes this
# string with the git tag at build time so the .deb's Version, the apt repo
# index and this constant always match — but committing the value here means
# that ad-hoc deploys via `cp -r` still surface the correct version, instead
# of inheriting whatever `dpkg -l go-web-ui` last installed.
__version__ = "2.2.0"

_VENDOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_vendor")
if _VENDOR not in sys.path:
    sys.path.insert(0, _VENDOR)
