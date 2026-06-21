# Data Intelligent Platform — Repository Re-Assessment & Fix Guide

Repository assessed: `haiprobmt/Data-Intelligent-Platform`  
Assessment date: 2026-06-21  
Document purpose: clear implementation guide for remaining fixes after the latest repository update.

---

## 1. Executive Summary

The repository has improved significantly compared with the previous assessment.

The current codebase is no longer just a simple scaffold. It now includes:

- JWT login
- Tenant membership validation
- Basic RBAC
- Source registration
- Structured file upload
- Metadata scan
- Index / relationship / view metadata models
- Bounded profiling configuration
- Document text extraction before AI extraction
- Job logs and cancellation flag
- Neo4j sync hook
- Recommendation and POC asset generation

However, it is still not yet production-ready as a SaaS platform.

Current maturity estimate:

```text
Previous state: 35-40% of MVP
Current state: 55-60% of MVP
```

The remaining work is mainly around:

1. Production-grade authentication and authorization
2. Secure multi-tenant secret handling
3. Safe and scalable source-system scanning
4. Stronger profiling and quality rules
5. Real document intelligence/OCR
6. Real Neo4j graph persistence and querying
7. Proper async job backend
8. Real deployable Fabric/Databricks/Power BI assets
9. Testing, CI/CD, and migration framework

---

## 2. What Has Improved

### 2.1 Authentication and RBAC

The API now includes:

- Login endpoint
- Token generation
- Token decoding
- Tenant membership validation
- Role hierarchy: `viewer`, `analyst`, `admin`

This is a major improvement from the previous `X-Tenant-Id` only approach.

Current role model:

```python
ROLE_ORDER = {"viewer": 0, "analyst": 1, "admin": 2}
```

### 2.2 Metadata Model

The metadata model now includes:

- `MetadataTable`
- `MetadataColumn`
- `MetadataIndex`
- `MetadataRelationship`
- `MetadataView`
- `MetadataProcedure`

This is closer to the target Enterprise Data Intelligence Hub design.

### 2.3 Document Extraction

The document flow now stores:

- `file_path`
- `extracted_text`
- `extraction_metadata`
- `extracted_fields`
- `confidence_score`

The document extraction service now reads file content before invoking Bedrock.

### 2.4 Profiling

Profiling now uses a `ProfileConfig` with:

- `row_limit`
- `max_columns`
- `timeout_seconds`

This is better than scanning every column across the full source table.

### 2.5 Job Tracking

Jobs now include:

- `progress_percent`
- `cancel_requested`
- `JobLog`

This is good for the portal experience.

### 2.6 Neo4j Sync Hook

Neo4j sync has been added and can push basic source/table/entity relationships into Neo4j when Neo4j settings are configured.

### 2.7 POC Asset Generation

The asset generator now produces more asset types:

- Architecture diagram
- Notebook template
- Power BI model markdown
- AI/RAG design
- Warehouse DDL
- Pipeline JSON
- dbt model

This is a good starting point for the POC generator.

---

## 3. Critical Issues to Fix

## P0 — Must Fix Before Showing to Real Clients

---

### 3.1 Replace Custom JWT Implementation With a Standard Library

#### Current Issue

The project manually builds and verifies JWT tokens using `hmac`, `base64`, and custom JSON encoding.

This works for a demo, but it is risky for production because JWT security has many edge cases:

- Algorithm handling
- Claims validation
- Expiry validation
- Issuer/audience validation
- Token revocation
- Key rotation
- Refresh tokens

#### Required Fix

Use a standard library:

```bash
pip install python-jose[cryptography] passlib[bcrypt]
```

or:

```bash
pip install PyJWT passlib[bcrypt]
```

#### Recommended Implementation

Create:

```text
apps/api/app/services/auth_tokens.py
```

Add:

```python
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError

ALGORITHM = "HS256"

def create_access_token(payload: dict, secret: str, ttl_minutes: int) -> str:
    data = payload.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
    data.update({"exp": expire})
    return jwt.encode(data, secret, algorithm=ALGORITHM)

def decode_access_token(token: str, secret: str) -> dict:
    try:
        return jwt.decode(token, secret, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise ValueError("Invalid token") from exc
```

#### Acceptance Criteria

