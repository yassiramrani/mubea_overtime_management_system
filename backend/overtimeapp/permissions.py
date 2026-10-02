"""
Custom permissions for Overtime Management System
"""
from rest_framework.permissions import BasePermission
from .access import user_role


class IsHeadManagerOrAdmin(BasePermission):
    """Permission for head managers and admins"""
    
    def has_permission(self, request, view):
        return user_role(request.user) in ['head_manager', 'admin']


class IsHRManagerOrAdmin(BasePermission):
    """Permission for HR managers and admins"""
    
    def has_permission(self, request, view):
        return user_role(request.user) in ['hr_manager', 'admin']


class IsDeptManagerOrAdmin(BasePermission):
    """Permission for department managers and admins"""
    
    def has_permission(self, request, view):
        return user_role(request.user) in ['dept_manager', 'admin']


class IsRequestOwnerOrHeadManager(BasePermission):
    """Permission for request owner or head manager"""
    
    def has_object_permission(self, request, view, obj):
        role = user_role(request.user)
        return role in ['head_manager', 'admin'] or (role == 'dept_manager' and obj.requester == request.user)
