# Contract Risk Analyzer

Email-driven contract risk analyzer for a take-home style project. The FastAPI app receives Mailgun-compatible inbound email webhooks, stores attachments, parses PDF, image, and CSV files, extracts structured contract fields with OpenAI, retrieves policy context from Azure AI Search, classifies risk, routes the outcome with deterministic rules, and persists an auditable trail in SQLite.

## Architecture

The app keeps transport, domain logic, infrastructure, and persistence clearly separated:

- `app/api/` exposes health, webhook, process-status, and review endpoints.
- `app/services/` coordinates ingestion, parsing, extraction, retrieval,
  classification, decision, and persistence.
- `app/infra/` contains parser, OpenAI, Azure AI Search, and SQLite adapters.
- `app/domain/models/` contains Pydantic models for inputs, outputs, and stored
  workflow state.
- `config/models/` and `app/infra/llm/prompts/` hold model and prompt settings.

SQLite stores process runs, email metadata, attachments, parsed documents, extractions, retrieved context excerpts, classifications, document evaluations, and review queue items. Logs include `process_id`, `document_id`, `stage`, and `filename` where relevant.

## Features

- Mailgun-compatible inbound email webhook
- Attachment handling for PDF, image, and CSV files
- File parsing with structured parser output and confidence hints
- Structured contract extraction with OpenAI
- Retrieval-augmented validation using Azure AI Search
- Deterministic routing to:
  - `auto_store`
  - `procurement_review`
  - `legal_review`
  - `manual_review`
- Auditable persistence in SQLite
- Process status and review queue endpoints for inspection
- In-process `/metrics` endpoint with HTTP counters and OpenAI request volume

## Prerequisites

- Python 3.11 or newer
- Optional local OCR/PDF dependencies used by `unstructured[csv,image,pdf]`
- OpenAI credentials for live extraction/classification
- Azure AI Search credentials for live retrieval and KB seeding

Tests and parse-only webhook demos do not require live OpenAI or Azure credentials.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Set secrets in `.env` when you want live extraction, retrieval, or classification:

```env
OPENAI_API_KEY=
AZURE_SEARCH_ENDPOINT=
AZURE_SEARCH_API_KEY=
AZURE_SEARCH_INDEX_NAME=contract-kb
DATABASE_URL=sqlite:///./data/app.db
MAILGUN_WEBHOOK_SECRET=
```

Model settings live in:

* `config/models/extraction.yaml`
* `config/models/classification.yaml`

Prompt templates live in:

* `app/infra/llm/prompts/extraction_prompt.yaml`
* `app/infra/llm/prompts/classification_prompt.yaml`

## RAG Knowledge Base

Demo policy and reference files live in `data/kb/` and are used to seed Azure AI Search. The KB includes:

* contract review policy
* clause library
* escalation matrix
* vendor reference data
* historical review examples
* legal playbook guidance

### How Retrieval Works

RAG search starts after structured extraction. The app does not generate or use
pregenerated search questions; instead, it uses the non-empty extracted contract
fields as search queries, such as liability, payment terms, data usage,
termination, renewal, governing law, vendor name, and contract type.

Each query runs through Azure AI Search as hybrid keyword plus vector search,
with clause-type filters where available. The best KB chunks are deduplicated,
ranked, saved for auditability, and passed to the classifier as policy context.

To inspect generated Azure AI Search documents without uploading:

```powershell
python scripts/seed_search_index.py --dry-run
```

To seed Azure AI Search after setting credentials:

```powershell
python scripts/seed_search_index.py
```

## Run the API

```powershell
uvicorn app.main:app --reload
```

Useful endpoints:

* `GET http://127.0.0.1:8000/health`
* `GET http://127.0.0.1:8000/metrics`
* `GET http://127.0.0.1:8000/model-configs`
* `POST http://127.0.0.1:8000/webhooks/mailgun/inbound`
* `GET http://127.0.0.1:8000/processes/{process_id}`
* `GET http://127.0.0.1:8000/reviews`

The process-status endpoint returns bounded parser summaries, extraction fields, retrieved context excerpts, classification, review state, timestamps, and errors. It does not return full raw document bodies.

The metrics endpoint returns runtime uptime, HTTP request counts and durations, and OpenAI chat/embedding call totals, including approximate sent payload characters, input text characters, response text characters, and token usage when the provider returns it.

## Local Testing Without Mailgun

The webhook accepts Mailgun-style multipart form payloads, so local development does not require a live Mailgun account. You can test with Postman, `curl`, or a small helper script.

