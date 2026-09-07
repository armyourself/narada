"""
This module contains the main FastAPI application and its routes.
TODO: improve docstring
"""

from __future__ import annotations
import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from src.internal.client_handler import ClientHandler
from src.internal.account_manager import AccountManager
from src.internal.file_system import FileObject, Root
from src.routers import (
    account_tasks,
    narada_identity_tasks,
    narada_protocol_tasks,
    mailbox_tasks,
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
account_manager = AccountManager()
uvicorn_logger = UvicornLogger()


# Narada outbox drainer state. The drainer is a small background task
# that runs every narada_DRAIN_INTERVAL seconds during the FastAPI
# lifespan; it tries to deliver every due outbox entry.
_narada_DRAIN_INTERVAL = 30.0  # seconds
_narada_drain_task: asyncio.Task | None = None
_narada_drain_stop = asyncio.Event() if False else None  # placeholder


def _drain_narada_outbox_once() -> None:
    """One pass over every Narada account with a non-empty outbox.

    Imports are inside the function so the module loads even if the
    Narada package is partially uninitialised in a future state.
    """
    try:
        from src.narada.adapter import NaradaAdapter
        from src.narada.outbox import Outbox
        from src.narada_identity.keystore import default_keystore
    except Exception as exc:  # noqa: BLE001
        uvicorn_logger.error(f"Narada drain: import failed: {exc}")
        return
    data_dir = os.path.join(os.path.expanduser("~"), "." + APP_NAME.lower())
    outbox = Outbox(os.path.join(data_dir, "Narada"))
    keystore = default_keystore()
    for account_id in outbox.list_all_accounts():
        try:
            adapter = NaradaAdapter(account_id, outbox=outbox, keystore=keystore)
            adapter.drain_outbox(max_per_account=32)
        except Exception as exc:  # noqa: BLE001
            uvicorn_logger.error(f"Narada drain: account {account_id}: {exc}")


async def _narada_drain_loop() -> None:
    uvicorn_logger.info("Narada outbox drainer started")
    while True:
        try:
            _drain_narada_outbox_once()
        except Exception as exc:  # noqa: BLE001
            uvicorn_logger.error(f"Narada drain loop error: {exc}")
        await asyncio.sleep(_narada_DRAIN_INTERVAL)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _narada_drain_task
    try:
        client_handler.create_openmail_clients()
        # Initialise the Narada relay store with a per-process
        # master key. The key is derived from the node-identity
        # seed so a fresh process cannot read another process's
        # relay deposits even if they share a data directory.
        try:
            from src.routers import narada_relay_tasks
            from src.narada_security.hmac_io import load_key
            data_dir = Path(os.path.join(
                os.path.expanduser("~"), "." + APP_NAME.lower()
            ))
            narada_relay_tasks.configure(
                data_dir=data_dir,
                master_key=load_key(data_dir),
            )
        except Exception as exc:
            uvicorn_logger.error(f"Narada relay: init failed: {exc}")
        # Start the Narada outbox drainer.
        try:
            loop = asyncio.get_running_loop()
            _narada_drain_task = loop.create_task(_narada_drain_loop())
        except RuntimeError:
            # No running loop (e.g. in a test). Skip starting the task;
            # tests can call _drain_narada_outbox_once() directly.
            _narada_drain_task = None
        yield
    finally:
        if _narada_drain_task is not None:
            _narada_drain_task.cancel()
            try:
                await _narada_drain_task
            except (asyncio.CancelledError, Exception):
                pass
        client_handler.shutdown()

app = FastAPI(lifespan=lifespan)
app.include_router(account_tasks.router)
app.include_router(mailbox_tasks.router)
app.include_router(narada_identity_tasks.router)
app.include_router(narada_protocol_tasks.router)
try:
    from src.routers import narada_relay_tasks
    app.include_router(narada_relay_tasks.router)
except Exception:
    pass
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

def main():
    global WHITELISTED_IPS

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

    # Config Allowed IPs
    while True:
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
    uvicorn_info.write(f"URL=http://{host}:{str(port)}\nPID={pid}\n")

    # Start server
    uvicorn_logger.info("Starting server at http://%s:%d | PID: %s", host, port, pid)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
