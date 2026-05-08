import hashlib
import json
import random
import string
from functools import wraps

from microdot import Microdot, Request, Response, redirect, send_file
from microdot.session import Session, with_session

from ModulineWebUI.conf import modify_conf

current_passkey = ""
tokens = []


def set_passkey(key: str):
    global current_passkey
    current_passkey = key


def get_passkey() -> str:
    global current_passkey
    return current_passkey


def authenticate_token(token: str) -> bool:
    try:
        tokens.index(token)
        return True
    except ValueError:
        return False


def register_token(token: str):
    tokens.append(token)


def remove_token(token: str):
    try:
        tokens.remove(token)
    except ValueError:
        pass


def auth(func):
    @wraps(func)
    async def wrapper(req: Request, session: Session, *args, **kwargs):
        if not authenticate_token(session.get("token")):
            return redirect("/")
        return await func(req, session, *args, **kwargs)

    return wrapper


app = Microdot()
Session(
    app,
    secret_key="".join(
        random.SystemRandom().choice(string.ascii_uppercase + string.digits)
        for _ in range(10)
    ),
)  # generate new session key when the server is restarted
Response.default_content_type = "text/html"


@app.get("/")
@with_session
async def index(req: Request, session: Session):
    token = session.get("token")
    if token is None or not authenticate_token(token):
        return send_file("ModulineWebUI/login.html")
    elif authenticate_token(token):
        return redirect("/static/home.html")


@app.post("/login")
@with_session
async def login(req: Request, session: Session):
    passkey = req.json
    pass_hash = hashlib.sha256(passkey.encode())
    passkey = pass_hash.hexdigest()
    if passkey == current_passkey:
        token = "".join(
            random.SystemRandom().choice(string.ascii_uppercase + string.digits)
            for _ in range(10)
        )  # generate new token for every new authorized session
        session["token"] = token
        register_token(token)
        session.save()
        return json.dumps("success")
    else:
        return json.dumps({"err": "Incorrect password"})


@app.post("/logout")
@with_session
async def logout(req: Request, session: Session):
    remove_token(session.get("token"))
    session.delete()
    return redirect("/")


@app.post("/api/set_passkey")
@with_session
@auth
async def set_passkey_route(req: Request, session: Session):
    data: dict = req.json
    pass_hash = hashlib.sha256(data["passkey"].encode())
    passkey = pass_hash.hexdigest()
    try:
        modify_conf("pass_hash", passkey)
    except FileNotFoundError or PermissionError as ex:
        return json.dumps(
            {
                "err": "Could not save the new password, password unchanged",
                "deets": f"{ex}",
            }
        )
    set_passkey(passkey)
    return json.dumps({})


#########################################################################################################

# file hosting


@app.route("/static/<path:path>")
@with_session
@auth
async def static(req: Request, session: Session, path: str):
    if ".." in path:
        return "Not allowed", 404
    return send_file("ModulineWebUI/static/" + path)


@app.route("/style/<path:path>")
async def style(req: Request, path):
    if ".." in path:
        return "Not allowed", 404
    return send_file("ModulineWebUI/style/" + path)


@app.route("/js/<path:path>")
async def js(request: Request, path):
    if ".." in path:
        return "Not allowed", 404
    return send_file("ModulineWebUI/js/" + path)


@app.route("/assets/<path:path>")
async def assets(request: Request, path):
    if ".." in path:
        return "Not allowed", 404
    return send_file("ModulineWebUI/assets/" + path)


@app.get("/favicon.ico")
async def favicon(request: Request):
    return send_file("ModulineWebUI/favicon.ico")
