"""Role-scoped reads and explicit, transactional workflow actions."""
import csv
import hashlib
from io import StringIO

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Prefetch
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response

from .models import UserProfile, OvertimeRequest, EmployeeAssignment, SAPExport, EmailLog, AuditEvent, ExportBatch
from .serializers import (
    UserSerializer, UserProfileSerializer, OvertimeRequestSerializer, OvertimeRequestCreateSerializer,
    OvertimeRequestApprovalSerializer, WithdrawalSerializer, EmployeeAssignmentSerializer,
    EmployeeAssignmentCreateSerializer, SAPExportSerializer, EmailLogSerializer,
    AuditEventSerializer, ExportSelectionSerializer, ExportBatchSerializer, ExportResultSerializer,
    AdminAccountSerializer, AdminAccountCreateSerializer, AdminAccountUpdateSerializer,
)
from .permissions import IsHeadManagerOrAdmin, IsHRManagerOrAdmin, IsSuperuser
from .access import account_role, eligible_employees, is_eligible_employee, user_role
from .emails import OvertimeEmailService


class Conflict(APIException):
    status_code = 409
    default_detail = 'This record changed. Refresh and try again.'


def audit(item, actor, action_name, **details):
    AuditEvent.objects.create(overtime_request=item, actor=actor, actor_name=actor.username,
                              action=action_name, details=details)


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ['username', 'email', 'first_name', 'last_name']

    def get_queryset(self):
        if user_role(self.request.user) in ['hr_manager', 'admin']:
            return eligible_employees().select_related('profile').order_by('username')
        return User.objects.filter(pk=self.request.user.pk).select_related('profile')

    def get_permissions(self):
        return [IsAuthenticated(), IsHRManagerOrAdmin()] if self.action == 'list' else [IsAuthenticated()]

    @action(detail=False, methods=['get'])
    def me(self, request):
        return Response(UserSerializer(request.user).data)


class UserProfileViewSet(viewsets.ModelViewSet):
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if user_role(self.request.user) == 'admin':
            return UserProfile.objects.select_related('user').all()
        return UserProfile.objects.select_related('user').filter(user=self.request.user)

    def get_permissions(self):
        if self.action not in ['list', 'retrieve', 'my_profile']:
            # Changing roles is a Django superuser responsibility, not ordinary staff.
            if not self.request.user.is_superuser:
                raise PermissionDenied('Only a system administrator can manage roles.')
            return [IsAuthenticated(), IsAdminUser()]
        return [IsAuthenticated()]

    @action(detail=False, methods=['get'])
    def my_profile(self, request):
        return Response(UserProfileSerializer(get_object_or_404(UserProfile, user=request.user)).data)


