# Hirewise

Hirewise is a full-stack recruitment workflow MVP built with React, FastAPI, PostgreSQL, and Python NLP. It covers recruiter registration and login, job management, resume intake and parsing, explainable candidate matching, pipeline stages, and database-backed dashboard analytics.

## Run locally with Docker

Requirements: Docker Desktop with Compose enabled.

1. Review the local-only database password and JWT secret in docker-compose.yml. Change both before any shared or deployed use.
2. From the project root, run: docker compose up --build
3. Open http://localhost:5173 and create a recruiter account.
4. Create a job, then add candidate resumes from Candidates or Jobs.
5. FastAPI docs are at http://localhost:8000/docs.

PostgreSQL and uploads are stored in Compose volumes. docker compose down stops services; docker compose down -v also removes the local database and uploaded resumes.

### Local fallback when Docker is unavailable

For local development without Docker or a PostgreSQL server, SQLite can be used as a temporary database. Install backend requirements with backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt, and install frontend packages with npm install from the frontend directory.

In a backend PowerShell terminal:

    cd backend
    $env:DATABASE_URL = "sqlite:///../work/hirewise-local.sqlite"
    $env:JWT_SECRET = "local-development-only-change-before-deployment"
    $env:UPLOAD_DIR = "../work/uploads"
    .\.venv\Scripts\Activate.ps1
    uvicorn app.main:app --reload --port 8000

In a second frontend terminal:

    cd frontend
    $env:VITE_API_URL = "http://localhost:8000"
    npm run dev -- --host 0.0.0.0

This fallback keeps local data in work/hirewise-local.sqlite and is for development only. Docker Compose remains the PostgreSQL setup.

## Run without Docker

Start PostgreSQL and create a database named recruitment. Configure DATABASE_URL, JWT_SECRET, UPLOAD_DIR, and CORS_ORIGINS using .env.example.

Backend (Python 3.11+):

    cd backend
    python -m venv .venv
    .venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    uvicorn app.main:app --reload --port 8000

Frontend (Node 20+), in a second terminal:

    cd frontend
    npm install
    npm run dev

Set VITE_API_URL if the API is not at http://localhost:8000.

## Deploy the backend on Render

Configure the backend Web Service with **Root Directory** `backend`, **Build Command** `pip install -r requirements.txt`, and **Start Command** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.

In the Render Environment settings, set `DATABASE_URL` to the **Internal Database URL** copied from your Render PostgreSQL database. The app accepts Render's `postgres://` or `postgresql://` URL and normalizes it for the installed psycopg v3 driver. Also set `JWT_SECRET` to a long, unique random value and `CORS_ORIGINS` to your deployed frontend origin. Do not use a localhost URL for the Render database. Save the settings, then use **Manual Deploy → Deploy latest commit**.

## Working features

- Recruiter registration and login, bcrypt password hashes, signed JWT sessions, and recruiter-scoped data.
- Job creation, editing through the API, activation/deactivation via job status, and deletion.
- PDF, DOCX, and TXT resume extraction, exact duplicate-file detection per job, curated technical skill recognition, and experience estimate from explicit phrases.
- Transparent 0–100 matching score: required skill coverage 35%, experience 25%, TF-IDF contextual similarity 30%, preferred skill coverage 10%. The breakdown includes matched/missing required skills and a human review explanation.
- Ranked candidates, name/email/role/skill search, pipeline stage filter, status updates with audit records, resume download API, and pipeline stages.
- Dashboard metrics and charts read from PostgreSQL. Empty states are shown when no applications exist.

Protected or sensitive personal attributes are not extracted or scored. The score is a decision-support indicator and must not be used for automatic rejection or selection.

## API endpoints

- POST /api/auth/register, POST /api/auth/login, GET /api/auth/me
- GET/POST /api/jobs, PUT/DELETE /api/jobs/{id}
- GET /api/applications, POST /api/jobs/{id}/applications
- PATCH /api/applications/{id}/status
- GET /api/applications/{id}/resume, GET /api/applications/{id}/summary
- GET /api/dashboard, GET /api/health

Send Authorization: Bearer <access_token> to authenticated routes. See /docs for request schemas.

## Scope and production work

This is a working core workflow, not the complete production platform in the source brief. Candidate self-service accounts and portal, password reset, admin roles, interviews and feedback, configurable score weights, Sentence Transformers semantic matching, data-grounded chat assistant, outbound email, and PDF/Excel report exports are not implemented. Legacy DOC files are rejected with conversion guidance. The candidate summary is extracted from resume text, not generated by an LLM. Matching currently uses TF-IDF similarity, not a transformer model.

Before production, add versioned Alembic migrations, managed secrets, TLS, malware scanning, retention and deletion workflows, backups, rate limiting, and security review. No sample resumes are bundled; use consented test resumes.
