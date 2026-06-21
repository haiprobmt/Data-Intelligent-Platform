# Data Intelligent Platform — Practical Test Report

Test date: 2026-06-21  
Repository: `haiprobmt/Data-Intelligent-Platform`  
Tester role: pilot user / QA tester

---

## 1. What I Tried

I attempted three levels of testing:

1. Real local clone and run.
2. Repository inspection through the GitHub connector.
3. Partial executable test reconstruction using current fetched repository files.

---

## 2. Local Clone Result

A direct sandbox clone still failed because the runtime cannot resolve `github.com`.

Result:

```text
fatal: unable to access 'https://github.com/haiprobmt/Data-Intelligent-Platform.git/':
Could not resolve host: github.com
```

This is an environment/network limitation, not necessarily a repository issue.

---

## 3. GitHub Connector Access Result

GitHub connector access works.

The repository is accessible and reports non-zero size.

I was able to fetch and inspect:

```text
README.md
docker-compose.yml
apps/api/requirements.txt
apps/api/app/config.py
apps/api/app/services/auth_tokens.py
apps/api/app/services/uploads.py
apps/api/tests/test_auth_security.py
apps/api/tests/test_uploads.py
apps/api/tests/test_graph.py
```

---

## 4. Partial Executable Test Result

Because direct clone is blocked, I reconstructed the current fetched backend testable files locally:

```text
app/config.py
app/services/auth_tokens.py
app/services/uploads.py
tests/test_auth_security.py
tests/test_uploads.py
```

Then I ran:

```bash
python -m pytest -q
```

Result:

```text
5 passed, 2 warnings in 1.15s
```

The warnings were from PyJWT because the unit test uses `test-secret`, which is shorter than the recommended HMAC key length.

### Passing Tests

| Test | Result |
|---|---|
| JWT round trip requires standard claims | Passed |
| Production environment rejects default JWT secret | Passed |
| Excel source rejects `.csv` file | Passed |
| PDF is allowed for document upload | Passed |
| MIME type rejects unexpected binary | Passed |

---

## 5. Test Findings

## 5.1 Backend Unit Logic Looks Better

The currently fetched unit-testable logic passed for:

- JWT token generation/decoding
- production JWT secret validation
- source file extension validation
- document PDF extension support
- MIME type rejection

This gives confidence that the recent security/upload improvements are moving in the right direction.

---

## 5.2 Repo Still Has a Major Frontend Blocker

The README says the project includes:

```text
Next.js App Router delivery portal in apps/web
```

and the quick start says:

```bash
npm install --prefix apps/web
npm --prefix apps/web run dev
```

Docker Compose also builds:

```yaml
web:
  build:
    context: ./apps/web
```

However, `apps/web/package.json` cannot be fetched and returns `Not Found`.

### Impact

A real user following the README will likely fail when trying to install or run the portal.

### Severity

```text
P0
```

### Required Fix

Commit the frontend implementation or remove/update the frontend instructions.

Minimum expected files:

```text
apps/web/package.json
apps/web/Dockerfile
apps/web/app/layout.tsx
apps/web/app/page.tsx
apps/web/lib/api.ts
apps/web/components/*
```

---

## 5.3 Backend Tests Are Too Small

The repository currently exposes only a few focused tests through search:

```text
test_auth_security.py
test_uploads.py
test_graph.py
```

These are useful but not enough to validate the full application.

### Missing Tests

```text
test_login_flow.py
test_bootstrap_admin.py
test_connection_secrets.py
test_source_system_creation.py
test_source_connection_test.py
test_scan_sqlite_source.py
test_profile_sqlite_source.py
test_document_review_patch.py
test_report_download.py
test_poc_generation.py
test_tenant_isolation.py
```

---

## 5.4 Connection Test Still Needs Full User-Level Validation

A true user flow requires:

```text
Register secret
→ Create source system
→ Test source connection
```

The repository has a connection secret test endpoint, but the important user-facing behavior should be source-system connection testing, not only secret resolution.

Recommended endpoint:

```http
POST /api/source-systems/{source_system_id}/test-connection
```

---

## 5.5 Docker Compose Will Likely Fail Because of `apps/web`

Docker Compose includes API, PostgreSQL, Redis, Neo4j, and Web.

The API build context appears valid:

```text
./apps/api
```

But the web build context appears invalid if `apps/web` is not committed:

```text
./apps/web
```

### Expected failure

```text
unable to prepare context: path "./apps/web" not found
```

---

## 6. Actual User Journey Readiness

| Step | Status | Notes |
|---|---|---|
| Open portal | Blocked | `apps/web` appears missing |
| Login | Backend exists | Needs full API integration test |
| Create project | Backend likely exists | Needs project-scoped flow test |
| Register secret | Backend likely exists | Needs end-to-end test |
| Test connection | Partial | Should test real source connectivity |
| Create source | Backend likely exists | Needs API test |
| Run scan | Backend likely exists | Needs SQLite/Postgres test |
| Run profile | Backend likely exists | Needs SQLite/Postgres test |
| Upload document | Backend likely exists | Upload validation passed unit tests |
| Extract document | Backend likely exists | Needs Bedrock-mocked test |
| Review fields | Backend likely exists | Needs API test |
| Generate report | Backend likely exists | Needs API test |
| Download ZIP | Backend likely exists | Needs API test |
| Docker full stack | Blocked | frontend path issue |

---

## 7. Recommended Immediate Fix

## P0 — Make the App Runnable

### Option A — Commit the Portal

Add the missing `apps/web` implementation.

Minimum frontend:

```text
Login page
Dashboard page
Project page
Source system form
Secret form
Document upload/review page
Report download button
```

### Option B — Backend-Only MVP

If the frontend is not ready, change README and docker-compose:

```text
Remove apps/web from docker-compose
Remove npm install/run commands
Document Swagger UI as first MVP portal
```

Users can then test via:

```text
http://localhost:8000/docs
```

---

## 8. Recommended Smoke Test Script

Add this file:

```text
scripts/smoke_test_api.py
```

It should perform:

```text
1. Login as bootstrap admin
2. Create assessment project
3. Register SQLite connection secret
4. Create SQLite source system
5. Test source connection
6. Run metadata scan
7. Poll job status
8. Run profile
9. Upload sample PDF/text document
10. Extract document
11. Patch extracted fields
12. Approve document
13. Generate recommendations
14. Generate POC assets
15. Download report markdown
16. Download ZIP
```

This will allow you to validate the backend without the frontend.

---

## 9. Final Verdict

The backend is becoming testable and several unit-level checks pass.

However, as an actual user, I still cannot complete the app journey because the documented `apps/web` portal appears missing from the repository.

Current readiness:

```text
Backend logic unit readiness: 75-80%
Backend end-to-end readiness: 60-65%
Frontend readiness: blocked / cannot verify
Full product user readiness: 55-60%
```

Main blocker:

```text
Commit or remove/fix apps/web.
```

Next best move:

```text
Make docker compose up --build work from a clean clone.
```
