# SKILL.md — Enterprise Data Intelligence Hub

## Project Overview

The **Enterprise Data Intelligence Hub** is a multi-tenant SaaS platform that connects to customer data systems, discovers data silos, profiles data quality, extracts structured information from unstructured documents, builds a business knowledge graph, and generates recommended Fabric/Databricks/Power BI/AI proof-of-concept assets.

**Core Value Proposition:** Reduce POC build time from weeks to days.

---

## Technology Stack

### Frontend
- **Framework:** Next.js (App Router)
- **UI Library:** React + Tailwind CSS + shadcn/ui
- **Graph Visualization:** React Flow (for knowledge graph and architecture diagrams)
- **Code/Diagram Editor:** Monaco Editor (for Mermaid source and generated code)

### Backend
- **API Framework:** Python FastAPI
- **ORM:** SQLAlchemy + Pydantic models
- **Job Queue:** Celery (MVP) or Temporal (production)
- **Cache/Queue Broker:** Redis

### Data Stores
| Store | Purpose |
|---|---|
| PostgreSQL | Metadata store, tenant data, scan results, profiling results, recommendations, job status, audit logs |
| Neo4j | Knowledge graph: entities, relationships, pain-point chains |
| Azure Blob Storage | Uploaded documents, generated reports, notebooks, deployment packages |
| Azure AI Search / pgvector | Vector store for document and metadata embeddings |

### AI Layer
- **LLM:** Azure OpenAI GPT-4.1 / GPT-4o
- **Agent Framework:** LangGraph (controlled workflows), CrewAI (multi-agent), Semantic Kernel (Microsoft ecosystem)
- **Document Intelligence:** Azure Document Intelligence
- **OCR fallback:** Tesseract / PaddleOCR
- **Document loaders:** LangChain, Unstructured.io, PyMuPDF

### Infrastructure
- **Containers:** Docker + Azure Container Apps (or Kubernetes)
- **Secrets:** Azure Key Vault
- **Storage:** Azure Storage Account
- **Registry:** Azure Container Registry
- **CI/CD:** GitHub Actions
- **IaC:** Terraform / Bicep

---

## Core Modules & How to Build Them

### 1. Connector Layer

**Purpose:** Securely connect to customer data sources.

**MVP Sources:**
- Structured: SQL Server, Oracle, PostgreSQL, MySQL, CSV, Excel
- Unstructured: PDF, Word, scanned docs, email attachments, SharePoint
- BI/Analytics: Power BI, Fabric, Databricks workspace metadata

**Implementation pattern:**
- Each connector is a Python class inheriting from a `BaseConnector` abstract class
- Connectors expose: `test_connection()`, `list_schemas()`, `list_tables()`, `get_column_metadata()`, `get_sample_rows()`
- Credentials are stored in Azure Key Vault; never in the app database
- Use Airbyte or OpenMetadata connectors where available; write custom Python otherwise
- REST API connectors: Microsoft Graph API, Fabric REST API, Databricks REST API

**Key rule:** Store credentials encrypted. Retrieve at runtime via Key Vault reference.

---

### 2. Metadata Discovery Engine

**Purpose:** Extract structural metadata from connected systems without pulling raw data.

**For each source system, capture:**
```
system_name, system_type, database_name, schema_name,
table_name, column_name, data_type, is_nullable,
is_primary_key, is_foreign_key, indexes, views,
stored_procedures, row_count, created_date, last_modified_date
```

