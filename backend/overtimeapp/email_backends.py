"""Alternative email backends for environments without SMTP credentials.

`OutlookComEmailBackend` hands each message to the Outlook desktop client that is
already signed in on this machine, so no mailbox password is used. Select it with:

    EMAIL_BACKEND=overtimeapp.email_backends.OutlookComEmailBackend

It requires Windows, the Outlook desktop client, pywin32, and a signed-in profile.
Outlook applies its own programmatic-access policy: company policy may prompt for
confirmation or block sending outright, and the machine must stay signed in. This suits
a local prototype or a Windows-hosted instance; the Linux deployment needs SMTP or an
API-based sender instead.
"""
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.base import BaseEmailBackend

# Outlook's olMailItem constant.
OL_MAIL_ITEM = 0


class OutlookComEmailBackend(BaseEmailBackend):
    """Send through the signed-in Outlook desktop client instead of SMTP."""

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        try:
            import pythoncom
            import win32com.client
        except ImportError as exc:
            raise ImproperlyConfigured(
                'The Outlook backend requires pywin32 and the Outlook desktop client on Windows.'
            ) from exc

        # COM must be initialized on the thread that uses it; Django serves requests on
        # several threads, and the delivery command may run on another one.
        pythoncom.CoInitialize()
        try:
            application = win32com.client.Dispatch('Outlook.Application')
            sent = 0
            for message in email_messages:
                try:
                    self._send(application, message)
                    sent += 1
                except Exception:
                    if not self.fail_silently:
                        raise
            return sent
        finally:
            pythoncom.CoUninitialize()

    @staticmethod
    def _send(application, message):
        item = application.CreateItem(OL_MAIL_ITEM)
        item.To = '; '.join(message.to)
        if message.cc:
            item.CC = '; '.join(message.cc)
        if message.bcc:
            item.BCC = '; '.join(message.bcc)
        item.Subject = message.subject or ''
        # Only EmailMultiAlternatives carries alternatives, stored as (content, mimetype).
        html = next((content for content, mimetype in getattr(message, 'alternatives', ()) if mimetype == 'text/html'), None)
        if html:
            item.HTMLBody = html
        else:
            item.Body = message.body
        item.Send()
