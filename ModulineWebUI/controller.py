import json
import os
import subprocess

from microdot import Request, send_file
from microdot.session import Session, with_session

from ModulineWebUI.app import app, auth
import ModulineWebUI.diag as diag
import ModulineWebUI.handlers.modules as modules_handler
import ModulineWebUI.handlers.parameters as parameters_handler
from ModulineWebUI.handlers.service import (
    get_service,
    get_service_blacklist,
    services,
    set_service,
)


@app.post("/api/get_service")
@with_session
@auth
async def get_service_route(req: Request, session: Session):
    service: str = req.json
    if service not in get_service_blacklist() and service in services:
        return json.dumps({"state": get_service(service)})
    else:
        return json.dumps({"err": "Invalid service"})


@app.post("/api/set_service")
@with_session
@auth
async def set_service_route(req: Request, session: Session):
    data = req.json
    new_state: bool = data["new_state"]
    service: str = data["service"]
    if service not in get_service_blacklist() and service in services:
        is_changed, error = set_service(service, new_state)
        if is_changed:
            return json.dumps({"new_state": new_state})
        else:
            return json.dumps(
                {"err": f"Failed to change service '{service}' state {error}"}
            )
    else:
        return json.dumps({"err": "Invalid service"})


# simulink
@app.get("/api/get_sim_ver")
@with_session
@auth
async def get_sim_ver(req: Request, session: Session):
    try:
        with open("/usr/mem-sim/MODEL_MAJOR", "r") as major:
            major_ver = major.readline()
        with open("/usr/mem-sim/MODEL_FEATURE", "r") as feature:
            feature_ver = feature.readline()
        with open("/usr/mem-sim/MODEL_FIX", "r") as fix:
            fix_ver = fix.readline()
        version = f"V{major_ver}.{feature_ver}.{fix_ver}"
        return json.dumps({"version": version})
    except Exception as ex:
        return json.dumps({"err": f"No changelog found\n{ex}"})


@app.get("/api/GOcontroll_Linux.a2l")  # last part of route determines file name
@with_session
@auth
async def a2l_down(req: Request, session: Session):
    path = "/usr/simulink/GOcontroll_Linux.a2l"
    if not os.path.isfile(path):
        return (
            json.dumps({"err": "No .a2l file is present on this controller. "
                               "It is generated when a Simulink application is built and uploaded."}),
            404,
            {"Content-Type": "application/json"},
        )
    return send_file(path)


# controller info
@app.get("/api/get_hardware")
@with_session
@auth
async def get_hardware(req: Request, session: Session):
    try:
        with open("/sys/firmware/devicetree/base/hardware", "r") as hardware_file:
            return json.dumps({"hardware": hardware_file.read().strip("\x00 \t\n\r")})
    except Exception as ex:
        return json.dumps({"err": f"No hardware description found\n{ex}"})


@app.get("/api/get_platform")
@with_session
@auth
async def get_platform(req: Request, session: Session):
    try:
        with open("/sys/firmware/devicetree/base/platform", "r") as platform_file:
            return json.dumps({"platform": platform_file.read().strip("\x00 \t\n\r")})
    except Exception as ex:
        return json.dumps({"err": f"No platform description found\n{ex}"})