- Token has `sub`, `email`, `tenant_id`, `role`, `exp`, `iat`
- Invalid token returns HTTP 401
- Expired token returns HTTP 401
- Token signed with wrong secret fails
- Unit tests cover all token paths

---

### 3.2 Enforce Strong JWT Secret Validation

#### Current Issue

The default config still contains:

```python
auth_jwt_secret = "change-this-secret"
```

If deployed accidentally, this is dangerous.

#### Required Fix

On startup:

- If environment is not local/dev
- And `AUTH_JWT_SECRET` is missing or equals `change-this-secret`
- Fail startup

#### Recommended Implementation

Add config:

```python
environment: str = "local"
```

Add validation:

```python
def validate_security_settings(settings):
    if settings.environment != "local":
        if settings.auth_jwt_secret in {"change-this-secret", "", None}:
            raise RuntimeError("AUTH_JWT_SECRET must be configured in non-local environments")
```

Call this in FastAPI startup.

#### Acceptance Criteria

- Local development can run
- Production cannot start with default secret
- README documents required production env vars

---

### 3.3 Fix Tenant-Scoped Key Vault Reference Validation

#### Current Issue

`validate_secret_reference_for_tenant()` currently checks whether the tenant ID appears inside the secret reference string.

That is brittle because Azure Key Vault secret names may not contain the application tenant UUID.

#### Current Risk

Valid enterprise Key Vault references may be rejected.

Example:

```text
kv://client-prod-kv/sql-prod-readonly
```

This may not include the SaaS `tenant_id`, but it can still be valid if the tenant owns that secret metadata.

#### Required Fix

Create a proper `tenant_secrets` table or `connection_secrets` table.

#### Suggested Model

```python
class ConnectionSecret(Base):
    __tablename__ = "connection_secrets"

    id = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id = mapped_column(String(36), index=True, nullable=False)
    name = mapped_column(String(180), nullable=False)
    provider = mapped_column(String(40), nullable=False)  # env, azure_key_vault
    reference = mapped_column(String(500), nullable=False)
    created_at = mapped_column(DateTime, default=datetime.utcnow)
```

Then source systems should reference:

```text
secret_id
```

not raw `kv://...`.

#### Acceptance Criteria

- A tenant can only use secrets registered under its tenant
- Source system stores `secret_id`
- Secret value is never exposed through API
- Admin can test connection without seeing credential

---

### 3.4 Replace `Base.metadata.create_all()` and SQLite Schema Compatibility With Alembic

#### Current Issue

The API uses:

```python
Base.metadata.create_all(bind=engine)
ensure_schema_compat(engine)
```

This is acceptable for local prototyping, but not for SaaS.

#### Problems

- No controlled migrations
- No rollback
- SQLite compatibility patches only
- Hard to maintain as schema grows
- Production database changes become risky

#### Required Fix

Add Alembic.

#### Commands

```bash
pip install alembic
alembic init migrations
```

Create migration files for:

- users
- tenants
- tenant_memberships
- source_systems
- metadata tables
- documents
- jobs
- job_logs
- recommendations
- poc_assets
- audit_logs

#### Acceptance Criteria

- App no longer calls `create_all()` in production
- Alembic migration can create the full schema from empty PostgreSQL
- Migration can upgrade from current local schema
- README includes migration commands

---

### 3.5 Stop Counting Full Rows During Metadata Scan

#### Current Issue

The SQLAlchemy connector still calculates row count using:

```python
SELECT COUNT(*) FROM table
```

during metadata discovery.

For large Oracle, SQL Server, PostgreSQL, or MySQL sources, this can be slow and intrusive.

#### Required Fix

Use approximate row counts where possible.

#### Recommended Strategy

| Database | Row Count Source |
|---|---|
| PostgreSQL | `pg_class.reltuples` |
| SQL Server | `sys.dm_db_partition_stats` |
| Oracle | `ALL_TABLES.NUM_ROWS` |
| MySQL | `information_schema.tables.TABLE_ROWS` |
| SQLite | exact count is acceptable |

#### Add Scan Mode

```python
scan_mode: Literal["metadata_only", "light_profile", "full_profile"]
```

Default should be:

```text
metadata_only
```

#### Acceptance Criteria

- Metadata scan does not run full `COUNT(*)` by default
- User can explicitly request accurate row count
- Timeout is respected
- Scan results show whether row count is approximate

---

