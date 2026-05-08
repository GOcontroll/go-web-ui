#!/usr/bin/env python3

import hashlib
import ipaddress
import logging
import os
import ssl
import subprocess
from argparse import ArgumentParser, BooleanOptionalAction
from logging.handlers import RotatingFileHandler
from pathlib import Path

from ModulineWebUI.app import app, set_passkey
from ModulineWebUI.conf import create_default_conf, get_conf
from ModulineWebUI.handlers.service import set_service_blacklist

logger = logging.getLogger(__name__)
#########################################################################################################


def parse_boolean(boolean: str) -> bool:
    if boolean.lower() in ["y", "yes", "true"]:
        return True
    elif boolean.lower() in ["n", "no", "false"]:
        return False
    else:
        raise ValueError


def setup_logging():
    # Create a logger
    logger = logging.getLogger()
    logger.setLevel(logging.WARNING)  # Set the logging level

    # Format for log messages
    formatter = logging.Formatter(
        "%(asctime)s {%(filename)s:%(lineno)d} %(levelname)s - %(message)s"
    )

    # Create a console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    try:
        # Create a rotating file handler
        file_handler = RotatingFileHandler(
            "/var/log/go_webui.log", maxBytes=5 * 1024 * 1024, backupCount=3
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except PermissionError:
        logger.warning(
            "Unable to open /var/log/go_webui.log due to insufficient permissions, only logging to console"
        )


def get_args():
    parser = ArgumentParser(
        prog="go-web-ui",
        description="""go-web-ui\n
        This program provides a web based interface for GOcontroll Moduline controllers""",
        epilog="Any argument passed will override the value set in /etc/go_webui.conf",
        add_help=True,
    )
    parser.add_argument(
        "-a",
        "--address",
        required=False,
        type=str,
        help="The address the server listens on",
    )
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        required=False,
        help="The port the server listens on",
    )
    parser.add_argument(
        "-P",
        "--passkey",
        required=False,
        type=str,
        help="the passkey for the login page",
    )
    parser.add_argument(
        "-b",
        "--service-blacklist",
        type=str,
        required=False,
        help="A comma seperated list of services that are not allowed to be managed via the web UI",
    )
    parser.add_argument(
        "--sslgen",
        action=BooleanOptionalAction,
        required=False,
        default=None,
        help="Generate an SSL key/certificate upon startup or not to override the config",
    )
    parser.add_argument(
        "-k",
        "--sslkey",
        required=False,
        type=Path,
        help="Supply a path to an ssl key file for the server to use",
    )
    parser.add_argument(
        "-c",
        "--sslcert",
        required=False,
        type=Path,
        help="Supply a path to an ssl certificate file for the server to use",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = get_args()
    setup_logging()
    logger.debug("Setup logging...")

    # register the routes from these modules
    from ModulineWebUI.controller import *
    from ModulineWebUI.ethernet import *
    from ModulineWebUI.wifi import *
    from ModulineWebUI.wwan import *
    from ModulineWebUI.can import *

    # process /etc/go_webui.conf
    conf = {}
    try:
        conf = get_conf()
    except FileNotFoundError:
        logger.warning(
            "missing configuration file /etc/go_webui.conf, trying to create a default configuration"
        )
        try:
            create_default_conf()
            conf = get_conf()
        except PermissionError:
            logger.error("not allowed to create default config, trying with arguments")
        except Exception as ex:
            logger.exception("Failed everything")
    except Exception as ex:
        logger.exception("Failed everything")

    # validate server address
    ip = conf.get("ip", "127.0.0.1")
    if args.address is not None:
        try:
            ipaddress.IPv4Address(args.address)
            ip = args.address
        except ValueError:
            logger.critical("Address passed as argument is not a valid IP address")
            exit(-1)
    else:
        try:
            ipaddress.IPv4Address(ip)
        except ValueError:
            logger.warning(
                "Invalid IP configured in /etc/go_webui.conf: %s, continuing with default 127.0.0.1",
                ip,
            )
            ip = "127.0.0.1"

    port = conf.get("port", 5000)
    if args.port is not None:
        print(args.port)
        if 1 <= args.port and args.port <= 65535:
            port = args.port
        else:
            logger.critical("Port passed as argument is not valid")
            exit(-1)
    else:
        try:
            port = int(port)
            if not 1 <= port and port <= 65535:
                raise ValueError
        except ValueError:
            logger.error(
                "Invalid port configured in /etc/go_webui.conf: %s, continuing with default 5000",
                port,
            )
            port = 5000

    service_blacklist = conf.get("service_blacklist", "").split(",")
    if args.service_blacklist is not None:
        try:
            service_blacklist = args.service_blacklist.split(",")
        except Exception as ex:
            logger.error(
                f"Failed to parse service-blacklist argument, using config instead\n{ex}"
            )
    set_service_blacklist(service_blacklist)

    sslg = conf.get("ssl_gen", "false")
    if args.sslgen is not None:
        sslg = args.sslgen
    else:
        try:
            sslg = parse_boolean(sslg)
        except ValueError:
            logger.error(
                """ssl_gen parameter in /etc/go_webui.conf is not configured right, check for typos
    it should be set to [y]es/[n]o or true/false, not %s.
    continuing with the default which is false""",
                sslg,
            )
            sslg = False

    sslc = conf.get("ssl_cert", "")
    if args.sslcert is not None:
        if os.path.exists(args.sslcert):
            sslc = args.sslcert.absolute()
        else:
            logger.critical(
                "SSL certificate passed as an argument doesn't exist at %s",
                args.sslcert.absolute(),
            )
            exit(-1)
    elif sslc != "":
        if not os.path.exists(sslc):
            logger.warning(
                "Could not find ssl certificate at %s, continuing without ssl",
                os.path.abspath(sslc),
            )
            sslc = ""

    sslk = conf.get("ssl_key", "")
    if args.sslkey is not None:
        if os.path.exists(args.sslcert):
            sslc = args.sslcert.absolute()
        else:
            logger.critical(
                "SSL key passed as an argument doesn't exist at %s",
                args.sslcert.absolute(),
            )
            exit(-1)
    elif sslk != "":
        if not os.path.exists(sslk):
            logger.warning(
                "Could not find ssl key at %s, continuing without ssl",
                os.path.abspath(sslk),
            )
            sslk = ""

    conf_passkey = conf.get("pass_hash", "")
    if args.passkey is not None:
        # passkey entered by argument still needs to be hashed
        set_passkey(hashlib.sha256(args.passkey.encode()).hexdigest())
    elif conf_passkey != "":
        # passkey in the conf should already be a hash
        set_passkey(conf_passkey)
    else:
        logger.critical(
            "No passkey has been found in the configuration or the arguments, the server must have a passkey to run"
        )
        exit(-1)

    # run the correct version of the server
    if sslg:
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:4096",
                "-nodes",
                "-out",
                "cert.pem",
                "-keyout",
                "key.pem",
                "-days",
                "365",
                "-subj",
                "/C=NL/ST=Gelderland/L=Ulft/O=GOcontroll B.V./OU='.'/CN=GOcontroll",
            ]
        ).check_returncode()
        sslctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        sslctx.load_cert_chain("cert.pem", "key.pem")
        app.run(host=ip, port=port, ssl=sslctx)

    elif sslc != "" and sslk != "":
        sslctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        sslctx.load_cert_chain(sslc, sslk)
        app.run(host=ip, port=port, ssl=sslctx)

    else:
        app.run(host=ip, port=port)
