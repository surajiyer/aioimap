import email
from email.header import decode_header


class Message(object):

    def __init__(self, msg):
        self.msg = email.message_from_bytes(msg)

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

    @property
    def content(self):
        # https://humberto.io/blog/sending-and-receiving-emails-with-python/
        if self.msg.is_multipart():
            mail_content = ''

            # on multipart we have the text message and
            # another things like annex, and html version
            # of the message, in that case we loop through
            # the email payload
            mail_content = " ".join(
                part.get_payload()
                for part in self.msg.get_payload()
                if part.get_content_type() == 'text/plain')
        else:
            # if the message isn't multipart, just extract it
            mail_content = self.msg.get_payload()

        return mail_content