### 3.6 Fix Profiling Timeout Implementation

#### Current Issue

The code uses:

```python
connection.execution_options(timeout=config.timeout_seconds)
```

SQLAlchemy does not consistently enforce this timeout across all DB drivers.

#### Required Fix

Implement dialect-specific timeout or application-level cancellation.

Examples:

#### PostgreSQL

```sql
SET statement_timeout = '30000';
```

#### SQL Server

Use driver/query timeout configuration.

#### Oracle

Use driver-level call timeout if supported.

#### Application Layer

Run profiling query with timeout wrapper and fail gracefully.

#### Acceptance Criteria

- Long profiling query stops within configured timeout
- Timeout creates a `DataQualityIssue` or job warning
- Job does not hang indefinitely

---

### 3.7 Fix Job Cancellation Behavior

#### Current Issue

Job cancellation flag exists, but long-running functions do not consistently call `update_job_progress()` or check cancellation.

#### Required Fix

Pass `job_id` into:

- `run_metadata_scan`
- `run_profile`
- document extraction
- agent analysis

Call cancellation checks between tables.

#### Example

```python
update_job_progress(db, tenant_id, job_id, 30, "Scanning table customer_master")
```

#### Acceptance Criteria

- User can cancel a running scan
- Scan stops after current table or current safe checkpoint
- Job status becomes `cancelled`
- Partial results are clearly marked

---

## 4. High Priority Fixes

## P1 — Needed for a Trustworthy MVP

---

### 4.1 Improve Business Pain Point Mapping

#### Current Issue

`build_pain_points()` still uses placeholders:

```python
"affected_systems": ["Contoso ERP"]
"affected_entities": ["Customer", "Invoice", "Funding"]
```

This should be dynamic.

#### Required Fix

Join:

- `DataQualityIssue`
- `MetadataTable`
- `SourceSystem`
- `MetadataColumn`
- `detected_entity`

#### Output Example

```json
{
  "pain_point": "customer_master has no declared primary key",
  "severity": "High",
  "affected_systems": ["Oracle ERP"],
  "affected_entities": ["Customer"],
  "affected_tables": ["customer_master"],
  "business_impact": "Customer duplication may affect Customer 360 and sales reporting.",
  "recommended_action": "Define durable business key before Silver model."
}
```

#### Acceptance Criteria

- No hardcoded `Contoso ERP`
- Affected system comes from actual source system
- Affected entity comes from `MetadataTable.detected_entity`
- Column-level issue includes the column name

---

### 4.2 Improve Graph IDs and Relationships

#### Current Issue

Graph lineage edges use table names for relationships:

```python
edges.append({"from": relationship.from_table, "to": relationship.to_table})
```

But other graph nodes use table IDs.

This can break graph visualization because edge IDs do not match node IDs.

#### Required Fix

Store table IDs in `MetadataRelationship`.

Update model:

```python
from_table_id
to_table_id
```

or resolve names to IDs when building graph output.

#### Acceptance Criteria

- Every graph edge `from` and `to` refers to a real node ID
- Graph visualization renders all relationships
- Relationships are tenant-scoped
- Same table name in different schemas does not collide

---

### 4.3 Fix Neo4j Tenant Isolation and Table Name Collision

#### Current Issue

Neo4j sync matches relationships using:

```cypher
MATCH (from_table:Table {name: $from_table})
MATCH (to_table:Table {name: $to_table})
```

This can incorrectly link tables across tenants or schemas.

#### Required Fix

Always include:

- `tenant_id`
- `source_system_id`
- `schema_name`
- `table_name`
- internal table ID

Recommended Cypher:

```cypher
MATCH (from_table:Table {tenant_id: $tenant_id, id: $from_table_id})
MATCH (to_table:Table {tenant_id: $tenant_id, id: $to_table_id})
MERGE (from_table)-[:DEPENDS_ON {type: $relationship_type}]->(to_table)
```

#### Acceptance Criteria

- Tables from different tenants cannot link
- Same table name in different schemas works
- Same table name in different source systems works

---

### 4.4 Add Real File Size and Type Limits

#### Current Issue

Uploaded files are saved directly after reading the full content:

```python
content = await file.read()
stored_path.write_bytes(content)
```

This can cause memory issues and security concerns.

#### Required Fix

Add:

