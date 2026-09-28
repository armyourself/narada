"""
This module contains the main FastAPI application and its routes.
"""

from __future__ import annotations
import argparse
import asyncio
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request, Response as FastAPIResponse, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from src.internal.client_handler import ClientHandler
from src.internal.nostr_handler import NostrHandler
from src.internal.account_manager import AccountManager
from src.internal.file_system import FileObject, Root
from src.routers import (
    account_tasks,
    mailbox_tasks,
    nostr_tasks,
)
from src.helpers.uvicorn_logger import UvicornLogger
from src.helpers.port_scanner import PortScanner

from src._types import Response
from src.consts import (
    APP_NAME,
    DEFAULT_HOST,
    DEFAULT_TRUSTED_HOSTS,
    DEFAULT_PORT_RANGE,
    DEFAULT_WHITELISTED_IPS,
)
from src.utils import is_address_valid, parse_err_msg


#################### SET UP #######################

WHITELISTED_IPS = DEFAULT_WHITELISTED_IPS

client_handler = ClientHandler()
nostr_handler = NostrHandler()
account_manager = AccountManager()
uvicorn_logger = UvicornLogger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        client_handler.create_openmail_clients()
        nostr_handler.load_stored_identities(nostr_handler.get_config())
        nostr_handler.connect_all()
        yield
    finally:
        nostr_handler.shutdown()
        client_handler.shutdown()

app = FastAPI(lifespan=lifespan)
app.include_router(account_tasks.router)
app.include_router(mailbox_tasks.router)
app.include_router(nostr_tasks.router)
def setup_api_middlewares(**kwargs):
    app.add_middleware(
        CORSMiddleware,
        allow_origins=kwargs.get("allow_origins", ["*"]),
        allow_credentials=kwargs.get("allow_credentials", True),
        allow_methods=kwargs.get("allow_methods", ["*"]),
        allow_headers=kwargs.get("allow_headers", ["*"]),
    )
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=kwargs.get("allowed_hosts", DEFAULT_TRUSTED_HOSTS)
    )

@app.middleware("http")
async def validate_ip(request: Request, call_next):
    global WHITELISTED_IPS
    if WHITELISTED_IPS != DEFAULT_WHITELISTED_IPS:
        ip = str(request.client.host)
        if ip not in WHITELISTED_IPS:
            raise HTTPException(status_code=403, detail="Forbidden: IP not allowed")

    # Proceed if IP is allowed
    return await call_next(request)


@app.middleware("http")
async def catch_request_for_logging(request: Request, call_next):
    async def get_response_body(response: FastAPIResponse) -> bytes:
        response_body = b""
        async for chunk in response.body_iterator:
            response_body += chunk
            return response_body
        return response_body

    response = await call_next(request)
    response._body = await get_response_body(response)
    uvicorn_logger.request(request, response)
    return FastAPIResponse(
        content=parse_err_msg(response._body)[0],
        status_code=response.status_code,
        headers=dict(response.headers),
        media_type=response.media_type,
    )


@app.get("/hello")
async def hello() -> Response:
    return Response(success=True, message="Hello, Server is ready for you!")

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Narada node server (FastAPI + Nostr transport)")
    parser.add_argument("--host", default=None, help="Bind host (implies --non-interactive)")
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Preferred port; scans upward if busy (implies --non-interactive)",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Skip all interactive prompts (for spawning from the desktop client)",
    )
    return parser.parse_args()


def main():
    global WHITELISTED_IPS

    args = _parse_args()
    non_interactive = args.non_interactive or args.host is not None or args.port is not None

    if non_interactive:
        # Config Host + Port without prompts (used by the client's "start local server")
        host = args.host or DEFAULT_HOST
        preferred_port = args.port if args.port is not None else DEFAULT_PORT_RANGE[0]
        scan_end = preferred_port + 100
        print(f"Finding free port at {host} starting from {preferred_port}...", flush=True)
        try:
            port = PortScanner.find_free_port(host, preferred_port, scan_end)
        except RuntimeError:
            print(f"error: no free port available in {preferred_port}-{scan_end} on {host}", file=sys.stderr)
            raise SystemExit(1)
    else:
        # Config Host
        host = str(input(f"Give an HOST to app run on (e.g. {DEFAULT_HOST}): ") or DEFAULT_HOST)

        # Config Port
        while True:
            try:
                port_start_range = int(input(f"Port start range (e.g. {DEFAULT_PORT_RANGE[0]}): ") or DEFAULT_PORT_RANGE[0])
                port_end_range = int(input(f"Port end range (e.g. {DEFAULT_PORT_RANGE[1]}): ") or DEFAULT_PORT_RANGE[1])
                print(f"Finding free port between {port_start_range}-{port_end_range}...")
                port = PortScanner.find_free_port(host, port_start_range, port_end_range)
                break
            except RuntimeError:
                pass

    # Config Allowed IPs (interactive only; non-interactive keeps the default "*")
    while not non_interactive:
        YES_ANSWER_KEY = "y"
        NO_ANSWER_KEY = "n"
        CANCEL_ADDRESS_KEY = "c"
        try:
            address = input(f"Enter an IP address allowed to connect to the server or type '{CANCEL_ADDRESS_KEY}' to skip: (e.g. 192.168.1.100): ")
            if address.lower() == CANCEL_ADDRESS_KEY.lower():
                if WHITELISTED_IPS == DEFAULT_WHITELISTED_IPS:
                    confirmation = input(
                        f"No IP addresses were provided. The default will be '{DEFAULT_WHITELISTED_IPS}' — meaning anyone can connect to the server.\n"
                        f"Are you sure you want to continue? ({YES_ANSWER_KEY}/{NO_ANSWER_KEY}): "
                    ).strip().lower()
                    if confirmation == YES_ANSWER_KEY:
                        break
                    elif confirmation == NO_ANSWER_KEY:
                        continue
                    else:
                        print("Invalid response. Please enter 'y' or 'n'.")
                        continue
                else:
                    break

            if is_address_valid(address):
                if WHITELISTED_IPS == DEFAULT_WHITELISTED_IPS:
                    WHITELISTED_IPS = []
                WHITELISTED_IPS.append(address)
            else:
                print(f"Error: Given address {address} is not valid. Try again please...")
        except KeyboardInterrupt:
            print("\nOperation cancelled by user.")
            break
        except RuntimeError:
            pass

    # TODO: User must be able change middleware config
    setup_api_middlewares()

    # Create file system
    pid = str(os.getpid())
    etc = Root("etc")
    uvicorn_info = FileObject("uvicorn.info")
    etc.append(uvicorn_info)
    uvicorn_info.write(f"URL=http://{host}:{str(port)}\nPID={pid}\n", overwrite=True)

    # Start server
    uvicorn_logger.info("Starting server at http://%s:%d | PID: %s", host, port, pid)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
