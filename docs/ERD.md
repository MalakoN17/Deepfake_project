# Database design (ERD)

```mermaid
erDiagram
    USERS ||--o{ MEETINGS : "runs"
    USERS ||--o{ AUDIT_LOGS : "generates"
    USERS ||--o{ ALERTS : "handles"
    USERS ||--o{ REFERENCE_IDENTITIES : "creates"
    REFERENCE_IDENTITIES ||--o{ MEETINGS : "is claimed in"
    MEETINGS ||--o{ ANALYSES : "contains"
    ANALYSES ||--o{ ALERTS : "raises"

    USERS {
        int user_id PK
        string name
        string email UK
        string password_hash
        string role "admin / analyst"
        datetime created_at
        int failed_logins
        datetime locked_until
        datetime last_login_at
    }
    REFERENCE_IDENTITIES {
        int identity_id PK
        string full_name
        string job_title
        string image_filename
        blob embedding "128 float32"
        int created_by FK
        datetime created_at
    }
    MEETINGS {
        int meeting_id PK
        int user_id FK
        int claimed_identity_id FK "nullable"
        string meeting_name
        string platform "Zoom / Teams / Webcam / Upload"
        string source_type "upload / webcam / screen"
        datetime start_time
        datetime end_time
        string status "active / completed / failed"
        float first_score_ms
    }
    ANALYSES {
        int analysis_id PK
        int meeting_id FK
        datetime timestamp
        int frames_analyzed
        int faces_detected
        float deepfake_score "0-100"
        float identity_match_score "0-100, nullable"
        float quality_score "0-100"
        float trust_score "0-100"
        string result "Approved / Suspicious / Rejected"
        string reasons
        float capture_ms
        float face_ms
        float inference_ms
        float processing_time_ms
        float cpu_percent
        float ram_mb
        string model_name
    }
    ALERTS {
        int alert_id PK
        int analysis_id FK
        datetime timestamp
        string severity "Warning / High / Critical"
        string message
        string status "Open / Acknowledged / Escalated / Resolved"
        int handled_by FK "nullable"
        datetime handled_at
    }
    AUDIT_LOGS {
        int log_id PK
        int user_id FK "nullable"
        datetime timestamp
        string event
        string ip_address
        string details
    }
```

## How the ERD supports the system

- **Users -> Meetings (1:N).** Every monitored session belongs to the analyst who ran it, which gives accountability.
- **Meetings -> Analyses (1:N).** An uploaded video produces one analysis; a live session produces one analysis
  per window of 5 frames. This is how the system keeps a *timeline* of risk during a call (temporal analysis).
- **Analyses -> Alerts (1:N).** Alerts point to the exact evidence that raised them. The alert status and
  `handled_by` support the incident-response workflow (acknowledge, escalate for extra verification, resolve).
- **ReferenceIdentities -> Meetings (1:N).** The identity a participant claims to be; its stored face embedding is
  what the live face is compared with (identity verification requirement from the Problem Identification).
- **Latency columns** (`capture_ms`, `face_ms`, `inference_ms`, `processing_time_ms`, `first_score_ms`, CPU, RAM)
  turn the real-time requirement into measured evidence.
- **AuditLogs** record security events (sign-ins, failures, lockouts, alert handling, exports) for investigation.
- `quality_score` and `reasons` make every decision explainable: the system states *why* a result was not Approved.