- max file size
- extension validation
- MIME type validation
- streaming write
- virus scanning hook
- upload quota per tenant

#### Suggested Settings

```python
max_upload_size_mb: int = 50
allowed_document_extensions: set[str]
allowed_source_extensions: set[str]
```

#### Acceptance Criteria

- 0-byte file rejected
- oversized file rejected
- unsupported extension rejected
- file saved through streaming chunks
- upload path cannot escape tenant folder

---

### 4.5 Support Scanned PDF / OCR

#### Current Issue

PDF extraction uses `pypdf`, which only works well for text-based PDFs.

For scanned PDFs, `page.extract_text()` will return empty or poor text.

#### Required Fix

Add OCR provider abstraction.

```python
class OcrProvider:
    def extract(self, file_path: str) -> DocumentExtractionResult:
        ...
```

Provider options:

- Azure Document Intelligence
- AWS Textract
- Tesseract for local dev

#### Acceptance Criteria

- Text-based PDF works through `pypdf`
- Scanned PDF routes to OCR provider
- Output includes page number and confidence
- Extracted fields include evidence/reference

---

### 4.6 Store Field-Level Confidence and References

#### Current Issue

The Bedrock prompt asks for:

```json
field_confidence
references
```

But the model only stores `extracted_fields` and global `confidence_score`.

#### Required Fix

Extend `Document` model or add child table:

```python
class DocumentExtractedField(Base):
    document_id
    field_name
    value
    confidence
    reference
    page_number
    reviewed_value
    review_status
```

#### Acceptance Criteria

- Each extracted field has confidence
- Each extracted field has source reference
- User can approve/correct each field
- Approved structured output uses reviewed value

---

### 4.7 Add Human Review Update Endpoint

#### Current Issue

Documents can be approved, but there is no clear endpoint to update corrected extracted fields before approval.

#### Required Endpoint

```http
PATCH /api/documents/{document_id}/extraction-result
```

Request:

```json
{
  "fields": {
    "funder_name": "ABC Foundation",
    "approved_funding_fy25": "100000"
  }
}
```

#### Acceptance Criteria

- Analyst can correct extraction
- Correction is audited
- Approval uses corrected values
- Original extraction is retained for traceability

---

### 4.8 Improve Platform Recommendation Logic

#### Current Issue

Platform choice is still mostly heuristic:

- table names
- total row count
- number of tables
- detected entity type

This is better than before, but still incomplete.

#### Required Fix

Create an assessment questionnaire and scoring model.

Add fields:

- current Microsoft 365 usage
- current Power BI usage
- current Databricks usage
- data volume
- streaming requirement
- ML/AI requirement
- budget sensitivity
- engineering maturity
- governance maturity
- deployment preference

#### Suggested API

```http
POST /api/assessment/profile
```

#### Example Output

```json
{
  "fabric_score": 82,
  "databricks_score": 74,
  "recommended_platform": "Microsoft Fabric",
  "reasoning": [
    "Existing Power BI adoption",
    "Moderate data volume",
    "Business dashboard priority"
  ]
}
```

#### Acceptance Criteria

- Recommendation is explainable
- User inputs affect recommendation
- Recommendation includes both score and reason
- Report shows trade-offs

---

## 5. Medium Priority Fixes

## P2 — Needed Before Paid Pilot

---

### 5.1 Add Real Source Connectors Beyond SQLAlchemy

SQLAlchemy is useful, but enterprise systems need connector-specific handling.

#### Add Dedicated Connectors

| Connector | Priority |
|---|---|
| PostgreSQL | High |
| SQL Server | High |
| Oracle | High |
| Fabric Warehouse | High |
| Databricks SQL Warehouse | High |
| SharePoint / OneDrive | Medium |
| Power BI metadata | Medium |
| Odoo | Medium |
| Salesforce | Later |

Each connector should implement:

```python
list_tables()
list_columns()
list_relationships()
list_views()
list_indexes()
profile_columns()
test_connection()
```

---

### 5.2 Add Power BI Metadata Scanner

This product is about Fabric/Databricks/Power BI/AI POC acceleration.

Power BI scanner is important.

#### Capture

- Workspaces
- Datasets / semantic models
- Reports
- Tables
- Measures
- Data sources
- Refresh status
- Owners
- Lineage where available

#### Output

Map Power BI reports back to:

