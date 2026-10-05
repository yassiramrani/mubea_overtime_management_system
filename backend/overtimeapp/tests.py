import os
import re
import sys
import types
from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch
from io import StringIO

from django.contrib.auth.models import User
from django.contrib.admin.sites import AdminSite
from django.core.cache import cache
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.mail.message import EmailMessage, EmailMultiAlternatives
from django.core.exceptions import ImproperlyConfigured
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, RequestFactory, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token
from .models import EmployeeAssignment, OvertimeRequest, SAPExport, UserProfile, AuditEvent, EmailLog, ExportBatch
from .admin import OvertimeRequestAdmin, WorkflowReadOnlyAdmin
from .views import selected_export
from .email_backends import OutlookComEmailBackend
from .management.commands import seed_users


@override_settings(SECURE_SSL_REDIRECT=False, EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class OvertimeWorkflowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.department_manager = self.create_user('dept', 'dept_manager', 'logistics')
        self.other_manager = self.create_user('other', 'dept_manager', 'quality')
        self.head_manager = self.create_user('head', 'head_manager')
        self.hr_manager = self.create_user('hr', 'hr_manager')
        self.employee = User.objects.create_user('employee', 'employee@example.com', 'password123')

    def create_user(self, username, role, department=None):
        user = User.objects.create_user(username, f'{username}@example.com', 'password123')
        UserProfile.objects.create(user=user, role=role, department=department)
        return user

    def request_payload(self):
        return {'department': 'logistics', 'title': 'Inventory count', 'description': 'Count stock.',
                'reason': 'Month end', 'start_date': '2026-09-10', 'end_date': '2026-09-10',
                'total_hours': Decimal('4.00'), 'hourly_rate': Decimal('25.00')}

    def make_request(self, **kwargs):
        return OvertimeRequest.objects.create(**({'requester': self.department_manager} | self.request_payload() | kwargs))

    def approve(self, item):
        self.client.force_authenticate(self.head_manager)
        response = self.client.patch(f'/api/requests/{item.pk}/approve/', {}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        item.refresh_from_db()

    def assign(self, item):
        self.client.force_authenticate(self.hr_manager)
        response = self.client.post('/api/assignments/', {'overtime_request': item.pk,
            'assigned_employees': [self.employee.pk], 'expected_version': item.version}, format='json')
        self.assertIn(response.status_code, [200, 201], response.data)
        item.refresh_from_db()
        return response

    def selection(self, item):
        return {'request_ids': [item.pk], 'versions': {str(item.pk): item.version}}

    def test_department_manager_can_submit_only_for_own_department(self):
        self.client.force_authenticate(self.department_manager)
        response = self.client.post('/api/requests/', self.request_payload(), format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['estimated_cost'], '100.00')
        self.assertEqual(EmailLog.objects.get(email_type='request_submitted').status, 'queued')
        self.assertEqual(AuditEvent.objects.get().action, 'submitted')
        response = self.client.post('/api/requests/', self.request_payload() | {'department': 'quality'}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_approval_fields_cannot_be_forged_on_creation(self):
        self.client.force_authenticate(self.department_manager)
        for field, value in [('status', 'approved'), ('approved_by', self.head_manager.pk), ('requester', self.other_manager.pk), ('estimated_cost', '0')]:
            with self.subTest(field=field):
                response = self.client.post('/api/requests/', self.request_payload() | {field: value}, format='json')
                self.assertEqual(response.status_code, 400)
        self.assertFalse(OvertimeRequest.objects.exists())

    def test_original_approval_bypass_and_alternate_mutations_are_closed(self):
        for state in ['pending', 'approved', 'rejected']:
            item = self.make_request(status=state)
            for actor in [self.department_manager, self.head_manager, self.hr_manager]:
                self.client.force_authenticate(actor)
                with self.subTest(state=state, actor=actor.username):
                    for method in ['patch', 'put']:
                        response = getattr(self.client, method)(f'/api/requests/{item.pk}/', {'status': 'approved', 'total_hours': '99.00', 'approved_by': actor.pk}, format='json')
                        self.assertEqual(response.status_code, 405)
                    self.assertEqual(self.client.delete(f'/api/requests/{item.pk}/').status_code, 405)
            item.refresh_from_db()
            self.assertEqual(item.status, state)
            self.assertEqual(item.total_hours, Decimal('4'))

    def test_head_manager_approval_and_hr_assignment_workflow(self):
        item = self.make_request()
        self.approve(item)
        self.assertEqual(item.approved_by, self.head_manager)
        self.assign(item)
        self.assertEqual(item.assignment.status, 'completed')
        self.client.force_authenticate(self.department_manager)
        result = self.client.get(f'/api/requests/{item.pk}/')
        self.assertEqual(result.data['assignment']['employees'][0]['id'], self.employee.pk)
        history = self.client.get(f'/api/requests/{item.pk}/history/')
        self.assertEqual([event['action'] for event in history.data], ['approved', 'employees_assigned'])

    def test_decisions_require_role_and_cannot_be_repeated(self):
        item = self.make_request()
        for actor in [self.department_manager, self.hr_manager, self.employee]:
            self.client.force_authenticate(actor)
            self.assertEqual(self.client.patch(f'/api/requests/{item.pk}/approve/', {}, format='json').status_code, 403)
        self.approve(item)
        self.assertEqual(self.client.patch(f'/api/requests/{item.pk}/approve/', {}, format='json').status_code, 409)
        self.assertEqual(self.client.patch(f'/api/requests/{item.pk}/reject/', {'rejection_reason': 'No'}, format='json').status_code, 409)
        self.assertEqual(AuditEvent.objects.filter(action='approved').count(), 1)

    def test_rejection_requires_reason_and_stays_visible(self):
        item = self.make_request()
        self.client.force_authenticate(self.head_manager)
        for payload in [{}, {'rejection_reason': '   '}, {'rejection_reason': 'No', 'status': 'approved'}]:
            self.assertEqual(self.client.patch(f'/api/requests/{item.pk}/reject/', payload, format='json').status_code, 400)
        self.assertEqual(self.client.patch(f'/api/requests/{item.pk}/reject/', {'rejection_reason': 'Budget exceeded'}, format='json').status_code, 200)
        self.assertEqual(self.client.get(f'/api/requests/{item.pk}/').status_code, 200)

    def test_requester_can_withdraw_pending_request_and_preserve_history(self):
        item = self.make_request()
        self.client.force_authenticate(self.other_manager)
        self.assertEqual(self.client.post(f'/api/requests/{item.pk}/withdraw/', {'reason': 'Cancel'}, format='json').status_code, 404)
        self.client.force_authenticate(self.department_manager)
        self.assertEqual(self.client.post(f'/api/requests/{item.pk}/withdraw/', {'reason': 'No longer needed'}, format='json').status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.status, 'withdrawn')
        self.client.force_authenticate(self.head_manager)
        self.assertEqual(self.client.patch(f'/api/requests/{item.pk}/approve/', {}, format='json').status_code, 409)

    def test_assignment_update_uses_checked_post_and_blocks_generic_reparenting(self):
        item = self.make_request()
        self.approve(item)
        original_version = item.version
        self.assign(item)
        stale = {'overtime_request': item.pk, 'assigned_employees': [self.employee.pk], 'expected_version': original_version}
        self.assertEqual(self.client.post('/api/assignments/', stale, format='json').status_code, 409)
        self.assertEqual(self.assign(item).status_code, 200)
        pending = self.make_request()
        for method in ['patch', 'put']:
            self.assertEqual(getattr(self.client, method)(f'/api/assignments/{item.assignment.pk}/', {'overtime_request': pending.pk}, format='json').status_code, 405)
        self.assertEqual(self.client.delete(f'/api/assignments/{item.assignment.pk}/').status_code, 405)

    def test_assignment_rejects_unapproved_empty_and_inactive_employees(self):
        item = self.make_request()
        self.client.force_authenticate(self.hr_manager)
        payload = {'overtime_request': item.pk, 'assigned_employees': [self.employee.pk], 'expected_version': item.version}
        self.assertEqual(self.client.post('/api/assignments/', payload, format='json').status_code, 400)
        self.approve(item)
        self.client.force_authenticate(self.hr_manager)
        payload['expected_version'] = item.version
        self.assertEqual(self.client.post('/api/assignments/', payload | {'assigned_employees': []}, format='json').status_code, 400)
        self.employee.is_active = False
        self.employee.save()
        self.assertEqual(self.client.post('/api/assignments/', payload, format='json').status_code, 400)

    def test_export_preview_selection_history_and_duplicate_prevention(self):
        item = self.make_request(title='=HYPERLINK("x")')
        self.approve(item)
        self.assign(item)
        selection = self.selection(item)
        preview = self.client.post('/api/sap-exports/preview/', selection, format='json')
        self.assertEqual(preview.status_code, 200)
        self.assertIn("'=HYPERLINK", preview.data['csv_data'])
        self.assertFalse(ExportBatch.objects.exists())
        exported = self.client.post('/api/sap-exports/export_to_csv/', selection, format='json')
        self.assertEqual(exported.status_code, 201, exported.data)
        batch_id = exported.data['batch']['id']
        self.assertEqual(exported.data['batch']['status'], 'generated')
        self.assertEqual(SAPExport.objects.get().status, 'pending')
        self.assertEqual(self.client.post('/api/sap-exports/export_to_csv/', selection, format='json').status_code, 409)
        download = self.client.get(f'/api/export-batches/{batch_id}/download/')
        self.assertEqual(download.content.decode(), preview.data['csv_data'])
        payload = {'overtime_request': item.pk, 'assigned_employees': [self.employee.pk], 'expected_version': item.version}
        self.assertEqual(self.client.post('/api/assignments/', payload, format='json').status_code, 409)
        self.client.force_authenticate(self.department_manager)
        self.assertEqual(self.client.get(f'/api/export-batches/{batch_id}/download/').status_code, 403)

    def test_export_supports_explicit_unnamed_advance_authorization(self):
        item = self.make_request(requires_employee_assignment=False)
        self.approve(item)
        self.client.force_authenticate(self.hr_manager)
        result = self.client.post('/api/sap-exports/export_to_csv/', self.selection(item), format='json')
        self.assertEqual(result.status_code, 201)

    def test_export_requires_selection_current_version_and_required_assignment(self):
        item = self.make_request()
        self.approve(item)
        self.client.force_authenticate(self.hr_manager)
        self.assertEqual(self.client.post('/api/sap-exports/export_to_csv/', {}, format='json').status_code, 400)
        self.assertEqual(self.client.post('/api/sap-exports/export_to_csv/', self.selection(item), format='json').status_code, 400)
        self.assign(item)
        stale = self.selection(item) | {'versions': {str(item.pk): 1}}
        self.assertEqual(self.client.post('/api/sap-exports/export_to_csv/', stale, format='json').status_code, 409)
        self.assertFalse(ExportBatch.objects.exists())

    def test_import_confirmation_is_explicit_and_audited(self):
        item = self.make_request(requires_employee_assignment=False)
        self.approve(item)
        self.client.force_authenticate(self.hr_manager)
        exported = self.client.post('/api/sap-exports/export_to_csv/', self.selection(item), format='json')
        url = f"/api/export-batches/{exported.data['batch']['id']}/record_result/"
        self.assertEqual(self.client.post(url, {'status': 'confirmed'}, format='json').status_code, 400)
        self.assertEqual(self.client.post(url, {'status': 'failed', 'result_note': 'Rejected format'}, format='json').status_code, 200)
        self.assertEqual(self.client.post(url, {'status': 'confirmed', 'sap_reference': 'IMPORT-42'}, format='json').status_code, 200)
        batch = ExportBatch.objects.get()
        self.assertEqual(batch.result_note, '')
        self.assertEqual(batch.sap_reference, 'IMPORT-42')
        self.assertEqual(SAPExport.objects.get().sap_reference, 'IMPORT-42')
        failed_event = AuditEvent.objects.filter(action='import_result_recorded').first()
        self.assertEqual(failed_event.details['note'], 'Rejected format')
        self.assertEqual(AuditEvent.objects.latest('id').details['note'], '')
        self.assertEqual(self.client.post(url, {'status': 'failed', 'result_note': 'Overwrite'}, format='json').status_code, 409)
        self.assertEqual(AuditEvent.objects.filter(action='import_result_recorded').count(), 2)

    def test_export_rechecks_employee_eligibility_after_assignment(self):
        for requires_names in [True, False]:
            for change in ['inactive', 'staff', 'superuser', 'application_admin']:
                with self.subTest(requires_names=requires_names, change=change):
                    item = self.make_request(requires_employee_assignment=requires_names)
                    self.approve(item)
                    self.assign(item)
                    if change == 'application_admin':
                        UserProfile.objects.create(user=self.employee, role='admin')
                    else:
                        field = {'inactive': 'is_active', 'staff': 'is_staff', 'superuser': 'is_superuser'}[change]
                        User.objects.filter(pk=self.employee.pk).update(**{field: change != 'inactive'})
                    for action_name in ['preview', 'export_to_csv']:
                        response = self.client.post(f'/api/sap-exports/{action_name}/', self.selection(item), format='json')
                        self.assertEqual(response.status_code, 400, response.data)
                        self.assertIn('no longer eligible', str(response.data))
                    self.assertFalse(ExportBatch.objects.exists())
                    self.assertFalse(SAPExport.objects.exists())
                    self.assertFalse(AuditEvent.objects.filter(action='export_generated').exists())
                    User.objects.filter(pk=self.employee.pk).update(is_active=True, is_staff=False, is_superuser=False)
                    UserProfile.objects.filter(user=self.employee).delete()

    def test_invalid_employee_blocks_entire_batch_and_can_be_reassigned(self):
        valid = self.make_request(requires_employee_assignment=False)
        invalid = self.make_request()
        self.approve(valid)
        self.approve(invalid)
        self.assign(invalid)
        User.objects.filter(pk=self.employee.pk).update(is_active=False)
        selection = {'request_ids': [valid.pk, invalid.pk],
                     'versions': {str(valid.pk): valid.version, str(invalid.pk): invalid.version}}
        response = self.client.post('/api/sap-exports/export_to_csv/', selection, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ExportBatch.objects.exists())
        self.assertFalse(SAPExport.objects.exists())
        replacement = User.objects.create_user('replacement', 'replacement@example.com')
        response = self.client.post('/api/assignments/', {'overtime_request': invalid.pk,
            'assigned_employees': [replacement.pk], 'expected_version': invalid.version}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        invalid.refresh_from_db()
        selection['versions'][str(invalid.pk)] = invalid.version
        response = self.client.post('/api/sap-exports/export_to_csv/', selection, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['batch']['row_count'], 2)

    def test_export_selection_loads_large_batch_in_bounded_queries(self):
        items = []
        for _ in range(25):
            item = self.make_request(status='approved', approved_by=self.head_manager, approval_date=timezone.now())
            assignment = EmployeeAssignment.objects.create(overtime_request=item, assigned_by=self.hr_manager, status='completed')
            assignment.assigned_employees.add(self.employee)
            items.append(item)
        selection = {'request_ids': [item.pk for item in items],
                     'versions': {str(item.pk): item.version for item in items}}
        with CaptureQueriesContext(connection) as queries:
            selected, content = selected_export(selection)
        self.assertEqual(len(selected), 25)
        self.assertEqual(content.count(self.employee.username), 25)
        self.assertLessEqual(len(queries), 6, 'Batch preparation must not query separately for every request or employee.')

    def test_optional_employee_names_can_be_cleared_before_export(self):
        item = self.make_request(requires_employee_assignment=False)
        self.approve(item)
        self.assign(item)
        response = self.client.post('/api/assignments/', {'overtime_request': item.pk,
            'assigned_employees': [], 'expected_version': item.version}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(item.assignment.assigned_employees.count(), 0)
        self.assertEqual(AuditEvent.objects.latest('id').details['employee_ids'], [])

    def test_cost_overflow_is_checked_after_currency_rounding(self):
        self.client.force_authenticate(self.department_manager)
        response = self.client.post('/api/requests/', self.request_payload() | {
            'total_hours': '105.61', 'hourly_rate': '94688003.03'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(OvertimeRequest.objects.exists())

    def test_request_ids_fit_schema_and_are_unique_within_same_second(self):
        with patch('overtimeapp.models.timezone.now', return_value=timezone.now()):
            ids = [self.make_request().request_id for _ in range(30)]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(len(value) <= OvertimeRequest._meta.get_field('request_id').max_length for value in ids))

    def test_date_hours_and_rate_validation(self):
        self.client.force_authenticate(self.department_manager)
        for change in [{'end_date': '2026-09-01'}, {'total_hours': '0'}, {'hourly_rate': '-1'}, {'hourly_rate': '99999999.99', 'total_hours': '999.99'}]:
            self.assertEqual(self.client.post('/api/requests/', self.request_payload() | change, format='json').status_code, 400)
        for change in [{'end_date': '2026-09-01'}, {'total_hours': Decimal('0')}, {'hourly_rate': Decimal('-1')}]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                self.make_request(**change)
        item = self.make_request(hourly_rate=Decimal('0'))
        self.assertEqual(item.estimated_cost, 0)

    def test_admin_workflow_is_read_only_even_for_superuser(self):
        user = User.objects.create_superuser('system', 'system@example.com', 'password123')
        request = RequestFactory().get('/admin/')
        request.user = user
        item = self.make_request()
        for model in [OvertimeRequest, EmployeeAssignment, ExportBatch, AuditEvent, SAPExport]:
            model_admin = WorkflowReadOnlyAdmin(model, AdminSite())
            self.assertFalse(model_admin.has_add_permission(request))
            self.assertFalse(model_admin.has_change_permission(request, item))
            self.assertFalse(model_admin.has_delete_permission(request, item))

    def test_role_scope_and_profile_mutation_protection(self):
        item = self.make_request()
        self.client.force_authenticate(self.other_manager)
        self.assertEqual(self.client.get(f'/api/requests/{item.pk}/').status_code, 404)
        self.assertEqual(self.client.get(f'/api/requests/{item.pk}/history/').status_code, 404)
        self.assertEqual(self.client.get('/api/users/').status_code, 403)
        self.assertEqual(self.client.patch(f'/api/profiles/{self.other_manager.profile.pk}/', {'role': 'admin'}, format='json').status_code, 403)
        self.client.force_authenticate(self.hr_manager)
        self.assertEqual(self.client.get('/api/users/').status_code, 200)

    def test_system_administrator_can_use_workflow_without_a_profile(self):
        system_admin = User.objects.create_superuser('system', 'system@example.com', 'password123')
        self.client.force_authenticate(system_admin)
        self.assertEqual(self.client.get('/api/users/me/').data['profile']['role'], 'admin')
        self.assertEqual(self.client.get('/api/users/').status_code, 200)
        response = self.client.post('/api/requests/', self.request_payload(), format='json')
        self.assertEqual(response.status_code, 201, response.data)
        own_request = response.data['id']
        self.assertEqual(self.client.patch(f'/api/requests/{own_request}/approve/', {}, format='json').status_code, 403)
        self.assertEqual(self.client.patch(f'/api/requests/{own_request}/reject/', {'rejection_reason': 'No'}, format='json').status_code, 403)
        item = self.make_request()
        approved = self.client.patch(f'/api/requests/{item.pk}/approve/', {}, format='json')
        self.assertEqual(approved.status_code, 200, approved.data)
        item.refresh_from_db()
        assigned = self.client.post('/api/assignments/', {'overtime_request': item.pk,
            'assigned_employees': [self.employee.pk], 'expected_version': item.version}, format='json')
        self.assertEqual(assigned.status_code, 201, assigned.data)
        item.refresh_from_db()
        exported = self.client.post('/api/sap-exports/export_to_csv/', self.selection(item), format='json')
        self.assertEqual(exported.status_code, 201, exported.data)
        self.assertGreater(self.client.get('/api/email-logs/').data['count'], 0)

    def test_system_administrator_can_manage_other_profiles_and_requires_department(self):
        system_admin = User.objects.create_superuser('system', 'system@example.com', 'password123')
        # A stored profile cannot make the API disagree with the effective system role.
        UserProfile.objects.create(user=system_admin, role='dept_manager', department='quality')
        self.client.force_authenticate(system_admin)
        self.assertEqual(self.client.get('/api/users/me/').data['profile']['role'], 'admin')
        url = f'/api/profiles/{self.other_manager.profile.pk}/'
        self.assertEqual(self.client.get(url).status_code, 200)
        response = self.client.patch(url, {'department': None}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('department', response.data)
        response = self.client.patch(url, {'department': 'planning'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.other_manager.profile.refresh_from_db()
        self.assertEqual(self.other_manager.profile.department, 'planning')
        response = self.client.post('/api/profiles/', {'user': self.employee.pk, 'role': 'dept_manager'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(UserProfile.objects.filter(user=self.employee).exists())

    def test_staff_and_application_admin_cannot_manage_roles(self):
        for user in [User.objects.create_user('staff', is_staff=True), self.create_user('appadmin', 'admin')]:
            self.client.force_authenticate(user)
            response = self.client.patch(f'/api/profiles/{self.other_manager.profile.pk}/', {'role': 'admin'}, format='json')
            self.assertEqual(response.status_code, 403)
        self.other_manager.profile.refresh_from_db()
        self.assertEqual(self.other_manager.profile.role, 'dept_manager')

    def test_search_and_department_filter_preserve_request_visibility(self):
        visible = self.make_request(title='Unique inventory count')
        hidden = self.make_request(requester=self.other_manager, department='quality', title='Unique inventory count')
        self.client.force_authenticate(self.department_manager)
        response = self.client.get('/api/requests/', {'search': 'Unique'})
        self.assertEqual([item['id'] for item in response.data['results']], [visible.pk])
        self.assertEqual(self.client.get('/api/requests/', {'search': hidden.request_id}).data['count'], 0)
        self.client.force_authenticate(self.head_manager)
        response = self.client.get('/api/requests/', {'search': 'Unique', 'department': 'quality'})
        self.assertEqual([item['id'] for item in response.data['results']], [hidden.pk])
        response = self.client.get('/api/requests/', {'search': visible.request_id})
        self.assertEqual([item['id'] for item in response.data['results']], [visible.pk])

    def test_notifications_retry_and_use_real_frontend_route(self):
        self.client.force_authenticate(self.department_manager)
        self.client.post('/api/requests/', self.request_payload(), format='json')
        item = EmailLog.objects.get()
        self.assertIn('/head-manager', item.body)
        with patch('overtimeapp.management.commands.send_notifications.send_notification_mail', side_effect=OSError('smtp failure')):
            call_command('send_notifications', stdout=StringIO())
        item.refresh_from_db()
        self.assertEqual(item.status, 'queued')
        self.assertEqual(item.attempts, 1)
        EmailLog.objects.filter(pk=item.pk).update(next_attempt_at=timezone.now())
        with patch('overtimeapp.management.commands.send_notifications.send_notification_mail', return_value=1) as send:
            call_command('send_notifications', stdout=StringIO())
            call_command('send_notifications', stdout=StringIO())
            self.assertEqual(send.call_count, 1)
        item.refresh_from_db()
        self.assertEqual(item.status, 'sent')
        self.assertIsNotNone(item.delivered_at)

    def test_outbox_failure_rolls_back_business_action(self):
        item = self.make_request()
        self.client.force_authenticate(self.head_manager)
        with patch('overtimeapp.views.OvertimeEmailService.send_approval_notification', side_effect=RuntimeError('storage unavailable')):
            with self.assertRaises(RuntimeError):
                self.client.patch(f'/api/requests/{item.pk}/approve/', {}, format='json')
        item.refresh_from_db()
        self.assertEqual(item.status, 'pending')
        self.assertFalse(AuditEvent.objects.exists())

    def test_logout_revokes_token_and_expired_tokens_are_rejected(self):
        token = Token.objects.create(user=self.department_manager)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        self.assertEqual(self.client.get('/api/users/me/').status_code, 200)
        self.assertEqual(self.client.post('/api/auth/logout/').status_code, 204)
        self.assertEqual(self.client.get('/api/users/me/').status_code, 401)
        token = Token.objects.create(user=self.department_manager)
        Token.objects.filter(pk=token.pk).update(created=timezone.now() - timedelta(days=2))
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        self.assertEqual(self.client.get('/api/users/me/').status_code, 401)

    def test_login_works_with_stale_header_and_is_throttled(self):
        self.client.credentials(HTTP_AUTHORIZATION='Token expired')
        response = self.client.post('/api/auth/login/', {'username': 'dept', 'password': 'password123'}, format='json')
        self.assertEqual(response.status_code, 200)
        for _ in range(9):
            self.client.post('/api/auth/login/', {'username': 'dept', 'password': 'wrong'}, format='json')
        self.assertEqual(self.client.post('/api/auth/login/', {'username': 'dept', 'password': 'wrong'}, format='json').status_code, 429)


class SeedUsersCommandTests(TestCase):
    """The provisioning command must map the supplied people onto the expected roles."""

    accounts = {account['username']: account for account in seed_users.ACCOUNTS}

    def run_command(self, *args, password='seed-password-123'):
        with patch.dict(os.environ, {'SEED_PASSWORD': password}):
            output = StringIO()
            call_command('seed_users', *args, stdout=output)
        return output.getvalue()

    def test_creates_accounts_with_roles_departments_and_emails(self):
        self.run_command()
        self.assertEqual(User.objects.filter(username__in=self.accounts).count(), len(self.accounts))
        for username, account in self.accounts.items():
            user = User.objects.get(username=username)
            self.assertEqual(user.email, account['email'])
            self.assertTrue(user.check_password('seed-password-123'))
            self.assertEqual(user.profile.role, account['role'])
            self.assertEqual(user.profile.department, account['department'])
            self.assertEqual(user.is_superuser, account['is_superuser'])
        self.assertEqual(self.accounts['mehdi.bousfiha']['department'], 'production')
        self.assertEqual(self.accounts['charaf.erraoui']['department'], 'logistics')

    def test_is_idempotent_and_preserves_existing_passwords(self):
        self.run_command()
        User.objects.filter(username='mariam.oumalek').update(email='')
        self.run_command(password='a-different-password')
        self.assertEqual(User.objects.filter(username__in=self.accounts).count(), len(self.accounts))
        user = User.objects.get(username='mariam.oumalek')
        self.assertTrue(user.check_password('seed-password-123'))
        self.assertEqual(user.email, self.accounts['mariam.oumalek']['email'])
        self.assertEqual(UserProfile.objects.filter(user=user).count(), 1)

    def test_reset_passwords_replaces_existing_password(self):
        self.run_command()
        self.run_command('--reset-passwords', password='rotated-password-456')
        self.assertTrue(User.objects.get(username='mariam.oumalek').check_password('rotated-password-456'))

    def test_generates_a_password_when_none_is_supplied(self):
        with patch.dict(os.environ, {'SEED_PASSWORD': '', 'SEED_PASSWORD_MARIAM_OUMALEK': ''}):
            output = StringIO()
            call_command('seed_users', stdout=output)
        text = output.getvalue()
        generated = re.search(r'Generated password for mariam\.oumalek: (\S+)', text).group(1)
        self.assertTrue(User.objects.get(username='mariam.oumalek').check_password(generated))
        self.assertTrue(User.objects.get(username='mariam.oumalek').has_usable_password())

    def test_dry_run_writes_nothing(self):
        output = self.run_command('--dry-run')
        self.assertFalse(User.objects.filter(username__in=self.accounts).exists())
        self.assertIn('would create mariam.oumalek (hr_manager)', output)


@override_settings(SECURE_SSL_REDIRECT=False, EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class AdminAccountManagementTests(TestCase):
    """Superuser-only account provisioning for the administration console."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.admin = User.objects.create_superuser('system', 'system@example.com', 'password123')
        self.manager = User.objects.create_user('manager', 'manager@example.com', 'password123')
        UserProfile.objects.create(user=self.manager, role='head_manager')

    def create_account(self, **overrides):
        payload = {'username': 'new.person', 'email': 'new.person@example.com', 'first_name': 'New', 'last_name': 'Person',
                   'role': 'employee', 'password': 'Mubea!Pilot#2026'}
        self.client.force_authenticate(self.admin)
        return self.client.post('/api/admin/accounts/', payload | overrides, format='json')

    def test_only_superusers_can_manage_accounts(self):
        actors = [self.manager, User.objects.create_user('staff', is_staff=True), User.objects.create_user('plain')]
        for actor in actors:
            self.client.force_authenticate(actor)
            with self.subTest(actor=actor.username):
                self.assertEqual(self.client.get('/api/admin/accounts/').status_code, 403)
                self.assertEqual(self.client.post('/api/admin/accounts/', {'username': 'x', 'role': 'employee',
                    'password': 'Mubea!Pilot#2026'}, format='json').status_code, 403)
                self.assertEqual(self.client.patch(f'/api/admin/accounts/{self.manager.pk}/', {'role': 'employee'}, format='json').status_code, 403)
        self.assertFalse(User.objects.filter(username='x').exists())
        self.manager.profile.refresh_from_db()
        self.assertEqual(self.manager.profile.role, 'head_manager')

    def test_creates_employee_and_manager_accounts(self):
        response = self.create_account()
        self.assertEqual(response.status_code, 201, response.data)
        employee = User.objects.get(username='new.person')
        self.assertTrue(employee.check_password('Mubea!Pilot#2026'))
        self.assertTrue(employee.is_active)
        self.assertFalse(employee.is_staff)
        self.assertFalse(UserProfile.objects.filter(user=employee).exists())
        self.assertIsNone(response.data['profile'])
        self.assertEqual(self.create_account(username='dept.lead', role='dept_manager').status_code, 400)
        response = self.create_account(username='dept.lead', role='dept_manager', department='quality')
        self.assertEqual(response.status_code, 201, response.data)
        profile = UserProfile.objects.get(user__username='dept.lead')
        self.assertEqual((profile.role, profile.department), ('dept_manager', 'quality'))
        self.assertEqual(self.create_account(username='hr.lead', role='hr_manager', django_admin=True).status_code, 400)
        response = self.create_account(username='owner2', role='admin', django_admin=True)
        self.assertEqual(response.status_code, 201, response.data)
        owner = User.objects.get(username='owner2')
        self.assertTrue(owner.is_superuser and owner.is_staff)
        self.assertEqual(owner.profile.role, 'admin')
        self.assertEqual(self.create_account(username='owner2').status_code, 400)
        self.assertEqual(self.create_account(username='weakling', password='short').status_code, 400)
        self.assertEqual(self.create_account(username='ceo', role='ceo').status_code, 400)
        self.assertEqual(self.create_account(username='extra', is_active=False).status_code, 400)

    def test_lists_all_accounts_including_administrators(self):
        User.objects.create_user('plain')
        User.objects.create_superuser('other.admin', 'other.admin@example.com', 'password123')
        self.client.force_authenticate(self.admin)
        response = self.client.get('/api/admin/accounts/')
        self.assertEqual(response.status_code, 200)
        usernames = {row['username'] for row in response.data['results']}
        self.assertIn('other.admin', usernames)
        self.assertIn('plain', usernames)
        self.assertEqual([row['username'] for row in self.client.get('/api/admin/accounts/', {'search': 'other.admin'}).data['results']], ['other.admin'])
        self.assertEqual(self.client.get(f'/api/admin/accounts/{self.manager.pk}/').data['profile']['role'], 'head_manager')

    def test_updates_roles_departments_and_deactivation(self):
        target = User.objects.create_user('target', 'target@example.com', 'password123')
        self.client.force_authenticate(self.admin)
        url = f'/api/admin/accounts/{target.pk}/'
        response = self.client.patch(url, {'role': 'hr_manager', 'first_name': 'Renamed'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        target.refresh_from_db()
        self.assertEqual((target.profile.role, target.first_name), ('hr_manager', 'Renamed'))
        self.assertEqual(self.client.patch(url, {'role': 'dept_manager', 'department': 'planning'}, format='json').status_code, 200)
        self.assertEqual(UserProfile.objects.get(user=target).department, 'planning')
        self.assertEqual(self.client.patch(url, {'role': 'dept_manager', 'department': None}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(url, {'role': 'employee'}, format='json').status_code, 200)
        self.assertFalse(UserProfile.objects.filter(user=target).exists())
        self.assertEqual(self.client.patch(url, {'is_active': False}, format='json').status_code, 200)
        target.refresh_from_db()
        self.assertFalse(target.is_active)
        self.assertEqual(self.client.post('/api/auth/login/', {'username': 'target', 'password': 'password123'}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(url, {'is_active': True}, format='json').status_code, 200)

    def test_password_reset_and_username_immutability(self):
        target = User.objects.create_user('reset.me', 'reset.me@example.com', 'password123')
        self.client.force_authenticate(self.admin)
        url = f'/api/admin/accounts/{target.pk}/'
        self.assertEqual(self.client.patch(url, {'password': 'short'}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(url, {'password': 'Mubea!Rotated#2026'}, format='json').status_code, 200)
        target.refresh_from_db()
        self.assertTrue(target.check_password('Mubea!Rotated#2026'))
        self.assertEqual(self.client.patch(url, {'username': 'renamed'}, format='json').status_code, 400)

    def test_administrator_access_cannot_be_removed_from_the_console(self):
        second = User.objects.create_superuser('second.admin', 'second.admin@example.com', 'password123')
        self.client.force_authenticate(self.admin)
        own = f'/api/admin/accounts/{self.admin.pk}/'
        for payload in [{'is_active': False}, {'django_admin': False}, {'role': 'hr_manager'}]:
            with self.subTest(payload=payload):
                self.assertEqual(self.client.patch(own, payload, format='json').status_code, 400)
        self.client.force_authenticate(second)
        demoted = self.client.patch(own, {'role': 'employee', 'django_admin': False}, format='json')
        self.assertEqual(demoted.status_code, 200, demoted.data)
        self.admin.refresh_from_db()
        self.assertFalse(self.admin.is_superuser)
        self.assertFalse(UserProfile.objects.filter(user=self.admin).exists())
        self.assertTrue(User.objects.filter(is_superuser=True, is_active=True).exists())


@override_settings(SECURE_SSL_REDIRECT=False)
class PasswordChangeTests(TestCase):
    """Self-service password changes rotate tokens and enforce the configured validators."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = User.objects.create_user('manager', 'manager@example.com', 'password123')

    def login(self, password):
        return self.client.post('/api/auth/login/', {'username': 'manager', 'password': password}, format='json')

    def test_requires_authentication_and_rejects_bad_input(self):
        response = self.client.post('/api/auth/change-password/', {'current_password': 'password123', 'new_password': 'Mubea!Rotated#2026'}, format='json')
        self.assertEqual(response.status_code, 401)
        self.client.force_authenticate(self.user)
        for payload in [
            {'current_password': 'wrong-password', 'new_password': 'Mubea!Rotated#2026'},
            {'current_password': 'password123', 'new_password': 'short'},
            {'current_password': 'password123', 'new_password': 'password123'},
            {'current_password': 'password123'},
            {'current_password': 'password123', 'new_password': 'Mubea!Rotated#2026', 'role': 'admin'},
        ]:
            with self.subTest(payload=payload):
                self.assertEqual(self.client.post('/api/auth/change-password/', payload, format='json').status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('password123'))
        self.assertTrue(Token.objects.filter(user=self.user).exists() is False)

    def test_changes_password_and_rotates_the_token(self):
        old_token = self.login('password123').data['token']
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {old_token}')
        response = self.client.post('/api/auth/change-password/', {'current_password': 'password123', 'new_password': 'Mubea!Rotated#2026'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        new_token = response.data['token']
        self.assertNotEqual(new_token, old_token)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Mubea!Rotated#2026'))
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {old_token}')
        self.assertEqual(self.client.get('/api/users/me/').status_code, 401)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {new_token}')
        self.assertEqual(self.client.get('/api/users/me/').status_code, 200)
        self.client.credentials()
        self.assertEqual(self.login('password123').status_code, 400)
        self.assertEqual(self.login('Mubea!Rotated#2026').status_code, 200)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                   DEFAULT_FROM_EMAIL='overtime@mubea.com')
class SendTestEmailCommandTests(TestCase):
    """The verification command must report the configured backend and surface failures."""

    def test_sends_one_message_to_the_requested_address(self):
        output = StringIO()
        call_command('send_test_email', '--to', 'Yassir.AMRANI@mubea.com', stdout=output)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['Yassir.AMRANI@mubea.com'])
        self.assertEqual(mail.outbox[0].from_email, 'overtime@mubea.com')
        self.assertIn('overtime@mubea.com', output.getvalue())

    def test_rejects_an_invalid_recipient(self):
        with self.assertRaises(CommandError):
            call_command('send_test_email', '--to', 'not-an-address', stdout=StringIO())
        self.assertEqual(len(mail.outbox), 0)

    def test_reports_a_delivery_failure_instead_of_passing(self):
        with patch('overtimeapp.management.commands.send_test_email.send_notification_mail',
                   side_effect=OSError('connection refused')):
            with self.assertRaises(CommandError) as caught:
                call_command('send_test_email', '--to', 'Yassir.AMRANI@mubea.com', stdout=StringIO())
        self.assertIn('OSError', str(caught.exception))

    def test_warns_when_a_non_smtp_backend_is_configured(self):
        output = StringIO()
        call_command('send_test_email', '--to', 'Yassir.AMRANI@mubea.com', stdout=output)
        self.assertIn('nothing leaves this machine', output.getvalue())

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_reports_the_smtp_server_without_exposing_credentials(self):
        with override_settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
                               EMAIL_HOST='smtp.office365.com', EMAIL_PORT=587,
                               EMAIL_USE_TLS=True, EMAIL_HOST_PASSWORD='super-secret'):
            output = StringIO()
            with patch('overtimeapp.management.commands.send_test_email.send_notification_mail', return_value=1):
                call_command('send_test_email', '--to', 'Yassir.AMRANI@mubea.com', stdout=output)
        self.assertIn('smtp.office365.com:587', output.getvalue())
        self.assertNotIn('super-secret', output.getvalue())


class FakeOutlookItem:
    def __init__(self):
        self.To = self.CC = self.BCC = self.Subject = self.Body = self.HTMLBody = ''
        self.sent = False

    def Send(self):
        self.sent = True


class FakeOutlookItemThatFails(FakeOutlookItem):
    def Send(self):
        raise RuntimeError('Outlook refused the message')


class FakeOutlook:
    def __init__(self, item_class=FakeOutlookItem):
        self.item_class = item_class
        self.items = []

    def CreateItem(self, kind):
        item = self.item_class()
        self.items.append(item)
        return item


class OutlookComBackendTests(TestCase):
    """The Outlook backend must map messages onto mail items without needing SMTP."""

    def patched_modules(self, outlook):
        client = types.ModuleType('win32com.client')
        client.Dispatch = lambda name: outlook
        package = types.ModuleType('win32com')
        package.client = client
        pythoncom = types.SimpleNamespace(CoInitialize=lambda: None, CoUninitialize=lambda: None)
        return patch.dict(sys.modules, {'pythoncom': pythoncom, 'win32com': package, 'win32com.client': client})

    def test_sends_each_message_through_the_signed_in_profile(self):
        outlook = FakeOutlook()
        message = EmailMessage('Overtime approval needed', 'Body text', None,
                               ['Andre-Nicolas.Faucon@mubea.com'], cc=['Mariam.Oumalek@mubea.com'])
        with self.patched_modules(outlook):
            sent = OutlookComEmailBackend().send_messages([message])
        self.assertEqual(sent, 1)
        item = outlook.items[0]
        self.assertEqual(item.To, 'Andre-Nicolas.Faucon@mubea.com')
        self.assertEqual(item.CC, 'Mariam.Oumalek@mubea.com')
        self.assertEqual(item.Subject, 'Overtime approval needed')
        self.assertEqual(item.Body, 'Body text')
        self.assertTrue(item.sent)

    def test_prefers_the_html_body_when_one_is_attached(self):
        outlook = FakeOutlook()
        message = EmailMultiAlternatives('Subject', 'plain text', None, ['a@mubea.com'])
        message.attach_alternative('<p>rich text</p>', 'text/html')
        with self.patched_modules(outlook):
            OutlookComEmailBackend().send_messages([message])
        self.assertEqual(outlook.items[0].HTMLBody, '<p>rich text</p>')
        self.assertEqual(outlook.items[0].Body, '')

    def test_no_messages_needs_no_com_automation(self):
        with patch.dict(sys.modules, {'pythoncom': None, 'win32com': None, 'win32com.client': None}):
            self.assertEqual(OutlookComEmailBackend().send_messages([]), 0)

    def test_missing_pywin32_is_reported_as_configuration_error(self):
        with patch.dict(sys.modules, {'pythoncom': None, 'win32com': None, 'win32com.client': None}):
            with self.assertRaises(ImproperlyConfigured):
                OutlookComEmailBackend().send_messages([EmailMessage('S', 'B', None, ['a@mubea.com'])])

    def test_send_failure_propagates_so_the_outbox_can_retry(self):
        outlook = FakeOutlook(FakeOutlookItemThatFails)
        message = EmailMessage('S', 'B', None, ['a@mubea.com'])
        with self.patched_modules(outlook):
            with self.assertRaises(RuntimeError):
                OutlookComEmailBackend().send_messages([message])
        self.assertEqual(outlook.items[0].sent, False)

    def test_silent_failure_reports_nothing_sent(self):
        outlook = FakeOutlook(FakeOutlookItemThatFails)
        with self.patched_modules(outlook):
            sent = OutlookComEmailBackend(fail_silently=True).send_messages([EmailMessage('S', 'B', None, ['a@mubea.com'])])
        self.assertEqual(sent, 0)


from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.db import close_old_connections
from django.test import TransactionTestCase, skipUnlessDBFeature


@skipUnlessDBFeature('has_select_for_update')
@override_settings(SECURE_SSL_REDIRECT=False, EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PostgreSQLConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.dept = User.objects.create_user('parallel-dept')
        UserProfile.objects.create(user=self.dept, role='dept_manager', department='logistics')
        self.head = User.objects.create_user('parallel-head')
        UserProfile.objects.create(user=self.head, role='head_manager')
        self.hr = User.objects.create_user('parallel-hr')
        UserProfile.objects.create(user=self.hr, role='hr_manager')
        self.employee = User.objects.create_user('parallel-employee')
        self.item = OvertimeRequest.objects.create(requester=self.dept, department='logistics',
            title='Concurrent work', description='Work', reason='Deadline', start_date='2026-10-01',
            end_date='2026-10-01', total_hours=Decimal('4'), requires_employee_assignment=False)

    def concurrently(self, operations):
        barrier = Barrier(len(operations))
        def run(operation):
            close_old_connections()
            try:
                user, method, url, payload = operation
                client = APIClient()
                client.force_authenticate(user)
                barrier.wait(timeout=10)
                response = getattr(client, method)(url, payload, format='json')
                return response.status_code
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=len(operations)) as executor:
            return sorted(executor.map(run, operations))

    def prepare_approved(self):
        self.item.status = 'approved'
        self.item.approved_by = self.head
        self.item.approval_date = timezone.now()
        self.item.save()
        return {'request_ids': [self.item.pk], 'versions': {str(self.item.pk): self.item.version}}

    def test_two_simultaneous_decisions_produce_one_audited_decision(self):
        url = f'/api/requests/{self.item.pk}/'
        results = self.concurrently([(self.head, 'patch', url + 'approve/', {}),
                                     (self.head, 'patch', url + 'reject/', {'rejection_reason': 'Budget'})])
        self.assertEqual(results, [200, 409])
        self.assertEqual(AuditEvent.objects.count(), 1)

    def test_two_simultaneous_exports_create_one_batch(self):
        payload = self.prepare_approved()
        operation = (self.hr, 'post', '/api/sap-exports/export_to_csv/', payload)
        self.assertEqual(self.concurrently([operation, operation]), [201, 409])
        self.assertEqual(ExportBatch.objects.count(), 1)
        self.assertEqual(SAPExport.objects.count(), 1)

    def test_assignment_and_export_cannot_race_past_version_check(self):
        payload = self.prepare_approved()
        assignment = {'overtime_request': self.item.pk, 'assigned_employees': [self.employee.pk], 'expected_version': self.item.version}
        self.assertEqual(self.concurrently([(self.hr, 'post', '/api/sap-exports/export_to_csv/', payload),
                                           (self.hr, 'post', '/api/assignments/', assignment)]), [201, 409])
