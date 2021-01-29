import email
from email.header import decode_header


class Message(object):

    def __init__(self, msg):
        msg = email.message_from_bytes(msg)
        self.msg = msg

    @property
    def subject(self):
        """Get email subject"""
        subject, encoding = decode_header(self.msg["Subject"])[0]
        if isinstance(subject, bytes):
            encoding = 'utf-8' if encoding is None else encoding
            subject = subject.decode(encoding)
        return subject

    @property
    def sender(self):
        """Get sender"""
        sender, encoding = decode_header(self.msg["From"])[0]
        if isinstance(sender, bytes):
            encoding = 'utf-8' if encoding is None else encoding
            sender = sender.decode(encoding)
        return sender
