import json
import os
import subprocess

from microdot import Request, send_file
from microdot.session import Session, with_session

from ModulineWebUI.app import app, auth
import ModulineWebUI.diag as diag
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


# parameters
@app.get("/api/get_parameters")
@with_session
@auth
async def get_parameters(req: Request, session: Session):
    try:
        parameters = []
        files = sorted(os.listdir("/etc/go-simulink"))
        for file in files:
            with open(f"/etc/go-simulink/{file}", "r") as par:
                parameters.append({"name": file, "val": par.readline().strip()})
        return json.dumps(parameters)
    except Exception as ex:
        return json.dumps({"err": f"Could not get parameters\n{ex}"})


@app.post("/api/save_parameters")
@with_session
@auth
async def save_parameters(req: Request, session: Session):
    parameters = req.json
    faulty = {"err": []}
    for param in parameters:
        if "/" in param["name"]:
            continue
        try:
            float(param["val"])
        except ValueError:
            faulty["err"].append(param["name"])
            continue
        with open(f"/etc/go-simulink/{param['name']}", "w") as par:
            par.write(param["val"])
    if len(faulty["err"]):
        return json.dumps(faulty), 400
    return json.dumps({})