class OvertimeRequestViewSet(mixins.CreateModelMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = OvertimeRequestSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'department']
    search_fields = ['request_id', 'title', 'description']
    ordering_fields = ['created_at', 'total_hours', 'estimated_cost']
    ordering = ['-created_at', '-id']

    def get_permissions(self):
        if self.action in ['approve', 'reject']:
            return [IsAuthenticated(), IsHeadManagerOrAdmin()]
        return [IsAuthenticated()]

    def get_queryset(self):
        qs = OvertimeRequest.objects.select_related('requester', 'approved_by', 'assignment', 'sap_export').prefetch_related('assignment__assigned_employees')
        role = user_role(self.request.user)
        if role in ['head_manager', 'admin']:
            return qs
        if role == 'hr_manager':
            return qs.filter(status='approved')
        if role == 'dept_manager':
            return qs.filter(requester=self.request.user)
        return qs.none()

    def locked_object(self):
        # The first lookup enforces role scope; lock only the request table (no nullable joins).
        visible = self.get_object()
        return OvertimeRequest.objects.select_for_update().get(pk=visible.pk)

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        if user_role(request.user) not in ['dept_manager', 'admin']:
            raise PermissionDenied('Only department managers can submit requests.')
        serializer = OvertimeRequestCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        item = OvertimeRequest.objects.create(requester=request.user, **serializer.validated_data)
        audit(item, request.user, 'submitted', snapshot=dict(OvertimeRequestSerializer(item).data))
        OvertimeEmailService.send_request_submitted_notification(item)
        return Response(OvertimeRequestSerializer(item).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['patch'])
    @transaction.atomic
    def approve(self, request, pk=None):
        if request.data:
            raise ValidationError('Approval does not accept request field changes.')
        item = self.locked_object()
        if item.requester_id == request.user.id:
            raise PermissionDenied('A request must be approved by a different person.')
        if item.status != 'pending':
            raise Conflict('Only pending requests can be approved.')
        # Conditional update also protects against a stale transition on databases without row locking.
        now = timezone.now()
        changed = OvertimeRequest.objects.filter(pk=item.pk, status='pending', version=item.version).update(
            status='approved', approved_by=request.user, approval_date=now, updated_at=now, version=item.version + 1)
        if not changed:
            raise Conflict()
        item.refresh_from_db()
        audit(item, request.user, 'approved', version=item.version, employee_hours=str(item.total_hours))
        OvertimeEmailService.send_approval_notification(item)
        return Response(OvertimeRequestSerializer(item).data)

    @action(detail=True, methods=['patch'])
    @transaction.atomic
    def reject(self, request, pk=None):
        serializer = OvertimeRequestApprovalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = self.locked_object()
        if item.requester_id == request.user.id:
            raise PermissionDenied('A request must be reviewed by a different person.')
        if item.status != 'pending':
            raise Conflict('Only pending requests can be rejected.')
        now = timezone.now()
        changed = OvertimeRequest.objects.filter(pk=item.pk, status='pending', version=item.version).update(
            status='rejected', rejection_reason=serializer.validated_data['rejection_reason'], rejection_date=now,
            updated_at=now, version=item.version + 1)
        if not changed:
            raise Conflict()
        item.refresh_from_db()
        audit(item, request.user, 'rejected', reason=item.rejection_reason)
        OvertimeEmailService.send_rejection_notification(item)
        return Response(OvertimeRequestSerializer(item).data)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def withdraw(self, request, pk=None):
        serializer = WithdrawalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = self.locked_object()
        if item.requester_id != request.user.id:
            raise PermissionDenied('Only the requester can withdraw this request.')
        if item.status != 'pending':
            raise Conflict('Only pending requests can be withdrawn.')
        changed = OvertimeRequest.objects.filter(pk=item.pk, status='pending', version=item.version).update(
            status='withdrawn', version=item.version + 1, updated_at=timezone.now())
        if not changed:
            raise Conflict()
        item.refresh_from_db()
        audit(item, request.user, 'withdrawn', reason=serializer.validated_data['reason'])
        return Response(OvertimeRequestSerializer(item).data)

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        return Response(AuditEventSerializer(self.get_object().events.all(), many=True).data)