Ready-made sample contracts live in `data/test files/`.

### Demo Script

After setting `OPENAI_API_KEY`, Azure AI Search settings, and seeding the demo KB, run:

```powershell
.\.venv\Scripts\python.exe scripts\demo_contract_risk.py
```

By default, the script runs the app in-process with temporary uploads and SQLite storage. To send the demo through a running API server and update that server's `/metrics` endpoint, start the API and pass `--base-url`:

```powershell
.\.venv\Scripts\python.exe scripts\demo_contract_risk.py --base-url http://127.0.0.1:8000
```

The script runs the three bundled PDF contracts through the webhook workflow and prints expected versus actual routing:

```text
=== Contract Risk Analyzer Demo ===

[1] Clean SaaS Agreement (Acme Hosting)
→ Expected: auto_store
→ Result: auto_store ✅

[2] Analytics Vendor Contract (BluePeak)
→ Expected: procurement_review
→ Result: procurement_review ⚠️

[3] AI Vendor Contract (DataForge)
→ Expected: legal_review
→ Result: legal_review 🚨
```

### Postman

Create a `POST` request to:

```text
http://127.0.0.1:8000/webhooks/mailgun/inbound
```

Optional query params:

* Parse only: no query params
* Extract after parsing: `extract=true`
* Full extraction, retrieval, classification, and routing: `classify=true`

In the Postman `Body` tab, choose `form-data` and add:

| Key                | Type | Example                                                             |
| ------------------ | ---- | ------------------------------------------------------------------- |
| `sender`           | Text | `legal@example.com`                                                 |
| `recipient`        | Text | `contracts@example.com`                                             |
| `subject`          | Text | `Contract review`                                                   |
| `body-plain`       | Text | `Please review the attached contract.`                              |
| `attachment-count` | Text | `1`                                                                 |
| `attachment-1`     | File | `data/test files/saas_master_services_agreement_northstar_acme.pdf` |

For a CSV or image test, swap the file used for `attachment-1`.

If `MAILGUN_WEBHOOK_SECRET` is set in `.env`, either clear it for local Postman testing or include valid Mailgun `timestamp`, `token`, and `signature` fields.

### curl

Example local request:

```bash
curl -X POST "http://127.0.0.1:8000/webhooks/mailgun/inbound?classify=true" \
  -F "sender=legal@example.com" \
  -F "recipient=contracts@example.com" \
  -F "subject=Contract review" \
  -F "body-plain=Please review the attached contract." \
  -F "attachment-count=1" \
  -F "attachment-1=@data/test files/saas_master_services_agreement_northstar_acme.pdf"
```

The response includes a `process_id`. Inspect the persisted workflow trail at:

```text
http://127.0.0.1:8000/processes/{process_id}
```

For a quick no-credential smoke test, send the request without `classify=true` and use the process endpoint plus logs to show parsing and persistence.

## Workflow Modes

The webhook supports different levels of processing for development and demo use:

* **Parse only**: store email and attachment metadata, parse document text
* **Extract**: parse and run structured contract extraction
* **Classify**: parse, extract, retrieve policy context, classify risk, apply
  routing, and persist the full evaluation trail

This makes it easy to demo the pipeline incrementally.

## Example Outcome

A successful clean-contract evaluation returns:

* extracted contract fields such as vendor name, payment terms, liability,
  termination, renewal, governing law, and data usage
* retrieved supporting KB chunks from Azure AI Search
* a structured classification result
* a final routed action such as `auto_store`

For clean aligned contracts, the expected result is typically:

* `risk_level: low`
* `recommended_action: auto_store`
* `rationale`: evidence-backed bullets such as payment alignment, liability cap,
  data-use limits, termination rights, and approved vendor status
* `clause_evaluations`: per-clause risk and reason entries for terms such as
  `payment_terms`, `liability`, and `data_usage`
* `policy_conflicts`: structured conflict objects with `clause_type` and
  `issue` when retrieved policy context supports a mismatch

## Tests

```powershell
python -m pytest
```

The tests use temporary SQLite databases and mocked external services where the workflow would otherwise call OpenAI or Azure AI Search.

## Known Limitations

* The API runs the workflow inline rather than through a background worker.
* Authentication and a full review UI are intentionally out of scope.
* OCR quality depends on local `unstructured` and system OCR support.
* Retrieval quality depends on the seeded Azure AI Search knowledge base.
* Classification is intended as a workflow demo aid, not legal advice.
