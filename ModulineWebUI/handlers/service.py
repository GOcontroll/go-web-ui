import logging
import subprocess

logger = logging.getLogger(__name__)

# keep this list up to date with index 0 of the list in services.js
# this list limits the services that can be accessed through this api

services = [
    "ssh",
    "go-simulink",
    "nodered",
    "go-bluetooth",
    "go-upload-server",
    "go-auto-shutdown",
    "gadget-getty@ttyGS0",
    "getty@ttymxc2",
    "go-webui",
]

service_blacklist = []


def set_service_blacklist(blacklist: list[str]):
    global service_blacklist
    service_blacklist = blacklist


def get_service_blacklist() -> list[str]:
    global service_blacklist
    return service_blacklist


def get_service(service: str) -> bool:
    return not bool(subprocess.run(["systemctl", "is-active", service]).returncode)


def set_service(service: str, enable: bool) -> "tuple[bool, str]":
    """
    Returns a tuple where bool is false if the service failed to change
    and str contains errors.
    """
    try:
        if enable:
            subprocess.run(
                ["systemctl", "enable", service],
                capture_output=True,
                text=True,
                check=True,
            )
            subprocess.run(
                ["systemctl", "start", service],
                capture_output=True,
                text=True,
                check=True,
            )
        else:
            subprocess.run(
                ["systemctl", "disable", service],
                capture_output=True,
                text=True,
                check=True,
            )
            subprocess.run(
                ["systemctl", "stop", service],
                capture_output=True,
                text=True,
                check=True,
            )
    except subprocess.CalledProcessError as e:
        logger.error(
            "Failed to change service '%s' state '%s'. Reason: %s",
            service,
            enable,
            e.stderr,
        )
        return False, e.stderr
    else:
        return True, ""
