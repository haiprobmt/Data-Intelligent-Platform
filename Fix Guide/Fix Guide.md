Critical gaps to address
1. Authentication is not production-ready

Tenant isolation is based only on X-Tenant-Id header. Anyone can change the header and access another tenant’s data.

Need to add:

Login
JWT/session auth
Tenant membership validation
RBAC
Entra ID / Google OAuth later
2. No real secret management yet

The README says credentials should use env://, and the connector rejects raw credentials, which is good.

But kv://, vault://, and secret:// are not implemented.

Need to add:

Azure Key Vault integration
Secret per tenant
Secret rotation
Credential test without exposing value
3. Metadata scan is too basic

The scanner captures table/column metadata and basic PK/FK flags.

But it does not capture:

indexes
views
stored procedures
relationships as first-class objects
lineage
constraints
source freshness
sample statistics
owner/steward info

Need to add: proper metadata model and relationship extraction.

4. Profiling is not scalable

Profiling currently runs COUNT, COUNT DISTINCT, and null count per column.

For large client databases, this can be very slow and expensive.

Need to add:

sampling mode
row limit
timeout
profiling config per table
async worker queue
database-safe query generation
avoid scanning every column by default
5. Data quality scoring is artificial

The quality score is calculated from issue count, not actual data quality dimensions.

Need to replace with real scoring:

Completeness = based on null %
Uniqueness = based on duplicate/distinct ratio
Freshness = based on update timestamp / max date
Validity = based on rules
Consistency = based on cross-table checks
6. Document extraction does not read document content

This is the biggest issue for the unstructured data vision.

The document extraction prompt only sends the file name, document type, and columns to Bedrock, not the actual file text/content.

The prompt even says if file contents are unavailable, return “Requires review.”

Need to add:

PDF parsing
OCR
Azure Document Intelligence / Textract
extracted text storage
page-level references
table extraction
confidence per field
human correction UI
7. Knowledge graph is not real yet

Neo4j exists in Docker Compose, but the graph service builds temporary JSON from PostgreSQL only.

Need to add:

actual Neo4j writes
graph schema
nodes: System, Table, Column, Entity, KPI, Report, Issue
relationships: CONTAINS, REPRESENTS, IMPACTS, DEPENDS_ON
Cypher queries
graph visualization
8. Recommendations are mostly rule/template based

Platform choice is currently:

if total_rows > 2_000_000 or "stream" in table_names:
    return "Databricks"
return "Microsoft Fabric"

This is too simple.

Need to include:

existing Microsoft/Power BI usage
data volume
transformation complexity
real-time requirement
AI/RAG requirement
team skillset
budget
governance maturity
9. POC generation is only placeholder assets

The POC generator creates a Mermaid diagram, notebook template, semantic model markdown, and AI/RAG text.

Good start, but not deployable.

Need to generate real assets:

Fabric pipeline JSON
Fabric notebook
Lakehouse/Warehouse DDL
Databricks notebook
Delta table DDL
dbt models
Power BI semantic model template
deployment ZIP
10. Background jobs are local only

Jobs use FastAPI BackgroundTasks.

This is okay for local MVP, but not for production.

Need to replace with:

Celery + Redis
or Temporal
retry policy
cancellation
progress percentage
job logs
worker scaling
Priority fix list
Must fix first
Real auth + tenant authorization
Real document content extraction
Proper metadata model
Scalable profiling
Real job queue
Neo4j-backed knowledge graph
Then improve
Better recommendation scoring
Real POC asset generation
Audit/security hardening
Deployment pipeline