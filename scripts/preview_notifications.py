"""Generate fictional email previews without opening the local database or sending mail.

From backend: venv/Scripts/python.exe ../scripts/preview_notifications.py
Outputs: .verification/stage1/index.html, five HTML/text/MIME previews, result.json.
"""
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from decimal import Decimal
from html import escape
from io import StringIO
from pathlib import Path


def main():
    project = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(project / 'backend'))
    os.environ['DJANGO_SETTINGS_MODULE'] = 'core.test_settings'
    os.environ['TEST_DB_ENGINE'] = 'sqlite3'

    import django
    from django.conf import settings

    # Force isolation before app loading, regardless of any local .env settings.
    settings.DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
    settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
    settings.DEFAULT_FROM_EMAIL = 'Mubea Demo <notifications@example.com>'
    settings.PUBLIC_BASE_URL = 'https://overtime.example.com'
    settings.NOTIFICATIONS_DELIVERY_ENABLED = True
    settings.NOTIFICATIONS_TEST_MODE = True
    settings.NOTIFICATIONS_REDIRECT_TO = ['demo@example.com']
    django.setup()

    from django.contrib.auth.models import User
    from django.core import mail
    from django.core.management import call_command
    from overtimeapp.emails import OvertimeEmailService
    from overtimeapp.models import EmailLog, OvertimeRequest, UserProfile

    call_command('migrate', verbosity=0, interactive=False)
    mail.get_connection()
    mail.outbox.clear()

    def person(username, email, first_name, last_name, role=None):
        user = User.objects.create_user(username, email, first_name=first_name, last_name=last_name)
        if role:
            UserProfile.objects.create(user=user, role=role,
                                       department='logistics' if role == 'dept_manager' else None)
        return user

    requester = person('demo-department', 'department@example.com', 'Alex', 'Example', 'dept_manager')
    head = person('demo-approver', 'approval@example.com', 'Jordan', 'Example', 'head_manager')
    hr = person('demo-hr', 'hr@example.com', 'Sam', 'Example', 'hr_manager')
    employees = [person('demo-employee-one', 'employee-one@example.com', 'Nina', 'Example'),
                 person('demo-employee-two', 'employee-two@example.com', 'Omar', 'Example')]
    timestamp = datetime(2026, 10, 5, 9, 0, tzinfo=timezone.utc)

    def request(number, **changes):
        item = OvertimeRequest.objects.create(
            request_id=f'OT-DEMO-{number:03d}', requester=requester, department='logistics',
            title='Warehouse inventory count',
            description='Count warehouse stock and reconcile bin records.\nTwo employees will complete the count.',
            reason='Month-end inventory preparation requires additional time after the normal shift.',
            start_date='2026-10-08', end_date='2026-10-09', total_hours=Decimal('12.50'),
            **changes,
        )
        OvertimeRequest.objects.filter(pk=item.pk).update(created_at=timestamp)
        item.refresh_from_db()
        return item

    submitted = request(1)
    approved = request(2, status='approved', approved_by=head, approval_date=timestamp)
    rejected = request(3, status='rejected', rejection_date=timestamp,
                       rejection_reason='Please revise the employee-hours estimate.\nA smaller allocation is available this week.')
    OvertimeEmailService.send_request_submitted_notification(submitted)
    OvertimeEmailService.send_approval_notification(approved)
    OvertimeEmailService.send_rejection_notification(rejected)
    OvertimeEmailService.send_assignment_notification(approved, employees)
    logs = list(EmailLog.objects.order_by('next_attempt_at', 'pk'))
    command_output = StringIO()
    call_command('send_notifications', limit=10, stdout=command_output)

    if len(mail.outbox) != 5 or EmailLog.objects.filter(status='sent').count() != 5:
        raise RuntimeError('Preview delivery did not complete all five notifications.')
    output = project / '.verification' / 'stage1'
    output.mkdir(parents=True, exist_ok=True)
    previews = []
    for log, message in zip(logs, mail.outbox):
        if message.to != ['demo@example.com'] or not message.subject.startswith('[TEST] '):
            raise RuntimeError('Preview recipient redirection or subject marker is missing.')
        if message.message().get_content_type() != 'multipart/alternative':
            raise RuntimeError('Preview is missing its HTML/text multipart alternatives.')
        name = {
            'request_submitted': 'submitted',
            'request_rejected': 'rejected',
            'assignment_ready': 'assignment',
        }.get(log.email_type)
        if log.email_type == 'request_approved':
            name = 'approved-hr' if log.recipient == hr.email else 'approved-requester'
        html_body = next(content for content, kind in message.alternatives if kind == 'text/html')
        (output / f'{name}.html').write_text(html_body, encoding='utf-8')
        (output / f'{name}.txt').write_text(message.body, encoding='utf-8')
        (output / f'{name}.eml').write_bytes(message.message().as_bytes(linesep='\r\n'))
        previews.append({'name': name, 'original_recipient': log.recipient,
                         'actual_recipient': message.to[0], 'subject': message.subject})

    rows = ''.join(
        f'<tr><td>{escape(preview["name"])}</td><td>{escape(preview["original_recipient"])}</td>'
        f'<td><a href="{preview["name"]}.html">HTML</a> · '
        f'<a href="{preview["name"]}.txt">Text</a> · <a href="{preview["name"]}.eml">EML</a></td></tr>'
        for preview in previews
    )
    (output / 'index.html').write_text(
        '<!DOCTYPE html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>Mubea notification previews</title><style>'
        'body{font-family:Arial,sans-serif;max-width:900px;margin:40px auto;padding:0 20px;color:#182635;}'
        'table{width:100%;border-collapse:collapse;}th,td{text-align:left;padding:12px;border-bottom:1px solid #ddd;}'
        'a{color:#003f6b;}</style><h1>Fictional notification previews</h1>'
        '<p>Generated with an in-memory database and local mail backend. No email left this machine. '
        'All five messages were redirected to demo@example.com.</p>'
        '<table><tr><th>Notification</th><th>Original fictional recipient</th><th>Preview</th></tr>'
        f'{rows}</table><p>Dashboard links use the fictional example.com domain. '
        'Open an EML file in Outlook to check rendering there.</p></html>', encoding='utf-8',
    )
    result = {
        'database': ':memory:', 'backend': settings.EMAIL_BACKEND,
        'test_mode': True, 'redirect_allowlist': ['demo@example.com'],
        'sent_locally': len(mail.outbox), 'external_delivery': False,
        'multipart_alternatives': True, 'previews': previews,
        'visual_review': {'status': 'not_run', 'agent_browser_available': bool(shutil.which('agent-browser')),
                          'outlook_rendering': 'not_verified'},
        'worker_output': command_output.getvalue().strip(),
    }
    (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(f'Generated {len(previews)} fictional multipart previews: {output / "index.html"}')


if __name__ == '__main__':
    main()