**Core DB table:**
```sql
CREATE TABLE metadata_columns (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL,
  source_system_id UUID NOT NULL,
  database_name TEXT,
  schema_name TEXT,
  table_name TEXT,
  column_name TEXT,
  data_type TEXT,
  is_nullable BOOLEAN,
  is_primary_key BOOLEAN,
  is_foreign_key BOOLEAN,
  discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Output:** Results stored in PostgreSQL; optionally synced to OpenMetadata.

---

### 3. Data Profiling Engine

**Purpose:** Understand data quality and readiness for platform migration.

**Run these checks per table/column:**
```
row_count, null_percentage, distinct_count, duplicate_count,
min_value, max_value, average_value, pattern_detection,
date_freshness, potential_pk_detection, potential_fk_detection, cdc_readiness
```

**Issue types to detect:**
- Missing primary key
- Duplicate business key
- No last updated timestamp
- High null percentage (>20%)
- Inconsistent date format
- Manual Excel dependency
- No CDC column
- No data owner assigned

**Data quality score output:**
```json
{
  "completeness": 82,
  "uniqueness": 76,
  "freshness": 65,
  "consistency": 71,
  "overall": 74
}
```

---

### 4. Document Intelligence Engine

**Purpose:** Convert unstructured documents (PDF, Word, scanned forms) into structured database records.

**Supported document types:**
- Invoices, Contracts, Funding agreements, Application forms, Receipts, Purchase orders, PDF reports, Scanned forms

**Processing pipeline (implement as sequential steps):**
```
Document Upload → OCR / Layout Analysis → Text Extraction →
Table Extraction → Entity Extraction → Schema Mapping →
Confidence Scoring → Human Review UI → Structured Output Table
```

**Technology choices (in order of preference):**
1. Azure Document Intelligence — for structured forms and invoices
2. LangChain + Azure OpenAI — for freeform text extraction
3. Unstructured.io / PyMuPDF — for PDF parsing
4. Tesseract / PaddleOCR — for scanned/image PDFs

**Target schema example (user-defined per document type):**
```json
{
  "table_name": "funding_agreement",
  "columns": [
    "service_name", "program_name", "person_in_charge",
    "funder_name", "approved_funding_fy25", "approved_funding_fy26",
    "approved_funding_fy27", "total_funding"
  ]
}
```

**Human review requirement:** Always surface a confidence score; require human approval before writing to destination.

**Output destinations:** Fabric Lakehouse, Fabric Warehouse, Databricks Delta table, PostgreSQL, CSV/Excel export.

---

### 5. Business Entity Discovery Agent

**Purpose:** Infer real business entities (Customer, Supplier, Invoice, etc.) from raw technical metadata.

**Detection techniques (apply in combination):**
- Table name analysis (e.g., `res_partner`, `crm_customer`, `cust_dim` → Customer)
- Column name analysis
- Sample value analysis
- Foreign key relationship analysis
- LLM-based classification (send table/column names to GPT-4; ask for entity type)
- Business glossary matching
- Existing report/dashboard analysis

**Standard entity types to detect:**
Customer, Supplier, Product, Invoice, Order, Employee, Student, Funding, Asset, Service, Program, Contract

---

### 6. Knowledge Graph Hub

**Technology:** Neo4j (MVP); optionally Azure Cosmos DB Gremlin or PostgreSQL graph extension.

**Node types:**
```
Tenant, SourceSystem, Database, Schema, Table, Column,
BusinessEntity, BusinessProcess, KPI, Dashboard, Report,
DataOwner, DataQualityIssue, Recommendation, POCAsset
```

**Relationship types:**
```cypher
(SourceSystem)-[:CONTAINS]->(Table)
(Table)-[:HAS_COLUMN]->(Column)
(Table)-[:REPRESENTS]->(BusinessEntity)
(Column)-[:MAPS_TO]->(BusinessAttribute)
(Dashboard)-[:USES]->(Table)
(KPI)-[:DEPENDS_ON]->(Column)
(Issue)-[:AFFECTS]->(Table)
(Issue)-[:IMPACTS]->(KPI)
(Recommendation)-[:FIXES]->(Issue)
(POCAsset)-[:IMPLEMENTS]->(Recommendation)
```

**Graph query API endpoints:**
```
GET /api/graph/entities
GET /api/graph/entity/{id}
GET /api/graph/lineage/{entity_id}
GET /api/graph/issues
```

---

### 7. Agentic Reasoning Layer

**Framework:** LangGraph for orchestrated multi-step workflows.

**Agent roster:**

| Agent | Responsibilities |
|---|---|
| Data Architect Agent | Analyze silos, identify duplicates, recommend Fabric/Databricks pattern, generate target conceptual model |
| Data Engineer Agent | Recommend ingestion strategy, CDC approach, Bronze/Silver/Gold design, generate pipeline/notebook templates |
| BI Agent | Analyze reports, detect KPI dependencies, recommend semantic model, generate Power BI measures and dashboard layout |
| AI Readiness Agent | Identify RAG opportunities, recommend vector search design, recommend AI governance controls |
| Governance Agent | Identify missing owners/glossary/sensitive columns, recommend access control and stewardship workflow |

**LangGraph node sequence:**
```
metadata_scanner_node → profiler_node → document_extraction_node →
entity_discovery_node → knowledge_graph_builder_node →
painpoint_agent_node → recommendation_agent_node →
poc_generator_node → report_generator_node
```

---

### 8. Pain-Point Analysis Engine

**Purpose:** Translate technical data issues into business-language pain points.

**Output format per pain point:**
```json
{
  "pain_point": "Customer data is duplicated across ERP and CRM",
  "severity": "High",
  "affected_systems": ["Odoo", "Salesforce"],
  "affected_entities": ["Customer"],
  "business_impact": "Sales dashboard may show inaccurate customer count",
  "recommended_action": "Create centralized customer master in Silver layer"
}
```

---

### 9. Recommendation Engine

**Purpose:** Generate target architecture recommendation and implementation roadmap.

**Recommendation categories:**
- Fabric readiness
- Databricks readiness
- Power BI readiness
- AI readiness
- Data governance readiness
- Data quality readiness

**Decision logic (simplified):**
- Microsoft 365 + Power BI existing → recommend Fabric
- High data volume + complex ML + multi-cloud → recommend Databricks

---

### 10. POC Generation Engine

**Fabric assets to generate:**
Lakehouse structure, Warehouse schema, data pipeline design, notebook code, Dataflow template, Semantic model design, Power BI dashboard template, RAG architecture

**Databricks assets to generate:**
Unity Catalog structure, Delta table DDL, Bronze/Silver/Gold notebooks, Workflow job JSON, dbt model template, Power BI connection guide, Vector search design

**AI assets to generate:**
Document extraction prompt, RAG prompt, Vector index schema, Knowledge base design, Copilot architecture, Evaluation checklist

---

### 11. Delivery Portal

**Purpose:** Present findings and generated assets to clients and consultants.

**Dashboard sections:**
- Source systems overview
- Data quality scorecards per system
- Business entity map
- Pain points list (by severity)
- Platform recommendation (Fabric vs Databricks)
- Architecture diagram (Mermaid rendered)
- Generated POC assets (downloadable)
- Final assessment report (PDF)

**Mermaid diagram generation flow:**
```
Agent generates Mermaid source →
Mermaid rendered in UI (via Monaco Editor or mermaid.js) →
Consultant edits if needed →
Export as PNG / SVG / PDF / draw.io
```

---

## Database Schema (Core Tables)

```sql
-- Tenants
CREATE TABLE tenants (
  id UUID PRIMARY KEY,
  name TEXT NOT NULL,
  industry TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Source Systems
CREATE TABLE source_systems (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL,
  name TEXT NOT NULL,
  system_type TEXT NOT NULL,
  connection_type TEXT,
  status TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Metadata Tables
CREATE TABLE metadata_tables (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL,
  source_system_id UUID NOT NULL,
  database_name TEXT,
  schema_name TEXT,
  table_name TEXT,
  row_count BIGINT,
  detected_entity TEXT,
  discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Metadata Columns
CREATE TABLE metadata_columns (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL,
  table_id UUID NOT NULL,
  column_name TEXT NOT NULL,
  data_type TEXT,
  is_nullable BOOLEAN,
  is_primary_key BOOLEAN,
  is_foreign_key BOOLEAN,
  null_percentage NUMERIC,
  distinct_count BIGINT,
  sample_values JSONB,
  discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Data Quality Issues
CREATE TABLE data_quality_issues (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL,
  table_id UUID,
  column_id UUID,
  issue_type TEXT,
  severity TEXT,
  description TEXT,
  recommendation TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Recommendations
CREATE TABLE recommendations (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL,
  category TEXT,
  title TEXT,
  description TEXT,
  priority TEXT,
  estimated_effort TEXT,
  business_value TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- POC Assets
CREATE TABLE poc_assets (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL,
  platform TEXT,
  asset_type TEXT,
  asset_name TEXT,
  file_path TEXT,
  generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## API Design

### Source System API
```
POST   /api/source-systems
GET    /api/source-systems
GET    /api/source-systems/{id}
DELETE /api/source-systems/{id}
```

### Scan API
```
POST /api/source-systems/{id}/scan
GET  /api/scans/{scan_id}/status
GET  /api/scans/{scan_id}/results
```

### Profiling API
```
POST /api/source-systems/{id}/profile
GET  /api/profiles/{profile_id}
```

### Document API
```
POST /api/documents/upload
POST /api/documents/{id}/extract
GET  /api/documents/{id}/extraction-result
POST /api/documents/{id}/approve
```

### Knowledge Graph API
```
GET /api/graph/entities
GET /api/graph/entity/{id}
GET /api/graph/lineage/{entity_id}
GET /api/graph/issues
```

### Agent API
```
POST /api/agents/analyze
POST /api/agents/recommend
POST /api/agents/generate-poc
GET  /api/agents/jobs/{job_id}
```

### Report API
```
POST /api/reports/generate
GET  /api/reports/{id}
GET  /api/reports/{id}/download
```

---

## Multi-Tenancy Rules

Every database table **must** include `tenant_id UUID NOT NULL`.

Every API query **must** filter by the authenticated user's `tenant_id`.

Never return data from one tenant in another tenant's context.

**MVP strategy:** Shared PostgreSQL database with row-level `tenant_id` filtering.
**Enterprise strategy:** Dedicated database + storage container + Key Vault namespace per tenant.

---

## Security Rules

- **Authentication:** Microsoft Entra ID / Google OAuth (MVP: email+password; Enterprise: SAML SSO)
- **Authorization roles:** Platform Admin, Tenant Admin, Consultant, Data Engineer, Business User, Viewer
- **Credentials:** Always store in Azure Key Vault — never in the application database
- **Data mode:** Metadata-first by default. Sample data only with explicit user approval. Never extract full datasets.
- **Transit:** TLS everywhere
- **Rest:** Encryption at rest on all storage
- **Audit:** Log all scan, extraction, approval, and generation events

---

## Background Job Patterns

Use Celery (MVP) or Temporal (production) for all long-running operations:
- Metadata scans
- Data profiling runs
- Document extraction batches
- Agent analysis workflows
- POC generation

Every job must have:
- A `job_id` returned immediately to the client
- A `/status` polling endpoint
- Retry logic with exponential backoff
- Partial completion recovery (resume from last checkpoint)
- Error notifications

---

## Non-Functional Requirements

| Requirement | Target |
|---|---|
| Metadata scan speed | Fast — metadata only, no full data read |
| Profiling mode | Sampling supported (user-configurable % of rows) |
| Document processing | Batch processing supported |
| Graph queries | Respond within 3 seconds |
| Multi-tenant | Full isolation per tenant |
| Async jobs | All long operations run as background jobs |

---

## MVP Build Order (Phases)

### Phase 1 — Foundation (4–6 weeks)
User auth, tenant management, source system registration, PostgreSQL metadata store, basic connector framework (PostgreSQL + SQL Server), metadata scanner, basic dashboard.

### Phase 2 — Data Profiling (4–6 weeks)
Row count, null, duplicate, distinct profiling; PK detection; data quality score; issue dashboard.

### Phase 3 — Document Intelligence (4–8 weeks)
PDF upload, OCR integration, LLM extraction, schema mapping, human review UI, structured output export.

### Phase 4 — Knowledge Graph (4–6 weeks)
Neo4j integration, entity discovery, relationship mapping, graph visualization, graph query API.

### Phase 5 — Agentic Recommendation (6–8 weeks)
Data Architect Agent, BI Agent, AI Readiness Agent, recommendation engine, architecture diagram generator, report generator.

### Phase 6 — POC Generator (8–12 weeks)
Fabric templates, Databricks templates, Power BI semantic model template, notebook generator, deployment package generator.

---

## Absolute Don'ts

- Do not store plain-text credentials in any database table
- Do not extract or store full raw data from client systems without explicit approval
- Do not skip `tenant_id` filtering on any query
- Do not make LLM extraction results final without human review and approval
- Do not run metadata scans synchronously in the API request thread — always queue as background jobs
- Do not hardcode connection strings or API keys in source code

---

## POC Output Package Checklist

Every generated POC must include:
- [ ] Architecture diagram (Mermaid source + rendered PNG/SVG)
- [ ] Data source inventory
- [ ] Data quality report
- [ ] Business entity map
- [ ] Knowledge graph summary
- [ ] Platform recommendation (Fabric or Databricks, with reasoning)
- [ ] Implementation roadmap
- [ ] Fabric / Databricks code templates
- [ ] Power BI semantic model suggestion
- [ ] AI / RAG use case suggestion
- [ ] Cost estimate
- [ ] Risk register

---

## Success Metrics to Track

| Metric | Description |
|---|---|
| Systems connected | Count of source systems successfully connected per tenant |
| Tables scanned | Total metadata tables discovered |
| Issues detected | Data quality issues found |
| Documents extracted | Documents processed through Document Intelligence Engine |
| Entities discovered | Business entities auto-detected |
| POC assets generated | Total generated artifacts per project |
| Time to assessment | Days from first connection to final report delivery |
| Target outcome | Traditional: 4–8 weeks → With Hub: 3–7 days |
