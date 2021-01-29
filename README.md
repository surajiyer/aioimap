# aioimap: Asyncio IMAP client
Receive e-mails from an IMAP server asynchronously and trigger a callback with the message.

## Dependencies
aioimap requires:
* Python (>=3.7)
* aioimaplib (>=0.7.18)

## Usage

```
from aioimap import Receiver
import asyncio
import logging
import os


# initialize logging
log_configs = {
    "level"     : logging.INFO,
    "format"    : '%(asctime)s %(filename)s:%(lineno)d %(levelname)s  %(message)s',
    "datefmt"   : '%Y-%m-%d %X'
}
logging.basicConfig(**log_configs)


def app(msg):
    logging.info(f"Subject: {msg.subject}")
    logging.info(f"Sender: {msg.sender}")


if __name__ == "__main__":
    receiver = Receiver()
    loop = asyncio.get_event_loop()

    try:
        # for outlook.com
        # imap_server = "imap-mail.outlook.com"
        # imap_port = 993
        # smtp_server = "smtp-mail.outlook.com"
        # smtp_port = 587
        asyncio.run(receiver.wait_for_new_message(
            host=os.environ['SERVER'],
            user=os.environ['EMAIL'],
            password=os.environ['PASS'],
            callback=app,
            mailbox='INBOX'))
    except KeyboardInterrupt:
        pass
    loop.close()
```