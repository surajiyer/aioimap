from .message import Message
import asyncio
from aioimaplib import aioimaplib
import concurrent.futures
import logging
import signal
import threading
import traceback
from typing import Any, Callable


HANDLED_SIGNALS = (
    signal.SIGINT,  # Unix signal 2. Sent by Ctrl+C.
    signal.SIGTERM,  # Unix signal 15. Sent by `kill <pid>`.
)


class Receiver(object):

    def __init__(self, host: str, timeout: int = 20):
        if not (
            isinstance(timeout, int)
            and timeout > -1
        ):
            raise ValueError(
                "`action_timeout` must be non-negative integer.")
        self.imap_client_lock = asyncio.Lock()
        self.imap_client = aioimaplib.IMAP4_SSL(
            host=host, timeout=timeout)
        self.started = False
        self.should_exit = False
        self.startup_event = asyncio.Event()
        self.shutdown_event = asyncio.Event()

    async def run(
        self,
        user: str,
        password: str,
        callback: Callable[[Message], Any],
        mailbox: str = "INBOX",
        install_signal_handlers: bool = True,
    ):
        if install_signal_handlers:
            self.install_signal_handlers()
        if await self.login(user, password):
            await self.main_loop(callback, mailbox)
            self.logout()
        self.shutdown_event.set()
        self.started = False

    async def login(self, user: str, password: str):
        try:
            async with self.imap_client_lock:
                await self.imap_client.wait_hello_from_server()
                response = await self.imap_client.login(user, password)
            if response.result != "OK":
                raise RuntimeError("Login failed.")
            logging.info("Logged in as {}".format(user))
        except:
            logging.error(traceback.format_exc())
            return False
        return True

    async def change_mailbox(self, mailbox: str):
        if not (
            isinstance(mailbox, str)
            and len(mailbox) > 0
        ):
            raise ValueError(
                "Invalid input. `mailbox` must"
                " be a non-empty string.")

        # add double-quotes around mailbox name if it contains
        # spaces
        mailbox = f'"{mailbox}"' if " " in mailbox else mailbox

        async with self.imap_client_lock:
            response = await self.imap_client.select(mailbox=mailbox)
        if response.result != "OK":
            raise RuntimeError(
                f"Selecting mailbox '{mailbox}' failed!")
        return response

    async def main_loop(
        self, callback: Callable[[Message], Any], mailbox: str = "INBOX",
    ):
        try:
            # select the mailbox
            response = await self.change_mailbox(mailbox)

            # get ID of latest message
            id = aioimaplib.extract_exists(response)

            # start waiting for new messages
            self.started = True
            self.startup_event.set()
            while not self.should_exit:
                id = await self.wait_for_new_message(callback, id)
        except:
            logging.error(traceback.format_exc())
            logging.info("Graceful shutdown")

    async def wait_for_new_message(
        self, callback: Callable[[Message], Any], id: str = None,
    ):
        async with self.imap_client_lock:
            # if new message is available, then fetch
            # it and let the callback handle it
            if id:
                response = await self.imap_client.fetch(
                    str(id), "(RFC822)")
                if len(response.lines) > 1:
                    callback(Message(response.lines[1]))

            # wait for new messages
            # the timeout here must be shorter than the
            # imap client timeout
            await self.imap_client.idle_start(
                timeout=min(5, self.imap_client.timeout))
            try:
                msg = await self.imap_client.wait_server_push(
                    timeout=self.imap_client.timeout)
            except concurrent.futures.TimeoutError:
                msg = []

            # get message ID
            id = next((
                m.split()[0] for m in msg
                if " EXISTS" in m), None)

            # Send IDLE done message to server
            if self.imap_client.has_pending_idle():
                self.imap_client.idle_done()

        return id

    def logout(self):
        try:
            if self.imap_client.has_pending_idle():
                # send IDLE done message to server
                self.imap_client.idle_done()
            self.imap_client.logout()
            logging.info("Logged out")
        except:
            logging.error(traceback.format_exc())
            return False
        return True

    def install_signal_handlers(self):
        if threading.current_thread() is not threading.main_thread():
            # Signals can only be listened to from the main thread.
            return

        loop = asyncio.get_event_loop()

        try:
            for sig in HANDLED_SIGNALS:
                loop.add_signal_handler(sig, self.handle_exit, sig, None)
        except NotImplementedError:
            # Windows
            for sig in HANDLED_SIGNALS:
                signal.signal(sig, self.handle_exit)

    def handle_exit(self, sig, frame):
        if not self.should_exit:
            self.should_exit = True
