# Historical backend setup milestone — superseded

This filename records an earlier setup milestone, not a claim that the backend is production-ready. The old shared credentials, generic edit endpoints, and completion claims have been removed.

Use the [backend guide](README.md) for current API contracts and checks, [Getting started](../GETTING_STARTED.md) for Windows/Linux installation, and [production readiness](../docs/PRODUCTION_READINESS.md) for migration and deployment requirements.

Create your own administrator account with `manage.py createsuperuser`; no documented shared password should be used. Workflow mutations go through the application actions and remain read-only in Django administration. Verification results are maintained separately in [verification evidence](../docs/VERIFICATION.md).