@app.get("/api/get_rootfs_build")
@with_session
@auth
async def get_rootfs_build(req: Request, session: Session):
    """Parse /etc/image-info (shell-style KEY=VALUE) emitted by the rootfs build."""
    try:
        info = {}
        with open("/etc/image-info", "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                info[key.strip()] = val.strip().strip('"').strip("'")
        return json.dumps({
            "build_date": info.get("IMAGE_BUILD_DATE", ""),
            "build_sha":  info.get("IMAGE_BUILD_SHA", ""),
            "variant":    info.get("IMAGE_VARIANT", ""),
            "rootfs":     info.get("IMAGE_ROOTFS", ""),
        })
    except FileNotFoundError:
        return json.dumps({"err": "No /etc/image-info on this controller"})
    except Exception as ex:
        return json.dumps({"err": f"Could not read /etc/image-info: {ex}"})


@app.get("/api/get_software")
@with_session
@auth
async def get_software(req: Request, session: Session):
    try:
        res = subprocess.run(["uname", "-rs"], stdout=subprocess.PIPE, text=True)
        res.check_returncode()
        return json.dumps({"version": res.stdout.strip()})
    except Exception as ex:
        return json.dumps({"err": f"Could not get version\n{ex}"})


_webui_version: "str | None" = None


@app.get("/api/get_webui_version")
@with_session
@auth
async def get_webui_version(req: Request, session: Session):
    """Return the installed go-web-ui Debian package version (cached)."""
    global _webui_version
    if _webui_version is None:
        try:
            res = subprocess.run(
                ["dpkg-query", "-W", "-f=${Version}", "go-web-ui"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            _webui_version = res.stdout.strip() if res.returncode == 0 else ""
        except Exception:
            _webui_version = ""
    return json.dumps({"version": _webui_version})


@app.get("/api/get_serial_number")
@with_session
@auth
async def get_serial_number(req: Request, session: Session):
    try:
        res = subprocess.run(["go-sn", "r"], stdout=subprocess.PIPE, text=True)
        res.check_returncode()
        return json.dumps({"sn": res.stdout.strip()})
    except subprocess.CalledProcessError as ex:
        return json.dumps({"err": f"Could not get the serial number\n{ex.output}"})
    except Exception as ex:
        return json.dumps({"err": f"Could not get the serial number\n{ex}"})


# modules
@app.get("/api/get_modules")
@with_session
@auth
async def get_modules_route(req: Request, session: Session):
    try:
        modules = modules_handler.get_modules()
    except FileNotFoundError:
        return json.dumps({"err": "modules.json not found on this controller"})
    except Exception as ex:
        return json.dumps({"err": f"Could not read modules.json: {ex}"})
    prefix, platform = modules_handler.get_slot_prefix()
    return json.dumps({
        "modules": modules,
        "platform": platform,
        "slot_prefix": prefix,
        "platform_image": modules_handler.PLATFORM_IMAGE.get(prefix),
    })


@app.get("/api/get_modules_manifest")
@with_session
@auth
async def get_modules_manifest_route(req: Request, session: Session):
    manifest, err = modules_handler.fetch_manifest()
    out = {}
    if manifest is not None:
        out["manifest"] = manifest
    if err is not None:
        out["err"] = err
    return json.dumps(out)


@app.get("/api/get_controller_pinning")
@with_session
@auth
async def get_controller_pinning_route(req: Request, session: Session):
    info = modules_handler.get_controller_pinning()
    if info is None:
        return json.dumps({"err": "No controller pinning data for this platform"})
    return json.dumps(info)


@app.get("/api/get_module_pinning")
@with_session
@auth
async def get_module_pinning_route(req: Request, session: Session):
    article = req.args.get("article", "")
    slot_str = req.args.get("slot", "")
    if not article or len(article) < 6 or not article[:6].isdigit():
        return json.dumps({"err": "Invalid article"})
    try:
        slot = int(slot_str)
    except (TypeError, ValueError):
        return json.dumps({"err": "Invalid slot"})
    pinning = modules_handler.get_pinning_for(article[:6], slot)
    if pinning is None:
        return json.dumps({"err": "No pinning data for this module type"})
    return json.dumps(pinning)


# errors
@app.get("/api/get_errors")
@with_session
@auth
async def get_errors(req: Request, session: Session):
    # try to import a custom get_errors script
    try:
        return json.dumps(diag.get_errors())
    # default route
    except:
        output = []
        try:
            files = os.listdir("/usr/mem-diag")
            for file in files:
                try:
                    int(file)
                except ValueError:
                    continue
                output.append({"fc": file})
            return json.dumps(output)
        except Exception as ex:
            return json.dumps({"err": f"Could not get errors\n{ex}"})


@app.post("/api/delete_errors")
@with_session
@auth
async def delete_errors(req: Request, session: Session):
    errors: "list[str]" = req.json
    try:
        for file in errors:
            if "/" in file:
                continue
            os.remove(f"/usr/mem-diag/{file}")
    except Exception as ex:
        return json.dumps({"err": f"Could not delete all requested errors\n{ex}"})
    return json.dumps({})


# Application configuration (/etc/gocontroll/config.json)
@app.get("/api/get_app_config")
@with_session
@auth
async def get_app_config_route(req: Request, session: Session):
    try:
        return json.dumps({"config": parameters_handler.get_config()})
    except Exception as ex:
        return json.dumps({"err": f"Could not read config: {ex}"})


@app.post("/api/save_app_config")
@with_session
@auth
async def save_app_config_route(req: Request, session: Session):
    data = req.json
    if not isinstance(data, dict):
        return json.dumps({"err": "Body must be an object of key/value pairs"})
    try:
        parameters_handler.save_config(data)
    except Exception as ex:
        return json.dumps({"err": f"Could not save config: {ex}"})
    return json.dumps({})


# Environment variables (/etc/gocontroll/parameters.js)
@app.get("/api/get_env_parameters")
@with_session
@auth
async def get_env_parameters_route(req: Request, session: Session):
    try:
        return json.dumps({"entries": parameters_handler.get_env_parameters()})
    except Exception as ex:
        return json.dumps({"err": f"Could not read parameters.js: {ex}"})


@app.post("/api/save_env_parameters")
@with_session
@auth
async def save_env_parameters_route(req: Request, session: Session):
    entries = req.json
    if not isinstance(entries, list):
        return json.dumps({"err": "Body must be a list of {alias, env, value} objects"})
    try:
        parameters_handler.save_env_parameters(entries)
    except Exception as ex:
        return json.dumps({"err": f"Could not save parameters.js: {ex}"})
    return json.dumps({})
