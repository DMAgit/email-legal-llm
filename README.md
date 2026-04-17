# Contract Risk Analyzer

Email-driven contract risk analyzer foundation for a take-home style project.

The current milestone accepts inbound Mailgun-style email webhooks, stores
attachments locally, detects PDF/image/CSV files, parses attachments into
normalized raw text and chunks, and can extract structured contract fields
through the OpenAI API.

## Local Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

Copy `.env.example` to `.env` if you need to reset local defaults. The checked-in
`.env` contains only empty secret placeholders for this milestone.

## Run

```powershell
uvicorn app.main:app --reload
```

Then open:

- `GET http://127.0.0.1:8000/health`
- `GET http://127.0.0.1:8000/model-configs`
- `POST http://127.0.0.1:8000/webhooks/mailgun/inbound`

The Mailgun webhook expects multipart form fields such as `sender`,
`recipient`, `subject`, `body-plain`, and one or more file fields like
`attachment-1`. If `MAILGUN_WEBHOOK_SECRET` is configured, requests must also
include Mailgun `timestamp`, `token`, and `signature` fields. Files are stored
under `data/uploads/{process_id}/`.

Attachment parsing and chunking use the Unstructured open source library.
Image/PDF OCR quality depends on the local Unstructured extras and system OCR
support available on the host.

Structured extraction uses `config/models/extraction.yaml`,
`app/infra/llm/prompts/extraction_prompt.yaml`, and the OpenAI SDK. Set
`OPENAI_API_KEY` in `.env` before calling extraction.

Demo a parsed document directly:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/extractions/contract `
  -ContentType application/json `
  -Body (@{
    document_id = "demo-doc"
    filename = "contract.txt"
    file_type = "txt"
    parser_name = "manual"
    raw_text = "Vendor: Acme Corp`nPayment Terms: Net 60"
  } | ConvertTo-Json)
```

Or ask the Mailgun webhook to extract after parsing:

```powershell
POST http://127.0.0.1:8000/webhooks/mailgun/inbound?extract=true
```

## Tests

```powershell
python -m pytest
```

Runtime-only installs can use `requirements.txt`.
