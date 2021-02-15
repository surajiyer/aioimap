from .message import Message
from aioimaplib import aioimaplib
import asyncio
from asyncio import CancelledError, TimeoutError
import logging
import signal
# import ssl
import threading
import traceback
from typing import Any, Callable


HANDLED_SIGNALS = (
    signal.SIGINT,  # Unix signal 2. Sent by Ctrl+C.
    signal.SIGTERM,  # Unix signal 15. Sent by `kill <pid>`.
)
RECEIVER_STOPPED = "RECEIVER_STOPPED"


class Receiver(object):

    def __init__(self):
        self.imap_client_lock = asyncio.Lock()
        self.should_exit = asyncio.Event()
        self.exit_event = asyncio.Event()

    async def run(
        self,
        host: str,
        user: str,
        password: str,
        callback: Callable[[Message], Any],
        mailbox: str = "INBOX",
        install_signal_handlers: bool = True,
    ):
        """
        Start running the main receiver loop.
        """
        # create the imap client
        self.imap_client = aioimaplib.IMAP4_SSL(host=host)

        # callback for when connection is lost
        def conn_lost_cb(exc):
            loop = self.imap_client.protocol.loop
            loop.create_task(self.reconnect())
        self.imap_client.protocol.conn_lost_cb = conn_lost_cb

        # signal handlers
        if install_signal_handlers:
            logging.debug("Receiver:run: Installing signal handlers")
            self.install_signal_handlers()

        logging.debug("Receiver:run: Clear exit and should_exit events")
        self.exit_event.clear()
        self.should_exit.clear()

        self._task_wfnm = None

        while not self.should_exit.is_set():
            if await self.login(user, password):
                # start waiting for new messages
                try:
                    self._task_wfnm = asyncio.create_task(
                        self.wait_for_new_message(callback, mailbox))
                    await self._task_wfnm

                except Exception as e:
                    if isinstance(e, CancelledError):
                        logging.debug("Receiver:run: wait_for_new_message task cancelled")
                    else:
                        logging.error(traceback.format_exc())
                        logging.debug("Receiver:run: Set should_exit event")
                        self.should_exit.set()

                # send a receiver stopped
                # message to the callback
                logging.info("Receiver:run: Called callback with RECEIVER_STOPPED message")
                try:
                    callback(RECEIVER_STOPPED)
                except:
                    logging.error(traceback.format_exc())

                # logout
                try:
                    await self.logout()
                except:
                    logging.error(traceback.format_exc())
                    logging.debug("Receiver:run: Set should_exit event")
                    self.should_exit.set()

            if self.should_exit.is_set():
                logging.info("Receiver:run: Graceful shutdown")
            else:
                logging.info("Receiver:run: Retrying")

        logging.debug("Receiver:run: Set exit event")
        self.exit_event.set()

    async def login(self, user: str, password: str):
        """
        Login to the IMAP server.
        """
        try:
            logging.debug("Receiver:login: Waiting for imap client lock")
            async with self.imap_client_lock:
                logging.debug("Receiver:login: Obtained imap client lock")

                await self.imap_client.wait_hello_from_server()
                response = await self.imap_client.login(user, password)

            if response.result != "OK":
                raise RuntimeError("Login failed.")
            logging.info("Receiver:login: Logged in as {}".format(user))

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

        logging.debug("Receiver:change_mailbox: Waiting for imap client lock")
        async with self.imap_client_lock:
            logging.debug("Receiver:change_mailbox: Obtained imap client lock")

            response = await self.imap_client.select(mailbox=mailbox)

        if response.result != "OK":
            raise RuntimeError(
                f"Selecting mailbox '{mailbox}' failed with status '{response.result}'.")

        logging.info(f"Receiver:change_mailbox: Selected mailbox '{mailbox}'")
        self.current_mailbox = mailbox

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
            logging.info(f"Receiver:search_unseen: Number of unseen messages: {len(unseen_ids)}")
        else:
            logging.error(f"Receiver:search_unseen: Search for unseen messages completed with status '{status}'")
        return unseen_ids

    async def wait_for_new_message(
        self, callback: Callable[[Message], Any], mailbox: str = "INBOX",
    ):
        """
        Receiver infinite loop waiting for new messages.
        """
        # select the mailbox
        await self.change_mailbox(mailbox)

        # if new messages are available, fetch
        # them and let the callback handle it
        for id in await self.search_unseen():
            response = await self.imap_client.fetch(
                str(id), "(RFC822)")
            if len(response.lines) > 1:
                try:
                    callback(Message(response.lines[1]))
                except:
                    logging.error(traceback.format_exc())

        while True:
            logging.debug("Receiver:wait_for_new_message: Waiting for imap client lock")

            async with self.imap_client_lock:
                logging.debug("Receiver:wait_for_new_message: Obtained imap client lock")

                # start IDLE waiting
                # idle queue must be empty, otherwise we get race
                # conditions between idle command status update
                # and unsolicited server messages
                if (
                    (not self.imap_client.has_pending_idle())
                    and self.imap_client.protocol.idle_queue.empty()
                ):
                    logging.debug("Receiver:wait_for_new_message: Start IDLE waiting")
                    self._idle = await self.imap_client.idle_start()

                # wait for status update
                msg = await self.imap_client.wait_server_push()
                logging.debug(f"Receiver:wait_for_new_message: Received IDLE message: {msg}")

                # send IDLE done to server; this has to happen
                # before search or fetch or any other command
                # for some reason.
                # https://tools.ietf.org/html/rfc2177
                if self.imap_client.has_pending_idle():
                    logging.debug("Receiver:wait_for_new_message: Send IDLE done")
                    self.imap_client.idle_done()
                    await asyncio.wait_for(self._idle, 10)

                # https://tools.ietf.org/html/rfc3501#section-7.3.1
                # EXISTS response occurs when size of the mailbox changes
                if isinstance(msg, list) and any("EXISTS" in m for m in msg):
                    logging.debug("Receiver:wait_for_new_message: Mailbox size changed")

                    # if new messages are available, fetch
                    # them and let the callback handle it
                    for id in await self.search_unseen():
                        response = await self.imap_client.fetch(
                            str(id), "(RFC822)")
                        if len(response.lines) > 1:
                            try:
                                callback(Message(response.lines[1]))
                            except:
                                logging.error(traceback.format_exc())

            logging.debug("Receiver:wait_for_new_message: Loop complete")

    async def logout(self):
        """
        Logout from the IMAP server.
        """
        valid_states = aioimaplib.Commands.get('LOGOUT').valid_states

        logging.debug("Receiver:logout: Waiting for lock")
        async with self.imap_client_lock:
            logging.debug("Receiver:logout: Obtained lock")

            if self.imap_client.protocol.state in valid_states:
                if self.imap_client.has_pending_idle():
                    # send IDLE done message to server
                    logging.debug("Receiver:logout: Send IDLE done")
                    self.imap_client.idle_done()

                    try:
                        if hasattr(self, '_idle') and self._idle is not None:
                            await asyncio.wait_for(self._idle, 10)
                    except TimeoutError:
                        logging.error(traceback.format_exc())

                try:
                    await self.imap_client.logout()
                    logging.info("Receiver:logout: Logged out")
                except TimeoutError:
                    logging.error(traceback.format_exc())

            else:
                logging.debug(f"Receiver:logout: Invalid state '{self.imap_client.protocol.state}'")

    def install_signal_handlers(self):
        """
        Install signal handlers to shut down
        the receiver main loop when SIGINT / SIGTERM
        signals are received.
        """
        if threading.current_thread() is not threading.main_thread():
            # Signals can only be listened to from the main thread.
            return

        loop = asyncio.get_running_loop()

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
        if not self.should_exit.is_set():
            logging.debug("Receiver:handle_exit: Set should_exit event")
            self.should_exit.set()

            # cancel the wait_for_new_message task
            if hasattr(self, '_task_wfnm') and self._task_wfnm is not None:
                self._task_wfnm.cancel()
                self._task_wfnm = None

    async def reconnect(self):
        # cancel the wait_for_new_message task
        if hasattr(self, '_task_wfnm') and self._task_wfnm is not None:
            logging.debug("Receiver:reconnect: Cancel wait_for_new_message task")
            self._task_wfnm.cancel()
            self._task_wfnm = None

            # give some time for the consequential actions
            # of cancelling the task to run
            logging.debug("Receiver:reconnect: Sleep")
            await asyncio.sleep(1)

        if not self.should_exit.is_set():
            # try reconnecting to the server every 5 seconds
            logging.debug("Receiver:reconnect: Waiting for lock")
            async with self.imap_client_lock:
                logging.debug("Receiver:reconnect: Obtained lock")

                while True:
                    try:
                        conn_lost_cb = self.imap_client.protocol.conn_lost_cb
                        self.imap_client = aioimaplib.IMAP4_SSL(
                            host=self.imap_client.host,
                            port=self.imap_client.port,
                            timeout=self.imap_client.timeout)
                        self.imap_client.protocol.conn_lost_cb = conn_lost_cb

                        logging.info("Receiver:reconnect: Connection recreated")
                        break

                    except OSError:
                        logging.error(traceback.format_exc())
                        await asyncio.sleep(5)

                    except:
                        logging.error(traceback.format_exc())
                        self.should_exit.set()
                        break
