# AI SQL Assistant Web App

Production-ready college minor-project starter for an AI-powered PostgreSQL-first SQL agent workspace.

## Architecture

```text
backend/
  app/
    api/        FastAPI route handlers
    agents/     LangGraph node implementations
    graph/      LangGraph workflow wiring
    services/   AI, SQL execution, and schema services
    models/     Pydantic API models and graph state
    db/         SQLAlchemy connection manager
    prompts/    Professional SQL assistant prompts
    utils/      JSON parsing and SQL safety checks
  main.py
  requirements.txt
  .env.example

frontend/
  index.html    Plain HTML SQL workspace
  styles.css    Modern dark responsive UI
  app.js        Browser JavaScript API integration

sql_agent/      Legacy-compatible backend package preserved from existing project
```

## Features

- Clean scrollable SQL pad with AI Review and human-approved execution actions.
- English-to-SQL generation for PostgreSQL by default, with MSSQL still selectable.
- LangGraph workflow with classifier, SQL generation, SQL review, execution, DB Q&A, and error handler nodes.
- FastAPI endpoints: `/api/query/execute`, `/api/query/review`, `/api/query/generate`, `/api/chat`, `/api/schema`.
- SQLAlchemy connection manager for MSSQL and PostgreSQL.
- Schema extraction with in-memory cache.
- Query timeout, max result limit, and basic SQL safety checks.
- Streaming shared-memory agent chat responses via Server-Sent Events.
- Modern responsive dark UI built with only HTML, CSS, and JavaScript.

## Backend Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `backend/.env`:

```env
LLM_PROVIDER=mistral
MISTRAL_API_KEY=your_mistral_key
MISTRAL_MODEL=mistral-large-latest
MSSQL_URL=mssql+pyodbc://username:password@server/database?driver=ODBC+Driver+17+for+SQL+Server
POSTGRES_URL=postgresql+psycopg2://postgres:password@host:5432/database
QUERY_TIMEOUT_SECONDS=30
MAX_RESULT_ROWS=200
SCHEMA_CACHE_SECONDS=300
```

Run backend from the project root:

```bash
uvicorn backend.main:app --reload --port 8000
```

## Frontend Setup

No Node.js or npm is required. Start a simple static file server:

```bash
cd frontend
python3 -m http.server 3000
```

Open `http://localhost:3000`.

The frontend calls the backend at `http://127.0.0.1:8000`. If you change the backend port, update `API_BASE_URL` in `frontend/app.js`.

## API Examples

```bash
curl -X POST http://127.0.0.1:8000/api/query/execute \
  -H 'Content-Type: application/json' \
  -d '{"query":"SELECT * FROM your_table LIMIT 10","database":{"type":"postgresql"}}'
```

```bash
curl -X POST http://127.0.0.1:8000/api/query/generate \
  -H 'Content-Type: application/json' \
  -d '{"question":"Show top 10 customers by revenue"}'
```

## Notes

- Keep real keys only in `.env` files. Do not commit secrets.
- The app prefers Mistral when `LLM_PROVIDER=mistral`; OpenAI is supported as fallback by setting `LLM_PROVIDER=openai` and `OPENAI_API_KEY`.
- Install the Microsoft ODBC Driver 17 or 18 only if you plan to use MSSQL Server via `pyodbc`.
- PostgreSQL is selected by default; use the database dropdown only when switching to MSSQL Server.
- Existing legacy files (`agent.py`, `webapp.py`, `Sqlconnect.py`, `sql_agent/`) are preserved for backward compatibility.
- Frontend intentionally uses plain HTML/CSS/JavaScript for older systems without Node.js/npm.
