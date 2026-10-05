"""Explicit input contracts for the overtime approval workflow."""
from rest_framework import serializers
from decimal import Decimal
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from .models import UserProfile, OvertimeRequest, EmployeeAssignment, SAPExport, EmailLog, AuditEvent, ExportBatch, ROLE_CHOICES, DEPARTMENT_CHOICES
from .access import account_role, eligible_employees, user_role


class StrictInputMixin:
    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError('Expected an object.')
        unexpected = set(data) - {name for name, field in self.fields.items() if not field.read_only}
        if unexpected:
            raise serializers.ValidationError({key: 'This field cannot be supplied.' for key in unexpected})
        return super().to_internal_value(data)


class UserSerializer(serializers.ModelSerializer):
    profile = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'is_staff', 'is_superuser', 'profile', 'date_joined']
        read_only_fields = fields

    def get_profile(self, obj):
        try:
            return {'role': user_role(obj), 'department': obj.profile.department, 'phone': obj.profile.phone}
        except UserProfile.DoesNotExist:
            if obj.is_superuser:
                return {'role': 'admin', 'department': None, 'phone': ''}
            return None


class UserProfileSerializer(StrictInputMixin, serializers.ModelSerializer):
    user_details = UserSerializer(source='user', read_only=True)

    class Meta:
        model = UserProfile
        fields = ['id', 'user', 'user_details', 'role', 'department', 'phone', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, attrs):
        role = attrs.get('role', getattr(self.instance, 'role', None))
        department = attrs.get('department', getattr(self.instance, 'department', None))
        if role == 'dept_manager' and not department:
            raise serializers.ValidationError({'department': 'A department manager must have an assigned department.'})
        return attrs


class AuditEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = ['id', 'actor_name', 'action', 'details', 'created_at']
        read_only_fields = fields


class OvertimeRequestSerializer(serializers.ModelSerializer):
    requester_name = serializers.CharField(source='requester.get_full_name', read_only=True)
    approved_by_name = serializers.CharField(source='approved_by.get_full_name', read_only=True, allow_null=True)
    assignment = serializers.SerializerMethodField()
    export_batch = serializers.SerializerMethodField()

    class Meta:
        model = OvertimeRequest
        fields = ['id', 'request_id', 'requester', 'requester_name', 'department', 'status', 'version',
                  'requires_employee_assignment', 'title', 'description', 'reason', 'start_date', 'end_date',
                  'total_hours', 'hourly_rate', 'estimated_cost', 'approved_by', 'approved_by_name',
                  'approval_date', 'rejection_reason', 'rejection_date', 'created_at', 'updated_at', 'assignment', 'export_batch']
        read_only_fields = fields

    def get_assignment(self, obj):
        try:
            return {'id': obj.assignment.id, 'notes': obj.assignment.notes, 'status': obj.assignment.status,
                    'employees': [{'id': u.id, 'name': u.get_full_name() or u.username} for u in obj.assignment.assigned_employees.all()]}
        except EmployeeAssignment.DoesNotExist:
            return None

    def get_export_batch(self, obj):
        try:
            return str(obj.sap_export.batch_id) if obj.sap_export.batch_id else 'legacy'
        except SAPExport.DoesNotExist:
            return None


class OvertimeRequestCreateSerializer(StrictInputMixin, serializers.ModelSerializer):
    class Meta:
        model = OvertimeRequest
        fields = ['department', 'title', 'description', 'reason', 'start_date', 'end_date', 'total_hours', 'hourly_rate', 'requires_employee_assignment']

    def validate(self, attrs):
        if attrs['end_date'] < attrs['start_date']:
            raise serializers.ValidationError({'end_date': 'End date must be on or after start date.'})
        user = self.context['request'].user
        if user_role(user) == 'dept_manager' and user.profile.department != attrs['department']:
            raise serializers.ValidationError({'department': 'Department must match your assigned department.'})
        rate = attrs.get('hourly_rate')
        if rate is not None and (rate * attrs['total_hours']).quantize(Decimal('0.01')) >= 10 ** 10:
            raise serializers.ValidationError({'hourly_rate': 'Estimated cost exceeds the supported maximum.'})
        return attrs


class OvertimeRequestApprovalSerializer(StrictInputMixin, serializers.Serializer):
    rejection_reason = serializers.CharField(max_length=2000, allow_blank=False)


class WithdrawalSerializer(StrictInputMixin, serializers.Serializer):
    reason = serializers.CharField(max_length=2000, allow_blank=False)


class EmployeeAssignmentSerializer(serializers.ModelSerializer):
    overtime_request_details = OvertimeRequestSerializer(source='overtime_request', read_only=True)
    assigned_employees_list = UserSerializer(source='assigned_employees', many=True, read_only=True)

    class Meta:
        model = EmployeeAssignment
        fields = ['id', 'overtime_request', 'overtime_request_details', 'assigned_by', 'status', 'assigned_employees', 'assigned_employees_list', 'notes', 'created_at', 'updated_at']
        read_only_fields = fields


class EmployeeAssignmentCreateSerializer(StrictInputMixin, serializers.Serializer):
    overtime_request = serializers.PrimaryKeyRelatedField(queryset=OvertimeRequest.objects.all())
    assigned_employees = serializers.PrimaryKeyRelatedField(queryset=eligible_employees(), many=True, allow_empty=True)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    expected_version = serializers.IntegerField(min_value=1)


