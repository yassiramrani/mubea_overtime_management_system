---
type: "query"
date: "2026-09-14T08:29:26.932784+00:00"
question: "What are the critical application workflow paths and production readiness gaps?"
contributor: "graphify"
outcome: "useful"
source_nodes: ["OvertimeRequestViewSet", "OvertimeRequest", "EmailLog", "ExportBatch", "PostgreSQLConcurrencyTests"]
---

# Q: What are the critical application workflow paths and production readiness gaps?

## Answer

Expanded from architecture query via graph vocabulary: authentication, token, permissions, request, assignment, export, notification, audit, concurrency, production. The graph identifies frontend role dashboards and API helpers; request decisions connect OvertimeRequestViewSet, OvertimeRequestSerializer, OvertimeRequest, AuditEvent, and OvertimeEmailService. Assignment and export share the request workflow and ExportBatch/SAPExport models. PostgreSQLConcurrencyTests covers simultaneous decisions, exports, and assignment/export races. Production settings and token expiration are separate configuration communities. AST graph cannot establish runtime HTTP wiring or prove production deployment readiness; source validation is required.

## Outcome

- Signal: useful

## Source Nodes

- OvertimeRequestViewSet
- OvertimeRequest
- EmailLog
- ExportBatch
- PostgreSQLConcurrencyTests