from .api import get_api
import logging
import os
import uvicorn


try:
    # Load environment variables from
    # .env file if available
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.getcwd(), ".env"))
except:
    pass


def default_callable(m):
    logging.info(f"Subject: {m.subject}")
    logging.info(f"Sender: {m.sender}")
    logging.info(f"Content: {m.content}")


def main(
    host: str = os.environ.get("SERVER", None),
    user: str = os.environ.get("EMAIL", None),
    password: str = os.environ.get("PASS", None),
    callback: callable = default_callable,
    mailbox: str = "INBOX",
    log_level: str = "INFO",
    port: int = os.environ.get("PORT", 8080),
):
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO))
    api = get_api(host, user, password, callback, mailbox)
    uvicorn.run(api, host="0.0.0.0", port=port)


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
        "-a", "--app", default="__main__:default_callable",
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
    parser.add_argument("--port", default=8080, type=int, help='Port number')
    args = parser.parse_args()

    main(
        host=args.host,
        user=args.user,
        password=args.pwd,
        callback=import_from_string(args.app),
        mailbox=args.mailbox,
        log_level=args.log_level,
        port=args.port,
    )
