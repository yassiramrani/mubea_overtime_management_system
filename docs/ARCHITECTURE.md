# System Architecture & Workflow

## Component Diagram

```mermaid
graph TB
    DM["📊 Dept Manager<br/>Dashboard"]
    HM["✅ Head Manager<br/>Dashboard"]
    HR["👥 HR Manager<br/>Dashboard"]
    
    API["Django REST API<br/>Backend"]
    DB[(PostgreSQL<br/>Database)]
    EMAIL["📧 Email Service<br/>SMTP"]
    SAP["🔗 SAP System"]
    
    DM -->|Request| API
    HM -->|Approve/Reject| API
    HR -->|Assign Team| API
    
    API -->|Read/Write| DB
    API -->|Send Email| EMAIL
    EMAIL -->|Notify| DM
    EMAIL -->|Notify| HM
    EMAIL -->|Notify| HR
    
    HR -->|Export CSV| SAP
    
    DB -->|Query| API
```

## Overtime Request Workflow

```mermaid
sequenceDiagram
    participant DM as Dept Manager
    participant HM as Head Manager
    participant HR as HR Manager
    participant DB as Database
    participant EMAIL as Email Service
    participant SAP as SAP System

    DM->>DB: 1. Submit OT Request
    DB->>EMAIL: Trigger notification
    EMAIL->>HM: 2. Email: New Request Pending
    
    HM->>DB: 3. Review & Approve
    DB->>EMAIL: Trigger approval
    EMAIL->>HR: 4. Email: Assignment Needed
    EMAIL->>DM: Email: Request Status
    
    HR->>DB: 5. Assign Employees
    DB->>EMAIL: Trigger assignment
    EMAIL->>DM: 6. Email: Team Assigned
    
    DM->>DB: View assigned team in dashboard
    
    HR->>DB: 7. Prepare SAP Export
    HR->>SAP: 8. Export CSV Data
    SAP->>DB: Confirm receipt
```

## Data Flow

1. **Request Submission** → OvertimeRequest created
2. **Notification to Head Manager** → Email sent, status = 'pending'
3. **Approval** → OvertimeRequest.status = 'approved', approved_by set
4. **Assignment Phase** → EmployeeAssignment created
5. **HR Assignment** → Employees assigned via ManyToMany
6. **Notification to Dept Manager** → Email with team details
7. **SAP Export** → CSV generated and sent, SAPExport record created
8. **Dashboard Update** → All roles see updated request status

## User Permissions

| Action | Dept Manager | Head Manager | HR Manager | Admin |
|--------|:------------:|:------------:|:----------:|:-----:|
| Submit Request | ✅ | ❌ | ❌ | ✅ |
| View Requests | Own Only | All | All | All |
| Approve/Reject | ❌ | ✅ | ❌ | ✅ |
| Assign Employees | ❌ | ❌ | ✅ | ✅ |
| Export CSV | ❌ | ❌ | ✅ | ✅ |
| View Audit Log | ❌ | ✅ | ✅ | ✅ |

## API Response Status Codes

- `201` - Request created successfully
- `200` - Request approved/rejected
- `400` - Validation error
- `401` - Unauthorized
- `403` - Permission denied
- `404` - Request not found
- `500` - Server error
