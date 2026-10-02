# Frontend setup guide — consolidated

The frontend already exists and uses React, TypeScript, and Vite. The former scaffolding guide is superseded by:

- [Getting started](../GETTING_STARTED.md): Windows/Linux installation, manager accounts, and a local workflow.
- [Frontend guide](README.md): `npm ci`, `npm run dev`, build configuration, and isolated browser verification.
- [Production readiness](../docs/PRODUCTION_READINESS.md): deployment requirements and remaining phases.

Use the supplied package manifest and lockfile. There is no frontend scaffolding step. Current login uses usernames and expiring tokens; MFA and cookie-based sessions are planned Phase 2 work.