- source tables
- KPIs
- business entities
- pain points

---

### 5.3 Add Fabric and Databricks Deployment Integrations

Current POC assets are text templates.

For the real product, add deploy actions.

#### Fabric

- create workspace
- create lakehouse
- create warehouse
- upload notebook
- create pipeline
- create semantic model template

#### Databricks

- create catalog/schema
- create Delta tables
- upload notebooks
- create workflow job
- create SQL dashboard template

---

### 5.4 Add Report Export

Current report download returns JSON.

Add:

- Markdown report
- PDF report
- DOCX report
- ZIP package export

Suggested endpoints:

```http
GET /api/reports/{id}/download?format=md
GET /api/reports/{id}/download?format=pdf
GET /api/poc-assets/download.zip
```

---

### 5.5 Add Tests

The repository needs tests before it grows further.

#### Required Test Areas

```text
tests/
├── test_auth.py
├── test_tenant_isolation.py
├── test_source_systems.py
├── test_file_uploads.py
├── test_metadata_scan.py
├── test_profile_scores.py
├── test_document_extraction.py
├── test_graph.py
├── test_recommendations.py
└── test_jobs.py
```

#### Minimum Acceptance

- Auth tests
- Tenant isolation tests
- Scan/profile happy path
- Document extraction happy path
- Graph edge consistency
- Recommendation generation fallback

---

## 6. Lower Priority Fixes

## P3 — Product Polish

---

### 6.1 Improve Frontend User Journey

The portal should guide users through:

```text
Create Assessment
→ Connect Systems
→ Upload Documents
→ Run Discovery
→ Review Findings
→ Generate Recommendations
→ Generate POC Assets
→ Export Report
```

Add visual status per step.

---

### 6.2 Add Assessment Project Entity

Currently the system is tenant-centric.

Add a project/assessment concept:

```python
class AssessmentProject(Base):
    id
    tenant_id
    name
    industry
    primary_goal
    status
    created_at
```

Then link:

- source systems
- documents
- scans
- recommendations
- POC assets
- reports

This is important because one tenant may run multiple assessments.

---

### 6.3 Add Data Sensitivity Detection

Add detection for:

- email
- phone
- NRIC / national ID
- passport
- credit card
- bank account
- address
- salary
- health data

Use this for AI readiness and governance assessment.

---

### 6.4 Add LLM Cost Tracking

Track:

- model
- prompt tokens
- completion tokens
- estimated cost
- tenant ID
- job ID
- endpoint

Create table:

```python
class LlmUsageLog(Base):
    tenant_id
    model
    prompt_tokens
    completion_tokens
    estimated_cost
    purpose
    created_at
```

---

## 7. Suggested Implementation Order

## Sprint 1 — Stabilize Security and Data Model

1. Replace custom JWT with standard library
2. Enforce strong JWT secret
3. Add Alembic migrations
4. Add `AssessmentProject`
5. Add proper secret registry table

## Sprint 2 — Make Discovery Safe

1. Replace exact row count with approximate row count
2. Add scan modes
3. Improve profiling timeout handling
4. Add job cancellation checkpoints
5. Add tests for scan/profile

## Sprint 3 — Fix Pain Points and Graph

1. Dynamic pain point mapping
2. Fix graph node/edge ID consistency
3. Fix Neo4j tenant isolation
4. Add graph query tests
5. Add graph visualization cleanup

## Sprint 4 — Improve Document Intelligence

1. Add OCR provider abstraction
2. Add scanned PDF support
3. Store field confidence and references
4. Add human correction endpoint
5. Add structured export to CSV/Delta-ready format

## Sprint 5 — Improve Recommendations and POC Assets

1. Add assessment questionnaire
2. Replace heuristic platform selection with scoring model
3. Generate real Fabric templates
4. Generate real Databricks templates
5. Generate Markdown/PDF/DOCX report

---

## 8. Immediate Code Fix Checklist

Use this as a practical checklist.

### Backend

