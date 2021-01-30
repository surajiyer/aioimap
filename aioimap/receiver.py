from .message import Message
import asyncio
from aioimaplib import aioimaplib
import concurrent.futures
import logging
import traceback


class Receiver(object):

    def __init__(self, host: str, idle_timeout: int = 20):
        if not (
            isinstance(idle_timeout, int)
            and idle_timeout > -1
        ):
            raise ValueError(
                "`idle_timeout` must be non-negative integer.")
        self.idle_timeout = idle_timeout
        self.imap_client_lock = asyncio.Lock()
        self.imap_client = aioimaplib.IMAP4_SSL(
            host=host, timeout=10)

    async def login(self, user: str, password: str):
        try:
            await asyncio.wait_for(
                self.imap_client.wait_hello_from_server(), 5)
            await self.imap_client.login(user, password)
            logging.info("Logged in as {}".format(user))
        except:
            logging.error(traceback.format_exc())
            return False
        return True

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

    async def wait_for_new_message(
        self, callback: callable, mailbox = "INBOX"):
        try:
            response = await asyncio.wait_for(
                self.imap_client.select(mailbox=mailbox), 5)
            id = aioimaplib.extract_exists(response)
            while True:
                async with self.imap_client_lock:
                    # if new message is available, then fetch
                    # it and let the callback handle it
                    if id:
                        response = await self.imap_client.fetch(
                            str(id), "(RFC822)")
                        if len(response.lines) > 1:
                            callback(Message(response.lines[1]))

                    # wait for new messages
                    await self.imap_client.idle_start(self.idle_timeout)
                    try:
                        msg = await self.imap_client.wait_server_push(
                            timeout=self.idle_timeout)
                    except concurrent.futures.TimeoutError:
                        msg = []

                    # get message ID
                    id = next((
                        m.split()[0] for m in msg
                        if " EXISTS" in m), None)

                    # Send IDLE done message to server
                    self.imap_client.idle_done()
        except:
            logging.error(traceback.format_exc())
            logging.info("Graceful shutdown")
        finally:
            self.logout()
