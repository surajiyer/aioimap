from .receiver import Receiver
import asyncio
from fastapi import FastAPI, HTTPException
import logging
import os
import uvicorn


try:
    # Load environment variables from
    # .env file if available
    from dotenv import load_dotenv
    load_dotenv()
except:
    pass


def default_callable(m):
    logging.info(f"Subject: {m.subject}")
    logging.info(f"Sender: {m.sender}")


def main(
    host: str = os.environ.get("SERVER", None),
    user: str = os.environ.get("EMAIL", None),
    password: str = os.environ.get("PASS", None),
    callback: callable = default_callable,
    mailbox: str = "INBOX",
    log_level: str = "INFO",
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
    if not isinstance(callback, callable):
        raise ValueError(
            "`callback` must be a callable object."
            f" Found type {type(callback)}")

    api = FastAPI()
    receiver = None
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO))

    @api.on_event("startup")
    async def on_startup():
        nonlocal receiver
        receiver = Receiver(host)
        asyncio.ensure_future(
            receiver.run(
                user,
                password,
                callback=callback,
                mailbox=mailbox,
                install_signal_handlers=False))


    @api.on_event("shutdown")
    async def on_shutdown():
        try:
            receiver.handle_exit(None, None)
            await receiver.shutdown_event.wait()
        except:
            import traceback
            logging.error(traceback.format_exc())


    @api.get("/")
    def read_root():
        return {"message": "Welcome from the API."}


    @api.get("/change-mailbox")
    async def change_mailbox(mailbox: str):
        if not (
            isinstance(mailbox, str)
            and len(mailbox) > 0
        ):
            raise HTTPException(
                status_code=422, detail="Invalid input given.")

        async with receiver.imap_client_lock:
            if (
                hasattr(receiver, "imap_client")
                and receiver.imap_client is not None
            ):
                try:
                    await asyncio.wait_for(
                        receiver.imap_client.select(mailbox=mailbox), 5)
                    app.mailbox = mailbox
                    return f"Switched to mailbox '{app.mailbox}'."
                except:
                    raise HTTPException(
                        status_code=500,
                        detail="Failure. Could not switch to mailbox"
                        f"'{mailbox}'.")
            else:
                raise HTTPException(
                    status_code=500,
                    detail="IMAP client is not available.")


    # start the server
    uvicorn.run(api, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    import argparse
    from uvicorn.importer import import_from_string

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--host", default=os.environ.get("SERVER", None),
        help=(
            'Email server host URL. E.g., for outlook.com the'
            ' host="imap-mail.outlook.com"'))
    parser.add_argument(
        "-u", "--user", default=os.environ.get("EMAIL", None),
        help='Email ID / username')
    parser.add_argument(
        "-p", "--pwd", default=os.environ.get("PASS", None),
        help='Email ID password')
    parser.add_argument(
        "-a", "--app", default="main:default_callable",
        help=(
            '"app" must be a string in format "<module>:<attribute>"'
            ' where attribute must be a callable. This will be used'
            ' as the callback function when new e-mails are received.'))
    parser.add_argument(
        "-m", "--mailbox", default="INBOX",
        help="Name of the mailbox to monitor, default='Inbox'")
    parser.add_argument(
        "-l", "--log_level", default="INFO", help='Log level',
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"])
    args = parser.parse_args()

    main(
        host=args.host,
        user=args.user,
        password=args.pwd,
        callback=import_from_string(args.app),
        mailbox=args.mailbox,
        log_level=args.log_level,
    )
