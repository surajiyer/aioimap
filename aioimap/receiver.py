from .message import Message
import asyncio
from aioimaplib import aioimaplib
from concurrent.futures import TimeoutError
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

    def __init__(self, host: str):
        self.imap_client = aioimaplib.IMAP4_SSL(host=host)
        self.imap_client_lock = asyncio.Lock()
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
        """
        Start running the main receiver loop.
        """
        if install_signal_handlers:
            self.install_signal_handlers()
        if await self.login(user, password):
            try:
                await self.wait_for_new_message(callback, mailbox)
            except:
                logging.error(traceback.format_exc())
                logging.info("Graceful shutdown")
            self.logout()
        self.shutdown_event.set()
        self.started = False

    async def login(self, user: str, password: str):
        """
        Login to the IMAP server.
        """
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
        """
        Switch to another mailbox.
        """
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
        else:
            logging.info(f"Selected mailbox '{mailbox}'")
        return response

    async def search_unseen(self):
        """
        Get IDs of unseen messages in the current mailbox.
        URL: https://tools.ietf.org/html/rfc3501#section-6.4.4
        """
        unseen_ids = []
        status, response = await self.imap_client.search("(UNSEEN)", charset=None)
        if status == "OK":
            unseen_ids.extend(response[0].split())
            logging.info(f"Number of unseen messages: {len(unseen_ids)}")
        else:
            logging.error(f"Search for unseen messages completed with status: {status}")
        return unseen_ids

    async def wait_for_new_message(
        self, callback: Callable[[Message], Any], mailbox: str = "INBOX",
    ):
        """
        Receiver main loop.
        """
        # select the mailbox
        # response = await self.change_mailbox(mailbox)
        await self.change_mailbox(mailbox)

        # get the id of the latest message
        # id = aioimaplib.extract_exists(response)

        # start waiting for new messages
        self.started = True
        self.startup_event.set()

        # if new messages are available, fetch
        # them and let the callback handle it
        for id in await self.search_unseen():
            response = await self.imap_client.fetch(
                str(id), "(RFC822)")
            if len(response.lines) > 1:
                callback(Message(response.lines[1]))

        while not self.should_exit:
            async with self.imap_client_lock:
                # start IDLE waiting
                # idle queue must be empty, otherwise we get race
                # conditions between idle command status update
                # and unsolicited server messages
                if (
                    (not self.imap_client.has_pending_idle())
                    and self.imap_client.protocol.idle_queue.empty()
                ):
                    logging.debug("Start IDLE waiting")
                    idle = await self.imap_client.idle_start()

                try:
                    # wait for status update
                    msg = await self.imap_client.wait_server_push()
                    logging.debug(f"Received IDLE message: {msg}")

                    # send IDLE done to server; this has to happen
                    # before search or fetch or any other command
                    # for some reason.
                    # https://tools.ietf.org/html/rfc2177
                    if self.imap_client.has_pending_idle():
                        logging.debug("Send IDLE done")
                        self.imap_client.idle_done()
                        await asyncio.wait_for(idle, 10)
                except TimeoutError:
                    logging.error(traceback.format_exc())
                    msg = []

                # https://tools.ietf.org/html/rfc3501#section-7.3.1
                # EXISTS response occurs when size of the mailbox changes
                if isinstance(msg, list) and any("EXISTS" in m for m in msg):
                    logging.debug("Mailbox size changed")

                    # if new messages are available, fetch
                    # them and let the callback handle it
                    for id in await self.search_unseen():
                        response = await self.imap_client.fetch(
                            str(id), "(RFC822)")
                        if len(response.lines) > 1:
                            callback(Message(response.lines[1]))

                logging.debug("Loop complete")

    def logout(self):
        """
        Logout from the IMAP server.
        """
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
        """
        Install signal handlers to shut down
        the receiver main loop when SIGINT / SIGTERM
        signals are received.
        """
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
        """
        Handle exiting the receiver main loop.
        """
        if not self.should_exit:
            asyncio.ensure_future(self.imap_client.stop_wait_server_push())
            self.should_exit = True