class EmployeeAssignmentViewSet(mixins.CreateModelMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = EmployeeAssignmentSerializer
    permission_classes = [IsAuthenticated, IsHRManagerOrAdmin]
    queryset = EmployeeAssignment.objects.select_related('overtime_request').prefetch_related('assigned_employees').order_by('-created_at')

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = EmployeeAssignmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        item = OvertimeRequest.objects.select_for_update().get(pk=data['overtime_request'].pk)
        if item.status != 'approved':
            raise ValidationError('Only approved requests can have employees assigned.')
        if item.version != data['expected_version']:
            raise Conflict()
        if SAPExport.objects.filter(overtime_request=item).exists():
            raise Conflict('Exported assignments are locked. Use the saved export history.')
        employees = data['assigned_employees']
        if item.requires_employee_assignment and not employees:
            raise ValidationError('Select at least one employee for this request.')
        if len({u.pk for u in employees}) != len(employees):
            raise ValidationError('Select each employee only once.')
        assignment, created = EmployeeAssignment.objects.get_or_create(overtime_request=item, defaults={'assigned_by': request.user})
        assignment.assigned_employees.set(employees)
        assignment.assigned_by = request.user
        assignment.notes = data.get('notes', '')
        assignment.status = 'completed'
        assignment.save()
        item.version += 1
        item.save(update_fields=['version', 'updated_at'])
        audit(item, request.user, 'employees_assigned', employee_ids=[u.pk for u in employees], notes=assignment.notes)
        OvertimeEmailService.send_assignment_notification(item, employees)
        return Response(EmployeeAssignmentSerializer(assignment).data, status=201 if created else 200)


def csv_cell(value):
    """Prevent user-supplied spreadsheet formulas in the human review CSV."""
    text = '' if value is None else str(value)
    if text.lstrip().startswith(('=', '+', '-', '@')) or text.startswith(('\t', '\r', '\n')):
        return "'" + text
    return text


def selected_export(data, lock=False):
    serializer = ExportSelectionSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    ids = serializer.validated_data['request_ids']
    assignments = EmployeeAssignment.objects.prefetch_related(Prefetch(
        'assigned_employees', queryset=User.objects.select_related('profile').order_by('pk')))
    # Keep joins out of the locked request query and load the batch in bounded queries.
    qs = OvertimeRequest.objects.filter(pk__in=ids).order_by('pk').prefetch_related(
        'requester', Prefetch('assignment', queryset=assignments), 'sap_export')
    if lock:
        qs = qs.select_for_update()
    items = list(qs)
    if len(items) != len(ids):
        raise ValidationError('One or more requests do not exist.')
    for item in items:
        if item.status != 'approved':
            raise ValidationError(f'{item.request_id} is not approved.')
        if not item.approved_by_id or not item.approval_date:
            raise ValidationError(f'{item.request_id} lacks approval attribution. Resolve the legacy record before export.')
        if item.version != serializer.validated_data['versions'][str(item.pk)]:
            raise Conflict(f'{item.request_id} changed. Refresh the queue before exporting.')
        if getattr(item, 'sap_export', None) is not None:
            raise Conflict(f'{item.request_id} was already exported. Download the saved batch.')
        assignment = getattr(item, 'assignment', None)
        employees = list(assignment.assigned_employees.all()) if assignment else []
        if item.requires_employee_assignment:
            if not assignment or assignment.status != 'completed' or not employees:
                raise ValidationError(f'{item.request_id} still needs employee assignment.')
        if any(not is_eligible_employee(employee) for employee in employees):
            raise ValidationError(f'{item.request_id} includes an employee who is no longer eligible. Update its assignment before exporting.')
    buffer = StringIO(newline='')
    writer = csv.writer(buffer)
    writer.writerow(['Request ID', 'Department', 'Requester', 'Title', 'Start Date', 'End Date',
                     'Approved Employee Hours', 'Hourly Rate', 'Estimated Cost', 'Assigned Employees', 'Notes'])
    for item in items:
        assignment = getattr(item, 'assignment', None)
        employees = ', '.join(u.get_full_name() or u.username for u in assignment.assigned_employees.all()) if assignment else ''
        writer.writerow([csv_cell(value) for value in [item.request_id, item.get_department_display(),
            item.requester.get_full_name() or item.requester.username, item.title, item.start_date, item.end_date,
            item.total_hours, item.hourly_rate, item.estimated_cost, employees, assignment.notes if assignment else '']])
    return items, buffer.getvalue()


class SAPExportViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SAPExport.objects.all().order_by('-export_date')
    serializer_class = SAPExportSerializer
    permission_classes = [IsAuthenticated, IsHRManagerOrAdmin]

    @action(detail=False, methods=['post'])
    def preview(self, request):
        items, content = selected_export(request.data)
        return Response({'csv_data': content, 'row_count': len(items), 'format_version': 'approval-review-v1',
                         'notice': 'Advance approval review file. SAP import mapping must be validated by your SAP team.'})

    @action(detail=False, methods=['post'])
    @transaction.atomic
    def export_to_csv(self, request):
        items, content = selected_export(request.data, lock=True)
        batch = ExportBatch.objects.create(created_by=request.user, csv_content=content,
            checksum=hashlib.sha256(content.encode('utf-8')).hexdigest(), row_count=len(items))
        for item in items:
            SAPExport.objects.create(overtime_request=item, exported_by=request.user, batch=batch, status='pending')
            audit(item, request.user, 'export_generated', batch_id=str(batch.pk), checksum=batch.checksum)
        return Response({'batch': ExportBatchSerializer(batch).data, 'csv_data': content,
                         'message': f'Saved {len(items)} approved requests in an export batch.'}, status=201)


class ExportBatchViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ExportBatch.objects.select_related('created_by').all()
    serializer_class = ExportBatchSerializer
    permission_classes = [IsAuthenticated, IsHRManagerOrAdmin]

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        batch = self.get_object()
        response = HttpResponse(batch.csv_content, content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="overtime-approval-{batch.pk}.csv"'
        response['Cache-Control'] = 'no-store'
        return response

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def record_result(self, request, pk=None):
        data = ExportResultSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        batch = get_object_or_404(ExportBatch.objects.select_for_update(), pk=pk)
        if batch.status == 'confirmed':
            raise Conflict('A confirmed import cannot be overwritten.')
        batch.status = data.validated_data['status']
        batch.sap_reference = data.validated_data.get('sap_reference', '')
        batch.result_note = data.validated_data.get('result_note', '')
        batch.confirmed_by = request.user
        batch.confirmed_at = timezone.now()
        batch.save(update_fields=['status', 'sap_reference', 'result_note', 'confirmed_by', 'confirmed_at'])
        batch.records.update(status=batch.status, sap_reference=batch.sap_reference)
        for record in batch.records.select_related('overtime_request'):
            audit(record.overtime_request, request.user, 'import_result_recorded', batch_id=str(batch.pk),
                  status=batch.status, sap_reference=batch.sap_reference, note=batch.result_note)
        return Response(ExportBatchSerializer(batch).data)


class EmailLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = EmailLogSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['email_type', 'status']

    def get_queryset(self):
        return EmailLog.objects.all().order_by('-sent_at') if user_role(self.request.user) == 'admin' else EmailLog.objects.none()


class AdminAccountViewSet(mixins.CreateModelMixin, mixins.UpdateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Superuser-only account directory and provisioning for the administration console.

    Deactivation replaces deletion so history and PROTECTed workflow references survive.
    """
    permission_classes = [IsAuthenticated, IsSuperuser]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']
    queryset = User.objects.select_related('profile').order_by('username')
    filter_backends = [filters.SearchFilter]
    search_fields = ['username', 'email', 'first_name', 'last_name']

    def get_serializer_class(self):
        if self.action == 'create':
            return AdminAccountCreateSerializer
        if self.action in ['update', 'partial_update']:
            return AdminAccountUpdateSerializer
        return AdminAccountSerializer

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = AdminAccountCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        account = User.objects.create_user(data['username'], data['email'], data['password'],
                                           first_name=data['first_name'], last_name=data['last_name'])
        if data['django_admin']:
            account.is_staff = True
            account.is_superuser = True
            account.save(update_fields=['is_staff', 'is_superuser'])
        if data['role'] != 'employee':
            UserProfile.objects.create(user=account, role=data['role'],
                                       department=data.get('department') if data['role'] == 'dept_manager' else None)
        return Response(AdminAccountSerializer(account).data, status=status.HTTP_201_CREATED)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        account = User.objects.select_for_update().get(pk=self.get_object().pk)
        serializer = AdminAccountUpdateSerializer(data=request.data, context={'account': account})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        role = data.get('role', account_role(account))
        django_admin = data.get('django_admin', account.is_superuser)
        is_active = data.get('is_active', account.is_active)
        if account.pk == request.user.pk:
            if role != 'admin':
                raise ValidationError('You cannot change your own role away from Administrator.')
            if not is_active:
                raise ValidationError('You cannot deactivate your own account.')
            if account.is_superuser and not django_admin:
                raise ValidationError('You cannot remove your own Django administration access.')
        if account.is_superuser and (not django_admin or not is_active):
            if not User.objects.filter(is_superuser=True, is_active=True).exclude(pk=account.pk).exists():
                raise ValidationError('At least one active administrator with Django access must remain.')
        account.first_name = data.get('first_name', account.first_name)
        account.last_name = data.get('last_name', account.last_name)
        account.email = data.get('email', account.email)
        account.is_active = is_active
        if django_admin:
            account.is_staff = True
            account.is_superuser = True
        elif account.is_superuser:
            account.is_staff = False
            account.is_superuser = False
        if 'password' in data:
            account.set_password(data['password'])
        account.save()
        if role == 'employee':
            UserProfile.objects.filter(user=account).delete()
        else:
            current_department = account.profile.department if hasattr(account, 'profile') else None
            UserProfile.objects.update_or_create(user=account, defaults={
                'role': role,
                'department': data.get('department', current_department) if role == 'dept_manager' else None,
            })
        return Response(AdminAccountSerializer(account).data)
