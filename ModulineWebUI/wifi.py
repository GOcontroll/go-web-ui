import json
import subprocess

import netifaces as ni
from microdot import Request
from microdot.session import Session, with_session

from ModulineWebUI.app import app, auth


@app.get("/api/get_wifi")
@with_session
@auth
async def get_wifi(req: Request, session: Session):
    try:
        out = subprocess.run(
            ["rfkill", "-J", "--output-all"], check=True, capture_output=True
        )
        info = json.loads(out.stdout.decode("utf-8"))
        for device in info["rfkilldevices"]:
            if device["type"] == "wlan":
                if device["soft"] == "unblocked" and device["hard"] == "unblocked":
                    return json.dumps({"state": True})
        else:
            return json.dumps({"state": False})
    except Exception as ex:
        return json.dumps({"err": f"could get wifi state\n{ex}"})


@app.post("/api/set_wifi")
@with_session
@auth
async def set_wifi(req: Request, session: Session):
    """Set the wifi state, request contains a json boolean value\n
    Returns the state of wifi after this function is finished"""
    state = req.json["new_state"]
    try:
        if state:
            subprocess.run(
                ["nmcli", "r", "wifi", "on"], check=True, capture_output=True
            )
        else:
            subprocess.run(
                ["nmcli", "r", "wifi", "off"], check=True, capture_output=True
            )
        return json.dumps({"state": state})
    except Exception as ex:
        return json.dumps({"err": f"could not switch state to {state}\n{ex}"})


@app.post("/api/set_wifi_type")
@with_session
@auth
async def set_wifi_type(req: Request, session: Session):
    """Set the wifi type, AP or receiver, request is a string containing 'ap' or 'wifi'"""
    wifi_type: str = req.json["new_type"]
    # to make the switch permanent all wifi connections need to have their autoconnect settings altered
    # so all wifi connections need to be gathered
    try:
        try:
            stdout = subprocess.run(
                ["nmcli", "-t", "con"], stdout=subprocess.PIPE, text=True
            )
            stdout.check_returncode()
        except:
            return json.dumps({"err": "Could not get list of connections"})
        connections = stdout.stdout.rstrip().split("\n")
        wifi_connections = []
        for con in connections:
            if "wireless" in con:
                if "GOcontroll-AP" not in con:
                    wifi_connections.append(con.split(":")[0])
        if wifi_type == "ap":
            for con in wifi_connections:
                try:
                    subprocess.run(
                        ["nmcli", "con", "mod", con, "connection.autoconnect", "no"]
                    ).check_returncode()
                except:
                    return json.dumps(
                        {"err": "could not turn of autoconnect on all wifi connections"}
                    )
            try:
                subprocess.run(
                    [
                        "nmcli",
                        "con",
                        "mod",
                        "GOcontroll-AP",
                        "connection.autoconnect",
                        "yes",
                    ]
                ).check_returncode()
            except:
                return json.dumps(
                    {"err": "could not set the access point to autoconnect"}
                )
            try:
                enable_connection("GOcontroll-AP")
            except:
                return json.dumps({"err": "Could not raise the access point"})
            return json.dumps({"type": "ap"})
        elif wifi_type == "wifi":
            for con in wifi_connections:
                try:
                    subprocess.run(
                        ["nmcli", "con", "mod", con, "connection.autoconnect", "yes"]
                    ).check_returncode()
                except:
                    return json.dumps(
                        {"err": "Could not set all wifi connections to autoconnect"}
                    )
            try:
                subprocess.run(
                    [
                        "nmcli",
                        "con",
                        "mod",
                        "GOcontroll-AP",
                        "connection.autoconnect",
                        "no",
                    ]
                ).check_returncode()
            except:
                return json.dumps(
                    {"err": "Could not disable access point auto connect"}
                )
            try:
                disable_connection("GOcontroll-AP")
            except:
                return json.dumps({"err": "Could not deactivate access point"})
            return json.dumps({"type": "wifi"})
        else:
            return json.dumps({"err": "Invalid type given, must be 'ap' or 'wifi'"})
    except:
        return json.dumps({"err": "Could not set wifi type"})


