from .message import Message
# import asyncio
from aioimaplib import aioimaplib
import concurrent.futures
import logging


class Receiver(object):
    idle = None
    IDLE_TIMEOUT = 20

    async def wait_for_new_message(
        self,
        host: str,
        user: str,
        password: str,
        callback: callable,
        mailbox = "INBOX"
    ):
        self.imap_client = aioimaplib.IMAP4_SSL(host=host, timeout=10)
        await self.imap_client.wait_hello_from_server()
        await self.imap_client.login(user, password)
        response = await self.imap_client.select(mailbox=mailbox)
        id = aioimaplib.extract_exists(response)
        logging.info("Logged in as {}".format(user))

        try:
            while True:
                if id:
                    # logging.info(f"ID: {id}")
                    response = await self.imap_client.fetch(str(id), "(RFC822)")
                    if len(response.lines) > 1:
                        callback(Message(response.lines[1]))

                self.idle = await self.imap_client.idle_start(timeout=self.IDLE_TIMEOUT)
                try:
                    msg = await self.imap_client.wait_server_push(timeout=self.IDLE_TIMEOUT)
                except concurrent.futures.TimeoutError:
                    msg = []
                # logging.info(msg)
                id = next((m.split()[0] for m in msg if " EXISTS" in m), None)
                # response = await self.imap_client.select()

                self.imap_client.idle_done()
                # await asyncio.wait_for(self.idle, 30)
        except:
            import traceback
            logging.error(traceback.format_exc())
        finally:
            await self.close()

    async def close(self):
        logging.info("Graceful shutdown")
        if self.imap_client.has_pending_idle():
            self.imap_client.idle_done()
            # await asyncio.wait_for(self.idle, 30)
        self.imap_client.logout()
        logging.info("Logged out")
