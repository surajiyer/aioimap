from .receiver import Receiver
import asyncio
from fastapi import FastAPI, HTTPException
import logging


def translate_py_exc_to_http(e):
    t = type(e).__name__
    if t == "ValueError":
        return 422
    else:
        return 500


def get_api(
    host: str,
    user: str,
    password: str,
    callback: callable,
    mailbox: str = "INBOX",
):
    if not (
        isinstance(host, str)
        and isinstance(user, str)
        and isinstance(password, str)
    ):
        raise ValueError(
            "`host`, `user`, `password` must be string type."
            f" Found {(type(host), type(user), type(password))}"
            " respectively.")
    if not callable(callback):
        raise ValueError(
            "`callback` must be a callable object."
            f" Found type {type(callback)}")

    api = FastAPI()
    receiver = None

    @api.on_event("startup")
    async def on_startup():
        nonlocal receiver
        receiver = Receiver()
        asyncio.ensure_future(
            receiver.run(
                host,
                user,
                password,
                callback=callback,
                mailbox=mailbox,
                install_signal_handlers=False))

    @api.on_event("shutdown")
    async def on_shutdown():
        try:
            if not receiver.exit_event.is_set():
                receiver.handle_exit(None, None)
                await receiver.exit_event.wait()
        except:
            import traceback
            logging.error(traceback.format_exc())

    @api.get("/")
    def read_root():
        try:
            if receiver.exit_event.is_set():
                return {"message": "Receiver not running."}
            else:
                return {"message": "Receiver running."}

        except:
            import traceback
            logging.error(traceback.format_exc())

    @api.get("/change-mailbox")
    async def change_mailbox(mailbox: str):
        try:
            if (
                hasattr(receiver, "imap_client")
                and receiver.imap_client is not None
                and not receiver.exit_event.is_set()
                and not receiver.should_exit.is_set()
            ):
                await receiver.change_mailbox(mailbox)

            else:
                raise RuntimeError(
                    "IMAP client is not available or is"
                    " not running.")

        except Exception as e:
            raise HTTPException(
                status_code=translate_py_exc_to_http(e),
                detail=e.message if hasattr(e, "message") else str(e))

        return {"message": "OK"}

    return api