class SAPExportSerializer(serializers.ModelSerializer):
    class Meta:
        model = SAPExport
        fields = ['id', 'overtime_request', 'batch', 'exported_by', 'export_date', 'sap_reference', 'status']
        read_only_fields = fields


class ExportSelectionSerializer(StrictInputMixin, serializers.Serializer):
    request_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), allow_empty=False, max_length=200)
    versions = serializers.DictField(child=serializers.IntegerField(min_value=1))

    def validate(self, attrs):
        ids = attrs['request_ids']
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError({'request_ids': 'Select each request only once.'})
        if set(attrs['versions']) != {str(pk) for pk in ids}:
            raise serializers.ValidationError({'versions': 'Supply the displayed version for every selected request.'})
        return attrs


class ExportResultSerializer(StrictInputMixin, serializers.Serializer):
    status = serializers.ChoiceField(choices=['confirmed', 'failed'])
    sap_reference = serializers.CharField(max_length=100, required=False, allow_blank=True)
    result_note = serializers.CharField(max_length=2000, required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs['status'] == 'confirmed' and not attrs.get('sap_reference'):
            raise serializers.ValidationError({'sap_reference': 'Enter the SAP import reference.'})
        if attrs['status'] == 'failed' and not attrs.get('result_note'):
            raise serializers.ValidationError({'result_note': 'Describe the import failure.'})
        return attrs


class ExportBatchSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.username', read_only=True, allow_null=True)

    class Meta:
        model = ExportBatch
        fields = ['id', 'created_at', 'created_by_name', 'checksum', 'row_count', 'format_version', 'status', 'sap_reference', 'result_note', 'confirmed_at']
        read_only_fields = fields


class EmailLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailLog
        fields = ['id', 'overtime_request', 'recipient', 'subject', 'email_type', 'sent_at', 'status', 'attempts', 'next_attempt_at', 'delivered_at', 'error_message']
        read_only_fields = fields


ACCOUNT_ROLE_CHOICES = [('employee', 'Employee account')] + list(ROLE_CHOICES)


class AdminAccountSerializer(serializers.ModelSerializer):
    """Complete account record, including administrator and deactivated accounts."""
    profile = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'is_active', 'is_staff', 'is_superuser',
                  'date_joined', 'profile']
        read_only_fields = fields

    def get_profile(self, obj):
        try:
            return {'id': obj.profile.id, 'role': obj.profile.role, 'department': obj.profile.department, 'phone': obj.profile.phone}
        except UserProfile.DoesNotExist:
            return None


def validate_account_password(value):
    try:
        validate_password(value)
    except DjangoValidationError as error:
        raise serializers.ValidationError(list(error.messages))
    return value


class AdminAccountCreateSerializer(StrictInputMixin, serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True, default='')
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default='')
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default='')
    role = serializers.ChoiceField(choices=ACCOUNT_ROLE_CHOICES)
    department = serializers.ChoiceField(choices=DEPARTMENT_CHOICES, required=False, allow_null=True)
    password = serializers.CharField(trim_whitespace=False)
    django_admin = serializers.BooleanField(required=False, default=False)

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError('This username is already taken.')
        return value

    def validate_password(self, value):
        return validate_account_password(value)

    def validate(self, attrs):
        if attrs['role'] == 'dept_manager' and not attrs.get('department'):
            raise serializers.ValidationError({'department': 'A department manager must have an assigned department.'})
        if attrs.get('django_admin') and attrs['role'] != 'admin':
            raise serializers.ValidationError({'django_admin': 'Django administration access requires the Administrator role.'})
        return attrs


class AdminAccountUpdateSerializer(StrictInputMixin, serializers.Serializer):
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    role = serializers.ChoiceField(choices=ACCOUNT_ROLE_CHOICES, required=False)
    department = serializers.ChoiceField(choices=DEPARTMENT_CHOICES, required=False, allow_null=True)
    is_active = serializers.BooleanField(required=False)
    django_admin = serializers.BooleanField(required=False)
    password = serializers.CharField(trim_whitespace=False, required=False)

    def validate_password(self, value):
        return validate_account_password(value)

    def validate(self, attrs):
        account = self.context['account']
        try:
            current_department = account.profile.department
        except UserProfile.DoesNotExist:
            current_department = None
        role = attrs.get('role', account_role(account))
        if role == 'dept_manager' and not attrs.get('department', current_department):
            raise serializers.ValidationError({'department': 'A department manager must have an assigned department.'})
        if attrs.get('django_admin', account.is_superuser) and role != 'admin':
            raise serializers.ValidationError({'django_admin': 'Django administration access requires the Administrator role.'})
        return attrs


class PasswordChangeSerializer(StrictInputMixin, serializers.Serializer):
    current_password = serializers.CharField(trim_whitespace=False)
    new_password = serializers.CharField(trim_whitespace=False)

    def validate_current_password(self, value):
        if not self.context['request'].user.check_password(value):
            raise serializers.ValidationError('The current password is not correct.')
        return value

    def validate_new_password(self, value):
        validate_account_password(value)
        if self.context['request'].user.check_password(value):
            raise serializers.ValidationError('Choose a password that differs from the current one.')
        return value