- [ ] Add `environment` setting
- [ ] Fail startup if JWT secret is default in non-local env
- [ ] Replace custom JWT implementation
- [ ] Add Alembic migrations
- [ ] Add `AssessmentProject` model
- [ ] Add `ConnectionSecret` model
- [ ] Replace source `secret_reference` with secret registry reference
- [ ] Add upload size limit
- [ ] Add streaming upload write
- [ ] Add OCR provider interface
- [ ] Add field-level extraction table
- [ ] Add document correction endpoint
- [ ] Add approximate row count per dialect
- [ ] Add scan modes
- [ ] Add job cancellation checks inside scan/profile loops
- [ ] Fix dynamic pain-point mapping
- [ ] Fix graph edge IDs
- [ ] Fix Neo4j tenant scoping
- [ ] Add report export formats
- [ ] Add LLM usage logging

### Frontend

- [ ] Add login page
- [ ] Store token securely
- [ ] Add assessment project creation page
- [ ] Add source connection wizard
- [ ] Add document review screen
- [ ] Add job progress/log screen
- [ ] Add graph explorer
- [ ] Add recommendation review screen
- [ ] Add POC asset download screen
- [ ] Add report export button

### DevOps

- [ ] Add `.env.example`
- [ ] Add Alembic migration command to README
- [ ] Add GitHub Actions CI
- [ ] Add backend tests
- [ ] Add frontend build check
- [ ] Add Docker health checks
- [ ] Add production deployment notes

---

## 9. Recommended GitHub Issues to Create

### Issue 1

Title:

```text
Replace custom JWT implementation with python-jose and enforce production secret validation
```

Labels:

```text
security, backend, p0
```

### Issue 2

Title:

```text
Introduce Alembic migrations and remove create_all from production startup
```

Labels:

```text
database, backend, p0
```

### Issue 3

Title:

```text
Implement tenant-scoped connection secret registry
```

Labels:

```text
security, multi-tenant, p0
```

### Issue 4

Title:

```text
Replace exact row count with approximate row count and scan modes
```

Labels:

```text
connector, performance, p0
```

### Issue 5

Title:

```text
Fix pain point generation to use actual source systems and detected entities
```

Labels:

```text
assessment, backend, p1
```

### Issue 6

Title:

```text
Fix graph edge IDs and Neo4j tenant isolation
```

Labels:

```text
knowledge-graph, backend, p1
```

### Issue 7

Title:

```text
Add OCR provider abstraction and scanned PDF support
```

Labels:

```text
document-ai, p1
```

### Issue 8

Title:

```text
Add human review correction endpoint for extracted document fields
```

Labels:

```text
document-ai, frontend, backend, p1
```

### Issue 9

Title:

```text
Add assessment questionnaire and explainable Fabric/Databricks scoring model
```

Labels:

```text
recommendation-engine, product, p1
```

### Issue 10

Title:

```text
Generate downloadable Markdown/PDF/DOCX assessment report
```

Labels:

```text
reporting, p2
```

---

## 10. Updated Maturity Score

| Area | Previous | Current | Target MVP |
|---|---:|---:|---:|
| Auth / RBAC | 10% | 55% | 80% |
| Tenant isolation | 25% | 60% | 85% |
| Source connectors | 35% | 45% | 75% |
| Metadata discovery | 40% | 65% | 80% |
| Data profiling | 35% | 55% | 75% |
| Document intelligence | 20% | 50% | 75% |
| Knowledge graph | 25% | 45% | 75% |
| Recommendation engine | 35% | 50% | 75% |
| POC generation | 25% | 45% | 70% |
| Job orchestration | 30% | 50% | 80% |
| Reporting/export | 20% | 35% | 75% |
| Testing/CI | 0% | 0-10% | 75% |

Overall:

```text
Current maturity: 55-60% of MVP
Production SaaS readiness: 30-35%
Client-demo readiness: 65-70%
```

---

## 11. Final Recommendation

The updated repository is moving in the right direction.

The next milestone should not be adding more flashy AI features.

The next milestone should be:

```text
Make one complete client assessment flow trustworthy end-to-end.
```

Recommended demo scenario:

```text
1. Login as admin
2. Create assessment project
3. Connect PostgreSQL or SQL Server sample database
4. Upload one real PDF funding agreement
5. Run metadata scan
6. Run profiling
7. Extract document fields
8. Review/correct extraction
9. Generate dynamic pain points
10. Generate Fabric/Databricks recommendation
11. Export Markdown/PDF report
12. Download POC asset package
```

Once this works reliably, the product becomes much easier to sell as:

```text
From siloed data and manual documents to a working Fabric/Databricks/Power BI/AI POC blueprint in one week.
```
