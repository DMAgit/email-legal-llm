# Contract Risk Analyzer

Email-driven contract risk analyzer for a take-home style project. The FastAPI
app receives Mailgun-style inbound email webhooks, stores attachments, parses
PDF/image/CSV files, extracts structured contract fields with OpenAI, retrieves
policy context from Azure AI Search, classifies risk, routes the outcome with
deterministic rules, and persists an auditable trail in SQLite.

## Architecture

The app keeps transport, domain logic, infrastructure, and persistence separate:

- `app/api/` exposes health, webhook, process-status, and review endpoints.
- `app/services/` coordinates ingestion, parsing, extraction, retrieval,
  classification, decision, and persistence.
- `app/infra/` contains parser, OpenAI, Azure Search, and SQLite adapters.
- `app/domain/models/` contains Pydantic models for inputs, outputs, and stored
  workflow state.
- `config/models/` and `app/infra/llm/prompts/` hold model and prompt settings.

SQLite stores process runs, email metadata, attachments, parsed documents,
extractions, retrieved context excerpts, classifications, document evaluations,
and review queue items. Logs include `process_id`, `document_id`, `stage`, and
`filename` where relevant.

## Prerequisites

- Python 3.11 or newer
- Optional local OCR/PDF dependencies used by `unstructured[csv,image,pdf]`
- OpenAI credentials for extraction/classification
- Azure AI Search credentials for live retrieval

Tests and parse-only webhook demos do not require live OpenAI or Azure
credentials.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Set secrets in `.env` when you want live extraction, retrieval, or
classification:

```env
OPENAI_API_KEY=
AZURE_SEARCH_ENDPOINT=
AZURE_SEARCH_API_KEY=
AZURE_SEARCH_INDEX_NAME=contract-kb
DATABASE_URL=sqlite:///./data/app.db
MAILGUN_WEBHOOK_SECRET=
```

Model settings live in `config/models/extraction.yaml` and
`config/models/classification.yaml`. Prompt templates live in
`app/infra/llm/prompts/extraction_prompt.yaml` and
`app/infra/llm/prompts/classification_prompt.yaml`.

## Seed Search

Demo policy files live in `data/kb/`. To inspect generated Azure AI Search
documents without uploading:

```powershell
python scripts/seed_search_index.py --dry-run
```

To seed Azure AI Search after setting credentials:

```powershell
python scripts/seed_search_index.py
```

## Run The API

```powershell
uvicorn app.main:app --reload
```

Useful endpoints:

- `GET http://127.0.0.1:8000/health`
- `GET http://127.0.0.1:8000/model-configs`
- `POST http://127.0.0.1:8000/webhooks/mailgun/inbound`
- `GET http://127.0.0.1:8000/processes/{process_id}`
- `GET http://127.0.0.1:8000/reviews`

The process-status endpoint returns bounded parser summaries, extraction fields,
classification, review state, errors, timestamps, and retrieved context
excerpts. It does not return full raw document bodies.

## Test With Postman

Ready-made test contracts live in `data/test files/`. Use Postman to send a
Mailgun-style multipart form request to the local webhook.

Create a `POST` request:

```text
http://127.0.0.1:8000/webhooks/mailgun/inbound
```

Add query params when needed:

- Parse only: no query params
- Extract after parsing: `extract=true`
- Full extraction, retrieval, classification, and routing: `classify=true`

In the Postman `Body` tab, choose `form-data` and add:

| Key | Type | Example |
| --- | --- | --- |
| `sender` | Text | `legal@example.com` |
| `recipient` | Text | `contracts@example.com` |
| `subject` | Text | `Contract review` |
| `body-plain` | Text | `Please review the attached contract.` |
| `attachment-count` | Text | `1` |
| `attachment-1` | File | `data/test files/sample-contract.csv` |

For a PDF test, use one of the PDF files in `data/test files/` as
`attachment-1`. PDF parsing may require the optional local PDF/OCR dependencies
from `unstructured`.

If `MAILGUN_WEBHOOK_SECRET` is set in `.env`, either clear it for local Postman
testing or include valid Mailgun `timestamp`, `token`, and `signature` fields.

The response includes a `process_id`. Inspect the persisted workflow trail at:

```text
http://127.0.0.1:8000/processes/{process_id}
```

For a quick no-credential smoke test, send the request without `classify=true`
and show parsing, process status, and structured logs.

## Tests

```powershell
python -m pytest
```

The tests use temporary SQLite databases and mocked external services where the
workflow would otherwise call OpenAI or Azure AI Search.

## Known Limitations

- The API runs the workflow inline rather than through a background worker.
- Authentication and a full review UI are intentionally out of scope.
- Search seeding requires a pre-created Azure AI Search index.
- OCR quality depends on local `unstructured` and system OCR support.
- The classifier is a demo aid, not legal advice.