@app.get("/api/get_wifi_type")
@with_session
@auth
async def get_wifi_type(req: Request, session: Session):
    try:
        try:
            output = subprocess.run(
                ["nmcli", "-t", "con", "show", "GOcontroll-AP"],
                stdout=subprocess.PIPE,
                text=True,
            )
            output.check_returncode()
        except:
            return json.dumps({"err": "Could not get access point information"})
        option = "connection.autoconnect:"
        idx = output.stdout.find(option)
        if idx >= 0:
            if output.stdout[idx + len(option)] == "y":
                return json.dumps({"type": "ap"})
            else:
                return json.dumps({"type": "wifi"})
        else:
            return json.dumps({"err": "Could not determine current wifi type"})
    except Exception as ex:
        return json.dumps({"err": f"Could not determine current wifi type:\n{ex}"})


def reload_ap():
    """Reload the access point after changes have been made for example
    raises subprocess.CalledProcessError when unsuccessfull"""
    disable_connection("GOcontroll-AP")
    enable_connection("GOcontroll-AP")


@app.post("/api/set_ap_pass")
@with_session
@auth
async def set_ap_pass(req: Request, session: Session):
    new_password: str = req.json
    try:
        subprocess.run(
            [
                "nmcli",
                "con",
                "mod",
                "GOcontroll-AP",
                "wifi-sec.psk",
                new_password,
            ]
        ).check_returncode()
    except subprocess.CalledProcessError as ex:
        return json.dumps({"err": f"Failed to set new password:\n{ex.output}"})
    except Exception as ex:
        return json.dumps({"err": f"Failed to set new password:\n{ex}"})
    reload_ap()
    return json.dumps({})


@app.post("/api/set_ap_ssid")
@with_session
@auth
async def set_ap_ssid(req: Request, session: Session):
    new_ssid: str = req.json
    try:
        subprocess.run(
            [
                "nmcli",
                "con",
                "mod",
                "GOcontroll-AP",
                "802-11-wireless.ssid",
                new_ssid,
            ]
        ).check_returncode()
    except subprocess.CalledProcessError as ex:
        return json.dumps({"err": f"Failed to set new ssid:\n{ex.output}"})
    except Exception as ex:
        return json.dumps({"err": f"Failed to set new ssid:\n{ex}"})
    reload_ap()
    return json.dumps({})


@app.get("/api/get_ap_connections")
@with_session
@auth
async def get_ap_connections(req: Request, session: Session):
    """Get a list of hostnames connected to the access point"""
    final_device_list = {}
    try:
        stdout = subprocess.run(
            ["ip", "n", "show", "dev", "wlan0"],
            stdout=subprocess.PIPE,
            text=True,
        )
        stdout.check_returncode()
    except subprocess.CalledProcessError as ex:
        return json.dumps({"err": f"Could not get information from ip:\n{ex.output}"})
    except Exception as ex:
        return json.dumps({"err": f"Could not get information from ip:\n{ex}"})

    connected_devices = stdout.stdout.split("\n")
    for i in reversed(range(len(connected_devices))):
        if (
            "REACHABLE" not in connected_devices[i]
            and "DELAY" not in connected_devices[i]
        ):
            connected_devices.pop(i)
    try:
        stdout = subprocess.run(
            ["cat", "/var/lib/misc/dnsmasq.leases"],
            stdout=subprocess.PIPE,
            text=True,
        )
        stdout.check_returncode()
    except subprocess.CalledProcessError as ex:
        return json.dumps({"err": f"Could not get dns leases:\n{ex.output}"})
    except Exception as ex:
        return json.dumps({"err": f"Could not get dns leases:\n{ex}"})

    previous_connections = stdout.stdout.split("\n")[:-1]

    for connected_device in connected_devices:
        connected_device_list = connected_device.split(" ")
        for previous_connection in previous_connections:
            if connected_device_list[2] in previous_connection:
                final_device_list[connected_device_list[2]] = previous_connection.split(
                    " "
                )[3]

    return json.dumps(final_device_list)


def disable_connection(con: str):
    """Set the connection 'con' to down
    raises subprocess.CalledProcessError when unsuccessfull"""
    subprocess.run(["nmcli", "con", "down", con]).check_returncode()


def enable_connection(con: str):
    """Set the connection 'con' to up
    raises subprocess.CalledProcessError when unsuccessfull"""
    subprocess.run(["nmcli", "con", "up", con]).check_returncode()


