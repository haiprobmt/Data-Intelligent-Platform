# Enterprise Data Intelligence Hub

A runnable MVP scaffold for the SaaS data discovery and POC acceleration platform described in the technical design document.

## What Is Included

- Next.js App Router delivery portal in `apps/web`
- FastAPI backend in `apps/api`
- Tenant-scoped source system, scan, profile, document, graph, agent, POC asset, and report APIs
- SQLAlchemy models for the core PostgreSQL-ready schema
- Real source registration, structured file upload validation, profiling, AWS Bedrock-backed AI surfaces, rendered architecture, and POC asset generation
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

The API enforces tenant scoping through the `X-Tenant-Id` header. If no header is supplied, it uses `DEFAULT_TENANT_ID` for local development.

Long-running operations return a job id immediately and record status in the `jobs` table. The local MVP runs these through FastAPI background tasks; the service layer is shaped so Celery or Temporal can replace that executor later.

## Assessment Flow

1. Create or list source systems with `/api/source-systems`.
2. Start a metadata scan with `/api/source-systems/{id}/scan`.
3. Profile data quality with `/api/source-systems/{id}/profile`.
4. Upload/extract/approve documents with `/api/documents/*`.
5. Generate recommendations and POC assets with `/api/agents/recommend` and `/api/agents/generate-poc`.
6. View graph, report, and asset data in the web portal.

## Connect Data Sources

Set the connection string only in the API process environment, then register the source with `env://HUB_SOURCE_URL` in the portal. The app stores the reference, not the credential value.

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
