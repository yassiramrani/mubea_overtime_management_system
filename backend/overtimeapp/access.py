"""Shared application roles and employee eligibility rules."""
from django.contrib.auth.models import User

from .models import UserProfile


def user_role(user):
    if not user.is_authenticated or not user.is_active:
        return None
    if user.is_superuser:
        return 'admin'
    try:
        return user.profile.role
    except UserProfile.DoesNotExist:
        return None


def eligible_employees():
    return User.objects.filter(is_active=True, is_staff=False, is_superuser=False).exclude(profile__role='admin')


def is_eligible_employee(user):
    return user.is_active and not user.is_staff and not user.is_superuser and user_role(user) != 'admin'


def account_role(user):
    """Effective role for account management, with plain accounts reported as employees.

    Unlike ``user_role`` this ignores the active flag so administrators can see and
    restore deactivated accounts.
    """
    if user.is_superuser:
        return 'admin'
    try:
        return user.profile.role
    except UserProfile.DoesNotExist:
        return 'employee'
