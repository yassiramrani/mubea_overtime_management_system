"""
Django models for Overtime Management System
"""
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.utils import timezone

# User Role Constants
ROLE_CHOICES = [
    ('dept_manager', 'Department Manager'),
    ('head_manager', 'Head Manager'),
    ('hr_manager', 'HR Manager'),
    ('admin', 'Administrator'),
]

DEPARTMENT_CHOICES = [
    ('logistics', 'Logistics'),
    ('quality', 'Quality'),
    ('production', 'Production'),
    ('maintenance', 'Maintenance'),
    ('planning', 'Planning'),
]

REQUEST_STATUS_CHOICES = [
    ('pending', 'Pending'),
    ('approved', 'Approved'),
    ('rejected', 'Rejected'),
]

ASSIGNMENT_STATUS_CHOICES = [
    ('pending', 'Pending'),
    ('completed', 'Completed'),
    ('cancelled', 'Cancelled'),
]


class UserProfile(models.Model):
    """Extended user profile with role and department"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    department = models.CharField(
        max_length=20, 
        choices=DEPARTMENT_CHOICES, 
        null=True, 
        blank=True
    )
    phone = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.get_role_display()})"

    class Meta:
        db_table = 'user_profiles'


class OvertimeRequest(models.Model):
    """Overtime request submitted by department manager"""
    request_id = models.CharField(max_length=20, unique=True)
    requester = models.ForeignKey(User, on_delete=models.PROTECT, related_name='overtime_requests')
    department = models.CharField(max_length=20, choices=DEPARTMENT_CHOICES)
    status = models.CharField(max_length=20, choices=REQUEST_STATUS_CHOICES, default='pending')
    
    # Request Details
    title = models.CharField(max_length=200)
    description = models.TextField()
    reason = models.TextField(help_text="Reason for overtime request")
    start_date = models.DateField()
    end_date = models.DateField()
    total_hours = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(0.5)])
    
    # Estimated cost
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    estimated_cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    
    # Approval tracking
    approved_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='approved_requests'
    )
    approval_date = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    rejection_date = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'overtime_requests'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['department']),
            models.Index(fields=['requester']),
        ]

    def __str__(self):
        return f"{self.request_id} - {self.title}"

    def save(self, *args, **kwargs):
        if not self.request_id:
            from django.utils.text import slugify
            timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
            self.request_id = f"OT-{self.department.upper()}-{timestamp}"
        
        if self.hourly_rate and self.total_hours:
            self.estimated_cost = self.hourly_rate * self.total_hours
        
        super().save(*args, **kwargs)


class EmployeeAssignment(models.Model):
    """Assignment of employees to approved overtime requests"""
    overtime_request = models.OneToOneField(
        OvertimeRequest, 
        on_delete=models.CASCADE, 
        related_name='assignment'
    )
    assigned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='assignments_created')
    status = models.CharField(max_length=20, choices=ASSIGNMENT_STATUS_CHOICES, default='pending')
    
    # Assignment Details
    assigned_employees = models.ManyToManyField(
        User, 
        related_name='assigned_overtimes',
        help_text="Employees assigned to this overtime"
    )
    
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'employee_assignments'
        ordering = ['-created_at']

    def __str__(self):
        return f"Assignment for {self.overtime_request.request_id}"


class SAPExport(models.Model):
    """Track data exported to SAP"""
    overtime_request = models.OneToOneField(
        OvertimeRequest, 
        on_delete=models.CASCADE, 
        related_name='sap_export'
    )
    exported_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='sap_exports')
    export_date = models.DateTimeField(auto_now_add=True)
    csv_file = models.FileField(upload_to='sap_exports/', null=True, blank=True)
    sap_reference = models.CharField(max_length=100, blank=True, help_text="SAP reference number")
    status = models.CharField(
        max_length=20, 
        choices=[('pending', 'Pending'), ('sent', 'Sent'), ('confirmed', 'Confirmed'), ('failed', 'Failed')],
        default='pending'
    )
    
    class Meta:
        db_table = 'sap_exports'
        ordering = ['-export_date']

    def __str__(self):
        return f"SAP Export for {self.overtime_request.request_id}"


class EmailLog(models.Model):
    """Log of all emails sent"""
    overtime_request = models.ForeignKey(
        OvertimeRequest, 
        on_delete=models.CASCADE, 
        related_name='email_logs',
        null=True,
        blank=True
    )
    recipient = models.EmailField()
    subject = models.CharField(max_length=255)
    email_type = models.CharField(
        max_length=50,
        choices=[
            ('request_submitted', 'Request Submitted'),
            ('request_approved', 'Request Approved'),
            ('request_rejected', 'Request Rejected'),
            ('assignment_ready', 'Assignment Ready'),
            ('export_notification', 'Export Notification'),
        ]
    )
    sent_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20, 
        choices=[('sent', 'Sent'), ('failed', 'Failed')],
        default='sent'
    )
    error_message = models.TextField(blank=True)
    
    class Meta:
        db_table = 'email_logs'
        ordering = ['-sent_at']

    def __str__(self):
        return f"Email to {self.recipient} - {self.get_email_type_display()}"