@app.get("/api/get_wifi_networks")
@with_session
@auth
async def get_wifi_networks(req: Request, session: Session):
    """Get the list of available wifi networks and their attributes"""
    # gets the list in a layout optimal for scripting, networks seperated by \n, columns seperated by :
    try:
        wifi_list = subprocess.run(
            ["nmcli", "-t", "dev", "wifi"], stdout=subprocess.PIPE, text=True
        )
        wifi_list.check_returncode()
    except subprocess.CalledProcessError as ex:
        return json.dumps({"err": f"Could not get wifi networks:\n{ex.output}"})
    except Exception as ex:
        return json.dumps({"err": f"Could not get wifi networks:\n{ex}"})

    networks = wifi_list.stdout.rstrip().split("\n")
    networks_out = {}
    for i in range(len(networks)):
        network = networks[i].split(":")
        if len(network) > 8:
            # some character that is not a space here means active
            connected = network[0] != " "
            # splitting by : unfortunately also splits the mac address, it also contains some \ characters
            # strip the \ characters and join it back
            mac = ":".join(map(lambda octet: octet.rstrip("\\"), network[1:7]))
            ssid = network[7]
            strength = network[11]
            security = network[13]
            networks_out[network[7]] = {
                "connected": connected,
                "mac": mac,
                "ssid": ssid,
                "strength": strength,
                "security": security,
            }
    return json.dumps(networks_out)


@app.post("/api/connect_to_wifi_network")
@with_session
@auth
async def connect_to_wifi_network(req: Request, session: Session):
    args: dict = req.json
    ssid = args["ssid"]
    password = args["password"]
    try:
        result = subprocess.run(
            ["nmcli", "dev", "wifi", "connect", ssid, "password", password],
            stdout=subprocess.PIPE,
            text=True,
        )
        result.check_returncode()
    except subprocess.CalledProcessError as ex:
        return json.dumps({"err": f"Could not connect to wifi network:\n{ex.output}"})
    # for some reason this function returns exit code 0 even on failure
    search_str = "Error:"
    idx = result.stdout.find(search_str)
    if idx >= 0:
        return json.dumps({"err": f"{result.stdout[len(search_str) :].strip()}"})
    return json.dumps({})


@app.post("/api/get_wifi_ip")
@with_session
@auth
async def get_wifi_ip(req: Request, session: Session):
    try:
        return json.dumps({"ip": ni.ifaddresses("wlan0")[ni.AF_INET][0]["addr"]})
    except Exception as ex:
        return json.dumps({"err": f"Could not get ip:\n{ex}"})


@app.get("/api/get_ap_info")
@with_session
@auth
async def get_ap_info(req: Request, session: Session):
    """Return the configured SSID of the GOcontroll-AP profile, no password."""
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "802-11-wireless.ssid", "con", "show", "GOcontroll-AP"],
            stdout=subprocess.PIPE,
            text=True,
        )
        result.check_returncode()
        ssid = ""
        for line in result.stdout.strip().split("\n"):
            if line.startswith("802-11-wireless.ssid:"):
                ssid = line.split(":", 1)[1]
                break
        return json.dumps({"ssid": ssid})
    except Exception as ex:
        return json.dumps({"err": f"Could not read AP profile: {ex}"})


def _wlan0_ip() -> str:
    try:
        return ni.ifaddresses("wlan0").get(ni.AF_INET, [{}])[0].get("addr", "")
    except Exception:
        return ""


def _active_wlan_connection() -> str:
    """Return the NetworkManager profile name of the currently active wifi connection
    on wlan0 (other than GOcontroll-AP). Empty string if none."""
    try:
        out = subprocess.run(
            ["nmcli", "-t", "-f", "NAME,TYPE,DEVICE", "con", "show", "--active"],
            stdout=subprocess.PIPE, text=True,
        )
        out.check_returncode()
    except Exception:
        return ""
    for line in out.stdout.strip().split("\n"):
        parts = line.split(":")
        if len(parts) < 3:
            continue
        name, ctype, device = parts[0], parts[1], parts[2]
        if "wireless" in ctype and device == "wlan0" and name != "GOcontroll-AP":
            return name
    return ""


