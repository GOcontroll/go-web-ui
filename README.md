# go-web-ui

Web-based configuration UI for GOcontroll Moduline controllers.

## Description

`go-web-ui` provides a browser-accessible interface to configure and monitor GOcontroll Moduline controllers. It allows users to:

- View general system information and controller status
- Configure network interfaces (Ethernet, WiFi, WWAN)
- Manage and control systemd services
- Read and clear diagnostic trouble codes (DTCs)
- Configure Simulink model parameters

The web server listens on port 5000 by default and is secured with a passkey.

## Configuration

The configuration file is located at `/etc/go_webui.conf`:

```ini
# IP the server listens on
ip=0.0.0.0
# Port the server listens on
port=5000
# SHA256 hash of the passkey (default: "Moduline")
pass_hash=70ee82b31794ab8fc317d80b7d20eef00f64a97459e3edd74adacafcc6bfd9be
# Comma-separated list of services not allowed to be controlled via the UI
service_blacklist=
# Generate a new SSL certificate/key on startup
ssl_gen=false
# Path to SSL key (ignored if ssl_gen=true)
ssl_key=
# Path to SSL certificate (ignored if ssl_gen=true)
ssl_cert=
```

## Development

Set up a virtual environment and install in editable mode:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install --editable ".[dev]"
go-web-ui --passkey test
```

## Changelog

### v1.3.0
- Initial release on apt.gocontroll.com
