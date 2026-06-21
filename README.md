# Enterprise Data Intelligence Hub

A runnable MVP scaffold for the SaaS data discovery and POC acceleration platform described in the technical design document.

## What Is Included

- Next.js App Router delivery portal in `apps/web`
- FastAPI backend in `apps/api`
- Tenant-scoped source system, scan, profile, document, graph, agent, POC asset, and report APIs
- SQLAlchemy models for the core PostgreSQL-ready schema
- JWT login, tenant membership validation, RBAC, real source registration, structured file upload validation, scalable profiling, document text extraction, AWS Bedrock-backed AI surfaces, rendered architecture, Neo4j sync hooks, and POC asset generation
- Docker Compose services for API, web, PostgreSQL, Redis, and Neo4j

## Quick Start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r apps/api/requirements.txt
npm install --prefix apps/web
```

Run the API:

```powershell
python -m uvicorn app.main:app --app-dir apps/api --reload --port 8000
```

Run the web portal in another terminal:

```powershell
npm --prefix apps/web run dev
```

Open `http://localhost:3000`.

## API Notes

The API requires login for tenant data. Set a bootstrap admin for local development:

```powershell
$env:DEFAULT_TENANT_ID="11111111-1111-4111-8111-111111111111"
$env:AUTH_JWT_SECRET="replace_with_a_long_random_secret"
$env:BOOTSTRAP_ADMIN_EMAIL="admin@example.com"
$env:BOOTSTRAP_ADMIN_PASSWORD="change_me"
```

Use `/api/auth/login` to get a bearer token. API calls must include `Authorization: Bearer <token>` and the matching `X-Tenant-Id`. Roles are `viewer`, `analyst`, and `admin`.

Long-running operations return a job id immediately and record status, progress, cancellation state, and logs in the `jobs` and `job_logs` tables. The default backend is FastAPI background tasks; `JOB_BACKEND` is reserved for Celery or Temporal wiring.

## Assessment Flow

1. Create or list source systems with `/api/source-systems`.
2. Start a metadata scan with `/api/source-systems/{id}/scan`.
3. Profile data quality with `/api/source-systems/{id}/profile`.
4. Upload/extract/approve documents with `/api/documents/*`.
5. Generate recommendations and POC assets with `/api/agents/recommend` and `/api/agents/generate-poc`.
6. View graph, report, and asset data in the web portal.

## Connect Data Sources

Set the connection string only in the API process environment, then register the source with `env://HUB_SOURCE_URL` in the portal. The app stores the reference, not the credential value. Azure Key Vault references are also supported with `kv://vault-name/secret-name`, `vault://vault-name/secret-name`, or `secret://vault-name/secret-name` when Azure credentials are available to the API process.

```powershell
$env:HUB_SOURCE_URL="postgresql+psycopg://readonly_user:password@localhost:5432/my_database"
python -m uvicorn app.main:app --app-dir apps/api --reload --port 8000
```

In the portal:

- Source name: your database name
- Type: `PostgreSQL`
- Secret reference: `env://HUB_SOURCE_URL`

Then use **Connect Data Source**, **Run Discovery**, **Run AI Assessment**, and **Generate POC Assets**.

Structured files can also be uploaded as connected systems. File validation is tied to the selected system type:

- `CSV`: `.csv`
- `Excel`: `.xlsx`, `.xls`
- `JSON`: `.json`
- `Parquet`: `.parquet`

PDF and image files are not accepted as connected systems.

## Profiling And Metadata

Metadata scans persist tables, columns, indexes, foreign-key relationships, views, and stored procedure placeholders where the connector can discover them. Profiling uses bounded sampling controls:

```powershell
$env:PROFILE_DEFAULT_ROW_LIMIT="10000"
$env:PROFILE_DEFAULT_MAX_COLUMNS="50"
$env:PROFILE_DEFAULT_TIMEOUT_SECONDS="30"
```

Quality scores are calculated from profiled null percentages, distinct-count ratios, freshness signals, validity issues, and relationship consistency.

## Documents

Document extraction reads uploaded file content before calling Bedrock. Supported local text extraction includes text, markdown, CSV, Excel, DOCX, and text-based PDF files. OCR/Textract/Azure Document Intelligence can be added behind the same extraction metadata contract for scanned documents.

## Knowledge Graph

PostgreSQL remains the source of truth for metadata. If Neo4j settings are present, scans also sync source systems, tables, business entities, and dependency relationships to Neo4j:

```powershell
$env:NEO4J_URI="bolt://localhost:7687"
$env:NEO4J_USER="neo4j"
$env:NEO4J_PASSWORD="hub_password"
```

## AWS Bedrock

AI-oriented services call Amazon Bedrock through `bedrock-runtime`. Configure AWS credentials through the standard AWS SDK chain, then set these variables as needed:

```powershell
$env:AWS_BEDROCK_REGION="us-east-1"
$env:AWS_BEDROCK_MODEL_ID="anthropic.claude-3-haiku-20240307-v1:0"
```

## Docker

```powershell
docker compose up --build
```

The Docker profile uses PostgreSQL-compatible configuration. Neo4j and Redis are included for the target architecture.
