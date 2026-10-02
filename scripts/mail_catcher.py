"""Receive real SMTP messages locally so notifications can be demonstrated without a
company mail server.

    python scripts/mail_catcher.py
    python scripts/mail_catcher.py --port 1025 --output .verification/mail-catcher

Point the application at it with these values, then run `manage.py send_notifications`:

    EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
    EMAIL_HOST=127.0.0.1
    EMAIL_PORT=1025
    EMAIL_USE_TLS=False

Each message is written to the output directory as a .eml file that opens in any mail
client. This is a development aid only: it does not authenticate senders and must never
be exposed beyond the local machine.
"""
import argparse
import email
import re
import socketserver
from email import policy
from pathlib import Path

MAX_MESSAGE_BYTES = 10 * 1024 * 1024


class MailCatcherHandler(socketserver.StreamRequestHandler):
    def reply(self, text):
        self.wfile.write((text + '\r\n').encode('ascii', 'replace'))
        self.wfile.flush()

    def handle(self):
        self.reply('220 mail-catcher ready')
        sender = ''
        recipients = []
        while True:
            line = self.rfile.readline(MAX_MESSAGE_BYTES)
            if not line:
                return
            command = line.decode('utf-8', 'replace').strip()
            verb = command.split(' ', 1)[0].upper()
            if verb in ('EHLO', 'HELO'):
                self.reply('250-mail-catcher')
                self.reply('250 SIZE %d' % MAX_MESSAGE_BYTES)
            elif verb == 'MAIL':
                sender = command.partition(':')[2].strip()
                recipients = []
                self.reply('250 OK')
            elif verb == 'RCPT':
                recipients.append(command.partition(':')[2].strip())
                self.reply('250 OK')
            elif verb == 'DATA':
                self.reply('354 End data with <CR><LF>.<CR><LF>')
                self.server.save(self.read_message(), sender, recipients)
                self.reply('250 OK: queued locally')
            elif verb == 'RSET':
                sender, recipients = '', []
                self.reply('250 OK')
            elif verb == 'NOOP':
                self.reply('250 OK')
            elif verb == 'QUIT':
                self.reply('221 Bye')
                return
            else:
                self.reply('502 Command not implemented')

    def read_message(self):
        lines = []
        while True:
            line = self.rfile.readline(MAX_MESSAGE_BYTES)
            if not line or line in (b'.\r\n', b'.\n'):
                break
            # SMTP dot-stuffing: a leading ".." restores a single ".".
            if line.startswith(b'..'):
                line = line[1:]
            lines.append(line)
        return b''.join(lines)


class MailCatcher(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address, output):
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.count = 0
        super().__init__(address, MailCatcherHandler)

    def save(self, raw, sender, recipients):
        self.count += 1
        message = email.message_from_bytes(raw, policy=policy.default)
        subject = str(message.get('subject') or '(no subject)')
        slug = re.sub(r'[^A-Za-z0-9]+', '-', subject).strip('-')[:60] or 'message'
        path = self.output / f'{self.count:03d}-{slug}.eml'
        path.write_bytes(raw)
        print(f'[{self.count:03d}] {sender} -> {", ".join(recipients)}')
        print(f'      Subject: {subject}')
        print(f'      Saved:   {path}')
        print(f'      Preview: {message.get_body(preferencelist=("plain",)).get_content().strip().splitlines()[0]}')


def main():
    parser = argparse.ArgumentParser(description='Receive SMTP mail locally for demonstrations.')
    parser.add_argument('--host', default='127.0.0.1', help='Interface to bind (default: 127.0.0.1)')
    parser.add_argument('--port', type=int, default=1025, help='Port to bind (default: 1025)')
    parser.add_argument('--output', default='.verification/mail-catcher', help='Directory for captured .eml files')
    arguments = parser.parse_args()

    with MailCatcher((arguments.host, arguments.port), arguments.output) as server:
        print(f'Listening on {arguments.host}:{arguments.port}')
        print(f'Writing messages to {server.output.resolve()}')
        print('Press Ctrl+C to stop.')
        server.serve_forever()


if __name__ == '__main__':
    main()