@app.get("/api/get_active_wifi")
@with_session
@auth
async def get_active_wifi(req: Request, session: Session):
    """Return live details of the currently joined wifi network on wlan0,
    excluding GOcontroll-AP. Cached scan results are used (no rescan triggered)."""
    name = _active_wlan_connection()
    if not name:
        return json.dumps({"connected": False})

    info = {"connected": True, "name": name, "ip": _wlan0_ip()}

    # Pull live BSSID, signal, security, frequency, rate from nmcli's cached scan.
    try:
        result = subprocess.run(
            ["nmcli", "-t",
             "-f", "ACTIVE,BSSID,SSID,SIGNAL,SECURITY,FREQ,RATE",
             "dev", "wifi", "list", "--rescan", "no"],
            stdout=subprocess.PIPE, text=True,
        )
        result.check_returncode()
        for line in result.stdout.rstrip().split("\n"):
            parts = line.split(":")
            # ACTIVE + 6×BSSID octets + SSID + SIGNAL + SECURITY + FREQ + RATE = 12 fields
            if len(parts) < 12:
                continue
            if parts[0] != "yes":
                continue
            info["bssid"]     = ":".join(o.rstrip("\\") for o in parts[1:7])
            info["ssid"]      = parts[7]
            info["signal"]    = parts[8]
            info["security"]  = parts[9] or "Open"
            info["frequency"] = parts[10]
            info["rate"]      = parts[11]
            break
    except Exception:
        pass

    return json.dumps(info)


@app.get("/api/get_saved_wifi_networks")
@with_session
@auth
async def get_saved_wifi_networks(req: Request, session: Session):
    """List all saved wifi profiles (excluding GOcontroll-AP).
    For each profile the SSID is read from its config; whether it's currently
    on wlan0 is reflected by the 'active' flag."""
    try:
        out = subprocess.run(
            ["nmcli", "-t", "-f", "NAME,TYPE,DEVICE,AUTOCONNECT", "con", "show"],
            stdout=subprocess.PIPE, text=True,
        )
        out.check_returncode()
    except Exception as ex:
        return json.dumps({"err": f"Could not list connections: {ex}"})

    networks = []
    for line in out.stdout.strip().split("\n"):
        parts = line.split(":")
        if len(parts) < 4:
            continue
        name, ctype, device, autoconnect = parts[0], parts[1], parts[2], parts[3]
        if "wireless" not in ctype or name == "GOcontroll-AP":
            continue
        ssid = name
        try:
            detail = subprocess.run(
                ["nmcli", "-t", "-f", "802-11-wireless.ssid", "con", "show", name],
                stdout=subprocess.PIPE, text=True,
            )
            detail.check_returncode()
            for dline in detail.stdout.strip().split("\n"):
                if dline.startswith("802-11-wireless.ssid:"):
                    ssid = dline.split(":", 1)[1] or name
                    break
        except Exception:
            pass
        networks.append({
            "name": name,
            "ssid": ssid,
            "active": device == "wlan0",
            "autoconnect": autoconnect == "yes",
        })
    return json.dumps(networks)


@app.post("/api/forget_wifi_network")
@with_session
@auth
async def forget_wifi_network(req: Request, session: Session):
    name = (req.json or {}).get("name", "")
    if not name or name == "GOcontroll-AP":
        return json.dumps({"err": "That connection cannot be removed"})
    try:
        result = subprocess.run(
            ["nmcli", "con", "delete", name],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        if result.returncode != 0:
            return json.dumps({"err": result.stderr.strip() or result.stdout.strip()})
        return json.dumps({"name": name})
    except Exception as ex:
        return json.dumps({"err": f"Could not delete profile: {ex}"})


@app.post("/api/connect_saved_wifi")
@with_session
@auth
async def connect_saved_wifi(req: Request, session: Session):
    """Activate an existing saved wifi profile by name. No password needed."""
    name = (req.json or {}).get("name", "")
    if not name or name == "GOcontroll-AP":
        return json.dumps({"err": "Invalid profile"})
    try:
        result = subprocess.run(
            ["nmcli", "con", "up", name],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        if result.returncode != 0:
            return json.dumps({"err": result.stderr.strip() or result.stdout.strip()})
        return json.dumps({"name": name})
    except Exception as ex:
        return json.dumps({"err": f"Could not connect: {ex}"})
