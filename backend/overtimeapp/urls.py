"""
URL routing for Overtime Management System API
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Create a router and register our viewsets
router = DefaultRouter()
router.register(r'users', views.UserViewSet, basename='user')
router.register(r'profiles', views.UserProfileViewSet, basename='profile')
router.register(r'requests', views.OvertimeRequestViewSet, basename='overtime-request')
router.register(r'assignments', views.EmployeeAssignmentViewSet, basename='employee-assignment')
router.register(r'sap-exports', views.SAPExportViewSet, basename='sap-export')
router.register(r'export-batches', views.ExportBatchViewSet, basename='export-batch')
router.register(r'email-logs', views.EmailLogViewSet, basename='email-log')
router.register(r'admin/accounts', views.AdminAccountViewSet, basename='admin-account')

# The API URLs are determined automatically by the router
urlpatterns = [
    path('', include(router.urls)),
]
